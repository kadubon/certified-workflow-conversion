from __future__ import annotations

import re

from typer.testing import CliRunner

from certified_workflow_conversion.cli.app import app


def test_cli_init_and_audit(tmp_path) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    state = tmp_path / ".cwc"
    result = runner.invoke(app, ["init", str(state)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["audit", "--state", str(state)])
    assert result.exit_code == 0, result.output
    assert "evidence" in result.output


def test_cli_evidence_network_claim_analyze(tmp_path) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    state = tmp_path / ".cwc"
    evidence_path = tmp_path / "evidence.jsonl"
    evidence_path.write_text(
        '{"kind":"validation","scope":"cli","source":"test","payload":{"ok":true}}\n',
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["evidence", "add", str(evidence_path), "--state", str(state)],
    )
    assert result.exit_code == 0, result.output

    network_path = tmp_path / "network.json"
    network_path.write_text(
        """
        {
          "name": "cli-network",
          "nodes": ["a", "b"],
          "edges": [{"name": "edge", "from_node": "a", "to_node": "b", "capacity": 2}]
        }
        """,
        encoding="utf-8",
    )
    result = runner.invoke(app, ["network", "add", str(network_path), "--state", str(state)])
    assert result.exit_code == 0, result.output
    network_id = _extract_prefixed(result.output, "net_")

    claim_path = tmp_path / "claim.json"
    claim_path.write_text(
        f'{{"network_id":"{network_id}","target_value":1,"required_scopes":["cli"]}}',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["claim", "compile", str(claim_path), "--state", str(state)])
    assert result.exit_code == 0, result.output
    claim_id = _extract_prefixed(result.output, "claim_")

    result = runner.invoke(
        app,
        ["analyze", "--network", network_id, "--claim", claim_id, "--state", str(state)],
    )
    assert result.exit_code == 0, result.output
    assert "lower_bound" in result.output


def _extract_prefixed(text: str, prefix: str) -> str:
    match = re.search(rf"{re.escape(prefix)}[0-9a-f]{{32}}", text)
    if match is not None:
        return match.group(0)
    raise AssertionError(f"could not find token with prefix {prefix!r} in {text!r}")
