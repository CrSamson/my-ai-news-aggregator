import feedparser
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from pydantic import AnyHttpUrl, BaseModel


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FEED_URLS: dict[str, str] = {
    "topstories": "https://www.marketwatch.com/rss/topstories",
    "markets":    "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
    "bulletins":  "https://feeds.content.dowjones.io/public/rss/mw_bulletins",
}


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class ArticleMetadata(BaseModel):
    """Represents a single RSS entry with title, url and full content."""

    title    : str
    url      : AnyHttpUrl
    published: datetime
    content  : str

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class MarketWatchRSS:
    """
    Fetches MarketWatch RSS feeds and returns recent articles as plain dicts.

    Supported categories: topstories, markets, bulletins.
    """

    def __init__(self, hours: int = 24) -> None:
        self.default_hours = hours

    def get_latest(self, category: str, hours: int | None = None) -> List[dict]:
        url = _FEED_URLS.get(category.lower())
        if url is None:
            raise ValueError(f"Unknown MarketWatch category '{category}'. "
                             f"Choose from: {', '.join(_FEED_URLS)}")

        feed   = feedparser.parse(url)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours or self.default_hours)

        results = []
        for entry in feed.entries:
            published = self._get_entry_date(entry)
            if published is None or published < cutoff:
                continue

            results.append(ArticleMetadata(
                title     = entry.get("title", ""),
                url       = entry.get("link", ""),
                published = published,
                content   = self._extract_content(entry),
            ).model_dump(mode="json"))

        results.sort(key=lambda r: r["published"], reverse=True)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_entry_date(entry) -> datetime | None:
        for attr in ("published_parsed", "updated_parsed"):
            ts = getattr(entry, attr, None)
            if ts:
                return datetime(*ts[:6], tzinfo=timezone.utc)
        return None

    @staticmethod
    def _extract_content(entry) -> str:
        if hasattr(entry, "content"):
            return "\n".join(item.get("value", "") for item in entry.content)
        return entry.get("summary", "")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    scraper = MarketWatchRSS()
    for cat in ("topstories", "markets", "bulletins"):
        print(f"\n{cat.upper()} — last 24h\n")
        for a in scraper.get_latest(cat):
            print(a["title"])
            print(a["url"])
            print(a["content"][:200].replace("\n", " "), "...\n")