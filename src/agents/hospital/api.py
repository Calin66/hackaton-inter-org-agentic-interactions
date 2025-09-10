from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional
from pathlib import Path
from uuid import uuid4
from datetime import datetime
import json
import requests

from .models import MessageRequest, PendingResponse, ApprovedResponse
from .llm import (
    extract_fields,
    interpret_doctor_message,
    generate_missing_prompt,
    resolve_procedure_name,
)
from .billing import (
    load_tariff, build_initial_invoice, pretty_invoice,
    add_procedure_free_text, add_procedure_exact,
    remove_procedure_by_index, remove_procedure_by_name, set_price
)
from .state import store
from .config import init_env, INSURANCE_AGENT_URL

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

# --------- Pricing helpers (discounts, tax, normalization) ----------
TAX_RATE = 0.15  # 15% tax

def _ensure_proc_fields(invoice: Dict[str, Any]) -> None:
    """Ensure each procedure has 'tariff' (full price), 'discount', and 'billed' (net)."""
    for p in invoice.get("procedures", []):
        # full tariff: prefer tariff table if available
        if "tariff" not in p or p.get("tariff") in (None, 0):
            full = float(TARIFF.get(p.get("name", ""), p.get("billed", 0.0) or 0.0))
            p["tariff"] = round(full, 2)
        # discount amount (currency)
        p["discount"] = round(float(p.get("discount", 0.0) or 0.0), 2)
        # recompute billed (net)
        net = p["tariff"] - p["discount"]
        p["billed"] = round(net if net > 0 else 0.0, 2)

def _recompute_totals(invoice: Dict[str, Any]) -> None:
    """Recompute subtotal/discounts/tax/total from lines."""
    _ensure_proc_fields(invoice)
    subtotal_tariff = round(sum(p.get("tariff", 0.0) for p in invoice.get("procedures", [])), 2)
    discounts_total = round(sum(p.get("discount", 0.0) for p in invoice.get("procedures", [])), 2)
    subtotal_after_discount = round(sum(p.get("billed", 0.0) for p in invoice.get("procedures", [])), 2)
    tax = round(subtotal_after_discount * TAX_RATE, 2)
    total = round(subtotal_after_discount + tax, 2)
    invoice["subtotal"] = subtotal_tariff
    invoice["discounts_total"] = discounts_total
    invoice["tax_rate"] = TAX_RATE
    invoice["tax"] = tax
    invoice["total"] = total

def _apply_discount_all(invoice: Dict[str, Any], percent: float) -> str:
    _ensure_proc_fields(invoice)
    for p in invoice.get("procedures", []):
        p["discount"] = round(p.get("discount", 0.0) + p["tariff"] * (percent / 100.0), 2)
    _recompute_totals(invoice)
    return f"Applied discount of {percent}% to all procedures."

def _apply_discount_index(invoice: Dict[str, Any], percent: float, index_1based: int) -> str:
    _ensure_proc_fields(invoice)
    i = index_1based - 1
    if i < 0 or i >= len(invoice.get("procedures", [])):
        return f"Procedure index {index_1based} out of range."
    p = invoice["procedures"][i]
    p["discount"] = round(p.get("discount", 0.0) + p["tariff"] * (percent / 100.0), 2)
    _recompute_totals(invoice)
    return f"Applied discount of {percent}% to procedure #{index_1based} ({p.get('name','')})."

def _apply_discount_name(invoice: Dict[str, Any], percent: float, name: str) -> str:
    _ensure_proc_fields(invoice)
    for p in invoice.get("procedures", []):
        if p.get("name", "").lower() == name.lower():
            p["discount"] = round(p.get("discount", 0.0) + p["tariff"] * (percent / 100.0), 2)
            _recompute_totals(invoice)
            return f"Applied discount of {percent}% to '{name}'."
    return f"Not found: {name}"
# ---------------------------------------------------------------------

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

# ---------- Helpers for saving approved claims ----------
def _claims_dir() -> Path:
    d = Path("data/claims")
    d.mkdir(parents=True, exist_ok=True)
    return d

def _canonicalize_invoice(inv: Dict[str, Any]) -> Dict[str, Any]:
    """Return the invoice exactly in the required JSON structure,
    coercing billed to int when possible (else 2-decimal float)."""
    out: Dict[str, Any] = {
        "patient name": inv.get("patient name", ""),
        "patient SSN": inv.get("patient SSN", ""),
        "hospital name": inv.get("hospital name", ""),
        "date of service": inv.get("date of service", ""),
        "diagnose": inv.get("diagnose", ""),
        "procedures": [],
    }
    for p in inv.get("procedures", []):
        billed = float(p.get("billed", 0))
        billed = int(billed) if float(billed).is_integer() else round(billed, 2)
        out["procedures"].append({"name": p.get("name", ""), "billed": billed})
    return out

def _save_claim(final_json: Dict[str, Any]) -> str:
    ssn = str(final_json.get("patient SSN") or final_json.get("patientSSN") or "").strip() or "unknown"
    dos = str(final_json.get("date of service") or final_json.get("dateOfService") or "").replace("-", "") or "nodate"
    fname = f"{dos}_{ssn}_{uuid4().hex[:8]}.json"
    path = _claims_dir() / fname
    path.write_text(json.dumps(final_json, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
    
def generate_claim_title(inv: Dict[str, Any]) -> str:
    procedures = inv.get("procedures", [])
    main_proc = procedures[0]["name"] if procedures and isinstance(procedures[0], dict) else ""
    
    # Scurtează procedura la primele 2 cuvinte (ex: "ER visit high complexity" -> "ER visit")
    short_proc = " ".join(main_proc.split()[:2]) if main_proc else "Procedure"

    # Extrage doar numele de familie
    name = (inv.get("patient name")
            or inv.get("full name")
            or inv.get("patient SSN")
            or "Patient")
    last_name = str(name).strip().split()[-1]

    return f"{short_proc} – {last_name}"

# --------------------------------------------------------

def _to_insurance_claim(inv: Dict[str, Any]) -> Dict[str, Any]:
    """Map internal invoice to the insurance agent's expected JSON fields."""
    canon = _canonicalize_invoice(inv)
    return {
        "fullName": canon.get("patient name", ""),
        "patientSSN": canon.get("patient SSN", ""),
        "hospitalName": canon.get("hospital name", ""),
        "dateOfService": canon.get("date of service", ""),
        "diagnose": canon.get("diagnose", ""),
        "procedures": canon.get("procedures", []),
    }

def _send_claim_to_insurance(inv: Dict[str, Any], conversation_id: Optional[str] = None) -> Dict[str, Any]:
    payload = {
        "conversation_id": conversation_id,
        "message": _to_insurance_claim(inv),
    }
    url = INSURANCE_AGENT_URL
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()  # lăsăm UI-ul să decidă ce folosește
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed contacting Insurance Agent: {e}")

@app.on_event("startup")
def _startup():
    init_env()
    global TARIFF
    TARIFF = load_tariff()

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
    global TARIFF
    if not TARIFF:
        try:
            TARIFF = load_tariff()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    sid = store.ensure(req.session_id)
    session = store.get(sid)

    # ---- Early smalltalk catch (even on very first message) ----
    try:
        probe = interpret_doctor_message(req.message, [])
        if probe.get("type") == "smalltalk":
            reply = (probe.get("params") or {}).get("reply") or "Hello! How can I help with the invoice?"
            return PendingResponse(
                session_id=sid,
                agent_reply=reply,
                invoice=session.get("invoice") or {}
            ).model_dump()
    except Exception:
        pass
    # ------------------------------------------------------------

    # ---- Early out-of-scope guard BEFORE building a draft invoice ----
    try:
        probe2 = interpret_doctor_message(req.message, [])
        if probe2.get("type") == "unknown" and (probe2.get("params") or {}).get("reason") == "out_of_scope":
            polite = (
                "I’m a hospital **billing** assistant, so I can’t help with that topic. "
                "I can create or adjust invoices (patient name/SSN/diagnosis), add or remove procedures, "
                "apply discounts, set prices, and finalize approval. "
                "What would you like to do with the current invoice?"
            )
            return PendingResponse(session_id=sid, agent_reply=polite, invoice=session.get("invoice") or {}).model_dump()
    except Exception:
        pass
    # ------------------------------------------------------------------

    # First turn (or after approval/cleared session)
    if session["status"] in ("empty") or not session.get("invoice"):
        extracted = extract_fields(req.message)
        invoice = build_initial_invoice(extracted, TARIFF)

        # normalize and compute totals (includes tariff, discount, tax)
        _ensure_proc_fields(invoice)
        _recompute_totals(invoice)

        session.update({"status": "pending", "invoice": invoice})
        store.upsert(sid, session)

        # If the doctor tried "send to insurance" on first turn, gate behind approval
        try:
            intent = interpret_doctor_message(req.message, [p.get("name", "") for p in invoice.get("procedures", [])])
        except Exception:
            intent = {"type": "unknown"}

        miss = missing_required(invoice)
        if intent.get("type") == "send_to_insurance":
            reply = (
                (generate_missing_prompt(invoice, miss) + "\n") if miss else ""
            ) + "Please approve the invoice first (say 'approve'). After approval, say 'send to insurance'."
            return PendingResponse(session_id=sid, agent_reply=reply, invoice=invoice).model_dump()

        # Otherwise proceed as usual: either ask for missing fields or present draft
        if miss:
            reply = generate_missing_prompt(invoice, miss)
        else:
            reply = (
                "Here is the proposed invoice based on your notes.\n\n"
                + pretty_invoice(invoice)
                + "\n\nYou can reply in natural language, e.g.: "
                  "'apply 10% discount', 'apply 10% discount to the second procedure', "
                  "'add specialist consult', 'set ER visit high complexity to 1150', "
                  "'change the invoice date to 2025-10-01', or 'approve'."
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
            reply = generate_missing_prompt(invoice, miss)
            session.update({"status": "pending", "invoice": invoice})
            store.upsert(sid, session)
            return PendingResponse(session_id=sid, agent_reply=reply, invoice=invoice).model_dump()

        # 1) Canonicalize
        final_json = _canonicalize_invoice(invoice)

        # ✅ 2) Adaugă titlul uman
        final_json["title"] = generate_claim_title(final_json)
            # 3) Salvează final_json complet (cu title)            
        file_path = _save_claim(final_json)

            # 4) Update sesiune
        session.update({"status": "approved", "invoice": final_json})
        store.upsert(sid, session)

          # 5) Răspuns final care conține title
        return ApprovedResponse(
            session_id=sid,   
            final_json=final_json,
            file_path=file_path
        ).model_dump()


    elif atype == "send_to_insurance":
        # Gate: must be approved first; also surface missing requirements if any
        miss = missing_required(invoice)
        if miss or session.get("status") != "approved":
            pre = (generate_missing_prompt(invoice, miss) + "\n") if miss else ""
            reply = pre + "Please approve the invoice first (say 'approve'). After approval, say 'send to insurance'."
            session.update({"status": "pending", "invoice": invoice})
            store.upsert(sid, session)
            return PendingResponse(session_id=sid, agent_reply=reply, invoice=invoice).model_dump()

        # Already approved -> send to insurance
        ins = _send_claim_to_insurance(invoice, conversation_id=session.get("insurance_conversation_id"))
        session["insurance_conversation_id"] = ins.get("conversation_id") or session.get("insurance_conversation_id")
        tool = ins.get("tool_result") or {}
        result_json = (tool or {}).get("result_json") or {}
        policy_valid = bool(result_json.get("eligible") and result_json.get("policy_id"))
        session["insurance_reply"] = {"text": ins.get("reply", ""), "tool_result": tool, "policy_valid": policy_valid}
        session["insurance_status"] = "received"  # awaiting human approval
        store.upsert(sid, session)

        out = PendingResponse(
            session_id=sid,
            agent_reply=("Sent the claim to the insurance agent and is awaiting for approval."),
            invoice=invoice,
        ).model_dump()
        enriched = dict(session["insurance_reply"] or {})
        enriched["session_id"] = sid
        out["insurance_pending"] = enriched
        return out

    elif atype == "discount_percent":
        pct = float(params.get("percent", 0))
        if "index" in params:
            status_note = _apply_discount_index(invoice, pct, int(params["index"]))
        elif "name" in params:
            status_note = _apply_discount_name(invoice, pct, str(params["name"]))
        else:
            status_note = _apply_discount_all(invoice, pct)

    elif atype == "add_procedure":
        wanted = (params.get("procedure_free_text") or "").strip()
        llm_choice = resolve_procedure_name(wanted, list(TARIFF.keys()))
        if llm_choice:
            status_note = add_procedure_exact(invoice, TARIFF, llm_choice) + " (via AI match)"
        else:
            status_note = add_procedure_free_text(invoice, TARIFF, wanted)
        _ensure_proc_fields(invoice)
        _recompute_totals(invoice)

    elif atype == "remove_procedure_by_index":
        idx = int(params.get("index", 0))
        status_note = remove_procedure_by_index(invoice, idx)
        _recompute_totals(invoice)

    elif atype == "remove_procedure_by_name":
        status_note = remove_procedure_by_name(invoice, params.get("name", ""))
        _recompute_totals(invoice)

    elif atype == "set_price":
        name = params.get("name", "")
        amount = float(params.get("amount", 0))
        # Use helper to find line and keep response semantics,
        # then overwrite our normalized fields to keep Tariff/Discount/Billed coherent.
        _ = set_price(invoice, name, amount)
        for p in invoice.get("procedures", []):
            if p.get("name") == name:
                p["tariff"] = round(float(amount), 2)
                # keep any prior discount amount unless you prefer to reset:
                p["discount"] = round(float(p.get("discount", 0.0) or 0.0), 2)
                p["billed"] = round(p["tariff"] - p["discount"], 2)
        _recompute_totals(invoice)

    elif atype == "provide_fields":
        extracted = extract_fields(req.message)
        for k in ["patient name", "patient SSN", "diagnose", "date of service"]:
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
        _ensure_proc_fields(invoice)
        _recompute_totals(invoice)

    else:
        # Strict guardrail: keep conversation on billing topic only
        reason = (action.get("params") or {}).get("reason", "")
        if reason == "out_of_scope":
            reply = (
                "I’m a hospital **billing** assistant, so I can’t help with that topic. "
                "I can create or adjust invoices (patient name/SSN/diagnosis), add or remove procedures, "
                "apply discounts, set prices, and finalize approval. "
                "What would you like to do with the current invoice?"
            )
            return PendingResponse(session_id=sid, agent_reply=reply, invoice=invoice).model_dump()
        # In-scope but unrecognized → give concrete billing examples
        status_note = (
            "I didn’t catch a billing action. You can say: 'apply 10% discount', "
            "'apply 10% discount to the second procedure', 'add specialist consult', "
            "'set ER visit high complexity to 1150', 'change the invoice date to 2025-10-01', or 'approve'."
        )

    # Friendly wrapper for status messages
    if status_note:
        status_note = f"✅ Got it — {status_note}"

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

@app.post("/approve_insurance")
def approve_insurance(payload: Dict[str, Any]):
    sid = (payload or {}).get("session_id")
    decision = (payload or {}).get("decision")  # 'approve' | 'deny'
    if decision not in ("approve", "deny"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'deny'")

    session = store.get(sid) if sid else None
    if not session:
        # Fallback: if exactly one pending exists, use it.
        snap = store.snapshot()
        received = [k for k, v in snap.items() if v.get("insurance_status") == "received" and v.get("insurance_reply")]
        if len(received) == 1:
            sid = received[0]
            session = snap[sid]
        else:
            raise HTTPException(status_code=404, detail="Invalid session_id")
    if not session.get("insurance_reply"):
        raise HTTPException(status_code=409, detail="No insurance reply to approve/deny")

    if decision == "deny":
        session["insurance_status"] = "denied"
        store.upsert(sid, session)
        return {"session_id": sid, "status": "denied"}

    # Approve path: surface the insurance reply to the chat
    session["insurance_status"] = "approved"
    reply = session["insurance_reply"].get("text", "")
    tool = session["insurance_reply"].get("tool_result")
    store.upsert(sid, session)
    return {"session_id": sid, "status": "approved", "insurance_reply": reply, "insurance_tool_result": tool}

@app.get("/insurance/pending")
def list_pending_insurance():
    all_sessions = store.snapshot()
    pending = []
    for sid, sess in all_sessions.items():
        if sess.get("insurance_status") == "received" and sess.get("insurance_reply"):
            pending.append({
                "session_id": sid,
                "invoice": sess.get("invoice"),
                "insurance_reply": sess.get("insurance_reply"),
            })
    return {"items": pending}

@app.get("/insurance/requests")
def list_insurance_requests(status: str = Query("pending", pattern="^(pending|approved|denied|all)$")):
    all_sessions = store.snapshot()
    items = []
    for sid, sess in all_sessions.items():
        st = sess.get("insurance_status")
        if status == "all" or (
            (status == "pending" and st == "received") or
            (status == "approved" and st == "approved") or
            (status == "denied" and st == "denied")
        ):
            entry = {
                "session_id": sid,
                "status": st or "",
                "invoice": sess.get("invoice"),
                "insurance_reply": sess.get("insurance_reply"),
            }
            items.append(entry)
    # For consistency, map "received" to "pending" in API response
    for it in items:
        if it.get("status") == "received":
            it["status"] = "pending"
    return {"items": items}

    