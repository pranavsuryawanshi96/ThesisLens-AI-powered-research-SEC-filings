"""Chat thread and message persistence through the Supabase client.

Callers choose the client: a user-scoped one where RLS should apply, the service-role
one for the privileged paths (ownership lookups, writing messages).
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from supabase import AsyncClient

DEFAULT_THREAD_TITLE = "New chat"


async def list_threads(client: AsyncClient, user_id: UUID) -> list[dict[str, Any]]:
    response = (
        await client.table("chat_threads")
        .select("id, title, created_at, updated_at")
        .eq("user_id", str(user_id))
        .order("updated_at", desc=True)
        .execute()
    )
    return response.data


async def create_thread(client: AsyncClient, user_id: UUID, title: str) -> dict[str, Any]:
    response = (
        await client.table("chat_threads")
        .insert({"user_id": str(user_id), "title": title})
        .execute()
    )
    return response.data[0]


async def get_thread(client: AsyncClient, thread_id: UUID) -> dict[str, Any] | None:
    response = (
        await client.table("chat_threads")
        .select("id, user_id, title, created_at, updated_at")
        .eq("id", str(thread_id))
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


async def list_messages(client: AsyncClient, thread_id: UUID) -> list[dict[str, Any]]:
    response = (
        await client.table("chat_messages")
        .select("id, role, parts")
        .eq("thread_id", str(thread_id))
        .order("created_at")
        .execute()
    )
    return response.data


async def save_turn(
    client: AsyncClient,
    thread_id: UUID,
    messages: list[dict[str, Any]],
    title: str | None,
) -> None:
    """Insert one turn's messages and mark the thread as recently active."""
    rows = [{**message, "thread_id": str(thread_id)} for message in messages]
    # One multi-row insert, so a turn is never half-saved.
    await client.table("chat_messages").insert(rows).execute()

    # The model's onupdate only fires through the ORM, not through PostgREST.
    thread_update: dict[str, Any] = {"updated_at": datetime.now(UTC).isoformat()}
    if title is not None:
        thread_update["title"] = title
    await client.table("chat_threads").update(thread_update).eq("id", str(thread_id)).execute()
