"""
agent/clusterer.py — Stateful greedy story clusterer.

Assigns every unclustered Article to a Story. Algorithm: for each new
article in chronological order, compute cosine similarity against the
centroids of every active (= last_seen_at within lookback window) story
loaded from the DB; if best similarity > threshold, join that story and
update its centroid to the new running mean (re-normalised); otherwise
seed a fresh story with this article as the first member.

Stateful is the key word: across runner passes, stories persist in the
DB and tomorrow's articles can join yesterday's stories. A multi-day
event (e.g. a court trial that runs all week) accumulates members
rather than re-clustering from scratch every morning.

Threshold and lookback come from env vars with backtested defaults:

    BREVIO_CLUSTER_THRESHOLD        default 0.65
    BREVIO_CLUSTER_LOOKBACK_HOURS   default 72

Run the clusterer programmatically via run_clustering() (called from
runner.py), or via this module's CLI for a one-shot pass:

    .venv/Scripts/python.exe -m agent.clusterer
    .venv/Scripts/python.exe -m agent.clusterer --threshold 0.65
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass

import numpy as np

from app.database.crud import (
    assign_article_to_story,
    create_story,
    get_active_stories,
    get_unclustered_articles,
)
from app.database.db import get_db


log = logging.getLogger(__name__)


# Backtested defaults — see experimentation/clustering_backtest.py.
DEFAULT_THRESHOLD: float = 0.65
DEFAULT_LOOKBACK_HOURS: int = 72


def _threshold() -> float:
    raw = os.environ.get("BREVIO_CLUSTER_THRESHOLD")
    return float(raw) if raw else DEFAULT_THRESHOLD


def _lookback_hours() -> int:
    raw = os.environ.get("BREVIO_CLUSTER_LOOKBACK_HOURS")
    return int(raw) if raw else DEFAULT_LOOKBACK_HOURS


@dataclass
class ClusterReport:
    processed:        int
    joined_existing:  int
    seeded_new:       int
    active_stories:   int     # snapshot at the start of the pass
    final_stories:    int     # total stories after the pass
    threshold:        float
    lookback_hours:   int


def _l2_normalise(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def _running_mean(centroid: np.ndarray, count: int, new_vec: np.ndarray) -> np.ndarray:
    """Update a running-mean centroid by adding one new member, then L2-normalise."""
    combined = (centroid * count + new_vec) / (count + 1)
    return _l2_normalise(combined)


def run_clustering(
    threshold: float | None = None,
    lookback_hours: int | None = None,
) -> ClusterReport:
    """Cluster every Article whose story_id is NULL. Idempotent."""
    t = threshold       if threshold       is not None else _threshold()
    lh = lookback_hours if lookback_hours is not None else _lookback_hours()

    with get_db() as db:
        unclustered = get_unclustered_articles(db)
        active = get_active_stories(db, hours=lh)
        n_active_at_start = len(active)
        n_unclustered     = len(unclustered)
        log.info("[cluster] threshold=%.2f, lookback=%dh, %d unclustered, %d active stories",
                 t, lh, n_unclustered, n_active_at_start)

        if not unclustered:
            return ClusterReport(0, 0, 0, n_active_at_start, n_active_at_start, t, lh)

        # In-memory mirror of active stories so we can update centroids
        # incrementally as we go. We flush to the DB at the end of each
        # article (so a crash mid-batch doesn't lose progress) — pg_vector
        # rewrites the full vector on UPDATE, which is cheap at 1536-dim.
        centroids = [np.asarray(s.centroid, dtype=np.float32) for s in active]
        # Stories track their own article_count + last_seen_at; we mirror
        # those into Python-side lists for fast in-loop access.
        counts        = [int(s.article_count or 0) for s in active]
        story_objs    = list(active)

        joined = 0
        seeded = 0
        for article in unclustered:
            emb = np.asarray(article.embedding, dtype=np.float32)
            emb = _l2_normalise(emb)

            best_idx = -1
            best_sim = -1.0
            if centroids:
                # Stack into a matrix for one batched matmul — much faster
                # than a Python loop once we have >50 active stories.
                C = np.stack(centroids)
                sims = C @ emb
                best_idx = int(np.argmax(sims))
                best_sim = float(sims[best_idx])

            if best_idx >= 0 and best_sim > t:
                story = story_objs[best_idx]
                new_centroid = _running_mean(centroids[best_idx], counts[best_idx], emb)
                assign_article_to_story(
                    db,
                    article=article,
                    story=story,
                    new_centroid=new_centroid,
                )
                centroids[best_idx] = new_centroid
                counts[best_idx]   += 1
                joined += 1
            else:
                story = create_story(
                    db,
                    centroid=emb,
                    topics=list(article.topics or []),
                    first_article=article,
                )
                centroids.append(emb)
                counts.append(1)
                story_objs.append(story)
                seeded += 1

            db.flush()    # surface FK errors immediately, keeps memory bounded

        n_final = len(story_objs)
        log.info("[cluster] done: processed=%d joined_existing=%d seeded_new=%d "
                 "total_stories=%d",
                 n_unclustered, joined, seeded, n_final)

    return ClusterReport(
        processed=n_unclustered,
        joined_existing=joined,
        seeded_new=seeded,
        active_stories=n_active_at_start,
        final_stories=n_final,
        threshold=t,
        lookback_hours=lh,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Greedy stateful story clusterer."
    )
    parser.add_argument("--threshold", type=float, default=None,
                        help=f"cosine similarity threshold for joining a "
                             f"story (default: ${{BREVIO_CLUSTER_THRESHOLD}} or "
                             f"{DEFAULT_THRESHOLD}).")
    parser.add_argument("--lookback-hours", type=int, default=None,
                        help=f"only compare against stories whose last_seen_at "
                             f"is within this window (default: "
                             f"${{BREVIO_CLUSTER_LOOKBACK_HOURS}} or "
                             f"{DEFAULT_LOOKBACK_HOURS}).")
    args = parser.parse_args()

    report = run_clustering(
        threshold=args.threshold,
        lookback_hours=args.lookback_hours,
    )

    print("=" * 60)
    print("  CLUSTER REPORT")
    print("=" * 60)
    print(f"  threshold:        {report.threshold:.2f}")
    print(f"  lookback_hours:   {report.lookback_hours}")
    print(f"  processed:        {report.processed} unclustered article(s)")
    print(f"  joined_existing:  {report.joined_existing}")
    print(f"  seeded_new:       {report.seeded_new}")
    print(f"  active_stories:   {report.active_stories} (snapshot at start)")
    print(f"  final_stories:    {report.final_stories} (after pass)")
    print()


if __name__ == "__main__":
    main()
