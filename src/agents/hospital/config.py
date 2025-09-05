
from __future__ import annotations
import os

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") 
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
HOSPITAL_NAME = os.environ.get("HOSPITAL_NAME", "City Hospital")
DATA_DIR = os.environ.get("HOSPITAL_DATA_DIR", os.path.join(os.getcwd(), "data", "claims"))
INSURANCE_URL = os.environ.get("INSURANCE_URL", "http://localhost:9001/ingest_claim")
