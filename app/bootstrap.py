import asyncio

from app.config import get_settings
from .database.checks import ensure_database_exists, get_database_tables
from app.database.seed import download_seed_files, seed_database
from app.database.roles import provision_read_only_role


async def bootstrap():
    settings = get_settings()

    created = await ensure_database_exists(settings=settings)

    if created:
        print(f"Created database: {settings.postgres_database}")
    else:
        print(f"Database already exists: {settings.postgres_database}")
    
    tables = await get_database_tables(settings)

    if tables:
        print(f"Dataset already present: {len(tables)} tables found")
    else:
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

        print(f"Dataset ingestion completed: {len(tables)} tables found")

    role_created = await provision_read_only_role(settings)

    if role_created:
        print(f"Created read-only role: {settings.postgres_read_only_user}")
    else:
        print(f"Read-only role already exists and permissions were refreshed: {settings.postgres_read_only_user}")

def main():
    asyncio.run(bootstrap())

if __name__ == "__main__":
    main()