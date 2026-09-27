import asyncio
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.database.supabase import (
    create_service_client,
    create_user_client,
    get_service_client,
)


def test_user_client_uses_anon_key_and_user_token():
    client = asyncio.run(create_user_client("user-jwt"))
    assert client.supabase_key == settings.supabase_anon_key
    assert client.options.headers["Authorization"] == "Bearer user-jwt"
    assert client.postgrest.session.headers["Authorization"] == "Bearer user-jwt"
    assert client.postgrest.session.headers["apikey"] == settings.supabase_anon_key


def test_service_client_uses_service_role_key():
    client = asyncio.run(create_service_client())
    key = settings.supabase_service_role_key
    assert client.supabase_key == key
    assert client.postgrest.session.headers["Authorization"] == f"Bearer {key}"


def test_clients_do_not_persist_or_refresh_sessions():
    for client in (
        asyncio.run(create_user_client("t")),
        asyncio.run(create_service_client()),
    ):
        assert client.options.persist_session is False
        assert client.options.auto_refresh_token is False


def test_get_service_client_reads_app_state():
    app = FastAPI()
    sentinel = object()
    app.state.supabase_service = sentinel

    @app.get("/probe")
    async def probe(client: Annotated[object, Depends(get_service_client)]):
        return {"same": client is sentinel}

    assert TestClient(app).get("/probe").json() == {"same": True}
