# AI News Aggregator

An intelligent news aggregation system that automatically collects, processes, and delivers personalized news digests using AI-powered summarization and email delivery.

## Project Overview

The AI News Aggregator is an automated system designed to:
- Aggregate news from multiple sources (YouTube RSS feeds and blog posts)
- Scrape and process full article content
- Generate AI-powered summaries using OpenAI
- Create personalized daily digests
- Send digest emails via Gmail SMTP
- Store and manage user profiles and preferences using PostgreSQL

## Project Structure

```
ai-news-aggregator/
├── main.py                          # Main entry point - runs scheduler and services
├── pyproject.toml                   # Project dependencies and metadata
├── README.md                        # Project documentation
│
├── app/
│   ├── __init__.py
│   ├── config.py                    # Configuration management and environment variables
│   ├── runner.py                    # Scheduler and background job runner
│   ├── daily_runner.py              # Daily task orchestration logic
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── curator_agent.py         # News curation agent logic
│   │   ├── digest_agent.py          # Digest generation agent logic
│   │   └── email_agent.py           # Email delivery agent logic
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py            # PostgreSQL connection management (SQLAlchemy)
│   │   ├── models.py                # SQLAlchemy ORM models (User, Article, Digest, etc.)
│   │   ├── create_tables.py         # Database schema initialization
│   │   └── repository.py            # Data access layer (CRUD operations)
│   │
│   ├── profiles/
│   │   ├── __init__.py
│   │   └── user_profile.py          # User preferences, interests, and settings
│   │
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── youtube.py               # YouTube RSS feed scraper
│   │   └── blog.py                  # Blog post scraper (full content extraction)
│   │
│   └── services/
│       ├── __init__.py
│       ├── openai_summarizer.py     # OpenAI API integration for summarization
│       ├── email.py                 # Gmail SMTP email service
│       ├── process_curator.py       # News curation service logic
│       ├── process_digest.py        # Daily digest generation service
│       ├── process_youtube.py       # YouTube scraping service
│       ├── process_blog.py          # Blog scraping service
│       └── process_email.py         # Email dispatch service
│
├── prompts/
│   ├── __init__.py
│   ├── system_prompts.py            # System prompts for AI agents (curator, digest, etc.)
│   └── user_insights.py             # User preference templates and insight generation
│
├── docker/
│   ├── Dockerfile                   # Container image definition
│   └── docker-compose.yml           # Multi-container orchestration (app + PostgreSQL)
│
└── config/
    ├── .env.example                 # Example environment variables
    └── requirements.txt             # Python dependencies (if not using pyproject.toml)
```

## Key Components

### 1. **Scrapers** (`app/scrapers/`)
- **YouTube RSS Feed Scraper**: Monitors and extracts video metadata from YouTube RSS feeds
- **Blog Post Scraper**: Performs full content extraction from blog URLs with HTML parsing

### 2. **Services** (`app/services/`)
- **OpenAI Summarizer**: Integrates with OpenAI API to generate concise article summaries
- **Email Service**: Uses Gmail SMTP to send personalized digest emails
- **Curation Service**: Filters and ranks news based on user preferences
- **Digest Service**: Aggregates curated news into formatted daily digests

### 3. **Database** (`app/database/`)
- **SQLAlchemy ORM Models**: Defines schemas for Users, Articles, Digests, Subscriptions
- **Connection Management**: Handles PostgreSQL connections and pool management
- **Repository Pattern**: Provides clean data access interface

### 4. **Agents** (`app/agent/`)
- **Curator Agent**: Intelligent news selection based on user interests
- **Digest Agent**: Creates formatted, personalized news summaries
- **Email Agent**: Manages email delivery logic and error handling

### 5. **User Profiles** (`app/profiles/`)
- Manages user preferences, interests, and subscription settings
- Tracks reading history and engagement metrics

### 6. **Prompts** (`prompts/`)
- **System Prompts**: LLM instructions for news curation and summarization
- **User Insights**: Templates for generating personalized content

### 7. **Configuration** (`app/config.py`)
- Environment-based configuration
- API keys and credentials management
- Database connection strings

## Technology Stack

| Component | Technology |
|-----------|-----------|
| **Language** | Python 3.10+ |
| **Database** | PostgreSQL (SQLAlchemy ORM) |
| **Summarization** | OpenAI API |
| **Email** | Gmail SMTP |
| **Containerization** | Docker & Docker Compose |
| **Scheduling** | APScheduler / Advanced Python Scheduler |

## Setup Instructions

### Prerequisites
- Python 3.10 or higher
- PostgreSQL 13+
- Docker & Docker Compose (optional, for containerized deployment)
- OpenAI API key
- Gmail account with app-specific password

### 1. Clone and Install
```bash
git clone <repository-url>
cd ai-news-aggregator
pip install -r requirements.txt
```

### 2. Environment Configuration
```bash
cp config/.env.example .env
```

Configure the following variables in `.env`:
```
OPENAI_API_KEY=your_openai_api_key
GMAIL_USER=your_gmail@gmail.com
GMAIL_PASSWORD=your_app_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=ai_news_db
DB_USER=postgres
DB_PASSWORD=your_password
```

### 3. Database Setup
```bash
python -m app.database.create_tables
```

### 4. Run the Application

**Local Development:**
```bash
python main.py
```

**Docker Deployment:**
```bash
docker-compose -f docker/docker-compose.yml up -d
```

## Usage

### Run Once
```python
from app.runner import NewsAggregatorRunner

runner = NewsAggregatorRunner()
runner.run_once()
```

### Schedule Daily Digest
```python
from app.daily_runner import DailyDigestRunner

runner = DailyDigestRunner()
runner.start()  # Runs at scheduled time daily
```

## API Key Management

Ensure all sensitive credentials are stored in `.env` file and never committed to version control. The `config.py` module loads these securely.

## Docker Deployment

The `docker-compose.yml` orchestrates:
- **App Service**: Python application container
- **PostgreSQL Service**: Database with persistent volume

```bash
docker-compose -f docker/docker-compose.yml up -d
docker-compose -f docker/docker-compose.yml logs -f app
```

## Contributing

Contributions are welcome! Please follow these guidelines:
1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Submit a pull request

## License

[Add your license here]

## Contact

For questions or support, please reach out to [your contact info]
