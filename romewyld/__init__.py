"""romewyld — resume/CV + public metadata -> ranked job-application leads."""
from __future__ import annotations

from .models import CandidateProfile, JobPosting, Lead
from .profile import build_profile, extract_text
from .metadata import load_metadata, enrich_from_github
from .config import load_config, Config
from .match import rank
from .sources import get_source, ALL_SOURCES

__version__ = "1.0.0"

__all__ = [
    "CandidateProfile", "JobPosting", "Lead",
    "build_profile", "extract_text",
    "load_metadata", "enrich_from_github",
    "load_config", "Config",
    "rank", "get_source", "ALL_SOURCES",
    "__version__",
]
