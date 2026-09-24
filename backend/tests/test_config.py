import pytest
from pydantic import ValidationError

from app.config import Settings

REQUIRED = {
    "supabase_url": "https://abc.supabase.co",
    "supabase_anon_key": "anon",
    "supabase_service_role_key": "service",
    "database_url": "postgresql://postgres:pw@db.abc.supabase.co:5432/postgres",
    "openai_api_key": "sk-test",
}


def test_cors_origins_parses_comma_separated_list():
    s = Settings(_env_file=None, **REQUIRED, allowed_origins="http://localhost:5173, https://app.example.com,")
    assert s.cors_origins == ["http://localhost:5173", "https://app.example.com"]


def test_defaults():
    s = Settings(_env_file=None, **REQUIRED)
    assert s.openai_embedding_model == "text-embedding-3-small"
    assert s.openai_embedding_dimensions == 1536
    assert s.cors_origins == ["http://localhost:5173"]


def test_missing_required_field_fails(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fields = {k: v for k, v in REQUIRED.items() if k != "openai_api_key"}
    with pytest.raises(ValidationError, match="openai_api_key"):
        Settings(_env_file=None, **fields)
