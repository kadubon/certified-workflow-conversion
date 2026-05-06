"""Validation-capital root reachability and root-cut checks."""

from __future__ import annotations

from collections import deque

from certified_workflow_conversion.core.certificates import (
    RootCutCertificate,
    ValidationDependencyGraph,
)


def certify_validation_capital(graph: ValidationDependencyGraph) -> RootCutCertificate:
    reachable = _root_reachable(graph)
    blocked_nodes = [
        node for node in graph.demand_nodes if not reachable.get(node, False)
    ]
    cut_capacity = _root_cut_capacity(graph)
    total_demand = sum(graph.demands.get(node, 0.0) for node in graph.demand_nodes)
    supported = min(total_demand, cut_capacity)
    return RootCutCertificate(
        root_reachable=reachable,
        cut_capacity=cut_capacity,
        supported_demand=supported,
        blocked_nodes=blocked_nodes,
    )


def _root_reachable(graph: ValidationDependencyGraph) -> dict[str, bool]:
    adjacency: dict[str, list[str]] = {node: [] for node in graph.nodes}
    for edge in graph.edges:
        adjacency.setdefault(edge.from_node, []).append(edge.to_node)
    seen = set(graph.root_nodes)
    queue: deque[str] = deque(graph.root_nodes)
    while queue:
        node = queue.popleft()
        for nxt in adjacency.get(node, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return {node: node in seen for node in graph.nodes}


def _root_cut_capacity(graph: ValidationDependencyGraph) -> float:
    if not graph.root_nodes or not graph.demand_nodes:
        return 0.0
    capacities: dict[tuple[str, str], float] = {}
    super_source = "__cwc_val_root__"
    super_sink = "__cwc_val_demand__"
    total_capacity = 0.0
    for edge in graph.edges:
        capacity = edge.capacity
        if edge.kind != "capacity" and capacity == 0:
            capacity = sum(graph.demands.values()) or 1.0
        capacities[(edge.from_node, edge.to_node)] = (
            capacities.get((edge.from_node, edge.to_node), 0.0) + capacity
        )
        total_capacity += capacity
    root_supply = max(total_capacity, sum(graph.demands.values()), 1.0)
    for root in graph.root_nodes:
        capacities[(super_source, root)] = root_supply
    for node in graph.demand_nodes:
        capacities[(node, super_sink)] = graph.demands.get(node, 0.0)
    return _max_flow(capacities, super_source, super_sink)


def _max_flow(capacities: dict[tuple[str, str], float], source: str, sink: str) -> float:
    residual = dict(capacities)
    total = 0.0
    while True:
        parent: dict[str, str | None] = {source: None}
        queue = [source]
        for node in queue:
            for (left, right), capacity in list(residual.items()):
                if left == node and capacity > 1e-12 and right not in parent:
                    parent[right] = left
                    queue.append(right)
                    if right == sink:
                        break
            if sink in parent:
                break
        if sink not in parent:
            return total
        path_capacity = float("inf")
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
            residual[(node, prev)] = residual.get((node, prev), 0.0) + path_capacity
            node = prev
        total += path_capacity

