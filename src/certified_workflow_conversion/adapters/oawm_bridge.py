"""Read-only OAWM SQLite bridge."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import orjson

from certified_workflow_conversion.core.errors import FailClosedError
from certified_workflow_conversion.core.models import (
    ContinuityCoordinate,
    TypedEvidenceObject,
)


class OAWMSQLiteBridge:
    bridge_name = "oawm-sqlite"

    def import_state(
        self,
        path: str | Path,
        *,
        run_id: str | None = None,
    ) -> list[TypedEvidenceObject]:
        db_path = _resolve_oawm_db(path)
        uri = f"file:{db_path.as_posix()}?mode=ro"
        evidence: list[TypedEvidenceObject] = []
        try:
            with sqlite3.connect(uri, uri=True) as con:
                con.row_factory = sqlite3.Row
                evidence.extend(_import_events(con, run_id=run_id))
                evidence.extend(_import_raw_table(con, "evidence_manifests"))
                evidence.extend(_import_passed_receipts(con))
                evidence.extend(_import_certified_memory(con))
                evidence.extend(_import_raw_table(con, "workflow_contracts"))
        except sqlite3.Error as exc:
            raise FailClosedError(f"could not read OAWM state: {exc}") from exc
        return evidence


def _resolve_oawm_db(path: str | Path) -> Path:
    target = Path(path)
    if target.is_dir():
        target = target / "oawm.sqlite"
    if not target.exists():
        raise FailClosedError(f"OAWM SQLite state not found: {target}")
    return target


def _import_events(con: sqlite3.Connection, *, run_id: str | None) -> list[TypedEvidenceObject]:
    if not _table_exists(con, "events"):
        return []
    rows = con.execute("SELECT raw_json FROM events ORDER BY obs_seq").fetchall()
    result: list[TypedEvidenceObject] = []
    for row in rows:
        payload = _load_raw(row)
        if run_id is not None and payload.get("run_id") != run_id:
            continue
        result.append(
            TypedEvidenceObject.create(
                kind="oawm.event",
                scope=str(payload.get("run_id") or "oawm"),
                source="oawm:events",
                payload=payload,
                external_refs=_external_refs(payload),
                continuity_coordinates=[ContinuityCoordinate.SERVICE],
            )
        )
    return result


def _import_raw_table(con: sqlite3.Connection, table: str) -> list[TypedEvidenceObject]:
    if not _table_exists(con, table):
        return []
    rows = con.execute(f"SELECT raw_json FROM {table}").fetchall()
    return [
        TypedEvidenceObject.create(
            kind=f"oawm.{table.rstrip('s')}",
            scope="oawm",
            source=f"oawm:{table}",
            payload=_load_raw(row),
            external_refs=_external_refs(_load_raw(row)),
            continuity_coordinates=[ContinuityCoordinate.SERVICE],
        )
        for row in rows
    ]


def _import_passed_receipts(con: sqlite3.Connection) -> list[TypedEvidenceObject]:
    if not _table_exists(con, "promotion_receipts"):
        return []
    rows = con.execute("SELECT raw_json FROM promotion_receipts").fetchall()
    result: list[TypedEvidenceObject] = []
    for row in rows:
        payload = _load_raw(row)
        if payload.get("result") != "passed":
            continue
        result.append(
            TypedEvidenceObject.create(
                kind="oawm.promotion_receipt.passed",
                scope="oawm",
                source="oawm:promotion_receipts",
                payload=payload,
                external_refs=_external_refs(payload),
                dependencies=[str(item) for item in payload.get("evidence_refs", [])],
                continuity_coordinates=[
                    ContinuityCoordinate.SERVICE,
                    ContinuityCoordinate.MEMORY,
                ],
            )
        )
    return result


def _import_certified_memory(con: sqlite3.Connection) -> list[TypedEvidenceObject]:
    if not _table_exists(con, "memory_records"):
        return []
    rows = con.execute("SELECT raw_json FROM memory_records").fetchall()
    result: list[TypedEvidenceObject] = []
    for row in rows:
        payload = _load_raw(row)
        if payload.get("lane") != "certified":
            continue
        result.append(
            TypedEvidenceObject.create(
                kind="oawm.memory.certified",
                scope="oawm",
                source="oawm:memory_records",
                payload=payload,
                external_refs=_external_refs(payload),
                dependencies=[str(item) for item in payload.get("evidence_refs", [])],
                continuity_coordinates=[
                    ContinuityCoordinate.SERVICE,
                    ContinuityCoordinate.MEMORY,
                ],
            )
        )
    return result


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _load_raw(row: sqlite3.Row) -> dict[str, Any]:
    payload = orjson.loads(str(row["raw_json"]))
    if not isinstance(payload, dict):
        raise FailClosedError("OAWM raw_json must contain an object")
    return payload


def _external_refs(payload: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in [
        "event_id",
        "manifest_id",
        "receipt_id",
        "verification_id",
        "memory_id",
        "update_id",
        "workflow_contract_id",
        "contract_id",
        "action_id",
    ]:
        value = payload.get(key)
        if isinstance(value, str) and value:
            refs.append(value)
    return sorted(set(refs))


def create_bridge() -> OAWMSQLiteBridge:
    return OAWMSQLiteBridge()
