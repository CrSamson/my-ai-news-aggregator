"""
experimentation/openai_embedding_compare.py

Compare MiniLM (384-dim, local, in DB) vs OpenAI text-embedding-3-small
(1536-dim, API call, cached to .npy here) on the SAME 569-article corpus.

Goal: decide whether OpenAI embeddings tighten the topic blobs (AWS/NVIDIA,
OpenAI news, AI stocks) and beat MiniLM on cross-source story dedup.

What it does:
  1. Pulls (article, MiniLM-embedding) for every embedded article.
  2. Computes OpenAI embeddings for the same articles in the same input
     order, using agent.embedder.article_text() so the input formatting
     matches MiniLM's. Caches to experimentation/openai_embeddings.npz so
     re-runs cost zero API tokens.
  3. Runs the same greedy clusterer at the same threshold sweep on each
     embedding set.
  4. Prints a side-by-side stats table + diffs spot-check at threshold
     0.65 (our chosen production threshold).

Cost: ~340k tokens total at $0.02/M = ~$0.007 per cold run. Free on
re-run because we cache the result.

Run:
    .venv/Scripts/python.exe experimentation/openai_embedding_compare.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from agent.embedder import OpenAIEmbedder, article_text
from app.database.db import get_db
from app.database.models import Article


CACHE_PATH = Path(__file__).resolve().parent / "openai_embeddings.npz"


# ---------------------------------------------------------------------------
# Data loading + OpenAI embedding (with cache)
# ---------------------------------------------------------------------------

def load_articles_and_minilm():
    """Returns (article_ids, meta, E_minilm) for every embedded article in DB."""
    with get_db() as db:
        rows = db.execute(
            select(Article)
            .where(Article.embedding.is_not(None))
            .order_by(Article.id.asc())   # deterministic order for cache reuse
        ).scalars().all()

        ids   = [r.id for r in rows]
        meta  = []
        vecs  = []
        texts = []
        for r in rows:
            meta.append({
                "id":           r.id,
                "source":       r.source,
                "title":        r.title or "",
                "url":          r.url,
                "published_at": r.published_at,
                "topics":       list(r.topics or []),
            })
            vecs.append(np.asarray(r.embedding, dtype=np.float32))
            texts.append(article_text(r))

    E = np.stack(vecs)
    # Defensive re-norm.
    norms = np.linalg.norm(E, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    E = E / norms
    return ids, meta, E, texts


def get_openai_embeddings(ids: list[int], texts: list[str]) -> np.ndarray:
    """Compute OpenAI embeddings, with on-disk cache keyed on article ids."""
    if CACHE_PATH.exists():
        cached = np.load(CACHE_PATH, allow_pickle=False)
        cached_ids = cached["ids"].tolist()
        if cached_ids == ids:
            print(f"  cache hit: loaded {len(ids)} OpenAI embeddings from {CACHE_PATH.name}")
            return cached["embeddings"].astype(np.float32)
        print(f"  cache miss: id list changed (cache had {len(cached_ids)}, "
              f"need {len(ids)}). Recomputing.")

    print(f"  computing OpenAI embeddings for {len(texts)} articles "
          f"(model=text-embedding-3-small, dim=1536) ...")
    t0 = time.time()
    embedder = OpenAIEmbedder()
    E = embedder.embed(texts)
    print(f"  done in {time.time() - t0:.1f}s, shape={E.shape}")

    np.savez(CACHE_PATH,
             ids=np.asarray(ids, dtype=np.int64),
             embeddings=E.astype(np.float32))
    print(f"  cached to {CACHE_PATH.name}")
    return E


# ---------------------------------------------------------------------------
# Greedy clusterer (same as clustering_backtest.py)
# ---------------------------------------------------------------------------

def greedy_cluster(E: np.ndarray, threshold: float) -> list[int]:
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
        C = np.stack(centroids)
        sims = C @ emb
        best = int(np.argmax(sims))
        if sims[best] > threshold:
            new_emb = (centroids[best] * counts[best] + emb) / (counts[best] + 1)
            n = float(np.linalg.norm(new_emb))
            if n > 0:
                new_emb = new_emb / n
            centroids[best] = new_emb
            counts[best]   += 1
            labels[i]       = best
        else:
            centroids.append(emb.copy())
            counts.append(1)
            labels[i] = len(centroids) - 1
    return labels


def summarise(labels: list[int], E: np.ndarray, meta: list[dict]) -> dict:
    members: dict[int, list[int]] = {}
    for i, lbl in enumerate(labels):
        members.setdefault(lbl, []).append(i)

    sizes      = [len(v) for v in members.values()]
    multi      = [v for v in members.values() if len(v) >= 2]
    singletons = [v for v in members.values() if len(v) == 1]

    intra = []
    for v in multi:
        sub = E[v]
        sims = sub @ sub.T
        n = len(v)
        upper = sims[np.triu_indices(n, k=1)]
        intra.append(float(np.mean(upper)))

    multi_xsrc = []
    for v in multi:
        srcs = {meta[i]["source"] for i in v}
        multi_xsrc.append(len(srcs))

    return {
        "n_clusters":         len(members),
        "n_singletons":       len(singletons),
        "n_multi":            len(multi),
        "max_size":           max(sizes) if sizes else 0,
        "median_multi_size":  float(np.median([len(v) for v in multi])) if multi else 0.0,
        "mean_intra_homog":   float(np.mean(intra)) if intra else 0.0,
        "mean_multi_sources": float(np.mean(multi_xsrc)) if multi_xsrc else 0.0,
        "n_multi_xsource":    sum(1 for c in multi_xsrc if c >= 2),
        "members":            members,
    }


# ---------------------------------------------------------------------------
# Spot-check helpers
# ---------------------------------------------------------------------------

def top_clusters(summary: dict, meta: list[dict], k: int = 8,
                 max_per: int = 6) -> list[tuple[int, list[int]]]:
    members = summary["members"]
    ordered = sorted(members.items(),
                     key=lambda kv: (-len(kv[1]), kv[1][0]))
    out = []
    for cid, idxs in ordered:
        if len(idxs) < 2:
            continue
        out.append((cid, idxs))
        if len(out) >= k:
            break
    return out


def print_spot_check(label: str, summary: dict, meta: list[dict],
                     k: int = 8, max_per: int = 6) -> None:
    print(f"\n--- {label}: top {k} clusters ---")
    for cid, idxs in top_clusters(summary, meta, k):
        srcs = sorted({meta[i]["source"] for i in idxs})
        print(f"\n  cluster #{cid}  size={len(idxs)}  sources={len(srcs)}: {srcs}")
        for i in idxs[:max_per]:
            m = meta[i]
            date = m["published_at"].strftime("%Y-%m-%d") if m["published_at"] else "?"
            print(f"      [{date}] {m['source']:24s} {m['title'][:80]}")
        if len(idxs) > max_per:
            print(f"      ... and {len(idxs) - max_per} more")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    print("Loading articles + MiniLM embeddings from Neon ...")
    ids, meta, E_mini, texts = load_articles_and_minilm()
    print(f"Loaded N={len(ids)} articles, MiniLM dim={E_mini.shape[1]}")

    print("\nFetching OpenAI embeddings ...")
    E_openai = get_openai_embeddings(ids, texts)
    print(f"OpenAI dim={E_openai.shape[1]}")

    thresholds = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]

    print("\n--- threshold sweep, MiniLM (384-dim) ---")
    print(f"  {'thresh':>7} {'#clusters':>10} {'#single':>8} {'#multi':>7} "
          f"{'max':>5} {'intra':>7} {'avg_src':>8} {'#xsrc':>6}")
    mini_summaries = {}
    for t in thresholds:
        labels = greedy_cluster(E_mini, t)
        s = summarise(labels, E_mini, meta)
        mini_summaries[t] = s
        print(f"  {t:7.2f} {s['n_clusters']:>10d} {s['n_singletons']:>8d} "
              f"{s['n_multi']:>7d} {s['max_size']:>5d} "
              f"{s['mean_intra_homog']:>7.3f} "
              f"{s['mean_multi_sources']:>8.2f} "
              f"{s['n_multi_xsource']:>6d}")

    print("\n--- threshold sweep, OpenAI text-embedding-3-small (1536-dim) ---")
    print(f"  {'thresh':>7} {'#clusters':>10} {'#single':>8} {'#multi':>7} "
          f"{'max':>5} {'intra':>7} {'avg_src':>8} {'#xsrc':>6}")
    oa_summaries = {}
    for t in thresholds:
        labels = greedy_cluster(E_openai, t)
        s = summarise(labels, E_openai, meta)
        oa_summaries[t] = s
        print(f"  {t:7.2f} {s['n_clusters']:>10d} {s['n_singletons']:>8d} "
              f"{s['n_multi']:>7d} {s['max_size']:>5d} "
              f"{s['mean_intra_homog']:>7.3f} "
              f"{s['mean_multi_sources']:>8.2f} "
              f"{s['n_multi_xsource']:>6d}")

    # Find each embedder's "best" threshold by max cross-source clusters,
    # then a tighter and looser one, for spot-checks.
    def best_t(summaries: dict) -> float:
        return max(summaries.items(), key=lambda kv: kv[1]["n_multi_xsource"])[0]

    mini_best   = best_t(mini_summaries)
    openai_best = best_t(oa_summaries)
    print(f"\nMiniLM best-by-xsrc threshold: {mini_best:.2f} "
          f"({mini_summaries[mini_best]['n_multi_xsource']} xsrc clusters)")
    print(f"OpenAI best-by-xsrc threshold: {openai_best:.2f} "
          f"({oa_summaries[openai_best]['n_multi_xsource']} xsrc clusters)")

    # Spot-checks at production-candidate thresholds.
    print_spot_check(f"MiniLM @ 0.65 (production candidate)",
                     mini_summaries[0.65], meta, k=8, max_per=6)
    print_spot_check(f"OpenAI @ 0.65 (matched xsrc count)",
                     oa_summaries[0.65], meta, k=8, max_per=6)
    print_spot_check(f"OpenAI @ 0.70 (matched max-size discipline)",
                     oa_summaries[0.70], meta, k=8, max_per=6)

    # Direct comparison of the worst MiniLM topic-blob clusters: do they
    # decompose under OpenAI?
    print("\n\n=== topic-blob decomposition: how does OpenAI handle MiniLM's "
          "biggest false-merge clusters? ===")
    # Look at MiniLM @ 0.50 top clusters (where the topic blobs surface)
    # and compare against OpenAI clustering at its production-equivalent
    # threshold (0.70 — same max-size discipline as MiniLM 0.65).
    oa_compare_t = 0.70
    oa_labels = greedy_cluster(E_openai, oa_compare_t)
    print(f"(comparing against OpenAI @ {oa_compare_t:.2f}, "
          f"production-equivalent threshold)")

    mini_top = top_clusters(mini_summaries[0.50], meta, k=5, max_per=999)
    for cid, idxs in mini_top:
        srcs = sorted({meta[i]["source"] for i in idxs})
        print(f"\nMiniLM @ 0.50 cluster #{cid} (size {len(idxs)}, sources {srcs}):")
        for i in idxs[:6]:
            m = meta[i]
            print(f"      [{m['source']:24s}] {m['title'][:75]}")
        if len(idxs) > 6:
            print(f"      ... and {len(idxs) - 6} more")
        # Now look up where these articles land under OpenAI @ oa_compare_t
        oa_clusters: dict[int, list[int]] = {}
        for i in idxs:
            oa_clusters.setdefault(oa_labels[i], []).append(i)
        sizes = sorted([len(v) for v in oa_clusters.values()], reverse=True)
        n_singletons = sum(1 for s in sizes if s == 1)
        n_multi      = sum(1 for s in sizes if s >= 2)
        print(f"  -> under OpenAI @ {oa_compare_t:.2f}: {len(oa_clusters)} clusters "
              f"(sizes {sizes}, {n_multi} multi + {n_singletons} singleton)")

    print("\nDone.")


if __name__ == "__main__":
    main()
