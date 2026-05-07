"""
experimentation/clustering_viz_interactive.py

Interactive HTML version of clustering_viz.py. Hovering over any point
shows the article title, source, date, topics, and which cluster the
point belongs to under each algorithm.

Side-by-side Plotly subplots:
  - left:  greedy @ cosine > 0.65
  - right: HDBSCAN @ epsilon = 0.35, min_cluster_size = 2

Both plots use the SAME UMAP projection (identical x/y coords) so
visual differences come purely from the colouring (= cluster
assignment), making cross-algorithm comparison straightforward.

Output: experimentation/clustering_viz_interactive.html

Open it in VSCode by right-clicking the file -> "Open Preview", or just
double-click to open in your default browser. The plot supports zoom
(scroll), pan (drag), box-select, and hover-tooltip with full article
metadata.

Plotly is installed locally for experimentation only — not added to
requirements.txt:

    .venv/Scripts/python.exe -m pip install plotly

Run:
    .venv/Scripts/python.exe experimentation/clustering_viz_interactive.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import umap
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experimentation.clustering_backtest import (  # noqa: E402
    greedy_cluster,
    hdbscan_cluster,
    load_embeddings_and_metadata,
)


PROD_THRESHOLD: float = 0.65
OUTPUT_PATH = Path(__file__).resolve().parent / "clustering_viz_interactive.html"


# Plotly's qualitative palettes give us reasonably distinct colours.
# We cycle through several stacked palettes since we may have ~120 clusters.
_PALETTE = (
    [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
        "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
        "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5",
    ]
    + [
        "#393b79", "#637939", "#8c6d31", "#843c39", "#7b4173",
        "#5254a3", "#8ca252", "#bd9e39", "#ad494a", "#a55194",
        "#6b6ecf", "#b5cf6b", "#e7ba52", "#d6616b", "#ce6dbd",
        "#9c9ede", "#cedb9c", "#e7cb94", "#e7969c", "#de9ed6",
    ]
    + [
        "#3182bd", "#e6550d", "#31a354", "#756bb1", "#636363",
        "#6baed6", "#fd8d3c", "#74c476", "#9e9ac8", "#969696",
        "#9ecae1", "#fdae6b", "#a1d99b", "#bcbddc", "#bdbdbd",
        "#c6dbef", "#fdd0a2", "#c7e9c0", "#dadaeb", "#d9d9d9",
    ]
)
_SINGLETON_COLOUR = "#cccccc"


def cluster_colour(cluster_id_to_rank: dict[int, int], cid: int) -> str:
    if cid not in cluster_id_to_rank:
        return _SINGLETON_COLOUR
    return _PALETTE[cluster_id_to_rank[cid] % len(_PALETTE)]


def cluster_size_summary(idxs: list[int], meta: list[dict]) -> str:
    """One-line description used in hover tooltips."""
    sources = Counter(meta[i]["source"] for i in idxs)
    n = len(idxs)
    if len(sources) == 1:
        return f"{n} articles · 1 source ({sources.most_common(1)[0][0]})"
    return f"{n} articles · {len(sources)} sources"


def build_trace(
    coords: np.ndarray,
    labels: list[int],
    meta: list[dict],
    algo_name: str,
) -> list[go.Scatter]:
    """Return one or two Scatter traces — one for singletons (grey, smaller)
    and one for multi-cluster points (coloured, larger)."""
    members: dict[int, list[int]] = {}
    for i, lbl in enumerate(labels):
        members.setdefault(lbl, []).append(i)

    multi_ids   = {cid for cid, idxs in members.items() if len(idxs) >= 2}
    ranked      = sorted(multi_ids, key=lambda c: (-len(members[c]), c))
    cid_to_rank = {cid: i for i, cid in enumerate(ranked)}

    # Pre-build hover text for every point.
    hover_texts: list[str] = []
    for i in range(len(meta)):
        m = meta[i]
        date = m["published_at"].strftime("%Y-%m-%d") if m["published_at"] else "?"
        cid = labels[i]
        if cid in multi_ids:
            cluster_info = (
                f"<b>{algo_name} cluster #{cid}</b><br>"
                f"  {cluster_size_summary(members[cid], meta)}"
            )
        else:
            cluster_info = f"<b>{algo_name}</b>: singleton"
        topics_str = ", ".join(m["topics"]) if m["topics"] else "—"
        hover_texts.append(
            f"<b>{m['title'][:140]}</b><br>"
            f"{m['source']} · {date} · topics: {topics_str}<br>"
            f"{cluster_info}<br>"
            f"<a href='{m['url']}'>{m['url'][:90]}</a>"
        )

    is_single = np.array([lbl not in multi_ids for lbl in labels])
    colours   = [cluster_colour(cid_to_rank, lbl) for lbl in labels]

    traces: list[go.Scatter] = []

    # Singleton trace (drawn first, behind).
    if is_single.any():
        s_idx = np.where(is_single)[0]
        traces.append(
            go.Scatter(
                x=coords[s_idx, 0],
                y=coords[s_idx, 1],
                mode="markers",
                marker=dict(
                    size=6,
                    color=_SINGLETON_COLOUR,
                    opacity=0.55,
                    line=dict(width=0),
                ),
                name=f"singletons ({len(s_idx)})",
                text=[hover_texts[i] for i in s_idx],
                hovertemplate="%{text}<extra></extra>",
                customdata=[labels[i] for i in s_idx],
            )
        )

    # Multi-cluster trace (drawn second, on top).
    if (~is_single).any():
        m_idx = np.where(~is_single)[0]
        traces.append(
            go.Scatter(
                x=coords[m_idx, 0],
                y=coords[m_idx, 1],
                mode="markers",
                marker=dict(
                    size=11,
                    color=[colours[i] for i in m_idx],
                    opacity=0.92,
                    line=dict(width=0.6, color="white"),
                ),
                name=f"clustered ({len(m_idx)})",
                text=[hover_texts[i] for i in m_idx],
                hovertemplate="%{text}<extra></extra>",
                customdata=[labels[i] for i in m_idx],
            )
        )

    return traces


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

    g_multi_count  = sum(1 for lbl in set(greedy_labels)
                         if greedy_labels.count(lbl) >= 2)
    h_multi_count  = sum(1 for lbl in set(hdbscan_labels)
                         if hdbscan_labels.count(lbl) >= 2)
    g_in_multi = sum(1 for lbl in greedy_labels
                     if greedy_labels.count(lbl) >= 2)
    h_in_multi = sum(1 for lbl in hdbscan_labels
                     if hdbscan_labels.count(lbl) >= 2)

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=(
            f"GREEDY @ cos > 0.65 — {g_multi_count} multi-clusters · "
            f"{g_in_multi}/{N} clustered",
            f"HDBSCAN @ ε=0.35, min_cs=2 — {h_multi_count} multi-clusters · "
            f"{h_in_multi}/{N} clustered",
        ),
        horizontal_spacing=0.06,
    )

    print("Building plotly traces ...")
    for trace in build_trace(coords, greedy_labels, meta, "GREEDY"):
        fig.add_trace(trace, row=1, col=1)
    for trace in build_trace(coords, hdbscan_labels, meta, "HDBSCAN"):
        fig.add_trace(trace, row=1, col=2)

    fig.update_layout(
        title=dict(
            text=(f"Clustering on {N} OpenAI-embedded articles "
                  f"(text-embedding-3-small, 1536-dim → UMAP 2D)"),
            x=0.5, xanchor="center",
            font=dict(size=15),
        ),
        height=720,
        hovermode="closest",
        legend=dict(orientation="h", y=-0.05),
        plot_bgcolor="white",
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"),
    )
    fig.update_xaxes(title_text="UMAP-1", showgrid=True, gridcolor="#eee", zeroline=False)
    fig.update_yaxes(title_text="UMAP-2", showgrid=True, gridcolor="#eee", zeroline=False)
    # Force the two axes to share scale so visual comparison is meaningful.
    fig.update_yaxes(scaleanchor="x",  scaleratio=1, row=1, col=1)
    fig.update_yaxes(scaleanchor="x2", scaleratio=1, row=1, col=2)

    fig.write_html(
        str(OUTPUT_PATH),
        include_plotlyjs="cdn",   # pulls plotly.js from CDN, keeps file ~1MB
        full_html=True,
    )
    print(f"saved {OUTPUT_PATH}")
    print()
    print("Open it via:")
    print(f"  - VSCode: right-click the file -> 'Open Preview'")
    print(f"  - Browser: double-click the file")
    print()
    print("Hover over any point to see the article title, source, date,")
    print("topics, cluster id, and a clickable link to the article.")


if __name__ == "__main__":
    main()
