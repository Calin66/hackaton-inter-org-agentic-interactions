import os, json, re
from typing import Dict, Any, List
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

# ------------------ Helpers ------------------
def normalize_ssn(ssn: str) -> str:
    return re.sub(r"\D+", "", ssn or "")

def normalize_date(text: str) -> str:
    if not text:
        return datetime.today().strftime("%Y-%m-%d")
    fmts = ["%Y-%m-%d","%d-%m-%Y","%d/%m/%Y","%m/%d/%Y","%Y/%m/%d","%d.%m.%Y","%b %d, %Y","%B %d, %Y"]
    for f in fmts:
        try:
            return datetime.strptime(text.strip(), f).strftime("%Y-%m-%d")
        except Exception:
            pass
    return datetime.today().strftime("%Y-%m-%d")

def get_client() -> OpenAI:
    load_dotenv(override=False)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)

def get_model() -> str:
    return os.environ.get("MODEL", "gpt-4o-mini")

# ------------------ Field extraction ------------------
EXTRACTION_SYSTEM = """
You are an expert hospital coding assistant. Extract key fields for billing from doctor's free text.
Return STRICT JSON with keys:
- patient name (string)
- patient SSN (string, digits only)
- hospital name (string)
- date of service (YYYY-MM-DD if present)
- diagnose (string, e.g., ICD-10 like S52.501A if given; else empty string)
- procedures (array of strings; short human names as provided by the doctor)

Do NOT include additional keys or commentary.
If something is missing, use an empty string (or empty array for procedures).
"""

def extract_fields(free_text: str) -> Dict[str, Any]:
    client = get_client()
    model = get_model()
    resp = client.chat.completions.create(
        model=model,
        response_format={ "type": "json_object" },
        messages=[
            { "role": "system", "content": EXTRACTION_SYSTEM },
            { "role": "user", "content": free_text },
        ],
        temperature=0.0,
    )
    content = resp.choices[0].message.content
    try:
        data = json.loads(content)
    except Exception:
        content = content.strip().strip("`")
        a, b = content.find("{"), content.rfind("}")
        data = json.loads(content[a:b+1]) if a != -1 and b != -1 and b > a else {}

    data.setdefault("patient name", "")
    data.setdefault("patient SSN", "")
    data.setdefault("hospital name", "")
    data.setdefault("date of service", "")
    data.setdefault("diagnose", "")
    data.setdefault("procedures", [])

    data["patient SSN"] = normalize_ssn(data.get("patient SSN", ""))
    data["date of service"] = normalize_date(data.get("date of service", ""))

    procs = data.get("procedures", [])
    if isinstance(procs, str):
        procs = [procs]
    data["procedures"] = [p for p in (procs or []) if isinstance(p, str) and p.strip()]

    return data

# ------------------ Natural language intent parsing ------------------
INTENT_SYSTEM = """
You convert a doctor's free-text message into a structured ACTION for a billing assistant.

You MUST return STRICT JSON with keys:
- type: one of [approve, add_procedure, remove_procedure_by_index, remove_procedure_by_name, discount_percent, set_price, provide_fields, unknown]
- params: an object with any of the following keys depending on type:
  - for approve: {}
  - for add_procedure: { "procedure_free_text": string }
  - for remove_procedure_by_index: { "index": integer >=1 }  # 1-based
  - for remove_procedure_by_name: { "name": string }
  - for discount_percent: { "percent": number }
  - for set_price: { "name": string, "amount": number }
  - for provide_fields: { 
        "patient name": string (optional), 
        "patient SSN": string (optional), 
        "diagnose": string (optional), 
        "procedures": array of strings (optional)
    }
  - for unknown: { "reason": string }

RULES:
- If the message expresses approval (e.g., "i confirm, the data is correct", "looks good, send it"), use type=approve.
- If the message asks to remove by position (e.g., "remove the second procedure"), use remove_procedure_by_index.
- If the message names a specific procedure to remove, use remove_procedure_by_name.
- If the message contains a percent discount (e.g., "apply 10% discount", "discount 15"), use discount_percent.
- If the message sets a price (e.g., "set ER visit to 1150"), use set_price.
- If the message provides patient fields (name, SSN, diagnose, procedures), use provide_fields and fill only what you can confidently extract.
- If none of the above, use unknown and give a short reason.

Return ONLY the JSON object. No commentary.
"""

def interpret_doctor_message(message: str, current_lines: List[str]) -> Dict[str, Any]:
    client = get_client()
    model = get_model()
    context = {
        "current_procedures": current_lines,
        "examples": [
            {"msg": "remove the second procedure", "expect": {"type":"remove_procedure_by_index","params":{"index":2}}},
            {"msg": "i confirm, the data is correct", "expect": {"type":"approve","params":{}}},
            {"msg": "apply a 10% discount", "expect": {"type":"discount_percent","params":{"percent":10}}},
            {"msg": "delete x-ray forearm", "expect": {"type":"remove_procedure_by_name","params":{"name":"X-ray forearm"}}},
            {"msg": "set ER visit high complexity to 1150", "expect": {"type":"set_price","params":{"name":"ER visit high complexity","amount":1150}}}
        ]
    }
    resp = client.chat.completions.create(
        model=model,
        response_format={ "type": "json_object" },
        messages=[
            {"role":"system","content":INTENT_SYSTEM},
            {"role":"user","content":json.dumps(context)},
            {"role":"user","content":message},
        ],
        temperature=0.0,
    )
    content = resp.choices[0].message.content
    try:
        data = json.loads(content)
    except Exception:
        data = {"type":"unknown","params":{"reason":"could not parse LLM response"}}
    if "type" not in data:
        data = {"type":"unknown","params":{"reason":"missing type"}}
    if "params" not in data or not isinstance(data["params"], dict):
        data["params"] = {}
    return data
