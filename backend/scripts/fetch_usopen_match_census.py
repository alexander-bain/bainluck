#!/usr/bin/env python3
"""Build the match-market census the register's SECOND population pass consumes (UX-P132).

Day 1 seeded the register from the two outright winner fields: 80 *contenders*,
which is exactly right for the championship boards and useless for the daily
slate.  The slate's players are the **qualifying draw**, and most of them are
not contenders, so ``validate_matchup`` rejected every qualifying matchup with
``MATCHUP_PLAYER_NOT_REGISTERED`` — correctly, and loudly.  This script produces
the input that closes that gap: *contenders and participants are different
sets*, and the register has to carry both.

It reads TWO sources and joins them, because neither one alone can answer the
question the slate needs answered.

**Our database** (via ``POST /api/admin/db-query``) supplies the identities we
can actually price: for each match, the Polymarket *condition* market row and
its ``Yes``/``No`` outcome ids.

    SELECT fm.group_id, fm.id AS market_id, fm.external_id AS market_ext,
           fm.name AS market_name, fm.status,
           fo.id AS outcome_id, fo.name AS outcome_name,
           fo.external_id AS outcome_ext,
           fo.current_probability, fo.opening_probability,
           (SELECT MAX(s.captured_at) FROM futures_odds_snapshots s
             WHERE s.outcome_id = fo.id AND s.probability IS NOT NULL)
             AS price_observed_at
      FROM futures_markets fm
      JOIN futures_outcomes fo ON fo.market_id = fm.id
     WHERE fm.source = 'polymarket'
       AND fm.name ILIKE 'US Open, Qualification%'
       AND fm.name ILIKE '% vs %'
       AND fm.external_id LIKE '0x%'
     ORDER BY fm.group_id, fo.name DESC;

**Polymarket Gamma** supplies the two things our database provably does not
hold, both measured this cycle:

1. **Which player ``Yes`` means.**  Searched for and not found: ``futures_outcomes``
   has no column carrying the source's own outcome label, and
   ``market_metadata->'shape'`` records ``side_kind: "yes_no"`` — a *kind*, never
   a *which*.  The repo's only Yes-to-competitor rule is a market-NAME parse
   (``prediction_market_matching.MatchupInfo.yes_team``, always the first-named
   side), which is source-agnostic prose and is known to be unreliable — there
   is an inversion backstop (``_check_and_fix_inversion``) in the tree precisely
   because it gets this wrong.  Gamma's ``moneyline`` sub-market states it
   outright: ``outcomes: ["Andrea Guerrieri", "August Holmgren"]``, ordered, and
   our write contract pins ``_yes`` to ``outcomes[0]``.  Reading it beats
   parsing it, and pinning what we read into a committed file beats both.
   Doctrine clause 4: label equality is not identity.

2. **Whether the match has already been played.**  Our ``resolution_date`` reads
   2026-08-31 → 09-02 on all 324 rows and every row reads ``status='open'``,
   while Gamma reports 95 of the 162 matches ``closed`` with real dates of
   08-24/25/26.  A date-window slate keyed on ``resolution_date`` would present
   64 finished Monday matches as Sunday's card.  That is gotcha #33's shape at
   59% of the population, and gotcha #14's — a resolution date is a close time,
   not a start time.

Nothing here runs at request time.  The register is agent-maintained by charter;
this is the agent's hands.  The output is a plain JSON file consumed by
``generate_tournament_register.py --matchups``.

Usage:
    python3 scripts/fetch_usopen_match_census.py \
        --db-dump /tmp/uso/cond_outcomes.json \
        --observed-at 2026-08-25T21:30:00+00:00 \
        --out /tmp/uso/match-census.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.tournament_register import normalize_player_name  # noqa: E402

GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"

#: Gamma answers 403 to a burst.  Measured this cycle: nine 20-id batches fired
#: back to back returned 403 for every one of them, and a single request 20
#: seconds later returned 200 — so the 403 is pacing, not a block, and a run
#: that treats it as "no data" silently writes an empty census.  Fifteen ids per
#: request with a three-second floor and exponential backoff fetched 162/162.
GAMMA_BATCH = 15
GAMMA_DELAY_SECONDS = 3.0
GAMMA_RETRIES = 5

#: ``US Open, Qualification ATP: Alex Bolt vs Pablo Llamas Ruiz``
TITLE_RE = re.compile(
    r"^US Open,\s*Qualification\s*(?P<tour>ATP|WTA)\s*:\s*(?P<a>.+?)\s+vs\s+(?P<b>.+?)\s*$",
    re.IGNORECASE,
)

TOUR_TO_DRAW = {"ATP": "mens-singles", "WTA": "womens-singles"}


def fetch_gamma_events(event_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch Gamma events in paced batches.  A batch that never succeeds RAISES.

    It does not return partial data with a warning.  A census that quietly
    covers 140 of 162 matches produces a register that quietly omits 22 of
    them, and nothing downstream can tell that apart from "those matches do not
    exist" (gotcha #53 — an empty answer is a response shape, not an absence).
    """
    events: dict[str, dict[str, Any]] = {}
    for start in range(0, len(event_ids), GAMMA_BATCH):
        batch = event_ids[start:start + GAMMA_BATCH]
        url = GAMMA_EVENTS_URL + "?" + "&".join(f"id={eid}" for eid in batch)
        backoff = GAMMA_DELAY_SECONDS
        for attempt in range(GAMMA_RETRIES):
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "bainluck-tournament-register/1.0"}
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = json.loads(response.read())
                for event in payload:
                    events[str(event["id"])] = event
                break
            except (urllib.error.URLError, ValueError, KeyError) as exc:
                print(f"  gamma batch {start} attempt {attempt + 1}: {exc}", file=sys.stderr)
                time.sleep(backoff)
                backoff *= 2
        else:
            raise RuntimeError(
                f"Gamma batch starting at {start} failed {GAMMA_RETRIES} times "
                f"({len(batch)} events). Refusing to write a partial census."
            )
        time.sleep(GAMMA_DELAY_SECONDS)
    return events


def read_query_dump(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    columns = payload["columns"]
    if payload.get("truncated"):
        raise RuntimeError(f"{path} is TRUNCATED — re-run the query with a higher limit.")
    return [dict(zip(columns, row)) for row in payload["rows"]]


def moneyline_market(event: dict[str, Any]) -> dict[str, Any] | None:
    """The one sub-market that is the match itself.

    Selected by ``sportsMarketType == 'moneyline'`` rather than by name, because
    the set-winner and totals sub-markets carry the *same* title with a suffix
    and a name test would take whichever came first.
    """
    markets = [
        m for m in event.get("markets", []) if m.get("sportsMarketType") == "moneyline"
    ]
    return markets[0] if len(markets) == 1 else None


def parse_outcomes(raw: Any) -> list[str]:
    """Gamma returns ``outcomes`` as a JSON-encoded STRING, not a list."""
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return []
        return [str(x) for x in parsed] if isinstance(parsed, list) else []
    return []


def build_census(rows: list[dict[str, Any]], events: dict[str, dict[str, Any]], observed_at: str):
    """Join our priceable identities to Gamma's side labels and real schedule."""
    by_group: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_group.setdefault(str(row["group_id"]), []).append(row)

    matches: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for group_id, group_rows in sorted(by_group.items()):
        event_id = group_id.split(":", 1)[-1]
        name = str(group_rows[0]["market_name"])

        def reject(reason: str) -> None:
            rejected.append({"group_id": group_id, "name": name, "reason": reason})

        title_match = TITLE_RE.match(name)
        if title_match is None:
            reject("TITLE_UNPARSEABLE")
            continue
        draw = TOUR_TO_DRAW[title_match.group("tour").upper()]
        title_a = title_match.group("a").strip()
        title_b = title_match.group("b").strip()

        event = events.get(event_id)
        if event is None:
            reject("GAMMA_EVENT_MISSING")
            continue
        market = moneyline_market(event)
        if market is None:
            reject("NO_SINGLE_MONEYLINE_SUBMARKET")
            continue

        labels = parse_outcomes(market.get("outcomes"))
        if len(labels) != 2:
            reject("MONEYLINE_NOT_TWO_SIDED")
            continue

        # The positional contract, VERIFIED per match rather than assumed. Our
        # writer pins `_yes` to outcomes[0]; the title names A first. If Gamma's
        # own ordering disagrees with its own title for even one match, that
        # match is dropped, not guessed at — an inverted slate row is a wrong
        # number wearing a player's name.
        if (
            normalize_player_name(labels[0]) != normalize_player_name(title_a)
            or normalize_player_name(labels[1]) != normalize_player_name(title_b)
        ):
            reject("SIDES_DISAGREE_WITH_TITLE")
            continue

        condition_id = str(market.get("conditionId") or "")
        yes_row = next((r for r in group_rows if r["outcome_name"] == "Yes"), None)
        no_row = next((r for r in group_rows if r["outcome_name"] == "No"), None)
        if yes_row is None or no_row is None:
            reject("NO_YES_NO_PAIR_IN_DB")
            continue
        if str(yes_row["market_ext"]).lower() != condition_id.lower():
            # Our condition row and Gamma's moneyline are different markets, so
            # the label ordering we just verified does not describe the outcome
            # ids we would price.
            reject("CONDITION_ID_MISMATCH")
            continue

        matches.append({
            "polymarket_event_id": event_id,
            "group_id": group_id,
            "draw": draw,
            "round": "qualifying",
            "market_name": name,
            "market_id": yes_row["market_id"],
            "market_external_id": yes_row["market_ext"],
            "db_status": yes_row["status"],
            # Gamma's real start, NEVER our resolution_date — that column reads
            # 08-31/09-02 on every one of these rows and is a close time.
            "start_time": event.get("startTime"),
            "event_date": event.get("eventDate"),
            "source_closed": bool(event.get("closed")),
            "sides": [
                {
                    "player_name": title_a,
                    "source_label": labels[0],
                    "side": "yes",
                    "outcome_id": yes_row["outcome_id"],
                    "outcome_external_id": yes_row["outcome_ext"],
                    "current_probability": yes_row["current_probability"],
                    "opening_probability": yes_row["opening_probability"],
                    "price_observed_at": yes_row["price_observed_at"],
                },
                {
                    "player_name": title_b,
                    "source_label": labels[1],
                    "side": "no",
                    "outcome_id": no_row["outcome_id"],
                    "outcome_external_id": no_row["outcome_ext"],
                    "current_probability": no_row["current_probability"],
                    "opening_probability": no_row["opening_probability"],
                    "price_observed_at": no_row["price_observed_at"],
                },
            ],
        })

    return {
        "kind": "match-market-census",
        "tournament": "us-open",
        "season": "2026",
        "observed_at": observed_at,
        "matches": matches,
        "rejected": rejected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-dump", required=True, help="db-query JSON for the condition markets")
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    rows = read_query_dump(Path(args.db_dump))
    event_ids = sorted({str(r["group_id"]).split(":", 1)[-1] for r in rows})
    print(f"db rows: {len(rows)} across {len(event_ids)} events")

    events = fetch_gamma_events(event_ids)
    print(f"gamma events: {len(events)}")

    census = build_census(rows, events, args.observed_at)
    matches = census["matches"]
    open_matches = [m for m in matches if not m["source_closed"]]
    print(f"matches: {len(matches)} joined, {len(open_matches)} not closed at source")
    print(f"rejected: {len(census['rejected'])}")
    for reason in sorted({r["reason"] for r in census["rejected"]}):
        n = sum(1 for r in census["rejected"] if r["reason"] == reason)
        print(f"  {reason}: {n}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(census, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
