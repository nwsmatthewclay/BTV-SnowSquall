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
        "probabilityEvolutionBody",
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
    assert "function renderProbabilityEvolution" in js


def test_training_viewer_marks_current_scan_and_benchmark_provenance():
    js = Path("viewer/app.js").read_text(encoding="utf-8")
    assert "activePointIndex" in js
    assert "class='chart-current'" in js
    assert "Current scan:" in js

    workflow = Path(".github/workflows/snow-squall-benchmark-replay.yml").read_text(encoding="utf-8")
    assert "Embed candidate model provenance" in workflow
    assert 'catalog["model_summary"]' in workflow
    assert "MODEL_RUN_ID" in workflow
