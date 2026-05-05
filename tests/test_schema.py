"""
tests/test_schema.py — schema-level smoke test.

Asserts (using SQLAlchemy reflection, not pytest):
  - table `articles` exists
  - `articles.url` has a unique constraint or unique index

Plain script — no test framework dependency. Exits 0 on pass, 1 on failure.

Run:
    python tests/test_schema.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable when running as a path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect

from app.database.db import engine


def _has_unique_on(insp, table: str, column: str) -> bool:
    """True if `column` is covered by either a unique constraint or a unique index."""
    for ix in insp.get_indexes(table):
        if ix.get("unique") and column in (ix.get("column_names") or []):
            return True
    for uc in insp.get_unique_constraints(table):
        if column in (uc.get("column_names") or []):
            return True
    return False


def main() -> int:
    insp = inspect(engine)
    table_names = set(insp.get_table_names())
    failures: list[str] = []

    if "articles" in table_names:
        print("[ok] table 'articles' exists")
    else:
        failures.append("missing table: articles")

    if "articles" in table_names:
        if _has_unique_on(insp, "articles", "url"):
            print("[ok] articles.url is unique")
        else:
            failures.append("articles.url is not unique")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nAll schema checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
