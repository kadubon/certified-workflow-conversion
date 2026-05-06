"""Report sink adapters."""

from __future__ import annotations

from pathlib import Path

from certified_workflow_conversion.core.models import BottleneckReport


class JsonReportSink:
    sink_name = "json"

    def write(self, report: BottleneckReport, target: str | Path) -> Path:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return path


def create_json_sink() -> JsonReportSink:
    return JsonReportSink()

