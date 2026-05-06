"""In-memory storage adapter used by tests and plugin authors."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

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


class InMemoryStore:
    backend_name = "memory"

    def __init__(self) -> None:
        self._evidence: dict[str, StoredEvidence] = {}
        self._networks: dict[str, ConversionNetwork] = {}
        self._claims: list[CompiledClaim] = []
        self._claims_by_compilation: dict[str, CompiledClaim] = {}
        self._reports: dict[str, BottleneckReport] = {}
        self._obs_seq = 0

    def initialize(self) -> None:
        return None

    def append_evidence(self, evidence: TypedEvidenceObject) -> StoredEvidence:
        existing = self._evidence.get(evidence.evidence_id)
        if existing is not None:
            if _stored_evidence_payload(existing) != evidence.model_dump(mode="json"):
                raise FailClosedError("evidence id collision with different payload")
            return existing
        self._obs_seq += 1
        stored = StoredEvidence(
            **evidence.model_dump(),
            obs_seq=self._obs_seq,
            obs_time=now_utc(),
        )
        self._evidence[stored.evidence_id] = stored
        return stored

    def get_evidence(self, evidence_id: str) -> StoredEvidence:
        try:
            return self._evidence[evidence_id]
        except KeyError as exc:
            raise NotFoundError(f"evidence not found: {evidence_id}") from exc

    def list_evidence(
        self,
        *,
        scope: str | None = None,
        kind: str | None = None,
        limit: int | None = None,
    ) -> list[StoredEvidence]:
        values = sorted(self._evidence.values(), key=lambda item: item.obs_seq)
        if scope is not None:
            values = [item for item in values if item.scope == scope]
        if kind is not None:
            values = [item for item in values if item.kind == kind]
        return values[:limit] if limit is not None else values

    def upsert_network(self, network: ConversionNetwork) -> ConversionNetwork:
        existing = self._networks.get(network.network_id)
        if existing is not None and existing.content_digest() != network.content_digest():
            raise FailClosedError("network id collision with different content")
        self._networks[network.network_id] = network
        return network

    def get_network(self, network_id: str) -> ConversionNetwork:
        try:
            return self._networks[network_id]
        except KeyError as exc:
            raise NotFoundError(f"network not found: {network_id}") from exc

    def append_claim(self, claim: CompiledClaim) -> CompiledClaim:
        existing = self._claims_by_compilation.get(claim.compilation_id)
        if existing is not None and existing.model_dump() != claim.model_dump():
            raise FailClosedError("compilation id collision with different content")
        if existing is None:
            self._claims.append(claim)
            self._claims_by_compilation[claim.compilation_id] = claim
        return claim

    def get_claim(self, claim_id: str) -> CompiledClaim:
        if claim_id in self._claims_by_compilation:
            return self._claims_by_compilation[claim_id]
        for claim in reversed(self._claims):
            if claim.claim_id == claim_id:
                return claim
        raise NotFoundError(f"claim not found: {claim_id}")

    def append_report(self, report: BottleneckReport) -> BottleneckReport:
        existing = self._reports.get(report.report_id)
        if existing is not None and existing.model_dump() != report.model_dump():
            raise FailClosedError("report id collision with different content")
        self._reports[report.report_id] = report
        return report

    def get_report(self, report_id: str) -> BottleneckReport:
        try:
            return self._reports[report_id]
        except KeyError as exc:
            raise NotFoundError(f"report not found: {report_id}") from exc

    def audit_counts(self) -> dict[str, int]:
        return {
            "evidence": len(self._evidence),
            "networks": len(self._networks),
            "claims": len(self._claims),
            "reports": len(self._reports),
        }

    @contextlib.contextmanager
    def transaction(self) -> Iterator[None]:
        yield

    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities(transactions=False)


def create_store() -> InMemoryStore:
    return InMemoryStore()


def _stored_evidence_payload(evidence: StoredEvidence) -> dict[str, object]:
    payload = evidence.model_dump(mode="json")
    payload.pop("obs_seq", None)
    payload.pop("obs_time", None)
    return payload
