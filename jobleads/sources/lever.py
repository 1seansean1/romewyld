"""Lever — per-company public postings. No key; needs company tokens.

Config: options.lever.boards = ["netflix", "spotify", ...] (or target_companies)
Token = slug in jobs.lever.co/<token>.
"""
from __future__ import annotations

from .base import Source, strip_html, relevance_filter
from ..models import CandidateProfile, JobPosting
from ..config import Config
from .. import http


class LeverSource(Source):
    name = "lever"

    def _boards(self, cfg: Config) -> list[str]:
        return cfg.opt(self.name, "boards") or cfg.target_companies or []

    def available(self, cfg: Config) -> tuple[bool, str]:
        if self._boards(cfg):
            return True, ""
        return False, "add target_companies or options.lever.boards (lever slugs)"

    def search(self, profile: CandidateProfile, cfg: Config) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        for token in self._boards(cfg):
            try:
                data = http.get_json(
                    f"https://api.lever.co/v0/postings/{token}",
                    params={"mode": "json"},
                    cache_ttl_minutes=cfg.cache_ttl_minutes,
                    user_agent=cfg.user_agent,
                )
            except Exception:
                continue
            for j in data if isinstance(data, list) else []:
                cats = j.get("categories") or {}
                loc = cats.get("location", "")
                desc = j.get("descriptionPlain") or strip_html(j.get("description", ""))
                jobs.append(
                    JobPosting(
                        source=self.name,
                        title=j.get("text", ""),
                        company=token,
                        location=loc,
                        remote="remote" in (loc or "").lower(),
                        url=j.get("hostedUrl", ""),
                        description=desc,
                        posted_at=str(j.get("createdAt", "")),
                        tags=[cats.get("team", ""), cats.get("commitment", "")],
                    )
                )
        return relevance_filter(jobs, profile, cfg, self.queries(profile, cfg))
