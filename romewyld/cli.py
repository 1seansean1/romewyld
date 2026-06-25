"""Command-line entrypoint: resume + metadata -> ranked job leads."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import profile as profile_mod
from . import metadata as meta_mod
from . import ingest as ingest_mod
from . import match as match_mod
from . import report as report_mod
from . import llm as llm_mod
from .config import load_config, Config
from .models import CandidateProfile
from .sources import get_source, ALL_SOURCES


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def collect(profile: CandidateProfile, cfg: Config, only: list[str] | None = None) -> list:
    sources = only or cfg.sources
    all_jobs = []
    for name in sources:
        try:
            src = get_source(name)
        except KeyError as e:
            _log(f"  ! {e}")
            continue
        ok, reason = src.available(cfg)
        if not ok:
            _log(f"  - {name:11s} skipped ({reason})")
            continue
        t0 = time.time()
        try:
            jobs = src.search(profile, cfg)
        except Exception as e:  # noqa: BLE001
            _log(f"  ! {name:11s} error: {e}")
            continue
        dt = time.time() - t0
        _log(f"  + {name:11s} {len(jobs):4d} postings ({dt:.1f}s)")
        all_jobs.extend(jobs)
    return all_jobs


def run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    # CLI overrides
    if args.sources:
        cfg.sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    if args.top:
        cfg.top_n = args.top
    if args.remote:
        cfg.remote_pref = "remote"
    if args.min_salary:
        cfg.min_salary = args.min_salary
    if args.companies:
        cfg.target_companies = [c.strip() for c in args.companies.split(",") if c.strip()]
    if args.llm:
        cfg.llm_enabled = True

    # ---- 1. ingest + profile ----
    inputs = args.resume if isinstance(args.resume, list) else [args.resume]
    md = meta_mod.load_metadata(args.metadata) if args.metadata else {}
    _log("Ingesting: " + ", ".join(inputs))
    ing = ingest_mod.ingest_paths(
        inputs, cfg, headshot_hint=args.headshot or md.get("headshot"),
        ocr=not args.no_ocr,
    )
    for n in ing.notes:
        _log(f"  {n}")
    resume_text = "\n\n".join(tp for tp in ing.text_parts if tp)
    # user-supplied metadata (-m) wins over auto-ingested structured data
    md = ingest_mod.merge_meta(ing.metadata, md)
    if md.get("github") or md.get("github_url"):
        _log("Enriching from GitHub…")
        md = meta_mod.enrich_from_github(md, user_agent=cfg.user_agent)
    prof = profile_mod.build_profile(resume_text, md)
    if ing.headshot and not prof.headshot:
        prof.headshot = ing.headshot
    prof.sources_ingested = ing.notes
    # merge config-level filters into profile
    if cfg.remote_pref and prof.remote_pref == "any":
        prof.remote_pref = cfg.remote_pref
    if cfg.locations and not prof.locations:
        prof.locations = cfg.locations
    if cfg.target_titles and not prof.target_titles:
        prof.target_titles = cfg.target_titles
    prof.keywords = list(dict.fromkeys(prof.keywords + cfg.keywords))
    prof.exclude_keywords = list(dict.fromkeys(prof.exclude_keywords + cfg.exclude_keywords))
    if cfg.min_salary and not prof.min_salary:
        prof.min_salary = cfg.min_salary

    _log(
        f"Profile: {prof.name or '(name?)'} | {prof.seniority or '?'} "
        f"(~{prof.years_experience:.0f}y) | {len(prof.skills)} skills"
    )
    _log(f"  targets: {', '.join(prof.target_titles) or '(none derived)'}")
    _log(f"  skills:  {', '.join(prof.skills[:18])}{' …' if len(prof.skills) > 18 else ''}")

    if args.dry_run:
        import json
        print(json.dumps(prof.to_dict(), indent=2))
        return 0

    # ---- 2. collect ----
    _log(f"\nSearching {len(cfg.sources)} sources…")
    jobs = collect(prof, cfg)
    _log(f"Collected {len(jobs)} raw postings")
    if not jobs:
        _log("No postings found. Try different --sources, add target_companies, or check connectivity.")
        return 2

    # ---- 3. rank ----
    leads = match_mod.rank(prof, jobs, cfg)
    if cfg.min_score:
        leads = [l for l in leads if l.score >= cfg.min_score]
    leads = leads[: cfg.top_n]
    _log(f"Ranked → top {len(leads)} leads")

    # ---- 4. optional LLM enrichment ----
    if cfg.llm_enabled:
        ok, reason = llm_mod.available()
        if ok:
            _log(f"LLM enrichment ({cfg.llm_model}) on top {cfg.llm_top_n}…")
            n = llm_mod.enrich(prof, leads, model=cfg.llm_model, top_n=cfg.llm_top_n)
            _log(f"  enriched {n} leads")
        else:
            _log(f"LLM enrichment requested but unavailable: {reason}")

    # ---- 5. report ----
    paths = report_mod.write_all(prof, leads, args.outdir, stem=args.stem)
    _log("\nWrote:")
    for fmt, p in paths.items():
        _log(f"  {fmt:4s} {p}")

    # console preview
    print()
    for i, l in enumerate(leads[: min(10, len(leads))], 1):
        j = l.job
        loc = j.location or ("Remote" if j.remote else "")
        print(f"{i:2d}. [{l.score:5.1f}] {j.title[:48]:48s} {(' @ ' + j.company)[:24]:24s} {loc[:18]:18s} {j.source}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="romewyld",
        description="Turn a resume/CV + public metadata into ranked job-application leads.",
    )
    p.add_argument("resume", nargs="+", metavar="INPUT",
                   help="any mix of files/folders: CV, resume, LinkedIn export (.zip/folder), "
                        "images (OCR'd or used as headshot), .json/.yaml metadata, .csv. "
                        "A folder is scanned recursively.")
    p.add_argument("-m", "--metadata", help="public metadata file (.yaml/.json)")
    p.add_argument("--headshot", help="path to a headshot image to embed in the dashboard")
    p.add_argument("--no-ocr", action="store_true", help="don't OCR images via Claude vision")
    p.add_argument("-c", "--config", help="config file (.yaml/.json)")
    p.add_argument("-o", "--outdir", default="data/out", help="output directory (default: data/out)")
    p.add_argument("--stem", default="leads", help="output filename stem (default: leads)")
    p.add_argument("--sources", help=f"comma list; available: {', '.join(ALL_SOURCES)}")
    p.add_argument("--companies", help="comma list of greenhouse/lever/ashby board tokens")
    p.add_argument("--top", type=int, help="number of leads to keep")
    p.add_argument("--min-salary", type=int, help="salary floor")
    p.add_argument("--remote", action="store_true", help="remote only")
    p.add_argument("--llm", action="store_true", help="enable Anthropic enrichment (needs ANTHROPIC_API_KEY)")
    p.add_argument("--dry-run", action="store_true", help="print parsed profile and exit")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except FileNotFoundError as e:
        _log(f"File not found: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        _log(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
