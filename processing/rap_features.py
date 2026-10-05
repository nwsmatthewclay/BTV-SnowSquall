"""Extract time-matched RAP environmental features at a radar-object centroid.

All values come from the RAP analysis valid at or before the radar scan time.
The extractor intentionally records missing fields as null rather than
silently substituting a different model cycle or a future analysis.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from collections import OrderedDict
from processing.snsq_profile import build_snsq_profile

import numpy as np
import xarray as xr


_FIELD_CACHE_MAX = 32
_FIELD_CACHE = OrderedDict()
_NEAREST_INDEX_CACHE_MAX = 256
_NEAREST_INDEX_CACHE = OrderedDict()

FIELD_SPECS = {
    "visibility_m": ("surface", "vis", None),
    "gust_ms": ("surface", "gust", None),
    "surface_temperature_k": ("heightAboveGround", "2t", 2),
    "cape_jkg": ("surface", "cape", None),
    "cin_jkg": ("surface", "cin", None),
    "pwat_mm": ("atmosphereSingleLayer", "pwat", None),
    "mlcape_jkg": ("pressureFromGroundLayer", "cape", 9000),
    "mlcin_jkg": ("pressureFromGroundLayer", "cin", 9000),
    "mucape_jkg": ("pressureFromGroundLayer", "cape", 18000),
    "mucin_jkg": ("pressureFromGroundLayer", "cin", 18000),
    "srh01_m2s2": ("heightAboveGroundLayer", "hlcy", (1000, 0)),
    "srh03_m2s2": ("heightAboveGroundLayer", "hlcy", (3000, 0)),
    "shear_u_0_6km_ms": ("heightAboveGroundLayer", "vucsh", (6000, 0)),
    "shear_v_0_6km_ms": ("heightAboveGroundLayer", "vvcsh", (6000, 0)),
    "u10_ms": ("heightAboveGround", "10u", 10),
    "v10_ms": ("heightAboveGround", "10v", 10),
    "temperature_2m_k": ("heightAboveGround", "2t", 2),
    "dewpoint_2m_k": ("heightAboveGround", "2d", 2),
    "rh_2m_pct": ("heightAboveGround", "2r", 2),
    "surface_pressure_pa": ("surface", "sp", None),
}


def _valid_time(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt64 = np.datetime64(value, "s")
            dt = datetime.fromtimestamp(int(dt64.astype("int64")), tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None
    return dt.astimezone(timezone.utc)


def _open_field(path: Path, type_of_level: str, short_name: str, level=None):
    key = (str(path.resolve()), type_of_level, short_name, level)
    cached = _FIELD_CACHE.get(key)
    if cached is not None:
        _FIELD_CACHE.move_to_end(key)
        return cached

    filters = {"typeOfLevel": type_of_level, "shortName": short_name}
    if level is not None:
        if type_of_level in ("heightAboveGround", "pressureFromGroundLayer"):
            filters["level"] = level
        elif type_of_level == "heightAboveGroundLayer":
            top, bottom = level
            filters["topLevel"] = top
            filters["bottomLevel"] = bottom

    ds = xr.open_dataset(
        path,
        engine="cfgrib",
        backend_kwargs={"filter_by_keys": filters, "indexpath": ""},
    )
    _FIELD_CACHE[key] = ds
    if len(_FIELD_CACHE) > _FIELD_CACHE_MAX:
        _, stale = _FIELD_CACHE.popitem(last=False)
        try:
            stale.close()
        except Exception:
            pass
    return ds


def _nearest_index(ds, latitude: float, longitude: float):
    key=(id(ds),round(float(latitude),4),round(float(longitude),4))
    cached=_NEAREST_INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    lat_name = next((x for x in ("latitude", "lat") if x in ds.coords), None)
    lon_name = next((x for x in ("longitude", "lon") if x in ds.coords), None)
    if lat_name is None or lon_name is None:
        return None
    lats = np.asarray(ds[lat_name].values)
    lons = np.asarray(ds[lon_name].values)
    distance = (lats - latitude) ** 2 + (
        (lons - longitude) * np.cos(np.deg2rad(latitude))
    ) ** 2
    idx = np.unravel_index(np.nanargmin(distance), distance.shape)
    _NEAREST_INDEX_CACHE[key]=idx
    _NEAREST_INDEX_CACHE.move_to_end(key)
    while len(_NEAREST_INDEX_CACHE) > _NEAREST_INDEX_CACHE_MAX:
        _NEAREST_INDEX_CACHE.popitem(last=False)
    return idx


def _nearest(ds, latitude: float, longitude: float):
    if not ds.data_vars:
        return None
    idx=_nearest_index(ds,latitude,longitude)
    if idx is None:
        return None
    variable = next(iter(ds.data_vars))
    value = np.asarray(ds[variable].values)[idx]
    return float(value) if np.isfinite(value) else None


def _dataset_valid_time(ds):
    """Return the dataset valid time from cfgrib/xarray metadata."""
    for key in ("valid_time", "time"):
        value = ds.attrs.get(key)
        parsed = _valid_time(value)
        if parsed is not None:
            return parsed
    for coord_name in ("valid_time", "time"):
        if coord_name in ds.coords:
            try:
                values = np.asarray(ds[coord_name].values).reshape(-1)
                for value in values:
                    parsed = _valid_time(value)
                    if parsed is not None:
                        return parsed
            except Exception:
                pass
    return None


def _height_from_pressure(target_pressure_hpa, pressure_hpa, heights_m):
    if target_pressure_hpa is None:
        return None
    p = np.asarray(pressure_hpa, dtype=float).reshape(-1)
    h = np.asarray(heights_m, dtype=float).reshape(-1)
    mask = np.isfinite(p) & np.isfinite(h)
    p, h = p[mask], h[mask]
    if len(p) < 2 or not np.isfinite(target_pressure_hpa):
        return None
    order = np.argsort(p)
    p, h = p[order], h[order]
    if float(target_pressure_hpa) < p[0] or float(target_pressure_hpa) > p[-1]:
        return None
    return float(np.interp(float(target_pressure_hpa), p, h))

def _metpy_derived_fields(path: Path, latitude, longitude, values):
    """Derive missing sounding diagnostics from the colocated RAP profile with MetPy."""
    result = {}
    try:
        from metpy.calc import (
            bulk_shear, downdraft_cape, el, lcl, lfc, mixed_layer_cape_cin,
            most_unstable_cape_cin, parcel_profile, relative_humidity_from_dewpoint,
            dewpoint_from_relative_humidity, dewpoint_from_specific_humidity,
            storm_relative_helicity, surface_based_cape_cin, wet_bulb_temperature,
        )
        from metpy.units import units
    except Exception as exc:
        result["__metpy_error"] = f"{type(exc).__name__}: {exc}"
        return result

    try:
        profile = {}
        for name in ("gh", "t", "u", "v"):
            profile[name] = _nearest_profile(_open_profile(path, name), latitude, longitude)
            if profile[name] is None:
                result["__metpy_error"] = f"profile_{name}_unavailable"
                return result
        t_levels, t_values = profile["t"]
        pressure = np.asarray(t_levels, dtype=float)
        if np.nanmedian(pressure) > 2000:
            pressure = pressure / 100.0
        temp = np.asarray(t_values, dtype=float)

        def align(pair):
            levels, vals = np.asarray(pair[0], dtype=float), np.asarray(pair[1], dtype=float)
            finite = np.isfinite(levels) & np.isfinite(vals)
            levels, vals = levels[finite], vals[finite]
            order = np.argsort(levels)
            levels_sorted, vals_sorted = levels[order], vals[order]
            target_order = np.argsort(pressure)
            target_sorted = pressure[target_order]
            interp_sorted = np.interp(target_sorted, levels_sorted, vals_sorted)
            aligned = np.empty_like(target_sorted, dtype=float)
            aligned[target_order] = interp_sorted
            return aligned

        gh = align(profile["gh"])
        u = align(profile["u"])
        v = align(profile["v"])

        def optional_profile(name):
            try:
                return _nearest_profile(_open_profile(path, name), latitude, longitude)
            except Exception:
                return None

        dpt_pair = optional_profile("dpt")
        rh_pair = optional_profile("r")
        q_pair = optional_profile("q")
        rh = align(rh_pair) if rh_pair is not None else None
        if dpt_pair is not None:
            dewpoint = align(dpt_pair)
        elif rh is not None:
            dewpoint = np.asarray(
                dewpoint_from_relative_humidity(
                    temp * units.kelvin, np.clip(rh / 100.0, 0.001, 1.0) * units.dimensionless
                ).to("kelvin").magnitude,
                dtype=float,
            )
        elif q_pair is not None:
            q = align(q_pair)
            dewpoint = np.asarray(
                dewpoint_from_specific_humidity(
                    pressure * units.hPa, specific_humidity=q * units.dimensionless
                ).to("kelvin").magnitude,
                dtype=float,
            )
        else:
            result["__metpy_error"] = "profile_moisture_unavailable"
            return result
        if rh is None:
            rh = np.asarray(
                relative_humidity_from_dewpoint(
                    temp * units.kelvin, dewpoint * units.kelvin
                ).to("dimensionless").magnitude * 100.0,
                dtype=float,
            )

        orog = _nearest(_open_field(path, "surface", "orog", None), latitude, longitude)
        sp = values.get("surface_pressure_pa")
        if orog is None:
            result["__metpy_error"] = "terrain_unavailable"
            return result
        if sp is None:
            result["__metpy_error"] = "surface_pressure_unavailable"
            return result
        heights = gh - float(orog)

        surface_t = values.get("temperature_2m_k")
        surface_td = values.get("dewpoint_2m_k")
        surface_u = values.get("u10_ms")
        surface_v = values.get("v10_ms")
        if surface_t is not None and surface_td is not None:
            pressure = np.concatenate([[float(sp) / 100.0], pressure])
            temp = np.concatenate([[float(surface_t)], temp])
            dewpoint = np.concatenate([[float(surface_td)], dewpoint])
            rh_surface = values.get("rh_2m_pct")
            if rh_surface is not None:
                rh = np.concatenate([[float(rh_surface)], rh])
            else:
                rh = np.concatenate([[float(relative_humidity_from_dewpoint(float(surface_t) * units.kelvin, float(surface_td) * units.kelvin).to("dimensionless").magnitude * 100.0)], rh])
            heights = np.concatenate([[0.0], heights])
            u = np.concatenate([[float(surface_u) if surface_u is not None else u[0]], u])
            v = np.concatenate([[float(surface_v) if surface_v is not None else v[0]], v])

        order = np.argsort(pressure)[::-1]
        pressure = pressure[order]; temp = temp[order]; dewpoint = dewpoint[order]
        rh = rh[order]; u = u[order]; v = v[order]; heights = heights[order]
        mask = np.isfinite(pressure) & np.isfinite(temp) & np.isfinite(dewpoint) & np.isfinite(rh) & np.isfinite(u) & np.isfinite(v) & np.isfinite(heights)
        pressure = pressure[mask]; temp = temp[mask]; dewpoint = dewpoint[mask]; rh = rh[mask]; u = u[mask]; v = v[mask]; heights = heights[mask]
        if len(pressure) < 5:
            return result

        pq = pressure * units.hPa; tq = temp * units.kelvin; tdq = dewpoint * units.kelvin
        uq = u * units("m/s"); vq = v * units("m/s"); hq = heights * units.meter

        def mag(value, unit):
            try:
                return float(value.to(unit).magnitude)
            except Exception:
                return None

        parcel = None
        try:
            parcel = parcel_profile(pq, tq[0], tdq[0])
        except Exception:
            parcel = None

        if values.get("lcl_m") is None:
            try:
                lp, _ = lcl(pq[0], tq[0], tdq[0])
                result["lcl_m"] = _height_from_pressure(mag(lp, units.hPa), pressure, heights)
            except Exception:
                pass
        if values.get("lfc_m") is None:
            try:
                lp, _ = lfc(pq, tq, tdq, parcel_temperature_profile=parcel) if parcel is not None else lfc(pq, tq, tdq)
                result["lfc_m"] = _height_from_pressure(mag(lp, units.hPa), pressure, heights)
            except Exception:
                pass
        if values.get("el_m") is None:
            try:
                ep, _ = el(pq, tq, tdq, parcel_temperature_profile=parcel) if parcel is not None else el(pq, tq, tdq)
                result["el_m"] = _height_from_pressure(mag(ep, units.hPa), pressure, heights)
            except Exception:
                pass

        for func, keyc, keyi in (
            (surface_based_cape_cin, "cape_jkg", "cin_jkg"),
            (mixed_layer_cape_cin, "mlcape_jkg", "mlcin_jkg"),
            (most_unstable_cape_cin, "mucape_jkg", "mucin_jkg"),
        ):
            try:
                cape, cin = func(pq, tq, tdq)
                if values.get(keyc) is None:
                    result[keyc] = mag(cape, units("J/kg"))
                if values.get(keyi) is None:
                    result[keyi] = mag(cin, units("J/kg"))
            except Exception:
                pass
        if values.get("dcape_jkg") is None:
            try:
                result["dcape_jkg"] = mag(downdraft_cape(pq, tq, tdq)[0], units("J/kg"))
            except Exception:
                pass

        for depth, key in ((1, "shear_0_1km_kt"), (3, "shear_0_3km_kt"), (6, "shear_0_6km_kt")):
            try:
                du, dv = bulk_shear(pq, uq, vq, height=hq, depth=depth * units.km)
                su = mag(du, units("m/s")); sv = mag(dv, units("m/s"))
                if su is not None and sv is not None:
                    result[key] = float(np.hypot(su, sv) * 1.943844492)
                    if depth == 6:
                        result["shear_u_0_6km_ms"] = su
                        result["shear_v_0_6km_ms"] = sv
                        result["shear_0_6km_ms"] = float(np.hypot(su, sv))
            except Exception:
                pass

        height_order = np.argsort(heights)
        hs = heights[height_order]; ts = temp[height_order]; us = u[height_order]; vs = v[height_order]; rhs = rh[height_order]
        def layer_mean(values_arr, top_m):
            if hs[0] > 0 or hs[-1] < top_m:
                return None
            mask_layer = (hs >= 0) & (hs <= top_m)
            x = hs[mask_layer]; y = np.asarray(values_arr)[mask_layer]
            if x.size < 2:
                return None
            if x[0] > 0:
                x = np.insert(x, 0, 0.0); y = np.insert(y, 0, np.interp(0.0, hs, values_arr))
            if x[-1] < top_m:
                x = np.append(x, top_m); y = np.append(y, np.interp(top_m, hs, values_arr))
            integrator = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
            return float(integrator(y, x) / top_m)

        result["wind_0_1km_kt"] = (layer_mean(np.hypot(us, vs), 1000.0) * 1.943844492) if layer_mean(np.hypot(us, vs), 1000.0) is not None else None
        result["wind_0_3km_kt"] = (layer_mean(np.hypot(us, vs), 3000.0) * 1.943844492) if layer_mean(np.hypot(us, vs), 3000.0) is not None else None
        if hs[0] <= 0 and hs[-1] >= 3000:
            t0 = float(np.interp(0.0, hs, ts)); t3 = float(np.interp(3000.0, hs, ts))
            result["lapse_rate_0_3km_c_km"] = (t0 - t3) / 3.0
        if hs[0] <= 0 and hs[-1] >= 7500:
            t0 = float(np.interp(0.0, hs, ts)); t75 = float(np.interp(7500.0, hs, ts))
            result["lapse_rate_0_7_5km_c_km"] = (t0 - t75) / 7.5

        try:
            wb = wet_bulb_temperature(pq, tq, tdq).to("degC").magnitude
            wb = np.asarray(wb, dtype=float)[height_order]
            result["wet_bulb_0_3km_c"] = layer_mean(wb, 3000.0)
        except Exception:
            pass
        if values.get("wetbulb_2m_c") is None and surface_t is not None and surface_td is not None:
            try:
                result["wetbulb_2m_c"] = mag(wet_bulb_temperature(float(sp) / 100.0 * units.hPa, float(surface_t) * units.kelvin, float(surface_td) * units.kelvin), units.degC)
            except Exception:
                pass

        if values.get("srh01_m2s2") is None:
            try:
                result["srh01_m2s2"] = mag(storm_relative_helicity(hq, uq, vq, depth=1 * units.km)[2], units("m^2/s^2"))
            except Exception:
                pass
        if values.get("srh03_m2s2") is None:
            try:
                result["srh03_m2s2"] = mag(storm_relative_helicity(hq, uq, vq, depth=3 * units.km)[2], units("m^2/s^2"))
            except Exception:
                pass

        freezing = np.where((ts[:-1] - 273.15) * (ts[1:] - 273.15) <= 0)[0]
        if freezing.size:
            j = int(freezing[0])
            if ts[j + 1] != ts[j]:
                result["freezing_level_m"] = float(hs[j] + (273.15 - ts[j]) * (hs[j + 1] - hs[j]) / (ts[j + 1] - ts[j]))

        try:
            snsq_result = build_snsq_profile(
                hs, np.asarray(pressure)[height_order], ts, np.asarray(dewpoint)[height_order], rhs,
                us, vs, float(sp) / 100.0, surface_t, surface_td,
                surface_rh_pct=values.get("rh_2m_pct"), surface_u_ms=surface_u, surface_v_ms=surface_v,
                wetbulb_2m_c=result.get("wetbulb_2m_c") or values.get("wetbulb_2m_c"),
            )
            result.update({k: v for k, v in snsq_result.items() if v is not None})
            if result.get("cloud_layer_mean_wind_ms") is not None:
                result["cloud_layer_mean_wind_kt"] = float(result["cloud_layer_mean_wind_ms"]) * 1.943844492
            if result.get("cloud_layer_shear_ms") is not None:
                result["cloud_layer_shear_kt"] = float(result["cloud_layer_shear_ms"]) * 1.943844492
        except Exception:
            pass
    except Exception as exc:
        result["__metpy_error"] = f"{type(exc).__name__}: {exc}"
        return result
    return {k: v for k, v in result.items() if v is not None}
def _open_profile(path: Path, short_name: str):
    last_error = None
    for level_type in ("isobaricInhPa", "isobaricInPa"):
        try:
            return _open_field(path, level_type, short_name, None)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return None

def _nearest_profile(ds, latitude, longitude):
    if ds is None or not ds.data_vars:
        return None
    lat_name = next((x for x in ("latitude", "lat") if x in ds.coords), None)
    lon_name = next((x for x in ("longitude", "lon") if x in ds.coords), None)
    level_name = next((x for x in ("isobaricInhPa", "isobaricInPa") if x in ds.coords), None)
    if lat_name is None or lon_name is None or level_name is None:
        return None
    lats = np.asarray(ds[lat_name].values)
    lons = np.asarray(ds[lon_name].values)
    distance = (lats - latitude) ** 2 + ((lons - longitude) * np.cos(np.deg2rad(latitude))) ** 2
    idx = np.unravel_index(np.nanargmin(distance), distance.shape)
    variable = next(iter(ds.data_vars))
    values = np.asarray(ds[variable].values)
    levels = np.asarray(ds[level_name].values, dtype=float).reshape(-1)
    if values.ndim != 3:
        return None
    return levels, values[:, idx[0], idx[1]].astype(float)

def _extract_snsq(path: Path, latitude, longitude, values):
    try:
        profiles = {}
        for name in ("gh", "t", "dpt", "u", "v"):
            result = _nearest_profile(_open_profile(path, name), latitude, longitude)
            if result is None:
                return {"snsq": None, "snsq_status": "profile_missing"}
            profiles[name] = result
        t_level, temp = profiles["t"]
        base_level = np.asarray(t_level, dtype=float)
        def _align(pair):
            levels, vals = np.asarray(pair[0], dtype=float), np.asarray(pair[1], dtype=float)
            if len(levels) == len(base_level) and np.allclose(levels, base_level):
                return np.asarray(vals, dtype=float)
            order = np.argsort(levels)
            return np.interp(base_level, levels[order], np.asarray(vals, dtype=float)[order])
        gh = _align(profiles["gh"])
        dpt = _align(profiles["dpt"])
        u = _align(profiles["u"])
        v = _align(profiles["v"])
        rh_profile = _nearest_profile(_open_profile(path, "r"), latitude, longitude)
        if rh_profile is not None:
            rh = _align(rh_profile)
        else:
            try:
                from metpy.calc import relative_humidity_from_dewpoint
                from metpy.units import units
                rh = (
                    relative_humidity_from_dewpoint(
                        np.asarray(temp, dtype=float) * units.kelvin,
                        np.asarray(dpt, dtype=float) * units.kelvin,
                    ).to("dimensionless").magnitude * 100.0
                )
            except Exception:
                return {"snsq": None, "snsq_status": "profile_rh_unavailable"}
        level = base_level
        orog = _nearest(_open_field(path, "surface", "orog", None), latitude, longitude)
        if orog is None:
            return {"snsq": None, "snsq_status": "terrain_missing"}
        pressure_hpa = level if np.nanmax(level) < 2000 else level / 100.0
        surface_pressure_hpa = float(values["surface_pressure_pa"]) / 100.0 if values.get("surface_pressure_pa") is not None else None
        if surface_pressure_hpa is None:
            return {"snsq": None, "snsq_status": "surface_pressure_missing"}
        wetbulb_2m_c = None
        try:
            if values.get("temperature_2m_k") is not None and values.get("dewpoint_2m_k") is not None:
                from metpy.calc import wet_bulb_temperature
                from metpy.units import units
                wetbulb_2m_c = float(
                    wet_bulb_temperature(
                        surface_pressure_hpa * units.hPa,
                        values["temperature_2m_k"] * units.kelvin,
                        values["dewpoint_2m_k"] * units.kelvin,
                    ).to("degC").magnitude
                )
        except Exception:
            wetbulb_2m_c = None
        result = build_snsq_profile(
            np.asarray(gh, dtype=float) - float(orog),
            pressure_hpa, np.asarray(temp, dtype=float), np.asarray(dpt, dtype=float),
            np.asarray(rh, dtype=float), np.asarray(u, dtype=float), np.asarray(v, dtype=float),
            surface_pressure_hpa, values.get("temperature_2m_k"), values.get("dewpoint_2m_k"),
            surface_rh_pct=values.get("rh_2m_pct"), surface_u_ms=values.get("u10_ms"),
            surface_v_ms=values.get("v10_ms"), wetbulb_2m_c=wetbulb_2m_c,
        )
        result["snsq_status"] = "complete" if result.get("snsq") is not None else "profile_insufficient"
        return result
    except Exception as exc:
        return {"snsq": None, "snsq_status": type(exc).__name__}


def extract_features(
    path: Path,
    latitude: float,
    longitude: float,
    radar_time: datetime,
    expected_valid_time: datetime | None = None,
    allow_future: bool = False,
) -> dict:
    radar_time = radar_time.astimezone(timezone.utc)
    expected_valid_time = (
        expected_valid_time.astimezone(timezone.utc)
        if expected_valid_time is not None else None
    )
    values = {name: None for name in FIELD_SPECS}
    source_valid_time = None
    failures = {}

    for name, (level_type, short_name, level) in FIELD_SPECS.items():
        try:
            ds = _open_field(path, level_type, short_name, level)
            valid = _dataset_valid_time(ds) or expected_valid_time
            if valid is not None:
                if valid > radar_time and not allow_future:
                    raise ValueError(
                        f"future RAP analysis {valid.isoformat()} > "
                        f"radar {radar_time.isoformat()}"
                    )
                source_valid_time = source_valid_time or valid
            values[name] = _nearest(ds, latitude, longitude)
        except Exception as exc:
            failures[name] = type(exc).__name__

    snsq = _extract_snsq(path, latitude, longitude, values)
    values.update(snsq)

    metpy_derived = _metpy_derived_fields(path, latitude, longitude, values)
    metpy_error = metpy_derived.get("__metpy_error")
    metpy_derived_fields = []
    for key, value in metpy_derived.items():
        if key.startswith("__"):
            continue
        if values.get(key) is None and value is not None:
            values[key] = value
            metpy_derived_fields.append(key)

    if values["pwat_mm"] is not None:
        # RAP PWAT is kg m^-2, numerically equivalent to mm of liquid water.
        values["pwat_mm"] = float(values["pwat_mm"])

    shear_u = values.get("shear_u_0_6km_ms")
    shear_v = values.get("shear_v_0_6km_ms")
    values["shear_0_6km_ms"] = (
        float(np.hypot(shear_u, shear_v))
        if shear_u is not None and shear_v is not None else None
    )

    remaining_missing = [name for name in FIELD_SPECS if values.get(name) is None]
    return {
        "source": "RAP",
        "source_valid_time_utc": (
            source_valid_time.isoformat() if source_valid_time else None
        ),
        "age_minutes": (
            (radar_time - source_valid_time).total_seconds() / 60.0
            if source_valid_time else None
        ),
        "fields": values,
        "metpy_derived_fields": sorted(set(metpy_derived_fields)),
        "metpy_status": "error" if metpy_error else ("derived" if metpy_derived_fields else "not_needed"),
        "metpy_error": metpy_error,
        "missing_fields": sorted(remaining_missing),
        "status": "complete" if not remaining_missing else "partial",
    }
