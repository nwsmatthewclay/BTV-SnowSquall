"""Score candidate probabilities at the event/track level.

This turns scan-level OOF probabilities into operationally meaningful diagnostics:
probability threshold crossings, event hit rate, null-window false-alert rate,
false-alarm ratio, and lead time. It does not choose an operational threshold.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

HORIZONS = (15, 30, 45, 60)
THRESHOLDS = (0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80)


def apply_calibration(model_dir: Path, probabilities: pd.Series) -> tuple[pd.Series, str]:
    path = model_dir / "probability_calibrator.joblib"
    if not path.exists():
        return probabilities, "raw_oof_probability"
    calibrator = joblib.load(path)
    p = pd.to_numeric(probabilities, errors="coerce").clip(1e-6, 1 - 1e-6)
    logits = np.log(p / (1.0 - p)).to_numpy().reshape(-1, 1)
    calibrated = calibrator.predict_proba(logits)[:, 1]
    return pd.Series(calibrated, index=probabilities.index), "platt_calibrated_oof_probability"


def event_groups(predictions: pd.DataFrame) -> pd.DataFrame:
    p = predictions.copy()
    p["scan_time_utc"] = pd.to_datetime(p["scan_time_utc"], utc=True, errors="coerce")
    p["oof_probability"] = pd.to_numeric(p["oof_probability"], errors="coerce")
    p = p[p["scan_time_utc"].notna() & p["oof_probability"].notna()].copy()

    # A positive historical event is represented at case level so multiple
    # radar objects/tracks inside the same documented case cannot create
    # multiple "hits". Null windows remain independent event candidates.
    p["event_group"] = np.where(
        p["population"].eq("verified_case_context"),
        "case:" + p["case_id"].fillna("").astype(str),
        "null:" + p["null_id"].fillna("").astype(str),
    )
    return p


def build_case_table(pred: pd.DataFrame, cases: pd.DataFrame, probability_col: str) -> pd.DataFrame:
    cases = cases.copy()
    cases["event_start_dt"] = pd.to_datetime(cases["event_start_utc"], utc=True, errors="coerce")
    case_starts = cases[["case_id", "event_start_dt"]].drop_duplicates("case_id")

    positive = pred[pred["population"].eq("verified_case_context")].copy()
    if not positive.empty:
        positive = positive.merge(case_starts, on="case_id", how="left", validate="many_to_one")
        positive = positive[positive["event_start_dt"].notna()].copy()
        positive = positive[
            positive["scan_time_utc"] < positive["event_start_dt"]
        ].copy()

    rows = []
    for case_id, g in positive.groupby("case_id", dropna=True):
        idx = g[probability_col].idxmax()
        max_row = g.loc[idx]
        rows.append({
            "event_type": "positive_case",
            "event_id": str(case_id),
            "group_count": int(g["split_group"].nunique()),
            "scan_count": int(len(g)),
            "max_probability": float(g[probability_col].max()),
            "max_probability_time_utc": max_row["scan_time_utc"].isoformat(),
            "event_start_utc": max_row["event_start_dt"].isoformat(),
        })

    nulls = pred[pred["population"].eq("winter_null_candidate")].copy()
    for null_id, g in nulls.groupby("null_id", dropna=True):
        idx = g[probability_col].idxmax()
        max_row = g.loc[idx]
        rows.append({
            "event_type": "null_window",
            "event_id": str(null_id),
            "group_count": int(g["split_group"].nunique()),
            "scan_count": int(len(g)),
            "max_probability": float(g[probability_col].max()),
            "max_probability_time_utc": max_row["scan_time_utc"].isoformat(),
            "event_start_utc": None,
        })
    return pd.DataFrame(rows)


def threshold_metrics(table: pd.DataFrame, predictions: pd.DataFrame, probability_col: str) -> pd.DataFrame:
    positives = table[table["event_type"].eq("positive_case")]
    nulls = table[table["event_type"].eq("null_window")]
    rows = []

    for threshold in THRESHOLDS:
        positive_hits = positives["max_probability"].ge(threshold)
        null_hits = nulls["max_probability"].ge(threshold)

        hit_ids = set(positives.loc[positive_hits, "event_id"])
        false_ids = set(nulls.loc[null_hits, "event_id"])

        lead_times = []
        raw_positive = predictions[
            predictions["population"].eq("verified_case_context")
        ].copy()
        if not raw_positive.empty:
            # Case-level first crossing gives event-level lead time. Once a case
            # crosses, later scans do not increase the reported lead.
            raw_positive = raw_positive.copy()
            if "_event_start_dt" in raw_positive:
                starts = raw_positive["_event_start_dt"]
            else:
                starts = pd.NaT
            for case_id, g in raw_positive.groupby("case_id", dropna=True):
                start = g["_event_start_dt"].iloc[0] if "_event_start_dt" in g else pd.NaT
                if pd.isna(start):
                    continue
                crossings = g[
                    (g[probability_col] >= threshold)
                    & (g["scan_time_utc"] < start)
                ]
                if not crossings.empty:
                    first = crossings["scan_time_utc"].min()
                    lead_times.append((start - first).total_seconds() / 60.0)

        positive_count = int(len(positives))
        null_count = int(len(nulls))
        hits = int(len(hit_ids))
        false_alerts = int(len(false_ids))
        event_total = hits + false_alerts
        rows.append({
            "threshold": threshold,
            "positive_cases": positive_count,
            "positive_hits": hits,
            "pod": hits / positive_count if positive_count else None,
            "null_windows": null_count,
            "false_alert_windows": false_alerts,
            "false_alert_rate": false_alerts / null_count if null_count else None,
            "false_alarm_ratio": false_alerts / event_total if event_total else None,
            "median_lead_min": float(np.median(lead_times)) if lead_times else None,
            "mean_lead_min": float(np.mean(lead_times)) if lead_times else None,
            "lead_case_count": len(lead_times),
        })

    return pd.DataFrame(rows)


def score_horizon(features: pd.DataFrame, predictions_path: Path, cases: pd.DataFrame, model_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    pred = pd.read_csv(predictions_path)
    required = {"population", "case_id", "null_id", "split_group", "scan_time_utc", "oof_probability"}
    missing = sorted(required - set(pred.columns))
    if missing:
        raise ValueError(f"OOF predictions missing columns: {missing}")

    pred["scan_time_utc"] = pd.to_datetime(pred["scan_time_utc"], utc=True, errors="coerce")
    probability, probability_source = apply_calibration(model_dir, pred["oof_probability"])
    pred["probability"] = probability

    cases = cases.copy()
    cases["event_start_dt"] = pd.to_datetime(cases["event_start_utc"], utc=True, errors="coerce")
    starts = cases[["case_id", "event_start_dt"]].drop_duplicates("case_id")
    pred = pred.merge(starts, on="case_id", how="left", validate="many_to_one")

    pred_groups = event_groups(pred)
    # Replace event-level grouping below with case/null event IDs while retaining
    # split_group for diagnostics.
    table = build_case_table(pred_groups, cases, "probability")
    metrics = threshold_metrics(table, pred.assign(_event_start_dt=pred["event_start_dt"]), "probability")
    metrics["probability_source"] = probability_source
    return table, metrics, {
        "probability_source": probability_source,
        "prediction_rows": int(len(pred)),
        "evaluated_positive_cases": int((table["event_type"] == "positive_case").sum()),
        "evaluated_null_windows": int((table["event_type"] == "null_window").sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", required=True, help="Cumulative feature CSV; retained for provenance.")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--prefix", default="candidate_ensemble_expansion_")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    features = pd.read_csv(args.features)
    cases = pd.read_csv(args.cases)
    model_root = Path(args.model_root)

    summary = {
        "version": "event-verification-v1",
        "dataset": str(args.features),
        "cases": str(args.cases),
        "thresholds": list(THRESHOLDS),
        "horizons": {},
    }

    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)

    for h in HORIZONS:
        model_dir = model_root / f"{args.prefix}{h}m"
        pred_path = model_dir / "oof_predictions.csv"
        if not pred_path.exists():
            summary["horizons"][str(h)] = {"status": "missing_oof_predictions"}
            continue
        table, metrics, diag = score_horizon(
            features,
            pred_path,
            cases,
            model_dir,
        )
        table.to_csv(output_root / f"event_table_{h}m.csv", index=False)
        metrics.to_csv(output_root / f"thresholds_{h}m.csv", index=False)
        summary["horizons"][str(h)] = {
            "status": "ok",
            **diag,
            "thresholds": metrics.to_dict("records"),
        }

    (output_root / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
