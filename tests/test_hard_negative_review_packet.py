import pandas as pd
import pytest

from scripts.build_hard_negative_review_packet import (
    build_packet,
    build_promoted_manifest,
    validate_packet,
)


def queue_frame():
    return pd.DataFrame({
        "null_id": ["N1", "N2"],
        "hard_negative_score": [7, 3],
        "peak_object_id": ["KCXX_001", "KTYX_002"],
        "peak_scan_time_utc": ["2026-01-01T00:30:00Z", "2026-01-02T00:30:00Z"],
        "peak_radar_site": ["KCXX", "KTYX"],
    })


def test_new_queue_rows_are_pending_and_not_training_eligible():
    packet = build_packet(queue_frame())

    assert set(packet["review_status"]) == {"pending"}
    assert not packet["training_eligible"].any()
    assert validate_packet(packet) == []


def test_only_explicit_human_review_promotes_negative():
    packet = build_packet(queue_frame())
    idx = packet.index[packet["null_id"].eq("N1")][0]

    packet.loc[idx, "review_status"] = "reviewed"
    packet.loc[idx, "final_class"] = "reviewed_negative"
    packet.loc[idx, "radar_target_present"] = "no"
    packet.loc[idx, "event_evidence_present"] = "no"
    packet.loc[idx, "surface_evidence_interpreted"] = "yes"
    packet.loc[idx, "reviewer"] = "forecaster"
    packet.loc[idx, "reviewed_at_utc"] = "2026-10-05T16:00:00Z"
    packet.loc[idx, "review_notes"] = "Radar review found no target object; event archives checked; surface evidence interpreted."
    packet = build_packet(packet)

    row = packet.loc[packet["null_id"].eq("N1")].iloc[0]
    assert bool(row["training_eligible"])

    promoted = build_promoted_manifest(packet)
    assert list(promoted["null_id"]) == ["N1"]
    assert promoted.iloc[0]["negative_truth_status"] == "reviewed_negative"


def test_radar_or_event_evidence_blocks_promotion():
    packet = build_packet(queue_frame())
    idx = packet.index[packet["null_id"].eq("N1")][0]

    packet.loc[idx, "review_status"] = "reviewed"
    packet.loc[idx, "final_class"] = "reviewed_negative"
    packet.loc[idx, "radar_target_present"] = "yes"
    packet.loc[idx, "event_evidence_present"] = "no"
    packet.loc[idx, "reviewer"] = "forecaster"
    packet.loc[idx, "reviewed_at_utc"] = "2026-10-05T16:00:00Z"

    packet = build_packet(packet)
    row = packet.loc[packet["null_id"].eq("N1")].iloc[0]
    assert not bool(row["training_eligible"])
    assert row["promotion_status"] == "reviewed_not_promotable"


def test_existing_review_decisions_are_preserved():
    queue = queue_frame()
    existing = pd.DataFrame({
        "null_id": ["N1"],
        "review_status": ["reviewed"],
        "final_class": ["contaminated_unknown"],
        "radar_target_present": ["yes"],
        "event_evidence_present": ["unknown"],
        "surface_evidence_interpreted": ["yes"],
        "reviewer": ["forecaster"],
        "reviewed_at_utc": ["2026-10-05T15:00:00Z"],
        "review_notes": ["Possible organized target; retain out of training."],
    })

    packet = build_packet(queue, existing_review=existing)
    row = packet.loc[packet["null_id"].eq("N1")].iloc[0]
    assert row["final_class"] == "contaminated_unknown"
    assert row["review_notes"].startswith("Possible organized target")
    assert not bool(row["training_eligible"])
    assert validate_packet(packet) == []


def test_invalid_manual_training_flag_is_rejected():
    packet = build_packet(queue_frame())
    packet.loc[packet["null_id"].eq("N1"), "training_eligible"] = True
    errors = validate_packet(packet)
    assert errors
    assert any("must be derived" in error for error in errors)


def test_packet_contains_review_candidates_not_entire_null_population():
    queue = queue_frame().copy()
    queue["review_recommended"] = [True, False]

    packet = build_packet(queue)

    assert set(packet["null_id"]) == {"N1"}


def test_surface_interpretation_is_required_for_promotion():
    packet = build_packet(queue_frame())
    idx = packet.index[packet["null_id"].eq("N1")][0]

    packet.loc[idx, "review_status"] = "reviewed"
    packet.loc[idx, "final_class"] = "reviewed_negative"
    packet.loc[idx, "radar_target_present"] = "no"
    packet.loc[idx, "event_evidence_present"] = "no"
    packet.loc[idx, "surface_evidence_interpreted"] = "unknown"
    packet.loc[idx, "reviewer"] = "forecaster"
    packet.loc[idx, "reviewed_at_utc"] = "2026-10-05T16:00:00Z"

    packet = build_packet(packet)
    row = packet.loc[packet["null_id"].eq("N1")].iloc[0]
    assert not bool(row["training_eligible"])


def test_reviewer_notes_are_required_for_promotion():
    packet = build_packet(queue_frame())
    idx = packet.index[packet["null_id"].eq("N1")][0]

    packet.loc[idx, "review_status"] = "reviewed"
    packet.loc[idx, "final_class"] = "reviewed_negative"
    packet.loc[idx, "radar_target_present"] = "no"
    packet.loc[idx, "event_evidence_present"] = "no"
    packet.loc[idx, "surface_evidence_interpreted"] = "yes"
    packet.loc[idx, "reviewer"] = "forecaster"
    packet.loc[idx, "reviewed_at_utc"] = "2026-10-05T16:00:00Z"
    packet.loc[idx, "review_notes"] = ""

    packet = build_packet(packet)
    row = packet.loc[packet["null_id"].eq("N1")].iloc[0]
    assert not bool(row["training_eligible"])
