## Set env variable
$env:OPENAI_API_KEY="your-new-api-key"

## Run uvicorn
uvicorn src.agents.insurance.main:app --reload --port 8001

## Open Swagger Interface 
http://localhost:8001/docs

~ POST /adjudicate

Deterministic, stateless adjudication of a single claim. No small-talk, no LLM. It validates the payload, does RAG matching for procedures, applies eligibility + limits + coverage tiers, and returns a structured result and a formatted “letter” you can send back to the Hospital Agent.

The service accepts both the hospital-style keys (with spaces) and the code-friendly ones. Examples:
{
  "full name": "Mark Johnson",
  "patient SSN": "328291609",
  "hospital name": "City Hospital",
  "date of service": "2025-09-01",
  "diagnose": "S52.501A",
  "procedures": [
    { "name": "ER visit high complexity", "billed": 1200 },
    { "name": "X-ray forearm", "billed": 300 }
  ]
}


~ POST /chat

Conversational entrypoint (LLM-powered). Keeps context (per conversation_id), asks for missing info, can parse natural language or embedded JSON, then calls the adjudication tool and explains the result.

{
  "message": "Please adjudicate: full name Mark Johnson, patientSSN-328291609, name of hospital City Hospital, date of Service 2025-09-01, diagnose S52.501A and procedure X-ray forearm billed 300"
}

 OR
 
{
  "conversation_id": "optional-string",
  "message": {
    "patient name": "Mark Johnson",
    "patient SSN": "328291609",
    "hospital name": "City Hospital",
    "date of service": "2025-09-01",
    "diagnose": "S52.501A",
    "procedures": [
      { "name": "ER visit high complexity", "billed": 1200 },
      { "name": "X-ray forearm", "billed": 300 }
    ]
  }
}

