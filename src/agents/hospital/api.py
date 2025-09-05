from __future__ import annotations
import json
from typing import List, Optional, Literal
from fastapi import FastAPI
from pydantic import BaseModel
from .graph import app_graph, AgentState
from .models import Claim
from .insurance_client import send_to_insurance
from .storage import load_claim

app = FastAPI(title="Hospital Agent API")

class DoctorMessage(BaseModel):
    message: str
    claim_id: Optional[str] = None

class AgentResponse(BaseModel):
    status: Literal["need_fields", "preview", "approved"]
    missing: List[str] = []
    claim_id: Optional[str] = None
    invoice_preview: Optional[str] = None
    claim: Optional[dict] = None

def _to_state(s) -> AgentState:
    """Normalize results from LangGraph .invoke() which might return dicts."""
    if isinstance(s, AgentState):
        return s
    if isinstance(s, dict):
        return AgentState(**s)
    # last resort
    return AgentState()

@app.post("/doctor_message", response_model=AgentResponse)
def doctor_message(payload: DoctorMessage):
    if payload.claim_id:
        # follow-up path
        raw = load_claim(payload.claim_id)
        state = AgentState(doctor_message=payload.message, parsed_claim=Claim(**raw), claim_id=payload.claim_id)

        s = app_graph.invoke(state, node="finalize_or_request_changes")
        s = _to_state(s)

        if s.approved:
            send_to_insurance(json.loads(s.parsed_claim.model_dump_json(by_alias=True)))
            return AgentResponse(
                status="approved",
                claim_id=s.claim_id,
                claim=json.loads(s.parsed_claim.model_dump_json(by_alias=True))
            )

        s = app_graph.invoke(s, node="make_invoice_preview")
        s = _to_state(s)

        return AgentResponse(
            status="preview",
            claim_id=s.claim_id,
            invoice_preview=s.invoice_preview,
            claim=json.loads(s.parsed_claim.model_dump_json(by_alias=True)),
        )

    # first pass
    s = app_graph.invoke(AgentState(doctor_message=payload.message))
    s = _to_state(s)

    if s.missing_fields:
        return AgentResponse(status="need_fields", missing=s.missing_fields)

    return AgentResponse(
        status="preview",
        claim_id=s.claim_id,
        invoice_preview=s.invoice_preview,
        claim=json.loads(s.parsed_claim.model_dump_json(by_alias=True)),
    )

# (optional) add CORS if frontend runs separately
try:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
except Exception:
    pass

# Run with:  uvicorn src.agents.hospital.api:app --reload --port 8000
