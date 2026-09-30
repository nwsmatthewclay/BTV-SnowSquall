#!/usr/bin/env python3
"""Harvest NWS Snow Squall Warning VTEC events from the IEM archive.

IEM provides a high-fidelity archive of NWS VTEC products. This script collects
warning-era metadata only; event verification remains a separate step.

The IEM VTEC Events JSON service is documented at:
https://mesonet.agron.iastate.edu/api/
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://mesonet.agron.iastate.edu/json/vtec_events.py"


def fetch(year: int, wfo: str) -> list[dict]:
    params = {
        "year": str(year),
        "wfo": wfo,
        "phenomena": "SQ",
        "significance": "W",
    }
    url = f"{BASE}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "BTV-SnowSquall historical research"})
    with urlopen(req, timeout=30) as resp:
        payload = json.load(resp)

    if isinstance(payload, dict):
        for key in ("data", "results", "features"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x.get("properties", x) if isinstance(x, dict) else {} for x in value]
    if isinstance(payload, list):
        return [x.get("properties", x) if isinstance(x, dict) else {} for x in payload]
    raise ValueError("Unsupported IEM response format")


def get(row: dict, *keys: str) -> str:
    for key in keys:
        if key in row and row[key] is not None:
            return str(row[key])
    return ""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start-year", type=int, default=2018)
    p.add_argument("--end-year", type=int, default=2026)
    p.add_argument("--wfo", default="BTV")
    p.add_argument("--output", default="data/historical/sqw_warning_inventory.csv")
    args = p.parse_args()

    rows: list[dict[str, str]] = []
    for year in range(args.start_year, args.end_year + 1):
        for row in fetch(year, args.wfo):
            rows.append(
                {
                    "wfo": args.wfo,
                    "year": str(year),
                    "phenomena": get(row, "phenom", "phenomena"),
                    "significance": get(row, "sig", "significance"),
                    "etn": get(row, "etn", "eventid", "event_id"),
                    "issued": get(row, "issued"),
                    "expired": get(row, "expired", "expire"),
                    "init_issued": get(row, "init_iss", "init_issued"),
                    "init_expired": get(row, "init_exp", "init_expired"),
                    "product_id": get(row, "prod_id", "product_id"),
                    "status": get(row, "status"),
                }
            )

    rows.sort(key=lambda r: (r["issued"], r["etn"]))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "wfo", "year", "phenomena", "significance", "etn", "issued", "expired",
        "init_issued", "init_expired", "product_id", "status",
    ]
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} Snow Squall Warning records to {out}")


if __name__ == "__main__":
    main()
