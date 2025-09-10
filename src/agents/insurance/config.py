# agents/insurance/config.py
import os

INSURANCE_URL = os.getenv("INSURANCE_URL", "http://localhost:8001/adjudicate")
DATA_DIR = os.getenv("DATA_DIR", "data")
CORPORATE_AGENT_URL = os.getenv("CORPORATE_AGENT_URL", "http://localhost:8003/decide")
