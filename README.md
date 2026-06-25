# romewyld

Give it a **resume/CV** + some **public metadata**, get back **ranked job-application
leads** — scored, explained, deduped, and rendered to JSON / CSV / Markdown / a
filterable HTML dashboard. Optional Anthropic enrichment writes a per-lead fit
assessment, tailored resume tweaks, and a cover-letter hook.

**Live demo dashboard:** https://1seansean1.github.io/romewyld/

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
python -m romewyld examples/sample_resume.md -m examples/sample_metadata.yaml

# 2. pass BOTH a CV and a resume — they're merged into one profile
python -m romewyld my_cv.pdf my_resume.docx -m me.yaml -c config.yaml --llm

# 3. just see how your documents parsed
python -m romewyld my_resume.pdf --dry-run
```

Outputs land in `data/out/leads.{json,csv,md,html}`. Open `leads.html` for the
dashboard (search box, source filter, remote-only toggle, score bars).

## Inputs

Pass **any mix of files and folders** as positional arguments — romewyld classifies
each one and folds them all into a single candidate profile. Point it at a whole
folder of material and it scans recursively:

| Material | How it's used |
|---|---|
| `.pdf` `.docx` `.md` `.txt` `.rtf` | CV / resume text extraction |
| LinkedIn export (`.zip` or the unzipped folder) | parses Profile / Positions / Skills / Education CSVs |
| images `.png` `.jpg` `.webp` … | OCR'd to text via Claude vision; a headshot is embedded in the dashboard instead |
| `.json` / `.yaml` | merged as structured metadata (tags, terms, links, target titles …) |
| `.csv` | folded in as text |

A headshot is detected by filename (`headshot`, `photo`, `portrait`, `avatar`, …)
or set explicitly with `--headshot path.jpg`. Image OCR uses Claude vision when
`ANTHROPIC_API_KEY` is set; pass `--no-ocr` to skip it. Tags and terms (from a
`.json`/`.yaml` or metadata file) become search keywords; Google Scholar / portfolio
/ LinkedIn URLs are stored as links and publications.

```bash
# throw a whole folder of material at it
python -m romewyld ./my_materials/ -m me.yaml
# or list inputs explicitly
python -m romewyld cv.pdf linkedin_export.zip headshot.jpg tags.json -m me.yaml
```

Everything parsed shows up in the dashboard's **Profile & Metadata** tab, including
an "Ingested inputs" log of exactly what was folded in.

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
python -m romewyld RESUME [RESUME ...] [-m METADATA] [-c CONFIG] [-o OUTDIR]
                   [--sources a,b,c] [--companies x,y] [--top N]
                   [--min-salary N] [--remote] [--llm] [--dry-run]
```

`RESUME` accepts multiple files — pass your CV **and** your resume to merge them.

## Library

```python
from romewyld import build_profile, extract_text, rank, get_source, load_config

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
romewyld/
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
