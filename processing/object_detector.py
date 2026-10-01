"""Research-quality reflectivity object segmentation."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy import ndimage


@dataclass(frozen=True)
class ObjectDetectionConfig:
    threshold_dbz: float = 25.0
    core_threshold_dbz: float = 35.0
    min_pixels: int = 24
    max_pixels: int = 12000
    connectivity: int = 2
    smooth_sigma: float = 0.8
    close_iterations: int = 1
    open_iterations: int = 1
    fill_holes: bool = True
    split_merged: bool = True
    min_peak_separation_px: int = 8


def _watershed_split(mask, field, config):
    # Avoid a dependency on skimage: identify separated local maxima, then
    # assign connected pixels to the nearest peak. This is intentionally
    # conservative and only splits broad, multi-core blobs.
    distance=ndimage.distance_transform_edt(mask)
    maxf=ndimage.maximum_filter(distance,size=max(3,config.min_peak_separation_px*2+1))
    peaks=(distance==maxf)&(distance>=config.min_peak_separation_px/2)
    peak_labels,n=ndimage.label(peaks,structure=ndimage.generate_binary_structure(2,2))
    if n<2:
        return [mask]
    centers=[]
    for i in range(1,n+1):
        yy,xx=np.where(peak_labels==i)
        if len(xx):
            centers.append((float(np.mean(yy)),float(np.mean(xx))))
    if len(centers)<2:
        return [mask]
    yy,xx=np.where(mask)
    pts=np.column_stack([yy,xx])
    c=np.asarray(centers)
    nearest=np.argmin(((pts[:,None,:]-c[None,:,:])**2).sum(axis=2),axis=1)
    pieces=[]
    for i in range(len(centers)):
        piece=np.zeros_like(mask)
        sel=nearest==i
        piece[yy[sel],xx[sel]]=True
        if piece.sum()>=config.min_pixels:
            pieces.append(piece)
    return pieces or [mask]


def detect_reflectivity_objects(reflectivity, config=ObjectDetectionConfig()):
    arr=np.asarray(reflectivity,dtype=float)
    finite=np.isfinite(arr)
    if not finite.any():
        return []
    work=np.where(finite,arr,np.nanmedian(arr[finite]))
    work=ndimage.gaussian_filter(work,sigma=config.smooth_sigma)
    mask=finite&(work>=config.threshold_dbz)
    structure=ndimage.generate_binary_structure(2,config.connectivity)
    if config.close_iterations:
        mask=ndimage.binary_closing(mask,structure=structure,iterations=config.close_iterations)
    if config.open_iterations:
        mask=ndimage.binary_opening(mask,structure=structure,iterations=config.open_iterations)
    if config.fill_holes:
        mask=ndimage.binary_fill_holes(mask)

    labels,count=ndimage.label(mask,structure=structure)
    objects=[]
    next_id=1
    for label_id in range(1,count+1):
        component=(labels==label_id)
        pixels=int(component.sum())
        if pixels<config.min_pixels:
            continue
        pieces=_watershed_split(component,work,config) if config.split_merged else [component]
        for piece in pieces:
            yy,xx=np.where(piece)
            if len(xx)<config.min_pixels or len(xx)>config.max_pixels:
                continue
            values=arr[yy,xx]
            valid_values=values[np.isfinite(values)]
            if valid_values.size==0:
                continue
            objects.append({
                "object_id":next_id,
                "pixel_count":int(len(xx)),
                "row_centroid":float(np.mean(yy)),
                "column_centroid":float(np.mean(xx)),
                "max_reflectivity_dbz":float(np.nanmax(valid_values)),
                "mean_reflectivity_dbz":float(np.nanmean(valid_values)),
                "core_pixel_count":int(np.sum(valid_values>=config.core_threshold_dbz)),
                "touches_grid_edge":bool(yy.min()==0 or xx.min()==0 or yy.max()==arr.shape[0]-1 or xx.max()==arr.shape[1]-1),
                "row_indices":yy.tolist(),
                "column_indices":xx.tolist(),
            })
            next_id+=1
    return objects
