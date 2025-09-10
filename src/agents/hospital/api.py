from fastapi import FastAPI, HTTPException, Query, Body
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
    load_tariff,
    build_initial_invoice,
    pretty_invoice,
    apply_discount,
    add_procedure_free_text,
    add_procedure_exact,
    remove_procedure_by_index,
    remove_procedure_by_name,
    set_price,
)
from .state import store
from .config import init_env, INSURANCE_AGENT_URL
from .chat_db import (
    init_db as init_chat_db,
    create_chat,
    list_chats,
    get_chat,
    update_chat,
    delete_chat,
    add_message,
    list_messages,
)

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
    subtotal_tariff = round(
        sum(p.get("tariff", 0.0) for p in invoice.get("procedures", [])), 2
    )
    discounts_total = round(
        sum(p.get("discount", 0.0) for p in invoice.get("procedures", [])), 2
    )
    subtotal_after_discount = round(
        sum(p.get("billed", 0.0) for p in invoice.get("procedures", [])), 2
    )
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
        p["discount"] = round(
            p.get("discount", 0.0) + p["tariff"] * (percent / 100.0), 2
        )
    _recompute_totals(invoice)
    return f"Applied discount of {percent}% to all procedures."


def _apply_discount_index(
    invoice: Dict[str, Any], percent: float, index_1based: int
) -> str:
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
            p["discount"] = round(
                p.get("discount", 0.0) + p["tariff"] * (percent / 100.0), 2
            )
            _recompute_totals(invoice)
            return f"Applied discount of {percent}% to '{name}'."
    return f"Not found: {name}"


# ---------------------------------------------------------------------

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
    subtotal_tariff = round(
        sum(p.get("tariff", 0.0) for p in invoice.get("procedures", [])), 2
    )
    discounts_total = round(
        sum(p.get("discount", 0.0) for p in invoice.get("procedures", [])), 2
    )
    subtotal_after_discount = round(
        sum(p.get("billed", 0.0) for p in invoice.get("procedures", [])), 2
    )
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
        p["discount"] = round(
            p.get("discount", 0.0) + p["tariff"] * (percent / 100.0), 2
        )
    _recompute_totals(invoice)
    return f"Applied discount of {percent}% to all procedures."


def _apply_discount_index(
    invoice: Dict[str, Any], percent: float, index_1based: int
) -> str:
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
            p["discount"] = round(
                p.get("discount", 0.0) + p["tariff"] * (percent / 100.0), 2
            )
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
    """Return the invoice in the required JSON structure for persistence/insurance,
    preserving tariff/discount/totals when available. Coerce currency fields to
    int when whole, else 2-decimal float.

    This keeps the frontend able to display detailed rows after approval while
    remaining backward-compatible with the insurance payload (which only uses
    name + billed).
    """
    # Ensure numbers are consistent before snapshotting
    try:
        _recompute_totals(inv)
    except Exception:
        pass

    out: Dict[str, Any] = {
        "patient name": inv.get("patient name", ""),
        "patient SSN": inv.get("patient SSN", ""),
        "hospital name": inv.get("hospital name", ""),
        "date of service": inv.get("date of service", ""),
        "diagnose": inv.get("diagnose", ""),
        "procedures": [],
        "work_accident": inv.get("work_accident") or None,  # <-- NEW
    }

    # Carry totals if present
    for k in ("subtotal", "discounts_total", "tax_rate", "tax", "total"):
        if k in inv:
            v = float(inv.get(k, 0))
            # Keep tax_rate as-is (fraction), others as currency
            if k != "tax_rate":
                v = int(v) if float(v).is_integer() else round(v, 2)
            out[k] = v

    def _money(x: Any) -> Any:
        try:
            xf = float(x)
            return int(xf) if float(xf).is_integer() else round(xf, 2)
        except Exception:
            return 0

    for p in inv.get("procedures", []):
        tariff = _money(p.get("tariff", 0))
        discount = _money(p.get("discount", 0))
        billed = _money(p.get("billed", 0))
        out["procedures"].append(
            {
                "name": p.get("name", ""),
                # Preserve full details to keep UI consistent post-approval
                "tariff": tariff,
                "discount": discount,
                "billed": billed,
            }
        )
    return out


def _save_claim(final_json: Dict[str, Any]) -> str:
    ssn = (
        str(final_json.get("patient SSN") or final_json.get("patientSSN") or "").strip()
        or "unknown"
    )
    dos = (
        str(
            final_json.get("date of service") or final_json.get("dateOfService") or ""
        ).replace("-", "")
        or "nodate"
    )
    fname = f"{dos}_{ssn}_{uuid4().hex[:8]}.json"
    path = _claims_dir() / fname
    path.write_text(
        json.dumps(final_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(path)


def _missing_work_acc(inv: Dict[str, Any]) -> List[str]:
    w = (inv or {}).get("work_accident") or {}
    needed: List[str] = []
    if not w.get("narrative"):
        needed.append("cum s-a întâmplat accidentul")
    if not w.get("location"):
        needed.append("unde s-a întâmplat accidentul")
    if w.get("during_work_hours") is None:
        needed.append("era în timpul orelor de lucru (da/nu)")
    if not w.get("sick_leave_days"):
        needed.append("zile de concediu medical")
    return needed


def compute_claim_title(inv: Dict[str, Any]) -> str:
    procedures = inv.get("procedures", [])
    main_proc = ""
    try:
        if procedures and isinstance(procedures[0], dict):
            main_proc = str(procedures[0].get("name") or "")
    except Exception:
        main_proc = ""

    short_proc = (
        " ".join(main_proc.split()[:2]) if (main_proc or "").strip() else "Claim"
    )
    name = (
        inv.get("patient name")
        or inv.get("full name")
        or inv.get("patient SSN")
        or "Patient"
    )
    name_s = str(name).strip()
    last_name = name_s.split()[-1] if name_s else "Patient"
    return f"{short_proc} - {last_name}"


def _to_insurance_claim(inv: Dict[str, Any]) -> Dict[str, Any]:
    """Map internal invoice to the insurance agent's expected JSON fields."""
    canon = _canonicalize_invoice(inv)
    # Ensure only the expected keys are passed for procedures
    procs = []
    for p in canon.get("procedures", []):
        try:
            billed = float(p.get("billed", 0))
        except Exception:
            billed = 0.0
        procs.append({"name": p.get("name", ""), "billed": billed})
    return {
        "fullName": canon.get("patient name", ""),
        "patientSSN": canon.get("patient SSN", ""),
        "hospitalName": canon.get("hospital name", ""),
        "dateOfService": canon.get("date of service", ""),
        "diagnose": canon.get("diagnose", ""),
        "procedures": procs,
        "work_accident": canon.get("work_accident") or None,  # <-- NEW
    }


def _send_claim_to_insurance(
    inv: Dict[str, Any], conversation_id: Optional[str] = None
) -> Dict[str, Any]:
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
        raise HTTPException(
            status_code=502, detail=f"Failed contacting Insurance Agent: {e}"
        )


@app.on_event("startup")
def _startup():
    init_env()
    global TARIFF
    TARIFF = load_tariff()
    # Initialize local chat DB (SQLite)
    try:
        init_chat_db()
    except Exception as e:
        # Do not crash server on DB init errors
        print(f"[chat_db] init failed: {e}")


@app.get("/hello")
def hello():
    return {
        "message": (
            "Hello! I’m your hospital billing assistant. "
            "How can I help today—create a new invoice, add or remove procedures, "
            "apply a discount, or finalize and approve one?"
        )
    }


# ------------------------- Chat storage endpoints -------------------------


@app.get("/chats")
def http_list_chats():
    try:
        return {"items": list_chats()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chats")
def http_create_chat(payload: Dict[str, Any] = Body(default={})):  # { id?, title? }
    try:
        cid = (payload or {}).get("id") or str(uuid4())[:8]
        title = (payload or {}).get("title") or "Claim"
        st = (payload or {}).get("insuranceStatus") or (payload or {}).get(
            "insurance_status"
        )
        row = create_chat(cid, title, st)
        return row
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/chats/{chat_id}")
def http_update_chat(
    chat_id: str, payload: Dict[str, Any] = Body(default={})
):  # { title?, insuranceStatus? }
    try:
        title = (payload or {}).get("title")
        st = (payload or {}).get("insuranceStatus") or (payload or {}).get(
            "insurance_status"
        )
        row = update_chat(chat_id, title=title, insurance_status=st)
        if not row:
            raise HTTPException(status_code=404, detail="chat not found")
        return row
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/chats/{chat_id}")
def http_delete_chat(chat_id: str):
    try:
        if not get_chat(chat_id):
            raise HTTPException(status_code=404, detail="chat not found")
        delete_chat(chat_id)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chats/{chat_id}/messages")
def http_list_messages(chat_id: str):
    try:
        if not get_chat(chat_id):
            raise HTTPException(status_code=404, detail="chat not found")
        items = list_messages(chat_id)
        # Normalize keys for frontend expectations
        for it in items:
            # pass-through
            pass
        return {"items": items}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chats/{chat_id}/messages")
def http_add_message(
    chat_id: str, payload: Dict[str, Any] = Body(default={})
):  # { id, role, content, tool_result?, status? }
    try:
        if not get_chat(chat_id):
            # auto-create chat with fallback title
            create_chat(chat_id, (payload or {}).get("title") or "Claim")
        mid = (payload or {}).get("id") or uuid4().hex[:10]
        role = (payload or {}).get("role")
        content = (payload or {}).get("content") or ""
        tool_result = (payload or {}).get("tool_result")
        status = (payload or {}).get("status")
        if role not in ("user", "assistant"):
            raise HTTPException(
                status_code=400, detail="role must be 'user' or 'assistant'"
            )
        row = add_message(
            id=mid,
            chat_id=chat_id,
            role=role,
            content=content,
            tool_result=tool_result,
            status=status,
        )
        return row
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

    # ensure defined early (used in multiple branches)
    status_note = None

    # ---- Early smalltalk catch (even on very first message) ----
    try:
        probe = interpret_doctor_message(req.message, [])
        if probe.get("type") == "smalltalk":
            reply = (probe.get("params") or {}).get(
                "reply"
            ) or "Hello! How can I help with the invoice?"
            return PendingResponse(
                session_id=sid, agent_reply=reply, invoice=session.get("invoice") or {}
            ).model_dump()
    except Exception:
        pass
    # ------------------------------------------------------------

    # ---- Early out-of-scope guard BEFORE building a draft invoice ----
    try:
        probe2 = interpret_doctor_message(req.message, [])
        if (
            probe2.get("type") == "unknown"
            and (probe2.get("params") or {}).get("reason") == "out_of_scope"
        ):
            polite = (
                "I’m a hospital **billing** assistant, so I can’t help with that topic. "
                "I can create or adjust invoices (patient name/SSN/diagnosis), add or remove procedures, "
                "apply discounts, set prices, and finalize approval. "
                "What would you like to do with the current invoice?"
            )
            return PendingResponse(
                session_id=sid, agent_reply=polite, invoice=session.get("invoice") or {}
            ).model_dump()
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
        # Suggest a title immediately for the UI
        try:
            invoice["title"] = compute_claim_title(invoice)
        except Exception:
            pass

        session.update({"status": "pending", "invoice": invoice})
        store.upsert(sid, session)

        # If the doctor tried "send to insurance" on first turn, gate behind approval
        try:
            intent = interpret_doctor_message(
                req.message, [p.get("name", "") for p in invoice.get("procedures", [])]
            )
        except Exception:
            intent = {"type": "unknown"}

        miss = missing_required(invoice)

        # If a work accident was already inferred at extraction time, collect any missing WA details first
        if invoice.get("work_accident", {}).get("suspected"):
            missW = _missing_work_acc(invoice)
            if missW:
                reply = (
                    ((status_note + "\n\n") if status_note else "")
                    + "Accident de muncă bănuit — am nevoie de: "
                    + ", ".join(missW)
                    + ". Exemplu: «accident pe bicicletă, la Moara de Foc, DA, 10 zile»"
                )
                return PendingResponse(
                    session_id=sid, agent_reply=reply, invoice=invoice
                ).model_dump()

        if intent.get("type") == "send_to_insurance" and not miss:
            ins = _send_claim_to_insurance(
                invoice, conversation_id=session.get("insurance_conversation_id")
            )
            tool = ins.get("tool_result") or {}
            result_json = (tool or {}).get("result_json") or {}
            payer = result_json.get("payer", "patient")
            session["who_pays_rest"] = payer  # for UI

            session["insurance_conversation_id"] = ins.get(
                "conversation_id"
            ) or session.get("insurance_conversation_id")
            policy_valid = bool(
                result_json.get("eligible") and result_json.get("policy_id")
            )
            session["insurance_reply"] = {
                "text": ins.get("reply", ""),
                "tool_result": tool,
                "policy_valid": policy_valid,
            }
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
        if intent.get("type") == "send_to_insurance":
            reply = (
                ((generate_missing_prompt(invoice, miss) + "\n") if miss else "")
                + "Please approve the invoice first (say 'approve'). After approval, say 'send to insurance'."
            )
            return PendingResponse(
                session_id=sid, agent_reply=reply, invoice=invoice
            ).model_dump()

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
        return PendingResponse(
            session_id=sid, agent_reply=reply, invoice=invoice
        ).model_dump()

    # ---------------- Follow-up turns (NLU) ----------------
    invoice = session["invoice"]
    current_lines = [p["name"] for p in invoice.get("procedures", [])]

    action = interpret_doctor_message(req.message, current_lines)
    atype = action.get("type")
    params = action.get("params", {}) or {}

    if atype == "approve":
        miss = missing_required(invoice)
        if invoice.get("work_accident", {}).get("suspected"):
            missW = _missing_work_acc(invoice)
            if missW:
                reply = (
                    ((status_note + "\n\n") if status_note else "")
                    + "Accident de muncă bănuit — am nevoie de: "
                    + ", ".join(missW)
                    + ". Exemplu: «accident pe bicicletă, la Moara de Foc, DA, 10 zile»"
                )
                return PendingResponse(
                    session_id=sid, agent_reply=reply, invoice=invoice
                ).model_dump()

        if miss:
            reply = generate_missing_prompt(invoice, miss)
            session.update({"status": "pending", "invoice": invoice})
            store.upsert(sid, session)
            return PendingResponse(
                session_id=sid, agent_reply=reply, invoice=invoice
            ).model_dump()

        # 1) Canonicalize
        final_json = _canonicalize_invoice(invoice)

        # ✅ 2) Adaugă titlul uman
        try:
            final_json["title"] = compute_claim_title(final_json)
        except Exception:
            pass
            # 3) Salvează final_json complet (cu title)
        file_path = _save_claim(final_json)

        # 4) Update sesiune
        session.update({"status": "approved", "invoice": final_json})
        store.upsert(sid, session)
        return ApprovedResponse(
            session_id=sid,
            final_json=_canonicalize_invoice(invoice),
            file_path=file_path,
        ).model_dump()

    elif atype == "set_work_accident":
        # merge + normalize work accident details
        invoice.setdefault("work_accident", {})
        for k in [
            "suspected",
            "narrative",
            "location",
            "during_work_hours",
            "sick_leave_days",
            "happened_at",
        ]:
            if k in params and params[k] not in (None, ""):
                invoice["work_accident"][k] = params[k]

        # normalize booleans and integers
        w = invoice["work_accident"]

        def _to_bool(v):
            if isinstance(v, bool):
                return v
            s = str(v).strip().lower()
            if s in ("da", "true", "1", "yes", "y"):
                return True
            if s in ("nu", "false", "0", "no", "n"):
                return False
            return None

        if "during_work_hours" in w:
            b = _to_bool(w["during_work_hours"])
            if b is not None:
                w["during_work_hours"] = b

        if "sick_leave_days" in w:
            try:
                w["sick_leave_days"] = int(w["sick_leave_days"])
            except Exception:
                pass

        if w.get("suspected") is not True:
            w["suspected"] = True

        status_note = "am setat flag-ul de accident de muncă și detaliile"

    elif atype == "send_to_insurance":
        # Gate: must be approved first; also surface missing requirements if any
        miss = missing_required(invoice)

        if invoice.get("work_accident", {}).get("suspected"):
            missW = _missing_work_acc(invoice)
            if missW:
                reply = (
                    ((status_note + "\n\n") if status_note else "")
                    + "Accident de muncă bănuit — am nevoie de: "
                    + ", ".join(missW)
                    + ". Exemplu: «accident pe bicicletă, la Moara de Foc, DA, 10 zile»"
                )
                return PendingResponse(
                    session_id=sid, agent_reply=reply, invoice=invoice
                ).model_dump()

        if miss or session.get("status") != "approved":
            pre = (generate_missing_prompt(invoice, miss) + "\n") if miss else ""
            reply = (
                pre
                + "Please approve the invoice first (say 'approve'). After approval, say 'send to insurance'."
            )
            session.update({"status": "pending", "invoice": invoice})
            store.upsert(sid, session)
            return PendingResponse(
                session_id=sid, agent_reply=reply, invoice=invoice
            ).model_dump()

        # Already approved -> send to insurance
        ins = _send_claim_to_insurance(
            invoice, conversation_id=session.get("insurance_conversation_id")
        )
        session["insurance_conversation_id"] = ins.get(
            "conversation_id"
        ) or session.get("insurance_conversation_id")
        tool = ins.get("tool_result") or {}
        result_json = (tool or {}).get("result_json") or {}
        payer = result_json.get("payer", "patient")
        session["who_pays_rest"] = payer  # for UI

        # Persist insurance conversation id/thread so subsequent messages thread correctly
        session["insurance_conversation_id"] = ins.get(
            "conversation_id"
        ) or session.get("insurance_conversation_id")
        policy_valid = bool(
            result_json.get("eligible") and result_json.get("policy_id")
        )
        session["insurance_reply"] = {
            "text": ins.get("reply", ""),
            "tool_result": tool,
            "policy_valid": policy_valid,
        }
        session["insurance_status"] = "received"  # awaiting human approval
        store.upsert(sid, session)

        out = PendingResponse(
            session_id=sid,
            agent_reply=(
                "Sent the claim to the insurance agent and is awaiting for approval."
            ),
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
            status_note = (
                add_procedure_exact(invoice, TARIFF, llm_choice) + " (via AI match)"
            )
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
            return PendingResponse(
                session_id=sid, agent_reply=reply, invoice=invoice
            ).model_dump()
        # In-scope but unrecognized → give concrete billing examples
        status_note = (
            "I didn’t catch a billing action. You can say: 'apply 10% discount', "
            "'apply 10% discount to the second procedure', 'add specialist consult', "
            "'set ER visit high complexity to 1150', 'change the invoice date to 2025-10-01', or 'approve'."
        )

    # Friendly wrapper for status messages
    if status_note:
        status_note = f"✅ Got it — {status_note}"

    try:
        invoice["title"] = compute_claim_title(invoice)
    except Exception:
        pass
    miss = missing_required(invoice)

    # Gate missing work-accident details if flagged
    if invoice.get("work_accident", {}).get("suspected"):
        missW = _missing_work_acc(invoice)
        if missW:
            reply = (
                ((status_note + "\n\n") if status_note else "")
                + "Accident de muncă bănuit — am nevoie de: "
                + ", ".join(missW)
                + ". Exemplu: «accident pe bicicletă, la Moara de Foc, DA, 10 zile»"
            )
            return PendingResponse(
                session_id=sid, agent_reply=reply, invoice=invoice
            ).model_dump()

    if miss:
        pre = status_note + "\n" if status_note else ""
        reply = pre + generate_missing_prompt(invoice, miss)
    else:
        reply = (
            (status_note + "\n\n" if status_note else "")
            + pretty_invoice(invoice)
            + "\n\nReply in natural language or say 'approve' to finalize."
        )

    session.update({"status": "pending", "invoice": invoice})
    store.upsert(sid, session)
    return PendingResponse(
        session_id=sid, agent_reply=reply, invoice=invoice
    ).model_dump()


@app.post("/approve_insurance")
def approve_insurance(payload: Dict[str, Any]):
    sid = (payload or {}).get("session_id")
    decision = (payload or {}).get("decision")  # 'approve' | 'deny'
    if decision not in ("approve", "deny"):
        raise HTTPException(
            status_code=400, detail="decision must be 'approve' or 'deny'"
        )

    session = store.get(sid) if sid else None
    if not session:
        # Fallback: if exactly one pending exists, use it.
        snap = store.snapshot()
        received = [
            k
            for k, v in snap.items()
            if v.get("insurance_status") == "received" and v.get("insurance_reply")
        ]
        if len(received) == 1:
            sid = received[0]
            session = snap[sid]
        else:
            raise HTTPException(status_code=404, detail="Invalid session_id")
    if not session.get("insurance_reply"):
        raise HTTPException(
            status_code=409, detail="No insurance reply to approve/deny"
        )

    if decision == "deny":
        session["insurance_status"] = "denied"
        store.upsert(sid, session)
        return {"session_id": sid, "status": "denied"}

    # Approve path: surface the insurance reply to the chat
    session["insurance_status"] = "approved"
    reply = session["insurance_reply"].get("text", "")
    tool = session["insurance_reply"].get("tool_result")
    store.upsert(sid, session)
    return {
        "session_id": sid,
        "status": "approved",
        "insurance_reply": reply,
        "insurance_tool_result": tool,
    }


@app.get("/insurance/pending")
def list_pending_insurance():
    all_sessions = store.snapshot()
    pending = []
    for sid, sess in all_sessions.items():
        if sess.get("insurance_status") == "received" and sess.get("insurance_reply"):
            pending.append(
                {
                    "session_id": sid,
                    "invoice": sess.get("invoice"),
                    "insurance_reply": sess.get("insurance_reply"),
                }
            )
    return {"items": pending}


@app.get("/insurance/requests")
def list_insurance_requests(
    status: str = Query("pending", pattern="^(pending|approved|denied|all)$")
):
    all_sessions = store.snapshot()
    items = []
    for sid, sess in all_sessions.items():
        st = sess.get("insurance_status")
        if status == "all" or (
            (status == "pending" and st == "received")
            or (status == "approved" and st == "approved")
            or (status == "denied" and st == "denied")
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
