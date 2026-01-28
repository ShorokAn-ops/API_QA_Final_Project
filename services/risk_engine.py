from typing import Any, List

from core.config import settings
from services.ai_risk import AIRiskClient


_ai = AIRiskClient()


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _level_from_rate(rate: float) -> str:
    if rate >= 0.9:
        return "CRITICAL"
    elif rate >= 0.7:
        return "HIGH"
    elif rate >= 0.4:
        return "MEDIUM"
    else:
        return "LOW"


def _compute_rule_based(invoice: dict, items: list[dict]) -> dict:
    """
    Baseline deterministic risk engine (QA-friendly).
    Uses Quantity + Unit Price + Invoice Total heuristics.

    NEW: Added MEDIUM rules so the system has a realistic ladder:
      LOW -> MEDIUM -> HIGH -> CRITICAL
    """
    reasons: list[dict] = []
    rate = 0.0

    for it in items:
        qty = float(it.get("qty") or 0)
        unit_price = float(it.get("rate") or 0)

        # -------------------------
        # CRITICAL / HIGH (existing)
        # -------------------------
        if qty >= 30 and unit_price >= 10000:
            rate = max(rate, 1.0)
            reasons.append(
                {"reason": "Extreme quantity & unit price", "details": {"qty": qty, "unit_price": unit_price}}
            )
        elif qty >= 10 and unit_price >= 3000:
            rate = max(rate, 0.9)
            reasons.append(
                {"reason": "High quantity and high unit price", "details": {"qty": qty, "unit_price": unit_price}}
            )
        elif unit_price >= 10000:
            rate = max(rate, 0.8)
            reasons.append({"reason": "Very high unit price", "details": {"unit_price": unit_price}})
        elif qty >= 25:
            rate = max(rate, 0.7)
            reasons.append({"reason": "Very high quantity", "details": {"qty": qty}})

        # -------------------------
        # MEDIUM (NEW)
        # -------------------------
        # Medium if unit price is high-ish but not extreme
        if unit_price >= 7000 and unit_price < 10000:
            rate = max(rate, 0.5)
            reasons.append({"reason": "Elevated unit price", "details": {"unit_price": unit_price}})

        # Medium if quantity is notable but not very high
        if qty >= 15 and qty < 25:
            rate = max(rate, 0.45)
            reasons.append({"reason": "Notable quantity", "details": {"qty": qty}})

    # -------------------------
    # Invoice total heuristics
    # -------------------------
    total = float(invoice.get("grand_total") or 0)

    # MEDIUM (NEW): notable invoice total
    if 80000 <= total < 200000:
        rate = max(rate, 0.55)
        reasons.append({"reason": "Notable invoice total", "details": {"grand_total": total}})

    # HIGH (existing): very high invoice total
    if total >= 200000:
        rate = max(rate, 0.85)
        reasons.append({"reason": "Very high invoice total", "details": {"grand_total": total}})

    rate = clamp01(rate)
    level = _level_from_rate(rate)

    return {"rate": float(rate), "risk_level": str(level), "reasons": reasons}


def compute_risk(invoice: dict, items: list[dict]) -> dict:
    """
    Hybrid Risk:
    1) Rule-based deterministic score (source of truth)
    2) Optional OpenAI enrichment (small adjustment + extra reasons)
       + stores one "AI metadata" object into reasons for audit/debug
    """
    base = _compute_rule_based(invoice, items)

    # AI is optional - keep deterministic behavior when disabled
    if not settings.AI_ENABLED or settings.AI_PROVIDER != "openai":
        return base

    # AI enrichment (safe fallback handled inside AIRiskClient)
    ai = _ai.analyze_invoice(
        invoice=invoice,
        items=items,
        base_rate=float(base["rate"]),
        base_level=str(base["risk_level"]),
    )

    adjustment = float(ai.get("risk_adjustment", 0.0))
    supplier_signal = str(ai.get("supplier_signal", "UNKNOWN"))
    extra_reasons = ai.get("extra_reasons", []) or []

    final_rate = clamp01(float(base["rate"]) + adjustment)
    final_level = _level_from_rate(final_rate)

    # Merge reasons
    merged_reasons: List[Any] = list(base.get("reasons") or [])

    # Add AI semantic reasons (human readable)
    for msg in extra_reasons[:5]:
        merged_reasons.append(
            {
                "reason": "AI insight",
                "details": {"message": str(msg)},
            }
        )

    # Add ONE clear AI metadata object (machine + audit friendly)
    merged_reasons.append(
        {
            "reason": "AI metadata",
            "details": {
                "provider": settings.AI_PROVIDER,
                "model": settings.OPENAI_MODEL,
                "risk_adjustment": adjustment,
                "supplier_signal": supplier_signal,
                "base_rate": float(base["rate"]),
                "final_rate": float(final_rate),
            },
        }
    )

    return {
        "rate": float(final_rate),
        "risk_level": str(final_level),
        "reasons": merged_reasons,
    }
