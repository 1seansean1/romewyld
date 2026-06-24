import json
from pathlib import Path

from jobleads.models import CandidateProfile, JobPosting
from jobleads import match, report


def _leads():
    prof = CandidateProfile(name="Jordan", skills=["python", "aws"],
                            target_titles=["Backend Engineer"], seniority="senior",
                            years_experience=9, raw_text="python aws backend")
    jobs = [
        JobPosting(source="t", title="Backend Engineer", company="Acme", remote=True,
                   url="https://x/1", description="python aws kubernetes"),
        JobPosting(source="t", title="Designer", company="B", url="https://x/2",
                   description="figma css"),
    ]
    return prof, match.rank(prof, jobs)


def test_write_all_creates_four_formats(tmp_path):
    prof, leads = _leads()
    paths = report.write_all(prof, leads, tmp_path, stem="t")
    for fmt in ("json", "csv", "md", "html"):
        assert Path(paths[fmt]).exists()
        assert Path(paths[fmt]).stat().st_size > 0


def test_json_structure(tmp_path):
    prof, leads = _leads()
    paths = report.write_all(prof, leads, tmp_path, stem="t")
    data = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert data["count"] == len(leads)
    assert data["candidate"]["name"] == "Jordan"
    assert data["leads"][0]["job"]["title"]
    assert "score" in data["leads"][0]


def test_html_has_cards_and_filter(tmp_path):
    prof, leads = _leads()
    paths = report.write_all(prof, leads, tmp_path, stem="t")
    html = Path(paths["html"]).read_text(encoding="utf-8")
    assert "Backend Engineer" in html
    assert "function flt()" in html
    assert "Jordan" in html
