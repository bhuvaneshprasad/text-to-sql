import openai

from app.models.tools import ExecuteSQLArgs


EXECUTE_SQL_TOOL = openai.pydantic_function_tool(
    ExecuteSQLArgs,
    name="execute_sql",
    description=(
        "Execute a validated, read-only PostgreSQL query against the provided database."
    ),
)