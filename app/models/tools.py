from pydantic import BaseModel, Field


class ExecuteSQLArgs(BaseModel):
    sql_query: str = Field(
        description=(
            "A single read-only PostgreSQL SELECT query or "
            "read-only WITH query."
        )
    )


class RequestClarificationArgs(BaseModel):
    question: str = Field(
        description=(
            "One concise clarifying question to ask the user when the request is "
            "vague, ambiguous, or incomplete and the conversation does not resolve "
            "it. Ask only about the detail that blocks a correct query."
        )
    )