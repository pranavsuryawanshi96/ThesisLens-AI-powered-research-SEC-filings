import asyncio
from types import SimpleNamespace

import pytest

from app.config import settings
from ingest.embedding import BATCH_SIZE, embed_texts

DIMS = settings.openai_embedding_dimensions


class FakeEmbeddings:
    def __init__(self, dims: int = DIMS):
        self.calls: list[dict] = []
        self.dims = dims

    async def create(self, *, model, input, dimensions):
        self.calls.append({"model": model, "input": input, "dimensions": dimensions})
        # Encode each text's position in the vector, and return items out of order.
        data = [
            SimpleNamespace(index=i, embedding=[float(text.split()[-1])] * self.dims)
            for i, text in enumerate(input)
        ]
        return SimpleNamespace(data=list(reversed(data)))


def fake_client(dims: int = DIMS) -> SimpleNamespace:
    return SimpleNamespace(embeddings=FakeEmbeddings(dims))


def test_embed_texts_batches_and_preserves_order():
    client = fake_client()
    texts = [f"chunk {i}" for i in range(BATCH_SIZE * 2 + 50)]

    vectors = asyncio.run(embed_texts(client, texts))

    assert [len(call["input"]) for call in client.embeddings.calls] == [BATCH_SIZE, BATCH_SIZE, 50]
    assert [vector[0] for vector in vectors] == [float(i) for i in range(len(texts))]


def test_embed_texts_uses_configured_model_and_dimensions():
    client = fake_client()
    asyncio.run(embed_texts(client, ["chunk 0"]))

    call = client.embeddings.calls[0]
    assert call["model"] == settings.openai_embedding_model
    assert call["dimensions"] == DIMS


def test_embed_texts_rejects_wrong_dimensions():
    with pytest.raises(ValueError):
        asyncio.run(embed_texts(fake_client(dims=DIMS - 1), ["chunk 0"]))
