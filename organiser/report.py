"""HTML run report: what was filed where, and why."""
from __future__ import annotations

import html
from collections import Counter
from pathlib import Path

CSS = """
.viz-root{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#e6e5e1;--tile:#f3f2ef;color-scheme:light}
@media (prefers-color-scheme: dark){.viz-root{--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--line:#383835;
--tile:#242422;color-scheme:dark}}
body{margin:0;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif}
.viz-root{background:var(--surface);color:var(--ink);min-height:100vh;padding:24px 32px}
h1{font-size:23px;margin:0}h2{font-size:17px;margin:26px 0 10px}.sub{color:var(--ink2);margin:4px 0 0}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:18px 0}
.kpi{background:var(--tile);border-radius:8px;padding:12px 14px}.kpi b{font-size:26px;display:block}
.kpi span{color:var(--ink2);font-size:13px}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--line);
text-align:left;vertical-align:top}th{color:var(--ink2);font-weight:600}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600;color:#0b0b0b}
.high{background:#cfe3cf}.medium{background:#dbe7f7}.review{background:#fab219}.dup{background:#e6e5e1}.skip{background:#e6e5e1}
"""


def build_report(result: dict, path: Path) -> Path:
    rows = result["rows"]
    e = html.escape
    filed = [r for r in rows if r["status"] in ("saved", "would save")]
    review = [r for r in filed if r["country"] == "_Needs_Review"]
    dups = [r for r in rows if r["status"] == "duplicate"]
    skipped = [r for r in rows if r["status"] == "skipped"]
    grid = Counter((r["country"], r["data_type"]) for r in filed)
    types = sorted({t for _, t in grid})
    countries = sorted({c for c, _ in grid}, key=lambda c: (c == "_Needs_Review", c))
    head = "".join(f"<th class='n'>{e(t)}</th>" for t in types)
    body = "".join(
        f"<tr><td>{e(c)}</td>" + "".join(f"<td class='n'>{grid.get((c, t), '') or ''}</td>"
                                         for t in types)
        + f"<td class='n'><b>{sum(grid.get((c, t), 0) for t in types)}</b></td></tr>"
        for c in countries)
    tiles = [(result["counts"]["messages scanned"], "messages scanned"),
             (result["counts"]["messages processed"], "messages with data"),
             (len(filed) - len(review), "files filed by country"),
             (len(review), "files to review"), (len(dups), "duplicates not saved")]
    kpis = "".join(f'<div class="kpi"><b>{v}</b><span>{lab}</span></div>' for v, lab in tiles)

    def cls(r):
        return {"duplicate": "dup", "skipped": "skip"}.get(r["status"], r["confidence"])

    detail = "".join(
        f"<tr><td><span class='tag {cls(r)}'>{e(r['status'] if r['status'] in ('duplicate', 'skipped') else r['confidence'])}</span></td>"
        f"<td>{e(r['attachment'])}</td><td>{e(r['country'])}</td><td>{e(r['data_type'])}</td>"
        f"<td>{e(r['reason'])}</td><td>{e(r['sender'])}<br><span class='sub'>{e(r['subject'])}</span></td></tr>"
        for r in rows)
    mode = " (dry run: nothing saved)" if result["dry_run"] else ""
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Inbox organiser run {e(result['run'])}</title>
<style>{CSS}</style></head><body><div class="viz-root">
<h1>Inbox organiser - run of {e(result['run'])}{mode}</h1>
<p class="sub">Output folder: {e(str(result['root']))} · {len(skipped)} signature images skipped ·
{result['counts'].get('skipped: not sent to a target address', 0)} messages not sent to a target address</p>
<div class="kpis">{kpis}</div>
<h2>Files filed, by country and data type</h2>
<table><thead><tr><th>Country</th>{head}<th class='n'>Total</th></tr></thead><tbody>{body}</tbody></table>
<h2>Every attachment and the reason for its folder</h2>
<table><thead><tr><th>Decision</th><th>Attachment</th><th>Country</th><th>Type</th><th>Reason</th>
<th>From / subject</th></tr></thead><tbody>{detail}</tbody></table>
</div></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path
