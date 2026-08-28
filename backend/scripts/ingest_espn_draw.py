"""Ingest the released main draw from ESPN into the tournament register (UX-P142).

    ALEX, on his phone, 2026-08-27: "The draw exists (ceremony was today) but
    the page shows none — the bracket must render the real draw."

WHY THIS SCRIPT EXISTS ALONGSIDE ``ingest_tournament_draw.py``, which already
ingests a draw.  Because they take different inputs and make different claims,
and the difference is the whole story of ceremony day.

``ingest_tournament_draw.py`` takes a **draw sheet**: 128 numbered slots a side.
It writes ``draw_slot``, which is a positional fact — slot 1 plays slot 2, and
the winner meets the winner of 3-v-4.  That is the input the runbook was written
for and it is the right one when you have it.

**We do not have it.**  ``usopen.org``'s draw feeds are unreachable from this
sandbox (measured 2026-08-27: every request to ``www.usopen.org`` times out at
the egress layer, while ``site.api.espn.com`` answers in under a second).  What
ESPN publishes is the **fixture list** — 64 first-round competitions a side,
every one naming its two players — and it publishes them in *ingest order, not
bracket order*: the men's list opens on a qualifier slot and Alcaraz is 37th.

So this script writes what ESPN actually knows and refuses to write what it does
not:

* **Pairings — YES.**  "Roman Safiullin plays Carlos Alcaraz" is a fact, it is
  checkable against any published draw, and it is the fact a reader opens the
  page for.  They land as register ``matchups`` at the round ESPN files them in.
* **Draw slots — NO.**  Assigning ESPN's list order to slots 1..128 would look
  identical to a real draw sheet and would fabricate the entire second round.
  ``draw_slot`` stays null, ``build_bracket`` keeps returning ``[]``, and the
  fixtures reach the page through the match list — the one list ruling 4 says
  this page has.
* **Country — YES.**  ESPN carries a flag per athlete on the same record as the
  name.  100% coverage on both draws, measured; it is the register's ``country``
  field, which has been null on every row since v1.

``draw_released`` is latched here because the draw IS released, and that is a
fact about the world rather than about our slot coverage.  The latch is what
turns on the draw pill on the bracket tab and turns off the "Draw is made
Thursday 27 August" panel — both of which are now wrong on a page a reader can
see.

USAGE (dry first, always — ``--out`` writes a candidate elsewhere):

    cd backend && python3 scripts/ingest_espn_draw.py \
      --register data/tournament_registers/us-open-2026.json \
      --event-name "US Open" --version 8 --supersedes-version 7 \
      --observed-at 2026-08-27T18:00:00+00:00 \
      --out /tmp/proposed-v8.json

Then re-run without ``--out`` to write in place.  ``--payload`` reads a saved
scoreboard instead of fetching, so the whole ingest is reproducible from a file
and testable without a network.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.espn_tennis import (  # noqa: E402
    fetch_scoreboards,
    parse_draw,
)
from app.utils.tournament_register import (  # noqa: E402
    classify,
    normalize_player_name,
    us_open_2026_contract,
    validate_register,
    validate_transition,
)

DEFAULT_DRAWS = ("mens-singles", "womens-singles")

#: Rounds whose fixtures this script writes.  The MAIN DRAW, and not qualifying.
#:
#: Not an oversight and not a filter added to make a number look better.  ESPN's
#: board carries all three qualifying rounds — 112 competitions a side, all of
#: them finished before the ceremony — and ingesting them would write 224
#: matchups for matches that are over and admit ~200 players who lost in
#: qualifying and will never appear in the main draw.  Finished qualifying
#: already reaches the page through ``build_results`` (ESPN's scores, UX-P139
#: item 9) and the 28 qualifying matchups the register already carries.
#:
#: Every later round is included even though all of them are empty today: the
#: same command run on day 4 picks up the Round of 64 with no argument change,
#: because ``parse_draw`` drops a fixture with no determined player.
MAIN_DRAW_ROUNDS = ("R128", "R64", "R32", "R16", "QF", "SF", "F")


def entity_key_from_name(name: str) -> str:
    """`Learner Tien` -> `learner-tien`.  The register's own slug shape.

    Identical to ``ingest_tournament_draw._entity_key_from_name`` on purpose:
    the two scripts must mint the same key for the same person or a player
    admitted by one becomes a second row under the other.
    """
    slug = "".join(c.lower() if c.isalnum() else "-" for c in name)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _iso(value: Any) -> Optional[str]:
    """ESPN's ``2026-08-30T04:00Z`` -> a full ISO-8601 instant, or ``None``."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def matchup_key(draw: str, keys: list[str], scheduled: Optional[str]) -> str:
    """`mens-singles:alcaraz-vs-safiullin:2026-08-30` — sorted, so it is stable.

    Sorted rather than in ESPN's order because the key must not change if ESPN
    reorders the two competitors between polls; a changing key is a duplicate
    row with extra steps.
    """
    day = (scheduled or "")[:10] or "undated"
    return f"{draw}:{'-vs-'.join(sorted(keys))}:{day}"


def pair_id(draw: str, keys: list[str]) -> tuple:
    return (draw, tuple(sorted(keys)))


def admit_from_draw(draw: str, side: dict[str, Any], existing_keys: set[str]) -> dict:
    """A player the draw names and the markets do not — identity only.

    ``sources: []`` is load-bearing, not an omission: the player has a name
    because the draw is definitive about it, and no market, so no number can
    attach to them anywhere.  ``role: participant`` keeps them off the
    championship board, which ranks contenders by a price they do not have.
    """
    key = entity_key_from_name(side["name"])
    if key in existing_keys:
        # Collisions happen across draws (Qinwen Zheng is registered twice).
        key = f"{key}-{draw}"
    return {
        "entity_key": key,
        "display_name": side["name"],
        "draw": draw,
        "role": "participant",
        "seed": None,
        "country": side.get("country"),
        "draw_slot": None,
        "section": None,
        "sources": [],
        "evidence": {
            "kind": "draw-ceremony-espn",
            "espn_athlete_id": side.get("espn_athlete_id"),
            "note": "named by the released draw; no market, so no price renders",
        },
    }


def censused_absence(observed_at: str, espn_competition_id: str) -> list[dict]:
    """Both sources asked, neither carries this fixture — written down as such.

    ``validate_matchup`` requires at least one source block, and this is the
    honest one for a main-draw fixture on ceremony day: no match market exists
    for a match four days out.  An empty list would be a fixture nobody looked
    at, and the register must not let that read the same as one that was
    cleared — the same rule ``reaches`` follows for its ``no_market`` cells.
    """
    return [
        {
            "source": source,
            "kind": "match",
            "market_id": None,
            "outcome_id": None,
            "status": "missing",
            "terminal_result": None,
            "evidence": {
                "kind": "draw-fixture-census-absent",
                "observed_at": observed_at,
                "espn_competition_id": espn_competition_id,
                "note": (
                    "fixture from the released draw; no match market pinned at "
                    "this source when the draw was ingested"
                ),
            },
        }
        for source in ("kalshi", "polymarket")
    ]


def ingest(
    register: dict,
    parsed: dict[str, Any],
    *,
    observed_at: str,
    register_from_draw: bool = False,
    rounds: tuple[str, ...] = MAIN_DRAW_ROUNDS,
) -> tuple[dict, list[str], list[str], dict[str, int]]:
    """Return ``(proposed, refusals, admitted, stats)``.  Never mutates input."""
    proposed = json.loads(json.dumps(register))
    refusals: list[str] = []
    admitted: list[str] = []
    stats = {
        "fixtures": 0,
        "fixtures_out_of_scope": 0,
        "fixtures_added": 0,
        "fixtures_already_registered": 0,
        # A fixture ESPN has named ONE side of: "Qualifier v Tommy Paul". Real,
        # and not yet a pair, so it cannot be a matchup — the register's shape
        # says a matchup is two registered players and that rule is what keeps
        # a half-known row off the slate. Counted loudly rather than dropped
        # silently, and it closes itself: qualifying finishes 2026-08-28 and
        # re-running this command writes every one of them.
        "fixtures_awaiting_qualifier": 0,
        "players_admitted": 0,
        "countries_filled": 0,
        "placeholder_sides": 0,
    }

    index: dict[tuple[str, str], dict] = {}
    existing_keys: set[str] = set()
    for player in proposed.get("players", []):
        if not isinstance(player, dict):
            continue
        index.setdefault(
            (player.get("draw"), normalize_player_name(player.get("display_name"))),
            player,
        )
        if player.get("entity_key"):
            existing_keys.add(str(player["entity_key"]))

    # Existing matchups keep their pinned markets. A fixture already carried by
    # the register (the qualifying slate) is NOT rewritten as a censused
    # absence — that would drop a live price to make room for a fact we already
    # had. Keyed on the unordered pair within a draw, which is the only key the
    # two datasets share.
    existing_pairs: set[tuple] = set()
    for matchup in proposed.get("matchups", []):
        if not isinstance(matchup, dict):
            continue
        players = matchup.get("players")
        if isinstance(players, list) and len(players) == 2:
            existing_pairs.add(
                pair_id(str(matchup.get("draw")), [str(p) for p in players])
            )

    for draw, fixtures in sorted(parsed.get("draws", {}).items()):
        for fixture in fixtures:
            if fixture["round"] not in rounds:
                stats["fixtures_out_of_scope"] += 1
                continue
            stats["fixtures"] += 1
            sides = fixture["players"]
            keys: list[str] = []
            undetermined = 0

            for side in sides:
                if not side["determined"]:
                    undetermined += 1
                    continue
                player = index.get((draw, normalize_player_name(side["name"])))
                if player is None:
                    if not register_from_draw:
                        refusals.append(
                            f"{draw}: {side['name']!r} drawn but NOT REGISTERED"
                        )
                        continue
                    player = admit_from_draw(draw, side, existing_keys)
                    existing_keys.add(player["entity_key"])
                    proposed.setdefault("players", []).append(player)
                    index[(draw, normalize_player_name(side["name"]))] = player
                    admitted.append(f"{draw}: {side['name']}")
                    stats["players_admitted"] += 1
                elif player.get("country") in (None, "") and side.get("country"):
                    # ESPN's own record, alongside the name it is joined on.
                    player["country"] = side["country"]
                    stats["countries_filled"] += 1
                keys.append(str(player["entity_key"]))

            stats["placeholder_sides"] += undetermined
            if len(keys) != 2:
                # One side is a qualifier ESPN has not named yet. A one-sided
                # fixture is not a matchup — the register's own shape says a
                # matchup is a PAIR — so it is counted and skipped rather than
                # written half-formed. Both players land the moment qualifying
                # finishes and the same command is re-run.
                if undetermined:
                    stats["fixtures_awaiting_qualifier"] += 1
                continue

            if pair_id(draw, keys) in existing_pairs:
                stats["fixtures_already_registered"] += 1
                continue

            scheduled = _iso(fixture.get("scheduled_at"))
            if scheduled is None:
                refusals.append(
                    f"{draw}: fixture {fixture['espn_competition_id']} has no usable date"
                )
                continue

            proposed.setdefault("matchups", []).append(
                {
                    "matchup_key": matchup_key(draw, keys, scheduled),
                    "draw": draw,
                    "round": fixture["round"],
                    "scheduled_date": scheduled,
                    "players": keys,
                    "sources": censused_absence(
                        observed_at, fixture["espn_competition_id"]
                    ),
                    "evidence": {
                        "kind": "draw-ceremony-espn",
                        "espn_competition_id": fixture["espn_competition_id"],
                        "espn_round": fixture.get("espn_round"),
                        "observed_at": observed_at,
                    },
                }
            )
            existing_pairs.add(pair_id(draw, keys))
            stats["fixtures_added"] += 1

    # THE LATCH. Set here and nowhere else, because the draw being released is
    # the same fact as these fixtures existing.
    proposed["draw_released"] = True
    proposed["draw_observed_at"] = observed_at
    return proposed, refusals, admitted, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", required=True)
    parser.add_argument("--event-name", default="US Open")
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--supersedes-version", type=int, required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--dates", help="ESPN YYYYMMDD; omitted, today's board")
    parser.add_argument(
        "--payload",
        action="append",
        default=[],
        help="a saved scoreboard JSON to parse instead of fetching (repeatable)",
    )
    parser.add_argument("--out", help="defaults to --register (in place)")
    parser.add_argument(
        "--register-from-draw",
        action="store_true",
        help="admit drawn-but-unregistered players as identity-only participants",
    )
    parser.add_argument("--allow-refusals", action="store_true")
    args = parser.parse_args()

    if args.payload:
        payloads = [json.loads(Path(p).read_text()) for p in args.payload]
        errors: list[str] = []
    else:
        payloads, errors = fetch_scoreboards(args.dates)

    if errors:
        print(f"FETCH ERRORS: {errors}", file=sys.stderr)
    if not payloads:
        # Gotcha #53: an empty parse from a failed fetch must never read as
        # "the draw is not out yet".
        print("NO PAYLOADS — nothing was read, so nothing is known.", file=sys.stderr)
        return 1

    parsed = parse_draw(payloads, event_name=args.event_name, draws=DEFAULT_DRAWS)
    print(f"espn parse: {parsed['stats']}")
    for draw, fixtures in sorted(parsed["draws"].items()):
        by_round: dict[str, int] = {}
        for fixture in fixtures:
            by_round[fixture["round"]] = by_round.get(fixture["round"], 0) + 1
        print(f"  {draw}: {len(fixtures)} fixtures {by_round}")

    register = json.loads(Path(args.register).read_text())
    proposed, refusals, admitted, stats = ingest(
        register,
        parsed,
        observed_at=args.observed_at,
        register_from_draw=args.register_from_draw,
    )
    proposed["version"] = args.version
    proposed["supersedes_version"] = args.supersedes_version

    print(
        f"\ndraw_released: {register.get('draw_released')} -> {proposed['draw_released']}"
    )
    print(f"ingest: {stats}")
    if admitted:
        print(
            f"\nADMITTED FROM THE DRAW ({len(admitted)}) — name only, no market, no price:"
        )
        for line in admitted:
            print(f"  {line}")

    if refusals:
        print(f"\nREFUSALS ({len(refusals)}):", file=sys.stderr)
        for line in refusals[:40]:
            print(f"  {line}", file=sys.stderr)
        if len(refusals) > 40:
            print(f"  ... and {len(refusals) - 40} more", file=sys.stderr)
        if not args.allow_refusals:
            print("\nREFUSING TO WRITE.", file=sys.stderr)
            return 1

    contract = us_open_2026_contract()
    findings = validate_register(proposed, contract)
    transition = validate_transition(register, proposed, contract)
    print(f"\nfindings:   {findings or 'none'}")
    print(f"transition: {transition or 'clean'}")
    print(f"verdict:    {classify(findings)}")

    if findings or transition:
        print("\nREFUSING TO WRITE — not a clean transition.", file=sys.stderr)
        return 1

    out = Path(args.out or args.register)
    out.write_text(json.dumps(proposed, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
