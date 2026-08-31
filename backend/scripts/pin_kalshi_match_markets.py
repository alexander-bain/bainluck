#!/usr/bin/env python3
"""Apply a Kalshi match-market census onto a committed register (Q466).

``fetch_kalshi_match_census.py`` decides WHICH market prices which fixture.
This applies that decision, and it is deliberately the dullest possible edit:
it fills in source blocks the draw ingest already wrote as ``status: "missing"``
and it touches nothing else.

═══ WHAT IT WILL AND WILL NOT OVERWRITE ═══

A ``missing`` block is a placeholder that says, in the register's own words,
"no match market pinned at this source when the draw was ingested".  Filling it
is the whole job.

**Anything that is not ``missing`` is left alone**, even when the census found a
market for it.  Stated positively on purpose: an earlier version refused only
``live`` and therefore overwrote **``settled``** — a real status carrying a
``terminal_result`` this pass does not hold and would have silently dropped,
which is how a decided fixture starts quoting again.  More generally, a block
that already says something was written against evidence this run cannot see,
and silently repointing a priced fixture at a different market is how a page
starts showing a real number from the wrong match.  Re-pinning is a deliberate
act with ``--repin``, and it prints every change it makes.

The result is validated with the register's own validator before it is written.
A register that fails its gate is never saved — a half-applied register is worse
than the gap it was fixing, because the gap was at least honest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.tournament_register import (  # noqa: E402
    us_open_2026_contract,
    validate_register,
)


def apply_census(
    register: dict[str, Any], census: dict[str, Any], *, repin: bool
) -> dict[str, Any]:
    """Fill `missing` kalshi match blocks from the census.  Returns a summary."""
    by_key = {m.get("matchup_key"): m for m in register.get("matchups") or []}
    stats = {
        "pinned": 0,
        # Split apart by CERT-529: `already_pinned` is a block that legitimately
        # already names a live market; `not_missing` is anything else the pass
        # refuses to touch — `settled` above all, whose `terminal_result` this
        # pass does not hold and would have dropped.
        "already_pinned": 0,
        "not_missing": 0,
        "repinned": 0,
        "no_such_fixture": 0,
        "no_kalshi_block": 0,
    }
    changes: list[str] = []

    for match in census.get("matches") or []:
        fixture = by_key.get(match.get("matchup_key"))
        if fixture is None:
            stats["no_such_fixture"] += 1
            continue

        blocks = fixture.get("sources")
        if not isinstance(blocks, list):
            stats["no_kalshi_block"] += 1
            continue
        block = next(
            (b for b in blocks
             if isinstance(b, dict) and b.get("source") == "kalshi"
             and b.get("kind") == "match"),
            None,
        )
        if block is None:
            stats["no_kalshi_block"] += 1
            continue
        # ═══ FILL ONLY WHAT IS `missing` (CERT-529) ═══
        #
        # The first version refused only `live` and therefore OVERWROTE anything
        # else — including **`settled`**, which is a real status carrying a
        # `terminal_result` this pass does not have and would silently drop. A
        # settled block is a finished match's banked answer; repointing it at a
        # live market is how a decided fixture starts quoting again.
        #
        # So the rule is stated positively: fill `missing`, leave everything
        # else, and let `--repin` be the one deliberate way to move a block that
        # already says something.
        status = block.get("status")
        if status != "missing" and not repin:
            stats["already_pinned" if status == "live" else "not_missing"] += 1
            continue
        was_pinned = status != "missing"

        sides = match["sides"]
        first = fixture["players"][0]
        block["market_id"] = match["market_id"]
        block["market_external_id"] = match["market_external_id"]
        # The block-level `outcome_id` is the FIRST-named player's, matching the
        # convention the polymarket pass writes; `sides` is the load-bearing map
        # and the only thing the slate reads to name a side.
        block["outcome_id"] = sides[first]["outcome_id"]
        block["status"] = "live"
        block["terminal_result"] = None
        block["sides"] = {
            key: {
                "outcome_id": side["outcome_id"],
                "outcome_external_id": side["outcome_external_id"],
                "source_label": side["source_label"],
            }
            for key, side in sides.items()
        }
        block["evidence"] = {
            "kind": "kalshi-match-market-census",
            "observed_at": match["observed_at"],
            "market_name": match["market_name"],
            "db_status": match["db_status"],
            # The source's OWN labels, so the sides mapping stays checkable
            # later without re-deriving it from a title parse.
            "source_labels": [side["source_label"] for side in sides.values()],
            "note": (
                "pinned after the draw ingest, which recorded this source as "
                "missing because no match market existed at ceremony time"
            ),
        }
        stats["repinned" if was_pinned else "pinned"] += 1
        changes.append(f"  {match['matchup_key']} -> {match['market_external_id']}")

    return {"stats": stats, "changes": changes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", required=True)
    parser.add_argument("--census", required=True)
    parser.add_argument("--out", help="defaults to writing the register in place")
    parser.add_argument(
        "--repin", action="store_true",
        help="also repoint blocks that are ALREADY live (prints every change)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    register_path = Path(args.register)
    register = json.loads(register_path.read_text())
    census = json.loads(Path(args.census).read_text())

    result = apply_census(register, census, repin=args.repin)
    for line in result["changes"]:
        print(line)
    print(json.dumps(result["stats"], indent=1))

    findings = validate_register(register, us_open_2026_contract())
    if findings:
        counts: dict[str, int] = {}
        for finding in findings:
            name = finding if isinstance(finding, str) else str(finding)
            counts[name] = counts.get(name, 0) + 1
        print("REFUSING TO WRITE — the register does not pass its own validator:")
        for name, count in sorted(counts.items()):
            print(f"  {name}: {count}")
        return 1
    print("register validates clean")

    if args.dry_run:
        print("dry run — nothing written")
        return 0

    out = Path(args.out) if args.out else register_path
    out.write_text(json.dumps(register, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
