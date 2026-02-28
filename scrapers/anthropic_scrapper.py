import feedparser
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from docling.document_converter import DocumentConverter
from pydantic import AnyHttpUrl, BaseModel


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

_FEED_URLS = [
    "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml",
    "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_research.xml",
    "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_engineering.xml",
]


class AnthropicArticle(BaseModel):
    title       : str
    description : str
    url         : AnyHttpUrl
    guid        : Optional[str] = None
    published_at: datetime
    category    : Optional[str] = None
    content     : str = ""

    model_config = {"frozen": True}


class AnthropicScraper:

    def __init__(self, hours: int = 24) -> None:
        self.hours     = hours
        self.converter = DocumentConverter()

    def fetch_articles(self, with_content: bool = False) -> List[dict]:
        now    = datetime.now(timezone.utc)
        # Round cutoff down to midnight so articles published "today" are never excluded
        cutoff = (now - timedelta(hours=self.hours)).replace(hour=0, minute=0, second=0, microsecond=0)

        seen   : set[str] = set()
        results: List[dict] = []

        for feed_url in _FEED_URLS:
            feed = feedparser.parse(feed_url, request_headers=_HEADERS)
            for entry in feed.entries:
                ts        = getattr(entry, "published_parsed", None)
                published = datetime(*ts[:6], tzinfo=timezone.utc) if ts else now

                if published < cutoff:
                    continue

                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)

                content = self.get_article_content(url) if with_content else ""

                results.append(AnthropicArticle(
                    title       = entry.get("title", ""),
                    description = entry.get("description", ""),
                    url         = url,
                    guid        = entry.get("id", url),
                    published_at= published,
                    category    = (entry.get("tags") or [{}])[0].get("term"),
                    content     = content,
                ).model_dump(mode="json"))

        results.sort(key=lambda r: r["published_at"], reverse=True)
        return results

    def get_article_content(self, url: str) -> str:
        try:
            result = self.converter.convert(url)
            return result.document.export_to_markdown()
        except Exception as e:
            print(f"[get_article_content] Failed for {url}: {e}")
            return ""


if __name__ == "__main__":
    scraper  = AnthropicScraper(hours=24)
    articles = scraper.fetch_articles(with_content=False)

    print(f"\n── ANTHROPIC ({len(articles)} articles) ──\n")
    for a in articles:
        print(f"  {a['published_at']}  {a['title']}")
        print(f"  {a['url']}\n")