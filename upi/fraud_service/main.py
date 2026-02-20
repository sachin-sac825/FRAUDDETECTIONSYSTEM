from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from . import transforms, logging as hashed_logging

app = FastAPI(title="UPI Fraud Service (scaffold)")

class Transaction(BaseModel):
    amount: float
    payer_vpa: str
    payee_vpa: str
    merchant: Optional[str] = None
    timestamp: Optional[str] = None
    behavioral: Optional[Dict[str, Any]] = None
    device: Optional[Dict[str, Any]] = None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/predict")
def predict(tx: Transaction):
    # Sanitize and feature transform
    try:
        sanitized = transforms.sanitize_transaction(tx.dict())
        features = transforms.build_feature_vector(sanitized)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Dummy model score and reason placeholders
    score = 0.02  # placeholder
    label = "not_fraud"
    reasons = ["low_amount", "known_payee"]

    # Log hashed event to persistent store (stub)
    hashed_logging.log_event(sanitized)

    return {
        "label": label,
        "score": score,
        "reasons": reasons,
        "features": features,
    }

@app.get("/reputation/{vpa_hash}")
def reputation(vpa_hash: str):
    # Placeholder reputation response
    return {"vpa_hash": vpa_hash, "flag_count": 0, "reputation_score": 0.0}
