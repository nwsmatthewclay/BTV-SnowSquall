"""Create a visual track reconstruction from pilot object-scan CSV data."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from shapely import wkt


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--output", default="data/derived/pilot_track.png")
    p.add_argument("--title", default="Snow Squall Radar Object Reconstruction")
    args = p.parse_args()

    df = pd.read_csv(args.input)
    df["scan_time_utc"] = pd.to_datetime(df["scan_time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["centroid_lat", "centroid_lon"]).sort_values(
        ["object_id", "scan_time_utc"]
    )
    if df.empty:
        raise SystemExit("No geographic object records found.")

    fig, ax = plt.subplots(figsize=(12, 9))

    for object_id, g in df.groupby("object_id"):
        ax.plot(g["centroid_lon"], g["centroid_lat"], linewidth=2, alpha=0.8)
        first = g.iloc[0]
        last = g.iloc[-1]
        ax.scatter(first["centroid_lon"], first["centroid_lat"], s=45, marker="o")
        ax.scatter(last["centroid_lon"], last["centroid_lat"], s=75, marker="x")
        ax.text(last["centroid_lon"], last["centroid_lat"], f" {int(object_id)}", fontsize=9)

        for _, row in g.iterrows():
            geom_text = row.get("geometry_wkt")
            if isinstance(geom_text, str) and geom_text:
                try:
                    geom = wkt.loads(geom_text)
                    if hasattr(geom, "exterior"):
                        x, y = geom.exterior.xy
                        ax.plot(x, y, linewidth=0.7, alpha=0.35)
                except Exception:
                    pass

    # Label the final object state with the values most useful to the eventual
    # probability display.
    latest = df.iloc[-1]
    ax.text(
        0.02, 0.02,
        f"Latest scan: {latest['scan_time_utc']}\n"
        f"Reflectivity: {latest['max_reflectivity_dbz']:.1f} dBZ\n"
        f"Area: {latest['area_km2']:.1f} km²",
        transform=ax.transAxes,
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.4", alpha=0.85),
    )

    ax.set_title(args.title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(alpha=0.25)
    ax.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
