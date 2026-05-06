from __future__ import annotations

from certified_workflow_conversion.adapters.scipy_flow import solve_conservative_flow
from certified_workflow_conversion.core.models import ConversionNetwork, ServiceEdgeProfile


def main() -> None:
    network = ConversionNetwork.create(
        name="parallel-demo",
        nodes=["source", "left", "right", "sink"],
        source_nodes=["source"],
        sink_nodes=["sink"],
        edges=[
            ServiceEdgeProfile.create(
                name="left-in",
                from_node="source",
                to_node="left",
                capacity=5,
            ),
            ServiceEdgeProfile.create(
                name="left-out",
                from_node="left",
                to_node="sink",
                capacity=5,
            ),
            ServiceEdgeProfile.create(
                name="right-in",
                from_node="source",
                to_node="right",
                capacity=7,
            ),
            ServiceEdgeProfile.create(
                name="right-out",
                from_node="right",
                to_node="sink",
                capacity=7,
            ),
        ],
    )
    result = solve_conservative_flow(network, target_value=20)
    print(result)


if __name__ == "__main__":
    main()

