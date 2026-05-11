"""
app/database/__init__.py — Makes app/database a package.
Re-exports the most commonly used symbols for convenience.
"""

from .db import engine, SessionLocal, get_db
from .models import Base, Article, Story
from .crud import (
    upsert_articles,
    get_all_articles,
    get_unsummarized_articles,
    set_article_summary,
    get_recent_summarized_articles,
    get_unembedded_articles,
    set_article_embedding,
    get_unclustered_articles,
    get_active_stories,
    create_story,
    assign_article_to_story,
    mark_digest_sent,
)

__all__ = [
    "engine",
    "SessionLocal",
    "get_db",
    "Base",
    "Article",
    "Story",
    "upsert_articles",
    "get_all_articles",
    "get_unsummarized_articles",
    "set_article_summary",
    "get_recent_summarized_articles",
    "get_unembedded_articles",
    "set_article_embedding",
    "get_unclustered_articles",
    "get_active_stories",
    "create_story",
    "assign_article_to_story",
    "mark_digest_sent",
]
