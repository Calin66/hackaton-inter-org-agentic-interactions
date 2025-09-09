from __future__ import annotations
import os
from typing import Dict

from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from .tools import TOOLS
from .tools import _require_api_key  # reuse

SYSTEM = SystemMessage(
    content=(
        "You are a hospital-side intake & billing agent.\n"
        "You are an assistant for the doctor making the claim. "
        "Only answer questions related to medical claims and invoices. "
        "If asked anything out of context, politely refuse to answer.\n"
        "If the doctor sends free text (not JSON), FIRST call complete_from_text to extract and fill tariffs/date, THEN call summarize_invoice and STOP.\n"
        "When the doctor requests a change (add/remove/discount/name/SSN/diagnosis/date), call modify_invoice with the right action and payload, THEN call summarize_invoice and STOP.\n"
        "Only call approve_invoice when the doctor says 'approve' and all required fields are present.\n"
        "When removing a procedure, pass the EXACT name string you see in the current invoice summary to modify_invoice.payload.name (case-insensitive matching is allowed)."
    )
)


prompt = ChatPromptTemplate.from_messages(
    [
        SYSTEM,
        MessagesPlaceholder("history"),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ]
)

llm = ChatOpenAI(
    model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
    temperature=0,
    api_key=_require_api_key(),
)

agent = create_openai_tools_agent(llm, TOOLS, prompt)

# in-memory sessions
_SESSIONS: Dict[str, ConversationBufferMemory] = {}

def _memory_for(session_id: str) -> ConversationBufferMemory:
    mem = _SESSIONS.get(session_id)
    if not mem:
        mem = ConversationBufferMemory(return_messages=True, memory_key="history")
        _SESSIONS[session_id] = mem
    return mem

def executor_for(session_id: str) -> AgentExecutor:
    memory = _memory_for(session_id)
    return AgentExecutor(
        agent=agent,
        tools=TOOLS,
        memory=memory,
        verbose=False,
        max_iterations=12,              # was default (~15) – set explicitly
        early_stopping_method="force",
        handle_parsing_errors=True,
        return_intermediate_steps=True # keep responses clean
    )