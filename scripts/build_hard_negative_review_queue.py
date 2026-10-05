"""Build a review queue of challenging historical null-window objects.

Hard-negative candidates are intentionally *not* converted into supervised
negative truth. They are objects that look sufficiently vigorous or organized
that a future reviewer should inspect them before they enter clean training.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def numeric(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(
        df[col], errors="coerce"
    ) if col in df.columns else pd.Series(float("nan"), index=df.index)


def build(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = frame.copy()
    nulls = d[d["population"].eq("winter_null_candidate")].copy()
    if nulls.empty:
        return (
            pd.DataFrame(columns=["null_id"]),
            pd.DataFrame(
                [{"status": "empty_null_population", "candidate_rows": 0}]
            ),
        )

    d["max_reflectivity_dbz"] = numeric(d, "max_reflectivity_dbz")
    base_max = numeric(d, "base_reflectivity_max_dbz")
    d["base_reflectivity_max_dbz"] = base_max
    d["core_pixel_count"] = numeric(d, "core_pixel_count")
    d["velocity_p90_abs_kt"] = numeric(d, "velocity_p90_abs_kt")
    d["base_velocity_p90_abs_kt"] = numeric(d, "base_velocity_p90_abs_kt")
    d["area_km2"] = numeric(d, "area_km2")
    d["track_scan_count_to_date"] = numeric(d, "track_scan_count_to_date")
    d["environment_contract_ok"] = (
        d["environment_contract_ok"].fillna(False).astype(bool)
        if "environment_contract_ok" in d.columns
        else False
    )

    rows = []
    for null_id, g in nulls.groupby("null_id", dropna=True):
        score = 0
        reasons = []

        max_z = pd.concat(
            [numeric(g, "max_reflectivity_dbz"), numeric(g, "base_reflectivity_max_dbz")]
        ).max()
        max_core = numeric(g, "core_pixel_count").max()
        max_vel = pd.concat(
            [numeric(g, "velocity_p90_abs_kt"), numeric(g, "base_velocity_p90_abs_kt")]
        ).max()
        max_area = numeric(g, "area_km2").max()
        max_scans = numeric(g, "track_scan_count_to_date").max()

        if pd.notna(max_z):
            if max_z >= 40:
                score += 2
                reasons.append("reflectivity_ge_40dbz")
            elif max_z >= 35:
                score += 1
                reasons.append("reflectivity_ge_35dbz")
        if pd.notna(max_core) and max_core > 0:
            score += 1
            reasons.append("convective_core_pixels_present")
        if pd.notna(max_vel) and max_vel >= 20:
            score += 1
            reasons.append("velocity_p90_abs_ge_20kt")
        if pd.notna(max_area) and max_area >= 100:
            score += 1
            reasons.append("object_area_ge_100km2")
        if pd.notna(max_scans) and max_scans >= 3:
            score += 1
            reasons.append("persistent_three_or_more_scans")

        activity = (
            str(g["activity_class"].dropna().iloc[0])
            if "activity_class" in g.columns and g["activity_class"].notna().any()
            else ""
        )

        rows.append({
            "null_id": str(null_id),
            "radars": ",".join(sorted(g["radar_site"].dropna().astype(str).unique())) if "radar_site" in g.columns else "",
            "scan_rows": int(len(g)),
            "max_reflectivity_dbz": float(max_z) if pd.notna(max_z) else None,
            "max_core_pixel_count": float(max_core) if pd.notna(max_core) else None,
            "max_velocity_p90_abs_kt": float(max_vel) if pd.notna(max_vel) else None,
            "max_area_km2": float(max_area) if pd.notna(max_area) else None,
            "max_track_scan_count_to_date": float(max_scans) if pd.notna(max_scans) else None,
            "environment_contract_fraction": float(g["environment_contract_ok"].mean()),
            "activity_class": activity,
            "hard_negative_score": int(score),
            "review_recommended": bool(score >= 3),
            "review_reasons": ";".join(reasons),
        })

    table = pd.DataFrame(rows).sort_values(
        ["review_recommended", "hard_negative_score", "max_reflectivity_dbz"],
        ascending=[False, False, False],
        na_position="last",
    )
    recommended = table[table["review_recommended"]].copy()

    summary = pd.DataFrame([{
        "status": "ok",
        "null_windows": int(len(table)),
        "review_candidates": int(len(recommended)),
        "candidate_fraction": round(float(len(recommended) / max(len(table), 1)), 4),
        "score_ge_4": int((table["hard_negative_score"] >= 4).sum()),
        "score_ge_3": int((table["hard_negative_score"] >= 3).sum()),
        "score_ge_2": int((table["hard_negative_score"] >= 2).sum()),
        "policy": "diagnostic_review_only; never automatic negative truth",
    }])
    return table, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("features")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    frame = pd.read_csv(args.features)
    required = {"population", "null_id"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SystemExit(f"Missing required columns: {missing}")

    table, summary = build(frame)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out.with_suffix(".csv"), index=False)
    summary.to_csv(out.with_suffix(".summary.csv"), index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
