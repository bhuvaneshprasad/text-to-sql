from pydantic import BaseModel, Field


class ExecuteSQLArgs(BaseModel):
    sql_query: str = Field(
        description=(
            "A single read-only PostgreSQL SELECT query or "
            "read-only WITH query."
        )
    )