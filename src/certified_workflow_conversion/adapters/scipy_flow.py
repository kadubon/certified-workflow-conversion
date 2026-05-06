"""SciPy-backed conservative conversion-flow relaxation."""

from __future__ import annotations

import math
from typing import Any

from certified_workflow_conversion.core.certificates import DualPriceInterval
from certified_workflow_conversion.core.errors import FailClosedError
from certified_workflow_conversion.core.models import ConversionNetwork


def assert_scipy_available() -> None:
    try:
        import scipy.optimize  # type: ignore[import-untyped]  # noqa: F401
    except ImportError as exc:
        raise FailClosedError(
            "full analysis profile requires installing the full extra: "
            "uv sync --extra dev --extra full"
        ) from exc


def solve_conservative_flow(
    network: ConversionNetwork,
    target_value: int,
) -> dict[str, Any]:
    assert_scipy_available()
    if not network.source_nodes or not network.sink_nodes:
        raise FailClosedError("full profile requires explicit source_nodes and sink_nodes")
    base = _solve_value(network, target_value, {})
    intervals: dict[str, dict[str, float | str]] = {}
    for edge in network.edges:
        capacity = float(edge.certified_capacity())
        perturbation = 1.0
        up = _solve_value(network, target_value, {edge.edge_id: capacity + perturbation})
        down = _solve_value(
            network,
            target_value,
            {edge.edge_id: max(0.0, capacity - perturbation)},
        )
        forward = max(0.0, up - base) / perturbation
        backward = max(0.0, base - down) / perturbation
        interval = DualPriceInterval(
            edge_id=edge.edge_id,
            lower=min(forward, backward),
            estimate=forward,
            upper=max(forward, backward),
            perturbation=perturbation,
        )
        intervals[edge.edge_id] = interval.model_dump(mode="json")
    return {
        "lower_bound": int(math.floor(base)),
        "flow_value": base,
        "dual_price_intervals": intervals,
    }


def _solve_value(
    network: ConversionNetwork,
    target_value: int,
    capacity_overrides: dict[str, float],
) -> float:
    from scipy.optimize import linprog

    super_source = "__cwc_source__"
    super_sink = "__cwc_sink__"
    flow_edges: list[tuple[str, str, str, float]] = []
    for edge in network.edges:
        capacity = capacity_overrides.get(edge.edge_id, float(edge.certified_capacity()))
        if edge.from_node not in network.nodes or edge.to_node not in network.nodes:
            continue
        flow_edges.append((edge.edge_id, edge.from_node, edge.to_node, max(0.0, capacity)))
    for source in network.source_nodes:
        flow_edges.append((f"source:{source}", super_source, source, float(target_value)))
    for sink in network.sink_nodes:
        flow_edges.append((f"sink:{sink}", sink, super_sink, float(target_value)))
    if not flow_edges:
        return 0.0

    c = [
        -1.0 if left == super_source else 0.0
        for _, left, _, _ in flow_edges
    ]
    nodes = sorted(set(network.nodes) | {super_source, super_sink})
    a_eq: list[list[float]] = []
    b_eq: list[float] = []
    for node in nodes:
        if node in {super_source, super_sink}:
            continue
        row = []
        for _, left, right, _ in flow_edges:
            if right == node:
                row.append(1.0)
            elif left == node:
                row.append(-1.0)
            else:
                row.append(0.0)
        a_eq.append(row)
        b_eq.append(0.0)
    bounds = [(0.0, capacity) for _, _, _, capacity in flow_edges]
    result = linprog(
        c,
        A_eq=a_eq or None,
        b_eq=b_eq or None,
        bounds=bounds,
        method="highs",
    )
    if not result.success:
        raise FailClosedError(f"SciPy flow relaxation failed: {result.message}")
    value = -float(result.fun)
    if value < 1e-9:
        return 0.0
    return min(float(target_value), value)
