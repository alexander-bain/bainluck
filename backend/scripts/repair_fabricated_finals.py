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

── PAGING: WHY THE CURSOR IS A DATE AND NOT AN OFFSET ───────────────────────────

This repair REMOVES ROWS FROM ITS OWN POPULATION — a quarantined row leaves
``status IN ('closed','completed')`` the moment it is written. CAL-P058 is the
banked lesson: an offset cursor over such a population skips as many untouched
rows as the last page repaired, and it does it silently, because the response
looks perfectly busy. So the unit of work is a DATE and the cursor is ``since``,
which only ever moves forward and is therefore stable under the rail's own
writes.

``held`` rows do not drain (that is what held means), so a re-run from the
beginning re-visits them and reaches the same verdict — idempotent, and the
right behaviour: an ESPN outage that held 40 rows on Tuesday should hold or
resolve them on Wednesday, not be forgotten.

── THE ESPN BUDGET, AND WHY IT BOUNDS THE PAGE ──────────────────────────────────

Adjudicating one (sport, date) costs THREE scoreboard calls — the stand-in is
midnight UTC of a ticker date and ESPN's scoreboard day boundary is not UTC
midnight, so the real fixture legitimately lands on either side of it
(``AUTHORITY_DAY_OFFSETS``). The client sleeps ``rate_limit_delay`` between
requests, so the page has to be bounded by CALLS, not by rows: the CAL-P002B
defect on the sibling rail was exactly this — ``limit`` bounded the ESPN calls
but not the scan, and every unscoped invocation H12'd at the 30s router wall.

Dates whose sports have no schedule of record cost ZERO calls, and they are the
bulk of this population (547 of 705), so a page can be large or small depending
on what is in it. The rail stops selecting dates when the next one would exceed
``MAX_AUTHORITY_CALLS`` and hands back ``next_since``.

── WHAT IT WRITES, AND THE COMPARE-AND-SET ON EVERY WRITE ───────────────────────

Three statements, one per writing disposition, and **every one of them re-states
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
    derive_completed_at,
)
from app.utils.fabricated_final import (  # noqa: E402
    AUTHORITY_DAY_OFFSETS,
    DERIVED_SOURCE_PARAM,
    DISPOSITIONS,
    FABRICATED_FINAL_PREDICATE,
    FINAL_STATUS,
    NO_SCHEDULE_OF_RECORD,
    NOT_ON_THE_AUTHORITY_SLATE,
    QUARANTINED,
    REPAIRED_FINAL,
    UNSETTLED,
    UNSETTLED_STATUS,
    VOID_STATUS,
    AuthorityVerdict,
    adapter_can_speak_for,
    disposition_for,
    has_schedule_of_record,
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
_CANDIDATE_SQL = f"""
    SELECT e.id AS event_id,
           s.key AS sport_key,
           e.status AS ev_status,
           e.home_team_name, e.away_team_name,
           e.commence_time, e.completed_at, e.espn_id,
           {_TICKER_DATE_EXPR} AS ticker_date
    FROM events e
    LEFT JOIN sports s ON s.id = e.sport_id
    WHERE {FABRICATED_FINAL_PREDICATE}
      AND {_TICKER_DATE_EXPR} = ANY(CAST(:dates AS date[]))
      AND (:sport IS NULL OR s.key = :sport)
    ORDER BY s.key, e.id
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

#: Scoreboard calls one invocation may spend. 30 x (one request + the client's
#: 0.5s courtesy sleep) is ~20s, inside the 30s Heroku router wall with room for
#: the queries either side. Three calls per adjudicable (sport, date), so ten
#: such groups per page.
MAX_AUTHORITY_CALLS = 30

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
) -> dict:
    """Session-taking core, shared by the CLI and
    ``POST /api/admin/repairs/fabricated-finals`` so the two cannot drift.

    Commits per DATE, so a router timeout leaves consistent, resumable progress.
    """
    from sqlalchemy import text

    from app.services.espn_api import get_espn_service

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
    written = {REPAIRED_FINAL: 0, UNSETTLED: 0, QUARANTINED: 0}
    raced = 0
    authority_calls = 0
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
    budget_spent = False

    for ticker_date in selected:
        if budget_spent:
            # The call budget ran out inside an earlier date. Stop rather than
            # walk on: `next_since` already points at the unfinished date, and
            # adjudicating the rest against slates we cannot afford to fetch is
            # how a hold becomes a void.
            break
        rows = (
            await session.execute(
                text(_CANDIDATE_SQL), {**bind, "dates": [ticker_date]}
            )
        ).all()
        if not rows:
            continue

        by_sport: dict[str, list] = {}
        for r in rows:
            by_sport.setdefault(r.sport_key, []).append(r)

        rows_by_id = {r.event_id: r for r in rows}
        completions = await _derive_completions(
            session, [r.event_id for r in rows], rows_by_id
        )

        date_ledger: list[tuple] = []
        for sport_key, sport_rows in by_sport.items():
            # Only pay for the slate when a verdict could possibly need it. A
            # sport with no schedule of record, or one this adapter cannot read,
            # is decided by `disposition_for` from the sport key alone.
            slate: list[dict] = []
            reachable = False
            if has_schedule_of_record(sport_key) and adapter_can_speak_for(sport_key):
                if authority_calls + len(AUTHORITY_DAY_OFFSETS) > MAX_AUTHORITY_CALLS:
                    # Budget spent mid-date. Stop cleanly rather than adjudicate
                    # this sport against an empty slate — the difference between
                    # a hold and a void. `next_since` returns to THIS date, so
                    # the sports already decided here are re-decided on the next
                    # call (idempotent: their rows have left the population) and
                    # the ones not reached are reached.
                    next_since = ticker_date
                    budget_spent = True
                    break
                reachable, slate = await _fetch_slate(espn, sport_key, ticker_date)
                authority_calls += len(AUTHORITY_DAY_OFFSETS)

            for r in sport_rows:
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
                disposition, reason = disposition_for(sport_key, verdict)
                counts[disposition] += 1
                reasons[reason] = reasons.get(reason, 0) + 1
                if reason == NO_SCHEDULE_OF_RECORD:
                    no_authority_leagues[sport_key or "<unknown>"] = (
                        no_authority_leagues.get(sport_key or "<unknown>", 0) + 1
                    )
                elif reason == NOT_ON_THE_AUTHORITY_SLATE:
                    absent_from_slate.append({
                        "event_id": r.event_id,
                        "sport_key": sport_key,
                        "ticker_date": str(r.ticker_date),
                        "matchup": f"{r.home_team_name} v {r.away_team_name}",
                        "slate_size": len(slate),
                    })
                date_ledger.append((r, disposition, reason, fixture))
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
            for r, disposition, _reason, fixture in date_ledger:
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

    after = (await session.execute(text(_POPULATION_SQL), bind)).scalar() or 0

    return {
        "population_before": before,
        "population_after": after,
        "dates_selected": [str(d) for d in selected],
        "dates_remaining": max(0, len(date_rows) - len(selected)),
        "next_since": str(next_since) if next_since else None,
        "authority_calls": authority_calls,
        "dispositions": counts,
        "reasons": reasons,
        "written": written if apply else {k: 0 for k in written},
        "raced": raced,
        # Doctrine rule 8's trigger, as data rather than a judgement call.
        "no_schedule_of_record_leagues": dict(
            sorted(no_authority_leagues.items(), key=lambda kv: -kv[1])
        ),
        # Named, never a bare count: this is the only quarantine class an
        # operator can check by hand, and it is where a matcher regression would
        # show up first.
        "absent_from_a_populated_slate": absent_from_slate,
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
    args = ap.parse_args()

    async with get_task_session() as session:
        out = await repair(
            session, args.apply, limit=args.limit, sport=args.sport, since=args.since
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
