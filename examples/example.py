"""Minimal Python API examples; run from the package root."""

from pathlib import Path
import sys

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from svg_converter import convert_batch, convert_image


INPUT_DIR = PACKAGE_ROOT / "examples" / "input"
GENERATED_DIR = PACKAGE_ROOT / "examples" / "generated"


single_svg = convert_image(
    INPUT_DIR / "002c66bddebfec777e2835d2529bad8c.png",
    GENERATED_DIR,
    overwrite=True,
)
print(f"single output: {single_svg}")

batch = convert_batch(INPUT_DIR, GENERATED_DIR, overwrite=True)
print(
    f"batch total={batch.input_count} success={batch.success_count} "
    f"failed={batch.failure_count}"
)
