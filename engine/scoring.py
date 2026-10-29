"""
engine/scoring.py: Motor de puntuación y clasificación de anomalías de precio (Glitch Score).
Evalúa DealItem de forma multivariable (0 a 100 puntos) para detectar errores de precio reales
y descartar ruido o placeholders de retail.
"""
from typing import Tuple, Dict, Any
from core.models import DealItem

HIGH_TICKET_KEYWORDS = (
    "tv", "smart tv", "televisor", "oled", "qled", "uhd", "4k",
    "notebook", "laptop", "macbook", "ipad", "tablet", "pc gamer",
    "celular", "smartphone", "iphone", "galaxy", "motorola", "xiaomi",
    "refrigerador", "lavadora", "secadora", "lavavajillas", "encimera",
    "sofá", "sofa", "seccional", "colchón", "colchon", "box spring", "cama",
    "bicicleta", "trotadora", "playstation", "ps5", "nintendo", "switch", "xbox",
    "cafetera", "espresso", "perfume", "eau de parfum", "air fryer", "aspiradora", "drone"
)


def calculate_glitch_score(deal: DealItem) -> int:
    """
    Calcula el puntaje de anomalía (0 a 100) para un DealItem.
    Un score >= 75 indica un error de precio crítico o liquidación extraordinaria.
    """
    score, _ = evaluate_glitch_score_with_breakdown(deal)
    return score


def evaluate_glitch_score_with_breakdown(deal: DealItem) -> Tuple[int, Dict[str, int]]:
    """
    Calcula el puntaje de anomalía retornando el desglose detallado de cada dimensión.
    Dimensiones:
    1. Caída vs récord histórico (max 35 pts)
    2. Incongruencia de categoría vs precio absoluto (max 25 pts)
    3. Factor de ahorro monetario absoluto (max 25 pts)
    4. Anomalía en dígitos / céntimos de retail (max 15 pts)
    5. Intensidad del descuento anunciado (max 10 pts)
    6. Penalizaciones anti-ruido (placeholders $9.999.999, baratijas)
    """
    breakdown = {
        "hist_drop": 0,
        "cat_incongruence": 0,
        "abs_savings": 0,
        "odd_digits": 0,
        "advertised_disc": 0,
        "penalties": 0,
    }

    # 1. Caída vs mínimo histórico previo (max 35 pts)
    min_hist = deal.previous_historical_low
    drop = deal.discount_vs_history

    if min_hist and drop is not None:
        if drop >= 85.0:
            breakdown["hist_drop"] = 35
        elif drop >= 70.0:
            breakdown["hist_drop"] = 25
        elif drop >= 50.0:
            breakdown["hist_drop"] = 15
        elif drop >= 30.0:
            breakdown["hist_drop"] = 10
    elif deal.discount_percentage >= 90:
        breakdown["hist_drop"] = 15

    # 2. Incongruencia categoría vs valor absoluto (max 25 pts)
    title_lower = (deal.title or "").lower()
    has_high_ticket = any(kw in title_lower for kw in HIGH_TICKET_KEYWORDS)

    if has_high_ticket:
        if deal.offer_price <= 10000:
            breakdown["cat_incongruence"] = 25
        elif deal.offer_price <= 50000 and (deal.original_price or 0) >= 150000:
            breakdown["cat_incongruence"] = 25
        elif deal.offer_price <= 100000 and (deal.original_price or 0) >= 400000:
            breakdown["cat_incongruence"] = 20
        elif deal.offer_price <= 350000 and (deal.original_price or 0) >= 1000000:
            breakdown["cat_incongruence"] = 20
        elif (deal.original_price or 0) >= 100000 and deal.offer_price <= 25000:
            breakdown["cat_incongruence"] = 20
    else:
        # Categorías generales o abarrotes con precio ridículo (ej. $50 o $300 pesos)
        if deal.offer_price <= 500 and (deal.original_price or 0) >= 5000:
            breakdown["cat_incongruence"] = 25
        elif (deal.original_price or 0) >= 30000 and deal.offer_price <= 3000:
            breakdown["cat_incongruence"] = 20
        elif (deal.original_price or 0) >= 200000 and deal.offer_price <= 50000:
            breakdown["cat_incongruence"] = 15

    # 3. Factor de ahorro monetario absoluto (max 25 pts)
    savings = deal.savings_amount
    if savings >= 1000000:
        breakdown["abs_savings"] = 25
    elif savings >= 400000:
        breakdown["abs_savings"] = 20
    elif savings >= 150000:
        breakdown["abs_savings"] = 15
    elif savings >= 50000:
        breakdown["abs_savings"] = 10

    # 4. Anomalía en dígitos / céntimos de retail (max 15 pts)
    price = deal.offer_price
    last_digit = price % 10

    if last_digit in [1, 2, 3, 4, 6, 7, 8]:
        breakdown["odd_digits"] = 15
    elif price in [1, 10, 50, 100, 300, 500]:
        breakdown["odd_digits"] = 15
    elif price < 1000 and (deal.original_price or 0) > 10000:
        breakdown["odd_digits"] = 10

    # 5. Intensidad del descuento anunciado (max 10 pts)
    if deal.discount_percentage >= 95:
        breakdown["advertised_disc"] = 10
    elif deal.discount_percentage >= 90:
        breakdown["advertised_disc"] = 5

    # 6. Penalizaciones anti-ruido
    # Placeholders de stock de retail agotado ($9.999.999)
    if deal.original_price and deal.original_price >= 9000000 and deal.offer_price > 5000:
        breakdown["penalties"] -= 80

    # Baratijas regulares sin caída extrema
    if deal.original_price and deal.original_price <= 3500 and deal.offer_price > 500:
        breakdown["penalties"] -= 30

    # Sin historial y descuento menor al 80%
    if min_hist is None and deal.discount_percentage < 80:
        breakdown["penalties"] -= 20

    raw = sum(breakdown.values())
    total_score = max(0, min(100, raw))
    return total_score, breakdown

