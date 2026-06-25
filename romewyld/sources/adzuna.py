"""Adzuna — aggregated jobs API. Free tier needs app_id + app_key."""
from __future__ import annotations

from .base import Source, strip_html
from ..models import CandidateProfile, JobPosting
from ..config import Config
from .. import http


class AdzunaSource(Source):
    name = "adzuna"
    requires_key = True

    def available(self, cfg: Config) -> tuple[bool, str]:
        if cfg.opt(self.name, "app_id") and cfg.opt(self.name, "app_key"):
            return True, ""
        return False, "set ADZUNA_APP_ID and ADZUNA_APP_KEY env vars (free at developer.adzuna.com)"

    def search(self, profile: CandidateProfile, cfg: Config) -> list[JobPosting]:
        app_id = cfg.opt(self.name, "app_id")
        app_key = cfg.opt(self.name, "app_key")
        country = (cfg.opt(self.name, "country") or "us").lower()
        where = (cfg.locations or profile.locations or [""])[0]
        jobs: list[JobPosting] = []
        seen: set[str] = set()
        for q in self.queries(profile, cfg, limit=3):
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "what": q,
                "results_per_page": min(50, cfg.max_per_source),
                "content-type": "application/json",
            }
            if where:
                params["where"] = where
            if cfg.min_salary:
                params["salary_min"] = cfg.min_salary
            try:
                data = http.get_json(
                    f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                    params=params,
                    cache_ttl_minutes=cfg.cache_ttl_minutes,
                    user_agent=cfg.user_agent,
                )
            except Exception:
                continue
            for j in data.get("results", []) if isinstance(data, dict) else []:
                url = j.get("redirect_url", "")
                if url in seen:
                    continue
                seen.add(url)
                jobs.append(
                    JobPosting(
                        source=self.name,
                        title=j.get("title", ""),
                        company=(j.get("company") or {}).get("display_name", ""),
                        location=(j.get("location") or {}).get("display_name", ""),
                        remote="remote" in (j.get("title", "") + (j.get("location") or {}).get("display_name", "")).lower(),
                        url=url,
                        description=strip_html(j.get("description", "")),
                        salary_min=int(j["salary_min"]) if j.get("salary_min") else None,
                        salary_max=int(j["salary_max"]) if j.get("salary_max") else None,
                        posted_at=j.get("created", ""),
                        tags=[(j.get("category") or {}).get("label", "")],
                    )
                )
        return jobs
