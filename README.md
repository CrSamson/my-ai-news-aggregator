# AI News Aggregator

> Pulls fresh news from **~30 RSS blog sources** spanning AI, tech, business, science, and general news. Stores everything in **Neon Postgres**, summarises each article with an LLM, and emails a daily HTML digest organised by topic. Runs on **GitHub Actions** at 08:00 Montreal time, every day.

## 🎯 Objective

Keep up with AI without ad-hoc tab-checking. Every morning a GitHub Actions runner fires up, scrapes a configurable list of trusted sources for the last *N* hours, summarises new articles with GPT-4o, and ships a single HTML email so the reader can decide in seconds what to click.

The summariser produces a busy-practitioner blurb (2–4 sentences, specifics over generalities) for every new article.

The pipeline is end-to-end and intentionally **single-user**: one recipient, one source list. Sources are config-driven in [config/sources.json](config/sources.json).

Adding a new RSS blog source is a JSON edit, no scraper to write.

## 🏗️ Architecture

*Once a day, a GitHub Actions cron job spins up a runner that runs three steps in sequence: scrape → summarize → email. All state lives in Neon. The runner exits when the pipeline is done; nothing stays running between fires.*

```mermaid
flowchart LR
    Cron[GitHub Actions cron<br/>0 12 * * * UTC] --> Scrape[Step 1: Scrape<br/>~30 RSS blog sources]
    Cfg[sources.json] -.config.-> Scrape

    Scrape --> DB[(Neon Postgres<br/>articles)]
    DB --> Sum[Step 2: Summarize<br/>GPT-4o]
    Sum --> DB
    DB --> Dig[Step 3: Digest<br/>topic-balanced + per-source diversity]
    Dig --> Mail[SMTP → inbox]
```

## 🛠️ Tech Stack

- **Language**: Python 3.12
- **RSS / Atom parsing**: `feedparser`
- **HTTP**: `requests`
- **Article content extraction (optional, per-source)**: [Docling](https://github.com/docling-project/docling) — URL → markdown
- **Validation**: Pydantic v2 (`BlogArticle`)
- **Database**: **Neon Postgres** (managed, free-tier — 500 MB / 191.9 compute-hours per month) accessed via SQLAlchemy 2.x ORM
  - Idempotent upserts via `INSERT … ON CONFLICT DO UPDATE`
  - Insert-vs-update distinguished via Postgres' `xmax = 0` trick
  - `summary` deliberately omitted from upsert SET clauses so re-scrapes never overwrite LLM output
- **LLM summarisation**: OpenAI `gpt-4o`
- **Email delivery**: stdlib `smtplib` + `EmailMessage` (multipart text + inline-styled HTML)
- **Daily trigger**: **GitHub Actions cron** (`.github/workflows/digest.yml`). Secrets in repo Actions secrets. APScheduler also ships in [agent/scheduler.py](agent/scheduler.py) for in-process scheduling if you'd rather have a long-running Python process

## 📊 What it does today

### Sources

~30 enabled blog sources in [config/sources.json](config/sources.json), spanning AI labs (Anthropic, OpenAI, Google Research, AWS ML, NVIDIA, BAIR, CMU ML), tech press (TechCrunch, Wired, The Verge, Ars Technica), business (Yahoo Finance, CNBC, Benzinga, Forbes), science (Phys.org, ScienceDaily, Quanta, Nature, MIT News), and general news (BBC, Independent, CBC, Le Monde).

### Tables (on Neon)

The single `articles` table carries `digest_sent_at TIMESTAMPTZ NULL` — the timestamp at which the row was first included in a sent digest, or `NULL` if it has never shipped. Used by the digest's no-duplicate filter (see *Digest selection* below).

- **`articles`** — every blog/news post. Conflict key: `url`. Per-row: `source` (e.g. `anthropic_news`, `openai_news`), `title`, `published_at`, `summary` (LLM, busy-practitioner tone), `content_md` (trafilatura, optional), `topics` (TEXT[]), `raw_metadata` (JSONB), `digest_sent_at`.

### Digest selection

`cap_by_topic` (in [agent/digest.py](agent/digest.py)) takes the most-recent summarised articles in the lookback window and trims them to a hard cap (default `--max-items 15`):

- **Topic quotas**: `--max-items` is split evenly across topic sections (5 topics → 3/3/3/3/3 at max=15), sorted by recency within each topic.
- **Per-source diversity**: `DIGEST_MAX_PER_SOURCE = 2` → no single publisher (e.g. TechCrunch) can dominate any topic section.
- **No duplicate sends**: `get_recent_summarized_articles` filters `WHERE digest_sent_at IS NULL`, so a row that has shipped in a previous email is never picked again. After `send_email()` returns, every included row is stamped with `digest_sent_at = NOW()` (see `mark_digest_sent` in [app/database/crud.py](app/database/crud.py)). The mark step runs **after** the SMTP call — an SMTP failure leaves the rows unsent and they get retried on the next cron. `--dry-run` skips the mark entirely. Re-scrapes never reset send state because all upserts omit `digest_sent_at` from their `SET` clauses.

### Resilience

- Per-entry try/except — one bad RSS row doesn't drop the others.
- Per-source try/except — one dead feed doesn't abort the run.
- **Idempotent re-runs**: the daily cron skips already-summarised rows. Running the pipeline twice in a day costs zero extra OpenAI tokens.

## 📁 Repository Structure

```
brevio-ai/
├── main.py                          # Manual one-shot scrape across all sources
├── runner.py                        # Orchestrates blog scraping + per-source reports
├── scrapers/
│   ├── base.py                      # BaseScraper ABC
│   ├── schemas.py                   # Pydantic v2: BlogArticle
│   └── rss_blog_scraper.py          # Generic RSS scraper, drives off sources.json
├── agent/
│   ├── summarizer.py                # OpenAI gpt-4o, per-article blurbs + topic classification
│   ├── digest.py                    # Topic-organised HTML + plain-text email + cap_by_topic
│   └── scheduler.py                 # Pipeline driver (--once for cron, BlockingScheduler for in-process)
├── app/database/
│   ├── db.py                        # Engine + session factory (reads DATABASE_URL)
│   ├── models.py                    # SQLAlchemy: Article
│   ├── crud.py                      # upsert_articles, get_recent_summarized_articles, mark_digest_sent
│   └── create_tables.py             # Idempotent schema init + additive ALTERs
├── config/
│   └── sources.json                 # blog source config (drives the runner)
├── tests/
│   ├── fixtures/                    # saved RSS snapshots
│   ├── test_schema.py
│   └── test_rss_blog_scraper.py     # fixture-driven offline tests
├── tools/
│   ├── verify_feeds.py              # pre-flight feed verifier
│   ├── backfill_digest_sent.py      # one-shot: stamp existing rows as already-sent
│   ├── backfill_topics.py           # one-shot: stamp topic tags from source config
│   └── phase6_check.py              # E2E backtest
├── .github/
│   └── workflows/
│       └── digest.yml               # daily cron + manual trigger
└── requirements.txt
```

## 🚀 How to Run

### Configure environment (local development)

Create `.env` at the project root:

```dotenv
# Database (Neon)
DATABASE_URL=postgresql+psycopg2://user:pass@ep-xxx.aws.neon.tech/db?sslmode=require&channel_binding=require

# LLM
OPENAI_API_KEY=sk-...

# Email (Gmail App Password example)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-16-char-app-password
DIGEST_FROM=you@gmail.com
DIGEST_TO=you@gmail.com
```

For production, the same values live in **GitHub Actions Secrets** (see Deployment).

### Initialise schema

```bash
pip install -r requirements.txt
python -m app.database.create_tables
```

Idempotent. Safe to re-run.

### One-shot from your venv

```powershell
# Smoke test - scrape, summarise, email
python -m agent.scheduler --once --max-items 10 --hours 48

# No email - render the digest to stdout
python -m agent.digest --hours 48 --max-items 10 --dry-run

# Cheaper iteration loops while tweaking the article prompt
python -m agent.summarizer --limit 3 --force
```

### Add or edit a source

Append to [config/sources.json](config/sources.json) under `blogs[]`:

```json
{
  "id":            "new_source_id",
  "name":          "Friendly name",
  "type":          "rss",
  "feed_url":      "https://example.com/feed.xml",
  "fetch_content": false,
  "enabled":       true,
  "fragile":       false
}
```

Set `fetch_content: true` to pull full article markdown via trafilatura for that source. Set `enabled: false` to skip without removing.

## 🧪 Tests

Offline test suites + a schema smoke test. Plain-runnable scripts (no pytest dependency):

```bash
python tests/test_schema.py                 # DB tables + indices
python tests/test_rss_blog_scraper.py       # fixture-driven
```

The fixtures under [tests/fixtures/](tests/fixtures/) are real saved RSS responses; tests work fully offline.

For runtime/DB checks, [tools/phase6_check.py](tools/phase6_check.py) runs the full Runner with `hours=72`, asserts per-source minimums, and verifies idempotency on a second run.

## 🚀 Deployment (GitHub Actions)

The daily cron lives in [.github/workflows/digest.yml](.github/workflows/digest.yml). The runner installs Python 3.12, the deps from `requirements.txt`, runs `create_tables` (idempotent), and then `python -m agent.scheduler --once --hours 48 --max-items 10`.

### Schedule

```yaml
on:
  schedule:
    - cron: '0 12 * * *'   # 12:00 UTC daily
  workflow_dispatch:
    inputs: { hours, max_items }
```

12:00 UTC lands at **08:00 EDT** (March → November, Montreal in daylight time) and **07:00 EST** (November → March). GitHub Actions cron is fixed to UTC and has no DST awareness, so the 1-hour winter drift is the lesser evil compared to running twice and double-emailing.

### Secrets

Repo → **Settings → Secrets and variables → Actions** → New repository secret. **Five mandatory:**

| Name | Value |
|---|---|
| `DATABASE_URL` | Your Neon URL — `postgresql+psycopg2://...neon.tech/...?sslmode=require&channel_binding=require` |
| `OPENAI_API_KEY` | Your `sk-proj-...` key |
| `SMTP_USER` | Sender Gmail address |
| `SMTP_PASSWORD` | Gmail App Password (16-char, no spaces in the secret) |
| `DIGEST_TO` | Recipient |

Three optional with defaults baked into the workflow (`smtp.gmail.com`, `587`, fallback to `SMTP_USER`):

| Name | Default if absent |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `DIGEST_FROM` | `${{ secrets.SMTP_USER }}` |

### Manual run / smoke test

GitHub repo → **Actions** tab → **Daily Digest** workflow → **Run workflow** button → optional `hours` and `max_items` form fields → **Run**. ~5–7 minutes later, the email arrives. Each step's stdout is preserved in the run log for 90 days.

### Free-tier capacity

| Resource | Free quota | Current usage | Headroom |
|---|---|---|---|
| **Neon storage** | 500 MB | ~1 MB | ~5 years at current ingestion rate |
| **Neon compute hours** | 191.9 hr/month | ~2.5 hr/month | 1.3% of cap |
| **GitHub Actions runner-min** (private repos) | 2,000 min/month | ~150 min/month | 7.5% of cap |
| **OpenAI tokens** | n/a (pay-as-you-go) | ~$0.15–0.25/day | ~$5–8/month |

If you flip `fetch_content: true` for blog sources, daily growth jumps to ~1 MB and you'd hit Neon's storage cap in ~12–18 months. That's the main lever.

## 📝 Limitations

What this **isn't**, by design and by current state:

**Single-tenant.** One global `DIGEST_TO`, one global source list. No user table, no auth, no per-user preferences. To change sources: edit [config/sources.json](config/sources.json).

**No retry/backoff on OpenAI rate limits.** A failed summary row is logged and stays unsummarised; the next pipeline run picks it up. No exponential backoff inside a single run.

**Long-source truncation is silent.** The summariser trims source text to 40k chars before the API call (see `MAX_SOURCE_CHARS` in [agent/summarizer.py](agent/summarizer.py)). Long full-content blog articles can lose their tail.

**No relevance ranking or cross-feed dedup.** A single AI announcement can ship as a card from `anthropic_news`, another from `techcrunch_ai`, and again from `openai_news` if everyone covers it. (Story-level cross-source deduplication via embedding + clustering is the next architecture step — see the project plan.)

**`cmu_ml` and `bair` regularly publish less than once per week.** Don't treat zero-fetched runs from those sources as failures.

**DST drift.** GitHub Actions cron is UTC-only. The daily fire is 08:00 in summer, 07:00 in winter. Acceptable for a personal digest; not acceptable if you ever need precise Montreal-local timing.

Other gotchas:
- **Anthropic feed source.** Feeds come from [Olshansk/rss-feeds](https://github.com/Olshansk/rss-feeds) on GitHub, not from Anthropic directly — freshness depends on that repo being maintained.
- **TechCrunch may Cloudflare-block** with a 403 from the runtime UA. Per-source try/except catches it; re-running usually succeeds.
- **Per-source title cleanup.** Anthropic feed titles arrive prefixed with date + category by the Olshansk mirror; `agent/digest.py:_article_title` strips that prefix only for sources whose id starts with `anthropic_`. A new upstream category leaks through unstripped.
