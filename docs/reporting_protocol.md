# Reporting Protocol

CWC reports should separate:

- ledger data: evidence used to build the current typed evidence ledger;
- selection data: evidence used to choose a network/controller/investment;
- certification data: evidence used to certify the final reported claim.

When the split is omitted, CWC can still produce diagnostic reports, but
`certified_lower_bound` mode fails closed. Diagnostic reports must not be
described as final certified adoption evidence.

In `light` profile, `certified_lower_bound` mode always fails closed. The light
analyzer is intentionally limited to engineering triage and cannot emit
certified lower-bound reports.

In `full` profile, certified lower-bound mode additionally requires accepted
verification witnesses, confidence budget composition, source/sink declarations,
statistical or path-law certificates, release accounting, root evidence, and a
validation dependency graph whose demanded nodes are root-reachable and within
root-cut capacity.

Full-profile reports also require report-term binding. Each `EvidenceContract`
exposes exactly one claim-facing object. Each service-edge capacity must be
exposed as `edge.capacity:<edge_id>` or, when edge names are unique,
`edge.capacity:<edge_name>` by an accepted contract/witness pair. The final
lower bound is capped by statistical and path-law lower certificates, then
reduced by queue boundary, direct cost, Goodhart, and open-world charge terms.
If any exposed term is missing, mismatched, inactive, ambiguous, or numerically
weaker than the certificate payload requires, the report is blocked.

The contract for a term must also name the evidence that produced that term in
its dependency list. This prevents a free-floating accepted witness from being
reused against an unrelated statistical certificate, queue certificate, release
accounting record, Goodhart account, open-world account, or edge support item.

Positive queue-boundary and Goodhart charges require derivation or construction
evidence. The nonempty uncertainty contract must include a nonempty proof,
constructive law, feasibility proof, or solver certificate.

If data references overlap across ledger, selection, and certification splits,
all active report-facing contracts must use an explicit uniform, time-uniform,
e-process, or simultaneous composition witness. A single unrelated witness is
not sufficient to justify adaptive reuse.

Every report includes limitations. Diagnostic bottleneck scores are local
screening signals and can be invalid under drift, hidden dependencies, Goodhart
pressure, or unsupported hazard classes.
