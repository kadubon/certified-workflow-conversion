from __future__ import annotations

from certified_workflow_conversion.adapters.in_memory_store import InMemoryStore
from certified_workflow_conversion.core.certificates import (
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
from certified_workflow_conversion.core.models import (
    ClaimRequirement,
    CompiledClaim,
    ConversionNetwork,
    ServiceEdgeProfile,
    TypedEvidenceObject,
)
from certified_workflow_conversion.runtime.kernel import ConversionKernel


def build_full_demo() -> tuple[ConversionKernel, ConversionNetwork, CompiledClaim]:
    kernel = ConversionKernel.open(".", plugins={"storage": InMemoryStore()})
    path_cert = DynamicPathLawCertificate(
        lower_q=9,
        bound_b=1,
        epsilon_path=0.1,
    )
    support = TypedEvidenceObject.create(
        kind="support",
        scope="demo",
        source="example",
        payload={"supported": True},
    )
    statistical = TypedEvidenceObject.create(
        kind="statistical_certificate",
        scope="demo",
        source="example",
        payload=StatisticalCertificate(
            kind="one_step_dr",
            params={
                "estimate": 10,
                "b_z": 1,
                "candidate_count": 1,
                "delta": 0.05,
                "n": 100,
            },
        ).model_dump(mode="json"),
    )
    path_law = TypedEvidenceObject.create(
        kind="path_law_certificate",
        scope="demo",
        source="example",
        payload=path_cert.model_dump(mode="json"),
    )
    queue = TypedEvidenceObject.create(
        kind="queue_certificate",
        scope="demo",
        source="example",
        payload=QueueCertificate(
            service_discipline="fifo",
            no_phantom_release=True,
            bounded_increments=True,
            boundary_correction=0,
            boundary_derivation={},
        ).model_dump(mode="json"),
    )
    release = TypedEvidenceObject.create(
        kind="release_accounting",
        scope="demo",
        source="example",
        payload=ReleaseAccountingCertificate(
            reward_lower_bounds={"accepted": 1},
            direct_cost_rate=0,
            disjoint_ledgers=True,
        ).model_dump(mode="json"),
    )
    goodhart = TypedEvidenceObject.create(
        kind="goodhart_account",
        scope="demo",
        source="example",
        payload=GoodhartBudget(statistical=0).model_dump(mode="json"),
    )
    open_world = TypedEvidenceObject.create(
        kind="open_world_account",
        scope="demo",
        source="example",
        payload=OpenWorldHazardCharge(
            coordinate="release",
            charge=0,
            construction_evidence=["surface-inventory"],
            fallback_action="hold",
        ).model_dump(mode="json"),
    )
    term_outputs = {
        "edge.capacity:certified-release": {
            "edge.capacity:certified-release": 5,
            "capacity": 5,
        },
        "statistical_lower": {"statistical_lower": 9.0},
        "path_law_lower": {"path_law_lower": path_cert.lower_bound()},
        "queue_boundary": {"queue_boundary": 0},
        "release_accounting": {"release_accounting": 0, "direct_cost_rate": 0},
        "goodhart_charge": {"goodhart_charge": 0},
        "open_world_charge": {"open_world_charge": 0},
    }
    term_dependencies = {
        "edge.capacity:certified-release": [support.evidence_id],
        "statistical_lower": [statistical.evidence_id],
        "path_law_lower": [path_law.evidence_id],
        "queue_boundary": [queue.evidence_id],
        "release_accounting": [release.evidence_id],
        "goodhart_charge": [goodhart.evidence_id],
        "open_world_charge": [open_world.evidence_id],
    }
    graph = ValidationDependencyGraph(
        nodes=["root", "checker"],
        root_nodes=["root"],
        edges=[
            ValidationDependencyEdge(
                from_node="root",
                to_node="checker",
                kind="capacity",
                capacity=4,
            )
        ],
        demand_nodes=["checker"],
        demands={"checker": 2},
    )
    evidence = [
        TypedEvidenceObject.create(
            kind="root",
            scope="demo",
            source="example",
            payload={"name": "root", "status": "ok", "rooted": True},
        ),
        *[
            item
            for term, output in term_outputs.items()
            for item in _contract_witness_evidence(
                term=term,
                output=output,
                dependencies=term_dependencies[term],
            )
        ],
        support,
        TypedEvidenceObject.create(
            kind="uncertainty_contract",
            scope="demo",
            source="example",
            payload={"nonempty": True},
        ),
        statistical,
        path_law,
        queue,
        release,
        goodhart,
        open_world,
        TypedEvidenceObject.create(
            kind="confidence_budget",
            scope="demo",
            source="example",
            payload={"max_microunits": 1_000_000},
        ),
        TypedEvidenceObject.create(
            kind="validation_dependency_graph",
            scope="demo",
            source="example",
            payload=graph.model_dump(mode="json"),
        ),
    ]
    stored = [kernel.add_evidence(item) for item in evidence]
    support_id = next(item.evidence_id for item in stored if item.kind == "support")
    network = kernel.register_network(
        ConversionNetwork.create(
            name="full-demo",
            nodes=["candidate", "released"],
            source_nodes=["candidate"],
            sink_nodes=["released"],
            edges=[
                ServiceEdgeProfile.create(
                    name="certified-release",
                    from_node="candidate",
                    to_node="released",
                    capacity=5,
                    evidence_ids=[support_id],
                )
            ],
        )
    )
    evidence_ids = [item.evidence_id for item in stored]
    claim = kernel.compile_claim(
        ClaimRequirement.create(
            network_id=network.network_id,
            target_value=3,
            required_evidence_ids=evidence_ids,
            certification_split={
                "ledger": [evidence_ids[0]],
                "selection": [evidence_ids[1]],
                "certification": [evidence_ids[2]],
            },
        )
    )
    return kernel, network, claim


def _contract_witness_evidence(
    *,
    term: str,
    output: dict[str, float | int],
    dependencies: list[str],
) -> list[TypedEvidenceObject]:
    contract = EvidenceContract.create(
        type="constraint",
        target="demo",
        checker="example-checker",
        exposes=term,
        scope={"scope": "demo"},
        assumptions={
            "input_digest": "example-input",
            "checker_digest": "example-checker",
        },
        budget_microunits=1_000,
        dependencies=dependencies,
    )
    witness = VerificationWitness.create(
        contract_id=contract.contract_id,
        input_digest="example-input",
        checker_digest="example-checker",
        verifier="example",
        accepted_output=output,
        scope=contract.scope,
        exposes=contract.exposes,
    )
    return [
        TypedEvidenceObject.create(
            kind="evidence_contract",
            scope="demo",
            source="example",
            payload=contract.model_dump(mode="json"),
            confidence_microunits=1_000,
        ),
        TypedEvidenceObject.create(
            kind="verification_witness",
            scope="demo",
            source="example",
            payload=witness.model_dump(mode="json"),
        ),
    ]
