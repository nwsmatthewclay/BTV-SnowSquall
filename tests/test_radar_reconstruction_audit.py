import pandas as pd

from scripts.audit_radar_reconstruction import audit


def test_reconstruction_audit_counts_backends_and_failures(tmp_path):
    objects = pd.DataFrame(
        {
            "source_file": ["a", "a", "b"],
            "reader_backend": ["pyart_legacy_nexrad", "pyart_legacy_nexrad", "xradar"],
        }
    )
    errors = pd.DataFrame(
        {
            "source_file": ["c"],
            "error_type": ["IndexError"],
        }
    )
    op = tmp_path / "objects.csv"
    ep = tmp_path / "errors.csv"
    objects.to_csv(op, index=False)
    errors.to_csv(ep, index=False)

    result = audit(op, ep)

    assert result["object_records"] == 3
    assert result["volumes_with_candidate_objects"] == 2
    assert result["failed_volumes"] == 1
    assert result["reader_backend_volume_counts"]["pyart_legacy_nexrad"] == 1
    assert result["reader_backend_volume_counts"]["xradar"] == 1
