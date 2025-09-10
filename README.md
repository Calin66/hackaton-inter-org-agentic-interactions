# 1. Create and activate Python virtual environment

python -m venv .venv
.\.venv\Scripts\Activate.ps1


# 2. In case of error on Windows

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1


# 2. Install backend requirements

pip install -r requirements.txt


# 3. Set OpenAI API key (replace with your real key)

$env:OPENAI_API_KEY="sk-..."

OR if you want to use a local .env file, make sure global env is set to null

$env:OPENAI_API_KEY = $null


# 4. Install frontend dependencies
npm install


# 5. Start backend agents (in separate terminals)

npm run dev:hospital

npm run dev:insurance


# 6. Start frontend (Next.js)

npm run dev
