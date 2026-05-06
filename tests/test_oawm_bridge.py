from __future__ import annotations

import sqlite3

from certified_workflow_conversion.adapters.oawm_bridge import OAWMSQLiteBridge
from certified_workflow_conversion.core.canonical import canonical_json
from certified_workflow_conversion.core.models import (
    ClaimRequirement,
    ConversionNetwork,
    ServiceEdgeProfile,
)
from certified_workflow_conversion.runtime.kernel import ConversionKernel


def test_oawm_bridge_imports_only_certified_and_passed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "oawm.sqlite"
    with sqlite3.connect(db) as con:
        con.executescript(
            """
            CREATE TABLE events(obs_seq INTEGER, raw_json TEXT);
            CREATE TABLE evidence_manifests(raw_json TEXT);
            CREATE TABLE promotion_receipts(raw_json TEXT);
            CREATE TABLE memory_records(raw_json TEXT);
            """
        )
        con.execute(
            "INSERT INTO events(obs_seq, raw_json) VALUES (?, ?)",
            (1, canonical_json({"event_id": "evt_1", "run_id": "run-a", "payload": {}})),
        )
        con.execute(
            "INSERT INTO evidence_manifests(raw_json) VALUES (?)",
            (canonical_json({"manifest_id": "evm_1", "candidate_id": "mem_1"}),),
        )
        con.execute(
            "INSERT INTO promotion_receipts(raw_json) VALUES (?)",
            (
                canonical_json(
                    {
                        "receipt_id": "rcp_pass",
                        "result": "passed",
                        "evidence_refs": ["evm_1"],
                    }
                ),
            ),
        )
        con.execute(
            "INSERT INTO promotion_receipts(raw_json) VALUES (?)",
            (
                canonical_json(
                    {
                        "receipt_id": "rcp_fail",
                        "result": "failed",
                        "evidence_refs": ["evm_2"],
                    }
                ),
            ),
        )
        con.execute(
            "INSERT INTO memory_records(raw_json) VALUES (?)",
            (canonical_json({"memory_id": "mem_1", "lane": "certified"}),),
        )
        con.execute(
            "INSERT INTO memory_records(raw_json) VALUES (?)",
            (canonical_json({"memory_id": "mem_2", "lane": "candidate"}),),
        )

    imported = OAWMSQLiteBridge().import_state(db, run_id="run-a")
    kinds = [item.kind for item in imported]
    assert "oawm.event" in kinds
    assert "oawm.promotion_receipt.passed" in kinds
    assert "oawm.memory.certified" in kinds
    refs = {ref for item in imported for ref in item.external_refs}
    assert "evm_1" in refs
    receipt = next(item for item in imported if item.kind == "oawm.promotion_receipt.passed")
    assert receipt.dependencies == ["evm_1"]
    assert all(item.payload.get("receipt_id") != "rcp_fail" for item in imported)
    assert all(item.payload.get("memory_id") != "mem_2" for item in imported)

    kernel = ConversionKernel.open(tmp_path / "cwc")
    stored = kernel.import_oawm(db, run_id="run-a")
    stored_receipt = next(item for item in stored if item.kind == "oawm.promotion_receipt.passed")
    network = kernel.register_network(
        ConversionNetwork.create(
            name="oawm-import",
            nodes=["candidate", "released"],
            edges=[
                ServiceEdgeProfile.create(
                    name="oawm-certified-step",
                    from_node="candidate",
                    to_node="released",
                    capacity=1,
                    evidence_ids=[stored_receipt.evidence_id],
                )
            ],
        )
    )
    claim = kernel.compile_claim(
        ClaimRequirement.create(
            network_id=network.network_id,
            target_value=1,
            required_evidence_ids=[stored_receipt.evidence_id],
        )
    )
    assert claim.supported is True
