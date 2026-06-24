"""USAJobs — US federal jobs API. Needs a free API key + the registered email."""
from __future__ import annotations

from .base import Source, strip_html
from ..models import CandidateProfile, JobPosting
from ..config import Config
from .. import http


class USAJobsSource(Source):
    name = "usajobs"
    requires_key = True

    def available(self, cfg: Config) -> tuple[bool, str]:
        if cfg.opt(self.name, "api_key") and cfg.opt(self.name, "email"):
            return True, ""
        return False, "set USAJOBS_API_KEY and USAJOBS_EMAIL env vars (free at developer.usajobs.gov)"

    def search(self, profile: CandidateProfile, cfg: Config) -> list[JobPosting]:
        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": cfg.opt(self.name, "email"),
            "Authorization-Key": cfg.opt(self.name, "api_key"),
        }
        where = (cfg.locations or profile.locations or [""])[0]
        jobs: list[JobPosting] = []
        seen: set[str] = set()
        for q in self.queries(profile, cfg, limit=3):
            params: dict = {"Keyword": q, "ResultsPerPage": min(50, cfg.max_per_source)}
            if where:
                params["LocationName"] = where
            if cfg.min_salary:
                params["RemunerationMinimumAmount"] = cfg.min_salary
            try:
                data = http.get_json(
                    "https://data.usajobs.gov/api/search",
                    params=params,
                    headers=headers,
                    cache_ttl_minutes=cfg.cache_ttl_minutes,
                    user_agent=cfg.user_agent,
                )
            except Exception:
                continue
            items = (data.get("SearchResult") or {}).get("SearchResultItems", [])
            for it in items:
                d = it.get("MatchedObjectDescriptor") or {}
                url = d.get("PositionURI", "")
                if url in seen:
                    continue
                seen.add(url)
                rem = (d.get("PositionRemuneration") or [{}])[0]
                summary = ((d.get("UserArea") or {}).get("Details") or {}).get("JobSummary", "")
                jobs.append(
                    JobPosting(
                        source=self.name,
                        title=d.get("PositionTitle", ""),
                        company=d.get("OrganizationName", ""),
                        location=d.get("PositionLocationDisplay", ""),
                        remote="remote" in d.get("PositionTitle", "").lower(),
                        url=url,
                        description=strip_html(summary),
                        salary_min=_int(rem.get("MinimumRange")),
                        salary_max=_int(rem.get("MaximumRange")),
                        posted_at=d.get("PublicationStartDate", ""),
                        tags=[j.get("Name", "") for j in (d.get("JobCategory") or [])],
                    )
                )
        return jobs


def _int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None
