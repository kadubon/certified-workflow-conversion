from __future__ import annotations

import datetime as dt

from certified_workflow_conversion.core.canonical import digest_json
from certified_workflow_conversion.core.models import (
    HardGate,
    RiskCharge,
    ServiceEdgeProfile,
    TypedEvidenceObject,
    now_utc,
)


def test_canonical_digest_is_deterministic() -> None:
    assert digest_json({"b": 1, "a": 2}) == digest_json({"a": 2, "b": 1})


def test_evidence_digest_and_expiry() -> None:
    evidence = TypedEvidenceObject.create(
        kind="validation",
        scope="core",
        source="test",
        payload={"ok": True},
        expiry=now_utc() - dt.timedelta(seconds=1),
    )
    assert evidence.payload_digest == digest_json({"ok": True})
    assert evidence.is_expired() is True


def test_edge_capacity_respects_risk_and_hard_gate() -> None:
    edge = ServiceEdgeProfile.create(
        name="review",
        from_node="a",
        to_node="b",
        capacity=5,
        hard_gates=[HardGate.create(name="authority", passed=False)],
        risk_charges=[RiskCharge.create(kind="open_world", amount=2)],
    )
    assert edge.certified_capacity() == 3
    assert edge.blocked_gates()[0].name == "authority"

