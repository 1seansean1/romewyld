"""Greenhouse — per-company public job boards. No key; needs board tokens.

Config: options.greenhouse.boards = ["stripe", "airbnb", ...]  (or use target_companies)
Token = the slug in boards.greenhouse.io/<token>.
"""
from __future__ import annotations

from .base import Source, strip_html, relevance_filter
from ..models import CandidateProfile, JobPosting
from ..config import Config
from .. import http


class GreenhouseSource(Source):
    name = "greenhouse"

    def _boards(self, cfg: Config) -> list[str]:
        return cfg.opt(self.name, "boards") or cfg.target_companies or []

    def available(self, cfg: Config) -> tuple[bool, str]:
        if self._boards(cfg):
            return True, ""
        return False, "add target_companies or options.greenhouse.boards (greenhouse slugs)"

    def search(self, profile: CandidateProfile, cfg: Config) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        for token in self._boards(cfg):
            try:
                data = http.get_json(
                    f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
                    params={"content": "true"},
                    cache_ttl_minutes=cfg.cache_ttl_minutes,
                    user_agent=cfg.user_agent,
                )
            except Exception:
                continue
            for j in data.get("jobs", []) if isinstance(data, dict) else []:
                loc = (j.get("location") or {}).get("name", "")
                jobs.append(
                    JobPosting(
                        source=self.name,
                        title=j.get("title", ""),
                        company=token,
                        location=loc,
                        remote="remote" in loc.lower(),
                        url=j.get("absolute_url", ""),
                        description=strip_html(j.get("content", "")),
                        posted_at=j.get("updated_at", ""),
                        tags=[d.get("name", "") for d in (j.get("departments") or [])],
                    )
                )
        return relevance_filter(jobs, profile, cfg, self.queries(profile, cfg))
