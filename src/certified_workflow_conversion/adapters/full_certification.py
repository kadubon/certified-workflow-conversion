"""Full-profile evidence-contract and certificate validation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from certified_workflow_conversion.adapters.scipy_flow import (
    assert_scipy_available,
    solve_conservative_flow,
)
from certified_workflow_conversion.adapters.statistical_certificates import (
    evaluate_statistical_certificate,
)
from certified_workflow_conversion.adapters.validation_capital import (
    certify_validation_capital,
)
from certified_workflow_conversion.core.certificates import (
    DataProtocol,
    DynamicPathLawCertificate,
    EvidenceContract,
    GoodhartBudget,
    OpenWorldHazardCharge,
    QueueCertificate,
    ReleaseAccountingCertificate,
    StatisticalCertificate,
    ValidationDependencyGraph,
    VerificationWitness,
)
from certified_workflow_conversion.core.errors import FailClosedError
from certified_workflow_conversion.core.models import (
    AnalysisMode,
    BottleneckReport,
    CompiledClaim,
    ConversionNetwork,
    ReportStatus,
    StoredEvidence,
)


@dataclass
class FullCertificationResult:
    ok: bool
    limitations: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    validation_capital: dict[str, Any] = field(default_factory=dict)
    term_bindings: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


class FullCertificationAnalyzer:
    analyzer_name = "full"

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
        assert_scipy_available()
        result = validate_full_certification_inputs(network, claim, evidence)
        evidence_ids = [item.evidence_id for item in evidence]
        hard_gate_failures = [
            f"{edge.edge_id}:{gate.name}:{gate.reason}"
            for edge in network.edges
            for gate in edge.blocked_gates()
        ]
        total_risk_charge = sum(
            charge.amount for edge in network.edges for charge in edge.risk_charges
        )
        if hard_gate_failures:
            result.ok = False
            result.limitations.append("hard gates are non-compensable")
        if mode == AnalysisMode.CERTIFIED_LOWER_BOUND and not result.ok:
            return _blocked_report(
                network=network,
                claim=claim,
                mode=mode,
                evidence_ids=evidence_ids,
                limitations=result.limitations,
                summary=result.summary,
                validation_capital=result.validation_capital,
                hard_gate_failures=hard_gate_failures,
                total_risk_charge=total_risk_charge,
            )
        if not result.ok:
            return _blocked_report(
                network=network,
                claim=claim,
                mode=mode,
                evidence_ids=evidence_ids,
                limitations=result.limitations,
                summary=result.summary,
                validation_capital=result.validation_capital,
                hard_gate_failures=hard_gate_failures,
                total_risk_charge=total_risk_charge,
            )
        try:
            flow = solve_conservative_flow(network, claim.request.target_value)
        except FailClosedError as exc:
            return _blocked_report(
                network=network,
                claim=claim,
                mode=mode,
                evidence_ids=evidence_ids,
                limitations=[str(exc)],
                summary=result.summary,
                validation_capital=result.validation_capital,
                hard_gate_failures=hard_gate_failures,
                total_risk_charge=total_risk_charge,
            )
        final_lower_bound, certificate_summary = _compose_full_lower_bound(
            flow_lower_bound=float(flow["lower_bound"]),
            summary=result.summary,
        )
        price_intervals = flow["dual_price_intervals"]
        bottlenecks = [
            edge_id
            for edge_id, interval in price_intervals.items()
            if float(interval["upper"]) > 0.0
        ]
        return BottleneckReport.create(
            network_id=network.network_id,
            claim_id=claim.claim_id,
            mode=mode,
            status=ReportStatus.OK,
            lower_bound=final_lower_bound,
            bottleneck_edges=sorted(bottlenecks),
            diagnostic_scores={
                edge_id: int(float(interval["estimate"]))
                for edge_id, interval in price_intervals.items()
            },
            total_risk_charge=total_risk_charge,
            hard_gate_failures=hard_gate_failures,
            evidence_ids=evidence_ids,
            limitations=[
                "full profile certifies evidence-bound procedural lower bounds, not factual truth",
                "dual prices remain diagnostic unless a post-investment certificate is supplied",
            ],
            certificate_summary=certificate_summary,
            dual_price_intervals=price_intervals,
            validation_capital=result.validation_capital,
            full_profile_status="full_checked",
        )


def validate_full_certification_inputs(
    network: ConversionNetwork,
    claim: CompiledClaim,
    evidence: list[StoredEvidence],
) -> FullCertificationResult:
    limitations: list[str] = []
    summary: dict[str, Any] = {}
    validation_capital: dict[str, Any] = {}
    if not claim.supported:
        limitations.append(f"claim unsupported: {claim.reason}")
    if not network.source_nodes or not network.sink_nodes:
        limitations.append("full profile requires explicit source_nodes and sink_nodes")

    evidence_refs = _evidence_refs(evidence)
    inactive = [item.evidence_id for item in evidence if not item.can_support_claim()]
    if inactive:
        limitations.append(f"inactive evidence cannot support full profile: {inactive}")

    required_kinds = {
        "evidence_contract",
        "verification_witness",
        "support",
        "uncertainty_contract",
        "statistical_certificate",
        "path_law_certificate",
        "queue_certificate",
        "release_accounting",
        "goodhart_account",
        "open_world_account",
        "confidence_budget",
        "root",
        "validation_dependency_graph",
    }
    observed = {item.kind for item in evidence if item.can_support_claim()}
    missing = sorted(required_kinds - observed)
    if missing:
        limitations.append(f"full profile missing evidence kinds: {missing}")

    contracts, contract_failures = _parse_contracts(evidence)
    witnesses, witness_failures = _parse_witnesses(evidence)
    limitations.extend(contract_failures)
    limitations.extend(witness_failures)
    split_failure = _validate_data_protocol(claim, evidence_refs, contracts, witnesses)
    if split_failure:
        limitations.append(split_failure)
    _validate_tcb_requirements(evidence, contracts, witnesses, limitations)
    term_bindings = _validate_contract_witness_binding(
        contracts,
        witnesses,
        evidence_refs,
        limitations,
    )
    _validate_uncertainty_contract(evidence, limitations, summary)
    _validate_edge_capacity_bindings(network, term_bindings, limitations, summary)
    _validate_queue(evidence, limitations, summary)
    _validate_release_accounting(evidence, limitations, summary)
    _validate_goodhart_and_open_world(evidence, limitations, summary)
    _validate_statistical_and_path(evidence, limitations, summary)
    _validate_report_term_bindings(term_bindings, summary, limitations)
    _validate_confidence_budget(evidence, contracts, limitations, summary)
    _validate_validation_capital(evidence, limitations, validation_capital)

    summary["contracts"] = len(contracts)
    summary["witnesses"] = len(witnesses)
    summary["bound_report_terms"] = sorted(term_bindings)
    summary["mode"] = "full"
    return FullCertificationResult(
        ok=not limitations,
        limitations=limitations,
        summary=summary,
        validation_capital=validation_capital,
        term_bindings=term_bindings,
    )


def _blocked_report(
    *,
    network: ConversionNetwork,
    claim: CompiledClaim,
    mode: AnalysisMode,
    evidence_ids: list[str],
    limitations: list[str],
    summary: dict[str, Any],
    validation_capital: dict[str, Any],
    hard_gate_failures: list[str],
    total_risk_charge: int,
) -> BottleneckReport:
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
        limitations=limitations,
        certificate_summary=summary,
        validation_capital=validation_capital,
        full_profile_status="blocked",
    )


def _evidence_refs(evidence: list[StoredEvidence]) -> set[str]:
    refs = {item.evidence_id for item in evidence}
    for item in evidence:
        refs.update(item.external_refs)
    return refs


def _compose_full_lower_bound(
    *,
    flow_lower_bound: float,
    summary: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    report_summary = dict(summary)
    certificate_bounds = [
        float(item["lower_bound"])
        for item in summary.get("statistical_certificates", [])
        if "lower_bound" in item
    ]
    term_bounds = summary.get("report_term_bounds", {})
    for term in ("statistical_lower", "path_law_lower"):
        if term in term_bounds:
            certificate_bounds.append(float(term_bounds[term]))
    if not certificate_bounds:
        raise FailClosedError("full profile has no report-facing lower-bound term")

    deductions = {
        "queue_boundary_correction": float(summary.get("queue_boundary_correction", 0)),
        "direct_cost_rate": float(summary.get("direct_cost_rate", 0)),
        "goodhart_total": float(summary.get("goodhart_total", 0)),
        "open_world_charge": float(summary.get("open_world_charge", 0)),
    }
    bound_cap = min([flow_lower_bound, *certificate_bounds])
    if not math.isfinite(bound_cap):
        raise FailClosedError("full profile lower bound is non-finite")
    raw_final = bound_cap - sum(deductions.values())
    final_lower_bound = max(0, int(math.floor(raw_final)))
    report_summary["flow_lower_bound"] = flow_lower_bound
    report_summary["certificate_lower_bound_cap"] = bound_cap
    report_summary["deductions"] = deductions
    report_summary["final_lower_bound_formula"] = (
        "floor(max(0, min(flow, statistical/path-law/report terms) "
        "- queue - direct_cost - goodhart - open_world))"
    )
    report_summary["final_lower_bound"] = final_lower_bound
    return final_lower_bound, report_summary


def _validate_data_protocol(
    claim: CompiledClaim,
    evidence_refs: set[str],
    contracts: list[EvidenceContract],
    witnesses: list[VerificationWitness],
) -> str:
    split = claim.request.certification_split
    if not split or any(not split.get(key) for key in ("ledger", "selection", "certification")):
        return "full certified mode requires non-empty ledger/selection/certification split"
    protocol = DataProtocol(
        build=split["ledger"],
        select=split["selection"],
        cert=split["certification"],
        composition_rule=None,
    )
    split_refs = split["ledger"] + split["selection"] + split["certification"]
    missing = sorted(ref for ref in split_refs if ref not in evidence_refs)
    if missing:
        return f"certification split references unavailable evidence: {missing}"
    if protocol.overlapping_refs() and not _has_overlap_composition_witness(
        contracts,
        witnesses,
    ):
        return "certification split overlaps without an explicit uniform/time-uniform witness"
    return ""


def _has_overlap_composition_witness(
    contracts: list[EvidenceContract],
    witnesses: list[VerificationWitness],
) -> bool:
    allowed = {"uniform", "time_uniform", "eprocess", "simultaneous"}
    if not contracts:
        return False
    accepted_by_contract: dict[str, list[VerificationWitness]] = {}
    for witness in witnesses:
        if witness.accepted():
            accepted_by_contract.setdefault(witness.contract_id, []).append(witness)
    for contract in contracts:
        if contract.compose not in allowed:
            return False
        if not any(
            (
                witness.accepted_output.get("composition_rule")
                or witness.residual.get("composition_rule")
            )
            in allowed
            for witness in accepted_by_contract.get(contract.contract_id, [])
        ):
            return False
    return True


def _parse_contracts(
    evidence: list[StoredEvidence],
) -> tuple[list[EvidenceContract], list[str]]:
    contracts: list[EvidenceContract] = []
    failures: list[str] = []
    for item in evidence:
        if item.kind != "evidence_contract":
            continue
        payload = item.payload.get("contract", item.payload)
        try:
            contract = EvidenceContract.model_validate(payload)
        except ValidationError as exc:
            failures.append(
                f"invalid evidence contract {item.evidence_id}: "
                f"{exc.errors()[0]['msg']}"
            )
            continue
        if contract.status != "active":
            failures.append(f"inactive evidence contract: {contract.contract_id}:{contract.status}")
        contracts.append(contract)
    return contracts, failures


def _parse_witnesses(
    evidence: list[StoredEvidence],
) -> tuple[list[VerificationWitness], list[str]]:
    witnesses: list[VerificationWitness] = []
    failures: list[str] = []
    for item in evidence:
        if item.kind != "verification_witness":
            continue
        payload = item.payload.get("witness", item.payload)
        try:
            witness = VerificationWitness.model_validate(payload)
        except ValidationError as exc:
            failures.append(
                f"invalid verification witness {item.evidence_id}: "
                f"{exc.errors()[0]['msg']}"
            )
            continue
        if not witness.accepted():
            failures.append(f"rejected verification witness: {witness.witness_id}")
        witnesses.append(witness)
    return witnesses, failures


def _validate_contract_witness_binding(
    contracts: list[EvidenceContract],
    witnesses: list[VerificationWitness],
    evidence_refs: set[str],
    limitations: list[str],
) -> dict[str, list[dict[str, Any]]]:
    bindings: dict[str, list[dict[str, Any]]] = {}
    accepted_by_contract: dict[str, list[VerificationWitness]] = {}
    for witness in witnesses:
        if witness.accepted():
            accepted_by_contract.setdefault(witness.contract_id, []).append(witness)
    for contract in contracts:
        if contract.contract_id not in accepted_by_contract:
            limitations.append(f"contract has no accepted witness: {contract.contract_id}")
            continue
        missing_deps = sorted(ref for ref in contract.dependencies if ref not in evidence_refs)
        if missing_deps:
            limitations.append(
                f"contract dependency refs are unavailable: {contract.contract_id}:{missing_deps}"
            )
        contract_terms = _split_exposes(contract.exposes)
        if not contract_terms:
            limitations.append(f"contract exposes no report terms: {contract.contract_id}")
            continue
        if len(contract_terms) != 1:
            limitations.append(
                "contract must expose exactly one claim-facing report term: "
                f"{contract.contract_id}:{contract_terms}"
            )
            continue
        contract_term = contract_terms[0]
        for witness in accepted_by_contract[contract.contract_id]:
            witness_terms = _split_exposes(witness.exposes)
            if witness_terms != [contract_term]:
                limitations.append(
                    "witness exposes do not match contract: "
                    f"{witness.witness_id}:{contract.contract_id}"
                )
                continue
            if not witness.input_digest:
                limitations.append(f"witness lacks input digest: {witness.witness_id}")
            expected_input = contract.assumptions.get("input_digest")
            if expected_input is not None and witness.input_digest != expected_input:
                limitations.append(
                    f"witness input digest mismatch: {witness.witness_id}"
                )
            if not witness.checker_digest:
                limitations.append(f"witness lacks checker digest: {witness.witness_id}")
            expected_checker = contract.assumptions.get("checker_digest")
            if expected_checker is not None and witness.checker_digest != expected_checker:
                limitations.append(
                    f"witness checker digest mismatch: {witness.witness_id}"
                )
            if contract.scope and witness.scope != contract.scope:
                limitations.append(f"witness scope mismatch: {witness.witness_id}")
            if not set(contract.tcb).issubset(set(witness.tcb)):
                limitations.append(
                    f"witness TCB does not cover contract TCB: {witness.witness_id}"
                )
            if not witness.accepted_output:
                limitations.append(f"witness lacks accepted output: {witness.witness_id}")
                continue
            bindings.setdefault(contract_term, []).append(
                {
                    "term": contract_term,
                    "contract_id": contract.contract_id,
                    "dependencies": contract.dependencies,
                    "witness_id": witness.witness_id,
                    "accepted_output": witness.accepted_output,
                }
            )
    return bindings


def _validate_tcb_requirements(
    evidence: list[StoredEvidence],
    contracts: list[EvidenceContract],
    witnesses: list[VerificationWitness],
    limitations: list[str],
) -> None:
    rooted_tcb = {
        str(item.payload.get("name"))
        for item in evidence
        if item.kind == "tcb"
        and item.can_support_claim()
        and item.payload.get("name")
        and item.payload.get("status") == "ok"
        and item.payload.get("rooted") is True
    }
    for item in evidence:
        for tcb in item.tcb_requirements:
            if tcb not in rooted_tcb:
                limitations.append(
                    f"evidence has unmet rooted TCB requirement: {item.evidence_id}:{tcb}"
                )
    for contract in contracts:
        for tcb in contract.tcb:
            if tcb not in rooted_tcb:
                limitations.append(
                    f"contract has unmet rooted TCB requirement: {contract.contract_id}:{tcb}"
                )
    for witness in witnesses:
        for tcb in witness.tcb:
            if tcb not in rooted_tcb:
                limitations.append(
                    f"witness has unmet rooted TCB requirement: {witness.witness_id}:{tcb}"
                )


def _validate_edge_capacity_bindings(
    network: ConversionNetwork,
    term_bindings: dict[str, list[dict[str, Any]]],
    limitations: list[str],
    summary: dict[str, Any],
) -> None:
    edge_terms: dict[str, dict[str, Any]] = {}
    name_counts: dict[str, int] = {}
    for edge in network.edges:
        name_counts[edge.name] = name_counts.get(edge.name, 0) + 1
    for edge in network.edges:
        id_term = f"edge.capacity:{edge.edge_id}"
        name_term = f"edge.capacity:{edge.name}"
        id_matches = list(term_bindings.get(id_term, []))
        name_matches = list(term_bindings.get(name_term, []))
        if name_matches and name_counts.get(edge.name, 0) > 1 and not id_matches:
            limitations.append(
                "edge capacity binding by name is ambiguous; use edge_id term: "
                f"{edge.name}"
            )
            continue
        matches = id_matches + name_matches
        if not matches:
            limitations.append(
                "edge capacity lacks accepted contract/witness binding: "
                f"{edge.edge_id}"
            )
            continue
        if not any(
            set(edge.evidence_ids).issubset(set(binding.get("dependencies", [])))
            for binding in matches
        ):
            limitations.append(
                "edge capacity contract does not depend on edge support evidence: "
                f"{edge.edge_id}"
            )
            continue
        capacity_values: list[float] = []
        for binding in matches:
            value = _numeric_output(
                binding["accepted_output"],
                str(binding["term"]),
                aliases=("capacity", "edge_capacity", "value", "lower_bound"),
            )
            if value is not None:
                capacity_values.append(value)
        accepted_capacity = max(capacity_values) if capacity_values else None
        if accepted_capacity is None:
            limitations.append(
                f"edge capacity binding lacks numeric capacity term: {edge.edge_id}"
            )
            continue
        if accepted_capacity < edge.capacity:
            limitations.append(
                "edge capacity binding is below declared capacity: "
                f"{edge.edge_id}:{accepted_capacity}<{edge.capacity}"
            )
        edge_terms[edge.edge_id] = {
            "edge_name": edge.name,
            "declared_capacity": edge.capacity,
            "accepted_capacity": accepted_capacity,
            "contracts": [binding["contract_id"] for binding in matches],
            "witnesses": [binding["witness_id"] for binding in matches],
        }
    summary["edge_capacity_terms"] = edge_terms


def _validate_uncertainty_contract(
    evidence: list[StoredEvidence],
    limitations: list[str],
    summary: dict[str, Any],
) -> None:
    for item in evidence:
        if item.kind != "uncertainty_contract":
            continue
        payload = item.payload
        if not (
            payload.get("nonempty") is True
            or payload.get("constructive_law")
            or payload.get("feasibility_proof")
            or payload.get("solver_certificate")
        ):
            limitations.append(
                "uncertainty contract must include nonempty proof, constructive law, "
                "feasibility proof, or solver certificate"
            )
        summary["uncertainty_contract"] = {
            "evidence_id": item.evidence_id,
            "nonempty": bool(payload.get("nonempty")),
        }
        return
    limitations.append("missing nonempty uncertainty contract")


def _validate_confidence_budget(
    evidence: list[StoredEvidence],
    contracts: list[EvidenceContract],
    limitations: list[str],
    summary: dict[str, Any],
) -> None:
    limits = [
        int(item.payload.get("max_microunits", -1))
        for item in evidence
        if item.kind == "confidence_budget"
    ]
    if not limits:
        limitations.append("missing confidence budget limit")
        return
    max_budget = min(limits)
    used = sum(item.confidence_microunits for item in evidence)
    used += sum(contract.budget_microunits for contract in contracts)
    used += int(summary.get("certificate_delta_microunits", 0))
    summary["confidence_microunits_used"] = used
    summary["confidence_microunits_max"] = max_budget
    if used > max_budget:
        limitations.append("confidence budget exceeded")


def _validate_queue(
    evidence: list[StoredEvidence],
    limitations: list[str],
    summary: dict[str, Any],
) -> None:
    for item in evidence:
        if item.kind != "queue_certificate":
            continue
        try:
            cert = QueueCertificate.model_validate(item.payload)
        except ValidationError as exc:
            limitations.append(
                f"invalid queue certificate {item.evidence_id}: "
                f"{exc.errors()[0]['msg']}"
            )
            return
        summary["queue_boundary_correction"] = cert.boundary_correction
        _term_refs(summary).setdefault("queue_boundary", []).append(item.evidence_id)
        if not cert.accepted():
            limitations.append(
                "queue certificate failed bounded-increment/no-phantom-release checks"
            )
        if cert.boundary_correction > 0 and not cert.boundary_derivation:
            limitations.append("positive queue boundary correction lacks derivation evidence")
        return
    limitations.append("missing queue certificate")


def _validate_release_accounting(
    evidence: list[StoredEvidence],
    limitations: list[str],
    summary: dict[str, Any],
) -> None:
    for item in evidence:
        if item.kind != "release_accounting":
            continue
        try:
            cert = ReleaseAccountingCertificate.model_validate(item.payload)
        except ValidationError as exc:
            limitations.append(
                f"invalid release accounting {item.evidence_id}: "
                f"{exc.errors()[0]['msg']}"
            )
            return
        summary["direct_cost_rate"] = cert.direct_cost_rate
        _term_refs(summary).setdefault("release_accounting", []).append(item.evidence_id)
        if not cert.disjoint_ledgers:
            limitations.append("release accounting ledgers are not disjoint")
        return
    limitations.append("missing release accounting certificate")


def _validate_goodhart_and_open_world(
    evidence: list[StoredEvidence],
    limitations: list[str],
    summary: dict[str, Any],
) -> None:
    for item in evidence:
        if item.kind == "goodhart_account":
            try:
                budget = GoodhartBudget.model_validate(item.payload)
            except ValidationError as exc:
                limitations.append(
                    f"invalid Goodhart budget {item.evidence_id}: "
                    f"{exc.errors()[0]['msg']}"
                )
                continue
            summary["goodhart_total"] = budget.total()
            _term_refs(summary).setdefault("goodhart_charge", []).append(item.evidence_id)
            if budget.total() > 0 and not budget.construction_evidence:
                limitations.append("positive Goodhart charge lacks construction evidence")
        if item.kind == "open_world_account":
            try:
                charge = OpenWorldHazardCharge.model_validate(item.payload)
            except ValidationError as exc:
                limitations.append(
                    f"invalid open-world charge {item.evidence_id}: "
                    f"{exc.errors()[0]['msg']}"
                )
                continue
            if not charge.construction_evidence:
                limitations.append("open-world charge lacks construction evidence")
            summary["open_world_charge"] = charge.charge
            _term_refs(summary).setdefault("open_world_charge", []).append(item.evidence_id)


def _validate_report_term_bindings(
    term_bindings: dict[str, list[dict[str, Any]]],
    summary: dict[str, Any],
    limitations: list[str],
) -> None:
    certificate_results = summary.get("statistical_certificates", [])
    computed_statistical = [
        float(item["lower_bound"])
        for item in certificate_results
        if item.get("kind") != "path_law" and "lower_bound" in item
    ]
    computed_path = [
        float(item["lower_bound"])
        for item in certificate_results
        if item.get("kind") == "path_law" and "lower_bound" in item
    ]
    expected: dict[str, tuple[float, str]] = {}
    if computed_statistical:
        expected["statistical_lower"] = (min(computed_statistical), "lower")
    if computed_path:
        expected["path_law_lower"] = (min(computed_path), "lower")
    expected["queue_boundary"] = (
        float(summary.get("queue_boundary_correction", 0)),
        "charge",
    )
    expected["release_accounting"] = (float(summary.get("direct_cost_rate", 0)), "charge")
    expected["goodhart_charge"] = (float(summary.get("goodhart_total", 0)), "charge")
    expected["open_world_charge"] = (float(summary.get("open_world_charge", 0)), "charge")

    report_terms: dict[str, float] = {}
    for term, (computed, direction) in expected.items():
        bindings = term_bindings.get(term, [])
        if not bindings:
            limitations.append(f"missing accepted report-term binding: {term}")
            continue
        required_refs = set(summary.get("term_evidence_refs", {}).get(term, []))
        if required_refs and not any(
            required_refs.issubset(set(binding.get("dependencies", [])))
            for binding in bindings
        ):
            limitations.append(
                f"report-term contract lacks dependency on source evidence: {term}"
            )
            continue
        values: list[float] = []
        for binding in bindings:
            value = _numeric_output(
                binding["accepted_output"],
                term,
                aliases=_term_output_aliases(term),
            )
            if value is not None:
                values.append(value)
        if not values:
            limitations.append(f"report-term binding lacks numeric output: {term}")
            continue
        if direction == "lower":
            accepted_value = max(values)
            if accepted_value > computed:
                limitations.append(
                    "report-term lower bound exceeds computed certificate: "
                    f"{term}:{accepted_value}>{computed}"
                )
            report_terms[term] = accepted_value
        else:
            accepted_value = max(values)
            if accepted_value < computed:
                limitations.append(
                    "report-term charge is below computed certificate charge: "
                    f"{term}:{accepted_value}<{computed}"
                )
            report_terms[term] = accepted_value
            if term == "queue_boundary":
                summary["queue_boundary_correction"] = accepted_value
            elif term == "release_accounting":
                summary["direct_cost_rate"] = accepted_value
            elif term == "goodhart_charge":
                summary["goodhart_total"] = accepted_value
            elif term == "open_world_charge":
                summary["open_world_charge"] = accepted_value
    summary["report_term_bounds"] = report_terms


def _validate_statistical_and_path(
    evidence: list[StoredEvidence],
    limitations: list[str],
    summary: dict[str, Any],
) -> None:
    stat_results: list[dict[str, Any]] = []
    delta_microunits = 0
    for item in evidence:
        if item.kind == "statistical_certificate":
            try:
                cert = StatisticalCertificate.model_validate(item.payload)
                stat_results.append(evaluate_statistical_certificate(cert))
                _term_refs(summary).setdefault("statistical_lower", []).append(
                    item.evidence_id
                )
                delta = cert.params.get("delta")
                if isinstance(delta, int | float) and delta >= 0:
                    delta_microunits += int(float(delta) * 1_000_000)
            except (ValidationError, FailClosedError, KeyError) as exc:
                limitations.append(f"invalid statistical certificate {item.evidence_id}: {exc}")
        if item.kind == "path_law_certificate":
            try:
                path_cert = DynamicPathLawCertificate.model_validate(item.payload)
                stat_results.append(
                    {"kind": "path_law", "lower_bound": path_cert.lower_bound()}
                )
                _term_refs(summary).setdefault("path_law_lower", []).append(
                    item.evidence_id
                )
                delta_microunits += path_cert.delta_microunits
            except ValidationError as exc:
                limitations.append(
                    f"invalid path-law certificate {item.evidence_id}: "
                    f"{exc.errors()[0]['msg']}"
                )
    if not stat_results:
        limitations.append("missing statistical/path-law certificate")
    else:
        summary["statistical_certificates"] = stat_results
    summary["certificate_delta_microunits"] = delta_microunits


def _validate_validation_capital(
    evidence: list[StoredEvidence],
    limitations: list[str],
    validation_capital: dict[str, Any],
) -> None:
    for item in evidence:
        if item.kind != "validation_dependency_graph":
            continue
        try:
            graph = ValidationDependencyGraph.model_validate(item.payload)
        except ValidationError as exc:
            limitations.append(
                f"invalid validation dependency graph {item.evidence_id}: "
                f"{exc.errors()[0]['msg']}"
            )
            return
        certificate = certify_validation_capital(graph)
        validation_capital.update(certificate.model_dump(mode="json"))
        if certificate.blocked_nodes:
            limitations.append(f"rootless validation nodes: {certificate.blocked_nodes}")
        if certificate.supported_demand < sum(graph.demands.values()):
            limitations.append("validation root-cut capacity is below declared demand")
        return
    limitations.append("missing validation dependency graph")


def _split_exposes(exposes: str) -> list[str]:
    return [term.strip() for term in exposes.split(",") if term.strip()]


def _numeric_output(
    output: dict[str, Any],
    key: str,
    *,
    aliases: tuple[str, ...] = (),
) -> float | None:
    for candidate in (key, *aliases):
        value = output.get(candidate)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float) and math.isfinite(float(value)):
            return float(value)
    return None


def _term_output_aliases(term: str) -> tuple[str, ...]:
    if term in {"statistical_lower", "path_law_lower"}:
        return ("lower_bound", "value")
    if term == "queue_boundary":
        return ("queue_boundary_correction", "boundary_correction", "charge", "value")
    if term == "release_accounting":
        return ("direct_cost_rate", "charge", "value")
    if term in {"goodhart_charge", "open_world_charge"}:
        return ("charge", "value")
    return ("value",)


def _term_refs(summary: dict[str, Any]) -> dict[str, list[str]]:
    refs = summary.setdefault("term_evidence_refs", {})
    if not isinstance(refs, dict):
        refs = {}
        summary["term_evidence_refs"] = refs
    return refs
