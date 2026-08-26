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

from datetime import datetime, timedelta  # noqa: E402

from app.utils.tournament_register import (  # noqa: E402
    DRAWS,
    SCHEMA_VERSION,
    build_contract,
    classify,
    is_non_player,
    normalize_player_name,
    validate_register,
)

#: A match may stay on the slate this long past its scheduled start before it
#: is dropped as almost certainly finished.
#:
#: This is the belt to ``source_closed``'s braces, and it exists because the
#: source's own flag is not always prompt.  Measured 2026-08-25: our database
#: had **all 324** US Open qualification rows at ``status='open'`` with
#: ``resolution_date`` 08-31/09-02 while Gamma reported **95 of 162** matches
#: closed with real dates of 08-24/25/26.  A slate keyed on our own columns
#: would have shown 64 finished Monday matches as Sunday's card.
#:
#: Five-set men's matches run past four hours; six is a bound that does not cut
#: a live match off, and a match still on the slate seven hours after its start
#: is a defect the drift sentinel should be told about, not a row.
MATCH_STALE_AFTER_HOURS = 6.0


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


def matchup_key(draw: str, keys: list[str], scheduled: str) -> str:
    """Stable per-match key: draw, both players sorted, and the date.

    Sorted so the key does not depend on which side the source happened to name
    first, and dated so a rematch in a later round is a different row rather
    than an overwrite of the first meeting.
    """
    return f"{draw}:{'-vs-'.join(sorted(keys))}:{scheduled[:10]}"


def match_exclusion(match: dict, *, now: datetime, excluded_ids: set[str]) -> str | None:
    """Why this match must not reach the slate, or ``None`` if it may.

    Three independent gates, deliberately not collapsed into one. Each catches
    a case the others cannot see, and a match is dropped if ANY fires:

    1. ``source_closed`` — Polymarket says the match is over. Authoritative
       when present, and 95 of 162 were closed at the measured moment.
    2. ``start_time`` older than the grace window — catches the match the
       source has not flagged yet. Our own ``status`` and ``resolution_date``
       cannot do this job: every row reads ``open`` and 08-31/09-02.
    3. The explicit exclusion list — the slot for findings that are neither,
       e.g. the measurement lane's stale-open inventory (gotcha #33's Kalshi
       Cincinnati set). A file, so it can be updated without a code change.

    Returning the REASON rather than a boolean is what makes the drop
    auditable: the generator prints a census of why matches left, so "the
    slate is short today" always has an answer.
    """
    if str(match.get("polymarket_event_id")) in excluded_ids:
        return "MANUALLY_EXCLUDED"
    if match.get("source_closed"):
        return "SOURCE_CLOSED"

    start = match.get("start_time")
    if not isinstance(start, str) or not start:
        # No start time is not "starts soon". Nothing anchors it, so it cannot
        # be shown as today's match (gotcha #53).
        return "NO_START_TIME"
    try:
        started = datetime.fromisoformat(start.replace("Z", "+00:00"))
    except ValueError:
        return "UNPARSEABLE_START_TIME"
    if started < now - timedelta(hours=MATCH_STALE_AFTER_HOURS):
        return "START_TIME_PAST"
    return None


def apply_match_pass(
    players: dict[tuple, dict],
    census: dict,
    *,
    now: datetime,
    excluded_ids: set[str],
    observed_at: str,
) -> tuple[list[dict], dict[str, int], int]:
    """The SECOND population pass: participants and matchups from match markets.

    Players discovered here are keyed on exactly the same
    ``(draw, normalize_player_name(name))`` tuple the outright pass uses, so a
    qualifier who is also a contender MERGES onto the existing entry and keeps
    ``role: contender``. That reuse is the point — it is the same normalizer
    that stopped Kalshi's ``Felix Auger-Aliassime`` and Polymarket's ``Felix
    Auger Aliassime`` from becoming two board rows, and here it stops a
    contender from being re-registered as a rootless participant.
    """
    matchups: list[dict] = []
    dropped: dict[str, int] = {}
    new_participants = 0

    for match in census.get("matches", []):
        reason = match_exclusion(match, now=now, excluded_ids=excluded_ids)
        if reason is not None:
            dropped[reason] = dropped.get(reason, 0) + 1
            continue

        draw = match["draw"]
        sides = match.get("sides") or []
        if len(sides) != 2:
            dropped["NOT_TWO_SIDED"] = dropped.get("NOT_TWO_SIDED", 0) + 1
            continue

        entity_keys: list[str] = []
        for side in sides:
            name = side["player_name"]
            key = (draw, normalize_player_name(name))
            player = players.get(key)
            if player is None:
                player = {
                    "entity_key": slugify(name),
                    "display_name": name,
                    "draw": draw,
                    # A participant is registered as an identity, not as a
                    # priceable row: their only quote is P(wins this match),
                    # which belongs on the matchup, not on a board.
                    "role": "participant",
                    "seed": None,
                    "country": None,
                    "draw_slot": None,
                    "section": None,
                    "sources": [],
                }
                players[key] = player
                new_participants += 1
            entity_keys.append(player["entity_key"])

        if entity_keys[0] == entity_keys[1]:
            # Two spellings of one name on both sides of a match. Registering
            # it would produce a player facing themselves.
            dropped["SIDES_COLLAPSE_TO_ONE_PLAYER"] = (
                dropped.get("SIDES_COLLAPSE_TO_ONE_PLAYER", 0) + 1
            )
            continue

        scheduled = str(match["start_time"])
        matchups.append({
            "matchup_key": matchup_key(draw, entity_keys, scheduled),
            "draw": draw,
            "round": match.get("round", "qualifying"),
            "scheduled_date": scheduled,
            "players": entity_keys,
            "sources": [{
                "source": "polymarket",
                "kind": "match",
                "market_id": match["market_id"],
                "outcome_id": sides[0]["outcome_id"],
                "market_external_id": match["market_external_id"],
                "status": "live",
                "terminal_result": None,
                "price_observed_at": _iso(sides[0].get("price_observed_at")),
                "evidence": {
                    "kind": "match-market-census",
                    "observed_at": observed_at,
                    "polymarket_event_id": match["polymarket_event_id"],
                    # The provenance that makes the sides mapping checkable
                    # later: these are the source's OWN labels, in the source's
                    # own order, not a parse of the market title.
                    "source_labels": [s.get("source_label") for s in sides],
                    "start_time": match.get("start_time"),
                },
                # The load-bearing field. Without it the slate prints
                # "Yes 54% / No 47%" instead of two players.
                "sides": {
                    entity_keys[0]: {
                        "outcome_id": sides[0]["outcome_id"],
                        "outcome_external_id": sides[0].get("outcome_external_id"),
                        "source_label": sides[0].get("source_label"),
                    },
                    entity_keys[1]: {
                        "outcome_id": sides[1]["outcome_id"],
                        "outcome_external_id": sides[1].get("outcome_external_id"),
                        "source_label": sides[1].get("source_label"),
                    },
                },
            }],
        })

    matchups.sort(key=lambda m: (m["scheduled_date"], m["matchup_key"]))
    return matchups, dropped, new_participants


def _iso(value) -> str | None:
    """Normalise a Postgres timestamp string to something ``is_iso8601`` accepts."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.replace(" ", "T", 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument(
        "--field", action="append", default=[],
        help="<draw>=<source>:<path-to-query-dump>",
    )
    parser.add_argument(
        "--base",
        help=(
            "an existing committed register to SUPERSEDE. Its players are carried "
            "forward verbatim instead of being re-derived from --field dumps"
        ),
    )
    parser.add_argument("--freshness", help="JSON: {'<source>:<market_ext>': '<iso ts>'}")
    parser.add_argument(
        "--matchups",
        help="match-market census from fetch_usopen_match_census.py (second population pass)",
    )
    parser.add_argument(
        "--exclude",
        help=(
            "JSON list of polymarket_event_ids to keep off the slate — the slot for the "
            "measurement lane's stale-open inventory"
        ),
    )
    parser.add_argument("--observed-at", required=True, help="ISO timestamp of the census")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--supersedes-version", type=int, default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    freshness = json.loads(Path(args.freshness).read_text()) if args.freshness else {}

    # entity_key -> player entry.  Keyed on the space-insensitive normalized
    # name so Kalshi's "Felix Auger-Aliassime" and Polymarket's "Felix Auger
    # Aliassime" land on ONE player instead of two board rows.
    players: dict[tuple, dict] = {}
    skipped_non_players: list[str] = []

    # Carrying the base register's players forward VERBATIM is deliberate. A
    # register version supersedes its predecessor; it does not re-decide it.
    # Re-deriving identity from fresh dumps every run would mean a source
    # renaming a player silently re-slugs their entity_key — the precise thing
    # a pinned identity exists to survive. Only the fields this pass owns
    # (`role`, `kind`) are filled in, and only where absent.
    if args.base:
        base = json.loads(Path(args.base).read_text())
        for player in base.get("players", []):
            player.setdefault("role", "contender")
            for block in player.get("sources") or []:
                if isinstance(block, dict):
                    block.setdefault("kind", "outright")
            players[(player["draw"], normalize_player_name(player["display_name"]))] = player
        print(f"base: {args.base} v{base.get('version')} -> {len(players)} players carried forward")

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
                    # Seeded from an OUTRIGHT field, so this is someone who can
                    # win the tournament: a contender, and a championship-board
                    # row. The match pass registers participants instead.
                    "role": "contender",
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
                "kind": "outright",
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

    # ---- second population pass: participants + matchups from match markets --
    matchups: list[dict] = []
    dropped: dict[str, int] = {}
    new_participants = 0
    if args.matchups:
        census = json.loads(Path(args.matchups).read_text())
        excluded_ids = (
            {str(x) for x in json.loads(Path(args.exclude).read_text())}
            if args.exclude
            else set()
        )
        now = datetime.fromisoformat(args.observed_at.replace("Z", "+00:00"))
        matchups, dropped, new_participants = apply_match_pass(
            players,
            census,
            now=now,
            excluded_ids=excluded_ids,
            observed_at=args.observed_at,
        )

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
        # A matchup may only name players the register already carries — which
        # is why the match pass registers its participants before it gets here.
        "matchups": matchups,
    }
    if args.supersedes_version is not None:
        register["supersedes_version"] = args.supersedes_version

    contract = build_contract({args.tournament: {"season": args.season, "entity_kind": "player"}})
    findings = validate_register(register, contract)
    verdict = classify(findings)

    contenders = [p for p in register["players"] if p.get("role", "contender") == "contender"]
    print(f"players:  {len(register['players'])} "
          f"({len(contenders)} contenders, {new_participants} new participants)")
    for draw in DRAWS:
        n = sum(1 for p in contenders if p["draw"] == draw)
        two = sum(1 for p in contenders if p["draw"] == draw and len(p["sources"]) == 2)
        print(f"  {draw}: {n} contenders, {two} with both sources, {n - two} single-source")
    print(f"skipped non-player buckets: {len(skipped_non_players)} {skipped_non_players}")
    if args.matchups:
        print(f"matchups: {len(matchups)} on the slate")
        for draw in DRAWS:
            print(f"  {draw}: {sum(1 for m in matchups if m['draw'] == draw)}")
        # Every drop is named and counted. "The slate is short today" must
        # always have an answer, or a silent exclusion reads as an absence.
        print(f"matches dropped: {sum(dropped.values())}")
        for reason in sorted(dropped):
            print(f"  {reason}: {dropped[reason]}")
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
