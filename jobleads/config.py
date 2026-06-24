"""Configuration loading and defaults."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
    _HAVE_YAML = True
except Exception:  # pragma: no cover
    _HAVE_YAML = False


DEFAULT_SOURCES = ["remotive", "remoteok", "arbeitnow", "themuse", "jobicy", "hackernews"]


@dataclass
class Config:
    sources: list[str] = field(default_factory=lambda: list(DEFAULT_SOURCES))
    # per-source options (api keys, company tokens, etc.)
    options: dict[str, Any] = field(default_factory=dict)
    # filters
    locations: list[str] = field(default_factory=list)
    remote_pref: str = "any"            # any|remote|hybrid|onsite
    min_salary: int | None = None
    exclude_keywords: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    target_titles: list[str] = field(default_factory=list)
    target_companies: list[str] = field(default_factory=list)   # greenhouse/lever/ashby tokens
    # search behaviour
    max_per_source: int = 50
    top_n: int = 25
    min_score: float = 0.0
    # llm enrichment
    llm_enabled: bool = False
    llm_model: str = "claude-opus-4-8"
    llm_top_n: int = 10
    # http
    cache_ttl_minutes: int = 360
    user_agent: str = "job-leads/1.0 (+https://github.com/1seansean1)"

    def opt(self, source: str, key: str, default: Any = None) -> Any:
        return self.options.get(source, {}).get(key, default)


def _load_raw(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        if not _HAVE_YAML:
            raise RuntimeError("PyYAML not installed; use a .json config or pip install pyyaml")
        return yaml.safe_load(text) or {}
    return json.loads(text)


def load_config(path: str | os.PathLike | None) -> Config:
    cfg = Config()
    if path:
        raw = _load_raw(Path(path))
        known = set(Config.__dataclass_fields__.keys())
        for k, v in raw.items():
            if k in known and v is not None:
                setattr(cfg, k, v)
    # env overrides for keys (never store secrets in config files)
    cfg.options.setdefault("adzuna", {})
    cfg.options.setdefault("usajobs", {})
    if os.getenv("ADZUNA_APP_ID"):
        cfg.options["adzuna"]["app_id"] = os.getenv("ADZUNA_APP_ID")
    if os.getenv("ADZUNA_APP_KEY"):
        cfg.options["adzuna"]["app_key"] = os.getenv("ADZUNA_APP_KEY")
    if os.getenv("USAJOBS_API_KEY"):
        cfg.options["usajobs"]["api_key"] = os.getenv("USAJOBS_API_KEY")
    if os.getenv("USAJOBS_EMAIL"):
        cfg.options["usajobs"]["email"] = os.getenv("USAJOBS_EMAIL")
    if os.getenv("ANTHROPIC_API_KEY") and not path:
        cfg.llm_enabled = True
    return cfg
