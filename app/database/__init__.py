"""
app/database/__init__.py — Makes app/database a package.
Re-exports the most commonly used symbols for convenience.
"""

from .db import engine, SessionLocal, get_db
from .models import Base, Article, Paper
from .crud import (
    upsert_articles,
    get_all_articles,
    get_unsummarized_articles,
    set_article_summary,
    get_recent_summarized_articles,
    upsert_papers,
    merge_hf_daily_papers,
    get_all_papers,
    get_unsummarized_papers,
    set_paper_summary,
    get_recent_summarized_papers,
    mark_digest_sent,
)

__all__ = [
    "engine",
    "SessionLocal",
    "get_db",
    "Base",
    "Article",
    "Paper",
    "upsert_articles",
    "get_all_articles",
    "get_unsummarized_articles",
    "set_article_summary",
    "get_recent_summarized_articles",
    "upsert_papers",
    "merge_hf_daily_papers",
    "get_all_papers",
    "get_unsummarized_papers",
    "set_paper_summary",
    "get_recent_summarized_papers",
    "mark_digest_sent",
]
