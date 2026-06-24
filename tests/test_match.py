from jobleads.models import CandidateProfile, JobPosting
from jobleads import match


def _profile():
    return CandidateProfile(
        name="Test",
        skills=["python", "aws", "kubernetes", "kafka", "go", "machine learning"],
        target_titles=["Backend Engineer", "ML Platform Engineer"],
        recent_titles=["Senior Software Engineer"],
        seniority="senior",
        years_experience=9,
        remote_pref="remote",
        raw_text="senior backend engineer python aws kubernetes kafka distributed systems",
    )


def _jobs():
    return [
        JobPosting(source="t", title="Senior Backend Engineer", company="Good",
                   remote=True, url="u1",
                   description="Python, AWS, Kubernetes, Kafka, distributed systems, ML platform."),
        JobPosting(source="t", title="Frontend Designer", company="Mismatch",
                   remote=False, location="NYC onsite", url="u2",
                   description="Figma, CSS, branding, illustration, no backend."),
        JobPosting(source="t", title="Staff ML Platform Engineer", company="Great",
                   remote=True, url="u3",
                   description="Python, Kubernetes, machine learning, Kafka, Go, Spark, Airflow."),
    ]


def test_ranking_orders_by_fit():
    leads = match.rank(_profile(), _jobs())
    assert len(leads) == 3
    # the relevant backend/ML roles should outrank the frontend designer
    titles = [l.job.title for l in leads]
    assert titles[-1] == "Frontend Designer"
    assert leads[0].score > leads[-1].score


def test_scores_bounded():
    for l in match.rank(_profile(), _jobs()):
        assert 0.0 <= l.score <= 100.0
        assert l.rationale


def test_matched_and_missing_skills():
    leads = match.rank(_profile(), _jobs())
    top = leads[0]
    assert "python" in top.matched_skills


def test_dedupe_by_url():
    j = JobPosting(source="t", title="X", url="dup", description="python")
    j2 = JobPosting(source="t", title="X", url="dup", description="python")
    leads = match.rank(_profile(), [j, j2])
    assert len(leads) == 1


def test_exclude_keyword_penalty():
    prof = _profile()
    prof.exclude_keywords = ["clearance required"]
    jobs = [
        JobPosting(source="t", title="Backend Engineer", url="a",
                   description="python aws kubernetes kafka"),
        JobPosting(source="t", title="Backend Engineer", url="b",
                   description="python aws kubernetes kafka clearance required ts/sci"),
    ]
    leads = match.rank(prof, jobs)
    by_url = {l.job.url: l for l in leads}
    assert by_url["b"].score < by_url["a"].score
    assert any("excluded" in f for f in by_url["b"].flags)


def test_date_parsing():
    assert match._parse_date("2026-06-01T12:00:00Z") is not None
    assert match._parse_date("1700000000") is not None
    assert match._parse_date("") is None
