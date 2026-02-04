import os
from pathlib import Path

from dotenv import load_dotenv


def _set_if_missing(dst: str, src: str) -> None:
    """If dst is missing/empty and src exists, copy src -> dst."""
    if (os.getenv(dst) is None or os.getenv(dst) == "") and os.getenv(src):
        os.environ[dst] = os.environ[src]


# ---------------------------------------------------------
# Load .env from project root (same folder as app.py)
# ---------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]  # project root
load_dotenv(ROOT / ".env", override=True)

# ---------------------------------------------------------
# Bi-directional mapping so BOTH styles work:
# - Some code/tests use ERPNEXT_*
# - Some live tests use ERP_*
# ---------------------------------------------------------

# ERPNEXT_* -> ERP_*
_set_if_missing("ERP_BASE_URL", "ERPNEXT_BASE_URL")
_set_if_missing("ERP_API_KEY", "ERPNEXT_API_KEY")
_set_if_missing("ERP_API_SECRET", "ERPNEXT_API_SECRET")

# ERP_* -> ERPNEXT_*
_set_if_missing("ERPNEXT_BASE_URL", "ERP_BASE_URL")
_set_if_missing("ERPNEXT_API_KEY", "ERP_API_KEY")
_set_if_missing("ERPNEXT_API_SECRET", "ERP_API_SECRET")

# ---------------------------------------------------------
# Optional: make tests deterministic (no real AI calls)
# We do NOT override if user already set it explicitly.
# ---------------------------------------------------------
if os.getenv("AI_ENABLED") is None:
    os.environ["AI_ENABLED"] = "false"
