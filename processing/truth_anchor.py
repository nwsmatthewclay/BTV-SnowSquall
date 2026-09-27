"""Attach a conservative station-proximity truth anchor to radar tracks."""
from __future__ import annotations
import pandas as pd
import numpy as np

STATIONS = {
    "KBTV": (44.471955, -73.153276),
    "KMPV": (44.203489, -72.562096),
    "KMSS": (44.936241, -74.845120),
}

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
    return 2*r*np.arcsin(np.sqrt(a))

def attach_truth_anchor(objects, cases, radius_km=40, pre_minutes=60, post_minutes=30):
    out = objects.copy()
    out["scan_time"] = pd.to_datetime(out["scan_time"], utc=True)
    out["truth_anchor"] = False
    out["truth_phase"] = "unmatched"

    for _, case in cases.iterrows():
        station = STATIONS.get(case["observing_station"])
        if station is None:
            continue
        onset = pd.to_datetime(case["event_start_utc"], utc=True)
        mask = (
            (out["case_id"] == case["case_id"]) &
            (out["scan_time"] >= onset - pd.Timedelta(minutes=pre_minutes)) &
            (out["scan_time"] <= onset + pd.Timedelta(minutes=post_minutes))
        )
        candidates = out.loc[mask].copy()
        if candidates.empty:
            continue
        candidates["distance_km"] = haversine_km(
            candidates["lat"], candidates["lon"], station[0], station[1]
        )
        candidates = candidates[candidates["distance_km"] <= radius_km]
        if candidates.empty:
            continue
        track = candidates.sort_values(["distance_km", "scan_time"]).iloc[0]["object_id"]
        track_mask = out["object_id"] == track
        out.loc[track_mask, "truth_anchor"] = True
        out.loc[track_mask & (out["scan_time"] < onset), "truth_phase"] = "developing"
        out.loc[track_mask & (out["scan_time"] >= onset), "truth_phase"] = "observed_onset"

    return out
