"""Create and validate the human-review packet for hard-negative null windows.

This module deliberately separates:
    candidate -> review -> reviewed_negative / contaminated_unknown

No row is promoted to training merely because it has a high hard-negative score.
Training eligibility is derived only from explicit human review fields.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


REVIEW_STATUSES = {"pending", "reviewed"}
FINAL_CLASSES = {
    "pending",
    "reviewed_negative",
    "contaminated_unknown",
    "retain_candidate",
}
EVIDENCE_VALUES = {"yes", "no", "unknown"}


def _clean_text(series: pd.Series, default: str = "") -> pd.Series:
    return series.fillna(default).astype(str).str.strip()


def build_packet(
    queue: pd.DataFrame,
    existing_review: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if "null_id" not in queue.columns:
        raise ValueError("Hard-negative queue must contain null_id")

    d = queue.copy()
    d["null_id"] = _clean_text(d["null_id"])
    d = d[d["null_id"].ne("")].drop_duplicates("null_id").copy()
    if "review_recommended" in d.columns:
        d = d[d["review_recommended"].fillna(False).astype(bool)].copy()

    existing = None
    if existing_review is not None and not existing_review.empty:
        if "null_id" not in existing_review.columns:
            raise ValueError("Existing review file must contain null_id")
        existing = existing_review.copy()
        existing["null_id"] = _clean_text(existing["null_id"])
        existing = existing[existing["null_id"].ne("")].drop_duplicates("null_id", keep="last")
        review_lookup = existing.set_index("null_id")
        protected = [
            c for c in (
                "review_status", "final_class", "radar_target_present",
                "event_evidence_present", "surface_evidence_interpreted",
                "reviewer", "reviewed_at_utc", "review_notes"
            ) if c in existing.columns
        ]
        for col in protected:
            mapped = d["null_id"].map(review_lookup[col])
            if col not in d.columns:
                d[col] = mapped
            else:
                current = d[col]
                missing = current.isna() | current.astype(str).str.strip().eq("")
                d.loc[missing, col] = mapped.loc[missing]

        # Preserve previously reviewed windows even when they are no longer in
        # the current diagnostic candidate set.
        existing_ids = set(existing["null_id"])
        current_ids = set(d["null_id"])
        missing_ids = sorted(existing_ids - current_ids)
        if missing_ids:
            carry = existing[existing["null_id"].isin(missing_ids)].copy()
            d = pd.concat([d, carry], ignore_index=True, sort=False)
    defaults = {
        "review_status": "pending",
        "final_class": "pending",
        "radar_target_present": "unknown",
        "event_evidence_present": "unknown",
        "surface_evidence_interpreted": "unknown",
        "reviewer": "",
        "reviewed_at_utc": "",
        "review_notes": "",
    }
    for col, default in defaults.items():
        if col not in d.columns:
            d[col] = default
        d[col] = _clean_text(d[col], default)

    d["training_eligible"] = False
    d["promotion_status"] = "not_promoted"
    d["promotion_reason"] = ""

    reviewed = d["review_status"].eq("reviewed")
    complete_review = (
        reviewed
        & d["final_class"].isin(FINAL_CLASSES - {"pending"})
        & d["radar_target_present"].isin({"yes", "no"})
        & d["event_evidence_present"].isin({"yes", "no"})
        & d["surface_evidence_interpreted"].isin({"yes", "no"})
        & d["reviewer"].ne("")
        & d["reviewed_at_utc"].ne("")
    )
    promotable = (
        complete_review
        & d["final_class"].eq("reviewed_negative")
        & d["radar_target_present"].eq("no")
        & d["event_evidence_present"].eq("no")
    )
    d.loc[complete_review & ~promotable, "promotion_status"] = "reviewed_not_promotable"
    d.loc[complete_review & ~promotable, "promotion_reason"] = (
        "review_completed_but_not_a_verified_hard_negative"
    )
    d.loc[promotable, "training_eligible"] = True
    d.loc[promotable, "promotion_status"] = "training_negative"
    d.loc[promotable, "promotion_reason"] = (
        "human_review_confirmed_no_target_and_no_event_evidence"
    )

    d["review_policy"] = (
        "human_review_required;score_is_diagnostic;training_eligibility_is_derived"
    )
    d["review_schema_version"] = "hard_negative_review_v1"

    sort_cols = [
        c for c in (
            "training_eligible", "review_status", "hard_negative_score",
            "max_reflectivity_dbz", "null_id"
        ) if c in d.columns
    ]
    ascending = [False, True, False, False, True][:len(sort_cols)]
    return d.sort_values(sort_cols, ascending=ascending, na_position="last").reset_index(drop=True)


def validate_packet(packet: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    required = {
        "null_id", "review_status", "final_class",
        "radar_target_present", "event_evidence_present",
        "reviewer", "reviewed_at_utc", "training_eligible",
    }
    missing = sorted(required - set(packet.columns))
    if missing:
        errors.append(f"Missing review columns: {missing}")
        return errors

    for idx, row in packet.iterrows():
        status = str(row["review_status"])
        final_class = str(row["final_class"])
        radar = str(row["radar_target_present"])
        event = str(row["event_evidence_present"])
        if status not in REVIEW_STATUSES:
            errors.append(f"row {idx}: invalid review_status={status!r}")
        if final_class not in FINAL_CLASSES:
            errors.append(f"row {idx}: invalid final_class={final_class!r}")
        if radar not in EVIDENCE_VALUES:
            errors.append(f"row {idx}: invalid radar_target_present={radar!r}")
        if event not in EVIDENCE_VALUES:
            errors.append(f"row {idx}: invalid event_evidence_present={event!r}")

        eligible = bool(row["training_eligible"])
        should_be_eligible = (
            status == "reviewed"
            and final_class == "reviewed_negative"
            and radar == "no"
            and event == "no"
            and str(row["surface_evidence_interpreted"]).strip() in {"yes", "no"}
            and str(row["reviewer"]).strip() != ""
            and str(row["reviewed_at_utc"]).strip() != ""
        )
        if eligible != should_be_eligible:
            errors.append(
                f"row {idx}: training_eligible must be derived from a complete "
                f"reviewed_negative decision, not manually asserted"
            )
        if status == "pending" and eligible:
            errors.append(f"row {idx}: pending review cannot be training eligible")
    return errors


def build_promoted_manifest(packet: pd.DataFrame) -> pd.DataFrame:
    errors = validate_packet(packet)
    if errors:
        raise ValueError("Invalid review packet:\n" + "\n".join(errors))

    promoted = packet.loc[packet["training_eligible"]].copy()
    if promoted.empty:
        return pd.DataFrame(columns=[
            "null_id", "peak_object_id", "peak_scan_time_utc", "peak_radar_site",
            "hard_negative_score", "radars", "reviewer", "reviewed_at_utc",
            "review_notes", "negative_truth_status", "promotion_reason",
        ])

    columns = [
        "null_id", "peak_object_id", "peak_scan_time_utc", "peak_radar_site",
        "hard_negative_score", "radars", "reviewer", "reviewed_at_utc",
        "review_notes", "promotion_reason",
    ]
    out = promoted[[c for c in columns if c in promoted.columns]].copy()
    out["negative_truth_status"] = "reviewed_negative"
    out["promotion_reason"] = (
        out.get("promotion_reason", pd.Series(
            "human_review_confirmed_no_target_and_no_event_evidence",
            index=out.index,
        ))
    )
    return out


def summary(packet: pd.DataFrame, promoted: pd.DataFrame) -> dict:
    return {
        "review_schema_version": "hard_negative_review_v1",
        "queue_rows": int(len(packet)),
        "pending": int(packet["review_status"].eq("pending").sum()),
        "reviewed": int(packet["review_status"].eq("reviewed").sum()),
        "reviewed_negative": int(packet["final_class"].eq("reviewed_negative").sum()),
        "contaminated_unknown": int(packet["final_class"].eq("contaminated_unknown").sum()),
        "retain_candidate": int(packet["final_class"].eq("retain_candidate").sum()),
        "training_negative_windows": int(len(promoted)),
        "policy": (
            "hard_negative_score_only_prioritizes_review; explicit_human_review "
            "is required before promotion to training negative"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--promoted-output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument(
        "--existing-review",
        default=None,
        help="Optional prior review packet; decisions are preserved by null_id.",
    )
    args = parser.parse_args()

    queue = pd.read_csv(args.queue)
    existing = pd.read_csv(args.existing_review) if args.existing_review else None
    packet = build_packet(queue, existing_review=existing)
    errors = validate_packet(packet)
    if errors:
        raise SystemExit("Invalid generated review packet:\n" + "\n".join(errors))

    promoted = build_promoted_manifest(packet)

    output = Path(args.output)
    promoted_output = Path(args.promoted_output)
    summary_output = Path(args.summary)
    for path in (output, promoted_output, summary_output):
        path.parent.mkdir(parents=True, exist_ok=True)

    packet.to_csv(output, index=False)
    promoted.to_csv(promoted_output, index=False)
    summary_output.write_text(json.dumps(summary(packet, promoted), indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary(packet, promoted), indent=2))
    print(f"Wrote review packet: {output}")
    print(f"Wrote promoted training-negative manifest: {promoted_output}")


if __name__ == "__main__":
    main()
