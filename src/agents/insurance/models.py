# insurance-agent/models.py
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional
from datetime import date

class ProcedureClaim(BaseModel):
    # Acceptă nume de câmpuri by_name dacă e nevoie
    model_config = ConfigDict(populate_by_name=True)
    name: str
    billed: float  # <— IMPORTANT: numeric, nu str

class Claim(BaseModel):
    # Poți trimite fie aliasurile cu spații (de la Hospital Agent),
    # fie variantele snake_case (în Swagger, de pildă)
    model_config = ConfigDict(populate_by_name=True)

    full_name: str = Field(alias="full name")
    patient_ssn: str = Field(alias="patient SSN")
    hospital_name: str = Field(alias="hospital name")
    date_of_service: date = Field(alias="date of service")
    diagnose: str
    procedures: List[ProcedureClaim]

# Opțional/auxiliar – utile dacă le folosești în alte părți:
class ProcedureRef(BaseModel):
    name: str            # nume canonic, ex: "er_visit"
    category: str        # ex: "imaging"
    price: float         # preț de referință
    text: Optional[str] = None  # descriere/concat pentru RAG (dacă e cazul)

class Policy(BaseModel):
    # suport pentru policy_id sau policyId via alias
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
