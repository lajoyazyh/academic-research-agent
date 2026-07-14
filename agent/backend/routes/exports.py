"""Downloadable and GitHub-backed research artifact exports."""
from __future__ import annotations

import io
from pathlib import PurePosixPath
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.artifact_export import collect_artifacts, render_export
from backend.github_client import GitHubClient, GitHubError, validate_repo
from .deps import session_mgr


router = APIRouter(prefix="/api/sessions", tags=["exports"])


class GitHubExportRequest(BaseModel):
    repository: str = Field(min_length=3, max_length=200)
    path: str = Field(default="research/review.md", min_length=1, max_length=500)
    branch: str | None = Field(default=None, max_length=200)
    format: str = Field(default="md", pattern="^(md|html|txt|json)$")
    include_all: bool = True
    commit_message: str = Field(default="docs: export academic research artifacts", max_length=200)


@router.get("/{session_id}/export")
def export_session(session_id: str, format: str = "md", include_all: bool = True):
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    try:
        payload, media_type, filename = render_export(
            collect_artifacts(session), format, include_all=include_all
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    return StreamingResponse(io.BytesIO(payload), media_type=media_type, headers=headers)


@router.post("/{session_id}/export/github")
def export_session_to_github(
    session_id: str,
    payload: GitHubExportRequest,
    x_github_token: str = Header(default="", alias="X-GitHub-Token"),
) -> dict:
    if not x_github_token.strip():
        raise HTTPException(status_code=428, detail="请先使用 GitHub 授权连接")
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    try:
        owner, repo = validate_repo(payload.repository)
        content, _, filename = render_export(
            collect_artifacts(session), payload.format, include_all=payload.include_all
        )
        target_path = payload.path.strip().lstrip("/")
        if target_path.endswith("/"):
            target_path += filename
        if not target_path.lower().endswith("." + payload.format):
            target_path += "." + payload.format
        parts = PurePosixPath(target_path).parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("GitHub 文件路径无效")
        if target_path.lower().startswith(".github/workflows/"):
            raise ValueError("为安全起见，研究产物不能导出到 GitHub Actions 工作流目录")
        result = GitHubClient(x_github_token).put_file(
            owner=owner,
            repo=repo,
            path=target_path,
            content=content,
            message=payload.commit_message,
            branch=payload.branch,
        )
        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            "path": target_path,
            "branch": payload.branch or result.get("branch"),
            "commit_url": (result.get("commit") or {}).get("html_url", ""),
            "content_url": (result.get("content") or {}).get("html_url", ""),
        }
    except GitHubError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.user_message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
