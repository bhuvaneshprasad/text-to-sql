from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg_pool import AsyncConnectionPool

from app.database.validator import prepare_queries, validate_sql
from app.models.database import QueryResult
from app.models.exceptions import SQLExecutionError


class SQLExecutor:
    def __init__(self, pool: AsyncConnectionPool, max_rows: int = 100, statement_timeout_ms: int = 10000):
        if max_rows <= 0:
            raise ValueError("max_rows must be greater than zero.")

        if statement_timeout_ms <= 0:
            raise ValueError(
                "statement_timeout_ms must be greater than zero."
            )

        self._pool = pool
        self._max_rows = max_rows
        self._statement_timeout_ms = statement_timeout_ms

    async def execute(self, query: str):
        validated = validate_sql(query)

        prepared = prepare_queries(
            validated,
            max_rows=self._max_rows,
        )

        try:
            async with self._pool.connection() as connection:
                async with connection.transaction():
                    await connection.execute("SET TRANSACTION READ ONLY")

                    await connection.execute(
                        "SELECT set_config('statement_timeout', %s, true)",
                        (str(self._statement_timeout_ms),),
                    )

                    total_count = await self._fetch_total_count(
                        connection,
                        prepared.count_query,
                    )

                    columns, rows = await self._fetch_rows(
                        connection,
                        prepared.data_query,
                    )

        except Exception as exc:
            raise SQLExecutionError(f"Failed to execute SQL query: {exc}") from exc

        serialized_rows = [
            {
                key: serialize_value(value)
                for key, value in row.items()
            }
            for row in rows
        ]

        row_count = len(serialized_rows)

        return QueryResult(
            columns=columns,
            rows=serialized_rows,
            total_count=total_count,
            row_count=row_count,
            requested_limit=prepared.requested_limit,
            applied_limit=prepared.applied_limit,
            offset=prepared.offset,
            truncated=row_count < total_count,
            has_more=(
                prepared.offset + row_count
                < total_count
            ),
        )

    async def _fetch_total_count(self, connection: Any, query: str):
        async with connection.cursor() as cursor:
            await cursor.execute(query)
            row = await cursor.fetchone()

        return int(row["total_count"]) if row else 0

    async def _fetch_rows(self, connection: Any, query: str):
        async with connection.cursor() as cursor:
            await cursor.execute(query)

            columns = [
                column.name
                for column in cursor.description or []
            ]

            rows = await cursor.fetchall()

        return columns, list(rows)


def serialize_value(value: Any):
    if value is None:
        return None

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, bytes):
        return value.hex()

    if isinstance(value, tuple):
        return [serialize_value(item) for item in value]

    if isinstance(value, list):
        return [serialize_value(item) for item in value]

    if isinstance(value, dict):
        return {
            str(key): serialize_value(item)
            for key, item in value.items()
        }

    return value