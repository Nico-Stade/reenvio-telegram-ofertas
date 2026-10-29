"""
engine/parser.py — Parsers orientados a objetos para proveedores de ofertas (Bunny y Nypau/Shark).
"""
import re
from typing import Optional, List, Dict, Type
from core.models import DealItem, HistoricalEntry
from engine.resolver import detect_store_from_title, detect_store_from_url


def _parse_digits(raw: str) -> Optional[int]:
    """Extrae todos los dígitos y devuelve un entero (e.g. '$159.990' -> 159990)."""
    clean = re.sub(r"[^\d]", "", raw)
    return int(clean) if clean else None


class BaseDealParser:
    """Clase base para parsers de ofertas."""
    def parse(self, message_id: int, text: str, source_channel: str = "") -> Optional[DealItem]:
        raise NotImplementedError


class BunnyDealParser(BaseDealParser):
    """
    Parser para canales de Bunny (60% OFF, 80% OFF, etc.).
    Formato: [🤖](img) #Tienda Dscto. XX% ** Titulo | **[🔍] $Orig -> **$Oferta** Historial: ...
    """

    def parse(self, message_id: int, text: str, source_channel: str = "") -> Optional[DealItem]:
        if not text or not text.strip():
            return None

        image_url = None
        m_img = re.search(r"\[🤖\]\((https?://[^)]+)\)", text)
        if m_img:
            image_url = m_img.group(1).strip()

        store = None
        m_store = re.search(r"#(\w+)", text)
        if m_store:
            store = m_store.group(1).strip()

        discount = None
        m_disc = re.search(r"Dscto\.\s*(\d+)%", text, re.IGNORECASE)
        if m_disc:
            discount = int(m_disc.group(1))

        title = None
        m_title = re.search(r"\*\*\s*(.+?)\s*\|\s*\*\*\[🔍\]", text)
        if m_title:
            title = m_title.group(1).strip()
        else:
            m_title_fb = re.search(r"\*\*\s*([^\*]+?)\s*\*\*", text)
            if m_title_fb:
                title = m_title_fb.group(1).strip()

        if not title:
            return None

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

        if offer_price is None or offer_price <= 0:
            return None

        if discount is None and orig_price and orig_price > offer_price:
            discount = int(round((1 - (offer_price / orig_price)) * 100))
        elif discount is None:
            discount = 0

        # Formato de historial Bunny: $PRECIO - DD/MM/YYYY
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

        product_url = None
        m_url = re.search(r"\[\*\*VER PRODUCTO\*\*\]\((https?://[^)]+)\)", text, re.IGNORECASE)
        if m_url:
            product_url = m_url.group(1).strip()
        else:
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


class NypauDealParser(BaseDealParser):
    """
    Parser para canales de Nypau / Shark.
    Soporta historial con formato invertido (DD/MM/YYYY $PRECIO) y detección
    de tienda por prefijo de título o dominios de imagen.
    """

    def parse(self, message_id: int, text: str, source_channel: str = "") -> Optional[DealItem]:
        if not text or not text.strip():
            return None

        if not ("[PRODUCTO]" in text or "link.ofertasshark.cl" in text or "**Precio histórico" in text):
            return None

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None

        # Extraer imagen (excluyendo enlaces de redirección y placeholders de error)
        image_url = None
        for m in re.finditer(r"\[[^\]]+\]\((https?://[^)]+)\)", text):
            url = m.group(1).strip()
            if "scraper-image-public" in url or "page-not-found" in url or "link.ofertasshark.cl" in url:
                continue
            image_url = url
            break

        first_line = lines[0]
        bolds = re.findall(r"\*\*(.+?)\*\*", first_line)

        title = None
        if len(bolds) >= 2:
            title = f"{bolds[0].strip()} - {bolds[1].strip()}"
        elif len(bolds) == 1:
            title = bolds[0].strip()
        else:
            for l in lines[1:3]:
                b = re.findall(r"\*\*(.+?)\*\*", l)
                if b and not any(k in b[0] for k in ["$", "%", "Precio"]):
                    title = b[0].strip()
                    break

        if not title:
            return None

        title = title.strip(" .-")

        # Detección de tienda mediante prefijo de marca o dominio de imagen
        store = detect_store_from_title(title)
        if not store and image_url:
            store = detect_store_from_url(image_url)

        offer_price = None
        m_offer = re.search(r"\*\*(\$[\d\.]+)\*\*", text)
        if m_offer:
            offer_price = _parse_digits(m_offer.group(1))

        if not offer_price or offer_price <= 0:
            return None

        orig_price = None
        m_orig = re.search(r"(?:__|\*)?(\$[\d\.]+)(?:__|\*)?\s*->", text)
        if m_orig:
            orig_price = _parse_digits(m_orig.group(1))

        discount = None
        m_disc = re.search(r"\(([\d\.,]+)%\)", text)
        if m_disc:
            try:
                discount = int(round(float(m_disc.group(1).replace(",", "."))))
            except ValueError:
                pass

        if discount is None and orig_price and orig_price > offer_price:
            discount = int(round((1 - (offer_price / orig_price)) * 100))
        elif discount is None:
            discount = 0

        # Formato Nypau: DD/MM/YYYY $PRECIO
        history: List[HistoricalEntry] = []
        hist_block = re.search(r"Precio hist[oó]rico.*?\n([\s\S]+)", text, re.IGNORECASE)
        if hist_block:
            for h_entry in re.finditer(r"(\d{2}/\d{2}/\d{4})\s+\$([\d\.]+)", hist_block.group(1)):
                p = _parse_digits(h_entry.group(2))
                if p:
                    history.append(HistoricalEntry(price=p, date=h_entry.group(1).strip()))

        product_url = None
        m_url = re.search(r"\[PRODUCTO\]\((https?://[^)]+)\)", text, re.IGNORECASE)
        if m_url:
            product_url = m_url.group(1).strip()
        else:
            m_shark = re.search(r"\((https?://link\.ofertasshark\.cl[^\s\)]+)\)", text)
            if m_shark:
                product_url = m_shark.group(1).strip()

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


PARSER_REGISTRY: Dict[str, Type[BaseDealParser]] = {
    "bunny": BunnyDealParser,
    "nypau": NypauDealParser,
    "shark": NypauDealParser,
    "ofertasshark": NypauDealParser,
}


def get_parser(name_or_alias: str) -> BaseDealParser:
    key = (name_or_alias or "").strip().lower()
    parser_cls = PARSER_REGISTRY.get(key, BunnyDealParser)
    return parser_cls()


def detect_parser(text: str) -> BaseDealParser:
    if not text:
        return BunnyDealParser()
    if "ofertasshark.cl" in text or "Precio histórico" in text or "[PRODUCTO]" in text:
        return NypauDealParser()
    return BunnyDealParser()
