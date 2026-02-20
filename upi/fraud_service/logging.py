import json
import os
from typing import Dict, Any

LOG_PATH = os.path.join(os.path.dirname(__file__), "events.log")


def log_event(tx: Dict[str, Any]):
    """Append a minimal hashed event to a local log file (scaffold)."""
    rec = {"event": "transaction", "id": tx.get("payer_vpa_hash")[:8], "summary": {"amount": tx.get("amount_clipped"), "merchant": tx.get("merchant")}}
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return True
