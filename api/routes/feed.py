"""
api/routes/feed.py — Curated per-topic feed.

The Topics tab in the app filters by one of AI / Technology / Business /
Science / General. Each topic returns:
  - every multi-source story tagged with that topic
  - the top-N singletons scored by agent.singleton_ranker

The ranker uses recency × source-authority × content-depth so we
surface ~5 high-quality singletons per topic instead of dumping all
~470 of them into the feed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from agent.singleton_ranker import DEFAULT_PER_TOPIC
from agent.summarizer import ALLOWED_TOPICS
from api.deps import db_session
from api.schemas import TopicFeedResponse
from api.services import DEFAULT_TOPIC_HOURS, get_topic_feed


router = APIRouter(prefix="/feed", tags=["feed"])


@router.get(
    "/topic/{topic}",
    response_model=TopicFeedResponse,
    summary="Multi-source stories + top-N singletons for one topic.",
    responses={404: {"description": "Unknown topic."}},
)
def topic_feed(
    topic: str,
    db: Session = Depends(db_session),
    multi_limit:  int = Query(50, ge=1, le=200),
    singletons_n: int = Query(DEFAULT_PER_TOPIC, ge=0, le=20,
                              description="How many top singletons to include. "
                                          "Set 0 to omit singletons entirely."),
    hours:        int = Query(DEFAULT_TOPIC_HOURS, ge=1, le=24 * 30),
) -> TopicFeedResponse:
    """Topics tab — one bucket per filter chip."""
    topic_lc = topic.lower().strip()
    if topic_lc not in ALLOWED_TOPICS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown topic {topic!r}. Allowed: {sorted(ALLOWED_TOPICS)}.",
        )

    return get_topic_feed(
        db,
        topic=topic_lc,
        multi_limit=multi_limit,
        singletons_n=singletons_n,
        hours=hours,
    )
