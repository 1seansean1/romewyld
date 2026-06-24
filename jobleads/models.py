"""Core data models for the job-lead engine."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class CandidateProfile:
    """Structured candidate built from a CV/resume + public metadata."""

    name: str = ""
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    summary: str = ""
    skills: list[str] = field(default_factory=list)          # normalized skill tokens
    target_titles: list[str] = field(default_factory=list)   # roles to search for
    recent_titles: list[str] = field(default_factory=list)   # held titles, newest first
    seniority: str = ""                                       # junior|mid|senior|lead|principal|exec
    years_experience: float = 0.0
    locations: list[str] = field(default_factory=list)        # preferred locations
    remote_pref: str = "any"                                  # any|remote|hybrid|onsite
    min_salary: Optional[int] = None
    industries: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    clearance: str = ""                                       # e.g. "TS/SCI"
    work_authorization: str = ""
    education: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)         # extra must-have terms
    exclude_keywords: list[str] = field(default_factory=list)
    raw_text: str = ""                                        # full resume text (for TF-IDF)

    def search_document(self) -> str:
        """The text blob representing the candidate, used for similarity scoring."""
        parts = [
            self.summary,
            " ".join(self.skills * 2),          # weight skills
            " ".join(self.target_titles * 3),   # weight target roles
            " ".join(self.recent_titles * 2),
            " ".join(self.industries),
            " ".join(self.certifications),
            " ".join(self.keywords * 2),
            self.raw_text,
        ]
        return "\n".join(p for p in parts if p)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JobPosting:
    """A raw job opening fetched from a source."""

    source: str
    title: str
    company: str = ""
    location: str = ""
    remote: bool = False
    url: str = ""
    description: str = ""
    salary: str = ""
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    posted_at: str = ""           # ISO date when known
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        """Stable id for dedupe: prefer URL, else company+title."""
        key = (self.url or f"{self.company}|{self.title}").strip().lower()
        return hashlib.sha1(key.encode("utf-8", "ignore")).hexdigest()[:16]

    def match_document(self) -> str:
        parts = [
            self.title,
            self.title,            # weight title
            self.company,
            " ".join(self.tags),
            self.location,
            self.description,
        ]
        return "\n".join(p for p in parts if p)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("raw", None)
        d["fingerprint"] = self.fingerprint
        return d


@dataclass
class Lead:
    """A scored, ranked job posting with explanation."""

    job: JobPosting
    score: float = 0.0                 # 0-100 overall
    signals: dict[str, float] = field(default_factory=dict)  # per-signal contributions
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    rationale: str = ""
    flags: list[str] = field(default_factory=list)           # e.g. "salary below floor"
    # Optional LLM enrichment:
    llm_fit: str = ""
    llm_summary: str = ""
    llm_resume_tweaks: list[str] = field(default_factory=list)
    llm_cover_hook: str = ""
    llm_confidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {
            "score": round(self.score, 1),
            "signals": {k: round(v, 1) for k, v in self.signals.items()},
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
            "rationale": self.rationale,
            "flags": self.flags,
        }
        if self.llm_summary or self.llm_fit:
            d["llm"] = {
                "fit": self.llm_fit,
                "summary": self.llm_summary,
                "resume_tweaks": self.llm_resume_tweaks,
                "cover_hook": self.llm_cover_hook,
                "confidence": self.llm_confidence,
            }
        d["job"] = self.job.to_dict()
        return d
