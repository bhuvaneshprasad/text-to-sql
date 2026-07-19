from dataclasses import dataclass
from typing import Any
from pydantic import BaseModel
from sqlglot import exp

@dataclass(frozen=True)
class ValidatedSQL:
    expression: exp.Query

@dataclass(frozen=True)
class PreparedQueries:
    count_query: str
    data_query: str
    requested_limit: int | None
    applied_limit: int
    offset: int

class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]

    total_count: int
    row_count: int

    requested_limit: int | None
    applied_limit: int
    offset: int

    truncated: bool
    has_more: bool