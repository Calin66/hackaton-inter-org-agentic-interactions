import os, json, re
from typing import Dict, Any, List, Optional
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv


# ------------------ Helpers ------------------
def normalize_ssn(ssn: str) -> str:
    return re.sub(r"\D+", "", ssn or "")


def normalize_date(text: str) -> str:
    if not text:
        return datetime.today().strftime("%Y-%m-%d")
    fmts = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%b %d, %Y",
        "%B %d, %Y",
    ]
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
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {"role": "user", "content": free_text},
        ],
        temperature=0.0,
    )
    content = resp.choices[0].message.content
    try:
        data = json.loads(content)
    except Exception:
        content = content.strip().strip("`")
        a, b = content.find("{"), content.rfind("}")
        data = json.loads(content[a : b + 1]) if a != -1 and b != -1 and b > a else {}

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


# ------------------ Talkative prompt for missing data ------------------
MISSING_PROMPT_SYSTEM = """
You are a friendly, concise hospital billing assistant. The doctor is creating an invoice.
Using the provided partial invoice and list of missing keys, write a short, warm message that:
- acknowledges any patient name if present (e.g., 'Started a draft for Mark Johnson.'),
- explains next steps succinctly,
- asks for the missing fields explicitly,
- offers an example of how to provide them in one line.

Keep it under 3 short sentences. Output plain text only.
"""


def generate_missing_prompt(invoice: Dict[str, Any], missing_keys: List[str]) -> str:
    client = get_client()
    model = get_model()
    payload = {"invoice": invoice, "missing": missing_keys}
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": MISSING_PROMPT_SYSTEM},
            {"role": "user", "content": json.dumps(payload)},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()


# ------------------ Natural language intent parsing ------------------
INTENT_SYSTEM = """
You convert a doctor's free-text message into a structured ACTION for a hospital billing assistant.

You MUST return STRICT JSON with keys:
- type: one of [
    approve,
    send_to_insurance,
    add_procedure,
    remove_procedure_by_index,
    remove_procedure_by_name,
    discount_percent,
    set_price,
    provide_fields,
    set_work_accident,
    smalltalk,
    unknown
  ]
- params: an object with any of the following keys depending on type:
  - for approve: {}
  - for add_procedure: { "procedure_free_text": string }
  - for remove_procedure_by_index: { "index": integer >=1 }  # 1-based
  - for remove_procedure_by_name: { "name": string }
  - for discount_percent: { "percent": number, "index": integer (optional, 1-based), "name": string (optional) }
    # If "index" is present, apply to that procedure position; if "name" is present, apply to that procedure by exact name.
    # If neither is present, apply to ALL procedures.
  - for set_price: { "name": string, "amount": number }
  - for provide_fields: {
        "patient name": string (optional),
        "patient SSN": string (optional),
        "date of service": string (optional, any natural date; the server will normalize),
        "diagnose": string (optional),
        "procedures": array of strings (optional)
    }
  - for set_work_accident: {
        "suspected": boolean (optional, default true if details provided),
        "narrative": string (optional),
        "location": string (optional),
        "during_work_hours": boolean (optional; accept ro: DA/NU),
        "sick_leave_days": integer (optional),
        "happened_at": string (ISO-like, e.g. "2025-09-10 08:30") (optional)
    }
  - for smalltalk: { "reply": string }
  - for unknown: { "reason": string }

IMPORTANT – USING current_procedures:
- You will also be given a list called current_procedures (exact line names on the invoice).
- When the message targets a specific procedure by NAME, set params.name to the EXACT string from current_procedures:
  * match case-insensitively, ignoring minor punctuation/hyphens/spaces;
  * pick the closest match if there’s minor variation;
  * do NOT invent new names.
- When the message targets a specific procedure by POSITION (e.g., "the second"), set params.index accordingly (1-based).
- If the message says "to <procedure>" or otherwise targets a single line, you MUST include either params.name or params.index.
  Only omit both for broad commands like "apply a 10% discount" that clearly apply to all procedures.

SCOPE POLICY:
- The assistant is ONLY for hospital billing tasks: drafting/adjusting/approving invoices, patient identifiers, diagnosis strings, procedures, prices/discounts, sending to insurance, and marking work accidents metadata for billing.
- If the message is not related to billing, return type="unknown" with reason="out_of_scope".
- Greetings/thanks → type="smalltalk" with a short reply.

MAPPING RULES:
- Romanian is allowed.
- If the message contains "trimite la insurance" or "send to insurance" -> type="send_to_insurance".
- If the message starts with or contains "seteaza accident de munca" / "set work accident" followed by key=value pairs (semicolon or comma separated), map to type="set_work_accident" and parse pairs into params.
  Accepted keys (case-insensitive): suspected, narrative, location, during_work_hours, sick_leave_days, happened_at.
  For during_work_hours, accept values in {DA, NU, true, false, yes, no, 1, 0}. Convert to boolean.
  For sick_leave_days, convert to integer when possible.
  If details are provided but suspected missing, set suspected=true.
- Natural phrasing like "e accident de munca: ... cum s-a intamplat ... unde ... in timpul orelor: DA ... zile: 10 ..." -> also type="set_work_accident" with extracted fields.
- Price/procedure edits map to their types as usual.
- If none matches but in scope → unknown with short reason.

Return ONLY the JSON object. No commentary.
"""


def interpret_doctor_message(message: str, current_lines: List[str]) -> Dict[str, Any]:
    client = get_client()
    model = get_model()
    # Expanded examples to bias name/index discounts and date changes
    # Examples include Romanian variants to robustly trigger intents
    context = {
        "current_procedures": current_lines,
        "examples": [
            # smalltalk
            {
                "msg": "hello",
                "expect": {
                    "type": "smalltalk",
                    "params": {
                        "reply": "Hello! I’m your hospital billing assistant. What can I help you with today?"
                    },
                },
            },
            {
                "msg": "salut",
                "expect": {
                    "type": "smalltalk",
                    "params": {"reply": "Salut! Cu ce te pot ajuta la facturare?"},
                },
            },
            {
                "msg": "multumesc",
                "expect": {
                    "type": "smalltalk",
                    "params": {"reply": "Cu plăcere! Mai pot ajuta cu factura?"},
                },
            },
            # send to insurance (EN + RO)
            {
                "msg": "send to insurance",
                "expect": {"type": "send_to_insurance", "params": {}},
            },
            {
                "msg": "trimite la insurance",
                "expect": {"type": "send_to_insurance", "params": {}},
            },
            {
                "msg": "trimite la asigurator",
                "expect": {"type": "send_to_insurance", "params": {}},
            },
            # approve
            {
                "msg": "i confirm, the data is correct",
                "expect": {"type": "approve", "params": {}},
            },
            {"msg": "aprob", "expect": {"type": "approve", "params": {}}},
            # procedures / prices
            {
                "msg": "apply a 10% discount",
                "expect": {"type": "discount_percent", "params": {"percent": 10}},
            },
            {
                "msg": "aplica discount 10%",
                "expect": {"type": "discount_percent", "params": {"percent": 10}},
            },
            {
                "msg": "remove the second procedure",
                "expect": {"type": "remove_procedure_by_index", "params": {"index": 2}},
            },
            {
                "msg": "sterge a doua procedura",
                "expect": {"type": "remove_procedure_by_index", "params": {"index": 2}},
            },
            {
                "msg": "delete x-ray forearm",
                "expect": {
                    "type": "remove_procedure_by_name",
                    "params": {"name": "X-ray forearm"},
                },
            },
            {
                "msg": "adauga ER visit",
                "expect": {
                    "type": "add_procedure",
                    "params": {"procedure_free_text": "ER visit"},
                },
            },
            {
                "msg": "set ER visit high complexity to 1150",
                "expect": {
                    "type": "set_price",
                    "params": {"name": "ER visit high complexity", "amount": 1150},
                },
            },
            # set_work_accident — EXACTLY your style
            {
                "msg": 'seteaza accident de munca: suspected=true; narrative="accident pe bicicleta in drum direct spre client"; location="Moara de Foc"; during_work_hours=DA; sick_leave_days=10; happened_at="2025-09-10 08:30"',
                "expect": {
                    "type": "set_work_accident",
                    "params": {
                        "suspected": True,
                        "narrative": "accident pe bicicleta in drum direct spre client",
                        "location": "Moara de Foc",
                        "during_work_hours": True,
                        "sick_leave_days": 10,
                        "happened_at": "2025-09-10 08:30",
                    },
                },
            },
            # set_work_accident — natural RO
            {
                "msg": "e accident de munca: cum s-a intamplat: pe bicicleta; unde: Moara de Foc; in timpul orelor: DA; zile concediu: 10; cand: 2025-09-10 08:30",
                "expect": {
                    "type": "set_work_accident",
                    "params": {
                        "suspected": True,
                        "narrative": "pe bicicleta",
                        "location": "Moara de Foc",
                        "during_work_hours": True,
                        "sick_leave_days": 10,
                        "happened_at": "2025-09-10 08:30",
                    },
                },
            },
            # out of scope
            {
                "msg": "what's the weather in Bucharest?",
                "expect": {"type": "unknown", "params": {"reason": "out_of_scope"}},
            },
            {
                "msg": "spune-mi un banc",
                "expect": {"type": "unknown", "params": {"reason": "out_of_scope"}},
            },
            # corporate agent
            {
                "msg": "date of service 2025-09-10",
                "expect": {
                    "type": "provide_fields",
                    "params": {"date of service": "2025-09-10"},
                },
            },
            {
                "msg": "set DOS to 2025-09-10",
                "expect": {
                    "type": "provide_fields",
                    "params": {"date of service": "2025-09-10"},
                },
            },
            {
                "msg": "data serviciului 2025-09-10",
                "expect": {
                    "type": "provide_fields",
                    "params": {"date of service": "2025-09-10"},
                },
            },
            {
                "msg": "seteaza data 2025-09-10",
                "expect": {
                    "type": "provide_fields",
                    "params": {"date of service": "2025-09-10"},
                },
            },
        ],
    }

    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": INTENT_SYSTEM},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            {"role": "user", "content": message},
        ],
        temperature=0.0,
    )
    content = resp.choices[0].message.content
    try:
        data = json.loads(content)
    except Exception:
        data = {"type": "unknown", "params": {"reason": "could not parse LLM response"}}
    if "type" not in data:
        data = {"type": "unknown", "params": {"reason": "missing type"}}
    if "params" not in data or not isinstance(data["params"], dict):
        data["params"] = {}
    return data


# ------------------ LLM mapping for procedures ------------------
PROC_MAP_SYSTEM = """
You map a doctor's free-text procedure description to the closest tariff name from a given list.
Return STRICT JSON: { "choice": "<exact tariff name or empty string>" }
Only choose from the provided list; if no good match, return empty string.
"""


def resolve_procedure_name(free_text: str, choices: List[str]) -> Optional[str]:
    if not free_text or not choices:
        return None
    client = get_client()
    model = get_model()
    prompt = {"free_text": free_text, "choices": choices}
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": PROC_MAP_SYSTEM},
            {"role": "user", "content": json.dumps(prompt)},
        ],
        temperature=0.0,
    )
    content = resp.choices[0].message.content
    try:
        data = json.loads(content)
        choice = (data.get("choice") or "").strip()
        return choice or None
    except Exception:
        return None
