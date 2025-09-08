import json
import time
import uuid
import hashlib
import requests
from datetime import datetime
from .config import INSURANCE_URL, DATA_DIR
from .storage import save_claim
import os

def _correlation_id() -> str:
    return str(uuid.uuid4())

def _idempotency_key(payload: dict) -> str:
    key_data = {
        "ssn": payload.get("patient SSN"),
        "dos": payload.get("date of service"),
        "procedures": payload.get("procedures", []),
    }
    base = json.dumps(key_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def _decision_path(claim_id: str) -> str:
    return os.path.join(DATA_DIR, f"{claim_id}.decision.json")

def send_to_insurance(payload: dict, claim_id: str | None = None) -> dict:
    correlation = _correlation_id()
    idem_key = _idempotency_key(payload)

    headers = {
        "Content-Type": "application/json",
        "X-Correlation-Id": correlation,
        "X-Idempotency-Key": idem_key,
        "X-Client": "hospital-agent/0.1",
    }

    backoffs = [0, 0.5, 1.0, 2.0]  # secunde
    last_err = None
    for wait in backoffs:
        if wait > 0:
            time.sleep(wait)
        try:
            resp = requests.post(INSURANCE_URL, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            result = resp.json()

            print(f"[HospitalAgent] Sent claim to Insurance.")
            print(f"Correlation ID: {correlation}")
            print(f"Idempotency Key: {idem_key}")
            print(f"Insurance response:\n{result.get('pretty_message', json.dumps(result, indent=2))}")

            if claim_id:
                with open(_decision_path(claim_id), "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2)

            return result
        except Exception as e:
            print(f"[HospitalAgent] Failed to send claim (attempt with {wait}s backoff): {e}")
            last_err = e

    raise RuntimeError(f"Failed to reach Insurance Agent after retries. Last error: {last_err}")
