from __future__ import annotations

import hashlib
import json
import unicodedata
from decimal import Decimal
from typing import Any


class CanonicalJsonError(ValueError):
    """Raised when a value cannot be represented by canonical_json_v1."""


def canonical_json_v1(value: Any) -> str:
    """Return the Slice 20 canonical JSON representation without a trailing LF."""

    normalized = _normalize(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_json_bytes_v1(value: Any) -> bytes:
    return canonical_json_v1(value).encode("utf-8")


def canonical_sha256_v1(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes_v1(value)).hexdigest()


def canonical_json_artifact_v1(value: Any) -> str:
    """Return canonical JSON with the single LF required for JSON artifacts."""

    return canonical_json_v1(value) + "\n"


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return 0 if value == 0 else value
    if isinstance(value, float):
        raise CanonicalJsonError(
            "Binary floating-point values are not canonical JSON values."
        )
    if isinstance(value, Decimal):
        return _canonical_decimal(value)
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJsonError("Canonical JSON object keys must be strings.")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise CanonicalJsonError(
                    f"Canonical JSON key collision after NFC normalization: {normalized_key!r}."
                )
            normalized[normalized_key] = _normalize(item)
        return normalized
    raise CanonicalJsonError(
        f"Unsupported canonical JSON value type: {type(value).__name__}."
    )


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise CanonicalJsonError("NaN and infinite decimal values are not canonical.")
    if value.is_zero():
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
