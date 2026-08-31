#!/usr/bin/env python3
"""Census the Kalshi MATCH markets a tournament's registered fixtures can be priced from (Q466).

═══ WHY THIS EXISTS ═══

The draw ceremony ingest pinned 96 US Open main-draw fixtures on 2026-08-27 and
wrote, on every one of them::

    "status": "missing",
    "note": "fixture from the released draw; no match market pinned at this
             source when the draw was ingested"

That was true when it was written — nobody quotes a first round before
qualifying finishes.  It stopped being true within days, and nothing ever
revisited it.  Measured on production at 2026-08-31: **0 of 28** finished
main-draw matches carried a pre-match probability, while the qualifying draw —
which a one-off Polymarket census DID cover — carried 25.  The better-covered
half was the half nobody quotes.  Meanwhile Kalshi held 5,048 ``KXATPMATCH`` /
``KXWTAMATCH`` markets, newest created that same day.

So this is a MATCHING failure and not an absence, which is exactly the
distinction the hill-climb guide insists on: any metric below target for markets
that SHOULD match is a bug.

═══ WHY KALSHI IS EASY WHERE POLYMARKET WAS HARD ═══

``fetch_usopen_match_census.py`` needs a Gamma round trip per event, because
Polymarket's stored outcomes are ``Yes``/``No`` and nothing in our schema says
which player ``Yes`` is (doctrine clause 4: label equality is not identity).

Kalshi does not have that problem.  ``futures_outcomes.name`` carries the
player's own name — ``Alexander Bublik``, ``Jeffrey John Wolf`` — one row per
side.  The identity is IN the row we already hold, so this census reads the
database and nothing else.  No third-party call, no pacing, no partial-fetch
hazard.

═══ WHAT IT REFUSES ═══

The join is: a market's two outcome names normalize to the two players of
exactly one registered fixture, in that fixture's draw.  Everything else is
REJECTED BY NAME and counted:

* the ticker window is every ATP/WTA match on earth in those weeks, so a
  Cincinnati market between two US Open entrants is a real hazard — it is
  refused because it must also agree with the fixture's DATE (``--date-slack``);
* a market whose two outcomes match two players who are not paired in the
  register is refused, never "helpfully" paired;
* two markets matching one fixture is an ambiguity, so BOTH are refused rather
  than taking the first — an inverted or wrong-match slate row is a real number
  wearing the wrong player's name, and it looks perfectly plausible.

Nothing here runs at request time.  The register is agent-maintained by charter;
this is the agent's hands, and the output is applied by
``pin_kalshi_match_markets.py``.

Usage::

    python3 scripts/fetch_kalshi_match_census.py \\
        --register data/tournament_registers/us-open-2026.json \\
        --observed-at 2026-08-31T04:00:00+00:00 \\
        --out /tmp/kalshi-match-census.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.tournament_register import normalize_player_name  # noqa: E402

#: ``KXATPMATCH-26AUG30BUBWOL`` -> the draw its two players belong to.
SERIES_TO_DRAW = {
    "KXATPMATCH": "mens-singles",
    "KXWTAMATCH": "womens-singles",
}

#: The row path is capped at 1,000 rows and hard-timed at 10 seconds, and the
#: candidate window is ~6,900 outcome rows.  Chunking is on ``fm.id`` — the
#: GROUPING key — so a market's two outcomes always land in the same chunk and a
#: pair is never silently half-read.
CHUNKS = 12


def db_query(sql: str, *, limit: int = 1000) -> list[dict[str, Any]]:
    """One read-only query against the admin endpoint.

    Refuses a truncated answer.  A census built on 1,000 of 1,200 rows omits 200
    fixtures and reads downstream exactly like "those fixtures have no market"
    (gotcha #53).
    """
    base = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not base or not token:
        raise RuntimeError("BAINLUCK_API and ADMIN_TOKEN must be set (source ~/.claude/.env)")
    request = urllib.request.Request(
        f"{base}/api/admin/db-query",
        data=json.dumps({"sql": sql, "limit": limit}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read())
    if "rows" not in payload:
        raise RuntimeError(f"db-query refused: {payload}")
    if payload.get("truncated"):
        raise RuntimeError("db-query TRUNCATED — raise the chunk count, never the limit")
    # Rows are ARRAYS, not objects — zip with the returned column order.
    return [dict(zip(payload["columns"], row)) for row in payload["rows"]]


#: ``KXATPMATCH-26AUG30BUBWOL`` -> ``date(2026, 8, 30)``.
#:
#: The ticker is the ONLY honest date on a Kalshi tennis row.  Measured on this
#: window: ``KXATPMATCH-26AUG30TIRMAN``, a match played on the 30th of August,
#: carries ``resolution_date = 2026-09-13`` — the tournament's end.  That is
#: gotcha #14 exactly ("Kalshi ``commence_time`` is often close time, not
#: start — use ticker-derived dates for matching"), and a date filter built on
#: the column would have refused every correct pin.
TICKER_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def ticker_date(external_id: str) -> datetime | None:
    """The match date encoded in the ticker suffix, or ``None`` if it is not there."""
    suffix = str(external_id).split("-", 1)[-1]
    if len(suffix) < 7:
        return None
    try:
        year = 2000 + int(suffix[0:2])
        month = TICKER_MONTHS[suffix[2:5].upper()]
        day = int(suffix[5:7])
        return datetime(year, month, day, tzinfo=timezone.utc)
    except (ValueError, KeyError):
        return None


def fetch_candidates(series: str, *, created_since: str) -> list[dict[str, Any]]:
    """Every outcome row for one series created since a date, chunked.

    Two things this deliberately does NOT do:

    * It does not bound on the ticker's date.  The ticker's month is
      ALPHABETIC, so ``>= '...-26AUG28'`` is a lexical range that sweeps up
      DEC, FEB, JAN, JUL, JUN, MAR, MAY, NOV and OCT — most of the year — while
      looking like a fortnight.  Bounding on ``created_at``, a real timestamp,
      is the honest version; the ticker's date is then used per row, where it
      can be parsed properly.
    * It does not use ``LIKE 'KX%'``.  Under this database's ``en_US``
      collation a prefix-LIKE cannot use the index; the range rewrite is the
      difference between a sub-second answer and a timeout.
    """
    rows: list[dict[str, Any]] = []
    ceiling = series[:-1] + chr(ord(series[-1]) + 1)
    for chunk in range(CHUNKS):
        rows.extend(db_query(
            "SELECT fm.id AS market_id, fm.external_id AS market_ext, fm.name AS market_name,"
            " fm.status, fm.resolution_date,"
            " fo.id AS outcome_id, fo.name AS outcome_name, fo.external_id AS outcome_ext,"
            " fo.current_probability, fo.opening_probability"
            " FROM futures_markets fm JOIN futures_outcomes fo ON fo.market_id = fm.id"
            f" WHERE fm.external_id >= '{series}' AND fm.external_id < '{ceiling}'"
            f" AND fm.created_at >= '{created_since}'"
            f" AND (fm.id % {CHUNKS}) = {chunk}"
            " ORDER BY fm.id, fo.name"
        ))
    return rows


def registered_pairs(register: dict[str, Any]) -> dict[tuple, dict[str, Any]]:
    """``(draw, frozenset of normalized player names)`` -> the fixture.

    Keyed on the NAMES rather than the entity keys because the Kalshi row names
    a player, and ``normalize_player_name`` is the same function that already
    stops ``Felix Auger-Aliassime`` and ``Felix Auger Aliassime`` becoming two
    board rows.
    """
    display = {
        p["entity_key"]: p.get("display_name") or ""
        for p in register.get("players") or []
    }
    out: dict[tuple, dict[str, Any]] = {}
    for matchup in register.get("matchups") or []:
        players = matchup.get("players")
        if not isinstance(players, list) or len(players) != 2:
            continue
        names = frozenset(normalize_player_name(display.get(k, k)) for k in players)
        if len(names) != 2:
            continue
        out.setdefault((matchup.get("draw"), names), matchup)
    return out


def build_census(
    rows: list[dict[str, Any]],
    register: dict[str, Any],
    *,
    draw: str,
    observed_at: str,
    date_slack_hours: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_market: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        by_market.setdefault(row["market_id"], []).append(row)

    pairs = registered_pairs(register)
    matched: dict[tuple, list[dict[str, Any]]] = {}
    rejected: list[dict[str, Any]] = []

    for market_id, sides in sorted(by_market.items(), key=lambda kv: str(kv[0])):
        name = str(sides[0]["market_name"])

        def reject(reason: str) -> None:
            rejected.append({"market_id": market_id, "name": name, "reason": reason})

        if len(sides) != 2:
            reject("NOT_TWO_SIDED")
            continue
        names = frozenset(normalize_player_name(str(s["outcome_name"])) for s in sides)
        if len(names) != 2:
            reject("SIDES_COLLAPSE_TO_ONE_PLAYER")
            continue

        fixture = pairs.get((draw, names))
        if fixture is None:
            # Overwhelmingly the common case and NOT a defect: the window holds
            # every ATP/WTA match on earth, and only this tournament's are ours.
            reject("PAIR_NOT_A_REGISTERED_FIXTURE")
            continue

        # ═══ THE DATE MUST AGREE, AND "I COULD NOT READ IT" IS NOT AGREEMENT ═══
        #
        # Two players meeting at the US Open may also have met in Cincinnati a
        # fortnight earlier, and that market is in this window. The
        # discriminator is the TICKER's date, never `resolution_date` (see
        # `ticker_date`).
        #
        # CERT-529: the first version ran the comparison only when BOTH dates
        # parsed, so an unreadable ticker or a fixture with no scheduled date
        # skipped the check entirely and the market was pinned. That is
        # absence-as-permission — the same class as reading a missing scoreboard
        # entry as "finished" — and it is worse here, because the whole job of
        # this discriminator is to be the thing standing between a US Open
        # fixture and an identically-named market from another tournament.
        #
        # A discriminator that cannot run has not passed. It refuses.
        scheduled = _moment(fixture.get("scheduled_date"))
        played = ticker_date(sides[0]["market_ext"])
        if scheduled is None or played is None:
            reject("DATE_UNREADABLE_SO_UNVERIFIABLE")
            continue
        if abs((played - scheduled).total_seconds()) > date_slack_hours * 3600:
            reject("DATE_DISAGREES_WITH_FIXTURE")
            continue

        if any(s.get("opening_probability") is None for s in sides):
            # The whole point is the OPENING quote — the only stored price
            # guaranteed to pre-date the match. A pin with no opening price
            # buys the page nothing it does not already have.
            reject("NO_OPENING_PRICE")
            continue

        matched.setdefault((draw, names), []).append({
            "market_id": market_id,
            "market_ext": sides[0]["market_ext"],
            "market_name": name,
            "status": sides[0]["status"],
            "resolution_date": sides[0].get("resolution_date"),
            "fixture": fixture,
            "sides": sides,
        })

    matches: list[dict[str, Any]] = []
    for key, candidates in sorted(matched.items(), key=lambda kv: str(sorted(kv[0][1]))):
        if len(candidates) > 1:
            # BOTH refused. Taking the first would pin a plausible number from
            # the wrong tournament, and it would look right on the page.
            for candidate in candidates:
                rejected.append({
                    "market_id": candidate["market_id"],
                    "name": candidate["market_name"],
                    "reason": "AMBIGUOUS_TWO_MARKETS_ONE_FIXTURE",
                })
            continue
        candidate = candidates[0]
        fixture = candidate["fixture"]
        display = {
            p["entity_key"]: p.get("display_name") or ""
            for p in register.get("players") or []
        }
        # The register's own player order, so the pin is written in the terms
        # the fixture already uses rather than in Kalshi's row order.
        sides_by_player: dict[str, dict[str, Any]] = {}
        for entity_key in fixture["players"]:
            wanted = normalize_player_name(display.get(entity_key, entity_key))
            row = next(
                (s for s in candidate["sides"]
                 if normalize_player_name(str(s["outcome_name"])) == wanted),
                None,
            )
            if row is None:
                break
            sides_by_player[entity_key] = {
                "outcome_id": row["outcome_id"],
                "outcome_external_id": row["outcome_ext"],
                "source_label": row["outcome_name"],
                "opening_probability": row["opening_probability"],
                "current_probability": row["current_probability"],
            }
        if len(sides_by_player) != 2:
            rejected.append({
                "market_id": candidate["market_id"],
                "name": candidate["market_name"],
                "reason": "SIDES_DID_NOT_MAP_BACK_TO_THE_FIXTURE",
            })
            continue

        matches.append({
            "source": "kalshi",
            "draw": draw,
            "matchup_key": fixture["matchup_key"],
            "market_id": candidate["market_id"],
            "market_external_id": candidate["market_ext"],
            "market_name": candidate["market_name"],
            "db_status": candidate["status"],
            "resolution_date": candidate["resolution_date"],
            "observed_at": observed_at,
            "sides": sides_by_player,
        })
    return matches, rejected


def _moment(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--created-since", default="2026-08-25",
        help="only markets our ingest first saw on or after this date",
    )
    parser.add_argument(
        "--date-slack-hours", type=float, default=96.0,
        help="how far a market's resolution_date may sit from the fixture's start "
             "(a Kalshi resolution date is a CLOSE time, not a start — gotcha #14)",
    )
    args = parser.parse_args()

    register = json.loads(Path(args.register).read_text())

    matches: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for series, draw in SERIES_TO_DRAW.items():
        rows = fetch_candidates(series, created_since=args.created_since)
        print(f"{series}: {len(rows)} outcome rows in the window", file=sys.stderr)
        found, refused = build_census(
            rows, register, draw=draw, observed_at=args.observed_at,
            date_slack_hours=args.date_slack_hours,
        )
        matches.extend(found)
        rejected.extend(refused)
        print(f"  -> {len(found)} fixtures pinned, {len(refused)} refused", file=sys.stderr)

    reasons: dict[str, int] = {}
    for entry in rejected:
        reasons[entry["reason"]] = reasons.get(entry["reason"], 0) + 1

    census = {
        "kind": "kalshi-match-market-census",
        "observed_at": args.observed_at,
        "window": {"created_since": args.created_since},
        "matches": matches,
        "rejected_counts": dict(sorted(reasons.items())),
        # The full list, not just the counts: a refusal nobody can look at is a
        # number that cannot be argued with.
        "rejected": rejected,
    }
    Path(args.out).write_text(json.dumps(census, indent=2, default=str) + "\n")
    print(f"\nwrote {args.out}: {len(matches)} pinned", file=sys.stderr)
    for reason, count in census["rejected_counts"].items():
        print(f"  refused {reason}: {count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
