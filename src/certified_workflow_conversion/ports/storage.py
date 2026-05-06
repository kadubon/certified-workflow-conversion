"""Storage backend ports."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from certified_workflow_conversion.core.models import (
    BottleneckReport,
    CompiledClaim,
    ConversionNetwork,
    StorageCapabilities,
    StoredEvidence,
    TypedEvidenceObject,
)


class EvidenceFilter(Protocol):
    scope: str | None
    kind: str | None
    limit: int | None


class EvidenceStore(Protocol):
    def append_evidence(self, evidence: TypedEvidenceObject) -> StoredEvidence:
        """Append one evidence object."""

    def get_evidence(self, evidence_id: str) -> StoredEvidence:
        """Return one evidence object."""

    def list_evidence(
        self,
        *,
        scope: str | None = None,
        kind: str | None = None,
        limit: int | None = None,
    ) -> list[StoredEvidence]:
        """List evidence in observable order."""


class NetworkStore(Protocol):
    def upsert_network(self, network: ConversionNetwork) -> ConversionNetwork:
        """Store a conversion network."""

    def get_network(self, network_id: str) -> ConversionNetwork:
        """Return a conversion network."""


class ReportStore(Protocol):
    def append_claim(self, claim: CompiledClaim) -> CompiledClaim:
        """Append or idempotently store a compiled claim."""

    def get_claim(self, claim_id: str) -> CompiledClaim:
        """Return a compiled claim."""

    def append_report(self, report: BottleneckReport) -> BottleneckReport:
        """Append or idempotently store a report."""

    def get_report(self, report_id: str) -> BottleneckReport:
        """Return a report."""


class StorageBackend(EvidenceStore, NetworkStore, ReportStore, Protocol):
    backend_name: str

    def initialize(self) -> None:
        """Create required structures."""

    def audit_counts(self) -> dict[str, int]:
        """Return coarse audit counts."""

    def transaction(self) -> AbstractContextManager[None]:
        """Return a transaction context manager."""

    def capabilities(self) -> StorageCapabilities:
        """Declare backend features."""
