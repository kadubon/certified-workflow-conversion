"""Machine-checkable certificate models for the full analysis profile."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import Field

from certified_workflow_conversion.core.canonical import digest_json
from certified_workflow_conversion.core.models import SCHEMA_VERSION, StrictModel, now_utc

ContractType = Literal["constraint", "charge", "gate", "reservation", "nonempty", "report"]
CompositionRule = Literal[
    "union",
    "split",
    "eprocess",
    "simultaneous",
    "time_uniform",
    "uniform",
    "deterministic",
]
ContractStatus = Literal[
    "active",
    "expired",
    "quarantined",
    "superseded",
    "policy_reserve",
]


class EvidenceContract(StrictModel):
    schema_version: str = SCHEMA_VERSION
    contract_id: str
    type: ContractType
    target: str
    scope: dict[str, Any] = Field(default_factory=dict)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    estimator: str = ""
    checker: str
    tcb: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    budget_microunits: int = Field(default=0, ge=0)
    compose: CompositionRule = "deterministic"
    exposes: str
    status: ContractStatus = "active"

    @classmethod
    def create(
        cls,
        *,
        type: ContractType,
        target: str,
        checker: str,
        exposes: str,
        scope: dict[str, Any] | None = None,
        assumptions: dict[str, Any] | None = None,
        estimator: str = "",
        tcb: list[str] | None = None,
        dependencies: list[str] | None = None,
        budget_microunits: int = 0,
        compose: CompositionRule = "deterministic",
        status: ContractStatus = "active",
    ) -> EvidenceContract:
        seed = {
            "type": type,
            "target": target,
            "scope": scope or {},
            "checker": checker,
            "exposes": exposes,
            "dependencies": dependencies or [],
            "budget_microunits": budget_microunits,
            "compose": compose,
        }
        return cls(
            contract_id=f"ctr_{digest_json(seed)[:32]}",
            type=type,
            target=target,
            checker=checker,
            exposes=exposes,
            scope=scope or {},
            assumptions=assumptions or {},
            estimator=estimator,
            tcb=tcb or [],
            dependencies=dependencies or [],
            budget_microunits=budget_microunits,
            compose=compose,
            status=status,
        )


class VerificationWitness(StrictModel):
    schema_version: str = SCHEMA_VERSION
    witness_id: str
    contract_id: str
    input_digest: str
    checker_digest: str
    proof_digest: str = ""
    scope: dict[str, Any] = Field(default_factory=dict)
    accepted_output: dict[str, Any] = Field(default_factory=dict)
    residual: dict[str, Any] = Field(default_factory=dict)
    verifier: str
    tcb: list[str] = Field(default_factory=list)
    signature: str = ""
    result: Literal["accept", "reject"] = "accept"
    exposes: str = ""

    @classmethod
    def create(
        cls,
        *,
        contract_id: str,
        input_digest: str,
        checker_digest: str,
        verifier: str,
        accepted_output: dict[str, Any] | None = None,
        residual: dict[str, Any] | None = None,
        scope: dict[str, Any] | None = None,
        tcb: list[str] | None = None,
        result: Literal["accept", "reject"] = "accept",
        exposes: str = "",
    ) -> VerificationWitness:
        seed = {
            "contract_id": contract_id,
            "input_digest": input_digest,
            "checker_digest": checker_digest,
            "verifier": verifier,
            "accepted_output": accepted_output or {},
            "residual": residual or {},
            "scope": scope or {},
            "tcb": tcb or [],
            "result": result,
            "exposes": exposes,
            "nonce": uuid.uuid4().hex,
        }
        return cls(
            witness_id=f"wit_{digest_json(seed)[:32]}",
            contract_id=contract_id,
            input_digest=input_digest,
            checker_digest=checker_digest,
            verifier=verifier,
            accepted_output=accepted_output or {},
            residual=residual or {},
            scope=scope or {},
            tcb=tcb or [],
            result=result,
            exposes=exposes,
        )

    def accepted(self) -> bool:
        return self.result == "accept"


class DataProtocol(StrictModel):
    schema_version: str = SCHEMA_VERSION
    build: list[str] = Field(default_factory=list)
    select: list[str] = Field(default_factory=list)
    cert: list[str] = Field(default_factory=list)
    composition_rule: CompositionRule | None = None

    def overlapping_refs(self) -> set[str]:
        build = set(self.build)
        select = set(self.select)
        cert = set(self.cert)
        return (build & select) | (build & cert) | (select & cert)


class ConfidenceBudget(StrictModel):
    schema_version: str = SCHEMA_VERSION
    max_microunits: int = Field(ge=0)
    composition_rule: CompositionRule = "union"


class StatisticalCertificate(StrictModel):
    schema_version: str = SCHEMA_VERSION
    kind: Literal["one_step_dr", "dynamic_path", "time_uniform"]
    params: dict[str, Any]


class DynamicPathLawCertificate(StrictModel):
    schema_version: str = SCHEMA_VERSION
    lower_q: float
    bound_b: float = Field(ge=0)
    epsilon_path: float = Field(ge=0)
    delta_microunits: int = Field(default=0, ge=0)

    def lower_bound(self) -> float:
        return self.lower_q - 2.0 * self.bound_b * self.epsilon_path


class QueueCertificate(StrictModel):
    schema_version: str = SCHEMA_VERSION
    service_discipline: str
    no_phantom_release: bool
    bounded_increments: bool
    boundary_correction: float = Field(ge=0)
    compact_allowance: float = Field(default=0, ge=0)
    boundary_derivation: dict[str, Any] = Field(default_factory=dict)

    def accepted(self) -> bool:
        return self.no_phantom_release and self.bounded_increments


class ReleaseAccountingCertificate(StrictModel):
    schema_version: str = SCHEMA_VERSION
    reward_lower_bounds: dict[str, float] = Field(default_factory=dict)
    direct_cost_rate: float = Field(default=0, ge=0)
    disjoint_ledgers: bool = True


class GoodhartBudget(StrictModel):
    schema_version: str = SCHEMA_VERSION
    statistical: float = Field(default=0, ge=0)
    calibration: float = Field(default=0, ge=0)
    transport: float = Field(default=0, ge=0)
    misspecification: float = Field(default=0, ge=0)
    selection: float = Field(default=0, ge=0)
    contamination: float = Field(default=0, ge=0)
    reuse: float = Field(default=0, ge=0)
    construction_evidence: list[str] = Field(default_factory=list)

    def total(self) -> float:
        return (
            self.statistical
            + self.calibration
            + self.transport
            + self.misspecification
            + self.selection
            + self.contamination
            + self.reuse
        )


class OpenWorldHazardCharge(StrictModel):
    schema_version: str = SCHEMA_VERSION
    coordinate: str
    charge: float = Field(ge=0)
    construction_evidence: list[str] = Field(default_factory=list)
    fallback_action: Literal["hold", "quarantine", "abstain", "retire", "reroot"]


class DualPriceInterval(StrictModel):
    schema_version: str = SCHEMA_VERSION
    edge_id: str
    lower: float
    estimate: float
    upper: float
    perturbation: float = Field(default=1.0, gt=0)


class ValidationDependencyEdge(StrictModel):
    from_node: str
    to_node: str
    kind: Literal["justify", "influence", "data", "train", "leak", "capacity"] = "justify"
    capacity: float = Field(default=0, ge=0)


class ValidationDependencyGraph(StrictModel):
    schema_version: str = SCHEMA_VERSION
    nodes: list[str]
    root_nodes: list[str] = Field(default_factory=list)
    edges: list[ValidationDependencyEdge] = Field(default_factory=list)
    demand_nodes: list[str] = Field(default_factory=list)
    demands: dict[str, float] = Field(default_factory=dict)


class RootCutCertificate(StrictModel):
    schema_version: str = SCHEMA_VERSION
    root_reachable: dict[str, bool]
    cut_capacity: float = Field(ge=0)
    supported_demand: float = Field(ge=0)
    blocked_nodes: list[str] = Field(default_factory=list)
    created_at: Any = Field(default_factory=now_utc)
