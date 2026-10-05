"""
engine/filters/dedup.py — Filtro anti-spam y deduplicación por ventana de tiempo.
"""
from core.models import DealItem, FilterResult
from core.database import SQLiteDealRepository
from engine.filters.base import BaseFilter


class DeduplicationFilter(BaseFilter):
    """
    Evita reenviar una oferta idéntica si ya fue despachada
    dentro de la ventana de tiempo especificada (en horas).
    """

    def __init__(self, repository: SQLiteDealRepository, window_hours: int = 12):
        self.repository = repository
        self.window_hours = window_hours

    async def evaluate(self, deal: DealItem) -> FilterResult:
        if self.repository.is_deal_recently_sent(deal, self.window_hours):
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason=f"Oferta duplicada: ya fue enviada en las últimas {self.window_hours} horas"
            )

        return FilterResult(
            passed=True,
            filter_name=self.name,
            reason="Oferta no vista recientemente en el repositorio"
        )
