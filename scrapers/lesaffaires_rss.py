import feedparser
from datetime import datetime, timedelta, timezone
from typing import List

from pydantic import AnyHttpUrl, BaseModel


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Confirmed feed pattern: https://www.lesaffaires.com/rss/<category>
# Categories sourced from lesaffaires.com/flux-rss/
_FEED_URLS: dict[str, str] = {
    # Top-level
    "dernieres-nouvelles"    : "https://www.lesaffaires.com/rss/dernieres-nouvelles",
    # Bourse
    "bourse"                 : "https://www.lesaffaires.com/rss/bourse",
    "actualites-boursieres"  : "https://www.lesaffaires.com/rss/actualites-boursieres",
    "analyses"               : "https://www.lesaffaires.com/rss/analyses",
    "placements"             : "https://www.lesaffaires.com/rss/placements",
    "revue-des-marches"      : "https://www.lesaffaires.com/rss/revue-des-marches",
    # Économie & finances
    "economie"               : "https://www.lesaffaires.com/rss/economie",
    "mes-finances"           : "https://www.lesaffaires.com/rss/mes-finances",
    "fiscalite"              : "https://www.lesaffaires.com/rss/fiscalite",
    "immobilier"             : "https://www.lesaffaires.com/rss/immobilier",
    # Secteurs
    "techno"                 : "https://www.lesaffaires.com/rss/techno",
    "energie"                : "https://www.lesaffaires.com/rss/energie",
    "commerce-de-detail"     : "https://www.lesaffaires.com/rss/commerce-de-detail",
    "environnement"          : "https://www.lesaffaires.com/rss/environnement",
    "politique"              : "https://www.lesaffaires.com/rss/politique",
    "monde"                  : "https://www.lesaffaires.com/rss/monde",
    "intelligence-artificielle": "https://www.lesaffaires.com/rss/intelligence-artificielle",
    # Mon entreprise
    "mon-entreprise"         : "https://www.lesaffaires.com/rss/mon-entreprise",
    "entrepreneuriat"        : "https://www.lesaffaires.com/rss/entrepreneuriat",
    "management"             : "https://www.lesaffaires.com/rss/management",
}


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class ArticleMetadata(BaseModel):
    """Validated output schema for a single Les Affaires article."""

    title      : str
    url        : AnyHttpUrl
    published  : datetime
    description: str

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class LesAffairesRSS:
    """
    Fetches Les Affaires RSS feeds and returns recent articles as plain dicts.

    Supported categories: see _FEED_URLS keys above.
    Default look-back window: 24 hours.
    """

    def __init__(self, hours: int = 24) -> None:
        self.default_hours = hours

    def get_latest(self, category: str, hours: int | None = None) -> List[dict]:
        url = _FEED_URLS.get(category.lower())
        if url is None:
            raise ValueError(
                f"Unknown category '{category}'. "
                f"Available: {', '.join(_FEED_URLS)}"
            )

        feed   = feedparser.parse(url)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours or self.default_hours)

        results = []
        for entry in feed.entries:
            published = self._get_entry_date(entry)
            if published is None or published < cutoff:
                continue

            results.append(ArticleMetadata(
                title       = entry.get("title", ""),
                url         = entry.get("link", ""),
                published   = published,
                description = self._extract_description(entry),
            ).model_dump(mode="json"))

        results.sort(key=lambda r: r["published"], reverse=True)
        return results

    def get_latest_all(self, hours: int | None = None) -> List[dict]:
        """Fetch and merge articles from all categories, deduped by URL."""
        seen   : set[str] = set()
        results: List[dict] = []

        for category in _FEED_URLS:
            for article in self.get_latest(category, hours=hours):
                if article["url"] not in seen:
                    seen.add(article["url"])
                    results.append(article)

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
    def _extract_description(entry) -> str:
        if hasattr(entry, "content"):
            return "\n".join(item.get("value", "") for item in entry.content)
        return entry.get("summary", "")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    scraper = LesAffairesRSS(hours=24)

    for cat in ("dernieres-nouvelles", "bourse", "economie", "techno"):
        articles = scraper.get_latest(cat)
        print(f"\n── {cat.upper()} ({len(articles)} articles) ──")
        for a in articles:
            print(f"  {a['published']}  {a['title']}")
            print(f"  {a['url']}\n")