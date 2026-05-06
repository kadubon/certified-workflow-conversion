"""High-level conversion kernel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from certified_workflow_conversion.adapters.deterministic_analyzer import (
    DeterministicAnalyzer,
    DeterministicOptimizer,
)
from certified_workflow_conversion.adapters.oawm_bridge import OAWMSQLiteBridge
from certified_workflow_conversion.adapters.sqlite_store import SQLiteStore
from certified_workflow_conversion.core.errors import FailClosedError, NotFoundError
from certified_workflow_conversion.core.models import (
    AnalysisMode,
    BottleneckReport,
    ClaimRequirement,
    CompiledClaim,
    ConversionNetwork,
    EvidenceStatus,
    InvestmentBudget,
    InvestmentCandidate,
    StoredEvidence,
    TypedEvidenceObject,
)
from certified_workflow_conversion.ports.analyzer import Analyzer, Optimizer
from certified_workflow_conversion.ports.bridge import OAWMBridge
from certified_workflow_conversion.ports.plugins import load_entry_point
from certified_workflow_conversion.ports.storage import StorageBackend


class ConversionKernel:
    """Storage-neutral orchestration facade."""

    def __init__(
        self,
        *,
        storage: StorageBackend,
        analyzer: Analyzer,
        optimizer: Optimizer,
        oawm_bridge: OAWMBridge,
    ) -> None:
        self.storage = storage
        self.analyzer = analyzer
        self.optimizer = optimizer
        self.oawm_bridge = oawm_bridge

    @classmethod
    def open(
        cls,
        path: str | Path,
        plugins: dict[str, Any] | None = None,
    ) -> ConversionKernel:
        plugin_map = plugins or {}
        state_path = Path(path)
        db_path = state_path if state_path.suffix == ".sqlite" else state_path / "cwc.sqlite"

        storage = plugin_map.get("storage")
        if storage is None:
            storage = SQLiteStore(db_path)
        elif isinstance(storage, str):
            storage = _instantiate_plugin("cwc.storage_backends", storage, db_path)
        storage.initialize()

        analyzer = plugin_map.get("analyzer")
        if analyzer is None:
            analyzer = DeterministicAnalyzer()
        elif isinstance(analyzer, str):
            analyzer = _instantiate_plugin("cwc.analyzers", analyzer)

        optimizer = plugin_map.get("optimizer")
        if optimizer is None:
            optimizer = DeterministicOptimizer()
        elif isinstance(optimizer, str):
            optimizer = _instantiate_plugin("cwc.optimizers", optimizer)

        oawm_bridge = plugin_map.get("oawm_bridge")
        if oawm_bridge is None:
            oawm_bridge = OAWMSQLiteBridge()
        elif isinstance(oawm_bridge, str):
            oawm_bridge = _instantiate_plugin("cwc.oawm_bridges", oawm_bridge)

        return cls(
            storage=storage,
            analyzer=analyzer,
            optimizer=optimizer,
            oawm_bridge=oawm_bridge,
        )

    def add_evidence(self, evidence: TypedEvidenceObject | dict[str, Any]) -> StoredEvidence:
        item = (
            evidence
            if isinstance(evidence, TypedEvidenceObject)
            else _evidence_from_dict(evidence)
        )
        return self.storage.append_evidence(item)

    def import_oawm(
        self,
        oawm_state: str | Path,
        run_id: str | None = None,
    ) -> list[StoredEvidence]:
        imported = self.oawm_bridge.import_state(oawm_state, run_id=run_id)
        return [self.add_evidence(item) for item in imported]

    def register_network(self, network: ConversionNetwork | dict[str, Any]) -> ConversionNetwork:
        item = network if isinstance(network, ConversionNetwork) else _network_from_dict(network)
        return self.storage.upsert_network(item)

    def compile_claim(self, claim_request: ClaimRequirement | dict[str, Any]) -> CompiledClaim:
        request = (
            claim_request
            if isinstance(claim_request, ClaimRequirement)
            else _claim_from_dict(claim_request)
        )
        try:
            network = self.storage.get_network(request.network_id)
        except NotFoundError as exc:
            compiled = CompiledClaim.create(request=request, supported=False, reason=str(exc))
            return self.storage.append_claim(compiled)

        candidate_ids, obligation_reasons = _network_evidence_obligations(network)
        candidate_ids.extend(request.required_evidence_ids)
        for scope in request.required_scopes:
            scoped = self.storage.list_evidence(scope=scope)
            candidate_ids.extend(item.evidence_id for item in scoped)
        unique_ids = sorted(set(candidate_ids))

        reasons: list[str] = list(obligation_reasons)
        evidence: dict[str, StoredEvidence] = {}
        for evidence_id in unique_ids:
            try:
                item = self.storage.get_evidence(evidence_id)
            except NotFoundError:
                reasons.append(f"missing evidence: {evidence_id}")
                continue
            if item.is_expired():
                reasons.append(f"expired evidence: {evidence_id}")
            elif not item.can_support_claim():
                reasons.append(f"inactive evidence: {evidence_id}:{item.status.value}")
            evidence[evidence_id] = item

        _add_dependency_closure(evidence, self.storage, reasons)

        for scope in request.required_scopes:
            if not any(
                item.scope == scope and item.can_support_claim() for item in evidence.values()
            ):
                reasons.append(f"unsupported scope: {scope}")

        for tcb in request.required_tcb:
            if not _tcb_supported(tcb, list(evidence.values())):
                reasons.append(f"missing TCB requirement: {tcb}")

        compiled = CompiledClaim.create(
            request=request,
            supported=not reasons,
            reason="; ".join(reasons),
            evidence_ids=sorted(evidence),
        )
        return self.storage.append_claim(compiled)

    def analyze(
        self,
        network_id: str,
        claim_id: str,
        allocation: dict[str, int] | None = None,
        mode: str | AnalysisMode = AnalysisMode.DIAGNOSTIC,
        profile: str = "light",
    ) -> BottleneckReport:
        network = self.storage.get_network(network_id)
        claim = self.storage.get_claim(claim_id)
        analysis_mode = mode if isinstance(mode, AnalysisMode) else AnalysisMode(mode)
        evidence = [self.storage.get_evidence(evidence_id) for evidence_id in claim.evidence_ids]
        analyzer = self.analyzer
        if profile == "full":
            from certified_workflow_conversion.adapters.full_certification import (
                FullCertificationAnalyzer,
            )

            analyzer = FullCertificationAnalyzer()
        elif profile != "light":
            raise FailClosedError("analysis profile must be 'light' or 'full'")
        report = analyzer.analyze(
            network=network,
            claim=claim,
            evidence=evidence,
            allocation=allocation,
            mode=analysis_mode,
        )
        return self.storage.append_report(report)

    def propose_investments(
        self,
        network_id: str,
        budget: InvestmentBudget | dict[str, Any],
        constraints: dict[str, Any] | None = None,
    ) -> list[InvestmentCandidate]:
        network = self.storage.get_network(network_id)
        actual_budget = (
            budget if isinstance(budget, InvestmentBudget) else _budget_from_dict(budget)
        )
        return self.optimizer.propose(
            network=network,
            budget=actual_budget,
            constraints=constraints,
        )

    def export_report(self, report_id: str, format: str = "json") -> str:
        if format != "json":
            raise FailClosedError("only JSON export is supported in v0.1")
        report = self.storage.get_report(report_id)
        return report.model_dump_json(indent=2)

    def audit(self) -> dict[str, int]:
        return self.storage.audit_counts()


def _network_evidence_obligations(network: ConversionNetwork) -> tuple[list[str], list[str]]:
    ids: list[str] = []
    reasons: list[str] = []
    for edge in network.edges:
        if not edge.evidence_ids:
            reasons.append(f"edge has no capacity/support evidence: {edge.edge_id}")
        ids.extend(edge.evidence_ids)
        for index, reservation in enumerate(edge.reservations):
            if not reservation.evidence_ids:
                reasons.append(
                    f"reservation has no evidence: {edge.edge_id}[{index}]"
                )
            ids.extend(reservation.evidence_ids)
        for gate in edge.hard_gates:
            if not gate.evidence_ids:
                reasons.append(f"hard gate has no evidence: {edge.edge_id}:{gate.name}")
            ids.extend(gate.evidence_ids)
        if edge.queue_state is not None:
            if not edge.queue_state.evidence_ids:
                reasons.append(f"queue state has no evidence: {edge.edge_id}")
            ids.extend(edge.queue_state.evidence_ids)
        for charge in edge.risk_charges:
            if not charge.evidence_ids:
                reasons.append(f"risk charge has no evidence: {edge.edge_id}:{charge.kind}")
            ids.extend(charge.evidence_ids)
    return ids, reasons


def _add_dependency_closure(
    evidence: dict[str, StoredEvidence],
    storage: StorageBackend,
    reasons: list[str],
) -> None:
    seen_missing: set[str] = set()
    changed = True
    while changed:
        changed = False
        known_refs = _known_refs(evidence)
        for item in list(evidence.values()):
            for dependency in item.dependencies:
                if dependency in known_refs:
                    continue
                resolved = _resolve_evidence_ref(storage, dependency)
                if resolved is None:
                    if dependency not in seen_missing:
                        seen_missing.add(dependency)
                        reasons.append(f"missing dependency: {dependency}")
                    continue
                evidence[resolved.evidence_id] = resolved
                if resolved.is_expired():
                    reasons.append(f"expired dependency evidence: {resolved.evidence_id}")
                elif not resolved.can_support_claim():
                    reasons.append(
                        "inactive dependency evidence: "
                        f"{resolved.evidence_id}:{resolved.status.value}"
                    )
                changed = True


def _tcb_supported(tcb: str, evidence: list[StoredEvidence]) -> bool:
    for item in evidence:
        if (
            item.kind == "tcb"
            and item.payload.get("name") == tcb
            and item.payload.get("status") == "ok"
            and item.payload.get("rooted") is True
        ):
            return True
    return False


def _known_refs(evidence: dict[str, StoredEvidence]) -> set[str]:
    refs = set(evidence)
    for item in evidence.values():
        refs.update(item.external_refs)
    return refs


def _resolve_evidence_ref(
    storage: StorageBackend,
    ref: str,
) -> StoredEvidence | None:
    try:
        return storage.get_evidence(ref)
    except NotFoundError:
        pass
    for item in storage.list_evidence():
        if ref in item.external_refs:
            return item
    return None


def _evidence_from_dict(payload: dict[str, Any]) -> TypedEvidenceObject:
    if "evidence_id" in payload:
        return TypedEvidenceObject(**payload)
    return TypedEvidenceObject.create(
        kind=str(payload["kind"]),
        scope=str(payload["scope"]),
        source=str(payload.get("source", "user")),
        payload=dict(payload.get("payload", {})),
        external_refs=[str(item) for item in payload.get("external_refs", [])],
        root_refs=[str(item) for item in payload.get("root_refs", [])],
        dependencies=[str(item) for item in payload.get("dependencies", [])],
        confidence_microunits=int(payload.get("confidence_microunits", 0)),
        status=EvidenceStatus(str(payload.get("status", "active"))),
        tcb_requirements=[str(item) for item in payload.get("tcb_requirements", [])],
    )


def _network_from_dict(payload: dict[str, Any]) -> ConversionNetwork:
    if "network_id" in payload:
        return ConversionNetwork(**payload)
    edges = [item if isinstance(item, dict) else {} for item in payload.get("edges", [])]
    network_edges = []
    from certified_workflow_conversion.core.models import ServiceEdgeProfile

    for edge in edges:
        if "edge_id" in edge:
            network_edges.append(ServiceEdgeProfile(**edge))
        else:
            network_edges.append(
                ServiceEdgeProfile.create(
                    name=str(edge["name"]),
                    from_node=str(edge["from_node"]),
                    to_node=str(edge["to_node"]),
                    capacity=int(edge["capacity"]),
                    cost_per_unit=int(edge.get("cost_per_unit", 1)),
                    delay_steps=int(edge.get("delay_steps", 0)),
                    evidence_ids=[str(item) for item in edge.get("evidence_ids", [])],
                )
            )
    return ConversionNetwork.create(
        name=str(payload["name"]),
        nodes=[str(item) for item in payload["nodes"]],
        edges=network_edges,
        source_nodes=[str(item) for item in payload.get("source_nodes", [])],
        sink_nodes=[str(item) for item in payload.get("sink_nodes", [])],
    )


def _claim_from_dict(payload: dict[str, Any]) -> ClaimRequirement:
    if "claim_id" in payload:
        return ClaimRequirement(**payload)
    return ClaimRequirement.create(
        network_id=str(payload["network_id"]),
        target_value=int(payload["target_value"]),
        required_scopes=[str(item) for item in payload.get("required_scopes", [])],
        required_evidence_ids=[str(item) for item in payload.get("required_evidence_ids", [])],
        required_tcb=[str(item) for item in payload.get("required_tcb", [])],
        certification_split=dict(payload.get("certification_split", {})),
    )


def _budget_from_dict(payload: dict[str, Any]) -> InvestmentBudget:
    if "budget_id" in payload:
        return InvestmentBudget(**payload)
    return InvestmentBudget.create(units=int(payload["units"]))


def _instantiate_plugin(group: str, name: str, *args: Any) -> Any:
    factory = load_entry_point(group, name)
    if callable(factory):
        try:
            return factory(*args)
        except TypeError:
            if args:
                return factory()
            raise
    if args:
        raise FailClosedError(f"plugin {group}:{name} is not callable")
    return factory
