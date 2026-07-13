"""Best-effort Supabase Storage snapshots for each user's workspace.

The existing agent is deliberately filesystem-oriented. Public deployments keep
that proven execution model on the Docker backend, while this adapter makes the
workspace durable across restarts. API keys are never included in snapshots.
"""
from __future__ import annotations

import io
import json
import os
import threading
import datetime
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from backend.tenant import tenant_key, tenant_path


class SupabaseWorkspaceStore:
    def __init__(self, sessions_root: str | Path):
        self.sessions_root = Path(sessions_root)
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "research-workspaces")
        self._hydrated: set[str] = set()
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.service_key)

    def _request(self, url: str, *, method: str = "GET", data: bytes | None = None,
                 content_type: str = "application/json", extra_headers: dict | None = None):
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": content_type,
        }
        headers.update(extra_headers or {})
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        return urllib.request.urlopen(request, timeout=30)

    def hydrate(self, user_id: str) -> None:
        if not self.enabled or user_id == "local":
            return
        key = tenant_key(user_id)
        with self._lock:
            if key in self._hydrated:
                return
            self._hydrated.add(key)
            object_path = urllib.parse.quote(f"{key}/workspace.zip", safe="/")
            url = f"{self.url}/storage/v1/object/{self.bucket}/{object_path}"
            try:
                with self._request(url) as response:
                    archive = response.read()
            except urllib.error.HTTPError as exc:
                # Supabase Storage currently reports a missing object as HTTP
                # 400 with a JSON `not_found` payload, while some compatible
                # deployments use the conventional HTTP 404.
                error_body = exc.read().decode("utf-8", errors="replace").lower()
                missing_object = exc.code == 404 or (
                    exc.code == 400
                    and ("not_found" in error_body or "object not found" in error_body)
                )
                if missing_object:
                    return
                self._hydrated.discard(key)
                raise
            target = tenant_path(self.sessions_root, user_id)
            with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
                # Zip-slip guard: only extract paths that remain under target.
                resolved_target = target.resolve()
                for member in bundle.infolist():
                    destination = (target / member.filename).resolve()
                    if resolved_target not in destination.parents and destination != resolved_target:
                        raise ValueError("Invalid workspace archive path")
                bundle.extractall(target)

    def sync(self, user_id: str) -> None:
        if not self.enabled or user_id == "local":
            return
        key = tenant_key(user_id)
        source = tenant_path(self.sessions_root, user_id)
        with self._lock:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
                for path in source.rglob("*"):
                    if not path.is_file() or ".embed_cache" in path.parts:
                        continue
                    bundle.write(path, path.relative_to(source).as_posix())
            object_path = urllib.parse.quote(f"{key}/workspace.zip", safe="/")
            url = f"{self.url}/storage/v1/object/{self.bucket}/{object_path}"
            with self._request(
                url,
                method="POST",
                data=buffer.getvalue(),
                content_type="application/zip",
                extra_headers={"x-upsert": "true"},
            ):
                pass

            # Maintain a small relational index for administration and cleanup.
            metadata_url = f"{self.url}/rest/v1/research_workspaces?on_conflict=user_id"
            payload = json.dumps({
                "user_id": user_id,
                "object_key": f"{key}/workspace.zip",
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }).encode()
            with self._request(
                metadata_url,
                method="POST",
                data=payload,
                extra_headers={"Prefer": "resolution=merge-duplicates"},
            ):
                pass
