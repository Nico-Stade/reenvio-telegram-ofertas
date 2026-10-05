"""
main.py — Punto de entrada del Telegram Deal Forwarder Pro.

Uso:
  python main.py              → Escucha en tiempo real (event-driven, 0ms latency)
  python main.py --backfill 20 → Analiza los últimos 20 mensajes y reenvía los que pasen filtros
  python main.py --dry-run    → Analiza sin enviar al bot (muestra qué pasaría y qué se descartaría)
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
from engine.parser import BunnyDealParser
from engine.filters.base import BaseFilter
from engine.filters.discount import MinDiscountFilter
from engine.filters.history import StrictHistoricalLowFilter
from engine.filters.dedup import DeduplicationFilter
from engine.filters.store import StoreFilter
from engine.filters.pipeline import FilterPipeline
from engine.formatters.embed_formatter import EmbedMessageFormatter
from engine.dispatchers.bot_dispatcher import TelegramBotDispatcher
from engine.listener import DealForwarderEngine
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


def build_pipeline(config: dict, repo: SQLiteDealRepository) -> FilterPipeline:
    filters_cfg = config.get("filters", {})
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
        min_drop = filters_cfg.get("min_drop_percentage", 20.0)
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


async def main():
    args = sys.argv[1:]
    is_dry_run = "--dry-run" in args
    backfill_limit = None

    if "--backfill" in args:
        idx = args.index("--backfill")
        try:
            backfill_limit = int(args[idx + 1])
        except (IndexError, ValueError):
            backfill_limit = 15

    config = load_config()
    source_channel = config["source_channel"]
    destination_channel = config["destination_channel"]
    bot_tokens = get_bot_tokens(config)

    if not bot_tokens and not is_dry_run:
        logger.error(
            "⚠️ No se encontró ningún BOT_TOKEN en el archivo .env ni en config.json.\n"
            "Agregá BOT_TOKEN=tu_token en .env para poder despachar mensajes con el bot."
        )
        return

    logger.info("=" * 60)
    logger.info("🚀 INICIANDO TELEGRAM DEAL FORWARDER PRO")
    logger.info(f"Canal Fuente  : {source_channel}")
    logger.info(f"Canal Destino : {destination_channel}")
    logger.info(f"Tokens Bot    : {len(bot_tokens)} configurado(s)")
    logger.info(f"Modo Dry Run  : {is_dry_run}")
    logger.info("=" * 60)

    repo = SQLiteDealRepository()
    parser = BunnyDealParser()
    pipeline = build_pipeline(config, repo)
    formatter = EmbedMessageFormatter()

    # Si es dry-run, podemos usar un dispatcher simulado que solo loguea
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

    # Iniciar cliente Telethon para escuchar
    telethon_client = build_client()

    async with telethon_client:
        if not await telethon_client.is_user_authorized():
            logger.info("Iniciando autenticación interactiva...")
            await telethon_client.start()

        me = await telethon_client.get_me()
        logger.success(f"Conectado como usuario: {me.first_name} (@{me.username})")

        engine = DealForwarderEngine(
            telethon_client=telethon_client,
            source_channel=source_channel,
            parser=parser,
            pipeline=pipeline,
            dispatcher=dispatcher,
            repository=repo,
        )

        if backfill_limit is not None or is_dry_run:
            limit = backfill_limit or 15
            logger.info(f"Ejecutando análisis de los últimos {limit} mensajes...")
            await engine.run_backfill(limit=limit)
            return

        # Modo en vivo continuo (eventos en tiempo real)
        logger.info("Iniciando escucha en tiempo real. Presioná Ctrl+C para salir.")
        await engine.run_live()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Forwarder detenido.")
