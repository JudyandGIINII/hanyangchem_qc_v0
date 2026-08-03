from __future__ import annotations

from decimal import Decimal

from hyc_local_ocr.contracts import LocalOcrLimits

REQUIRED_NATIVE_MARKERS = ("SUPPLIER", "PRODUCT", "LOT")


def native_text_is_sufficient(text: str, limits: LocalOcrLimits) -> bool:
    """Single routing predicate shared by PDF rendering and extraction."""

    compact = "".join(text.split())
    if len(compact) < limits.native_text_min_characters:
        return False
    alphanumeric = sum(character.isalnum() for character in compact)
    ratio = Decimal(alphanumeric) / Decimal(len(compact))
    upper = text.upper()
    marker_count = sum(marker in upper for marker in REQUIRED_NATIVE_MARKERS)
    return ratio >= limits.native_text_min_alnum_ratio and marker_count >= 2
