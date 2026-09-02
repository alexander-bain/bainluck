"""Q506 (#2446, D26 = a) — un-settle the 705 fabricated "finished" events.

SHIP: a match that was never played stops showing as a finished game with no
score. Measured on production 2026-09-01: 705 such rows, 468 of them inside the
preceding seven days, 391 holding markets — roughly 67 fabricated
finished-but-never-played events a night, most of them user-visible.

PILLAR: TRUTH. Alex, D26, verbatim *"For D26: A!"* — history gets fixed, not
left dirty, and it gets fixed FROM THE AUTHORITY.

The decision layer, with the full argument for every branch, is
``app/utils/fabricated_final.py``. Read that first; this file is the SQL, the
ESPN adapter, and the paging. Nothing here decides anything: every verdict comes
back from ``disposition_for``, which takes no session and no network.

    POST /api/admin/repairs/fabricated-finals?apply=false             # dry-run ledger
    POST /api/admin/repairs/fabricated-finals?apply=true&since=2026-08-25

    python3 scripts/repair_fabricated_finals.py                       # dry-run ledger
    python3 scripts/repair_fabricated_finals.py --apply --since 2026-08-25

Heroku one-off (gotcha #48 — a non-detached run does not execute in the sandbox;
PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`). Prefer the endpoint.

── THE TWO AUTHORITIES ──────────────────────────────────────────────────────────

Which authority speaks is decided by the sport, not by convenience:

* **ESPN scoreboard** for the head-to-head leagues it has an endpoint for.
* **The venue (Kalshi) as authority of last resort** for the rest —
  ``EVENT-GRAPH-DOCTRINE`` rule 8, and 547 of the 705 rows. CERT-708 blocked the
  first cut of this rail for skipping this: it read "ESPN has no endpoint" as
  "the match never happened" and quarantined all 547 on that. One Kalshi call
  per row, ``/events/{ticker}?with_nested_markets=true``, which is permanent
  where market data purges (gotcha #35) and answered 200 on 69 of 69 sampled.

── PAGING: WHY THE CURSOR IS A KEYSET AND NOT AN OFFSET ─────────────────────────

This repair REMOVES ROWS FROM ITS OWN POPULATION — a quarantined row leaves
``status IN ('closed','completed')`` the moment it is written. CAL-P058 is the
banked lesson: an offset cursor over such a population skips as many untouched
rows as the last page repaired, and it does it silently, because the response
looks perfectly busy. So the cursor is ``(since, after_id)``, both halves of
which only ever move forward and are therefore stable under the rail's writes.

``held`` rows do not drain (that is what held means), so a re-run from the
beginning re-visits them and reaches the same verdict — idempotent, and the
right behaviour: an ESPN outage that held 40 rows on Tuesday should hold or
resolve them on Wednesday, not be forgotten.

**The id half is what makes that safe.** A date is no longer all-or-nothing: the
biggest one carries 193 venue rows against a 50-call budget, so it takes four
calls to walk. With a date-only cursor those four calls would each re-adjudicate
the same leading 50 rows and never reach row 51 — and since HELD rows never
drain, a date whose front is held would spin forever. The keyset closes that.

── THE CALL BUDGETS, AND WHY THEY BOUND THE PAGE ────────────────────────────────

Adjudicating one (sport, date) costs THREE scoreboard calls — the stand-in is
midnight UTC of a ticker date and ESPN's scoreboard day boundary is not UTC
midnight, so the real fixture legitimately lands on either side of it
(``AUTHORITY_DAY_OFFSETS``). Adjudicating one venue row costs ONE Kalshi call.
Either way the page has to be bounded by CALLS, not by rows: the CAL-P002B
defect on the sibling rail was exactly this — ``limit`` bounded the ESPN calls
but not the scan, and every unscoped invocation H12'd at the 30s router wall.

The two budgets are separate because the two calls cost different amounts of
wall clock (a scoreboard is a whole day's slate; a Kalshi event is one object),
and both are checked BEFORE a row is adjudicated rather than after — a row
adjudicated against an authority we could not afford to ask gets the
empty-answer verdict, and on this rail that is a void.

── WHAT IT WRITES, AND THE COMPARE-AND-SET ON EVERY WRITE ───────────────────────

Five statements, one per writing disposition, and **every one of them re-states
the whole population predicate in its own WHERE clause**. A row that acquires a
score, or is settled differently, or has its provenance corrected between the
census and the write is counted ``raced`` and left exactly as it is. Gotcha #21
in the form that matters here: a real result outranks any schedule correction,
including one this rail computed forty seconds ago.

``completed_at`` is always overwritten on the two paths that move the start, and
it is derived by ``event_completion.derive_completed_at`` from the last real
post-commence snapshot — never ``now()`` (gotcha #22). For this cohort that
derivation returns NULL, because these rows carry no snapshots at all (Kalshi
prices live in ``futures_markets``, not ``odds_snapshots``). A NULL there is a
visible gap the next repair can fill; a plausible-looking ``now()`` is a wrong
value nothing will ever question. Overwriting rather than leaving it is also
what keeps gotcha #46 true: the stale completion was computed from the STAND-IN
start, so moving the start forward to the authority's real time would otherwise
invert the invariant on rows that currently satisfy it.

``espn_id`` is deliberately NOT written. #1947 holds three ``espn_id`` values
shared by genuinely different games, and anchoring 158 rows off a name match
would seed that class rather than drain it. The anchor channel is #1946's job.

``futures_markets`` is not touched at all — see the module docstring of
``app/utils/fabricated_final.py`` for why the 1,198 attached markets stay
attached.
"""
import argparse
import asyncio
import os
import sys
from datetime import date as _date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.event_completion import (  # noqa: E402
    LAST_POST_COMMENCE_SNAPSHOT_SQL as _LAST_SNAPSHOT_SQL,
    TICKER_DERIVED_COMMENCE_SOURCE,
    derive_completed_at,
)
from app.utils.fabricated_final import (  # noqa: E402
    AUTHORITY_DAY_OFFSETS,
    DERIVED_SOURCE_PARAM,
    DISPOSITIONS,
    FABRICATED_FINAL_PREDICATE,
    FINAL_STATUS,
    NOT_ON_THE_AUTHORITY_SLATE,
    QUARANTINED,
    REPAIRED_FINAL,
    UNSETTLED,
    UNSETTLED_STATUS,
    VENUE_COMMENCE_SOURCE,
    VENUE_CONFIRMED,
    VENUE_HAS_NO_RECORD,
    VENUE_SETTLED_WITHOUT_A_RESULT,
    VOID_STATUS,
    AuthorityVerdict,
    VenueVerdict,
    adapter_can_speak_for,
    disposition_for,
    has_schedule_of_record,
    venue_verdict_from_event,
)
from app.utils.name_normalization import names_match  # noqa: E402

#: The ticker date, recovered exactly. The stand-in IS midnight UTC of the date
#: parsed out of the Kalshi ticker, so a UTC cast returns that date and nothing
#: else. Deliberately NOT the ``America/New_York`` cast the sibling rail uses:
#: there the timestamps are real ET game times, here the value is a UTC-midnight
#: artefact and any other zone shifts it a day and asks ESPN the wrong question.
_TICKER_DATE_EXPR = "(e.commence_time AT TIME ZONE 'UTC')::date"

# STEP 1 — the cheap bound. A plain GROUP BY over the population predicate: no
# correlated subqueries, no per-row work, no network. This is what the page
# selection slices, and it runs BEFORE anything expensive (CAL-P002B).
_DATES_SQL = f"""
    SELECT {_TICKER_DATE_EXPR} AS ticker_date,
           COUNT(*) AS n,
           COUNT(DISTINCT s.key) AS sports
    FROM events e
    LEFT JOIN sports s ON s.id = e.sport_id
    WHERE {FABRICATED_FINAL_PREDICATE}
      AND (:since IS NULL OR {_TICKER_DATE_EXPR} >= CAST(:since AS date))
      AND (:sport IS NULL OR s.key = :sport)
    GROUP BY 1
    ORDER BY 1
"""

# STEP 2 — candidate rows for the SELECTED dates only.
#
# `venue_ticker` is the KALSHI EVENT TICKER, and it is the whole venue-authority
# channel. `futures_markets.external_id` holds the EVENT ticker, not a market
# ticker — measured 2026-09-01, `/markets/{external_id}` 404s on every row of
# this cohort while `/events/{external_id}` returns 200 on 69 of 69. MIN() picks
# one deterministically: an event's markets all belong to the same Kalshi event,
# so any of them names the same venue record.
#
# ORDER BY e.id, not `s.key, e.id`: the id is the within-date cursor
# (`after_id`), so the scan order has to BE the cursor order or a resumed
# page would skip rows. Sport grouping is unaffected — it is done in Python.
_CANDIDATE_SQL = f"""
    SELECT e.id AS event_id,
           s.key AS sport_key,
           e.status AS ev_status,
           e.home_team_name, e.away_team_name,
           e.commence_time, e.completed_at, e.espn_id,
           {_TICKER_DATE_EXPR} AS ticker_date,
           (SELECT MIN(fm.external_id)
              FROM futures_markets fm
             WHERE fm.event_id = e.id
               AND fm.source = 'kalshi'
               AND fm.external_id IS NOT NULL) AS venue_ticker
    FROM events e
    LEFT JOIN sports s ON s.id = e.sport_id
    WHERE {FABRICATED_FINAL_PREDICATE}
      AND {_TICKER_DATE_EXPR} = ANY(CAST(:dates AS date[]))
      AND (:sport IS NULL OR s.key = :sport)
      AND (:after_id IS NULL OR e.id > CAST(:after_id AS bigint))
    ORDER BY e.id
"""

_POPULATION_SQL = f"""
    SELECT COUNT(*) AS n
    FROM events e
    LEFT JOIN sports s ON s.id = e.sport_id
    WHERE {FABRICATED_FINAL_PREDICATE}
      AND (:sport IS NULL OR s.key = :sport)
"""

# ── The three writes ─────────────────────────────────────────────────────────
#
# Each restates the population predicate inline (it cannot use the shared
# fragment: that one is written against the `events e` alias of a SELECT with a
# join, and an UPDATE has no join here). The guard test
# `test_every_write_is_compare_and_set_on_the_population` asserts each of them
# carries all four conjuncts, so the duplication cannot rot into a bare
# `WHERE id = :event_id`.

_PRECONDITION = """
      AND status IN ('closed', 'completed')
      AND home_score IS NULL
      AND away_score IS NULL
      AND commence_time_source = ANY(:derived_sources)
"""

_WRITE_FINAL_SQL = f"""
    UPDATE events
       SET home_score = :home_score,
           away_score = :away_score,
           status = '{FINAL_STATUS}',
           completed_at = :completed_at,
           commence_time = :commence_time,
           commence_time_source = 'espn'
     WHERE id = :event_id
     {_PRECONDITION}
"""

_WRITE_UNSETTLE_SQL = f"""
    UPDATE events
       SET status = '{UNSETTLED_STATUS}',
           completed_at = NULL,
           commence_time = :commence_time,
           commence_time_source = 'espn'
     WHERE id = :event_id
     {_PRECONDITION}
"""

# The quarantine carries ONE extra conjunct the other two do not need:
# `espn_id IS NULL`. A row anchored to an authority is not a phantom, whatever
# else is true of it, and voiding one would hide a real game behind a status no
# surface reads. Measured 0/705 today — this is a guard on the rail's future,
# not a filter that is doing work now, and it is labelled so rather than
# presented as evidence.
_WRITE_VOID_SQL = f"""
    UPDATE events
       SET status = '{VOID_STATUS}'
     WHERE id = :event_id
       AND espn_id IS NULL
     {_PRECONDITION}
"""

# ── The two venue writes ─────────────────────────────────────────────────────
#
# Both take their start from the venue's own `occurrence_datetime` and stamp
# `commence_time_source = 'kalshi_event'`, which is NOT in
# `DERIVED_COMMENCE_SOURCES`. That is load-bearing three times over: it records
# a REPORTED start where a stand-in was, it lets CERT-690's producer doors run a
# clock from the row again, and it DRAINS the row out of this rail's own
# population so a re-run does not re-read it from Kalshi forever.
#
# Neither writes a score. The venue names a WINNER, not a score, and the
# directive's floor is that we do not invent one.

#: The venue settled on a real result: the match was played and is over. The
#: row's `closed` status was right; only its start was fabricated. Status is
#: deliberately UNTOUCHED — a `completed` flip would promise a result the row
#: still has no score for, and Alex's settled-language ruling is that a settled
#: surface shows the result.
_WRITE_VENUE_CONFIRM_SQL = f"""
    UPDATE events
       SET commence_time = :commence_time,
           commence_time_source = '{VENUE_COMMENCE_SOURCE}',
           completed_at = :completed_at
     WHERE id = :event_id
     {_PRECONDITION}
"""

#: The venue is still taking bets, so the match is NOT over. Clear the
#: settlement exactly as the ESPN path does, and take the venue's real start.
#:
#: The SOURCE is bound rather than inlined here, and only here. Clearing a FINAL
#: the venue contradicts is worth doing whether or not we also learned a real
#: start, so on the rare event that carries no unambiguous `occurrence_datetime`
#: this still runs — keeping the row's existing start and its existing
#: `kalshi_ticker` provenance, which is honest: we did not learn a start, so we
#: must not stamp one as reported. The row drains anyway, on the status.
_WRITE_VENUE_UNSETTLE_SQL = f"""
    UPDATE events
       SET status = '{UNSETTLED_STATUS}',
           completed_at = NULL,
           commence_time = :commence_time,
           commence_time_source = :commence_time_source
     WHERE id = :event_id
     {_PRECONDITION}
"""

#: Scoreboard calls one invocation may spend. 30 x (one request + the client's
#: 0.5s courtesy sleep) is ~20s, inside the 30s Heroku router wall with room for
#: the queries either side. Three calls per adjudicable (sport, date), so ten
#: such groups per page.
MAX_AUTHORITY_CALLS = 30

#: VENUE calls one invocation may spend, budgeted separately from the ESPN one
#: because the two cost wildly different amounts of wall clock: an ESPN
#: scoreboard is a whole day's slate (the US Open payload is 625 competitions),
#: a Kalshi event is one small object. Sized so the worst case — both budgets
#: fully spent in one request — stays inside the 30s Heroku router wall:
#: 30 x ~0.6s + 50 x ~0.08s ≈ 22s.
#:
#: This bounds the page; it does NOT bound the drain, and it must not be raised
#: to try to. The biggest single date carries 193 venue rows, so that date takes
#: four calls to walk — which is exactly what `next_after_id` is for.
MAX_VENUE_CALLS = 50

#: Max DATES per invocation, independent of the call budget — a page of pure
#: no-schedule-of-record dates costs no ESPN calls at all and would otherwise
#: try to void the whole backlog in one transaction.
DEFAULT_DATE_LIMIT = 5


def _match_fixture(row, slate) -> tuple[dict | None, bool, bool]:
    """Find ``row``'s fixture in the slate. ``(fixture, swapped, any_side_seen)``.

    ``names_match`` is the registry's own predicate — the same one Step 3 of
    ``find_or_create_event`` uses to decide whether two rows are the same game —
    so a pairing this rail calls a match is a pairing the matcher would too.

    BOTH sides must match. A single-side match is how "Manchester United vs
    Everton" becomes "Manchester United vs Fulham", and on this rail the cost of
    a wrong match is a wrong SCORE written onto a real row.

    ``swapped`` is returned rather than silently accepted. The pairing being
    present is enough to prove the fixture EXISTS (so it is not quarantined),
    but it is not enough to know which of OUR two names is really the home side,
    and a score written to the wrong side is the CAL-P002 corruption class.
    ``disposition_for`` holds those rows.

    ``any_side_seen`` is the SINGLE-side signal, and it exists precisely because
    a single side is not a match. It is never used to identify a fixture — only
    to answer "is the authority even covering this competition today, or is our
    matcher the thing that failed?". Without it, ``names_match``'s deliberate
    suffix-only conservatism ("Brighton" does not match "Brighton & Hove
    Albion") reads as the authority having no record, and the row is VOIDED.
    """
    home = row.home_team_name or ""
    away = row.away_team_name or ""
    if not home or not away:
        return (None, False, False)

    any_side = False
    for fixture in slate:
        f_home = fixture.get("home") or ""
        f_away = fixture.get("away") or ""
        if not f_home or not f_away:
            continue
        if names_match(home, f_home) and names_match(away, f_away):
            return (fixture, False, True)
        if names_match(home, f_away) and names_match(away, f_home):
            return (fixture, True, True)
        if (names_match(home, f_home) or names_match(home, f_away)
                or names_match(away, f_home) or names_match(away, f_away)):
            any_side = True
    return (None, False, any_side)


async def _fetch_slate(espn, sport_key: str, ticker_date: _date) -> tuple[bool, list[dict]]:
    """``(reachable, fixtures)`` for the three-day window around ``ticker_date``.

    Reachability is ANDed across the three days on purpose: if any one of them
    failed we do not know the window, and a partial window is exactly the shape
    that makes a real fixture look absent. Gotcha #53 — the whole point of this
    function returning a flag at all.
    """
    fixtures: list[dict] = []
    reachable = True
    for offset in AUTHORITY_DAY_OFFSETS:
        day = ticker_date + timedelta(days=offset)
        ok, events = await espn.get_scoreboard_reachable(sport_key, day.strftime("%Y%m%d"))
        if not ok:
            reachable = False
            continue
        for ee in events:
            fixtures.append({
                "espn_id": ee.espn_id,
                "status": ee.status,
                "home": (ee.home_team.name if ee.home_team else None),
                "away": (ee.away_team.name if ee.away_team else None),
                "home_score": ee.home_score,
                "away_score": ee.away_score,
                "start": ee.date,
                # ESPN's own sport-independent "is it over", carried because the
                # MAPPED status is not: soccer finals arrive as
                # `status_full_time`, never `post`. See `authority_says_final`.
                "completed": ee.completed,
                "state": ee.state,
            })
    return (reachable, fixtures)


async def _fetch_venue(kalshi, venue_ticker: str) -> VenueVerdict:
    """The venue authority of last resort for ONE event (doctrine rule 8).

    One call per EVENT, not per market: ``with_nested_markets=true`` brings back
    every market's status, result and ``occurrence_datetime`` in the same
    payload, so an event with twelve side-markets still costs one request.

    ``get_event_reachable``, never ``get_event``: the latter returns ``None``
    for a 404 AND for a failed request, and the whole reason this rail exists in
    its current form is that reading a failure as an absence voids real events.
    """
    reachable, event = await kalshi.get_event_reachable(venue_ticker)
    return venue_verdict_from_event(event, reachable=reachable)


async def _derive_completions(session, event_ids: list[int], rows_by_id: dict) -> dict:
    """``{event_id: completed_at or None}`` from the last real post-commence
    snapshot, batched. Shares ``LAST_POST_COMMENCE_SNAPSHOT_SQL`` with both
    staleness nets and the CAL-P002 rail, so the producer and every repair
    answer "when did this end" the same way."""
    from sqlalchemy import text

    if not event_ids:
        return {}
    now = datetime.now(timezone.utc)
    snaps = {
        r.event_id: r.last_snap
        for r in (
            await session.execute(text(_LAST_SNAPSHOT_SQL), {"event_ids": event_ids})
        ).all()
    }
    return {
        eid: derive_completed_at(
            snaps.get(eid), rows_by_id[eid].commence_time, now=now
        )
        for eid in event_ids
    }


async def repair(
    session,
    apply: bool,
    *,
    limit: int = None,
    sport: str = None,
    since: str = None,
    after_id: int = None,
) -> dict:
    """Session-taking core, shared by the CLI and
    ``POST /api/admin/repairs/fabricated-finals`` so the two cannot drift.

    Commits per DATE, so a router timeout leaves consistent, resumable progress.

    ── THE CURSOR IS ``(since, after_id)``, AND THE SECOND HALF IS NEW ────

    A date used to be all-or-nothing. That was survivable while the only
    per-row cost was free (a sport with no ESPN endpoint was decided from the
    sport key alone), and the venue authority ended it: **the biggest single
    date in this population carries 193 venue rows**, measured 2026-09-01, and
    each one is a Kalshi request.

    A date bigger than the call budget therefore has to be resumable IN THE
    MIDDLE, and "resume where the budget ran out" cannot be spelled with a date
    alone. Without the row half of the cursor the rail would re-adjudicate the
    same leading rows every call and never reach the tail — and the rows most
    likely to sit at the front are exactly the ones that do not drain (a HELD
    row stays in the population by design). That is the starvation CERT-708
    filed as ``Q506-MIDDATE-CURSOR-PROGRESS``; the keyset cursor closes it
    instead of leaving it owed.
    """
    from sqlalchemy import text

    from app.services.espn_api import get_espn_service
    from app.services.kalshi_api import KalshiAPIService

    date_limit = int(limit) if limit else DEFAULT_DATE_LIMIT
    bind = {"derived_sources": DERIVED_SOURCE_PARAM, "sport": sport}

    before = (await session.execute(text(_POPULATION_SQL), bind)).scalar() or 0

    date_rows = (
        await session.execute(text(_DATES_SQL), {**bind, "since": since})
    ).all()

    # ── Page selection: bounded by DATES and by the ESPN call budget ─────────
    selected: list[_date] = []
    projected_calls = 0
    next_since = None
    for dr in date_rows:
        if len(selected) >= date_limit:
            next_since = dr.ticker_date
            break
        cost = 3 * int(dr.sports or 0)  # worst case: every sport adjudicable
        if selected and projected_calls + cost > MAX_AUTHORITY_CALLS:
            next_since = dr.ticker_date
            break
        selected.append(dr.ticker_date)
        projected_calls += cost

    ledger: list[dict] = []
    counts = {d: 0 for d in DISPOSITIONS}
    reasons: dict[str, int] = {}
    written = {REPAIRED_FINAL: 0, UNSETTLED: 0, QUARANTINED: 0, VENUE_CONFIRMED: 0}
    raced = 0
    authority_calls = 0
    venue_calls = 0
    #: The keyset watermark. Seeded from the incoming cursor so that a page
    #: which spends its budget before adjudicating ANYTHING hands back the
    #: position it started from, rather than `None` — which would silently
    #: restart the date and re-read every row ahead of the cursor.
    last_id = after_id
    #: Doctrine rule 8: a league with no schedule of record gets NAMED, so the
    #: decision to chase a source is a rule and not a judgement. Counted here
    #: because this rail is the only thing that walks the whole cohort.
    no_authority_leagues: dict[str, int] = {}
    #: Quarantines where the authority DID have a slate and simply did not carry
    #: the fixture — reported separately from the 547 no-schedule-of-record ones
    #: because they are a different claim and a much smaller, checkable list.
    #: Measured on the real population 2026-09-01: NINE, and eight of them are a
    #: SECOND defect showing through — a second-tier fixture filed under the
    #: top-flight key (`Cottbus v Greuther Fürth` and `Heidenheim v Dresden` as
    #: Bundesliga; `Albacete v Oviedo`, `Girona v Las Palmas`,
    #: `Leganes v Eldense`, `Cordoba v Granada` as La Liga), the #1081
    #: sport-misclassification class. Voiding them is still right — the row
    #: asserts a top-flight FINAL the top-flight authority does not have — but
    #: they are named here so the misclassification can be chased instead of
    #: quietly disappearing with them.
    absent_from_slate: list[dict] = []

    espn = get_espn_service() if selected else None
    kalshi = KalshiAPIService() if selected else None
    budget_spent = False
    #: Row half of the cursor. Consumed on the FIRST selected date only — it is
    #: a position within that date, and carrying it onto the next one would skip
    #: every lower-id row there.
    cursor_after = after_id
    next_after_id = None

    try:
        for ticker_date in selected:
            if budget_spent:
                # The call budget ran out inside an earlier date. Stop rather
                # than walk on: the cursor already points at the unfinished
                # position, and adjudicating the rest against authorities we
                # cannot afford to ask is how a hold becomes a void.
                break
            rows = (
                await session.execute(
                    text(_CANDIDATE_SQL),
                    {**bind, "dates": [ticker_date], "after_id": cursor_after},
                )
            ).all()
            cursor_after = None  # position applies to the resumed date only
            if not rows:
                continue

            rows_by_id = {r.event_id: r for r in rows}
            completions = await _derive_completions(
                session, [r.event_id for r in rows], rows_by_id
            )

            # One slate per (sport, date), fetched lazily and cached, so strict
            # id ordering costs nothing: eight EPL rows interleaved with eighty
            # esports rows still buy the EPL slate exactly once.
            slates: dict[str, tuple[bool, list[dict]]] = {}
            date_ledger: list[tuple] = []

            for r in rows:
                sport_key = r.sport_key
                espn_sport = (
                    has_schedule_of_record(sport_key)
                    and adapter_can_speak_for(sport_key)
                )
                needs_venue = not has_schedule_of_record(sport_key) and r.venue_ticker

                # ── Budget, checked BEFORE the row is adjudicated ────────────
                # Stopping here rather than after is the whole point: a row
                # adjudicated against an authority we could not afford to ask
                # gets the empty-slate verdict, and on this rail that is a void.
                if espn_sport and sport_key not in slates:
                    if authority_calls + len(AUTHORITY_DAY_OFFSETS) > MAX_AUTHORITY_CALLS:
                        next_since, next_after_id = ticker_date, last_id
                        budget_spent = True
                        break
                elif needs_venue:
                    if venue_calls + 1 > MAX_VENUE_CALLS:
                        next_since, next_after_id = ticker_date, last_id
                        budget_spent = True
                        break

                slate: list[dict] = []
                reachable = False
                if espn_sport:
                    if sport_key not in slates:
                        slates[sport_key] = await _fetch_slate(
                            espn, sport_key, ticker_date
                        )
                        authority_calls += len(AUTHORITY_DAY_OFFSETS)
                    reachable, slate = slates[sport_key]

                venue: VenueVerdict = None
                if not has_schedule_of_record(sport_key):
                    if r.venue_ticker:
                        venue = await _fetch_venue(kalshi, r.venue_ticker)
                        venue_calls += 1
                    # else: venue stays None -> HELD, `no_venue_record_channel`.

                fixture, swapped, any_side = (
                    _match_fixture(r, slate) if slate else (None, False, False)
                )
                verdict = AuthorityVerdict(
                    reachable=reachable,
                    slate_size=len(slate),
                    fixture=fixture,
                    orientation_swapped=swapped,
                    any_side_on_slate=any_side,
                )
                disposition, reason = disposition_for(sport_key, verdict, venue)
                counts[disposition] += 1
                reasons[reason] = reasons.get(reason, 0) + 1
                last_id = r.event_id

                if not has_schedule_of_record(sport_key):
                    # Doctrine rule 8's trigger fires on the LEAGUE, not on the
                    # verdict: the league has no schedule of record whether the
                    # venue then confirmed the match or not, and that is exactly
                    # the fact rule 8 wants named.
                    no_authority_leagues[sport_key or "<unknown>"] = (
                        no_authority_leagues.get(sport_key or "<unknown>", 0) + 1
                    )
                if reason in (
                    NOT_ON_THE_AUTHORITY_SLATE,
                    VENUE_HAS_NO_RECORD,
                    VENUE_SETTLED_WITHOUT_A_RESULT,
                ):
                    # Every quarantine, named individually. These are the only
                    # rows this rail removes from the site, so they are the ones
                    # an operator must be able to check by hand — a bare count
                    # is exactly what would hide a matcher or vocabulary
                    # regression here.
                    absent_from_slate.append({
                        "event_id": r.event_id,
                        "sport_key": sport_key,
                        "ticker_date": str(r.ticker_date),
                        "matchup": f"{r.home_team_name} v {r.away_team_name}",
                        "reason": reason,
                        "slate_size": len(slate),
                        "venue_ticker": r.venue_ticker,
                    })
                date_ledger.append((r, disposition, reason, fixture, venue))
                if len(ledger) < 500:
                    ledger.append({
                        "event_id": r.event_id,
                        "sport_key": sport_key,
                        "ticker_date": str(r.ticker_date),
                        "status": r.ev_status,
                        "home": r.home_team_name,
                        "away": r.away_team_name,
                        "disposition": disposition,
                        "reason": reason,
                        "authority_final": (
                            None if not fixture
                            else f"{fixture.get('home_score')}-{fixture.get('away_score')}"
                        ),
                    })

            if apply:
                for r, disposition, _reason, fixture, venue in date_ledger:
                    params = {
                        "event_id": r.event_id,
                        "derived_sources": DERIVED_SOURCE_PARAM,
                    }
                    if disposition == REPAIRED_FINAL:
                        res = await session.execute(text(_WRITE_FINAL_SQL), {
                            **params,
                            "home_score": fixture["home_score"],
                            "away_score": fixture["away_score"],
                            "completed_at": completions.get(r.event_id),
                            "commence_time": fixture["start"] or r.commence_time,
                        })
                    elif disposition == VENUE_CONFIRMED:
                        res = await session.execute(text(_WRITE_VENUE_CONFIRM_SQL), {
                            **params,
                            "completed_at": completions.get(r.event_id),
                            "commence_time": venue.occurrence_time,
                        })
                    elif disposition == UNSETTLED and fixture is None:
                        # The VENUE unsettled it. Take its start when it gave an
                        # unambiguous one and leave the provenance alone when it
                        # did not — a `kalshi_event` stamp over a start we never
                        # learned would be the same lie this rail exists to undo.
                        occurrence = venue.occurrence_time if venue else None
                        res = await session.execute(text(_WRITE_VENUE_UNSETTLE_SQL), {
                            **params,
                            "commence_time": occurrence or r.commence_time,
                            "commence_time_source": (
                                VENUE_COMMENCE_SOURCE if occurrence
                                else TICKER_DERIVED_COMMENCE_SOURCE
                            ),
                        })
                    elif disposition == UNSETTLED:
                        res = await session.execute(text(_WRITE_UNSETTLE_SQL), {
                            **params,
                            "commence_time": fixture["start"] or r.commence_time,
                        })
                    elif disposition == QUARANTINED:
                        res = await session.execute(text(_WRITE_VOID_SQL), params)
                    else:
                        continue
                    n = res.rowcount or 0
                    if n:
                        written[disposition] += n
                    else:
                        raced += 1
                await session.commit()
    finally:
        # The Kalshi client owns an httpx.AsyncClient. The ESPN service is a
        # process-wide singleton and is deliberately NOT closed here.
        if kalshi is not None:
            await kalshi.close()

    after = (await session.execute(text(_POPULATION_SQL), bind)).scalar() or 0

    return {
        "population_before": before,
        "population_after": after,
        "dates_selected": [str(d) for d in selected],
        "dates_remaining": max(0, len(date_rows) - len(selected)),
        "next_since": str(next_since) if next_since else None,
        # The row half of the keyset cursor. Non-null ONLY when a date was cut
        # in the middle, and it must be passed back WITH `next_since` — the pair
        # is the position, and `since` alone would re-read the whole date.
        "next_after_id": next_after_id,
        "authority_calls": authority_calls,
        "venue_calls": venue_calls,
        "dispositions": counts,
        "reasons": reasons,
        "written": written if apply else {k: 0 for k in written},
        "raced": raced,
        # Doctrine rule 8's trigger, as data rather than a judgement call.
        "no_schedule_of_record_leagues": dict(
            sorted(no_authority_leagues.items(), key=lambda kv: -kv[1])
        ),
        # Every row this rail takes off the site, named individually — never a
        # bare count. This is where a matcher regression, a venue-vocabulary
        # drift, or a sport misclassification shows up first.
        "quarantined_rows": absent_from_slate,
        "ledger": ledger,
        "applied": apply,
    }


async def _main():
    from app.tasks.base import get_task_session

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="commit (default: dry run)")
    ap.add_argument("--limit", type=int, default=None, help="max DATES this call")
    ap.add_argument("--sport", default=None, help="sport-key filter")
    ap.add_argument("--since", default=None, help="cursor: YYYY-MM-DD, inclusive")
    ap.add_argument(
        "--after-event-id", type=int, default=None,
        help="cursor: row position WITHIN --since's date (from next_after_id)",
    )
    args = ap.parse_args()

    async with get_task_session() as session:
        out = await repair(
            session, args.apply, limit=args.limit, sport=args.sport,
            since=args.since, after_id=args.after_id,
        )

    import json

    ledger = out.pop("ledger", [])
    print(json.dumps(out, indent=2, default=str))
    for row in ledger[:60]:
        print(
            f"  {row['event_id']:>9}  {row['sport_key']:<28} {row['ticker_date']}  "
            f"{row['disposition']:<15} {row['reason']}"
        )
    if not args.apply:
        print("\nDRY RUN — no writes. Re-run with --apply to commit.")


if __name__ == "__main__":
    asyncio.run(_main())
