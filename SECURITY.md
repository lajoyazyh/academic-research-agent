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

## BYOK Handling

Public deployments should use BYOK mode. Request-scoped API keys:

- are sent only in LLM-triggering requests,
- are used in memory by the backend client,
- are not written to `agent/sessions/`,
- are not stored in traces or metadata,
- are not echoed in error messages.

The optional browser "Save locally" setting stores the key in the visitor's own `localStorage`; it is not a server-side feature.

## Public Demo Warning

This app can trigger paid LLM calls. If you deploy it publicly, do not configure an unrestricted private server-side key unless you also add authentication, rate limits, and billing safeguards.

## Reporting Issues

Please open a GitHub issue without including secrets or private research data.
