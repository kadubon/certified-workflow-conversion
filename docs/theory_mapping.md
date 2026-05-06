# Theory Mapping

CWC implements two layers of the attached workflow theory papers.

- `light` profile: a local diagnostic kernel for quick bottleneck screening.
  It never emits certified lower-bound reports.
- `full` profile: optional SciPy-backed checks for machine-readable contracts,
  witnesses, statistical/path-law certificates, queue/release accounting, dual
  price intervals, and validation-capital root cuts.

## Certified Conversion Networks

- Typed evidence ledger -> `TypedEvidenceObject` and `StoredEvidence`.
- Monotone claim compiler -> `ClaimRequirement` and `CompiledClaim`.
- Conversion network -> `ConversionNetwork` and `ServiceEdgeProfile`.
- Hard gates -> `HardGate`; failures block reports rather than become finite
  penalties.
- Queue-stable conversion -> `QueueState` and conservative queue penalties.
- Bottleneck prices -> `light` diagnostic scores, and `full`
  `DualPriceInterval` objects from a SciPy flow relaxation.
- Validation capital -> `ValidationDependencyGraph` and `RootCutCertificate`;
  rootless positive credit is rejected.
- Goodhart/open-world charges -> `RiskCharge`.
- No support, no certification -> claim compilation fails when service edge
  capacity, reservation, queue, risk charge, or hard gate evidence is missing.
- Three-way reporting protocol -> `full` `certified_lower_bound` mode requires
  ledger, selection, and certification evidence splits plus support,
  uncertainty, queue, Goodhart, and open-world evidence kinds.
- Evidence-contract DSL -> `EvidenceContract` and `VerificationWitness`; full
  profile enforces one claim-facing term per contract.
- Report-term soundness -> `full` profile requires accepted witnesses to expose
  each edge capacity and report-facing statistical, queue, release, Goodhart,
  and open-world term used in the lower-bound formula.
- One-step DR lower certificate -> deterministic formula in
  `adapters.statistical_certificates`.
- Dynamic path-law lower certificate -> `L_Q - 2 B_H epsilon_path`.
- Nonempty contract certificate -> `uncertainty_contract` evidence must declare
  a nonempty proof, constructive law, feasibility proof, or solver certificate.
- Queue certificate -> machine-readable checks for no-phantom release, bounded
  increments, and derivation-backed boundary correction.
- Release accounting -> disjoint ledger declaration plus direct cost rate.
- Goodhart/open-world construction -> positive charges require construction
  evidence, not unsupported declarations.

The implementation is intentionally conservative. If a required certificate is
missing, malformed, inactive, outside the declared split, over budget, rootless,
or not bound to the reported term, the report is blocked rather than degraded
into an optimistic score.

## Certified Service Is Not Enough

Service evidence is not enough for responsible long-running agency. CWC keeps
continuity coordinates explicit: service, recovery, authority, identity,
mutation, goal, memory, federation, liability, TCB, and consistency.

CWC does not release external effects and does not claim the full continuity
kernel by itself. It models continuity coordinates as evidence and gates, but
authority, identity, recovery, memory, federation, liability, and TCB enforcement
must be implemented by deployment controls or connected systems. If an analysis
recommends workflow investment that changes tools, credentials, memory, or
release behavior, the actual execution must be mediated by a separate authority
gate such as OAWM `ActionIntent` plus action-bound receipt.

The full profile still does not certify factual truth, model honesty, or
production safety. It certifies that the reported lower bound is procedurally
admissible under the supplied evidence contracts.
