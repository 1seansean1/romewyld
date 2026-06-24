"""The Muse — free public jobs API (key optional, raises limits). Filtered client-side."""
from __future__ import annotations

from .base import Source, strip_html, relevance_filter
from ..models import CandidateProfile, JobPosting
from ..config import Config
from .. import http

_LEVEL_MAP = {
    "junior": "Entry Level", "mid": "Mid Level", "senior": "Senior Level",
    "lead": "Management", "principal": "Senior Level", "exec": "Senior Level",
}


class TheMuseSource(Source):
    name = "themuse"

    def search(self, profile: CandidateProfile, cfg: Config) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        seen: set[str] = set()
        api_key = cfg.opt(self.name, "api_key")
        level = _LEVEL_MAP.get(profile.seniority, "")
        pages = max(1, min(4, cfg.max_per_source // 20 + 1))
        for page in range(pages):
            params: dict = {"page": page}
            if level:
                params["level"] = level
            if api_key:
                params["api_key"] = api_key
            for loc in (profile.locations[:1] or [None]):
                p = dict(params)
                if loc:
                    p["location"] = loc
                try:
                    data = http.get_json(
                        "https://www.themuse.com/api/public/jobs",
                        params=p,
                        cache_ttl_minutes=cfg.cache_ttl_minutes,
                        user_agent=cfg.user_agent,
                    )
                except Exception:
                    continue
                for j in data.get("results", []) if isinstance(data, dict) else []:
                    url = (j.get("refs") or {}).get("landing_page", "")
                    if url in seen:
                        continue
                    seen.add(url)
                    locs = ", ".join(l.get("name", "") for l in (j.get("locations") or []))
                    jobs.append(
                        JobPosting(
                            source=self.name,
                            title=j.get("name", ""),
                            company=(j.get("company") or {}).get("name", ""),
                            location=locs,
                            remote="remote" in locs.lower(),
                            url=url,
                            description=strip_html(j.get("contents", "")),
                            posted_at=j.get("publication_date", ""),
                            tags=[l.get("name", "") for l in (j.get("levels") or [])]
                            + [c.get("name", "") for c in (j.get("categories") or [])],
                        )
                    )
        return relevance_filter(jobs, profile, cfg, self.queries(profile, cfg))
