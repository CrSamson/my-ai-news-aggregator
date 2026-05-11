"""
scrapers/schemas.py - Pydantic v2 schemas for scraper output.

These are the validated payloads scrapers produce; the CRUD layer maps
them to Article rows.

Two intentional design notes:
  - `summary` is always None at scrape time. It's the LLM-output column
    in the DB; the scraper never writes it. The RSS feed's <description>
    goes into raw_metadata instead.
  - `frozen=True` makes scraper outputs immutable once produced.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BlogArticle(BaseModel):
    """One blog/news entry from any RSS source."""

    source         : str                  # source.id from config/sources.json
    url            : str
    title          : str
    author         : str | None = None
    published_at   : datetime | None = None
    summary        : str | None = None    # LLM output, set later
    content_md     : str | None = None    # Docling output
    content_fetched: bool = False
    topics         : list[str] = []       # from source_config["topics"]
    raw_metadata   : dict = {}

    model_config = {"frozen": True}
