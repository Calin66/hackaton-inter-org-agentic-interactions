# insurance-agent/models.py
from pydantic import BaseModel, Field, ConfigDict
from typing import (
    List,
    Dict,
    Optional,
    Any,
    Literal,
)  # <--- asigură-te că ai Any, Literal
from datetime import date


class ProcedureClaim(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    billed: float


# --- NOU: structura pentru work accident (opțional) ---
class WorkAccidentInfo(BaseModel):
    suspected: bool = False
    narrative: Optional[str] = None
    location: Optional[str] = None
    during_work_hours: Optional[bool] = None
    sick_leave_days: Optional[int] = None
    happened_at: Optional[str] = None  # ISO datetime string


class Claim(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    full_name: str = Field(alias="full name")
    patient_ssn: str = Field(alias="patient SSN")
    hospital_name: str = Field(alias="hospital name")
    date_of_service: date = Field(alias="date of service")
    diagnose: str
    procedures: List[ProcedureClaim]

    # --- NOU, opțional ---
    work_accident: Optional[WorkAccidentInfo] = None


class ProcedureRef(BaseModel):
    name: str
    category: str
    price: float
    text: Optional[str] = None


class Policy(BaseModel):
    policy_id: Optional[str] = Field(default=None, alias="policyId")
    member: Dict[str, str]
    eligibility: Dict[str, str]
    coverage: Dict[str, Dict]
    limits: Dict[str, Dict]


class AdjudicatedItem(BaseModel):
    claim_name: str
    matched_name: str
    category: str
    billed: float
    ref_price: float
    allowed_amount: float
    payable_amount: float
    notes: str


class AdjudicationResult(BaseModel):
    policy_id: Optional[str]
    eligible: bool
    reason: Optional[str]
    items: List[AdjudicatedItem]
    total_payable: float
    pretty_message: str

    # --- NOI: câmpuri pe care le setezi în /adjudicate ---
    payer: Literal["patient", "corporation"] = "patient"
    corporate_meta: Optional[Dict[str, Any]] = None
