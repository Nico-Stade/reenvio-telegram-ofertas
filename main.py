"""
main.py — Punto de entrada del Telegram Deal Forwarder Pro (Multi-canal y Multi-proveedor).

Uso:
  python main.py              → Escucha en tiempo real todos los canales configurados (event-driven, 0ms)
  python main.py --backfill 20 → Analiza los últimos 20 mensajes de cada canal
  python main.py --backfill 20 --channel -1001815551781 → Analiza los últimos 20 de un canal específico
  python main.py --dry-run    → Modo simulación (no envía mensajes al bot)
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

from core.database import SQLiteDealRepository
from engine.parser import get_parser, BunnyDealParser, BaseDealParser
from engine.filters.base import BaseFilter
from engine.filters.discount import MinDiscountFilter
from engine.filters.history import StrictHistoricalLowFilter
from engine.filters.dedup import DeduplicationFilter
from engine.filters.store import StoreFilter
from engine.filters.pipeline import FilterPipeline
from engine.formatters.embed_formatter import EmbedMessageFormatter
from engine.dispatchers.bot_dispatcher import TelegramBotDispatcher
from engine.listener import DealForwarderEngine, ChannelSourceConfig
from core.client import build_client

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"No se encontró {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_bot_tokens(config: dict) -> list[str]:
    """Obtiene los tokens del bot desde .env o config.json."""
    env_tokens = os.getenv("BOT_TOKEN", "") or os.getenv("BOT_TOKENS", "")
    if env_tokens:
        return [t.strip() for t in env_tokens.split(",") if t.strip()]

    cfg_tokens = config.get("bot_tokens", [])
    if isinstance(cfg_tokens, str):
        return [cfg_tokens.strip()]
    return [t.strip() for t in cfg_tokens if t and t.strip()]


def build_pipeline_from_dict(filters_cfg: dict, repo: SQLiteDealRepository) -> FilterPipeline:
    """Construye un FilterPipeline a partir de un diccionario de configuración de filtros."""
    filters_list: list[BaseFilter] = []

    # 1. Filtro de Tiendas (Whitelist / Blacklist)
    allowed = filters_cfg.get("allowed_stores", [])
    blocked = filters_cfg.get("blocked_stores", [])
    if allowed or blocked:
        filters_list.append(StoreFilter(allowed_stores=allowed, blocked_stores=blocked))

    # 2. Filtro de Descuento Mínimo y Límites de Precio
    min_disc = filters_cfg.get("min_discount", 60)
    min_p = filters_cfg.get("min_price")
    max_p = filters_cfg.get("max_price")
    filters_list.append(MinDiscountFilter(min_discount=min_disc, min_price=min_p, max_price=max_p))

    # 3. Filtro Anti-Ruido: Mínimo Histórico Estricto
    if filters_cfg.get("strict_historical_low", True):
        allow_no_hist = filters_cfg.get("allow_no_history", False)
        min_disc_no_hist = filters_cfg.get("min_discount_if_no_history", 80)
        min_drop = filters_cfg.get("min_drop_percentage", 60.0)
        filters_list.append(
            StrictHistoricalLowFilter(
                allow_no_history=allow_no_hist,
                min_discount_if_no_history=min_disc_no_hist,
                min_drop_percentage=min_drop,
            )
        )

    # 4. Filtro de Deduplicación
    window_h = filters_cfg.get("dedup_window_hours", 12)
    if window_h > 0:
        filters_list.append(DeduplicationFilter(repository=repo, window_hours=window_h))

    return FilterPipeline(filters_list)


def build_sources(config: dict, repo: SQLiteDealRepository) -> list[ChannelSourceConfig]:
    """Crea la lista de configuraciones de fuentes con sus respectivos parsers y pipelines."""
    sources_cfg = config.get("sources", [])
    global_filters = config.get("filters", {})

    sources: list[ChannelSourceConfig] = []

    if sources_cfg and isinstance(sources_cfg, list):
        for item in sources_cfg:
            cid = str(item.get("channel_id", "")).strip()
            if not cid:
                continue
            name = item.get("name", cid)
            parser_type = item.get("parser", "bunny")
            parser = get_parser(parser_type)

            merged_filters = dict(global_filters)
            if "filters" in item and isinstance(item["filters"], dict):
                merged_filters.update(item["filters"])

            pipeline = build_pipeline_from_dict(merged_filters, repo)
            sources.append(ChannelSourceConfig(
                channel_id=cid,
                name=name,
                parser=parser,
                pipeline=pipeline,
            ))

    # Retrocompatibilidad para 'source_channel' como string único
    if not sources and "source_channel" in config:
        cid = str(config["source_channel"]).strip()
        pipeline = build_pipeline_from_dict(global_filters, repo)
        sources.append(ChannelSourceConfig(
            channel_id=cid,
            name="Canal Principal",
            parser=BunnyDealParser(),
            pipeline=pipeline,
        ))

    return sources


async def main():
    args = sys.argv[1:]
    is_dry_run = "--dry-run" in args
    backfill_limit = None
    target_channel = None

    if "--backfill" in args:
        idx = args.index("--backfill")
        try:
            backfill_limit = int(args[idx + 1])
        except (IndexError, ValueError):
            backfill_limit = 15

    if "--channel" in args:
        idx = args.index("--channel")
        try:
            target_channel = args[idx + 1]
        except IndexError:
            pass

    config = load_config()
    destination_channel = config["destination_channel"]
    bot_tokens = get_bot_tokens(config)

    if not bot_tokens and not is_dry_run:
        logger.error(
            "⚠️ No se encontró ningún BOT_TOKEN en el archivo .env ni en config.json.\n"
            "Agregá BOT_TOKEN=tu_token en .env para poder despachar mensajes con el bot."
        )
        return

    repo = SQLiteDealRepository()
    sources = build_sources(config, repo)

    if not sources:
        logger.error("⚠️ No hay canales fuente configurados en 'sources' ni 'source_channel'.")
        return

    logger.info("=" * 65)
    logger.info("🚀 INICIANDO TELEGRAM DEAL FORWARDER PRO (MULTI-CANAL)")
    logger.info(f"Canales Fuente : {len(sources)} activo(s):")
    for s in sources:
        logger.info(f"   • {s.name} ({s.channel_id}) -> Parser: {type(s.parser).__name__}")
    logger.info(f"Canal Destino  : {destination_channel}")
    logger.info(f"Tokens Bot     : {len(bot_tokens)} configurado(s)")
    logger.info(f"Modo Dry Run   : {is_dry_run}")
    logger.info("=" * 65)

    formatter = EmbedMessageFormatter()

    if is_dry_run:
        class DummyDispatcher:
            async def dispatch(self, deal):
                logger.info(f"[DRY-RUN] Simulado envío de '{deal.title}' a {destination_channel}")
                return True
        dispatcher = DummyDispatcher()
    else:
        dispatcher = TelegramBotDispatcher(
            bot_tokens=bot_tokens,
            destination_chat_id=destination_channel,
            formatter=formatter,
            include_inline_button=config.get("options", {}).get("include_inline_button", True),
            show_above_text=config.get("options", {}).get("show_above_text", False),
        )

    telethon_client = build_client()

    async with telethon_client:
        if not await telethon_client.is_user_authorized():
            logger.info("Iniciando autenticación interactiva...")
            await telethon_client.start()

        me = await telethon_client.get_me()
        logger.success(f"Conectado como usuario: {me.first_name} (@{me.username})")

        engine = DealForwarderEngine(
            telethon_client=telethon_client,
            dispatcher=dispatcher,
            repository=repo,
            sources=sources,
        )

        try:
            if backfill_limit is not None or is_dry_run:
                limit = backfill_limit or 15
                logger.info(f"Ejecutando backfill de los últimos {limit} mensajes...")
                await engine.run_backfill(limit=limit, target_channel=target_channel)
                return

            # Modo en vivo continuo (eventos en tiempo real)
            logger.info("Iniciando escucha en tiempo real. Presioná Ctrl+C para salir.")
            await engine.run_live()
        finally:
            await engine.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Forwarder detenido.")
