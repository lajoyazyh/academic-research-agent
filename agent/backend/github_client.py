"""Small GitHub REST client used for repository research and exports.

OAuth tokens are accepted per request and are never written to disk or logs.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


GITHUB_API = "https://api.github.com"
REPO_PATTERN = re.compile(r"^(?:https?://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


@dataclass
class GitHubError(Exception):
    status_code: int
    user_message: str
    code: str = "github_error"

    def __str__(self) -> str:
        return self.user_message


def validate_repo(value: str) -> tuple[str, str]:
    match = REPO_PATTERN.match((value or "").strip())
    if not match:
        raise ValueError("仓库格式应为 owner/repository 或完整 GitHub URL")
    return match.group(1), match.group(2)


class GitHubClient:
    def __init__(self, token: str = ""):
        self.token = (token or "").strip()

    def _request(self, method: str, path: str, data: dict | None = None, accept: str = "application/vnd.github+json"):
        url = path if path.startswith("http") else GITHUB_API + path
        headers = {
            "Accept": accept,
            "User-Agent": "AcademicResearchAgent/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        body = json.dumps(data).encode("utf-8") if data is not None else None
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = response.read()
                if not payload:
                    return {}
                return json.loads(payload.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("message", "")
            except Exception:
                detail = ""
            messages = {
                401: "GitHub 授权已失效，请重新连接",
                403: "GitHub 拒绝了请求；请检查仓库权限或稍后重试",
                404: "未找到仓库或当前授权无权访问",
                409: "仓库状态冲突，请确认目标分支已存在",
                422: "GitHub 无法处理该内容或路径，请检查目标分支与文件名",
            }
            raise GitHubError(exc.code, messages.get(exc.code, detail or "GitHub 请求失败"), detail or "github_http_error") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise GitHubError(503, "暂时无法连接 GitHub，请稍后重试", "github_unavailable") from exc

    def viewer(self) -> dict:
        return self._request("GET", "/user")

    def list_repositories(self, page: int = 1, per_page: int = 50) -> list[dict]:
        query = urllib.parse.urlencode({"sort": "updated", "affiliation": "owner,collaborator,organization_member", "page": page, "per_page": min(per_page, 100)})
        return self._request("GET", "/user/repos?" + query)

    def search_repositories(self, query: str, page: int = 1, per_page: int = 10) -> dict:
        params = urllib.parse.urlencode({"q": query, "sort": "stars", "order": "desc", "page": page, "per_page": min(per_page, 30)})
        return self._request("GET", "/search/repositories?" + params)

    def repository(self, owner: str, repo: str) -> dict:
        return self._request("GET", f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}")

    def readme(self, owner: str, repo: str) -> str:
        data = self._request("GET", f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/readme")
        encoded = str(data.get("content") or "").replace("\n", "")
        return base64.b64decode(encoded).decode("utf-8", errors="replace") if encoded else ""

    def tree(self, owner: str, repo: str, branch: str) -> list[dict]:
        data = self._request(
            "GET",
            f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/git/trees/{urllib.parse.quote(branch, safe='')}?recursive=1",
        )
        return data.get("tree") or []

    def file_text(self, owner: str, repo: str, path: str, ref: str = "") -> str:
        suffix = "?" + urllib.parse.urlencode({"ref": ref}) if ref else ""
        data = self._request(
            "GET",
            f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/contents/{urllib.parse.quote(path, safe='/')}" + suffix,
        )
        encoded = str(data.get("content") or "").replace("\n", "")
        return base64.b64decode(encoded).decode("utf-8", errors="replace") if encoded else ""

    def put_file(self, owner: str, repo: str, path: str, content: bytes, message: str, branch: str | None = None) -> dict:
        endpoint = f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/contents/{urllib.parse.quote(path, safe='/')}"
        existing_sha = ""
        query = "?" + urllib.parse.urlencode({"ref": branch}) if branch else ""
        try:
            existing = self._request("GET", endpoint + query)
            existing_sha = str(existing.get("sha") or "")
        except GitHubError as exc:
            if exc.status_code != 404:
                raise
        body = {
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
        }
        if existing_sha:
            body["sha"] = existing_sha
        if branch:
            body["branch"] = branch
        result = self._request("PUT", endpoint, body)
        result["branch"] = branch or self.repository(owner, repo).get("default_branch")
        return result
