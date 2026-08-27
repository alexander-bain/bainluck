#!/usr/bin/env python3
"""Populate the register's per-player per-round REACH cells (UX-P139).

Alex's amendment to ruling 3: "The register carries per-player per-round market
IDs from BOTH sources; the grid reads only the register; wrong-future placement
(a reach-QF market feeding the SF cell) is a named eval failure."

This is the pass that writes those IDs down.  It is deliberately the *only* way
a reach cell can come to exist: the grid has no discovery path, so a market this
script does not pin cannot render, and a cell this script does not write renders
as an alarm rather than as a blank.

═══ THE CENSUS THIS SCRIPT ENCODES (measured 2026-08-26) ═══

**Polymarket** publishes eight ladder events for the 2026 US Open:

    910150  To Reach Round of 16   (Men's Singles)     44 markets
    910151  To Reach Quarterfinals (Men's Singles)     44
    910171  To Reach Semifinals    (Men's Singles)     44
    910152  To Reach the Final     (Men's Singles)     44
    910153  To Reach Round of 16   (Women's Singles)   40
    910223  To Reach Quarterfinals (Women's Singles)   40
    910232  To Reach Semifinals    (Women's Singles)   40
    910235  To Reach the Final     (Women's Singles)   40

336 markets over 84 players, and every one of those players carries all four
rounds — verified against Gamma directly, so the 44/40 is Polymarket's own
inventory and not a shortfall in our ingest.

**Kalshi publishes none.**  Its entire US Open inventory is five markets: the
two outright winner fields, ``KXATPCOMPETE-26USOALC`` / ``-SIN``, and
``KXUSOPENPRICE-26AUGOPENAVG``.  There is no round-advancement series to link,
which is why every cell written here carries an explicit ``missing`` Kalshi
block with an evidence timestamp.  That block is the difference between "we
looked and there is nothing" and "nobody looked", and the grid renders those two
states differently on purpose.

═══ WHAT THIS SCRIPT REFUSES TO DO ═══

1. **Guess the round from the ticker.**  The round comes from parsing the
   market's own question text with a closed regex, and the parsed round, draw
   and subject are all WRITTEN INTO the block as ``question_round`` /
   ``question_draw`` / ``question_subject``.  ``validate_reach`` then asserts
   they agree with the cell.  A parse that drifts produces a register that will
   not validate, instead of a plausible number in the wrong column.
2. **Attach a market to a player by proximity.**  The subject must normalize to
   exactly one registered player in that draw or the market is SKIPPED and
   listed in the report.  A curated market on the wrong player is worse than one
   on nobody, because it renders as a confident answer.
3. **Invent a cell.**  A (player, round) with no market at either source is
   written with two ``missing`` blocks, never omitted — omission is what makes a
   grid look complete when it is not.
4. **Write a register that does not validate.**  Same refusal as the other two
   generators.

Input is one ``/api/admin/db-query`` dump in that endpoint's own shape:

    SELECT fm.id AS market_id, fm.external_id AS market_ext, fm.source,
           fm.name AS market_name, fm.status,
           fm.market_metadata->>'polymarket_event_id' AS ev,
           fo.id AS outcome_id, fo.external_id AS outcome_ext,
           fo.name AS outcome_name, fo.current_probability
      FROM futures_markets fm
      JOIN futures_outcomes fo ON fo.market_id = fm.id
     WHERE fm.name ILIKE '%advance to the%'
       AND fm.name ILIKE '%2026 US Open%'
     ORDER BY fm.id, fo.id;

plus an optional freshness dump (``outcome_id``, ``max(captured_at)``), because
``futures_outcomes.last_updated`` is not a freshness signal on this platform and
``price_observed_at`` must come from ``futures_odds_snapshots.captured_at``.

Usage:
    python3 scripts/populate_tournament_reaches.py \\
        --register data/tournament_registers/us-open-2026.json \\
        --dump /tmp/uso/advance-raw.json \\
        --freshness /tmp/uso/advance-fresh.json \\
        --observed-at 2026-08-26T23:45:00+00:00 \\
        --version 5 --supersedes-version 4
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.tournament_register import (  # noqa: E402
    ALLOWED_SOURCES,
    classify,
    normalize_player_name,
    player_role,
    us_open_2026_contract,
    validate_register,
)

#: The question shape Polymarket writes, and the ONLY one this script reads.
#:
#: A closed regex rather than a token search: "advance to the Final" and
#: "advance to the Semifinals" differ by one word, and a loose matcher that
#: found "Final" inside "Semifinals" would populate the F column from SF
#: markets across the whole draw — the wrong-future defect at scale. Anchored at
#: both ends so a market whose wording changes fails to parse (and is reported)
#: rather than matching partially.
QUESTION = re.compile(
    r"^Will (?P<subject>.+?) advance to the "
    r"(?P<round>Round of 16|Quarterfinals|Semifinals|Final) in "
    r"(?P<draw>Men's|Women's) Singles at the (?P<season>\d{4}) US Open\?$"
)

ROUND_FROM_QUESTION: dict[str, str] = {
    "Round of 16": "R16",
    "Quarterfinals": "QF",
    "Semifinals": "SF",
    "Final": "F",
}

DRAW_FROM_QUESTION: dict[str, str] = {
    "Men's": "mens-singles",
    "Women's": "womens-singles",
}

#: The binary's YES side is the answer to "does this player reach round R".
#: The NO side is the same question negated and is never the cell's number;
#: pinning it would print the complement in the confident type.
ANSWER_OUTCOME = "yes"

#: Sources censused for round-advancement futures. Both are written to every
#: cell — the one that carries the market as a pinned identity, the one that
#: does not as an explicit `missing` with its own evidence timestamp.
CENSUSED_SOURCES = ("polymarket", "kalshi")

#: Why Kalshi is `missing` on every cell, in the words the register carries.
#: Written down rather than left implicit so the next pass re-checks the claim
#: instead of inheriting it.
KALSHI_ABSENCE = (
    "Kalshi publishes no round-advancement series for this tournament — its "
    "entire US Open inventory is the two outright winner fields, two "
    "to-play markets and a ticket-price market (censused 2026-08-26)"
)


def fold(name: str) -> str:
    """NFD-fold then normalize — `Auger-Aliassime` and `Auger Aliassime` agree."""
    return normalize_player_name(unicodedata.normalize("NFD", name or ""))


def slugify(name: str) -> str:
    """``Gael Monfils`` -> ``gael-monfils`` — the same rule the main generator uses.

    Kept identical to ``generate_tournament_register.slugify`` on purpose: two
    scripts minting entity keys by two rules is how one player ends up as two
    rows, which is the defect ``DUPLICATE_PLAYER_ACROSS_KEYS`` exists to catch.
    """
    ascii_name = unicodedata.normalize("NFKD", (name or "").replace("’", "'"))
    ascii_name = "".join(c for c in ascii_name if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def read_query_dump(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    if payload.get("truncated"):
        raise RuntimeError(f"{path} is TRUNCATED — re-run with a higher limit.")
    return [dict(zip(payload["columns"], row)) for row in payload["rows"]]


def parse_ladder(rows: list[dict[str, Any]], season: str) -> tuple[dict, list[str]]:
    """Group the dump into ``(draw, round, subject) -> yes-outcome row``.

    Returns the index and the list of market names that did not parse.  An
    unparsed market is REPORTED, never silently dropped: a wording change at
    the source is exactly the drift the register exists to surface, and a
    generator that quietly skipped it would hand back a smaller grid with no
    explanation.
    """
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    unparsed: list[str] = []
    for row in rows:
        match = QUESTION.match(str(row.get("market_name") or ""))
        if match is None:
            name = str(row.get("market_name"))
            if name not in unparsed:
                unparsed.append(name)
            continue
        if match.group("season") != season:
            continue
        if str(row.get("outcome_name") or "").strip().lower() != ANSWER_OUTCOME:
            continue
        key = (
            DRAW_FROM_QUESTION[match.group("draw")],
            ROUND_FROM_QUESTION[match.group("round")],
            fold(match.group("subject")),
        )
        index[key] = {**row, "subject": match.group("subject").strip()}
    return index, unparsed


def register_ladder_players(
    register: dict[str, Any],
    ladder: dict[tuple[str, str, str], dict[str, Any]],
    observed_at: str,
) -> list[dict[str, Any]]:
    """Register ladder subjects the file does not yet carry, as PARTICIPANTS.

    Measured 2026-08-26: 32 of the 84 ladder players are not in the register at
    all — Gael Monfils, Brandon Nakashima, Ugo Humbert, Leylah Fernandez, Venus
    Williams among them.  They are absent for a good reason (the register was
    seeded from the two outright winner fields, and none of these carries a
    title price) and leaving them absent has a bad consequence: their reach
    markets exist, are priced, and would be invisible.  On the men's side that
    is 20 of the 44 priced ladder rows silently missing from a grid whose whole
    claim is that it shows what the market prices.

    ``participant``, not ``contender``, and the distinction is load-bearing.  A
    contender's identity is an outright quote and it ranks on the championship
    board; these players have no outright quote, so registering them as
    contenders would either fail validation (``REGISTER_PLAYER_NO_SOURCES``) or
    put an unpriced row on the board.  A participant carries no player-level
    source by construction — its priceable identities live in ``matchups`` and,
    now, in ``reaches`` — which is exactly the shape these players have.
    """
    existing = {
        (p.get("draw"), fold(p.get("display_name", "")))
        for p in register.get("players", [])
        if isinstance(p, dict)
    }
    known_keys = {
        p.get("entity_key") for p in register.get("players", []) if isinstance(p, dict)
    }

    added: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for (draw, _round_name, subject_fold), row in sorted(ladder.items()):
        if (draw, subject_fold) in existing or (draw, subject_fold) in seen:
            continue
        seen.add((draw, subject_fold))
        display_name = row["subject"]
        entity_key = slugify(display_name)
        if entity_key in known_keys:
            # Two different people slugging to one key. Refuse rather than
            # overwrite: `DUPLICATE_ENTITY_KEY` would catch it a step later,
            # but the message here names the collision.
            raise RuntimeError(
                f"entity_key collision registering ladder player {display_name!r}: "
                f"{entity_key!r} already exists"
            )
        known_keys.add(entity_key)
        added.append({
            "entity_key": entity_key,
            "display_name": display_name,
            "draw": draw,
            "seed": None,
            "country": None,
            "draw_slot": None,
            "section": None,
            "sources": [],
            "role": "participant",
            "evidence": {
                "kind": "advance-ladder-census",
                "observed_at": observed_at,
                "note": "registered from the round-advancement ladder; no outright quote",
            },
        })
    return added


def build_reaches(
    register: dict[str, Any],
    ladder: dict[tuple[str, str, str], dict[str, Any]],
    freshness: dict[int, str],
    observed_at: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One cell per (griddable player, round the draw has a ladder for).

    "Griddable" is contenders (they carry the title column) PLUS any player the
    ladder itself names (they carry reach columns and no title).  Iterating
    contenders alone was the first draft and it dropped 128 priced markets on
    the floor — see ``register_ladder_players``.
    """
    ladder_folds: dict[str, set[str]] = defaultdict(set)
    for draw, _round_name, subject_fold in ladder:
        ladder_folds[draw].add(subject_fold)

    griddable: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for player in register.get("players", []):
        if not isinstance(player, dict):
            continue
        draw = player.get("draw")
        is_contender = player_role(player) == "contender"
        on_ladder = fold(player.get("display_name", "")) in ladder_folds.get(draw, set())
        if is_contender or on_ladder:
            griddable[draw].append(player)

    # Which rounds each draw's ladder covers, straight off the parsed dump.
    rounds_by_draw: dict[str, list[str]] = defaultdict(list)
    for draw, round_name, _subject in ladder:
        if round_name not in rounds_by_draw[draw]:
            rounds_by_draw[draw].append(round_name)
    for draw in rounds_by_draw:
        rounds_by_draw[draw].sort(key=["R128", "R64", "R32", "R16", "QF", "SF", "F"].index)

    reaches: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "linked": 0,
        "no_market": 0,
        "ambiguous_subject": [],
        "unmatched_markets": [],
        "rounds_by_draw": dict(rounds_by_draw),
        "griddable": {draw: len(players) for draw, players in sorted(griddable.items())},
    }

    # A ladder subject must resolve to exactly ONE registered player in its own
    # draw. Built once, per draw, so the check is a lookup and an ambiguous
    # name is a reported skip rather than an arbitrary pick.
    by_fold: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for draw, players in griddable.items():
        table: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for player in players:
            table[fold(player.get("display_name", ""))].append(player)
        by_fold[draw] = table

    matched_keys: set[tuple[str, str, str]] = set()

    for draw, players in sorted(griddable.items()):
        for round_name in rounds_by_draw.get(draw, []):
            for player in sorted(players, key=lambda p: p.get("entity_key", "")):
                subject_key = fold(player.get("display_name", ""))
                candidates = by_fold[draw].get(subject_key, [])
                if len(candidates) > 1:
                    stats["ambiguous_subject"].append(player.get("display_name"))
                    continue

                row = ladder.get((draw, round_name, subject_key))
                sources: list[dict[str, Any]] = []

                if row is not None:
                    matched_keys.add((draw, round_name, subject_key))
                    outcome_id = row.get("outcome_id")
                    sources.append({
                        "source": row.get("source"),
                        "kind": "reach",
                        "market_id": row.get("market_id"),
                        "outcome_id": outcome_id,
                        "market_external_id": row.get("market_ext"),
                        "outcome_external_id": row.get("outcome_ext"),
                        "source_name": row.get("outcome_name"),
                        # THE THREE RESTATEMENTS. `validate_reach` asserts each
                        # against the cell; a parse that drifts fails the file.
                        "question_round": round_name,
                        "question_draw": draw,
                        "question_subject": row.get("subject"),
                        "question": row.get("market_name"),
                        "status": (
                            "live" if str(row.get("status")) == "open" else "settled"
                        ),
                        "terminal_result": (
                            None if str(row.get("status")) == "open" else "eliminated"
                        ),
                        # From `futures_odds_snapshots.captured_at`, never from
                        # `futures_outcomes.last_updated` — the census measured
                        # the latter a month stale while snapshots ran current.
                        "price_observed_at": freshness.get(outcome_id),
                        "evidence": {
                            "kind": "advance-ladder-census",
                            "observed_at": observed_at,
                            "polymarket_event_id": row.get("ev"),
                        },
                    })
                    stats["linked"] += 1
                else:
                    stats["no_market"] += 1

                carried = {block["source"] for block in sources}
                for source in CENSUSED_SOURCES:
                    if source in carried or source not in ALLOWED_SOURCES:
                        continue
                    sources.append({
                        "source": source,
                        "kind": "reach",
                        "market_id": None,
                        "outcome_id": None,
                        "status": "missing",
                        "terminal_result": None,
                        "evidence": {
                            "kind": "advance-ladder-census-absent",
                            "observed_at": observed_at,
                            "note": (
                                KALSHI_ABSENCE
                                if source == "kalshi"
                                else f"{source} publishes no {round_name} "
                                f"market for this player (censused)"
                            ),
                        },
                    })

                reaches.append({
                    "draw": draw,
                    "entity_key": player.get("entity_key"),
                    "round": round_name,
                    "sources": sources,
                })

    stats["unmatched_markets"] = sorted(
        f"{d}/{r}/{s}" for (d, r, s) in ladder if (d, r, s) not in matched_keys
    )
    return reaches, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", required=True)
    parser.add_argument("--dump", required=True)
    parser.add_argument("--freshness", help="outcome_id -> max(captured_at) dump")
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--supersedes-version", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    register_path = Path(args.register)
    register = json.loads(register_path.read_text())

    ladder, unparsed = parse_ladder(
        read_query_dump(Path(args.dump)), register.get("season", "")
    )

    # The ladder names 32 players the register does not carry. They are added
    # BEFORE the cells are built, so every priced market has somewhere to land.
    added_players = register_ladder_players(register, ladder, args.observed_at)
    register["players"] = [*register.get("players", []), *added_players]

    freshness: dict[int, str] = {}
    if args.freshness:
        for row in read_query_dump(Path(args.freshness)):
            observed = row.get("last_captured") or row.get("observed_at")
            if row.get("outcome_id") is not None and observed:
                # The dump renders timestamps space-separated; ISO wants a T.
                freshness[row["outcome_id"]] = str(observed).replace(" ", "T")

    reaches, stats = build_reaches(register, ladder, freshness, args.observed_at)

    register["reaches"] = reaches
    register["reaches_observed_at"] = args.observed_at
    register["version"] = args.version
    register["supersedes_version"] = args.supersedes_version
    register["generated_at"] = args.observed_at

    findings = validate_register(register, us_open_2026_contract())
    verdict = classify(findings)

    print(f"ladder players added: {len(added_players)}")
    print(f"griddable per draw  : {stats['griddable']}")
    print(f"reach cells written : {len(reaches)}")
    print(f"  linked to a market: {stats['linked']}")
    print(f"  no market anywhere: {stats['no_market']}")
    print(f"  rounds per draw   : {stats['rounds_by_draw']}")
    if stats["ambiguous_subject"]:
        print(f"  AMBIGUOUS SUBJECTS (skipped): {stats['ambiguous_subject']}")
    if stats["unmatched_markets"]:
        print(f"  markets with no registered contender: {len(stats['unmatched_markets'])}")
        for name in stats["unmatched_markets"][:10]:
            print(f"    {name}")
    if unparsed:
        print(f"  UNPARSED QUESTIONS: {len(unparsed)}")
        for name in unparsed[:5]:
            print(f"    {name}")
    print(f"findings: {findings or 'none'}")
    print(f"verdict : {verdict}")

    if findings:
        # Same refusal as the other two generators: a register that does not
        # validate is never written. An invalid file on disk is a page-shaped
        # outage that looks like a data problem.
        print("REFUSING to write — register does not validate.", file=sys.stderr)
        return 1

    if args.dry_run:
        print("dry run — not written")
        return 0

    register_path.write_text(json.dumps(register, indent=1) + "\n")
    print(f"wrote {register_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
