"""Thin HTTP client with on-disk response caching and polite retries."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "http_cache"


def _cache_path(key: str) -> Path:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{h}.json"


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    cache_ttl_minutes: int = 360,
    timeout: int = 25,
    retries: int = 2,
    method: str = "GET",
    data: Any = None,
    user_agent: str = "romewyld/1.0",
) -> Any:
    """Fetch JSON with caching. Returns parsed JSON or raises on hard failure."""
    headers = dict(headers or {})
    headers.setdefault("User-Agent", user_agent)
    headers.setdefault("Accept", "application/json")

    cache_key = json.dumps(
        {"u": url, "p": params, "m": method, "d": data, "h": {k: v for k, v in headers.items() if k.lower() != "authorization"}},
        sort_keys=True,
    )
    cpath = _cache_path(cache_key)
    if cache_ttl_minutes > 0 and cpath.exists():
        age_min = (time.time() - cpath.stat().st_mtime) / 60.0
        if age_min < cache_ttl_minutes:
            try:
                return json.loads(cpath.read_text(encoding="utf-8"))
            except Exception:
                pass

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.request(
                method, url, params=params, headers=headers,
                json=data if method != "GET" else None, timeout=timeout,
            )
            if resp.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            payload = resp.json()
            if cache_ttl_minutes > 0:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cpath.write_text(json.dumps(payload), encoding="utf-8")
            return payload
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"HTTP failed for {url}: {last_err}")


def get_text(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
    user_agent: str = "romewyld/1.0",
) -> str:
    headers = dict(headers or {})
    headers.setdefault("User-Agent", user_agent)
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text
