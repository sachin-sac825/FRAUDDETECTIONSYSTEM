import re
import hashlib
import hmac
import json
from typing import Dict, Any

# Use a fixed salt for scaffold; in prod, use secure key management
SALT = b"scaffold_secret_salt"

VPA_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+$")


def hash_vpa_on_device(vpa_raw: str) -> str:
    """Hash a VPA (HMAC-SHA256) deterministically for pseudonymous id."""
    v = vpa_raw.strip().lower()
    return hmac.new(SALT, v.encode("utf-8"), hashlib.sha256).hexdigest()


def sanitize_vpa(vpa_raw: str) -> str:
    v = vpa_raw.strip()
    # remove hidden/zero-width characters
    v = "".join(ch for ch in v if ord(ch) > 31)
    if not VPA_PATTERN.match(v):
        raise ValueError("Invalid VPA format")
    return v


def sanitize_transaction(tx: Dict[str, Any]) -> Dict[str, Any]:
    tx = dict(tx)
    payer = tx.get("payer_vpa")
    payee = tx.get("payee_vpa")
    if not payer or not payee:
        raise ValueError("payer_vpa and payee_vpa required")

    tx["payer_vpa_sanitized"] = sanitize_vpa(payer)
    tx["payee_vpa_sanitized"] = sanitize_vpa(payee)

    tx["payer_vpa_hash"] = hash_vpa_on_device(tx["payer_vpa_sanitized"])
    tx["payee_vpa_hash"] = hash_vpa_on_device(tx["payee_vpa_sanitized"])

    # merchant
    m = tx.get("merchant") or "unknown"
    tx["merchant"] = m.strip() if isinstance(m, str) else "unknown"

    # amount clipping as placeholder (0.1-99.9 percentile placeholder values)
    try:
        amt = float(tx.get("amount", 0.0))
    except Exception:
        raise ValueError("Invalid amount")
    # simple clipping for scaffold
    tx["amount_clipped"] = max(1.0, min(100000.0, amt))

    # fill missing fields
    tx.setdefault("behavioral", {})
    tx.setdefault("device", {})

    return tx


def build_feature_vector(tx: Dict[str, Any]) -> Dict[str, Any]:
    # Deterministic, minimal feature assembly for scaffold
    feat = {}
    feat["amount_log"] = round(float(tx.get("amount_clipped", 0.0)) + 1.0, 6)
    feat["merchant_unknown"] = 1 if tx.get("merchant") == "unknown" else 0
    # behavioral placeholders
    behavioral = tx.get("behavioral", {})
    feat["typing_speed"] = float(behavioral.get("typing_speed", 0.0))
    feat["paste_flag"] = 1 if behavioral.get("paste_detected") else 0
    # simple known-payee flag (placeholder)
    feat["known_payee"] = 0
    return feat


def serialize_feature_vector(feat: Dict[str, Any]) -> str:
    return json.dumps(feat, sort_keys=True)
