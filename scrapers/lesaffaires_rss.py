import feedparser
import trafilatura
from datetime import datetime, timedelta, timezone
from typing import List

from pydantic import AnyHttpUrl, BaseModel


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

_BASE = "https://www.lesaffaires.com/sections"

_FEED_URLS: dict[str, str] = {
    # Bourse
    "actualites-boursieres"    : f"{_BASE}/bourse/actualites-boursieres/feed/",
    "analyses"                 : f"{_BASE}/bourse/analyses-de-titres/feed/",
    "placements"               : f"{_BASE}/bourse/placements/feed/",
    "revue-des-marches"        : f"{_BASE}/bourse/revue-des-marches/feed/",
    "a-surveiller"             : f"{_BASE}/bourse/a-surveiller/feed/",
    # Secteurs
    "techno"                   : f"{_BASE}/secteurs/techno/feed/",
    "energie"                  : f"{_BASE}/secteurs/energie-et-ressources-naturelles/feed/",
    "environnement"            : f"{_BASE}/secteurs/environnement/feed/",
    "intelligence-artificielle": f"{_BASE}/secteurs/intelligence-artificielle/feed/",
}


class ArticleMetadata(BaseModel):
    title      : str
    url        : AnyHttpUrl
    published  : datetime
    description: str
    content    : str = ""

    model_config = {"frozen": True}


class LesAffairesRSS:

    def __init__(self, hours: int = 48) -> None:
        self.hours = hours

    def get_latest(self, category: str, with_content: bool = False) -> List[dict]:
        url = _FEED_URLS.get(category.lower())
        if url is None:
            raise ValueError(f"Unknown category '{category}'. Available: {', '.join(_FEED_URLS)}")

        feed   = feedparser.parse(url, request_headers=_HEADERS)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.hours)

        results = []
        for entry in feed.entries:
            published = self._parse_date(entry)
            if published is None or published < cutoff:
                continue

            content = self.get_article_content(entry.get("link", "")) if with_content else ""

            results.append(ArticleMetadata(
                title       = entry.get("title", ""),
                url         = entry.get("link", ""),
                published   = published,
                description = entry.get("summary", ""),
                content     = content,
            ).model_dump(mode="json"))

        results.sort(key=lambda r: r["published"], reverse=True)
        return results

    def get_article_content(self, url: str) -> str:
        try:
            html = trafilatura.fetch_url(url)
            return trafilatura.extract(html, include_comments=False, include_tables=False) or ""
        except Exception as e:
            print(f"[get_article_content] Failed for {url}: {e}")
            return ""

    @staticmethod
    def _parse_date(entry) -> datetime | None:
        for attr in ("published_parsed", "updated_parsed"):
            ts = getattr(entry, attr, None)
            if ts:
                return datetime(*ts[:6], tzinfo=timezone.utc)
        return None


if __name__ == "__main__":
    scraper = LesAffairesRSS(hours=9999)

    for cat in _FEED_URLS:
        articles = scraper.get_latest(cat, with_content=False)
        print(f"\n── {cat.upper()} ({len(articles)} articles) ──")
        for a in articles:
            print(f"  {a['published']}  {a['title']}")
            print(f"  {a['url']}")