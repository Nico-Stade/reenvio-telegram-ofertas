"""
core/models.py — Modelos de dominio fuertemente tipados.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import re
from urllib.parse import urlparse, parse_qs, unquote


@dataclass(frozen=True)
class HistoricalEntry:
    """Representa una entrada en el historial de precios."""
    price: int
    date: str  # formato DD/MM/YYYY o similar


@dataclass
class DealItem:
    """Representa un producto/oferta extraído del canal de Telegram."""
    raw_id: int
    title: str
    store: Optional[str]
    original_price: Optional[int]
    offer_price: int
    discount_percentage: int
    history: List[HistoricalEntry] = field(default_factory=list)
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    source_channel: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    raw_text: str = ""

    @property
    def min_historical_price(self) -> Optional[int]:
        """Devuelve el precio más bajo registrado en el historial."""
        if not self.history:
            return None
        return min(h.price for h in self.history if h.price is not None and h.price > 0)

    @property
    def previous_historical_low(self) -> Optional[int]:
        """Alias semántico para el precio mínimo del historial."""
        return self.min_historical_price

    @property
    def discount_vs_history(self) -> Optional[float]:
        """
        Calcula el porcentaje de descuento REAL comparado con el precio más bajo del historial.
        Ej: si estuvo a $9.500 y ahora bajó a $7.600 -> 20.0% de descuento real.
        """
        min_hist = self.min_historical_price
        if min_hist and min_hist > 0:
            return round((1 - (self.offer_price / min_hist)) * 100, 1)
        return None

    @property
    def savings_vs_history(self) -> int:
        """Ahorro monetario en pesos respecto al precio más bajo previo."""
        min_hist = self.min_historical_price
        if min_hist and min_hist > self.offer_price:
            return min_hist - self.offer_price
        return 0

    @property
    def is_strict_historical_low(self) -> bool:
        """
        Retorna True si el precio de oferta actual es menor o igual
        al precio mínimo registrado en el historial.
        """
        min_hist = self.min_historical_price
        if min_hist is None:
            return False
        return self.offer_price <= min_hist

    @property
    def clean_product_url(self) -> str:
        """
        Limpia enlaces de afiliados o wrappers (por ejemplo Soicos dl=...).
        Retorna la URL directa del producto si es posible.
        """
        if not self.product_url:
            return ""
        
        # Desempaquetar redirects comunes como Soicos (ej. ad.soicos.com/...?dl=https://...)
        if "soicos.com" in self.product_url and "dl=" in self.product_url:
            try:
                parsed = urlparse(self.product_url)
                params = parse_qs(parsed.query)
                if "dl" in params:
                    return unquote(params["dl"][0])
            except Exception:
                pass
        return self.product_url

    @property
    def savings_amount(self) -> int:
        """Calcula el ahorro total en pesos."""
        if self.original_price and self.original_price > self.offer_price:
            return self.original_price - self.offer_price
        return 0


@dataclass(frozen=True)
class FilterResult:
    """Resultado de evaluar un filtro sobre un DealItem."""
    passed: bool
    filter_name: str
    reason: str
