from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.database.models import Base

TABLES = Base.metadata.tables


def ddl(construct) -> str:
    return str(construct.compile(dialect=postgresql.dialect()))


def test_all_tables_registered():
    assert set(TABLES) == {
        "users",
        "source_documents",
        "document_chunks",
        "chat_threads",
        "chat_messages",
        "message_citations",
    }


def test_every_table_compiles_to_postgres_ddl():
    for table in Base.metadata.sorted_tables:
        ddl(CreateTable(table))
        for index in table.indexes:
            ddl(CreateIndex(index))


def test_chunk_embedding_and_generated_search_vector():
    sql = ddl(CreateTable(TABLES["document_chunks"]))
    assert "embedding VECTOR(1536)" in sql
    assert "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED" in sql


def test_chunk_search_indexes():
    indexes = {i.name: ddl(CreateIndex(i)) for i in TABLES["document_chunks"].indexes}
    assert "USING hnsw (embedding vector_cosine_ops)" in indexes["ix_document_chunks_embedding_hnsw"]
    assert "USING gin (search_vector)" in indexes["ix_document_chunks_search_vector_gin"]


def test_deleting_a_cited_chunk_is_blocked():
    (fk,) = [fk for fk in TABLES["message_citations"].foreign_keys if fk.column.table.name == "document_chunks"]
    assert fk.ondelete == "RESTRICT"


def test_constraint_and_index_names_are_unique():
    names = [
        obj.name
        for table in TABLES.values()
        for obj in (*table.indexes, *table.constraints)
    ]
    assert len(names) == len(set(names))
