"""Deterministic statistical certificate calculations."""

from __future__ import annotations

import math
from typing import Any

from certified_workflow_conversion.core.certificates import (
    DynamicPathLawCertificate,
    StatisticalCertificate,
)
from certified_workflow_conversion.core.errors import FailClosedError


def one_step_dr_lower_bound(
    *,
    estimate: float,
    b_z: float,
    candidate_count: int,
    delta: float,
    n: int,
    epsilon_int: float = 0.0,
    epsilon_label: float = 0.0,
) -> float:
    if n <= 0:
        raise FailClosedError("one-step DR certificate requires n > 0")
    if candidate_count <= 0:
        raise FailClosedError("one-step DR certificate requires candidate_count > 0")
    if not 0.0 < delta < 1.0:
        raise FailClosedError("one-step DR certificate requires 0 < delta < 1")
    if b_z < 0 or epsilon_int < 0 or epsilon_label < 0:
        raise FailClosedError("certificate radii must be non-negative")
    radius = b_z * math.sqrt(2.0 * math.log(2.0 * candidate_count / delta) / n)
    return estimate - radius - epsilon_int - epsilon_label


def dynamic_path_lower_bound(*, lower_q: float, bound_b: float, epsilon_path: float) -> float:
    return DynamicPathLawCertificate(
        lower_q=lower_q,
        bound_b=bound_b,
        epsilon_path=epsilon_path,
    ).lower_bound()


def time_uniform_lower_bound(
    *,
    lower_q: float,
    bound_b: float,
    epsilon_tau: float,
    delta_val: float,
    delta_path: float,
    max_delta: float,
) -> dict[str, float]:
    if min(delta_val, delta_path, max_delta) < 0:
        raise FailClosedError("time-uniform deltas must be non-negative")
    joint_delta = delta_val + delta_path
    if joint_delta > max_delta:
        raise FailClosedError("time-uniform confidence budget exceeded")
    return {
        "lower_bound": dynamic_path_lower_bound(
            lower_q=lower_q,
            bound_b=bound_b,
            epsilon_path=epsilon_tau,
        ),
        "joint_delta": joint_delta,
    }


def evaluate_statistical_certificate(certificate: StatisticalCertificate) -> dict[str, Any]:
    params = certificate.params
    if certificate.kind == "one_step_dr":
        return {
            "kind": certificate.kind,
            "lower_bound": one_step_dr_lower_bound(
                estimate=float(params["estimate"]),
                b_z=float(params["b_z"]),
                candidate_count=int(params["candidate_count"]),
                delta=float(params["delta"]),
                n=int(params["n"]),
                epsilon_int=float(params.get("epsilon_int", 0.0)),
                epsilon_label=float(params.get("epsilon_label", 0.0)),
            ),
        }
    if certificate.kind == "dynamic_path":
        return {
            "kind": certificate.kind,
            "lower_bound": dynamic_path_lower_bound(
                lower_q=float(params["lower_q"]),
                bound_b=float(params["bound_b"]),
                epsilon_path=float(params["epsilon_path"]),
            ),
        }
    if certificate.kind == "time_uniform":
        result: dict[str, Any] = time_uniform_lower_bound(
            lower_q=float(params["lower_q"]),
            bound_b=float(params["bound_b"]),
            epsilon_tau=float(params["epsilon_tau"]),
            delta_val=float(params["delta_val"]),
            delta_path=float(params["delta_path"]),
            max_delta=float(params["max_delta"]),
        )
        result["kind"] = certificate.kind
        return result
    raise FailClosedError(f"unsupported statistical certificate: {certificate.kind}")
