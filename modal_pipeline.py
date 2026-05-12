"""
modal_pipeline.py — daily Brevio pipeline on Modal.

Wraps the existing local pipeline (`runner.Runner().run()`) and registers
it as a Modal cron job that fires once a morning. Replaces the deleted
GitHub Actions workflow with something that respects its schedule.

The mobile app will read from Neon directly via the FastAPI endpoint
(deployed separately in api/). The Modal cron is pure data production —
no email side-effect.

Modal primitives used:
  • modal.App                              — namespace for our resources
  • modal.Image                            — Debian-slim Python container,
                                             built from requirements.txt,
                                             with the project tree copied in
  • modal.Cron("0 11 * * *")               — schedule trigger
  • modal.Secret.from_name(...)            — env vars (DB URL, OPENAI key)
  • @app.function(...)                     — defines the runnable entry

One-time setup (locally, by the user):

  1. Authenticate Modal (browser SSO):
       modal setup

  2. Create the secrets (replace placeholder values):
       modal secret create brevio-db \\
           DATABASE_URL='postgresql+psycopg2://...neon.tech/...?sslmode=require'

       modal secret create brevio-openai \\
           OPENAI_API_KEY='sk-...'

  3. One-off smoke test (runs once, immediately, then exits):
       modal run modal_pipeline.py::run_pipeline_now

  4. Deploy the cron schedule (registers the daily fire):
       modal deploy modal_pipeline.py
"""
from __future__ import annotations

import modal


# ---------------------------------------------------------------------------
# Modal app + image
# ---------------------------------------------------------------------------

app = modal.App("brevio-pipeline")

# Container image: Python 3.12, our requirements installed, the project tree
# copied in at /root. `copy=True` snapshots the tree into the image so that
# `modal deploy` (not just `modal run`) sees the code at cron-fire time.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements.txt")
    .add_local_dir(
        ".",
        remote_path="/root",
        ignore=[
            # Local Python detritus
            "__pycache__",
            "**/__pycache__",
            "*.egg-info",
            ".pytest_cache/**",
            # Source control + editor metadata
            ".git/**",
            ".venv/**",
            ".vscode/**",
            ".idea/**",
            ".claude/**",
            # Local secrets — Modal injects via modal.Secret, NEVER ship .env
            ".env",
            ".env.*",
            "!.env.example",
            # JS / web build artefacts (future-proof for the Expo Web build dir)
            "node_modules/**",
            "web-build/**",
            # Experimentation snapshots (re-derivable, large)
            "experimentation/*.npz",
            "experimentation/*.png",
            "experimentation/architecture_experiments.ipynb",
            # One-off A/B output
            "tools/extractor_comparison/**",
        ],
        copy=True,
    )
    .workdir("/root")
)


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------
# Created once via `modal secret create ...` (see module docstring above).
# Each Secret becomes one or more env vars at function-invocation time.

SECRETS = [
    modal.Secret.from_name("brevio-db"),       # DATABASE_URL
    modal.Secret.from_name("brevio-openai"),   # OPENAI_API_KEY
]


# ---------------------------------------------------------------------------
# Pipeline functions
# ---------------------------------------------------------------------------
# Schedule: 11:00 UTC daily ≈ 07:00 ET in summer / 06:00 ET in winter.
# Adjust as you like — Modal honours the cron string to the second.

CRON_SCHEDULE = "0 11 * * *"

# Generous timeout: a normal daily fire finishes in 3–8 minutes (30–50 new
# articles). A multi-day catch-up after an outage can hit 25–40 minutes
# because per-article summarisation is sequential at ~3s/call. 60 min is
# enough headroom for the worst observed case (394 new articles in 15min
# of summarisation alone). Modal bills per CPU-second so this only costs
# more on rare slow runs.
TIMEOUT_SECONDS = 60 * 60


@app.function(
    image=image,
    secrets=SECRETS,
    schedule=modal.Cron(CRON_SCHEDULE),
    timeout=TIMEOUT_SECONDS,
)
def run_daily_pipeline() -> dict:
    """Cron-scheduled daily fire. Runs the full Brevio data pipeline:
    scrape → embed → cluster → per-article summarise → story synthesise.

    Mobile app reads the resulting stories from Neon directly via the
    FastAPI endpoint (see api/), so no email/SMTP side-effect here.

    Returns the runner report dict for Modal's run-history log.
    """
    import sys
    sys.path.insert(0, "/root")

    from runner import Runner

    print("=" * 60)
    print("  Brevio daily pipeline — Modal cron fire")
    print("=" * 60)

    return Runner(hours=48).run()


@app.function(
    image=image,
    secrets=SECRETS,
    timeout=TIMEOUT_SECONDS,
)
def run_pipeline_now() -> dict:
    """Manual one-off entry. Invoke locally with:
        modal run modal_pipeline.py::run_pipeline_now

    Identical to run_daily_pipeline but doesn't register a cron — used
    for smoke-testing after the first deploy or after secrets change.
    """
    import sys
    sys.path.insert(0, "/root")

    from runner import Runner

    print("=" * 60)
    print("  Brevio pipeline — manual run")
    print("=" * 60)

    return Runner(hours=48).run()


# ---------------------------------------------------------------------------
# Local entrypoint (Modal-CLI runs this when no specific function is named)
# ---------------------------------------------------------------------------

@app.local_entrypoint()
def main():
    """`modal run modal_pipeline.py` invokes this — runs the pipeline once
    in Modal's cloud and prints the report. Equivalent to
    `modal run modal_pipeline.py::run_pipeline_now`."""
    report = run_pipeline_now.remote()
    print("\nReport keys:", list(report.keys()))
    print("Done.")
