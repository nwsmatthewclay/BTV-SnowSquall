from scripts.build_event_archive import ENV_FIELDS, normalize_coord

def test_archive_contract_has_core_environment():
    assert {"snsq","cape_jkg","mucape_jkg","mlcape_jkg","dcape_jkg","pwat_mm"}.issubset(set(ENV_FIELDS))

def test_station_coordinate_fallback():
    lat,lon=normalize_coord({"case_lat":None,"case_lon":None,"observing_station":"KBTV"})
    assert round(lat,3)==44.472 and round(lon,3)==-73.153
