from app.config import Settings
from psycopg import AsyncConnection, sql


async def read_only_role_exists(settings: Settings):
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
                    FROM pg_roles
                    WHERE rolname = %s
                )
                """,
                (settings.postgres_read_only_user,),
            )

            result = await cursor.fetchone()
    
    return bool(result and result[0])

async def ensure_read_only_role(settings: Settings):
    role_exists = await read_only_role_exists(settings=settings)

    async with await AsyncConnection.connect(
        settings.admin_database_uri,
        autocommit=True,
        connect_timeout=settings.postgres_connect_timeout_seconds,
    ) as connection:
        if role_exists:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    sql.SQL(
                        """
                        ALTER ROLE {}
                        WITH
                            LOGIN
                            PASSWORD {}
                            NOSUPERUSER
                            NOCREATEDB
                            NOCREATEROLE
                            NOREPLICATION
                            NOBYPASSRLS
                    """
                    ).format(
                        sql.Identifier(settings.postgres_read_only_user),
                        sql.Literal(settings.postgres_read_only_password.get_secret_value()),
                    )
                )

                return False
        
        await connection.execute(
            sql.SQL(
                """
                CREATE ROLE {}
                WITH
                    LOGIN
                    PASSWORD {}
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                    NOREPLICATION
                    NOBYPASSRLS
            """
            ).format(
                sql.Identifier(settings.postgres_read_only_user),
                sql.Literal(settings.postgres_read_only_password.get_secret_value()),
            )
        )

    return True

async def grant_read_only_permissions(settings: Settings):
    async with await AsyncConnection.connect(
        settings.target_admin_database_url,
        autocommit=True,
        connect_timeout=settings.postgres_connect_timeout_seconds,
    ) as connection:
        role = sql.Identifier(settings.postgres_read_only_user)
        database = sql.Identifier(settings.postgres_database)

        statements = [
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                database,
                role,
            ),
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role),
            sql.SQL(
                "GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}"
            ).format(role),
            sql.SQL(
                "GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO {}"
            ).format(role),
        ]

        for statement in statements:
            await connection.execute(statement)

async def grant_default_read_only_permissions(
    settings: Settings,
):
    async with await AsyncConnection.connect(
        settings.target_admin_database_url,
        autocommit=True,
        connect_timeout=settings.postgres_connect_timeout_seconds,
    ) as connection:
        role = sql.Identifier(settings.postgres_read_only_user)

        await connection.execute(
            sql.SQL(
                """
                ALTER DEFAULT PRIVILEGES
                IN SCHEMA public
                GRANT SELECT ON TABLES TO {}
                """
            ).format(role)
        )

        await connection.execute(
            sql.SQL(
                """
                ALTER DEFAULT PRIVILEGES
                IN SCHEMA public
                GRANT SELECT ON SEQUENCES TO {}
                """
            ).format(role)
        )

async def provision_read_only_role(settings: Settings) -> bool:
    created = await ensure_read_only_role(settings)
    await grant_read_only_permissions(settings)
    await grant_default_read_only_permissions(settings)

    return created