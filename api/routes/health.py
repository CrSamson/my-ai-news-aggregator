"""
api/routes/health.py — uptime probe.

Used by:
  - Modal's run-history dashboard (auto-pinged on web-endpoint cold-start)
  - the mobile app's "Couldn't reach Brevio" error state
  - any monitoring / uptime checker you point at this URL
"""
from __future__ import annotations

from fastapi import APIRouter

from api.schemas import Health


router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health)
def health() -> Health:
    return Health()
