from pathlib import Path

from romewyld import normalize as N
from romewyld.profile import build_profile, estimate_years, guess_name, extract_text

RESUME = (Path(__file__).resolve().parent.parent / "examples" / "sample_resume.md").read_text(encoding="utf-8")


def test_extract_skills_finds_known():
    sk = N.extract_skills("Built services in Python and Go on AWS with Kubernetes and Kafka.")
    for s in ["python", "go", "aws", "kubernetes", "kafka"]:
        assert s in sk


def test_skill_aliases_canonicalize():
    sk = N.extract_skills("Strong with golang and k8s and sklearn")
    assert "go" in sk and "kubernetes" in sk and "scikit-learn" in sk
    assert "golang" not in sk


def test_estimate_years_explicit():
    assert estimate_years("9 years of experience building systems") == 9.0


def test_guess_name():
    assert guess_name(RESUME).lower().startswith("jordan")


def test_build_profile_from_sample():
    prof = build_profile(RESUME)
    assert prof.emails == ["jordan.rivera@example.com"]
    assert prof.years_experience >= 8
    assert "python" in prof.skills and "kubernetes" in prof.skills
    assert prof.seniority in ("senior", "lead", "principal")
    assert prof.search_document()


def test_metadata_overrides():
    prof = build_profile(RESUME, {"target_titles": ["Staff Engineer"], "remote_pref": "remote",
                                  "skills": ["grpc"], "min_salary": 180000})
    assert "Staff Engineer" in prof.target_titles
    assert prof.remote_pref == "remote"
    assert "grpc" in prof.skills
    assert prof.min_salary == 180000


def test_infer_seniority_bands():
    assert N.infer_seniority("Senior Software Engineer") == "senior"
    assert N.infer_seniority("Principal Engineer") == "principal"
    assert N.infer_seniority("", years=2) == "junior"
