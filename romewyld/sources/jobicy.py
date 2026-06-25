"""Jobicy — free remote jobs API with tag/geo/industry filters. No key."""
from __future__ import annotations

from .base import Source, strip_html, relevance_filter
from ..models import CandidateProfile, JobPosting
from ..config import Config
from .. import http


class JobicySource(Source):
    name = "jobicy"

    def search(self, profile: CandidateProfile, cfg: Config) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        seen: set[str] = set()
        tags = self.queries(profile, cfg, limit=3)
        for tag in tags:
            params = {"count": min(50, cfg.max_per_source), "tag": tag}
            try:
                data = http.get_json(
                    "https://jobicy.com/api/v2/remote-jobs",
                    params=params,
                    cache_ttl_minutes=cfg.cache_ttl_minutes,
                    user_agent=cfg.user_agent,
                )
            except Exception:
                continue
            for j in data.get("jobs", []) if isinstance(data, dict) else []:
                url = j.get("url", "")
                if url in seen:
                    continue
                seen.add(url)
                jobs.append(
                    JobPosting(
                        source=self.name,
                        title=j.get("jobTitle", ""),
                        company=j.get("companyName", ""),
                        location=j.get("jobGeo", "") or "Remote",
                        remote=True,
                        url=url,
                        description=strip_html(j.get("jobDescription", "") or j.get("jobExcerpt", "")),
                        salary=_salary(j),
                        posted_at=j.get("pubDate", ""),
                        tags=_as_list(j.get("jobIndustry")) + _as_list(j.get("jobType")),
                    )
                )
        return relevance_filter(jobs, profile, cfg, tags)


def _salary(j: dict) -> str:
    lo, hi = j.get("annualSalaryMin"), j.get("annualSalaryMax")
    cur = j.get("salaryCurrency", "USD")
    if lo and hi:
        return f"{cur} {int(lo):,}-{int(hi):,}"
    return ""


def _as_list(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]
