#!/usr/bin/env python3
"""Ingest a released draw into the register and latch `draw_released` (UX-P134).

**This is Thursday's script, rehearsed on Tuesday.** The US Open draw ceremony
is ~08-27/28 and the page ships Sunday 08-30, so the draw has to go in and be
correct inside one session — which is not the day to discover that the ingest
needs writing. The charter amendment says it plainly: blockers block items,
never lanes, so the ingest path is built and proven against a synthetic 128-slot
draw NOW, and Thursday is `--draw the-real-file.json` and nothing else.

What it does, in the order the contract demands:

1. Reads the committed register (the current version) and a draw file.
2. Maps each drawn name onto a REGISTERED identity, using the same
   space-dropping normalizer that merged `Felix Auger-Aliassime`. A drawn name
   that matches no registered player is REFUSED, never invented — the register
   is the page's truth and the ceremony does not get to add rows to it silently.
3. Writes `draw_slot` on each matched player, and latches `draw_released: true`.
4. Validates the result as a TRANSITION, not merely as a register: one version
   newer, same scope, linked back, and the latch never un-latching.
5. Refuses to write anything unless that transition is clean.

The `draw_released` latch is what makes step 3 safe. `draw_slot` is rejected by
`validate_player` while `draw_released` is false — "before the ceremony there is
no draw, so a slot is a guess wearing the authority of a fact" — so the slots
and the latch have to land in the SAME version. This script is the only thing
that writes both, together, which is why it exists rather than being two edits.

Usage:
    python3 scripts/ingest_tournament_draw.py \\
        --register data/tournament_registers/us-open-2026.json \\
        --draw data/tournament_registers/_synthetic-usopen-draw.json \\
        --version 4 --supersedes-version 3

    # Thursday, for real, add --out to keep the committed file untouched first:
    #   ... --draw /tmp/usopen-draw-2026.json --out /tmp/proposed-v4.json
    # inspect, then re-run without --out.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.tournament_register import (  # noqa: E402
    DRAWS,
    classify,
    normalize_player_name,
    us_open_2026_contract,
    validate_register,
    validate_transition,
)

#: A main draw is 128 slots per side. Anything else is a draw file we do not
#: understand, and half a bracket is worse than none — `buildBracket` refuses a
#: non-power-of-two rather than truncating, so a short file would render an
#: empty tab with no explanation.
MAIN_DRAW_SIZE = 128


def load_draw(path: Path) -> dict[str, list[dict]]:
    """Read a draw file: ``{"mens-singles": [{slot, name, seed}, ...], ...}``."""
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: draw file must be an object keyed by draw")
    unknown = set(data) - set(DRAWS)
    if unknown:
        raise SystemExit(f"{path}: unknown draws {sorted(unknown)}; expected {sorted(DRAWS)}")
    return data


def ingest(register: dict, draw_data: dict[str, list[dict]]) -> tuple[dict, list[str]]:
    """Return (proposed_register, refusals). Never mutates the input."""
    proposed = json.loads(json.dumps(register))
    refusals: list[str] = []

    # Index registered players by (draw, normalized name). Keyed BY DRAW on
    # purpose: Qinwen Zheng is registered in both the contender and qualifying
    # sets, and a tournament-wide name index would put a women's-draw slot on
    # whichever entry it happened to hit first.
    index: dict[tuple[str, str], dict] = {}
    for player in proposed.get("players", []):
        if not isinstance(player, dict):
            continue
        key = (player.get("draw"), normalize_player_name(player.get("display_name")))
        # First registration wins; a duplicate is reported, not silently merged.
        index.setdefault(key, player)

    for draw_name, slots in draw_data.items():
        if len(slots) != MAIN_DRAW_SIZE:
            refusals.append(
                f"{draw_name}: {len(slots)} slots, expected {MAIN_DRAW_SIZE} — "
                "a partial draw renders an empty bracket, so it is refused whole"
            )
            continue

        seen_slots: set[int] = set()
        for entry in slots:
            slot = entry.get("slot")
            name = entry.get("name")
            if not isinstance(slot, int) or not 1 <= slot <= MAIN_DRAW_SIZE:
                refusals.append(f"{draw_name}: bad slot {slot!r} for {name!r}")
                continue
            if slot in seen_slots:
                refusals.append(f"{draw_name}: slot {slot} appears twice")
                continue
            seen_slots.add(slot)

            player = index.get((draw_name, normalize_player_name(name)))
            if player is None:
                # THE refusal that matters. A drawn player we do not have a
                # registered identity for cannot be added here: we would have a
                # name and no market, so the bracket would show a person the
                # rest of the page cannot price or link. It goes on the report
                # for a register regeneration pass, which is a decision.
                refusals.append(f"{draw_name}: {name!r} drawn but NOT REGISTERED")
                continue
            player["draw_slot"] = slot
            if entry.get("seed") is not None:
                player["seed"] = entry["seed"]

    # The latch, set with the slots and never separately — `draw_slot` is
    # invalid while this is false, so the two are one atomic change.
    proposed["draw_released"] = True
    return proposed, refusals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", required=True)
    parser.add_argument("--draw", required=True)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--supersedes-version", type=int, required=True)
    parser.add_argument("--out", help="defaults to --register (in place)")
    parser.add_argument(
        "--allow-unregistered",
        action="store_true",
        help="proceed despite drawn-but-unregistered players (they get no slot)",
    )
    args = parser.parse_args()

    register = json.loads(Path(args.register).read_text())
    draw_data = load_draw(Path(args.draw))

    proposed, refusals = ingest(register, draw_data)
    proposed["version"] = args.version
    proposed["supersedes_version"] = args.supersedes_version

    slotted = sum(
        1 for p in proposed.get("players", [])
        if isinstance(p, dict) and p.get("draw_slot") is not None
    )
    print(f"draw_released: {register.get('draw_released')} -> {proposed['draw_released']}")
    print(f"players with a draw slot: {slotted}")
    for draw_name in sorted(draw_data):
        n = sum(
            1 for p in proposed.get("players", [])
            if isinstance(p, dict) and p.get("draw") == draw_name and p.get("draw_slot") is not None
        )
        print(f"  {draw_name}: {n}/{MAIN_DRAW_SIZE}")

    if refusals:
        print(f"\nREFUSALS ({len(refusals)}):", file=sys.stderr)
        for line in refusals[:40]:
            print(f"  {line}", file=sys.stderr)
        if len(refusals) > 40:
            print(f"  ... and {len(refusals) - 40} more", file=sys.stderr)
        if not args.allow_unregistered:
            print(
                "\nREFUSING TO WRITE. Every refusal is a bracket slot that would "
                "render a player the rest of the page cannot price. Fix the "
                "register (regeneration pass) or re-run with --allow-unregistered "
                "to ship the draw with those slots empty.",
                file=sys.stderr,
            )
            return 1

    contract = us_open_2026_contract()
    findings = validate_register(proposed, contract)
    transition = validate_transition(register, proposed, contract)
    verdict = classify(findings)

    print(f"\nfindings:   {findings or 'none'}")
    print(f"transition: {transition or 'clean'}")
    print(f"verdict:    {verdict}")

    if findings or transition:
        print("\nREFUSING TO WRITE — the proposed version is not a clean transition.", file=sys.stderr)
        return 1

    out = Path(args.out or args.register)
    out.write_text(json.dumps(proposed, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
