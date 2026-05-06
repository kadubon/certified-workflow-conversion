from __future__ import annotations

from full_profile_common import build_full_demo


def main() -> None:
    kernel, network, claim = build_full_demo()
    report = kernel.analyze(
        network.network_id,
        claim.claim_id,
        mode="certified_lower_bound",
        profile="full",
    )
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

