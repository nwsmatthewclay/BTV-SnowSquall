from pathlib import Path

def test_live_publisher_contract():
    root=Path(__file__).resolve().parents[1]
    text=(root/'.github/workflows/live-object-publisher.yml').read_text(encoding='utf-8')
    assert 'cron: "*/5 * * * *"' in text
    assert 'ref: snow-squall-model-foundation' in text
    assert '--radar KCXX' in text
    assert '--radar KTYX' in text
    assert 'KCXX_state.json' in text and 'KTYX_state.json' in text
    assert 'KCXX_objects.geojson' in text and 'KTYX_objects.geojson' in text
    assert 'Restore prior live feed history' in text
    assert 'git push --force origin HEAD:snow-squall-live-data' in text
    assert 'snow-squall-live-data' in text