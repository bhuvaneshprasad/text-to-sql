from app.config import Settings
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

def create_read_only_pool(settings: Settings):
    return AsyncConnectionPool(
        conninfo=settings.read_only_database_url,
        min_size=settings.postgres_pool_min_size,
        max_size=settings.postgres_pool_max_size,
        open=False,
        kwargs={
            "autocommit": False,
            "row_factory": dict_row,
            "connect_timeout": settings.postgres_connect_timeout_seconds
        },
    )