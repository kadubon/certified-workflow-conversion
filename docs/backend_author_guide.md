# Backend Author Guide

CWC storage backends implement `StorageBackend`. SQLite is the default adapter,
not an architectural assumption.

Required methods:

- `initialize()`
- `append_evidence(evidence)`
- `get_evidence(evidence_id)`
- `list_evidence(scope=None, kind=None, limit=None)`
- `upsert_network(network)`
- `get_network(network_id)`
- `append_claim(claim)`
- `get_claim(claim_id)`
- `append_report(report)`
- `get_report(report_id)`
- `audit_counts()`
- `transaction()`
- `capabilities()`

Backend rules:

- Evidence is append-oriented. If an existing id is reused with different
  content, fail closed.
- Claim compilations are append-only. A stable `claim_id` can have multiple
  `compilation_id` records as evidence changes; `get_claim(claim_id)` should
  return the latest compilation.
- Stored JSON must preserve every public model field.
- `obs_seq` or an equivalent monotonic observable order is required for evidence.
- SQL, row ids, PRAGMAs, cloud SDK objects, and backend-specific handles must not
  leak into `core` or `runtime`.
- Declare capabilities truthfully. If a backend lacks transactions or JSON query,
  callers must be able to discover that through `StorageCapabilities`.

Suggested mappings:

- PostgreSQL: JSONB columns, serial `obs_seq`, transaction-backed writes.
- DuckDB: local analytics backend for batch evidence and reports.
- S3-like stores: object blobs plus a small index backend for ids and ordering.
- In-memory stores: tests and examples only.
