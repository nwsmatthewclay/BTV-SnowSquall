"""Research-quality reflectivity object segmentation."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy import ndimage
from skimage.segmentation import watershed


@dataclass(frozen=True)
class ObjectDetectionConfig:
    # Snow-squall candidate threshold follows published convective-snow
    # detection work: Z >= 20 dBZ plus a sharp reflectivity gradient.
    threshold_dbz: float = 20.0
    core_threshold_dbz: float = 30.0
    min_pixels: int = 4
    max_pixels: int = 3000
    gradient_threshold_dbkm: float = 5.0
    min_gradient_fraction: float = 0.03
    min_gradient_pixels: int = 4
    min_background_contrast_db: float = 3.0
    background_ring_pixels: int = 3
    connectivity: int = 2
    smooth_sigma: float = 0.8
    close_iterations: int = 1
    open_iterations: int = 1
    fill_holes: bool = True
    split_merged: bool = True
    preserve_boundary_components: bool = True
    max_boundary_pixels: int = 1200
    min_peak_separation_px: int = 8
    # Secondary dynamical evidence. Thresholds are in knots after conversion
    # from the native Level-II radial-velocity field.
    velocity_rescue_reflectivity_dbz: float = 15.0
    velocity_rescue_contrast_kt: float = 8.0
    velocity_rescue_gradient_ktkm: float = 6.0
    min_candidate_rank_score: float = 0.0
    use_watershed: bool = True
    watershed_seed_dbz: float = 30.0
    watershed_max_dbz: float = 57.0
    watershed_min_distance_px: int = 6
    watershed_min_saliency_pixels: int = 8
    retain_coherent_objects: bool = False
    watershed_min_prominence_db: float = 3.0


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
        peak = float(np.nanmax(local[sy, sx]))
        seeds.append((peak, float(np.mean(sy)), float(np.mean(sx)), int(len(sx))))
    if len(seeds) < 2:
        return [component]

    # Preserve a clearly elongated, laterally extensive band as one object.
    # Multiple embedded cores are useful features, but turning the band into
    # Voronoi fragments creates artificial object identities and hurts tracking.
    cy, cx = np.where(component)
    if len(cx) >= 3:
        bbox_h = float(np.max(cy) - np.min(cy) + 1)
        bbox_w = float(np.max(cx) - np.min(cx) + 1)
        bbox_aspect = max(bbox_h, bbox_w) / max(1.0, min(bbox_h, bbox_w))
        # Only preserve very clearly slender echoes as a single band. More
        # compact broad echoes still get core-seeded separation so distinct
        # embedded cells remain individually identifiable.
        if max(bbox_h, bbox_w) >= 15.0 and bbox_aspect >= 10.0:
            return [component]

    # Keep only genuinely separated cores. Without this guard, a broad snow
    # squall band containing several nearby threshold-crossing pixels can be
    # partitioned into many artificial Voronoi fragments that then become
    # confusing pseudo-tracks.
    seeds.sort(key=lambda s: (-s[0], -s[3], s[1], s[2]))
    selected = []
    min_sep = max(0, int(config.min_peak_separation_px))
    for seed in seeds:
        if all(
            np.hypot(seed[1] - keep[1], seed[2] - keep[2]) >= min_sep
            for keep in selected
        ):
            selected.append(seed)
    if len(selected) < 2:
        return [component]

    centers = np.asarray([(s[1], s[2]) for s in selected], dtype=float)
    points = np.column_stack((yy, xx))
    nearest = np.argmin(
        ((points[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2),
        axis=1,
    )
    pieces = []
    for seed_index in range(len(selected)):
        piece = np.zeros_like(component)
        select = nearest == seed_index
        piece[yy[select], xx[select]] = True
        if int(piece.sum()) >= config.min_pixels:
            pieces.append(piece)
    return pieces or [component]


def _clip01(value, low, high):
    if value is None or not np.isfinite(value) or high <= low:
        return None
    return float(np.clip((float(value) - low) / (high - low), 0.0, 1.0))


def candidate_rank_score(max_reflectivity_dbz, gradient_p90_dbkm, reflectivity_contrast_db, core_fraction, velocity_contrast_kt=None, velocity_gradient_p90_ktkm=None):
    """Deterministic 0–100 detection-quality triage score, not a probability."""
    components = [
        (_clip01(max_reflectivity_dbz, 20.0, 45.0), 30.0),
        (_clip01(gradient_p90_dbkm, 5.0, 12.0), 20.0),
        (_clip01(reflectivity_contrast_db, 3.0, 10.0), 20.0),
        (_clip01(core_fraction, 0.0, 0.25), 15.0),
    ]
    if velocity_contrast_kt is not None and velocity_gradient_p90_ktkm is not None:
        vc = _clip01(velocity_contrast_kt, 8.0, 20.0)
        vg = _clip01(velocity_gradient_p90_ktkm, 6.0, 14.0)
        if vc is not None and vg is not None:
            components.append((0.5 * vc + 0.5 * vg, 15.0))
    usable = [(v,w) for v,w in components if v is not None]
    if not usable:
        return 0.0
    return float(100.0 * sum(v*w for v,w in usable) / sum(w for _,w in usable))


def candidate_rank_tier(score):
    score = float(score)
    if score >= 80: return "priority"
    if score >= 65: return "strong"
    if score >= 50: return "candidate"
    if score >= 35: return "weak"
    return "low"


def detect_reflectivity_objects(reflectivity, config=ObjectDetectionConfig(), velocity=None):
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

    # A broad, relatively uniform snow shield is not treated as a candidate
    # merely because it exceeds the Z threshold. Sharp gradients identify the
    # narrow precipitation enhancements that are most relevant to squalls.
    gradient = np.hypot(
        *np.gradient(work, 1.0, edge_order=1)
    )

    # Radial velocity is a first-class radar signal for object diagnostics and
    # weak-echo recovery, but it is not allowed to create arbitrary velocity
    # objects. Velocity support must be spatially collocated with at least
    # 15 dBZ precipitation so wind-noise regions do not become objects.
    velocity_arr_kt = None
    velocity_gradient = None
    velocity_rescue = np.zeros_like(arr, dtype=bool)
    velocity_rescue_region = np.zeros_like(arr, dtype=bool)
    if velocity is not None:
        velocity_arr = np.asarray(velocity, dtype=float)
        if velocity_arr.shape != arr.shape:
            raise ValueError("velocity must have the same grid shape as reflectivity")
        velocity_finite = np.isfinite(velocity_arr)
        if velocity_finite.any():
            velocity_arr_kt = velocity_arr * 1.94384449244
            velocity_work = np.where(
                velocity_finite,
                velocity_arr_kt,
                np.nanmedian(velocity_arr_kt[velocity_finite]),
            )
            velocity_smoothed = ndimage.gaussian_filter(
                velocity_work, sigma=config.smooth_sigma
            )
            velocity_gradient_smoothed = np.hypot(
                *np.gradient(velocity_smoothed, 1.0, edge_order=1)
            )
            velocity_gradient_raw = np.hypot(
                *np.gradient(velocity_arr_kt, 1.0, edge_order=1)
            )
            # Retain sharp raw velocity boundaries while using the smoothed
            # field for local contrast. This prevents smoothing from erasing
            # narrow coherent wind shifts that are useful for weak-echo rescue.
            velocity_work = velocity_smoothed
            velocity_gradient = np.maximum(
                np.nan_to_num(velocity_gradient_smoothed, nan=0.0),
                np.nan_to_num(velocity_gradient_raw, nan=0.0),
            )
            local_velocity = ndimage.median_filter(
                velocity_work, size=11, mode="nearest"
            )
            velocity_contrast_map = np.abs(velocity_work - local_velocity)
            velocity_rescue = (
                finite
                & (arr >= config.velocity_rescue_reflectivity_dbz)
                & (velocity_contrast_map >= config.velocity_rescue_contrast_kt)
                & (velocity_gradient >= config.velocity_rescue_gradient_ktkm)
            )

            # Treat velocity rescue as evidence for the coherent weak-echo
            # footprint, not as two thin edge-only objects created by the
            # velocity gradient itself. A connected >=15 dBZ precipitation
            # patch is rescued as one region when a meaningful fraction carries
            # the required velocity signature.
            rescue_seed = finite & (arr >= config.velocity_rescue_reflectivity_dbz)
            rescue_labels, rescue_count = ndimage.label(
                rescue_seed,
                structure=ndimage.generate_binary_structure(2, 2),
            )
            for rescue_id in range(1, rescue_count + 1):
                rescue_component = rescue_labels == rescue_id
                fraction = float(np.mean(velocity_rescue[rescue_component]))
                if fraction >= 0.10:
                    velocity_rescue_region |= rescue_component

    # Candidate generation is intentionally separate from severity scoring.
    # ProbSevere first identifies coherent radar objects, then extracts
    # predictors from them. For snow squalls we therefore use a lower
    # reflectivity floor than ProbSevere's 40-dBZ convective threshold while
    # retaining its enhanced-watershed/local-maximum concept.
    if velocity_arr_kt is not None:
        mask = finite & (
            (work >= config.threshold_dbz)
            | velocity_rescue_region
            | velocity_rescue
        )
    else:
        mask = finite & (work >= config.threshold_dbz)

    structure = ndimage.generate_binary_structure(2, config.connectivity)
    if config.close_iterations:
        mask = ndimage.binary_closing(mask, structure=structure, iterations=config.close_iterations)
    if config.open_iterations:
        mask = ndimage.binary_opening(mask, structure=structure, iterations=config.open_iterations)
    if config.fill_holes:
        mask = ndimage.binary_fill_holes(mask)
    if velocity_arr_kt is not None:
        mask |= velocity_rescue

    if config.preserve_boundary_components:
        raw_labels, raw_count = ndimage.label(raw_mask, structure=structure)
        boundary = np.zeros_like(raw_mask, dtype=bool)
        if raw_count:
            edge_ids = set(np.unique(np.concatenate([
                raw_labels[0, :], raw_labels[-1, :],
                raw_labels[:, 0], raw_labels[:, -1],
            ])).tolist())
            edge_ids.discard(0)
            for raw_id in edge_ids:
                component = raw_labels == raw_id
                pixels = int(component.sum())
                if pixels < config.min_pixels:
                    continue
                if pixels <= config.max_boundary_pixels:
                    boundary |= component
                elif int(np.sum(arr[component] >= config.core_threshold_dbz)) >= 4:
                    boundary |= component
        mask |= boundary

    if config.use_watershed:
        # Seed from separated local maxima, then let the reflectivity field
        # determine the footprint. This is much closer to w2segmotionll than
        # labeling one threshold-connected blob and then trying to split it.
        seed_field = np.where(mask, np.minimum(work, config.watershed_max_dbz), -np.inf)
        neighborhood = max(3, 2 * int(config.watershed_min_distance_px) + 1)
        local_high = ndimage.maximum_filter(
            np.where(np.isfinite(seed_field), seed_field, -np.inf),
            size=neighborhood, mode="nearest"
        )
        local_low = ndimage.minimum_filter(
            np.where(np.isfinite(seed_field), seed_field, np.inf),
            size=neighborhood, mode="nearest"
        )
        # Require local prominence so a flat 20–25 dBZ snow shield does not
        # become dozens of watershed seeds. This is the key distinction
        # between a coherent precipitation area and a trackable embedded cell.
        local_max = (
            np.isfinite(seed_field)
            & (seed_field >= float(config.watershed_seed_dbz))
            & (seed_field == local_high)
            & ((seed_field - local_low) >= float(config.watershed_min_prominence_db))
        )
        coords = np.argwhere(local_max)
        if coords.size:
            peaks = sorted(
                [(float(seed_field[y, x]), int(y), int(x)) for y, x in coords],
                key=lambda item: (-item[0], item[1], item[2]),
            )
            markers = np.zeros_like(arr, dtype=np.int32)
            selected = []
            min_sep = max(1, int(config.watershed_min_distance_px))
            for peak, y, x in peaks:
                if all(np.hypot(y - sy, x - sx) >= min_sep for _, sy, sx in selected):
                    selected.append((peak, y, x))
            for marker_id, (_, y, x) in enumerate(selected, start=1):
                markers[y, x] = marker_id
            if selected:
                labels = watershed(
                    -np.nan_to_num(work, nan=-999.0),
                    markers,
                    mask=mask,
                    watershed_line=False,
                )
                count = int(labels.max())
            else:
                labels, count = ndimage.label(mask, structure=structure)
        else:
            labels, count = ndimage.label(mask, structure=structure)
    else:
        labels, count = ndimage.label(mask, structure=structure)
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

            piece_gradient = gradient[piece]
            piece_gradient = piece_gradient[np.isfinite(piece_gradient)]
            gradient_fraction = (
                float(np.mean(piece_gradient >= config.gradient_threshold_dbkm))
                if piece_gradient.size else 0.0
            )
            gradient_p90 = (
                float(np.percentile(piece_gradient,90))
                if piece_gradient.size else np.nan
            )

            # Compare the object to a small surrounding ring. This suppresses
            # broad uniform echoes while retaining embedded convective cells or
            # narrow bands that may not have very high absolute reflectivity.
            dilated = ndimage.binary_dilation(
                piece,
                iterations=max(1,int(config.background_ring_pixels)),
            )
            ring = dilated & ~piece & finite
            ring_values = arr[ring]
            ring_values = ring_values[np.isfinite(ring_values)]
            background_dbz = (
                float(np.median(ring_values))
                if ring_values.size else np.nan
            )
            object_median_dbz = float(np.median(valid_values))
            contrast_db = (
                object_median_dbz - background_dbz
                if np.isfinite(background_dbz) else np.nan
            )

            gradient_good = (
                int(np.sum(piece_gradient >= config.gradient_threshold_dbkm))
                >= max(
                    config.min_gradient_pixels,
                    int(np.ceil(len(xx) * config.min_gradient_fraction)),
                )
            )
            contrast_good = (
                np.isfinite(contrast_db)
                and contrast_db >= config.min_background_contrast_db
            )
            core_good = int(np.sum(valid_values >= config.core_threshold_dbz)) >= 2

            velocity_values = (
                velocity_arr_kt[piece]
                if velocity_arr_kt is not None else np.asarray([], dtype=float)
            )
            velocity_values = velocity_values[np.isfinite(velocity_values)]
            velocity_mean_kt = float(np.mean(velocity_values)) if velocity_values.size else np.nan
            velocity_std_kt = float(np.std(velocity_values)) if velocity_values.size else np.nan
            velocity_p90_abs_kt = (
                float(np.percentile(np.abs(velocity_values), 90))
                if velocity_values.size else np.nan
            )
            velocity_gradient_values = (
                velocity_gradient[piece]
                if velocity_gradient is not None else np.asarray([], dtype=float)
            )
            velocity_gradient_values = velocity_gradient_values[np.isfinite(velocity_gradient_values)]
            velocity_gradient_p90_ktkm = (
                float(np.percentile(velocity_gradient_values, 90))
                if velocity_gradient_values.size else np.nan
            )
            velocity_background_kt = np.nan
            velocity_contrast_kt = np.nan
            if velocity_arr_kt is not None:
                velocity_dilated = ndimage.binary_dilation(
                    piece,
                    iterations=max(1, int(config.background_ring_pixels)),
                )
                velocity_ring = (
                    velocity_dilated & ~piece & np.isfinite(velocity_arr_kt)
                )
                velocity_ring_values = velocity_arr_kt[velocity_ring]
                velocity_ring_values = velocity_ring_values[np.isfinite(velocity_ring_values)]
                if velocity_ring_values.size and velocity_values.size:
                    velocity_background_kt = float(np.median(velocity_ring_values))
                    velocity_contrast_kt = float(
                        abs(np.median(velocity_values) - velocity_background_kt)
                    )
            velocity_support_fraction = (
                float(np.mean(velocity_rescue[piece]))
                if velocity_arr_kt is not None and len(xx)
                else 0.0
            )
            velocity_good = velocity_support_fraction >= 0.20
            velocity_structure_good = bool(
                velocity_arr_kt is not None
                and np.isfinite(velocity_contrast_kt)
                and np.isfinite(velocity_gradient_p90_ktkm)
                and (
                    velocity_contrast_kt >= config.velocity_rescue_contrast_kt
                    or velocity_gradient_p90_ktkm >= config.velocity_rescue_gradient_ktkm
                )
            )

            bbox_h = int(np.max(yy) - np.min(yy) + 1)
            bbox_w = int(np.max(xx) - np.min(xx) + 1)
            bbox_aspect_ratio = (
                max(bbox_h, bbox_w) / max(1.0, min(bbox_h, bbox_w))
            )
            object_mode = (
                "band"
                if max(bbox_h, bbox_w) >= 15 and bbox_aspect_ratio >= 3.0
                else "cell_cluster"
            )

            # Candidate generation only: event truth remains downstream.
            # Every coherent reflectivity object is retained; gradient,
            # contrast, core and velocity are diagnostic evidence rather than
            # hard gates. This prevents the detector from silently discarding
            # real echoes simply because they are broad or slowly varying.
            detection_evidence = []
            if gradient_good:
                detection_evidence.append("reflectivity_gradient")
            if contrast_good:
                detection_evidence.append("reflectivity_contrast")
            if core_good:
                detection_evidence.append("reflectivity_core")
            if velocity_good:
                detection_evidence.append("velocity_rescue")
            elif velocity_structure_good:
                detection_evidence.append("velocity_structure")
            if not detection_evidence and not config.retain_coherent_objects:
                continue
            if not detection_evidence:
                detection_evidence.append("reflectivity_object")

            core_fraction = float(np.sum(valid_values >= config.core_threshold_dbz)) / max(1, len(xx))
            rank_score = candidate_rank_score(
                float(np.nanmax(valid_values)), gradient_p90, contrast_db, core_fraction,
                velocity_contrast_kt if np.isfinite(velocity_contrast_kt) else None,
                velocity_gradient_p90_ktkm if np.isfinite(velocity_gradient_p90_ktkm) else None,
            )
            if rank_score < float(config.min_candidate_rank_score):
                continue
            objects.append({
                "object_id":next_id,
                "pixel_count":int(len(xx)),
                "row_centroid":float(np.mean(yy)),
                "column_centroid":float(np.mean(xx)),
                "max_reflectivity_dbz":float(np.nanmax(valid_values)),
                "mean_reflectivity_dbz":float(np.nanmean(valid_values)),
                "core_pixel_count":int(np.sum(valid_values>=config.core_threshold_dbz)),
                "reflectivity_gradient_p90_dbkm":gradient_p90,
                "gradient_fraction_above_5dbkm":gradient_fraction,
                "background_reflectivity_dbz":background_dbz,
                "reflectivity_contrast_db":contrast_db,
                "bbox_aspect_ratio":float(bbox_aspect_ratio),
                "object_mode":object_mode,
                "velocity_mean_kt":velocity_mean_kt,
                "velocity_std_kt":velocity_std_kt,
                "velocity_p90_abs_kt":velocity_p90_abs_kt,
                "velocity_gradient_p90_ktkm":velocity_gradient_p90_ktkm,
                "velocity_background_kt":velocity_background_kt,
                "velocity_contrast_kt":velocity_contrast_kt,
                "velocity_rescue":velocity_good,
                "velocity_support_fraction":velocity_support_fraction,
                "velocity_structure":velocity_structure_good,
                "detection_evidence":detection_evidence,
                "candidate_rank_score":rank_score,
                "candidate_rank_tier":candidate_rank_tier(rank_score),
                "detection_method":"probsevere_style_enhanced_watershed" if config.use_watershed else "connected_component",
                "watershed_seed_dbz":float(config.watershed_seed_dbz),
                "touches_grid_edge":bool(yy.min()==0 or xx.min()==0 or yy.max()==arr.shape[0]-1 or xx.max()==arr.shape[1]-1),
                "row_indices":yy.tolist(),
                "column_indices":xx.tolist(),
            })
            next_id+=1
    return objects
