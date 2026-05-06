"""Reusable adapter contract tests."""

from __future__ import annotations

from collections.abc import Callable

from certified_workflow_conversion.core.errors import FailClosedError
from certified_workflow_conversion.core.models import (
    ClaimRequirement,
    CompiledClaim,
    ConversionNetwork,
    ServiceEdgeProfile,
    StorageCapabilities,
    TypedEvidenceObject,
)
from certified_workflow_conversion.ports.storage import StorageBackend


def exercise_storage_contract(factory: Callable[[], StorageBackend]) -> None:
    store = factory()
    store.initialize()
    assert isinstance(store.capabilities(), StorageCapabilities)

    evidence = TypedEvidenceObject.create(
        kind="validation",
        scope="contract",
        source="test",
        payload={"passed": True},
    )
    stored = store.append_evidence(evidence)
    assert stored.obs_seq >= 1
    assert store.get_evidence(evidence.evidence_id).payload_digest == evidence.payload_digest
    assert [item.evidence_id for item in store.list_evidence(scope="contract")] == [
        evidence.evidence_id
    ]

    network = ConversionNetwork.create(
        name="contract-network",
        nodes=["a", "b"],
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
    store.upsert_network(network)
    assert store.get_network(network.network_id).network_id == network.network_id

    request = ClaimRequirement.create(
        network_id=network.network_id,
        target_value=2,
        required_evidence_ids=[evidence.evidence_id],
    )
    claim = CompiledClaim.create(
        request=request,
        supported=True,
        evidence_ids=[evidence.evidence_id],
    )
    store.append_claim(claim)
    assert store.get_claim(claim.claim_id).supported is True

    counts = store.audit_counts()
    assert counts["evidence"] == 1
    assert counts["networks"] == 1
    assert counts["claims"] == 1


def assert_collision_fails(factory: Callable[[], StorageBackend]) -> None:
    store = factory()
    store.initialize()
    evidence = TypedEvidenceObject.create(
        kind="validation",
        scope="contract",
        source="test",
        payload={"passed": True},
    )
    store.append_evidence(evidence)
    data = evidence.model_dump()
    data["payload"] = {"passed": False}
    data["payload_digest"] = "0" * 64
    try:
        store.append_evidence(TypedEvidenceObject(**data))
    except (FailClosedError, ValueError):
        return
    raise AssertionError("collision did not fail closed")
