"""Canonical JSON and digest helpers."""

from __future__ import annotations

from typing import Any

import orjson


def canonical_bytes(value: Any) -> bytes:
    """Serialize JSON-like data deterministically."""

    return orjson.dumps(
        value,
        option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z | orjson.OPT_NAIVE_UTC,
    )


def canonical_json(value: Any) -> str:
    return canonical_bytes(value).decode("utf-8")


def digest_json(value: Any) -> str:
    import hashlib

    return hashlib.sha256(canonical_bytes(value)).hexdigest()

