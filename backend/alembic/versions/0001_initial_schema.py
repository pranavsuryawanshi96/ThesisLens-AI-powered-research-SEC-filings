"""initial schema: users, documents, chunks, chats, citations, RLS

Revision ID: 0001
Revises:
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "users",
    "source_documents",
    "document_chunks",
    "chat_threads",
    "chat_messages",
    "message_citations",
)


def timestamp(name: str, default: str = "now()") -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text(default), nullable=False)


def uuid_pk() -> sa.Column:
    return sa.Column(
        "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
    )


def upgrade() -> None:
    # Supabase convention: extensions live in the `extensions` schema, which is on
    # the default search_path, so `vector` and `vector_cosine_ops` resolve unqualified.
    op.execute("create extension if not exists vector with schema extensions")

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        timestamp("updated_at"),
        timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    # auth.users is Supabase-owned, so this FK is not modelled in SQLAlchemy metadata.
    op.execute(
        "alter table public.users add constraint fk_users_id_auth_users "
        "foreign key (id) references auth.users (id) on delete cascade"
    )

    op.create_table(
        "source_documents",
        uuid_pk(),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("cik", sa.Text(), nullable=False),
        sa.Column("filing_type", sa.Text(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_source_documents"),
        sa.UniqueConstraint("accession_number", name="uq_source_documents_accession_number"),
    )
    op.create_index(
        "ix_source_documents_ticker_fiscal_year",
        "source_documents",
        ["ticker", "fiscal_year"],
    )

    op.create_table(
        "document_chunks",
        uuid_pk(),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(1536), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["source_documents.id"],
            name="fk_document_chunks_document_id_source_documents",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_id_chunk_index"
        ),
    )
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_document_chunks_search_vector_gin",
        "document_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )

    op.create_table(
        "chat_threads",
        uuid_pk(),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        timestamp("updated_at"),
        timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_chat_threads"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_chat_threads_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_chat_threads_user_id_updated_at",
        "chat_threads",
        ["user_id", sa.text("updated_at DESC")],
    )

    op.create_table(
        "chat_messages",
        uuid_pk(),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "parts",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("usage", postgresql.JSONB(), nullable=True),
        timestamp("created_at", default="clock_timestamp()"),
        sa.PrimaryKeyConstraint("id", name="pk_chat_messages"),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["chat_threads.id"],
            name="fk_chat_messages_thread_id_chat_threads",
            ondelete="CASCADE",
        ),
        # Short name: the metadata naming convention adds the ck_chat_messages_ prefix.
        sa.CheckConstraint("role IN ('user', 'assistant', 'system')", name="role"),
    )
    op.create_index(
        "ix_chat_messages_thread_id_created_at", "chat_messages", ["thread_id", "created_at"]
    )

    op.create_table(
        "message_citations",
        uuid_pk(),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("citation_index", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_message_citations"),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            name="fk_message_citations_message_id_chat_messages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name="fk_message_citations_chunk_id_document_chunks",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "message_id",
            "citation_index",
            name="uq_message_citations_message_id_citation_index",
        ),
    )
    op.create_index("ix_message_citations_chunk_id", "message_citations", ["chunk_id"])

    create_user_sync_trigger()
    enable_row_level_security()


def create_user_sync_trigger() -> None:
    # Every Supabase sign-up gets a public.users row, so chat_threads.user_id
    # always has a target without the backend having to upsert on each request.
    op.execute(
        """
        create function public.handle_new_auth_user() returns trigger
        language plpgsql security definer set search_path = ''
        as $$
        begin
          insert into public.users (id, email) values (new.id, new.email);
          return new;
        end;
        $$
        """
    )
    op.execute(
        "create trigger on_auth_user_created after insert on auth.users "
        "for each row execute function public.handle_new_auth_user()"
    )
    # Accounts created before this migration (e.g. during auth testing).
    op.execute(
        "insert into public.users (id, email) select id, email from auth.users "
        "where email is not null on conflict (id) do nothing"
    )


def enable_row_level_security() -> None:
    # The browser holds the anon key + user JWT and can call PostgREST directly,
    # so policies define what a signed-in user may do *without* the backend.
    # Messages and citations are read-only here: only the backend (service role,
    # which bypasses RLS) may write them, otherwise a user could forge grounded answers.
    for table in TABLES:
        op.execute(f"alter table public.{table} enable row level security")

    uid = "(select auth.uid())"  # wrapped in select so Postgres evaluates it once per query
    owns_thread = f"exists (select 1 from public.chat_threads t where t.id = thread_id and t.user_id = {uid})"

    op.execute(
        f"create policy users_select_own on public.users for select to authenticated using (id = {uid})"
    )

    # The filing corpus is shared by every analyst; writes come only from ingestion.
    op.execute(
        "create policy source_documents_select on public.source_documents "
        "for select to authenticated using (true)"
    )
    op.execute(
        "create policy document_chunks_select on public.document_chunks "
        "for select to authenticated using (true)"
    )

    op.execute(
        f"create policy chat_threads_all_own on public.chat_threads for all to authenticated "
        f"using (user_id = {uid}) with check (user_id = {uid})"
    )
    op.execute(
        f"create policy chat_messages_select_own on public.chat_messages "
        f"for select to authenticated using ({owns_thread})"
    )
    op.execute(
        f"""
        create policy message_citations_select_own on public.message_citations
        for select to authenticated using (
          exists (
            select 1 from public.chat_messages m
            join public.chat_threads t on t.id = m.thread_id
            where m.id = message_id and t.user_id = {uid}
          )
        )
        """
    )


def downgrade() -> None:
    op.execute("drop trigger if exists on_auth_user_created on auth.users")
    op.execute("drop function if exists public.handle_new_auth_user()")
    # Policies and indexes are dropped with their tables. The vector extension
    # is left installed: other schemas may use it, and it holds no app data.
    for table in reversed(TABLES):
        op.drop_table(table)
