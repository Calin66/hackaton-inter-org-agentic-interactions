from pydantic import BaseModel
from typing import Optional, Any, Dict, Union

class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: Union[str, Dict[str, Any]]

class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    tool_result: Optional[Dict[str, Any]] = None  # includes result_json/message if a tool was used
