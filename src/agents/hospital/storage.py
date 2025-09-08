from __future__ import annotations
import os, json, uuid
from typing import Any, Dict, Optional
from pydantic import BaseModel
from .config import CLAIMS_DIR

# Minimal pydantic Claim mirror to serialize properly if needed
try:
    from .models import Claim
except Exception:
    class Claim(BaseModel):  # fallback
        hospital_name: str
        full_name: str
        patient_ssn: str
        diagnose: str
        date_of_service: str
        procedures: list[dict]

def _claim_path(claim_id: str) -> str:
    return os.path.join(CLAIMS_DIR, f"{claim_id}.json")

def save_claim(claim: Claim) -> str:
    claim_id = str(uuid.uuid4())[:8]
    with open(_claim_path(claim_id), "w", encoding="utf-8") as f:
        json.dump(claim.model_dump(by_alias=True), f, ensure_ascii=False, indent=2)
    return claim_id

def load_claim(claim_id: str) -> Dict[str, Any]:
    path = _claim_path(claim_id)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Claim {claim_id} not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
