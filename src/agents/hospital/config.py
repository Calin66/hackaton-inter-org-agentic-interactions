from __future__ import annotations
import os

# Base data directory for hospital agent (can be overridden with env var)
DATA_DIR = os.getenv("HOSPITAL_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)

# Subfolders
CLAIMS_DIR = os.path.join(DATA_DIR, "claims")
os.makedirs(CLAIMS_DIR, exist_ok=True)
