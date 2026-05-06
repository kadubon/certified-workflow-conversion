"""Deterministic conservative analyzer."""

from __future__ import annotations

from typing import Any

from certified_workflow_conversion.core.models import (
    AnalysisMode,
    BottleneckReport,
    CompiledClaim,
    ConversionNetwork,
    InvestmentBudget,
    InvestmentCandidate,
    ReportStatus,
    ServiceEdgeProfile,
    StoredEvidence,
)


class DeterministicAnalyzer:
    analyzer_name = "deterministic"

    def analyze(
        self,
        *,
        network: ConversionNetwork,
        claim: CompiledClaim,
        evidence: list[StoredEvidence],
        allocation: dict[str, int] | None = None,
        mode: AnalysisMode = AnalysisMode.DIAGNOSTIC,
    ) -> BottleneckReport:
        del allocation
        evidence_ids = [item.evidence_id for item in evidence]
        if mode == AnalysisMode.CERTIFIED_LOWER_BOUND:
            return BottleneckReport.create(
                network_id=network.network_id,
                claim_id=claim.claim_id,
                mode=mode,
                status=ReportStatus.BLOCKED,
                lower_bound=0,
                bottleneck_edges=[],
                diagnostic_scores={},
                total_risk_charge=0,
                hard_gate_failures=[],
                evidence_ids=evidence_ids,
                limitations=[
                    "light profile cannot emit certified lower-bound reports",
                    "rerun with profile='full' and evidence contracts, "
                    "witnesses, and report-term bindings",
                ],
            )
        if not claim.supported:
            return BottleneckReport.create(
                network_id=network.network_id,
                claim_id=claim.claim_id,
                mode=mode,
                status=ReportStatus.BLOCKED,
                lower_bound=0,
                bottleneck_edges=[],
                diagnostic_scores={},
                total_risk_charge=0,
                hard_gate_failures=[],
                evidence_ids=evidence_ids,
                limitations=[f"claim unsupported: {claim.reason}"],
            )

        hard_gate_failures = [
            f"{edge.edge_id}:{gate.name}:{gate.reason}"
            for edge in network.edges
            for gate in edge.blocked_gates()
        ]
        total_risk_charge = sum(
            charge.amount for edge in network.edges for charge in edge.risk_charges
        )
        if hard_gate_failures:
            return BottleneckReport.create(
                network_id=network.network_id,
                claim_id=claim.claim_id,
                mode=mode,
                status=ReportStatus.BLOCKED,
                lower_bound=0,
                bottleneck_edges=[],
                diagnostic_scores={},
                total_risk_charge=total_risk_charge,
                hard_gate_failures=hard_gate_failures,
                evidence_ids=evidence_ids,
                limitations=["hard gates are non-compensable"],
            )

        lower_bound = _network_lower_bound(network, claim.request.target_value)
        diagnostic_scores = _diagnostic_scores(network, claim.request.target_value)
        bottlenecks = [
            edge_id for edge_id, score in diagnostic_scores.items() if score > 0
        ]
        return BottleneckReport.create(
            network_id=network.network_id,
            claim_id=claim.claim_id,
            mode=mode,
            status=ReportStatus.OK,
            lower_bound=lower_bound,
            bottleneck_edges=bottlenecks,
            diagnostic_scores=diagnostic_scores,
            total_risk_charge=total_risk_charge,
            evidence_ids=evidence_ids,
            limitations=[
                "diagnostic scores are screening signals, not deployment authorization",
                "diagnostic mode is a conservative flow heuristic, not a certified adoption claim",
                "the report does not certify factual truth",
            ],
        )


class DeterministicOptimizer:
    optimizer_name = "deterministic"

    def propose(
        self,
        *,
        network: ConversionNetwork,
        budget: InvestmentBudget,
        constraints: dict[str, Any] | None = None,
    ) -> list[InvestmentCandidate]:
        del constraints
        scores = _diagnostic_scores(network, target_value=10**9)
        candidates: list[InvestmentCandidate] = []
        for edge in sorted(network.edges, key=lambda item: (-scores[item.edge_id], item.edge_id)):
            if len(candidates) >= budget.units:
                break
            score = scores[edge.edge_id]
            if score <= 0:
                continue
            candidates.append(
                InvestmentCandidate.create(
                    edge_id=edge.edge_id,
                    resource=f"increase capacity on {edge.name}",
                    cost=1,
                    expected_lower_bound_gain=score,
                    reason="diagnostic marginal bottleneck gain",
                )
            )
        return candidates


def _diagnostic_scores(network: ConversionNetwork, target_value: int) -> dict[str, int]:
    base = _network_lower_bound(network, target_value)
    scores: dict[str, int] = {}
    for edge in network.edges:
        perturbed: list[ServiceEdgeProfile] = []
        for item in network.edges:
            if item.edge_id == edge.edge_id:
                data = item.model_dump()
                data["capacity"] = item.capacity + 1
                perturbed.append(ServiceEdgeProfile(**data))
            else:
                perturbed.append(item)
        data = network.model_dump()
        data["edges"] = [edge.model_dump() for edge in perturbed]
        scores[edge.edge_id] = (
            _network_lower_bound(ConversionNetwork(**data), target_value) - base
        )
    return scores


def _network_lower_bound(network: ConversionNetwork, target_value: int) -> int:
    if not network.edges:
        return 0
    active_nodes = {
        node for edge in network.edges for node in (edge.from_node, edge.to_node)
    }
    source_nodes = set(network.source_nodes) or {
        node
        for node in active_nodes
        if all(edge.to_node != node for edge in network.edges)
        and any(edge.from_node == node for edge in network.edges)
    }
    sink_nodes = set(network.sink_nodes) or {
        node
        for node in active_nodes
        if all(edge.from_node != node for edge in network.edges)
        and any(edge.to_node == node for edge in network.edges)
    }
    if not source_nodes or not sink_nodes:
        return 0
    capacities: dict[tuple[str, str], int] = {}
    for edge in network.edges:
        if edge.from_node not in network.nodes or edge.to_node not in network.nodes:
            continue
        key = (edge.from_node, edge.to_node)
        capacities[key] = capacities.get(key, 0) + edge.certified_capacity()
    super_source = "__cwc_source__"
    super_sink = "__cwc_sink__"
    for node in source_nodes:
        capacities[(super_source, node)] = target_value
    for node in sink_nodes:
        capacities[(node, super_sink)] = target_value
    return min(target_value, _max_flow(capacities, super_source, super_sink))


def _max_flow(capacities: dict[tuple[str, str], int], source: str, sink: str) -> int:
    residual = dict(capacities)
    total = 0
    while True:
        parent: dict[str, str | None] = {source: None}
        queue = [source]
        for node in queue:
            for (left, right), capacity in residual.items():
                if left == node and capacity > 0 and right not in parent:
                    parent[right] = left
                    queue.append(right)
                    if right == sink:
                        break
            if sink in parent:
                break
        if sink not in parent:
            return total
        path_capacity = 10**18
        node = sink
        while parent[node] is not None:
            prev = parent[node]
            assert prev is not None
            path_capacity = min(path_capacity, residual[(prev, node)])
            node = prev
        node = sink
        while parent[node] is not None:
            prev = parent[node]
            assert prev is not None
            residual[(prev, node)] -= path_capacity
            residual[(node, prev)] = residual.get((node, prev), 0) + path_capacity
            node = prev
        total += int(path_capacity)


def create_analyzer() -> DeterministicAnalyzer:
    return DeterministicAnalyzer()


def create_optimizer() -> DeterministicOptimizer:
    return DeterministicOptimizer()
