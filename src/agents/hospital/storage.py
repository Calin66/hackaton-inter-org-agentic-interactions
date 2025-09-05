
from __future__ import annotations
import os, json, uuid
from typing import Dict
from .config import DATA_DIR
from .models import Claim

os.makedirs(DATA_DIR, exist_ok=True)

def save_claim(claim: Claim, claim_id: str | None = None) -> str:
    cid = claim_id or str(uuid.uuid4())
    path = os.path.join(DATA_DIR, f"{cid}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(json.loads(claim.model_dump_json(by_alias=True)), f, indent=2)
    return cid

def load_claim(claim_id: str) -> Dict:
    path = os.path.join(DATA_DIR, f"{claim_id}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
