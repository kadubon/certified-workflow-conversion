"""Storage-neutral domain models."""

from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from certified_workflow_conversion.core.canonical import digest_json

SCHEMA_VERSION = "0.1"


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ContinuityCoordinate(StrEnum):
    SERVICE = "service"
    RECOVERY = "recovery"
    AUTHORITY = "authority"
    IDENTITY = "identity"
    MUTATION = "mutation"
    GOAL = "goal"
    MEMORY = "memory"
    FEDERATION = "federation"
    LIABILITY = "liability"
    TCB = "tcb"
    CONSISTENCY = "consistency"


class AnalysisMode(StrEnum):
    DIAGNOSTIC = "diagnostic"
    CERTIFIED_LOWER_BOUND = "certified_lower_bound"


class ReportStatus(StrEnum):
    OK = "ok"
    BLOCKED = "blocked"


class EvidenceStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"
    POLICY_RESERVE = "policy_reserve"


class StorageCapabilities(StrictModel):
    transactions: bool = False
    full_text_search: bool = False
    json_query: bool = False
    advisory_locks: bool = False
    blob_store: bool = False
    migrations: bool = False


class TypedEvidenceObject(StrictModel):
    schema_version: str = SCHEMA_VERSION
    evidence_id: str
    kind: str
    scope: str
    source: str
    payload: dict[str, Any]
    payload_digest: str
    status: EvidenceStatus = EvidenceStatus.ACTIVE
    root_refs: list[str] = Field(default_factory=list)
    external_refs: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    expiry: dt.datetime | None = None
    confidence_microunits: int = 0
    tcb_requirements: list[str] = Field(default_factory=list)
    continuity_coordinates: list[ContinuityCoordinate] = Field(default_factory=list)
    created_at: dt.datetime = Field(default_factory=now_utc)

    @classmethod
    def create(
        cls,
        *,
        kind: str,
        scope: str,
        source: str,
        payload: dict[str, Any],
        dependencies: list[str] | None = None,
        external_refs: list[str] | None = None,
        root_refs: list[str] | None = None,
        expiry: dt.datetime | None = None,
        confidence_microunits: int = 0,
        status: EvidenceStatus = EvidenceStatus.ACTIVE,
        tcb_requirements: list[str] | None = None,
        continuity_coordinates: list[ContinuityCoordinate] | None = None,
    ) -> TypedEvidenceObject:
        payload_digest = digest_json(payload)
        seed = {
            "kind": kind,
            "scope": scope,
            "source": source,
            "payload_digest": payload_digest,
            "external_refs": external_refs or [],
            "root_refs": root_refs or [],
            "dependencies": dependencies or [],
            "expiry": expiry.isoformat() if expiry else None,
            "status": status.value,
            "tcb_requirements": tcb_requirements or [],
            "continuity_coordinates": [
                coordinate.value for coordinate in continuity_coordinates or []
            ],
        }
        return cls(
            evidence_id=f"ev_{digest_json(seed)[:32]}",
            kind=kind,
            scope=scope,
            source=source,
            payload=payload,
            payload_digest=payload_digest,
            status=status,
            root_refs=root_refs or [],
            external_refs=external_refs or [],
            dependencies=dependencies or [],
            expiry=expiry,
            confidence_microunits=confidence_microunits,
            tcb_requirements=tcb_requirements or [],
            continuity_coordinates=continuity_coordinates or [],
        )

    @model_validator(mode="after")
    def validate_digest(self) -> TypedEvidenceObject:
        expected = digest_json(self.payload)
        if self.payload_digest != expected:
            raise ValueError("payload_digest does not match payload")
        return self

    def is_expired(self, at: dt.datetime | None = None) -> bool:
        return self.status == EvidenceStatus.EXPIRED or (
            self.expiry is not None and self.expiry <= (at or now_utc())
        )

    def can_support_claim(self, at: dt.datetime | None = None) -> bool:
        return self.status == EvidenceStatus.ACTIVE and not self.is_expired(at)


class StoredEvidence(TypedEvidenceObject):
    obs_seq: int
    obs_time: dt.datetime


class CapacityReservation(StrictModel):
    resource: str
    amount: int = Field(ge=0)
    evidence_ids: list[str] = Field(default_factory=list)


class QueueState(StrictModel):
    edge_id: str
    backlog: int = Field(ge=0)
    arrival_rate: int = Field(ge=0)
    service_rate: int = Field(ge=0)
    evidence_ids: list[str] = Field(default_factory=list)


class RiskCharge(StrictModel):
    charge_id: str
    kind: Literal["goodhart", "open_world", "continuity", "operational"]
    amount: int = Field(ge=0)
    reason: str = ""
    evidence_ids: list[str] = Field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        kind: Literal["goodhart", "open_world", "continuity", "operational"],
        amount: int,
        reason: str = "",
        evidence_ids: list[str] | None = None,
    ) -> RiskCharge:
        seed = {
            "kind": kind,
            "amount": amount,
            "reason": reason,
            "evidence_ids": evidence_ids or [],
        }
        return cls(
            charge_id=f"chg_{digest_json(seed)[:32]}",
            kind=kind,
            amount=amount,
            reason=reason,
            evidence_ids=evidence_ids or [],
        )


class HardGate(StrictModel):
    gate_id: str
    name: str
    passed: bool
    reason: str = ""
    evidence_ids: list[str] = Field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        passed: bool,
        reason: str = "",
        evidence_ids: list[str] | None = None,
    ) -> HardGate:
        seed = {
            "name": name,
            "passed": passed,
            "reason": reason,
            "evidence_ids": evidence_ids or [],
        }
        return cls(
            gate_id=f"gate_{digest_json(seed)[:32]}",
            name=name,
            passed=passed,
            reason=reason,
            evidence_ids=evidence_ids or [],
        )


class ServiceEdgeProfile(StrictModel):
    edge_id: str
    name: str
    from_node: str
    to_node: str
    capacity: int = Field(ge=0)
    cost_per_unit: int = Field(default=1, ge=0)
    delay_steps: int = Field(default=0, ge=0)
    error_rate_ppm: int = Field(default=0, ge=0, le=1_000_000)
    evidence_ids: list[str] = Field(default_factory=list)
    reservations: list[CapacityReservation] = Field(default_factory=list)
    hard_gates: list[HardGate] = Field(default_factory=list)
    queue_state: QueueState | None = None
    risk_charges: list[RiskCharge] = Field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        from_node: str,
        to_node: str,
        capacity: int,
        cost_per_unit: int = 1,
        delay_steps: int = 0,
        evidence_ids: list[str] | None = None,
        reservations: list[CapacityReservation] | None = None,
        hard_gates: list[HardGate] | None = None,
        queue_state: QueueState | None = None,
        risk_charges: list[RiskCharge] | None = None,
    ) -> ServiceEdgeProfile:
        seed = {
            "name": name,
            "from_node": from_node,
            "to_node": to_node,
            "capacity": capacity,
            "evidence_ids": evidence_ids or [],
        }
        return cls(
            edge_id=f"edge_{digest_json(seed)[:32]}",
            name=name,
            from_node=from_node,
            to_node=to_node,
            capacity=capacity,
            cost_per_unit=cost_per_unit,
            delay_steps=delay_steps,
            evidence_ids=evidence_ids or [],
            reservations=reservations or [],
            hard_gates=hard_gates or [],
            queue_state=queue_state,
            risk_charges=risk_charges or [],
        )

    def blocked_gates(self) -> list[HardGate]:
        return [gate for gate in self.hard_gates if not gate.passed]

    def certified_capacity(self) -> int:
        reserved = sum(reservation.amount for reservation in self.reservations)
        charge = sum(risk.amount for risk in self.risk_charges)
        queue_penalty = 0
        if self.queue_state is not None:
            queue_penalty = max(0, self.queue_state.arrival_rate - self.queue_state.service_rate)
        return max(0, self.capacity - reserved - charge - queue_penalty)


class ConversionNetwork(StrictModel):
    schema_version: str = SCHEMA_VERSION
    network_id: str
    name: str
    nodes: list[str]
    edges: list[ServiceEdgeProfile]
    source_nodes: list[str] = Field(default_factory=list)
    sink_nodes: list[str] = Field(default_factory=list)
    created_at: dt.datetime = Field(default_factory=now_utc)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        nodes: list[str],
        edges: list[ServiceEdgeProfile],
        source_nodes: list[str] | None = None,
        sink_nodes: list[str] | None = None,
    ) -> ConversionNetwork:
        seed = {
            "name": name,
            "nodes": nodes,
            "edges": [edge.model_dump(mode="json") for edge in edges],
            "source_nodes": source_nodes or [],
            "sink_nodes": sink_nodes or [],
        }
        return cls(
            network_id=f"net_{digest_json(seed)[:32]}",
            name=name,
            nodes=nodes,
            edges=edges,
            source_nodes=source_nodes or [],
            sink_nodes=sink_nodes or [],
        )

    def content_digest(self) -> str:
        return digest_json(self.model_dump(mode="json", exclude={"created_at"}))


class ClaimRequirement(StrictModel):
    schema_version: str = SCHEMA_VERSION
    claim_id: str
    network_id: str
    target_value: int = Field(ge=0)
    required_scopes: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    required_tcb: list[str] = Field(default_factory=list)
    certification_split: dict[str, list[str]] = Field(default_factory=dict)
    created_at: dt.datetime = Field(default_factory=now_utc)

    @classmethod
    def create(
        cls,
        *,
        network_id: str,
        target_value: int,
        required_scopes: list[str] | None = None,
        required_evidence_ids: list[str] | None = None,
        required_tcb: list[str] | None = None,
        certification_split: dict[str, list[str]] | None = None,
    ) -> ClaimRequirement:
        seed = {
            "network_id": network_id,
            "target_value": target_value,
            "required_scopes": required_scopes or [],
            "required_evidence_ids": required_evidence_ids or [],
            "required_tcb": required_tcb or [],
            "certification_split": certification_split or {},
        }
        return cls(
            claim_id=f"claim_{digest_json(seed)[:32]}",
            network_id=network_id,
            target_value=target_value,
            required_scopes=required_scopes or [],
            required_evidence_ids=required_evidence_ids or [],
            required_tcb=required_tcb or [],
            certification_split=certification_split or {},
        )

    @field_validator("certification_split")
    @classmethod
    def split_must_be_declared(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        if value and not {"ledger", "selection", "certification"}.issubset(value):
            raise ValueError("certification_split must include ledger, selection, certification")
        return value


class CompiledClaim(StrictModel):
    schema_version: str = SCHEMA_VERSION
    compilation_id: str
    claim_id: str
    request: ClaimRequirement
    request_digest: str
    supported: bool
    reason: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: dt.datetime = Field(default_factory=now_utc)

    @classmethod
    def create(
        cls,
        *,
        request: ClaimRequirement,
        supported: bool,
        reason: str = "",
        evidence_ids: list[str] | None = None,
    ) -> CompiledClaim:
        compilation_seed = {
            "claim_id": request.claim_id,
            "request_digest": digest_json(request.model_dump(mode="json")),
            "supported": supported,
            "reason": reason,
            "evidence_ids": evidence_ids or [],
            "nonce": uuid.uuid4().hex,
        }
        return cls(
            compilation_id=f"cmp_{digest_json(compilation_seed)[:32]}",
            claim_id=request.claim_id,
            request=request,
            request_digest=digest_json(request.model_dump(mode="json")),
            supported=supported,
            reason=reason,
            evidence_ids=evidence_ids or [],
        )


class BottleneckReport(StrictModel):
    schema_version: str = SCHEMA_VERSION
    report_id: str
    network_id: str
    claim_id: str
    mode: AnalysisMode
    status: ReportStatus
    lower_bound: int = Field(ge=0)
    bottleneck_edges: list[str] = Field(default_factory=list)
    diagnostic_scores: dict[str, int] = Field(default_factory=dict)
    total_risk_charge: int = Field(default=0, ge=0)
    hard_gate_failures: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    certificate_summary: dict[str, Any] = Field(default_factory=dict)
    dual_price_intervals: dict[str, Any] = Field(default_factory=dict)
    validation_capital: dict[str, Any] = Field(default_factory=dict)
    full_profile_status: str | None = None
    created_at: dt.datetime = Field(default_factory=now_utc)

    @classmethod
    def create(
        cls,
        *,
        network_id: str,
        claim_id: str,
        mode: AnalysisMode,
        status: ReportStatus,
        lower_bound: int,
        bottleneck_edges: list[str],
        diagnostic_scores: dict[str, int],
        total_risk_charge: int,
        hard_gate_failures: list[str] | None = None,
        evidence_ids: list[str] | None = None,
        limitations: list[str] | None = None,
        certificate_summary: dict[str, Any] | None = None,
        dual_price_intervals: dict[str, Any] | None = None,
        validation_capital: dict[str, Any] | None = None,
        full_profile_status: str | None = None,
    ) -> BottleneckReport:
        seed = {
            "network_id": network_id,
            "claim_id": claim_id,
            "mode": mode.value,
            "status": status.value,
            "lower_bound": lower_bound,
            "bottleneck_edges": bottleneck_edges,
            "diagnostic_scores": diagnostic_scores,
            "total_risk_charge": total_risk_charge,
            "hard_gate_failures": hard_gate_failures or [],
            "evidence_ids": evidence_ids or [],
            "certificate_summary": certificate_summary or {},
            "dual_price_intervals": dual_price_intervals or {},
            "validation_capital": validation_capital or {},
            "full_profile_status": full_profile_status,
        }
        return cls(
            report_id=f"rep_{digest_json(seed)[:32]}",
            network_id=network_id,
            claim_id=claim_id,
            mode=mode,
            status=status,
            lower_bound=lower_bound,
            bottleneck_edges=bottleneck_edges,
            diagnostic_scores=diagnostic_scores,
            total_risk_charge=total_risk_charge,
            hard_gate_failures=hard_gate_failures or [],
            evidence_ids=evidence_ids or [],
            limitations=limitations or [],
            certificate_summary=certificate_summary or {},
            dual_price_intervals=dual_price_intervals or {},
            validation_capital=validation_capital or {},
            full_profile_status=full_profile_status,
        )


class InvestmentBudget(StrictModel):
    budget_id: str
    units: int = Field(ge=0)

    @classmethod
    def create(cls, *, units: int) -> InvestmentBudget:
        return cls(budget_id=f"budget_{digest_json({'units': units})[:32]}", units=units)


class InvestmentCandidate(StrictModel):
    schema_version: str = SCHEMA_VERSION
    candidate_id: str
    edge_id: str
    resource: str
    cost: int = Field(ge=0)
    expected_lower_bound_gain: int
    output_class: Literal["screen", "report", "adopt", "experiment", "certified_floor"] = "screen"
    reason: str = ""

    @classmethod
    def create(
        cls,
        *,
        edge_id: str,
        resource: str,
        cost: int,
        expected_lower_bound_gain: int,
        reason: str,
    ) -> InvestmentCandidate:
        seed = {
            "edge_id": edge_id,
            "resource": resource,
            "cost": cost,
            "expected_lower_bound_gain": expected_lower_bound_gain,
            "reason": reason,
        }
        return cls(
            candidate_id=f"inv_{digest_json(seed)[:32]}",
            edge_id=edge_id,
            resource=resource,
            cost=cost,
            expected_lower_bound_gain=expected_lower_bound_gain,
            reason=reason,
        )
