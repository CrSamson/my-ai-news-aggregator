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

from app.database.models import Article
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
