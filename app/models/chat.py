from pydantic import BaseModel, Field
from typing import Literal
class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str
class ChatRequest(BaseModel):
    question: str
    history: list[ChatTurn] = Field(default_factory=list)

class ChatResponse(BaseModel):
    response: str