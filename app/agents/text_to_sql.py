import json
import logging
import time

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.database.executor import SQLExecutor
from app.models.tools import ExecuteSQLArgs
from app.prompts.text_to_sql_agent import get_text_to_sql_prompt
from app.tools.db_tools import EXECUTE_SQL_TOOL
from app.models.chat import ChatTurn, AgentResult, StepTrace, ToolCallTrace

logger = logging.getLogger(__name__)


class TextToSQLAgent:
    def __init__(self, client: AsyncOpenAI, model: str, sql_executor: SQLExecutor, schema_context: str, max_tool_calls: int = 15):
        self.client = client
        self.model = model
        self.sql_executor = sql_executor
        self.schema_context = schema_context
        self.max_tool_calls = max_tool_calls
    
    async def invoke(self, question: str, history: list[ChatTurn] | None = None):
        messages: list[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": get_text_to_sql_prompt(self.schema_context),
            }
        ]

        for turn in history or []:
            messages.append({"role": turn.role, "content": turn.content})

        messages.append({"role": "user", "content": question})

        steps: list[StepTrace] = []

        for iteration in range(self.max_tool_calls):
            logger.info(
                "LLM call %d/%d (model=%s)",
                iteration + 1,
                self.max_tool_calls,
                self.model,
            )
            started = time.perf_counter()
            completion = await self.client.chat.completions.parse(
                model=self.model,
                messages=messages,
                tools=[EXECUTE_SQL_TOOL],
                tool_choice="auto",
            )
            llm_latency_ms = (time.perf_counter() - started) * 1000

            message = completion.choices[0].message
            messages.append(message)

            tool_calls = message.tool_calls or []
            logger.info(
                "LLM responded in %.1f ms: %d tool call(s) requested",
                llm_latency_ms,
                len(tool_calls),
            )

            steps.append(
                StepTrace(
                    index=len(steps) + 1,
                    kind="llm",
                    label="LLM (tool call requested)" if tool_calls else "LLM (final answer)",
                    latency_ms=round(llm_latency_ms, 1),
                )
            )

            if not tool_calls:
                logger.info("LLM returned final answer after %d step(s)", len(steps))
                return AgentResult(response=message.content or "", steps=steps)

            for tool_call in tool_calls:
                content, trace = await self.execute_tool_call(tool_call)

                steps.append(
                    StepTrace(
                        index=len(steps) + 1,
                        kind="tool",
                        label=f"Tool: {trace.name}",
                        latency_ms=trace.latency_ms,
                        tool_call=trace,
                    )
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": content,
                })
        
        logger.warning("Agent exceeded the maximum number of tool calls (%d)", self.max_tool_calls)
        raise RuntimeError("Agent exceeded the maximum number of tool calls")
    
    async def execute_tool_call(self, tool_call):
        name = tool_call.function.name

        if name != "execute_sql":
            raise ValueError(f"Unsupported tool: {name}")

        args = tool_call.function.parsed_arguments

        if not isinstance(args, ExecuteSQLArgs):
            raise TypeError("invalid execute_sql tool arguments.")

        sql_query = args.sql_query
        logger.info("Executing tool '%s': %s", name, sql_query)
        started = time.perf_counter()
        error: str | None = None
        row_count: int | None = None
        columns = []
        rows = []
        total_count = None
        truncated = False

        try:
            result = await self.sql_executor.execute(sql_query)
            content = result.model_dump_json()
            row_count = result.row_count
            columns = result.columns
            rows = result.rows
            total_count = result.total_count
            truncated = result.truncated
        except Exception as exc:
            error = str(exc)
            # capture the error, feed it back to the model to correct itself instead of crashing
            content = json.dumps({"error": error})
            logger.warning("Tool '%s' failed: %s", name, error)

        latency_ms = (time.perf_counter() - started) * 1000

        if error is None:
            logger.info(
                "Tool '%s' returned %s row(s) in %.1f ms (total_count=%s, truncated=%s)",
                name,
                row_count,
                latency_ms,
                total_count,
                truncated,
            )

        trace = ToolCallTrace(
            name=name,
            args=args.model_dump(),
            latency_ms=round(latency_ms, 1),
            sql_query=sql_query,
            row_count=row_count,
            error=error,
            columns=columns,
            rows=rows,
            total_count=total_count,
            truncated=truncated,
        )

        return content, trace
