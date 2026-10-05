"""
engine/filters/discount.py — Filtro por porcentaje de descuento y límites de precio.
"""
from typing import Optional
from core.models import DealItem, FilterResult
from engine.filters.base import BaseFilter


class MinDiscountFilter(BaseFilter):
    """Filtra ofertas que no alcancen el porcentaje de descuento configurado."""

    def __init__(self, min_discount: int = 60, min_price: Optional[int] = None, max_price: Optional[int] = None):
        self.min_discount = min_discount
        self.min_price = min_price
        self.max_price = max_price

    async def evaluate(self, deal: DealItem) -> FilterResult:
        if deal.discount_percentage < self.min_discount:
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason=f"Descuento insuficiente: {deal.discount_percentage}% < mínimo configurado {self.min_discount}%"
            )

        if self.min_price and deal.offer_price < self.min_price:
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason=f"Precio ${deal.offer_price:,} por debajo del mínimo permitido ${self.min_price:,}"
            )

        if self.max_price and deal.offer_price > self.max_price:
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason=f"Precio ${deal.offer_price:,} por encima del máximo permitido ${self.max_price:,}"
            )

        return FilterResult(
            passed=True,
            filter_name=self.name,
            reason=f"Descuento ({deal.discount_percentage}%) y precio (${deal.offer_price:,}) dentro de los rangos válidos"
        )
