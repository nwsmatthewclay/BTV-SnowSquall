from pathlib import Path


def test_training_viewer_shell_is_present_and_uses_training_mode():
    html = Path("viewer/training.html").read_text(encoding="utf-8")
    assert '<body data-mode="training">' in html
    for element_id in (
        "caseSelect",
        "map",
        "slider",
        "playBtn",
        "metrics",
        "researchProbabilityBody",
        "trackHistory",
        "environment",
        "outcome",
        "detailsBtn",
    ):
        assert f'id="{element_id}"' in html


def test_shared_viewer_selects_benchmark_case_in_training_mode():
    js = Path("viewer/app.js").read_text(encoding="utf-8")
    assert 'document.body.dataset.mode==="training"' in js
    assert 'x.case_id==="BTV20181121"' in js
