"""Upload reviewed external-curator ground truth through the admin API.

This avoids requiring local Postgres. Use it after producing an accepted JSONL
file with review_social_ground_truth.py.

Usage:
    ADMIN_TOKEN=... python3 scripts/upload_external_curator_ground_truth.py /tmp/social.accepted.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.external_curator_ground_truth import (  # noqa: E402
    load_external_curator_ground_truth_from_path,
)

DEFAULT_API_URL = "https://api.bainluck.com"


def load_upload_rows(path: str | Path, *, input_format: str | None = None) -> list[dict[str, str]]:
    return load_external_curator_ground_truth_from_path(path, input_format=input_format)


def build_import_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"rows": rows}


def upload_rows(
    rows: list[dict[str, Any]],
    *,
    api_url: str,
    admin_token: str,
    timeout: float = 60.0,
) -> dict[str, Any]:
    base = api_url.rstrip("/")
    response = httpx.post(
        f"{base}/api/admin/discover-external-curator-ground-truth/import-rows",
        params={"secret": admin_token},
        json=build_import_payload(rows),
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Reviewed accepted CSV/JSON/JSONL curator file")
    parser.add_argument(
        "--input-format",
        default=None,
        choices=["csv", "json", "jsonl", None],
        help="Optional format override; otherwise inferred from extension",
    )
    parser.add_argument("--api-url", default=os.getenv("BAINLUCK_API_URL", DEFAULT_API_URL))
    parser.add_argument("--admin-token", default=os.getenv("ADMIN_TOKEN"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    rows = load_upload_rows(args.input, input_format=args.input_format)
    if args.dry_run:
        print(json.dumps({"dry_run": True, "rows": len(rows)}, sort_keys=True))
        return 0
    if not args.admin_token:
        raise SystemExit("ADMIN_TOKEN or --admin-token is required")

    result = upload_rows(
        rows,
        api_url=args.api_url,
        admin_token=args.admin_token,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
