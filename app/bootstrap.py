import asyncio
import logging

from app.config import get_settings
from .database.checks import ensure_database_exists, get_database_tables
from app.database.seed import download_seed_files, seed_database, get_local_sql_files, execute_sql_file
from app.database.roles import provision_read_only_role
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)


async def bootstrap():
    settings = get_settings()

    created = await ensure_database_exists(settings=settings)

    if created:
        logger.info("Created database: %s", settings.postgres_database)
    else:
        logger.info("Database already exists: %s", settings.postgres_database)

    tables = await get_database_tables(settings)

    if tables:
        logger.info("Dataset already present: %d tables found", len(tables))
    else:
        logger.info("No dataset found; downloading and seeding")
        seed_files = download_seed_files(settings)

        await seed_database(
            settings=settings,
            seed_files=seed_files,
        )

        tables = await get_database_tables(settings)

        if not tables:
            raise RuntimeError(
                "Seed scripts completed but no tables were found"
            )

        logger.info("Dataset ingestion completed: %d tables found", len(tables))

    for sql_file in get_local_sql_files():
        logger.info("Applying descriptions from: %s", sql_file.name)
        await execute_sql_file(settings, sql_file)

    role_created = await provision_read_only_role(settings)

    if role_created:
        logger.info("Created read-only role: %s", settings.postgres_read_only_user)
    else:
        logger.info(
            "Read-only role already exists and permissions were refreshed: %s",
            settings.postgres_read_only_user,
        )

def main():
    settings = get_settings()
    configure_logging(settings.log_level)
    asyncio.run(bootstrap())

if __name__ == "__main__":
    main()