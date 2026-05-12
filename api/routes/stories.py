"""
api/routes/stories.py — Story list + detail endpoints.

Backed by api.services. The route layer is thin: parse query params,
delegate to services, return.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.deps import db_session
from api.schemas import StoryDetail, StoryListResponse
from api.services import (
    DEFAULT_ALL_HOURS,
    DEFAULT_TOP_HOURS,
    get_all_stories,
    get_story_detail,
    get_top_stories,
)


router = APIRouter(prefix="/stories", tags=["stories"])


@router.get(
    "/top",
    response_model=StoryListResponse,
    summary="Multi-source stories only, sorted by source-count then recency.",
)
def list_top_stories(
    db: Session = Depends(db_session),
    limit:  int = Query(50,  ge=1, le=200),
    offset: int = Query(0,   ge=0),
    hours:  int = Query(DEFAULT_TOP_HOURS, ge=1, le=24 * 30,
                        description="Lookback window for last_seen_at."),
) -> StoryListResponse:
    """The Top Stories tab feed. Only multi-source clusters surface here."""
    return get_top_stories(db, limit=limit, offset=offset, hours=hours)


@router.get(
    "/all",
    response_model=StoryListResponse,
    summary="Chronological feed of every story (multi + singleton).",
)
def list_all_stories(
    db: Session = Depends(db_session),
    limit:  int = Query(100, ge=1, le=200),
    offset: int = Query(0,   ge=0),
    hours:  int = Query(DEFAULT_ALL_HOURS, ge=1, le=24 * 30,
                        description="Lookback window for last_seen_at."),
) -> StoryListResponse:
    """The All News tab feed. Sorted by last_seen_at DESC, includes singletons."""
    return get_all_stories(db, limit=limit, offset=offset, hours=hours)


@router.get(
    "/{story_id}",
    response_model=StoryDetail,
    summary="One story + every member article, chronologically ordered.",
    responses={404: {"description": "Story not found."}},
)
def story_detail(
    story_id: int,
    db: Session = Depends(db_session),
) -> StoryDetail:
    """Backs the Story Detail screen — full synthesis + source timeline."""
    detail = get_story_detail(db, story_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Story {story_id} not found.",
        )
    return detail
