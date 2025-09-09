This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.


## Hospital Agent Setup & Testing

### 1. Create and activate a Python virtual environment

```sh
python -m venv .venv
.venv\Scripts\activate
```

In case of error:

```sh
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 2. Install required dependencies

```sh
pip install langgraph langchain langchain-openai pydantic fastapi uvicorn
```

### 3. Configure the OpenAI API key

$env:OPENAI_API_KEY = $null

Add your key to the `.env` file:

```
OPENAI_API_KEY=sk-...
```

### 4. Start the agent API

```sh
uvicorn src.agents.hospital.api:app --reload --port 8000
```

### 5. Test the agent from CLI (example with PowerShell)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/doctor_message" `
>>   -Method Post -ContentType "application/json" `
>>   -Body '{"session_id": null, "message": "Full name Mark Johnson, SSN 328291609, City Hospital on 2025-09-01. Diagnose S52.501A. Procedures: ER visit high complexity; X-ray forearm."}' `
>> | Select-Object session_id, agent_reply | ConvertTo-Json -Depth 100
```