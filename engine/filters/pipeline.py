"""
engine/filters/pipeline.py — Orquestador del pipeline de filtrado (Pattern: Chain of Responsibility).
"""
from typing import List
from loguru import logger
from core.models import DealItem, FilterResult
from engine.filters.base import BaseFilter


class FilterPipeline:
    """
    Ejecuta una secuencia ordenada de filtros sobre un DealItem.
    Si cualquier filtro falla, interrumpe la ejecución inmediatamente (short-circuit)
    y retorna el resultado con la causa exacta del rechazo.
    """

    def __init__(self, filters: List[BaseFilter]):
        self.filters = filters

    async def execute(self, deal: DealItem) -> FilterResult:
        for f in self.filters:
            result = await f.evaluate(deal)
            if not result.passed:
                logger.info(f"[{f.name}] ❌ Rechazado [{deal.title[:35]}...]: {result.reason}")
                return result
            logger.debug(f"[{f.name}] ✓ Aprobado: {result.reason}")

        logger.success(f"[Pipeline] 🌟 OFERTA APROBADA: '{deal.title[:45]}' (${deal.offer_price:,} / -{deal.discount_percentage}%)")
        return FilterResult(passed=True, filter_name="Pipeline", reason="Aprobado por todos los filtros")
