from pathlib import Path

def test_live_publisher_contract():
    root=Path(__file__).resolve().parents[1]
    text=(root/'.github/workflows/live-object-publisher.yml').read_text(encoding='utf-8')
    assert 'cron: "*/15 * * * *"' in text
    assert 'ref: snow-squall-model-foundation' in text
    assert '--radar KCXX' in text
    assert '--radar KTYX' in text
    assert 'KCXX_state.json' in text and 'KTYX_state.json' in text
    assert 'KCXX_objects.geojson' in text and 'KTYX_objects.geojson' in text
    assert 'git push origin HEAD:snow-squall-model-foundation' in text
    assert '[skip ci]' in text