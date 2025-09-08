import os
import json
from typing import List, Dict, Any, Tuple
from datetime import date
from uuid import uuid4

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain.tools import StructuredTool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory

from .models import Claim, ProcedureClaim
from .adjudicator import adjudicate


# ---------- Schemas ----------
class ProcedureIn(BaseModel):
    name: str = Field(..., description="Procedure name as received in the claim")
    billed: float = Field(..., description="Billed amount from hospital for this procedure")

class ClaimIn(BaseModel):
    fullName: str
    patientSSN: str
    hospitalName: str
    dateOfService: date
    diagnose: str
    procedures: List[ProcedureIn]

class FreeText(BaseModel):
    text: str

class RawJSON(BaseModel):
    raw: str


def _require_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in environment. Load it via .env or export it before running.")
    return api_key


# ---------- Tool: structured adjudication ----------
def _adjudicate_tool_fn(**kwargs) -> Dict[str, Any]:
    data = ClaimIn(**kwargs)
    claim_model = Claim(
        full_name=data.fullName,
        patient_ssn=data.patientSSN,
        hospital_name=data.hospitalName,
        date_of_service=data.dateOfService,
        diagnose=data.diagnose,
        procedures=[ProcedureClaim(name=p.name, billed=p.billed) for p in data.procedures],
    )
    result = adjudicate(claim_model, write_usage=False)
    return {"result_json": result.model_dump(), "message": result.pretty_message}

adjudicate_claim_tool = StructuredTool.from_function(
    func=_adjudicate_tool_fn,
    name="adjudicate_claim",
    description=(
        "Compute coverage/payable for a medical claim when you have "
        "fullName, patientSSN, hospitalName, dateOfService (YYYY-MM-DD), diagnose, procedures[{name,billed}]."
    ),
    args_schema=ClaimIn,
    handle_tool_error=True,
)


# ---------- Tool: extract from natural language ----------
def _extract_claim_from_text_fn(text: str) -> Dict[str, Any]:
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        temperature=0,
        api_key=_require_api_key(),  # <-- explicit
    )
    extractor = llm.with_structured_output(ClaimIn)
    prompt = (
        "Extract the medical claim fields from the text below. "
        "Only fill fields explicitly present; otherwise leave them empty or omit. "
        "NUMERIC billed must be a number.\n\n"
        f"TEXT:\n{text}"
    )
    parsed: ClaimIn = extractor.invoke(prompt)
    return parsed.model_dump()

extract_claim_from_text_tool = StructuredTool.from_function(
    func=_extract_claim_from_text_fn,
    name="extract_claim_from_text",
    description=(
        "Extract structured claim fields from natural language text. "
        "Use this when the user provides claim details in prose (no JSON). "
        "Returns ClaimIn fields: fullName, patientSSN, hospitalName, dateOfService (YYYY-MM-DD), "
        "diagnose, procedures[{name,billed}]."
    ),
    args_schema=FreeText,
    handle_tool_error=True,
)


# ---------- Tool: adjudicate from raw JSON embedded in text ----------
def _adjudicate_raw_json_tool_fn(raw: str) -> Dict[str, Any]:
    s = raw.strip()
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start:end+1]

    payload = json.loads(s)

    def pick(d: dict, *keys):
        for k in keys:
            if k in d and d[k] not in (None, ""):
                return d[k]
        return None

    procedures_in = payload.get("procedures") or []
    norm_procs: List[ProcedureClaim] = []
    for p in procedures_in:
        billed = p.get("billed")
        try:
            billed = float(billed)
        except Exception:
            raise ValueError("Procedure 'billed' must be numeric.")
        norm_procs.append(ProcedureClaim(name=p.get("name"), billed=billed))

    full_name       = pick(payload, "full name", "fullName", "full_name", "patient name", "patientName")
    patient_ssn     = pick(payload, "patient SSN", "patientSSN", "patient_ssn", "ssn")
    hospital_name   = pick(payload, "hospital name", "hospitalName", "hospital_name", "name of hospital", "hospital")
    date_of_service = pick(payload, "date of service", "dateOfService", "date_of_service", "service date", "dos", "date")
    diagnose        = pick(payload, "diagnose", "diagnosis", "dx")

    claim_model = Claim(
        full_name=full_name,
        patient_ssn=patient_ssn,
        hospital_name=hospital_name,
        date_of_service=date_of_service,  # Pydantic will parse YYYY-MM-DD
        diagnose=diagnose,
        procedures=norm_procs,
    )

    result = adjudicate(claim_model, write_usage=False)
    return {"result_json": result.model_dump(), "message": result.pretty_message}

adjudicate_claim_json_tool = StructuredTool.from_function(
    func=_adjudicate_raw_json_tool_fn,
    name="adjudicate_claim_json",
    description="Adjudicate when the user pasted a JSON claim inside their message. Pass the raw JSON string in 'raw'.",
    args_schema=RawJSON,
    handle_tool_error=True,
)


# ---------- Agent ----------
SYSTEM_PROMPT = (
    "You are the Insurance Agent. "
    "If the user provides claim details in natural language, first call extract_claim_from_text. "
    "If the user pasted a JSON claim, call adjudicate_claim_json. "
    "Otherwise, when you already have all required fields, call adjudicate_claim. "
    "If something is missing, ask concise follow-up questions. "
    "When explaining results, clearly cover payable, limits, patient responsibility (allowed portion), "
    "and potential balance bill (if out-of-network). Be brief and professional."
)

def build_agent() -> AgentExecutor:
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        temperature=0,
        api_key=_require_api_key(),  # <-- explicit
    )

    tools = [
        extract_claim_from_text_tool,
        adjudicate_claim_tool,
        adjudicate_claim_json_tool,
    ]

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

    return AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        verbose=False,
        return_intermediate_steps=True,
    )


# ---------- Sessions ----------
_SESSIONS: Dict[str, AgentExecutor] = {}

def get_or_create_session(conversation_id: str | None) -> Tuple[str, AgentExecutor]:
    if not conversation_id:
        conversation_id = str(uuid4())
    if conversation_id not in _SESSIONS:
        _SESSIONS[conversation_id] = build_agent()
    return conversation_id, _SESSIONS[conversation_id]
