import feedparser
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import List

from pydantic import AnyHttpUrl, BaseModel


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# Confirmed URL pattern from lesaffaires.com/flux-rss/:
# https://www.lesaffaires.com/sections/<section>/<subsection>/feed/
_BASE = "https://www.lesaffaires.com/sections"

_FEED_URLS: dict[str, str] = {
    # Bourse
    "actualites-boursieres"    : f"{_BASE}/bourse/actualites-boursieres/feed/",
    "analyses"                 : f"{_BASE}/bourse/analyses-de-titres/feed/",
    "placements"               : f"{_BASE}/bourse/placements/feed/",
    "revue-des-marches"        : f"{_BASE}/bourse/revue-des-marches/feed/",
    "a-surveiller"             : f"{_BASE}/bourse/a-surveiller/feed/",
    # Économie & finances
    "economie"                 : f"{_BASE}/economie/nouvelles-economiques/feed/",
    "mes-finances"             : f"{_BASE}/mes-finances/feed/",
    "fiscalite"                : f"{_BASE}/mes-finances/fiscalite/feed/",
    "immobilier"               : f"{_BASE}/mes-finances/immobilier/feed/",
    "retraite"                 : f"{_BASE}/mes-finances/retraite/feed/",
    # Secteurs
    "techno"                   : f"{_BASE}/secteurs/techno/feed/",
    "energie"                  : f"{_BASE}/secteurs/energie-et-ressources-naturelles/feed/",
    "commerce-de-detail"       : f"{_BASE}/secteurs/commerce-de-detail/feed/",
    "environnement"            : f"{_BASE}/secteurs/environnement/feed/",
    "aeronautique"             : f"{_BASE}/secteurs/aeronautique-et-transport/feed/",
    "manufacturier"            : f"{_BASE}/secteurs/manufacturier/feed/",
    # Mon entreprise
    "entrepreneuriat"          : f"{_BASE}/mon-entreprise/entrepreneuriat-et-pme/feed/",
    "management"               : f"{_BASE}/mon-entreprise/management-et-rh/feed/",
    "marketing"                : f"{_BASE}/mon-entreprise/communication-et-marketing/feed/",
    # Autres
    "politique"                : f"{_BASE}/politique/feed/",
    "monde"                    : f"{_BASE}/monde/feed/",
    "intelligence-artificielle": f"{_BASE}/secteurs/intelligence-artificielle/feed/",
    "opinions"                 : f"{_BASE}/opinions/feed/",
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
    """

    def __init__(self, hours: int) -> None:
        self.default_hours = hours

    def get_latest(self, category: str, hours: int | None = None) -> List[dict]:
        url = _FEED_URLS.get(category.lower())
        if url is None:
            raise ValueError(
                f"Unknown category '{category}'. "
                f"Available: {', '.join(_FEED_URLS)}"
            )

        feed   = feedparser.parse(url, request_headers=_HEADERS)
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
        """Fetch and merge all categories, deduped by URL."""
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
# URL validator  —  run:  python lesaffaires_rss.py --validate
# ---------------------------------------------------------------------------

def validate_feeds() -> None:
    """Probe every feed URL and print a live status report."""
    print(f"{'CATEGORY':<30} {'STATUS':>6}  {'ENTRIES':>7}  NOTE")
    print("-" * 65)

    for name, url in _FEED_URLS.items():
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                http_status  = resp.status
                content_type = resp.headers.get("Content-Type", "")

            feed    = feedparser.parse(url, request_headers=_HEADERS)
            entries = len(feed.entries)
            note    = content_type.split(";")[0].strip()

            if "html" in content_type.lower():
                note = "WARNING: HTML returned — wrong URL or redirect"

            print(f"{name:<30} {http_status:>6}  {entries:>7}  {note}")

        except urllib.error.HTTPError as e:
            print(f"{name:<30} {e.code:>6}  {'N/A':>7}  {e.reason}")
        except Exception as e:
            print(f"{name:<30} {'ERR':>6}  {'N/A':>7}  {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if "--validate" in sys.argv:
        validate_feeds()
    else:
        scraper = LesAffairesRSS(hours=100)
        for cat in ("actualites-boursieres", "economie", "techno"):
            articles = scraper.get_latest(cat)
            print(f"\n── {cat.upper()} ({len(articles)} articles) ──")
            for a in articles:
                print(f"  {a['published']}  {a['title']}")
                print(f"  {a['url']}\n")