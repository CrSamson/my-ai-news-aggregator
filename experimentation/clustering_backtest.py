"""
experimentation/clustering_backtest.py

Backtest two clustering algorithms on the live embeddings already in Neon:
  - greedy: single-pass online clustering with running-mean centroids
            (notebook-prototype, what Phase 4 will most likely use).
  - hdbscan: density-based hierarchical clustering (sklearn). Sweeps
            cluster_selection_epsilon = 1 - cosine_threshold so the two
            methods sweep on directly comparable axes.

Both are run at every cosine threshold in the sweep, and stats are
printed side-by-side so you can see where they agree/diverge.

Goal: pick a threshold AND clustering algorithm for Phase 4 by
spot-checking real-world clusters rather than the toy 19-article set
in architecture_experiments.ipynb.

What it does:
  1. Pulls every (id, source, title, published_at, topics, embedding) from
     `articles` where embedding IS NOT NULL.
  2. Runs greedy AND hdbscan at each threshold.
  3. Per (algo, threshold): cluster count, singleton ratio, largest cluster
     size, median multi-cluster size, mean intra-cluster cosine similarity,
     mean #-sources per multi-cluster (cross-source dedup proxy).
  4. For two or three promising thresholds, prints the top-N largest
     clusters from BOTH algorithms with their member titles + sources +
     dates so you can eyeball whether the algorithms grouped sensibly.

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
from sklearn.cluster import HDBSCAN

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
                "url":          r.url or "",
                "published_at": r.published_at,
                "topics":       list(r.topics or []),
            })
            vecs.append(np.asarray(r.embedding, dtype=np.float32))
        if skipped:
            print(f"  filtered out: {dict(skipped)} "
                  f"(total filtered = {sum(skipped.values())})")

    if not vecs:
        return np.zeros((0, 1536), dtype=np.float32), []
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
# HDBSCAN density-based clustering (sklearn)
# ---------------------------------------------------------------------------

def hdbscan_cluster(E: np.ndarray, threshold: float,
                    min_cluster_size: int = 2) -> list[int]:
    """Density-based hierarchical clustering at a given cosine threshold.

    HDBSCAN's natural distance is cosine_distance = 1 - cosine_similarity,
    so we set cluster_selection_epsilon = 1 - threshold to make the sweep
    axis comparable to greedy_cluster's threshold.

    Differences from greedy:
      - Order-independent: the global density structure is what matters.
      - Marks low-density points as noise (-1). We re-label every noise
        point as its own singleton cluster so summarise() works the same.
      - min_cluster_size=2 because we want even pair-stories to count.
      - cluster_selection_method='leaf' tends to produce tighter, smaller
        clusters than the default 'eom' — better match for our use case
        where we'd rather over-split than over-merge.
    """
    if E.shape[0] == 0:
        return []
    epsilon = 1.0 - threshold
    model = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=1,                       # most permissive density rule
        metric="cosine",
        cluster_selection_epsilon=epsilon,
        cluster_selection_method="leaf",
        copy=True,                           # silence sklearn 1.10 FutureWarning
    )
    raw = model.fit_predict(E)
    # Re-label noise (-1) as fresh singleton ids so the summariser treats
    # them like greedy's singletons.
    next_id = int(raw.max()) + 1 if (raw >= 0).any() else 0
    labels: list[int] = []
    for v in raw:
        if v == -1:
            labels.append(next_id)
            next_id += 1
        else:
            labels.append(int(v))
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

def print_top_clusters(label: str, summary: dict, meta: list[dict],
                       top_k: int = 10, max_per_cluster: int = 8) -> None:
    print(f"\n--- spot-check, {label}, top {top_k} clusters by size ---")
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
    greedy_summaries:  dict[float, dict] = {}
    hdbscan_summaries: dict[float, dict] = {}

    # ---- side-by-side sweep ----
    print("\n--- threshold sweep: greedy vs hdbscan ---")
    print(f"  {'thresh':>7}  | "
          f"{'GREEDY (#clu/#sng/#mul/max/intra/xsrc)':<46} | "
          f"{'HDBSCAN (#clu/#sng/#mul/max/intra/xsrc)':<46}")
    print(f"  {'-'*7}  | {'-'*46} | {'-'*46}")
    for t in thresholds:
        g_labels = greedy_cluster(E, t)
        g = summarise(g_labels, E, meta)
        greedy_summaries[t] = g

        h_labels = hdbscan_cluster(E, t)
        h = summarise(h_labels, E, meta)
        hdbscan_summaries[t] = h

        def fmt(s: dict) -> str:
            return (f"{s['n_clusters']:>4d}/{s['n_singletons']:>4d}/"
                    f"{s['n_multi']:>3d}/{s['max_size']:>3d}/"
                    f"{s['mean_intra_homog']:>5.3f}/{s['n_multi_xsource']:>3d}")

        print(f"  {t:7.2f}  | {fmt(g):<46} | {fmt(h):<46}")

    # Detailed per-algorithm sweep tables (full columns).
    def print_full_table(label: str, summaries: dict[float, dict]) -> None:
        print(f"\n--- {label} sweep (full stats) ---")
        print(f"  {'thresh':>7} {'#clusters':>10} {'#single':>8} {'#multi':>7} "
              f"{'max':>5} {'med_multi':>10} {'intra_homog':>12} "
              f"{'avg_src/multi':>14} {'#multi_xsrc':>12}")
        for t in thresholds:
            s = summaries[t]
            print(f"  {t:7.2f} {s['n_clusters']:>10d} {s['n_singletons']:>8d} "
                  f"{s['n_multi']:>7d} {s['max_size']:>5d} "
                  f"{s['median_multi_size']:>10.1f} "
                  f"{s['mean_intra_homog']:>12.3f} "
                  f"{s['mean_multi_sources']:>14.2f} "
                  f"{s['n_multi_xsource']:>12d}")

    print_full_table("greedy",  greedy_summaries)
    print_full_table("hdbscan", hdbscan_summaries)

    # ---- spot-checks at the production threshold ----
    PROD_T = 0.65
    print(f"\n\n=== spot-check at production threshold {PROD_T:.2f} ===")
    print_top_clusters(f"GREEDY @ {PROD_T:.2f}",
                       greedy_summaries[PROD_T], meta,
                       top_k=8, max_per_cluster=6)
    print_top_clusters(f"HDBSCAN @ {PROD_T:.2f} (epsilon={1-PROD_T:.2f})",
                       hdbscan_summaries[PROD_T], meta,
                       top_k=8, max_per_cluster=6)

    # ---- HDBSCAN's actual tightening knob: min_cluster_size ----
    # The threshold sweep above shows hdbscan plateaus between 0.65 and 0.75
    # because cluster_selection_epsilon is a "merge floor" and no natural
    # merge candidates sit in the (0.25, 0.35) distance window. To tighten
    # HDBSCAN you raise min_cluster_size or switch cluster_selection_method.
    # This sweep holds threshold=0.65 and varies min_cluster_size from 2 to 6.
    print(f"\n\n=== HDBSCAN min_cluster_size sweep at threshold {PROD_T:.2f} ===")
    print(f"  (cluster_selection_epsilon = {1 - PROD_T:.2f}, "
          f"cluster_selection_method='leaf')")
    print(f"  {'min_cs':>7} {'#clusters':>10} {'#single':>8} {'#multi':>7} "
          f"{'max':>5} {'intra_homog':>12} {'#multi_xsrc':>12}")
    for mcs in [2, 3, 4, 5, 6]:
        labels = hdbscan_cluster(E, PROD_T, min_cluster_size=mcs)
        s = summarise(labels, E, meta)
        print(f"  {mcs:>7d} {s['n_clusters']:>10d} {s['n_singletons']:>8d} "
              f"{s['n_multi']:>7d} {s['max_size']:>5d} "
              f"{s['mean_intra_homog']:>12.3f} "
              f"{s['n_multi_xsource']:>12d}")

    # ---- where do the algos disagree? ----
    print("\n\n=== disagreement analysis at "
          f"threshold {PROD_T:.2f} ===")
    g_members = greedy_summaries[PROD_T]["members"]
    h_members = hdbscan_summaries[PROD_T]["members"]
    g_multi = {cid: idxs for cid, idxs in g_members.items() if len(idxs) >= 2}
    h_multi = {cid: idxs for cid, idxs in h_members.items() if len(idxs) >= 2}
    print(f"  greedy multi-clusters:  {len(g_multi)}")
    print(f"  hdbscan multi-clusters: {len(h_multi)}")

    # Articles that are in a multi-cluster under greedy but a singleton under hdbscan
    g_clustered = {i for v in g_multi.values() for i in v}
    h_clustered = {i for v in h_multi.values() for i in v}
    only_greedy  = g_clustered - h_clustered
    only_hdbscan = h_clustered - g_clustered
    both         = g_clustered & h_clustered
    print(f"  articles clustered by both:        {len(both)}")
    print(f"  articles clustered only by greedy: {len(only_greedy)}")
    print(f"  articles clustered only by hdbscan:{len(only_hdbscan)}")

    # Show greedy-only and hdbscan-only sample articles to understand
    # which method is being too aggressive / too conservative.
    if only_greedy:
        print(f"\n  -- sample of articles greedy clustered but hdbscan didn't (first 6) --")
        for i in sorted(only_greedy)[:6]:
            m = meta[i]
            date = m["published_at"].strftime("%Y-%m-%d") if m["published_at"] else "?"
            print(f"      [{date}] {m['source']:24s} {m['title'][:80]}")

    if only_hdbscan:
        print(f"\n  -- sample of articles hdbscan clustered but greedy didn't (first 6) --")
        for i in sorted(only_hdbscan)[:6]:
            m = meta[i]
            date = m["published_at"].strftime("%Y-%m-%d") if m["published_at"] else "?"
            print(f"      [{date}] {m['source']:24s} {m['title'][:80]}")

    print("\nDone.")


if __name__ == "__main__":
    main()
