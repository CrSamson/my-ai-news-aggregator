"""
api/services.py — Query + transform: Story rows + Article rows → response shapes.

Centralises the SINGLE place where multi-source vs singleton fallback
logic lives. Routes call these functions and return their result; they
never look at SQLAlchemy ORM objects directly.

Public functions (used by routes/):
    get_top_stories(db, limit, offset, hours)             → StoryListResponse
    get_all_stories(db, limit, offset, hours)             → StoryListResponse
    get_topic_feed(db, topic, multi_limit, singletons_n)  → TopicFeedResponse
    get_story_detail(db, story_id)                        → StoryDetail | None

Source-publisher display names + the "summary preview" length come from
constants defined here so the app's UX stays consistent across endpoints.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import desc, func, select, text
from sqlalchemy.orm import Session

from agent.singleton_ranker import (
    DEFAULT_PER_TOPIC,
    rank_singletons_one_topic,
    score_article,
)
from agent.summarizer import ALLOWED_TOPICS
from api.schemas import (
    ArticleSource,
    StoryCard,
    StoryDetail,
    StoryListResponse,
    TopicFeedResponse,
)
from app.database.models import Article, Story


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Per UI spec: multi-source cards show ~3 lines of summary, singletons ~2.
# At ~70 chars/line on a phone, 3 × 70 = 210 chars. Plus generous headroom
# for the fade-out at line 3. 280 chars covers both card variants.
SUMMARY_PREVIEW_CHARS: int = 280

# Cap on source_ids returned per story — the app's source-dot row shows up
# to 4 + "+N" overflow, so 6 is enough metadata.
MAX_SOURCE_IDS_IN_LIST: int = 6

# Default lookback windows.
DEFAULT_TOP_HOURS:  int = 72       # /stories/top — last 3 days
DEFAULT_ALL_HOURS:  int = 48       # /stories/all — last 2 days
DEFAULT_TOPIC_HOURS: int = 72


# Hard-coded source → display name map. Moves to sources.json `display_name`
# field in the deferred Phase G1 backend cleanup. Falls back to title-casing
# the source id (e.g. "openai_news" → "Openai News") for unmapped sources.
SOURCE_DISPLAY_NAMES: dict[str, str] = {
    "anthropic_news":        "Anthropic",
    "anthropic_research":    "Anthropic Research",
    "anthropic_engineering": "Anthropic Engineering",
    "openai_news":           "OpenAI",
    "google_research":       "Google Research",
    "aws_ml":                "AWS ML",
    "nvidia_developer":      "NVIDIA Developer",
    "meta_ai":               "Meta AI",
    "bair":                  "BAIR",
    "cmu_ml":                "CMU ML",
    "mit_news":              "MIT News",
    "techcrunch_ai":         "TechCrunch",
    "the_verge":             "The Verge",
    "ars_technica":          "Ars Technica",
    "wired":                 "Wired",
    "nature":                "Nature",
    "sciencedaily":          "ScienceDaily",
    "phys_org":              "Phys.org",
    "quanta":                "Quanta Magazine",
    "bbc_news":              "BBC News",
    "cnbc":                  "CNBC",
    "the_independent":       "The Independent",
    "cna":                   "Channel News Asia",
    "forbes_business":       "Forbes",
    "yahoo_finance":         "Yahoo Finance",
    "air_space_forces":      "Air & Space Forces",
    "cbc_news":              "CBC News",
}


def source_display_name(source_id: str) -> str:
    if source_id in SOURCE_DISPLAY_NAMES:
        return SOURCE_DISPLAY_NAMES[source_id]
    # Last-resort title-case: "venturebeat_ai" → "Venturebeat Ai"
    return source_id.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Strip HTML tags + collapse whitespace. Used on RSS-description fallback
# bodies because some feeds (Nature, phys_org) embed full <p>/<a>/<img> HTML
# in their <description> field, which would render as raw markup on the
# mobile card. LLM-generated summaries don't need this — they're plain text
# by construction — but the API runs every preview through the strip
# defensively so the contract "summary_preview is plain text" always holds.
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
# Common named entities. Keep this short — we only strip the ones that
# actually show up in our feeds.
_HTML_ENTITIES = {
    "&amp;":  "&",
    "&lt;":   "<",
    "&gt;":   ">",
    "&quot;": "\"",
    "&apos;": "'",
    "&#39;":  "'",
    "&nbsp;": " ",
    "&ndash;": "–",
    "&mdash;": "—",
    "&hellip;": "…",
    "&rsquo;": "'",
    "&lsquo;": "'",
    "&rdquo;": "\"",
    "&ldquo;": "\"",
}


def _strip_html(text_in: str) -> str:
    """Remove HTML tags + decode the common named entities. Returns plain
    text suitable for a card preview."""
    s = _HTML_TAG_RE.sub("", text_in or "")
    for ent, rep in _HTML_ENTITIES.items():
        s = s.replace(ent, rep)
    s = _WHITESPACE_RE.sub(" ", s)
    return s.strip()


def _truncate_preview(text_in: str, max_chars: int = SUMMARY_PREVIEW_CHARS) -> str:
    """Strip HTML, then truncate to max_chars at the nearest word boundary,
    appending an ellipsis if cut. Returns '' for None / empty input."""
    s = _strip_html(text_in or "").strip()
    if not s:
        return ""
    if len(s) <= max_chars:
        return s
    cut = s[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"


def _members_for_story(db: Session, story_id: int) -> list[Article]:
    """Member articles of one story, oldest-first (chronological)."""
    stmt = (
        select(Article)
        .where(Article.story_id == story_id)
        .order_by(Article.published_at.asc().nullsfirst(), Article.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def _first_member_summary(article: Article) -> str:
    """Best body text we have for a singleton card."""
    if article.summary:
        return article.summary
    if article.raw_metadata:
        return (
            article.raw_metadata.get("summary")
            or article.raw_metadata.get("description")
            or ""
        )
    return ""


def _story_to_card(db: Session, story: Story) -> StoryCard:
    """Project a Story (+ its members on the fly) into the uniform StoryCard
    response shape. Handles the multi-source / singleton fallback in one
    place so routes never branch on synthesis."""
    is_multi = story.article_count >= 2
    members = _members_for_story(db, story.id)
    if not members:
        # Defensive — should not happen given the FK + article_count invariant.
        members = []

    if is_multi and story.synthesis:
        syn = story.synthesis or {}
        headline = (syn.get("headline") or "").strip() or "(no headline)"
        summary  = (syn.get("summary")  or "").strip()
        topics   = list(syn.get("topics") or [])
    elif is_multi and not story.synthesis:
        # Multi-source story whose synthesis hasn't run yet. Treat it like
        # a singleton fallback using the oldest member's content.
        first = members[0]
        headline = (first.title or "").strip() or "(no headline)"
        summary  = _first_member_summary(first)
        topics   = list(story.topics or [])
    else:
        # Singleton
        first = members[0] if members else None
        if first:
            headline = (first.title or "").strip() or "(no headline)"
            summary  = _first_member_summary(first)
            topics   = list(first.topics or [])
        else:                                       # pragma: no cover
            headline = "(no content)"
            summary  = ""
            topics   = []

    # source_ids: distinct sources, in insertion order = chronological order
    source_ids: list[str] = []
    seen: set[str] = set()
    for m in members:
        if m.source and m.source not in seen:
            source_ids.append(m.source)
            seen.add(m.source)
        if len(source_ids) >= MAX_SOURCE_IDS_IN_LIST:
            break

    primary_source = source_ids[0] if source_ids else None

    return StoryCard(
        id=story.id,
        is_multi_source=is_multi,
        headline=headline,
        summary_preview=_truncate_preview(summary),
        topics=topics,
        article_count=story.article_count or 0,
        source_ids=source_ids,
        primary_source=primary_source,
        first_seen_at=story.first_seen_at,
        last_seen_at=story.last_seen_at,
    )


def _story_to_detail(db: Session, story: Story) -> StoryDetail:
    """Same as _story_to_card but adds full summary + key_points + entities
    + every member article expanded."""
    card = _story_to_card(db, story)
    members = _members_for_story(db, story.id)

    is_multi = (story.article_count or 0) >= 2
    if is_multi and story.synthesis:
        syn = story.synthesis or {}
        full_summary = (syn.get("summary") or "").strip()
        key_points   = list(syn.get("key_points") or [])
        entities     = list(syn.get("entities") or [])
    else:
        # Singleton or unsynthesised multi: use first member's full summary.
        full_summary = _first_member_summary(members[0]) if members else ""
        key_points   = []
        entities     = []

    article_sources = [
        ArticleSource(
            id=a.id,
            source=a.source,
            source_display_name=source_display_name(a.source),
            url=a.url,
            title=a.title or "",
            author=a.author,
            published_at=a.published_at,
            rss_summary=(
                a.summary
                or (a.raw_metadata.get("summary") if a.raw_metadata else None)
                or (a.raw_metadata.get("description") if a.raw_metadata else None)
            ),
        )
        for a in members
    ]

    return StoryDetail(
        **card.model_dump(),
        summary=full_summary,
        key_points=key_points,
        entities=entities,
        articles=article_sources,
    )


def _cutoff(hours: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


# ---------------------------------------------------------------------------
# Public API: list endpoints
# ---------------------------------------------------------------------------

def get_top_stories(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    hours: int = DEFAULT_TOP_HOURS,
) -> StoryListResponse:
    """Multi-source stories only, sorted by (article_count DESC, last_seen_at DESC).
    The headline view: only stories with cross-source corroboration appear."""
    cutoff = _cutoff(hours)
    base = (
        select(Story)
        .where(Story.article_count >= 2)
        .where(Story.last_seen_at >= cutoff)
        .order_by(desc(Story.article_count), desc(Story.last_seen_at))
    )

    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar() or 0

    stmt = base.limit(limit).offset(offset)
    stories = list(db.execute(stmt).scalars().all())

    items = [_story_to_card(db, s) for s in stories]
    next_off = offset + limit if (offset + limit) < total else None

    return StoryListResponse(
        items=items,
        next_offset=next_off,
        total_in_window=total,
    )


def get_all_stories(
    db: Session,
    limit: int = 100,
    offset: int = 0,
    hours: int = DEFAULT_ALL_HOURS,
) -> StoryListResponse:
    """Chronological feed of everything (multi + singleton), newest first.
    The All News tab consumes this."""
    cutoff = _cutoff(hours)
    base = (
        select(Story)
        .where(Story.last_seen_at >= cutoff)
        .order_by(desc(Story.last_seen_at))
    )

    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar() or 0

    stmt = base.limit(limit).offset(offset)
    stories = list(db.execute(stmt).scalars().all())

    items = [_story_to_card(db, s) for s in stories]
    next_off = offset + limit if (offset + limit) < total else None

    return StoryListResponse(
        items=items,
        next_offset=next_off,
        total_in_window=total,
    )


def get_topic_feed(
    db: Session,
    topic: str,
    multi_limit: int = 50,
    singletons_n: int = DEFAULT_PER_TOPIC,
    hours: int = DEFAULT_TOPIC_HOURS,
) -> TopicFeedResponse:
    """Curated per-topic mix: every multi-source story tagged with this topic
    + the top-N singletons scored by agent.singleton_ranker.

    Topic-tagging signal:
      - multi-source stories: synthesis->'topics' (LLM-classified)
      - singletons: article.topics (LLM-classified via per-article summarizer)

    Both use the same ALLOWED_TOPICS taxonomy so the routing is consistent."""
    topic = topic.lower().strip()
    if topic not in ALLOWED_TOPICS:
        return TopicFeedResponse(topic=topic, multi_stories=[], top_singletons=[])

    cutoff = _cutoff(hours)

    # Multi-source stories: synthesis IS NOT NULL AND synthesis->'topics' contains topic.
    # The Postgres `?` operator on a jsonb array tests if a string is an element.
    multi_stmt = (
        select(Story)
        .where(Story.article_count >= 2)
        .where(Story.last_seen_at >= cutoff)
        .where(Story.synthesis.isnot(None))
        .where(text("synthesis->'topics' ? :topic").bindparams(topic=topic))
        .order_by(desc(Story.article_count), desc(Story.last_seen_at))
        .limit(multi_limit)
    )
    multi_stories_rows = list(db.execute(multi_stmt).scalars().all())
    multi_cards = [_story_to_card(db, s) for s in multi_stories_rows]

    # Top-N singletons via the ranker (uses article.topics + the
    # recency × authority × depth scoring).
    scored = rank_singletons_one_topic(db, topic=topic, per_topic=singletons_n)
    # Map ScoredArticle → StoryCard via its singleton story
    singleton_cards: list[StoryCard] = []
    for s in scored:
        article = s.article
        if article.story_id is None:
            continue
        story = db.get(Story, article.story_id)
        if story is None:
            continue
        singleton_cards.append(_story_to_card(db, story))

    return TopicFeedResponse(
        topic=topic,
        multi_stories=multi_cards,
        top_singletons=singleton_cards,
    )


def get_story_detail(db: Session, story_id: int) -> Optional[StoryDetail]:
    """Single story + every member article in chronological order.
    Returns None if the story doesn't exist."""
    story = db.get(Story, story_id)
    if story is None:
        return None
    return _story_to_detail(db, story)
