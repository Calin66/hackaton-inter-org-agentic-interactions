from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List
from pathlib import Path
from uuid import uuid4
from datetime import datetime
import json
import os
import time

from .models import MessageRequest, PendingResponse, ApprovedResponse
from .llm import (
    extract_fields,
    interpret_doctor_message,
    generate_missing_prompt,
    resolve_procedure_name,
)
from .billing import (
    load_tariff, build_initial_invoice, pretty_invoice,
    apply_discount, add_procedure_free_text, add_procedure_exact,
    remove_procedure_by_index, remove_procedure_by_name, set_price
)
from .state import store
from .config import init_env

app = FastAPI(title="Hospital Billing Agent (NLU, talkative)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TARIFF: Dict[str, float] = {}
REQUIRED_FIELDS = ["patient name", "patient SSN", "diagnose", "procedures"]


# ---------- helpers (persisting + canonicalization + title) ----------

def _claims_dir() -> Path:
    d = Path("data/claims")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _canonicalize_invoice(inv: Dict[str, Any]) -> Dict[str, Any]:
    """
    Produce the JSON structure the insurer expects.
    - Keep keys as specified.
    - For 'billed' ensure int if whole number, else 2 decimal float.
    """
    out: Dict[str, Any] = {
        "patient name": inv.get("patient name", ""),
        "patient SSN": inv.get("patient SSN", ""),
        "hospital name": inv.get("hospital name", ""),
        "date of service": inv.get("date of service", ""),
        "diagnose": inv.get("diagnose", ""),
        "procedures": [],
    }
    for p in inv.get("procedures", []):
        try:
            billed = float(p.get("billed", 0))
            billed = int(billed) if billed.is_integer() else round(billed, 2)
        except Exception:
            billed = 0
        out["procedures"].append({"name": p.get("name", ""), "billed": billed})
    return out


def generate_claim_title(inv: Dict[str, Any]) -> str:
    """
    Create a short, human-friendly title such as:
    'John Doe — Appendectomy · $3,450 on 2025-09-09'
    (Falls back gracefully if fields are missing.)
    """
    patient = (inv.get("patient name") or "").strip()
    if not patient:
        patient = str(inv.get("patient SSN") or "Patient").strip()

    procedures = inv.get("procedures") or []
    main_proc = ""
    if procedures:
        p = procedures[0] or {}
        main_proc = p.get("name") or ""

    # compute total best-effort
    total = None
    try:
        total = sum(float(p.get("billed") or 0) for p in procedures) if procedures else None
    except Exception:
        total = None

    raw_date = inv.get("date of service")
    try:
        dt = datetime.fromisoformat(str(raw_date).replace("Z", "")) if raw_date else datetime.utcnow()
    except Exception:
        dt = datetime.utcnow()

    proc_part = f" — {main_proc}" if main_proc else ""
    total_part = f" · ${total:,.2f}" if isinstance(total, (int, float)) else ""
    date_part = f" on {dt.date().isoformat()}"

    title = f"{patient}{proc_part}{total_part}{date_part}"
    return " ".join(title.split())[:120]


def _save_claim(final_json: Dict[str, Any]) -> str:
    """
    Save the already-canonicalized claim (including 'title') into data/claims/.
    Use a filename that’s deterministic enough for debugging.
    """
    ssn = str(final_json.get("patient SSN", "")).strip() or "unknown"
    dos = str(final_json.get("date of service", "")).replace("-", "") or "nodate"
    fname = f"{dos}_{ssn}_{uuid4().hex[:8]}.json"
    path = _claims_dir() / fname
    path.write_text(json.dumps(final_json, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


# ---------- misc business helpers ----------

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


# ---------- app lifecycle ----------

@app.on_event("startup")
def _startup():
    init_env()
    global TARIFF
    TARIFF = load_tariff()


# ---------- routes ----------

@app.get("/hello")
def hello():
    return {
        "message": (
            "Hello! I’m your hospital billing assistant. "
            "How can I help today—create a new invoice, add or remove procedures, "
            "apply a discount, or finalize and approve one?"
        )
    }


@app.post("/doctor_message")
def doctor_message(req: MessageRequest):
    """
    Single endpoint that manages the natural-language flow.
    Returns either a PendingResponse (keep editing) or ApprovedResponse (final JSON + saved path).
    """
    global TARIFF
    if not TARIFF:
        try:
            TARIFF = load_tariff()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    sid = store.ensure(req.session_id)
    session = store.get(sid)

    # First turn (or after fresh approval)
    if session["status"] in ("empty", "approved") or not session.get("invoice"):
        extracted = extract_fields(req.message)
        invoice = build_initial_invoice(extracted, TARIFF)
        session.update({"status": "pending", "invoice": invoice})
        store.upsert(sid, session)

        miss = missing_required(invoice)
        if miss:
            reply = generate_missing_prompt(invoice, miss)
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

    # Follow-up turns
    invoice = session["invoice"]
    current_lines = [p["name"] for p in invoice.get("procedures", [])]

    action = interpret_doctor_message(req.message, current_lines)
    atype = action.get("type")
    params = action.get("params", {}) or {}

    status_note = None

    if atype == "smalltalk":
        reply = params.get("reply") or "Hi! How can I help with the invoice?"
        return PendingResponse(session_id=sid, agent_reply=reply, invoice=invoice).model_dump()

    if atype == "approve":
        miss = missing_required(invoice)
        if miss:
            reply = generate_missing_prompt(invoice, miss)
            session.update({"status": "pending", "invoice": invoice})
            store.upsert(sid, session)
            return PendingResponse(session_id=sid, agent_reply=reply, invoice=invoice).model_dump()

        # 👇 NEW: add a friendly title and save canonical JSON
        final_json = _canonicalize_invoice(invoice)
        final_json["title"] = generate_claim_title(final_json)

        file_path = _save_claim(final_json)

        session.update({"status": "approved", "invoice": final_json})
        store.upsert(sid, session)

        return ApprovedResponse(
            session_id=sid,
            final_json=final_json,
            file_path=file_path
        ).model_dump()

    elif atype == "discount_percent":
        pct = float(params.get("percent", 0))
        status_note = apply_discount(invoice, pct)

    elif atype == "add_procedure":
        wanted = (params.get("procedure_free_text") or "").strip()
        llm_choice = resolve_procedure_name(wanted, list(TARIFF.keys()))
        if llm_choice:
            status_note = add_procedure_exact(invoice, TARIFF, llm_choice) + " (via AI match)"
        else:
            status_note = add_procedure_free_text(invoice, TARIFF, wanted)

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
                wanted = raw.strip()
                llm_choice = resolve_procedure_name(wanted, list(TARIFF.keys()))
                if llm_choice:
                    add_procedure_exact(invoice, TARIFF, llm_choice)
                else:
                    add_procedure_free_text(invoice, TARIFF, wanted)

    else:
        status_note = (
            "Sorry, I didn't understand. You can say: 'apply 10% discount', "
            "'remove the second procedure', 'add specialist consult', "
            "'set ER visit high complexity to 1150', or 'approve'."
        )

    # Rebuild reply after edits
    miss = missing_required(invoice)
    if miss:
        pre = (status_note + "\n" if status_note else "")
        reply = pre + generate_missing_prompt(invoice, miss)
    else:
        reply = (
            (status_note + "\n\n" if status_note else "")
            + pretty_invoice(invoice)
            + "\n\nReply in natural language or say 'approve' to finalize."
        )

    session.update({"status": "pending", "invoice": invoice})
    store.upsert(sid, session)
    return PendingResponse(session_id=sid, agent_reply=reply, invoice=invoice).model_dump()
