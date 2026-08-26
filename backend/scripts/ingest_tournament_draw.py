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
   that matches no registered player is REFUSED by default, never invented — the
   register is the page's truth and the ceremony does not get to add rows to it
   silently. `--register-from-draw` is the one sanctioned exception; see below.
3. Writes `draw_slot` on each matched player, and latches `draw_released: true`.
4. Validates the result as a TRANSITION, not merely as a register: one version
   newer, same scope, linked back, and the latch never un-latching.
5. Refuses to write anything unless that transition is clean.

**THE REGISTRATION GAP, AND WHY `--register-from-draw` EXISTS (UX-P135).**
The Tuesday rehearsal found Thursday's blocker: the register holds 96 men and
115 women against 128 slots a side, so the real ingest would have REFUSED on
45 names and written nothing. That gap is not a bug in the register — it is
what a register built from *markets* looks like before the draw. Nobody quotes
a qualifier who has not qualified yet, so those players have no market, and no
regeneration pass over market data can conjure them. The field is only fully
known AT the ceremony, from the ceremony.

The three options were: refuse (no bracket on the marquee weekend),
`--allow-unregistered` (a bracket with 45 blank slots), or let the draw
register the players it names. The third is chosen and is the honest one,
because it turns on WHICH authority is being trusted for WHAT. The draw sheet
is *definitive* about membership — it is the document that decides who is in
the tournament — and says nothing at all about price. So an admitted player is
written with a `draw-ceremony` provenance block, `role: participant`, and
**`sources: []`**: a name and a slot, no market, and therefore no number
anywhere on the page. `board_players` takes only priced contenders, so an
admitted player cannot reach a championship board; `build_bracket` prints the
name with `probability: None`.

That is strictly more honest than the alternative it replaces. A blank slot
says "we do not know who is here" when we do know — it is printed on the draw
sheet. The old refusal comment worried about "a player the rest of the page
cannot price", which is real, and the answer is to not price them, not to
un-name them.

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

    # THURSDAY, FOR REAL — one line, proven end to end 2026-08-26:
    #   python3 scripts/ingest_tournament_draw.py \\
    #       --register data/tournament_registers/us-open-2026.json \\
    #       --draw /tmp/usopen-draw-2026.json \\
    #       --version 5 --supersedes-version 4 --register-from-draw \\
    #       --out /tmp/proposed-v5.json
    # inspect the ADMITTED list, then re-run without --out to write in place.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

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


def _entity_key_from_name(name: str) -> str:
    """`Learner Tien` -> `learner-tien`. The register's own slug shape."""
    slug = "".join(c.lower() if c.isalnum() else "-" for c in name)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def admit_from_draw(
    draw_name: str, name: str, slot: int, seed: Any, existing_keys: set[str]
) -> dict:
    """A player the draw names and the markets do not — identity only.

    `sources: []` is the load-bearing part, not an omission. It is what makes
    this admission safe: the player has a name and a slot because the draw
    sheet is definitive about both, and no market, so no number can attach to
    them anywhere. `role: participant` keeps them off the championship boards,
    which rank contenders by a price they do not have.
    """
    key = _entity_key_from_name(name)
    # Collisions are possible across draws (Qinwen Zheng is registered twice),
    # so the key is disambiguated rather than allowed to overwrite.
    if key in existing_keys:
        key = f"{key}-{draw_name}"
    return {
        "entity_key": key,
        "display_name": name,
        "draw": draw_name,
        "role": "participant",
        "seed": seed if isinstance(seed, int) and not isinstance(seed, bool) else None,
        "country": None,
        "draw_slot": slot,
        "section": None,
        "sources": [],
        "evidence": {
            "kind": "draw-ceremony",
            "note": "named by the released draw; no market, so no price renders",
        },
    }


def ingest(
    register: dict,
    draw_data: dict[str, list[dict]],
    *,
    register_from_draw: bool = False,
) -> tuple[dict, list[str], list[str]]:
    """Return (proposed_register, refusals, admitted). Never mutates the input."""
    proposed = json.loads(json.dumps(register))
    refusals: list[str] = []
    admitted: list[str] = []

    # Index registered players by (draw, normalized name). Keyed BY DRAW on
    # purpose: Qinwen Zheng is registered in both the contender and qualifying
    # sets, and a tournament-wide name index would put a women's-draw slot on
    # whichever entry it happened to hit first.
    index: dict[tuple[str, str], dict] = {}
    existing_keys: set[str] = set()
    for player in proposed.get("players", []):
        if not isinstance(player, dict):
            continue
        key = (player.get("draw"), normalize_player_name(player.get("display_name")))
        # First registration wins; a duplicate is reported, not silently merged.
        index.setdefault(key, player)
        if player.get("entity_key"):
            existing_keys.add(str(player["entity_key"]))

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
                if not register_from_draw:
                    # The default refusal. A drawn player we have no registered
                    # identity for is not silently added: without the explicit
                    # flag, the operator has not decided that the draw sheet may
                    # write rows, and this script does not decide it for them.
                    refusals.append(f"{draw_name}: {name!r} drawn but NOT REGISTERED")
                    continue
                if not isinstance(name, str) or not name.strip():
                    refusals.append(f"{draw_name}: slot {slot} has no usable name")
                    continue
                player = admit_from_draw(
                    draw_name, name.strip(), slot, entry.get("seed"), existing_keys
                )
                existing_keys.add(player["entity_key"])
                proposed.setdefault("players", []).append(player)
                index[(draw_name, normalize_player_name(name))] = player
                admitted.append(f"{draw_name}: {name} (slot {slot})")
                continue
            player["draw_slot"] = slot
            if entry.get("seed") is not None:
                player["seed"] = entry["seed"]

    # The latch, set with the slots and never separately — `draw_slot` is
    # invalid while this is false, so the two are one atomic change.
    proposed["draw_released"] = True
    return proposed, refusals, admitted


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
    parser.add_argument(
        "--register-from-draw",
        action="store_true",
        help="admit drawn-but-unregistered players as identity-only participants "
        "(name + slot, sources: [], so no number can render for them). This is "
        "Thursday's flag: the register is built from markets and a qualifier who "
        "has not qualified has no market.",
    )
    args = parser.parse_args()

    register = json.loads(Path(args.register).read_text())
    draw_data = load_draw(Path(args.draw))

    proposed, refusals, admitted = ingest(
        register, draw_data, register_from_draw=args.register_from_draw
    )
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

    if admitted:
        # Loud, itemised, and never a summary count alone: these are rows the
        # ceremony wrote into the register, and a reader must be able to see
        # exactly which without re-deriving them.
        print(f"\nADMITTED FROM THE DRAW ({len(admitted)}) — name + slot, no market, no price:")
        for line in admitted:
            print(f"  {line}")

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
