"""Report export sink port."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from certified_workflow_conversion.core.models import BottleneckReport


class ReportSink(Protocol):
    sink_name: str

    def write(self, report: BottleneckReport, target: str | Path) -> Path:
        """Write a report to a target path."""

