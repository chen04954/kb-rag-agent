from functools import cached_property
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", ".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    model_provider: str = "openai"
    model_names: list[str] = Field(
        default_factory=lambda: ["gpt-4o-mini", "gpt-4o-mini"]
    )
    model_base_url: str = ""
    embeddings_model_name: str = "text-embedding-3-small"
    embeddings_base_url: str = ""
    tavily_api_key: str = ""

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expiry_mins: int = 30
    refresh_token_expiry_days: int = 7

    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_database: str = "kb_rag_agent"
    pgvector_collection_name: str = "kb_rag_agent_chunks"

    backend_base_url: str = "http://127.0.0.1:8000/api/v1"
    testing: bool = False
    reset_schema: bool = False

    def _postgres_url(self, driver: str) -> str:
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        credentials = f"{user}:{password}" if password else user
        return (
            f"postgresql+{driver}://{credentials}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_database}"
        )

    @cached_property
    def database_url(self) -> str:
        return self._postgres_url("asyncpg")

    @cached_property
    def psycopg_url(self) -> str:
        return self._postgres_url("psycopg")

    @cached_property
    def checkpointer_url(self) -> str:
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        credentials = f"{user}:{password}" if password else user
        return (
            f"postgresql://{credentials}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_database}"
        )


settings = Settings()
