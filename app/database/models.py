"""
app/database/models.py — SQLAlchemy ORM models.

Tables:
  • Article — any blog/news post from any source. Conflict key: url.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Article(Base):
    """
    Any blog / news post from any source.

    Conflict key: `url` (unique). One row per canonical URL.
    `source` identifies which entry of config/sources.json produced the row,
    e.g. 'anthropic_news', 'openai_news', 'aws_ml'.
    """

    __tablename__ = "articles"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)

    source          = Column(String(64),  nullable=False, index=True)
    url             = Column(Text,        nullable=False, unique=True)   # conflict key
    title           = Column(Text,        nullable=False)
    author          = Column(Text,        nullable=True)
    published_at    = Column(DateTime(timezone=True), nullable=True, index=True)

    summary         = Column(Text,        nullable=True)                 # LLM-generated, set later
    content_md      = Column(Text,        nullable=True)                 # Docling output
    content_fetched = Column(Boolean,     nullable=False,
                             default=False, server_default=text("false"))

    # NULL = not yet included in a sent digest. Set to NOW() once an email
    # containing this row goes out successfully. Filtered by the digest queries
    # so the same row never ships in two emails.
    digest_sent_at  = Column(DateTime(timezone=True), nullable=True)

    # Topic tags inherited from sources.json config (e.g. ["ai", "technology"]).
    # Populated at insert time; refreshed on conflict so config edits propagate.
    topics          = Column(ARRAY(String), nullable=False,
                             server_default=text("ARRAY[]::varchar[]"))

    # Original feedparser entry, kept verbatim so we don't lose anything.
    raw_metadata    = Column(JSONB,       nullable=False,
                             default=dict, server_default=text("'{}'::jsonb"))

    created_at      = Column(DateTime(timezone=True),
                             server_default=func.now(), nullable=False)
    updated_at      = Column(DateTime(timezone=True),
                             server_default=func.now(), onupdate=func.now(),
                             nullable=False)

    def __repr__(self) -> str:
        return f"<Article id={self.id} source={self.source!r} title={self.title!r}>"
