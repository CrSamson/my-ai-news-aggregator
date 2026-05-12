"""
agent/singleton_ranker.py — Score and pick the top-N singleton articles per topic.

92% of stories on Neon are singletons (one-article clusters). Showing all of
them in the app would drown out the multi-source stories that are the wedge.
This module scores every singleton by

    score = recency_decay × source_authority × content_depth

and exposes a function that returns the top N (default 5) per topic.

Score components, all derived from existing data — no schema changes:

  recency_decay      exp(-age_hours / 24)
                     half-life 24h, floor 0.05 so anything from this week
                     still scores non-trivially.

  source_authority   per-source multiplier from SOURCE_AUTHORITY below.
                     - 1.5×: primary AI-lab feeds (Anthropic, OpenAI,
                             Google Research, AWS ML, NVIDIA, BAIR,
                             CMU, MIT, Meta AI — they break their own news)
                     - 1.3×: specialist tech/science publications with
                             editorial standards (TechCrunch, The Verge,
                             Ars Technica, Wired, Nature, sciencedaily,
                             phys_org, Quanta)
                     - 1.0×: major general-news outlets (BBC, CNBC,
                             The Independent, CNA, Forbes, Yahoo Finance)
                     - 0.9×: unknown source (configured fallback)

  content_depth      bonus for richer raw input:
                     - content_md > 500 chars:   1.3×
                     - llm summary > 50 chars:   1.1×
                     - else:                     1.0×

Per-topic selection: for each of ALLOWED_TOPICS, filter singletons whose
`articles.topics` array contains the topic, sort by score desc, take top N.
A multi-topic article (e.g. ["ai", "business"]) can appear in BOTH lists —
that mirrors how the same story shows up across the Topics-tab filter chips
in the UI spec.

CLI for backtesting:
    .venv/Scripts/python.exe -m agent.singleton_ranker
    .venv/Scripts/python.exe -m agent.singleton_ranker --per-topic 5
    .venv/Scripts/python.exe -m agent.singleton_ranker --topic ai
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import Article, Story
from agent.summarizer import ALLOWED_TOPICS


# ---------------------------------------------------------------------------
# Scoring config
# ---------------------------------------------------------------------------

# Per-source authority multipliers. Anything not in the map gets DEFAULT_AUTHORITY.
SOURCE_AUTHORITY: dict[str, float] = {
    # Tier S — primary AI labs / research institutions (break their own news)
    "anthropic_news":         1.5,
    "anthropic_research":     1.5,
    "anthropic_engineering":  1.5,
    "openai_news":            1.5,
    "google_research":        1.5,
    "aws_ml":                 1.5,
    "nvidia_developer":       1.5,
    "meta_ai":                1.5,
    "bair":                   1.5,
    "cmu_ml":                 1.5,
    "mit_news":               1.5,

    # Tier A — specialist tech/science publications with editorial standards
    "techcrunch_ai":          1.3,
    "the_verge":              1.3,
    "ars_technica":           1.3,
    "wired":                  1.3,
    "nature":                 1.3,
    "sciencedaily":           1.3,
    "phys_org":               1.3,
    "quanta":                 1.3,

    # Tier B — major general-news outlets
    "bbc_news":               1.0,
    "cnbc":                   1.0,
    "the_independent":        1.0,
    "cna":                    1.0,
    "forbes_business":        1.0,
    "yahoo_finance":          1.0,
}

DEFAULT_AUTHORITY: float = 0.9       # unknown source

# Recency decay
HALF_LIFE_HOURS: float = 24.0
RECENCY_FLOOR:   float = 0.05

# Content depth
CONTENT_MD_BONUS_MIN_CHARS: int   = 500
CONTENT_MD_BONUS:           float = 1.3
SUMMARY_BONUS_MIN_CHARS:    int   = 50
SUMMARY_BONUS:              float = 1.1

# Default cap on singletons per topic (matches user's "5 per topic" target)
DEFAULT_PER_TOPIC:          int   = 5


@dataclass
class ScoredArticle:
    """Container for an article + its components broken down for inspection."""
    article: Article
    score:   float
    recency: float
    authority: float
    depth:   float

    def __repr__(self) -> str:                                # pragma: no cover
        return (f"<ScoredArticle id={self.article.id} score={self.score:.3f} "
                f"recency={self.recency:.3f} authority={self.authority:.2f} "
                f"depth={self.depth:.2f}>")


# ---------------------------------------------------------------------------
# Scoring primitives
# ---------------------------------------------------------------------------

def _recency_score(published_at: Optional[datetime],
                   now: Optional[datetime] = None) -> float:
    """Exponential decay with 24h half-life. Floor at 0.05 so older
    articles can still appear if no fresher ones cover their topic."""
    if published_at is None:
        return RECENCY_FLOOR
    if now is None:
        now = datetime.now(timezone.utc)
    age_hours = (now - published_at).total_seconds() / 3600.0
    if age_hours < 0:                # future-dated entry — treat as fresh
        age_hours = 0.0
    decay = math.exp(-age_hours / HALF_LIFE_HOURS)
    return max(decay, RECENCY_FLOOR)


def _source_authority(source: str) -> float:
    return SOURCE_AUTHORITY.get(source, DEFAULT_AUTHORITY)


def _content_depth(article: Article) -> float:
    if article.content_md and len(article.content_md) > CONTENT_MD_BONUS_MIN_CHARS:
        return CONTENT_MD_BONUS
    if article.summary and len(article.summary) > SUMMARY_BONUS_MIN_CHARS:
        return SUMMARY_BONUS
    return 1.0


def score_article(article: Article, now: Optional[datetime] = None) -> ScoredArticle:
    """Compute the singleton-ranking score for one article."""
    recency   = _recency_score(article.published_at, now=now)
    authority = _source_authority(article.source)
    depth     = _content_depth(article)
    return ScoredArticle(
        article=article,
        score=recency * authority * depth,
        recency=recency,
        authority=authority,
        depth=depth,
    )


# ---------------------------------------------------------------------------
# DB queries
# ---------------------------------------------------------------------------

def _fetch_singleton_articles(db: Session) -> list[Article]:
    """Articles whose Story has exactly one member (i.e., singletons)."""
    stmt = (
        select(Article)
        .join(Story, Article.story_id == Story.id)
        .where(Story.article_count == 1)
        .where(func.cardinality(Article.topics) > 0)
        .order_by(Article.published_at.desc().nullslast())
    )
    return list(db.execute(stmt).scalars().all())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rank_singletons_per_topic(
    db: Session,
    per_topic: int = DEFAULT_PER_TOPIC,
    now: Optional[datetime] = None,
) -> dict[str, list[ScoredArticle]]:
    """Return the top `per_topic` singletons for each topic in ALLOWED_TOPICS,
    keyed by topic name.

    An article tagged with two topics (e.g. ["ai", "business"]) appears in
    both topics' top lists — same article surfaced under both filter chips
    in the app, matching the UI spec's Topics tab behaviour.

    The dict always contains every key in ALLOWED_TOPICS, with an empty
    list if no eligible articles were found for that topic.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    singletons = _fetch_singleton_articles(db)
    scored     = [score_article(a, now=now) for a in singletons]

    by_topic: dict[str, list[ScoredArticle]] = {t: [] for t in ALLOWED_TOPICS}
    for s in scored:
        for topic in (s.article.topics or []):
            if topic in by_topic:
                by_topic[topic].append(s)

    # Sort each topic's bucket by score descending, then trim to per_topic.
    for topic, items in by_topic.items():
        items.sort(key=lambda x: x.score, reverse=True)
        by_topic[topic] = items[:per_topic]

    return by_topic


def rank_singletons_one_topic(
    db: Session,
    topic: str,
    per_topic: int = DEFAULT_PER_TOPIC,
    now: Optional[datetime] = None,
) -> list[ScoredArticle]:
    """Convenience wrapper for picking one topic's bucket."""
    all_topics = rank_singletons_per_topic(db, per_topic=per_topic, now=now)
    return all_topics.get(topic, [])


# ---------------------------------------------------------------------------
# CLI — backtest
# ---------------------------------------------------------------------------

def _format_age(dt: Optional[datetime], now: datetime) -> str:
    if dt is None:
        return "no-date"
    age_hours = (now - dt).total_seconds() / 3600.0
    if age_hours < 1:
        return "now"
    if age_hours < 24:
        return f"{int(age_hours)}h ago"
    days = age_hours / 24
    if days < 7:
        return f"{int(days)}d ago"
    return dt.strftime("%Y-%m-%d")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")          # type: ignore[attr-defined]
    except Exception:                                      # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(
        description="Score and pick top-N singletons per topic.",
    )
    parser.add_argument("--per-topic", type=int, default=DEFAULT_PER_TOPIC,
                        help=f"Number of singletons to pick per topic "
                             f"(default: {DEFAULT_PER_TOPIC}).")
    parser.add_argument("--topic", type=str, default=None,
                        help="Show only this topic (default: all topics).")
    parser.add_argument("--show-score-breakdown", action="store_true",
                        help="Print recency/authority/depth components per article.")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    # Stay inside the session for the whole print loop so detached-instance
    # errors don't trip on attribute access after session close.
    with get_db() as db:
        by_topic = rank_singletons_per_topic(db, per_topic=args.per_topic, now=now)

        topics_to_show = [args.topic] if args.topic else sorted(by_topic.keys())
        grand_total_unique: set[int] = set()

        for topic in topics_to_show:
            bucket = by_topic.get(topic, [])
            print(f"\n=== {topic.upper()} — top {len(bucket)} singleton(s) ===")
            if not bucket:
                print("  (no eligible singletons for this topic)")
                continue
            for rank, s in enumerate(bucket, start=1):
                a = s.article
                grand_total_unique.add(a.id)
                age = _format_age(a.published_at, now)
                print(f"  {rank}. [{age:>10s}] [{a.source:24s}] {a.title[:78]}")
                if args.show_score_breakdown:
                    print(f"        score={s.score:.3f}  "
                          f"recency={s.recency:.3f}  "
                          f"authority={s.authority:.2f}  "
                          f"depth={s.depth:.2f}")

        if not args.topic:
            print(f"\n=== Summary ===")
            print(f"  unique singletons selected across topics: {len(grand_total_unique)}")
            total_picked = sum(len(v) for v in by_topic.values())
            print(f"  total picks (sum across topics):          {total_picked}")
            print(f"  per-topic cap:                            {args.per_topic}")


if __name__ == "__main__":
    main()
