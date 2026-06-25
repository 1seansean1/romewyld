"""Hacker News 'Who is hiring?' — parse the latest monthly thread via Algolia. No key."""
from __future__ import annotations

import re

from .base import Source, strip_html, relevance_filter
from ..models import CandidateProfile, JobPosting
from ..config import Config
from .. import http

_REMOTE_RE = re.compile(r"\bremote\b", re.I)
# heuristic: "Company | Role | Location | ..." or "Company (location) — role"
_SEP = re.compile(r"\s*[|•·–—\-]\s*|\s{2,}")


class HackerNewsSource(Source):
    name = "hackernews"

    def search(self, profile: CandidateProfile, cfg: Config) -> list[JobPosting]:
        thread_id = self._latest_thread(cfg)
        if not thread_id:
            return []
        try:
            item = http.get_json(
                f"https://hn.algolia.com/api/v1/items/{thread_id}",
                cache_ttl_minutes=cfg.cache_ttl_minutes,
                user_agent=cfg.user_agent,
            )
        except Exception:
            return []
        jobs: list[JobPosting] = []
        for child in item.get("children", []) if isinstance(item, dict) else []:
            text = child.get("text") or ""
            if not text or len(text) < 60:
                continue
            clean = strip_html(text)
            first_line = clean.split(". ")[0][:160]
            parts = [p for p in _SEP.split(first_line) if p.strip()]
            company = parts[0].strip()[:80] if parts else (child.get("author") or "")
            title = parts[1].strip()[:100] if len(parts) > 1 else "See posting"
            jobs.append(
                JobPosting(
                    source=self.name,
                    title=title,
                    company=company,
                    location="Remote" if _REMOTE_RE.search(clean) else "",
                    remote=bool(_REMOTE_RE.search(clean)),
                    url=f"https://news.ycombinator.com/item?id={child.get('id')}",
                    description=clean[:4000],
                    posted_at=child.get("created_at", ""),
                    tags=["hn-whoishiring"],
                )
            )
        return relevance_filter(jobs, profile, cfg, self.queries(profile, cfg))

    def _latest_thread(self, cfg: Config) -> int | None:
        override = cfg.opt(self.name, "thread_id")
        if override:
            return int(override)
        try:
            res = http.get_json(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={
                    "query": "Ask HN: Who is hiring?",
                    "tags": "story,author_whoishiring",
                    "hitsPerPage": 1,
                },
                cache_ttl_minutes=720,
                user_agent=cfg.user_agent,
            )
        except Exception:
            return None
        hits = res.get("hits", []) if isinstance(res, dict) else []
        if hits:
            return int(hits[0]["objectID"])
        return None
