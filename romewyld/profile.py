"""Build a CandidateProfile from a CV/resume file plus public metadata."""
from __future__ import annotations

import re
from pathlib import Path

from .models import CandidateProfile
from . import normalize as N


# ---------------------------------------------------------------------------
# Text extraction from common resume formats
# ---------------------------------------------------------------------------
def extract_text(path: str | Path) -> str:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".txt", ".md", ".markdown", ".text"):
        return p.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        return _extract_pdf(p)
    if suffix in (".docx",):
        return _extract_docx(p)
    if suffix in (".doc",):
        raise ValueError(".doc (legacy Word) not supported; export to .docx or .pdf")
    # last resort: try as text
    return p.read_text(encoding="utf-8", errors="ignore")


def _extract_pdf(p: Path) -> str:
    text = ""
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(str(p)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        text = ""
    if len(text.strip()) < 40:
        try:
            from pypdf import PdfReader  # type: ignore
            reader = PdfReader(str(p))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:  # pragma: no cover
            raise RuntimeError(f"Could not extract text from PDF {p}: {e}")
    return text


def _extract_docx(p: Path) -> str:
    try:
        import docx  # type: ignore
        d = docx.Document(str(p))
        return "\n".join(par.text for par in d.paragraphs)
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"Could not extract text from DOCX {p}: {e}")


# ---------------------------------------------------------------------------
# Heuristic structure extraction
# ---------------------------------------------------------------------------
_YEARS_RE = re.compile(r"(\d{1,2})\+?\s*(?:years|yrs)\b", re.I)
_DATE_RANGE_RE = re.compile(
    r"\b(19|20)\d{2}\b\s*[\-–to]+\s*((?:19|20)\d{2}|present|current|now)", re.I
)
_CLEARANCE_RE = re.compile(
    r"\b(TS/SCI(?:\s*w/?\s*(?:CI\s*)?poly)?|top secret(?:/sci)?|secret|public trust|"
    r"interim secret|interim top secret)\b",
    re.I,
)
_TITLE_HINT = re.compile(
    r"\b(engineer|developer|scientist|manager|director|analyst|architect|consultant|"
    r"designer|lead|specialist|administrator|officer|researcher|founder|head of|"
    r"vp|cto|ceo|cfo|coo|product manager|program manager|data scientist|"
    r"software engineer|principal|staff)\b",
    re.I,
)


def estimate_years(text: str) -> float:
    explicit = [int(m.group(1)) for m in _YEARS_RE.finditer(text)]
    if explicit:
        return float(max(explicit))
    # else infer span from date ranges
    years: list[int] = []
    for m in _DATE_RANGE_RE.finditer(text):
        start = int(m.group(0)[:4]) if m.group(0)[:4].isdigit() else None
        end_raw = m.group(2).lower()
        end = 2026 if end_raw in ("present", "current", "now") else int(re.search(r"\d{4}", end_raw).group())
        if start and end and end >= start:
            years.append(end - start)
    if years:
        # rough: total tenure capped to avoid overlap inflation
        return float(min(sum(years), max(years) + 10))
    return 0.0


def guess_name(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # a name line: 2-4 capitalized words, no digits/@, short
        if (
            2 <= len(line.split()) <= 4
            and "@" not in line
            and not any(ch.isdigit() for ch in line)
            and len(line) < 50
            and sum(w[0].isupper() for w in line.split() if w) >= 2
        ):
            return line
        break
    return ""


def extract_recent_titles(text: str, limit: int = 6) -> list[str]:
    titles: list[str] = []
    for line in text.splitlines():
        line = line.strip(" \t#-•*|>")
        if not line or len(line) > 80:
            continue
        if _TITLE_HINT.search(line) and "@" not in line and not line.lower().startswith(("http", "www")):
            # avoid pure section headers
            words = line.split()
            if 1 <= len(words) <= 9:
                titles.append(line)
        if len(titles) >= limit:
            break
    # de-dup preserving order
    out: list[str] = []
    seen: set[str] = set()
    for t in titles:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out


def build_profile(resume_text: str, metadata: dict | None = None) -> CandidateProfile:
    """Heuristic profile builder. `metadata` overrides/augments inferred fields."""
    metadata = metadata or {}
    text = N.normalize_text(resume_text)

    contacts = N.extract_contacts(text)
    years = estimate_years(text)
    skills = N.extract_skills(text)
    recent_titles = extract_recent_titles(text)
    clearance_m = _CLEARANCE_RE.search(text)

    prof = CandidateProfile(
        name=metadata.get("name") or guess_name(text),
        emails=contacts["emails"],
        phones=contacts["phones"],
        urls=list(dict.fromkeys(contacts["urls"] + _meta_list(metadata, "urls"))),
        skills=skills,
        recent_titles=recent_titles,
        years_experience=float(metadata.get("years_experience") or years),
        clearance=metadata.get("clearance") or (clearance_m.group(0) if clearance_m else ""),
        raw_text=text,
    )

    # target titles: metadata first, else derive from most recent held titles
    prof.target_titles = _meta_list(metadata, "target_titles") or _derive_targets(recent_titles)
    prof.seniority = metadata.get("seniority") or N.infer_seniority(" ".join(recent_titles) or text, years)
    prof.locations = _meta_list(metadata, "locations")
    prof.remote_pref = metadata.get("remote_pref", "any")
    prof.min_salary = metadata.get("min_salary")
    prof.industries = _meta_list(metadata, "industries")
    prof.certifications = _meta_list(metadata, "certifications")
    prof.work_authorization = metadata.get("work_authorization", "")
    prof.keywords = _meta_list(metadata, "keywords")
    prof.exclude_keywords = _meta_list(metadata, "exclude_keywords")
    prof.summary = metadata.get("summary", "")

    # merge any explicit skills from metadata
    extra_skills = [N.canonical_skill(s) for s in _meta_list(metadata, "skills")]
    for s in extra_skills:
        if s not in prof.skills:
            prof.skills.append(s)

    return prof


def _meta_list(metadata: dict, key: str) -> list[str]:
    v = metadata.get(key)
    if not v:
        return []
    if isinstance(v, str):
        return [v]
    return [str(x) for x in v]


def _derive_targets(recent_titles: list[str]) -> list[str]:
    """Pick search-friendly target titles from held titles (strip seniority noise)."""
    targets: list[str] = []
    for t in recent_titles[:3]:
        # drop company/date noise: keep the part before the first comma, strip parentheticals
        head = re.sub(r"\([^)]*\)", "", t).split(",")[0]
        cleaned = re.sub(
            r"\b(senior|sr\.?|junior|jr\.?|lead|principal|staff|chief|head of|vp of|vp|i{1,3}|iv)\b",
            "",
            head,
            flags=re.I,
        ).strip(" ,-")
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        if cleaned and cleaned.lower() not in (x.lower() for x in targets):
            targets.append(cleaned)
    return targets or recent_titles[:2]
