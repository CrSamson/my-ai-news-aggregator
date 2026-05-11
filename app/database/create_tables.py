"""
app/database/create_tables.py — Idempotent table initialisation script.

Run once (or any number of times) to create all tables in the database.
Tables that already exist are left untouched.

Usage:
    python app/database/create_tables.py
"""

import sys
from pathlib import Path

# Allow running from the project root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import inspect, text

from app.database.db import engine
from app.database.models import (  # noqa: F401
    Base,
    Article,
    EMBEDDING_DIM,
    Story,
)


# Postgres extensions required by the schema. Enabled before create_all so
# the Vector(N) column type resolves on a fresh DB.
_REQUIRED_EXTENSIONS: list[str] = [
    "vector",   # pgvector — backs articles.embedding
]


# Columns whose type changed and need to be dropped before _ADDITIVE_COLUMNS
# can re-add them with the new type. Each entry: (table, column, old_type)
# — the column is dropped only if its current type exactly matches old_type.
# Carried for one or two migrations after a type change, then prunable.
#
# Indices on the column are also dropped here; the relevant entry of
# _EXTRA_INDICES will rebuild them after the column is re-added.
_MIGRATED_COLUMNS: list[tuple[str, str, str, list[str]]] = [
    # MiniLM -> OpenAI text-embedding-3-small swap (2026-05-05).
    # Drops 384-dim embedding column + HNSW index so additive ALTER
    # below re-adds the column at vector(1536).
    ("articles", "embedding", "vector(384)", ["ix_articles_embedding_hnsw"]),
]


# (table, column, ddl-fragment) — kept here so re-running this script is enough
# to bring an existing DB in line with the current models.
_ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    # Digest send-state. NULL = not yet emailed; set to NOW() once a digest
    # containing the row is successfully sent. See agent/digest.py.
    ("articles", "digest_sent_at", "TIMESTAMPTZ"),
    # Topic tags inherited from source config in sources.json.
    # Empty array on existing rows until tools/backfill_topics.py runs.
    ("articles", "topics",         "VARCHAR[] NOT NULL DEFAULT ARRAY[]::varchar[]"),
    # Per-article OpenAI embedding. NULL until agent/embedder runs.
    ("articles", "embedding",      f"VECTOR({EMBEDDING_DIM})"),
    # FK into stories.id. NULL until agent/clusterer runs. ON DELETE SET
    # NULL so deleting a story doesn't cascade to its member articles.
    ("articles", "story_id",       "BIGINT REFERENCES stories(id) ON DELETE SET NULL"),
]


# Indices that aren't expressed in the ORM model. Created with IF NOT EXISTS
# so re-runs are idempotent.
_EXTRA_INDICES: list[tuple[str, str]] = [
    # HNSW index for cosine-similarity nearest-neighbour search on the
    # article embedding.
    (
        "ix_articles_embedding_hnsw",
        "CREATE INDEX IF NOT EXISTS ix_articles_embedding_hnsw "
        "ON articles USING hnsw (embedding vector_cosine_ops)",
    ),
    # HNSW index for cosine-similarity nearest-neighbour search on story
    # centroids. The clusterer's hot path is "find the closest active
    # story to this new article", which is exactly this index's job.
    (
        "ix_stories_centroid_hnsw",
        "CREATE INDEX IF NOT EXISTS ix_stories_centroid_hnsw "
        "ON stories USING hnsw (centroid vector_cosine_ops)",
    ),
    # Plain btree on story_id so 'get every article belonging to story X'
    # is fast. ORM-level index=True on the column also produces this; the
    # CREATE INDEX IF NOT EXISTS here is a belt-and-suspenders for hand-run
    # migrations.
    (
        "ix_articles_story_id",
        "CREATE INDEX IF NOT EXISTS ix_articles_story_id "
        "ON articles (story_id)",
    ),
]


# Tables removed from the schema. DROPped on every run so a stale Neon DB
# cleans itself up. Safe to keep here forever — DROP IF EXISTS is a no-op
# once the table is gone. Carried for one or two migrations, then prunable.
_DROPPED_TABLES: list[str] = [
    "youtube_videos",
    "papers",
]


def _current_column_type(conn, table: str, column: str) -> str | None:
    """Return the current Postgres type string for `table.column`, or None
    if the column doesn't exist. Uses information_schema so it works for
    both standard types and pgvector's vector(N) type."""
    row = conn.execute(text(
        """
        SELECT format_type(a.atttypid, a.atttypmod) AS data_type
          FROM pg_attribute a
          JOIN pg_class c ON a.attrelid = c.oid
          JOIN pg_namespace n ON c.relnamespace = n.oid
         WHERE c.relname = :table
           AND a.attname = :column
           AND a.attnum > 0
           AND NOT a.attisdropped
           AND n.nspname = ANY (current_schemas(false))
        """
    ), {"table": table, "column": column}).first()
    return row[0] if row else None


def main() -> None:
    print(f"Connecting to: {engine.url}\n")

    # Step 1: enable required extensions BEFORE create_all so Vector(N)
    # column types resolve on a fresh database.
    with engine.begin() as conn:
        for ext in _REQUIRED_EXTENSIONS:
            conn.execute(text(f'CREATE EXTENSION IF NOT EXISTS {ext}'))
            print(f"  [EXT OK]     {ext}")

    # Step 2: handle column type migrations BEFORE create_all so the
    # subsequent additive ALTER picks up the new type. Drop indices first
    # because the column DROP would fail otherwise.
    with engine.begin() as conn:
        for table, column, old_type, drop_indices in _MIGRATED_COLUMNS:
            current = _current_column_type(conn, table, column)
            if current is None:
                continue                  # column doesn't exist; nothing to migrate
            if current.lower() != old_type.lower():
                continue                  # already migrated or unrelated type
            for idx in drop_indices:
                conn.execute(text(f'DROP INDEX IF EXISTS {idx}'))
                print(f"  [DROPPED IX] {idx}")
            conn.execute(text(f'ALTER TABLE {table} DROP COLUMN {column}'))
            print(f"  [DROPPED COL] {table}.{column} (was {old_type})")

    inspector   = inspect(engine)
    before      = set(inspector.get_table_names())
    all_tables  = set(Base.metadata.tables.keys())

    Base.metadata.create_all(engine)

    inspector   = inspect(engine)          # refresh after create
    after       = set(inspector.get_table_names())
    created     = after - before
    preexisting = all_tables - created

    for table in sorted(created):
        print(f"  [CREATED]    {table}")
    for table in sorted(preexisting):
        print(f"  [EXISTS]     {table}")

    # ADD COLUMN IF NOT EXISTS keeps existing rows + lets this script stay idempotent
    with engine.begin() as conn:
        for table, column, ddl in _ADDITIVE_COLUMNS:
            if table not in after:
                continue
            conn.execute(text(
                f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}'
            ))
            print(f"  [COLUMN OK]  {table}.{column}")

        for index_name, ddl in _EXTRA_INDICES:
            conn.execute(text(ddl))
            print(f"  [INDEX OK]   {index_name}")

        for table in _DROPPED_TABLES:
            if table in after:
                conn.execute(text(f'DROP TABLE IF EXISTS {table}'))
                print(f"  [DROPPED]    {table}")

    print(f"\nDone. {len(created)} table(s) created, {len(preexisting)} already existed.")


if __name__ == "__main__":
    main()
