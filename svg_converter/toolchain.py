"""Bundled Potrace/resvg invocation and final SVG validation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from typing import Optional
import xml.etree.ElementTree as ET


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
POTRACE_BIN = PACKAGE_ROOT / "tools" / "potrace" / "potrace"
RESVG_BIN = PACKAGE_ROOT / "tools" / "resvg" / "resvg"
POTRACE_SHA256 = "E2D26F8322A7770A6CCDCF30889503B6C61E27ED8A30F13FC8F340174EB435B0"
RESVG_SHA256 = "A53A45EAFCAF3C04CEEFC0C150C3D10FDF582D143D1CA5E4A7A64E661C55F02E"
_LENGTH_PATTERN = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([A-Za-z]*)\s*$"
)
_BLACK_FILLS = {"black", "#000", "#000000", "rgb(0,0,0)", "rgb(0%,0%,0%)"}


@dataclass(frozen=True)
class ToolCall:
    tool: str
    command: tuple[str, ...]
    returncode: int


CALL_LEDGER: list[ToolCall] = []


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _run_version(executable: Path, expected_text: str, expected_hash: str) -> None:
    if not executable.is_file():
        raise FileNotFoundError(f"Bundled tool is missing: {executable}")
    if not os.access(executable, os.X_OK):
        raise PermissionError(
            f"Bundled Linux tool is not executable: {executable}; "
            f"run: chmod +x {executable}"
        )
    actual_hash = _sha256(executable)
    if actual_hash != expected_hash:
        raise RuntimeError(
            f"Bundled tool hash mismatch for {executable.name}: "
            f"expected {expected_hash}, got {actual_hash}"
        )
    completed = subprocess.run(
        [str(executable), "--version"],
        capture_output=True,
        text=True,
        shell=False,
    )
    version_text = "\n".join((completed.stdout, completed.stderr)).strip()
    if completed.returncode != 0 or expected_text not in version_text:
        raise RuntimeError(
            f"Unexpected {executable.name} version output "
            f"(exit {completed.returncode}): {version_text or '<empty>'}"
        )


def validate_toolchain() -> None:
    """Validate the bundled executable versions and frozen SHA-256 hashes."""
    if not sys.platform.startswith("linux"):
        raise RuntimeError(
            f"This delivery is Linux-only; current platform is {sys.platform!r}"
        )
    machine = platform.machine().lower()
    if machine not in {"x86_64", "amd64"}:
        raise RuntimeError(
            f"This delivery requires Linux x86-64; current machine is {machine!r}"
        )
    _run_version(POTRACE_BIN, "potrace 1.16", POTRACE_SHA256)
    _run_version(RESVG_BIN, "0.47.0", RESVG_SHA256)


def run_potrace(mask_path: Path, svg_path: Path) -> ToolCall:
    """Run exactly one bundled Potrace 1.16 call with frozen arguments."""
    command = (
        str(POTRACE_BIN),
        str(mask_path),
        "--svg",
        "--output",
        str(svg_path),
        "--turdsize",
        "0",
        "--resolution",
        "72",
    )
    completed = subprocess.run(command, capture_output=True, text=True, shell=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Potrace failed with exit code {completed.returncode}: "
            f"{completed.stderr.strip() or '<no stderr>'}"
        )
    if not svg_path.is_file() or svg_path.stat().st_size == 0:
        raise RuntimeError("Potrace did not create a non-empty SVG")
    call = ToolCall("potrace", command, completed.returncode)
    CALL_LEDGER.append(call)
    return call


def rasterize_svg(svg_path: Path, png_path: Path) -> ToolCall:
    """Rasterize once with bundled resvg 0.47.0 at the frozen 72 DPI."""
    command = (
        str(RESVG_BIN),
        "--dpi",
        "72",
        str(svg_path),
        str(png_path),
    )
    completed = subprocess.run(command, capture_output=True, text=True, shell=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"resvg failed with exit code {completed.returncode}: "
            f"{completed.stderr.strip() or '<no stderr>'}"
        )
    if not png_path.is_file() or png_path.stat().st_size == 0:
        raise RuntimeError("resvg did not create a non-empty PNG")
    call = ToolCall("resvg", command, completed.returncode)
    CALL_LEDGER.append(call)
    return call


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_length(value: Optional[str], name: str) -> float:
    if value is None:
        raise ValueError(f"SVG is missing {name}")
    match = _LENGTH_PATTERN.fullmatch(value)
    if match is None or match.group(2).lower() not in {"", "pt", "px"}:
        raise ValueError(f"SVG {name} is not a supported numeric length: {value!r}")
    return float(match.group(1))


def validate_svg(svg_path: Path, expected_width: int, expected_height: int) -> None:
    """Require a non-empty, parseable, self-contained SVG on the expected canvas."""
    if not svg_path.is_file() or svg_path.stat().st_size == 0:
        raise FileNotFoundError(f"SVG does not exist or is empty: {svg_path}")
    try:
        root = ET.parse(svg_path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"SVG XML is invalid: {svg_path}: {exc}") from exc
    if _local_name(root.tag) != "svg":
        raise ValueError("Root XML element is not svg")
    width = _parse_length(root.attrib.get("width"), "width")
    height = _parse_length(root.attrib.get("height"), "height")
    if not math.isclose(width, expected_width, rel_tol=0, abs_tol=1e-9):
        raise ValueError(f"SVG width {width} does not match expected {expected_width}")
    if not math.isclose(height, expected_height, rel_tol=0, abs_tol=1e-9):
        raise ValueError(f"SVG height {height} does not match expected {expected_height}")
    view_box = [
        float(part)
        for part in re.split(r"[\s,]+", root.attrib.get("viewBox", "").strip())
        if part
    ]
    if view_box != [0.0, 0.0, float(expected_width), float(expected_height)]:
        raise ValueError(f"SVG viewBox does not match 0 0 {expected_width} {expected_height}")
    elements = list(root.iter())
    if not any(_local_name(element.tag) == "path" for element in elements):
        raise ValueError("SVG does not contain a path element")
    if not any(
        re.sub(r"\s+", "", element.attrib.get("fill", "")).lower() in _BLACK_FILLS
        for element in elements
    ):
        raise ValueError("SVG does not declare a black foreground fill")
    for element in elements:
        for name, value in element.attrib.items():
            local_name = _local_name(name).lower()
            if local_name == "href" and value and not value.startswith("#"):
                raise ValueError(f"SVG contains an external href: {value}")
            for target in re.findall(r"url\(([^)]+)\)", value, flags=re.IGNORECASE):
                normalized = target.strip().strip("\"'")
                if not normalized.startswith("#"):
                    raise ValueError(f"SVG contains an external URL reference: {normalized}")
