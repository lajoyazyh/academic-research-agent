# Security Policy

## Secrets

Do not commit:

- `.env` files
- API keys
- GitHub or GitLab tokens
- downloaded PDFs
- generated sessions
- user prompts, traces, or private draft reviews

The repository ignores `agent/sessions/` because runtime sessions may contain private research topics, generated drafts, paper metadata, and traces.

## Public Demo Warning

This app can trigger paid LLM calls. If you deploy it publicly, protect it with authentication, rate limits, restricted API keys, or a demo-only dataset.

## Reporting Issues

Please open a GitHub issue without including secrets or private research data.

