"""RemoteOK — free remote jobs feed (no server search; filtered client-side). No key."""
from __future__ import annotations

from .base import Source, strip_html, relevance_filter
from ..models import CandidateProfile, JobPosting
from ..config import Config
from .. import http


class RemoteOKSource(Source):
    name = "remoteok"

    def search(self, profile: CandidateProfile, cfg: Config) -> list[JobPosting]:
        try:
            data = http.get_json(
                "https://remoteok.com/api",
                cache_ttl_minutes=cfg.cache_ttl_minutes,
                user_agent=cfg.user_agent,
            )
        except Exception:
            return []
        jobs: list[JobPosting] = []
        for j in data if isinstance(data, list) else []:
            if not isinstance(j, dict) or "position" not in j:
                continue  # first element is a legal/license notice
            jobs.append(
                JobPosting(
                    source=self.name,
                    title=j.get("position", "") or j.get("title", ""),
                    company=j.get("company", ""),
                    location=j.get("location", "") or "Remote",
                    remote=True,
                    url=j.get("url", "") or j.get("apply_url", ""),
                    description=strip_html(j.get("description", "")),
                    salary=_salary(j),
                    salary_min=j.get("salary_min") or None,
                    salary_max=j.get("salary_max") or None,
                    posted_at=j.get("date", ""),
                    tags=j.get("tags", []) or [],
                )
            )
        return relevance_filter(jobs, profile, cfg, self.queries(profile, cfg))


def _salary(j: dict) -> str:
    lo, hi = j.get("salary_min"), j.get("salary_max")
    if lo and hi:
        return f"${int(lo):,}-${int(hi):,}"
    return ""
