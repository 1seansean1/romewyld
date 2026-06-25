"""Parse a LinkedIn data export (the 'Get a copy of your data' zip or folder).

LinkedIn exports a set of CSVs: Profile.csv, Positions.csv, Skills.csv,
Education.csv, Email Addresses.csv, etc. This reads whichever are present and
returns (text, metadata) to fold into a CandidateProfile.
"""
from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any

# filenames (case-insensitive) we know how to read
_KNOWN = {"profile.csv", "positions.csv", "skills.csv", "education.csv",
          "email addresses.csv", "certifications.csv", "languages.csv"}


def looks_like_export(path: str | Path) -> bool:
    p = Path(path)
    try:
        if p.is_dir():
            names = {f.name.lower() for f in p.iterdir()}
            return bool(names & {"profile.csv", "positions.csv", "skills.csv"})
        if p.suffix.lower() == ".zip" and zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                names = {Path(n).name.lower() for n in z.namelist()}
                return bool(names & {"profile.csv", "positions.csv", "skills.csv"})
    except Exception:
        return False
    return False


def _read_csvs(path: Path) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    if path.is_dir():
        for f in path.iterdir():
            if f.name.lower() in _KNOWN:
                out[f.name.lower()] = _parse_csv(f.read_text(encoding="utf-8", errors="ignore"))
    else:
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                base = Path(n).name.lower()
                if base in _KNOWN:
                    out[base] = _parse_csv(z.read(n).decode("utf-8", "ignore"))
    return out


def _parse_csv(text: str) -> list[dict[str, str]]:
    # LinkedIn occasionally prepends a "Notes:" preamble / blank lines before the header.
    lines = text.splitlines()
    while lines and (not lines[0].strip() or lines[0].lower().startswith("notes:")):
        lines.pop(0)
    if not lines:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    return [dict(r) for r in reader]


def _g(row: dict, *keys: str) -> str:
    for k in keys:
        for actual in row:
            if actual.strip().lower() == k.lower():
                return (row[actual] or "").strip()
    return ""


def parse_export(path: str | Path) -> tuple[str, dict[str, Any]]:
    p = Path(path)
    tables = _read_csvs(p)
    meta: dict[str, Any] = {}
    text_parts: list[str] = []

    prof = (tables.get("profile.csv") or [{}])[0]
    first, last = _g(prof, "First Name"), _g(prof, "Last Name")
    name = (first + " " + last).strip()
    if name:
        meta["name"] = name
    headline = _g(prof, "Headline")
    summary = _g(prof, "Summary")
    industry = _g(prof, "Industry")
    if summary:
        meta["summary"] = summary
        text_parts.append(summary)
    if headline:
        meta.setdefault("target_titles", []).append(headline)
        text_parts.append(headline)
    if industry:
        meta.setdefault("industries", []).append(industry)

    titles: list[str] = []
    for pos in tables.get("positions.csv", []):
        t = _g(pos, "Title")
        company = _g(pos, "Company Name")
        desc = _g(pos, "Description")
        if t:
            titles.append(t)
            text_parts.append(f"{t} at {company}. {desc}".strip())
    if titles:
        meta["recent_titles"] = titles

    skills = [_g(s, "Name") for s in tables.get("skills.csv", []) if _g(s, "Name")]
    if skills:
        meta["skills"] = skills
        text_parts.append(", ".join(skills))

    edu: list[str] = []
    for e in tables.get("education.csv", []):
        school, degree = _g(e, "School Name"), _g(e, "Degree Name")
        line = " — ".join(x for x in (school, degree) if x)
        if line:
            edu.append(line)
            text_parts.append(line)
    if edu:
        meta["education"] = edu

    certs = [_g(c, "Name") for c in tables.get("certifications.csv", []) if _g(c, "Name")]
    if certs:
        meta["certifications"] = certs

    emails = [_g(r, "Email Address") for r in tables.get("email addresses.csv", []) if _g(r, "Email Address")]
    if emails:
        meta["emails"] = emails

    return "\n".join(tp for tp in text_parts if tp), meta
