"""Build a concise, evidence-first HTML report from the historical object pilot."""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


def table_html(df: pd.DataFrame, columns):
    if df.empty:
        return "<p><em>No records available.</em></p>"
    view = df[[c for c in columns if c in df.columns]].copy()
    return view.to_html(index=False, border=0, classes="data")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--positive", required=True)
    p.add_argument("--null", required=True)
    p.add_argument("--positive-tracks", required=True)
    p.add_argument("--null-tracks", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    pos = pd.read_csv(args.positive)
    null = pd.read_csv(args.null)
    pos_tracks = pd.read_csv(args.positive_tracks)
    null_tracks = pd.read_csv(args.null_tracks)

    def nuniq(frame, col):
        return int(frame[col].nunique(dropna=True)) if col in frame else 0

    label_counts = (
        pos["label_status"].value_counts(dropna=False).rename_axis("status")
        .reset_index(name="records")
        if "label_status" in pos.columns else pd.DataFrame()
    )
    env_counts = (
        pos["environment_status"].value_counts(dropna=False).rename_axis("status")
        .reset_index(name="records")
        if "environment_status" in pos.columns else pd.DataFrame()
    )
    null_env = (
        null["environment_status"].value_counts(dropna=False).rename_axis("status")
        .reset_index(name="records")
        if "environment_status" in null.columns else pd.DataFrame()
    )

    rows = []
    for name, frame in [("Verified-case context", pos), ("Winter null candidates", null)]:
        rows.append(
            f"<tr><td>{name}</td><td>{len(frame):,}</td>"
            f"<td>{nuniq(frame, 'object_id'):,}</td>"
            f"<td>{nuniq(frame, 'radar_site'):,}</td></tr>"
        )

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BTV Snow Squall — Historical Object Pilot</title>
<style>
body{{font-family:Arial,sans-serif;background:#f4f6f8;color:#17202a;margin:0}}
header{{background:#12344d;color:white;padding:28px 34px}}
h1{{margin:0 0 6px;font-size:30px}} h2{{margin-top:30px}}
main{{max-width:1200px;margin:24px auto;padding:0 20px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
.card{{background:white;border-radius:10px;padding:18px;box-shadow:0 1px 4px #0002}}
.card b{{display:block;font-size:28px;margin-top:5px}}
.data{{border-collapse:collapse;width:100%;background:white}}
.data th,.data td{{padding:9px;border-bottom:1px solid #ddd;text-align:left}}
.data th{{background:#e9eef2}}
.note{{background:#fff7df;border-left:5px solid #d59b00;padding:14px}}
.small{{color:#5d6872;font-size:13px}}
@media(max-width:800px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head>
<body>
<header><h1>BTV Snow Squall — Historical Object Pilot</h1>
<div>Real NEXRAD Level-II object reconstruction • research/pilot dataset • not an operational probability model</div></header>
<main>
<div class="grid">
<div class="card">Positive-context scans<b>{len(pos):,}</b></div>
<div class="card">Positive-context tracks<b>{len(pos_tracks):,}</b></div>
<div class="card">Null-candidate scans<b>{len(null):,}</b></div>
<div class="card">Null-candidate tracks<b>{len(null_tracks):,}</b></div>
</div>

<h2>What this pilot demonstrates</h2>
<p>This pilot converts archived Level-II radar volumes into geographic, trackable precipitation objects and attaches time-matched environmental information where available. The positive population represents verified historical case context; the winter-null population remains explicitly <strong>candidate</strong> until event/object quality control is complete.</p>

<h2>Population</h2>
<table class="data"><thead><tr><th>Population</th><th>Object scans</th><th>Unique objects</th><th>Radars</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>

<h2>Positive-context label status</h2>
{table_html(label_counts, ["status","records"])}

<h2>Environmental data availability</h2>
<h3>Positive-context objects</h3>
{table_html(env_counts, ["status","records"])}
<h3>Null candidates</h3>
{table_html(null_env, ["status","records"])}

<h2>Radar/object characteristics</h2>
{table_html(pos.describe(include="all").transpose().reset_index().rename(columns={"index":"field"}).head(20), ["field","count","mean","min","25%","50%","75%","max"])}

<h2>Archive/data-quality note</h2>
<div class="note">
The five-window null pilot contains one archive gap: NULL0002 (8 February 2006) returned zero Level-II volumes from both KCXX and KTYX. This is <strong>not</strong> treated as a meteorological null. NOAA's NEXRAD inventory lists KCXX Level-II coverage beginning in 1997, so the missing window requires archive-source investigation before it is retained as a valid null sample.
</div>

<h2>Scientific guardrails</h2>
<ul>
<li>Future-information policy: past and current information only.</li>
<li>Null candidates are not treated as verified negative examples.</li>
<li>Environmental provider is date-aware: RUC for the pre-RAP historical period and RAP after the transition.</li>
<li>Object association labels are pilot labels and require tighter track/event QC before model training.</li>
</ul>
<p class="small">Generated automatically from the workflow artifacts. Use this report to review the data pipeline with the SOO; do not interpret the current population as a trained forecast model.</p>
</main></body></html>"""

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote pilot report to {out}")


if __name__ == "__main__":
    main()
