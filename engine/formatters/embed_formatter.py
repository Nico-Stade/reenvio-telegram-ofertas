"""
engine/formatters/embed_formatter.py — Formateador de 'Ofertas Aguja'.
Limpio, con identidad propia, sin texto de más y con historial completo.
"""
import html
from typing import Optional, Dict, Any
from core.models import DealItem


def format_clp(amount: Optional[int]) -> str:
    """Formatea precios en formato chileno con punto: 15990 -> 15.990"""
    if amount is None:
        return "—"
    return f"{amount:,}".replace(",", ".")


class EmbedMessageFormatter:
    """
    Formato 'Ofertas Aguja':
    - Marca de proveedor: 🪡 Ofertas Aguja · #Tienda ✨
    - Imagen embebida limpia.
    - Título en negrita.
    - Comparativa de precio con flecha (precio récord anterior ➜ precio oferta).
    - Historial completo de precios y fechas.
    - Botón interactivo: [🛍️ Obtener Oferta].
    """

    def __init__(self, brand_name: str = "🪡 <b>Ofertas Aguja</b>"):
        self.brand_name = brand_name

    def build_message(self, deal: DealItem) -> str:
        # 1. Enlace invisible para generar la tarjeta embed de imagen
        preview_anchor = f'<a href="{deal.image_url}">&#8205;</a>' if deal.image_url else ""

        # 2. Tienda y Título
        clean_title = html.escape(deal.title)
        store = deal.store or "Oferta"

        # 3. Cabecera con marca y tienda (sin porcentaje redundante arriba)
        header = f"{self.brand_name} · <b>#{store}</b> ✨\n"

        # 4. Cálculo de la rebaja real
        min_hist = deal.previous_historical_low
        drop = deal.discount_vs_history

        if min_hist and drop and drop > 0:
            price_line = f"<b>${format_clp(min_hist)}</b> ➜ <b>${format_clp(deal.offer_price)}</b> (<b>-{drop:.0f}%</b>)"
        elif min_hist:
            price_line = f"<b>${format_clp(deal.offer_price)}</b> (<b>Mínimo histórico récord</b>)"
        else:
            price_line = f"<b>${format_clp(deal.original_price)}</b> ➜ <b>${format_clp(deal.offer_price)}</b> (<b>-{deal.discount_percentage}%</b>)"

        # Referencia del precio de lista de la tienda (si existía y es mayor al histórico)
        ref_line = ""
        if deal.original_price and min_hist and deal.original_price > min_hist:
            ref_line = f"<i>(Precio lista tienda: ${format_clp(deal.original_price)})</i>\n"

        # 5. Historial completo (incluye todos los registros del mensaje original)
        history_block = ""
        if deal.history:
            history_lines = [f"${format_clp(h.price)} - {h.date}" for h in deal.history]
            history_block = f"<b>Historial 📈</b>\n" + "\n".join(history_lines)

        # 6. Composición final
        parts = [
            header,
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
        """Botón interactivo limpio: '🛍️ Obtener Oferta'."""
        target_url = deal.clean_product_url or deal.product_url
        if not target_url:
            return None

        return {
            "inline_keyboard": [
                [
                    {"text": "🛍️ Obtener Oferta", "url": target_url}
                ]
            ]
        }
