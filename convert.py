"""Command-line entry point for the frozen v0.3.6 converter."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from svg_converter import convert_batch, convert_image


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert one image or a directory's first-level PNG/JPG/JPEG images "
            "to frozen v0.3.6 SVG output. Formal input size is 2048x2048; "
            "inputs are never resized, cropped or padded."
        )
    )
    parser.add_argument("--input", required=True, type=Path, help="input image or directory")
    parser.add_argument("--output", required=True, type=Path, help="final SVG output directory")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="explicitly allow replacement of existing same-name SVG files",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.input.is_dir():
            result = convert_batch(args.input, args.output, overwrite=args.overwrite)
            print(
                f"total={result.input_count} success={result.success_count} "
                f"failed={result.failure_count} output={args.output.resolve()}"
            )
            for failure in result.failures:
                print(f"FAILED {failure.input_path.name}: {failure.reason}")
            return 0 if result.all_succeeded else 1
        output_path = convert_image(args.input, args.output, overwrite=args.overwrite)
        print(f"total=1 success=1 failed=0 output={output_path.resolve()}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
