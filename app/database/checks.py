from app.config import Settings
from psycopg import AsyncConnection, sql
from psycopg.errors import DuplicateDatabase

async def database_exists(settings: Settings):
    async with await AsyncConnection.connect(
        settings.admin_database_uri,
        autocommit=True,
        connect_timeout=settings.postgres_connect_timeout_seconds,
    ) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_database
                    WHERE datname=%s)
                """,
                (settings.postgres_database,),
            )

            result = await cursor.fetchone()
    
    return bool(result and result[0])

async def create_database(settings: Settings):
    try:
        async with await AsyncConnection.connect(
            settings.admin_database_uri,
            autocommit=True,
            connect_timeout=settings.postgres_connect_timeout_seconds,
        ) as connection:
            await connection.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(settings.postgres_database)
                )
            )
    except DuplicateDatabase:
        return

async def ensure_database_exists(settings: Settings):
    if await database_exists(settings):
        return False

    await create_database(settings)
    return True

async def get_database_tables(settings: Settings):
    async with await AsyncConnection.connect(
        settings.target_admin_database_url,
        connect_timeout=settings.postgres_connect_timeout_seconds,
    ) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                """
            )

            rows = await cursor.fetchall()

        return {row[0] for row in rows}

async def database_has_tables(settings: Settings):
    tables = await get_database_tables(settings)
    return bool(tables)

