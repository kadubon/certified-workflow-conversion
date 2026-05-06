# Security Model

CWC is a local diagnostic and reporting kernel. It is not a sandbox, credential
manager, or external-effect gateway.

Security-relevant assumptions:

- Local storage is trusted local state in v0.1.0 beta.
- Evidence can be incomplete, stale, or adversarial.
- Expired evidence, missing dependencies, unsupported scopes, and missing TCB
  requirements fail closed at claim compilation.
- `tcb_requirements` on evidence declare dependencies; they do not prove TCB
  health. A TCB requirement is satisfied only by rooted TCB evidence with
  `status == "ok"`.
- Unsupported service edge capacity is not certified throughput. Edges,
  reservations, queue states, risk charges, and hard gates must reference active
  evidence.
- In `full` profile, report-facing terms must be bound one-to-one by an active
  evidence contract and an accepted witness. Ambiguous edge-name bindings fail
  closed.
- Report-term contracts must depend on the source evidence that generated the
  term, so accepted witnesses cannot be detached from their statistical,
  queue, release, Goodhart, open-world, or edge-support evidence.
- Nonempty uncertainty contracts, positive queue boundary corrections, and
  positive Goodhart/open-world charges require explicit proof or construction
  evidence.
- Hard gates are non-compensable.
- Diagnostic investment output is not authorization to execute a change.
- `light` profile is a diagnostic screen, not a statistical certification mode.
- `full` profile is fail-closed and evidence-bound, but it is not a sandbox and
  does not verify hidden operating-system, network, credential, or human-process
  channels.
- External effects still require OS, network, identity, and secrets controls.
- OAWM integration is read-only import by default.

Certified throughput means evidence-bound procedural reportability. It does not
mean factual truth, model honesty, safe production deployment, or full
continuity certification. Authority, identity, recovery, memory, federation,
liability, and trusted-base controls must still be enforced by the deployment or
by connected systems.
