"""
agent/embedder.py — Pluggable article-embedding layer.

Defines a thin `Embedder` protocol with two concrete implementations:

    MiniLMEmbedder    default. sentence-transformers/all-MiniLM-L6-v2,
                      L2-normalised, 384-dim. Local, free per call,
                      ~80MB model on first download.
    OpenAIEmbedder    stub. Raises NotImplementedError until activated;
                      the swap point is here so callers don't change.

Pick via the BREVIO_EMBEDDER env var (default "minilm"):

    BREVIO_EMBEDDER=minilm   # default
    BREVIO_EMBEDDER=openai   # not implemented yet

Inputs are pre-formatted strings — `article_text(article)` is the helper
that produces them from an Article row, mirroring notebook cell 6:

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
    """Stub for OpenAI text-embedding-3-small (1536-dim). Not implemented
    yet — wired in advance so future callers don't have to change shape."""

    dim: int = 1536  # text-embedding-3-small native dim

    def embed(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError(
            "OpenAIEmbedder is a stub. Set BREVIO_EMBEDDER=minilm or "
            "implement this when you're ready to swap."
        )


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------

def get_default_embedder() -> Embedder:
    """Return the embedder named by BREVIO_EMBEDDER (default: minilm)."""
    name = os.environ.get("BREVIO_EMBEDDER", "minilm").strip().lower()
    if name == "minilm":
        return MiniLMEmbedder()
    if name == "openai":
        return OpenAIEmbedder()
    raise ValueError(
        f"Unknown BREVIO_EMBEDDER={name!r}. Expected one of: minilm, openai."
    )
