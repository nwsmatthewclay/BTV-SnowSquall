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
    preserve_boundary_components: bool = True
    min_peak_separation_px: int = 8


def _core_seed_split(component, field, config):
    """Split a broad echo by separated reflectivity cores.

    Snow squall bands can be elongated and contiguous while containing one or
    more stronger embedded elements. Core-seeded partitioning preserves a
    single broad band when there is one core, while separating genuinely
    distinct embedded echoes.
    """
    yy, xx = np.where(component)
    if len(xx) == 0:
        return []
    local = np.asarray(field, dtype=float)
    core = component & np.isfinite(local) & (local >= config.core_threshold_dbz)
    seed_labels, count = ndimage.label(
        core, structure=ndimage.generate_binary_structure(2, 2)
    )
    seeds = []
    for seed_id in range(1, count + 1):
        sy, sx = np.where(seed_labels == seed_id)
        if len(sx) < 2:
            continue
        seeds.append((float(np.mean(sy)), float(np.mean(sx))))
    if len(seeds) < 2:
        return [component]

    points = np.column_stack((yy, xx))
    centers = np.asarray(seeds)
    nearest = np.argmin(
        ((points[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2),
        axis=1,
    )
    pieces = []
    for seed_index in range(len(seeds)):
        piece = np.zeros_like(component)
        select = nearest == seed_index
        piece[yy[select], xx[select]] = True
        if int(piece.sum()) >= config.min_pixels:
            pieces.append(piece)
    return pieces or [component]


def detect_reflectivity_objects(reflectivity, config=ObjectDetectionConfig()):
    arr=np.asarray(reflectivity,dtype=float)
    finite=np.isfinite(arr)
    if not finite.any():
        return []
    # Preserve the unsmoothed threshold mask for edge-component recovery.
    # Gaussian smoothing can attenuate a small echo that touches the grid edge
    # even though the original radar field contains a valid threshold-exceeding
    # component that should remain trackable.
    raw_mask = finite & (arr >= config.threshold_dbz)
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

    if config.preserve_boundary_components:
        raw_labels, raw_count = ndimage.label(raw_mask, structure=structure)
        boundary = np.zeros_like(raw_mask, dtype=bool)
        if raw_count:
            edge_ids = set(np.unique(np.concatenate([
                raw_labels[0, :],
                raw_labels[-1, :],
                raw_labels[:, 0],
                raw_labels[:, -1],
            ])).tolist())
            edge_ids.discard(0)
            for raw_id in edge_ids:
                component = raw_labels == raw_id
                if int(component.sum()) >= config.min_pixels:
                    boundary |= component
        mask |= boundary

    labels,count=ndimage.label(mask,structure=structure)
    objects=[]
    next_id=1
    for label_id in range(1,count+1):
        component=(labels==label_id)
        pixels=int(component.sum())
        if pixels<config.min_pixels:
            continue
        pieces=_core_seed_split(component,work,config) if config.split_merged else [component]
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
