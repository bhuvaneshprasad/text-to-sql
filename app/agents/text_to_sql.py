from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.database.executor import SQLExecutor
from app.models.tools import ExecuteSQLArgs
from app.prompts.text_to_sql_agent import get_text_to_sql_prompt
from app.tools.db_tools import EXECUTE_SQL_TOOL
from app.models.chat import ChatTurn


class TextToSQLAgent:
    def __init__(self, client: AsyncOpenAI, model: str, sql_executor: SQLExecutor, schema_context: str, max_tool_calls: int = 3):
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

        for _ in range(self.max_tool_calls):
            completion = await self.client.chat.completions.parse(
                model=self.model,
                messages=messages,
                tools=[EXECUTE_SQL_TOOL],
                tool_choice="auto",
            )

            message = completion.choices[0].message
            messages.append(message)

            tool_calls = message.tool_calls or []

            if not tool_calls:
                return message.content or ""

            for tool_call in tool_calls:
                tool_results = await self.execute_tool_call(tool_call)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_results,
                })
        
        raise RuntimeError("Agent exceeded the maximum number of tool calls")
    
    async def execute_tool_call(self, tool_call):
        if tool_call.function.name != "execute_sql":
            raise ValueError(f"Unsupported tool: {tool_call.function.name}")
        
        args = tool_call.function.parsed_arguments

        if not isinstance(args, ExecuteSQLArgs):
            raise TypeError("invalid execute_sql tool arguments.")
        
        result = await self.sql_executor.execute(args.sql_query)

        return result.model_dump_json()
