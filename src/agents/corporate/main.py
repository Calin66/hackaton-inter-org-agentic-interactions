# agents/corporate/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

app = FastAPI(title="Corporate Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class WorkAccident(BaseModel):
    suspected: bool = False
    narrative: Optional[str] = None
    location: Optional[str] = None
    during_work_hours: Optional[bool] = None
    sick_leave_days: Optional[int] = None
    happened_at: Optional[str] = None  # ISO or free text


class DecideRequest(BaseModel):
    policy_id: Optional[str] = None
    work_accident: WorkAccident
    patient: Dict[str, Any] = {}
    context: Dict[str, Any] = {}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/decide")
def decide(req: DecideRequest):
    w = req.work_accident
    # Simple demo rules:
    # - need suspected=True
    # - pass if during_work_hours == True OR narrative contains "drum direct"
    narrative = (w.narrative or "").lower()
    clause1 = w.during_work_hours is True
    clause2 = ("drum direct" in narrative) or ("direct spre client" in narrative)

    passes = []
    fails = []
    if clause1:
        passes.append(
            {
                "id": "HRS-005",
                "title": "Accident în timpul programului",
                "verdict": "pass",
            }
        )
    else:
        fails.append(
            {
                "id": "HRS-005",
                "title": "Accident în timpul programului",
                "verdict": "fail",
            }
        )
    if clause2:
        passes.append(
            {
                "id": "TRAVEL-001",
                "title": "Deplasare directă la client",
                "verdict": "pass",
            }
        )
    else:
        fails.append(
            {
                "id": "TRAVEL-001",
                "title": "Deplasare directă la client",
                "verdict": "fail",
            }
        )

    ok = w.suspected and (clause1 or clause2)
    reason = (
        ("Accident de muncă confirmat." if ok else "Nu se confirmă accident de muncă.")
        + " Motiv: "
        + ", ".join(
            [c["title"] for c in passes if c["verdict"] == "pass"]
            or ["nicio clauză îndeplinită"]
        )
    )

    return {
        "decision_id": f"DEC-{(req.policy_id or 'NA')}",
        "is_work_accident": bool(ok),
        "reason": reason,
        "confidence": 0.85 if ok else 0.5,
        "evidence": w.model_dump(),
        "policy_clauses": passes + fails,
    }
