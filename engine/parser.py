"""
engine/parser.py — Parser orientado a objetos para mensajes de canales de ofertas (Bunny / similares).
"""
import re
from typing import Optional, List
from core.models import DealItem, HistoricalEntry


def _parse_digits(raw: str) -> Optional[int]:
    """Extrae todos los dígitos y devuelve un entero, e.g. '$159.990' -> 159990."""
    clean = re.sub(r"[^\d]", "", raw)
    return int(clean) if clean else None


class BaseDealParser:
    """Clase base abstracta para parsers de ofertas."""
    def parse(self, message_id: int, text: str, source_channel: str = "") -> Optional[DealItem]:
        raise NotImplementedError


class BunnyDealParser(BaseDealParser):
    """
    Parser especializado para los canales de Bunny (60% OFF, 80% OFF, etc.).
    Extrae campos estructurados y devuelve un objeto DealItem.
    """

    def parse(self, message_id: int, text: str, source_channel: str = "") -> Optional[DealItem]:
        if not text or not text.strip():
            return None

        # 1. URL de la Imagen: [🤖](https://...)
        image_url = None
        m_img = re.search(r"\[🤖\]\((https?://[^)]+)\)", text)
        if m_img:
            image_url = m_img.group(1).strip()

        # 2. Tienda: hashtag #Tienda (e.g. #Falabella, #Paris, #Lider, etc.)
        store = None
        m_store = re.search(r"#(\w+)", text)
        if m_store:
            store = m_store.group(1).strip()

        # 3. Descuento anunciado: Dscto. 75% o similar
        discount = None
        m_disc = re.search(r"Dscto\.\s*(\d+)%", text, re.IGNORECASE)
        if m_disc:
            discount = int(m_disc.group(1))

        # 4. Nombre del producto: ** Titulo | **[🔍]
        title = None
        m_title = re.search(r"\*\*\s*(.+?)\s*\|\s*\*\*\[🔍\]", text)
        if m_title:
            title = m_title.group(1).strip()
        else:
            # Fallback si no tiene el emoji de lupa
            m_title_fb = re.search(r"\*\*\s*([^\*]+?)\s*\*\*", text)
            if m_title_fb:
                title = m_title_fb.group(1).strip()

        # Si no logramos extraer un título, descartar
        if not title:
            return None

        # 5. Precios: "$X.XXX -> **$Y.YYY (N%)**"
        orig_price = None
        offer_price = None
        m_price = re.search(
            r"(\$[\d\.]+)\s*->\s*\*\*(\$[\d\.]+)\s*(?:\((\d+)%\))?\*\*",
            text,
        )
        if m_price:
            orig_price = _parse_digits(m_price.group(1))
            offer_price = _parse_digits(m_price.group(2))
            if discount is None and m_price.group(3):
                discount = int(m_price.group(3))

        # Si no hay precio de oferta, no es una oferta válida
        if offer_price is None or offer_price <= 0:
            return None

        # Si aún no tenemos discount, calcularlo matemáticamente
        if discount is None and orig_price and orig_price > offer_price:
            discount = int(round((1 - (offer_price / orig_price)) * 100))
        elif discount is None:
            discount = 0

        # 6. Historial de precios: bloque **Historial 📊 **
        history: List[HistoricalEntry] = []
        hist_block = re.search(
            r"Historial.*?\n((?:\s*\$[\d\.]+\s+-\s+\d{2}/\d{2}/\d{4}\s*\n?)+)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if hist_block:
            for entry in re.finditer(r"(\$[\d\.]+)\s+-\s+(\d{2}/\d{2}/\d{4})", hist_block.group(1)):
                p = _parse_digits(entry.group(1))
                if p:
                    history.append(HistoricalEntry(price=p, date=entry.group(2).strip()))

        # 7. URL del producto: [**VER PRODUCTO**](url) o similar
        product_url = None
        m_url = re.search(r"\[\*\*VER PRODUCTO\*\*\]\((https?://[^)]+)\)", text, re.IGNORECASE)
        if m_url:
            product_url = m_url.group(1).strip()
        else:
            # Fallback para cualquier link http
            m_any_url = re.search(r"\((https?://[^\s\)]+)\)", text)
            if m_any_url:
                product_url = m_any_url.group(1).strip()

        return DealItem(
            raw_id=message_id,
            title=title,
            store=store,
            original_price=orig_price,
            offer_price=offer_price,
            discount_percentage=discount,
            history=history,
            product_url=product_url,
            image_url=image_url,
            source_channel=str(source_channel),
            raw_text=text,
        )
