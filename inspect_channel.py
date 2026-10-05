"""
inspect_channel.py — Muestra los últimos N mensajes de un canal.
Útil para ver el contenido exacto y verificar el parsing de diferentes proveedores (Bunny, Nypau, etc.).

Uso:
  python inspect_channel.py -c @canal_o_id -n 10
  python inspect_channel.py -c -1001630413456 -n 10 --parse
  python inspect_channel.py -c -1001815551781 -n 10 --parse --parser nypau
  python inspect_channel.py -c -1002023523123 -n 20 --json
"""
import asyncio
import argparse
import sys
import json

# Force UTF-8 output so non-ASCII channel names/messages don't crash on Windows cp1252 terminals
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

from core.client import build_client, parse_peer as _parse_peer
from engine.parser import get_parser, detect_parser, BaseDealParser

load_dotenv()

SEPARATOR = "-" * 60


def _print_parsed(deal) -> None:
    print(SEPARATOR)
    print(f"  ID              : {deal.raw_id}")
    print(f"  Tienda          : {deal.store or '—'}")
    print(f"  Producto        : {deal.title or '—'}")
    print(f"  Precio original : {deal.original_price:,}" if deal.original_price else "  Precio original : —")
    print(f"  Precio oferta   : {deal.offer_price:,}" if deal.offer_price else "  Precio oferta   : —")
    print(f"  Descuento       : {deal.discount_percentage}%" if deal.discount_percentage else "  Descuento       : —")
    if deal.min_historical_price:
        drop = deal.discount_vs_history
        print(f"  Récord histórico: ${deal.min_historical_price:,} (Rebaja real: -{drop}%)")
    if deal.history:
        print(f"  Historial       :")
        for h in deal.history:
            print(f"    ${h.price:,} — {h.date}")
    else:
        print(f"  Historial       : —")
    print(f"  URL producto    : {deal.product_url or '—'}")
    print(f"  URL imagen      : {deal.image_url or '—'}")
    print()


async def inspect(channel: str, limit: int, parse: bool, parser_name: str, as_json: bool) -> None:
    client = build_client()
    explicit_parser = get_parser(parser_name) if parser_name != "auto" else None

    async with client:
        if not await client.is_user_authorized():
            await client.start()

        entity = await client.get_entity(_parse_peer(channel))
        messages = await client.get_messages(entity, limit=limit)
        messages = sorted(messages, key=lambda m: m.id)

        if as_json:
            output = []
            for msg in messages:
                record = {
                    "id": msg.id,
                    "fecha": msg.date.strftime("%Y-%m-%d %H:%M:%S"),
                    "media": type(msg.media).__name__ if msg.media else None,
                    "texto": msg.text or "",
                }
                if msg.text:
                    p = explicit_parser or detect_parser(msg.text)
                    d = p.parse(msg.id, msg.text, channel)
                    if d:
                        record["parsed"] = {
                            "parser": type(p).__name__,
                            "tienda": d.store,
                            "nombre_producto": d.title,
                            "descuento": d.discount_percentage,
                            "precio_original": d.original_price,
                            "precio_oferta": d.offer_price,
                            "min_historico": d.min_historical_price,
                            "rebaja_vs_historia": d.discount_vs_history,
                            "historico": [{"precio": h.price, "fecha": h.date} for h in d.history],
                            "url_producto": d.product_url,
                            "url_imagen": d.image_url,
                        }
                output.append(record)
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return

        print(f"\n{'='*60}")
        print(f"  Canal : {getattr(entity, 'title', channel)}")
        print(f"  Mostrando últimos {len(messages)} mensajes")
        print(f"{'='*60}\n")

        for msg in messages:
            fecha = msg.date.strftime("%Y-%m-%d %H:%M:%S")

            if parse and msg.text:
                p = explicit_parser or detect_parser(msg.text)
                d = p.parse(msg.id, msg.text, channel)
                if d:
                    _print_parsed(d)
                else:
                    print(f"[No se pudo parsear como oferta: ID {msg.id}]")
            else:
                media_type = type(msg.media).__name__ if msg.media else "—"
                print(SEPARATOR)
                print(f"  ID     : {msg.id}")
                print(f"  Fecha  : {fecha}")
                print(f"  Media  : {media_type}")
                if msg.text:
                    print(f"  Texto  :")
                    for line in msg.text.splitlines():
                        print(f"    {line}")
                else:
                    print(f"  Texto  : (sin texto)")
                print()

        print(SEPARATOR)
        print(f"  Total mostrado: {len(messages)} mensajes")
        print(SEPARATOR + "\n")


def main():
    parser = argparse.ArgumentParser(description="Inspecciona mensajes de un canal de Telegram.")
    parser.add_argument("-c", "--channel", required=True, help="Username (@canal) o ID numérico del canal")
    parser.add_argument("-n", "--limit", type=int, default=10, help="Cantidad de mensajes a mostrar (default: 10)")
    parser.add_argument("--parse", action="store_true", help="Parsear campos estructurados (producto, precio, historial, etc.)")
    parser.add_argument("--parser", default="auto", choices=["auto", "bunny", "nypau"], help="Parser a utilizar (default: auto)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Exportar output como JSON (incluye texto crudo + parsed)")
    args = parser.parse_args()

    asyncio.run(inspect(args.channel, args.limit, parse=args.parse, parser_name=args.parser, as_json=args.as_json))


if __name__ == "__main__":
    main()
