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


def _metpy_derived_fields(path: Path, latitude, longitude, values):
    result = {}
    try:
        from metpy.calc import bulk_shear, downdraft_cape, el, lcl, lfc, surface_based_cape_cin, mixed_layer_cape_cin, most_unstable_cape_cin
        from metpy.units import units
        profiles = {}
        for name in ('gh','t','dpt','u','v'):
            profiles[name] = _nearest_profile(_open_profile(path, name), latitude, longitude)
            if profiles[name] is None:
                return result
        _, temp = profiles['t']
        p = np.asarray(profiles['t'][0], dtype=float)
        def interp_profile(pair):
            lev, val = np.asarray(pair[0],dtype=float), np.asarray(pair[1],dtype=float)
            order = np.argsort(lev)
            return np.interp(p, lev[order], val[order])
        gh = interp_profile(profiles['gh'])
        td = interp_profile(profiles['dpt'])
        u = interp_profile(profiles['u'])
        v = interp_profile(profiles['v'])
        temp = np.asarray(temp,dtype=float)
        orog = _nearest(_open_field(path,'surface','orog',None),latitude,longitude)
        sp = values.get('surface_pressure_pa')
        if orog is None or sp is None:
            return result
        h = gh - float(orog)
        spt = values.get('temperature_2m_k')
        sptd = values.get('dewpoint_2m_k')
        spu, spv = values.get('u10_ms'), values.get('v10_ms')
        if spt is not None and sptd is not None:
            p = np.concatenate([[float(sp)/100.0],p]); temp=np.concatenate([[float(spt)],temp]); td=np.concatenate([[float(sptd)],td]); h=np.concatenate([[0.0],h])
            u=np.concatenate([[float(spu) if spu is not None else u[0]],u]); v=np.concatenate([[float(spv) if spv is not None else v[0]],v])
        order=np.argsort(p)[::-1]; p,temp,td,u,v,h=[np.asarray(x)[order] for x in (p,temp,td,u,v,h)]
        mask=np.isfinite(p)&np.isfinite(temp)&np.isfinite(td)&np.isfinite(u)&np.isfinite(v)&np.isfinite(h)
        p,temp,td,u,v,h=[np.asarray(x)[mask] for x in (p,temp,td,u,v,h)]
        if len(p)<5:return result
        pq=p*units.hPa; tq=temp*units.kelvin; tdq=td*units.kelvin; hq=h*units.meter; uq=u*units('m/s'); vq=v*units('m/s')
        def val(q,unit):
            try:return float(q.to(unit).magnitude)
            except Exception:return None
        if values.get('lcl_m') is None:
            try: result['lcl_m']=_height_from_pressure(val(lcl(pq[0],tq[0],tdq[0])[0],units.hPa),p,h)
            except Exception: pass
        if values.get('lfc_m') is None:
            try: result['lfc_m']=_height_from_pressure(val(lfc(pq,tq,tdq)[0],units.hPa),p,h)
            except Exception: pass
        if values.get('el_m') is None:
            try: result['el_m']=_height_from_pressure(val(el(pq,tq,tdq)[0],units.hPa),p,h)
            except Exception: pass
        if values.get('dcape_jkg') is None:
            try: result['dcape_jkg']=val(downdraft_cape(pq,tq,tdq)[0],units('J/kg'))
            except Exception: pass
        try:
            du,dv=bulk_shear(pq,uq,vq,height=hq,depth=6*units.km)
            result['shear_u_0_6km_ms']=val(du,units('m/s')); result['shear_v_0_6km_ms']=val(dv,units('m/s'))
            result['shear_0_6km_ms']=float(np.hypot(result['shear_u_0_6km_ms'],result['shear_v_0_6km_ms']))
            result['bs06_kt']=result['shear_0_6km_ms']*1.943844492
        except Exception: pass
        hs=np.argsort(h); hh=h[hs]; tt=temp[hs]
        for target,key in ((3000.0,'lr03_Ckm'),(7500.0,'lr75_Ckm')):
            if hh[0]<=0 and hh[-1]>=target:
                t0=float(np.interp(0.0,hh,tt)); tx=float(np.interp(target,hh,tt)); result[key]=(t0-tx)/(target/1000.0)
        if values.get('cape_jkg') is None:
            try: result['cape_jkg']=val(surface_based_cape_cin(pq,tq,tdq)[0],units('J/kg'))
            except Exception: pass
        if values.get('mlcape_jkg') is None:
            try: result['mlcape_jkg']=val(mixed_layer_cape_cin(pq,tq,tdq)[0],units('J/kg'))
            except Exception: pass
        if values.get('mucape_jkg') is None:
            try: result['mucape_jkg']=val(most_unstable_cape_cin(pq,tq,tdq)[0],units('J/kg'))
            except Exception: pass
    except Exception:
        return result
    return {k:v for k,v in result.items() if v is not None}
def _open_profile(path: Path, short_name: str):
    return _open_field(path, "isobaricInhPa", short_name, None)

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
        for name in ("r", "gh", "t", "dpt", "u", "v"):
            result = _nearest_profile(_open_profile(path, name), latitude, longitude)
            if result is None:
                return {"snsq": None, "snsq_status": "profile_missing"}
            profiles[name] = result
        level, rh = profiles["r"]
        gh_level, gh = profiles["gh"]
        t_level, temp = profiles["t"]
        dpt_level, dpt = profiles["dpt"]
        u_level, u = profiles["u"]
        v_level, v = profiles["v"]
        if not all(np.array_equal(level, other) for other in (gh_level, t_level, dpt_level, u_level, v_level)):
            return {"snsq": None, "snsq_status": "profile_level_mismatch"}
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
    values.update({k: v for k, v in _metpy_derived_fields(path, latitude, longitude, values).items() if values.get(k) is None})

    if values["pwat_mm"] is not None:
        # RAP PWAT is kg m^-2, numerically equivalent to mm of liquid water.
        values["pwat_mm"] = float(values["pwat_mm"])

    shear_u = values.get("shear_u_0_6km_ms")
    shear_v = values.get("shear_v_0_6km_ms")
    values["shear_0_6km_ms"] = (
        float(np.hypot(shear_u, shear_v))
        if shear_u is not None and shear_v is not None else None
    )

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
        "missing_fields": sorted(failures),
        "status": "complete" if not failures else "partial",
    }
