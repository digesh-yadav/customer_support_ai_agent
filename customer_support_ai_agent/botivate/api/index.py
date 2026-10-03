"""Vercel serverless entrypoint.

Vercel looks for an ASGI `app` inside /api. The real application lives in
backend/app, so we put backend/ on sys.path and re-export it here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402,F401
