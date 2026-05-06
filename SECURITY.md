# Security Policy

## Scope

CWC is a local evidence and reporting kernel. It is not a sandbox, credential
manager, policy engine, or external-effect gateway.

Security issues in scope include:

- incorrect fail-closed behavior;
- accepting inactive, expired, unsupported, or rootless evidence as certified
  support;
- accepting unbound evidence contracts or witnesses in `full` profile;
- unsafe file handling in CLI/import paths;
- accidental disclosure of local secrets or private paths in examples, tests, or
  docs.

Out of scope for this repository:

- operating-system sandboxing;
- network isolation;
- credential storage;
- production authorization policy;
- model truthfulness, factual truth, or alignment claims.

## Reporting

Please report vulnerabilities through GitHub private vulnerability reporting if
enabled for the repository. If that is unavailable, open an issue with a minimal
reproduction that does not include secrets, tokens, private data, or proprietary
logs.

## Supported Versions

`0.1.x` beta versions receive best-effort security fixes. APIs and schemas may
change before a stable release.

## Security Assumptions

- Local SQLite state is trusted local state in the beta.
- Evidence can be poisoned, stale, or adversarial.
- Raw evidence and diagnostic reports are not deployment authorization.
- `light` profile is diagnostic only.
- `full` profile certifies evidence-bound procedural admissibility, not factual
  truth or production safety.
- External-effect tools require deployment-level OS, network, identity, secrets,
  audit, and recovery controls outside CWC.
