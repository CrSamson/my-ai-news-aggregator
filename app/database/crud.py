"""
app/database/crud.py — Single CRUD interface for all database operations.

Uses PostgreSQL ON CONFLICT … DO UPDATE (upsert) so scrapers can safely
re-insert the same article without duplicates.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, literal_column, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database.models import Article, Story
from scrapers.schemas import BlogArticle


log = logging.getLogger(__name__)


def _digest_cutoff(hours: int) -> datetime:
    """
    Cutoff used by the digest queries.

    Rounded down to midnight UTC so a "today" article is never excluded
    by a few wall-clock hours - matches the cutoff rounding in
    RssBlogScraper._parse_feed_bytes.
    """
    return (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).replace(hour=0, minute=0, second=0, microsecond=0)


# ===================================================================
# Articles
# ===================================================================

def upsert_articles(db: Session, items: list[BlogArticle]) -> dict:
    """
    Upsert a batch of BlogArticle rows (conflict key: url).

    Returns {"inserted": N, "updated": N, "total": N}.

    Insert vs update is detected via Postgres' xmax trick:
        xmax = 0  -> row was just inserted
        xmax != 0 -> row already existed and ON CONFLICT fired

    `summary` is deliberately omitted from the SET clause so a re-scrape
    never overwrites an LLM-generated summary downstream.
    """
    inserted = 0
    updated  = 0

    for item in items:
        values = {
            "source"         : item.source,
            "url"            : item.url,
            "title"          : item.title,
            "author"         : item.author,
            "published_at"   : item.published_at,
            "summary"        : item.summary,           # always None at scrape time
            "content_md"     : item.content_md,
            "content_fetched": item.content_fetched,
            "topics"         : item.topics,
            "raw_metadata"   : item.raw_metadata or {},
        }

        stmt = (
            pg_insert(Article)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["url"],
                set_={
                    "title"          : values["title"],
                    "author"         : values["author"],
                    "published_at"   : values["published_at"],
                    "content_md"     : values["content_md"],
                    "content_fetched": values["content_fetched"],
                    # Articles have one source -> overwrite topics with the
                    # latest source-config tags so config edits propagate.
                    "topics"         : values["topics"],
                    "raw_metadata"   : values["raw_metadata"],
                    # summary intentionally omitted - preserve LLM output
                    "updated_at"     : func.now(),
                },
            )
            .returning(literal_column("(xmax = 0)").label("was_inserted"))
        )
        was_inserted = db.execute(stmt).scalar()
        if was_inserted:
            inserted += 1
        else:
            updated += 1

    db.flush()
    return {"inserted": inserted, "updated": updated, "total": inserted + updated}


def get_all_articles(db: Session) -> list[Article]:
    """Return all Articles, newest first."""
    stmt = select(Article).order_by(Article.published_at.desc())
    return list(db.execute(stmt).scalars().all())


def get_unsummarized_articles(db: Session, limit: Optional[int] = None) -> list[Article]:
    """Return Articles whose summary is NULL or empty, newest first."""
    stmt = (
        select(Article)
        .where(or_(Article.summary.is_(None), Article.summary == ""))
        .order_by(Article.published_at.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars().all())


def set_article_summary(
    db: Session,
    article_id: int,
    summary: str,
    topics: list[str] | None = None,
) -> None:
    """Persist a generated summary for one Article. If `topics` is provided
    (LLM-classified), it overwrites the source-declared tags."""
    article = db.get(Article, article_id)
    if article is None:
        raise ValueError(f"Article id={article_id} not found")
    article.summary = summary
    if topics is not None:
        article.topics = topics


def get_recent_summarized_articles(db: Session, hours: int) -> list[Article]:
    """Return Articles published in the last `hours` hours that have a non-empty
    summary AND have not already been included in a sent digest."""
    cutoff = _digest_cutoff(hours)
    stmt = (
        select(Article)
        .where(Article.summary.isnot(None))
        .where(Article.summary != "")
        .where(Article.published_at >= cutoff)
        .where(Article.digest_sent_at.is_(None))
        .order_by(Article.published_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


# ===================================================================
# Embeddings (Phase 3)
# ===================================================================

def get_unembedded_articles(db: Session, limit: Optional[int] = None) -> list[Article]:
    """Return Articles whose `embedding` column is NULL, newest first."""
    stmt = (
        select(Article)
        .where(Article.embedding.is_(None))
        .order_by(Article.published_at.desc().nullslast())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars().all())


def set_article_embedding(db: Session, article_id: int, embedding) -> None:
    """Persist the embedding vector for one Article. `embedding` is a 1D
    numpy array or list of floats of length EMBEDDING_DIM (1536)."""
    article = db.get(Article, article_id)
    if article is None:
        raise ValueError(f"Article id={article_id} not found")
    # pgvector accepts numpy arrays and python lists; convert to list to
    # avoid surprising the SQLAlchemy adapter on some numpy dtypes.
    article.embedding = list(embedding)


# ===================================================================
# Stories / clustering (Phase 4)
# ===================================================================

def get_unclustered_articles(db: Session, limit: Optional[int] = None) -> list[Article]:
    """Return embedded Articles whose `story_id` is NULL, oldest first.

    Oldest-first matters: the stateful clusterer wants the earliest
    article to seed a story, and newer ones to optionally join it. This
    matches the chronological behaviour of the production daily pipeline
    where today's batch is layered on top of yesterday's stories.
    """
    stmt = (
        select(Article)
        .where(Article.story_id.is_(None))
        .where(Article.embedding.is_not(None))
        .order_by(Article.published_at.asc().nullsfirst())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_active_stories(db: Session, hours: int) -> list[Story]:
    """Return stories whose `last_seen_at` is within the lookback window.

    The clusterer compares each new article against this set; stories
    that haven't seen new members in `hours` hours are considered "cold"
    and a fresh same-topic article will spawn a new story instead of
    extending the old one.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(Story)
        .where(Story.last_seen_at >= cutoff)
        .order_by(Story.last_seen_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def create_story(
    db: Session,
    *,
    centroid,
    topics: list[str],
    first_article: Article,
) -> Story:
    """Insert a new story seeded by one article. The article is updated
    in-place to point at the new story_id; story.article_count starts
    at 1; first_seen_at and last_seen_at are stamped from the article's
    published_at (or now() as a fallback)."""
    now = datetime.now(timezone.utc)
    seen_at = first_article.published_at or now
    story = Story(
        centroid=list(centroid),
        article_count=1,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        topics=list(topics or []),
    )
    db.add(story)
    db.flush()             # populate story.id
    first_article.story_id = story.id
    return story


def assign_article_to_story(
    db: Session,
    *,
    article: Article,
    story: Story,
    new_centroid,
) -> None:
    """Add `article` to `story`, bump article_count, advance last_seen_at,
    union the topics, and overwrite the centroid with the freshly-computed
    running mean (caller supplies it L2-normalised).

    Also invalidates the story's cached LLM synthesis so the next Phase 5
    pass re-synthesises with the new member set. The cheapest correct
    invalidation: NULL the synthesis fields. The synthesis pass only looks
    at stories whose `synthesis IS NULL`, so this row gets picked up
    automatically next run.
    """
    article.story_id      = story.id
    story.centroid        = list(new_centroid)
    story.article_count   = (story.article_count or 0) + 1
    if article.published_at is not None and (
        story.last_seen_at is None or article.published_at > story.last_seen_at
    ):
        story.last_seen_at = article.published_at
    # Topic union (preserve order, dedupe).
    existing = list(story.topics or [])
    seen = set(existing)
    for t in article.topics or []:
        if t not in seen:
            existing.append(t)
            seen.add(t)
    story.topics = existing
    # Membership changed -> previous synthesis is stale.
    story.synthesis       = None
    story.synthesis_model = None
    story.synthesis_at    = None
    story.synthesis_hash  = None


# ===================================================================
# Story-level LLM synthesis (Phase 5)
# ===================================================================

def get_stories_needing_synthesis(
    db: Session,
    *,
    limit: Optional[int] = None,
    min_size: int = 2,
    force: bool = False,
) -> list[Story]:
    """Return stories whose LLM synthesis is missing or stale.

    Args:
      min_size: skip stories below this article_count. Default 2 so the
                synthesis pass only touches multi-article clusters; the
                470 singletons in the current corpus don't burn API
                tokens until we explicitly opt them in.
      force:    bypass the "synthesis is NULL" guard and return every
                multi-story for re-synthesis. Used by --force flag.
    """
    stmt = select(Story).where(Story.article_count >= min_size)
    if not force:
        stmt = stmt.where(Story.synthesis.is_(None))
    stmt = stmt.order_by(Story.last_seen_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_story_members(db: Session, story_id: int) -> list[Article]:
    """Return every Article belonging to one story, ordered by
    published_at ascending (so the synthesis prompt sees them in
    chronological order). Stable order also makes the synthesis_hash
    deterministic across re-runs."""
    stmt = (
        select(Article)
        .where(Article.story_id == story_id)
        .order_by(Article.published_at.asc().nullsfirst(), Article.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def set_story_synthesis(
    db: Session,
    story_id: int,
    *,
    synthesis: dict,
    model: str,
    hash_value: str,
) -> None:
    """Persist a freshly-generated synthesis for one story."""
    story = db.get(Story, story_id)
    if story is None:
        raise ValueError(f"Story id={story_id} not found")
    story.synthesis       = synthesis
    story.synthesis_model = model
    story.synthesis_at    = func.now()
    story.synthesis_hash  = hash_value


# ===================================================================
# Digest send-state
# ===================================================================

def mark_digest_sent(db: Session, model, ids: list[int]) -> int:
    """
    Stamp `digest_sent_at = NOW()` on the rows of `model` whose `id` is in
    `ids`. Used after a digest email goes out successfully so the same row
    never ships twice.

    Returns the number of rows updated.

    Idempotent: re-applying to the same ids just refreshes the timestamp.
    `model` must have a `digest_sent_at` column.
    """
    if not ids:
        return 0
    stmt = (
        update(model)
        .where(model.id.in_(ids))
        .values(digest_sent_at=func.now())
    )
    result = db.execute(stmt)
    db.flush()
    return result.rowcount or 0
