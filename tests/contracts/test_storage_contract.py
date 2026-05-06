from __future__ import annotations

import pytest

from certified_workflow_conversion.adapters.in_memory_store import InMemoryStore
from certified_workflow_conversion.adapters.sqlite_store import SQLiteStore
from certified_workflow_conversion.core.errors import NotFoundError
from certified_workflow_conversion.core.models import TypedEvidenceObject
from certified_workflow_conversion.testing.contracts import (
    assert_collision_fails,
    exercise_storage_contract,
)


def test_in_memory_storage_contract() -> None:
    exercise_storage_contract(InMemoryStore)
    assert_collision_fails(InMemoryStore)


def test_sqlite_storage_contract(tmp_path) -> None:  # type: ignore[no-untyped-def]
    def factory() -> SQLiteStore:
        return SQLiteStore(tmp_path / "cwc.sqlite")

    exercise_storage_contract(factory)
    assert_collision_fails(lambda: SQLiteStore(tmp_path / "collision.sqlite"))


def test_sqlite_transaction_rolls_back(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = SQLiteStore(tmp_path / "rollback.sqlite")
    store.initialize()
    evidence = TypedEvidenceObject.create(
        kind="validation",
        scope="rollback",
        source="test",
        payload={"ok": True},
    )
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.append_evidence(evidence)
            raise RuntimeError("rollback")
    with pytest.raises(NotFoundError):
        store.get_evidence(evidence.evidence_id)


def test_sqlite_claim_compilations_are_append_only(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = SQLiteStore(tmp_path / "claims.sqlite")
    store.initialize()
    request_network = "net_" + "0" * 32
    from certified_workflow_conversion.core.models import ClaimRequirement, CompiledClaim

    request = ClaimRequirement.create(network_id=request_network, target_value=1)
    first = store.append_claim(
        CompiledClaim.create(request=request, supported=False, reason="missing evidence")
    )
    second = store.append_claim(CompiledClaim.create(request=request, supported=True))
    assert first.claim_id == second.claim_id
    assert first.compilation_id != second.compilation_id
    assert store.get_claim(request.claim_id).supported is True
    assert store.audit_counts()["claims"] == 2
