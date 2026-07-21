import openai

from app.models.tools import ExecuteSQLArgs, RequestClarificationArgs


EXECUTE_SQL_TOOL = openai.pydantic_function_tool(
    ExecuteSQLArgs,
    name="execute_sql",
    description=(
        "Execute a validated, read-only PostgreSQL query against the provided database."
    ),
)

REQUEST_CLARIFICATION_TOOL = openai.pydantic_function_tool(
    RequestClarificationArgs,
    name="request_clarification",
    description=(
        "Ask the user ONE clarifying question instead of querying, when the request "
        "is vague, ambiguous, or incomplete and the conversation does not resolve it "
        "(e.g. a ranking with no stated metric, or a missing filter/timeframe/entity). "
        "Call this instead of execute_sql; do not guess and do not query in the same turn."
    ),
)