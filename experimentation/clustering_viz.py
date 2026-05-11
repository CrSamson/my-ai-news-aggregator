"""
experimentation/clustering_viz.py

2D side-by-side visualisation of greedy vs HDBSCAN clustering on the
569-article OpenAI-embedded corpus.

Both algorithms use cosine threshold 0.65 (the production candidate
established in the backtest):
  - greedy:  cosine_similarity > 0.65 to merge into a centroid
  - hdbscan: cluster_selection_epsilon = 1 - 0.65 = 0.35,
             min_cluster_size = 2, metric = 'cosine'

Projection: UMAP from 1536-dim -> 2D, cosine metric, n_neighbors=15.
Singletons render as small grey dots; multi-clusters get distinct
colours. The biggest clusters get text labels with the dominant
topic / source.

Output: experimentation/clustering_viz.png

Run:
    .venv/Scripts/python.exe experimentation/clustering_viz.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import umap

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experimentation.clustering_backtest import (  # noqa: E402
    greedy_cluster,
    hdbscan_cluster,
    load_embeddings_and_metadata,
)


PROD_THRESHOLD: float = 0.65
OUTPUT_PATH = Path(__file__).resolve().parent / "clustering_viz.png"


# ---------------------------------------------------------------------------
# Cluster -> colour assignment
# ---------------------------------------------------------------------------

def assign_colours(labels: list[int]) -> tuple[np.ndarray, set[int]]:
    """Return (per-point RGBA, set of multi-cluster ids).

    Singletons get a flat grey. Multi-clusters get distinct colours from
    a high-variety palette so adjacent clusters stay visually separable.
    """
    members: dict[int, list[int]] = {}
    for i, lbl in enumerate(labels):
        members.setdefault(lbl, []).append(i)
    multi_ids = {cid for cid, idxs in members.items() if len(idxs) >= 2}

    # Stable colour-id ordering so re-runs produce the same picture.
    ordered_multi = sorted(multi_ids, key=lambda c: (-len(members[c]), c))

    # Cycle through tab20 + Set3 + Dark2 to get up to ~70 visually distinct
    # colours; matplotlib will wrap if we have more clusters than that and
    # that's fine — adjacent same-colour points are unlikely on UMAP.
    palette = (
        list(plt.cm.tab20.colors)
        + list(plt.cm.tab20b.colors)
        + list(plt.cm.tab20c.colors)
        + list(plt.cm.Set3.colors)
    )
    cid_to_colour: dict[int, tuple[float, float, float, float]] = {}
    for i, cid in enumerate(ordered_multi):
        rgb = palette[i % len(palette)]
        cid_to_colour[cid] = (*rgb, 0.85)

    grey = (0.78, 0.78, 0.78, 0.55)
    colours = np.array([
        cid_to_colour[lbl] if lbl in cid_to_colour else grey
        for lbl in labels
    ])
    return colours, multi_ids


# ---------------------------------------------------------------------------
# Cluster label-text helper (for annotating biggest clusters)
# ---------------------------------------------------------------------------

def cluster_label(idxs: list[int], meta: list[dict], maxlen: int = 36) -> str:
    """One-line description of a cluster for plot annotation. Picks the
    most-common source if homogeneous, else 'multi-src'; tacks on the
    most-common topic; ends with the size.

    Falls back to a salient title fragment when sources/topics aren't
    informative."""
    sources = Counter(meta[i]["source"] for i in idxs)
    topics  = Counter(t for i in idxs for t in (meta[i]["topics"] or []))
    n = len(idxs)

    src_str = (
        f"{n}x{sources.most_common(1)[0][0]}"
        if len(sources) == 1
        else f"{n} from {len(sources)} src"
    )
    topic_str = topics.most_common(1)[0][0] if topics else "?"

    # Headline fragment from the first article, if short enough.
    head = (meta[idxs[0]]["title"] or "")[:maxlen].replace("\n", " ").strip()
    return f"{src_str} · {topic_str}\n{head}…"


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot_side_by_side(
    coords: np.ndarray,
    greedy_labels: list[int],
    hdbscan_labels: list[int],
    meta: list[dict],
    output_path: Path,
) -> None:
    g_colours, g_multi = assign_colours(greedy_labels)
    h_colours, h_multi = assign_colours(hdbscan_labels)

    g_members: dict[int, list[int]] = {}
    h_members: dict[int, list[int]] = {}
    for i, lbl in enumerate(greedy_labels):
        g_members.setdefault(lbl, []).append(i)
    for i, lbl in enumerate(hdbscan_labels):
        h_members.setdefault(lbl, []).append(i)

    fig, (ax_g, ax_h) = plt.subplots(1, 2, figsize=(20, 9), dpi=120)

    def draw(ax, coords, colours, labels, members, multi_ids, title: str):
        # Singletons drawn first (small + faint), multi-clusters on top.
        is_single = np.array([lbl not in multi_ids for lbl in labels])
        ax.scatter(
            coords[is_single, 0], coords[is_single, 1],
            c=colours[is_single], s=14, alpha=0.55, linewidths=0,
            label=f"singletons ({int(is_single.sum())})",
        )
        ax.scatter(
            coords[~is_single, 0], coords[~is_single, 1],
            c=colours[~is_single], s=44, alpha=0.95, linewidths=0.4,
            edgecolors="white",
        )

        # Annotate the biggest 8 clusters with a short label.
        biggest = sorted(multi_ids,
                         key=lambda c: (-len(members[c]), c))[:8]
        for cid in biggest:
            idxs = members[cid]
            cx = float(np.mean(coords[idxs, 0]))
            cy = float(np.mean(coords[idxs, 1]))
            ax.annotate(
                cluster_label(idxs, meta),
                xy=(cx, cy),
                xytext=(8, 8), textcoords="offset points",
                fontsize=8,
                bbox=dict(boxstyle="round,pad=0.3",
                          fc="white", ec="#888", alpha=0.85),
            )

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("UMAP-1")
        ax.set_ylabel("UMAP-2")
        ax.grid(True, alpha=0.2)
        ax.legend(loc="lower right", fontsize=9)

    g_n_multi = sum(1 for v in g_members.values() if len(v) >= 2)
    h_n_multi = sum(1 for v in h_members.values() if len(v) >= 2)
    g_in_multi = sum(len(v) for v in g_members.values() if len(v) >= 2)
    h_in_multi = sum(len(v) for v in h_members.values() if len(v) >= 2)

    draw(ax_g, coords, g_colours, greedy_labels, g_members, g_multi,
         f"GREEDY @ cos>0.65 — {g_n_multi} multi-clusters, "
         f"{g_in_multi} of {len(meta)} articles clustered")
    draw(ax_h, coords, h_colours, hdbscan_labels, h_members, h_multi,
         f"HDBSCAN @ epsilon=0.35, min_cluster_size=2 — "
         f"{h_n_multi} multi-clusters, {h_in_multi} of {len(meta)} articles clustered")

    fig.suptitle(
        f"Clustering on 569 OpenAI-embedded articles "
        f"(text-embedding-3-small, 1536-dim → UMAP 2D)",
        fontsize=15, y=0.995,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output_path, bbox_inches="tight")
    print(f"saved {output_path}")


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
        print("No embeddings; run the runner first.")
        return

    print(f"Running greedy_cluster at threshold {PROD_THRESHOLD} ...")
    greedy_labels = greedy_cluster(E, PROD_THRESHOLD)
    print(f"Running hdbscan_cluster at threshold {PROD_THRESHOLD} (min_cs=2) ...")
    hdbscan_labels = hdbscan_cluster(E, PROD_THRESHOLD, min_cluster_size=2)

    print("Projecting embeddings to 2D via UMAP (metric=cosine) ...")
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=15,
        min_dist=0.1,
        metric="cosine",
        random_state=42,
    )
    coords = reducer.fit_transform(E)
    print(f"  coords shape: {coords.shape}")

    plot_side_by_side(coords, greedy_labels, hdbscan_labels, meta, OUTPUT_PATH)
    print("done.")


if __name__ == "__main__":
    main()
