from fastapi import APIRouter, Depends, Request
from psycopg_pool import AsyncConnectionPool

from app.agents.text_to_sql import TextToSQLAgent
from app.config import get_settings
from app.database.executor import SQLExecutor
from app.database.introspection import get_schema_metadata, format_schema_context
from app.llm.client import create_llm_client
from app.models.chat import ChatRequest, ChatResponse

chat_router = APIRouter(prefix="/chat")

@chat_router.post("/", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, settings = Depends(get_settings)):
    pool: AsyncConnectionPool = request.app.state.database_pool
    schema_metadata = await get_schema_metadata(pool)
    schema_context = format_schema_context(schema_metadata)

    executor = SQLExecutor(
        pool=pool,
        max_rows=settings.sql_max_rows,
        statement_timeout_ms=settings.sql_statement_timeout_ms,
    )

    agent = TextToSQLAgent(
        client=create_llm_client(settings=settings),
        model=settings.llm_chat_model,
        sql_executor=executor,
        schema_context=schema_context,
    )

    response =  await agent.invoke(question=payload.question)

    return ChatResponse(response=response)