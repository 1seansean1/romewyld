"""Scoring engine: turn (profile, postings) into ranked Leads with explanations."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from .models import CandidateProfile, JobPosting, Lead
from . import normalize as N

# signal weights (sum = 100)
WEIGHTS = {
    "similarity": 35.0,
    "skills": 30.0,
    "title": 15.0,
    "location": 8.0,
    "seniority": 7.0,
    "recency": 5.0,
}

_BAND_RANK = {"junior": 0, "mid": 1, "senior": 2, "lead": 3, "principal": 4, "exec": 5}


def rank(profile: CandidateProfile, jobs: list[JobPosting], cfg=None) -> list[Lead]:
    jobs = _dedupe(jobs)
    if not jobs:
        return []

    sims = _tfidf_similarity(profile, jobs)
    leads: list[Lead] = []
    cand_skills = {s.lower() for s in profile.skills}

    for job, sim in zip(jobs, sims):
        job_text = job.match_document()
        job_skills = set(N.extract_skills(job_text))
        matched = sorted(cand_skills & job_skills)
        missing = sorted(job_skills - cand_skills)

        s_sim = sim
        s_skills = _skill_signal(cand_skills, job_skills)
        s_title = _title_signal(profile, job)
        s_loc = _location_signal(profile, job, cfg)
        s_sen = _seniority_signal(profile, job)
        s_rec = _recency_signal(job)

        signals = {
            "similarity": s_sim * WEIGHTS["similarity"],
            "skills": s_skills * WEIGHTS["skills"],
            "title": s_title * WEIGHTS["title"],
            "location": s_loc * WEIGHTS["location"],
            "seniority": s_sen * WEIGHTS["seniority"],
            "recency": s_rec * WEIGHTS["recency"],
        }
        score = sum(signals.values())

        flags: list[str] = []
        # salary floor
        floor = (cfg.min_salary if cfg else None) or profile.min_salary
        if floor and job.salary_max and job.salary_max < floor:
            flags.append(f"salary max ${job.salary_max:,} below floor ${floor:,}")
            score *= 0.7
        # exclude keywords
        excl = set((profile.exclude_keywords or []) + (cfg.exclude_keywords if cfg else []))
        blob = job_text.lower()
        hit = [k for k in excl if k and k.lower() in blob]
        if hit:
            flags.append(f"contains excluded: {', '.join(hit)}")
            score *= 0.4

        lead = Lead(
            job=job,
            score=max(0.0, min(100.0, score)),
            signals=signals,
            matched_skills=matched,
            missing_skills=missing[:12],
            flags=flags,
        )
        lead.rationale = _rationale(lead, profile)
        leads.append(lead)

    leads.sort(key=lambda l: l.score, reverse=True)
    return leads


# ---------------------------------------------------------------------------
def _dedupe(jobs: list[JobPosting]) -> list[JobPosting]:
    seen: set[str] = set()
    out: list[JobPosting] = []
    for j in jobs:
        fp = j.fingerprint
        if fp in seen:
            continue
        seen.add(fp)
        out.append(j)
    return out


def _tfidf_similarity(profile: CandidateProfile, jobs: list[JobPosting]) -> list[float]:
    docs = [profile.search_document()] + [j.match_document() for j in jobs]
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vec = TfidfVectorizer(
            stop_words="english", ngram_range=(1, 2), min_df=1, max_df=0.9, sublinear_tf=True,
        )
        m = vec.fit_transform(docs)
        sims = cosine_similarity(m[0:1], m[1:]).ravel()
        return [float(x) for x in sims]
    except Exception:
        return _bow_similarity(docs)


def _bow_similarity(docs: list[str]) -> list[float]:
    """Pure-python TF cosine fallback if sklearn is unavailable."""
    from collections import Counter

    def vec(t: str) -> Counter:
        return Counter(N.clean_tokens(t))

    cand = vec(docs[0])
    cand_norm = math.sqrt(sum(v * v for v in cand.values())) or 1.0
    out = []
    for d in docs[1:]:
        jv = vec(d)
        dot = sum(cand[k] * jv.get(k, 0) for k in cand)
        jn = math.sqrt(sum(v * v for v in jv.values())) or 1.0
        out.append(dot / (cand_norm * jn))
    return out


def _skill_signal(cand: set[str], job: set[str]) -> float:
    if not job:
        return 0.4 if cand else 0.0  # no detectable skills in posting → neutral-ish
    matched = cand & job
    if not matched:
        return 0.0
    job_cov = len(matched) / len(job)            # how many of the job's skills you have
    cand_use = len(matched) / max(1, min(len(cand), 15))
    return 0.65 * job_cov + 0.35 * min(1.0, cand_use)


def _tokens(s: str) -> set[str]:
    return {t for t in N.tokenize(s) if t not in N.STOPWORDS and len(t) > 1}


def _title_signal(profile: CandidateProfile, job: JobPosting) -> float:
    targets = profile.target_titles + profile.recent_titles
    if not targets or not job.title:
        return 0.3
    jt = _tokens(job.title)
    best = 0.0
    for t in targets:
        tt = _tokens(t)
        if not tt:
            continue
        overlap = len(tt & jt) / len(tt)
        best = max(best, overlap)
    return best


def _location_signal(profile: CandidateProfile, job: JobPosting, cfg) -> float:
    pref = profile.remote_pref or "any"
    locs = [l.lower() for l in (profile.locations or [])]
    if cfg and cfg.locations:
        locs += [l.lower() for l in cfg.locations]
    jl = (job.location or "").lower()

    if pref == "remote":
        return 1.0 if (job.remote or "remote" in jl or "anywhere" in jl) else 0.2
    if pref == "onsite":
        if locs and any(l in jl for l in locs):
            return 1.0
        return 0.3 if not job.remote else 0.5
    # any / hybrid
    if job.remote or "remote" in jl:
        return 1.0
    if locs and any(l in jl for l in locs):
        return 1.0
    if not locs:
        return 0.7
    return 0.45


def _seniority_signal(profile: CandidateProfile, job: JobPosting) -> float:
    cand = _BAND_RANK.get(profile.seniority)
    job_band = N.infer_seniority(job.title + " " + job.description[:400])
    jb = _BAND_RANK.get(job_band)
    if cand is None or jb is None:
        return 0.7
    diff = abs(cand - jb)
    return {0: 1.0, 1: 0.75, 2: 0.45}.get(diff, 0.2)


_EPOCH_RE = re.compile(r"^\d{9,13}$")


def _recency_signal(job: JobPosting) -> float:
    dt = _parse_date(job.posted_at)
    if not dt:
        return 0.5
    now = datetime.now(timezone.utc)
    days = max(0.0, (now - dt).total_seconds() / 86400.0)
    return math.exp(-days / 45.0)


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    s = str(s).strip()
    if _EPOCH_RE.match(s):
        try:
            val = int(s)
            if val > 1e12:
                val /= 1000
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except Exception:
            return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s.replace("Z", "+0000") if fmt.endswith("%z") and s.endswith("Z") else s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    # try fromisoformat
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _rationale(lead: Lead, profile: CandidateProfile) -> str:
    j = lead.job
    bits = []
    top = sorted(lead.signals.items(), key=lambda kv: kv[1], reverse=True)[:3]
    bits.append("strongest fit on " + ", ".join(k for k, _ in top if _ > 0))
    if lead.matched_skills:
        bits.append(f"matches {len(lead.matched_skills)} skills ({', '.join(lead.matched_skills[:6])})")
    if lead.missing_skills:
        bits.append(f"gaps: {', '.join(lead.missing_skills[:4])}")
    if j.remote:
        bits.append("remote")
    if lead.flags:
        bits.append("⚠ " + "; ".join(lead.flags))
    return "; ".join(b for b in bits if b)
