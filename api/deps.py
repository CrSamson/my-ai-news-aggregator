"""
api/deps.py — FastAPI dependencies.

`db_session` yields a SQLAlchemy Session. Wrapping our existing
`app.database.db.get_db()` context manager into a generator so it
plugs into FastAPI's `Depends(...)` mechanism.

Future hook: `current_user` once auth lands. For now public read-only.
"""
from __future__ import annotations

from typing import Generator

from sqlalchemy.orm import Session

from app.database.db import get_db


def db_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session for the duration of a request."""
    with get_db() as db:
        yield db
