from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any

class ProcedureLine(BaseModel):
    name: str
    billed: float

class Invoice(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    patient_name: str = Field(alias="patient name")
    patient_ssn: str = Field(alias="patient SSN")
    hospital_name: str = Field(alias="hospital name")
    date_of_service: str = Field(alias="date of service")
    diagnose: str
    procedures: List[ProcedureLine] = []

class MessageRequest(BaseModel):
    session_id: Optional[str] = None
    message: str

class PendingResponse(BaseModel):
    session_id: str
    status: str = "pending"
    agent_reply: str
    invoice: Dict[str, Any]

class ApprovedResponse(BaseModel):
    session_id: str
    status: str = "approved"
    final_json: Dict[str, Any]
    file_path: Optional[str] = None  # <-- NEW: path to saved claim file
