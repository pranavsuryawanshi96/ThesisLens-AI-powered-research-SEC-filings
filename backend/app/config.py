"""Backend settings — the single source of truth for environment config.

Import `settings` from here; never read `os.environ` or call `load_dotenv` elsewhere.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Validation errors would otherwise echo secret values into startup logs.
        hide_input_in_errors=True,
    )

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str

    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536

    # Comma-separated in .env; use `cors_origins` for the parsed list.
    allowed_origins: str = "http://localhost:5173"

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]

    @field_validator("database_url")
    @classmethod
    def _reject_transaction_pooler(cls, value: str) -> str:
        url = urlsplit(value)
        if url.scheme not in ("postgresql", "postgres"):
            raise ValueError("DATABASE_URL must be a postgresql:// connection string")
        # Supavisor transaction mode (port 6543) breaks Alembic; direct or session mode (5432) is fine.
        if url.hostname and url.hostname.endswith("pooler.supabase.com") and url.port == 6543:
            raise ValueError(
                "DATABASE_URL uses the Supabase transaction pooler (port 6543); "
                "use the direct connection or the session pooler on port 5432"
            )
        return value


settings = Settings()

# The OpenAI SDK and PydanticAI read OPENAI_API_KEY from os.environ directly,
# and pydantic-settings does not export .env values, so mirror it here.
os.environ["OPENAI_API_KEY"] = settings.openai_api_key