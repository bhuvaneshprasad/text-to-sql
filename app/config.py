from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from urllib.parse import quote_plus

class Settings(BaseSettings):
    app_name: str ="Text-to-SQL"
    debug: bool = False

    postgres_host: str
    postgres_port: int = 5432

    postgres_admin_database: str = "postgres"
    postgres_database: str = "querypilot"

    postgres_admin_user: str = "postgres"
    postgres_admin_password: SecretStr

    postgres_read_only_user: str = "querypilot_reader"
    postgres_read_only_password: SecretStr

    postgres_pool_min_size: int = 1
    postgres_pool_max_size: int = 5
    postgres_connect_timeout_seconds: int = 10

    querypilot_seed_base_url: str = (
        "https://raw.githubusercontent.com/QueryPilot/studio/master/seeds/postgres"
    )
    querypilot_seed_cache_dir: Path = Path(".cache/querypilot")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

    def build_postgres_uri(self, user: str, password: SecretStr, database: str):
        encoded_user = quote_plus(user)
        encoded_password = quote_plus(password.get_secret_value())

        return (f"postgresql://{encoded_user}:{encoded_password}@{self.postgres_host}:{self.postgres_port}/{database}")
    
    @property
    def admin_database_uri(self):
        return self.build_postgres_uri(
            user=self.postgres_admin_user,
            password=self.postgres_admin_password,
            database=self.postgres_admin_database
        )
    
    @property
    def target_admin_database_url(self) -> str:
        return self.build_postgres_uri(
            user=self.postgres_admin_user,
            password=self.postgres_admin_password,
            database=self.postgres_database,
        )

    @property
    def readonly_database_url(self) -> str:
        return self.build_postgres_uri(
            user=self.postgres_readonly_user,
            password=self.postgres_readonly_password,
            database=self.postgres_database,
        )

@lru_cache
def get_settings():
    return Settings()