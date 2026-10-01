"""Estimate bulk storm motion directly from successive radar reflectivity fields."""
from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.signal import fftconvolve


def _prepare(field, threshold_dbz=15.0):
    arr=np.asarray(field,dtype=float)
    finite=np.isfinite(arr)
    if not finite.any():
        return None
    filled=np.where(finite,arr,np.nanmedian(arr[finite]))
    smooth=ndimage.gaussian_filter(filled,sigma=1.0)
    anomaly=np.maximum(smooth-threshold_dbz,0.0)
    if np.nanmax(anomaly)<=0:
        return None
    # Normalize so a broad bright echo does not overwhelm the shift estimate.
    scale=np.nanpercentile(anomaly[anomaly>0],[50,95])
    ref=max(float(scale[1]-scale[0]),1.0)
    return np.clip((anomaly-scale[0])/ref,0.0,4.0)


def estimate_radar_storm_motion(previous, current, dt_minutes, spacing_km=1.0,
                                 threshold_dbz=15.0, max_shift_km=120.0):
    """Estimate a domain bulk displacement using reflectivity pattern correlation.

    Positive row shift is southward; positive column shift is eastward.
    Returns a dict with grid motion and meteorological speed/direction.
    """
    if dt_minutes is None or not np.isfinite(dt_minutes) or dt_minutes<=0:
        return None
    a=_prepare(previous,threshold_dbz)
    b=_prepare(current,threshold_dbz)
    if a is None or b is None or a.shape!=b.shape:
        return None

    win=np.isfinite(a)&np.isfinite(b)
    if win.mean()<0.10:
        return None
    a=np.where(win,a,0.0)
    b=np.where(win,b,0.0)
    a-=a.mean(); b-=b.mean()

    corr=fftconvolve(b,a[::-1,::-1],mode="same")
    # Restrict to physically plausible domain shifts.
    cy,cx=np.array(corr.shape)//2
    radius=max(1,int(max_shift_km/max(spacing_km,0.01)))
    yy0=max(0,cy-radius); yy1=min(corr.shape[0],cy+radius+1)
    xx0=max(0,cx-radius); xx1=min(corr.shape[1],cx+radius+1)
    sub=corr[yy0:yy1,xx0:xx1]
    if not np.isfinite(sub).any():
        return None
    sy,sx=np.unravel_index(np.nanargmax(sub),sub.shape)
    shift_row=float(yy0+sy-cy)
    shift_col=float(xx0+sx-cx)
    max_allowed=max_shift_km/max(spacing_km,0.01)
    if np.hypot(shift_row,shift_col)>max_allowed:
        return None

    distance_km=float(np.hypot(shift_row,shift_col)*spacing_km)
    speed_kt=distance_km/(dt_minutes/60.0)/1.852
    # Grid rows increase southward; meteorological direction is travel-to.
    u_east=shift_col*spacing_km/(dt_minutes/60.0)
    v_north=-shift_row*spacing_km/(dt_minutes/60.0)
    direction=(np.degrees(np.arctan2(u_east,v_north))+360.0)%360.0

    peak=float(corr[yy0+sy,xx0+sx])
    center=float(corr[cy,cx])
    confidence=float(max(0.0,min(1.0,(peak-center)/(abs(peak)+1e-6))))
    return {
        "radar_motion_row_per_min": float(shift_row/dt_minutes),
        "radar_motion_column_per_min": float(shift_col/dt_minutes),
        "radar_motion_distance_km": distance_km,
        "radar_motion_speed_kt": float(speed_kt),
        "radar_motion_direction_deg": float(direction),
        "radar_motion_u_kt": float(u_east / 1.852),
        "radar_motion_v_kt": float(v_north / 1.852),
        "radar_motion_confidence": confidence,
    }


def attach_radar_storm_motion(previous, current, dt_minutes, spacing_km=1.0, **kwargs):
    motion=estimate_radar_storm_motion(previous,current,dt_minutes,spacing_km,**kwargs)
    return motion or {
        "radar_motion_row_per_min": np.nan,
        "radar_motion_column_per_min": np.nan,
        "radar_motion_distance_km": np.nan,
        "radar_motion_speed_kt": np.nan,
        "radar_motion_direction_deg": np.nan,
        "radar_motion_u_kt": np.nan,
        "radar_motion_v_kt": np.nan,
        "radar_motion_confidence": 0.0,
    }
