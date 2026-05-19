"""Check advisory Discover ground-truth source health.

This script is read-only. It loads configured Polymarket email and external
curator/social ground-truth inputs, then reports stale/empty/under-parsed
sources before those inputs are used for Discover diagnostics.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.external_curator_ground_truth import (  # noqa: E402
    load_external_curator_ground_truth_report_from_env,
)
from app.utils.ground_truth_health import (  # noqa: E402
    assess_ground_truth_report_health,
    summarize_ground_truth_health,
)
from app.utils.polymarket_email_ground_truth import (  # noqa: E402
    load_polymarket_email_ground_truth_report_from_env,
)


def build_health_report(*, min_load_rate: float) -> dict:
    email_report = load_polymarket_email_ground_truth_report_from_env()
    curator_report = load_external_curator_ground_truth_report_from_env()
    return summarize_ground_truth_health(
        [
            assess_ground_truth_report_health(
                email_report,
                label="polymarket_email",
                min_load_rate=min_load_rate,
            ),
            assess_ground_truth_report_health(
                curator_report,
                label="external_curator",
                min_load_rate=min_load_rate,
            ),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--min-load-rate",
        type=float,
        default=0.25,
        help="Warn when loaded/raw row rate falls below this threshold",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit nonzero on warning or critical health",
    )
    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        help="Exit nonzero only on critical health",
    )
    args = parser.parse_args(argv)

    report = build_health_report(min_load_rate=args.min_load_rate)
    print(json.dumps(report, indent=2, sort_keys=True))

    if report["severity"] == "critical" and (args.fail_on_critical or args.fail_on_warning):
        return 2
    if report["severity"] == "warning" and args.fail_on_warning:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
