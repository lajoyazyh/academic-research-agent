# Agent App

This directory contains the FastAPI application, static frontend, Agent pipeline, tools, and runtime session storage.

Run from this directory:

```bash
python web_app.py
```

Or from the repository root:

```bash
uvicorn web_app:app --app-dir agent --host 0.0.0.0 --port 8000
```

Runtime sessions are stored in `agent/sessions/` and are ignored by Git.

