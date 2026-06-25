"""Multi-source ingestion: fold a pile of professional material into one profile.

Accepts files and directories of mixed types and routes each to a handler:
  documents  .pdf .docx .md .txt .rtf       -> text
  images     .png .jpg .jpeg .webp .gif ...  -> headshot (display) or OCR'd text
  linkedin   export .zip / folder of CSVs    -> structured fields + text
  data       .json .yaml .yml                -> structured metadata merge
  tabular    .csv                            -> text
A directory is expanded (recursively, one level of nesting) into its files.
"""
from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import profile as profile_mod
from . import linkedin as linkedin_mod
from . import llm as llm_mod

try:
    import yaml  # type: ignore
    _HAVE_YAML = True
except Exception:  # pragma: no cover
    _HAVE_YAML = False

DOC_EXT = {".pdf", ".docx", ".md", ".markdown", ".txt", ".text", ".rtf"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
DATA_EXT = {".json", ".yaml", ".yml"}
CSV_EXT = {".csv"}
LIST_KEYS = {"skills", "target_titles", "recent_titles", "locations", "industries",
             "certifications", "keywords", "exclude_keywords", "education", "urls",
             "publications", "emails", "phones", "tags", "terms", "links"}

_HEADSHOT_HINTS = ("headshot", "photo", "portrait", "avatar", "profile-pic",
                   "profilepic", "selfie", "me.")


@dataclass
class Ingested:
    text_parts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    headshot: str = ""               # data URI
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
def merge_meta(base: dict, add: dict) -> dict:
    """Union list-valued keys; for scalars, keep base unless empty."""
    out = dict(base)
    for k, v in (add or {}).items():
        if v in (None, "", [], {}):
            continue
        if k in LIST_KEYS or isinstance(v, list):
            cur = list(out.get(k) or [])
            for item in (v if isinstance(v, list) else [v]):
                if item not in cur:
                    cur.append(item)
            out[k] = cur
        else:
            if not out.get(k):
                out[k] = v
    return out


def _expand(paths: list[str]) -> list[Path]:
    files: list[Path] = []

    def walk(d: Path) -> None:
        # a LinkedIn export folder (at any depth) is handled as a unit, not expanded
        if linkedin_mod.looks_like_export(d):
            files.append(d)
            return
        for child in sorted(d.iterdir()):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                walk(child)
            elif child.is_file():
                files.append(child)

    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            walk(p)
        else:
            files.append(p)
    return files


def _is_headshot(path: Path, hint: str | None) -> bool:
    if hint and Path(hint).resolve() == path.resolve():
        return True
    low = path.name.lower()
    return any(h in low for h in _HEADSHOT_HINTS)


def image_data_uri(path: Path, max_px: int = 320) -> str:
    """Downscaled base64 data URI for embedding a headshot in HTML."""
    try:
        from PIL import Image
    except Exception:
        # no Pillow: embed raw bytes as-is
        import mimetypes
        media = mimetypes.guess_type(str(path))[0] or "image/png"
        b64 = base64.standard_b64encode(path.read_bytes()).decode()
        return f"data:{media};base64,{b64}"
    im = Image.open(path)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    im.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=82)
    b64 = base64.standard_b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


# ---------------------------------------------------------------------------
def ingest_paths(paths: list[str], cfg, *, headshot_hint: str | None = None,
                 ocr: bool = True) -> Ingested:
    out = Ingested()
    model = getattr(cfg, "llm_model", "claude-opus-4-8")
    ocr_ok, ocr_reason = llm_mod.available()

    for f in _expand(paths):
        # LinkedIn export (zip or folder)
        if linkedin_mod.looks_like_export(f):
            try:
                text, meta = linkedin_mod.parse_export(f)
                out.text_parts.append(text)
                out.metadata = merge_meta(out.metadata, meta)
                out.notes.append(f"linkedin   {f.name} ({len(meta.get('recent_titles', []))} positions, "
                                 f"{len(meta.get('skills', []))} skills)")
            except Exception as e:  # noqa: BLE001
                out.notes.append(f"linkedin   {f.name} FAILED: {e}")
            continue

        if not f.exists():
            out.notes.append(f"missing    {f}")
            continue
        ext = f.suffix.lower()

        if ext in DOC_EXT:
            try:
                text = profile_mod.extract_text(f)
                out.text_parts.append(text)
                out.notes.append(f"document   {f.name} ({len(text)} chars)")
            except Exception as e:  # noqa: BLE001
                out.notes.append(f"document   {f.name} FAILED: {e}")

        elif ext in IMG_EXT:
            if _is_headshot(f, headshot_hint) and not out.headshot:
                out.headshot = image_data_uri(f)
                out.notes.append(f"headshot   {f.name} (embedded)")
            elif ocr and ocr_ok:
                text = llm_mod.ocr_image(f, model=model)
                if text:
                    out.text_parts.append(text)
                    out.notes.append(f"image-ocr  {f.name} ({len(text)} chars via vision)")
                elif not out.headshot:
                    out.headshot = image_data_uri(f)
                    out.notes.append(f"headshot   {f.name} (no text found, used as photo)")
                else:
                    out.notes.append(f"image      {f.name} (no text)")
            else:
                if not out.headshot:
                    out.headshot = image_data_uri(f)
                    out.notes.append(f"headshot   {f.name} (OCR off: {ocr_reason})")
                else:
                    out.notes.append(f"image      {f.name} skipped (OCR off: {ocr_reason})")

        elif ext in DATA_EXT:
            try:
                raw = f.read_text(encoding="utf-8")
                data = yaml.safe_load(raw) if (ext != ".json" and _HAVE_YAML) else json.loads(raw)
                if isinstance(data, dict):
                    out.metadata = merge_meta(out.metadata, data)
                    out.notes.append(f"metadata   {f.name} ({len(data)} keys)")
            except Exception as e:  # noqa: BLE001
                out.notes.append(f"metadata   {f.name} FAILED: {e}")

        elif ext in CSV_EXT:
            text = f.read_text(encoding="utf-8", errors="ignore")
            out.text_parts.append(text)
            out.notes.append(f"tabular    {f.name} ({len(text)} chars)")

        else:
            out.notes.append(f"skipped    {f.name} (unsupported type {ext or '?'})")

    return out
