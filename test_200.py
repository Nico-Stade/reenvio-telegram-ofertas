"""
test_200.py: Script de testing especializado y segmentado por canal.
Analiza los últimos N mensajes de cada canal configurado (o uno en particular),
evaluando la precisión del parser (Bunny, Nypau, etc.) y filtrando ofertas
cuyo precio actual sea MUCHO MENOR a su récord histórico.

POR DEFECTO NO ENVÍA MENSAJES AL CANAL (Modo Seguro / Análisis).
Para despachar al canal de destino, pasar explícitamente el flag `--send`.

Uso:
  python test_200.py                         -> Analiza todos los canales en config.json (sin enviar)
  python test_200.py --bunny                 -> Analiza únicamente los canales de Bunny
  python test_200.py -c -1002230433964       -> Analiza un canal específico por ID o nombre
  python test_200.py --min-drop 30           -> Filtra caídas >= 30% respecto al mínimo histórico
  python test_200.py --limit 50              -> Analiza los últimos 50 mensajes por canal
  python test_200.py --send                  -> Despacha las ofertas aprobadas al canal de destino
"""
import asyncio
import sys
import argparse
from pathlib import Path
from typing import Optional, List, Dict
from loguru import logger
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows terminals
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Reconfigure loguru sink for UTF-8 clean output
logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
)

load_dotenv()

from core.client import build_client, parse_peer as _parse_peer
from engine.parser import get_parser, detect_parser, BaseDealParser
from engine.formatters.embed_formatter import EmbedMessageFormatter
from engine.dispatchers.bot_dispatcher import TelegramBotDispatcher
from main import load_config, get_bot_tokens


def resolve_channels_to_test(config: dict, target: Optional[str] = None, bunny_only: bool = False) -> List[dict]:
    """Resuelve la lista de canales a testear a partir de config.json y argumentos CLI."""
    sources = config.get("sources", [])
    if not sources and "source_channel" in config:
        sources = [{
            "channel_id": str(config["source_channel"]),
            "name": "Canal Principal",
            "parser": "bunny"
        }]

    if bunny_only:
        sources = [s for s in sources if s.get("parser", "bunny").lower() == "bunny"]

    if not target:
        return sources

    target_clean = target.strip().lower()
    matched = []
    for s in sources:
        cid = str(s.get("channel_id", "")).strip().lower()
        cname = str(s.get("name", "")).strip().lower()
        if target_clean == cid or target_clean in cname:
            matched.append(s)

    if matched:
        return matched

    # Si no coincide con ninguno en config.json, creamos una entrada ad-hoc
    return [{
        "channel_id": target.strip(),
        "name": f"Canal Personalizado ({target.strip()})",
        "parser": "bunny" if bunny_only else "auto"
    }]


async def analyze_channel(
    client,
    channel_info: dict,
    limit: int = 200,
    min_drop: float = 25.0,
    force_parser: Optional[str] = None,
) -> Dict:
    """Descarga y analiza los mensajes de un canal específico."""
    cid = str(channel_info.get("channel_id", ""))
    label = channel_info.get("name", cid)
    parser_type = force_parser if force_parser and force_parser != "auto" else channel_info.get("parser", "auto")

    entity = await client.get_entity(_parse_peer(cid))
    real_title = getattr(entity, "title", label)

    logger.info(f"📥 Descargando últimos {limit} mensajes de '{real_title}' ({cid})...")
    messages = await client.get_messages(entity, limit=limit)
    sorted_messages = sorted(messages, key=lambda m: m.id)

    total_with_text = 0
    total_parsed_ok = 0
    discarded_no_hist = 0
    discarded_no_drop = 0
    discarded_min_drop = 0
    approved_deals = []
    stores_count: Dict[str, int] = {}

    for m in sorted_messages:
        if not m.text or not m.text.strip():
            continue

        total_with_text += 1

        if parser_type == "auto":
            parser = detect_parser(m.text)
        else:
            parser = get_parser(parser_type)

        deal = parser.parse(m.id, m.text, cid)
        if not deal:
            continue

        total_parsed_ok += 1
        st = deal.store or "Desconocida"
        stores_count[st] = stores_count.get(st, 0) + 1

        min_hist = deal.previous_historical_low

        # 1. Sin historial previo registrado
        if min_hist is None:
            discarded_no_hist += 1
            continue

        # 2. Precio actual no es menor al mínimo histórico
        if deal.offer_price >= min_hist:
            discarded_no_drop += 1
            continue

        # 3. Caída real menor al umbral exigido (min_drop)
        drop = deal.discount_vs_history or 0.0
        if drop < min_drop:
            discarded_min_drop += 1
            continue

        approved_deals.append(deal)

    approved_deals.sort(key=lambda d: d.discount_vs_history or 0.0, reverse=True)

    return {
        "channel_id": cid,
        "name": label,
        "title": real_title,
        "parser_used": parser_type,
        "total_messages": len(sorted_messages),
        "total_with_text": total_with_text,
        "parsed_ok": total_parsed_ok,
        "discarded_no_hist": discarded_no_hist,
        "discarded_no_drop": discarded_no_drop,
        "discarded_min_drop": discarded_min_drop,
        "approved_deals": approved_deals,
        "stores_count": stores_count,
    }


def print_channel_report(result: Dict, min_drop: float) -> None:
    """Imprime el reporte detallado segmentado de un canal."""
    print("\n" + "=" * 90)
    print(f" 📡 CANAL: {result['title']} (ID: {result['channel_id']})")
    print(f"    Parser: {result['parser_used'].upper()} | Mensajes: {result['total_messages']} | Con texto: {result['total_with_text']}")
    print("=" * 90)

    approved = result["approved_deals"]
    if approved:
        print(f"{'CAÍDA REAL':<14} | {'OFERTA':<10} | {'MÍN HIST':<10} | {'TIENDA':<12} | {'DSCTO':<6} | {'PRODUCTO'}")
        print("-" * 90)
        for d in approved:
            drop_str = f"-{d.discount_vs_history:>4.1f}% menos"
            disc_str = f"{d.discount_percentage}%" if d.discount_percentage else "-"
            store_str = (d.store or "-")[:12]
            title_str = d.title[:36] if d.title else "Sin título"
            tag = " [⚠️ ERROR PRECIO]" if d.is_price_glitch else ""
            print(f"{drop_str:<14} | ${d.offer_price:<9,} | ${d.previous_historical_low:<9,} | {store_str:<12} | {disc_str:<6} | {title_str}{tag}")
        print("-" * 90)
    else:
        print(f"  ℹ️  Ninguna oferta superó el filtro de caída >= {min_drop}% en este lote.")

    print(f"\n  📊 DESGLOSE DEL SEGMENTO:")
    print(f"     • Ofertas parseadas correctamente : {result['parsed_ok']}/{result['total_with_text']} ({round((result['parsed_ok']/result['total_with_text'])*100, 1) if result['total_with_text'] else 0}%)")
    print(f"     • Descartadas por falta de historial: {result['discarded_no_hist']}")
    print(f"     • Descartadas (precio >= mínimo)  : {result['discarded_no_drop']}")
    print(f"     • Descartadas (caída < {min_drop}%)     : {result['discarded_min_drop']}")
    print(f"     • 🌟 OFERTAS BOMBA DETECTADAS     : {len(approved)}")
    if result["stores_count"]:
        top_stores = sorted(result["stores_count"].items(), key=lambda x: x[1], reverse=True)[:5]
        stores_str = ", ".join(f"{s} ({c})" for s, c in top_stores)
        print(f"     • Tiendas detectadas              : {stores_str}")
    print()


async def run_testing_200(
    channel_target: Optional[str] = None,
    bunny_only: bool = False,
    min_drop: float = 25.0,
    send_messages: bool = False,
    limit: int = 200,
    force_parser: Optional[str] = None,
):
    config = load_config()
    destination_channel = config.get("destination_channel", "-1003952548471")
    bot_tokens = get_bot_tokens(config)

    channels_to_test = resolve_channels_to_test(config, channel_target, bunny_only)

    if not channels_to_test:
        logger.error("No se encontraron canales para testear.")
        return

    logger.info("=" * 80)
    logger.info("🔍 INICIANDO TESTING DE OFERTAS SEGMENTADO POR CANAL")
    logger.info(f"Canales a analizar : {len(channels_to_test)}")
    for ch in channels_to_test:
        logger.info(f"   • {ch.get('name', 'Canal')} ({ch.get('channel_id')}) [Parser: {ch.get('parser', 'auto')}]")
    logger.info(f"Mensajes por canal : {limit}")
    logger.info(f"Umbral de Caída    : >= {min_drop}% MENOR al mínimo histórico previo")
    logger.info(f"Modo de Envío      : {'⚠️ ENVIANDO A TELEGRAM' if send_messages else '🔒 MODO ANÁLISIS SEGURO (Sin envíos)'}")
    if send_messages:
        logger.info(f"Canal Destino      : {destination_channel}")
    logger.info("=" * 80)

    # Inicializar cliente Telethon
    client = build_client()
    results = []

    async with client:
        if not await client.is_user_authorized():
            await client.start()

        for ch in channels_to_test:
            try:
                res = await analyze_channel(
                    client=client,
                    channel_info=ch,
                    limit=limit,
                    min_drop=min_drop,
                    force_parser=force_parser,
                )
                results.append(res)
                print_channel_report(res, min_drop)
                await asyncio.sleep(0.6)
            except Exception as e:
                logger.error(f"Error analizando canal {ch.get('name', '')} ({ch.get('channel_id')}): {e}")

    # Resumen global consolidado si se analizaron 2 o más canales
    if len(results) > 1:
        print("\n" + "=" * 90)
        print(" 📈 RESUMEN COMPARATIVO ENTRE CANALES:")
        print("=" * 90)
        print(f"{'CANAL':<28} | {'PARSER':<8} | {'MENSAJES':<8} | {'PARSEADOS':<9} | {'BOMBAS':<6}")
        print("-" * 90)
        total_msgs = 0
        total_parsed = 0
        total_approved = 0
        for r in results:
            total_msgs += r["total_messages"]
            total_parsed += r["parsed_ok"]
            total_approved += len(r["approved_deals"])
            name_display = r["title"][:28]
            print(f"{name_display:<28} | {r['parser_used'].upper():<8} | {r['total_messages']:<8} | {r['parsed_ok']:<9} | {len(r['approved_deals']):<6}")
        print("-" * 90)
        print(f"{'TOTAL GLOBAL':<28} | {'-':<8} | {total_msgs:<8} | {total_parsed:<9} | {total_approved:<6}")
        print("=" * 90 + "\n")

    # Envío opcional (SOLO SI SE PASÓ --send EXPLÍCITAMENTE)
    if not send_messages:
        logger.info("🔒 Modo seguro finalizado. NINGÚN mensaje fue enviado al canal de destino.")
        logger.info("💡 Si luego deseas despachar ofertas al canal Testing, ejecutá con el flag: --send")
        return

    # Si se solicitó enviar
    if not bot_tokens:
        logger.error("No se encontró BOT_TOKEN para despachar mensajes.")
        return

    all_approved = []
    for r in results:
        all_approved.extend(r["approved_deals"])

    if not all_approved:
        logger.info("No hay ofertas aprobadas para enviar.")
        return

    logger.warning(f"🚀 Despachando {len(all_approved)} ofertas seleccionadas a {destination_channel}...")
    formatter = EmbedMessageFormatter()
    dispatcher = TelegramBotDispatcher(
        bot_tokens=bot_tokens,
        destination_chat_id=destination_channel,
        formatter=formatter,
        include_inline_button=config.get("options", {}).get("include_inline_button", True),
        show_above_text=config.get("options", {}).get("show_above_text", False),
    )

    sent_count = 0
    for deal in all_approved:
        success = await dispatcher.dispatch(deal)
        if success:
            sent_count += 1
            await asyncio.sleep(1.2)

    logger.success(f"Completado: {sent_count}/{len(all_approved)} ofertas enviadas a {destination_channel}.")


def main():
    arg_parser = argparse.ArgumentParser(
        description="Testing segmentado por canal con análisis de mínimo histórico (Sin envíos por defecto)."
    )
    arg_parser.add_argument(
        "-c", "--channel",
        type=str,
        default=None,
        help="ID o nombre del canal a testear (si no se indica, prueba todos los configurados)",
    )
    arg_parser.add_argument(
        "--bunny",
        action="store_true",
        help="Filtrar únicamente canales de Bunny (60%% OFF, 80%% OFF, etc.)",
    )
    arg_parser.add_argument(
        "--min-drop",
        type=float,
        default=25.0,
        help="Porcentaje mínimo de caída respecto al récord histórico (default: 25.0%%)",
    )
    arg_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Cantidad de mensajes a inspeccionar por canal (default: 50)",
    )
    arg_parser.add_argument(
        "--parser",
        type=str,
        default=None,
        choices=["bunny", "nypau", "auto"],
        help="Forzar un parser específico en lugar de usar el de config.json",
    )
    arg_parser.add_argument(
        "--send",
        action="store_true",
        help="Despachar ofertas bomba al canal de Telegram (por defecto está DESACTIVADO)",
    )
    args = arg_parser.parse_args()

    asyncio.run(
        run_testing_200(
            channel_target=args.channel,
            bunny_only=args.bunny,
            min_drop=args.min_drop,
            send_messages=args.send,
            limit=args.limit,
            force_parser=args.parser,
        )
    )


if __name__ == "__main__":
    main()
