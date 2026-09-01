"""Public one-step Python API for the frozen v0.3.6 SVG package."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import tempfile

from .image_io import SUPPORTED_SUFFIXES, discover_inputs, load_grayscale
from .mask_builder import (
    build_local_curvature_short_curve_mask,
    fill_small_enclosed_background_holes,
    save_mask_bmp,
)
from .svg_postprocess import repair_svg
from .toolchain import rasterize_svg, run_potrace, validate_svg, validate_toolchain


STANDARD_SIZE = (2048, 2048)


class ConversionError(RuntimeError):
    """A single input could not be converted."""


class NamingConflictError(ConversionError):
    """Two input files would map to the same SVG filename."""


@dataclass(frozen=True)
class BatchFailure:
    input_path: Path
    reason: str


@dataclass(frozen=True)
class BatchResult:
    input_count: int
    success_count: int
    failure_count: int
    output_paths: tuple[Path, ...]
    failures: tuple[BatchFailure, ...]

    @property
    def all_succeeded(self) -> bool:
        return self.failure_count == 0


def _build_frozen_v035_mask(gray):
    v034_mask, _ = build_local_curvature_short_curve_mask(
        gray,
        strong_threshold=128,
        weak_threshold=240,
        local_window=15,
        min_local_contrast=12.0,
        independent_min_component_pixels=12,
        min_principal_span=18.0,
        independent_min_elongation=2.0,
        independent_min_component_mean_contrast=12.0,
        faint_gray_max=254,
        faint_min_local_contrast=1.0,
        source_min_component_pixels=6,
        min_axis_span=10.0,
        source_min_elongation=1.2,
        source_min_component_mean_contrast=2.0,
        min_curve_pixels=8,
        max_curve_pixels=19,
        min_curve_span=7.0,
        max_curve_span=11.0,
        max_transverse_rms=1.6,
        min_quadratic_gain=0.30,
        min_normalized_curvature=0.45,
        min_curve_mean_contrast=20.0,
    )
    v035_mask, _ = fill_small_enclosed_background_holes(
        v034_mask,
        max_hole_area=10,
        background_connectivity=8,
    )
    return v035_mask


def _validate_input_file(input_path: Path) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Input image does not exist: {input_path}")
    if not input_path.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"Unsupported input format {input_path.suffix or '<none>'}; "
            "supported formats are .png, .jpg and .jpeg"
        )


def _prepare_output_dir(output_dir: Path) -> None:
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"Output path is not a directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)


def _publish(candidate: Path, output_path: Path, overwrite: bool) -> None:
    if overwrite:
        candidate.replace(output_path)
        return
    created = False
    try:
        with candidate.open("rb") as source, output_path.open("xb") as destination:
            created = True
            shutil.copyfileobj(source, destination)
    except BaseException:
        if created:
            output_path.unlink(missing_ok=True)
        raise


def _convert_image(
    input_path: Path,
    output_dir: Path,
    *,
    overwrite: bool,
    toolchain_validated: bool,
) -> Path:
    _validate_input_file(input_path)
    _prepare_output_dir(output_dir)
    output_path = output_dir / f"{input_path.stem}.svg"
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output SVG already exists (overwrite is disabled): {output_path}")

    gray = load_grayscale(input_path)
    actual_size = (int(gray.shape[1]), int(gray.shape[0]))
    if actual_size != STANDARD_SIZE:
        raise ValueError(
            f"Unsupported image size {actual_size[0]}x{actual_size[1]}; "
            f"this package formally supports {STANDARD_SIZE[0]}x{STANDARD_SIZE[1]} "
            "and does not resize, crop or pad inputs"
        )
    if not toolchain_validated:
        validate_toolchain()

    try:
        with tempfile.TemporaryDirectory(
            prefix=f".{input_path.stem}-v036-", dir=str(output_dir)
        ) as temporary_name:
            temporary_root = Path(temporary_name)
            mask_path = temporary_root / "mask.bmp"
            baseline_svg = temporary_root / "baseline.svg"
            baseline_raster = temporary_root / "baseline.png"
            candidate_svg = temporary_root / "candidate.svg"

            expected_mask = _build_frozen_v035_mask(gray)
            save_mask_bmp(expected_mask, mask_path)
            run_potrace(mask_path, baseline_svg)
            validate_svg(baseline_svg, *STANDARD_SIZE)
            rasterize_svg(baseline_svg, baseline_raster)
            repair_svg(baseline_svg, baseline_raster, expected_mask, candidate_svg)
            validate_svg(candidate_svg, *STANDARD_SIZE)
            _publish(candidate_svg, output_path, overwrite)
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, FileExistsError):
            raise
        raise ConversionError(f"Failed to convert {input_path}: {exc}") from exc

    return output_path


def convert_image(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Convert one supported 2048x2048 image and return its final SVG path."""
    return _convert_image(
        Path(input_path),
        Path(output_dir),
        overwrite=overwrite,
        toolchain_validated=False,
    )


def _conflicting_inputs(inputs: list[Path]) -> set[Path]:
    groups: dict[str, list[Path]] = {}
    for input_path in inputs:
        groups.setdefault(input_path.stem.casefold(), []).append(input_path)
    return {
        input_path
        for group in groups.values()
        if len(group) > 1
        for input_path in group
    }


def convert_batch(
    input_dir: str | Path,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
) -> BatchResult:
    """Convert supported first-level images and return per-file results."""
    input_root = Path(input_dir)
    if not input_root.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_root}")
    if not input_root.is_dir():
        raise ValueError(f"Batch input is not a directory: {input_root}")
    inputs = discover_inputs(input_root)
    if not inputs:
        raise ValueError(
            f"Input directory contains no supported first-level images: {input_root}"
        )
    output_root = Path(output_dir)
    _prepare_output_dir(output_root)
    validate_toolchain()

    conflicts = _conflicting_inputs(inputs)
    failures = []
    outputs = []
    for input_path in inputs:
        if input_path in conflicts:
            peers = sorted(
                path.name
                for path in inputs
                if path.stem.casefold() == input_path.stem.casefold()
            )
            failures.append(
                BatchFailure(
                    input_path,
                    "Naming conflict: inputs map to the same SVG name: " + ", ".join(peers),
                )
            )
            continue
        try:
            outputs.append(
                _convert_image(
                    input_path,
                    output_root,
                    overwrite=overwrite,
                    toolchain_validated=True,
                )
            )
        except Exception as exc:
            failures.append(BatchFailure(input_path, str(exc)))

    return BatchResult(
        input_count=len(inputs),
        success_count=len(outputs),
        failure_count=len(failures),
        output_paths=tuple(outputs),
        failures=tuple(failures),
    )
