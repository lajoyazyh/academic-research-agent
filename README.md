# Academic Research Agent

An interactive LLM agent for academic literature research and literature review drafting.

Academic Research Agent turns a research topic into a traceable research workspace: it plans search keywords, retrieves papers, generates RAG-based notes, produces comparative analysis, drafts a Markdown literature review, and keeps every intermediate artifact editable.

## Highlights

- **Interactive research workflow**: review and edit keywords, papers, notes, analysis cards, and final drafts.
- **One-click automation**: run `planning -> search -> notes -> analysis -> review` end to end.
- **Plan + ReAct + Reflexion**: explicit planning, tool-based search loops, retries, quality gates, and fallback paths.
- **RAG notes**: generate structured notes from paper abstracts or PDF text with BM25 / embedding retrieval fallback.
- **Deep analysis cards**: method comparison, research lineage, and research gaps feed into the final review writer.
- **Editable Markdown workspace**: notes, analysis cards, and review drafts use a Markdown editor in the web UI.
- **Trace observability**: inspect tool calls, errors, fallback decisions, and active Skill status.
- **Custom Skills**: configure search, note-taking, and writing behavior per workspace.
- **Cross-session Copilot**: ask questions across saved research sessions, optionally scoped to selected sessions.

## Screens and Workflow

```text
Create session
  -> plan keywords
  -> search papers
  -> generate RAG notes
  -> generate compare / lineage / gaps analysis
  -> draft literature review
  -> revise via Markdown editor or chat
```

The app supports both manual checkpoints and full automation. Manual mode is useful when users want to curate papers and edit intermediate artifacts; automatic mode is useful for quick demos and first-pass research exploration.

## Repository Layout

```text
academic-research-agent/
├── agent/                 # FastAPI app, frontend, Agent pipeline, tools
├── docs/                  # Requirements, design notes, API and architecture docs
├── evaluation/            # Optional evaluation runner and scoring utilities
├── tests/                 # Pytest tests
├── requirements.txt       # Main runtime dependencies
├── .env.example           # Environment variable template
├── Dockerfile             # Container deployment
└── DEPLOYMENT.md          # Deployment notes
```

Runtime sessions are stored under `agent/sessions/`. This directory is intentionally ignored by Git, except for a `.gitkeep` placeholder.

## Quick Start

### 1. Install

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS / Linux

python -m pip install -r requirements.txt
```

### 2. Configure

Create `.env` in the repository root or in `agent/.env`:

```env
ZHIPU_API_KEY=your_key_here
ZHIPU_MODEL=glm-4-flash
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4/

AGENT_MIN_PAPERS=3
AGENT_LOOP_DELAY_SEC=3
ARXIV_SEARCH_RETRY_LIMIT=3
```

You can also use an OpenAI-compatible provider by setting `OPENAI_API_KEY`, `ZHIPU_BASE_URL`, and `ZHIPU_MODEL` appropriately.

### 3. Run the Web App

```bash
cd agent
python web_app.py
```

Open:

```text
http://127.0.0.1:8000/
```

### 4. Run Tests

```bash
python -m pytest tests -q
```

## Docker

```bash
docker build -t academic-research-agent .
docker run --env-file .env -p 8000:8000 academic-research-agent
```

Then open `http://127.0.0.1:8000/`.

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for Render, Railway, Fly.io, VPS, Docker, and personal website portfolio notes.

For a public demo, do not expose an unrestricted paid LLM API key. Prefer one of:

- a private demo behind authentication,
- a limited-cost API key,
- a preloaded sample session,
- or a demo mode that disables expensive long-running workflows.

## Documentation

- [Requirements](docs/Agent需求文档.md)
- [System Design](docs/Agent详细设计文档.md)
- [API Reference](docs/API接口文档.md)
- [Optimization Report](docs/Agent优化文档.md)
- [Architecture Analysis](docs/项目架构分析.md)

## Evaluation

The `evaluation/` directory contains an optional standalone evaluation runner and fallback scoring utilities. It can be used to compare generated answers or reviews against reference data, even when some third-party evaluation dependencies are unavailable.

## Security Notes

- Never commit `.env`, API keys, tokens, session data, or downloaded PDFs.
- `agent/sessions/` is ignored because it may contain user prompts, generated drafts, traces, and paper PDFs.
- Check copyright before redistributing downloaded papers or generated datasets.

## License

MIT License. See [LICENSE](LICENSE).

