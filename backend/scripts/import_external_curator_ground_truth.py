"""Import reviewed external-curator ground truth into the DB.

Use this after reviewing Manus/social rows with review_social_ground_truth.py.
The import is still advisory: persisted rows feed Discover admin/debug
diagnostics, not production ranking.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.tasks.base import get_task_session  # noqa: E402
from app.utils.external_curator_ground_truth import (  # noqa: E402
    load_external_curator_ground_truth_from_path,
)
from app.utils.persisted_external_curator_ground_truth import (  # noqa: E402
    import_external_curator_ground_truth_rows,
)


async def _run(args: argparse.Namespace) -> int:
    rows = load_external_curator_ground_truth_from_path(
        args.input,
        input_format=args.input_format,
    )
    if args.dry_run:
        print(json.dumps({"dry_run": True, "rows": len(rows)}, sort_keys=True))
        return 0

    async with get_task_session() as session:
        result = await import_external_curator_ground_truth_rows(session, rows)
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Reviewed accepted CSV/JSON/JSONL curator file")
    parser.add_argument(
        "--input-format",
        default=None,
        choices=["csv", "json", "jsonl", None],
        help="Optional format override; otherwise inferred from extension",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
