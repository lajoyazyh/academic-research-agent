"""Supabase-backed persistence for public, multi-user research workspaces.

The agent still executes against a tenant-scoped temporary filesystem because
many mature research tools expect paths. Durable state is database-first:

* Postgres stores queryable sessions, papers, artifacts, conversations, runs,
  and file metadata.
* Supabase Storage stores a small per-session compatibility archive plus large
  paper files as independent objects.
* The legacy per-user workspace.zip is read only as a one-time migration source.

API keys, GitHub tokens, and authorization headers never enter this store.
"""
from __future__ import annotations

import datetime
import hashlib
import io
import json
import mimetypes
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Iterable

from backend.tenant import tenant_key, tenant_path


SECRET_FIELDS = {"api_key", "authorization", "github_token", "x_github_token", "provider_token"}
STATE_LABELS = {
    "planning": "规划中",
    "plan_confirmed": "规划已确认",
    "searching": "检索中",
    "search_complete": "检索完成",
    "reviewing_notes": "整理笔记",
    "writing": "撰写中",
    "complete": "已完成",
}


class RemoteStoreError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"Supabase request failed ({status}): {body[:300]}")
        self.status = status
        self.body = body


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _safe_json(item)
            for key, item in value.items()
            if str(key).lower() not in SECRET_FIELDS and not str(key).startswith("_")
        }
    if isinstance(value, (list, tuple)):
        return [_safe_json(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _timestamp(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class SupabaseWorkspaceStore:
    """Relational read model plus on-demand filesystem materialization."""

    def __init__(self, sessions_root: str | Path):
        self.sessions_root = Path(sessions_root)
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "research-workspaces")
        self._lock = threading.RLock()
        self._index_ready: set[str] = set()
        self._legacy_hydrated: set[str] = set()
        # Backward-compatible diagnostic name used by existing health tests.
        self._hydrated = self._legacy_hydrated
        self._auxiliary_hydrated: set[str] = set()
        self._hydrated_sessions: set[str] = set()
        self._last_fingerprint: dict[str, str] = {}
        self._pending: dict[str, threading.Timer] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.service_key)

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        data: bytes | None = None,
        content_type: str = "application/json",
        extra_headers: dict | None = None,
        timeout: int = 30,
    ):
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": content_type,
        }
        headers.update(extra_headers or {})
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RemoteStoreError(exc.code, body) from exc

    def _json_request(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: Any = None,
        extra_headers: dict | None = None,
    ) -> Any:
        data = None if payload is None else json.dumps(_safe_json(payload), ensure_ascii=False).encode("utf-8")
        try:
            with self._request(url, method=method, data=data, extra_headers=extra_headers) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RemoteStoreError(exc.code, body) from exc
        return json.loads(raw.decode("utf-8")) if raw else None

    def _rest_url(self, table: str, query: str = "") -> str:
        return f"{self.url}/rest/v1/{table}{'?' + query if query else ''}"

    @staticmethod
    def _missing_relation(error: RemoteStoreError) -> bool:
        body = error.body.lower()
        return (
            error.status == 404
            or "pgrst205" in body
            or "does not exist" in body
            or (error.status == 400 and "not_found" in body)
        )

    def _select(self, table: str, query: str) -> list[dict] | None:
        try:
            result = self._json_request(self._rest_url(table, query))
            return result if isinstance(result, list) else []
        except RemoteStoreError as exc:
            if self._missing_relation(exc):
                return None
            raise

    def _upsert(self, table: str, rows: dict | list[dict], conflict: str) -> None:
        items = rows if isinstance(rows, list) else [rows]
        if not items:
            return
        query = urllib.parse.urlencode({"on_conflict": conflict}, safe=",")
        self._json_request(
            self._rest_url(table, query),
            method="POST",
            payload=items,
            extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )

    def _delete(self, table: str, filters: dict[str, str]) -> None:
        query = urllib.parse.urlencode(filters, safe="(),.*_-")
        self._json_request(
            self._rest_url(table, query),
            method="DELETE",
            extra_headers={"Prefer": "return=minimal"},
        )

    def _download_object(self, object_key: str) -> bytes | None:
        quoted = urllib.parse.quote(object_key, safe="/")
        try:
            with self._request(f"{self.url}/storage/v1/object/{self.bucket}/{quoted}") as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404 or (
                exc.code == 400 and ("not_found" in body.lower() or "object not found" in body.lower())
            ):
                return None
            raise RemoteStoreError(exc.code, body) from exc
        except RemoteStoreError as exc:
            body = exc.body.lower()
            if exc.status == 404 or (exc.status == 400 and ("not_found" in body or "object not found" in body)):
                return None
            raise

    def _upload_object(self, object_key: str, data: bytes, content_type: str) -> None:
        quoted = urllib.parse.quote(object_key, safe="/")
        with self._request(
            f"{self.url}/storage/v1/object/{self.bucket}/{quoted}",
            method="POST",
            data=data,
            content_type=content_type,
            extra_headers={"x-upsert": "true"},
        ):
            pass

    def _delete_objects(self, object_keys: Iterable[str]) -> None:
        prefixes = sorted({str(item) for item in object_keys if item})
        if not prefixes:
            return
        try:
            self._json_request(
                f"{self.url}/storage/v1/object/{self.bucket}",
                method="DELETE",
                payload={"prefixes": prefixes},
            )
        except RemoteStoreError:
            # Relational deletion is authoritative. Orphan cleanup can be retried
            # without turning a successful user deletion into a 500 response.
            pass

    @staticmethod
    def _workspace_files(source: Path):
        for path in source.rglob("*"):
            if not path.is_file() or ".embed_cache" in path.parts or path.name.endswith(".tmp"):
                continue
            yield path

    @staticmethod
    def _is_external_file(relative_path: Path) -> bool:
        return (
            len(relative_path.parts) > 1
            and relative_path.parts[0] == "papers"
            and relative_path.name not in {"papers_list.json", "deleted_papers.json"}
        )

    def _fingerprint(self, source: Path) -> str:
        digest = hashlib.sha256()
        if not source.exists():
            return digest.hexdigest()
        for path in sorted(self._workspace_files(source), key=lambda item: item.as_posix()):
            stat = path.stat()
            digest.update(path.relative_to(source).as_posix().encode("utf-8"))
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
        return digest.hexdigest()

    def _session_archive(self, source: Path) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in self._workspace_files(source):
                relative = path.relative_to(source)
                if self._is_external_file(relative):
                    continue
                bundle.write(path, relative.as_posix())
        return buffer.getvalue()

    def _auxiliary_archive(self, root: Path) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in self._workspace_files(root):
                relative = path.relative_to(root)
                if not relative.parts or not relative.parts[0].startswith("."):
                    continue
                if relative.parts[0] == ".runs":
                    continue
                bundle.write(path, relative.as_posix())
        return buffer.getvalue()

    def _extract_archive(self, archive: bytes, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            resolved_target = target.resolve()
            for member in bundle.infolist():
                destination = (target / member.filename).resolve()
                if resolved_target not in destination.parents and destination != resolved_target:
                    raise ValueError("Invalid workspace archive path")
            bundle.extractall(target)

    def _snapshot_from_dir(self, session_dir: Path) -> tuple[dict, dict]:
        metadata = _read_json(session_dir / "metadata.json", {}) or {}
        keywords = _read_json(session_dir / "plan" / "confirmed_keywords.json", []) or []
        papers = _read_json(session_dir / "papers" / "papers_list.json", []) or []
        notes = _read_text(session_dir / "notes" / "draft_notes.md")
        initial_plan = _read_text(session_dir / "plan" / "initial_plan.md")
        review_dir = session_dir / "review"
        review = _read_text(review_dir / "current_review.md")
        review_files = sorted(review_dir.glob("review_v*.md"), reverse=True) if review_dir.exists() else []
        if not review and review_files:
            review = _read_text(review_files[0])
        review_version = 0
        if review_files:
            match = re.search(r"review_v(\d+)", review_files[0].name)
            review_version = int(match.group(1)) if match else 0
        traces = _read_json(session_dir / "traces" / "run_traces.json", []) or []
        analysis = _read_json(session_dir / "analysis" / "analysis_results.json", {}) or {}
        repositories = _read_json(session_dir / "repositories" / "sources.json", []) or []
        review_quality = _read_json(review_dir / "quality.json", {}) or {}
        search_runs = _read_json(session_dir / "plan" / "search_runs.json", []) or []
        conversations = _read_json(session_dir / "chats" / "index.json", []) or []
        methodology_dir = session_dir / "methodology"
        scientific = {
            name[:-5]: _read_json(methodology_dir / name, [] if name not in {"current_protocol.json"} else {})
            for name in (
                "protocols.json",
                "current_protocol.json",
                "search_queries.json",
                "candidates.json",
                "screening_decisions.json",
                "extractions.json",
                "appraisals.json",
                "inclusion_snapshots.json",
                "synthesis_groups.json",
                "claims.json",
                "review_versions.json",
            )
        }
        accepted_ids = sorted(
            str(paper.get("paper_id"))
            for paper in papers
            if isinstance(paper, dict) and paper.get("status") == "accepted" and paper.get("paper_id")
        )
        referenced_ids = sorted(str(item) for item in metadata.get("review_referenced_papers", []) if item)
        snapshot = {
            "session_id": metadata.get("session_id", session_dir.name),
            "topic": metadata.get("topic", ""),
            "state": metadata.get("state", "planning"),
            "created_at": metadata.get("created_at", ""),
            "updated_at": metadata.get("updated_at", ""),
            "rewrite_count": metadata.get("rewrite_count", 0),
            "workflow_version": metadata.get("workflow_version", 1),
            "skills": metadata.get("skills", {}),
            "review_referenced_papers": metadata.get("review_referenced_papers", []),
            "initial_plan": initial_plan,
            "keywords": keywords,
            "papers": papers,
            "notes": notes,
            "review": review,
            "review_version": review_version,
            "draft": review,
            "draft_version": review_version,
            "traces": traces,
            "analysis": analysis,
            "repositories": repositories,
            "review_quality": review_quality,
            "review_is_stale": bool(review) and accepted_ids != referenced_ids,
            "accepted_paper_ids": accepted_ids,
            "search_runs": search_runs,
            "conversations": conversations,
            "scientific": scientific,
        }
        total_notes = sum(
            1 for paper in papers
            if isinstance(paper, dict) and str(paper.get("notes") or "").strip()
        )
        summary = {
            "session_id": snapshot["session_id"],
            "topic": snapshot["topic"],
            "state": snapshot["state"],
            "state_label": STATE_LABELS.get(snapshot["state"], "未知"),
            "created_at": snapshot["created_at"],
            "updated_at": snapshot["updated_at"],
            "paper_count": len(papers),
            "note_size": len(notes.encode("utf-8")),
            "total_notes": total_notes,
            "review_count": len(review_files) or (1 if review else 0),
            "review_version": review_version,
        }
        return _safe_json(snapshot), summary

    def _materialize_snapshot(self, target: Path, snapshot: dict) -> None:
        target.mkdir(parents=True, exist_ok=True)
        metadata = {
            "session_id": snapshot.get("session_id", target.name),
            "topic": snapshot.get("topic", ""),
            "state": snapshot.get("state", "planning"),
            "created_at": snapshot.get("created_at", ""),
            "updated_at": snapshot.get("updated_at", ""),
            "rewrite_count": snapshot.get("rewrite_count", 0),
            "skills": snapshot.get("skills", {}),
            "review_referenced_papers": snapshot.get("review_referenced_papers", []),
            "workflow_version": snapshot.get("workflow_version", 1),
        }
        files: list[tuple[Path, Any, bool]] = [
            (target / "metadata.json", metadata, True),
            (target / "plan" / "confirmed_keywords.json", snapshot.get("keywords", []), True),
            (target / "papers" / "papers_list.json", snapshot.get("papers", []), True),
            (target / "traces" / "run_traces.json", snapshot.get("traces", []), True),
            (target / "analysis" / "analysis_results.json", snapshot.get("analysis", {}), True),
            (target / "repositories" / "sources.json", snapshot.get("repositories", []), True),
            (target / "review" / "quality.json", snapshot.get("review_quality", {}), True),
            (target / "plan" / "search_runs.json", snapshot.get("search_runs", []), True),
            (target / "chats" / "index.json", snapshot.get("conversations", []), True),
            (target / "plan" / "initial_plan.md", snapshot.get("initial_plan", ""), False),
            (target / "notes" / "draft_notes.md", snapshot.get("notes", ""), False),
            (target / "review" / "current_review.md", snapshot.get("review", ""), False),
        ]
        for name, value in (snapshot.get("scientific") or {}).items():
            files.append((target / "methodology" / f"{name}.json", value, True))
        version = _integer(snapshot.get("review_version")) or 0
        if version and snapshot.get("review"):
            files.append((target / "review" / f"review_v{version}.md", snapshot["review"], False))
        for path, value, is_json in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            if is_json:
                path.write_text(json.dumps(_safe_json(value), ensure_ascii=False, indent=2), encoding="utf-8")
            elif value:
                path.write_text(str(value), encoding="utf-8")

    def _legacy_workspace(self, user_id: str) -> bool:
        key = tenant_key(user_id)
        if key in self._legacy_hydrated:
            return tenant_path(self.sessions_root, user_id).exists()
        self._legacy_hydrated.add(key)
        archive = self._download_object(f"{key}/workspace.zip")
        if not archive:
            return False
        self._extract_archive(archive, tenant_path(self.sessions_root, user_id))
        return True

    def _select_session_rows(self, user_id: str) -> list[dict] | None:
        query = urllib.parse.urlencode({
            "select": (
                "session_id,topic,state,state_label,created_at,updated_at,"
                "paper_count,note_size,total_notes,review_count,review_version"
            ),
            "user_id": f"eq.{user_id}",
            "order": "updated_at.desc",
        }, safe=",.*_-")
        return self._select("research_sessions", query)

    def ensure_index(self, user_id: str) -> bool:
        """Ensure old workspace.zip data has been imported once."""
        if not self.enabled or user_id == "local":
            return False
        key = tenant_key(user_id)
        with self._lock:
            if key in self._index_ready:
                return True
            rows = self._select_session_rows(user_id)
            if rows is None:
                return False
            if not rows and self._legacy_workspace(user_id):
                root = tenant_path(self.sessions_root, user_id)
                bootstrap_rows = []
                for session_dir in root.iterdir():
                    if session_dir.is_dir() and not session_dir.name.startswith(".") and (
                        session_dir / "metadata.json"
                    ).exists():
                        snapshot, summary = self._snapshot_from_dir(session_dir)
                        bootstrap_rows.append({
                            "user_id": user_id,
                            **summary,
                            "created_at": _timestamp(summary.get("created_at")),
                            "updated_at": _timestamp(summary.get("updated_at"))
                                or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            "snapshot": snapshot,
                        })
                if bootstrap_rows:
                    self._upsert(
                        "research_sessions",
                        bootstrap_rows,
                        "user_id,session_id",
                    )
                # Large PDFs/full text are copied after the relational index is
                # already available, so the one-time migration does not block
                # the user's first session list.
                self.schedule_sync(user_id, delay_seconds=0.2)
            self._index_ready.add(key)
            return True

    def list_sessions(self, user_id: str) -> list[dict] | None:
        if not self.ensure_index(user_id):
            return None
        rows = self._select_session_rows(user_id)
        return rows if rows is not None else None

    def get_stats(self, user_id: str) -> dict | None:
        sessions = self.list_sessions(user_id)
        if sessions is None:
            return None
        state_counts: dict[str, int] = {}
        activities = []
        for session in sessions:
            label = session.get("state_label") or STATE_LABELS.get(session.get("state", ""), "未知")
            state_counts[label] = state_counts.get(label, 0) + 1
            activities.append({
                "time": session.get("updated_at") or session.get("created_at") or "",
                "topic": session.get("topic", ""),
                "state": session.get("state", "planning"),
                "state_label": label,
                "session_id": session.get("session_id", ""),
                "paper_count": session.get("paper_count", 0),
            })
        activities.sort(key=lambda item: item["time"], reverse=True)
        return {
            "total_sessions": len(sessions),
            "active_sessions": sum(1 for item in sessions if item.get("state") != "complete"),
            "total_papers": sum(int(item.get("paper_count") or 0) for item in sessions),
            "total_notes": sum(int(item.get("total_notes") or 0) for item in sessions),
            "total_reviews": sum(int(item.get("review_count") or 0) for item in sessions),
            "state_breakdown": state_counts,
            "recent_activity": activities[0] if activities else None,
            "recent_activities": activities[:5],
        }

    def _session_snapshot(self, user_id: str, session_id: str) -> dict | None:
        query = urllib.parse.urlencode({
            "select": "snapshot",
            "user_id": f"eq.{user_id}",
            "session_id": f"eq.{session_id}",
            "limit": "1",
        }, safe=",.*_-")
        rows = self._select("research_sessions", query)
        if rows:
            snapshot = rows[0].get("snapshot")
            return snapshot if isinstance(snapshot, dict) else None
        return None

    def hydrate_session(self, user_id: str, session_id: str, *, include_files: bool = False) -> bool:
        if not self.enabled or user_id == "local":
            return False
        safe_session_id = Path(session_id).name
        if safe_session_id != session_id:
            return False
        target = tenant_path(self.sessions_root, user_id) / safe_session_id
        cache_key = f"{tenant_key(user_id)}:{safe_session_id}"
        with self._lock:
            if cache_key not in self._hydrated_sessions:
                if not (target / "metadata.json").exists():
                    self.ensure_index(user_id)
                    archive = self._download_object(
                        f"{tenant_key(user_id)}/sessions/{safe_session_id}/session.zip"
                    )
                    if archive:
                        self._extract_archive(archive, target)
                    else:
                        snapshot = self._session_snapshot(user_id, safe_session_id)
                        if snapshot:
                            self._materialize_snapshot(target, snapshot)
                        elif self._legacy_workspace(user_id):
                            target = tenant_path(self.sessions_root, user_id) / safe_session_id
                self._materialize_relational_children(user_id, safe_session_id, target)
                self._hydrated_sessions.add(cache_key)
        if include_files:
            self.hydrate_session_files(user_id, safe_session_id)
        return (target / "metadata.json").exists()

    def hydrate(self, user_id: str, *, include_files: bool = False) -> None:
        """Compatibility entry point for features that need every session."""
        self._hydrate_auxiliary(user_id)
        sessions = self.list_sessions(user_id)
        if sessions is None:
            self._legacy_workspace(user_id)
            return
        for session in sessions:
            session_id = str(session.get("session_id") or "")
            if session_id:
                self.hydrate_session(user_id, session_id, include_files=include_files)

    def _hydrate_auxiliary(self, user_id: str) -> None:
        key = tenant_key(user_id)
        if key in self._auxiliary_hydrated:
            return
        archive = self._download_object(f"{key}/workspace-aux.zip")
        if archive:
            self._extract_archive(archive, tenant_path(self.sessions_root, user_id))
        elif self._legacy_workspace(user_id):
            self._sync_auxiliary(user_id, tenant_path(self.sessions_root, user_id))
        self._auxiliary_hydrated.add(key)

    def _materialize_relational_children(self, user_id: str, session_id: str, target: Path) -> None:
        conversations_query = urllib.parse.urlencode({
            "select": "conversation_id,title,message_count,created_at,updated_at,metadata",
            "user_id": f"eq.{user_id}",
            "session_id": f"eq.{session_id}",
            "order": "updated_at.asc",
        }, safe=",.*_-")
        conversations = self._select("research_conversations", conversations_query) or []
        if conversations:
            index = []
            chats_dir = target / "chats"
            chats_dir.mkdir(parents=True, exist_ok=True)
            for conversation in conversations:
                conversation_id = str(conversation.get("conversation_id") or "")
                if not conversation_id:
                    continue
                index.append({
                    "conv_id": conversation_id,
                    "title": conversation.get("title", ""),
                    "message_count": conversation.get("message_count", 0),
                    "created_at": conversation.get("created_at", ""),
                    "updated_at": conversation.get("updated_at", ""),
                    **(conversation.get("metadata") or {}),
                })
                message_query = urllib.parse.urlencode({
                    "select": "message_index,payload,role,content,created_at",
                    "user_id": f"eq.{user_id}",
                    "session_id": f"eq.{session_id}",
                    "conversation_id": f"eq.{conversation_id}",
                    "order": "message_index.asc",
                }, safe=",.*_-")
                rows = self._select("research_messages", message_query) or []
                messages = []
                for row in rows:
                    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
                    messages.append({
                        **payload,
                        "role": row.get("role", payload.get("role", "")),
                        "content": row.get("content", payload.get("content", "")),
                        "created_at": row.get("created_at", payload.get("created_at", "")),
                    })
                (chats_dir / f"{conversation_id}.json").write_text(
                    json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            (chats_dir / "index.json").write_text(
                json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        runs_query = urllib.parse.urlencode({
            "select": "*",
            "user_id": f"eq.{user_id}",
            "session_id": f"eq.{session_id}",
            "order": "updated_at.asc",
        }, safe=",.*_-")
        runs = self._select("research_runs", runs_query) or []
        if runs:
            run_dir = tenant_path(self.sessions_root, user_id) / ".runs" / session_id
            run_dir.mkdir(parents=True, exist_ok=True)
            for row in runs:
                run = {
                    "run_id": row.get("run_id", ""),
                    "session_id": session_id,
                    "kind": row.get("kind", ""),
                    "status": row.get("status", ""),
                    "phase": row.get("phase", ""),
                    "checkpoint": row.get("checkpoint", ""),
                    "retryable": bool(row.get("retryable")),
                    "payload": row.get("payload") or {},
                    "progress": row.get("progress") or {},
                    "message": row.get("message", ""),
                    "error_code": row.get("error_code"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                }
                (run_dir / f"{Path(run['run_id']).name}.json").write_text(
                    json.dumps(_safe_json(run), ensure_ascii=False, indent=2), encoding="utf-8"
                )

    def hydrate_session_files(self, user_id: str, session_id: str) -> int:
        query = urllib.parse.urlencode({
            "select": "relative_path,object_key,sha256",
            "user_id": f"eq.{user_id}",
            "session_id": f"eq.{session_id}",
        }, safe=",.*_-")
        rows = self._select("research_files", query) or []
        target = tenant_path(self.sessions_root, user_id) / session_id
        restored = 0
        for row in rows:
            relative = Path(str(row.get("relative_path") or ""))
            destination = (target / relative).resolve()
            resolved_target = target.resolve()
            if resolved_target not in destination.parents:
                continue
            if destination.exists():
                continue
            data = self._download_object(str(row.get("object_key") or ""))
            if data is None:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            restored += 1
        return restored

    def hydrate_file(self, user_id: str, session_id: str, relative_path: str) -> Path | None:
        relative = Path(relative_path)
        target = tenant_path(self.sessions_root, user_id) / session_id
        destination = (target / relative).resolve()
        if target.resolve() not in destination.parents:
            return None
        if destination.exists():
            return destination
        query = urllib.parse.urlencode({
            "select": "object_key",
            "user_id": f"eq.{user_id}",
            "session_id": f"eq.{session_id}",
            "relative_path": f"eq.{relative.as_posix()}",
            "limit": "1",
        }, safe=",.*_-/")
        rows = self._select("research_files", query) or []
        if not rows:
            return None
        data = self._download_object(str(rows[0].get("object_key") or ""))
        if data is None:
            return None
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return destination

    def schedule_sync(
        self,
        user_id: str,
        *,
        session_id: str | None = None,
        delay_seconds: float = 0.8,
    ) -> None:
        if not self.enabled or user_id == "local":
            return
        pending_key = f"{tenant_key(user_id)}:{session_id or '*'}"
        with self._lock:
            previous = self._pending.pop(pending_key, None)
            if previous:
                previous.cancel()

            def flush():
                try:
                    self.sync(user_id, session_id=session_id)
                except Exception as exc:
                    print(f"[WorkspaceSync] scheduled relational sync failed for {pending_key}: {exc}")
                finally:
                    with self._lock:
                        self._pending.pop(pending_key, None)

            timer = threading.Timer(max(0.1, delay_seconds), flush)
            timer.daemon = True
            self._pending[pending_key] = timer
            timer.start()

    def sync(self, user_id: str, session_id: str | None = None) -> None:
        if not self.enabled or user_id == "local":
            return
        root = tenant_path(self.sessions_root, user_id)
        if not root.exists():
            return
        with self._lock:
            if session_id:
                candidates = [root / Path(session_id).name]
            else:
                candidates = [path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")]
            for session_dir in candidates:
                if (session_dir / "metadata.json").exists():
                    self._sync_session(user_id, session_dir)
            self._sync_auxiliary(user_id, root)
            self._index_ready.add(tenant_key(user_id))

    def _sync_auxiliary(self, user_id: str, root: Path) -> None:
        archive = self._auxiliary_archive(root)
        fingerprint = hashlib.sha256(archive).hexdigest()
        fingerprint_key = f"{tenant_key(user_id)}:auxiliary"
        if self._last_fingerprint.get(fingerprint_key) == fingerprint:
            return
        self._upload_object(
            f"{tenant_key(user_id)}/workspace-aux.zip",
            archive,
            "application/zip",
        )
        self._last_fingerprint[fingerprint_key] = fingerprint

    def _sync_session(
        self,
        user_id: str,
        session_dir: Path,
        *,
        include_external_files: bool = True,
    ) -> None:
        session_id = session_dir.name
        fingerprint_key = f"{tenant_key(user_id)}:{session_id}"
        fingerprint = self._fingerprint(session_dir)
        if self._last_fingerprint.get(fingerprint_key) == fingerprint:
            return
        snapshot, summary = self._snapshot_from_dir(session_dir)
        session_row = {
            "user_id": user_id,
            **summary,
            "created_at": _timestamp(summary.get("created_at")),
            "updated_at": _timestamp(summary.get("updated_at"))
                or datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "snapshot": snapshot,
        }
        self._upsert("research_sessions", session_row, "user_id,session_id")
        self._sync_papers(user_id, session_id, snapshot.get("papers") or [])
        self._sync_artifacts(user_id, session_id, snapshot)
        self._sync_scientific(user_id, session_id, snapshot.get("scientific") or {})
        self._sync_conversations(user_id, session_dir)
        self._sync_runs(user_id, session_id)
        if include_external_files:
            self._sync_external_files(user_id, session_dir)
        archive_key = f"{tenant_key(user_id)}/sessions/{session_id}/session.zip"
        self._upload_object(archive_key, self._session_archive(session_dir), "application/zip")
        if include_external_files:
            self._last_fingerprint[fingerprint_key] = fingerprint
        self._hydrated_sessions.add(fingerprint_key)

    def _replace_children(self, table: str, user_id: str, session_id: str, rows: list[dict], conflict: str) -> None:
        self._delete(table, {"user_id": f"eq.{user_id}", "session_id": f"eq.{session_id}"})
        if rows:
            self._upsert(table, rows, conflict)

    def _sync_papers(self, user_id: str, session_id: str, papers: list[dict]) -> None:
        rows = []
        for paper in papers:
            if not isinstance(paper, dict) or not paper.get("paper_id"):
                continue
            year = _integer(paper.get("year") or paper.get("published_year"))
            authors = paper.get("authors") or []
            if isinstance(authors, str):
                authors = [item.strip() for item in authors.split(",") if item.strip()]
            rows.append({
                "user_id": user_id,
                "session_id": session_id,
                "paper_id": str(paper["paper_id"]),
                "title": str(paper.get("title") or ""),
                "status": str(paper.get("status") or "pending"),
                "source_type": str(paper.get("source_type") or paper.get("source") or ""),
                "published_year": year,
                "authors": authors,
                "metadata": paper,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
        self._replace_children(
            "research_papers", user_id, session_id, rows, "user_id,session_id,paper_id"
        )

    def _sync_artifacts(self, user_id: str, session_id: str, snapshot: dict) -> None:
        artifacts = [
            ("initial_plan", 0, snapshot.get("initial_plan", ""), None),
            ("notes", 0, snapshot.get("notes", ""), None),
            ("review", int(snapshot.get("review_version") or 0), snapshot.get("review", ""), None),
            ("analysis", 0, None, snapshot.get("analysis") or {}),
            ("traces", 0, None, snapshot.get("traces") or []),
            ("repositories", 0, None, snapshot.get("repositories") or []),
            ("review_quality", 0, None, snapshot.get("review_quality") or {}),
            ("search_runs", 0, None, snapshot.get("search_runs") or []),
            ("scientific_methodology", 0, None, snapshot.get("scientific") or {}),
        ]
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rows = [
            {
                "user_id": user_id,
                "session_id": session_id,
                "kind": kind,
                "version": version,
                "content_text": text,
                "content_json": data,
                "metadata": {},
                "updated_at": now,
            }
            for kind, version, text, data in artifacts
            if text or data
        ]
        self._replace_children(
            "research_artifacts", user_id, session_id, rows, "user_id,session_id,kind,version"
        )

    def _sync_scientific(self, user_id: str, session_id: str, scientific: dict) -> None:
        """Mirror scientific workflow state into queryable Postgres relations."""
        if not scientific:
            return
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        protocols = scientific.get("protocols") or []
        search_queries = scientific.get("search_queries") or []
        candidates = scientific.get("candidates") or []
        decisions = scientific.get("screening_decisions") or []
        extractions = scientific.get("extractions") or []
        appraisals = scientific.get("appraisals") or []
        snapshots = scientific.get("inclusion_snapshots") or []
        synthesis_groups = scientific.get("synthesis_groups") or []
        claims = scientific.get("claims") or []
        review_versions = scientific.get("review_versions") or []
        try:
            protocol_rows = [{
                "user_id": user_id,
                "session_id": session_id,
                "protocol_id": str(item.get("protocol_id") or ""),
                "version": int(item.get("version") or 1),
                "status": str(item.get("status") or "draft"),
                "mode": str(item.get("mode") or "rapid"),
                "research_question": str(item.get("research_question") or ""),
                "candidate_cap": int(item.get("candidate_cap") or 100),
                "protocol": item,
                "created_at": _timestamp(item.get("created_at")) or now,
                "updated_at": _timestamp(item.get("updated_at")) or now,
            } for item in protocols if item.get("protocol_id")]
            self._replace_children(
                "review_protocols", user_id, session_id, protocol_rows,
                "user_id,session_id,protocol_id",
            )

            query_rows = [{
                "user_id": user_id,
                "session_id": session_id,
                "search_query_id": str(item.get("search_query_id") or ""),
                "protocol_id": str(item.get("protocol_id") or ""),
                "source": str(item.get("source") or ""),
                "query_text": str(item.get("query") or ""),
                "status": str(item.get("status") or "pending"),
                "query_data": item,
                "created_at": _timestamp(item.get("created_at")) or now,
                "completed_at": _timestamp(item.get("completed_at")),
            } for item in search_queries if item.get("search_query_id") and item.get("protocol_id")]
            self._replace_children(
                "review_search_queries", user_id, session_id, query_rows,
                "user_id,session_id,search_query_id",
            )

            candidate_rows = [{
                "user_id": user_id,
                "session_id": session_id,
                "candidate_id": str(item.get("candidate_id") or ""),
                "protocol_id": str(item.get("protocol_id") or ""),
                "paper_id": str(item.get("paper_id") or ""),
                "status": str(item.get("status") or "candidate"),
                "screening_stage": str(item.get("screening_stage") or "discovered"),
                "record": item,
                "discovered_at": _timestamp(item.get("discovered_at")) or now,
                "updated_at": _timestamp(item.get("updated_at")) or now,
            } for item in candidates if item.get("candidate_id") and item.get("protocol_id")]
            self._replace_children(
                "research_candidates", user_id, session_id, candidate_rows,
                "user_id,session_id,candidate_id",
            )

            decision_rows = [{
                "user_id": user_id,
                "session_id": session_id,
                "decision_id": str(item.get("decision_id") or ""),
                "protocol_id": str(item.get("protocol_id") or ""),
                "candidate_id": str(item.get("candidate_id") or ""),
                "paper_id": str(item.get("paper_id") or ""),
                "stage": str(item.get("stage") or "title_abstract"),
                "decision": str(item.get("decision") or "uncertain"),
                "reason_code": item.get("reason_code"),
                "reviewer": str(item.get("reviewer") or "human"),
                "decision_data": item,
                "created_at": _timestamp(item.get("created_at")) or now,
            } for item in decisions if item.get("decision_id") and item.get("candidate_id")]
            self._replace_children(
                "screening_decisions", user_id, session_id, decision_rows,
                "user_id,session_id,decision_id",
            )

            extraction_rows = [{
                "user_id": user_id,
                "session_id": session_id,
                "extraction_id": str(item.get("extraction_id") or ""),
                "protocol_id": str(item.get("protocol_id") or ""),
                "paper_id": str(item.get("paper_id") or ""),
                "evidence_basis": str(item.get("evidence_basis") or "unknown"),
                "review_status": str(item.get("review_status") or "ai_draft"),
                "extraction": item,
                "created_at": _timestamp(item.get("created_at")) or now,
                "updated_at": _timestamp(item.get("updated_at")) or now,
            } for item in extractions if item.get("extraction_id") and item.get("protocol_id")]
            self._replace_children(
                "evidence_extractions", user_id, session_id, extraction_rows,
                "user_id,session_id,extraction_id",
            )

            appraisal_rows = [{
                "user_id": user_id,
                "session_id": session_id,
                "appraisal_id": str(item.get("appraisal_id") or ""),
                "protocol_id": str(item.get("protocol_id") or ""),
                "paper_id": str(item.get("paper_id") or ""),
                "profile": str(item.get("profile") or "general"),
                "overall_judgement": str(item.get("overall_judgement") or "unclear"),
                "appraisal": item,
                "created_at": _timestamp(item.get("created_at")) or now,
            } for item in appraisals if item.get("appraisal_id") and item.get("protocol_id")]
            self._replace_children(
                "study_appraisals", user_id, session_id, appraisal_rows,
                "user_id,session_id,appraisal_id",
            )

            snapshot_rows = [{
                "user_id": user_id,
                "session_id": session_id,
                "snapshot_id": str(item.get("snapshot_id") or ""),
                "protocol_id": str(item.get("protocol_id") or ""),
                "version": int(item.get("version") or 1),
                "paper_ids": item.get("paper_ids") or [],
                "confirmed_by": str(item.get("confirmed_by") or "human"),
                "confirmed_at": _timestamp(item.get("confirmed_at")) or now,
            } for item in snapshots if item.get("snapshot_id") and item.get("protocol_id")]
            self._replace_children(
                "inclusion_snapshots", user_id, session_id, snapshot_rows,
                "user_id,session_id,snapshot_id",
            )

            synthesis_rows = [{
                "user_id": user_id,
                "session_id": session_id,
                "synthesis_group_id": str(item.get("synthesis_group_id") or item.get("group_id") or ""),
                "protocol_id": str(item.get("protocol_id") or ""),
                "inclusion_snapshot_id": str(item.get("inclusion_snapshot_id") or ""),
                "synthesis_data": item,
                "created_at": _timestamp(item.get("created_at")) or now,
            } for item in synthesis_groups if (
                (item.get("synthesis_group_id") or item.get("group_id"))
                and item.get("inclusion_snapshot_id")
            )]
            self._replace_children(
                "synthesis_groups", user_id, session_id, synthesis_rows,
                "user_id,session_id,synthesis_group_id",
            )

            claim_rows = [{
                "user_id": user_id,
                "session_id": session_id,
                "claim_id": str(item.get("claim_id") or ""),
                "protocol_id": str(item.get("protocol_id") or ""),
                "inclusion_snapshot_id": str(item.get("inclusion_snapshot_id") or ""),
                "claim_text": str(item.get("claim_text") or item.get("claim") or ""),
                "support_status": str(item.get("support_status") or "unverified"),
                "claim_data": item,
                "created_at": _timestamp(item.get("created_at")) or now,
            } for item in claims if item.get("claim_id") and item.get("inclusion_snapshot_id")]
            self._replace_children(
                "review_claims", user_id, session_id, claim_rows,
                "user_id,session_id,claim_id",
            )

            review_rows = [{
                "user_id": user_id,
                "session_id": session_id,
                "review_version_id": str(item.get("review_version_id") or ""),
                "protocol_id": str(item.get("protocol_id") or ""),
                "inclusion_snapshot_id": item.get("inclusion_snapshot_id"),
                "version": int(item.get("version") or 1),
                "output_label": str(item.get("output_label") or "incomplete_research_draft"),
                "version_data": item,
                "created_at": _timestamp(item.get("created_at")) or now,
            } for item in review_versions if item.get("review_version_id") and item.get("protocol_id")]
            self._replace_children(
                "review_versions", user_id, session_id, review_rows,
                "user_id,session_id,review_version_id",
            )
        except RemoteStoreError as exc:
            if not self._missing_relation(exc):
                raise

    def _sync_conversations(self, user_id: str, session_dir: Path) -> None:
        session_id = session_dir.name
        conversations = _read_json(session_dir / "chats" / "index.json", []) or []
        conversation_rows = []
        message_rows = []
        for conversation in conversations:
            if not isinstance(conversation, dict):
                continue
            conversation_id = str(conversation.get("conv_id") or conversation.get("conversation_id") or "")
            if not conversation_id:
                continue
            messages = _read_json(session_dir / "chats" / f"{conversation_id}.json", []) or []
            conversation_rows.append({
                "user_id": user_id,
                "session_id": session_id,
                "conversation_id": conversation_id,
                "title": str(conversation.get("title") or ""),
                "message_count": len(messages),
                "created_at": _timestamp(conversation.get("created_at")),
                "updated_at": _timestamp(conversation.get("updated_at"))
                    or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "metadata": conversation,
            })
            for index, message in enumerate(messages):
                if not isinstance(message, dict):
                    continue
                message_rows.append({
                    "user_id": user_id,
                    "session_id": session_id,
                    "conversation_id": conversation_id,
                    "message_index": index,
                    "role": str(message.get("role") or ""),
                    "content": str(message.get("content") or ""),
                    "payload": message,
                    "created_at": _timestamp(message.get("created_at")),
                })
        self._replace_children(
            "research_conversations", user_id, session_id, conversation_rows,
            "user_id,session_id,conversation_id",
        )
        # Conversation replacement cascades old messages.
        if message_rows:
            self._upsert(
                "research_messages", message_rows,
                "user_id,session_id,conversation_id,message_index",
            )

    def _sync_runs(self, user_id: str, session_id: str) -> None:
        run_dir = tenant_path(self.sessions_root, user_id) / ".runs" / session_id
        rows = []
        if run_dir.exists():
            for path in run_dir.glob("run_*.json"):
                run = _read_json(path, {}) or {}
                if not run.get("run_id"):
                    continue
                rows.append({
                    "user_id": user_id,
                    "session_id": session_id,
                    "run_id": str(run["run_id"]),
                    "kind": str(run.get("kind") or ""),
                    "status": str(run.get("status") or ""),
                    "phase": str(run.get("phase") or ""),
                    "checkpoint": str(run.get("checkpoint") or ""),
                    "retryable": bool(run.get("retryable")),
                    "payload": run.get("payload") or {},
                    "progress": run.get("progress") or {},
                    "message": str(run.get("message") or ""),
                    "error_code": run.get("error_code"),
                    "created_at": _timestamp(run.get("created_at")),
                    "updated_at": _timestamp(run.get("updated_at"))
                        or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                })
        self._replace_children(
            "research_runs", user_id, session_id, rows, "user_id,session_id,run_id"
        )

    def _sync_external_files(self, user_id: str, session_dir: Path) -> None:
        session_id = session_dir.name
        query = urllib.parse.urlencode({
            "select": "relative_path,object_key,sha256",
            "user_id": f"eq.{user_id}",
            "session_id": f"eq.{session_id}",
        }, safe=",.*_-")
        existing_rows = self._select("research_files", query) or []
        existing = {str(row.get("relative_path")): row for row in existing_rows}
        rows = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for path in self._workspace_files(session_dir):
            relative = path.relative_to(session_dir)
            if not self._is_external_file(relative):
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            relative_text = relative.as_posix()
            object_key = (
                existing.get(relative_text, {}).get("object_key")
                or f"{tenant_key(user_id)}/sessions/{session_id}/files/{digest[:16]}-{path.name}"
            )
            if existing.get(relative_text, {}).get("sha256") != digest:
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self._upload_object(object_key, path.read_bytes(), content_type)
            rows.append({
                "user_id": user_id,
                "session_id": session_id,
                "relative_path": relative_text,
                "object_key": object_key,
                "content_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "byte_size": path.stat().st_size,
                "sha256": digest,
                "updated_at": now,
            })
        self._replace_children(
            "research_files", user_id, session_id, rows, "user_id,session_id,relative_path"
        )

    def delete_session(self, user_id: str, session_id: str) -> None:
        if not self.enabled or user_id == "local":
            return
        query = urllib.parse.urlencode({
            "select": "object_key",
            "user_id": f"eq.{user_id}",
            "session_id": f"eq.{session_id}",
        }, safe=",.*_-")
        file_rows = self._select("research_files", query) or []
        object_keys = [row.get("object_key") for row in file_rows]
        object_keys.append(f"{tenant_key(user_id)}/sessions/{session_id}/session.zip")
        self._delete(
            "research_sessions",
            {"user_id": f"eq.{user_id}", "session_id": f"eq.{session_id}"},
        )
        self._delete_objects(object_keys)
        cache_key = f"{tenant_key(user_id)}:{session_id}"
        self._hydrated_sessions.discard(cache_key)
        self._last_fingerprint.pop(cache_key, None)


_STORE_INSTANCES: dict[str, SupabaseWorkspaceStore] = {}
_STORE_INSTANCES_LOCK = threading.Lock()


def get_workspace_store(sessions_root: str | Path) -> SupabaseWorkspaceStore:
    key = str(Path(sessions_root).resolve())
    with _STORE_INSTANCES_LOCK:
        if key not in _STORE_INSTANCES:
            _STORE_INSTANCES[key] = SupabaseWorkspaceStore(sessions_root)
        return _STORE_INSTANCES[key]
