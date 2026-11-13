"""Persistent vector store using Chroma (local, on-disk) with cosine distance.

Docker/pgvector was not available on the lab machine, so Chroma PersistentClient
is used (allowed by GUIDE.md). One collection per strategy; metadata filters are
applied inside Chroma (``where=``), never by post-filtering in Python.
Chroma's default index is HNSW => approximate nearest-neighbour search.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import Chunk

_ALLOWED_FILTERS = {"chapter", "section", "document_id"}


class ChromaStore:
    def __init__(self, path: str | Path, dimensions: int, collection_prefix: str = "day06") -> None:
        import chromadb

        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.path = Path(path)
        self.dimensions = dimensions
        self.prefix = collection_prefix
        self.client = chromadb.PersistentClient(path=str(self.path))
        self.chroma_version = chromadb.__version__

    def _name(self, strategy: str) -> str:
        return f"{self.prefix}_{strategy}"

    def create_schema(self, strategy: str, embedding_model: str):
        """Create (or open) the collection for a strategy with cosine space."""
        col = self.client.get_or_create_collection(
            name=self._name(strategy),
            metadata={"hnsw:space": "cosine", "embedding_model": embedding_model,
                      "dimensions": self.dimensions},
            embedding_function=None,
        )
        md = col.metadata or {}
        if md.get("embedding_model") != embedding_model or md.get("dimensions") != self.dimensions \
                or md.get("hnsw:space") != "cosine":
            raise ValueError(f"Collection {col.name} was built with {md}; refusing to mix with "
                             f"{embedding_model}/{self.dimensions}d. Delete chroma_db/ to rebuild.")
        return col

    def count(self, strategy: str) -> int:
        return self.client.get_collection(self._name(strategy)).count()

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]],
               embedding_model: str) -> dict[str, int]:
        """Upsert with stable IDs and delete obsolete chunks of the same documents.

        Returns counts so the caller can log idempotency (re-ingest => no growth).
        """
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        for v in vectors:
            if len(v) != self.dimensions:
                raise ValueError(f"vector has {len(v)} dims, expected {self.dimensions}")
        ids = [c.chunk_id for c in chunks]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate chunk IDs in one batch")
        col = self.create_schema(strategy, embedding_model)
        before = col.count()
        metadatas = []
        for c in chunks:
            md = {"document_id": c.document_id, "source": c.source, "page": int(c.page)}
            md.update({k: v for k, v in c.metadata.items() if v is not None})
            metadatas.append(md)
        # Skip chunks whose ID, content hash and metadata are unchanged: re-ingesting the
        # same version writes nothing (rewriting identical IDs churns the HNSW index).
        existing = col.get(ids=ids, include=["metadatas"])
        known = dict(zip(existing["ids"], existing["metadatas"]))
        todo = [i for i, cid in enumerate(ids) if known.get(cid) != metadatas[i]]
        for j in range(0, len(todo), 500):
            batch = todo[j:j + 500]
            col.upsert(ids=[ids[i] for i in batch], embeddings=[vectors[i] for i in batch],
                       documents=[chunks[i].text for i in batch], metadatas=[metadatas[i] for i in batch])
        # Remove chunks of these documents that no longer exist (changed source).
        removed = 0
        for doc_id in {c.document_id for c in chunks}:
            existing = col.get(where={"document_id": doc_id}, include=[])["ids"]
            stale = sorted(set(existing) - set(ids))
            if stale:
                col.delete(ids=stale)
                removed += len(stale)
        return {"before": before, "input_chunks": len(ids), "written": len(todo),
                "unchanged_skipped": len(ids) - len(todo), "removed_stale": removed, "after": col.count()}

    def exact_top_k(self, strategy: str, query_vector: list[float], top_k: int = 3,
                    filters: dict[str, Any] | None = None) -> list[str]:
        """Brute-force cosine top-k over the stored vectors (audit of the ANN result)."""
        import numpy as np

        col = self.client.get_collection(self._name(strategy))
        data = col.get(where=self._where(filters), include=["embeddings"])
        if not data["ids"]:
            return []
        sims = np.asarray(data["embeddings"]) @ np.asarray(query_vector)
        return [data["ids"][i] for i in np.argsort(-sims)[:top_k]]

    @staticmethod
    def _where(filters: dict[str, Any] | None):
        if not filters:
            return None
        unknown = set(filters) - _ALLOWED_FILTERS
        if unknown:
            raise ValueError(f"filter fields not allowed: {unknown}")
        clauses = [{k: v} for k, v in filters.items()]
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Filter metadata inside Chroma, rank by cosine distance, return top-k."""
        if len(query_vector) != self.dimensions:
            raise ValueError("query vector has wrong dimensions")
        where = self._where(filters)
        col = self.client.get_collection(self._name(strategy))
        res = col.query(query_embeddings=[query_vector], n_results=top_k, where=where,
                        include=["documents", "metadatas", "distances"])
        hits = []
        for rank, (cid, doc, md, dist) in enumerate(zip(res["ids"][0], res["documents"][0],
                                                        res["metadatas"][0], res["distances"][0]), 1):
            hits.append({"rank": rank, "chunk_id": cid, "text": doc, "score": round(1.0 - dist, 4),
                         "cosine_distance": round(dist, 4), "metadata": md})
        return hits
