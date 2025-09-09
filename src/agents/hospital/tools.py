# src/agents/hospital/tools.py
from __future__ import annotations

import os
import re
import json
import datetime as dt
from difflib import get_close_matches
from typing import Any, Dict, List, Optional

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ValidationError

# Load environment variables early so OPENAI_API_KEY is available
from dotenv import load_dotenv
load_dotenv()

# LangChain / OpenAI
from langchain_openai import ChatOpenAI
from langchain.tools import StructuredTool

# Shared models (packaged inside hospital/)
from .models import Claim, ClaimIn  # type: ignore

# Local storage & tariff (packaged inside hospital/)
from .storage import save_claim  # type: ignore
from .tariff import SYNTHETIC_TARIFF  # type: ignore

# Local schemas used for tool IO / validation
from .models_local import InvoiceDraft, FreeText, REQUIRED_FIELDS


# -----------------------------
# Module-level draft cache
# -----------------------------
# We keep the latest working draft here so tools can operate across turns
# even when the LLM forgets to pass the draft explicitly.
_DRAFT: Dict[str, Any] = {}

def _set_draft(d: Dict[str, Any]) -> None:
    global _DRAFT
    _DRAFT = d

def _get_draft(fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return (fallback if fallback else _DRAFT) or {}


# -----------------------------
# General helpers
# -----------------------------

_TZ = dt.timezone(dt.timedelta(hours=3))  # Europe/Bucharest

def today_ro() -> str:
    return dt.datetime.now(tz=_TZ).date().isoformat()

def _require_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing")
    return key

def _with_warning(d: Dict[str, Any], key: str, msg: str) -> Dict[str, Any]:
    out = json.loads(InvoiceDraft.model_validate(_get_draft(d)).model_dump_json(by_alias=True, exclude_none=True))
    out.setdefault("_warnings", {})
    out["_warnings"][key] = msg
    _set_draft(out)
    return out


# -----------------------------
# Tool 1: extract from free text (structured)
# -----------------------------

def _extract_claim_from_text_fn(text: str) -> Dict[str, Any]:
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        temperature=0,
        api_key=_require_api_key(),
    )
    extractor = llm.with_structured_output(ClaimIn)
    prompt = (
        "Extract the medical claim fields from the text below. "
        "Only fill fields explicitly present; otherwise leave them empty or omit. "
        "NUMERIC billed must be a number.\n\n"
        f"TEXT:\n{text}"
    )
    parsed: ClaimIn = extractor.invoke(prompt)
    # Return with alias keys to match InvoiceDraft/Claim pretty keys
    return parsed.model_dump(by_alias=True, exclude_none=True)

extract_claim_from_text_tool = StructuredTool.from_function(
    func=_extract_claim_from_text_fn,
    name="extract_claim_from_text",
    description=(
        "Extract structured claim fields from natural language text. "
        "Use this when the doctor provides details in prose (no JSON). "
        "Returns ClaimIn fields: full name, patient SSN, hospital name, date of service (YYYY-MM-DD), "
        "diagnose, procedures[{name,billed}]."
    ),
    args_schema=FreeText,
    handle_tool_error=True,
)


# -----------------------------
# Tool 2: complete invoice from tariff + defaults
# -----------------------------

class CompleteArgs(BaseModel):
    # Default to empty dict to avoid crashes if the agent forgets to pass it
    draft: Dict[str, Any] = Field(
        default_factory=dict,
        description="Partial invoice JSON using pretty keys",
    )

def _complete_invoice_fn(draft: Dict[str, Any] | None = None) -> Dict[str, Any]:
    # Safeguard when invoked with no args at all (use cached draft)
    draft = _get_draft(draft)

    inv = InvoiceDraft.model_validate(draft)

    # Defaults
    if not inv.hospital_name:
        inv.hospital_name = draft.get("hospital name") or "City Hospital"
    if not inv.date_of_service:
        inv.date_of_service = today_ro()

    procs = inv.procedures or []
    completed: List[Dict[str, Any]] = []
    missing_names: List[str] = []

    for p in procs:
        name = p.get("name")
        if not name:
            continue
        billed = p.get("billed")
        if billed is None:
            if name in SYNTHETIC_TARIFF:
                billed = SYNTHETIC_TARIFF[name]
            else:
                # case-insensitive exact match fallback
                for tname in SYNTHETIC_TARIFF.keys():
                    if tname.lower() == name.lower():
                        name = tname
                        billed = SYNTHETIC_TARIFF[tname]
                        break
        if billed is None:
            missing_names.append(name)
        else:
            completed.append({"name": name, "billed": float(billed)})

    inv.procedures = completed

    out = json.loads(inv.model_dump_json(by_alias=True, exclude_none=True))
    out["_warnings"] = out.get("_warnings", {})

    missing_fields = [k for k in REQUIRED_FIELDS if k not in out or not out.get(k)]
    if missing_names:
        out["_warnings"]["unpriced_procedures"] = missing_names
    if missing_fields:
        out["_warnings"]["missing_fields"] = missing_fields

    _set_draft(out)
    return out

complete_invoice_tool = StructuredTool.from_function(
    func=_complete_invoice_fn,
    name="complete_invoice",
    description=(
        "Complete a partial invoice JSON by filling defaults and billed amounts from the tariff table. "
        "If any required fields are missing (full name, patient SSN, diagnose, procedures), include them in _warnings.missing_fields. "
        "Tariff lookups come from the local tariff.py."
    ),
    args_schema=CompleteArgs,
    handle_tool_error=True,
)


# -----------------------------
# Tool 2b: complete FROM TEXT (extract → complete)
# -----------------------------

class CompleteFromTextArgs(BaseModel):
    text: str

def _complete_from_text_fn(text: str) -> Dict[str, Any]:
    extracted = _extract_claim_from_text_fn(text)  # alias keys
    out = _complete_invoice_fn(extracted or {})    # safe even if extraction sparse
    _set_draft(out)
    return out

complete_from_text_tool = StructuredTool.from_function(
    func=_complete_from_text_fn,
    name="complete_from_text",
    description=(
        "For free-text doctor input, first extract fields then complete with tariff/date. "
        "Use this as the first step when the user provides prose, not JSON."
    ),
    args_schema=CompleteFromTextArgs,
    handle_tool_error=True,
)


# -----------------------------
# Tool 3: modification helpers
# -----------------------------

class ModifyArgs(BaseModel):
    # Default to empty dict; agent sometimes forgets to pass the current draft
    draft: Dict[str, Any] = Field(
        default_factory=dict,
        description="Current invoice draft to be modified",
    )
    action: str = Field(
        ...,
        description=(
            "One of: add_procedure, remove_procedure, discount_invoice, discount_procedure, "
            "update_patient, set_diagnosis, set_date"
        ),
    )
    payload: Dict[str, Any] = Field(default_factory=dict)

def _apply_modification_fn(
    draft: Dict[str, Any] | None = None,
    action: str = "",
    payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    # Safeguards for missing args + pull last known draft
    draft = _get_draft(draft)
    payload = payload or {}

    inv = InvoiceDraft.model_validate(draft)

    if action == "add_procedure":
        name = payload.get("name")
        billed = payload.get("billed")
        if not name:
            return _with_warning(draft, "missing_param", "add_procedure requires 'name'")

        # If billed isn't provided, try tariff lookup (case-insensitive)
        if billed is None:
            if name in SYNTHETIC_TARIFF:
                billed = SYNTHETIC_TARIFF[name]
            else:
                # case-insensitive exact match fallback (like complete_invoice)
                for tname in SYNTHETIC_TARIFF.keys():
                    if tname.lower() == name.lower():
                        name = tname
                        billed = SYNTHETIC_TARIFF[tname]
                        break

        if billed is None:
            return _with_warning(
                draft,
                "unknown_procedure",
                f"'{name}' not in tariff (case-insensitive); please provide billed"
            )

        inv.procedures = (inv.procedures or []) + [{"name": name, "billed": float(billed)}]

    elif action == "remove_procedure":
        target = (payload.get("name") or "").strip()
        if not target:
            return _with_warning(draft, "missing_param", "remove_procedure requires 'name'")

        def norm(s: str) -> str:
            # normalize: lowercase, strip non-alnum
            return re.sub(r"\W+", "", (s or "").lower())

        target_n = norm(target)
        procs = inv.procedures or []

        # 1) exact normalized match
        exact_map = {norm(p.get("name", "")): p.get("name", "") for p in procs}
        chosen = exact_map.get(target_n)

        # 2) if no exact, try substring match on normalized
        if not chosen and target_n:
            for p in procs:
                if target_n in norm(p.get("name", "")):
                    chosen = p.get("name", "")
                    break

        # 3) if still no match, fuzzy closest by human name
        if not chosen and procs:
            names = [p.get("name", "") for p in procs]
            cand = get_close_matches(target, names, n=1, cutoff=0.75)
            if cand:
                chosen = cand[0]

        if not chosen:
            return _with_warning(draft, "not_found", f"No procedure matching '{target}'")

        inv.procedures = [p for p in procs if p.get("name") != chosen]

    elif action == "discount_invoice":
        pct = float(payload.get("percent", 0))
        if pct <= 0:
            return _with_warning(draft, "invalid_param", "discount_invoice requires percent > 0")
        inv.procedures = [
            {"name": p["name"], "billed": round(float(p["billed"]) * (1 - pct / 100.0), 2)}
            for p in (inv.procedures or [])
        ]

    elif action == "discount_procedure":
        name = payload.get("name")
        pct = float(payload.get("percent", 0))
        if not name:
            return _with_warning(draft, "missing_param", "discount_procedure requires 'name'")
        if pct <= 0:
            return _with_warning(draft, "invalid_param", "discount_procedure requires percent > 0")
        newp: List[Dict[str, Any]] = []
        for p in (inv.procedures or []):
            if (p.get("name") or "").lower() == name.lower():
                newp.append({"name": p.get("name"), "billed": round(float(p["billed"]) * (1 - pct / 100.0), 2)})
            else:
                newp.append(p)
        inv.procedures = newp

    elif action == "update_patient":
        if "full name" in payload:
            inv.full_name = payload["full name"]
        if "patient SSN" in payload:
            inv.patient_ssn = payload["patient SSN"]

    elif action == "set_diagnosis":
        inv.diagnose = payload.get("diagnose")

    elif action == "set_date":
        inv.date_of_service = payload.get("date of service") or today_ro()

    else:
        return _with_warning(draft, "unknown_action", f"Unsupported action '{action}'")

    out = json.loads(inv.model_dump_json(by_alias=True, exclude_none=True))
    _set_draft(out)
    return out

modify_invoice_tool = StructuredTool.from_function(
    func=_apply_modification_fn,
    name="modify_invoice",
    description=(
        "Apply a modification to the invoice draft. Supported actions: "
        "add_procedure{name,billed?}, remove_procedure{name}, "
        "discount_invoice{percent}, discount_procedure{name,percent}, "
        "update_patient{'full name'?, 'patient SSN'?}, set_diagnosis{diagnose}, set_date{'date of service'?}."
    ),
    args_schema=ModifyArgs,
    handle_tool_error=True,
)


# -----------------------------
# Tool 4: summarize invoice
# -----------------------------

class SummarizeArgs(BaseModel):
    draft: Dict[str, Any] = Field(default_factory=dict)

def _summarize_invoice_fn(draft: Dict[str, Any] | None = None) -> Dict[str, Any]:
    draft = _get_draft(draft)
    inv = InvoiceDraft.model_validate(draft)
    procs = inv.procedures or []

    # Compute total safely
    total = sum(float(p.get("billed", 0) or 0) for p in procs)

    # Build a clear, detailed summary
    header = [
        f"Patient: {inv.full_name or '[missing]'} (SSN: {inv.patient_ssn or '[missing]'})",
        f"Hospital: {inv.hospital_name or '[missing]'}",
        f"Date of service: {inv.date_of_service or today_ro()}",
        f"Diagnosis: {inv.diagnose or '[missing]'}",
        "",
        "Procedures:" if procs else "Procedures: [missing]",
    ]

    lines = []
    for p in procs:
        nm = p.get("name") or "[missing name]"
        amt = float(p.get("billed", 0) or 0)
        lines.append(f"  - {nm}: ${amt:.2f}")

    footer = ["", f"Total billed: ${total:.2f}"]

    # Compute missing required fields to nudge clearly
    missing = []
    if not inv.full_name: missing.append("full name")
    if not inv.patient_ssn: missing.append("patient SSN")
    if not inv.diagnose: missing.append("diagnose")
    if not procs: missing.append("procedures")

    if missing:
        footer += [
            "",
            "Missing required: " + ", ".join(missing) + ".",
            "Please provide the missing info, then I’ll update the invoice."
        ]
    else:
        footer += [
            "",
            "Would you like any changes? You can say:",
            "• \"add <procedure name>\" (optionally: \"billed <amount>\")",
            "• \"remove <procedure name>\"",
            "• \"add <percent>% discount to invoice\"",
            "• \"discount <procedure name> by <percent>%\"",
            "• or \"approve\" to finalize",
        ]

    message = "\n".join(header + lines + footer)

    out = {"summary": message, "total": round(total, 2), "missing": missing}
    # Keep the latest validated draft in cache for next turns
    _set_draft(json.loads(inv.model_dump_json(by_alias=True, exclude_none=True)))
    return out

summarize_invoice_tool = StructuredTool.from_function(
    func=_summarize_invoice_fn,
    name="summarize_invoice",
    description="Produce a readable summary of the current invoice and list any missing required fields.",
    args_schema=SummarizeArgs,
    handle_tool_error=True,
)


# -----------------------------
# Tool 5: approve & persist
# -----------------------------

class ApproveArgs(BaseModel):
    draft: Dict[str, Any] = Field(default_factory=dict)

def _approve_and_persist_fn(draft: Dict[str, Any] | None = None) -> Dict[str, Any]:
    draft = _get_draft(draft)
    try:
        claim = Claim.model_validate(draft)
    except ValidationError as e:
        return _with_warning(draft, "validation_error", f"Cannot approve; validation failed: {e}")

    claim_id = save_claim(claim)

    minimal = {
        "hospital name": claim.hospital_name,
        "full name": claim.full_name,
        "patient SSN": claim.patient_ssn,
        "diagnose": claim.diagnose,
        "date of service": str(claim.date_of_service),
        "procedures": [{"name": p.name, "billed": p.billed} for p in claim.procedures],
    }
    result = {"claim_id": claim_id, "ready_for_insurance": minimal}

    # Ensure draft has JSON-safe values (no raw date objects)
    _set_draft(jsonable_encoder(claim.model_dump(by_alias=True)))

    return jsonable_encoder(result)

approve_tool = StructuredTool.from_function(
    func=_approve_and_persist_fn,
    name="approve_invoice",
    description=(
        "Validate and persist the invoice locally, and return the minimal JSON payload "
        "(Hospital Name, Patient Full Name, Patient SSN, Diagnosis, Procedures, date of service) "
        "to send to the insurance agent."
    ),
    args_schema=ApproveArgs,
    handle_tool_error=True,
)


# -----------------------------
# Expose tool list
# -----------------------------

TOOLS = [
    extract_claim_from_text_tool,
    complete_from_text_tool,   # extract → complete for free text
    complete_invoice_tool,
    modify_invoice_tool,
    summarize_invoice_tool,
    approve_tool,
]
