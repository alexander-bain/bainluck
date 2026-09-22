#!/usr/bin/env python3
"""#7739 — a Polymarket-minted US-sport game stops naming the away team as host.

WHAT A READER SEES TODAY. `/search?q=tempo` renders `Toronto Tempo 42% /
Connecticut Sun 58%` for event 15310072, and every card on the page puts the
HOST on top. ESPN's `homeAway` for that fixture (401857215) is home=Connecticut
Sun. The label and the price disagree with each other on one card.

WHERE IT COMES FROM. `_create_event_from_prediction_market` stamps
`home_team_name = team_a`, the club Polymarket names FIRST in "A vs. B".
Measured against ESPN on 2026-09-22 (artifacts-lane1-591), Polymarket mirrors
each sport's own listing habit rather than one convention:

    WNBA + NHL   87 fixtures   87 away-first    0 home-first
    soccer       34 fixtures    0 away-first   34 home-first

So `team_a` is right for world football and European club basketball and wrong
for the US leagues. See `POLYMARKET_AWAY_FIRST_LEAGUES` for the full note,
including why the mint path itself is NOT the place to fix this.

TWO SIGNALS, BOTH REQUIRED, AND WHY.
  1. ESPN's explicit `homeAway` for the same fixture, matched on both club
     names AND a kickoff inside `--kickoff-tolerance-min`.
  2. The measured venue convention for the league the clubs resolve to.

A row is rewritten only when both agree it is reversed. ESPN alone is not
enough: the WNBA and NHL slates both carry same-minute home-and-home pairs
(`nhl-ott-mon-2026-09-26` is two ESPN fixtures at 23:00Z with opposite
orientations), so a name-and-time join can land on the wrong leg of a pair and
"correct" a row that was already right. Requiring the convention to predict the
same flip means a wrong-leg match produces DISAGREE — which is reported and
skipped, never written.

SAFETY (D51(b) / notice 47(c)).
  * Dry run is the DEFAULT. `--apply` is the only thing that writes.
  * `--apply` refuses to start without `--backup`, which copies every row it is
    about to touch into `backup_event_orientation_7739` FIRST and prints the
    one-command restore before the first UPDATE.
  * Runtime DDL (`CREATE TABLE IF NOT EXISTS backup_*`), attended invocation
    only — this script is never run by a release or a beat.
  * Scheduled/live rows only. A completed game's orientation is load-bearing for
    scores already stored against it; swapping names there would silently
    reverse a final score, which is a worse defect than the one being fixed.

🔴 THE SWAP IS A TRANSPOSITION, NOT A RENAME, AND THIS IS THE WHOLE RISK.
`home_team_name` is not a label sitting on its own — every probability we store
for a game is HOME-ORIENTED. Event 15310072 carries
`win_probability_sources.polymarket.value = 0.585` with `hero_probability`
0.585 / `hero_probability_away` 0.415, and the card reads `Toronto Tempo 59%`.
Rename the two clubs and nothing else, and the page serves **Connecticut Sun
59%** — the market's price on the wrong club. That is a strictly worse defect
than the one being repaired: a wrong label becomes a wrong number.

So a swap moves, atomically:
    events.home_team_name  <-> away_team_name
    events.home_team_id    <-> away_team_id
    events.win_probability_sources.<source>.value  ->  1 - value
    win_prob_snapshots.home_win_probability <-> away_win_probability

and NOTHING ELSE IS ALLOWED TO BE PRESENT. `--apply` refuses any row carrying an
orientation-dependent field this script does not transpose (a score, an
opening/closing probability or spread, an odds snapshot). All 31 rows in the
2026-09-22 dry run are clean on every one of those, so the refusal is a guard
rather than a blocker — but it is what keeps this repair honest if the
population ever changes shape.

`yes_is_home` is deliberately NOT written: it is not a stored column.
`resolve_orientation` recomputes it from the current home/away names on every
pass, so the live writers produce the correctly-oriented value by themselves
once the names are right. Transposing the stored value is only there so the
page is never briefly wrong in the window before that pass.

🔴 AND THAT LAST SENTENCE IS THE ONE THAT COST A RUN. The transposition is not
a courtesy covering a gap — it is the half of this repair that can LOSE, and
losing it lands the exact "wrong label becomes a wrong number" state the
paragraph above calls strictly worse than the bug.

WHAT HAPPENED (production, 2026-09-22). `--apply` committed 30 rows at 13:27:45Z
and exited 0; 30/30 in the log, 30/30 in the row count. Within 22 seconds **20
of the 30 had the names still swapped and the price back to its pre-swap
value**, and the run was restored by hand at 13:33:03Z. The 7 that held were
exactly the 7 no writer touched: `win_prob_snapshots.captured_at` dates the
overwrite and the split is the writer's, not the repair's.

The writer is `live_blend_refresh`'s WS fast lane. `_refresh_batch` reads its
`Event` rows at the TOP of a batch and stamps the JSONB at the bottom, so a
batch already in flight when the swap commits computes from pre-commit names
and writes a value the commit has just invalidated. Nothing is wrong with the
batch; it is a plain read-then-write race, and a one-shot repair cannot win it
by trying harder.

🟢 SO: DOES IT SELF-HEAL? MEASURED, not reasoned — because the two answers pick
different fixes and the "games days out" cohort cannot be made to fire a
refresh on demand. `artifacts-lane1-598/trace_cohort.py` replays production's
OWN market and outcome rows through the real `compute_source_home_probability`,
twice per row: a CONTROL on the current names, which must reproduce the value
production has stored before the row is allowed to count, and the same group
read with the names the repair leaves behind.

    30 rows · 26 SELF-HEALS · 1 VACUOUS (stored p = 0.5, where `p` and `1 - p`
    are the same number and the row can convict nothing) · 3 UNPRICED · 0
    controls unfaithful · 0 rows whose value ignores the event names.

Every path in `find_moneyline_outcome` resolves the side by matching outcome
names against the CURRENT `home_team_name`, so once the names are right the
next refresh writes the repaired orientation by itself. **The race is transient,
not a permanent inversion** — but "transient" here means "until the next refresh
of a game that may be a week away", which is days of a wrong number on a card.

🟢 THE SETTLE STAGE is what that measurement buys. After the swap commits,
`--apply` verifies its own write against the WRITER'S OWN FUNCTION rather than
against the value it just wrote:

    expected = compute_source_home_probability(<this event's polymarket
               group>, current home_team_name, current away_team_name)

A row whose stored value equals `expected` is settled — including when both are
absent, which is reported as UNPRICED and never counted as a win (trap 3:
"both prices absent" is uncorroborated, not corroborated). A row that disagrees
by EXACTLY the inversion signature is re-stamped and re-checked. A row that
disagrees any OTHER way is reported and NOT written: that is a disagreement
this script does not understand, and the one thing worse than a lost race is a
confident write into one.

The final round never writes. Its read is the verdict, so a clean exit means a
value that was verified stable after the writer's cycle, not one that was
merely written a moment ago.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import uuid
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.utils.agent_origin import curl_args  # noqa: E402
from app.utils.prediction_market_matching import (  # noqa: E402
    POLYMARKET_AWAY_FIRST_LEAGUES,
    polymarket_lists_away_first,
)

BACKUP_TABLE = "backup_event_orientation_7739"
PRODUCER_APP = "bainluck"

# Resolved league -> the ESPN scoreboard path that carries its fixtures. Only
# the leagues whose convention was actually measured; an unlisted league is
# skipped, never guessed at.
ESPN_PATHS = {
    "basketball_wnba": "basketball/wnba",
    "icehockey_nhl": "hockey/nhl",
    "icehockey_nhl_preseason": "hockey/nhl",
}

# The rows this defect can reach: minted by a Polymarket market (so the anchor
# channel knows only that source), never reconciled to the authority, and still
# ahead of or inside their own game.
CANDIDATE_SQL = """
WITH pm AS (
    SELECT DISTINCT event_id FROM event_provider_anchors WHERE source = 'polymarket'
), other AS (
    SELECT DISTINCT event_id FROM event_provider_anchors WHERE source <> 'polymarket'
)
SELECT e.id, s.key AS sport_key, e.home_team_name, e.away_team_name,
       e.commence_time, e.status
FROM events e
JOIN pm ON pm.event_id = e.id
LEFT JOIN other ON other.event_id = e.id
JOIN sports s ON s.id = e.sport_id
WHERE other.event_id IS NULL
  AND e.espn_id IS NULL
  AND e.status IN ('scheduled', 'live')
  AND e.commence_time BETWEEN now() - interval '1 day'
                          AND now() + (cast(:horizon_days AS int) * interval '1 day')
ORDER BY e.commence_time
"""
# 🪤 `interval :horizon_days` is not parameterisable and never was. INTERVAL is a
# type constructor whose operand must be a literal, so `interval $1` dies in the
# PARSER — before binding, before types, before any row is considered:
#
#     asyncpg.exceptions.PostgresSyntaxError: syntax error at or near "$1"
#
# Measured on production 2026-09-22 (`run.3888`, 12:03Z, the first invocation
# after the script reached the slug): exit 1 on the first statement, so no
# argument to this script has ever selected a row. Every unit test passed
# throughout, because none of them lets a server see the text — the same gap
# #7354 shipped through, and `tests/integration/
# test_repair_7739_candidate_sql_real_postgres.py` is the guard that closes it
# here. The multiplication is the parameterisable form.
#
# 🪤 AND THE OBVIOUS FIX IS ALSO WRONG: `:horizon_days::int` is not a bind at all.
# SQLAlchemy's bind regex refuses a colon preceded by a colon, so `::` swallows the
# parameter and `text()` emits the literal `:horizon_days::int` — a SECOND syntax
# error ("at or near \":\""), on a form that reads correct and compiles with an
# EMPTY bind list. `cast(... AS int)` is the spelling that survives both the
# SQLAlchemy layer and the server. Verified through SQLAlchemy+asyncpg against a
# real PostgreSQL before this was committed, not reasoned about.

# Every club in the measured leagues, read ONCE. Resolution then happens in
# Python against `same_club`, which is the same rule the ESPN join uses.
#
# Exact-on-`teams` is not enough and the gap is not an edge case: run that way
# against production on 2026-09-22, 493 of 500 candidate rows came back
# UNRESOLVED and every NHL row was among them, because Polymarket titles them
# `Capitals vs. Hurricanes` while `teams` says `Washington Capitals`. An
# unresolved row is skipped, so exact matching quietly reduced this repair to
# its WNBA seventh while reporting a clean run.
CLUBS_SQL = """
SELECT s.key AS league, t.name
FROM teams t
JOIN sports s ON s.id = t.sport_id
WHERE s.key = ANY(:leagues)
"""


# Orientation-dependent data this script does NOT transpose. A row holding any
# of it is refused rather than half-swapped.
UNHANDLED_SQL = """
SELECT e.id,
       (e.home_score IS NOT NULL OR e.away_score IS NOT NULL) AS has_score,
       (e.opening_home_probability IS NOT NULL
        OR e.opening_away_probability IS NOT NULL
        OR e.opening_home_spread IS NOT NULL
        OR e.opening_favorite IS NOT NULL) AS has_opening,
       (e.closing_home_probability IS NOT NULL
        OR e.closing_away_probability IS NOT NULL
        OR e.closing_home_spread IS NOT NULL) AS has_closing,
       (SELECT count(*) FROM odds_snapshots o WHERE o.event_id = e.id)
           AS odds_snapshots
FROM events e
WHERE e.id = ANY(:ids)
"""

# The transposition itself. One statement per table, both inside one
# transaction: a half-applied swap is the wrong-price defect this guards.
SWAP_EVENT_SQL = """
UPDATE events SET
    home_team_name = away_team_name,
    away_team_name = home_team_name,
    home_team_id   = away_team_id,
    away_team_id   = home_team_id,
    win_probability_sources = (
        SELECT jsonb_object_agg(
                   key,
                   CASE WHEN jsonb_typeof(val -> 'value') = 'number'
                        THEN jsonb_set(val, '{value}',
                                 to_jsonb(round((1 - (val ->> 'value')::numeric), 4)))
                        ELSE val END)
        FROM jsonb_each(win_probability_sources) AS s(key, val)
    )
WHERE id = ANY(:ids)
"""

SWAP_SNAPSHOTS_SQL = """
UPDATE win_prob_snapshots SET
    home_win_probability = away_win_probability,
    away_win_probability = home_win_probability
WHERE event_id = ANY(:ids)
"""

# ── the settle stage ─────────────────────────────────────────────────────────

#: How far a stored value may sit from the writer's own recomputation and still
#: be called the same number. The blend rounds to 4dp (`round(home_prob, 4)` in
#: `live_blend_refresh`), so this is one unit in that last place with room to
#: spare. Deliberately NOT a "close enough" tolerance: a real price move between
#: two reads is not a settled row, it is a row to look at again next round.
SETTLE_EPSILON = 5e-4

#: Re-stamp ONLY the source this repair transposes. `jsonb_set` on a path whose
#: parent is absent is a no-op rather than an error, and the `WHERE` makes that
#: explicit so a row with no polymarket leg can never be counted as re-stamped.
#:
#: 🪤 `cast(:value AS numeric)`, never `:value::numeric` — the same trap that
#: made this script's first production invocation inert.
#:
#: MEASURED, because the two accessors disagree and a guard has to pick one.
#: `text(":horizon_days::int").compile().params` is `{}` — which is where "an
#: EMPTY bind list" comes from and is what the integration strawman asserts. But
#: `._bindparams` is NOT empty: it holds `horizon_day`, the name SHORT BY ONE
#: CHARACTER. Either way the caller's own key is never bound and the literal text
#: reaches the server; a guard that asks `._bindparams == expected` catches it
#: because the NAME is wrong, not because the parameter is missing.
RESTAMP_SQL = """
UPDATE events SET win_probability_sources = jsonb_set(
    win_probability_sources, '{polymarket,value}',
    to_jsonb(round(cast(:value AS numeric), 4)))
WHERE id = :event_id
  AND win_probability_sources -> 'polymarket' ? 'value'
"""

#: Snapshots the racing writer laid down AFTER the swap carry the pre-swap
#: orientation; the ones the swap itself transposed are already right. Re-swapping
#: every snapshot for the event would invert those, so the settle stage bounds
#: itself by `captured_at` (trap 5: the JSONB's own `updated_at` is the MARKET's
#: timestamp and cannot witness a write).
#: 🔴 IDEMPOTENT BY VALUE, NOT BY WATERMARK (CERT-3301's follow-up).
#:
#: A time bound alone is not enough and the second round is where it breaks. The
#: lower bound is the SWAP's commit instant and it does not move, so round 2
#: re-reads every snapshot round 1 already corrected: the racing writer adds S2
#: (wrong), the statement transposes S1 *and* S2, and S1 — repaired one round
#: ago — is inverted straight back. The settle loop would then oscillate a
#: snapshot it had already fixed, which is the same "re-swapping inverts what
#: the swap already fixed" failure the time bound was added to prevent, one
#: level up.
#:
#: So the predicate is the one the rest of this stage already uses: a row is
#: touched ONLY when it carries exactly the inversion of what the writer would
#: say right now. A snapshot already holding `expected` does not match and is
#: left alone, so running this twice is a no-op the second time — idempotence by
#: construction rather than by bookkeeping, which is what makes it safe inside a
#: loop whose whole job is to run again.
#:
#: Fail-closed in the same direction, too: a snapshot at a price that has since
#: MOVED matches neither arm and is not written. That is a disagreement this
#: script does not understand, and the rule above it is that those get reported,
#: never repaired.
#:
#: `captured_at >= :since` stays as a second bound. It is close to redundant —
#: pre-swap history was already transposed by `SWAP_SNAPSHOTS_SQL` and so no
#: longer looks inverted — but it costs nothing and keeps this statement
#: incapable of reaching a row the swap did not touch.
RESTAMP_SNAPSHOTS_SQL = """
UPDATE win_prob_snapshots SET
    home_win_probability = away_win_probability,
    away_win_probability = home_win_probability
WHERE event_id = :event_id
  AND captured_at >= :since
  AND home_win_probability IS NOT NULL
  AND away_win_probability IS NOT NULL
  AND abs(home_win_probability - (1 - cast(:expected AS numeric)))
      <= cast(:eps AS numeric)
"""


async def writer_expectation(session, ids: list[int]) -> dict[int, float | None]:
    """What the live writer would publish for each event, from its CURRENT names.

    THE AUTHORITY IS THE WRITER'S OWN FUNCTION, asked the way the writer asks it.
    Checking "did the value I wrote survive" cannot distinguish a lost race from
    a legitimate price move, and it has no opinion at all about a row this repair
    never touched. Checking "does the stored value agree with what the writer
    would compute from the names that are there now" is the invariant the page
    actually depends on, and it is race-free: both sides are read after the
    commit.

    Returns `None` for an event whose polymarket group says nothing — which is a
    real answer ("this source should hold no value here"), not a failure.
    """
    from sqlalchemy import select

    from app.models.models import Event, FuturesMarket, FuturesOutcome
    from app.utils.live_blend import (
        MarketOutcomes,
        compute_source_home_probability,
    )

    market_rows = (await session.execute(
        select(FuturesMarket, Event)
        .join(Event, FuturesMarket.event_id == Event.id)
        .where(FuturesMarket.source == "polymarket",
               FuturesMarket.event_id.in_(ids))
    )).all()

    outcomes_by_market: dict[int, list] = {}
    if market_rows:
        for outcome in (await session.execute(
            select(FuturesOutcome).where(
                FuturesOutcome.market_id.in_([m.id for m, _ in market_rows])
            )
        )).scalars():
            outcomes_by_market.setdefault(outcome.market_id, []).append(outcome)

    grouped: dict[int, tuple] = {}
    for market, event in market_rows:
        entry = grouped.setdefault(event.id, (event, []))
        entry[1].append(MarketOutcomes(
            market=market,
            outcomes=outcomes_by_market.get(market.id, []),
            event_has_result=event.completed_at is not None,
        ))

    expected: dict[int, float | None] = {eid: None for eid in ids}
    for event_id, (event, group) in grouped.items():
        reading = compute_source_home_probability(
            group, event.home_team_name, event.away_team_name,
        )
        expected[event_id] = (
            None if reading is None else round(reading.home_probability, 4)
        )
    return expected


STORED_SQL = """
SELECT id, (win_probability_sources -> 'polymarket' ->> 'value')::float AS value
FROM events WHERE id = ANY(:ids)
"""


def classify_settlement(stored: float | None, expected: float | None) -> str:
    """One row's settle verdict. Pure, so the four outcomes are unit-testable."""
    if stored is None and expected is None:
        # Trap 3: both absent is UNCORROBORATED, not corroborated. Named
        # separately so it can never be read as a row this repair got right.
        return "UNPRICED"
    if stored is None:
        # The writer has an opinion and the row carries none. Minting it here
        # would be publishing a number, not repairing one.
        return "NOT-YET-WRITTEN"
    if expected is None:
        # The group would be retired. That is `_retire_unbacked_blend_source`'s
        # job and a different defect; this script does not get to decide it.
        return "SOURCE-WOULD-RETIRE"
    if abs(stored - expected) < SETTLE_EPSILON:
        return "SETTLED"
    if abs(expected - (1.0 - stored)) < SETTLE_EPSILON:
        return "REVERTED"
    return "UNEXPECTED"


async def settle(session, ids: list[int], swapped_at, rounds: int,
                 wait_s: int) -> tuple[dict[int, str], Counter]:
    """Verify the swap against the writer, re-stamping what the race clobbered.

    Rounds 1..N-1 may write; the LAST round only reads. That asymmetry is the
    point of the stage rather than a detail — a verdict taken immediately after
    a write says nothing about whether the write survives the writer, which is
    the entire failure this exists to catch.
    """
    verdicts: dict[int, str] = {}
    tally = Counter()
    for attempt in range(1, rounds + 1):
        final = attempt == rounds
        print(f"\n── settle round {attempt}/{rounds}"
              f"{' (verify only)' if final else ''} — waiting {wait_s}s for the "
              f"writer's cycle")
        await asyncio.sleep(wait_s)

        expected = await writer_expectation(session, ids)
        stored = {r["id"]: r["value"] for r in (await session.execute(
            text(STORED_SQL), {"ids": ids})).mappings().all()}

        verdicts = {
            eid: classify_settlement(stored.get(eid), expected.get(eid))
            for eid in ids
        }
        tally = Counter(verdicts.values())
        print(f"   {dict(tally)}")

        reverted = [e for e, v in verdicts.items() if v == "REVERTED"]
        for event_id, verdict in sorted(verdicts.items()):
            if verdict in ("SETTLED", "UNPRICED"):
                continue
            print(f"   {verdict}: {event_id} stored={stored.get(event_id)} "
                  f"writer={expected.get(event_id)}")

        if final or not reverted:
            if not reverted and not final:
                print("   nothing reverted — going straight to the final "
                      "verify-only round.")
                # Still owe a verify-only read AFTER another writer cycle: a
                # quiet round is not a settled one, it is a round the writer
                # may simply not have reached yet.
                continue
            break

        snaps = 0
        for event_id in reverted:
            await session.execute(text(RESTAMP_SQL), {
                "event_id": event_id, "value": expected[event_id],
            })
            # The racing writer also laid down snapshots in the old
            # orientation. Per event, because the predicate needs that event's
            # own expected value — see RESTAMP_SNAPSHOTS_SQL for why a bare
            # time bound re-inverts what the previous round repaired.
            snaps += (await session.execute(
                text(RESTAMP_SNAPSHOTS_SQL),
                {"event_id": event_id, "since": swapped_at,
                 "expected": expected[event_id], "eps": SETTLE_EPSILON},
            )).rowcount
        await session.commit()
        print(f"   re-stamped {len(reverted)} events and {snaps} snapshots "
              f"laid down since {swapped_at.isoformat()}")

    return verdicts, tally


def unhandled_reasons(row: dict) -> list[str]:
    """Named reasons a row may not be swapped, or an empty list."""
    reasons = []
    if row.get("has_score"):
        reasons.append("score")
    if row.get("has_opening"):
        reasons.append("opening-probability")
    if row.get("has_closing"):
        reasons.append("closing-probability")
    if row.get("odds_snapshots"):
        reasons.append(f"{row['odds_snapshots']} odds snapshots")
    return reasons


def norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def same_club(a: str | None, b: str | None) -> bool:
    """Containment either way, on a stem long enough to mean something.

    Polymarket titles an NHL club `Capitals` where ESPN says `Washington
    Capitals`. Exact equality matches none of those rows, and a miss here reads
    as "ESPN does not list this fixture" — the quietest possible wrong answer.
    """
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if min(len(na), len(nb)) < 5:
        return False
    return na in nb or nb in na


def espn_slate(path: str, yyyymmdd: str) -> list[dict]:
    """One ESPN scoreboard day.

    curl, not urllib: ESPN 403s a bare urllib User-Agent, and an exception per
    fetch would have made an all-failing census print zero findings. The HTTP
    code is read, never inferred from a body that happens to parse.

    Notice 39: the argv goes through `curl_args` even though ESPN is a third
    party. `origin_headers` decides on `is_our_host` at RUNTIME and returns
    nothing for a foreign host, so this splices an empty list and the request
    on the wire is unchanged — but the static rule the guard enforces stays the
    simple one (every outbound call goes through the carrier) rather than a
    judgment call per site. A subprocess execs the curl BINARY, so rung 1's
    shell function can never reach this call.
    """
    url = (f"https://site.api.espn.com/apis/site/v2/sports/{path}"
           f"/scoreboard?dates={yyyymmdd}&limit=200")
    out = subprocess.run(
        ["curl", *curl_args(url), "-s", "--max-time", "30",
         "-w", "\n%{http_code}", url],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"curl exit {out.returncode}")
    body, _, code = out.stdout.rpartition("\n")
    if code.strip() != "200":
        raise RuntimeError(f"HTTP {code.strip()}")
    fixtures = []
    for ev in json.loads(body).get("events", []):
        comp = ev["competitions"][0]
        sides = {c["homeAway"]: c["team"].get("displayName")
                 for c in comp["competitors"]}
        fixtures.append({
            "espn_id": ev["id"],
            "kickoff": datetime.fromisoformat(ev["date"].replace("Z", "+00:00")),
            "home": sides.get("home"),
            "away": sides.get("away"),
            "neutral": bool(comp.get("neutralSite")),
        })
    return fixtures


def leagues_for_club(clubs: list[dict], name: str) -> set[str]:
    """Leagues whose club list contains exactly ONE match for ``name``.

    Uniqueness is the whole safeguard. `Kings` names one club inside the NHL and
    another inside the NBA; scoping the club list to the measured leagues keeps
    that apart, and requiring a single hit inside a league means an ambiguous
    nickname resolves to nothing rather than to whichever row sorted first.
    """
    out = set()
    for league in POLYMARKET_AWAY_FIRST_LEAGUES:
        hits = [c for c in clubs
                if c["league"] == league and same_club(name, c["name"])]
        if len(hits) == 1:
            out.add(league)
    return out


def resolve_league(clubs: list[dict], home: str, away: str) -> str | None:
    """The league this pair plays in, or None.

    NOT "exactly one shared league". Every NHL club is carried twice — once
    under `icehockey_nhl` and once under `icehockey_nhl_preseason` — so an
    exactly-one rule resolves every NHL pair to nothing, which is the whole
    hockey half of this defect silently skipped. Measured on production
    2026-09-22: `Pittsburgh Penguins` is team 60 and team 19703.

    What actually has to be unambiguous is the two things a verdict reads: the
    convention (every league in the set is away-first by construction) and the
    ESPN scoreboard to ask. Both NHL keys name `hockey/nhl`, so the tie is
    immaterial and resolving it is honest. A pair spanning two DIFFERENT
    scoreboards still returns None.
    """
    shared = leagues_for_club(clubs, home) & leagues_for_club(clubs, away)
    if not shared:
        return None
    paths = {ESPN_PATHS.get(lg) for lg in shared}
    if len(paths) != 1 or None in paths:
        return None
    return sorted(shared)[0]


def classify(row, fixtures, tolerance_min: int, league: str):
    """One of REVERSED / CORRECT / DISAGREE / NO-ESPN-FIXTURE / AMBIGUOUS."""
    window = timedelta(minutes=tolerance_min)
    hits = []
    for f in fixtures:
        if abs(f["kickoff"] - row["commence_time"]) > window:
            continue
        straight = (same_club(row["home_team_name"], f["home"])
                    and same_club(row["away_team_name"], f["away"]))
        flipped = (same_club(row["home_team_name"], f["away"])
                   and same_club(row["away_team_name"], f["home"]))
        # Written as two named booleans rather than one chained expression: the
        # `and`/`or` form of this test binds so that the time window silently
        # stops applying to one branch, which admits a fixture days away.
        if straight or flipped:
            hits.append(f)
    if not hits:
        return "NO-ESPN-FIXTURE", None
    if len(hits) > 1:
        # A same-minute home-and-home pair. Both legs carry the same two clubs,
        # so nothing here can say which one this row is; writing either way
        # would be a coin toss on a truth field.
        return "AMBIGUOUS", None
    hit = hits[0]
    if hit["neutral"]:
        return "NEUTRAL-SITE", hit
    espn_says_reversed = same_club(row["home_team_name"], hit["away"])
    convention_says_reversed = polymarket_lists_away_first(league)
    if espn_says_reversed and convention_says_reversed:
        return "REVERSED", hit
    if not espn_says_reversed:
        return "CORRECT", hit
    return "DISAGREE", hit


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the swaps (default is a dry run)")
    ap.add_argument("--backup", action="store_true",
                    help=f"copy touched rows into {BACKUP_TABLE} first; "
                         "required by --apply")
    ap.add_argument("--horizon-days", type=int, default=30)
    ap.add_argument("--kickoff-tolerance-min", type=int, default=90)
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N rewrites (0 = no cap)")
    # The observed reverts landed 1-22s after the commit, so one wait has to
    # outlast a whole in-flight batch rather than the gap that was measured.
    # Three rounds because the last one never writes.
    ap.add_argument("--settle-wait", type=int, default=60,
                    help="seconds to wait for the writer's cycle per settle "
                         "round (default 60)")
    ap.add_argument("--settle-rounds", type=int, default=3,
                    help="settle rounds; the LAST is always verify-only "
                         "(default 3)")
    args = ap.parse_args()

    if args.settle_rounds < 2:
        print("REFUSING: --settle-rounds must be at least 2 — the last round "
              "is verify-only, so one round would write and never check.",
              file=sys.stderr)
        return 2

    if args.apply and not args.backup:
        print("REFUSING: --apply requires --backup (D51(b)).", file=sys.stderr)
        return 2
    if args.apply and os.environ.get("HEROKU_APP_NAME") != PRODUCER_APP:
        seen = os.environ.get("HEROKU_APP_NAME")
        where = f"'{seen}'" if seen else "not a Heroku dyno (HEROKU_APP_NAME unset)"
        print(f"REFUSING --apply: this is {where}, not '{PRODUCER_APP}'.",
              file=sys.stderr)
        return 2

    # Imported here, not at module scope: the verdict logic below is pure and is
    # unit-tested by importing this file, and a module-level DB import would drag
    # the task layer into that test for no reason.
    from app.tasks.base import get_task_session

    verdicts = Counter()
    planned, slates = [], {}

    async with get_task_session() as session:
        rows = (await session.execute(
            text(CANDIDATE_SQL), {"horizon_days": args.horizon_days}
        )).mappings().all()
        clubs = [dict(r) for r in (await session.execute(
            text(CLUBS_SQL), {"leagues": list(POLYMARKET_AWAY_FIRST_LEAGUES)}
        )).mappings().all()]
        print(f"candidate rows (polymarket-only anchor, no espn_id, "
              f"scheduled/live, next {args.horizon_days}d): {len(rows)}")
        print(f"clubs in the {len(POLYMARKET_AWAY_FIRST_LEAGUES)} measured "
              f"leagues: {len(clubs)}")

        for row in rows:
            league = resolve_league(
                clubs, row["home_team_name"], row["away_team_name"]
            )
            if not league:
                verdicts["UNRESOLVED-LEAGUE"] += 1
                continue
            path = ESPN_PATHS.get(league)
            if not path:
                verdicts["NO-ESPN-PATH"] += 1
                continue
            # The authority's slate is a US-Eastern day, so a 02:00Z tip-off
            # sits on the PREVIOUS one. Read both and union.
            fixtures = []
            for delta in (0, -1):
                day = (row["commence_time"] + timedelta(days=delta)).strftime("%Y%m%d")
                key = (path, day)
                if key not in slates:
                    try:
                        slates[key] = espn_slate(path, day)
                    except Exception as exc:  # noqa: BLE001
                        print(f"  espn {path} {day}: FAILED {exc}", file=sys.stderr)
                        slates[key] = []
                fixtures.extend(slates[key])

            verdict, hit = classify(
                row, fixtures, args.kickoff_tolerance_min, league
            )
            verdicts[verdict] += 1
            if verdict != "REVERSED":
                if verdict in ("DISAGREE", "AMBIGUOUS", "NEUTRAL-SITE"):
                    print(f"  {verdict}: {row['id']} "
                          f"{row['home_team_name']} / {row['away_team_name']}")
                continue
            print(f"  REVERSED: {row['id']} [{league}] "
                  f"stored home={row['home_team_name']} -> "
                  f"espn home={hit['home']} (espn {hit['espn_id']})")
            planned.append(row)
            if args.limit and len(planned) >= args.limit:
                break

        print()
        print("VERDICTS:", dict(verdicts))
        print(f"would rewrite: {len(planned)}")

        if not args.apply:
            print("\nDRY RUN — nothing written. Re-run with --apply --backup.")
            return 0
        if not planned:
            print("nothing to do.")
            return 0

        ids = [r["id"] for r in planned]

        # A rename is safe only where there is nothing else oriented to `home`.
        blocked = []
        for row in (await session.execute(
            text(UNHANDLED_SQL), {"ids": ids}
        )).mappings().all():
            reasons = unhandled_reasons(dict(row))
            if reasons:
                blocked.append((row["id"], reasons))
        if blocked:
            for event_id, reasons in blocked:
                print(f"  REFUSING {event_id}: carries {', '.join(reasons)} "
                      f"— this script does not transpose it", file=sys.stderr)
            print(f"\nREFUSING --apply: {len(blocked)} of {len(ids)} rows carry "
                  "orientation-dependent data this script does not transpose. "
                  "A half-swap serves the market's price on the wrong club.",
                  file=sys.stderr)
            return 2

        # 🪤 THE UNDO WAS NOT RE-RUN SAFE. `CREATE TABLE IF NOT EXISTS` plus an
        # unconditional `INSERT` means a second `--apply --backup` APPENDS: the
        # table then holds two rows per `event_id` and the printed restore
        # (`... FROM backup b WHERE b.event_id = e.id`) picks an arbitrary one.
        # The undo goes nondeterministic at exactly the moment it is needed.
        # Every apply now stamps its own `run_id` and the restore is scoped to
        # it, so history accumulates without the rollback ever becoming
        # ambiguous. `ADD COLUMN IF NOT EXISTS` carries the table that already
        # exists on production from the 2026-09-22 run.
        run_id = uuid.uuid4().hex
        await session.execute(text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            " event_id bigint, home_team_name text, away_team_name text,"
            " home_team_id bigint, away_team_id bigint,"
            " win_probability_sources jsonb,"
            " backed_up_at timestamptz DEFAULT now())"
        ))
        await session.execute(text(
            f"ALTER TABLE {BACKUP_TABLE} ADD COLUMN IF NOT EXISTS run_id text"
        ))
        await session.execute(text(
            f"INSERT INTO {BACKUP_TABLE} (event_id, home_team_name,"
            " away_team_name, home_team_id, away_team_id,"
            " win_probability_sources, run_id)"
            " SELECT id, home_team_name, away_team_name, home_team_id,"
            " away_team_id, win_probability_sources, :run_id"
            " FROM events WHERE id = ANY(:ids)"
        ), {"ids": ids, "run_id": run_id})
        await session.commit()
        print(f"\nbacked up {len(ids)} rows into {BACKUP_TABLE} "
              f"as run_id {run_id}")
        print("RESTORE (one command — re-swapping the snapshots is its own"
              " inverse, so it is included; scoped to THIS run):")
        print(f"  UPDATE events e SET home_team_name = b.home_team_name,"
              f" away_team_name = b.away_team_name,"
              f" home_team_id = b.home_team_id, away_team_id = b.away_team_id,"
              f" win_probability_sources = b.win_probability_sources"
              f" FROM {BACKUP_TABLE} b WHERE b.event_id = e.id"
              f" AND b.run_id = '{run_id}';"
              f" UPDATE win_prob_snapshots SET"
              f" home_win_probability = away_win_probability,"
              f" away_win_probability = home_win_probability"
              f" WHERE event_id IN (SELECT event_id FROM {BACKUP_TABLE}"
              f" WHERE run_id = '{run_id}');")

        # One transaction: a swap that moved the names but not the prices is
        # exactly the wrong-price defect the refusal above exists to prevent.
        events_done = (await session.execute(
            text(SWAP_EVENT_SQL), {"ids": ids})).rowcount
        snaps_done = (await session.execute(
            text(SWAP_SNAPSHOTS_SQL), {"ids": ids})).rowcount
        await session.commit()
        # The commit instant, read from the database rather than from this
        # process's clock, because it is the lower bound the snapshot re-stamp
        # is scoped by and the two must be on the same clock.
        swapped_at = (await session.execute(text("SELECT now()"))).scalar_one()
        print(f"transposed {events_done} event rows and {snaps_done} "
              f"win-probability snapshots at {swapped_at.isoformat()}.")

        verdicts, tally = await settle(
            session, ids, swapped_at, args.settle_rounds, args.settle_wait,
        )

        unsettled = sorted(
            e for e, v in verdicts.items() if v not in ("SETTLED", "UNPRICED")
        )
        print("\n" + "=" * 70)
        print(f"SETTLE VERDICT: {dict(tally)}")
        if not unsettled:
            print(f"All {len(ids)} rows verified against the writer's own "
                  f"recomputation after its cycle. The names and the price "
                  f"agree.")
            return 0
        print(f"🔴 {len(unsettled)} of {len(ids)} rows did NOT settle: "
              f"{unsettled}")
        print("The NAMES are repaired and stay repaired — no writer touches "
              "them. The price on these rows disagrees with what the live "
              "writer would compute from those names.")
        print(f"Re-run the settle check, or restore this run with the "
              f"run_id {run_id} command printed above.")
        # Distinct from 2 (refused, nothing written) on purpose: this exit says
        # the swap LANDED and the verification did not come back clean, which
        # is a different thing to do next.
        return 3


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
