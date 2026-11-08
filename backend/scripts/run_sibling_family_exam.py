#!/usr/bin/env python3
"""Run and score the sibling-family exam (#12374, #12221 §3, Decide 61-A).

Usage:
    python3 scripts/run_sibling_family_exam.py [--write]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.utils.sibling_family_exam import (  # noqa: E402
    export_sibling_family_exam_for_evals,
    format_sibling_family_exam_markdown,
    run_sibling_family_exam,
)

DEFAULT_DOC_PATH = REPO_ROOT / "docs" / "discover" / "sibling-family-exam-2026-11.md"
DEFAULT_JSON_PATH = (
    REPO_ROOT / "frontend" / "lib" / "evals" / "data" / "sibling-family-exam-2026-11.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run and score the sibling-family exam (#12374)."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the markdown receipt and /evals JSON record.",
    )
    parser.add_argument(
        "--doc-out",
        type=Path,
        default=DEFAULT_DOC_PATH,
        help="Path to write markdown receipt.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help="Path to write /evals JSON record.",
    )
    args = parser.parse_args(argv)

    record = run_sibling_family_exam()
    cost_banner = str(record.get("cost_banner") or "")
    evals_payload = export_sibling_family_exam_for_evals(record)
    markdown = format_sibling_family_exam_markdown(record, cost_banner=cost_banner)

    print(
        f"[sibling_family_exam] result={record['result']} "
        f"licence={record['licences']['sibling_family']}"
    )
    for gate in record["gate_results"]:
        print(f"  gate={gate['id']} -> {gate['result']}")

    if args.write:
        args.doc_out.parent.mkdir(parents=True, exist_ok=True)
        args.doc_out.write_text(markdown, encoding="utf-8")
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(evals_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[sibling_family_exam] wrote {args.doc_out} and {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
