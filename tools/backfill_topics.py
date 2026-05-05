"""
tools/backfill_topics.py — Phase 2 one-shot.

Stamps `topics` on every existing row of articles based on its `source`,
reading the topic mapping from config/sources.json. Idempotent: rows that
already have the right topic array stay unchanged; re-runs report 0
updates.

Without this backfill, every existing row has `topics = '{}'` (the default
from the additive ALTER), and the digest's per-topic queries would treat
them as untagged.

Run:
    python tools/backfill_topics.py            # apply
    python tools/backfill_topics.py --dry-run  # report counts only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select, update

from app.database.db import get_db
from app.database.models import Article


PROJECT_ROOT  = Path(__file__).resolve().parents[1]
SOURCES_FILE  = PROJECT_ROOT / "config" / "sources.json"


def _load_source_topics() -> dict[str, list[str]]:
    """Map source_id -> topics for blog sources."""
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    out: dict[str, list[str]] = {}
    for src in cfg.get("blogs", []):
        out[src["id"]] = list(src.get("topics", []))
    return out


def _backfill_articles(db, source_topics: dict[str, list[str]], dry_run: bool) -> tuple[int, int]:
    """Returns (eligible_pre, updated)."""
    eligible_pre = db.execute(
        select(func.count()).select_from(Article).where(Article.topics == [])
    ).scalar() or 0

    if dry_run or eligible_pre == 0:
        return eligible_pre, 0

    updated = 0
    for source_id, topics in source_topics.items():
        if not topics:
            continue
        result = db.execute(
            update(Article)
            .where(Article.source == source_id)
            .where(Article.topics == [])
            .values(topics=topics)
        )
        updated += result.rowcount or 0
    return eligible_pre, updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Count eligible rows but make no changes.")
    args = parser.parse_args()

    print(f"=== backfill topics ({'DRY RUN' if args.dry_run else 'APPLY'}) ===\n")

    source_topics = _load_source_topics()
    print(f"source_topics: {len(source_topics)} entries from sources.json (id-keyed, for blogs)\n")

    with get_db() as db:
        a_pre, a_upd = _backfill_articles(db, source_topics, args.dry_run)

    print(f"  {'table':<20} {'untagged_pre':>14} {'updated':>10}")
    print(f"  {'-'*20} {'-'*14} {'-'*10}")
    print(f"  {'articles':<20} {a_pre:>14} {a_upd:>10}")
    print()

    if args.dry_run:
        print("Dry run - no changes made.")
    else:
        print(f"Done. {a_upd} row(s) backfilled.")

    # Post-state sanity: every row should now be tagged (assuming its source
    # has topics in config). Log how many remain untagged.
    with get_db() as db:
        a_post = db.execute(select(func.count()).select_from(Article)
                            .where(Article.topics == [])).scalar() or 0
    print(f"\npost-state untagged: articles={a_post}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
