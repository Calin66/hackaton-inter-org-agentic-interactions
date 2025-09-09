from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List
from .models import MessageRequest, PendingResponse, ApprovedResponse
from .llm import extract_fields, interpret_doctor_message
from .billing import (
    load_tariff, build_initial_invoice, pretty_invoice,
    apply_discount, add_procedure_free_text, remove_procedure_by_index,
    remove_procedure_by_name, set_price
)
from .state import store
from .config import init_env

app = FastAPI(title="Hospital Billing Agent (NLU)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TARIFF: Dict[str, float] = {}

REQUIRED_FIELDS = ["patient name", "patient SSN", "diagnose", "procedures"]

def missing_required(invoice: Dict[str, Any]) -> List[str]:
    missing = []
    for key in REQUIRED_FIELDS:
        if key == "procedures":
            if not invoice.get("procedures"):
                missing.append("procedures")
        else:
            if not str(invoice.get(key, "")).strip():
                missing.append(key)
    return missing

def ask_for_missing(missing_keys: List[str]) -> str:
    labels = {
        "patient name": "Full Name",
        "patient SSN": "SSN",
        "diagnose": "Diagnose",
        "procedures": "Procedures",
    }
    items = ", ".join(labels.get(k, k) for k in missing_keys)
    return (
        f"Missing required information: {items}. "
        "Please provide them in free text (e.g., "
        "'Full name John Doe, SSN 123..., Diagnose M16.5, Procedures: ...')."
    )

@app.on_event("startup")
def _startup():
    init_env()
    global TARIFF
    TARIFF = load_tariff()

@app.post("/doctor_message")
def doctor_message(req: MessageRequest):
    global TARIFF
    if not TARIFF:
        try:
            TARIFF = load_tariff()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    sid = store.ensure(req.session_id)
    session = store.get(sid)

    # First turn (or after approval/cleared session)
    if session["status"] in ("empty", "approved") or not session.get("invoice"):
        extracted = extract_fields(req.message)
        invoice = build_initial_invoice(extracted, TARIFF)
        session.update({"status": "pending", "invoice": invoice})
        store.upsert(sid, session)

        miss = missing_required(invoice)
        if miss:
            reply = ask_for_missing(miss)
        else:
            reply = (
                "Here is the proposed invoice based on your notes.\n\n"
                + pretty_invoice(invoice)
                + "\n\nYou can reply in natural language, e.g.: "
                  "'apply 10% discount', 'remove the second procedure', "
                  "'add specialist consult', 'set ER visit high complexity to 1150', "
                  "'i confirm, the data is correct'."
            )
        return PendingResponse(session_id=sid, agent_reply=reply, invoice=invoice).model_dump()

    # Follow-up turns (NLU)
    invoice = session["invoice"]
    current_lines = [p["name"] for p in invoice.get("procedures", [])]

    action = interpret_doctor_message(req.message, current_lines)
    atype = action.get("type")
    params = action.get("params", {}) or {}

    status_note = None

    if atype == "approve":
        miss = missing_required(invoice)
        if miss:
            reply = ask_for_missing(miss)
            session.update({"status": "pending", "invoice": invoice})
            store.upsert(sid, session)
            return PendingResponse(session_id=sid, agent_reply=reply, invoice=invoice).model_dump()

        session.update({"status": "approved", "invoice": invoice})
        store.upsert(sid, session)
        return ApprovedResponse(session_id=sid, final_json=invoice).model_dump()

    elif atype == "discount_percent":
        pct = float(params.get("percent", 0))
        status_note = apply_discount(invoice, pct)

    elif atype == "add_procedure":
        status_note = add_procedure_free_text(invoice, TARIFF, params.get("procedure_free_text", ""))

    elif atype == "remove_procedure_by_index":
        idx = int(params.get("index", 0))
        status_note = remove_procedure_by_index(invoice, idx)

    elif atype == "remove_procedure_by_name":
        status_note = remove_procedure_by_name(invoice, params.get("name", ""))

    elif atype == "set_price":
        name = params.get("name", "")
        amount = float(params.get("amount", 0))
        status_note = set_price(invoice, name, amount)

    elif atype == "provide_fields":
        extracted = extract_fields(req.message)
        for k in ["patient name", "patient SSN", "diagnose"]:
            if extracted.get(k):
                invoice[k] = extracted[k]
        if extracted.get("procedures"):
            for raw in extracted["procedures"]:
                add_procedure_free_text(invoice, TARIFF, raw)

    else:
        status_note = (
            "Sorry, I didn't understand. You can say: 'apply 10% discount', "
            "'remove the second procedure', 'add specialist consult', "
            "'set ER visit high complexity to 1150', or 'approve'."
        )

    miss = missing_required(invoice)
    if miss:
        reply = (status_note + "\n" if status_note else "") + ask_for_missing(miss)
    else:
        reply = (
            (status_note + "\n\n" if status_note else "")
            + pretty_invoice(invoice)
            + "\n\nReply in natural language or say 'approve' to finalize."
        )

    session.update({"status": "pending", "invoice": invoice})
    store.upsert(sid, session)
    return PendingResponse(session_id=sid, agent_reply=reply, invoice=invoice).model_dump()
