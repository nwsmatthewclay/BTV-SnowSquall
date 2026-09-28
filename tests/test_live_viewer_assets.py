from pathlib import Path

def test_live_viewer_references_operational_feed_assets():
    root=Path(__file__).resolve().parents[1]
    html=(root/'viewer/live.html').read_text(encoding='utf-8')
    js=(root/'viewer/live.js').read_text(encoding='utf-8')
    assert 'live.js' in html
    assert 'KCXX' in js and 'KTYX' in js
    assert '_objects.geojson' in js
    assert 'probability scoring disabled' in html.lower()
    assert 'raw.githubusercontent.com/nwsmatthewclay/BTV-SnowSquall/snow-squall-model-foundation/viewer/data/live/' in js
