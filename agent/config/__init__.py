"""Shared path constants for the Academic Agent app."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
DOCS_DIR = BASE_DIR / "documents"
SESSIONS_ROOT = str(BASE_DIR / "sessions")
SESSIONS_DIR = Path(SESSIONS_ROOT)
TOOLS_CONFIG = BASE_DIR / "config" / "tools.json"
