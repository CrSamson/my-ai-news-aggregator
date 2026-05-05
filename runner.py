"""
runner.py - orchestrates blog scraping + embedding for a given time window.

Pipeline:
    1. Scrape every enabled blog source defined in `config/sources.json`.
    2. Embed every article whose `embedding` column is still NULL.

Usage:
    from runner import Runner
    runner = Runner(hours=24)
    report = runner.run()

Returned report shape:
    {
        "generated_at": "...",
        "hours": 24,
        "blogs":  {"sources": {sid: {fetched, inserted, updated, error}}, "total_fetched": N},
        "embed":  {"embedded": N, "batches": M, "error": str | None},
    }
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.database.crud import (
    get_unembedded_articles,
    set_article_embedding,
    upsert_articles,
)
from app.database.db import get_db
from scrapers import RssBlogScraper


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONFIG_DIR    = Path(__file__).parent / "config"
SOURCES_FILE  = CONFIG_DIR / "sources.json"


# Number of articles per embedding batch. Larger = faster on GPU, more
# memory; on a laptop CPU 64 is the sweet spot for MiniLM.
EMBED_BATCH_SIZE: int = 64


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------

def load_blog_sources(path: Path = SOURCES_FILE) -> list[dict]:
    """Load enabled blog source configs from sources.json."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [s for s in data.get("blogs", []) if s.get("enabled", True)]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class Runner:
    """
    Runs every configured blog scraper for a given time window, then embeds
    any newly-inserted (or previously-unembedded) articles. Returns a
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
        embed_data = self._embed_new_articles()

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "hours":        self.hours,
            "blogs":        blog_data,
            "embed":        embed_data,
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
    # Embedding (Phase 3)
    # ------------------------------------------------------------------

    def _embed_new_articles(self) -> dict:
        """Embed every article whose `embedding` is still NULL.

        Loads the embedder lazily so a scrape-only smoke test doesn't pay
        the import cost of sentence-transformers / torch. Failure here is
        non-fatal: a per-batch exception is logged and the rest of the
        articles continue. Articles that fail stay NULL and are picked up
        on the next run.
        """
        # Lazy import: ~2-3 s of torch startup avoided when embedding is a no-op.
        from agent.embedder import article_text, get_default_embedder

        with get_db() as db:
            articles = get_unembedded_articles(db)
            n = len(articles)
            print(f"[2/2] Embedding {n} unembedded article(s) ...")

            if n == 0:
                print(f"      Nothing to embed.\n")
                return {"embedded": 0, "batches": 0, "error": None}

            try:
                embedder = get_default_embedder()
            except Exception as e:  # noqa: BLE001 - selector failure is recoverable
                print(f"      ERROR: could not load embedder: {e}\n")
                return {"embedded": 0, "batches": 0, "error": f"{type(e).__name__}: {e}"}

            embedded = 0
            batches  = 0
            for start in range(0, n, EMBED_BATCH_SIZE):
                chunk = articles[start:start + EMBED_BATCH_SIZE]
                texts = [article_text(a) for a in chunk]
                try:
                    vectors = embedder.embed(texts)
                except Exception as e:  # noqa: BLE001 - per-batch isolation
                    print(f"      batch {batches + 1} failed: {e}")
                    batches += 1
                    continue
                for article, vec in zip(chunk, vectors):
                    set_article_embedding(db, article.id, vec)
                db.flush()
                embedded += len(chunk)
                batches  += 1
                print(f"      batch {batches}: embedded={len(chunk)} "
                      f"(running total {embedded}/{n})")

        print(f"      Total embedded: {embedded}/{n} across {batches} batch(es).\n")
        return {"embedded": embedded, "batches": batches, "error": None}

    # ------------------------------------------------------------------
    # Pretty-print
    # ------------------------------------------------------------------

    @staticmethod
    def _print_summary(report: dict) -> None:
        print(f"{'='*60}")
        print("  SUMMARY")
        print(f"{'='*60}\n")

        block = report["blogs"]
        print(f"  Blog sources ({len(block['sources'])}, "
              f"total fetched={block['total_fetched']}):")
        for sid, stats in block["sources"].items():
            tag = "ERR" if stats["error"] else " ok"
            print(f"    [{tag}] {sid:24s}  "
                  f"fetched={stats['fetched']:3d}  "
                  f"inserted={stats['inserted']:3d}  "
                  f"updated={stats['updated']:3d}")
            if stats["error"]:
                print(f"          -> {stats['error']}")

        embed = report["embed"]
        tag = "ERR" if embed["error"] else " ok"
        print(f"\n  Embeddings: [{tag}] embedded={embed['embedded']}, "
              f"batches={embed['batches']}")
        if embed["error"]:
            print(f"          -> {embed['error']}")

        print(f"\n{'='*60}\n")
