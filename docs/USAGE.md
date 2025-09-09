# Hospital ⇄ Insurance Agent Flow

## Prerequisites

- Python 3.10+ and Node 18+
- `OPENAI_API_KEY` set in your environment for both Python services
- Optional:
  - `INSURANCE_AGENT_URL` (default `http://localhost:8001/chat`)
  - `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`)

## Install

```bash
python -m venv .venv
# Windows PowerShell
. .venv/Scripts/activate
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt
npm install
```

## Run Services

Open 3 terminals:

1) Insurance Agent (port 8001)

```bash
uvicorn src.agents.insurance.main:app --host 0.0.0.0 --port 8001 --reload
```

2) Hospital Agent (port 8000)

```bash
# ensure INSURANCE_AGENT_URL points to insurance /chat
uvicorn src.agents.hospital.api:app --host 0.0.0.0 --port 8000 --reload
```

3) Frontend (port 3000)

```bash
npm run dev
# open http://localhost:3000
```

Alternatively (three terminals):

```bash
npm run dev:web
npm run dev:hospital
npm run dev:insurance
```

## Use the App

1. New claim → first message must include required fields:

   Patient Mark Johnson, SSN 123-45-6789, City Hospital, 2025-09-01, diagnose S52.501A. Procedures: ER visit high complexity billed 1200; X-ray forearm billed 300.

2. Type: `send to insurance`.

   - You will see an "Insurance response received" approval card and a "Reply" badge in the sidebar.

3. Approve or Deny in the card.

   - Approve → posts reply into the chat, clears sidebar badge.
   - Deny → dismisses the card, clears sidebar badge.

4. To finalize and save the hospital claim JSON, type `approve` to the hospital agent; JSON is saved to `data/claims/`.

## Verify Delivery

- Browser Network → POST `/doctor_message` contains `insurance_pending` when insurer replied.
- Insurance terminal shows `POST /chat 200` when it receives the claim.

## Troubleshooting

- Empty draft after `send to insurance`:
  - Provide patient name, SSN, diagnose, and at least one billed procedure first.
- 502 from hospital when contacting insurance:
  - Ensure insurance runs on 8001 and `INSURANCE_AGENT_URL` matches.
- LLM errors:
  - Ensure `OPENAI_API_KEY` is set for both services.

