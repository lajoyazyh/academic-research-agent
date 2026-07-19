"""Supabase access-token validation for the FastAPI backend."""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

from fastapi import HTTPException


_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def auth_enabled() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_ANON_KEY"))


def validate_access_token(token: str) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    now = time.time()
    with _cache_lock:
        if len(_cache) > 2000:
            for stale_token in [key for key, value in _cache.items() if value[0] <= now]:
                _cache.pop(stale_token, None)
        cached = _cache.get(token)
        if cached and cached[0] > now:
            return cached[1]

    url = os.environ["SUPABASE_URL"].rstrip("/") + "/auth/v1/user"
    request = urllib.request.Request(
        url,
        headers={
            "apikey": os.environ["SUPABASE_ANON_KEY"],
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            user = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc
    if not user.get("id"):
        raise HTTPException(status_code=401, detail="Invalid access token")
    with _cache_lock:
        _cache[token] = (now + 60, user)
    return user
