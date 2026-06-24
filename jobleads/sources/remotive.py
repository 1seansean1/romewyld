"""Remotive — free remote-jobs API with server-side search. No key."""
from __future__ import annotations

from .base import Source, strip_html
from ..models import CandidateProfile, JobPosting
from ..config import Config
from .. import http


class RemotiveSource(Source):
    name = "remotive"

    def search(self, profile: CandidateProfile, cfg: Config) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        seen: set[str] = set()
        for q in self.queries(profile, cfg, limit=3):
            try:
                data = http.get_json(
                    "https://remotive.com/api/remote-jobs",
                    params={"search": q, "limit": cfg.max_per_source},
                    cache_ttl_minutes=cfg.cache_ttl_minutes,
                    user_agent=cfg.user_agent,
                )
            except Exception:
                continue
            for j in data.get("jobs", []):
                url = j.get("url", "")
                if url in seen:
                    continue
                seen.add(url)
                jobs.append(
                    JobPosting(
                        source=self.name,
                        title=j.get("title", ""),
                        company=j.get("company_name", ""),
                        location=j.get("candidate_required_location", "") or "Remote",
                        remote=True,
                        url=url,
                        description=strip_html(j.get("description", "")),
                        salary=j.get("salary", "") or "",
                        posted_at=j.get("publication_date", ""),
                        tags=j.get("tags", []) or [],
                    )
                )
        return jobs[: cfg.max_per_source * 2]
