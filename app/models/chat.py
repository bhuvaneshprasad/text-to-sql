from pydantic import BaseModel, Field
from typing import Literal, Any
class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str
class ChatRequest(BaseModel):
    question: str
    history: list[ChatTurn] = Field(default_factory=list)

class ToolCallTrace(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float
    sql_query: str | None = None
    row_count: int | None = None
    error: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    total_count: int | None = None
    truncated: bool = False

class StepTrace(BaseModel):
    index: int
    kind: Literal["llm", "tool"]
    label: str
    latency_ms: float
    tool_call: ToolCallTrace | None = None

class AgentResult(BaseModel):
    response: str
    steps: list[StepTrace] = Field(default_factory=list)

class ChatResponse(BaseModel):
    response: str
    total_latency_ms: float = 0.0
    steps: list[StepTrace] = Field(default_factory=list)
    sql_queries: list[str] = Field(default_factory=list)