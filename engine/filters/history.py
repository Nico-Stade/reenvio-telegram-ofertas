"""
engine/filters/history.py — Filtro estricto de mínimo histórico anti-ruido.
Calcula y filtra basándose en el PRECIO MÁS BAJO DEL HISTORIAL.
"""
from typing import Optional
from core.models import DealItem, FilterResult
from engine.filters.base import BaseFilter


class StrictHistoricalLowFilter(BaseFilter):
    """
    Filtro de Mínimo Histórico:
    - Compara oferta actual contra el precio más bajo del historial (previous_historical_low).
    - Exige que el precio actual sea menor o igual al récord histórico más bajo.
    - Opcionalmente exige una caída mínima porcentual (min_drop_percentage, default 0%).
    - Descarta todo lo que sea más caro que su mínimo anterior (puro ruido).
    """

    def __init__(
        self,
        allow_no_history: bool = False,
        min_discount_if_no_history: int = 80,
        min_drop_percentage: float = 0.0,
    ):
        self.allow_no_history = allow_no_history
        self.min_discount_if_no_history = min_discount_if_no_history
        self.min_drop_percentage = min_drop_percentage

    async def evaluate(self, deal: DealItem) -> FilterResult:
        min_hist = deal.previous_historical_low

        # Caso 1: El producto tiene historial informado
        if min_hist is not None:
            drop = deal.discount_vs_history or 0.0

            if deal.offer_price <= min_hist and drop >= self.min_drop_percentage:
                return FilterResult(
                    passed=True,
                    filter_name=self.name,
                    reason=(
                        f"Mínimo histórico verificado: ${deal.offer_price:,} <= "
                        f"mínimo anterior ${min_hist:,} (Rebaja real vs histórico: -{drop:.1f}%)"
                    ),
                )
            else:
                return FilterResult(
                    passed=False,
                    filter_name=self.name,
                    reason=(
                        f"Descartado (Ruido): Precio actual ${deal.offer_price:,} "
                        f"no supera el mínimo histórico ${min_hist:,} (Rebaja real: {drop:.1f}%)"
                    ),
                )

        # Caso 2: El mensaje no tiene bloque de historial
        if self.allow_no_history:
            if deal.discount_percentage >= self.min_discount_if_no_history:
                return FilterResult(
                    passed=True,
                    filter_name=self.name,
                    reason=f"Sin historial previo pero califica por descuento extraordinario ({deal.discount_percentage}% >= {self.min_discount_if_no_history}%)"
                )
            else:
                return FilterResult(
                    passed=False,
                    filter_name=self.name,
                    reason=f"Sin historial y descuento ({deal.discount_percentage}%) menor al requerido sin historial ({self.min_discount_if_no_history}%)"
                )

        return FilterResult(
            passed=False,
            filter_name=self.name,
            reason="Descartado: El mensaje no contiene historial para verificar mínimo histórico."
        )
