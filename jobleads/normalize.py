"""Text normalization, tokenization, and skill extraction."""
from __future__ import annotations

import re
from functools import lru_cache

# A pragmatic, extensible lexicon of recognizable skills/technologies/competencies.
# Multi-word phrases are matched first. Keep lowercase.
SKILL_LEXICON: set[str] = {
    # languages
    "python", "java", "javascript", "typescript", "go", "golang", "rust", "c++", "c#",
    "c", "ruby", "php", "scala", "kotlin", "swift", "r", "matlab", "sql", "bash",
    "powershell", "perl", "julia", "dart", "elixir", "haskell", "lua", "fortran",
    # web / frontend
    "react", "react native", "vue", "angular", "svelte", "next.js", "nextjs", "node.js",
    "nodejs", "express", "django", "flask", "fastapi", "spring", "spring boot", "rails",
    "laravel", "graphql", "rest", "html", "css", "tailwind", "redux", "webpack", "vite",
    # data / ml
    "machine learning", "deep learning", "nlp", "computer vision", "llm", "pytorch",
    "tensorflow", "keras", "scikit-learn", "sklearn", "pandas", "numpy", "spark",
    "hadoop", "kafka", "airflow", "dbt", "snowflake", "databricks", "tableau",
    "power bi", "looker", "data engineering", "data science", "mlops", "reinforcement learning",
    "rag", "vector database", "embeddings", "transformers",
    # cloud / devops
    "aws", "azure", "gcp", "google cloud", "kubernetes", "k8s", "docker", "terraform",
    "ansible", "jenkins", "github actions", "gitlab ci", "ci/cd", "helm", "prometheus",
    "grafana", "datadog", "linux", "nginx", "serverless", "lambda", "ec2", "s3",
    "cloudformation", "pulumi", "istio", "argocd",
    # databases
    "postgres", "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "dynamodb",
    "cassandra", "sqlite", "oracle", "bigquery", "redshift", "neo4j", "clickhouse",
    # security
    "cybersecurity", "penetration testing", "incident response", "threat modeling",
    "siem", "soc", "nist", "iso 27001", "owasp", "vulnerability management", "zero trust",
    "cryptography", "reverse engineering", "malware analysis", "forensics",
    # methods / pm
    "agile", "scrum", "kanban", "jira", "product management", "program management",
    "stakeholder management", "roadmap", "okrs", "systems engineering", "requirements",
    "earned value", "risk management", "cost estimation", "acquisition", "contracts",
    "far", "dfars", "milestone", "gantt", "wbs",
    # domain
    "aerospace", "defense", "space", "satellite", "rf", "signal processing", "gnc",
    "embedded", "firmware", "fpga", "robotics", "controls", "telemetry", "orbital mechanics",
    "fintech", "healthcare", "biotech", "saas", "b2b", "ecommerce", "logistics",
    # soft / leadership
    "leadership", "mentoring", "communication", "strategy", "operations", "hiring",
    "team building", "cross-functional", "p&l", "go-to-market", "fundraising",
}

# canonical aliases -> canonical form
SKILL_ALIASES: dict[str, str] = {
    "golang": "go",
    "k8s": "kubernetes",
    "nextjs": "next.js",
    "nodejs": "node.js",
    "sklearn": "scikit-learn",
    "postgresql": "postgres",
    "google cloud": "gcp",
    "ml": "machine learning",
}

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.#\-]*")
_EMAIL_RE = re.compile(r"[\w.\-+]+@[\w\-]+\.[\w.\-]+")
_PHONE_RE = re.compile(r"(?:\+?\d{1,2}[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
_URL_RE = re.compile(r"https?://[^\s)<>\"']+|(?:www\.|linkedin\.com|github\.com)[^\s)<>\"']+")

# very small English stopword set for TF-IDF token cleanup
STOPWORDS: set[str] = set(
    """a an the and or but if then else for to of in on at by with from as is are was were be been
    being this that these those it its we you they he she i our your their will would can could should
    may might must do does did have has had not no yes will more most some any all each our about into
    over under out up down off than too very just also etc per via using use used work working role job
    team teams company companies experience years year strong excellent ability able including include""".split()
)


def normalize_text(text: str) -> str:
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def clean_tokens(text: str) -> list[str]:
    return [t for t in tokenize(text) if t not in STOPWORDS and len(t) > 1]


def canonical_skill(skill: str) -> str:
    s = skill.strip().lower()
    return SKILL_ALIASES.get(s, s)


@lru_cache(maxsize=1)
def _sorted_lexicon() -> list[str]:
    # longest phrases first so multi-word skills win over substrings
    return sorted(SKILL_LEXICON, key=lambda s: (-len(s), s))


def extract_skills(text: str) -> list[str]:
    """Find known skills present in free text. Returns canonicalized, de-duped, order-stable."""
    if not text:
        return []
    low = " " + re.sub(r"[^a-z0-9+.#\-\s]", " ", text.lower()) + " "
    found: list[str] = []
    seen: set[str] = set()
    for skill in _sorted_lexicon():
        # word-boundary-ish match; skills with special chars handled by padding spaces
        needle = skill
        pattern = r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])"
        if re.search(pattern, low):
            canon = canonical_skill(skill)
            if canon not in seen:
                seen.add(canon)
                found.append(canon)
    return found


def extract_contacts(text: str) -> dict[str, list[str]]:
    emails = list(dict.fromkeys(_EMAIL_RE.findall(text)))
    phones = list(dict.fromkeys(m.strip() for m in _PHONE_RE.findall(text) if len(re.sub(r"\D", "", m)) >= 10))
    urls = list(dict.fromkeys(u.rstrip(".,);") for u in _URL_RE.findall(text)))
    return {"emails": emails, "phones": phones, "urls": urls}


SENIORITY_RANK = {
    "intern": 0, "junior": 1, "associate": 1, "mid": 2, "intermediate": 2,
    "senior": 3, "staff": 4, "lead": 4, "principal": 5, "director": 6,
    "head": 6, "vp": 7, "chief": 8, "cto": 8, "ceo": 8, "executive": 7,
}


def infer_seniority(text: str, years: float = 0.0) -> str:
    low = text.lower()
    best = ""
    best_rank = -1
    for token, rank in SENIORITY_RANK.items():
        if re.search(r"(?<![a-z])" + token + r"(?![a-z])", low) and rank > best_rank:
            best, best_rank = token, rank
    if best:
        # collapse to canonical bands
        if best_rank <= 1:
            return "junior"
        if best_rank == 2:
            return "mid"
        if best_rank == 3:
            return "senior"
        if best_rank in (4,):
            return "lead"
        if best_rank == 5:
            return "principal"
        return "exec"
    # fall back to years
    if years >= 12:
        return "principal"
    if years >= 8:
        return "senior"
    if years >= 4:
        return "mid"
    if years > 0:
        return "junior"
    return ""
