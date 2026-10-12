import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.auth.dependencies import CurrentUser, get_current_user, get_user_client
from app.database import chats
from app.database.supabase import get_service_client
from app.main import app

USER = CurrentUser(id=uuid4(), email="analyst@example.com", access_token="t")
OTHER_USER_ID = uuid4()
NOW = "2026-09-27T10:00:00+00:00"


def thread_row(owner: UUID, title: str = chats.DEFAULT_THREAD_TITLE) -> dict:
    return {"id": str(uuid4()), "user_id": str(owner), "title": title, "created_at": NOW, "updated_at": NOW}


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_user_client] = lambda: "user-client"
    app.dependency_overrides[get_service_client] = lambda: "service-client"
    app.dependency_overrides[chat_api.get_agent] = lambda: "agent"
    app.dependency_overrides[chat_api.get_retriever] = lambda: "retriever"
    # Not entered as a context manager: the lifespan would build a real Supabase client.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def threads(monkeypatch):
    """In-memory stand-in for the chats persistence functions."""
    store: dict[str, dict] = {}
    saved: list[dict] = []

    async def get_thread(_client, thread_id):
        return store.get(str(thread_id))

    async def save_turn(db_client, thread_id, messages, title):
        saved.append({"client": db_client, "thread_id": thread_id, "messages": messages, "title": title})

    monkeypatch.setattr(chats, "get_thread", get_thread)
    monkeypatch.setattr(chats, "save_turn", save_turn)

    def add(row: dict) -> dict:
        store[row["id"]] = row
        return row

    add.saved = saved
    return add


def stream_body(thread_id: str, text: str = "How did Apple's revenue mix change?") -> dict:
    return {
        "id": thread_id,
        "messages": [{"id": "u1", "role": "user", "parts": [{"type": "text", "text": text}]}],
        "trigger": "submit-message",
    }


def parse_events(body: str) -> list:
    frames = [frame.removeprefix("data: ") for frame in body.split("\n\n") if frame]
    return [frame if frame == "[DONE]" else json.loads(frame) for frame in frames]


def test_list_threads_returns_camel_case_threads(client, monkeypatch):
    row = thread_row(USER.id)
    calls = []

    async def list_threads(db_client, user_id):
        calls.append((db_client, user_id))
        return [row]

    monkeypatch.setattr(chats, "list_threads", list_threads)

    response = client.get("/chat/threads")

    assert response.status_code == 200
    serialized_now = "2026-09-27T10:00:00Z"
    assert response.json() == [
        {"id": row["id"], "title": row["title"], "createdAt": serialized_now, "updatedAt": serialized_now}
    ]
    assert calls == [("user-client", USER.id)]


def test_create_thread_defaults_title(client, monkeypatch):
    created = []

    async def create_thread(_client, user_id, title):
        created.append((user_id, title))
        return thread_row(user_id, title)

    monkeypatch.setattr(chats, "create_thread", create_thread)

    assert client.post("/chat/threads").status_code == 201
    assert client.post("/chat/threads", json={"title": "Azure capacity"}).json()["title"] == "Azure capacity"
    assert created == [(USER.id, chats.DEFAULT_THREAD_TITLE), (USER.id, "Azure capacity")]


def test_message_history_returns_ui_messages(client, threads, monkeypatch):
    thread = threads(thread_row(USER.id))
    message_id = uuid4()
    parts = [{"type": "text", "text": "hi"}]

    async def list_messages(db_client, thread_id):
        assert db_client == "user-client"
        return [{"id": str(message_id), "role": "user", "parts": parts}]

    monkeypatch.setattr(chats, "list_messages", list_messages)

    response = client.get(f"/chat/threads/{thread['id']}/messages")

    assert response.status_code == 200
    assert response.json() == [{"id": str(message_id), "role": "user", "parts": parts}]


@pytest.mark.parametrize("path", ["messages", "stream"])
def test_other_users_thread_is_forbidden(client, threads, path):
    thread = threads(thread_row(OTHER_USER_ID))
    if path == "messages":
        response = client.get(f"/chat/threads/{thread['id']}/messages")
    else:
        response = client.post("/chat/stream", json=stream_body(thread["id"]))

    assert response.status_code == 403
    assert threads.saved == []


@pytest.mark.parametrize("path", ["messages", "stream"])
def test_missing_thread_is_not_found(client, threads, path):
    missing = str(uuid4())
    if path == "messages":
        response = client.get(f"/chat/threads/{missing}/messages")
    else:
        response = client.post("/chat/stream", json=stream_body(missing))

    assert response.status_code == 404


def test_stream_rejects_turn_without_user_message(client, threads):
    thread = threads(thread_row(USER.id))
    body = stream_body(thread["id"])
    body["messages"][0]["role"] = "assistant"

    assert client.post("/chat/stream", json=body).status_code == 422


def test_stream_hands_the_turn_to_the_orchestrator_as_an_ai_sdk_stream(client, threads, monkeypatch):
    thread = threads(thread_row(USER.id))
    question = "How did Apple's revenue mix change?"
    calls = []

    async def fake_turn(service, agent, retriever, user_id, owned_thread, user_message):
        calls.append((service, agent, retriever, user_id, owned_thread, user_message))
        yield 'data: {"type": "start", "messageId": "m1"}\n\n'
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(chat_api, "stream_grounded_turn", fake_turn)

    response = client.post("/chat/stream", json=stream_body(thread["id"], question))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert parse_events(response.text) == [{"type": "start", "messageId": "m1"}, "[DONE]"]
    [(service, agent, retriever, user_id, owned_thread, user_message)] = calls
    assert (service, agent, retriever, user_id) == ("service-client", "agent", "retriever", USER.id)
    assert UUID(owned_thread["id"]) == UUID(thread["id"])
    assert user_message.parts == [{"type": "text", "text": question}]
