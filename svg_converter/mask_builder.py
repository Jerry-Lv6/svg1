"""Baseline and connectivity-constrained foreground mask construction."""

from __future__ import annotations

import math
from numbers import Real
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


DEFAULT_STRONG_THRESHOLD = 128
DEFAULT_WEAK_THRESHOLD = 240
DEFAULT_LOCAL_WINDOW = 15
DEFAULT_MIN_LOCAL_CONTRAST = 12.0
DEFAULT_MIN_COMPONENT_PIXELS = 12
DEFAULT_MIN_PRINCIPAL_SPAN = 18.0
DEFAULT_MIN_ELONGATION = 2.0
DEFAULT_MIN_COMPONENT_MEAN_CONTRAST = 12.0
DEFAULT_FAINT_GRAY_MAX = 254
DEFAULT_FAINT_MIN_LOCAL_CONTRAST = 1.0
DEFAULT_SOURCE_MIN_COMPONENT_PIXELS = 6
DEFAULT_SOURCE_MIN_AXIS_SPAN = 10.0
DEFAULT_SOURCE_MIN_ELONGATION = 1.2
DEFAULT_SOURCE_MIN_COMPONENT_MEAN_CONTRAST = 2.0
DEFAULT_CURVE_MIN_PIXELS = 8
DEFAULT_CURVE_MAX_PIXELS = 19
DEFAULT_CURVE_MIN_SPAN = 7.0
DEFAULT_CURVE_MAX_SPAN = 11.0
DEFAULT_CURVE_MAX_TRANSVERSE_RMS = 1.6
DEFAULT_CURVE_MIN_QUADRATIC_GAIN = 0.30
DEFAULT_CURVE_MIN_NORMALIZED_CURVATURE = 0.45
DEFAULT_CURVE_MIN_MEAN_CONTRAST = 20.0
DEFAULT_MAX_HOLE_AREA = 10
DEFAULT_BACKGROUND_CONNECTIVITY = 8
CONNECTIVITY_MASK_KEYS = (
    "strong",
    "weak_candidate",
    "candidate",
    "accepted_weak",
    "rejected_weak",
    "final",
)
INDEPENDENT_TEXTURE_MASK_KEYS = (
    "strong",
    "weak_candidate",
    "candidate",
    "accepted_connected_weak",
    "connectivity_final",
    "rejected_before_independent",
    "accepted_independent_weak",
    "rejected_independent_weak",
    "final",
)
SOURCE_SUPPORTED_MASK_KEYS = INDEPENDENT_TEXTURE_MASK_KEYS[:-1] + (
    "v031_final",
    "faint_source_support",
    "accepted_source_supported_stroke",
    "rejected_after_source_supported_stroke",
    "final",
)
LOCAL_CURVATURE_MASK_KEYS = SOURCE_SUPPORTED_MASK_KEYS[:-1] + (
    "v033_final",
    "residual_source_support",
    "accepted_local_curvature_curve",
    "rejected_after_local_curvature",
    "final",
)
SMALL_HOLE_FILL_MASK_KEYS = (
    "v034_final",
    "accepted_small_white_holes",
    "rejected_background",
    "v035_final",
    "final",
)


def build_baseline_mask(
    gray: np.ndarray,
    threshold: int = 128,
) -> np.ndarray:
    """Return a boolean foreground mask using one fixed global threshold."""
    if isinstance(threshold, (bool, np.bool_)) or not isinstance(
        threshold, (int, np.integer)
    ):
        raise TypeError("Threshold must be an integer from 0 to 255")
    if not 0 <= int(threshold) <= 255:
        raise ValueError("Threshold must be from 0 to 255")
    if not isinstance(gray, np.ndarray):
        raise TypeError("Grayscale image must be a NumPy array")
    if gray.ndim != 2:
        raise ValueError("Grayscale image must be two-dimensional")
    if gray.dtype != np.uint8:
        raise ValueError("Grayscale image dtype must be uint8")

    return gray <= threshold


def validate_connectivity_parameters(
    strong_threshold: int,
    weak_threshold: int,
    local_window: int,
    min_local_contrast: float,
) -> None:
    """Validate the single global v0.3.0 connectivity parameter set."""
    for name, value in (
        ("strong_threshold", strong_threshold),
        ("weak_threshold", weak_threshold),
        ("local_window", local_window),
    ):
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, np.integer)
        ):
            raise TypeError(f"{name} must be an integer")

    strong_threshold = int(strong_threshold)
    weak_threshold = int(weak_threshold)
    local_window = int(local_window)
    if not 0 <= strong_threshold < weak_threshold <= 254:
        raise ValueError("Thresholds must satisfy 0 <= strong < weak <= 254")
    if local_window < 3 or local_window % 2 == 0:
        raise ValueError("local_window must be an odd integer greater than or equal to 3")
    if isinstance(min_local_contrast, (bool, np.bool_)) or not isinstance(
        min_local_contrast, Real
    ):
        raise TypeError("min_local_contrast must be a real number")
    if not math.isfinite(float(min_local_contrast)) or min_local_contrast <= 0:
        raise ValueError("min_local_contrast must be finite and greater than zero")


def build_connectivity_mask(
    gray: np.ndarray,
    strong_threshold: int = DEFAULT_STRONG_THRESHOLD,
    weak_threshold: int = DEFAULT_WEAK_THRESHOLD,
    local_window: int = DEFAULT_LOCAL_WINDOW,
    min_local_contrast: float = DEFAULT_MIN_LOCAL_CONTRAST,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Build one final mask from strong seeds and connected weak candidates."""
    if not isinstance(gray, np.ndarray):
        raise TypeError("Grayscale image must be a NumPy array")
    if gray.ndim != 2:
        raise ValueError("Grayscale image must be two-dimensional")
    if gray.dtype != np.uint8:
        raise ValueError("Grayscale image dtype must be uint8")
    if gray.shape[0] <= 0 or gray.shape[1] <= 0:
        raise ValueError("Grayscale image dimensions must be greater than zero")
    validate_connectivity_parameters(
        strong_threshold,
        weak_threshold,
        local_window,
        min_local_contrast,
    )

    gray_float = gray.astype(np.float32)
    strong = gray <= int(strong_threshold)
    local_background = cv2.boxFilter(
        gray_float,
        ddepth=-1,
        ksize=(int(local_window), int(local_window)),
        normalize=True,
        borderType=cv2.BORDER_REFLECT,
    )
    local_contrast = local_background - gray_float
    weak_candidate = (
        (gray > int(strong_threshold))
        & (gray <= int(weak_threshold))
        & (local_contrast >= float(min_local_contrast))
    )
    candidate = strong | weak_candidate

    _, labels = cv2.connectedComponents(
        candidate.astype(np.uint8),
        connectivity=8,
    )
    strong_labels = np.unique(labels[strong])
    strong_labels = strong_labels[strong_labels != 0]
    final = np.isin(labels, strong_labels)
    accepted_weak = final & weak_candidate
    rejected_weak = weak_candidate & ~final

    masks = {
        "strong": strong,
        "weak_candidate": weak_candidate,
        "candidate": candidate,
        "accepted_weak": accepted_weak,
        "rejected_weak": rejected_weak,
        "final": final,
    }
    return final, masks


def validate_independent_texture_parameters(
    min_component_pixels: int,
    min_principal_span: float,
    min_elongation: float,
    min_component_mean_contrast: float,
) -> None:
    """Validate the one frozen v0.3.1 component-selection parameter set."""
    if isinstance(min_component_pixels, (bool, np.bool_)) or not isinstance(
        min_component_pixels, (int, np.integer)
    ):
        raise TypeError("min_component_pixels must be an integer")
    if int(min_component_pixels) <= 0:
        raise ValueError("min_component_pixels must be greater than zero")
    for name, value in (
        ("min_principal_span", min_principal_span),
        ("min_elongation", min_elongation),
        ("min_component_mean_contrast", min_component_mean_contrast),
    ):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
            raise TypeError(f"{name} must be a real number")
        if not math.isfinite(float(value)) or float(value) <= 0:
            raise ValueError(f"{name} must be finite and greater than zero")


def _component_features(
    rejected: np.ndarray,
    local_contrast: np.ndarray,
) -> tuple[np.ndarray, list[dict[str, float | int]]]:
    """Return fixed 8-neighborhood labels and the four approved features."""
    component_count, labels = cv2.connectedComponents(
        rejected.astype(np.uint8), connectivity=8
    )
    features: list[dict[str, float | int]] = []
    for component_id in range(1, component_count):
        ys, xs = np.nonzero(labels == component_id)
        pixel_count = int(xs.size)
        if pixel_count == 1:
            principal_span = 1.0
            elongation = 1.0
        else:
            coordinates = np.column_stack((xs, ys)).astype(np.float64)
            centered = coordinates - coordinates.mean(axis=0)
            covariance = centered.T @ centered / pixel_count
            eigenvalues, eigenvectors = np.linalg.eigh(covariance)
            eigenvalues = np.maximum(eigenvalues, 0.0)
            major = eigenvectors[:, int(np.argmax(eigenvalues))]
            projections = centered @ major
            principal_span = float(projections.max() - projections.min() + 1.0)
            major_value = float(eigenvalues.max())
            minor_value = float(eigenvalues.min())
            elongation = math.sqrt(
                (major_value + 1.0 / 12.0) / (minor_value + 1.0 / 12.0)
            )
        features.append(
            {
                "component_id": component_id,
                "pixel_count": pixel_count,
                "principal_span": principal_span,
                "elongation": elongation,
                "mean_local_contrast": float(local_contrast[ys, xs].mean()),
            }
        )
    return labels, features


def build_independent_texture_mask(
    gray: np.ndarray,
    strong_threshold: int = DEFAULT_STRONG_THRESHOLD,
    weak_threshold: int = DEFAULT_WEAK_THRESHOLD,
    local_window: int = DEFAULT_LOCAL_WINDOW,
    min_local_contrast: float = DEFAULT_MIN_LOCAL_CONTRAST,
    min_component_pixels: int = DEFAULT_MIN_COMPONENT_PIXELS,
    min_principal_span: float = DEFAULT_MIN_PRINCIPAL_SPAN,
    min_elongation: float = DEFAULT_MIN_ELONGATION,
    min_component_mean_contrast: float = DEFAULT_MIN_COMPONENT_MEAN_CONTRAST,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Conservatively restore elongated components rejected by v0.3.0."""
    connectivity_final, connectivity = build_connectivity_mask(
        gray,
        strong_threshold,
        weak_threshold,
        local_window,
        min_local_contrast,
    )
    validate_independent_texture_parameters(
        min_component_pixels,
        min_principal_span,
        min_elongation,
        min_component_mean_contrast,
    )

    gray_float = gray.astype(np.float32)
    local_background = cv2.boxFilter(
        gray_float,
        ddepth=-1,
        ksize=(int(local_window), int(local_window)),
        normalize=True,
        borderType=cv2.BORDER_REFLECT,
    )
    local_contrast = local_background - gray_float
    rejected_before_independent = connectivity["rejected_weak"]
    labels, features = _component_features(
        rejected_before_independent, local_contrast
    )
    accepted_ids = [
        int(feature["component_id"])
        for feature in features
        if int(feature["pixel_count"]) >= int(min_component_pixels)
        and float(feature["principal_span"]) >= float(min_principal_span)
        and float(feature["elongation"]) >= float(min_elongation)
        and float(feature["mean_local_contrast"])
        >= float(min_component_mean_contrast)
    ]
    accepted_independent_weak = (
        np.isin(labels, accepted_ids) & rejected_before_independent
    )
    rejected_independent_weak = (
        rejected_before_independent & ~accepted_independent_weak
    )
    final = connectivity_final | accepted_independent_weak
    masks = {
        "strong": connectivity["strong"],
        "weak_candidate": connectivity["weak_candidate"],
        "candidate": connectivity["candidate"],
        "accepted_connected_weak": connectivity["accepted_weak"],
        "connectivity_final": connectivity_final,
        "rejected_before_independent": rejected_before_independent,
        "accepted_independent_weak": accepted_independent_weak,
        "rejected_independent_weak": rejected_independent_weak,
        "final": final,
    }
    return final, masks


def validate_source_supported_parameters(
    faint_gray_max: int,
    faint_min_local_contrast: float,
    min_component_pixels: int,
    min_axis_span: float,
    min_elongation: float,
    min_component_mean_contrast: float,
) -> None:
    """Validate the single frozen v0.3.3 source-supported parameter set."""
    if isinstance(faint_gray_max, (bool, np.bool_)) or not isinstance(
        faint_gray_max, (int, np.integer)
    ):
        raise TypeError("faint_gray_max must be an integer")
    if not 129 <= int(faint_gray_max) <= 254:
        raise ValueError("faint_gray_max must be from 129 to 254")
    if isinstance(min_component_pixels, (bool, np.bool_)) or not isinstance(
        min_component_pixels, (int, np.integer)
    ):
        raise TypeError("min_component_pixels must be an integer")
    if int(min_component_pixels) <= 0:
        raise ValueError("min_component_pixels must be greater than zero")
    for name, value in (
        ("faint_min_local_contrast", faint_min_local_contrast),
        ("min_axis_span", min_axis_span),
        ("min_elongation", min_elongation),
        ("min_component_mean_contrast", min_component_mean_contrast),
    ):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
            raise TypeError(f"{name} must be a real number")
        if not math.isfinite(float(value)) or float(value) <= 0:
            raise ValueError(f"{name} must be finite and greater than zero")


def _one_pixel_halo(mask: np.ndarray) -> np.ndarray:
    """Return a fixed 8-neighbour exclusion halo without morphology calls."""
    halo = mask.copy()
    height, width = mask.shape
    for dy, dx in (
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1), (0, 1),
        (1, -1), (1, 0), (1, 1),
    ):
        source_y0 = max(0, -dy)
        source_y1 = min(height, height - dy)
        source_x0 = max(0, -dx)
        source_x1 = min(width, width - dx)
        halo[
            source_y0 + dy:source_y1 + dy,
            source_x0 + dx:source_x1 + dx,
        ] |= mask[source_y0:source_y1, source_x0:source_x1]
    return halo


def _select_source_components(
    support: np.ndarray,
    local_contrast: np.ndarray,
    min_component_pixels: int,
    min_axis_span: float,
    min_elongation: float,
    min_component_mean_contrast: float,
) -> np.ndarray:
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        support.astype(np.uint8), connectivity=8
    )
    flat_labels = labels.ravel()
    ys, xs = np.indices(labels.shape)
    counts = np.bincount(flat_labels, minlength=component_count).astype(np.float64)
    safe_counts = np.maximum(counts, 1.0)
    sum_x = np.bincount(flat_labels, weights=xs.ravel(), minlength=component_count)
    sum_y = np.bincount(flat_labels, weights=ys.ravel(), minlength=component_count)
    sum_xx = np.bincount(flat_labels, weights=(xs * xs).ravel(), minlength=component_count)
    sum_yy = np.bincount(flat_labels, weights=(ys * ys).ravel(), minlength=component_count)
    sum_xy = np.bincount(flat_labels, weights=(xs * ys).ravel(), minlength=component_count)
    mean_x = sum_x / safe_counts
    mean_y = sum_y / safe_counts
    var_x = np.maximum(sum_xx / safe_counts - mean_x * mean_x, 0.0)
    var_y = np.maximum(sum_yy / safe_counts - mean_y * mean_y, 0.0)
    cov_xy = sum_xy / safe_counts - mean_x * mean_y
    trace = var_x + var_y
    discriminant = np.sqrt(
        np.maximum((var_x - var_y) ** 2 + 4.0 * cov_xy ** 2, 0.0)
    )
    major = np.maximum((trace + discriminant) / 2.0, 0.0)
    minor = np.maximum((trace - discriminant) / 2.0, 0.0)
    elongation = np.sqrt((major + 1.0 / 12.0) / (minor + 1.0 / 12.0))
    axis_span = np.maximum(stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT])
    contrast_sum = np.bincount(
        flat_labels, weights=local_contrast.ravel(), minlength=component_count
    )
    mean_contrast = contrast_sum / safe_counts
    accepted_flags = (
        (counts >= int(min_component_pixels))
        & (axis_span >= float(min_axis_span))
        & (elongation >= float(min_elongation))
        & (mean_contrast >= float(min_component_mean_contrast))
    )
    accepted_flags[0] = False
    return np.isin(labels, np.flatnonzero(accepted_flags)) & support


def build_source_supported_stroke_mask(
    gray: np.ndarray,
    strong_threshold: int = DEFAULT_STRONG_THRESHOLD,
    weak_threshold: int = DEFAULT_WEAK_THRESHOLD,
    local_window: int = DEFAULT_LOCAL_WINDOW,
    min_local_contrast: float = DEFAULT_MIN_LOCAL_CONTRAST,
    independent_min_component_pixels: int = DEFAULT_MIN_COMPONENT_PIXELS,
    min_principal_span: float = DEFAULT_MIN_PRINCIPAL_SPAN,
    independent_min_elongation: float = DEFAULT_MIN_ELONGATION,
    independent_min_component_mean_contrast: float = DEFAULT_MIN_COMPONENT_MEAN_CONTRAST,
    faint_gray_max: int = DEFAULT_FAINT_GRAY_MAX,
    faint_min_local_contrast: float = DEFAULT_FAINT_MIN_LOCAL_CONTRAST,
    min_component_pixels: int = DEFAULT_SOURCE_MIN_COMPONENT_PIXELS,
    min_axis_span: float = DEFAULT_SOURCE_MIN_AXIS_SPAN,
    min_elongation: float = DEFAULT_SOURCE_MIN_ELONGATION,
    min_component_mean_contrast: float = DEFAULT_SOURCE_MIN_COMPONENT_MEAN_CONTRAST,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Restore complete source-supported weak stroke components over v0.3.1."""
    if not isinstance(gray, np.ndarray):
        raise TypeError("Grayscale image must be a NumPy array")
    if gray.ndim != 2:
        raise ValueError("Grayscale image must be two-dimensional")
    if gray.dtype != np.uint8:
        raise ValueError("Grayscale image dtype must be uint8")
    if gray.shape[0] <= 0 or gray.shape[1] <= 0:
        raise ValueError("Grayscale image dimensions must be greater than zero")
    validate_source_supported_parameters(
        faint_gray_max,
        faint_min_local_contrast,
        min_component_pixels,
        min_axis_span,
        min_elongation,
        min_component_mean_contrast,
    )
    v031_final, old = build_independent_texture_mask(
        gray,
        strong_threshold,
        weak_threshold,
        local_window,
        min_local_contrast,
        independent_min_component_pixels,
        min_principal_span,
        independent_min_elongation,
        independent_min_component_mean_contrast,
    )
    gray_float = gray.astype(np.float32)
    local_background = cv2.boxFilter(
        gray_float,
        ddepth=-1,
        ksize=(int(local_window), int(local_window)),
        normalize=True,
        borderType=cv2.BORDER_REFLECT,
    )
    local_contrast = local_background - gray_float
    faint_source_support = (
        (gray > int(strong_threshold))
        & (gray <= int(faint_gray_max))
        & (local_contrast >= float(faint_min_local_contrast))
        & ~_one_pixel_halo(v031_final)
    )
    accepted = _select_source_components(
        faint_source_support,
        local_contrast,
        min_component_pixels,
        min_axis_span,
        min_elongation,
        min_component_mean_contrast,
    )
    final = v031_final | accepted
    masks = {name: value for name, value in old.items() if name != "final"}
    masks.update({
        "v031_final": v031_final,
        "faint_source_support": faint_source_support,
        "accepted_source_supported_stroke": accepted,
        "rejected_after_source_supported_stroke": (
            old["rejected_independent_weak"] & ~accepted
        ),
        "final": final,
    })
    return final, masks


def validate_local_curvature_parameters(
    min_curve_pixels: int,
    max_curve_pixels: int,
    min_curve_span: float,
    max_curve_span: float,
    max_transverse_rms: float,
    min_quadratic_gain: float,
    min_normalized_curvature: float,
    min_curve_mean_contrast: float,
) -> None:
    """Validate the single frozen v0.3.4 short-curve parameter set."""
    for name, value in (
        ("min_curve_pixels", min_curve_pixels),
        ("max_curve_pixels", max_curve_pixels),
    ):
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, np.integer)
        ):
            raise TypeError(f"{name} must be an integer")
        if int(value) <= 0:
            raise ValueError(f"{name} must be greater than zero")
    if int(min_curve_pixels) > int(max_curve_pixels):
        raise ValueError("min_curve_pixels must not exceed max_curve_pixels")

    for name, value in (
        ("min_curve_span", min_curve_span),
        ("max_curve_span", max_curve_span),
        ("max_transverse_rms", max_transverse_rms),
        ("min_normalized_curvature", min_normalized_curvature),
        ("min_curve_mean_contrast", min_curve_mean_contrast),
    ):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
            raise TypeError(f"{name} must be a real number")
        if not math.isfinite(float(value)) or float(value) <= 0:
            raise ValueError(f"{name} must be finite and greater than zero")
    if float(min_curve_span) > float(max_curve_span):
        raise ValueError("min_curve_span must not exceed max_curve_span")
    if isinstance(min_quadratic_gain, (bool, np.bool_)) or not isinstance(
        min_quadratic_gain, Real
    ):
        raise TypeError("min_quadratic_gain must be a real number")
    if not math.isfinite(float(min_quadratic_gain)) or not 0.0 <= float(
        min_quadratic_gain
    ) <= 1.0:
        raise ValueError("min_quadratic_gain must be finite and from 0 to 1")


def _local_curvature_features(
    support: np.ndarray,
    local_contrast: np.ndarray,
) -> tuple[np.ndarray, list[dict[str, float | int | bool]]]:
    """Measure fixed PCA and quadratic-fit features for 8-neighbour components."""
    _, labels = cv2.connectedComponents(support.astype(np.uint8), connectivity=8)
    ys, xs = np.nonzero(labels)
    if xs.size == 0:
        return labels, []
    ids = labels[ys, xs]
    contrast_values = local_contrast[ys, xs]
    order = np.argsort(ids, kind="stable")
    ids = ids[order]
    xs = xs[order].astype(np.float64)
    ys = ys[order].astype(np.float64)
    contrast_values = contrast_values[order]
    starts = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    ends = np.r_[starts[1:], ids.size]
    features: list[dict[str, float | int | bool]] = []
    for start, end in zip(starts, ends):
        component_id = int(ids[start])
        component_x = xs[start:end]
        component_y = ys[start:end]
        pixel_count = int(end - start)
        coordinates = np.column_stack((component_x, component_y))
        centered = coordinates - coordinates.mean(axis=0)
        valid_fit = pixel_count >= 3 and np.linalg.matrix_rank(centered) >= 2
        principal_span = 0.0
        transverse_rms = 0.0
        line_mse = 0.0
        quadratic_mse = 0.0
        quadratic_gain = 0.0
        normalized_curvature = 0.0
        if valid_fit:
            covariance = centered.T @ centered / pixel_count
            eigenvalues, eigenvectors = np.linalg.eigh(covariance)
            major = eigenvectors[:, int(np.argmax(eigenvalues))]
            minor = eigenvectors[:, int(np.argmin(eigenvalues))]
            u = centered @ major
            v = centered @ minor
            principal_span = float(u.max() - u.min() + 1.0)
            line_mse = float(np.mean(v * v))
            transverse_rms = math.sqrt(max(line_mse, 0.0))
            design = np.column_stack((u * u, u, np.ones_like(u)))
            valid_fit = np.linalg.matrix_rank(design) == 3 and line_mse > 1.0e-6
            if valid_fit:
                coefficients, _, _, _ = np.linalg.lstsq(design, v, rcond=None)
                residual = v - design @ coefficients
                quadratic_mse = float(np.mean(residual * residual))
                quadratic_gain = max(
                    0.0, min(1.0, (line_mse - quadratic_mse) / line_mse)
                )
                normalized_curvature = float(
                    abs(coefficients[0]) * principal_span
                )
                valid_fit = all(
                    math.isfinite(value)
                    for value in (
                        principal_span,
                        transverse_rms,
                        line_mse,
                        quadratic_mse,
                        quadratic_gain,
                        normalized_curvature,
                    )
                )
        features.append({
            "component_id": component_id,
            "pixel_count": pixel_count,
            "principal_span": principal_span,
            "transverse_rms": transverse_rms,
            "line_mse": line_mse,
            "quadratic_mse": quadratic_mse,
            "quadratic_gain": quadratic_gain,
            "normalized_curvature": normalized_curvature,
            "mean_local_contrast": float(contrast_values[start:end].mean()),
            "valid_fit": bool(valid_fit),
        })
    return labels, features


def build_local_curvature_short_curve_mask(
    gray: np.ndarray,
    strong_threshold: int = DEFAULT_STRONG_THRESHOLD,
    weak_threshold: int = DEFAULT_WEAK_THRESHOLD,
    local_window: int = DEFAULT_LOCAL_WINDOW,
    min_local_contrast: float = DEFAULT_MIN_LOCAL_CONTRAST,
    independent_min_component_pixels: int = DEFAULT_MIN_COMPONENT_PIXELS,
    min_principal_span: float = DEFAULT_MIN_PRINCIPAL_SPAN,
    independent_min_elongation: float = DEFAULT_MIN_ELONGATION,
    independent_min_component_mean_contrast: float = DEFAULT_MIN_COMPONENT_MEAN_CONTRAST,
    faint_gray_max: int = DEFAULT_FAINT_GRAY_MAX,
    faint_min_local_contrast: float = DEFAULT_FAINT_MIN_LOCAL_CONTRAST,
    source_min_component_pixels: int = DEFAULT_SOURCE_MIN_COMPONENT_PIXELS,
    min_axis_span: float = DEFAULT_SOURCE_MIN_AXIS_SPAN,
    source_min_elongation: float = DEFAULT_SOURCE_MIN_ELONGATION,
    source_min_component_mean_contrast: float = DEFAULT_SOURCE_MIN_COMPONENT_MEAN_CONTRAST,
    min_curve_pixels: int = DEFAULT_CURVE_MIN_PIXELS,
    max_curve_pixels: int = DEFAULT_CURVE_MAX_PIXELS,
    min_curve_span: float = DEFAULT_CURVE_MIN_SPAN,
    max_curve_span: float = DEFAULT_CURVE_MAX_SPAN,
    max_transverse_rms: float = DEFAULT_CURVE_MAX_TRANSVERSE_RMS,
    min_quadratic_gain: float = DEFAULT_CURVE_MIN_QUADRATIC_GAIN,
    min_normalized_curvature: float = DEFAULT_CURVE_MIN_NORMALIZED_CURVATURE,
    min_curve_mean_contrast: float = DEFAULT_CURVE_MIN_MEAN_CONTRAST,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Add only short curved residual components to the frozen v0.3.3 mask."""
    validate_local_curvature_parameters(
        min_curve_pixels,
        max_curve_pixels,
        min_curve_span,
        max_curve_span,
        max_transverse_rms,
        min_quadratic_gain,
        min_normalized_curvature,
        min_curve_mean_contrast,
    )
    v033_final, old = build_source_supported_stroke_mask(
        gray,
        strong_threshold,
        weak_threshold,
        local_window,
        min_local_contrast,
        independent_min_component_pixels,
        min_principal_span,
        independent_min_elongation,
        independent_min_component_mean_contrast,
        faint_gray_max,
        faint_min_local_contrast,
        source_min_component_pixels,
        min_axis_span,
        source_min_elongation,
        source_min_component_mean_contrast,
    )
    gray_float = gray.astype(np.float32)
    local_background = cv2.boxFilter(
        gray_float,
        ddepth=-1,
        ksize=(int(local_window), int(local_window)),
        normalize=True,
        borderType=cv2.BORDER_REFLECT,
    )
    local_contrast = local_background - gray_float
    residual = old["faint_source_support"] & ~old[
        "accepted_source_supported_stroke"
    ]
    labels, features = _local_curvature_features(residual, local_contrast)
    accepted_ids = [
        int(row["component_id"])
        for row in features
        if row["valid_fit"]
        and int(min_curve_pixels) <= row["pixel_count"] <= int(max_curve_pixels)
        and float(min_curve_span) <= row["principal_span"] <= float(max_curve_span)
        and row["transverse_rms"] <= float(max_transverse_rms)
        and row["quadratic_gain"] >= float(min_quadratic_gain)
        and row["normalized_curvature"] >= float(min_normalized_curvature)
        and row["mean_local_contrast"] >= float(min_curve_mean_contrast)
    ]
    accepted = np.isin(labels, accepted_ids) & residual
    rejected = residual & ~accepted
    final = v033_final | accepted
    masks = {name: value for name, value in old.items() if name != "final"}
    masks.update({
        "v033_final": v033_final,
        "residual_source_support": residual,
        "accepted_local_curvature_curve": accepted,
        "rejected_after_local_curvature": rejected,
        "final": final,
    })
    return final, masks


def fill_small_enclosed_background_holes(
    foreground_mask: np.ndarray,
    max_hole_area: int = DEFAULT_MAX_HOLE_AREA,
    background_connectivity: int = DEFAULT_BACKGROUND_CONNECTIVITY,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Fill complete non-border background components up to one fixed area."""
    if not isinstance(foreground_mask, np.ndarray):
        raise TypeError("Foreground mask must be a NumPy array")
    if foreground_mask.ndim != 2:
        raise ValueError("Foreground mask must be two-dimensional")
    if foreground_mask.dtype != np.bool_:
        raise ValueError("Foreground mask dtype must be bool")
    if foreground_mask.shape[0] <= 0 or foreground_mask.shape[1] <= 0:
        raise ValueError("Foreground mask dimensions must be greater than zero")
    if isinstance(max_hole_area, (bool, np.bool_)) or not isinstance(
        max_hole_area, (int, np.integer)
    ):
        raise TypeError("max_hole_area must be an integer")
    if int(max_hole_area) <= 0:
        raise ValueError("max_hole_area must be greater than zero")
    if isinstance(background_connectivity, (bool, np.bool_)) or not isinstance(
        background_connectivity, (int, np.integer)
    ):
        raise TypeError("background_connectivity must be an integer")
    if int(background_connectivity) not in (4, 8):
        raise ValueError("background_connectivity must be 4 or 8")

    v034_final = foreground_mask.copy()
    background = ~v034_final
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        background.astype(np.uint8),
        connectivity=int(background_connectivity),
    )
    border_ids = np.unique(
        np.concatenate(
            (labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1])
        )
    )
    areas = stats[:, cv2.CC_STAT_AREA]
    accepted_flags = (
        (np.arange(component_count) != 0)
        & (areas >= 1)
        & (areas <= int(max_hole_area))
        & ~np.isin(np.arange(component_count), border_ids)
    )
    accepted_ids = np.flatnonzero(accepted_flags)
    accepted = np.isin(labels, accepted_ids) & background
    rejected = background & ~accepted
    final = v034_final | accepted
    masks = {
        "v034_final": v034_final,
        "accepted_small_white_holes": accepted,
        "rejected_background": rejected,
        "v035_final": final,
        "final": final,
    }
    return final, masks


def save_mask_bmp(
    foreground_mask: np.ndarray,
    output_path: Path,
) -> None:
    """Save and verify one black-foreground, white-background 1-bit BMP."""
    if not isinstance(foreground_mask, np.ndarray):
        raise TypeError("Foreground mask must be a NumPy array")
    if foreground_mask.ndim != 2:
        raise ValueError("Foreground mask must be two-dimensional")
    if foreground_mask.dtype != np.bool_:
        raise ValueError("Foreground mask dtype must be bool")
    if foreground_mask.shape[0] <= 0 or foreground_mask.shape[1] <= 0:
        raise ValueError("Foreground mask dimensions must be greater than zero")

    pixels = np.where(foreground_mask, 0, 255).astype(np.uint8)
    bitmap = Image.fromarray(pixels).convert("1", dither=Image.Dither.NONE)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bitmap.save(output_path, format="BMP")

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise OSError(f"Mask BMP was not created: {output_path}")

    with Image.open(output_path) as saved:
        if saved.mode != "1":
            raise ValueError(f"Saved mask is not a 1-bit BMP: {output_path}")
        if saved.size != (foreground_mask.shape[1], foreground_mask.shape[0]):
            raise ValueError(f"Saved mask dimensions do not match input: {output_path}")
        restored = np.array(saved.convert("L"), dtype=np.uint8)

    values = set(np.unique(restored).tolist())
    if not values.issubset({0, 255}):
        raise ValueError(f"Saved mask contains non-binary pixels: {output_path}")
    if not np.all(restored[foreground_mask] == 0):
        raise ValueError(f"Saved mask foreground is not black: {output_path}")
    if not np.all(restored[~foreground_mask] == 255):
        raise ValueError(f"Saved mask background is not white: {output_path}")
