"""Frozen v0.3.6 original-image to final-SVG package."""

from .api import (
    BatchFailure,
    BatchResult,
    ConversionError,
    NamingConflictError,
    convert_batch,
    convert_image,
)

__all__ = [
    "BatchFailure",
    "BatchResult",
    "ConversionError",
    "NamingConflictError",
    "convert_batch",
    "convert_image",
]
