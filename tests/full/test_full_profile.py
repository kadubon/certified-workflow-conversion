from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("scipy")

from certified_workflow_conversion.adapters.in_memory_store import InMemoryStore
from certified_workflow_conversion.adapters.json_loader import load_mapping
from certified_workflow_conversion.adapters.scipy_flow import solve_conservative_flow
from certified_workflow_conversion.adapters.statistical_certificates import (
    dynamic_path_lower_bound,
    one_step_dr_lower_bound,
    time_uniform_lower_bound,
)
from certified_workflow_conversion.adapters.validation_capital import (
    certify_validation_capital,
)
from certified_workflow_conversion.core.certificates import (
    CompositionRule,
    DynamicPathLawCertificate,
    EvidenceContract,
    GoodhartBudget,
    OpenWorldHazardCharge,
    QueueCertificate,
    ReleaseAccountingCertificate,
    StatisticalCertificate,
    ValidationDependencyEdge,
    ValidationDependencyGraph,
    VerificationWitness,
)
from certified_workflow_conversion.core.errors import FailClosedError
from certified_workflow_conversion.core.models import (
    ClaimRequirement,
    CompiledClaim,
    ConversionNetwork,
    EvidenceStatus,
    HardGate,
    ServiceEdgeProfile,
    TypedEvidenceObject,
)
from certified_workflow_conversion.runtime.kernel import ConversionKernel


def test_full_certified_lower_bound_passes_with_complete_evidence() -> None:
    kernel, network, claim = _full_kernel()

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "ok"
    assert report.lower_bound == 3
    assert report.full_profile_status == "full_checked"
    assert report.dual_price_intervals


def test_full_certified_lower_bound_blocks_missing_contract() -> None:
    kernel, network, claim = _full_kernel(omit_kind="evidence_contract")

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    assert "evidence_contract" in " ".join(report.limitations)


def test_full_certified_lower_bound_blocks_confidence_budget_overflow() -> None:
    kernel, network, claim = _full_kernel(confidence_budget=1)

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    assert "confidence budget exceeded" in " ".join(report.limitations)


def test_full_profile_blocks_hard_gate_even_when_lp_has_capacity() -> None:
    kernel, network, claim = _full_kernel(hard_gate_passed=False)

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    assert report.lower_bound == 0
    assert "hard gates are non-compensable" in " ".join(report.limitations)


def test_full_profile_blocks_generic_support_for_arbitrary_edge_capacity() -> None:
    kernel, network, claim = _full_kernel(
        capacity=999,
        target_value=999,
        contract_exposes=(
            "statistical_lower,path_law_lower,queue_boundary,"
            "release_accounting,goodhart_charge,open_world_charge"
        ),
    )

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    assert "edge capacity lacks accepted contract/witness binding" in " ".join(
        report.limitations
    )


def test_full_profile_certificate_lower_bounds_cap_flow() -> None:
    kernel, network, claim = _full_kernel(capacity=999, target_value=999)

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "ok"
    assert report.lower_bound == 8
    assert report.certificate_summary["flow_lower_bound"] == 999
    assert report.certificate_summary["certificate_lower_bound_cap"] == pytest.approx(8.8)


def test_full_profile_queue_and_risk_terms_reduce_lower_bound() -> None:
    kernel, network, claim = _full_kernel(
        capacity=999,
        target_value=999,
        queue_boundary=1,
        direct_cost_rate=1,
        goodhart_charge=1,
        open_world_charge=1,
    )

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "ok"
    assert report.lower_bound == 4
    assert report.certificate_summary["deductions"] == {
        "queue_boundary_correction": 1.0,
        "direct_cost_rate": 1.0,
        "goodhart_total": 1.0,
        "open_world_charge": 1.0,
    }


def test_full_profile_blocks_unrelated_witness_exposes() -> None:
    kernel, network, claim = _full_kernel(witness_exposes="edge.capacity:other")

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    assert "witness exposes do not match contract" in " ".join(report.limitations)


def test_full_profile_blocks_mismatched_witness_digest() -> None:
    kernel, network, claim = _full_kernel(witness_checker_digest="different-checker")

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    assert "witness checker digest mismatch" in " ".join(report.limitations)


def test_full_profile_blocks_unrooted_contract_tcb() -> None:
    kernel, network, claim = _full_kernel(contract_tcb=["root-a"])

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    assert "contract has unmet rooted TCB requirement" in " ".join(report.limitations)


def test_full_profile_allows_overlap_with_explicit_uniform_witness() -> None:
    kernel, network, claim = _full_kernel(split_overlap=True, composition_rule="uniform")

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "ok"


def test_full_profile_blocks_overlap_without_uniform_witness() -> None:
    kernel, network, claim = _full_kernel(split_overlap=True)

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    assert "certification split overlaps" in " ".join(report.limitations)


def test_full_profile_blocks_contract_that_exposes_multiple_terms() -> None:
    kernel, network, claim = _full_kernel(single_multi_term_contract=True)

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    assert "contract must expose exactly one" in " ".join(report.limitations)


def test_full_profile_blocks_ambiguous_edge_name_capacity_binding() -> None:
    kernel, network, claim = _full_kernel(duplicate_edge_name=True)

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    assert "edge capacity binding by name is ambiguous" in " ".join(report.limitations)


def test_full_profile_blocks_positive_queue_boundary_without_derivation() -> None:
    kernel, network, claim = _full_kernel(
        capacity=999,
        target_value=999,
        queue_boundary=1,
        queue_boundary_derivation=False,
    )

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    assert "positive queue boundary correction lacks derivation" in " ".join(
        report.limitations
    )


def test_full_profile_blocks_positive_goodhart_without_construction_evidence() -> None:
    kernel, network, claim = _full_kernel(
        capacity=999,
        target_value=999,
        goodhart_charge=1,
        goodhart_construction_evidence=False,
    )

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    assert "positive Goodhart charge lacks construction evidence" in " ".join(
        report.limitations
    )


def test_full_profile_blocks_empty_uncertainty_contract() -> None:
    kernel, network, claim = _full_kernel(uncertainty_nonempty=False)

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    assert "uncertainty contract must include nonempty proof" in " ".join(
        report.limitations
    )


def test_full_profile_blocks_report_term_contract_without_source_dependency() -> None:
    kernel, network, claim = _full_kernel(omit_term_dependencies=True)

    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )

    assert report.status.value == "blocked"
    joined = " ".join(report.limitations)
    assert (
        "report-term contract lacks dependency on source evidence" in joined
        or "edge capacity contract does not depend on edge support evidence" in joined
    )


def test_inactive_evidence_cannot_support_claim() -> None:
    kernel = ConversionKernel.open(".", plugins={"storage": InMemoryStore()})
    evidence = kernel.add_evidence(
        TypedEvidenceObject.create(
            kind="validation",
            scope="inactive",
            source="test",
            payload={"ok": True},
            status=EvidenceStatus.QUARANTINED,
        )
    )
    network = kernel.register_network(
        ConversionNetwork.create(
            name="inactive",
            nodes=["a", "b"],
            edges=[
                ServiceEdgeProfile.create(
                    name="edge",
                    from_node="a",
                    to_node="b",
                    capacity=1,
                    evidence_ids=[evidence.evidence_id],
                )
            ],
        )
    )
    claim = kernel.compile_claim(
        ClaimRequirement.create(
            network_id=network.network_id,
            target_value=1,
            required_evidence_ids=[evidence.evidence_id],
        )
    )
    assert claim.supported is False
    assert "inactive evidence" in claim.reason


def test_duplicate_json_key_and_nan_fail_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"kind":"a","kind":"b"}', encoding="utf-8")
    with pytest.raises(FailClosedError):
        load_mapping(duplicate)

    nonfinite = tmp_path / "nan.json"
    nonfinite.write_text('{"value": NaN}', encoding="utf-8")
    with pytest.raises(FailClosedError):
        load_mapping(nonfinite)


def test_evidence_collision_uses_full_object_not_only_payload_digest() -> None:
    store = InMemoryStore()
    evidence = TypedEvidenceObject.create(
        kind="validation",
        scope="collision",
        source="test",
        payload={"ok": True},
    )
    store.append_evidence(evidence)
    changed = TypedEvidenceObject(
        **{
            **evidence.model_dump(),
            "root_refs": ["different-root"],
        }
    )
    with pytest.raises(FailClosedError):
        store.append_evidence(changed)


def test_statistical_certificate_formulas() -> None:
    one_step = one_step_dr_lower_bound(
        estimate=10.0,
        b_z=1.0,
        candidate_count=2,
        delta=0.05,
        n=100,
        epsilon_int=0.1,
        epsilon_label=0.2,
    )
    assert one_step < 10.0
    assert dynamic_path_lower_bound(lower_q=8.0, bound_b=2.0, epsilon_path=0.25) == 7.0
    assert time_uniform_lower_bound(
        lower_q=8.0,
        bound_b=2.0,
        epsilon_tau=0.25,
        delta_val=0.01,
        delta_path=0.02,
        max_delta=0.05,
    )["joint_delta"] == pytest.approx(0.03)


def test_scipy_flow_handles_parallel_graph_and_prices() -> None:
    network = ConversionNetwork.create(
        name="parallel-full",
        nodes=["s", "l", "r", "t"],
        source_nodes=["s"],
        sink_nodes=["t"],
        edges=[
            ServiceEdgeProfile.create(name="sl", from_node="s", to_node="l", capacity=5),
            ServiceEdgeProfile.create(name="lt", from_node="l", to_node="t", capacity=5),
            ServiceEdgeProfile.create(name="sr", from_node="s", to_node="r", capacity=7),
            ServiceEdgeProfile.create(name="rt", from_node="r", to_node="t", capacity=7),
        ],
    )

    result = solve_conservative_flow(network, target_value=20)

    assert result["lower_bound"] == 12
    assert result["dual_price_intervals"]


def test_validation_capital_blocks_rootless_demand() -> None:
    graph = ValidationDependencyGraph(
        nodes=["root", "checker", "orphan"],
        root_nodes=["root"],
        edges=[
            ValidationDependencyEdge(
                from_node="root",
                to_node="checker",
                kind="capacity",
                capacity=1,
            )
        ],
        demand_nodes=["checker", "orphan"],
        demands={"checker": 1, "orphan": 1},
    )

    certificate = certify_validation_capital(graph)

    assert "orphan" in certificate.blocked_nodes
    assert certificate.supported_demand < sum(graph.demands.values())


def _full_kernel(
    *,
    omit_kind: str | None = None,
    confidence_budget: int = 1_000_000,
    hard_gate_passed: bool = True,
    capacity: int = 5,
    target_value: int = 3,
    contract_exposes: str | None = None,
    witness_exposes: str | None = None,
    witness_checker_digest: str | None = None,
    queue_boundary: float = 0,
    direct_cost_rate: float = 0,
    goodhart_charge: float = 0,
    open_world_charge: float = 0,
    split_overlap: bool = False,
    composition_rule: CompositionRule | None = None,
    contract_tcb: list[str] | None = None,
    queue_boundary_derivation: bool = True,
    goodhart_construction_evidence: bool = True,
    uncertainty_nonempty: bool = True,
    single_multi_term_contract: bool = False,
    duplicate_edge_name: bool = False,
    omit_term_dependencies: bool = False,
) -> tuple[ConversionKernel, ConversionNetwork, CompiledClaim]:
    kernel = ConversionKernel.open(".", plugins={"storage": InMemoryStore()})
    evidence = _full_evidence(
        confidence_budget=confidence_budget,
        edge_capacity=capacity,
        contract_exposes=contract_exposes,
        witness_exposes=witness_exposes,
        witness_checker_digest=witness_checker_digest,
        queue_boundary=queue_boundary,
        direct_cost_rate=direct_cost_rate,
        goodhart_charge=goodhart_charge,
        open_world_charge=open_world_charge,
        composition_rule=composition_rule,
        contract_tcb=contract_tcb,
        queue_boundary_derivation=queue_boundary_derivation,
        goodhart_construction_evidence=goodhart_construction_evidence,
        uncertainty_nonempty=uncertainty_nonempty,
        single_multi_term_contract=single_multi_term_contract,
        omit_term_dependencies=omit_term_dependencies,
    )
    stored = [
        kernel.add_evidence(item)
        for item in evidence
        if item.kind != omit_kind
    ]
    evidence_ids = [item.evidence_id for item in stored]
    support_id = next(item.evidence_id for item in stored if item.kind == "support")
    edges = [
        ServiceEdgeProfile.create(
            name="edge",
            from_node="a",
            to_node="b",
            capacity=capacity,
            evidence_ids=[support_id],
            hard_gates=[
                HardGate.create(
                    name="authority",
                    passed=hard_gate_passed,
                    evidence_ids=[support_id],
                )
            ],
        )
    ]
    nodes = ["a", "b"]
    sink_nodes = ["b"]
    if duplicate_edge_name:
        nodes.append("c")
        sink_nodes.append("c")
        edges.append(
            ServiceEdgeProfile.create(
                name="edge",
                from_node="a",
                to_node="c",
                capacity=capacity,
                evidence_ids=[support_id],
            )
        )
    network = kernel.register_network(
        ConversionNetwork.create(
            name="full",
            nodes=nodes,
            source_nodes=["a"],
            sink_nodes=sink_nodes,
            edges=edges,
        )
    )
    ledger_id = next(item.evidence_id for item in stored if item.kind == "root")
    selection_id = next(
        (item.evidence_id for item in stored if item.kind == "evidence_contract"),
        ledger_id,
    )
    certification_id = next(
        (item.evidence_id for item in stored if item.kind == "verification_witness"),
        ledger_id,
    )
    claim = kernel.compile_claim(
        ClaimRequirement.create(
            network_id=network.network_id,
            target_value=target_value,
            required_evidence_ids=evidence_ids,
            certification_split={
                "ledger": [ledger_id],
                "selection": [ledger_id if split_overlap else selection_id],
                "certification": [certification_id],
            },
        )
    )
    return kernel, network, claim


def _full_evidence(
    *,
    confidence_budget: int,
    edge_capacity: int,
    contract_exposes: str | None = None,
    witness_exposes: str | None = None,
    witness_checker_digest: str | None = None,
    queue_boundary: float = 0,
    direct_cost_rate: float = 0,
    goodhart_charge: float = 0,
    open_world_charge: float = 0,
    composition_rule: CompositionRule | None = None,
    contract_tcb: list[str] | None = None,
    queue_boundary_derivation: bool = True,
    goodhart_construction_evidence: bool = True,
    uncertainty_nonempty: bool = True,
    single_multi_term_contract: bool = False,
    omit_term_dependencies: bool = False,
) -> list[TypedEvidenceObject]:
    stat_params = {
        "estimate": 10,
        "b_z": 1,
        "candidate_count": 1,
        "delta": 0.05,
        "n": 100,
    }
    path_cert = DynamicPathLawCertificate(
        lower_q=9,
        bound_b=1,
        epsilon_path=0.1,
    )
    exposes = contract_exposes or (
        "edge.capacity:edge,statistical_lower,path_law_lower,queue_boundary,"
        "release_accounting,goodhart_charge,open_world_charge"
    )
    checker_digest = "checker"
    input_digest = "input"
    term_values = {
        "edge.capacity:edge": edge_capacity,
        "statistical_lower": 9.0,
        "path_law_lower": path_cert.lower_bound(),
        "queue_boundary": queue_boundary,
        "release_accounting": direct_cost_rate,
        "goodhart_charge": goodhart_charge,
        "open_world_charge": open_world_charge,
    }
    support = TypedEvidenceObject.create(
        kind="support",
        scope="full",
        source="test",
        payload={"supported": True},
    )
    statistical = TypedEvidenceObject.create(
        kind="statistical_certificate",
        scope="full",
        source="test",
        payload=StatisticalCertificate(
            kind="one_step_dr",
            params=stat_params,
        ).model_dump(mode="json"),
    )
    path_law = TypedEvidenceObject.create(
        kind="path_law_certificate",
        scope="full",
        source="test",
        payload=path_cert.model_dump(mode="json"),
    )
    queue = TypedEvidenceObject.create(
        kind="queue_certificate",
        scope="full",
        source="test",
        payload=QueueCertificate(
            service_discipline="fifo",
            no_phantom_release=True,
            bounded_increments=True,
            boundary_correction=queue_boundary,
            boundary_derivation=(
                {"source": "lyapunov-smoke-test"}
                if queue_boundary > 0 and queue_boundary_derivation
                else {}
            ),
        ).model_dump(mode="json"),
    )
    release = TypedEvidenceObject.create(
        kind="release_accounting",
        scope="full",
        source="test",
        payload=ReleaseAccountingCertificate(
            reward_lower_bounds={"accepted": 1},
            direct_cost_rate=direct_cost_rate,
            disjoint_ledgers=True,
        ).model_dump(mode="json"),
    )
    goodhart = TypedEvidenceObject.create(
        kind="goodhart_account",
        scope="full",
        source="test",
        payload=GoodhartBudget(
            statistical=goodhart_charge,
            construction_evidence=(
                ["challenge-transport-bound"]
                if goodhart_charge > 0 and goodhart_construction_evidence
                else []
            ),
        ).model_dump(mode="json"),
    )
    open_world = TypedEvidenceObject.create(
        kind="open_world_account",
        scope="full",
        source="test",
        payload=OpenWorldHazardCharge(
            coordinate="release",
            charge=open_world_charge,
            construction_evidence=["surface-inventory"],
            fallback_action="hold",
        ).model_dump(mode="json"),
    )
    term_dependencies = {
        "edge.capacity:edge": [support.evidence_id],
        "statistical_lower": [statistical.evidence_id],
        "path_law_lower": [path_law.evidence_id],
        "queue_boundary": [queue.evidence_id],
        "release_accounting": [release.evidence_id],
        "goodhart_charge": [goodhart.evidence_id],
        "open_world_charge": [open_world.evidence_id],
    }
    terms = [term.strip() for term in exposes.split(",") if term.strip()]
    contract_witness_evidence: list[TypedEvidenceObject] = []
    if single_multi_term_contract:
        contract_witness_evidence.extend(
            _contract_witness_objects(
                term=exposes,
                output={
                    "capacity": edge_capacity,
                    "statistical_lower": 9.0,
                    "path_law_lower": path_cert.lower_bound(),
                    "queue_boundary": queue_boundary,
                    "release_accounting": direct_cost_rate,
                    "goodhart_charge": goodhart_charge,
                    "open_world_charge": open_world_charge,
                },
                input_digest=input_digest,
                checker_digest=checker_digest,
                witness_checker_digest=witness_checker_digest,
                witness_exposes=witness_exposes,
                composition_rule=composition_rule,
                contract_tcb=contract_tcb,
                dependencies=(
                    [] if omit_term_dependencies else [
                        ref for refs in term_dependencies.values() for ref in refs
                    ]
                ),
            )
        )
    else:
        for term in terms:
            output: dict[str, Any] = {term: term_values.get(term, 0)}
            if term.startswith("edge.capacity:"):
                output["capacity"] = edge_capacity
            if term == "release_accounting":
                output["direct_cost_rate"] = direct_cost_rate
            if composition_rule is not None:
                output["composition_rule"] = composition_rule
            contract_witness_evidence.extend(
                _contract_witness_objects(
                    term=term,
                    output=output,
                    input_digest=input_digest,
                    checker_digest=checker_digest,
                    witness_checker_digest=witness_checker_digest,
                    witness_exposes=witness_exposes,
                    composition_rule=composition_rule,
                    contract_tcb=contract_tcb,
                    dependencies=[] if omit_term_dependencies else term_dependencies.get(term, []),
                )
            )
    graph = ValidationDependencyGraph(
        nodes=["root", "checker"],
        root_nodes=["root"],
        edges=[
            ValidationDependencyEdge(
                from_node="root",
                to_node="checker",
                kind="capacity",
                capacity=3,
            )
        ],
        demand_nodes=["checker"],
        demands={"checker": 2},
    )
    return [
        TypedEvidenceObject.create(
            kind="root",
            scope="full",
            source="test",
            payload={"name": "root", "status": "ok", "rooted": True},
        ),
        *contract_witness_evidence,
        support,
        TypedEvidenceObject.create(
            kind="uncertainty_contract",
            scope="full",
            source="test",
            payload={"nonempty": uncertainty_nonempty},
        ),
        statistical,
        path_law,
        queue,
        release,
        goodhart,
        open_world,
        TypedEvidenceObject.create(
            kind="confidence_budget",
            scope="full",
            source="test",
            payload={"max_microunits": confidence_budget},
        ),
        TypedEvidenceObject.create(
            kind="validation_dependency_graph",
            scope="full",
            source="test",
            payload=graph.model_dump(mode="json"),
        ),
    ]


def _contract_witness_objects(
    *,
    term: str,
    output: dict[str, Any],
    input_digest: str,
    checker_digest: str,
    witness_checker_digest: str | None,
    witness_exposes: str | None,
    composition_rule: CompositionRule | None,
    contract_tcb: list[str] | None,
    dependencies: list[str],
) -> list[TypedEvidenceObject]:
    contract = EvidenceContract.create(
        type="constraint",
        target="full",
        checker="unit-checker",
        exposes=term,
        scope={"scope": "full"},
        assumptions={
            "input_digest": input_digest,
            "checker_digest": checker_digest,
        },
        budget_microunits=1_000,
        compose=composition_rule or "deterministic",
        tcb=contract_tcb,
        dependencies=dependencies,
    )
    witness = VerificationWitness.create(
        contract_id=contract.contract_id,
        input_digest=input_digest,
        checker_digest=witness_checker_digest or checker_digest,
        verifier="unit-test",
        accepted_output=output,
        scope=contract.scope,
        exposes=witness_exposes or contract.exposes,
        tcb=contract_tcb,
    )
    return [
        TypedEvidenceObject.create(
            kind="evidence_contract",
            scope="full",
            source="test",
            payload=contract.model_dump(mode="json"),
            confidence_microunits=1_000,
        ),
        TypedEvidenceObject.create(
            kind="verification_witness",
            scope="full",
            source="test",
            payload=witness.model_dump(mode="json"),
        ),
    ]
