"""Profile-based Snow Squall Parameter diagnostics."""
from __future__ import annotations

import numpy as np

from processing.snsq import snow_squall_parameter


def _finite_profile(*arrays):
    arrays=[np.asarray(a,dtype=float).reshape(-1) for a in arrays]
    mask=np.ones(arrays[0].shape,dtype=bool)
    for a in arrays: mask &= np.isfinite(a)
    return [a[mask] for a in arrays]


def _interp_at(height_m, heights, values, target=2000.0, tolerance=350.0):
    heights=np.asarray(heights,dtype=float)
    values=np.asarray(values,dtype=float)
    order=np.argsort(heights)
    heights=heights[order]; values=values[order]
    if len(heights)<1: return None
    exact=np.where(np.isclose(heights,target,atol=1.0))[0]
    if exact.size: return float(values[exact[0]])
    lower=np.where(heights<target)[0]
    upper=np.where(heights>target)[0]
    if lower.size and upper.size:
        i=lower[-1]; j=upper[0]
        if heights[j]-heights[i] <= 900:
            return float(np.interp(target,[heights[i],heights[j]],[values[i],values[j]]))
    nearest=int(np.argmin(np.abs(heights-target)))
    return float(values[nearest]) if abs(heights[nearest]-target)<=tolerance else None


def _height_weighted_mean(heights, values):
    heights=np.asarray(heights,dtype=float); values=np.asarray(values,dtype=float)
    if len(heights)<2: return None
    order=np.argsort(heights); heights=heights[order]; values=values[order]
    span=float(heights[-1]-heights[0])
    if span<=0: return None
    integrator = np.trapezoid if hasattr(np, 'trapezoid') else np.trapz
    return float(integrator(values, heights) / span)


def _thetae_fallback(pressure_hpa, temperature_k, dewpoint_k):
    """Approximate equivalent potential temperature for dependency fallback."""
    p = float(pressure_hpa)
    t = float(temperature_k)
    td = float(dewpoint_k)
    if min(p, t, td) <= 0:
        raise ValueError('nonphysical thermodynamic input')
    epsilon = 0.622
    e_hpa = 6.112 * np.exp(17.67 * (td - 273.15) / (td - 29.65))
    mixing_ratio = epsilon * e_hpa / max(1e-6, p - e_hpa)
    theta = t * (1000.0 / p) ** 0.2854
    return theta * np.exp((2.5e6 * mixing_ratio) / (1004.0 * t))
def build_snsq_profile(
    heights_m, pressure_hpa, temperature_k, dewpoint_k, rh_pct, u_ms, v_ms,
    surface_pressure_hpa, surface_temperature_k, surface_dewpoint_k,
    surface_rh_pct=None, surface_u_ms=None, surface_v_ms=None, wetbulb_2m_c=None,
):
    heights_m, pressure_hpa, temperature_k, dewpoint_k, rh_pct, u_ms, v_ms = _finite_profile(
        heights_m, pressure_hpa, temperature_k, dewpoint_k, rh_pct, u_ms, v_ms
    )
    if len(heights_m)<2 or surface_pressure_hpa is None or surface_temperature_k is None or surface_dewpoint_k is None:
        return {"snsq":None,"mean_rh_0_2km_pct":None,"thetae_delta_0_2km_k":None,"mean_wind_0_2km_ms":None,"wetbulb_2m_c":wetbulb_2m_c}
    keep=(heights_m>=0.0)&(heights_m<=2200.0)&np.isfinite(pressure_hpa)
    heights_m=heights_m[keep]; pressure_hpa=pressure_hpa[keep]; temperature_k=temperature_k[keep]; dewpoint_k=dewpoint_k[keep]; rh_pct=rh_pct[keep]; u_ms=u_ms[keep]; v_ms=v_ms[keep]
    if len(heights_m)<2: return {"snsq":None,"mean_rh_0_2km_pct":None,"thetae_delta_0_2km_k":None,"mean_wind_0_2km_ms":None,"wetbulb_2m_c":wetbulb_2m_c}
    if surface_rh_pct is not None and surface_u_ms is not None and surface_v_ms is not None:
        heights_m=np.concatenate([[0.0],heights_m])
        pressure_hpa=np.concatenate([[float(surface_pressure_hpa)],pressure_hpa])
        temperature_k=np.concatenate([[float(surface_temperature_k)],temperature_k])
        dewpoint_k=np.concatenate([[float(surface_dewpoint_k)],dewpoint_k])
        rh_pct=np.concatenate([[float(surface_rh_pct)],rh_pct])
        u_ms=np.concatenate([[float(surface_u_ms)],u_ms])
        v_ms=np.concatenate([[float(surface_v_ms)],v_ms])
    mean_mask = heights_m <= 2000.0
    mean_heights = heights_m[mean_mask]
    mean_rh_values = rh_pct[mean_mask]
    mean_u = u_ms[mean_mask]
    mean_v = v_ms[mean_mask]
    mean_rh = _height_weighted_mean(mean_heights, mean_rh_values)
    mean_wind = _height_weighted_mean(mean_heights, np.hypot(mean_u, mean_v))
    td2=_interp_at(heights_m,heights_m,dewpoint_k)
    t2=_interp_at(heights_m,heights_m,temperature_k)
    p2=_interp_at(heights_m,heights_m,pressure_hpa)
    if td2 is None or t2 is None or p2 is None: return {"snsq":None,"mean_rh_0_2km_pct":mean_rh,"thetae_delta_0_2km_k":None,"mean_wind_0_2km_ms":mean_wind,"wetbulb_2m_c":wetbulb_2m_c}
    try:
        from metpy.calc import equivalent_potential_temperature
        from metpy.units import units
        thetae_surface=equivalent_potential_temperature(
            float(surface_pressure_hpa)*units.hPa, float(surface_temperature_k)*units.kelvin, float(surface_dewpoint_k)*units.kelvin
        ).to('kelvin').magnitude
        thetae_2km=equivalent_potential_temperature(
            float(p2)*units.hPa, float(t2)*units.kelvin, float(td2)*units.kelvin
        ).to('kelvin').magnitude
        delta=float(thetae_2km-thetae_surface)
    except Exception:
        try:
            thetae_surface = _thetae_fallback(surface_pressure_hpa, surface_temperature_k, surface_dewpoint_k)
            thetae_2km = _thetae_fallback(p2, t2, td2)
            delta = float(thetae_2km - thetae_surface)
        except Exception:
            return {"snsq":None,"mean_rh_0_2km_pct":mean_rh,"thetae_delta_0_2km_k":None,"mean_wind_0_2km_ms":mean_wind,"wetbulb_2m_c":wetbulb_2m_c}
    # Penn State Schneider et al. (2024) cloud-layer diagnostic:
    # cloud-layer top is the height where theta-e becomes 2 K greater
    # than the surface value. This is calculated from the same current
    # RAP profile and therefore remains safe for live use.
    cloud_layer_depth_m = None
    cloud_layer_rh_pct = None
    cloud_layer_mean_wind_ms = None
    cloud_layer_shear_ms = None
    try:
        from metpy.calc import equivalent_potential_temperature
        from metpy.units import units
        thetae_profile = equivalent_potential_temperature(
            pressure_hpa * units.hPa,
            temperature_k * units.kelvin,
            dewpoint_k * units.kelvin,
        ).to('kelvin').magnitude
        surface_thetae = equivalent_potential_temperature(
            float(surface_pressure_hpa) * units.hPa,
            float(surface_temperature_k) * units.kelvin,
            float(surface_dewpoint_k) * units.kelvin,
        ).to('kelvin').magnitude
        target_thetae = float(surface_thetae) + 2.0
        order = np.argsort(heights_m)
        h = heights_m[order]
        th = np.asarray(thetae_profile)[order]
        rh_sorted = rh_pct[order]
        u_sorted = u_ms[order]
        v_sorted = v_ms[order]
        crossings = np.where((th[:-1] - target_thetae) * (th[1:] - target_thetae) <= 0)[0]
        if crossings.size:
            idx = int(crossings[0])
            h0, h1 = float(h[idx]), float(h[idx + 1])
            th0, th1 = float(th[idx]), float(th[idx + 1])
            if h1 > h0 and th1 != th0:
                top = h0 + (target_thetae - th0) * (h1 - h0) / (th1 - th0)
            else:
                top = h1
            if top > 0:
                cloud_layer_depth_m = float(top)
                layer_mask = h <= top
                layer_h = np.concatenate([h[layer_mask], [top]])
                layer_rh = np.concatenate([rh_sorted[layer_mask], [np.interp(top, h, rh_sorted)]])
                layer_u = np.concatenate([u_sorted[layer_mask], [np.interp(top, h, u_sorted)]])
                layer_v = np.concatenate([v_sorted[layer_mask], [np.interp(top, h, v_sorted)]])
                cloud_layer_rh_pct = _height_weighted_mean(layer_h, layer_rh)
                cloud_layer_mean_wind_ms = _height_weighted_mean(layer_h, np.hypot(layer_u, layer_v))
                top_u = float(layer_u[-1])
                top_v = float(layer_v[-1])
                surface_u = float(u_sorted[0])
                surface_v = float(v_sorted[0])
                cloud_layer_shear_ms = float(np.hypot(top_u - surface_u, top_v - surface_v))
    except Exception:
        pass

    result=snow_squall_parameter(mean_rh,delta,mean_wind,wetbulb_2m_c=wetbulb_2m_c)
    result.update({
        'mean_rh_0_2km_pct':float(mean_rh),
        'thetae_delta_0_2km_k':delta,
        'mean_wind_0_2km_ms':float(mean_wind),
        'wetbulb_2m_c':wetbulb_2m_c,
        'cloud_layer_depth_m':cloud_layer_depth_m,
        'cloud_layer_rh_pct':cloud_layer_rh_pct,
        'cloud_layer_mean_wind_ms':cloud_layer_mean_wind_ms,
        'cloud_layer_shear_ms':cloud_layer_shear_ms,
    })
    return result
