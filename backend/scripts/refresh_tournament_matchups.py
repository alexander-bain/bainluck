#!/usr/bin/env python3
"""Refresh a committed register's MATCHUPS in place (UX-P139).

Why an in-place refresher rather than another run of
``generate_tournament_register.py``: that script builds a register from
scratch, and the file it would overwrite now carries three collections it
knows nothing about — ``props`` (UX-P132/134/135), ``broadcasts`` (UX-P132) and
``reaches`` (UX-P139).  Rebuilding would silently drop all three.

WHAT THIS EXISTS TO PREVENT.  ``generated_at`` is not decoration: it is the
register's claim about *when its contents were true*, and the whole slate
pipeline reads it that way — ``build_slate`` drops any matchup that started
before ``now`` minus the grace window, precisely so a committed file cannot
present this morning's matches at midnight.  Bumping ``generated_at`` for a
props or reaches pass, while leaving yesterday's matchups in place, produces a
register that is internally inconsistent in the one direction that matters: it
claims to be current and its slate is empty.  Discovered by
``test_the_committed_register_produces_a_real_slate``, which is exactly the
guard that assertion is for.

So the rule this script enforces is: **any pass that moves ``generated_at``
forward must move the matchups with it.**  Everything else in the register is
carried through untouched, and the result is re-validated before it is written.

Input is the census ``fetch_usopen_match_census.py`` produces.

Usage:
    python3 scripts/refresh_tournament_matchups.py \\
        --register data/tournament_registers/us-open-2026.json \\
        --census /tmp/uso/match-census.json \\
        --observed-at 2026-08-27T00:15:00+00:00 \\
        --version 6 --supersedes-version 5
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.tournament_register import (  # noqa: E402
    classify,
    normalize_player_name,
    us_open_2026_contract,
    validate_register,
)

# The matchup pass itself is imported rather than reimplemented: two scripts
# minting matchup keys or sides maps by two rules is how one match becomes two
# slate rows.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_tournament_register import apply_match_pass  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", required=True)
    parser.add_argument("--census", required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--supersedes-version", type=int, required=True)
    parser.add_argument("--excluded", help="JSON list of polymarket_event_ids to drop")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    register_path = Path(args.register)
    register: dict[str, Any] = json.loads(register_path.read_text())
    census = json.loads(Path(args.census).read_text())
    now = datetime.fromisoformat(args.observed_at.replace("Z", "+00:00"))

    excluded_ids = set(
        json.loads(Path(args.excluded).read_text()) if args.excluded else []
    )

    # Keyed exactly as the outright pass keys them, so a qualifier who is also a
    # contender MERGES onto the existing entry and keeps `role: contender`
    # rather than being re-registered as a rootless participant.
    players: dict[tuple, dict[str, Any]] = {
        (p["draw"], normalize_player_name(p.get("display_name"))): p
        for p in register.get("players", [])
        if isinstance(p, dict) and p.get("draw")
    }
    before_players = len(players)

    matchups, dropped, new_participants = apply_match_pass(
        players,
        census,
        now=now,
        excluded_ids=excluded_ids,
        observed_at=args.observed_at,
    )

    register["players"] = list(players.values())
    register["matchups"] = matchups
    register["version"] = args.version
    register["supersedes_version"] = args.supersedes_version
    register["generated_at"] = args.observed_at
    register["matchups_observed_at"] = args.observed_at

    findings = validate_register(register, us_open_2026_contract())
    verdict = classify(findings)

    print(f"matchups      : {len(matchups)} (was {len(json.loads(register_path.read_text()).get('matchups', []))})")
    print(f"players       : {len(register['players'])} (was {before_players}, +{new_participants} participants)")
    print(f"dropped       : {dropped}")
    print(f"carried       : reaches={len(register.get('reaches') or [])} "
          f"props={len(register.get('props') or [])} "
          f"broadcasts={len(register.get('broadcasts') or [])}")
    print(f"findings      : {findings or 'none'}")
    print(f"verdict       : {verdict}")

    if findings:
        print("REFUSING to write — register does not validate.", file=sys.stderr)
        return 1
    if not matchups:
        # An empty slate may be true (no play today) but it is never something
        # to write without saying so out loud. gotcha #53.
        print("WARNING: zero matchups survived the census — the slate will be empty.")

    if args.dry_run:
        print("dry run — not written")
        return 0

    register_path.write_text(json.dumps(register, indent=1) + "\n")
    print(f"wrote {register_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
