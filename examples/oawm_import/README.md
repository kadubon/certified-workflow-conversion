# OAWM Import Example

This repository does not require OAWM. When an OAWM state directory is available,
CWC can read it as evidence without mutating the OAWM database:

```powershell
uv run cwc import-oawm --state C:\path\to\.oawm --cwc-state .cwc
```

The bridge imports passed promotion receipts, certified memory records, evidence
manifests, workflow contracts, and events as typed CWC evidence. Failed receipts
and non-certified memory are not used as certified conversion evidence.

