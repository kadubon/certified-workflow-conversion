# Certified Workflow Conversion

`certified-workflow-conversion` (`cwc`) is a local-first Python toolkit for
improving AI agent pipelines without changing the model. It treats an agent
deployment as a workflow conversion network: candidates become usable value only
after generation, tool execution, validation, review, authorization, memory
governance, release, rollback, and incident handling.

CWC answers a narrow operational question:

> Given the current evidence ledger, which workflow layer is limiting
> evidence-bound certified throughput?

It does not certify factual truth, model intelligence, alignment, or production
safety. A certified CWC report means only that a lower-bound workflow claim is
procedurally admissible under declared evidence, contracts, witnesses, and
checks.

## Why This Exists

Model quality is not the only bottleneck in long-running AI systems. A stronger
model can still fail to create usable output when validation queues, release
gates, authority checks, memory governance, rollback capacity, or incident
response are the binding constraints.

CWC makes those constraints machine-readable:

- typed evidence objects describe what is known and where it applies;
- a monotone claim compiler rejects unsupported claims;
- conversion networks model workflow edges and capacities;
- hard gates block rather than become finite penalties;
- diagnostic analyzers identify bottlenecks;
- full-profile reports require evidence contracts and accepted verification
  witnesses for every report-facing term.

## What Is Unique

- **Workflow-first, model-independent:** no model provider is required. CWC
  analyzes the pipeline around the model.
- **Evidence-bound, not memory-only:** raw observations are not treated as
  certified throughput. Claims must be backed by active typed evidence.
- **Fail-closed certification path:** missing support, inactive evidence,
  missing TCB roots, failed hard gates, malformed witnesses, or unbound report
  terms block the report.
- **Report-term binding:** in `full` mode, each `EvidenceContract` exposes
  exactly one claim-facing term, and each accepted `VerificationWitness` must
  bind that term to deterministic numeric output and the source evidence it
  depends on.
- **Bottleneck investment signals:** dual prices and diagnostic scores can
  suggest where to invest next, while remaining separate from adoption claims.
- **Ports and adapters:** SQLite is the default local backend, not an
  architectural assumption. Storage, analyzers, optimizers, OAWM bridges, and
  report sinks are replaceable.

## What You Can Do

- Store typed evidence in a local append-oriented ledger.
- Register conversion networks for AI workflows.
- Compile claims against evidence, scope, dependency, expiry, and TCB checks.
- Run lightweight diagnostic bottleneck analysis.
- Run optional SciPy-backed full-profile lower-bound checks.
- Import certified OAWM state as read-only evidence.
- Build custom storage backends, analyzers, checkers, and report sinks.

## Analysis Profiles

| Profile | Purpose | Dependencies | Claim Strength |
| --- | --- | --- | --- |
| `light` | Fast local bottleneck screening | base install | diagnostic only |
| `full` | Evidence-contract lower-bound reports | `--extra full` | procedural lower bound under supplied evidence |

`light` mode is useful for engineering triage. It is not a full statistical
certificate, and `certified_lower_bound` requests in `light` profile fail
closed rather than returning a weaker pseudo-certificate.

`full` mode checks active evidence, three-way reporting splits, one-term
contracts, accepted witnesses, confidence budgets, source/sink declarations,
statistical or path-law certificates, queue certificates, release accounting,
Goodhart/open-world charges, and validation-capital root cuts.

For every report-facing term, the contract must also depend on the evidence that
produced the term. For example, an `edge.capacity:*` contract must depend on the
edge support evidence, and a `statistical_lower` contract must depend on the
statistical certificate evidence.

The `full` lower bound is composed conservatively:

```text
floor(max(0,
  min(flow, statistical/path-law/report-term lower bounds)
  - queue boundary
  - direct cost rate
  - Goodhart charge
  - open-world charge
))
```

Raw network flow is never enough by itself.

## Ten-Minute Local Run

```powershell
uv sync --extra dev
uv run python examples/coding_agent_pipeline/run_demo.py
```

That example creates local evidence, registers a coding-agent pipeline, compiles
a claim, analyzes bottlenecks, and prints investment candidates. It uses no API
keys and makes no network calls.

CLI workflow:

```powershell
uv run cwc init .cwc
uv run cwc evidence add examples/coding_agent_pipeline/evidence.jsonl --state .cwc
uv run cwc network add examples/coding_agent_pipeline/network.json --state .cwc
uv run cwc audit --state .cwc
```

For the full profile:

```powershell
uv sync --extra dev --extra full
uv run python examples/full_certified_lower_bound.py
uv run python examples/dual_price_interval.py
uv run python examples/validation_capital_root_cut.py
```

## Minimal Python API

```python
from certified_workflow_conversion.core.models import (
    ClaimRequirement,
    ConversionNetwork,
    ServiceEdgeProfile,
    TypedEvidenceObject,
)
from certified_workflow_conversion.runtime.kernel import ConversionKernel

kernel = ConversionKernel.open(".cwc")

evidence = kernel.add_evidence(
    TypedEvidenceObject.create(
        kind="validation",
        scope="demo",
        source="local-test",
        payload={"passed": True},
    )
)

edge = ServiceEdgeProfile.create(
    name="validation",
    from_node="candidate",
    to_node="accepted",
    capacity=5,
    evidence_ids=[evidence.evidence_id],
)

network = kernel.register_network(
    ConversionNetwork.create(
        name="demo",
        nodes=["candidate", "accepted"],
        source_nodes=["candidate"],
        sink_nodes=["accepted"],
        edges=[edge],
    )
)

claim = kernel.compile_claim(
    ClaimRequirement.create(
        network_id=network.network_id,
        target_value=4,
        required_evidence_ids=[evidence.evidence_id],
    )
)

report = kernel.analyze(network.network_id, claim.claim_id)
```

Full-profile calls use the same kernel:

```python
report = kernel.analyze(
    network.network_id,
    claim.claim_id,
    mode="certified_lower_bound",
    profile="full",
)
```

## Core Concepts

| Concept | Meaning |
| --- | --- |
| `TypedEvidenceObject` | Active, scoped evidence with dependencies, expiry, TCB requirements, and digest binding |
| `ConversionNetwork` | Directed workflow graph whose edges represent services such as generation, validation, release, memory, or recovery |
| `ClaimRequirement` | A requested lower-bound claim over a network and target value |
| `CompiledClaim` | A monotone compilation result; unsupported claims remain audit-visible |
| `EvidenceContract` | A machine-checkable contract exposing exactly one report-facing term |
| `VerificationWitness` | Accepted checker output binding a contract to inputs, scope, checker digest, TCB, and numeric result |
| `BottleneckReport` | Diagnostic or certified-lower-bound report with limitations and evidence ids |

## Extensibility

CWC uses ports and adapters:

- `cwc.storage_backends`: SQLite, PostgreSQL, DuckDB, object-store, enterprise DB.
- `cwc.analyzers`: deterministic, optimization-backed, or domain-specific analyzers.
- `cwc.optimizers`: investment search strategies.
- `cwc.oawm_bridges`: importers from external agent-memory systems.
- `cwc.report_sinks`: JSON, Markdown, database, dashboard, or observability export.

The core package does not import SQLite, cloud SDKs, model providers, or OAWM.
Backend authors can run the storage contract helpers in
`certified_workflow_conversion.testing.contracts`.

## Security And Limitations

- CWC is not a sandbox, credential manager, policy engine, or external-effect
  gateway.
- CWC does not execute tools or release actions.
- Certified throughput does not mean factual truth or model truthfulness.
- `light` profile is diagnostic only.
- `full` profile is fail-closed and evidence-bound, but only as strong as the
  supplied evidence, contracts, witnesses, roots, and domain-specific checkers.
- Full-profile reports currently use normalized unit throughput; richer value
  accounting should be implemented in domain analyzers.
- SQLite state is trusted local state in this beta.
- Semantic validity depends on domain-specific evidence and checker plugins.
- TCB requirements require rooted, active TCB evidence. Declaring a requirement
  is not proof that the TCB is healthy.
- Dual prices are local planning signals, not adoption authorization.
- APIs and schemas may change before a stable non-beta release.

For production systems, external effects still need OS, network, identity,
secrets, sandboxing, audit, and recovery controls outside CWC.

## Documentation

- [Theory mapping](docs/theory_mapping.md)
- [Full certification profile](docs/full_certification.md)
- [Reporting protocol](docs/reporting_protocol.md)
- [Security model](docs/security_model.md)
- [Backend author guide](docs/backend_author_guide.md)
- [Plugin guide](docs/plugin_guide.md)
- [Release checklist](docs/release_checklist.md)

## Development Checks

```powershell
uv run pytest
uv run ruff check .
uv run mypy src
```

Full-profile development:

```powershell
uv sync --extra dev --extra full
uv run pytest tests/full
```
