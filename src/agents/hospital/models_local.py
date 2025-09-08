from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class FreeText(BaseModel):
    text: str

class InvoiceDraft(BaseModel):
    full_name: Optional[str] = Field(None, alias="full name")
    patient_ssn: Optional[str] = Field(None, alias="patient SSN")
    hospital_name: Optional[str] = Field(None, alias="hospital name")
    date_of_service: Optional[str] = Field(None, alias="date of service")
    diagnose: Optional[str] = None
    procedures: Optional[List[Dict[str, Any]]] = None

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "full name": "Mark Johnson",
                "patient SSN": "328291609",
                "hospital name": "City Hospital",
                "date of service": "2025-09-01",
                "diagnose": "S52.501A",
                "procedures": [
                    {"name": "ER visit high complexity", "billed": 1200},
                    {"name": "X-ray forearm", "billed": 300},
                ],
            }
        }

REQUIRED_FIELDS = ["full name", "patient SSN", "diagnose", "procedures"]
