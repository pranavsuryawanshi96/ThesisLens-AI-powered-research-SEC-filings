from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from supabase import AsyncClient

from app.auth.dependencies import CurrentUser, CurrentUserDep, UserClientDep
from app.chat.messages import ChatStreamRequest, UIMessage
from app.chat.orchestrator import stream_stub_turn
from app.chat.streaming import STREAM_HEADERS
from app.database import chats
from app.database.supabase import get_service_client

router = APIRouter(prefix="/chat", tags=["chat"])

ServiceClientDep = Annotated[AsyncClient, Depends(get_service_client)]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ThreadResponse(CamelModel):
    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class CreateThreadRequest(CamelModel):
    title: str = Field(default=chats.DEFAULT_THREAD_TITLE, min_length=1, max_length=200)


async def get_owned_thread(
    service: AsyncClient, thread_id: UUID, user: CurrentUser
) -> dict[str, Any]:
    # Looked up with the service role: under RLS another user's thread is simply
    # invisible, which could only ever produce a 404, never the 403 we want.
    thread = await chats.get_thread(service, thread_id)
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")
    if UUID(thread["user_id"]) != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Thread belongs to another user")
    return thread


@router.get("/threads")
async def list_threads(user: CurrentUserDep, client: UserClientDep) -> list[ThreadResponse]:
    rows = await chats.list_threads(client, user.id)
    return [ThreadResponse.model_validate(row) for row in rows]


@router.post("/threads", status_code=status.HTTP_201_CREATED)
async def create_thread(
    user: CurrentUserDep, client: UserClientDep, body: CreateThreadRequest | None = None
) -> ThreadResponse:
    title = (body or CreateThreadRequest()).title
    row = await chats.create_thread(client, user.id, title)
    return ThreadResponse.model_validate(row)


@router.get("/threads/{thread_id}/messages")
async def list_messages(
    thread_id: UUID, user: CurrentUserDep, client: UserClientDep, service: ServiceClientDep
) -> list[UIMessage]:
    await get_owned_thread(service, thread_id, user)
    rows = await chats.list_messages(client, thread_id)
    return [UIMessage.model_validate({**row, "id": str(row["id"])}) for row in rows]


@router.post("/stream")
async def stream(
    body: ChatStreamRequest, user: CurrentUserDep, service: ServiceClientDep
) -> StreamingResponse:
    # Checked before streaming starts, so auth and ownership failures are plain HTTP errors.
    thread = await get_owned_thread(service, body.thread_id, user)
    return StreamingResponse(
        stream_stub_turn(service, thread, body.user_message),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )
