import asyncio

from app.config import get_settings
from .database.checks import ensure_database_exists


async def bootstrap():
    settings = get_settings()

    created = await ensure_database_exists(settings=settings)

    if created:
        print(f"Created database: {settings.postgres_database}")
    else:
        print(f"Database already exists: {settings.postgres_database}")

def main():
    asyncio.run(bootstrap())

if __name__ == "__main__":
    main()