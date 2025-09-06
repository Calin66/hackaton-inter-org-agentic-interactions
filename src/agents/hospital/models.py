
from __future__ import annotations
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field, validator

class Procedure(BaseModel):
    name: str
    billed: Optional[int] = None

class Claim(BaseModel):
    full_name: str = Field(..., alias="full name")
    patient_ssn: str = Field(..., alias="patient SSN")
    hospital_name: str = Field(..., alias="hospital name")
    date_of_service: str = Field(..., alias="date of service")
    diagnose: str
    procedures: List[Procedure]

    class Config:
        populate_by_name = True

    @validator("date_of_service")
    def validate_date(cls, v: str):
        y, m, d = map(int, v.split("-"))
        _ = date(y, m, d)
        return v

REQUIRED_FIELDS = ["full name", "patient SSN", "diagnose", "procedures"]
