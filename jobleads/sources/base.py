"""Source connector base class and shared helpers."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from html.parser import HTMLParser

from ..models import CandidateProfile, JobPosting
from ..config import Config


class Source(ABC):
    name: str = "base"
    requires_key: bool = False

    def available(self, cfg: Config) -> tuple[bool, str]:
        """Return (usable, reason). Override for key-gated sources."""
        return True, ""

    @abstractmethod
    def search(self, profile: CandidateProfile, cfg: Config) -> list[JobPosting]:
        ...

    # ----- helpers -----
    @staticmethod
    def queries(profile: CandidateProfile, cfg: Config, limit: int = 4) -> list[str]:
        qs = list(cfg.target_titles) + list(profile.target_titles) + list(profile.recent_titles[:1])
        if not qs:
            qs = profile.skills[:2]
        # de-dupe, keep order
        out: list[str] = []
        seen: set[str] = set()
        for q in qs:
            k = q.strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append(q.strip())
        return out[:limit] or ["software engineer"]


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def relevance_filter(
    jobs: list[JobPosting], profile: CandidateProfile, cfg: Config, queries: list[str]
) -> list[JobPosting]:
    """Light client-side filter for sources without server-side search.

    Keep postings whose text mentions a query term or one of the candidate's
    top skills; if nothing matches, keep all (let the ranker decide).
    """
    terms = {q.lower() for q in queries}
    terms |= {s.lower() for s in profile.skills[:12]}
    terms |= {k.lower() for k in profile.keywords}
    terms = {t for t in terms if len(t) > 2}
    if not terms:
        return jobs[: cfg.max_per_source]
    kept = []
    for j in jobs:
        blob = (j.title + " " + " ".join(j.tags) + " " + j.description).lower()
        if any(t in blob for t in terms):
            kept.append(j)
    result = kept or jobs
    return result[: cfg.max_per_source]


def strip_html(html: str) -> str:
    if not html:
        return ""
    s = _Stripper()
    try:
        s.feed(html)
        text = " ".join(s.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()
