"""Render ranked leads to JSON, CSV, Markdown, and a standalone HTML dashboard."""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from .models import CandidateProfile, Lead


def write_all(profile: CandidateProfile, leads: list[Lead], outdir: str | Path, stem: str = "leads") -> dict[str, str]:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": str(out / f"{stem}.json"),
        "csv": str(out / f"{stem}.csv"),
        "md": str(out / f"{stem}.md"),
        "html": str(out / f"{stem}.html"),
    }
    write_json(profile, leads, paths["json"])
    write_csv(leads, paths["csv"])
    write_markdown(profile, leads, paths["md"])
    write_html(profile, leads, paths["html"])
    return paths


def write_json(profile: CandidateProfile, leads: list[Lead], path: str) -> None:
    payload = {
        "candidate": {
            "name": profile.name,
            "target_titles": profile.target_titles,
            "seniority": profile.seniority,
            "years_experience": profile.years_experience,
            "skills": profile.skills,
            "remote_pref": profile.remote_pref,
            "locations": profile.locations,
            "clearance": profile.clearance,
        },
        "count": len(leads),
        "leads": [l.to_dict() for l in leads],
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(leads: list[Lead], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["score", "title", "company", "location", "remote", "source",
                    "matched_skills", "missing_skills", "fit", "flags", "url"])
        for l in leads:
            w.writerow([
                round(l.score, 1), l.job.title, l.job.company, l.job.location,
                "yes" if l.job.remote else "", l.job.source,
                "; ".join(l.matched_skills), "; ".join(l.missing_skills),
                l.llm_fit, "; ".join(l.flags), l.job.url,
            ])


def write_markdown(profile: CandidateProfile, leads: list[Lead], path: str) -> None:
    lines = [f"# Job leads for {profile.name or 'candidate'}", ""]
    lines.append(
        f"_{len(leads)} leads · target: {', '.join(profile.target_titles) or 'n/a'} · "
        f"{profile.seniority or 'n/a'} (~{profile.years_experience:.0f}y) · "
        f"remote: {profile.remote_pref}_"
    )
    lines.append("")
    for i, l in enumerate(leads, 1):
        j = l.job
        lines.append(f"## {i}. {j.title} — {j.company or 'unknown'}  ·  **{l.score:.0f}/100**")
        meta = [j.location or ("Remote" if j.remote else "")]
        if j.salary:
            meta.append(j.salary)
        meta.append(f"source: {j.source}")
        if j.posted_at:
            meta.append(f"posted: {j.posted_at[:10]}")
        lines.append("  ·  ".join(m for m in meta if m))
        if j.url:
            lines.append(f"\n[Apply / view posting]({j.url})")
        lines.append(f"\n- **Why:** {l.rationale}")
        if l.matched_skills:
            lines.append(f"- **Matched skills:** {', '.join(l.matched_skills)}")
        if l.missing_skills:
            lines.append(f"- **Gaps:** {', '.join(l.missing_skills)}")
        if l.llm_summary:
            lines.append(f"- **Fit ({l.llm_fit}/{l.llm_confidence}):** {l.llm_summary}")
        if l.llm_resume_tweaks:
            lines.append("- **Resume tweaks:**")
            lines += [f"    - {t}" for t in l.llm_resume_tweaks]
        if l.llm_cover_hook:
            lines.append(f"- **Cover hook:** {l.llm_cover_hook}")
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def write_html(profile: CandidateProfile, leads: list[Lead], path: str) -> None:
    def esc(s: str) -> str:
        return html.escape(str(s or ""))

    cards = []
    for i, l in enumerate(leads, 1):
        j = l.job
        bar = int(round(l.score))
        skill_chips = "".join(f'<span class="chip ok">{esc(s)}</span>' for s in l.matched_skills[:12])
        gap_chips = "".join(f'<span class="chip gap">{esc(s)}</span>' for s in l.missing_skills[:6])
        flags = "".join(f'<span class="flag">{esc(fl)}</span>' for fl in l.flags)
        llm = ""
        if l.llm_summary:
            tweaks = "".join(f"<li>{esc(t)}</li>" for t in l.llm_resume_tweaks)
            llm = f"""<div class="llm">
              <div class="fit fit-{esc(l.llm_fit)}">{esc(l.llm_fit)} · {esc(l.llm_confidence)} confidence</div>
              <p>{esc(l.llm_summary)}</p>
              {f'<details><summary>Resume tweaks</summary><ul>{tweaks}</ul></details>' if tweaks else ''}
              {f'<details><summary>Cover hook</summary><p>{esc(l.llm_cover_hook)}</p></details>' if l.llm_cover_hook else ''}
            </div>"""
        meta = "  ·  ".join(
            esc(m) for m in [
                j.location or ("Remote" if j.remote else ""),
                j.salary, f"src: {j.source}", (j.posted_at[:10] if j.posted_at else "")
            ] if m
        )
        sig = " ".join(
            f'<span class="sig">{k} {v:.0f}</span>'
            for k, v in sorted(l.signals.items(), key=lambda kv: -kv[1])
        )
        cards.append(f"""
        <article class="card" data-score="{bar}" data-source="{esc(j.source)}" data-remote="{int(j.remote)}">
          <div class="rank">{i}</div>
          <div class="body">
            <h2><a href="{esc(j.url)}" target="_blank" rel="noopener">{esc(j.title)}</a></h2>
            <div class="company">{esc(j.company) or 'Unknown company'}</div>
            <div class="meta">{meta}</div>
            <div class="chips">{skill_chips}{gap_chips}</div>
            {f'<div class="flags">{flags}</div>' if flags else ''}
            <div class="sigs">{sig}</div>
            {llm}
          </div>
          <div class="scorebox">
            <div class="scorenum">{bar}</div>
            <div class="scorebar"><div class="fill" style="width:{bar}%"></div></div>
          </div>
        </article>""")

    sources = sorted({l.job.source for l in leads})
    source_opts = "".join(f'<option value="{esc(s)}">{esc(s)}</option>' for s in sources)

    # ----- Profile / Metadata tab -----
    from collections import Counter

    def row(label, value):
        if not value:
            return ""
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(x) for x in value)
        return f'<div class="mk">{esc(label)}</div><div class="mv">{esc(value)}</div>'

    def row_html(label, inner_html):
        if not inner_html:
            return ""
        return f'<div class="mk">{esc(label)}</div><div class="mv">{inner_html}</div>'

    def _href(u: str) -> str:
        return u if u.startswith("http") else "https://" + u

    contact = " · ".join(filter(None, [", ".join(profile.emails), ", ".join(profile.phones)]))
    url_links = " ".join(
        f'<a href="{esc(_href(u))}" target="_blank" rel="noopener">{esc(u)}</a>' for u in profile.urls
    )
    sen = ""
    if profile.seniority or profile.years_experience:
        sen = f"{profile.seniority or '?'} (~{profile.years_experience:.0f} yrs)"

    meta_rows = "".join([
        row("Name", profile.name),
        row_html("Contact", esc(contact)) if contact else "",
        row_html("Links", url_links),
        row("Target titles", profile.target_titles),
        row("Held titles", profile.recent_titles),
        row("Seniority", sen),
        row("Remote preference", profile.remote_pref),
        row("Locations", profile.locations),
        row("Min salary", f"${profile.min_salary:,}" if profile.min_salary else ""),
        row("Clearance", profile.clearance),
        row("Work authorization", profile.work_authorization),
        row("Industries", profile.industries),
        row("Certifications", profile.certifications),
        row("Keywords", profile.keywords),
        row("Exclude keywords", profile.exclude_keywords),
    ])
    all_skill_chips = "".join(f'<span class="chip ok">{esc(s)}</span>' for s in profile.skills)
    summary_block = (
        f'<h3>Summary</h3><div class="summary-block">{esc(profile.summary)}</div>'
        if profile.summary else ""
    )
    src_counts = Counter(l.job.source for l in leads)
    src_max = max(src_counts.values()) if src_counts else 1
    src_rows = "".join(
        f'<span class="sname">{esc(s)}</span>'
        f'<span class="sbar"><i style="width:{(c / src_max * 100):.0f}%"></i></span>'
        f'<span class="scount">{c}</span>'
        for s, c in src_counts.most_common()
    )
    scores = [l.score for l in leads]
    score_line = (
        f"top {max(scores):.0f} · median {sorted(scores)[len(scores)//2]:.0f} · low {min(scores):.0f}"
        if scores else "n/a"
    )

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job leads — {esc(profile.name or 'candidate')}</title>
<style>
:root{{--bg:#0f1115;--card:#181b22;--mut:#8b93a7;--fg:#e7eaf0;--ok:#1f6f43;--okc:#7ee2a8;
--gap:#4a3b1f;--gapc:#f0cf86;--accent:#5b8cff;--bar:#2a2f3a}}
*{{box-sizing:border-box}}
body{{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--fg)}}
header{{padding:24px 28px;border-bottom:1px solid #232733;position:sticky;top:0;background:var(--bg);z-index:5}}
h1{{margin:0 0 4px;font-size:20px}}
.sub{{color:var(--mut);font-size:13px}}
.controls{{margin-top:14px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
.controls input,.controls select{{background:var(--card);border:1px solid #2a2f3a;color:var(--fg);
padding:7px 10px;border-radius:8px;font-size:13px}}
main{{max-width:980px;margin:0 auto;padding:18px}}
.card{{display:flex;gap:14px;background:var(--card);border:1px solid #232733;border-radius:14px;
padding:16px 18px;margin-bottom:12px}}
.rank{{color:var(--mut);font-size:13px;min-width:22px}}
.body{{flex:1;min-width:0}}
h2{{margin:0 0 2px;font-size:16px}}
h2 a{{color:var(--fg);text-decoration:none}} h2 a:hover{{color:var(--accent)}}
.company{{color:var(--fg);font-weight:600;font-size:13px}}
.meta{{color:var(--mut);font-size:12px;margin:3px 0 8px}}
.chips{{display:flex;flex-wrap:wrap;gap:5px;margin:6px 0}}
.chip{{font-size:11px;padding:2px 8px;border-radius:20px}}
.chip.ok{{background:var(--ok);color:var(--okc)}}
.chip.gap{{background:var(--gap);color:var(--gapc)}}
.flags{{margin:6px 0}} .flag{{font-size:11px;color:#f0a886;border:1px solid #5a2f1f;padding:2px 8px;border-radius:6px;margin-right:6px}}
.sigs{{margin-top:6px}} .sig{{font-size:10px;color:var(--mut);margin-right:8px;font-variant-numeric:tabular-nums}}
.scorebox{{width:64px;text-align:center}}
.scorenum{{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}}
.scorebar{{height:6px;background:var(--bar);border-radius:4px;margin-top:6px;overflow:hidden}}
.fill{{height:100%;background:linear-gradient(90deg,#5b8cff,#7ee2a8)}}
.llm{{margin-top:10px;padding:10px 12px;background:#11141a;border-radius:10px;border:1px solid #232733}}
.fit{{font-weight:700;font-size:12px;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px}}
.fit-strong{{color:#7ee2a8}}.fit-moderate{{color:#9fc2ff}}.fit-stretch{{color:#f0cf86}}.fit-weak{{color:#f0a886}}
.llm p{{margin:4px 0}} details{{margin-top:6px}} summary{{cursor:pointer;color:var(--accent);font-size:12px}}
.llm li{{font-size:13px;margin:3px 0}}
.tabs{{margin-top:14px;display:flex;gap:6px}}
.tab{{background:transparent;border:1px solid #2a2f3a;color:var(--mut);padding:7px 14px;border-radius:8px;font-size:13px;cursor:pointer;font-family:inherit}}
.tab:hover{{color:var(--fg)}}
.tab.active{{background:var(--card);color:var(--fg);border-color:var(--accent)}}
.badge{{background:#2a2f3a;border-radius:10px;padding:1px 7px;font-size:11px;margin-left:5px}}
.panel{{display:none}} .panel.active{{display:block}}
.metacard{{background:var(--card);border:1px solid #232733;border-radius:14px;padding:20px 24px;max-width:760px}}
.meta-grid{{display:grid;grid-template-columns:160px 1fr;gap:9px 18px;font-size:14px}}
.mk{{color:var(--mut)}}
.mv{{color:var(--fg);word-break:break-word}}
.mv a{{color:var(--accent);text-decoration:none;margin-right:10px}} .mv a:hover{{text-decoration:underline}}
.metacard h3{{font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:var(--mut);margin:24px 0 11px}}
.metacard .chips{{margin:0}}
.sources-bd{{display:grid;grid-template-columns:120px 1fr 38px;gap:7px 12px;align-items:center;max-width:460px}}
.sname{{font-size:13px}}
.sbar{{height:8px;background:var(--bar);border-radius:5px;overflow:hidden}}
.sbar>i{{display:block;height:100%;background:linear-gradient(90deg,#5b8cff,#7ee2a8)}}
.scount{{font-size:13px;color:var(--mut);text-align:right;font-variant-numeric:tabular-nums}}
.summary-block{{font-size:14px;line-height:1.6;color:var(--fg)}}
</style></head>
<body>
<header>
  <h1>Job leads — {esc(profile.name or 'candidate')}</h1>
  <div class="sub">{len(leads)} leads · target: {esc(', '.join(profile.target_titles) or 'n/a')} ·
   {esc(profile.seniority or 'n/a')} (~{profile.years_experience:.0f}y) · remote: {esc(profile.remote_pref)}</div>
  <div class="tabs">
    <button class="tab active" data-tab="leads" onclick="tab('leads')">Leads <span class="badge">{len(leads)}</span></button>
    <button class="tab" data-tab="meta" onclick="tab('meta')">Profile &amp; Metadata</button>
  </div>
</header>
<main>
  <section id="panel-leads" class="panel active">
    <div class="controls">
      <input id="q" type="search" placeholder="filter title / company / skill…" oninput="flt()">
      <select id="src" onchange="flt()"><option value="">all sources</option>{source_opts}</select>
      <label class="sub"><input id="rem" type="checkbox" onchange="flt()"> remote only</label>
      <span class="sub" id="cnt"></span>
    </div>
    <div id="list">
{''.join(cards)}
    </div>
  </section>
  <section id="panel-meta" class="panel">
    <div class="metacard">
      <div class="meta-grid">{meta_rows}</div>
      {summary_block}
      <h3>Skills ({len(profile.skills)})</h3>
      <div class="chips">{all_skill_chips}</div>
      <h3>Lead sources</h3>
      <div class="sub" style="margin:-4px 0 11px">{len(leads)} leads · fit {score_line}</div>
      <div class="sources-bd">{src_rows}</div>
    </div>
  </section>
</main>
<script>
function flt(){{
  const q=document.getElementById('q').value.toLowerCase();
  const s=document.getElementById('src').value;
  const r=document.getElementById('rem').checked;
  let n=0;
  document.querySelectorAll('.card').forEach(c=>{{
    const t=c.innerText.toLowerCase();
    const ok=(!q||t.includes(q))&&(!s||c.dataset.source===s)&&(!r||c.dataset.remote==='1');
    c.style.display=ok?'flex':'none'; if(ok)n++;
  }});
  document.getElementById('cnt').textContent=n+' shown';
}}
function tab(name){{
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active', p.id==='panel-'+name));
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active', t.dataset.tab===name));
}}
flt();
</script>
</body></html>"""
    Path(path).write_text(doc, encoding="utf-8")
