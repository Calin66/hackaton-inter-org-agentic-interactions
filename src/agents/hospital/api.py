# src/agents/hospital/api.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from dotenv import load_dotenv

from .agent import executor_for
from .tariff import SYNTHETIC_TARIFF
# Deterministic pipeline tools
from .tools import complete_from_text_tool, summarize_invoice_tool

# Load environment variables from .env (OPENAI_API_KEY, etc.)
load_dotenv()

app = FastAPI(title="Hospital Agent", version="0.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Deterministic free-text filter endpoint
# -------------------------
@app.post("/doctor/parse")
def doctor_parse(payload: dict = Body(...)):
    """
    Deterministic pipeline for free text:
      text -> extract -> complete (tariff/date) -> summarize
    Returns both the structured draft and the human-readable summary.
    """
    try:
        text = (payload.get("message") or "").strip()
        if not text:
            raise ValueError("Body must include a non-empty 'message' field.")

        # 1) extract + complete
        completed = complete_from_text_tool.invoke({"text": text})  # -> dict draft

        # 2) summarize
        summary = summarize_invoice_tool.invoke({"draft": completed})

        return {
            "message": summary.get("summary", ""),
            "draft": completed,     # structured JSON draft
            "summary": summary,     # includes total and missing fields
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------
# Helper functions for agent-driven endpoint
# -------------------------
def _coerce_tool_output(val: Any) -> Optional[Dict[str, Any]]:
    """
    Tool outputs might be dicts or JSON strings. Best-effort normalize to dict.
    """
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return None
    return None


def _extract_tool_result(result: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Returns (summarize_result, approve_result) if found.
    Works with both top-level keys and AgentExecutor 'intermediate_steps'
    when return_intermediate_steps=True.
    """
    summarize = None
    approve = None

    # 1) Top-level keys
    for k, v in list(result.items()):
        if isinstance(k, str) and k.endswith(":summarize_invoice"):
            summarize = _coerce_tool_output(v) or summarize
        if isinstance(k, str) and k.endswith(":approve_invoice"):
            approve = _coerce_tool_output(v) or approve

    # 2) Intermediate steps
    steps = result.get("intermediate_steps")
    if isinstance(steps, list):
        for action, out in steps:
            try:
                tool_name = getattr(action, "tool", None) or getattr(action, "tool_name", None)
            except Exception:
                tool_name = None
            if tool_name == "summarize_invoice":
                candidate = _coerce_tool_output(out)
                if candidate:
                    summarize = candidate
            elif tool_name == "approve_invoice":
                candidate = _coerce_tool_output(out)
                if candidate:
                    approve = candidate

    return summarize, approve


# -------------------------
# Agent-driven conversational endpoint
# -------------------------
@app.post("/doctor_message")
def doctor_message(payload: dict = Body(...)):
    try:
        text = (payload.get("message") or "").strip()
        session_id = str(payload.get("session_id") or "default")   # <— NEW
        if not text:
            raise ValueError("Body must include a non-empty 'message' field.")

        executor = executor_for(session_id)                         # <— USE IT
        result = executor.invoke({"input": text})

        agent_text = result.get("output", "") or ""

        summarize, approve = _extract_tool_result(result)
        tool_result = approve or summarize

        if summarize and "summary" in summarize:
            agent_text = summarize["summary"]

        if approve:
            agent_text = (
                "Invoice approved ✅. "
                "JSON ready for insurance is available in 'tool_result.ready_for_insurance'."
            )

        # 👇 force safe serialization
        return jsonable_encoder({"message": agent_text, "tool_result": tool_result})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------
# Health check
# -------------------------
@app.get("/hospital/health")
def health():
    ok = bool(SYNTHETIC_TARIFF)
    return {"ok": ok, "tariff_items": len(SYNTHETIC_TARIFF)}
