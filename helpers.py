import re
import json
import time
import hashlib
from typing import Any, Optional, Dict, Tuple
from fastapi import UploadFile

# ---------------------------
# Simple internal TTL cache (in-memory)
# ---------------------------
CacheStore = Dict[str, Tuple[float, Any]]
# value is stored as: key -> (expires_at_epoch, data)

def cache_get(store: CacheStore, key: str) -> Optional[Any]:
    """
    Return cached value if not expired, else None.
    """
    if not store:
        return None
    hit = store.get(key)
    if not hit:
        return None

    expires_at, data = hit
    if time.time() >= expires_at:
        store.pop(key, None)
        return None
    return data


def cache_set(store: CacheStore, key: str, value: Any, ttl_seconds: int) -> None:
    """
    Set cached value with ttl.
    """
    if ttl_seconds <= 0:
        # treat as "no cache"
        store.pop(key, None)
        return
    store[key] = (time.time() + ttl_seconds, value)


def cache_clear_prefix(store: CacheStore, prefix: str) -> int:
    """
    Remove all keys starting with prefix. Returns number removed.
    """
    if not store:
        return 0
    keys = [k for k in store.keys() if k.startswith(prefix)]
    for k in keys:
        store.pop(k, None)
    return len(keys)
