import json
from datetime import datetime,timezone
from scripts.audit_operational_readiness import validate

def test_operational_readiness_accepts_unscored_polygon_product(tmp_path):
    now=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state={"last_source":"KCXX20260928_190000_V06","last_scan_time_utc":now,"last_object_count":1}
    geo={"type":"FeatureCollection","features":[{
        "type":"Feature",
        "geometry":{"type":"Polygon","coordinates":[[[-73.2,44.4],[-73.1,44.4],[-73.1,44.5],[-73.2,44.4]]]},
        "properties":{
            "track_id":"1","timestamp":now,"centroid_lat":44.45,"centroid_lon":-73.15,
            "probability_15min":None,"probability_30min":None,
            "probability_45min":None,"probability_60min":None,
        }}],
        "metadata":{"scan_time_utc":now,"source_file":"KCXX20260928_190000_V06",
                    "object_count":1,"probability_status":"not_scored"}}
    sp=tmp_path/"state.json"; gp=tmp_path/"objects.geojson"
    sp.write_text(json.dumps(state),encoding="utf-8"); gp.write_text(json.dumps(geo),encoding="utf-8")
    assert validate(sp,gp)["status"]=="ready_for_research_weighted_live_object_delivery"
