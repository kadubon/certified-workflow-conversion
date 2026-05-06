# Plugin Guide

Plugins are ordinary Python packages exposing entry points.

```toml
[project.entry-points."cwc.storage_backends"]
postgres = "my_package.postgres:create_store"

[project.entry-points."cwc.analyzers"]
my_analyzer = "my_package.analysis:create_analyzer"

[project.entry-points."cwc.report_sinks"]
markdown = "my_package.reports:create_sink"
```

Storage plugins should run the contract helpers in
`certified_workflow_conversion.testing.contracts`. Analyzer plugins must keep
diagnostic results separate from certified lower-bound claims and must fail
closed on missing evidence.

## Analyzer Rules

Custom analyzers may return diagnostic scores freely, but a certified
lower-bound report should preserve these invariants:

- raw workflow capacity is not enough;
- inactive, expired, quarantined, superseded, or policy-reserve evidence cannot
  support a certified claim;
- hard gates are non-compensable;
- every report-facing term is bound to evidence and deterministic checker
  output;
- diagnostic dual prices are planning signals, not adoption authorization;
- factual truth, model honesty, and sandbox safety must not be claimed.

Domain analyzers can extend value accounting, richer queue certificates, or
deployment-specific continuity coordinates. They should encode those additions
as typed evidence, contracts, witnesses, and explicit limitations rather than
as hidden assumptions.

## Minimal Storage Plugin Shape

```python
from pathlib import Path

from certified_workflow_conversion.adapters.sqlite_store import SQLiteStore


def create_store(path: Path) -> SQLiteStore:
    return SQLiteStore(path)
```

Third-party packages can replace this with PostgreSQL, DuckDB, object storage,
or enterprise evidence ledgers as long as they implement the `StorageBackend`
protocol and preserve observable ordering.
