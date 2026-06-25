"""Arbeitnow — free job board API (EU + remote). No key."""
from __future__ import annotations

from .base import Source, strip_html, relevance_filter
from ..models import CandidateProfile, JobPosting
from ..config import Config
from .. import http


class ArbeitnowSource(Source):
    name = "arbeitnow"

    def search(self, profile: CandidateProfile, cfg: Config) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        pages = max(1, min(3, cfg.max_per_source // 50 + 1))
        for page in range(1, pages + 1):
            try:
                data = http.get_json(
                    "https://www.arbeitnow.com/api/job-board-api",
                    params={"page": page},
                    cache_ttl_minutes=cfg.cache_ttl_minutes,
                    user_agent=cfg.user_agent,
                )
            except Exception:
                break
            rows = data.get("data", []) if isinstance(data, dict) else []
            if not rows:
                break
            for j in rows:
                jobs.append(
                    JobPosting(
                        source=self.name,
                        title=j.get("title", ""),
                        company=j.get("company_name", ""),
                        location=j.get("location", ""),
                        remote=bool(j.get("remote")),
                        url=j.get("url", ""),
                        description=strip_html(j.get("description", "")),
                        posted_at=str(j.get("created_at", "")),
                        tags=(j.get("tags", []) or []) + (j.get("job_types", []) or []),
                    )
                )
        return relevance_filter(jobs, profile, cfg, self.queries(profile, cfg))
