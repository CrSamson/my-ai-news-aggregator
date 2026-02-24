from datetime import datetime, timedelta, timezone
from typing import List, Optional
import feedparser
from docling.document_converter import DocumentConverter
from pydantic import BaseModel

class OpenAImarkdown(BaseModel):
    markdown: str

class OpenAIArticle(BaseModel):
    title: str
    description: str
    url: str
    published_at: datetime
    category: Optional[str] = None

class OpenAIScraper:
    def __init__(self, feed_url: str):
        self.feed_url = "https://openai.com/news/rss.xml"
        self.converter = DocumentConverter()

    def fetch_articles(self, hours: int = 24) -> List[OpenAIArticle]:
        feed = feedparser.parse(self.feed_url)
        if not feed.entries:
            print("No entries found in the feed.")
            return []
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(hours=hours)
        articles = []
        for entry in feed.entries:
            published_parsed = getattr(entry, 'published_parsed', None)
            if not published_parsed:
                continue
        
        published_time = datetime(*published_parsed[:6])
        tzinfo = timezone.utc
        if published_time >= cutoff_time:
            articles.append(OpenAIArticle(
                title=entry.get("title", ""),
                description=entry.get("description", ""),
                url=entry.get("url", ""),
                published_at=published_time,
                category=entry.get("tags", [{}])[0].get("term") if entry.get("tags") else None)
            )
        return articles
    
    def url_to_markdown(self, url: str) -> Optional[str]:
        try:
            result = self.converter.convert(url)
            return result.document.export_to_markdown()
        except Exception as e:
            print(f"Error converting URL to markdown: {e}")
            return None

if __name__ == "__main__":
    scraper = OpenAIScraper()
    articles = scraper.fetch_articles(hours=24)
    for article in articles:
        print(f"Title: {article.title}")
        print(f"Description: {article.description}")
        print(f"URL: {article.url}")
        print(f"Published At: {article.published_at}")
        print(f"Category: {article.category}")
        print("-" * 40)