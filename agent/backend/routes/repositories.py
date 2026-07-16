"""GitHub repository discovery, inspection and evidence-grounded research."""
from __future__ import annotations

import datetime
import json
from pathlib import PurePosixPath

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.github_client import GitHubClient, GitHubError, validate_repo
from backend.provider import ensure_provider_available
from llms.client import LLMClient
from .deps import session_mgr
from .models import ProviderConfig


router = APIRouter(prefix="/api/github", tags=["github-research"])

TEXT_EXTENSIONS = {
    ".md", ".rst", ".txt", ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".kt", ".scala", ".sh",
    ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg",
}
IMPORTANT_NAMES = {
    "readme.md", "pyproject.toml", "package.json", "requirements.txt", "cargo.toml",
    "go.mod", "dockerfile", "docker-compose.yml", "contributing.md", "architecture.md",
}


class RepositorySearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    limit: int = Field(default=10, ge=1, le=20)


class RepositoryInspectRequest(BaseModel):
    repository: str = Field(min_length=3, max_length=200)


class RepositoryResearchRequest(BaseModel):
    repository: str | None = Field(default=None, max_length=200)
    query: str | None = Field(default=None, max_length=300)
    question: str = Field(default="分析该仓库的目标、架构、核心实现、工程质量、适用边界和研究价值", max_length=1000)
    session_id: str | None = Field(default=None, max_length=120)
    provider: ProviderConfig | None = None


def _token(value: str) -> str:
    return (value or "").strip()


def _repo_summary(item: dict) -> dict:
    owner = item.get("owner") or {}
    return {
        "full_name": item.get("full_name", ""),
        "name": item.get("name", ""),
        "owner": owner.get("login", ""),
        "html_url": item.get("html_url", ""),
        "description": item.get("description") or "",
        "default_branch": item.get("default_branch") or "main",
        "language": item.get("language") or "",
        "stars": item.get("stargazers_count") or 0,
        "forks": item.get("forks_count") or 0,
        "open_issues": item.get("open_issues_count") or 0,
        "license": (item.get("license") or {}).get("spdx_id", ""),
        "topics": item.get("topics") or [],
        "updated_at": item.get("updated_at") or "",
        "private": bool(item.get("private", False)),
    }


def _candidate_files(tree: list[dict], limit: int = 12) -> list[dict]:
    candidates = []
    for entry in tree:
        if entry.get("type") != "blob" or int(entry.get("size") or 0) > 120_000:
            continue
        path = str(entry.get("path") or "")
        name = PurePosixPath(path).name.lower()
        suffix = PurePosixPath(path).suffix.lower()
        if name not in IMPORTANT_NAMES and suffix not in TEXT_EXTENSIONS:
            continue
        depth = path.count("/")
        score = 0
        if name in IMPORTANT_NAMES:
            score += 100
        if path.startswith(("src/", "app/", "lib/", "agent/")):
            score += 35
        if any(marker in name for marker in ("main", "index", "api", "agent", "model", "config")):
            score += 20
        score -= depth * 4
        candidates.append((score, entry))
    candidates.sort(key=lambda item: (-item[0], item[1].get("path", "")))
    return [entry for _, entry in candidates[:limit]]


def inspect_repository(client: GitHubClient, repository: str, file_limit: int = 12) -> dict:
    owner, repo = validate_repo(repository)
    metadata = client.repository(owner, repo)
    summary = _repo_summary(metadata)
    branch = summary["default_branch"]
    try:
        readme = client.readme(owner, repo)[:20_000]
    except GitHubError:
        readme = ""
    tree = client.tree(owner, repo, branch)
    selected = _candidate_files(tree, limit=file_limit)
    files = []
    budget = 55_000
    for entry in selected:
        if budget <= 0:
            break
        path = entry.get("path", "")
        try:
            content = client.file_text(owner, repo, path, branch)[: min(12_000, budget)]
        except GitHubError:
            continue
        budget -= len(content)
        files.append({
            "path": path,
            "size": entry.get("size") or len(content),
            "url": f"https://github.com/{owner}/{repo}/blob/{branch}/{path}",
            "content": content,
        })
    summary.update({
        "readme": readme,
        "tree_file_count": sum(1 for entry in tree if entry.get("type") == "blob"),
        "files": files,
    })
    return summary


def _save_repository_source(session_id: str, source: dict) -> None:
    if not session_mgr.load_session(session_id):
        raise HTTPException(status_code=404, detail="研究项目不存在")
    directory = session_mgr.root / session_id / "repositories"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "sources.json"
    try:
        sources = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except (json.JSONDecodeError, OSError):
        sources = []
    sources = [item for item in sources if item.get("full_name") != source.get("full_name")]
    sources.append(source)
    path.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/status")
def github_status(x_github_token: str = Header(default="", alias="X-GitHub-Token")) -> dict:
    if not _token(x_github_token):
        return {"connected": False}
    try:
        viewer = GitHubClient(x_github_token).viewer()
        return {
            "connected": True,
            "login": viewer.get("login", ""),
            "name": viewer.get("name") or viewer.get("login") or "",
            "avatar_url": viewer.get("avatar_url", ""),
        }
    except GitHubError:
        return {"connected": False}


@router.get("/repositories")
def list_authorized_repositories(x_github_token: str = Header(default="", alias="X-GitHub-Token")) -> dict:
    if not _token(x_github_token):
        raise HTTPException(status_code=428, detail="请先使用 GitHub 授权连接")
    try:
        items = GitHubClient(x_github_token).list_repositories()
        return {"repositories": [_repo_summary(item) for item in items]}
    except GitHubError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.user_message) from exc


@router.post("/search")
def search_repositories(payload: RepositorySearchRequest, x_github_token: str = Header(default="", alias="X-GitHub-Token")) -> dict:
    try:
        result = GitHubClient(x_github_token).search_repositories(payload.query, per_page=payload.limit)
        return {
            "query": payload.query,
            "total_count": result.get("total_count", 0),
            "repositories": [_repo_summary(item) for item in result.get("items") or []],
        }
    except GitHubError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.user_message) from exc


@router.post("/inspect")
def inspect_repository_endpoint(payload: RepositoryInspectRequest, x_github_token: str = Header(default="", alias="X-GitHub-Token")) -> dict:
    try:
        return inspect_repository(GitHubClient(x_github_token), payload.repository)
    except GitHubError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.user_message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/research")
def research_repository(payload: RepositoryResearchRequest, x_github_token: str = Header(default="", alias="X-GitHub-Token")) -> dict:
    if not (payload.repository or payload.query):
        raise HTTPException(status_code=400, detail="请提供指定仓库或仓库检索主题")
    provider = ensure_provider_available(payload.provider)
    client = GitHubClient(x_github_token)
    try:
        inspected = []
        discovery = []
        if payload.repository:
            inspected.append(inspect_repository(client, payload.repository))
        else:
            result = client.search_repositories(payload.query or "", per_page=5)
            discovery = [_repo_summary(item) for item in result.get("items") or []]
            for item in discovery[:3]:
                inspected.append(inspect_repository(client, item["full_name"], file_limit=6))
        if not inspected:
            raise HTTPException(status_code=404, detail="没有找到可调研的 GitHub 仓库")

        llm = LLMClient(provider)
        context_blocks = []
        for repo in inspected:
            files = "\n\n".join(
                f"### {'File' if llm.language == 'en' else '文件'}: {item['path']}\nURL: {item['url']}\n```text\n{item['content']}\n```"
                for item in repo.get("files") or []
            )
            if llm.language == "en":
                context_blocks.append(
                    f"## Repository {repo['full_name']}\nURL: {repo['html_url']}\n"
                    f"Description: {repo['description']}\nDefault branch: {repo['default_branch']}\n"
                    f"Stars: {repo['stars']}; primary language: {repo['language']}; license: {repo['license']}\n\n"
                    f"### README\n{repo.get('readme') or 'Not provided'}\n\n{files}"
                )
            else:
                context_blocks.append(
                    f"## 仓库 {repo['full_name']}\nURL: {repo['html_url']}\n"
                    f"描述: {repo['description']}\n默认分支: {repo['default_branch']}\n"
                    f"Stars: {repo['stars']}，主要语言: {repo['language']}，许可证: {repo['license']}\n\n"
                    f"### README\n{repo.get('readme') or '未提供'}\n\n{files}"
                )
        context = "\n\n---\n\n".join(context_blocks)
        if llm.language == "en":
            prompt = f"""Answer the research question using only the supplied GitHub repository metadata, README files, and code excerpts.

Research question: {payload.question}

Requirements:
1. Return Markdown with: executive summary; repository selection and scope; architecture and core flow; key implementation evidence; engineering quality and maintenance signals; applicability boundaries and risks; and recommended follow-up verification.
2. Every code-level claim must cite a real file path as `[owner/repo:path]`; repository-level claims cite `[owner/repo]`.
3. Distinguish README claims from facts verified in code. Mark unread areas as “Not verified by the available material.”
4. Do not treat stars as evidence of research quality. Never fabricate runtime results, performance data, security properties, or license conclusions.
5. When several repositories are present, explain their selection and compare them across shared dimensions instead of summarizing each mechanically.

Repository evidence:
{context}
"""
            repository_system = "You are a rigorous open-source repository researcher. Draw conclusions only from the supplied repository evidence and write in English."
        else:
            prompt = f"""你是一名开源软件研究员。请根据给定的 GitHub 仓库元数据、README 和代码文件回答研究问题。

研究问题：{payload.question}

要求：
1. 输出 Markdown，包含“结论摘要、仓库选择/范围、架构与核心流程、关键实现证据、工程质量与维护信号、适用边界与风险、后续验证建议”。
2. 每个代码层面的判断必须引用真实文件路径，格式为 `[owner/repo:path]`；仓库层面的判断引用 `[owner/repo]`。
3. 区分 README 声明与代码中可验证的事实；未读取到的部分明确写“当前材料未验证”。
4. 不把 Stars 当作学术质量证据，不虚构运行结果、性能数据、安全性或许可证结论。
5. 多仓库场景需要解释选择理由并进行横向比较，不逐仓库机械复述。

【仓库材料】
{context}
"""
            repository_system = "你是严谨的开源仓库研究员，只依据提供的仓库材料下结论。"
        report = llm.chat(repository_system, prompt, []).strip()
        saved_sources = []
        for repo in inspected:
            source = {
                key: repo.get(key)
                for key in ("full_name", "owner", "html_url", "description", "default_branch", "language", "stars", "license", "updated_at")
            }
            source["files"] = [{"path": item["path"], "url": item["url"]} for item in repo.get("files") or []]
            source["report"] = report
            source["researched_at"] = datetime.datetime.now().isoformat()
            saved_sources.append(source)
            if payload.session_id:
                _save_repository_source(payload.session_id, source)
        return {
            "ok": True,
            "mode": "specified" if payload.repository else "discovery",
            "query": payload.query or "",
            "repositories": saved_sources,
            "discovery": discovery,
            "report": report,
            "saved_to_session": bool(payload.session_id),
        }
    except HTTPException:
        raise
    except GitHubError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.user_message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="仓库调研暂时失败，请检查模型配置后重试") from exc
