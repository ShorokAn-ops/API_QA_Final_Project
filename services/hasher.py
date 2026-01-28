import hashlib
import json


def canonical_items(items: list[dict]) -> list[dict]:
    clean = []
    for it in items:
        clean.append({
            "item_code": it.get("item_code"),
            "item_name": it.get("item_name"),
            "qty": float(it["qty"]) if it.get("qty") is not None else None,
            "rate": float(it["rate"]) if it.get("rate") is not None else None,
            "amount": float(it["amount"]) if it.get("amount") is not None else None,
            "idx": it.get("idx"),
        })
    # stable order
    clean.sort(key=lambda x: (x.get("item_code") or "", x.get("item_name") or "", x.get("idx") or 0))
    return clean


def items_hash(items: list[dict]) -> str:
    payload = canonical_items(items)
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
