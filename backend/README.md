# ThesisLens Backend

FastAPI service. All commands run from the `backend/` folder.

## Setup

```bash
uv sync                  # install dependencies into .venv
```

Create `backend/.env` with the keys listed in `app/config.py` (Supabase, `DATABASE_URL`, OpenAI, `ALLOWED_ORIGINS`). The app will not start if a required key is missing.

## Run

```bash
uv run uvicorn app.main:app --reload
```

- Health check: http://localhost:8000/health
- API docs: http://localhost:8000/docs

## Common tasks

```bash
uv add <package>                 # add a runtime dependency
uv add --dev <package>           # add a dev dependency
uv run pytest -m "not integration"   # fast tests
uv run ruff check . && uv run ruff format .   # lint + format
uv run alembic upgrade head      # apply database migrations
```

## Layout

- `app/main.py` — FastAPI app, CORS, routes
- `app/config.py` — settings; import with `from app.config import settings`
- `tests/` — pytest tests
