from __future__ import annotations

from tempfile import TemporaryDirectory

from certified_workflow_conversion.core.models import (
    CapacityReservation,
    ClaimRequirement,
    ConversionNetwork,
    InvestmentBudget,
    QueueState,
    ServiceEdgeProfile,
    TypedEvidenceObject,
)
from certified_workflow_conversion.runtime.kernel import ConversionKernel


def main() -> None:
    with TemporaryDirectory(prefix="cwc-demo-") as state:
        kernel = ConversionKernel.open(state)

        validation = kernel.add_evidence(
            TypedEvidenceObject.create(
                kind="validation",
                scope="coding-demo",
                source="pytest",
                payload={"tests_passed": True, "cases": 12},
                tcb_requirements=["local-runner"],
            )
        )
        review = kernel.add_evidence(
            TypedEvidenceObject.create(
                kind="review",
                scope="coding-demo",
                source="review-log",
                payload={"blocking_findings": 0},
            )
        )
        release_queue = kernel.add_evidence(
            TypedEvidenceObject.create(
                kind="queue_certificate",
                scope="coding-demo",
                source="release-log",
                payload={"backlog": 2, "arrival_rate": 3, "service_rate": 2},
            )
        )
        tcb = kernel.add_evidence(
            TypedEvidenceObject.create(
                kind="tcb",
                scope="coding-demo",
                source="local",
                payload={"name": "local-runner", "status": "ok", "rooted": True},
            )
        )

        network = kernel.register_network(
            ConversionNetwork.create(
                name="coding-agent-pipeline",
                nodes=["proposal", "validated", "reviewed", "released"],
                edges=[
                    ServiceEdgeProfile.create(
                        name="test validation",
                        from_node="proposal",
                        to_node="validated",
                        capacity=6,
                        evidence_ids=[validation.evidence_id],
                    ),
                    ServiceEdgeProfile.create(
                        name="human review",
                        from_node="validated",
                        to_node="reviewed",
                        capacity=3,
                        evidence_ids=[review.evidence_id],
                        reservations=[
                            CapacityReservation(
                                resource="reviewer-hours",
                                amount=1,
                                evidence_ids=[review.evidence_id],
                            )
                        ],
                    ),
                    ServiceEdgeProfile.create(
                        name="release approval",
                        from_node="reviewed",
                        to_node="released",
                        capacity=4,
                        evidence_ids=[release_queue.evidence_id],
                        queue_state=QueueState(
                            edge_id="release",
                            backlog=2,
                            arrival_rate=3,
                            service_rate=2,
                            evidence_ids=[release_queue.evidence_id],
                        ),
                    ),
                ],
            )
        )
        claim = kernel.compile_claim(
            ClaimRequirement.create(
                network_id=network.network_id,
                target_value=5,
                required_scopes=["coding-demo"],
                required_evidence_ids=[
                    validation.evidence_id,
                    review.evidence_id,
                    release_queue.evidence_id,
                    tcb.evidence_id,
                ],
                required_tcb=["local-runner"],
            )
        )
        report = kernel.analyze(network.network_id, claim.claim_id)
        investments = kernel.propose_investments(
            network.network_id,
            InvestmentBudget.create(units=2),
        )
        print(
            {
                "claim_supported": claim.supported,
                "lower_bound": report.lower_bound,
                "bottleneck_edges": report.bottleneck_edges,
                "investment_edges": [item.edge_id for item in investments],
            }
        )


if __name__ == "__main__":
    main()
