"""
test_200.py — Script de testing especializado:
Analiza los últimos 200 mensajes del canal y solo procesa/envía si el precio
actual es MUCHO MENOR al mínimo histórico registrado (filtra todo el ruido).

Uso:
  python test_200.py              → Analiza 200 mensajes y envía al canal Testing los que caigan >= 25% vs su mínimo
  python test_200.py --dry-run    → Solo muestra en consola la tabla de ofertas filtradas sin enviar nada
  python test_200.py --min-drop 30 → Solo ofertas que hayan caído al menos un 30% respecto a su mínimo histórico
"""
import asyncio
import sys
import argparse
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

from core.client import build_client, parse_peer as _parse_peer
from engine.parser import BunnyDealParser
from engine.formatters.embed_formatter import EmbedMessageFormatter
from engine.dispatchers.bot_dispatcher import TelegramBotDispatcher
from main import load_config, get_bot_tokens


async def run_testing_200(min_drop: float = 25.0, dry_run: bool = False, limit: int = 200):
    config = load_config()
    source_channel = config.get("source_channel", "-1002230433964")
    destination_channel = config.get("destination_channel", "-1003952548471")
    bot_tokens = get_bot_tokens(config)

    logger.info("=" * 75)
    logger.info("🔍 INICIANDO TESTING DE 200 MENSAJES (FILTRADO AGRESIVO ANTI-RUIDO)")
    logger.info(f"Canal Fuente      : {source_channel}")
    logger.info(f"Canal Destino     : {destination_channel}")
    logger.info(f"Umbral de Caída   : >= {min_drop}% MENOR que el mínimo histórico")
    logger.info(f"Modo Dry-Run      : {dry_run}")
    logger.info("=" * 75)

    parser = BunnyDealParser()
    formatter = EmbedMessageFormatter()

    if not dry_run:
        if not bot_tokens:
            logger.error("No se encontró BOT_TOKEN en el entorno para despachar.")
            return
        dispatcher = TelegramBotDispatcher(
            bot_tokens=bot_tokens,
            destination_chat_id=destination_channel,
            formatter=formatter,
            include_inline_button=config.get("options", {}).get("include_inline_button", True),
            show_above_text=config.get("options", {}).get("show_above_text", False),
        )
    else:
        dispatcher = None

    client = build_client()

    async with client:
        if not await client.is_user_authorized():
            await client.start()

        entity = await client.get_entity(_parse_peer(source_channel))
        title = getattr(entity, "title", source_channel)
        logger.info(f"Descargando los últimos {limit} mensajes de '{title}'...")

        messages = await client.get_messages(entity, limit=limit)
        sorted_messages = sorted(messages, key=lambda m: m.id)

    total_parsed = 0
    discarded_no_hist = 0
    discarded_noise = 0
    approved_deals = []

    for m in sorted_messages:
        if not m.text:
            continue

        deal = parser.parse(m.id, m.text, source_channel)
        if not deal:
            continue

        total_parsed += 1
        min_hist = deal.previous_historical_low

        # 1. Descartar si no tiene historial verificable
        if min_hist is None:
            discarded_no_hist += 1
            continue

        # 2. Descartar si el precio actual es mayor o apenas igual al histórico
        if deal.offer_price >= min_hist:
            discarded_noise += 1
            continue

        # 3. Filtrar agresivamente: La caída DEBE ser mucho menor al histórico (>= min_drop)
        drop = deal.discount_vs_history or 0.0
        if drop < min_drop:
            discarded_noise += 1
            continue

        # ¡CALIFICA COMO VERDADERA OFERTA BOMBA!
        approved_deals.append(deal)

    # Ordenar las aprobadas de mayor a menor caída porcentual
    approved_deals.sort(key=lambda d: d.discount_vs_history or 0.0, reverse=True)

    print("\n" + "=" * 80)
    print(f"{'CAÍDA REAL':<14} | {'OFERTA':<10} | {'MÍN HIST':<10} | {'TIENDA':<10} | {'PRODUCTO'}")
    print("=" * 80)

    for d in approved_deals:
        print(f"-{d.discount_vs_history:>4.1f}% menos  | ${d.offer_price:<9,} | ${d.previous_historical_low:<9,} | {d.store or '—':<10} | {d.title[:42]}")

    print("=" * 80)
    print(f"\n📊 RESULTADOS DEL ANÁLISIS:")
    print(f"Total mensajes analizados           : {len(sorted_messages)}")
    print(f"Ofertas parseadas correctamente     : {total_parsed}")
    print(f"Descartadas por no tener historial  : {discarded_no_hist}")
    print(f"Descartadas por ruido (caída < {min_drop}%): {discarded_noise}")
    print(f"🌟 OFERTAS BOMBA SELECCIONADAS      : {len(approved_deals)}\n")

    if dry_run or not approved_deals:
        if dry_run:
            logger.info("Modo dry-run finalizado. Ningún mensaje fue enviado al canal.")
        return

    # Despachar las ofertas aprobadas al canal de Testing
    logger.info(f"Enviando {len(approved_deals)} ofertas seleccionadas como EMBED a {destination_channel}...")
    sent_count = 0

    for deal in approved_deals:
        success = await dispatcher.dispatch(deal)
        if success:
            sent_count += 1
            # Pausa breve para evitar flood
            await asyncio.sleep(1.2)

    logger.success(f"Testing completado con éxito: {sent_count}/{len(approved_deals)} embeds enviados a {destination_channel}!")


def main():
    arg_parser = argparse.ArgumentParser(description="Testing de 200 mensajes con filtro agresivo de caída vs histórico.")
    arg_parser.add_argument("--min-drop", type=float, default=40.0, help="Porcentaje mínimo de caída respecto al récord histórico (default: 25.0)")
    arg_parser.add_argument("--dry-run", action="store_true", help="Solo analizar y listar sin enviar al bot")
    arg_parser.add_argument("--limit", type=int, default=200, help="Cantidad de mensajes a inspeccionar (default: 200)")
    args = arg_parser.parse_args()

    asyncio.run(run_testing_200(min_drop=args.min_drop, dry_run=args.dry_run, limit=args.limit))


if __name__ == "__main__":
    main()
