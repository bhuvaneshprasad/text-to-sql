from app.config import Settings
from app.database.constants import (
    CATALOGUE_RELATIONS,
    CATALOGUE_SCHEMA,
    TEXT_TO_SQL_RELATIONS,
)
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
        role = sql.Identifier(settings.postgres_read_only_user)
        password = sql.Literal(
            settings.postgres_read_only_password.get_secret_value()
        )

        if role_exists:
            await connection.execute(
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
                ).format(role, password)
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
            ).format(role, password)
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
        catalogue_schema = sql.Identifier(CATALOGUE_SCHEMA)

        allowed_relations = sql.SQL(", ").join(
            sql.Identifier("public", relation_name)
            for relation_name in TEXT_TO_SQL_RELATIONS
        )

        catalogue_relations = sql.SQL(", ").join(
            sql.Identifier(CATALOGUE_SCHEMA, relation_name)
            for relation_name in CATALOGUE_RELATIONS
        )

        statements = [
            # Allow the role to connect to the target database.
            sql.SQL(
                "GRANT CONNECT ON DATABASE {} TO {}"
            ).format(database, role),

            # Allow object lookup inside the public schema.
            sql.SQL(
                "GRANT USAGE ON SCHEMA public TO {}"
            ).format(role),

            # Allow object lookup inside the catalogue schema.
            sql.SQL(
                "GRANT USAGE ON SCHEMA {} TO {}"
            ).format(catalogue_schema, role),

            # Remove permissions previously granted by the old bootstrap.
            sql.SQL(
                """
                REVOKE ALL PRIVILEGES
                ON ALL TABLES IN SCHEMA public
                FROM {}
                """
            ).format(role),

            sql.SQL(
                """
                REVOKE ALL PRIVILEGES
                ON ALL SEQUENCES IN SCHEMA public
                FROM {}
                """
            ).format(role),

            # Grant SELECT only on approved business relations.
            sql.SQL(
                """
                GRANT SELECT
                ON TABLE {}
                TO {}
                """
            ).format(
                allowed_relations,
                role,
            ),

            # Grant read-only access to the Text-to-SQL catalogue tables.
            sql.SQL(
                """
                GRANT SELECT
                ON TABLE {}
                TO {}
                """
            ).format(
                catalogue_relations,
                role,
            ),
        ]

        for statement in statements:
            await connection.execute(statement)


async def revoke_default_read_only_permissions(settings: Settings):
    async with await AsyncConnection.connect(
        settings.target_admin_database_url,
        autocommit=True,
        connect_timeout=settings.postgres_connect_timeout_seconds,
    ) as connection:
        role = sql.Identifier(settings.postgres_read_only_user)

        # Remove the broad defaults configured by the previous bootstrap.
        await connection.execute(
            sql.SQL(
                """
                ALTER DEFAULT PRIVILEGES
                IN SCHEMA public
                REVOKE ALL PRIVILEGES ON TABLES FROM {}
                """
            ).format(role)
        )

        await connection.execute(
            sql.SQL(
                """
                ALTER DEFAULT PRIVILEGES
                IN SCHEMA public
                REVOKE ALL PRIVILEGES ON SEQUENCES FROM {}
                """
            ).format(role)
        )


async def provision_read_only_role(settings: Settings):
    created = await ensure_read_only_role(settings)

    await grant_read_only_permissions(settings)
    await revoke_default_read_only_permissions(settings)

    return created