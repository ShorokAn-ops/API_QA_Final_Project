from typing import Any, Dict, List
from openai import OpenAI

from core.config import settings


class AIRiskClient:
    """
    OpenAI-based risk enrichment.
    This service NEVER replaces rule-based risk.
    It only adds:
      - risk_adjustment (small delta)
      - extra_reasons (textual / semantic)
      - supplier_signal (LOW / MEDIUM / HIGH)
    """

    def __init__(self) -> None:
        if not settings.AI_ENABLED or settings.AI_PROVIDER != "openai":
            self.enabled = False
            self.client = None
            return

        self.enabled = True
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    def analyze_invoice(
        self,
        *,
        invoice: Dict[str, Any],
        items: List[Dict[str, Any]],
        base_rate: float,
        base_level: str,
    ) -> Dict[str, Any]:
        """
        Returns a SAFE, bounded AI response.
        If AI fails → returns neutral enrichment.
        """

        # Hard fallback (QA-safe)
        fallback = {
            "risk_adjustment": 0.0,
            "extra_reasons": [],
            "supplier_signal": "UNKNOWN",
        }

        if not self.enabled:
            return fallback

        try:
            prompt = self._build_prompt(
                invoice=invoice,
                items=items,
                base_rate=base_rate,
                base_level=base_level,
            )

            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=0.1,  # low = stable for QA
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a financial risk analysis engine. "
                            "You MUST respond with VALID JSON ONLY. "
                            "No explanations, no markdown, no text outside JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                timeout=15,
            )

            raw = resp.choices[0].message.content
            data = self._safe_parse_json(raw)

            # Validate & clamp
            return {
                "risk_adjustment": self._clamp(
                    float(data.get("risk_adjustment", 0.0)), -0.2, 0.2
                ),
                "extra_reasons": list(data.get("extra_reasons", []))[:5],
                "supplier_signal": str(data.get("supplier_signal", "UNKNOWN")),
            }

        except Exception:
            # NEVER break sync / API because of AI
            return fallback

    # -------------------------
    # Helpers
    # -------------------------

    def _build_prompt(
        self,
        *,
        invoice: Dict[str, Any],
        items: List[Dict[str, Any]],
        base_rate: float,
        base_level: str,
    ) -> str:
        return f"""
Analyze the following purchase invoice and supplier behavior.

RULE-BASED RESULT (already computed, do NOT override):
- base_rate: {base_rate}
- base_level: {base_level}

Invoice:
{invoice}

Items:
{items}

TASK:
Return a JSON object with:
- risk_adjustment: number between -0.2 and +0.2
- extra_reasons: list of short strings (max 5)
- supplier_signal: one of ["LOW", "MEDIUM", "HIGH", "UNKNOWN"]

IMPORTANT:
- Do NOT repeat the rule-based reasons.
- Focus on semantic / contextual risk.
- JSON ONLY.
"""

    def _safe_parse_json(self, raw: str) -> Dict[str, Any]:
        import json

        # Trim just in case (defensive)
        raw = raw.strip()
        return json.loads(raw)

    def _clamp(self, x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, x))
