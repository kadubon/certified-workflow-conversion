"""JSON and optional YAML loading helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from certified_workflow_conversion.core.errors import FailClosedError


def load_mapping(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if target.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise FailClosedError("YAML input requires installing the yaml extra") from exc
        payload = yaml.safe_load(text)
    else:
        payload = _strict_json_loads(text)
    if not isinstance(payload, dict):
        raise FailClosedError("input file must contain an object")
    return payload


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        payload = _strict_json_loads(stripped)
        if not isinstance(payload, dict):
            raise FailClosedError(f"line {line_no} must contain a JSON object")
        result.append(payload)
    return result


def _strict_json_loads(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise FailClosedError(f"non-finite JSON number is not allowed: {value}")

    def object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise FailClosedError(f"duplicate JSON key is not allowed: {key}")
            result[key] = value
        return result

    return json.loads(
        text,
        object_pairs_hook=object_pairs_hook,
        parse_constant=reject_constant,
    )
