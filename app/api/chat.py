import logging
import time

from fastapi import APIRouter, Depends, Request
from psycopg_pool import AsyncConnectionPool

from app.agents.text_to_sql import TextToSQLAgent
from app.config import get_settings
from app.database.constants import CATALOGUE_RELATIONS, CATALOGUE_SCHEMA
from app.database.executor import SQLExecutor
from app.database.introspection import get_schema_metadata, format_schema_context
from app.llm.client import create_llm_client
from app.models.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

chat_router = APIRouter(prefix="/chat")

@chat_router.post("/", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, settings = Depends(get_settings)):
    started = time.perf_counter()
    logger.info(
        "Chat request received: question=%r, history_turns=%d",
        payload.question,
        len(payload.history or []),
    )
    pool: AsyncConnectionPool = request.app.state.database_pool

    business_metadata = await get_schema_metadata(pool)
    catalogue_metadata = await get_schema_metadata(
        pool,
        schema_name=CATALOGUE_SCHEMA,
        relation_names=CATALOGUE_RELATIONS,
    )

    schema_context = (
        "# Business schema (query these public tables/views to produce answers)\n\n"
        f"{format_schema_context(business_metadata)}\n\n"
        "# Metadata catalogue (read-only; query to validate identifiers and values, "
        "never as the answer)\n\n"
        f"{format_schema_context(catalogue_metadata, table_prefix=f'{CATALOGUE_SCHEMA}.')}"
    )
    logger.debug("Schema context loaded (%d chars)", len(schema_context))

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

    response =  await agent.invoke(question=payload.question, history=payload.history)

    total_latency_ms = (time.perf_counter() - started) * 1000

    sql_queries = [
        step.tool_call.sql_query
        for step in response.steps
        if step.tool_call and step.tool_call.sql_query
    ]

    logger.info(
        "Chat request completed in %.1f ms: %d steps, %d SQL queries",
        total_latency_ms,
        len(response.steps),
        len(sql_queries),
    )

    return ChatResponse(
        response=response.response,
        total_latency_ms=total_latency_ms,
        steps=response.steps,
        sql_queries=sql_queries,
        )