
import json
from .config import INSURANCE_URL

def send_to_insurance(payload: dict) -> None:
    """Replace with HTTP/queue call as needed. For now, print to console."""
    # Example HTTP call (uncomment to use):
    # import requests
    # requests.post(INSURANCE_URL, json=payload, timeout=5)
    print("[HospitalAgent] Sent claim to InsuranceAgent:")
    print(json.dumps(payload, indent=2))
