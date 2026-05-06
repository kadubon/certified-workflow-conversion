"""Command line interface."""

from __future__ import annotations

from importlib.metadata import entry_points
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from certified_workflow_conversion.adapters.json_loader import load_jsonl, load_mapping
from certified_workflow_conversion.core.models import InvestmentBudget
from certified_workflow_conversion.runtime.kernel import ConversionKernel

app = typer.Typer(no_args_is_help=True)
evidence_app = typer.Typer(no_args_is_help=True)
network_app = typer.Typer(no_args_is_help=True)
claim_app = typer.Typer(no_args_is_help=True)
plugins_app = typer.Typer(no_args_is_help=True)
app.add_typer(evidence_app, name="evidence")
app.add_typer(network_app, name="network")
app.add_typer(claim_app, name="claim")
app.add_typer(plugins_app, name="plugins")
console = Console()


def _kernel(state: Path) -> ConversionKernel:
    return ConversionKernel.open(state)


@app.command()
def init(
    state: Annotated[Path, typer.Argument(help="CWC state directory.")] = Path(".cwc"),
) -> None:
    """Initialize local state."""

    kernel = _kernel(state)
    console.print({"state": str(state), "audit": kernel.audit()})


@evidence_app.command("add")
def evidence_add(
    file: Annotated[Path, typer.Argument(help="Evidence JSON object or JSONL file.")],
    state: Annotated[Path, typer.Option(help="CWC state directory.")] = Path(".cwc"),
) -> None:
    """Append evidence objects."""

    kernel = _kernel(state)
    payloads = load_jsonl(file) if file.suffix.lower() == ".jsonl" else [load_mapping(file)]
    table = Table("evidence_id", "scope", "kind", "obs_seq")
    for payload in payloads:
        stored = kernel.add_evidence(payload)
        table.add_row(stored.evidence_id, stored.scope, stored.kind, str(stored.obs_seq))
    console.print(table)


@network_app.command("add")
def network_add(
    file: Annotated[Path, typer.Argument(help="Network JSON/YAML file.")],
    state: Annotated[Path, typer.Option(help="CWC state directory.")] = Path(".cwc"),
) -> None:
    """Register a conversion network."""

    kernel = _kernel(state)
    network = kernel.register_network(load_mapping(file))
    console.print({"network_id": network.network_id, "edges": len(network.edges)})


@claim_app.command("compile")
def claim_compile(
    file: Annotated[Path, typer.Argument(help="Claim JSON/YAML file.")],
    state: Annotated[Path, typer.Option(help="CWC state directory.")] = Path(".cwc"),
) -> None:
    """Compile a claim against current evidence."""

    kernel = _kernel(state)
    claim = kernel.compile_claim(load_mapping(file))
    console.print(
        {
            "claim_id": claim.claim_id,
            "supported": claim.supported,
            "reason": claim.reason,
        }
    )


@app.command("import-oawm")
def import_oawm(
    oawm_state: Annotated[Path, typer.Option("--state", help="OAWM state dir or SQLite file.")],
    run_id: Annotated[str | None, typer.Option(help="Optional OAWM run_id filter.")] = None,
    cwc_state: Annotated[
        Path,
        typer.Option("--cwc-state", help="CWC state directory."),
    ] = Path(".cwc"),
) -> None:
    """Import OAWM state as read-only CWC evidence."""

    kernel = _kernel(cwc_state)
    imported = kernel.import_oawm(oawm_state, run_id=run_id)
    console.print({"imported": len(imported)})


@app.command()
def analyze(
    network: Annotated[str, typer.Option("--network", help="Network id.")],
    claim: Annotated[str, typer.Option("--claim", help="Compiled claim id.")],
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help="diagnostic or certified_lower_bound; certified reports require --profile full.",
        ),
    ] = "diagnostic",
    profile: Annotated[
        str,
        typer.Option("--profile", help="light or full analysis profile."),
    ] = "light",
    state: Annotated[Path, typer.Option(help="CWC state directory.")] = Path(".cwc"),
) -> None:
    """Analyze a conversion network.

    The light profile is diagnostic only. certified_lower_bound requests in
    light profile fail closed.
    """

    kernel = _kernel(state)
    report = kernel.analyze(network, claim, mode=mode, profile=profile)
    console.print(
        {
            "report_id": report.report_id,
            "status": report.status.value,
            "lower_bound": report.lower_bound,
            "bottleneck_edges": report.bottleneck_edges,
            "profile": profile,
        }
    )


@app.command()
def investments(
    network: Annotated[str, typer.Option("--network", help="Network id.")],
    budget: Annotated[Path, typer.Option("--budget", help="Budget JSON/YAML file.")],
    state: Annotated[Path, typer.Option(help="CWC state directory.")] = Path(".cwc"),
) -> None:
    """Print diagnostic investment candidates."""

    kernel = _kernel(state)
    budget_payload = load_mapping(budget)
    candidates = kernel.propose_investments(
        network,
        InvestmentBudget.create(**budget_payload),
    )
    table = Table("candidate_id", "edge_id", "gain", "class", "reason")
    for candidate in candidates:
        table.add_row(
            candidate.candidate_id,
            candidate.edge_id,
            str(candidate.expected_lower_bound_gain),
            candidate.output_class,
            candidate.reason,
        )
    console.print(table)


@app.command()
def report(
    report_id: Annotated[str, typer.Argument(help="Report id.")],
    state: Annotated[Path, typer.Option(help="CWC state directory.")] = Path(".cwc"),
) -> None:
    """Print a report as JSON."""

    kernel = _kernel(state)
    console.print(kernel.export_report(report_id))


@app.command()
def audit(
    state: Annotated[Path, typer.Option(help="CWC state directory.")] = Path(".cwc"),
) -> None:
    """Print audit counts."""

    console.print(_kernel(state).audit())


@plugins_app.command("list")
def plugins_list() -> None:
    """List installed CWC entry point plugins."""

    table = Table("group", "name", "value")
    for group in [
        "cwc.storage_backends",
        "cwc.analyzers",
        "cwc.optimizers",
        "cwc.checkers",
        "cwc.oawm_bridges",
        "cwc.report_sinks",
    ]:
        for item in entry_points(group=group):
            table.add_row(group, item.name, item.value)
    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
