"""#5637 — the wrong-sport rows the classifier fix cannot reach on its own.

PILLAR: TRUTH. SHIP: the Redblacks game a reader finds by searching their club
stops being filed under basketball. Today `KXCFLTOTAL-26SEP12OTTTOR`
("Ottawa Redblacks vs Toronto Argonauts: Total Points", kickoff 2026-09-12
20:00Z) is stored `llm_sport_category='basketball'`, and it will stay
basketball forever without this rail.

WHY THE CLASSIFIER FIX IS NOT ENOUGH — CERT-2737'S FINDING, AND IT IS RIGHT
==========================================================================

#5637's ship added step 1b to `_categorize_kalshi_market`: an UNMAPPED Kalshi
series is sorted by the sport tag the venue itself publishes, instead of by name
rules that read club names which happen to be sport words. That stops the defect
being MINTED. It does not move a single row that already exists, because
`app/tasks/kalshi.py` writes the tag through::

    coalesce(nullif(FuturesMarket.llm_sport_category, "other"), sport_category)

which is #1888's honest-empty rule: **an existing real tag is never
overwritten.** So the `other` rows converge on the next poll and the rows that
carry a WRONG SPORT — the ones a reader actually trips over — do not.

CERT-2737 blocked the ship for exactly this: "the poll's coalescing update
preserves every current non-`other` wrong sport, so the cited Redblacks ghost
remains visible". Measured on production 2026-09-12 15:5xZ, over the five
families #5637's venue census named:

    open, wrong, and frozen:   28 rows
      basketball  17   (14 × KXNFLFFPTS NFL "Fantasy Points", 3 × KXCFLTOTAL)
      tennis       9   (KXEFLL1* — AFC Wimbledon, an EFL League One club)
      baseball     1   (KXNWSLGAME — Houston vs Utah Royals)
      motorsports  1   (KXARGPREMDIVGAME — Huracan vs Racing Avellaneda)
    open and 'other':          74 rows  — these the poll converges by itself
    open and already right:    26 rows  — soccer, and the gate leaves them alone

Every one of the 28 is a game being played between 2026-09-12 and 2026-09-17.
This is not a historical tidy-up; it is the current weekend.

🔴 AND THE POLLER CANNOT UNDO IT. That same `nullif(..., 'other')` rail is what
makes this repair durable: once a row reads `football`, the coalesce keeps
`football`. The #1888 comment's warning that "a repair backfill run against
still-open rows is self-undoing" was written about a rail that OVERWROTE with a
fresh seasonal guess; under the shipped coalesce the opposite is true. No
tap-off interlock is needed here, which is why this rail — unlike #5621's — does
not refuse to run outside `bainluck-heavy`.

NO SECOND CLASSIFIER, AND NO SPORT VOCABULARY AT ALL
====================================================

This module contains no sport keywords, no regex over market names, no ticker
literals and no target category. It cannot: it does not know what it is going to
write until the venue tells it. It asks, in order, the exact functions the
Kalshi ingest path calls:

    result = await _resolve_series_tag_result(service, ticker)   # the venue
    target = series_tag_to_category(result.tag)                  # our maps
    verdict = _categorize_kalshi_market(name, None, ticker,
                                        series_tag=result.tag)   # the cascade

If this rail and the poller ever disagree, that is a bug in one of them, not a
policy difference. `test_the_rail_has_no_sport_vocabulary_of_its_own` pins the
absence, which is a stronger guard than the sibling rails can carry — their
`TARGET_CATEGORY` is a sport word by necessity, and this one has no target.

THE GATES — ALL OF THEM, AND WHAT EACH REFUSES
==============================================

A row is written only when every gate passes. Each refusal is counted under its
own name, because "examined 500, changed 3" with no breakdown is the shape that
hides a rail quietly doing nothing (gotcha #53).

1. `not_kalshi` — the predicate says kalshi; the gate re-asserts it. A row from
   another venue has no Kalshi series to ask about.
2. `mapped_ticker` — `sport_keys.py` already maps this ticker, so step 1 of the
   cascade is authoritative and names the LEAGUE, not merely the sport. No
   network call is made and nothing is written. This is the majority of the
   scanned population and it is the reason a pass is cheap.
3. `indeterminate` — the venue could not be asked (429 past its backoff, 5xx,
   timeout, transport error). **Counted, never written, and the row keeps its
   place**: the cursor does not advance past it. A transient failure is not a
   verdict (#36), and this rail exists because one was treated as one.
4. `no_usable_tag` — the venue answered and the answer is not a sport we model
   (`Olympics`, `Television`, `Table Tennis`), or the series carries no tag, or
   there is no such series (404). Falling through is the safe failure; a guess
   is not.
5. `cascade_disagrees` — the venue's tag resolves to X but the SHIPPED cascade,
   given that tag, does not answer X. Something above step 1b spoke (the IPO
   rule, say). **This is the gate that makes the predicate safe rather than
   merely narrow** — the same role gate 2 plays in the enumerated sibling rails.
6. `already_correct` — the stored value is what the venue says. Counted, not
   written. On a healthy repeat pass this is where the whole population lands.

WHY A PREDICATE AND NOT A FROZEN ID LIST
========================================

`repair_kalshi_senate_category` and `repair_kalshi_nhl_prop_category` enumerate
their rows, and the second says a third of these should trigger consolidation.
This is the third, and it deliberately does not enumerate — for a reason that is
about this defect rather than about taste:

**the population is still growing.** The classifier fix is merged but is not yet
running: it lives in a `HEAVY_TASKS` path, so it does nothing until
`bainluck-heavy` carries it (standing notice 48). Every CFL and NFL fixture
ingested between the measurement above and that release mints more wrong rows.
An id list measured today would be incomplete by the time it could be applied,
and silently so.

The enumerated rails freeze ids because their evidence is a name shape and their
population is closed. Here the evidence is the venue's own published tag, which
is strictly stronger than an id list — the NHL module says as much about its own
gate 2: "gate 2 is what makes the id list safe rather than merely short". This
rail keeps that gate and drops the list the gate was protecting.

BOUNDS, ORDER AND RESUMPTION
============================

Newest `commence_time` first: the ship is the games a reader opens this weekend.
Gotcha #41 warns that newest-first starves the old tail, and it would here, so
the tail is never silent — `remaining` is reported on every call and the pass
emits a `next_cursor` until `scan_exhausted` comes back true.

Two budgets, because there are two costs and they are not the same cost:

* `ROW_SCAN_CAP` bounds the DB read and the local classifier work.
* `VENUE_CALL_BUDGET` bounds the only expensive thing — one `/series/{ticker}`
  read per DISTINCT UNMAPPED series. Mapped tickers cost nothing, so a page of
  500 NFL rows spends zero budget. When the budget runs out the pass STOPS,
  reports `terminal="paused_venue_budget"`, and emits a cursor.

The cursor is a keyset on `(commence_time, id)`, never an offset: this repair
removes rows from its own population, so an offset would skip exactly as many
untouched rows as the last page fixed.

🔴 The cursor advances only past RESOLVED rows. A row that came back
`indeterminate` stops the scan where it stands, and `scan_exhausted` additionally
requires `indeterminate == 0`, so "finished" is unreachable while any retryable
row remains. This is CERT-666's correction to the Polymarket sibling, adopted
here rather than re-learned.

D51 — BACKUP AND RESTORE
========================

Every planned change carries its `before` value in the returned payload, on the
dry run as well as the apply, and `apply=True` logs the restore statement. The
undo is one statement per distinct before-value and it is exact, because the
planned ids are enumerated in the payload::

    UPDATE futures_markets SET llm_sport_category = 'basketball'
     WHERE id IN (<the ids reported as changed>);

WHAT IS NEVER WRITTEN
=====================

`llm_sport_category` and nothing else, by Core UPDATE (gotchas #4/#5). No price,
no outcome, no `is_winner`, no resolution field, no `category`, no event row.
"Settled means settled" is untouched: a taxonomy badge is not a result.

THE GHOST EVENT ROWS — AND WHY THEY ARE THIS RAIL'S AFTER ALL
=============================================================

The first cut of this module scoped them out, on the reading that a duplicate
event row is a matching symptom and therefore #2693's under D35 / notice 14.
**CERT-2744 blocked that and was right.** The duplicate a reader sees IS an
`events` row: search serves events, so correcting the market's badge leaves
`q=Redblacks` returning the game twice, and the issue's acceptance unmet.

And the precedent was already in this lane's own tree —
`scripts/repair_5621_phantom_ffpts_events.py` retires exactly this kind of row,
for exactly this cause, for the sibling family. D35 says do not touch the
MATCHER; it does not say leave rows our own classifier minted lying around.

So the event arm retires a ghost only on proof it is a DUPLICATE — four gates,
in `_plan_ghost_events`, of which gate 3 is the one that decides whether a
reader loses a game. Measured 2026-09-12: of 13 candidate ghosts only **4**
have a real counterpart. The other 9 (five NWSL fixtures among them) are the
only row we hold for that match, and retiring one would not remove a duplicate
— it would remove the game. They are refused under `no_real_counterpart`.

The 4 retirable ones include the specimen #5637 was filed about: ghost 15308761
`basketball_other` beside real `americanfootball_cfl` 15307938.

WHAT IS WRITTEN, AND WHAT IS NEVER WRITTEN
==========================================

* `futures_markets.llm_sport_category` — the sport the venue says.
* `events.status` -> `voided` on a PROVEN duplicate, never a delete (`events`
  has 11 FK children, two of them NO ACTION — `repair_2871`'s measurement).
* `futures_markets.event_id` -> NULL on markets of a retired event. This is the
  half that turns hiding into fixing: gotcha #15 says a matcher must never
  re-time-window an already-linked market, so while the wrong link stands the
  prop can never reach the real fixture however good matching gets.

No price, no outcome, no `is_winner`, no resolution field, no `category`.
"Settled means settled" is untouched: a taxonomy badge is not a result, and a
voided duplicate is not a graded game.

ATTENDED ONLY: never wire this to a beat. It is a terminating repair, not a
standing job.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select, text, update

from app.models import Event, FuturesMarket

#: The one actor name this module is allowed to receipt under. Imported at
#: module scope, not passed as a literal at the call site, so that a rename in
#: the closed `match_receipts.ACTORS` set breaks the IMPORT — loudly, at
#: startup, in CI — instead of surviving every test and raising in the middle
#: of an attended production apply that has already committed its writes.
from app.utils.match_receipts import ACTOR_ADMIN_REPAIR

#: What a retired ghost's `status` becomes. `repair_5621_phantom_ffpts_events`
#: writes the same value for the same reason: the row is not deleted (`events`
#: has 11 FK children, two of them NO ACTION), it is marked so no surface shows
#: it, and the D51 restore puts the old status straight back.
RETIRED_STATUS = "voided"

logger = logging.getLogger(__name__)


#: Rows read and locally classified per call. The DB read is not the cost here
#: (the predicate is indexed on `source`/`status`), the venue is — see below.
ROW_SCAN_CAP = 500

#: Distinct UNMAPPED series a single pass may ask the venue about. This is the
#: real budget: a mapped ticker short-circuits with no call at all, so a page of
#: NFL rows spends none of it, while a page of unmapped families spends one per
#: series (never one per row — the resolver caches by series).
#:
#: Sized against the 30s router wall the Polymarket sibling measured: each call
#: is one GET with a 3-attempt backoff, so a budget of 40 leaves room for the
#: scan, the writes and the commit inside the wall.
VENUE_CALL_BUDGET = 40

#: Wall clock for the loop, leaving the post-loop UPDATE/commit and the
#: `remaining` count inside the router's 30s.
LOOP_DEADLINE_SECONDS = 18.0


def restore_sql(rows: list[dict[str, Any]]) -> str:
    """The D51 undo, as statements that can be pasted and run.

    🔴 ONE STATEMENT PER DISTINCT BEFORE-VALUE, not one statement for all rows —
    the mistake the senate sibling shipped first, where the before-value MAP was
    interpolated where a value belongs, producing a line that looks like a
    restore and is not one.

    This rail spans several before-values by construction (the measured rows are
    basketball, tennis, baseball and motorsports at once), so the multi-statement
    case is the normal case here, not a hypothetical.

    🔴 CERT-2744 follow-up `5637-RESTORE-ONLY-CAS-MATCHED-ROWS`: on an APPLY this
    is handed the rows the compare-and-set ACTUALLY CHANGED, never the rows that
    were merely planned. The two differ exactly when a row drifts between the
    scan and the write — and for that row the plan's `before` is a value the
    database no longer holds, so "restoring" it would WRITE A STALE SPORT onto a
    row this rail deliberately left alone. An undo that corrupts a row the repair
    refused to touch is worse than no undo, which is the whole reason D51 asks
    for one.

    On the DRY RUN it is handed the plan, because nothing has changed yet and the
    plan is precisely the offer being reviewed.
    """
    by_before: dict[Optional[str], list[int]] = {}
    for row in rows:
        by_before.setdefault(row["before"], []).append(row["id"])

    lines = []
    for before, ids in sorted(by_before.items(), key=lambda kv: str(kv[0])):
        ids_csv = ", ".join(str(i) for i in sorted(ids))
        value = "NULL" if before is None else f"'{before}'"
        lines.append(
            f"UPDATE futures_markets SET llm_sport_category = {value} "
            f"WHERE id IN ({ids_csv});"
        )
    return "\n".join(lines)


def _population_predicate():
    """Open Kalshi rows carrying a real sport tag — the bug's own output.

    `other` is excluded because the poll already converges those through
    #1888's `nullif` door; including them would make the rail claim credit for
    work ingest does by itself. NULL is excluded for the same reason.
    """
    return and_(
        FuturesMarket.source == "kalshi",
        FuturesMarket.status == "open",
        FuturesMarket.llm_sport_category.isnot(None),
        FuturesMarket.llm_sport_category != "other",
    )


def _parse_after_date(raw: Any):
    """The dispatcher hands `after_date` over as a STRING; the column is a
    timestamp.

    Parsed here rather than left to Postgres' implicit cast so a malformed
    cursor fails on this line, naming itself, instead of deep inside the
    statement as a type error about a column the operator did not mention.
    """
    if raw is None or isinstance(raw, datetime):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


#: Sanity ceiling on the EVENT arm, not a floor. gotcha #53 says an empty result
#: is a response shape rather than an absence — but the inverse matters more for
#: a writer that retires rows a reader can see: this predicate should never match
#: a large population, and if it suddenly does, something upstream changed and a
#: person should look before games start disappearing. Measured 2026-09-12: 13
#: candidate ghosts in these families, of which 4 pass the counterpart proof.
#: Borrowed from `repair_5621_phantom_ffpts_events.MAX_EXPECTED_POPULATION`.
MAX_EXPECTED_GHOST_EVENTS = 60

#: Every candidate ghost event, with its best real counterpart in either
#: orientation. #5621's `_POPULATION_SQL` is the parent of this query and the
#: LATERAL is the same safety gate — but the ANCHOR is different, and that
#: difference is the whole reason this could not simply reuse that script.
#:
#: 🔴 #5621 proves the counterpart with `e2.espn_id IS NOT NULL`. Measured on
#: production 2026-09-12, EVERY real counterpart in these four families has
#: `espn_id` NULL — the real CFL fixture (15307938) and the real EFL League One
#: fixture (15305089) both do — so that gate would find nothing and abort every
#: apply. ESPN coverage is an NFL-shaped assumption.
#:
#: What actually separates a minted ghost from an ingested fixture here is the
#: TEAM BINDING, and it separates them perfectly on all 13 candidates:
#:
#:     ghost  : external_id NULL, commence_time_source 'kalshi',
#:              home_team_id NULL, away_team_id NULL, kalshi markets only
#:     real   : external_id set, commence_time_source 'odds_api',
#:              BOTH team ids bound
#:
#: That is ruling 048's shape stated in columns: the ghost is the id-less claim
#: that CREATED instead of absorbing. Requiring the counterpart to carry bound
#: team ids is a strictly stronger anchor than `espn_id`, because it is what
#: `espn_id` was standing in for — "a schedule provider knows this fixture".
_GHOST_EVENT_SQL = """
WITH ghost AS (
    SELECT e.id,
           e.home_team_name AS h,
           e.away_team_name AS a,
           e.commence_time  AS ct,
           e.status         AS st,
           s.key            AS sport_key
      FROM events e
      JOIN sports s ON s.id = e.sport_id
     WHERE e.id = ANY(:event_ids)
       AND e.external_id IS NULL
       AND e.commence_time_source = 'kalshi'
       AND e.home_team_id IS NULL
       AND e.away_team_id IS NULL
       AND e.home_team_name IS NOT NULL
       AND e.away_team_name IS NOT NULL
       AND NOT EXISTS (
             SELECT 1 FROM futures_markets f
              WHERE f.event_id = e.id AND f.source <> 'kalshi'
           )
)
SELECT g.id, g.h, g.a, g.ct, g.st, g.sport_key,
       r.id AS real_id, r.real_key, r.real_ct
  FROM ghost g
  LEFT JOIN LATERAL (
        SELECT e2.id, s2.key AS real_key, e2.commence_time AS real_ct
          FROM events e2
          JOIN sports s2 ON s2.id = e2.sport_id
         WHERE e2.id <> g.id
           AND e2.home_team_id IS NOT NULL
           AND e2.away_team_id IS NOT NULL
           AND (
                 (lower(e2.home_team_name) LIKE lower(g.h) || '%'
                  AND lower(e2.away_team_name) LIKE lower(g.a) || '%')
              OR (lower(e2.home_team_name) LIKE lower(g.a) || '%'
                  AND lower(e2.away_team_name) LIKE lower(g.h) || '%')
               )
           AND e2.commence_time BETWEEN g.ct - interval '36 hours'
                                    AND g.ct + interval '36 hours'
         ORDER BY abs(extract(epoch FROM (e2.commence_time - g.ct)))
         LIMIT 1
  ) r ON true
"""


async def _record_link_change(market_rows, **kwargs) -> int:
    """LINKLOSS-03's receipt, behind one seam so a test can observe it.

    A thin wrapper rather than a direct call because
    `record_link_change_receipts` opens its OWN session (it must: it re-reads
    each market after the commit to prove the link moved), which a unit test
    with a fake session cannot provide. The name is one of the markers
    `test_every_unlink_writer_in_the_app_records_a_link_change` scans for, so
    the guard still sees this module's unlink as receipted.
    """
    from app.utils.match_receipts import record_link_change_receipts

    return await record_link_change_receipts(market_rows, **kwargs)


def _cursor_for(row) -> dict[str, Any]:
    """The resume cursor that points just past `row`.

    The date half is emitted as an ISO STRING, not a `datetime`, so what the
    payload shows is exactly what a client can hand back as `?after_date=`. A
    cursor a reader has to reformat before it works is a cursor that gets
    reformatted wrongly.
    """
    commence = row.commence_time
    return {
        "after_date": commence.isoformat() if commence is not None else None,
        "after_id": row.id,
    }


def _keyset_after(cursor: Optional[dict[str, Any]]):
    """Keyset gate for `(commence_time DESC, id DESC)`, NULLS LAST.

    Gated on `after_id is not None`, never on a truthy `after_date` — the
    Polymarket sibling's Q496 defect 3 was exactly that, and it made the
    NULL-`commence_time` region unresumable, silently restarting at page one.

    So `after_id` alone is NOT a malformed half-keyset here: it is the cursor
    this rail itself emits once the walk reaches the NULL-`commence_time`
    region, where there is no date to carry. Both keys always travel in
    `next_cursor`; a client echoing it back cannot send a null date as a query
    param, and `after_id` alone is exactly what that echo looks like.
    """
    if not cursor or cursor.get("after_id") is None:
        return None

    after_id = cursor["after_id"]
    after_date = _parse_after_date(cursor.get("after_date"))

    if after_date is None:
        # Already inside the NULL region: only lower ids remain.
        return and_(
            FuturesMarket.commence_time.is_(None),
            FuturesMarket.id < after_id,
        )

    return or_(
        FuturesMarket.commence_time < after_date,
        FuturesMarket.commence_time.is_(None),
        and_(
            FuturesMarket.commence_time == after_date,
            FuturesMarket.id < after_id,
        ),
    )


async def _plan_ghost_events(
    session, target_by_event: dict[int, str]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Which of these events are provable duplicates, and which are not.

    `target_by_event` maps an event id to the sport category the VENUE says its
    Kalshi market is — computed by the caller from the same tag and the same
    shipped cascade that decide the market write. This function adds no opinion
    about sport; it only compares.

    An event is retired only when ALL of these hold:

    1. it was minted by us, not ingested — `external_id` NULL,
       `commence_time_source` 'kalshi', both team ids NULL, Kalshi markets only
       (the SQL above);
    2. its stored sport is NOT the sport the venue says — otherwise it is simply
       an event we made, in the right sport, and retiring it would be vandalism;
    3. a real counterpart exists with BOTH team ids bound, the same two teams in
       either orientation, within 36 hours;
    4. that counterpart is IN the sport the venue says — proving it is the same
       fixture properly filed, not a different sport's lookalike.

    🔴 Gate 3 is the one that decides whether a reader loses a game. Measured on
    production 2026-09-12: of 13 candidate ghosts in these families only **4**
    have a counterpart. The other 9 — five NWSL fixtures among them — are the
    ONLY row we hold for that game. Retiring those would not remove a duplicate,
    it would remove the match from the site. They are refused, counted under
    `no_real_counterpart`, and left exactly as they are; they are the ruling-048
    residual proper and belong to #2693.
    """
    from app.utils.sport_keys import get_llm_category_for_prefix

    refused: dict[str, int] = {}
    if not target_by_event:
        return [], refused

    rows = (
        await session.execute(
            text(_GHOST_EVENT_SQL), {"event_ids": list(target_by_event)}
        )
    ).all()

    # An id the SQL did not return failed gate 1 — it is an ingested event, or it
    # carries a non-Kalshi market. Named rather than inferred from a shortfall.
    returned = {r.id for r in rows}
    missing = len(set(target_by_event) - returned)
    if missing:
        refused["event_not_ours_to_retire"] = missing

    planned: list[dict[str, Any]] = []
    for r in rows:
        target = target_by_event[r.id]
        stored = get_llm_category_for_prefix((r.sport_key or "").split("_")[0])
        if stored == target:
            refused["event_already_right_sport"] = (
                refused.get("event_already_right_sport", 0) + 1
            )
            continue
        if r.real_id is None:
            refused["no_real_counterpart"] = refused.get("no_real_counterpart", 0) + 1
            continue
        real = get_llm_category_for_prefix((r.real_key or "").split("_")[0])
        if real != target:
            refused["counterpart_wrong_sport"] = (
                refused.get("counterpart_wrong_sport", 0) + 1
            )
            continue
        planned.append(
            {
                "event_id": r.id,
                "teams": f"{r.h} vs {r.a}",
                "before_status": r.st,
                "stored_sport": r.sport_key,
                "venue_sport": target,
                "real_event_id": r.real_id,
                "real_sport_key": r.real_key,
            }
        )
    return planned, refused


def event_restore_sql(rows: list[dict[str, Any]]) -> str:
    """The D51 undo for the EVENT arm, grouped by the status each row held.

    Same rule as `restore_sql`: on an apply this is handed the rows the
    compare-and-set matched, never the rows merely planned.
    """
    by_status: dict[Optional[str], list[int]] = {}
    for row in rows:
        by_status.setdefault(row["before_status"], []).append(row["event_id"])

    lines = []
    for status, ids in sorted(by_status.items(), key=lambda kv: str(kv[0])):
        ids_csv = ", ".join(str(i) for i in sorted(ids))
        value = "NULL" if status is None else f"'{status}'"
        lines.append(
            f"UPDATE events SET status = {value} WHERE id IN ({ids_csv});"
        )
    return "\n".join(lines)


async def repair(
    session,
    apply: bool = False,
    after_date: Optional[str] = None,
    after_id: Optional[int] = None,
    **_ignored,
) -> dict[str, Any]:
    """Plan (and optionally apply) the #5637 current-row convergence.

    Returns a payload complete enough to BE the D51 backup: every row it
    changed with its `before`, every refusal under a named reason, a runnable
    `restore_sql`, and a cursor if there is more to do.
    """
    from app.services.kalshi_api import KalshiAPIService
    from app.tasks.kalshi import (
        _categorize_kalshi_market,
        _resolve_series_tag_result,
        series_tag_to_category,
    )

    started = time.monotonic()
    cursor = {"after_date": after_date, "after_id": after_id}

    stmt = (
        select(
            FuturesMarket.id,
            FuturesMarket.name,
            FuturesMarket.source,
            FuturesMarket.external_id,
            FuturesMarket.llm_sport_category,
            FuturesMarket.commence_time,
            FuturesMarket.event_id,
        )
        .where(_population_predicate())
        .order_by(
            FuturesMarket.commence_time.desc().nullslast(),
            FuturesMarket.id.desc(),
        )
        .limit(ROW_SCAN_CAP)
    )
    keyset = _keyset_after(cursor)
    if keyset is not None:
        stmt = stmt.where(keyset)

    rows = (await session.execute(stmt)).all()

    service = KalshiAPIService()
    planned: list[dict[str, Any]] = []
    refused: dict[str, int] = {}
    indeterminate_rows: list[dict[str, Any]] = []
    series_asked: set[str] = set()
    venue_calls = 0
    target_by_event: dict[int, str] = {}
    examined = 0
    stopped_at_unresolved = False
    stopped_reason: Optional[str] = None
    next_cursor: Optional[dict[str, Any]] = None

    def _refuse(reason: str) -> None:
        refused[reason] = refused.get(reason, 0) + 1

    for row in rows:
        if time.monotonic() - started > LOOP_DEADLINE_SECONDS:
            stopped_reason = "deadline"
            break

        # 🔴 Metered on calls ACTUALLY MADE, and checked at the top of the loop
        # rather than in front of the resolve. The first cut guessed, before
        # resolving, whether a row would cost a request — and guessed wrong for
        # a series already in the resolver's cache, charging budget for a free
        # answer and stalling a drain that had spent nothing. The resolver is
        # the only thing that knows (cache hit, TTL suppression and mapped
        # ticker all answer without touching the venue), so it reports
        # `called` and this only counts.
        #
        # Stopping here is conservative: the rows after this one might all be
        # mapped and cost nothing. That is the right way to be wrong — the
        # cursor makes it resumable, and the alternative is a second guess at
        # what the resolver is about to do.
        if venue_calls >= VENUE_CALL_BUDGET:
            stopped_reason = "venue_budget"
            break

        if row.source != "kalshi":
            _refuse("not_kalshi")
            examined += 1
            next_cursor = _cursor_for(row)
            continue

        from app.services.kalshi_api import event_series_ticker

        series = event_series_ticker(row.external_id or "")
        result = await _resolve_series_tag_result(service, row.external_id)
        if result.called:
            venue_calls += 1
            if series:
                series_asked.add(series)

        if result.not_asked:
            # A mapped ticker (or no ticker at all): step 1 of the cascade is
            # authoritative and more specific than any tag. No call was made.
            _refuse("mapped_ticker")
            examined += 1
            next_cursor = _cursor_for(row)
            continue

        if not result.resolved:
            # 🔴 The cursor does NOT advance past this row, and exhaustion is
            # impossible while any of these remain. A transient venue failure is
            # not a verdict about the series (#36) — the reason this rail exists.
            _refuse("indeterminate")
            indeterminate_rows.append({"id": row.id, "series": series})
            examined += 1
            stopped_at_unresolved = True
            stopped_reason = "indeterminate"
            break

        target = series_tag_to_category(result.tag)
        if not target:
            _refuse("no_usable_tag")
            examined += 1
            next_cursor = _cursor_for(row)
            continue

        # THE GATE THAT MAKES THE PREDICATE SAFE. The venue's tag resolves to
        # `target`, but the shipped cascade is what ingest actually runs, and
        # something above step 1b may legitimately override it.
        verdict = _categorize_kalshi_market(
            row.name or "", None, row.external_id, series_tag=result.tag
        )
        if verdict != target:
            _refuse("cascade_disagrees")
            examined += 1
            next_cursor = _cursor_for(row)
            continue

        if row.llm_sport_category == target:
            _refuse("already_correct")
            examined += 1
            next_cursor = _cursor_for(row)
            continue

        planned.append(
            {
                "id": row.id,
                "name": row.name,
                "external_id": row.external_id,
                "before": row.llm_sport_category,
                "after": target,
                "venue_tag": result.tag,
                "event_id": row.event_id,
            }
        )
        # The event this market hangs off is a ghost CANDIDATE — decided later,
        # in one query, by evidence this loop does not have. The venue's answer
        # travels with it so the event arm never re-derives a sport.
        if row.event_id is not None:
            target_by_event[row.event_id] = target
        examined += 1
        next_cursor = _cursor_for(row)

    changed = 0
    drifted: list[dict[str, Any]] = []
    # 🔴 The rows the compare-and-set actually matched — NOT the rows planned.
    # `restore_sql` is built from this on an apply (CERT-2744 follow-up
    # `5637-RESTORE-ONLY-CAS-MATCHED-ROWS`): a drifted row's planned `before` is
    # a value the database no longer holds, so restoring it would write a stale
    # sport onto a row this rail deliberately refused to touch.
    applied_rows: list[dict[str, Any]] = []
    if apply and planned:
        # 🔴 COMPARE-AND-SET on the value the plan was made from, grouped by
        # (before, after) — a blind write by id would not notice the column
        # moving between the scan and the write (CERT-2394's finding).
        by_pair: dict[tuple[Optional[str], str], list[int]] = {}
        for item in planned:
            by_pair.setdefault((item["before"], item["after"]), []).append(item["id"])

        for (before, after), ids in by_pair.items():
            result_ = await session.execute(
                update(FuturesMarket)
                .where(FuturesMarket.id.in_(ids))
                .where(
                    FuturesMarket.llm_sport_category.is_(None)
                    if before is None
                    else FuturesMarket.llm_sport_category == before
                )
                .values(llm_sport_category=after)
                # RETURNING, not rowcount alone: the undo has to name the rows
                # that moved, and a count cannot say WHICH of the ids they were.
                .returning(FuturesMarket.id)
            )
            matched_ids = sorted(r[0] for r in result_.fetchall())
            changed += len(matched_ids)
            applied_rows.extend(
                {"id": i, "before": before, "after": after} for i in matched_ids
            )
            if len(matched_ids) != len(ids):
                # Not an error, and NOT silent: somebody moved a row mid-pass,
                # its plan is stale and it was left alone. "planned 9, changed 7"
                # with no explanation reads as the write half-failing.
                drifted.append(
                    {
                        "before": before,
                        "after": after,
                        "ids": sorted(ids),
                        "matched": len(matched_ids),
                        "skipped_ids": sorted(set(ids) - set(matched_ids)),
                    }
                )

        await session.commit()
        logger.warning(
            "#5637 series-tag category repair applied: %s of %s planned rows "
            "(drifted: %s). D51 RESTORE (matched rows only):\n%s",
            changed,
            len(planned),
            drifted or "none",
            restore_sql(applied_rows),
        )

    # ---------------------------------------------------------------- events --
    # THE ARM CERT-2744 REQUIRED (`5637-RETIRE-WRONG-SPORT-GHOST-EVENTS`).
    # Correcting the market's badge does not remove the duplicate CARD — that is
    # an `events` row, and until it is retired `q=Redblacks` still returns the
    # game twice. Planned even on a dry run so an operator reads what would be
    # retired before deciding.
    ghost_planned, ghost_refused = await _plan_ghost_events(session, target_by_event)

    ghost_retired = 0
    ghost_drifted: list[dict[str, Any]] = []
    ghost_applied: list[dict[str, Any]] = []
    #: Receipts that could not be written for an unlink that DID commit. Empty
    #: is the normal state and the only acceptable one; a non-empty list means
    #: the link-change audit trail (#2705/#2706) has a hole that someone has to
    #: backfill, so it travels in the payload rather than living in a log line.
    link_receipt_errors: list[dict[str, Any]] = []
    ghost_over_ceiling = len(ghost_planned) > MAX_EXPECTED_GHOST_EVENTS

    if apply and ghost_planned and not ghost_over_ceiling:
        by_status: dict[Optional[str], list[int]] = {}
        for item in ghost_planned:
            by_status.setdefault(item["before_status"], []).append(item["event_id"])

        for status, ids in by_status.items():
            res = await session.execute(
                update(Event)
                .where(Event.id.in_(ids))
                .where(
                    Event.status.is_(None)
                    if status is None
                    else Event.status == status
                )
                .values(status=RETIRED_STATUS)
                .returning(Event.id)
            )
            matched_ids = sorted(r[0] for r in res.fetchall())
            ghost_retired += len(matched_ids)
            ghost_applied.extend(
                {"event_id": i, "before_status": status} for i in matched_ids
            )
            if len(matched_ids) != len(ids):
                ghost_drifted.append(
                    {
                        "before_status": status,
                        "ids": sorted(ids),
                        "matched": len(matched_ids),
                        "skipped_ids": sorted(set(ids) - set(matched_ids)),
                    }
                )

        unlinked_by_event: dict[int, list[dict[str, Any]]] = {}
        if ghost_applied:
            # 🔴 UNHOOK, and this is the half that turns hiding into fixing —
            # `repair_5621_phantom_ffpts_events`'s lesson, restated. Gotcha #15:
            # a matcher must never re-time-window an already-linked market, so
            # while the wrong link stands the prop can NEVER reach the real
            # fixture, however good matching gets. Cleared, the next matching
            # pass can attach it to the counterpart the gate already proved
            # exists. Only markets on events we actually retired.
            #
            # 🔴 READ THE MARKETS FIRST — and not from `planned`. The ghost may
            # carry markets this pass never judged (the Wimbledon ghost holds 8
            # from 8 different series), and `previous_event_id` does not survive
            # the update, so LINKLOSS-03's receipt could not be written after it.
            for retired in ghost_applied:
                eid = retired["event_id"]
                market_rows = (
                    await session.execute(
                        select(
                            FuturesMarket.id,
                            FuturesMarket.source,
                            FuturesMarket.external_id,
                            FuturesMarket.name,
                        ).where(FuturesMarket.event_id == eid)
                    )
                ).all()
                unlinked_by_event[eid] = [
                    {
                        "id": m.id,
                        "source": m.source,
                        "external_id": m.external_id,
                        "name": m.name,
                    }
                    for m in market_rows
                ]

            retired_ids = [r["event_id"] for r in ghost_applied]
            await session.execute(
                update(FuturesMarket)
                .where(FuturesMarket.event_id.in_(retired_ids))
                .values(event_id=None)
            )
        await session.commit()

        # LINKLOSS-03: EVERY writer that clears `event_id` receipts the change,
        # or the price leaves a card with no explanation anywhere in the system.
        # Called AFTER the commit, as `record_link_change_receipts` requires —
        # it re-reads each market on a fresh session to prove the link really
        # moved, so a claim published before the commit would read the pre-change
        # row and be downgraded as un-durable.
        #
        # 🔴 THE ACTOR IS THE REGISTRY'S CONSTANT, NEVER THIS MODULE'S NAME.
        # `record_link_change_receipts` validates `actor` against the closed
        # `match_receipts.ACTORS` set and RAISES on an unknown one. The first
        # production apply (2026-09-12, on release v4471 / 19:46Z) passed the string
        # "repair_kalshi_series_tag_category" and died with
        # `unknown link-change actor` — AFTER the commit above, so page 1's
        # four category rows and its one retired ghost event were durable while
        # the operator got a 500 with no census and, worse, no `restore_sql`.
        # The write survived; the only D51 undo for it did not. This module is
        # an admin repair like its four siblings in `admin_matching.py` /
        # `admin_events.py` / `source_intelligence.py`, so it uses the same
        # constant they do. A string literal here cannot be checked by anything.
        #
        # And the comment that used to sit on this line — "it never raises" —
        # was an inherited claim about a helper this module does not own, and
        # it was false. It is made true HERE instead of asserted: a receipt
        # failure is caught, counted into `link_receipt_errors`, and logged
        # loudly, because the record must not be able to cost the thing it
        # records. Swallowed, but never silent (gotcha #53).
        for eid, market_rows in unlinked_by_event.items():
            try:
                await _record_link_change(
                    market_rows,
                    previous_event_id=eid,
                    new_event_id=None,
                    actor=ACTOR_ADMIN_REPAIR,
                    phase="ghost_event_retired_5637",
                )
            except Exception as exc:  # noqa: BLE001 — see the block above
                link_receipt_errors.append(
                    {
                        "event_id": eid,
                        "markets": [m.get("id") for m in market_rows],
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                logger.error(
                    "#5637 ghost-event retirement: the link-change RECEIPT for "
                    "event %s failed (%s). The unlink itself is COMMITTED and "
                    "the census below is correct; the audit row is missing and "
                    "is reported as `link_receipt_errors` in the payload.",
                    eid,
                    exc,
                    exc_info=True,
                )

        logger.warning(
            "#5637 ghost-event retirement applied: %s of %s planned events "
            "(drifted: %s). D51 RESTORE (matched rows only):\n%s",
            ghost_retired,
            len(ghost_planned),
            ghost_drifted or "none",
            event_restore_sql(ghost_applied),
        )

    remaining = (
        await session.execute(
            select(func.count()).select_from(FuturesMarket).where(_population_predicate())
        )
    ).scalar_one()

    # Exhaustion is proven by the pager AND by there being nothing retryable.
    # A short page alone is not enough: CERT-666 found the sibling reporting
    # "finished" on a page whose last row had failed transiently.
    scan_exhausted = (
        len(rows) < ROW_SCAN_CAP
        and stopped_reason is None
        and refused.get("indeterminate", 0) == 0
    )

    if scan_exhausted:
        terminal = "complete"
        next_cursor = None
    elif stopped_at_unresolved:
        terminal = "paused_unresolved"
    elif stopped_reason == "venue_budget":
        terminal = "paused_venue_budget"
    elif stopped_reason == "deadline":
        terminal = "paused_deadline"
    elif not rows:
        terminal = "no_work"
    else:
        terminal = "changed" if apply else "dry_run"

    return {
        "examined": examined,
        "scanned_rows": len(rows),
        "planned": planned,
        "refused": refused,
        "indeterminate_rows": indeterminate_rows,
        # Distinct UNMAPPED series this pass actually asked the venue about.
        # Zero on a page of mapped tickers, which is the common case and is what
        # makes a full drain affordable.
        "series_asked": len(series_asked),
        # Requests actually issued. Equal to `series_asked` within one pass and
        # potentially larger across a drain (a series can be asked once, fail,
        # and be asked again after its suppression lapses) — the budget meters
        # THIS, because this is the cost.
        "venue_calls": venue_calls,
        "venue_call_budget": VENUE_CALL_BUDGET,
        "changed": changed,
        "drifted": drifted,
        # `remaining` counts the POPULATION, which legitimately contains rows the
        # gate refuses (`already_correct`, `mapped_ticker`). It is a floor with a
        # positive value, never a progress bar — exhaustion is `scan_exhausted`.
        "remaining_population_floor": remaining,
        "scan_exhausted": scan_exhausted,
        "stopped_at_unresolved": stopped_at_unresolved,
        "next_cursor": next_cursor,
        # The D51 undo travels WITH the plan, on the dry run too — an operator
        # reads the restore before deciding to apply, not afterwards in a log.
        # On an APPLY this names only the rows the compare-and-set matched; on a
        # DRY RUN it names the plan, which is the offer being reviewed and has
        # changed nothing. `applied_rows` is empty on a dry run, so the choice is
        # made by what actually happened rather than by re-reading `apply`.
        "restore_sql": restore_sql(applied_rows if apply else planned),
        "applied_rows": applied_rows,
        # ---- the ghost-EVENT arm (`5637-RETIRE-WRONG-SPORT-GHOST-EVENTS`) ----
        # The duplicate CARD a reader sees is an `events` row, not a market, so
        # these are reported as their own numbers and never folded into the
        # market counts — a single "changed" spanning two tables could not tell
        # an operator which one moved.
        "ghost_events_planned": ghost_planned,
        "ghost_events_refused": ghost_refused,
        "ghost_events_retired": ghost_retired,
        "ghost_events_drifted": ghost_drifted,
        # A ceiling breach REFUSES the arm rather than trimming it: if this
        # predicate suddenly matches a crowd, something upstream changed and a
        # person should look before games start disappearing from the site.
        "ghost_events_over_ceiling": ghost_over_ceiling,
        "ghost_events_ceiling": MAX_EXPECTED_GHOST_EVENTS,
        "event_restore_sql": event_restore_sql(
            ghost_applied if apply else ghost_planned
        ),
        # Non-empty means an unlink COMMITTED without its link-change receipt.
        # The repair's own numbers above are still true; the audit trail is not
        # complete. It rides the payload so the operator reading the response
        # sees it — a hole recorded only in a log line is a hole nobody finds.
        "link_receipt_errors": link_receipt_errors,
        "terminal": terminal,
    }
