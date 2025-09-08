import json
import os
from datetime import date
from typing import Optional, Dict, List
from sqlalchemy import create_engine, text

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
POLICIES_PATH = os.path.join(DATA_DIR, "policies.json")
SQLITE_PATH = os.path.join(DATA_DIR, "usage.sqlite3")

engine = create_engine(f"sqlite:///{SQLITE_PATH}", future=True)

def init_db(seed: bool = False):
    os.makedirs(DATA_DIR, exist_ok=True)
    with engine.begin() as conn:
        # usage pentru limite anuale
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS usage (
            patient_ssn TEXT NOT NULL,
            category TEXT NOT NULL,
            year INTEGER NOT NULL,
            used INTEGER NOT NULL,
            PRIMARY KEY (patient_ssn, category, year)
        )
        """))

        # catalogul de proceduri – sursa pentru RAG (IN LOCUL procedures.json)
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS procedure_catalog (
            name TEXT PRIMARY KEY,            -- nume canonic: ex. 'er_visit', 'x_ray_forearm'
            category TEXT NOT NULL,           -- ex. 'er_visit', 'imaging'
            reference_price REAL NOT NULL,    -- prețul de referință
            aliases TEXT                      -- JSON array cu aliasuri (opțional)
        )
        """))

        if seed:
            # seed de exemplu (nu în prod)
            conn.execute(text("""
            INSERT INTO procedure_catalog (name, category, reference_price, aliases) VALUES
            ('er_visit','er_visit',1100,'["ER visit","ER visit high complexity","emergency room visit"]'),
            ('x_ray_forearm','imaging',250,'["X-ray forearm","forearm xray","radiography forearm"]')
            ON CONFLICT(name) DO UPDATE SET
              category=excluded.category,
              reference_price=excluded.reference_price,
              aliases=excluded.aliases
            """))

def get_policy_by_ssn(ssn: str) -> Optional[Dict]:
    with open(POLICIES_PATH, "r", encoding="utf-8") as f:
        policies = json.load(f)
    for p in policies:
        m = p.get("member", {})
        found = (
            m.get("patient SSN") or
            m.get("patientSSN") or
            m.get("patient_ssn")
        )
        if found == ssn:
            return p
    return None

def get_usage(patient_ssn: str, category: str, year: int) -> int:
    with engine.begin() as conn:
        res = conn.execute(text("""
            SELECT used FROM usage WHERE patient_ssn=:ssn AND category=:cat AND year=:year
        """), {"ssn": patient_ssn, "cat": category, "year": year}).fetchone()
        return int(res[0]) if res else 0

def increment_usage(patient_ssn: str, category: str, year: int, inc: int = 1):
    with engine.begin() as conn:
        res = conn.execute(text("""
            SELECT used FROM usage WHERE patient_ssn=:ssn AND category=:cat AND year=:year
        """), {"ssn": patient_ssn, "cat": category, "year": year}).fetchone()
        current = int(res[0]) if res else 0
        new_val = current + inc
        conn.execute(text("""
            INSERT INTO usage (patient_ssn, category, year, used)
            VALUES (:ssn, :cat, :year, :used)
            ON CONFLICT(patient_ssn, category, year) DO UPDATE SET used=:used
        """), {"ssn": patient_ssn, "cat": category, "year": year, "used": new_val})

def get_procedure_catalog_rows() -> List[Dict]:
    """Întoarce rândurile din catalogul de proceduri pentru RAG."""
    with engine.begin() as conn:
        res = conn.execute(text("""
            SELECT name, category, reference_price, COALESCE(aliases,'[]') as aliases
            FROM procedure_catalog
        """)).mappings().all()
        rows = []
        for r in res:
            try:
                aliases = json.loads(r["aliases"])
            except Exception:
                aliases = []
            rows.append({
                "name": r["name"],
                "category": r["category"],
                "price": float(r["reference_price"]),
                "aliases": aliases
            })
        return rows
