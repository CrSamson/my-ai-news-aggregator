"""
runner.py - orchestrates every scraper for a given time window.

Scrapes blog and paper sources defined in `config/sources.json`.

Usage:
    from runner import Runner
    runner = Runner(hours=24)
    report = runner.run()

Returned report shape:
    {
        "generated_at": "...",
        "hours": 24,
        "blogs":  {"sources": {sid: {fetched, inserted, updated, error}}, "total_fetched": N},
        "papers": {"sources": {sid: {fetched, inserted, updated, error}}, "total_fetched": N},
    }
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.database.crud import (
    merge_hf_daily_papers,
    upsert_articles,
    upsert_papers,
)
from app.database.db import get_db
from scrapers import (
    ArxivScraper,
    HfDailyScraper,
    RssBlogScraper,
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONFIG_DIR    = Path(__file__).parent / "config"
SOURCES_FILE  = CONFIG_DIR / "sources.json"


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------

def load_blog_sources(path: Path = SOURCES_FILE) -> list[dict]:
    """Load enabled blog source configs from sources.json."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [s for s in data.get("blogs", []) if s.get("enabled", True)]


def load_paper_sources(path: Path = SOURCES_FILE) -> list[dict]:
    """Load enabled paper source configs from sources.json."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [s for s in data.get("papers", []) if s.get("enabled", True)]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class Runner:
    """
    Runs every configured scraper for a given time window and returns a
    unified report dict.
    """

    def __init__(self, hours: int = 24) -> None:
        self.hours = hours

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self) -> dict:
        print(f"\n{'='*60}")
        print(f"  AI News Aggregator - last {self.hours}h")
        print(f"{'='*60}\n")

        blog_data  = self._scrape_and_save_blogs()
        paper_data = self._scrape_and_save_papers()

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "hours":        self.hours,
            "blogs":        blog_data,
            "papers":       paper_data,
        }

        self._print_summary(report)
        return report

    # ------------------------------------------------------------------
    # Blogs (generic, driven by sources.json)
    # ------------------------------------------------------------------

    def _scrape_and_save_blogs(self) -> dict:
        sources = load_blog_sources()
        print(f"[1/2] Scraping {len(sources)} blog source(s) ...")

        by_source: dict[str, dict] = {}

        with get_db() as db:
            for cfg in sources:
                sid = cfg["id"]
                try:
                    scraper = RssBlogScraper(cfg)
                    items   = scraper.fetch(hours=self.hours)
                    stats   = upsert_articles(db, items)
                    by_source[sid] = {
                        "fetched":  len(items),
                        "inserted": stats["inserted"],
                        "updated":  stats["updated"],
                        "error":    None,
                    }
                    print(
                        f"      {sid:24s}  fetched={len(items):3d}  "
                        f"inserted={stats['inserted']:3d}  updated={stats['updated']:3d}"
                    )
                except Exception as e:  # noqa: BLE001 - per-source isolation
                    by_source[sid] = {
                        "fetched": 0, "inserted": 0, "updated": 0,
                        "error":   f"{type(e).__name__}: {e}",
                    }
                    print(f"      {sid:24s}  ERROR: {e}")

        total = sum(r["fetched"] for r in by_source.values())
        print(f"      Total fetched across blogs: {total}\n")
        return {"sources": by_source, "total_fetched": total}

    # ------------------------------------------------------------------
    # Papers (arXiv + HuggingFace Daily, driven by sources.json papers[])
    # ------------------------------------------------------------------

    def _scrape_and_save_papers(self) -> dict:
        sources = load_paper_sources()
        print(f"[2/2] Scraping {len(sources)} paper source(s) ...")

        by_source: dict[str, dict] = {}

        with get_db() as db:
            for cfg in sources:
                sid   = cfg["id"]
                ptype = cfg.get("type")
                try:
                    if ptype == "arxiv":
                        items = ArxivScraper(cfg).fetch(hours=self.hours)
                        stats = upsert_papers(db, items)
                    elif ptype == "hf_daily":
                        items = HfDailyScraper(cfg).fetch(hours=self.hours)
                        stats = merge_hf_daily_papers(db, items)
                    else:
                        raise ValueError(f"unknown paper source type: {ptype!r}")
                    by_source[sid] = {
                        "fetched":  len(items),
                        "inserted": stats["inserted"],
                        "updated":  stats["updated"],
                        "skipped":  stats.get("skipped", 0),
                        "error":    None,
                    }
                    print(
                        f"      {sid:24s}  fetched={len(items):3d}  "
                        f"inserted={stats['inserted']:3d}  updated={stats['updated']:3d}"
                    )
                except Exception as e:  # noqa: BLE001 - per-source isolation
                    by_source[sid] = {
                        "fetched": 0, "inserted": 0, "updated": 0, "skipped": 0,
                        "error":   f"{type(e).__name__}: {e}",
                    }
                    print(f"      {sid:24s}  ERROR: {e}")

        total = sum(r["fetched"] for r in by_source.values())
        print(f"      Total fetched across papers: {total}\n")
        return {"sources": by_source, "total_fetched": total}

    # ------------------------------------------------------------------
    # Pretty-print
    # ------------------------------------------------------------------

    @staticmethod
    def _print_summary(report: dict) -> None:
        print(f"{'='*60}")
        print("  SUMMARY")
        print(f"{'='*60}\n")

        def _print_source_block(label: str, block: dict) -> None:
            print(f"  {label} ({len(block['sources'])}, "
                  f"total fetched={block['total_fetched']}):")
            for sid, stats in block["sources"].items():
                tag = "ERR" if stats["error"] else " ok"
                print(f"    [{tag}] {sid:24s}  "
                      f"fetched={stats['fetched']:3d}  "
                      f"inserted={stats['inserted']:3d}  "
                      f"updated={stats['updated']:3d}")
                if stats["error"]:
                    print(f"          -> {stats['error']}")

        _print_source_block("Blog sources", report["blogs"])
        print()
        _print_source_block("Paper sources", report["papers"])

        print(f"\n{'='*60}\n")
