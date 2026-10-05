"""
engine/filters/base.py — Interfaz base para los filtros de ofertas.
"""
from abc import ABC, abstractmethod
from core.models import DealItem, FilterResult


class BaseFilter(ABC):
    """Clase base abstracta para cualquier filtro en el pipeline."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    async def evaluate(self, deal: DealItem) -> FilterResult:
        """
        Evalúa el DealItem.
        Retorna FilterResult(passed=True/False, filter_name=..., reason=...)
        """
        pass
