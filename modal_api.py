"""
modal_api.py — Brevio read-only HTTP API on Modal.

Hosts the FastAPI app defined in `api/main.py` as a Modal ASGI web
endpoint. Modal exposes it on an HTTPS URL on first `modal deploy`,
auto-scales to zero when idle, cold-starts in ~1–3s when traffic
arrives. The mobile app (Cloudflare-Pages-hosted PWA) calls this URL.

Modal primitives used:
  • modal.App                — separate "brevio-api" app, NOT the same
                                Modal app as the cron pipeline
                                (the cron + API have independent lifecycles)
  • modal.Image              — same Debian-slim image + requirements.txt
                                as the pipeline (incl. FastAPI + uvicorn)
  • modal.Secret.from_name   — reuses brevio-db (DATABASE_URL)
                                does NOT need brevio-openai (read-only,
                                no LLM calls at request time)
  • @modal.asgi_app()        — exposes the FastAPI app as a web endpoint

Deployment:
    PYTHONIOENCODING=utf-8 modal deploy modal_api.py

After deploy, Modal prints the HTTPS URL. Use that for:
  - manual curl tests: curl <url>/api/v1/health
  - the PWA's `EXPO_PUBLIC_API_URL` env var
"""
from __future__ import annotations

import modal


# ---------------------------------------------------------------------------
# Modal app + image
# ---------------------------------------------------------------------------

app = modal.App("brevio-api")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements.txt")
    .add_local_dir(
        ".",
        remote_path="/root",
        ignore=[
            # Same ignore list as modal_pipeline.py — keep .env, .venv, caches
            # out of the container. Critical for security: never ship .env.
            "__pycache__",
            "**/__pycache__",
            "*.egg-info",
            ".pytest_cache/**",
            ".git/**",
            ".venv/**",
            ".vscode/**",
            ".idea/**",
            ".claude/**",
            ".env",
            ".env.*",
            "!.env.example",
            "node_modules/**",
            "web-build/**",
            "experimentation/*.npz",
            "experimentation/*.png",
            "experimentation/architecture_experiments.ipynb",
            "tools/extractor_comparison/**",
        ],
        copy=True,
    )
    .workdir("/root")
)


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------
# Read-only API only needs Postgres. No OpenAI calls happen at request time;
# all LLM work is done in the pipeline and persisted to Neon ahead of time.

SECRETS = [
    modal.Secret.from_name("brevio-db"),       # DATABASE_URL
]


# ---------------------------------------------------------------------------
# Web endpoint
# ---------------------------------------------------------------------------

@app.function(
    image=image,
    secrets=SECRETS,
    # Scale-to-zero when idle; cold-start is fast since the image is cached.
    # min_containers=0 is the default — explicit here for documentation.
    min_containers=0,
    # Generous per-request timeout. Reads from Neon should be <1s, but bump
    # to 30s for the rare edge case where the pooler is reconnecting.
    timeout=30,
)
@modal.asgi_app()
def fastapi_app():
    """Modal serves whatever ASGI app this function returns.

    Imports happen here (rather than at module top) so Modal's image-build
    introspection doesn't try to evaluate FastAPI's lazy dependencies.
    """
    import sys
    sys.path.insert(0, "/root")
    from api.main import app as fastapi_instance
    return fastapi_instance
