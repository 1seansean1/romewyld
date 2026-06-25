"""Optional Anthropic enrichment: per-lead fit analysis + tailored application hooks.

Degrades gracefully: if the SDK or ANTHROPIC_API_KEY is absent, enrichment is skipped
and the deterministic rationale stands on its own.
"""
from __future__ import annotations

import json
import os

from .models import CandidateProfile, Lead


def available() -> tuple[bool, str]:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False, "ANTHROPIC_API_KEY not set"
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False, "anthropic SDK not installed (pip install anthropic)"
    return True, ""


_SCHEMA = {
    "name": "lead_assessment",
    "description": "Structured fit assessment of a candidate for one job posting.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fit": {"type": "string", "enum": ["strong", "moderate", "stretch", "weak"]},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "summary": {"type": "string", "description": "2-3 sentences: why this is/ isn't a fit."},
            "resume_tweaks": {
                "type": "array", "items": {"type": "string"},
                "description": "Up to 4 concrete resume bullet edits to emphasize for THIS job.",
            },
            "cover_hook": {"type": "string", "description": "A 2-3 sentence opening hook for a cover letter / outreach note."},
        },
        "required": ["fit", "confidence", "summary"],
    },
}


def ocr_image(path, *, model: str = "claude-opus-4-8") -> str:
    """Transcribe text from an image via Claude vision. Returns '' if unavailable."""
    ok, _ = available()
    if not ok:
        return ""
    import base64
    import mimetypes
    from pathlib import Path

    p = Path(path)
    media = mimetypes.guess_type(str(p))[0] or "image/png"
    raw = p.read_bytes()
    if media not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        try:  # convert tiff/bmp/etc. to PNG for the API
            import io
            from PIL import Image
            buf = io.BytesIO()
            Image.open(p).convert("RGB").save(buf, format="PNG")
            raw, media = buf.getvalue(), "image/png"
        except Exception:
            return ""
    data = base64.standard_b64encode(raw).decode()

    import anthropic
    client = anthropic.Anthropic()
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}},
                {"type": "text", "text":
                    "This image is a professional document (resume, CV, LinkedIn profile, "
                    "certificate, or similar). Transcribe ALL readable text verbatim, no "
                    "commentary. If it has no document text (e.g. just a headshot photo), "
                    "output exactly: NO_TEXT"},
            ]}],
        )
    except Exception:
        return ""
    out = "".join(getattr(b, "text", "") for b in resp.content
                  if getattr(b, "type", "") == "text").strip()
    return "" if out.strip() == "NO_TEXT" else out


def enrich(profile: CandidateProfile, leads: list[Lead], *, model: str, top_n: int) -> int:
    ok, _ = available()
    if not ok:
        return 0
    import anthropic

    client = anthropic.Anthropic()
    cand_brief = _candidate_brief(profile)
    enriched = 0
    for lead in leads[:top_n]:
        try:
            _enrich_one(client, model, cand_brief, lead)
            enriched += 1
        except Exception:
            continue
    return enriched


def _candidate_brief(p: CandidateProfile) -> str:
    return (
        f"Name: {p.name or 'candidate'}\n"
        f"Target roles: {', '.join(p.target_titles) or 'n/a'}\n"
        f"Seniority: {p.seniority} (~{p.years_experience:.0f} yrs)\n"
        f"Top skills: {', '.join(p.skills[:25])}\n"
        f"Clearance: {p.clearance or 'none'}\n"
        f"Location pref: {p.remote_pref}; {', '.join(p.locations) or 'flexible'}\n"
        f"Summary: {p.summary[:600]}"
    )


def _enrich_one(client, model: str, cand_brief: str, lead: Lead) -> None:
    j = lead.job
    prompt = (
        "You are an expert technical recruiter. Assess how well the candidate fits this "
        "job and produce tailored application material. Be concrete and honest; do not "
        "invent experience the candidate lacks.\n\n"
        f"=== CANDIDATE ===\n{cand_brief}\n\n"
        f"=== JOB ===\n{j.title} @ {j.company} ({j.location})\n"
        f"Matched skills: {', '.join(lead.matched_skills) or 'none detected'}\n"
        f"Apparent gaps: {', '.join(lead.missing_skills) or 'none detected'}\n\n"
        f"{j.description[:3500]}\n\n"
        "Call the lead_assessment tool with your analysis."
    )
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        tools=[_SCHEMA],
        tool_choice={"type": "tool", "name": "lead_assessment"},
        messages=[{"role": "user", "content": prompt}],
    )
    data = None
    for block in resp.content:
        if getattr(block, "type", "") == "tool_use":
            data = block.input
            break
    if not isinstance(data, dict):
        return
    lead.llm_fit = data.get("fit", "")
    lead.llm_confidence = data.get("confidence", "")
    lead.llm_summary = data.get("summary", "")
    lead.llm_resume_tweaks = data.get("resume_tweaks", []) or []
    lead.llm_cover_hook = data.get("cover_hook", "")
