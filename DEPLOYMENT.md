# Deployment Guide

This project is a FastAPI web app with a static frontend served from `agent/frontend`.

## Local Production Run

```bash
python -m pip install -r requirements.txt
cd agent
uvicorn web_app:app --host 0.0.0.0 --port 8000
```

## Docker

```bash
cp .env.example .env
docker build -t academic-research-agent .
docker run --env-file .env -p 8000:8000 academic-research-agent
```

With Compose:

```bash
docker compose up --build
```

## Render / Railway

Use the Dockerfile.

Recommended settings:

- Build command: Docker build, or leave default if the platform detects `Dockerfile`.
- Start command: handled by Dockerfile.
- Port: `8000` or platform-provided `PORT`.
- Environment variables:
  - `ZHIPU_API_KEY`
  - `ZHIPU_BASE_URL`
  - `ZHIPU_MODEL`
  - `AGENT_MIN_PAPERS`
  - `AGENT_LOOP_DELAY_SEC`

If the platform provides ephemeral storage, sessions may disappear after redeploys. For persistent demos, mount a volume at:

```text
/app/agent/sessions
```

## Fly.io

Use Docker deployment:

```bash
fly launch
fly secrets set ZHIPU_API_KEY=...
fly deploy
```

For persistent session storage, create and mount a Fly volume at `/app/agent/sessions`.

## VPS Deployment

```bash
git clone <your-repo-url>
cd academic-research-agent
cp .env.example .env
docker compose up -d --build
```

Then put Nginx or Caddy in front of `127.0.0.1:8000`.

Example Nginx location:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## Public Demo Safety

Running the full Agent can call paid LLM APIs and external academic APIs. For a public portfolio demo:

- use a limited billing key,
- add authentication,
- preload sample sessions,
- disable high-cost workflows,
- or deploy a private demo and show screenshots on your portfolio page.

## Portfolio Card Copy

**Academic Research Agent**  
An interactive AI research assistant for literature review workflows. It supports paper search, RAG-based notes, comparative analysis, editable Markdown review drafts, trace visualization, custom Skills, and cross-session knowledge retrieval.

Suggested stack tags:

```text
Python, FastAPI, LLM Agent, RAG, BM25, Embeddings, Markdown, Pytest, Docker
```

