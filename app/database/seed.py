import asyncio
import os
from pathlib import Path
from urllib.request import urlopen

from app.config import Settings

SEED_FILES = [
    "01_schema.sql",
    "02_seed_data.sql",
]

def download_file(url: str, destination: Path):
    try:
        with urlopen(url, timeout=60) as response:
            content = response.read()
    except Exception as e:
        raise RuntimeError(f"Failed to download {url}: {e}")
    
    if not content:
        raise RuntimeError(f"Downloaded an empty file from {url}")
    
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)

def download_seed_files(settings: Settings):
    cache_dir = settings.querypilot_seed_cache_dir
    downloaded_files: list[Path] = []

    for filename in SEED_FILES:
        destination = cache_dir / filename

        if destination.exists():
            downloaded_files.append(destination)
            continue

        url = f"{settings.querypilot_seed_base_url.rstrip('/')}/{filename}"

        download_file(
            url=url,
            destination=destination,
        )

        downloaded_files.append(destination)
    
    return downloaded_files

async def execute_sql_file(settings: Settings,sql_file: Path):
    if not sql_file.is_file():
        raise FileNotFoundError(f"SQL file not found: {sql_file}")

    environment = os.environ.copy()
    environment["PGPASSWORD"] = (
        settings.postgres_admin_password.get_secret_value()
    )

    process = await asyncio.create_subprocess_exec(
        "psql",
        "--host",
        settings.postgres_host,
        "--port",
        str(settings.postgres_port),
        "--username",
        settings.postgres_admin_user,
        "--dbname",
        settings.postgres_database,
        "--set",
        "ON_ERROR_STOP=1",
        "--file",
        str(sql_file),
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"Failed to execute {sql_file.name}:\n{error}"
        )

async def seed_database(settings: Settings, seed_files: list[Path]) -> None:
    for seed_file in seed_files:
        print(f"Executing: {seed_file.name}")
        await execute_sql_file(settings, seed_file)