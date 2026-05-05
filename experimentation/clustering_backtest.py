"""
experimentation/clustering_backtest.py

Backtest greedy threshold clustering on the live embeddings already in Neon.

Goal: pick a threshold for Phase 4 by spot-checking real-world clusters
rather than the toy 19-article set in architecture_experiments.ipynb.

What it does:
  1. Pulls every (id, source, title, published_at, topics, embedding) from
     `articles` where embedding IS NOT NULL.
  2. Runs the greedy single-pass clusterer at a sweep of thresholds.
  3. Per threshold: cluster count, singleton ratio, largest cluster size,
     median multi-cluster size, mean intra-cluster cosine similarity,
     mean #-sources per multi-cluster (cross-source dedup proxy).
  4. For two or three promising thresholds, prints the top-N largest
     clusters with their member titles + sources + dates so you can eyeball
     whether the algorithm grouped sensibly.

Run:
    .venv/Scripts/python.exe experimentation/clustering_backtest.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database.db import get_db
from app.database.models import Article


# ---------------------------------------------------------------------------
# Source-config filters (mirror what RssBlogScraper would apply going forward)
# ---------------------------------------------------------------------------

SOURCES_FILE = Path(__file__).resolve().parents[1] / "config" / "sources.json"


def load_source_filters() -> tuple[set[str], dict[str, list[re.Pattern[str]]]]:
    """Returns (disabled_source_ids, url_blocklist_per_source)."""
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    disabled: set[str] = set()
    blocklist: dict[str, list[re.Pattern[str]]] = {}
    for s in cfg.get("blogs", []):
        sid = s["id"]
        if not s.get("enabled", True):
            disabled.add(sid)
        patterns = s.get("url_blocklist") or []
        if patterns:
            blocklist[sid] = [re.compile(p, re.IGNORECASE) for p in patterns]
    return disabled, blocklist


def article_passes_filters(
    source: str,
    url: str,
    disabled: set[str],
    blocklist: dict[str, list[re.Pattern[str]]],
) -> bool:
    if source in disabled:
        return False
    for pat in blocklist.get(source, []):
        if pat.search(url or ""):
            return False
    return True


# ---------------------------------------------------------------------------
# Data load
# ---------------------------------------------------------------------------

def load_embeddings_and_metadata():
    """Returns (E, meta) where E is (N, 384) float32 L2-normalised, and
    meta is a list of dicts with id/source/title/published_at/topics.

    Honours the disabled-source and url_blocklist filters from
    config/sources.json so the backtest reflects the future production
    state, not the pre-filter DB snapshot.
    """
    disabled, blocklist = load_source_filters()
    print(f"  filters: disabled sources = {sorted(disabled)}")
    print(f"  filters: url_blocklist sources = {sorted(blocklist.keys())}")

    with get_db() as db:
        rows = db.execute(
            select(Article)
            .where(Article.embedding.is_not(None))
            .order_by(Article.published_at.asc().nullsfirst())
        ).scalars().all()

        meta = []
        vecs = []
        skipped = Counter()
        for r in rows:
            if not article_passes_filters(r.source, r.url, disabled, blocklist):
                skipped[r.source] += 1
                continue
            meta.append({
                "id":           r.id,
                "source":       r.source,
                "title":        r.title or "",
                "published_at": r.published_at,
                "topics":       list(r.topics or []),
            })
            vecs.append(np.asarray(r.embedding, dtype=np.float32))
        if skipped:
            print(f"  filtered out: {dict(skipped)} "
                  f"(total filtered = {sum(skipped.values())})")

    if not vecs:
        return np.zeros((0, 384), dtype=np.float32), []
    E = np.stack(vecs)
    # Defensive re-norm in case anything drifted.
    norms = np.linalg.norm(E, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    E = E / norms
    return E, meta


# ---------------------------------------------------------------------------
# Greedy single-pass clustering (port of notebook cell 7)
# ---------------------------------------------------------------------------

def greedy_cluster(E: np.ndarray, threshold: float) -> list[int]:
    """Greedy single-pass online clustering with running-mean centroids.

    Articles are processed in input order. For each, we find the most
    similar existing centroid; if cos > threshold, the article joins that
    cluster and the centroid is updated to the running mean (re-normalised).
    Otherwise it seeds a new cluster.
    """
    N = E.shape[0]
    labels = [-1] * N
    centroids: list[np.ndarray] = []
    counts:    list[int]        = []

    for i in range(N):
        emb = E[i]
        if not centroids:
            centroids.append(emb.copy())
            counts.append(1)
            labels[i] = 0
            continue
        # cos sim against every centroid (centroids are L2-normalised; emb too)
        C = np.stack(centroids)
        sims = C @ emb
        best = int(np.argmax(sims))
        if sims[best] > threshold:
            new_emb = (centroids[best] * counts[best] + emb) / (counts[best] + 1)
            new_norm = float(np.linalg.norm(new_emb))
            if new_norm > 0:
                new_emb = new_emb / new_norm
            centroids[best] = new_emb
            counts[best]   += 1
            labels[i]       = best
        else:
            centroids.append(emb.copy())
            counts.append(1)
            labels[i] = len(centroids) - 1

    return labels


# ---------------------------------------------------------------------------
# Stats per threshold
# ---------------------------------------------------------------------------

def summarise(labels: list[int], E: np.ndarray, meta: list[dict]) -> dict:
    """Return a dict of summary statistics for a given clustering."""
    members: dict[int, list[int]] = {}
    for i, lbl in enumerate(labels):
        members.setdefault(lbl, []).append(i)

    sizes = [len(v) for v in members.values()]
    multi = [v for v in members.values() if len(v) >= 2]
    singletons = [v for v in members.values() if len(v) == 1]

    # Mean intra-cluster cosine similarity, averaged across multi-clusters.
    # For each multi-cluster: mean of all pairwise cosines.
    intra_homogeneity = []
    for v in multi:
        sub = E[v]
        sims = sub @ sub.T
        # ignore the diagonal (1.0 self-sim)
        n = len(v)
        upper = sims[np.triu_indices(n, k=1)]
        intra_homogeneity.append(float(np.mean(upper)))

    # Cross-source spread per multi-cluster.
    multi_source_counts = []
    for v in multi:
        sources = {meta[i]["source"] for i in v}
        multi_source_counts.append(len(sources))

    return {
        "n_clusters":          len(members),
        "n_singletons":        len(singletons),
        "n_multi":             len(multi),
        "max_size":            max(sizes) if sizes else 0,
        "median_multi_size":   float(np.median([len(v) for v in multi])) if multi else 0.0,
        "mean_intra_homog":    float(np.mean(intra_homogeneity)) if intra_homogeneity else 0.0,
        "mean_multi_sources":  float(np.mean(multi_source_counts)) if multi_source_counts else 0.0,
        "n_multi_xsource":     sum(1 for c in multi_source_counts if c >= 2),
        "members":             members,
    }


# ---------------------------------------------------------------------------
# Spot-check printer
# ---------------------------------------------------------------------------

def print_top_clusters(threshold: float, summary: dict, meta: list[dict],
                       top_k: int = 10, max_per_cluster: int = 8) -> None:
    print(f"\n--- spot-check, threshold={threshold:.2f}, top {top_k} clusters by size ---")
    members = summary["members"]
    # Sort by size desc, then by lowest member id (stable display)
    ordered = sorted(members.items(),
                     key=lambda kv: (-len(kv[1]), kv[1][0]))
    shown = 0
    for cid, idxs in ordered:
        if len(idxs) < 2:
            continue                                # skip singletons in spot-check
        sources = sorted({meta[i]["source"] for i in idxs})
        print(f"\n  cluster #{cid}  size={len(idxs)}  sources={len(sources)}: {sources}")
        for i in idxs[:max_per_cluster]:
            m = meta[i]
            date = m["published_at"].strftime("%Y-%m-%d") if m["published_at"] else "?"
            title = m["title"][:90].replace("\n", " ")
            print(f"      [{date}] {m['source']:24s} {title}")
        if len(idxs) > max_per_cluster:
            print(f"      ... and {len(idxs) - max_per_cluster} more")
        shown += 1
        if shown >= top_k:
            break


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    print("Loading embeddings from Neon ...")
    E, meta = load_embeddings_and_metadata()
    N = E.shape[0]
    print(f"Loaded N={N} articles, dim={E.shape[1]}")

    if N == 0:
        print("No embeddings to cluster. Run the runner first.")
        return

    thresholds = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]
    summaries  = {}

    print("\n--- threshold sweep ---")
    print(f"  {'thresh':>7} {'#clusters':>10} {'#single':>8} {'#multi':>7} "
          f"{'max':>5} {'med_multi':>10} {'intra_homog':>12} "
          f"{'avg_src/multi':>14} {'#multi_xsrc':>12}")
    for t in thresholds:
        labels = greedy_cluster(E, t)
        s = summarise(labels, E, meta)
        summaries[t] = s
        print(f"  {t:7.2f} {s['n_clusters']:>10d} {s['n_singletons']:>8d} "
              f"{s['n_multi']:>7d} {s['max_size']:>5d} "
              f"{s['median_multi_size']:>10.1f} "
              f"{s['mean_intra_homog']:>12.3f} "
              f"{s['mean_multi_sources']:>14.2f} "
              f"{s['n_multi_xsource']:>12d}")

    # Spot-check three thresholds: a tight, a middle, a loose one.
    # Pick by quick heuristic: middle = the one that maximises
    # cross-source multi-clusters (most useful for deduplication).
    by_xsource = sorted(summaries.items(), key=lambda kv: -kv[1]["n_multi_xsource"])
    middle_t = by_xsource[0][0]
    spot_thresholds = sorted({0.55, middle_t, 0.75})
    print(f"\nspot-checking thresholds: {spot_thresholds}")
    for t in spot_thresholds:
        print_top_clusters(t, summaries[t], meta, top_k=8, max_per_cluster=8)

    # Sanity stats on the cross-source multi-clusters at the middle threshold.
    s = summaries[middle_t]
    print(f"\n--- cross-source multi-cluster sample, threshold={middle_t:.2f} ---")
    members = s["members"]
    xs = []
    for cid, idxs in members.items():
        if len(idxs) < 2:
            continue
        sources = {meta[i]["source"] for i in idxs}
        if len(sources) >= 2:
            xs.append((cid, idxs, sources))
    xs.sort(key=lambda t: (-len(t[2]), -len(t[1])))
    print(f"  {len(xs)} cross-source clusters; showing top 5 by source diversity")
    for cid, idxs, sources in xs[:5]:
        print(f"\n  cluster #{cid}  size={len(idxs)}  sources={sorted(sources)}")
        for i in idxs:
            m = meta[i]
            date = m["published_at"].strftime("%Y-%m-%d") if m["published_at"] else "?"
            title = m["title"][:90].replace("\n", " ")
            print(f"      [{date}] {m['source']:24s} {title}")

    print("\nDone.")


if __name__ == "__main__":
    main()
