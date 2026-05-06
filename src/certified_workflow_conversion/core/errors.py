"""Domain errors."""

from __future__ import annotations


class CWCError(Exception):
    """Base project error."""


class FailClosedError(CWCError):
    """Raised when certification or configuration must fail closed."""


class NotFoundError(CWCError):
    """Raised when a persisted object is absent."""

