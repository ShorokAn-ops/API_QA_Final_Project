import hashlib
import json

def canonical_items(items: list[dict]) -> list[dict]:
    """
    Normalize items for stable hashing:
    - keep only meaningful fields
    - normalize types
    - strip strings
    - sort deterministically
    """
    normalized: list[dict] = []

    for it in items or []:
        normalized.append(
            {
                "idx": int(it.get("idx") or 0),
                "item_code": (it.get("item_code") or "").strip(),
                "item_name": (it.get("item_name") or "").strip(),
                "qty": float(it.get("qty") or 0),
                "rate": float(it.get("rate") or 0),
                "amount": float(it.get("amount") or 0),
            }
        )

    # VERY IMPORTANT: deterministic order
    normalized.sort(key=lambda x: (x["idx"], x["item_code"]))

    return normalized


def items_hash(items: list[dict]) -> str:
    payload = canonical_items(items)
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()