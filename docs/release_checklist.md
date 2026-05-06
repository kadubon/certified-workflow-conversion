# Release Checklist

Use this checklist before publishing a beta or stable release.

## Quality Gates

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run mypy src
uv sync --extra dev --extra full
uv run pytest tests/full
uv run python examples/coding_agent_pipeline/run_demo.py
uv run python examples/full_certified_lower_bound.py
uv run python examples/dual_price_interval.py
uv run python examples/validation_capital_root_cut.py
uv build
```

Inspect generated package artifacts before upload:

```powershell
uv run python -m tarfile -l dist/certified_workflow_conversion-*.tar.gz
```

Delete `dist/`, `build/`, caches, and virtual environments before final source
inspection if they were generated locally.

## Security Review

- Confirm no API keys, tokens, credentials, private logs, local user paths, or
  private machine names were added.
- Confirm examples run without network access or API keys.
- Confirm `light` profile remains diagnostic only.
- Confirm `full` profile still fails closed on missing contracts, witnesses,
  evidence dependencies, TCB roots, split violations, and unbound report terms.
- Confirm docs do not claim factual truth, model truthfulness, sandboxing, or
  production authorization.

## Documentation Review

- README states what the project does, what is unique, how to run it, and what
  it cannot guarantee.
- `docs/theory_mapping.md` separates implemented behavior from limitations.
- `docs/security_model.md` and `SECURITY.md` agree.
- Public examples are deterministic and require no external services.

## Release Steps

1. Update `CHANGELOG.md`.
2. Update the package version in `pyproject.toml` and
   `src/certified_workflow_conversion/__init__.py`.
3. Run all quality gates.
4. Inspect source and package artifacts for secrets and generated files.
5. Commit, tag, and push from a clean local checkout.
6. Create a GitHub release with limitations and beta status stated clearly.
7. Optionally publish to PyPI.
8. Optionally archive the release to Zenodo.
