"""Causal historical analog retrieval for SnowSquallProbSevere.

Analog retrieval is strictly causal: candidates must predate the query scan and
come from a different historical event/window. Multiple radar scans from the
same event are collapsed to the single closest state so one long-lived storm
cannot dominate the neighborhood.
"""
from __future__ import annotations

from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

HORIZONS = (15, 30, 45, 60)

RADAR_FEATURES = (
    "max_reflectivity_dbz", "mean_reflectivity_dbz", "area_km2",
    "length_km", "width_km", "core_pixel_count", "pixel_count",
    "echo_top_km", "top_minus_base_km", "zdr_mean_db", "rhohv_mean",
    "kdp_mean_degkm", "velocity_mean_kt", "velocity_std_kt",
    "motion_speed_kt", "reflectivity_core_excess", "centroid_displacement_km",
    "max_reflectivity_dbz_rate_per_min", "area_km2_rate_per_min",
)

ENV_FEATURES = (
    "snsq", "cape_jkg", "mucape_jkg", "mlcape_jkg", "cin_jkg",
    "dcape_jkg", "pwat_mm", "lcl_m", "rh_0_2km_pct",
    "shear_0_6km_kt", "srh01_m2s2", "lapse_rate_0_3km_c_km",
    "lapse_rate_0_7_5km_c_km", "wet_bulb_0_3km_c",
    "temperature_dewpoint_spread_k", "cloud_layer_depth_m",
    "cloud_layer_rh_pct", "cloud_layer_mean_wind_kt", "cloud_layer_shear_kt",
)


def _numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = pd.DataFrame(index=frame.index)
    for col in columns:
        out[col] = (
            pd.to_numeric(frame[col], errors="coerce")
            if col in frame.columns else np.nan
        )
    return out


def _binary(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float)
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    return series.astype(str).str.strip().str.lower().map(
        {"true": 1, "false": 0, "yes": 1, "no": 0, "1": 1, "0": 0}
    )


def _group_keys(reference: pd.DataFrame) -> np.ndarray:
    case = reference.get(
        "case_id", pd.Series("", index=reference.index)
    ).astype(str)
    null_id = reference.get(
        "null_id", pd.Series("", index=reference.index)
    ).astype(str)
    population = reference.get(
        "population_id", pd.Series("", index=reference.index)
    ).astype(str)

    keys = []
    for case_id, null_value, pop_value, row_id in zip(
        case, null_id, population, reference.index
    ):
        if case_id and case_id.lower() not in {"nan", "none"}:
            keys.append("case:" + case_id)
        elif null_value and null_value.lower() not in {"nan", "none"}:
            keys.append("null:" + null_value)
        elif pop_value and pop_value.lower() not in {"nan", "none"}:
            keys.append("pop:" + pop_value)
        else:
            keys.append("row:" + str(row_id))
    return np.asarray(keys, dtype=str)


@dataclass
class AnalogLibrary:
    feature_columns: list[str]
    matrix: np.ndarray
    scaler: StandardScaler
    groups: np.ndarray
    timestamps: np.ndarray
    targets: dict[int, np.ndarray]
    medians: np.ndarray

    @classmethod
    def fit(cls, reference: pd.DataFrame) -> "AnalogLibrary":
        if "scan_time_utc" not in reference.columns:
            raise ValueError("Analog reference requires scan_time_utc")

        times = pd.to_datetime(
            reference["scan_time_utc"], utc=True, errors="coerce"
        )
        valid_time = times.notna()
        if not valid_time.any():
            raise ValueError("Analog reference contains no valid timestamps")

        reference = reference.loc[valid_time].copy()
        times = times.loc[valid_time]

        cols = [
            c for c in (*RADAR_FEATURES, *ENV_FEATURES)
            if c in reference.columns
        ]
        if not cols:
            raise ValueError("No analog feature columns are present")

        x = _numeric(reference, cols)
        med = x.median(numeric_only=True).reindex(cols).fillna(0.0)
        x = x.fillna(med).fillna(0.0)

        scaler = StandardScaler().fit(x.values)
        matrix = scaler.transform(x.values)
        groups = _group_keys(reference)
        timestamps = times.astype("int64").to_numpy()

        targets = {}
        for h in HORIZONS:
            name = f"squall_onset_within_{h}m"
            if name in reference.columns:
                values = _binary(reference[name]).fillna(0.0).to_numpy()
            else:
                values = np.zeros(len(reference), dtype=float)
            targets[h] = values

        return cls(
            feature_columns=cols,
            matrix=matrix,
            scaler=scaler,
            groups=groups,
            timestamps=timestamps,
            targets=targets,
            medians=med.to_numpy(dtype=float),
        )

    def query(
        self,
        query: pd.DataFrame,
        *,
        top_k: int = 15,
        max_age_days: float | None = None,
        exclude_case_col: str = "case_id",
        time_col: str = "scan_time_utc",
    ) -> pd.DataFrame:
        cols = self.feature_columns
        q = _numeric(query, cols)
        q = q.fillna(pd.Series(self.medians, index=cols)).fillna(0.0)
        qz = self.scaler.transform(q.values)

        query_times = pd.to_datetime(
            query[time_col], utc=True, errors="coerce"
        )
        query_valid = query_times.notna().to_numpy()
        query_ts = (
            query_times.fillna(pd.Timestamp("1900-01-01", tz="UTC"))
            .astype("int64")
            .to_numpy()
        )

        case_series = query.get(
            exclude_case_col, pd.Series("", index=query.index)
        ).astype(str)
        null_series = query.get(
            "null_id", pd.Series("", index=query.index)
        ).astype(str)
        pop_series = query.get(
            "population_id", pd.Series("", index=query.index)
        ).astype(str)

        query_groups = []
        for case_id, null_value, pop_value in zip(
            case_series, null_series, pop_series
        ):
            if case_id and case_id.lower() not in {"nan", "none"}:
                query_groups.append("case:" + case_id)
            elif null_value and null_value.lower() not in {"nan", "none"}:
                query_groups.append("null:" + null_value)
            elif pop_value and pop_value.lower() not in {"nan", "none"}:
                query_groups.append("pop:" + pop_value)
            else:
                query_groups.append("")

        out = pd.DataFrame(index=query.index)
        out["analog_count"] = 0
        out["analog_case_count"] = 0
        out["analog_distance"] = np.nan
        out["analog_similarity"] = np.nan
        out["analog_nearest_distance"] = np.nan
        out["analog_nearest_age_hours"] = np.nan
        for h in HORIZONS:
            out[f"analog_onset_rate_{h}m"] = np.nan
            out[f"analog_onset_count_{h}m"] = 0

        for qi, row_index in enumerate(query.index):
            if not query_valid[qi]:
                continue

            eligible = self.timestamps < query_ts[qi]
            if query_groups[qi]:
                eligible &= self.groups != query_groups[qi]
            if max_age_days is not None:
                eligible &= (
                    query_ts[qi] - self.timestamps
                    <= int(max_age_days * 86400 * 1e9)
                )

            idx = np.flatnonzero(eligible)
            if idx.size == 0:
                continue

            distances = np.linalg.norm(self.matrix[idx] - qz[qi], axis=1)
            order = np.argsort(distances)

            picked = []
            picked_distances = []
            seen_groups: set[str] = set()
            for position in order:
                candidate = int(idx[position])
                group = str(self.groups[candidate])
                if group in seen_groups:
                    continue
                seen_groups.add(group)
                picked.append(candidate)
                picked_distances.append(float(distances[position]))
                if len(picked) >= max(1, int(top_k)):
                    break

            if not picked:
                continue

            picked_idx = np.asarray(picked, dtype=int)
            dist = np.asarray(picked_distances, dtype=float)
            weights = np.exp(-0.5 * np.minimum(dist, 12.0) ** 2)
            if not np.isfinite(weights).any() or weights.sum() <= 0:
                continue
            weights /= weights.sum()

            out.at[row_index, "analog_count"] = int(len(picked_idx))
            out.at[row_index, "analog_case_count"] = int(
                pd.Series(self.groups[picked_idx]).nunique()
            )
            out.at[row_index, "analog_distance"] = float(
                np.average(dist, weights=weights)
            )
            out.at[row_index, "analog_similarity"] = float(
                np.average(np.exp(-dist), weights=weights)
            )
            out.at[row_index, "analog_nearest_distance"] = float(dist[0])
            out.at[row_index, "analog_nearest_age_hours"] = float(
                (query_ts[qi] - self.timestamps[picked_idx[0]]) / 3.6e12
            )

            for h in HORIZONS:
                values = self.targets[h][picked_idx]
                out.at[row_index, f"analog_onset_rate_{h}m"] = float(
                    np.average(values, weights=weights)
                )
                out.at[row_index, f"analog_onset_count_{h}m"] = int(
                    np.sum(values)
                )

        return out

    def save(self, path) -> None:
        joblib.dump(self, path)

    @classmethod
    def load(cls, path) -> "AnalogLibrary":
        return joblib.load(path)


def add_causal_analog_features(
    frame: pd.DataFrame,
    top_k: int = 15,
    max_age_days: float | None = None,
) -> pd.DataFrame:
    out = frame.copy()
    if "scan_time_utc" not in out.columns:
        return out

    if "case_id" not in out.columns:
        work = out.copy()
        work["case_id"] = ""
    else:
        work = out.copy()

    work["_scan_dt"] = pd.to_datetime(
        work["scan_time_utc"], utc=True, errors="coerce"
    )
    work = work.sort_values("_scan_dt", kind="stable").reset_index(drop=False)
    query = work.drop(columns=["_scan_dt"])
    library = AnalogLibrary.fit(query)
    analogs = library.query(query, top_k=top_k, max_age_days=max_age_days)

    analogs["__original_index"] = work["index"].to_numpy()
    analogs = analogs.set_index("__original_index")
    for col in analogs.columns:
        out.loc[analogs.index, col] = analogs[col]
    return out
