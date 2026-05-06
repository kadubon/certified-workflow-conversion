from __future__ import annotations

import datetime as dt

from certified_workflow_conversion.adapters.in_memory_store import InMemoryStore
from certified_workflow_conversion.core.models import (
    ClaimRequirement,
    ConversionNetwork,
    HardGate,
    ServiceEdgeProfile,
    TypedEvidenceObject,
    now_utc,
)
from certified_workflow_conversion.runtime.kernel import ConversionKernel


def _kernel() -> ConversionKernel:
    return ConversionKernel.open(".", plugins={"storage": InMemoryStore()})


def test_compile_claim_fails_closed_on_expired_evidence() -> None:
    kernel = _kernel()
    evidence = kernel.add_evidence(
        TypedEvidenceObject.create(
            kind="validation",
            scope="demo",
            source="test",
            payload={"ok": True},
            expiry=now_utc() - dt.timedelta(seconds=1),
        )
    )
    network = kernel.register_network(
        ConversionNetwork.create(
            name="demo",
            nodes=["a", "b"],
            edges=[
                ServiceEdgeProfile.create(
                    name="edge",
                    from_node="a",
                    to_node="b",
                    capacity=5,
                    evidence_ids=[evidence.evidence_id],
                )
            ],
        )
    )
    claim = kernel.compile_claim(
        ClaimRequirement.create(
            network_id=network.network_id,
            target_value=3,
            required_evidence_ids=[evidence.evidence_id],
        )
    )
    assert claim.supported is False
    assert "expired evidence" in claim.reason


def test_compile_claim_rejects_unsupported_edge_capacity() -> None:
    kernel = _kernel()
    network = kernel.register_network(
        ConversionNetwork.create(
            name="unsupported",
            nodes=["a", "b"],
            edges=[
                ServiceEdgeProfile.create(
                    name="edge",
                    from_node="a",
                    to_node="b",
                    capacity=99,
                )
            ],
        )
    )
    claim = kernel.compile_claim(
        ClaimRequirement.create(network_id=network.network_id, target_value=50)
    )
    report = kernel.analyze(network.network_id, claim.claim_id)
    assert claim.supported is False
    assert "has no capacity/support evidence" in claim.reason
    assert report.status.value == "blocked"
    assert report.lower_bound == 0


def test_tcb_requirements_need_rooted_tcb_evidence() -> None:
    kernel = _kernel()
    evidence = kernel.add_evidence(
        TypedEvidenceObject.create(
            kind="validation",
            scope="demo",
            source="test",
            payload={"ok": True},
            tcb_requirements=["root-a"],
        )
    )
    network = kernel.register_network(
        ConversionNetwork.create(
            name="demo",
            nodes=["a", "b"],
            edges=[
                ServiceEdgeProfile.create(
                    name="edge",
                    from_node="a",
                    to_node="b",
                    capacity=5,
                    evidence_ids=[evidence.evidence_id],
                )
            ],
        )
    )
    claim = kernel.compile_claim(
        ClaimRequirement.create(
            network_id=network.network_id,
            target_value=3,
            required_evidence_ids=[evidence.evidence_id],
            required_tcb=["root-a"],
        )
    )
    assert claim.supported is False
    assert "missing TCB requirement: root-a" in claim.reason


def test_hard_gate_blocks_report() -> None:
    kernel = _kernel()
    evidence = kernel.add_evidence(
        TypedEvidenceObject.create(
            kind="authority",
            scope="demo",
            source="test",
            payload={"authorized": False},
        )
    )
    network = kernel.register_network(
        ConversionNetwork.create(
            name="demo",
            nodes=["a", "b"],
            edges=[
                ServiceEdgeProfile.create(
                    name="edge",
                    from_node="a",
                    to_node="b",
                    capacity=100,
                    evidence_ids=[evidence.evidence_id],
                    hard_gates=[
                        HardGate.create(
                            name="authority",
                            passed=False,
                            reason="token revoked",
                            evidence_ids=[evidence.evidence_id],
                        )
                    ],
                )
            ],
        )
    )
    claim = kernel.compile_claim(
        ClaimRequirement.create(
            network_id=network.network_id,
            target_value=10,
            required_evidence_ids=[evidence.evidence_id],
        )
    )
    report = kernel.analyze(network.network_id, claim.claim_id)
    assert report.status.value == "blocked"
    assert report.lower_bound == 0
    assert "hard gates are non-compensable" in report.limitations


def test_certified_lower_bound_requires_reporting_protocol() -> None:
    kernel = _kernel()
    evidence = kernel.add_evidence(
        TypedEvidenceObject.create(
            kind="validation",
            scope="demo",
            source="test",
            payload={"ok": True},
        )
    )
    network = kernel.register_network(
        ConversionNetwork.create(
            name="demo",
            nodes=["a", "b"],
            edges=[
                ServiceEdgeProfile.create(
                    name="edge",
                    from_node="a",
                    to_node="b",
                    capacity=5,
                    evidence_ids=[evidence.evidence_id],
                )
            ],
        )
    )
    claim = kernel.compile_claim(
        ClaimRequirement.create(
            network_id=network.network_id,
            target_value=3,
            required_evidence_ids=[evidence.evidence_id],
        )
    )
    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
    )
    assert report.status.value == "blocked"
    assert "light profile cannot emit certified lower-bound reports" in " ".join(
        report.limitations
    )


def test_compile_claim_fails_on_missing_dependency_and_tcb() -> None:
    kernel = _kernel()
    evidence = kernel.add_evidence(
        TypedEvidenceObject.create(
            kind="validation",
            scope="demo",
            source="test",
            payload={"ok": True},
            dependencies=["ev_missing"],
        )
    )
    network = kernel.register_network(
        ConversionNetwork.create(
            name="demo",
            nodes=["a", "b"],
            edges=[
                ServiceEdgeProfile.create(
                    name="edge",
                    from_node="a",
                    to_node="b",
                    capacity=5,
                    evidence_ids=[evidence.evidence_id],
                )
            ],
        )
    )
    claim = kernel.compile_claim(
        ClaimRequirement.create(
            network_id=network.network_id,
            target_value=3,
            required_evidence_ids=[evidence.evidence_id],
            required_tcb=["independent-runner"],
        )
    )
    assert claim.supported is False
    assert "missing dependency" in claim.reason
    assert "missing TCB requirement" in claim.reason


def test_bottleneck_and_investment_are_diagnostic() -> None:
    kernel = _kernel()
    evidence = kernel.add_evidence(
        TypedEvidenceObject.create(
            kind="validation",
            scope="demo",
            source="test",
            payload={"ok": True},
        )
    )
    network = kernel.register_network(
        ConversionNetwork.create(
            name="demo",
            nodes=["a", "b", "c"],
            edges=[
                ServiceEdgeProfile.create(
                    name="fast",
                    from_node="a",
                    to_node="b",
                    capacity=10,
                    evidence_ids=[evidence.evidence_id],
                ),
                ServiceEdgeProfile.create(
                    name="slow",
                    from_node="b",
                    to_node="c",
                    capacity=2,
                    evidence_ids=[evidence.evidence_id],
                ),
            ],
        )
    )
    claim = kernel.compile_claim(
        ClaimRequirement.create(
            network_id=network.network_id,
            target_value=8,
            required_evidence_ids=[evidence.evidence_id],
        )
    )
    report = kernel.analyze(network.network_id, claim.claim_id)
    assert report.lower_bound == 2
    assert len(report.bottleneck_edges) == 1
    assert report.diagnostic_scores[report.bottleneck_edges[0]] == 1
    assert "not deployment authorization" in " ".join(report.limitations)


def test_parallel_graph_uses_flow_not_global_min_edge() -> None:
    kernel = _kernel()
    evidence = kernel.add_evidence(
        TypedEvidenceObject.create(
            kind="validation",
            scope="demo",
            source="test",
            payload={"ok": True},
        )
    )
    network = kernel.register_network(
        ConversionNetwork.create(
            name="parallel",
            nodes=["source", "left", "right", "sink"],
            edges=[
                ServiceEdgeProfile.create(
                    name="left-in",
                    from_node="source",
                    to_node="left",
                    capacity=5,
                    evidence_ids=[evidence.evidence_id],
                ),
                ServiceEdgeProfile.create(
                    name="left-out",
                    from_node="left",
                    to_node="sink",
                    capacity=5,
                    evidence_ids=[evidence.evidence_id],
                ),
                ServiceEdgeProfile.create(
                    name="right-in",
                    from_node="source",
                    to_node="right",
                    capacity=7,
                    evidence_ids=[evidence.evidence_id],
                ),
                ServiceEdgeProfile.create(
                    name="right-out",
                    from_node="right",
                    to_node="sink",
                    capacity=7,
                    evidence_ids=[evidence.evidence_id],
                ),
            ],
        )
    )
    claim = kernel.compile_claim(
        ClaimRequirement.create(
            network_id=network.network_id,
            target_value=20,
            required_evidence_ids=[evidence.evidence_id],
        )
    )
    report = kernel.analyze(network.network_id, claim.claim_id)
    assert report.lower_bound == 12


def test_disconnected_isolated_node_does_not_create_flow() -> None:
    kernel = _kernel()
    evidence = kernel.add_evidence(
        TypedEvidenceObject.create(
            kind="validation",
            scope="demo",
            source="test",
            payload={"ok": True},
        )
    )
    network = kernel.register_network(
        ConversionNetwork.create(
            name="disconnected",
            nodes=["isolated", "a", "b"],
            edges=[
                ServiceEdgeProfile.create(
                    name="edge",
                    from_node="a",
                    to_node="b",
                    capacity=3,
                    evidence_ids=[evidence.evidence_id],
                )
            ],
        )
    )
    claim = kernel.compile_claim(
        ClaimRequirement.create(
            network_id=network.network_id,
            target_value=20,
            required_evidence_ids=[evidence.evidence_id],
        )
    )
    report = kernel.analyze(network.network_id, claim.claim_id)
    assert report.lower_bound == 3
