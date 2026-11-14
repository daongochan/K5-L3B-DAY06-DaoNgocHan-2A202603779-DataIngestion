"""Real embedding provider backed by Sentence Transformers.

Model: intfloat/multilingual-e5-base (768 dimensions, multilingual, trained for
retrieval). E5 expects task prefixes on both sides — ``passage:`` for documents
and ``query:`` for questions. Omitting them measurably degrades retrieval, so
they are applied inside the adapter and stay identical across all strategies.

There is no mock or random fallback: if the model cannot be loaded, the error
propagates so the pipeline fails loudly instead of silently scoring noise.
"""
from __future__ import annotations

import os
from typing import Protocol

# Keep Hugging Face output quiet; these are warnings about cache symlinks on
# Windows and progress bars, neither of which affects correctness.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

DEFAULT_MODEL = "intfloat/multilingual-e5-base"
DOCUMENT_PREFIX = "passage: "
QUERY_PREFIX = "query: "


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class SentenceTransformerEmbedder:
    """E5 adapter applying the required passage/query prefixes.

    Vectors are L2-normalized, so cosine similarity equals the dot product and
    pgvector's cosine distance is directly comparable across strategies.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str | None = None,
        batch_size: int = 16,
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.batch_size = batch_size
        self._model = SentenceTransformer(model_name, device=device)
        self.dimensions = self._model.get_sentence_embedding_dimension()
        if not self.dimensions:
            raise RuntimeError(f"could not determine embedding size for {model_name}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            [DOCUMENT_PREFIX + text for text in texts],
            normalize_embeddings=True,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def embed_query(self, question: str) -> list[float]:
        vector = self._model.encode(
            QUERY_PREFIX + question,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector.tolist()
