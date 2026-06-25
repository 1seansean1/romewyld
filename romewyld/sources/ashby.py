"""Ashby — per-company public job boards. No key; needs board names.

Config: options.ashby.boards = ["Ramp", "Linear", ...] (or target_companies)
Token = the job-board name in jobs.ashbyhq.com/<token>.
"""
from __future__ import annotations

from .base import Source, strip_html, relevance_filter
from ..models import CandidateProfile, JobPosting
from ..config import Config
from .. import http


class AshbySource(Source):
    name = "ashby"

    def _boards(self, cfg: Config) -> list[str]:
        return cfg.opt(self.name, "boards") or cfg.target_companies or []

    def available(self, cfg: Config) -> tuple[bool, str]:
        if self._boards(cfg):
            return True, ""
        return False, "add target_companies or options.ashby.boards (ashby board names)"

    def search(self, profile: CandidateProfile, cfg: Config) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        for token in self._boards(cfg):
            try:
                data = http.get_json(
                    f"https://api.ashbyhq.com/posting-api/job-board/{token}",
                    params={"includeCompensation": "true"},
                    cache_ttl_minutes=cfg.cache_ttl_minutes,
                    user_agent=cfg.user_agent,
                )
            except Exception:
                continue
            company = data.get("name", token) if isinstance(data, dict) else token
            for j in data.get("jobs", []) if isinstance(data, dict) else []:
                desc = j.get("descriptionPlain") or strip_html(j.get("descriptionHtml", ""))
                jobs.append(
                    JobPosting(
                        source=self.name,
                        title=j.get("title", ""),
                        company=company,
                        location=j.get("location", ""),
                        remote=bool(j.get("isRemote")),
                        url=j.get("jobUrl", "") or j.get("applyUrl", ""),
                        description=desc,
                        salary=_comp(j),
                        posted_at=j.get("publishedAt", ""),
                        tags=[j.get("department", ""), j.get("team", ""), j.get("employmentType", "")],
                    )
                )
        return relevance_filter(jobs, profile, cfg, self.queries(profile, cfg))


def _comp(j: dict) -> str:
    c = j.get("compensation") or {}
    summary = c.get("compensationTierSummary") or c.get("summary")
    return summary or ""
