"""OpenAI embeddings, shared by ingestion and live queries so both use one model."""

from openai import AsyncOpenAI

from app.config import settings

# Well under the API's 2048-inputs / 300k-tokens per request at 512-token chunks.
BATCH_SIZE = 100


async def embed_texts(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        response = await client.embeddings.create(
            model=settings.openai_embedding_model,
            input=batch,
            dimensions=settings.openai_embedding_dimensions,
        )
        embeddings = [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
        if len(embeddings) != len(batch) or any(
            len(vector) != settings.openai_embedding_dimensions for vector in embeddings
        ):
            raise ValueError("OpenAI returned embeddings that do not match the request")
        vectors.extend(embeddings)
    return vectors


async def embed_query(client: AsyncOpenAI, text: str) -> list[float]:
    [vector] = await embed_texts(client, [text])
    return vector
