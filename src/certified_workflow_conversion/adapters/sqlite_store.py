"""SQLite storage adapter."""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from certified_workflow_conversion.core.canonical import canonical_json
from certified_workflow_conversion.core.errors import FailClosedError, NotFoundError
from certified_workflow_conversion.core.models import (
    BottleneckReport,
    CompiledClaim,
    ConversionNetwork,
    StorageCapabilities,
    StoredEvidence,
    TypedEvidenceObject,
    now_utc,
)


class SQLiteStore:
    backend_name = "sqlite"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._active_con: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(
                """
                PRAGMA user_version = 1;
                CREATE TABLE IF NOT EXISTS evidence (
                    obs_seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    evidence_id TEXT NOT NULL UNIQUE,
                    scope TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    obs_time TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS networks (
                    network_id TEXT PRIMARY KEY,
                    raw_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS claims (
                    claim_seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    compilation_id TEXT NOT NULL UNIQUE,
                    claim_id TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    report_seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id TEXT NOT NULL UNIQUE,
                    network_id TEXT NOT NULL,
                    claim_id TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );
                """
            )

    def append_evidence(self, evidence: TypedEvidenceObject) -> StoredEvidence:
        obs_time = now_utc()
        stored = StoredEvidence(
            **evidence.model_dump(),
            obs_seq=0,
            obs_time=obs_time,
        )
        raw_json = canonical_json(stored.model_dump(mode="json", exclude={"obs_seq"}))
        with self._connect() as con:
            try:
                cur = con.execute(
                    """
                    INSERT INTO evidence(evidence_id, scope, kind, raw_json, obs_time)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        evidence.evidence_id,
                        evidence.scope,
                        evidence.kind,
                        raw_json,
                        obs_time.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError:
                existing = self.get_evidence(evidence.evidence_id)
                if _stored_evidence_payload(existing) != evidence.model_dump(mode="json"):
                    raise FailClosedError("evidence id collision with different payload") from None
                return existing
            if cur.lastrowid is None:
                raise FailClosedError("SQLite did not return evidence obs_seq")
            obs_seq = int(cur.lastrowid)
        data = stored.model_dump()
        data["obs_seq"] = obs_seq
        return StoredEvidence.model_validate(data)

    def get_evidence(self, evidence_id: str) -> StoredEvidence:
        with self._connect() as con:
            row = con.execute(
                "SELECT raw_json, obs_seq FROM evidence WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"evidence not found: {evidence_id}")
        payload = _loads_model_json(str(row["raw_json"]))
        payload["obs_seq"] = int(row["obs_seq"])
        return StoredEvidence.model_validate(payload)

    def list_evidence(
        self,
        *,
        scope: str | None = None,
        kind: str | None = None,
        limit: int | None = None,
    ) -> list[StoredEvidence]:
        clauses: list[str] = []
        args: list[object] = []
        if scope is not None:
            clauses.append("scope = ?")
            args.append(scope)
        if kind is not None:
            clauses.append("kind = ?")
            args.append(kind)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_sql = "LIMIT ?" if limit is not None else ""
        if limit is not None:
            args.append(limit)
        sql = f"SELECT raw_json, obs_seq FROM evidence {where} ORDER BY obs_seq {limit_sql}"
        with self._connect() as con:
            rows = con.execute(sql, args).fetchall()
        result: list[StoredEvidence] = []
        for row in rows:
            payload = _loads_model_json(str(row["raw_json"]))
            payload["obs_seq"] = int(row["obs_seq"])
            result.append(StoredEvidence.model_validate(payload))
        return result

    def upsert_network(self, network: ConversionNetwork) -> ConversionNetwork:
        raw_json = canonical_json(network.model_dump(mode="json"))
        with self._connect() as con:
            existing = con.execute(
                "SELECT raw_json FROM networks WHERE network_id = ?",
                (network.network_id,),
            ).fetchone()
            if existing is not None and str(existing["raw_json"]) != raw_json:
                raise FailClosedError("network id collision with different content")
            con.execute(
                "INSERT OR IGNORE INTO networks(network_id, raw_json) VALUES (?, ?)",
                (network.network_id, raw_json),
            )
        return network

    def get_network(self, network_id: str) -> ConversionNetwork:
        with self._connect() as con:
            row = con.execute(
                "SELECT raw_json FROM networks WHERE network_id = ?",
                (network_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"network not found: {network_id}")
        return ConversionNetwork.model_validate(_loads_model_json(str(row["raw_json"])))

    def append_claim(self, claim: CompiledClaim) -> CompiledClaim:
        raw_json = canonical_json(claim.model_dump(mode="json"))
        with self._connect() as con:
            existing = con.execute(
                "SELECT raw_json FROM claims WHERE compilation_id = ?",
                (claim.compilation_id,),
            ).fetchone()
            if existing is not None and str(existing["raw_json"]) != raw_json:
                raise FailClosedError("compilation id collision with different content")
            con.execute(
                """
                INSERT OR IGNORE INTO claims(compilation_id, claim_id, raw_json)
                VALUES (?, ?, ?)
                """,
                (claim.compilation_id, claim.claim_id, raw_json),
            )
        return claim

    def get_claim(self, claim_id: str) -> CompiledClaim:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT raw_json FROM claims
                WHERE claim_id = ? OR compilation_id = ?
                ORDER BY claim_seq DESC
                LIMIT 1
                """,
                (claim_id, claim_id),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"claim not found: {claim_id}")
        return CompiledClaim.model_validate(_loads_model_json(str(row["raw_json"])))

    def append_report(self, report: BottleneckReport) -> BottleneckReport:
        raw_json = canonical_json(report.model_dump(mode="json"))
        with self._connect() as con:
            existing = con.execute(
                "SELECT raw_json FROM reports WHERE report_id = ?",
                (report.report_id,),
            ).fetchone()
            if existing is not None and str(existing["raw_json"]) != raw_json:
                raise FailClosedError("report id collision with different content")
            con.execute(
                """
                INSERT OR IGNORE INTO reports(report_id, network_id, claim_id, raw_json)
                VALUES (?, ?, ?, ?)
                """,
                (report.report_id, report.network_id, report.claim_id, raw_json),
            )
        return report

    def get_report(self, report_id: str) -> BottleneckReport:
        with self._connect() as con:
            row = con.execute(
                "SELECT raw_json FROM reports WHERE report_id = ?",
                (report_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"report not found: {report_id}")
        return BottleneckReport.model_validate(_loads_model_json(str(row["raw_json"])))

    def audit_counts(self) -> dict[str, int]:
        with self._connect() as con:
            return {
                "evidence": _count(con, "evidence"),
                "networks": _count(con, "networks"),
                "claims": _count(con, "claims"),
                "reports": _count(con, "reports"),
            }

    @contextlib.contextmanager
    def transaction(self) -> Iterator[None]:
        if self._active_con is not None:
            yield
            return
        con = self._open()
        self._active_con = con
        try:
            con.execute("BEGIN")
            yield
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            self._active_con = None
            con.close()

    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities(transactions=True, json_query=False, migrations=True)

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._active_con is not None:
            yield self._active_con
            return
        con = self._open()
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _open(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con


def _count(con: sqlite3.Connection, table: str) -> int:
    row = con.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"])


def _loads_model_json(raw: str) -> dict[str, Any]:
    import orjson

    payload = orjson.loads(raw)
    if not isinstance(payload, dict):
        raise FailClosedError("stored JSON model must be an object")
    return payload


def _stored_evidence_payload(evidence: StoredEvidence) -> dict[str, Any]:
    payload = evidence.model_dump(mode="json")
    payload.pop("obs_seq", None)
    payload.pop("obs_time", None)
    return payload


def create_store(path: str | Path) -> SQLiteStore:
    return SQLiteStore(path)
