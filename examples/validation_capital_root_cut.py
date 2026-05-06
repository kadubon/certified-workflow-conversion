from __future__ import annotations

from certified_workflow_conversion.adapters.validation_capital import (
    certify_validation_capital,
)
from certified_workflow_conversion.core.certificates import (
    ValidationDependencyEdge,
    ValidationDependencyGraph,
)


def main() -> None:
    graph = ValidationDependencyGraph(
        nodes=["external-root", "checker", "unrooted-rubric"],
        root_nodes=["external-root"],
        edges=[
            ValidationDependencyEdge(
                from_node="external-root",
                to_node="checker",
                kind="capacity",
                capacity=2,
            )
        ],
        demand_nodes=["checker", "unrooted-rubric"],
        demands={"checker": 1, "unrooted-rubric": 1},
    )
    certificate = certify_validation_capital(graph)
    print(certificate.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

