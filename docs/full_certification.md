# Full Certification Profile

The `full` profile is the optional implementation layer for reports that need
more than lightweight diagnostic screening.

Install it with:

```powershell
uv sync --extra dev --extra full
```

Run it with:

```powershell
uv run cwc analyze --network NET --claim CLAIM --mode certified_lower_bound --profile full
```

## What It Checks

- Active typed evidence only. Expired, quarantined, superseded, and
  policy-reserve evidence cannot support a certified report.
- Non-empty three-way split: ledger/build, selection, and final certification
  references must exist and must not overlap unless an explicit uniform or
  time-uniform witness is supplied.
- `EvidenceContract` plus accepted `VerificationWitness`.
- Report-term binding: every claim-facing term must be exposed by an active
  contract and accepted witness. Each contract exposes exactly one term.
  Supported terms include
  `edge.capacity:<edge_id>`, `edge.capacity:<edge_name>`, `statistical_lower`,
  `path_law_lower`, `queue_boundary`, `release_accounting`,
  `goodhart_charge`, and `open_world_charge`.
- Term dependency binding: the exposing contract must depend on the source
  evidence for that term. Edge capacity contracts depend on edge support
  evidence; statistical, path-law, queue, release, Goodhart, and open-world
  contracts depend on their corresponding certificate/accounting evidence.
- Nonempty uncertainty contract evidence. Empty uncertainty contracts do not
  define certified lower bounds.
- Confidence budget composition.
- One-step DR, dynamic path-law, or time-uniform lower-bound certificates.
- Queue certificates for no-phantom release and bounded increments.
- Positive queue boundary corrections require derivation evidence.
- Release accounting with disjoint ledgers.
- Goodhart and open-world charges as evidence-bound report terms.
- Positive Goodhart/open-world charges require construction evidence.
- Validation-capital root reachability and consumable root-cut capacity.
- SciPy-backed conservative flow relaxation and dual price intervals.

The final reported lower bound is composed conservatively:

```text
floor(max(0,
  min(flow, statistical/path-law/report-term lower bounds)
  - queue boundary
  - direct cost rate
  - Goodhart charge
  - open-world charge
))
```

This means a large network capacity cannot become certified throughput unless
the edge capacity and each lower-bound or charge term are supported by matching
contracts, witnesses, and certificate payloads.

## Report-Term Binding

`EvidenceContract.exposes` names exactly one report term. The corresponding
`VerificationWitness.exposes` must name the same single term, and
`accepted_output` must contain a deterministic numeric value for that term. This
one-term rule keeps contracts reusable, auditable, and easy for third-party
checkers to replace.

Example:

```json
{
  "exposes": "edge.capacity:release",
  "dependencies": ["ev_support_for_release_edge"],
  "accepted_output": {
    "edge.capacity:release": 5,
    "capacity": 5
  }
}
```

Use separate contract/witness pairs for `statistical_lower`, `path_law_lower`,
`queue_boundary`, `release_accounting`, `goodhart_charge`, and
`open_world_charge`.

Witnesses also bind scope, input digest, checker digest, and TCB requirements
when the contract declares them. Overlapping ledger/selection/certification
splits are blocked unless every active report-facing contract uses an accepted
witness that explicitly declares `uniform`, `time_uniform`, `eprocess`, or
`simultaneous` composition.

## What It Does Not Claim

The full profile does not prove factual truth, model truthfulness, or production
safety. It only reports that a lower-bound claim is admissible under the supplied
evidence, contracts, witnesses, roots, and deterministic checks.

The current full profile uses normalized unit throughput. General value
accounting with item reward vectors, incident-cost ledgers, and deployment-local
utility functions should be implemented by domain analyzers that still satisfy
the same report-validity protocol.

Dual price intervals are local planning signals. They can identify candidate
bottlenecks, but adoption still requires a post-investment ledger and certificate.

## Extension Points

The full profile is still adapter-based. Projects can replace:

- the flow optimizer with another `Analyzer`;
- statistical certificate parsers with domain-specific checkers;
- validation-capital analysis with an enterprise graph backend;
- storage with PostgreSQL, DuckDB, object-store, or in-memory adapters.

Backends should preserve the public JSON models and should fail closed when they
cannot represent ordering, dependency closure, or report artifacts faithfully.
