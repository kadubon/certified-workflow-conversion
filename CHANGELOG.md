# Changelog

## Unreleased

- Made `light` profile fail closed for `certified_lower_bound` requests so only
  the `full` profile can emit procedural lower-bound reports.
- Added root `SECURITY.md` and a release checklist for pre-publication review.

## 0.1.0b1

- Initial v0.1.0 beta scaffold.
- Added storage-neutral core models and ports-and-adapters architecture.
- Added SQLite and in-memory storage adapters with contract tests.
- Added deterministic conversion analyzer and diagnostic investment candidates.
- Added read-only OAWM SQLite bridge.
- Added Typer CLI, examples, docs, schemas, and CI matrix.
- Hardened claim compilation so unsupported service edges, reservations, queues,
  risk charges, hard gates, and unrooted TCB requirements fail closed.
- Separated diagnostic reports from certified lower-bound reporting protocol.
- Made claim compilations append-only with stable claim ids and compilation ids.
- Added optional `full` profile with SciPy-backed flow relaxation, dual price
  intervals, evidence-contract/witness checks, statistical/path-law formulas,
  queue/release accounting checks, and validation-capital root-cut proof.
- Hardened `full` profile so edge capacities and report-facing lower/charge
  terms must be bound to accepted contract/witness outputs, and final lower
  bounds are capped by statistical/path-law certificates before deductions.
- Aligned `full` profile with the one-term evidence-contract DSL, blocked
  ambiguous edge-name capacity bindings, and required nonempty uncertainty,
  queue-boundary derivation, and Goodhart construction evidence.
- Added term-specific dependency binding so full-profile contracts must depend
  on the evidence objects that produced their exposed report terms.
- Reworked README and docs for clearer positioning, limitations, quickstart,
  extension points, and beta-safe scientific claims.
- Added full-profile docs, examples, tests, and a dedicated CI job.
