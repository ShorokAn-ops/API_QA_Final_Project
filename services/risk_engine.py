def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_risk(invoice: dict, items: list[dict]) -> dict:
    """
    Simple rule-based risk (אפשר לשפר בהמשך).
    משתמש ב-Quantity + Unit Price כדי לתת CRITICAL במקרים חריגים.
    """
    reasons: list[dict] = []
    rate = 0.0

    for it in items:
        qty = float(it.get("qty") or 0)
        unit_price = float(it.get("rate") or 0)

        if qty >= 30 and unit_price >= 10000:
            rate = max(rate, 1.0)
            reasons.append({"reason": "Extreme quantity & unit price", "details": {"qty": qty, "unit_price": unit_price}})
        elif qty >= 10 and unit_price >= 3000:
            rate = max(rate, 0.9)
            reasons.append({"reason": "High quantity and high unit price", "details": {"qty": qty, "unit_price": unit_price}})
        elif unit_price >= 10000:
            rate = max(rate, 0.8)
            reasons.append({"reason": "Very high unit price", "details": {"unit_price": unit_price}})
        elif qty >= 25:
            rate = max(rate, 0.7)
            reasons.append({"reason": "Very high quantity", "details": {"qty": qty}})

    # invoice total heuristic
    total = float(invoice.get("grand_total") or 0)
    if total >= 200000:
        rate = max(rate, 0.85)
        reasons.append({"reason": "Very high invoice total", "details": {"grand_total": total}})

    rate = clamp01(rate)
    if rate >= 0.9:
        level = "CRITICAL"
    elif rate >= 0.7:
        level = "HIGH"
    elif rate >= 0.4:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {"rate": rate, "risk_level": level, "reasons": reasons}
