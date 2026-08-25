#!/usr/bin/env python3
"""Generate a tournament register from an identity census (UX-P130).

The register is **agent-maintained** by charter: no runtime fuzzy matching, ever.
This script is how the agent maintains it reproducibly — it turns a census of
per-source market identities into a validated ``tournament-register/v1`` file,
and refuses to write one that does not validate.

Input is one JSON file per outright field, in the shape
``/api/admin/db-query`` returns (``{"columns": [...], "rows": [[...]]}``).  The
exact SQL, so a later lane can reproduce the input without archaeology:

    SELECT fm.id   AS market_id,
           fm.external_id AS market_ext,
           fm.source,
           fo.id   AS outcome_id,
           fo.external_id AS outcome_ext,
           fo.name,
           fo.current_probability,
           fo.opening_probability
      FROM futures_markets fm
      JOIN futures_outcomes fo ON fo.market_id = fm.id
     WHERE fm.external_id = '<KXATP-26USO|KXWTA-26USO|139236|139255>'
     ORDER BY fo.current_probability DESC NULLS LAST;

Freshness is a **separate** input (``--freshness``) because
``futures_outcomes.last_updated`` cannot supply it — the 2026-08-24 census
measured the Polymarket men's field reading ``2026-07-21`` on every outcome
while its snapshots ran to ``2026-08-10``.  ``price_observed_at`` comes from:

    SELECT MAX(captured_at) FROM futures_odds_snapshots
     WHERE outcome_id IN (SELECT fo.id FROM futures_outcomes fo
                            JOIN futures_markets fm ON fm.id = fo.market_id
                           WHERE fm.external_id = '<...>');

Usage:
    python3 scripts/generate_tournament_register.py \
        --tournament us-open --season 2026 \
        --field mens-singles=kalshi:/tmp/uso/KXATP-26USO.json \
        --field mens-singles=polymarket:/tmp/uso/139236.json \
        --field womens-singles=kalshi:/tmp/uso/KXWTA-26USO.json \
        --field womens-singles=polymarket:/tmp/uso/139255.json \
        --freshness /tmp/uso/freshness.json \
        --observed-at 2026-08-25T00:50:00+00:00 \
        --out backend/data/tournament_registers/us-open-2026.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.tournament_register import (  # noqa: E402
    DRAWS,
    SCHEMA_VERSION,
    build_contract,
    classify,
    is_non_player,
    normalize_player_name,
    validate_register,
)


def slugify(name: str) -> str:
    """``Felix Auger-Aliassime`` -> ``felix-auger-aliassime``.

    The slug is the register's ``entity_key`` and therefore the page's identity
    for a player.  It is derived once, here, and then *pinned* — a later source
    rename never re-derives it, because the whole point of a register is that
    identity survives the source changing its mind about spelling.
    """
    ascii_name = (
        name.replace("’", "'")
        .replace("é", "e").replace("è", "e").replace("ê", "e")
        .replace("í", "i").replace("ï", "i")
        .replace("ó", "o").replace("ö", "o")
        .replace("ú", "u").replace("ü", "u")
        .replace("á", "a").replace("à", "a").replace("ä", "a")
        .replace("č", "c").replace("š", "s").replace("ž", "z")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug


def read_query_dump(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    columns = payload["columns"]
    return [dict(zip(columns, row)) for row in payload["rows"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument(
        "--field", action="append", required=True,
        help="<draw>=<source>:<path-to-query-dump>",
    )
    parser.add_argument("--freshness", help="JSON: {'<source>:<market_ext>': '<iso ts>'}")
    parser.add_argument("--observed-at", required=True, help="ISO timestamp of the census")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    freshness = json.loads(Path(args.freshness).read_text()) if args.freshness else {}

    # entity_key -> player entry.  Keyed on the space-insensitive normalized
    # name so Kalshi's "Felix Auger-Aliassime" and Polymarket's "Felix Auger
    # Aliassime" land on ONE player instead of two board rows.
    players: dict[tuple, dict] = {}
    skipped_non_players: list[str] = []

    for spec in args.field:
        draw, rest = spec.split("=", 1)
        source, path = rest.split(":", 1)
        if draw not in DRAWS:
            parser.error(f"unknown draw {draw!r}")

        for row in read_query_dump(Path(path)):
            name = row["name"]
            # An aggregate bucket is not a player.  The measured case: both
            # Polymarket fields carry "Other" pinned at 1.000 since 2026-05-12,
            # which sorts FIRST on a probability-ordered board.  Excluding it
            # here is why it cannot render.
            if is_non_player(name):
                skipped_non_players.append(f"{source}/{draw}/{name}")
                continue

            key = (draw, normalize_player_name(name))
            player = players.get(key)
            if player is None:
                player = {
                    "entity_key": slugify(name),
                    "display_name": name,
                    "draw": draw,
                    # Seeds are published with the draw; both stay empty until
                    # then, and the validator rejects a slot written early.
                    "seed": None,
                    "country": None,
                    "draw_slot": None,
                    "section": None,
                    "sources": [],
                }
                players[key] = player

            market_ext = str(row["market_ext"])
            player["sources"].append({
                "source": source,
                "market_id": row["market_id"],
                "outcome_id": row["outcome_id"],
                "market_external_id": market_ext,
                "outcome_external_id": row.get("outcome_ext"),
                "source_name": name,
                "status": "live",
                "terminal_result": None,
                "price_observed_at": freshness.get(f"{source}:{market_ext}"),
                "evidence": {
                    "kind": "outright-field-census",
                    "observed_at": args.observed_at,
                    "market_external_id": market_ext,
                },
            })

    register = {
        "schema_version": SCHEMA_VERSION,
        "tournament": args.tournament,
        "season": args.season,
        "version": args.version,
        "generated_at": args.observed_at,
        # The draw ceremony has not happened.  Every draw_slot stays null and
        # the validator enforces it until this latches true.
        "draw_released": False,
        "players": sorted(players.values(), key=lambda p: (p["draw"], p["entity_key"])),
        # Filled when the daily slate ships; a matchup may only name players the
        # register already carries.
        "matchups": [],
    }

    contract = build_contract({args.tournament: {"season": args.season, "entity_kind": "player"}})
    findings = validate_register(register, contract)
    verdict = classify(findings)

    print(f"players:  {len(register['players'])}")
    for draw in DRAWS:
        n = sum(1 for p in register["players"] if p["draw"] == draw)
        two = sum(1 for p in register["players"] if p["draw"] == draw and len(p["sources"]) == 2)
        print(f"  {draw}: {n} players, {two} with both sources, {n - two} single-source")
    print(f"skipped non-player buckets: {len(skipped_non_players)} {skipped_non_players}")
    print(f"findings: {findings or 'none'}")
    print(f"verdict:  {verdict}")

    if verdict["classification"] == "invalid":
        print("REFUSING TO WRITE — register does not validate.", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(register, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
