"""
engine/resolver.py — Utilidades de normalización de URLs y detección de tiendas.
Diseñado para entornos headless ligeros sin dependencias de navegador (Chrome/Selenium).
"""
from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote


STORE_DOMAIN_MAP = {
    "falabella.com": "Falabella",
    "ripley.cl": "Ripley",
    "paris.cl": "Paris",
    "cencosud.com": "Paris",
    "sodimac.cl": "Sodimac",
    "lider.cl": "Líder",
    "walmartimages.cl": "Líder",
    "mercadolibre.cl": "Mercado Libre",
    "mercadolibre.com": "Mercado Libre",
    "hites.com": "Hites",
    "easy.cl": "Easy",
    "abcdin.cl": "Abcdin",
    "pcfactory.cl": "PC Factory",
    "spdigital.cl": "SP Digital",
    "zara.com": "Zara",
    "hm.com": "H&M",
    "stretto.cl": "Stretto",
    "lenovo.com": "Lenovo",
    "samsung.com": "Samsung",
    "aliexpress.com": "AliExpress",
    "amazon.com": "Amazon",
    "linio.cl": "Linio",
    "claro.cl": "Claro",
    "entel.cl": "Entel",
    "movistar.cl": "Movistar",
    "wom.cl": "WOM",
    "gacel.cl": "Gacel",
    "tottus.cl": "Tottus",
    "superzoo.cl": "SuperZoo",
    "unimarc.cl": "Unimarc",
}


def detect_store_from_url(url: str) -> Optional[str]:
    """Extrae el nombre comercial de la tienda a partir de una URL directa."""
    if not url:
        return None
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain.startswith("simple."):
            domain = domain[7:]

        for dom, store in STORE_DOMAIN_MAP.items():
            if dom in domain:
                return store
    except Exception:
        pass
    return None


def detect_store_from_title(title: str) -> Optional[str]:
    """
    Detecta la tienda o marca cuando el título incluye un prefijo estructurado
    (e.g. 'Stretto - Monomando...', 'Abc - Smart TV...', 'Gacel - Botín...').
    """
    if not title:
        return None

    if " - " in title:
        prefix = title.split(" - ")[0].strip()
        if len(prefix) <= 25 and not any(char.isdigit() for char in prefix):
            p_lower = prefix.lower()
            if p_lower in ("abc", "abcdin"):
                return "Abcdin"
            return prefix

    for store_name in STORE_DOMAIN_MAP.values():
        if title.lower().startswith(store_name.lower()):
            return store_name

    return None


def unpack_redirect_url(url: str) -> str:
    """
    Extrae la URL de destino de wrappers comunes de afiliados (como Soicos dl=...)
    sin necesidad de realizar peticiones de red.
    """
    if not url:
        return ""
    if "soicos.com" in url and "dl=" in url:
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if "dl" in params:
                return unquote(params["dl"][0])
        except Exception:
            pass
    return url
