"""
api/main.py — FastAPI app instance.

Registers routes under /api/v1 + CORS for the mobile-app's PWA origin.
Production deploys via Modal (modal_api.py at repo root). Local dev:

    .venv/Scripts/python.exe -m uvicorn api.main:app --reload
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import feed, health, stories


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Brevio API",
    description=(
        "Read-only HTTP API serving deduplicated news stories from Neon. "
        "Backs the Brevio mobile app (PWA + future native via Expo). "
        "Pipeline (scrape/embed/cluster/synthesise) runs separately on Modal "
        "cron — see modal_pipeline.py."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Allows the future Cloudflare-Pages-hosted PWA to call this API from any
# origin (incl. localhost during dev + `*.pages.dev` after CF deploy).
#
# Read-only, no cookies, no Authorization header (yet) — broad allow is safe.
# Tighten later if/when auth lands.

_cors_origins_env = os.environ.get("BREVIO_CORS_ORIGINS", "*").strip()
if _cors_origins_env == "*":
    cors_origins = ["*"]
else:
    cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
    max_age=3600,
)


# ---------------------------------------------------------------------------
# Routes (mounted under /api/v1)
# ---------------------------------------------------------------------------

API_V1_PREFIX = "/api/v1"

app.include_router(health.router,  prefix=API_V1_PREFIX)
app.include_router(stories.router, prefix=API_V1_PREFIX)
app.include_router(feed.router,    prefix=API_V1_PREFIX)


# ---------------------------------------------------------------------------
# Root → docs
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root():
    """Quick orientation for anyone hitting the root URL in a browser."""
    return {
        "name":    "Brevio API",
        "version": app.version,
        "docs":    "/docs",
        "v1": {
            "health":      f"{API_V1_PREFIX}/health",
            "top":         f"{API_V1_PREFIX}/stories/top",
            "all":         f"{API_V1_PREFIX}/stories/all",
            "detail":      f"{API_V1_PREFIX}/stories/<id>",
            "topic_feed":  f"{API_V1_PREFIX}/feed/topic/<topic>",
        },
    }
