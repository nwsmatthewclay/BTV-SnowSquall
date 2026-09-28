"""Dual-polarization feature calculations."""
from __future__ import annotations
import numpy as np

def summarize_dualpol(zdr=None, rhohv=None, kdp=None):
    def stats(values):
        if values is None:
            return {"mean": np.nan, "p10": np.nan, "p90": np.nan}
        a = np.asarray(values, dtype=float)
        a = a[np.isfinite(a)]
        if not a.size:
            return {"mean": np.nan, "p10": np.nan, "p90": np.nan}
        return {"mean": float(np.mean(a)), "p10": float(np.percentile(a, 10)),
                "p90": float(np.percentile(a, 90))}
    return {"zdr": stats(zdr), "rhohv": stats(rhohv), "kdp": stats(kdp)}

def melting_layer_flag(rhohv, threshold=0.92):
    if rhohv is None:
        return False
    a = np.asarray(rhohv, dtype=float)
    a = a[np.isfinite(a)]
    return bool(a.size and np.nanmin(a) < threshold)
