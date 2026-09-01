"""Input discovery and grayscale normalization for the v0.3.6 package."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png"}


def discover_inputs(input_path: Path) -> list[Path]:
    """Return supported input images without recursing into directories."""
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    if input_path.is_file():
        if input_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"Unsupported input image format: {input_path.suffix or '<none>'}")
        return [input_path]

    if not input_path.is_dir():
        raise ValueError(f"Input path is neither a file nor a directory: {input_path}")

    images = [
        path
        for path in input_path.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    ]
    return sorted(images, key=lambda path: (path.name.casefold(), path.name))


def load_grayscale(input_path: Path) -> np.ndarray:
    """Load an image as a two-dimensional uint8 grayscale array."""
    input_path = Path(input_path)

    with Image.open(input_path) as source:
        image = ImageOps.exif_transpose(source)
        has_transparency = image.mode in {"RGBA", "LA"} or "transparency" in image.info

        if has_transparency:
            rgba = image.convert("RGBA")
            white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            image = Image.alpha_composite(white, rgba)

        gray_image = image.convert("L")
        gray = np.array(gray_image, dtype=np.uint8, copy=True)

    if gray.ndim != 2:
        raise ValueError(f"Expected a two-dimensional grayscale image: {input_path}")
    if gray.shape[0] <= 0 or gray.shape[1] <= 0:
        raise ValueError(f"Image dimensions must be greater than zero: {input_path}")

    return gray


def save_grayscale_png(gray: np.ndarray, output_path: Path) -> None:
    """Save a two-dimensional uint8 array as an 8-bit grayscale PNG."""
    if not isinstance(gray, np.ndarray) or gray.ndim != 2:
        raise ValueError("Grayscale image must be a two-dimensional NumPy array")
    if gray.dtype != np.uint8:
        raise ValueError("Grayscale image dtype must be uint8")
    if gray.shape[0] <= 0 or gray.shape[1] <= 0:
        raise ValueError("Grayscale image dimensions must be greater than zero")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(gray).save(output_path, format="PNG")

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise OSError(f"Grayscale PNG was not created: {output_path}")
