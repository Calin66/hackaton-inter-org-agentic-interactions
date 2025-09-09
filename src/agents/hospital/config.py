from dotenv import load_dotenv
import os
from pathlib import Path

def init_env() -> None:
    # Load .env if present; don't override OS-provided env vars
    load_dotenv(override=False)

# Default URL for the Insurance Agent FastAPI chat endpoint
INSURANCE_AGENT_URL = os.getenv("INSURANCE_AGENT_URL", "http://localhost:8001/chat")

# Data directory for hospital-side artifacts (e.g., saved decisions)
DATA_DIR = os.getenv("HOSPITAL_DATA_DIR", str(Path("data").absolute()))

