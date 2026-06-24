# job-leads

Give it a **resume/CV** + some **public metadata**, get back **ranked job-application
leads** — scored, explained, deduped, and rendered to JSON / CSV / Markdown / a
filterable HTML dashboard. Optional Anthropic enrichment writes a per-lead fit
assessment, tailored resume tweaks, and a cover-letter hook.

```
resume.(pdf|docx|md|txt) ─┐
                          ├─▶ profile ─▶ search 11 sources ─▶ rank ─▶ [LLM] ─▶ report
metadata.(yaml|json) ─────┘
```

## Why

Job boards make you search title-by-title and eyeball relevance. This inverts it:
parse what you actually are (skills, seniority, history) once, fan out across many
job sources, and score every posting against *you* with a transparent breakdown so
you know **why** each lead ranks where it does.

## Install

Core needs only `requests`. The full feature set (PDF/DOCX parsing, YAML config,
sklearn ranking) uses libs that are commonly already present:

```bash
pip install -e ".[full]"        # resume parsing + yaml + sklearn ranking
pip install -e ".[full,llm]"    # + Anthropic enrichment
```

Everything degrades gracefully: no sklearn → pure-Python TF cosine fallback; no
PyYAML → use JSON config; no `anthropic`/key → skip LLM, keep deterministic scoring.

## Quick start

```bash
# 1. no-key sources, out of the box
python -m jobleads examples/sample_resume.md -m examples/sample_metadata.yaml

# 2. with a config + company boards + LLM enrichment
python -m jobleads my_resume.pdf -m me.yaml -c config.yaml --llm

# 3. just see how your resume parsed
python -m jobleads my_resume.pdf --dry-run
```

Outputs land in `data/out/leads.{json,csv,md,html}`. Open `leads.html` for the
dashboard (search box, source filter, remote-only toggle, score bars).

## Inputs

**Resume/CV** — `.pdf`, `.docx`, `.md`, or `.txt`. Parsed for contacts, skills
(against an extensible lexicon), held titles, years of experience, seniority band,
and clearance.

**Metadata** (optional `.yaml`/`.json`) — overrides and augments what the resume
can't say. See [examples/sample_metadata.yaml](examples/sample_metadata.yaml):

```yaml
target_titles: [Staff Software Engineer, ML Platform Engineer]
seniority: senior
github: yourhandle           # pulls public language/topic signal
remote_pref: remote          # any | remote | hybrid | onsite
locations: [Denver, Remote US]
min_salary: 180000
keywords: [distributed systems]
exclude_keywords: [clearance required, internship]
skills: [grpc, event-driven] # assert skills beyond the resume
```

## Sources

| Source | Key needed | Notes |
|---|---|---|
| `remotive` | no | remote jobs, server-side search |
| `remoteok` | no | remote jobs feed |
| `arbeitnow` | no | EU + remote board |
| `themuse` | optional | key only raises rate limits |
| `jobicy` | no | remote jobs, tag search |
| `hackernews` | no | latest "Who is hiring?" thread |
| `adzuna` | yes | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` |
| `usajobs` | yes | `USAJOBS_API_KEY`, `USAJOBS_EMAIL` (US federal) |
| `greenhouse` | no | per-company boards (slugs) |
| `lever` | no | per-company boards (slugs) |
| `ashby` | no | per-company boards (names) |

Keys come from **environment variables only**, never config files. For
`greenhouse`/`lever`/`ashby`, list company board slugs in `target_companies` or
`--companies stripe,anthropic,ramp` (find the slug in the careers-page URL).

## Scoring

Each posting gets a 0-100 score from six weighted signals, all surfaced per lead:

| Signal | Weight | What it measures |
|---|---|---|
| similarity | 35 | TF-IDF cosine between your profile and the posting |
| skills | 30 | overlap of your skills with the posting's detected skills |
| title | 15 | token overlap with your target/held titles |
| location | 8 | remote/location preference fit |
| seniority | 7 | your band vs. the posting's inferred band |
| recency | 5 | how recently it was posted |

Salary below your floor and excluded keywords apply penalties and raise flags.
Postings are deduped by URL (then company+title) across all sources.

## LLM enrichment (optional)

With `--llm` and `ANTHROPIC_API_KEY` set, the top N leads get a structured
assessment via Claude (`fit`, `confidence`, 2-3 sentence summary, up to 4 concrete
resume tweaks, a cover-letter hook). Honest by design — it's told not to invent
experience you don't have. Skipped silently if unavailable.

## CLI

```
python -m jobleads RESUME [-m METADATA] [-c CONFIG] [-o OUTDIR]
                   [--sources a,b,c] [--companies x,y] [--top N]
                   [--min-salary N] [--remote] [--llm] [--dry-run]
```

## Library

```python
from jobleads import build_profile, extract_text, rank, get_source, load_config

prof = build_profile(extract_text("resume.pdf"), {"target_titles": ["SRE"]})
cfg = load_config(None)
jobs = get_source("remotive").search(prof, cfg)
leads = rank(prof, jobs, cfg)
for l in leads[:5]:
    print(l.score, l.job.title, l.rationale)
```

## Tests

```bash
python -m pytest -q     # 23 tests, fully offline (sources use canned payloads)
```

## Layout

```
jobleads/
  profile.py    resume → CandidateProfile
  metadata.py   metadata load + GitHub enrichment
  match.py      scoring/ranking engine
  llm.py        optional Anthropic enrichment
  report.py     JSON/CSV/Markdown/HTML output
  cli.py        orchestrator
  sources/      11 job-source connectors + registry
```

## License

MIT.
