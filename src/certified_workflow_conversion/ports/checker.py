"""Checker port for evidence and claims."""

from __future__ import annotations

from typing import Any, Protocol

from certified_workflow_conversion.core.models import TypedEvidenceObject


class CheckerResult(TypedEvidenceObject):
    """Evidence-compatible checker result."""


class Checker(Protocol):
    checker_name: str

    def verify(self, *, payload: dict[str, Any], context: dict[str, Any]) -> CheckerResult:
        """Return deterministic checker evidence."""

