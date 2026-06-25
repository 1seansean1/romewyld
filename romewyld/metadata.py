"""Load public metadata and optionally enrich from public web profiles."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import http

try:
    import yaml  # type: ignore
    _HAVE_YAML = True
except Exception:  # pragma: no cover
    _HAVE_YAML = False


def load_metadata(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        if not _HAVE_YAML:
            raise RuntimeError("PyYAML not installed; provide JSON metadata")
        return yaml.safe_load(text) or {}
    return json.loads(text)


_GH_USER_RE = re.compile(r"github\.com/([A-Za-z0-9\-]+)")


def enrich_from_github(metadata: dict[str, Any], *, user_agent: str = "romewyld/1.0") -> dict[str, Any]:
    """Pull public language signal from a GitHub username (no auth, rate-limited)."""
    url = metadata.get("github_url") or ""
    user = metadata.get("github")
    if not user and url:
        m = _GH_USER_RE.search(url)
        if m:
            user = m.group(1)
    if not user:
        return metadata
    try:
        repos = http.get_json(
            f"https://api.github.com/users/{user}/repos",
            params={"per_page": 100, "sort": "pushed"},
            cache_ttl_minutes=1440,
            user_agent=user_agent,
        )
    except Exception:
        return metadata
    langs: dict[str, int] = {}
    topics: dict[str, int] = {}
    for r in repos if isinstance(repos, list) else []:
        lang = r.get("language")
        if lang:
            langs[lang.lower()] = langs.get(lang.lower(), 0) + 1
        for t in r.get("topics", []) or []:
            topics[t.lower()] = topics.get(t.lower(), 0) + 1
    top_langs = [k for k, _ in sorted(langs.items(), key=lambda kv: -kv[1])[:8]]
    top_topics = [k for k, _ in sorted(topics.items(), key=lambda kv: -kv[1])[:10]]
    merged_skills = list(dict.fromkeys(_as_list(metadata.get("skills")) + top_langs + top_topics))
    metadata = {**metadata, "skills": merged_skills}
    metadata.setdefault("_github_languages", top_langs)
    return metadata


def _as_list(v: Any) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        return [v]
    return [str(x) for x in v]
