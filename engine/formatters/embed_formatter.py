"""
engine/formatters/embed_formatter.py: Formateador de 'Ofertas Aguja'.
Limpio, con identidad sobria y botones de acción rápida.
"""
import html
import urllib.parse
from typing import Optional, Dict, Any
from core.models import DealItem


def format_clp(amount: Optional[int]) -> str:
    """Formatea precios en formato chileno con punto: 15990 -> 15.990"""
    if amount is None:
        return "-"
    return f"{amount:,}".replace(",", ".")


class EmbedMessageFormatter:
    """
    Formato 'Ofertas Aguja':
    - Cabecera: Marca, tienda y etiqueta sobria en caso de error de precio.
    - Imagen embebida limpia.
    - Título y precio con histórico comparado.
    - Botones en línea: Ver oferta y Búsqueda en Google (bypass directo).
    """

    def __init__(self, brand_name: str = "🪡 <b>Ofertas Aguja</b>"):
        self.brand_name = brand_name

    def build_message(self, deal: DealItem) -> str:
        preview_anchor = f'<a href="{deal.image_url}">&#8205;</a>' if deal.image_url else ""
        clean_title = html.escape(deal.title)

        # 1. Cabecera con tienda
        if deal.store:
            header = f"{self.brand_name} · <b>#{deal.store}</b>"
        else:
            header = f"{self.brand_name}"

        # 2. Alerta sobria de error de precio (sin estridencias ni emojis repetidos)
        alert_line = "\n⚠️ <b>Posible error de precio</b>" if deal.is_price_glitch else ""

        # 3. Comparativa de precios
        min_hist = deal.previous_historical_low
        drop = deal.discount_vs_history

        if min_hist and drop and drop > 0:
            price_line = f"<b>${format_clp(min_hist)}</b> ➜ <b>${format_clp(deal.offer_price)}</b> (<b>-{drop:.0f}%</b>)"
        elif min_hist:
            price_line = f"<b>${format_clp(deal.offer_price)}</b> (<b>Mínimo histórico</b>)"
        else:
            price_line = f"<b>${format_clp(deal.original_price)}</b> ➜ <b>${format_clp(deal.offer_price)}</b> (<b>-{deal.discount_percentage}%</b>)"

        # Precio de lista referencial si aporta contexto
        ref_line = ""
        if deal.original_price and min_hist and deal.original_price > min_hist:
            ref_line = f"<i>(Precio lista: ${format_clp(deal.original_price)})</i>\n"

        # 4. Historial
        history_block = ""
        if deal.history:
            history_lines = [f"${format_clp(h.price)} ({h.date})" for h in deal.history]
            history_block = "<b>Historial 📈</b>\n" + "\n".join(history_lines)

        parts = [
            f"{header}{alert_line}\n",
            f"{preview_anchor}<b>{clean_title}</b>\n",
            price_line,
        ]

        if ref_line:
            parts.append(ref_line)
        else:
            parts.append("")

        if history_block:
            parts.append(history_block)

        return "\n".join(parts).strip()

    def build_reply_markup(self, deal: DealItem) -> Optional[Dict[str, Any]]:
        """
        Genera dos botones horizontales:
        1. Enlace original a la oferta.
        2. Búsqueda en Google para bypass inmediato de bloqueos o verificación.
        """
        target_url = deal.clean_product_url or deal.product_url
        if not target_url:
            return None

        # Botón 1: Enlace a la oferta
        offer_btn = {"text": "🛍️ Ver oferta", "url": target_url}

        # Botón 2: Búsqueda en Google (incluye tienda y título para ir directo al producto)
        query = f"{deal.store or ''} {deal.title}".strip()
        google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
        google_btn = {"text": "🔍 Buscar", "url": google_url}

        return {
            "inline_keyboard": [
                [offer_btn, google_btn]
            ]
        }
