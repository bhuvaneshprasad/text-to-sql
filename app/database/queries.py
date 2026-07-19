from collections.abc import Mapping, Sequence
from typing import Any

from psycopg import sql
from psycopg_pool import AsyncConnectionPool


QueryParameters = Sequence[Any] | Mapping[str, Any] | None

async def fetch_all(
    pool: AsyncConnectionPool,
    query: str | sql.Composable,
    params: QueryParameters = None,
):
    async with pool.connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(query, params)
            rows = await cursor.fetchall()

    return list(rows)


async def fetch_one(
    pool: AsyncConnectionPool,
    query: str | sql.Composable,
    params: QueryParameters = None,
):
    async with pool.connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(query, params)
            return await cursor.fetchone()