"""
runner.py - orchestrates blog scraping + embedding + clustering + synthesis.

Pipeline:
    1. Scrape every enabled blog source defined in `config/sources.json`.
    2. Embed every article whose `embedding` column is still NULL.
    3. Cluster every embedded article whose `story_id` is still NULL
       into stories (joins existing active stories or seeds new ones).
    4. Synthesise (LLM) every multi-article story whose `synthesis` is
       still NULL — produces the headline/summary/key_points/entities/
       topics JSON the digest will render.

Usage:
    from runner import Runner
    runner = Runner(hours=24)
    report = runner.run()

Returned report shape:
    {
        "generated_at": "...",
        "hours": 24,
        "blogs":     {"sources": {sid: {fetched, inserted, updated, error}}, "total_fetched": N},
        "embed":     {"embedded": N, "batches": M, "error": str | None},
        "cluster":   {"processed": N, "joined_existing": J, "seeded_new": K,
                      "final_stories": S, "error": str | None},
        "synthesis": {"processed": N, "skipped": K, "failed": F,
                      "model": str, "error": str | None},
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


# Number of articles per embedding batch. OpenAI text-embedding-3-small
# accepts up to 2048 inputs per call; 64 is a safe sweet spot — bigger
# batches surface less progress, smaller ones add round-trip latency.
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
    Runs every configured blog scraper for a given time window, embeds
    new articles, then clusters them into stories. Returns a unified
    report dict.
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

        blog_data      = self._scrape_and_save_blogs()
        embed_data     = self._embed_new_articles()
        cluster_data   = self._cluster_new_articles()
        synthesis_data = self._synthesise_stories()

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "hours":        self.hours,
            "blogs":        blog_data,
            "embed":        embed_data,
            "cluster":      cluster_data,
            "synthesis":    synthesis_data,
        }

        self._print_summary(report)
        return report

    # ------------------------------------------------------------------
    # Blogs (generic, driven by sources.json)
    # ------------------------------------------------------------------

    def _scrape_and_save_blogs(self) -> dict:
        sources = load_blog_sources()
        print(f"[1/4] Scraping {len(sources)} blog source(s) ...")

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
        the import cost. Failure here is non-fatal: a per-batch exception
        is logged and the rest of the articles continue. Articles that
        fail stay NULL and are picked up on the next run.
        """
        # Lazy import: avoid the OpenAI client construction cost when
        # there's nothing to embed.
        from agent.embedder import article_text, get_default_embedder

        with get_db() as db:
            articles = get_unembedded_articles(db)
            n = len(articles)
            print(f"[2/4] Embedding {n} unembedded article(s) ...")

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
    # Clustering (Phase 4)
    # ------------------------------------------------------------------

    def _cluster_new_articles(self) -> dict:
        """Assign every embedded article without a story_id to a story.

        Failure here is non-fatal — embedded but unclustered articles stay
        unclustered and the next runner pass retries them.
        """
        # Lazy import keeps numpy out of the path until clustering needs it.
        from agent.clusterer import run_clustering

        print("[3/4] Clustering unclustered articles ...")
        try:
            report = run_clustering()
        except Exception as e:  # noqa: BLE001
            print(f"      ERROR: clustering failed: {e}\n")
            return {
                "processed": 0, "joined_existing": 0, "seeded_new": 0,
                "final_stories": 0, "error": f"{type(e).__name__}: {e}",
            }

        print(
            f"      processed={report.processed}, "
            f"joined_existing={report.joined_existing}, "
            f"seeded_new={report.seeded_new}, "
            f"total_stories={report.final_stories} "
            f"(threshold={report.threshold:.2f}, "
            f"lookback={report.lookback_hours}h)\n"
        )
        return {
            "processed":       report.processed,
            "joined_existing": report.joined_existing,
            "seeded_new":      report.seeded_new,
            "final_stories":   report.final_stories,
            "error":           None,
        }

    # ------------------------------------------------------------------
    # Story-level LLM synthesis (Phase 5)
    # ------------------------------------------------------------------

    def _synthesise_stories(self) -> dict:
        """LLM-synthesise every multi-article story whose `synthesis` is
        still NULL. Singletons are excluded by the default `min_size=2`
        gate in run_synthesis.

        Failure here is non-fatal — stories without synthesis fall back
        to their first member's title in the digest until the next pass
        retries them.
        """
        # Lazy import so a scrape-only run doesn't construct the OpenAI client.
        from agent.story_summarizer import run_synthesis

        print("[4/4] Synthesising multi-stories ...")
        try:
            report = run_synthesis()
        except Exception as e:  # noqa: BLE001
            print(f"      ERROR: synthesis failed: {e}\n")
            return {
                "processed": 0, "skipped": 0, "failed": 0,
                "model": "", "error": f"{type(e).__name__}: {e}",
            }

        print(
            f"      processed={report.processed}, "
            f"skipped={report.skipped}, "
            f"failed={report.failed} "
            f"(model={report.model}, min_size={report.min_size})\n"
        )
        return {
            "processed": report.processed,
            "skipped":   report.skipped,
            "failed":    report.failed,
            "model":     report.model,
            "error":     None,
        }

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

        cluster = report["cluster"]
        tag = "ERR" if cluster["error"] else " ok"
        print(f"\n  Clustering: [{tag}] processed={cluster['processed']}, "
              f"joined={cluster['joined_existing']}, "
              f"seeded={cluster['seeded_new']}, "
              f"total_stories={cluster['final_stories']}")
        if cluster["error"]:
            print(f"          -> {cluster['error']}")

        synthesis = report["synthesis"]
        tag = "ERR" if synthesis["error"] else " ok"
        print(f"\n  Synthesis:  [{tag}] processed={synthesis['processed']}, "
              f"skipped={synthesis['skipped']}, "
              f"failed={synthesis['failed']} "
              f"(model={synthesis['model']})")
        if synthesis["error"]:
            print(f"          -> {synthesis['error']}")

        print(f"\n{'='*60}\n")
