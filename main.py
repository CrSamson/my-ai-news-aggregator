"""
main.py — Entry point for the AI News Aggregator.

Collects articles from blogs and papers from arXiv + HuggingFace Daily
published in the last N hours.
"""

from runner import Runner


def main() -> None:
    runner = Runner(hours=100)   # look back this many hours (default: 24)
    # Per-source content fetching is configured in config/sources.json
    # (per-source `fetch_content` flag), not at the Runner level.
    report = runner.run()

    # `report` dict is available for downstream use (e.g. pass to an agent)
    # Keys: generated_at, hours, blogs, papers


if __name__ == "__main__":
    main()
