"""
api/schemas.py — Pydantic response models.

Shapes match what the mobile app's TypeScript codegen will consume.
Uniform shape across multi-source stories and singletons so the app
doesn't need to branch on `is_multi_source` to render cards.

Field-level fallback rules baked into the API layer (see services.py):

  multi-source story (article_count >= 2, synthesis != NULL):
      headline / summary / key_points / entities / topics → synthesis JSON
      source_ids                                          → distinct member sources
      primary_source                                      → first member's source

  singleton (article_count == 1):
      headline                                            → article.title
      summary                                             → article.summary
                                                            (falls back to RSS description
                                                             when summary is NULL/empty)
      key_points / entities                               → []
      topics                                              → article.topics
      source_ids                                          → [article.source]
      primary_source                                      → article.source

This keeps the app's render path single-branch: pick the card-size
variant by `is_multi_source`, but pull every text field from the same
keys regardless of variant.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class Health(BaseModel):
    ok: bool = True
    version: str = "v1"


# ---------------------------------------------------------------------------
# Article (used inside StoryDetail.articles[])
# ---------------------------------------------------------------------------

class ArticleSource(BaseModel):
    """One member article in a story's source timeline."""

    id: int
    source: str
    source_display_name: Optional[str] = None
    url: str
    title: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    rss_summary: Optional[str] = Field(
        default=None,
        description="RSS feed's <description> or the LLM per-article summary; "
                    "the app renders this as the source-card preview body.",
    )


# ---------------------------------------------------------------------------
# Story card (list endpoints)
# ---------------------------------------------------------------------------

class StoryCard(BaseModel):
    """Compact story representation for list endpoints (Top, Topic, All).

    Multi-source vs singleton differences are flattened: the same keys
    are populated for both, only the values change. `is_multi_source`
    drives the card-size variant in the app.
    """

    id: int
    is_multi_source: bool

    headline: str
    summary_preview: str = Field(
        description="3-line summary for multi-source cards, 2-line for singletons. "
                    "Truncated server-side to keep payloads small."
    )

    topics: list[str] = Field(default_factory=list)

    article_count: int
    source_ids: list[str] = Field(
        default_factory=list,
        description="Distinct source ids for the source-dot row. "
                    "Limited to ~6 in API responses; app shows up to 4 with '+N' overflow.",
    )
    primary_source: Optional[str] = Field(
        default=None,
        description="The source whose name renders inline next to the singleton "
                    "card's source dot. For multi-source cards this is the source "
                    "that broke the story (oldest member's source).",
    )

    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None


class StoryListResponse(BaseModel):
    """Paginated list of stories. Used by /stories/top, /stories/all."""

    items: list[StoryCard]
    next_offset: Optional[int] = None
    total_in_window: Optional[int] = None


# ---------------------------------------------------------------------------
# Story detail (single-story endpoint)
# ---------------------------------------------------------------------------

class StoryDetail(StoryCard):
    """Full story payload for the detail screen.

    Inherits every StoryCard field, adds the synthesis body (summary text,
    key points, entities) and the chronologically-sorted source articles.
    """

    summary: str = Field(
        description="Full ~100-word neutral synthesis (multi) or per-article "
                    "summary text (singleton).",
    )
    key_points: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)

    articles: list[ArticleSource] = Field(
        default_factory=list,
        description="Member articles in chronological-ascending order. "
                    "The app's Timeline section renders these top-to-bottom.",
    )


# ---------------------------------------------------------------------------
# Topic feed (curated mix)
# ---------------------------------------------------------------------------

class TopicFeedResponse(BaseModel):
    """Curated per-topic feed: every multi-source story in the topic +
    the top-N highest-scoring singletons. App's Topics tab consumes this."""

    topic: str
    multi_stories: list[StoryCard] = Field(
        description="Every multi-source story tagged with this topic, "
                    "ordered by (article_count DESC, last_seen_at DESC).",
    )
    top_singletons: list[StoryCard] = Field(
        description="Top-N singletons scored by the singleton ranker "
                    "(recency × source authority × content depth). Default N=5.",
    )
