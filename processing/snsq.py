"""Snow Squall Parameter (SNSQ) calculation.

Implements the Banacos et al. composite from its three diagnosed 0-2 km
ingredients. Inputs are intentionally explicit so the caller can supply
provider-appropriate profile diagnostics without hiding interpolation or
missing-data decisions.
"""
from __future__ import annotations

import math


def snow_squall_parameter(
    mean_rh_0_2km_pct,
    thetae_delta_0_2km_k,
    mean_wind_0_2km_ms,
    wetbulb_2m_c=None,
):
    """Return SNSQ plus its ingredient factors.

    The published formulation multiplies:
      moisture = (RH - 60) / 15
      instability = (4 - delta_theta-e) / 4
      wind = mean 0-2 km wind / 9 m/s

    Negative moisture/instability factors are floored at zero. When a
    2-m wet-bulb value is supplied, values above 1 C are also zeroed,
    consistent with the operational cold-enough-for-snow guard.
    """
    values = (
        mean_rh_0_2km_pct,
        thetae_delta_0_2km_k,
        mean_wind_0_2km_ms,
    )
    if any(v is None or not math.isfinite(float(v)) for v in values):
        return {
            "snsq": None,
            "moisture_factor": None,
            "instability_factor": None,
            "wind_factor": None,
            "snow_temperature_pass": None,
        }

    rh = float(mean_rh_0_2km_pct)
    dthetae = float(thetae_delta_0_2km_k)
    wind = float(mean_wind_0_2km_ms)

    moisture = max(0.0, (rh - 60.0) / 15.0)
    instability = max(0.0, (4.0 - dthetae) / 4.0)
    wind_factor = max(0.0, wind / 9.0)

    temp_pass = True
    if wetbulb_2m_c is not None:
        temp_pass = math.isfinite(float(wetbulb_2m_c)) and float(wetbulb_2m_c) <= 1.0

    value = moisture * instability * wind_factor if temp_pass else 0.0

    return {
        "snsq": float(value),
        "moisture_factor": float(moisture),
        "instability_factor": float(instability),
        "wind_factor": float(wind_factor),
        "snow_temperature_pass": bool(temp_pass),
    }
