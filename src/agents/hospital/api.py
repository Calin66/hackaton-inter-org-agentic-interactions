from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List
from pathlib import Path
from uuid import uuid4
import json
import os
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
    apply_discount, add_procedure_free_text, add_procedure_exact,
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
        billed = int(billed) if billed.is_integer() else round(billed, 2)
        out["procedures"].append({"name": p.get("name", ""), "billed": billed})
    return out

def _save_claim(inv: Dict[str, Any]) -> str:
    clean = _canonicalize_invoice(inv)
    ssn = str(clean.get("patient SSN", "")).strip() or "unknown"
    dos = str(clean.get("date of service", "")).replace("-", "") or "nodate"
    fname = f"{dos}_{ssn}_{uuid4().hex[:8]}.json"
    path = _claims_dir() / fname
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
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

def _send_claim_to_insurance(inv: Dict[str, Any], conversation_id: str | None = None) -> Dict[str, Any]:
    payload = {
        "conversation_id": conversation_id,
        "message": _to_insurance_claim(inv),
    }
    url = INSURANCE_AGENT_URL
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # Expect schema of ChatResponse: { conversation_id, reply, tool_result }
        return {
            "conversation_id": data.get("conversation_id") or conversation_id or "",
            "reply": data.get("reply", ""),
            "tool_result": data.get("tool_result"),
        }
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
        # If intent parsing fails for any reason, fall through to normal flow.
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
    if session["status"] in ("empty", "approved") or not session.get("invoice"):
        extracted = extract_fields(req.message)
        invoice = build_initial_invoice(extracted, TARIFF)
        session.update({"status": "pending", "invoice": invoice})
        store.upsert(sid, session)

        # If the doctor intended to send to insurance immediately and we have required fields, do it now
        try:
            intent = interpret_doctor_message(req.message, [p.get("name", "") for p in invoice.get("procedures", [])])
        except Exception:
            intent = {"type": "unknown"}

        miss = missing_required(invoice)
        if intent.get("type") == "send_to_insurance" and not miss:
            ins = _send_claim_to_insurance(invoice, conversation_id=session.get("insurance_conversation_id"))
            session["insurance_conversation_id"] = ins.get("conversation_id") or session.get("insurance_conversation_id")
            tool = ins.get("tool_result") or {}
            result_json = (tool or {}).get("result_json") or {}
            policy_valid = bool(result_json.get("eligible") and result_json.get("policy_id"))
            session["insurance_reply"] = {"text": ins.get("reply", ""), "tool_result": tool, "policy_valid": policy_valid}
            session["insurance_status"] = "received"
            store.upsert(sid, session)
            out = PendingResponse(
                session_id=sid,
                agent_reply=(
                    "Sent the claim to the insurance agent and is awaiting for approval"
                ),
                invoice=invoice,
            ).model_dump()
            enriched = dict(session["insurance_reply"] or {})
            enriched["session_id"] = sid
            out["insurance_pending"] = enriched
            return out

        # Otherwise proceed as usual: either ask for missing fields or present draft
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

    # Follow-up turns (NLU)
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

        # SAVE the approved claim to data/claims as JSON in the requested structure
        file_path = _save_claim(invoice)

        session.update({"status": "approved", "invoice": invoice})
        store.upsert(sid, session)
        return ApprovedResponse(session_id=sid, final_json=_canonicalize_invoice(invoice), file_path=file_path).model_dump()

    elif atype == "send_to_insurance":
        # Ensure minimal required fields are there before sending
        miss = missing_required(invoice)
        if miss:
            reply = generate_missing_prompt(invoice, miss)
            session.update({"status": "pending", "invoice": invoice})
            store.upsert(sid, session)
            return PendingResponse(session_id=sid, agent_reply=reply, invoice=invoice).model_dump()

        # Send to insurance agent and store pending insurance reply (requires human approval)
        ins = _send_claim_to_insurance(invoice, conversation_id=session.get("insurance_conversation_id"))
        # Persist insurance conversation id/thread so subsequent messages thread correctly
        session["insurance_conversation_id"] = ins.get("conversation_id") or session.get("insurance_conversation_id")
        tool = ins.get("tool_result") or {}
        result_json = (tool or {}).get("result_json") or {}
        policy_valid = bool(result_json.get("eligible") and result_json.get("policy_id"))
        session["insurance_reply"] = {"text": ins.get("reply", ""), "tool_result": tool, "policy_valid": policy_valid}
        session["insurance_status"] = "received"  # awaiting human approval
        store.upsert(sid, session)

        # Tell UI there is an insurance answer waiting for approval
        out = PendingResponse(
            session_id=sid,
            agent_reply=(
                "Sent the claim to the insurance agent and is awaiting for approval."
            ),
            invoice=invoice,
        ).model_dump()
        # Enrich response with meta the UI can use for approval card
        enriched = dict(session["insurance_reply"] or {})
        enriched["session_id"] = sid
        out["insurance_pending"] = enriched
        return out

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
            "'remove the second procedure', 'add specialist consult', "
            "'set ER visit high complexity to 1150', or 'approve'."
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
