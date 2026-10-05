"""Render a compact browser review board for hard-negative candidates.

The HTML is a read-only review aid. Decisions remain authoritative only in the
CSV review ledger and are revalidated by build_hard_negative_review_packet.py.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import pandas as pd


def esc(value) -> str:
    return html.escape("" if pd.isna(value) else str(value))


def build(packet: pd.DataFrame, output: Path) -> None:
    rows = packet.copy().fillna("")
    columns = [
        "null_id", "hard_negative_score", "review_status", "final_class",
        "radars", "peak_radar_site", "peak_scan_time_utc", "peak_object_id",
        "max_reflectivity_dbz", "max_velocity_p90_abs_kt", "max_area_km2",
        "max_track_scan_count_to_date", "surface_report_count",
        "surface_min_visibility_m", "surface_max_gust_kt", "surface_snow_reports",
        "environment_contract_fraction", "review_reasons", "review_notes",
    ]
    columns = [c for c in columns if c in rows.columns]

    body = []
    for _, row in rows.iterrows():
        risk = float(pd.to_numeric(pd.Series([row.get("hard_negative_score")]), errors="coerce").iloc[0]) if str(row.get("hard_negative_score", "")).strip() else 0.0
        cls = str(row.get("final_class", "pending"))
        body.append(
            "<tr data-score='{}' data-status='{}' data-class='{}'>".format(
                esc(row.get("hard_negative_score", "")),
                esc(row.get("review_status", "")),
                esc(cls),
            )
            + "".join(f"<td>{esc(row.get(c, ''))}</td>" for c in columns)
            + "</tr>"
        )

    headers = "".join(f"<th>{esc(c)}</th>" for c in columns)
    payload = {
        "rows": len(rows),
        "pending": int(rows.get("review_status", pd.Series(dtype="object")).eq("pending").sum()),
        "reviewed": int(rows.get("review_status", pd.Series(dtype="object")).eq("reviewed").sum()),
    }

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BTV Snow Squall Hard-Negative Review Board</title>
<style>
body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#0f1720;color:#e6edf3}}
header{{padding:18px 22px;border-bottom:1px solid #2a3947;position:sticky;top:0;background:#111b25;z-index:3}}
h1{{font-size:21px;margin:0 0 6px}}
.meta{{font-size:13px;color:#9fb0bf}}
.controls{{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}}
input,select{{background:#15222e;color:#e6edf3;border:1px solid #415262;border-radius:5px;padding:7px 9px}}
main{{padding:16px 22px}}
.badge{{display:inline-block;padding:3px 7px;border:1px solid #3b4a59;border-radius:999px;margin-right:6px;font-size:12px}}
.wrap{{overflow:auto;border:1px solid #2a3947;border-radius:7px}}
table{{border-collapse:collapse;min-width:1700px;width:100%;font-size:12px}}
th,td{{border-bottom:1px solid #263746;border-right:1px solid #22313e;padding:6px 8px;text-align:left;vertical-align:top;white-space:nowrap}}
th{{position:sticky;top:102px;background:#182531;z-index:2}}
tr:nth-child(even){{background:#121c25}}
tr:hover{{background:#1a2a38}}
.note{{margin:12px 0;color:#b6c4cf;font-size:12px;line-height:1.45}}
</style>
</head>
<body>
<header>
<h1>BTV Snow Squall Hard-Negative Review Board</h1>
<div class="meta">
<span class="badge">Rows: {payload["rows"]}</span>
<span class="badge">Pending: {payload["pending"]}</span>
<span class="badge">Reviewed: {payload["reviewed"]}</span>
</div>
<div class="controls">
<input id="search" placeholder="Search null/object/radar/reason…" oninput="filterRows()">
<select id="status" onchange="filterRows()">
<option value="">All review status</option>
<option value="pending">Pending</option>
<option value="reviewed">Reviewed</option>
</select>
<select id="class" onchange="filterRows()">
<option value="">All final classes</option>
<option value="pending">Pending</option>
<option value="reviewed_negative">Reviewed negative</option>
<option value="contaminated_unknown">Contaminated / unknown</option>
<option value="retain_candidate">Retain candidate</option>
</select>
</div>
</header>
<main>
<div class="note">
The score is a review-priority diagnostic, not truth. Actual training promotion occurs
only through the validated CSV review ledger and requires explicit radar, event, and
surface-evidence decisions plus reviewer/timestamp provenance.
</div>
<div class="wrap">
<table id="review">
<thead><tr>{headers}</tr></thead>
<tbody>{''.join(body)}</tbody>
</table>
</div>
</main>
<script>
function filterRows(){{
  const q=document.getElementById('search').value.toLowerCase();
  const s=document.getElementById('status').value;
  const c=document.getElementById('class').value;
  document.querySelectorAll('#review tbody tr').forEach(tr=>{{
    const text=tr.innerText.toLowerCase();
    const okQ=!q||text.includes(q);
    const okS=!s||tr.dataset.status===s;
    const okC=!c||tr.dataset.class===c;
    tr.style.display=(okQ&&okS&&okC)?'':'none';
  }});
}}
</script>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(pd.read_csv(args.packet), Path(args.output))
    print(f"Wrote review board: {args.output}")


if __name__ == "__main__":
    main()
