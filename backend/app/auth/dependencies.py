"""Authentication for route handlers.

Every protected route depends on `get_current_user`. The token is verified by asking
Supabase Auth, not by decoding the JWT locally: it is one call, it honours revoked
sessions and deleted users, and there is no signing secret or key rotation to manage.
"""

from dataclasses import dataclass, field
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import AsyncClient
from supabase_auth.errors import AuthApiError

from app.database.supabase import create_user_client, get_service_client

# auto_error=False so a missing header gets our 401, not FastAPI's default 403.
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str | None
    # Kept so later code can build a user-scoped (RLS) client; excluded from repr/logs.
    access_token: str = field(repr=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    supabase: Annotated[AsyncClient, Depends(get_service_client)],
) -> CurrentUser:
    if credentials is None:
        raise _unauthorized("Missing bearer token")

    token = credentials.credentials
    try:
        response = await supabase.auth.get_user(token)
    except AuthApiError as exc:
        # 4xx means the token is bad or expired; a Supabase outage is not the caller's fault.
        if exc.status >= 500:
            raise
        raise _unauthorized("Invalid or expired token") from exc

    if response is None or response.user is None:
        raise _unauthorized("Invalid or expired token")

    user = response.user
    return CurrentUser(id=UUID(user.id), email=user.email, access_token=token)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def get_user_client(user: CurrentUserDep) -> AsyncClient:
    """FastAPI dependency: a Supabase client acting as the current user (RLS enforced)."""
    return await create_user_client(user.access_token)


UserClientDep = Annotated[AsyncClient, Depends(get_user_client)]
