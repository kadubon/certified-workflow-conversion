"""Analyzer and optimizer ports."""

from __future__ import annotations

from typing import Any, Protocol

from certified_workflow_conversion.core.models import (
    AnalysisMode,
    BottleneckReport,
    CompiledClaim,
    ConversionNetwork,
    InvestmentBudget,
    InvestmentCandidate,
    StoredEvidence,
)


class Analyzer(Protocol):
    analyzer_name: str

    def analyze(
        self,
        *,
        network: ConversionNetwork,
        claim: CompiledClaim,
        evidence: list[StoredEvidence],
        allocation: dict[str, int] | None = None,
        mode: AnalysisMode = AnalysisMode.DIAGNOSTIC,
    ) -> BottleneckReport:
        """Analyze certified conversion throughput."""


class Optimizer(Protocol):
    optimizer_name: str

    def propose(
        self,
        *,
        network: ConversionNetwork,
        budget: InvestmentBudget,
        constraints: dict[str, Any] | None = None,
    ) -> list[InvestmentCandidate]:
        """Propose diagnostic investment candidates."""

