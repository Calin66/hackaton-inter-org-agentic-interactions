
import json
import logging
from .models import Claim, AdjudicationResult
from .adjudicator import adjudicate
from .db import init_db
from .chat_agent import get_or_create_session, _adjudicate_raw_json_tool_fn  # import the JSON adjudication function
from .schemas_chat import ChatRequest, ChatResponse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

init_db(seed=False)

app = FastAPI(title="Insurance Agent Service")

load_dotenv()

def _extract_tool_result(agent_result) -> dict | None:
    steps = agent_result.get("intermediate_steps", []) if isinstance(agent_result, dict) else []
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
    allow_headers=["*"]
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/adjudicate", response_model=AdjudicationResult)
def post_adjudicate(claim: Claim):
    result = adjudicate(claim, write_usage=False)
    return result

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
    # 1) If message is a dict, adjudicate directly from JSON (also accepts 'patient name', etc.)
        if isinstance(req.message, dict):
            raw = json.dumps(req.message)
            obs = _adjudicate_raw_json_tool_fn(raw=raw)
            return ChatResponse(conversation_id=req.conversation_id or "", reply=obs["message"], tool_result=obs)

    # 2) Otherwise, run the conversational agent
        conv_id, executor = get_or_create_session(req.conversation_id)
        result = executor.invoke({"input": req.message})
        reply = result.get("output", "") if isinstance(result, dict) else str(result)
        tool_result = _extract_tool_result(result)
        return ChatResponse(conversation_id=conv_id, reply=reply, tool_result=tool_result)
    except Exception as e:
        logging.exception("Chat endpoint failed")
        return JSONResponse(status_code=500, content={"error": str(e)})
