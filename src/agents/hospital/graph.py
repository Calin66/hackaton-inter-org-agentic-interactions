
from __future__ import annotations
import json
from datetime import date
from typing import List, Optional
from pydantic import BaseModel
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage
from dotenv import load_dotenv  
import os 

from .config import OPENAI_API_KEY, OPENAI_MODEL, HOSPITAL_NAME
from .prompts import system_prompt
from .models import Claim, Procedure, REQUIRED_FIELDS
from .tariff import SYNTHETIC_TARIFF
from .storage import save_claim

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
class AgentState(BaseModel):
    doctor_message: Optional[str] = None
    parsed_claim: Optional[Claim] = None
    missing_fields: List[str] = []
    claim_id: Optional[str] = None
    invoice_preview: Optional[str] = None
    approved: Optional[bool] = None

llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0, openai_api_key=api_key or OPENAI_API_KEY)

def parse_or_request_fields(state: AgentState) -> AgentState:
    messages = [SystemMessage(content=system_prompt())]
    messages.append(HumanMessage(content=state.doctor_message or ""))
    text = llm.invoke(messages).content.strip()
    new_state = state.model_copy(deep=True)
    try:
        payload = json.loads(text)
        payload.setdefault("hospital name", HOSPITAL_NAME)
        payload.setdefault("date of service", date.today().isoformat())
        claim = Claim(**payload)
        new_state.parsed_claim = claim
        new_state.missing_fields = []
        return new_state
    except Exception:
        missing = []
        lower = text.lower()
        for f in REQUIRED_FIELDS:
            if f in lower and f not in missing:
                missing.append(f)
        if not missing:
            for f in REQUIRED_FIELDS:
                if f not in (state.doctor_message or ""):
                    missing.append(f)
        new_state.missing_fields = missing
        return new_state

def enrich_prices_and_store(state: AgentState) -> AgentState:
    if not state.parsed_claim:
        return state
    c = state.parsed_claim
    for p in c.procedures:
        if p.billed is None:
            price = None
            for k, v in SYNTHETIC_TARIFF.items():
                if p.name.strip().lower() == k.lower():
                    price = v; break
            if price is None:
                for k, v in SYNTHETIC_TARIFF.items():
                    if p.name.lower() in k.lower() or k.lower() in p.name.lower():
                        price = v; break
            p.billed = price or 0
    state.claim_id = save_claim(c, state.claim_id)
    return state

def make_invoice_preview(state: AgentState) -> AgentState:
    c = state.parsed_claim
    if not c: return state
    total = sum(p.billed or 0 for p in c.procedures)
    lines = [
        f"=== {HOSPITAL_NAME} — Claim Preview ===",
        f"Patient: {c.full_name} (SSN: {c.patient_ssn})",
        f"Date of service: {c.date_of_service}",
        f"Diagnose: {c.diagnose}",
        "", "Procedures:",
    ]
    for p in c.procedures:
        lines.append(f"  • {p.name} — ${p.billed}")
    lines += ["", f"Subtotal billed: ${total}", "",
              "If all looks correct, reply 'approve'. If not, say what to change."]
    state.invoice_preview = "\n".join(lines)
    return state

def finalize_or_request_changes(state: AgentState) -> AgentState:
    feedback = (state.doctor_message or "").strip().lower()
    new_state = state.model_copy(deep=True)
    if any(t in feedback for t in ["approve", "ok", "da", "confirm"]):
        new_state.approved = True
        return new_state
    c = new_state.parsed_claim
    if not c: return new_state
    if "ssn" in feedback and "to" in feedback:
        try:
            new_ssn = feedback.split("ssn")[1].split("to")[1].strip().split()[0]
            c.patient_ssn = new_ssn
        except: pass
    if "name" in feedback and "to" in feedback:
        try:
            new_name = feedback.split("name")[1].split("to")[1].strip()
            c.full_name = new_name.title()
        except: pass
    if "add procedure" in feedback:
        try:
            new_proc = feedback.split("add procedure")[1].strip()
            if new_proc:
                price = SYNTHETIC_TARIFF.get(new_proc, 0)
                c.procedures.append(Procedure(name=new_proc, billed=price))
        except: pass
    state.parsed_claim = c
    return state

workflow = StateGraph(AgentState)
workflow.add_node("parse_or_request_fields", parse_or_request_fields)
workflow.add_node("enrich_prices_and_store", enrich_prices_and_store)
workflow.add_node("make_invoice_preview", make_invoice_preview)
workflow.add_node("finalize_or_request_changes", finalize_or_request_changes)
workflow.set_entry_point("parse_or_request_fields")
workflow.add_edge("parse_or_request_fields", "enrich_prices_and_store")
workflow.add_edge("enrich_prices_and_store", "make_invoice_preview")
workflow.add_edge("make_invoice_preview", END)
workflow.add_edge("finalize_or_request_changes", "enrich_prices_and_store")
app_graph = workflow.compile()
