"""Offline tests for multi-source ingestion (no network, no API key needed)."""
import json
from pathlib import Path

from romewyld.config import Config
from romewyld import ingest, linkedin


def _png(path: Path, color=(120, 180, 90)):
    from PIL import Image
    Image.new("RGB", (12, 12), color).save(path)


def test_merge_meta_unions_lists_keeps_scalars():
    base = {"skills": ["python"], "name": "A", "remote_pref": "remote"}
    add = {"skills": ["aws", "python"], "name": "B", "locations": ["Denver"]}
    out = ingest.merge_meta(base, add)
    assert out["skills"] == ["python", "aws"]      # union, order-stable
    assert out["name"] == "A"                       # scalar: base kept
    assert out["locations"] == ["Denver"]


def test_ingest_mixed_folder(tmp_path):
    (tmp_path / "resume.md").write_text("Senior Python Engineer. AWS, Kubernetes.", encoding="utf-8")
    (tmp_path / "extra.json").write_text(json.dumps({"target_titles": ["SRE"], "tags": ["platform"]}), encoding="utf-8")
    (tmp_path / "notes.csv").write_text("col\nGo and Kafka experience", encoding="utf-8")
    _png(tmp_path / "headshot.png")

    ing = ingest.ingest_paths([str(tmp_path)], Config(), ocr=False)
    blob = "\n".join(ing.text_parts)
    assert "Python Engineer" in blob and "Kafka" in blob   # md + csv folded in
    assert ing.metadata["target_titles"] == ["SRE"]
    assert ing.metadata["tags"] == ["platform"]
    assert ing.headshot.startswith("data:image/")          # headshot embedded
    assert any("headshot" in n for n in ing.notes)


def test_image_without_hint_becomes_headshot_when_ocr_off(tmp_path):
    _png(tmp_path / "scan001.png")
    ing = ingest.ingest_paths([str(tmp_path)], Config(), ocr=False)
    assert ing.headshot.startswith("data:image/")
    assert any("OCR off" in n for n in ing.notes)


def _make_linkedin_dir(tmp_path: Path) -> Path:
    d = tmp_path / "LinkedInExport"
    d.mkdir()
    (d / "Profile.csv").write_text(
        "First Name,Last Name,Headline,Summary,Industry\n"
        "Jordan,Rivera,Staff Engineer,Backend & ML platforms,Software\n", encoding="utf-8")
    (d / "Positions.csv").write_text(
        "Company Name,Title,Description,Started On\n"
        "Acme,Senior Software Engineer,Built data platform on AWS,2021\n", encoding="utf-8")
    (d / "Skills.csv").write_text("Name\nPython\nKubernetes\nKafka\n", encoding="utf-8")
    (d / "Education.csv").write_text("School Name,Degree Name\nCU Boulder,BS CS\n", encoding="utf-8")
    return d


def test_linkedin_export_detected_and_parsed(tmp_path):
    d = _make_linkedin_dir(tmp_path)
    assert linkedin.looks_like_export(d)
    text, meta = linkedin.parse_export(d)
    assert meta["name"] == "Jordan Rivera"
    assert "Staff Engineer" in meta["target_titles"]
    assert "Senior Software Engineer" in meta["recent_titles"]
    assert {"Python", "Kubernetes", "Kafka"} <= set(meta["skills"])
    assert "AWS" in text


def test_ingest_picks_up_linkedin_folder(tmp_path):
    _make_linkedin_dir(tmp_path)
    ing = ingest.ingest_paths([str(tmp_path)], Config(), ocr=False)
    assert ing.metadata.get("name") == "Jordan Rivera"
    assert any("linkedin" in n for n in ing.notes)


def test_linkedin_zip(tmp_path):
    import zipfile
    d = _make_linkedin_dir(tmp_path)
    z = tmp_path / "export.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in d.iterdir():
            zf.write(f, f.name)
    assert linkedin.looks_like_export(z)
    _, meta = linkedin.parse_export(z)
    assert meta["name"] == "Jordan Rivera"
