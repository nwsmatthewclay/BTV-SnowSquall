"""Build descriptive surface-impact evidence for candidate SQW episodes."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from acquisition.asos_iem import request_observations


SNOW_TOKENS = {"SN", "-SN", "+SN", "BLSN", "-BLSN", "+BLSN"}


def iso_utc(value) -> str:
    return pd.to_datetime(value, utc=True).strftime("%Y-%m-%dT%H:%M:%SZ")


def summarize_station(
    data: pd.DataFrame,
    episode_start=None,
    episode_end=None,
) -> dict:
    out = {
        "surface_rows": int(len(data)),
        "min_visibility_mi": None,
        "visibility_min_time_utc": None,
        "first_visibility_le_0p5_sm_utc": None,
        "first_visibility_le_0p25_sm_utc": None,
        "max_wind_gust_kt": None,
        "present_weather_codes": "",
        "present_weather_at_visibility_min": "",
        "snow_code_at_visibility_min": False,
        "baseline_visibility_median_mi": None,
        "visibility_drop_from_baseline_mi": None,
    }
    if data.empty:
        return out

    working = data.copy()
    working["valid"] = pd.to_datetime(working["valid"], utc=True, errors="coerce", format="mixed")

    if "visibility_mi" in working.columns:
        vis = pd.to_numeric(working["visibility_mi"], errors="coerce")
        valid = working.assign(_vis=vis).dropna(subset=["valid", "_vis"]).sort_values("valid")
        if not valid.empty:
            min_row = valid.loc[valid["_vis"].idxmin()]
            out["min_visibility_mi"] = float(min_row["_vis"])
            out["visibility_min_time_utc"] = iso_utc(min_row["valid"])
            wx = str(min_row.get("wxcodes", "") or "")
            out["present_weather_at_visibility_min"] = wx
            tokens = set(wx.upper().replace(",", " ").split())
            out["snow_code_at_visibility_min"] = bool(tokens & SNOW_TOKENS)

            for threshold, key in (
                (0.5, "first_visibility_le_0p5_sm_utc"),
                (0.25, "first_visibility_le_0p25_sm_utc"),
            ):
                hit = valid[valid["_vis"] <= threshold]
                if not hit.empty:
                    out[key] = iso_utc(hit.iloc[0]["valid"])

            if episode_start is not None:
                start = pd.to_datetime(episode_start, utc=True)
                baseline = valid[valid["valid"] < start]["_vis"]
                if not baseline.empty:
                    out["baseline_visibility_median_mi"] = float(baseline.median())
                    out["visibility_drop_from_baseline_mi"] = (
                        out["baseline_visibility_median_mi"] - out["min_visibility_mi"]
                    )

    if "wind_gust_kt" in working.columns:
        gust = pd.to_numeric(working["wind_gust_kt"], errors="coerce")
        if gust.notna().any():
            out["max_wind_gust_kt"] = float(gust.max())

    if "wxcodes" in working.columns:
        vals = sorted({
            str(v).strip()
            for v in working["wxcodes"].dropna()
            if str(v).strip() and str(v).strip().lower() not in {"nan", "m"}
        })
        out["present_weather_codes"] = ";".join(vals)

    return out


def build(episodes_path: Path, stations_path: Path, output_root: Path) -> pd.DataFrame:
    episodes = pd.read_csv(episodes_path)
    stations = pd.read_csv(stations_path)

    required_episode = {"episode_id", "episode_start", "episode_end"}
    missing = required_episode - set(episodes.columns)
    if missing:
        raise ValueError(f"Episode table missing required columns: {sorted(missing)}")

    required_station = {"station", "lat", "lon"}
    missing = required_station - set(stations.columns)
    if missing:
        raise ValueError(f"Station manifest missing required columns: {sorted(missing)}")

    rows, errors = [], []
    output_root.mkdir(parents=True, exist_ok=True)

    for episode in episodes.itertuples(index=False):
        start = pd.to_datetime(episode.episode_start, utc=True) - pd.Timedelta(minutes=30)
        end = pd.to_datetime(episode.episode_end, utc=True) + pd.Timedelta(minutes=30)

        for station_row in stations.itertuples(index=False):
            station = str(station_row.station)
            try:
                data = request_observations(station, start, end)
                summary = summarize_station(
                    data,
                    episode_start=pd.to_datetime(episode.episode_start, utc=True),
                    episode_end=pd.to_datetime(episode.episode_end, utc=True),
                )
                rows.append({
                    "episode_id": str(episode.episode_id),
                    "episode_start_utc": iso_utc(episode.episode_start),
                    "episode_end_utc": iso_utc(episode.episode_end),
                    "station": station,
                    "station_lat": float(station_row.lat),
                    "station_lon": float(station_row.lon),
                    "query_start_utc": iso_utc(start),
                    "query_end_utc": iso_utc(end),
                    "query_status": "success",
                    **summary,
                })
                out = output_root / station / f"{episode.episode_id}.csv"
                out.parent.mkdir(parents=True, exist_ok=True)
                data.to_csv(out, index=False)
                print(
                    f"{episode.episode_id} {station}: rows={summary['surface_rows']} "
                    f"min_vis={summary['min_visibility_mi']} "
                    f"gust={summary['max_wind_gust_kt']} "
                    f"snow_at_min={summary['snow_code_at_visibility_min']}"
                )
            except Exception as exc:
                errors.append({
                    "episode_id": str(episode.episode_id),
                    "station": station,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                })
                print(f"FAILED {episode.episode_id} {station}: {type(exc).__name__}: {exc}")

    result = pd.DataFrame(rows)
    result.to_csv(output_root / "modern_sqw_surface_impact_inventory.csv", index=False)
    pd.DataFrame(
        errors,
        columns=["episode_id", "station", "error_type", "error_message"],
    ).to_csv(output_root / "modern_sqw_surface_impact_errors.csv", index=False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", required=True)
    parser.add_argument("--stations", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build(Path(args.episodes), Path(args.stations), Path(args.output))
    print(f"Built {len(result)} episode-station surface records.")


if __name__ == "__main__":
    main()
