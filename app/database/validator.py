from typing import Literal

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from app.models.database import PreparedQueries, ValidatedSQL
from app.models.exceptions import SQLValidationError


SQL_DIALECT = "postgres"


def validate_sql(query: str):
    if not query.strip():
        raise SQLValidationError("SQL query cannot be empty.")

    try:
        statement = parse_one(query, read=SQL_DIALECT)
    except ParseError as exc:
        raise SQLValidationError(
            f"Invalid PostgreSQL query: {exc}"
        ) from exc

    if not isinstance(statement, exp.Query):
        raise SQLValidationError("Only SELECT queries are allowed.")

    if statement.find(exp.Lock):
        raise SQLValidationError(
            "Row-locking queries are not allowed."
        )

    return ValidatedSQL(expression=statement)


def prepare_queries(validated: ValidatedSQL, max_rows: int):
    if max_rows <= 0:
        raise ValueError("max_rows must be greater than zero.")

    original = validated.expression
    requested_limit = extract_pagination_value(
        original,
        clause="limit",
    )
    offset = extract_pagination_value(
        original,
        clause="offset",
    ) or 0

    applied_limit = min(
        requested_limit or max_rows,
        max_rows,
    )

    count_source = original.copy()
    count_source.set("limit", None)
    count_source.set("offset", None)
    count_source.set("order", None)

    count_expression = (
        exp.select(
            exp.alias_(
                exp.Count(this=exp.Star()),
                "total_count",
            )
        )
        .from_(count_source.subquery("query_result"))
    )

    data_expression = original.copy()
    data_expression.limit(applied_limit, copy=False)

    return PreparedQueries(
        count_query=to_postgres_sql(count_expression),
        data_query=to_postgres_sql(data_expression),
        requested_limit=requested_limit,
        applied_limit=applied_limit,
        offset=offset,
    )


def extract_pagination_value(expression: exp.Query, clause: Literal["limit", "offset"]):
    pagination = expression.args.get(clause)

    if pagination is None:
        return None

    value_expression = pagination.expression
    label = clause.upper()

    if (
        not isinstance(value_expression, exp.Literal)
        or not value_expression.is_int
    ):
        raise SQLValidationError(
            f"{label} must be an integer literal."
        )

    value = int(value_expression.this)
    minimum = 1 if clause == "limit" else 0

    if value < minimum:
        requirement = (
            "greater than zero"
            if clause == "limit"
            else "non-negative"
        )
        raise SQLValidationError(
            f"{label} must be {requirement}."
        )

    return value


def to_postgres_sql(expression: exp.Expression):
    return expression.sql(
        dialect=SQL_DIALECT,
        pretty=False,
    )