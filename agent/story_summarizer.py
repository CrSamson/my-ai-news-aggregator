"""
agent/story_summarizer.py — Story-level LLM synthesis (Phase 5).

For every multi-article Story whose `synthesis` is NULL (or stale via
membership change — see crud.assign_article_to_story), this module:

  1. Loads every member article in chronological order.
  2. Builds a synthesis prompt that asks the model to merge coverage
     across sources into ONE neutral, factual JSON-shaped story summary.
  3. Calls OpenAI (default gpt-4o-mini) with temperature 0.2.
  4. Parses + validates the response, classifies the story's topics
     against the project-wide ALLOWED_TOPICS taxonomy.
  5. Writes the result to stories.synthesis (+ synthesis_model,
     synthesis_at, synthesis_hash) so subsequent runs cache-hit.

Singletons are skipped on purpose: 470 of the 507 current stories are
one-article clusters and we'd rather not pay an OpenAI call to rewrite
a single article when its raw title/summary works for the digest. The
`min_size=2` default on get_stories_needing_synthesis enforces this.

Run directly:

    python -m agent.story_summarizer
    python -m agent.story_summarizer --limit 5      # cap (testing)
    python -m agent.story_summarizer --force        # re-synthesise all multi-stories
    python -m agent.story_summarizer --min-size 1   # opt singletons in
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.database.crud import (
    get_stories_needing_synthesis,
    get_story_members,
    set_story_synthesis,
)
from app.database.db import get_db
from app.database.models import Article, Story
# Re-use the project-wide topic taxonomy + validator the per-article
# summariser already uses.
from agent.summarizer import ALLOWED_TOPICS, _validate_topics


log = logging.getLogger(__name__)


# .env at project root (mirrors agent/summarizer.py).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env", override=True)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class StorySummarizerConfig:
    """All knobs in one place."""
    model:                       str   = "gpt-4o-mini"
    max_headline_words:          int   = 12
    max_summary_words:           int   = 100
    max_key_points:              int   = 5
    max_input_chars_per_article: int   = 1500
    temperature:                 float = 0.2
    max_tokens:                  int   = 1024
    timeout_seconds:             float = 30.0
    max_retries:                 int   = 3
    retry_initial_delay:         float = 1.0          # exponential backoff base


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

# Static editor-role prompt. Same wording as the experimentation prototype
# in architecture_experiments.ipynb cell 11; topic-classification rules
# appended for Phase 6 digest routing.
_SYSTEM_PROMPT = (
    "You are a news editor synthesizing coverage of a single story from "
    "multiple sources.\n\n"
    "Your job: produce ONE concise, factual summary that captures what "
    "happened across all the articles provided.\n\n"
    "CRITICAL RULES:\n"
    "1. Only use information present in the source articles. Do not "
    "invent facts, numbers, quotes, or details.\n"
    "2. If sources disagree on a fact, note the disagreement rather than "
    "picking one silently.\n"
    "3. Lead with the actual finding or news, not the framing. "
    "\"Anthropic released Claude X\" not \"Anthropic announced "
    "developments today.\"\n"
    "4. Use neutral, factual language. No marketing voice, no "
    "editorializing.\n"
    "5. Do not use phrases like \"according to reports\" or \"sources "
    "say\" — just state the facts.\n"
    "6. Synthesize across sources. The summary should reflect ALL the "
    "articles, not just one.\n\n"
    "TOPIC CLASSIFICATION:\n"
    "Also classify the story under 1 or 2 topics from a fixed "
    "taxonomy. Allowed values: \"ai\", \"technology\", \"business\", "
    "\"science\", \"general\". No others. Most stories get exactly 1 "
    "topic. Use 2 only when the story genuinely sits in two buckets "
    "(e.g. an AI-company funding round = [\"ai\", \"business\"]).\n"
    "- \"ai\": ML/LLMs/AI products/AI research/AI companies.\n"
    "- \"technology\": non-AI tech — hardware, software, telecoms, "
    "gadgets, platforms, cybersecurity.\n"
    "- \"business\": finance, markets, earnings, deals, "
    "macroeconomics — when AI/tech is not the central subject.\n"
    "- \"science\": non-AI research — physics, biology, chemistry, "
    "space, medicine, climate.\n"
    "- \"general\": catch-all for politics, conflict, crime, sports, "
    "lifestyle, human interest. NEVER combine \"general\" with another "
    "topic. If \"general\" applies, return [\"general\"] alone.\n\n"
    "Return your response as JSON matching the requested schema."
)


def _build_user_prompt(
    articles: list[Article],
    cfg: StorySummarizerConfig,
) -> str:
    """Build the user-side prompt. Concatenates a schema description with
    one block per article. Bodies are truncated at the nearest word
    boundary to keep token costs predictable."""
    blocks: list[str] = []
    for i, a in enumerate(articles, start=1):
        title = (a.title or "(no title)").strip()
        # Mirror the body-source logic from agent/embedder.article_text:
        # prefer trafilatura-extracted markdown, fall back to the RSS
        # feed's description/summary.
        body = a.content_md or ""
        if not body and a.raw_metadata:
            body = (
                a.raw_metadata.get("summary")
                or a.raw_metadata.get("description")
                or ""
            )
        body = (body or "").strip()
        if len(body) > cfg.max_input_chars_per_article:
            body = body[:cfg.max_input_chars_per_article].rsplit(" ", 1)[0] + "..."
        url = (a.url or "").strip()
        blocks.append(f"[Source {i}] {title}\nURL: {url}\n\n{body}")

    sources_text = "\n\n---\n\n".join(blocks)
    n = len(articles)
    schema = (
        f"Synthesize the following {n} articles about the same story.\n\n"
        f"Return JSON with these exact keys:\n"
        f"{{\n"
        f'  "headline":   "string, max {cfg.max_headline_words} words, '
        f'the canonical headline for the story",\n'
        f'  "summary":    "string, max {cfg.max_summary_words} words, '
        f'neutral factual summary synthesizing all sources",\n'
        f'  "key_points": ["3 to {cfg.max_key_points} short factual bullet strings"],\n'
        f'  "entities":   ["list of named entities — people, '
        f'organizations, products — mentioned across sources"],\n'
        f'  "topics":     ["1 or 2 values from: ai, technology, business, '
        f'science, general"]\n'
        f"}}\n\n"
        f"Articles:\n\n{sources_text}"
    )
    return schema


# ---------------------------------------------------------------------------
# Hash (cache key)
# ---------------------------------------------------------------------------

def synthesis_hash_for_articles(articles: list[Article]) -> str:
    """sha256 of sorted member URLs. Stable across re-runs as long as the
    member set doesn't change; changes the moment a new article joins or
    one is removed."""
    urls = sorted((a.url or "").strip() for a in articles)
    payload = "|".join(urls)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _parse_llm_json(raw: str) -> dict | None:
    """Best-effort extraction of the JSON object. Strips ``` fences if the
    model sneaks them in. Returns None on hard parse failure."""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip()
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _word_count(s: str) -> int:
    return len((s or "").split())


def _validate_and_clean(
    raw: dict,
    cfg: StorySummarizerConfig,
    fallback_topics: list[str],
) -> tuple[dict, list[str]]:
    """Coerce the LLM output to the expected shape, drop garbage, and
    enforce caps. Returns (cleaned_dict, list of warning strings).

    Never raises — partial outputs still produce a usable dict so a
    slightly off response doesn't lose the whole call."""
    warnings: list[str] = []

    headline   = str(raw.get("headline", "")).strip()
    summary    = str(raw.get("summary", "")).strip()
    key_points = raw.get("key_points", []) or []
    entities   = raw.get("entities", []) or []

    # Word-count guard rails (warn only).
    if _word_count(headline) > cfg.max_headline_words + 3:
        warnings.append(
            f"headline over cap: {_word_count(headline)} > "
            f"{cfg.max_headline_words}"
        )
    if _word_count(summary) > cfg.max_summary_words + 15:
        warnings.append(
            f"summary over cap: {_word_count(summary)} > "
            f"{cfg.max_summary_words}"
        )

    # Type-coerce list fields.
    if not isinstance(key_points, list):
        warnings.append("key_points not a list; coercing to []")
        key_points = []
    if not isinstance(entities, list):
        warnings.append("entities not a list; coercing to []")
        entities = []

    key_points = [str(x).strip() for x in key_points if str(x).strip()]
    key_points = key_points[:cfg.max_key_points]
    entities   = [str(x).strip() for x in entities if str(x).strip()][:20]

    # Topics: route through the project-wide validator. Falls back to the
    # source-declared topics if the LLM returned nothing usable.
    topics = _validate_topics(raw.get("topics"), fallback=fallback_topics)

    if not headline and summary:
        warnings.append("headline empty; deriving from summary")
        headline = summary.split(".")[0][:80]

    return (
        {
            "headline":   headline,
            "summary":    summary,
            "key_points": key_points,
            "entities":   entities,
            "topics":     topics,
        },
        warnings,
    )


# ---------------------------------------------------------------------------
# Summariser
# ---------------------------------------------------------------------------

class StorySummarizer:
    """Wraps the OpenAI Chat Completions API for one-story-at-a-time
    synthesis. Implements simple exponential-backoff retry for transient
    API errors."""

    def __init__(self, config: StorySummarizerConfig | None = None) -> None:
        self.config = config or StorySummarizerConfig()
        # Lazy import so importing this module doesn't require openai
        # when the caller only wants helpers (e.g. synthesis_hash_for_articles).
        from openai import OpenAI
        self.client = OpenAI(timeout=self.config.timeout_seconds)

    def summarize_story(
        self,
        articles: list[Article],
        fallback_topics: list[str],
    ) -> tuple[dict, list[str]]:
        """Returns (synthesis dict, warnings list).

        Raises only if the API failed for all retries; otherwise returns
        a best-effort cleaned dict (possibly with empty fields)."""
        if not articles:
            raise ValueError("Cannot summarize a story with zero articles.")

        cfg = self.config
        user_prompt = _build_user_prompt(articles, cfg)

        # Lazy import keeps non-OpenAI failure modes (e.g. ImportError on a
        # bad install) from leaking through the rest of the module.
        from openai import APIError, APITimeoutError, RateLimitError

        delay = cfg.retry_initial_delay
        last_err: Exception | None = None
        for attempt in range(cfg.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=cfg.model,
                    max_tokens=cfg.max_tokens,
                    temperature=cfg.temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user",   "content": user_prompt},
                    ],
                )
                break
            except (RateLimitError, APITimeoutError, APIError) as e:
                last_err = e
                log.warning(
                    "[story_summarizer] attempt %d/%d failed: %s; "
                    "backing off %.1fs",
                    attempt + 1, cfg.max_retries, e, delay,
                )
                if attempt + 1 >= cfg.max_retries:
                    raise
                time.sleep(delay)
                delay *= 2
        else:                                                    # pragma: no cover
            raise RuntimeError(f"Exhausted retries: {last_err}")

        raw = (response.choices[0].message.content or "").strip()
        parsed = _parse_llm_json(raw)
        if parsed is None:
            # The model violated response_format despite the constraint.
            # Return a stub so at least the headline carries the raw text.
            return (
                {
                    "headline":   raw[:80],
                    "summary":    raw,
                    "key_points": [],
                    "entities":   [],
                    "topics":     _validate_topics(None, fallback=fallback_topics),
                },
                ["LLM returned non-JSON; stored raw text in summary"],
            )

        return _validate_and_clean(parsed, cfg, fallback_topics)


# ---------------------------------------------------------------------------
# Batch runner — called from CLI + runner.py
# ---------------------------------------------------------------------------

@dataclass
class SynthesisReport:
    processed:  int      # stories actually synthesised
    skipped:    int      # stories the gate dropped (e.g. zero members)
    failed:     int      # stories that errored out
    model:      str
    min_size:   int


def run_synthesis(
    *,
    limit: int | None = None,
    force: bool = False,
    min_size: int = 2,
    config: StorySummarizerConfig | None = None,
) -> SynthesisReport:
    """Synthesise every story returned by get_stories_needing_synthesis.

    Idempotent: stories with non-NULL synthesis are skipped unless
    `force=True`. Cache invalidation on member-set change is handled in
    crud.assign_article_to_story (which NULLs the synthesis fields when
    a new article joins).

    Per-story commit: each successful synthesis is committed independently
    so a mid-batch crash doesn't lose prior progress.
    """
    cfg = config or StorySummarizerConfig()
    summarizer: StorySummarizer | None = None

    processed = 0
    skipped   = 0
    failed    = 0

    with get_db() as db:
        stories = get_stories_needing_synthesis(
            db, limit=limit, force=force, min_size=min_size,
        )
        log.info(
            "[story_summarizer] model=%s, min_size=%d, force=%s -> "
            "%d stories to synthesise",
            cfg.model, min_size, force, len(stories),
        )

        for i, story in enumerate(stories, start=1):
            members = get_story_members(db, story.id)
            if not members:
                log.warning("  story id=%d has zero members; skipping",
                            story.id)
                skipped += 1
                continue

            # Lazy construction so a "nothing to do" run pays nothing.
            if summarizer is None:
                summarizer = StorySummarizer(config=cfg)

            srcs   = sorted({m.source for m in members})
            print(f"  ({i}/{len(stories)}) story #{story.id}  "
                  f"size={len(members)}  sources={len(srcs)}: {srcs[:3]}")

            try:
                synthesis, warnings = summarizer.summarize_story(
                    members,
                    fallback_topics=list(story.topics or []),
                )
            except Exception as e:                                # noqa: BLE001
                log.warning("    synthesis failed: %s", e)
                failed += 1
                db.rollback()
                continue

            for w in warnings:
                log.info("    warn: %s", w)

            hash_value = synthesis_hash_for_articles(members)
            set_story_synthesis(
                db,
                story.id,
                synthesis=synthesis,
                model=cfg.model,
                hash_value=hash_value,
            )
            db.commit()
            processed += 1
            print(f"      headline={synthesis.get('headline', '')[:80]!r}")
            print(f"      topics={synthesis.get('topics', [])}")

    return SynthesisReport(
        processed=processed,
        skipped=skipped,
        failed=failed,
        model=cfg.model,
        min_size=min_size,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")          # type: ignore[attr-defined]
    except Exception:                                      # noqa: BLE001
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Phase 5: story-level LLM synthesis.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap how many stories to synthesise (default: all eligible).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-synthesise every multi-story, even those that already "
             "have a synthesis. Burns API credits — pair with --limit "
             "for testing.",
    )
    parser.add_argument(
        "--min-size", type=int, default=2,
        help="Minimum article_count for synthesis (default: 2 = skip "
             "singletons).",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Override OpenAI model (default: gpt-4o-mini).",
    )
    args = parser.parse_args()

    if "OPENAI_API_KEY" not in os.environ:
        raise SystemExit(
            "OPENAI_API_KEY is not set. Add it to your .env at the project root."
        )

    cfg = StorySummarizerConfig()
    if args.model:
        cfg.model = args.model

    report = run_synthesis(
        limit=args.limit,
        force=args.force,
        min_size=args.min_size,
        config=cfg,
    )

    print("=" * 60)
    print("  SYNTHESIS REPORT")
    print("=" * 60)
    print(f"  model:       {report.model}")
    print(f"  min_size:    {report.min_size}")
    print(f"  processed:   {report.processed} story/ies synthesised")
    print(f"  skipped:     {report.skipped} (zero-member or filtered)")
    print(f"  failed:      {report.failed}")


if __name__ == "__main__":
    main()
