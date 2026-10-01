"""Causal historical analog retrieval for SnowSquallProbSevere.

An analog query compares the current radar-object/environment state with
earlier archived case states only. The query case itself is always excluded,
and only analog states whose timestamps precede the query timestamp are
eligible. Outcome labels attached to analog states are historical knowledge
available to a real-time model.
"""
from __future__ import annotations
from dataclasses import dataclass
import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

HORIZONS = (15, 30, 45, 60)
RADAR_FEATURES = (
    "max_reflectivity_dbz", "mean_reflectivity_dbz", "area_km2", "length_km", "width_km",
    "core_pixel_count", "pixel_count", "echo_top_km", "top_minus_base_km",
    "zdr_mean_db", "rhohv_mean", "kdp_mean_degkm", "velocity_mean_kt", "velocity_std_kt",
    "motion_speed_kt", "reflectivity_core_excess", "centroid_displacement_km",
    "max_reflectivity_dbz_rate_per_min", "area_km2_rate_per_min",
)
ENV_FEATURES = (
    "snsq", "cape_jkg", "mucape_jkg", "mlcape_jkg", "cin_jkg", "dcape_jkg",
    "pwat_mm", "lcl_m", "rh_0_2km_pct", "shear_0_6km_kt", "srh01_m2s2",
    "lapse_rate_0_3km_c_km", "lapse_rate_0_7_5km_c_km", "wet_bulb_0_3km_c",
    "temperature_dewpoint_spread_k", "cloud_layer_depth_m", "cloud_layer_rh_pct",
    "cloud_layer_mean_wind_kt", "cloud_layer_shear_kt",
)

def _numeric(frame, columns):
    out = pd.DataFrame(index=frame.index)
    for col in columns:
        out[col] = pd.to_numeric(frame[col], errors="coerce") if col in frame.columns else np.nan
    return out

def _binary(series):
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float)
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    return series.astype(str).str.strip().str.lower().map(
        {"true": 1, "false": 0, "yes": 1, "no": 0, "1": 1, "0": 0}
    )

@dataclass
class AnalogLibrary:
    feature_columns: list[str]
    matrix: np.ndarray
    scaler: StandardScaler
    cases: np.ndarray
    timestamps: np.ndarray
    targets: dict[int, np.ndarray]

    @classmethod
    def fit(cls, reference: pd.DataFrame):
        cols = [c for c in (*RADAR_FEATURES, *ENV_FEATURES) if c in reference.columns]
        if not cols:
            raise ValueError("No analog feature columns are present")
        x = _numeric(reference, cols)
        med = x.median(numeric_only=True)
        x = x.fillna(med).fillna(0.0)
        scaler = StandardScaler().fit(x.values)
        matrix = scaler.transform(x.values)
        cases = reference.get("case_id", pd.Series("", index=reference.index)).astype(str).to_numpy()
        times = pd.to_datetime(reference["scan_time_utc"], utc=True, errors="coerce")
        valid_time = times.notna().to_numpy()
        if not valid_time.any():
            raise ValueError("Analog reference contains no valid timestamps")
        reference = reference.loc[valid_time].copy()
        x = x.loc[valid_time]
        times = times.loc[valid_time]
        cases = reference.get("case_id", pd.Series("", index=reference.index)).astype(str).to_numpy()
        ts = times.astype("int64").to_numpy()
        targets = {}
        for h in HORIZONS:
            name = f"squall_onset_within_{h}m"
            targets[h] = _binary(reference[name]).fillna(0).to_numpy() if name in reference.columns else np.zeros(len(reference))
        lib = cls(cols, matrix, scaler, cases, ts, targets)
        lib.medians_ = med.reindex(cols).fillna(0.0).to_numpy(dtype=float)
        return lib

    def query(self, query: pd.DataFrame, *, top_k=15, max_age_days=None,
              exclude_case_col="case_id", time_col="scan_time_utc"):
        cols = self.feature_columns
        q = _numeric(query, cols).fillna(pd.Series(self.medians_, index=cols)).fillna(0.0)
        qz = self.scaler.transform(q.values)
        query_cases = query.get(exclude_case_col, pd.Series("", index=query.index)).astype(str).to_numpy()
        query_ts = pd.to_datetime(query[time_col], utc=True, errors="coerce").astype("int64").to_numpy()
        out = pd.DataFrame(index=query.index)
        out["analog_count"] = 0
        out["analog_distance"] = np.nan
        out["analog_similarity"] = np.nan
        out["analog_case_count"] = 0
        for h in HORIZONS:
            out[f"analog_onset_rate_{h}m"] = np.nan
            out[f"analog_onset_count_{h}m"] = 0
        for qi, row_index in enumerate(query.index):
            if not np.isfinite(query_ts[qi]):
                continue
            eligible = self.timestamps < query_ts[qi]
            eligible &= self.cases != query_cases[qi]
            if max_age_days is not None:
                eligible &= (query_ts[qi] - self.timestamps) <= int(max_age_days * 86400 * 1e9)
            idx = np.flatnonzero(eligible)
            if idx.size == 0:
                continue
            d = np.linalg.norm(self.matrix[idx] - qz[qi], axis=1)
            order = np.argsort(d)[:max(1, int(top_k))]
            picked = idx[order]
            dist = d[order]
            weights = np.exp(-0.5 * np.minimum(dist, 12.0) ** 2)
            if not np.isfinite(weights).any() or weights.sum() <= 0:
                continue
            weights = weights / weights.sum()
            out.at[row_index, "analog_count"] = int(len(picked))
            out.at[row_index, "analog_distance"] = float(np.average(dist, weights=weights))
            out.at[row_index, "analog_similarity"] = float(np.average(np.exp(-dist), weights=weights))
            out.at[row_index, "analog_case_count"] = int(pd.Series(self.cases[picked]).nunique())
            for h in HORIZONS:
                y = self.targets[h][picked]
                out.at[row_index, f"analog_onset_rate_{h}m"] = float(np.average(y, weights=weights))
                out.at[row_index, f"analog_onset_count_{h}m"] = int(np.sum(y))
        return out

    def save(self, path):
        joblib.dump(self, path)

    @classmethod
    def load(cls, path):
        return joblib.load(path)

def add_causal_analog_features(frame: pd.DataFrame, top_k=15, max_age_days=None) -> pd.DataFrame:
    out = frame.copy()
    if "scan_time_utc" not in out.columns or "case_id" not in out.columns:
        out["analog_count"] = 0
        out["analog_case_count"] = 0
        out["analog_distance"] = np.nan
        out["analog_similarity"] = np.nan
        for h in HORIZONS:
            out[f"analog_onset_rate_{h}m"] = np.nan
            out[f"analog_onset_count_{h}m"] = 0
        return out
    work = out.copy()
    work["_scan_dt"] = pd.to_datetime(work["scan_time_utc"], utc=True, errors="coerce")
    work = work.sort_values("_scan_dt", kind="stable").reset_index(drop=False)
    query = work.drop(columns=["_scan_dt"])
    lib = AnalogLibrary.fit(query)
    result = lib.query(query, top_k=top_k, max_age_days=max_age_days)
    result["__original_index"] = work["index"].to_numpy()
    result = result.set_index("__original_index")
    for col in result.columns:
        out.loc[result.index, col] = result[col]
    return out