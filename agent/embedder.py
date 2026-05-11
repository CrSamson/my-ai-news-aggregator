"""
agent/embedder.py — Pluggable article-embedding layer.

Defines a thin `Embedder` protocol with two concrete implementations:

    OpenAIEmbedder    default. text-embedding-3-small, 1536-dim,
                      L2-normalised post-hoc. Requires OPENAI_API_KEY
                      (already wired up for summarisation). Costs
                      ~$0.0006/day at production volume.
    MiniLMEmbedder    fallback. sentence-transformers/all-MiniLM-L6-v2,
                      384-dim, L2-normalised. Local, free per call.
                      Requires sentence-transformers + torch in the
                      environment (not in default requirements.txt).

The embedder swap landed in 2026-05-05 after a backtest on 569 articles
showed OpenAI catches more cross-source stories (Apple Mac mini, Mythos
cluster, larger Musk v. Altman) and correctly decomposes the topic blobs
that MiniLM merged (AWS GenAI, OpenAI weekly news, AI stocks). See
experimentation/openai_embedding_compare.py for the full comparison.

Pick via the BREVIO_EMBEDDER env var (default "openai"):

    BREVIO_EMBEDDER=openai   # default
    BREVIO_EMBEDDER=minilm   # requires `pip install sentence-transformers`

Inputs are pre-formatted strings — `article_text(article)` is the helper
that produces them from an Article row:

    title + " " + (content_md or raw_metadata.summary or "")[:500]

Embeddings are returned as a (N, dim) numpy array, L2-normalised, so
cosine similarity equals the inner product — convenient for the greedy
threshold clusterer in Phase 4.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Protocol

import numpy as np

from app.database.models import EMBEDDING_DIM

if TYPE_CHECKING:
    from app.database.models import Article


# ---------------------------------------------------------------------------
# Article -> string helper
# ---------------------------------------------------------------------------

# Cap on body chars passed into the embedder. Notebook used 500. Title is
# weighted by being prepended (the model attends to it disproportionately
# anyway, but the prefix is cheap insurance).
EMBED_BODY_CHARS: int = 500


def article_text(article: "Article") -> str:
    """Build the string we embed for one Article. Mirrors the prototype in
    experimentation/architecture_experiments.ipynb (cell 6)."""
    body = article.content_md or ""
    if not body and article.raw_metadata:
        body = (
            article.raw_metadata.get("summary")
            or article.raw_metadata.get("description")
            or ""
        )
    body = (body or "").strip()[:EMBED_BODY_CHARS]
    title = (article.title or "").strip()
    return f"{title} {body}".strip()


# ---------------------------------------------------------------------------
# Protocol + implementations
# ---------------------------------------------------------------------------

class Embedder(Protocol):
    """Anything with `dim` and `embed(texts) -> (N, dim) np.ndarray` works."""

    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:  # pragma: no cover - protocol
        ...


class MiniLMEmbedder:
    """sentence-transformers/all-MiniLM-L6-v2. 384-dim, L2-normalised.

    Model is downloaded on first use (~80MB) and cached under the
    huggingface hub directory (~/.cache/huggingface).
    """

    dim: int = EMBEDDING_DIM
    MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self) -> None:
        self._model = None  # lazy

    def _load(self):
        if self._model is None:
            # Imported lazily so the rest of the codebase doesn't pay the
            # ~2-3 s import cost of sentence-transformers + torch when
            # nothing is being embedded.
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.MODEL_NAME)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        model = self._load()
        # `normalize_embeddings=True` does L2-norm in C; cheaper than a
        # post-hoc sklearn normalize() pass.
        arr = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return np.asarray(arr, dtype=np.float32)


class OpenAIEmbedder:
    """OpenAI text-embedding-3-small (1536-dim, L2-normalised post-hoc).

    Reads OPENAI_API_KEY from the environment (already loaded by callers
    that import dotenv). Batches inputs in groups of 100; OpenAI accepts
    up to 2048 inputs per call but smaller batches keep memory predictable
    and surface failures earlier.

    Note on output dim: 1536 is the native dim for text-embedding-3-small.
    The endpoint also supports a `dimensions` parameter for Matryoshka
    truncation if a smaller column is preferable; we don't use it here so
    callers get the full quality of the model. Phase 4's pgvector column
    must match whatever dim is in use; currently 384 (MiniLM). Switching
    to this embedder requires altering the column type to vector(1536)
    and rebuilding the HNSW index.
    """

    dim: int = 1536
    MODEL_NAME: str = "text-embedding-3-small"
    BATCH_SIZE: int = 100

    def __init__(self) -> None:
        # Lazy-imported so importing this module doesn't require openai
        # if the user is on the MiniLM path.
        from openai import OpenAI
        self._client = OpenAI()

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        all_vecs: list[list[float]] = []
        for start in range(0, len(texts), self.BATCH_SIZE):
            chunk = texts[start:start + self.BATCH_SIZE]
            # OpenAI rejects empty strings; replace with a single space so
            # the call doesn't fail on the rare title-only article with
            # no body.
            chunk = [t if t.strip() else " " for t in chunk]
            resp = self._client.embeddings.create(
                model=self.MODEL_NAME,
                input=chunk,
            )
            # Response order matches input order per the API contract.
            all_vecs.extend(item.embedding for item in resp.data)
        arr = np.asarray(all_vecs, dtype=np.float32)
        # Post-hoc L2-normalise so cosine == inner product for the
        # downstream clusterer.
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------

def get_default_embedder() -> Embedder:
    """Return the embedder named by BREVIO_EMBEDDER (default: openai)."""
    name = os.environ.get("BREVIO_EMBEDDER", "openai").strip().lower()
    if name == "openai":
        return OpenAIEmbedder()
    if name == "minilm":
        return MiniLMEmbedder()
    raise ValueError(
        f"Unknown BREVIO_EMBEDDER={name!r}. Expected one of: openai, minilm."
    )
