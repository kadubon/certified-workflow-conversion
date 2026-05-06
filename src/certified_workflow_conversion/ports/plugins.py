"""Entry point loading."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

from certified_workflow_conversion.core.errors import FailClosedError


def load_entry_point(group: str, name: str) -> Any:
    matches = entry_points(group=group)
    for item in matches:
        if item.name == name:
            return item.load()
    raise FailClosedError(f"plugin not found: {group}:{name}")

