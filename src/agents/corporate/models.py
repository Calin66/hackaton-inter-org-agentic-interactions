# agents/corporate/models.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class WorkAccidentInput(BaseModel):
    # Info venită din Hospital/Insurance
    suspected: bool = False
    narrative: Optional[str] = None  # cum s-a întâmplat
    location: Optional[str] = None  # unde s-a întâmplat
    during_work_hours: Optional[bool] = None
    sick_leave_days: Optional[int] = None
    happened_at: Optional[str] = None  # ISO datetime dacă există
    raw_doctor_text: Optional[str] = None
    claim_snapshot: Optional[Dict[str, Any]] = (
        None  # copia claimului ca să arătăm context la aprobator
    )


class CorporateDecision(BaseModel):
    decision_id: str
    is_work_accident: Optional[bool] = None  # None = pending human
    rationale: Optional[str] = None
    status: str = "pending"  # pending | approved | denied
    approver: Optional[str] = None
    payer: Optional[str] = None  # "patient" | "corporation"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
