"""
app/database/models.py — SQLAlchemy ORM models.

Tables:
  • Article — any blog/news post from any source. Conflict key: url.
  • Story   — a cluster of related articles covering the same news event.
              Built by agent/clusterer.py from article embeddings.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()


# Embedding dimensionality. Matches OpenAI text-embedding-3-small.
# If you swap to a different model with a different dim, change this
# constant AND add a migration entry to create_tables._MIGRATED_COLUMNS
# so existing rows get re-embedded.
EMBEDDING_DIM: int = 1536


class Article(Base):
    """
    Any blog / news post from any source.

    Conflict key: `url` (unique). One row per canonical URL.
    `source` identifies which entry of config/sources.json produced the row,
    e.g. 'anthropic_news', 'openai_news', 'aws_ml'.
    """

    __tablename__ = "articles"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)

    source          = Column(String(64),  nullable=False, index=True)
    url             = Column(Text,        nullable=False, unique=True)   # conflict key
    title           = Column(Text,        nullable=False)
    author          = Column(Text,        nullable=True)
    published_at    = Column(DateTime(timezone=True), nullable=True, index=True)

    summary         = Column(Text,        nullable=True)                 # LLM-generated, set later
    content_md      = Column(Text,        nullable=True)                 # Docling output
    content_fetched = Column(Boolean,     nullable=False,
                             default=False, server_default=text("false"))

    # NULL = not yet included in a sent digest. Set to NOW() once an email
    # containing this row goes out successfully. Filtered by the digest queries
    # so the same row never ships in two emails.
    digest_sent_at  = Column(DateTime(timezone=True), nullable=True)

    # Topic tags inherited from sources.json config (e.g. ["ai", "technology"]).
    # Populated at insert time; refreshed on conflict so config edits propagate.
    topics          = Column(ARRAY(String), nullable=False,
                             server_default=text("ARRAY[]::varchar[]"))

    # 1536-dim OpenAI text-embedding-3-small of (title + content[:500]).
    # NULL until agent/embedder.py runs. L2-normalised so cosine similarity
    # equals the inner product. Indexed with HNSW + vector_cosine_ops for
    # nearest-neighbour story-clustering lookups (Phase 4).
    embedding       = Column(Vector(EMBEDDING_DIM), nullable=True)

    # FK into stories.id. NULL until agent/clusterer.py runs. ON DELETE
    # SET NULL so deleting a story (rare) doesn't cascade-delete its
    # member articles; they become unclustered again and the next runner
    # pass will reassign them.
    story_id        = Column(BigInteger,
                             ForeignKey("stories.id", ondelete="SET NULL"),
                             nullable=True, index=True)

    # Original feedparser entry, kept verbatim so we don't lose anything.
    raw_metadata    = Column(JSONB,       nullable=False,
                             default=dict, server_default=text("'{}'::jsonb"))

    created_at      = Column(DateTime(timezone=True),
                             server_default=func.now(), nullable=False)
    updated_at      = Column(DateTime(timezone=True),
                             server_default=func.now(), onupdate=func.now(),
                             nullable=False)

    def __repr__(self) -> str:
        return f"<Article id={self.id} source={self.source!r} title={self.title!r}>"


class Story(Base):
    """
    A cluster of related articles covering the same news event.

    Built by agent/clusterer.py from L2-normalised article embeddings via
    greedy single-pass clustering with running-mean centroids (cosine
    threshold 0.65, see experimentation/clustering_backtest.py for the
    backtest that set the threshold).

    `centroid` is the L2-normalised running mean of every member
    article's embedding — cosine similarity to the centroid equals the
    inner product. HNSW-indexed so the clusterer can look up the nearest
    active stories in O(log n) when assigning a new article.

    `synthesis*` columns are populated by Phase 5 (story-level LLM
    summarisation). They stay NULL through Phase 4.
    """

    __tablename__ = "stories"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)

    # Running-mean centroid, L2-normalised after every member join.
    centroid        = Column(Vector(EMBEDDING_DIM), nullable=False)
    article_count   = Column(BigInteger, nullable=False,
                             server_default=text("0"))

    # Stamped to first member's published_at on creation, never moves.
    first_seen_at   = Column(DateTime(timezone=True), nullable=False)
    # Bumped to the joining member's published_at every time a new article
    # joins. The clusterer filters active stories on last_seen_at >= cutoff
    # so stories older than the lookback window can't accumulate new
    # members (a fresh same-topic event spawns a new story instead).
    last_seen_at    = Column(DateTime(timezone=True), nullable=False, index=True)

    # Union of member articles' topics. Refreshed on every join.
    topics          = Column(ARRAY(String), nullable=False,
                             server_default=text("ARRAY[]::varchar[]"))

    # ------------------------------------------------------------------
    # Phase 5: story-level LLM synthesis. NULL until story_summarizer runs.
    # ------------------------------------------------------------------
    # JSON blob with the StorySummary fields (headline / summary / key_points
    # / entities / model / tokens / etc.). One row per story; re-synthesised
    # only when the member set changes (detected via synthesis_hash).
    synthesis       = Column(JSONB,       nullable=True)
    synthesis_model = Column(Text,        nullable=True)   # audit
    synthesis_at    = Column(DateTime(timezone=True), nullable=True)
    # sha256 of sorted member URLs at synthesis time. Used by the cache
    # check: if recomputed hash != stored hash, members have changed and
    # the story needs re-synthesis.
    synthesis_hash  = Column(Text,        nullable=True)

    # Stamped once the story ships in a digest. Filtered by the digest
    # query so the same story can't be emailed twice.
    digest_sent_at  = Column(DateTime(timezone=True), nullable=True)

    created_at      = Column(DateTime(timezone=True),
                             server_default=func.now(), nullable=False)
    updated_at      = Column(DateTime(timezone=True),
                             server_default=func.now(), onupdate=func.now(),
                             nullable=False)

    def __repr__(self) -> str:
        return (f"<Story id={self.id} article_count={self.article_count} "
                f"last_seen_at={self.last_seen_at!s}>")
