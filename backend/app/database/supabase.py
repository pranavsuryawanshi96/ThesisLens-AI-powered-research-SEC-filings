"""Supabase client construction for the backend.

Two kinds of client:

- **User-scoped** — anon key + the caller's access token, so Postgres RLS applies
  exactly as it would for that user. Use this wherever possible.
- **Service-role** — bypasses RLS. Only for privileged writes (ingestion, persisting
  assistant messages/citations); callers must still attach the authenticated `user_id`.

The service-role client is created once at startup and kept on `app.state`;
user-scoped clients are built per request because they carry that request's token.
"""

from fastapi import Request
from supabase import AsyncClient, AsyncClientOptions, acreate_client

from app.config import settings


def _server_options(bearer_token: str) -> AsyncClientOptions:
    # The server never signs anyone in: no session storage, no background refresh.
    # Passing Authorization explicitly also stops the SDK from looking up a stored session.
    return AsyncClientOptions(
        headers={"Authorization": f"Bearer {bearer_token}"},
        auto_refresh_token=False,
        persist_session=False,
    )


async def create_user_client(access_token: str) -> AsyncClient:
    """Client that acts as the user who owns `access_token` (RLS enforced)."""
    return await acreate_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=_server_options(access_token),
    )


async def create_service_client() -> AsyncClient:
    """Client with the service-role key (RLS bypassed). Backend only."""
    return await acreate_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=_server_options(settings.supabase_service_role_key),
    )


def get_service_client(request: Request) -> AsyncClient:
    """FastAPI dependency: the shared service-role client created in the app lifespan."""
    return request.app.state.supabase_service
