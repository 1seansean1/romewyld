"""Offline source tests: monkeypatch the HTTP layer with canned API payloads."""
import romewyld.http as http
from romewyld.config import Config
from romewyld.models import CandidateProfile
from romewyld import sources


def _profile():
    return CandidateProfile(skills=["python", "aws"], target_titles=["Backend Engineer"],
                            recent_titles=["Engineer"], raw_text="python aws")


def test_registry_complete():
    expected = {"remotive", "remoteok", "arbeitnow", "themuse", "jobicy",
                "hackernews", "adzuna", "usajobs", "greenhouse", "lever", "ashby"}
    assert expected <= set(sources.ALL_SOURCES)


def test_remotive_parsing(monkeypatch):
    payload = {"jobs": [{
        "title": "Backend Engineer", "company_name": "Acme",
        "candidate_required_location": "USA", "url": "https://x/1",
        "description": "<p>Python and AWS</p>", "publication_date": "2026-06-01",
        "tags": ["python", "aws"], "salary": "$150k",
    }]}
    monkeypatch.setattr(http, "get_json", lambda *a, **k: payload)
    monkeypatch.setattr("romewyld.sources.remotive.http.get_json", lambda *a, **k: payload)
    jobs = sources.get_source("remotive").search(_profile(), Config())
    assert jobs and jobs[0].title == "Backend Engineer"
    assert "Python and AWS" in jobs[0].description  # html stripped
    assert jobs[0].remote is True


def test_remoteok_skips_legal_notice(monkeypatch):
    payload = [
        {"legal": "notice, no position key here"},
        {"position": "Senior Python Engineer", "company": "Beta", "url": "https://x/2",
         "description": "<b>Python</b> AWS", "tags": ["python"], "date": "2026-05-01"},
    ]
    monkeypatch.setattr("romewyld.sources.remoteok.http.get_json", lambda *a, **k: payload)
    jobs = sources.get_source("remoteok").search(_profile(), Config())
    assert len(jobs) == 1
    assert jobs[0].title == "Senior Python Engineer"


def test_greenhouse_requires_boards():
    cfg = Config()
    ok, _ = sources.get_source("greenhouse").available(cfg)
    assert ok is False
    cfg.target_companies = ["stripe"]
    ok, _ = sources.get_source("greenhouse").available(cfg)
    assert ok is True


def test_greenhouse_parsing(monkeypatch):
    payload = {"jobs": [{
        "title": "Software Engineer, Backend", "location": {"name": "Remote"},
        "absolute_url": "https://boards.greenhouse.io/x/1",
        "content": "&lt;p&gt;Python AWS Kubernetes&lt;/p&gt;",
        "updated_at": "2026-06-10", "departments": [{"name": "Eng"}],
    }]}
    monkeypatch.setattr("romewyld.sources.greenhouse.http.get_json", lambda *a, **k: payload)
    cfg = Config(target_companies=["acme"])
    jobs = sources.get_source("greenhouse").search(_profile(), cfg)
    assert jobs and jobs[0].company == "acme"
    assert jobs[0].remote is True


def test_adzuna_unavailable_without_keys():
    ok, reason = sources.get_source("adzuna").available(Config())
    assert ok is False and "ADZUNA" in reason


def test_lever_parsing(monkeypatch):
    payload = [{
        "text": "Backend Engineer", "categories": {"location": "Remote", "team": "Platform"},
        "hostedUrl": "https://jobs.lever.co/x/1", "descriptionPlain": "Python AWS",
        "createdAt": 1717200000000,
    }]
    monkeypatch.setattr("romewyld.sources.lever.http.get_json", lambda *a, **k: payload)
    cfg = Config(target_companies=["acme"])
    jobs = sources.get_source("lever").search(_profile(), cfg)
    assert jobs and jobs[0].title == "Backend Engineer" and jobs[0].remote
