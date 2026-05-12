"""
api/ — FastAPI read-only HTTP API for the Brevio mobile app.

Routes are namespaced under /api/v1. Production deploys via Modal
(modal_api.py at repo root), local dev runs with uvicorn:

    .venv/Scripts/python.exe -m uvicorn api.main:app --reload

The API is intentionally read-only and stateless. The mobile app
queries Neon-backed story data; writes happen only in the Modal
pipeline (modal_pipeline.py).
"""
