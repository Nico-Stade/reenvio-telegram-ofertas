"""
engine/filters/store.py — Filtro por tienda/origen de la oferta.
"""
from typing import List, Optional
from core.models import DealItem, FilterResult
from engine.filters.base import BaseFilter


class StoreFilter(BaseFilter):
    """Permite filtrar por tiendas permitidas (whitelist) o bloqueadas (blacklist)."""

    def __init__(self, allowed_stores: Optional[List[str]] = None, blocked_stores: Optional[List[str]] = None):
        self.allowed_stores = [s.lower().lstrip("#") for s in allowed_stores or []]
        self.blocked_stores = [s.lower().lstrip("#") for s in blocked_stores or []]

    async def evaluate(self, deal: DealItem) -> FilterResult:
        store = (deal.store or "").lower().lstrip("#")

        if self.blocked_stores and store in self.blocked_stores:
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason=f"Tienda '{deal.store}' está en la lista negra"
            )

        if self.allowed_stores and store not in self.allowed_stores:
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason=f"Tienda '{deal.store}' no está en la lista permitida {self.allowed_stores}"
            )

        return FilterResult(
            passed=True,
            filter_name=self.name,
            reason=f"Tienda '{deal.store}' permitida"
        )
