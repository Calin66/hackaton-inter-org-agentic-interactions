from .models import Claim, AdjudicationResult
from .adjudicator import adjudicate
from .db import init_db
from .chat_agent import (
    get_or_create_session,
    _adjudicate_raw_json_tool_fn,
)  # import the JSON adjudication function
from .schemas_chat import ChatRequest, ChatResponse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import os, json, logging, requests

init_db(seed=False)

app = FastAPI(title="Insurance Agent Service")

load_dotenv()

# ... imports existente ...
import requests
from .config import CORPORATE_AGENT_URL


from urllib.parse import urlparse, urlunparse


def _normalize_corporate_url(raw: str) -> str:
    try:
        u = urlparse(raw or "")
        if not u.scheme:
            return "http://localhost:8003/decide"
        # dacă nu are path sau e doar '/', atașează /decide
        if (not u.path) or (u.path == "/"):
            u = u._replace(path="/decide")
        return urlunparse(u)
    except Exception:
        return "http://localhost:8003/decide"


def _call_corporate_decider(
    work_acc: dict, policy_id: str | None, claim_ctx: dict
) -> dict | None:
    if not (work_acc and (work_acc.get("suspected") is True)):
        return None

    raw_url = os.getenv("CORPORATE_AGENT_URL", CORPORATE_AGENT_URL)
    url = _normalize_corporate_url(raw_url)

    payload = {
        "policy_id": policy_id,
        "work_accident": work_acc,
        "patient": {
            "name": claim_ctx.get("full_name", ""),
            "ssn": claim_ctx.get("patient_ssn", ""),
        },
        "context": {
            "hospital_name": claim_ctx.get("hospital_name", ""),
            "date_of_service": claim_ctx.get("date_of_service", ""),
            "diagnose": claim_ctx.get("diagnose", ""),
            "procedures": claim_ctx.get("procedures", []),
        },
    }
    try:
        r = requests.post(url, json=payload, timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": f"{e}"}


def _attach_corporate(obs: dict, msg_dict: dict) -> dict:
    """
    Dacă mesajul de la Hospital conține work_accident.suspected=True, cere decizia Corporate și
    atașează în tool_result:
      - result_json.corporate_meta
      - result_json.payer = 'corporation' | 'patient'
    """
    try:
        work_acc = (msg_dict or {}).get("work_accident") or {}
        if not (isinstance(work_acc, dict) and work_acc.get("suspected") is True):
            return obs

        rj = obs.get("result_json") or {}
        policy_id = rj.get("policy_id")

        # Construim un context simplu (dict), fără modele Pydantic:
        procs = []
        for p in msg_dict.get("procedures") or []:
            try:
                procs.append(
                    {
                        "name": str(p.get("name", "")),
                        "billed": float(p.get("billed", 0)),
                    }
                )
            except Exception:
                procs.append({"name": str(p.get("name", "")), "billed": 0.0})

        claim_ctx = {
            "full_name": msg_dict.get("fullName") or msg_dict.get("full name") or "",
            "patient_ssn": msg_dict.get("patientSSN")
            or msg_dict.get("patient SSN")
            or "",
            "hospital_name": msg_dict.get("hospitalName")
            or msg_dict.get("hospital name")
            or "",
            "date_of_service": msg_dict.get("dateOfService")
            or msg_dict.get("date of service")
            or "",
            "diagnose": msg_dict.get("diagnose") or "",
            "procedures": procs,
        }

        corp = _call_corporate_decider(work_acc, policy_id, claim_ctx)

        meta = None
        if isinstance(corp, dict):
            # acceptăm fie direct dict-ul, fie sub-chei convenționale
            meta = corp.get("corporate_meta") or corp.get("decision") or corp

        payer = "patient"
        if isinstance(meta, dict) and meta.get("is_work_accident") is True:
            payer = "corporation"

        obs.setdefault("result_json", {})
        obs["result_json"]["corporate_meta"] = meta
        obs["result_json"]["payer"] = payer
        return obs

    except Exception as e:
        obs.setdefault("result_json", {})
        obs["result_json"]["corporate_meta"] = {"error": f"corporate call failed: {e}"}
        obs["result_json"]["payer"] = "patient"
        return obs


def _extract_tool_result(agent_result) -> dict | None:
    steps = (
        agent_result.get("intermediate_steps", [])
        if isinstance(agent_result, dict)
        else []
    )
    for step in steps:
        try:
            observation = step[1]
            if isinstance(observation, dict) and "result_json" in observation:
                return observation
        except Exception:
            pass
    return None


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post(
    "/adjudicate", response_model=None
)  # scoatem response_model ca să putem adăuga câmpuri extra
def post_adjudicate(claim: Claim):
    result = adjudicate(claim, write_usage=False)

    # ==== OPTIONAL Corporate flow ====
    payer = "patient"
    corporate_meta = None

    # Ne uităm dacă a venit work_accident din hospital (prin chat sau adjudicate direct)
    try:
        # Claim nu are campul in model, dar îl poți prelua din request body cu starlette Request
        # sau (mai simplu) acceptă și path-ul /chat care deja primește dict cu work_accident.
        # Variantă simplă: încercăm să citim din environul requestului via context local (nu mereu OK).
        # Recomandat: mută flow-ul corporate în /chat (deja implementat în varianta ta) sau
        # extinde modelul Claim cu un Optional[dict] work_accident.
        # Mai jos e varianta când ai extins modelul:
        wa = getattr(claim, "work_accident", None)
    except Exception:
        wa = None

    # Dacă ai extins modelul (recomandat):
    if isinstance(wa, dict) and wa.get("suspected"):
        try:
            import os, requests

            CORPORATE_URL = os.getenv(
                "CORPORATE_AGENT_URL", "http://localhost:8003/adjudicate"
            )
            payload = {
                "patient": {"full_name": claim.full_name, "ssn": claim.patient_ssn},
                "happened_at": (wa.get("happened_at") or ""),
                "location": (wa.get("location") or ""),
                "narrative": (wa.get("narrative") or ""),
                "during_work_hours": bool(wa.get("during_work_hours")),
                "sick_leave_days": wa.get("sick_leave_days"),
                "date_of_service": claim.date_of_service.isoformat(),
            }
            r = requests.post(CORPORATE_URL, json=payload, timeout=10)
            r.raise_for_status()
            corp = r.json() or {}
            corporate_meta = {
                "decision_id": corp.get("decision_id"),
                "status": corp.get("status"),
                "suggested": {
                    "is_work_accident": corp.get("is_work_accident"),
                    "payer": (
                        "corporation" if corp.get("is_work_accident") else "patient"
                    ),
                },
                "reason": corp.get("reason"),
            }
            if corp.get("is_work_accident"):
                payer = "corporation"
        except Exception as e:
            corporate_meta = {"error": str(e)}

    # întoarcem json-ul adjudicării + meta corporate + payer
    base = result.model_dump()
    base["payer"] = payer
    base["corporate_meta"] = corporate_meta
    return base


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        # 1) JSON direct de la Hospital → adjudicare + corporate enrich
        if isinstance(req.message, dict):
            raw = json.dumps(req.message)
            obs = _adjudicate_raw_json_tool_fn(raw=raw)
            obs = _attach_corporate(obs, req.message)  # <— AICI e cheia
            return ChatResponse(
                conversation_id=req.conversation_id or "",
                reply=obs["message"],
                tool_result=obs,
            )

        # 2) Conversațional (mai rar pentru Hospital) – rămâne cum era
        conv_id, executor = get_or_create_session(req.conversation_id)
        result = executor.invoke({"input": req.message})
        reply = result.get("output", "") if isinstance(result, dict) else str(result)
        tool_result = _extract_tool_result(result)

        # ✨ opțional: dacă vrei să încerci enrichment și aici, ai nevoie de un msg_dict.
        return ChatResponse(
            conversation_id=conv_id, reply=reply, tool_result=tool_result
        )

    except Exception as e:
        logging.exception("Chat endpoint failed")
        return JSONResponse(status_code=500, content={"error": str(e)})
