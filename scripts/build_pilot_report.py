"""Build a concise, evidence-first HTML report from the historical object pilot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def table_html(df: pd.DataFrame, columns):
    if df.empty:
        return "<p><em>No records available.</em></p>"
    view = df[[c for c in columns if c in df.columns]].copy()
    return view.to_html(index=False, border=0, classes="data")


def load_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--positive", required=True)
    p.add_argument("--null", required=True)
    p.add_argument("--positive-tracks", required=True)
    p.add_argument("--null-tracks", required=True)
    p.add_argument("--surface-audit")
    p.add_argument("--surface-summary")
    p.add_argument("--positive-radar-audit")
    p.add_argument("--null-radar-audit")
    p.add_argument("--baseline-root")
    p.add_argument("--coverage")
    p.add_argument("--positive-level2-fields")
    p.add_argument("--null-level2-fields")
    p.add_argument("--output", required=True)
    args = p.parse_args()

    pos = pd.read_csv(args.positive)
    null = pd.read_csv(args.null)
    pos_tracks = pd.read_csv(args.positive_tracks)
    null_tracks = pd.read_csv(args.null_tracks)

    def nuniq(frame, col):
        return int(frame[col].nunique(dropna=True)) if col in frame else 0

    label_counts = (
        pos["label_status"].value_counts(dropna=False).rename_axis("status").reset_index(name="records")
        if "label_status" in pos.columns else pd.DataFrame()
    )
    env_counts = (
        pos["environment_status"].value_counts(dropna=False).rename_axis("status").reset_index(name="records")
        if "environment_status" in pos.columns else pd.DataFrame()
    )
    null_env = (
        null["environment_status"].value_counts(dropna=False).rename_axis("status").reset_index(name="records")
        if "environment_status" in null.columns else pd.DataFrame()
    )

    population_rows = []
    for name, frame in [("Verified-case context", pos), ("Winter null candidates", null)]:
        population_rows.append(
            f"<tr><td>{name}</td><td>{len(frame):,}</td>"
            f"<td>{nuniq(frame, 'object_id'):,}</td>"
            f"<td>{nuniq(frame, 'radar_site'):,}</td></tr>"
        )

    surface_section = "<p><em>Surface-observation audit not supplied.</em></p>"
    if args.surface_audit and Path(args.surface_audit).exists():
        surface = pd.read_csv(args.surface_audit)
        cols = [
            "case_id", "station", "status", "observation_count",
            "minimum_visibility_m", "maximum_peak_wind_gust_kt",
            "first_le_0p4km_utc", "first_le_0p8km_utc",
            "offset_from_published_start_0p4km_min",
            "offset_from_published_start_0p8km_min",
            "surface_timing_consistent",
        ]
        surface_section = table_html(surface, cols)

    radar_sections = []
    for label, path in [
        ("Positive reconstruction", args.positive_radar_audit),
        ("Null reconstruction", args.null_radar_audit),
    ]:
        if path:
            data = load_json(Path(path))
            if data:
                backend_rows = [
                    {"reader_backend": k, "volumes": v}
                    for k, v in data.get("reader_backend_volume_counts", {}).items()
                ]
                radar_sections.append(
                    f"<h3>{label}</h3>"
                    f"<p>Object records: <strong>{data.get('object_records', 0):,}</strong> · "
                    f"failed volumes: <strong>{data.get('failed_volumes', 0):,}</strong></p>"
                    f"{table_html(pd.DataFrame(backend_rows), ['reader_backend','volumes'])}"
                )
    radar_section = "".join(radar_sections) or "<p><em>No reconstruction audit supplied.</em></p>"

    field_section = "<p><em>Native Level-II field audit not supplied.</em></p>"
    field_rows = []
    for label, path in [
        ("Positive Level-II sample", args.positive_level2_fields),
        ("Null Level-II sample", args.null_level2_fields),
    ]:
        if path:
            data = load_json(Path(path))
            resolved = data.get("resolved_field_counts", {})
            if data:
                field_rows.append({
                    "sample": label,
                    "files_sampled": data.get("sampled_files", 0),
                    "successful_reads": data.get("successful_reads", 0),
                    "failed_reads": data.get("failed_reads", 0),
                    "reflectivity": resolved.get("reflectivity", 0),
                    "velocity": resolved.get("velocity", 0),
                    "zdr": resolved.get("zdr", 0),
                    "rhohv": resolved.get("rhohv", 0),
                    "kdp": resolved.get("kdp", 0),
                })
    if field_rows:
        field_section = table_html(
            pd.DataFrame(field_rows),
            ["sample", "files_sampled", "successful_reads", "failed_reads",
             "reflectivity", "velocity", "zdr", "rhohv", "kdp"],
        )
    coverage_section = "<p><em>Feature coverage audit not supplied.</em></p>"
    if args.coverage and Path(args.coverage).exists():
        coverage = load_json(Path(args.coverage))
        group_rows = coverage.get("group_coverage", [])
        coverage_section = table_html(
            pd.DataFrame(group_rows),
            ["group", "fields_with_values", "fields_present", "fields", "mean_field_coverage_pct"],
        )
        zero = coverage.get("zero_coverage_fields", [])
        coverage_section += (
            f"<p class=\"small\">Zero-coverage schema fields: "
            f"<strong>{len(zero)}</strong>.</p>"
        )

    baseline_section = "<p><em>Baseline model metrics not supplied.</em></p>"
    if args.baseline_root:
        baseline_rows = []
        root = Path(args.baseline_root)
        baseline_paths = sorted(
            list(root.glob("baseline_model_*m/metrics.json"))
            + list(root.glob("baseline_expansion_*m/metrics.json"))
        )
        for path in baseline_paths:
            data = load_json(path)
            metrics = data.get("metrics", {})
            folder = path.parent.name
            horizon = folder.replace("baseline_model_", "").replace("baseline_expansion_", "")
            baseline_rows.append({
                "horizon": horizon,
                "training_rows": data.get("training_rows"),
                "groups": data.get("training_groups"),
                "positive_case_groups": data.get("positive_case_group_count"),
                "evaluation_status": data.get("evaluation_status"),
                "ROC_AUC": metrics.get("auc_roc"),
                "Average_Precision": metrics.get("average_precision"),
                "Brier": metrics.get("brier_score"),
                "Climatology_Brier": (metrics.get("climatology") or {}).get("brier_score"),
            })
        baseline_df = pd.DataFrame(baseline_rows)
        baseline_section = table_html(baseline_df, [
            "horizon", "training_rows", "groups", "positive_case_groups",
            "evaluation_status", "ROC_AUC", "Average_Precision", "Brier",
            "Climatology_Brier",
        ])
        not_ready = baseline_df[
            baseline_df.get("evaluation_status", pd.Series(dtype=str)).eq(
                "case_held_out_not_interpretable"
            )
        ] if not baseline_df.empty else pd.DataFrame()
        if not not_ready.empty:
            baseline_section += (
                '<div class="note"><strong>Baseline readiness warning:</strong> '
                'fewer than three independent historical case groups contain positive '
                'forecast labels. The displayed holdout metrics are not scientifically '
                'interpretable as model skill yet.</div>'
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
<div>Real NEXRAD Level-II object reconstruction • multi-era environment enrichment • independent surface-observation audit • research/pilot dataset • not an operational probability model</div></header>
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
<tbody>{''.join(population_rows)}</tbody></table>

<h2>Positive-context label status</h2>
{table_html(label_counts, ["status","records"])}

<h2>Independent ASOS/METAR surface audit</h2>
{surface_section}

<h2>Environmental data availability</h2>
<h3>Positive-context objects</h3>
{table_html(env_counts, ["status","records"])}
<h3>Null candidates</h3>
{table_html(null_env, ["status","records"])}

<h2>Radar reconstruction audit</h2>
{radar_section}

<h2>Realized feature coverage</h2>
{coverage_section}

<h2>Native Level-II field availability</h2>
{field_section}

<h2>Case-held-out baseline model</h2>
{baseline_section}

<h2>Radar/object characteristics</h2>
{table_html(pos.describe(include="all").transpose().reset_index().rename(columns={"index":"field"}).head(20), ["field","count","mean","min","25%","50%","75%","max"])}

<h2>Scientific guardrails</h2>
<div class="note">
This report deliberately separates verified event context from candidate nulls. Future-information policy is current-and-past only at prediction time. Post-onset observations are excluded from the first baseline training set. Model metrics are exploratory and case-held-out; they are not an operational verification of forecast skill.
</div>
<ul>
<li>Environmental provider is date-aware: NARR before 1 April 2007, RUC from 1 April 2007 through 30 April 2012, and RAP from 1 May 2012 onward.</li>
<li>Object association labels are pilot labels and require tighter track/event QC before model training at scale.</li>
<li>ASOS/METAR surface observations are currently an independent truth/QC layer, not a model predictor.</li>
</ul>
<p class="small">Generated automatically from the workflow artifacts. Use this report to review the data pipeline with the SOO; do not interpret the current population as a trained operational forecast model.</p>
</main></body></html>"""

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote pilot report to {out}")


if __name__ == "__main__":
    main()
