"""Real embedding model (local Sentence Transformers). No mock/random fallback.

Default model: intfloat/multilingual-e5-small (384 dims). E5 models expect the
prefixes "query: " for questions and "passage: " for documents; vectors are
L2-normalized so cosine similarity == dot product.
"""
from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, question: str) -> list[float]:
        ...


class SentenceTransformerEmbedder:
    """Local Sentence Transformers adapter; raises if the model cannot load."""

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small", batch_size: int = 32,
                 device: str | None = None) -> None:
        from sentence_transformers import SentenceTransformer  # import errors surface loudly

        self.model_name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name, device=device)
        dim = self.model.get_embedding_dimension()
        if not dim:
            raise RuntimeError(f"Could not determine embedding dimensions for {model_name}")
        self.dimensions = int(dim)
        self._is_e5 = "e5" in model_name.lower()

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                    show_progress_bar=False, convert_to_numpy=True)
        if vectors.shape[1] != self.dimensions:
            raise RuntimeError("Embedding dimension mismatch")
        return vectors.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefix = "passage: " if self._is_e5 else ""
        return self._encode([prefix + t for t in texts])

    def embed_query(self, question: str) -> list[float]:
        prefix = "query: " if self._is_e5 else ""
        return self._encode([prefix + question])[0]
