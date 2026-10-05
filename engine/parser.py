"""
engine/parser.py — Parsers orientados a objetos para múltiples proveedores de ofertas.
Soporta:
  1. BunnyDealParser: Canales de Bunny (60% OFF, 80% OFF, etc.)
  2. NypauDealParser: Canales de Nypau / Shark (70%-99% Nypau, Alerta de Ofertas)
"""
import re
from typing import Optional, List, Dict, Type
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
        # Formato Bunny: $PRECIO - DD/MM/YYYY
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


STORE_DOMAINS = {
    "falabella.com": "Falabella",
    "ripley.cl": "Ripley",
    "cencosud.com": "Paris",
    "paris.cl": "Paris",
    "walmartimages.cl": "Lider",
    "lider.cl": "Lider",
    "mlstatic.com": "Mercado Libre",
    "mercadolibre.cl": "Mercado Libre",
    "pcfactory.cl": "PC Factory",
    "hites.com": "Hites",
    "jumbo.cl": "Jumbo",
    "easy.cl": "Easy",
    "sodimac.cl": "Sodimac",
    "zara.com": "Zara",
    "hm.com": "H&M",
    "stretto.cl": "Stretto",
}


class NypauDealParser(BaseDealParser):
    """
    Parser especializado para los canales de Nypau / Shark.
    Soporta:
      - Canales: -1001630413456 (70%-99% Nypau), -1001815551781 (Alerta de Ofertas)
      - Redirecciones Cloudflare / ofertasshark.cl
      - Historial invertido (DD/MM/YYYY $PRECIO)
      - Detección de tienda por negritas en primera línea o dominios CDN de imagen
    """

    def parse(self, message_id: int, text: str, source_channel: str = "") -> Optional[DealItem]:
        if not text or not text.strip():
            return None

        # Descartar mensajes no estructurados (charlas, texto libre o enlaces sueltos)
        if not ("[PRODUCTO]" in text or "link.ofertasshark.cl" in text or "**Precio histórico" in text):
            return None

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None

        # 1. URL de la Imagen: primer enlace markdown ignorando placeholders de s3
        image_url = None
        for m in re.finditer(r"\[[^\]]+\]\((https?://[^)]+)\)", text):
            url = m.group(1).strip()
            if "scraper-image-public" in url or "page-not-found" in url or "ofertasshark.cl" in url:
                continue
            image_url = url
            break

        # 2. Título desde la primera línea (tienda omitida hasta resolver link real)
        first_line = lines[0]
        bolds = re.findall(r"\*\*(.+?)\*\*", first_line)

        title = None
        if len(bolds) >= 2:
            # Si hay dos negritas (ej: **Pesas Chile** **Par Guantes...**), unimos para no perder el contexto
            title = f"{bolds[0].strip()} - {bolds[1].strip()}"
        elif len(bolds) == 1:
            title = bolds[0].strip()
        else:
            # Fallback en caso de que el título esté en líneas siguientes
            for l in lines[1:3]:
                b = re.findall(r"\*\*(.+?)\*\*", l)
                if b and not any(k in b[0] for k in ["$", "%", "Precio"]):
                    title = b[0].strip()
                    break

        if not title:
            return None

        # Limpiar caracteres decorativos del final del título
        title = title.strip(" .-")
        store = None  # No definir tienda por ahora hasta que se obtenga el link real directo

        # 4. Precios: "$ORIG -> ... -> **$OFERTA** (XX%)"
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

        # Porcentaje anunciado
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

        # 5. Historial de precios: bloque **Precio histórico 📉**
        # Formato Nypau: DD/MM/YYYY $PRECIO
        history: List[HistoricalEntry] = []
        hist_block = re.search(r"Precio hist[oó]rico.*?\n([\s\S]+)", text, re.IGNORECASE)
        if hist_block:
            for h_entry in re.finditer(r"(\d{2}/\d{2}/\d{4})\s+\$([\d\.]+)", hist_block.group(1)):
                p = _parse_digits(h_entry.group(2))
                if p:
                    history.append(HistoricalEntry(price=p, date=h_entry.group(1).strip()))

        # 6. URL del producto: [PRODUCTO](https://link.ofertasshark.cl/...)
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
    """Retorna una instancia del parser configurado por nombre."""
    key = (name_or_alias or "").strip().lower()
    parser_cls = PARSER_REGISTRY.get(key, BunnyDealParser)
    return parser_cls()


def detect_parser(text: str) -> BaseDealParser:
    """Detecta heurísticamente el parser adecuado según el contenido del mensaje."""
    if not text:
        return BunnyDealParser()
    if "ofertasshark.cl" in text or "Precio histórico" in text or "[PRODUCTO]" in text:
        return NypauDealParser()
    return BunnyDealParser()
