"""External integration ports."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from certified_workflow_conversion.core.models import TypedEvidenceObject


class OAWMBridge(Protocol):
    bridge_name: str

    def import_state(
        self,
        path: str | Path,
        *,
        run_id: str | None = None,
    ) -> list[TypedEvidenceObject]:
        """Read OAWM state and convert it into CWC evidence."""
