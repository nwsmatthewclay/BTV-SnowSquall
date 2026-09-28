"""Build a descriptive surface-impact inventory for candidate SQW episodes."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from acquisition.asos_iem import request_observations


def load_stations(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"station", "lat", "lon"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Station manifest missing required columns: {sorted(missing)}")
    return df


def summarize_station(data: pd.DataFrame) -> dict:
    out = {
        "surface_rows": int(len(data)),
        "min_visibility_mi": None,
        "first_visibility_le_0p5_sm_utc": None,
        "first_visibility_le_0p25_sm_utc": None,
        "max_wind_gust_kt": None,
        "present_weather_codes": "",
    }
    if data.empty:
        return out

    if "visibility_mi" in data.columns:
        vis = pd.to_numeric(data["visibility_mi"], errors="coerce")
        valid = data.assign(_vis=vis).dropna(subset=["_vis"]).sort_values("valid")
        if not valid.empty:
            out["min_visibility_mi"] = float(valid["_vis"].min())
            for threshold, key in ((0.5, "first_visibility_le_0p5_sm_utc"),
                                   (0.25, "first_visibility_le_0p25_sm_utc")):
                hit = valid[valid["_vis"] <= threshold]
                if not hit.empty:
                    out[key] = str(hit.iloc[0]["valid"])

    if "wind_gust_kt" in data.columns:
        gust = pd.to_numeric(data["wind_gust_kt"], errors="coerce")
        if gust.notna().any():
            out["max_wind_gust_kt"] = float(gust.max())

    if "wxcodes" in data.columns:
        vals = sorted({
            str(v).strip()
            for v in data["wxcodes"].dropna()
            if str(v).strip() and str(v).strip().lower() not in {"nan", "m"}
        })
        out["present_weather_codes"] = ";".join(vals)

    return out


def build(episodes_path: Path, stations_path: Path, output_root: Path) -> pd.DataFrame:
    episodes = pd.read_csv(episodes_path)
    stations = load_stations(stations_path)
    required = {"episode_id", "episode_start", "episode_end"}
    missing = required - set(episodes.columns)
    if missing:
        raise ValueError(f"Episode table missing required columns: {sorted(missing)}")

    rows = []
    errors = []
    output_root.mkdir(parents=True, exist_ok=True)

    for episode in episodes.itertuples(index=False):
        start = pd.to_datetime(episode.episode_start, utc=True) - pd.Timedelta(minutes=30)
        end = pd.to_datetime(episode.episode_end, utc=True) + pd.Timedelta(minutes=30)
        for station_row in stations.itertuples(index=False):
            station = str(station_row.station)
            try:
                data = request_observations(station, start, end)
                station_out = summarize_station(data)
                rows.append({
                    "episode_id": str(episode.episode_id),
                    "episode_start_utc": pd.to_datetime(episode.episode_start, utc=True).isoformat(),
                    "episode_end_utc": pd.to_datetime(episode.episode_end, utc=True).isoformat(),
                    "station": station,
                    "station_lat": float(station_row.lat),
                    "station_lon": float(station_row.lon),
                    "query_start_utc": start.isoformat(),
                    "query_end_utc": end.isoformat(),
                    "query_status": "success",
                    **station_out,
                })
                data.to_csv(
                    output_root / station / f"{episode.episode_id}.csv",
                    index=False,
                )
                print(
                    f"{episode.episode_id} {station}: "
                    f"{station_out['surface_rows']} observations, "
                    f"min_vis={station_out['min_visibility_mi']}, "
                    f"max_gust={station_out['max_wind_gust_kt']}"
                )
            except Exception as exc:
                errors.append({
                    "episode_id": str(episode.episode_id),
                    "station": station,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                })
                print(
                    f"FAILED {episode.episode_id} {station}: "
                    f"{type(exc).__name__}: {exc}"
                )

    result = pd.DataFrame(rows)
    result.to_csv(output_root / "modern_sqw_surface_impact_inventory.csv", index=False)
    pd.DataFrame(
        errors, columns=["episode_id", "station", "error_type", "error_message"]
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
