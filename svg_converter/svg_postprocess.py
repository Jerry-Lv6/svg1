"""Frozen v0.3.6 mask-aware SVG small-hole post-processing."""

from __future__ import annotations

from collections import Counter
import heapq
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


MAX_VISIBLE_HOLE_AREA_PX = 10
MAX_CORRIDOR_CUT_PIXELS = 3
SEARCH_RADII = (8, 16, 32, 64)
NEIGHBOURS_8 = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1), (0, 1),
    (1, -1), (1, 0), (1, 1),
)


def rendered_foreground(path: Path) -> np.ndarray:
    """Composite on white and apply the frozen grayscale < 128 rule."""
    with Image.open(path) as source:
        rgba = source.convert("RGBA")
        white = Image.new("RGBA", rgba.size, "white")
        white.alpha_composite(rgba)
        rgb = np.asarray(white.convert("RGB"), dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) < 128


def _background_components(
    foreground: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, set[int]]:
    _, labels, stats, _ = cv2.connectedComponentsWithStats(
        (~foreground).astype(np.uint8), connectivity=8
    )
    border_ids = set(
        np.unique(
            np.concatenate((labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]))
        ).tolist()
    )
    return labels, stats, border_ids


def _small_holes(foreground: np.ndarray) -> list[dict]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (~foreground).astype(np.uint8), connectivity=8
    )
    border_ids = set(
        np.unique(
            np.concatenate((labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]))
        ).tolist()
    )
    target_ids = [
        component_id
        for component_id in range(1, count)
        if component_id not in border_ids
        and 1 <= int(stats[component_id, cv2.CC_STAT_AREA]) <= MAX_VISIBLE_HOLE_AREA_PX
    ]
    selected = np.zeros(count, dtype=bool)
    selected[target_ids] = True
    ys, xs = np.where(selected[labels])
    coordinates = {component_id: [] for component_id in target_ids}
    for y, x in zip(ys.tolist(), xs.tolist()):
        coordinates[int(labels[y, x])].append((y, x))
    return [
        {
            "component_id": component_id,
            "area_px": int(stats[component_id, cv2.CC_STAT_AREA]),
            "pixels": coordinates[component_id],
        }
        for component_id in target_ids
    ]


def _shortest_safe_corridor(
    hole: dict,
    expected_mask: np.ndarray,
    mask_background_labels: np.ndarray,
    svg_foreground: np.ndarray,
    svg_background_labels: np.ndarray,
    svg_background_stats: np.ndarray,
    svg_border_ids: set[int],
) -> dict | None:
    white_seed_pixels = [pixel for pixel in hole["pixels"] if not expected_mask[pixel]]
    if not white_seed_pixels:
        return None
    parent_counts = Counter(int(mask_background_labels[pixel]) for pixel in white_seed_pixels)
    parent_id, _ = parent_counts.most_common(1)[0]
    if parent_id == 0:
        return None
    large_or_border = np.zeros(len(svg_background_stats), dtype=bool)
    for component_id in range(1, len(svg_background_stats)):
        large_or_border[component_id] = (
            component_id in svg_border_ids
            or int(svg_background_stats[component_id, cv2.CC_STAT_AREA])
            > MAX_VISIBLE_HOLE_AREA_PX
        )
    ys = [pixel[0] for pixel in white_seed_pixels]
    xs = [pixel[1] for pixel in white_seed_pixels]
    height, width = expected_mask.shape
    for radius in SEARCH_RADII:
        y0 = max(0, min(ys) - radius)
        y1 = min(height, max(ys) + radius + 1)
        x0 = max(0, min(xs) - radius)
        x1 = min(width, max(xs) + radius + 1)
        parent_local = mask_background_labels[y0:y1, x0:x1] == parent_id
        svg_labels_local = svg_background_labels[y0:y1, x0:x1]
        target_local = (
            parent_local
            & (svg_labels_local != hole["component_id"])
            & large_or_border[svg_labels_local]
        )
        if not bool(np.any(target_local)):
            continue
        best: dict[tuple[int, int], tuple[int, int]] = {}
        previous: dict[tuple[int, int], tuple[int, int] | None] = {}
        queue = []
        for y, x in white_seed_pixels:
            if not (y0 <= y < y1 and x0 <= x < x1):
                continue
            node = (y, x)
            best[node] = (0, 0)
            previous[node] = None
            heapq.heappush(queue, (0, 0, y, x))
        destination = None
        while queue:
            cut_cost, steps, y, x = heapq.heappop(queue)
            node = (y, x)
            if best.get(node) != (cut_cost, steps):
                continue
            if cut_cost > MAX_CORRIDOR_CUT_PIXELS:
                break
            if target_local[y - y0, x - x0]:
                destination = node
                break
            for dy, dx in NEIGHBOURS_8:
                ny, nx = y + dy, x + dx
                if not (y0 <= ny < y1 and x0 <= nx < x1):
                    continue
                if not parent_local[ny - y0, nx - x0]:
                    continue
                next_cost = cut_cost + int(svg_foreground[ny, nx])
                if next_cost > MAX_CORRIDOR_CUT_PIXELS:
                    continue
                next_state = (next_cost, steps + 1)
                next_node = (ny, nx)
                if next_state >= best.get(next_node, (10**9, 10**9)):
                    continue
                best[next_node] = next_state
                previous[next_node] = node
                heapq.heappush(queue, (*next_state, ny, nx))
        if destination is None:
            continue
        path = []
        node = destination
        while node is not None:
            path.append(node)
            node = previous[node]
        path.reverse()
        cut_pixels = [pixel for pixel in path if svg_foreground[pixel]]
        if not cut_pixels or len(cut_pixels) > MAX_CORRIDOR_CUT_PIXELS:
            continue
        return {"cut_pixels": cut_pixels}
    return None


def _pixel_run_path(pixels: set[tuple[int, int]]) -> str:
    by_row: dict[int, list[int]] = {}
    for y, x in pixels:
        by_row.setdefault(y, []).append(x)
    commands = []
    for y in sorted(by_row):
        row = sorted(set(by_row[y]))
        start = previous = row[0]
        for x in row[1:] + [None]:
            if x is not None and x == previous + 1:
                previous = x
                continue
            commands.append(f"M {start} {y} H {previous + 1} V {y + 1} H {start} Z")
            if x is not None:
                start = previous = x
    return " ".join(commands)


def _write_candidate_svg(
    source_svg: Path,
    output_svg: Path,
    positive_pixels: set[tuple[int, int]],
    cut_pixels: set[tuple[int, int]],
) -> None:
    text = source_svg.read_text(encoding="utf-8")
    drawing_start = text.find("<g transform=")
    drawing_end_start = text.rfind("</g>")
    if drawing_start < 0 or drawing_end_start < drawing_start:
        raise ValueError("Expected one top-level Potrace drawing group")
    drawing_end = drawing_end_start + len("</g>")
    drawing = text[drawing_start:drawing_end]
    prefix = text[:drawing_start]
    suffix = text[drawing_end:]
    if cut_pixels:
        clip_path = _pixel_run_path(cut_pixels)
        defs = (
            '<defs><clipPath id="v036-mask-aware-cut" clipPathUnits="userSpaceOnUse">'
            '<path clip-rule="evenodd" fill-rule="evenodd" '
            f'd="M 0 0 H 2048 V 2048 H 0 Z {clip_path}"/>'
            "</clipPath></defs>\n"
        )
        drawing = (
            '<g id="v036-mask-aware-clipped-artwork" '
            'clip-path="url(#v036-mask-aware-cut)">\n'
            + drawing
            + "\n</g>"
        )
    else:
        defs = ""
    if positive_pixels:
        patches = (
            '\n<path id="v036-mask-supported-positive-patches" '
            'fill="#000000" stroke="none" shape-rendering="crispEdges" '
            f'd="{_pixel_run_path(positive_pixels)}"/>\n'
        )
    else:
        patches = "\n"
    # The frozen v0.3.6 reference was serialized on Windows with CRLF. Write the
    # same bytes explicitly so Linux output remains hash-reproducible while the
    # SVG geometry and algorithm stay unchanged.
    serialized = prefix + defs + drawing + patches + suffix
    normalized = serialized.replace("\r\n", "\n").replace("\r", "\n")
    output_svg.write_bytes(normalized.replace("\n", "\r\n").encode("utf-8"))


def repair_svg(
    source_svg: Path,
    baseline_raster: Path,
    expected_mask: np.ndarray,
    output_svg: Path,
) -> None:
    """Apply the frozen v0.3.6 repair to one v0.3.5 Potrace SVG."""
    baseline = rendered_foreground(baseline_raster)
    if baseline.shape != expected_mask.shape:
        raise ValueError("Rendered SVG dimensions do not match the input mask")
    holes = _small_holes(baseline)
    mask_labels, _, _ = _background_components(expected_mask)
    svg_labels, svg_stats, svg_border_ids = _background_components(baseline)
    positive_pixels: set[tuple[int, int]] = set()
    cut_pixels: set[tuple[int, int]] = set()
    for hole in holes:
        positive_pixels.update(pixel for pixel in hole["pixels"] if expected_mask[pixel])
        corridor = _shortest_safe_corridor(
            hole,
            expected_mask,
            mask_labels,
            baseline,
            svg_labels,
            svg_stats,
            svg_border_ids,
        )
        if corridor is not None:
            cut_pixels.update(corridor["cut_pixels"])
    _write_candidate_svg(source_svg, output_svg, positive_pixels, cut_pixels)
