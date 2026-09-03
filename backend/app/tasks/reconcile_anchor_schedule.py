"""Dereference each anchor BY ID and reconcile the kickoff it names. #2693/#2697.

WHO DECIDES is not in this file.  ``app/utils/anchor_schedule`` holds the whole
rule and the argument for it; this module is the plumbing — which rows to ask
about, how to ask ESPN, and how to write the answer down.  The read-only
``scripts/audit_anchor_schedule.py`` runs the identical module against
production, so a dry run and this rail cannot drift.

═══ WHY THIS RAIL EXISTS AT ALL — THE BLIND SPOT ═══

Every other ESPN pass is driven by **today's scoreboard**: it fetches the slate
for the current date and visits the rows whose anchor (or teams) appear on it.
A row anchored to a game three months out appears on no slate we fetch, so it
is visited by nothing.  ``sync_scheduled_events`` already carries the right
suspicion for this class — it refuses a start-time correction that is beyond
the same-game window and logs *"the espn_id on this row points at a different
game (#1947)"* — and that refusal is unreachable for exactly the rows that need
it most.

So this rail inverts the direction of the question.  Instead of "who on today's
board matches this row?", it asks "**what game is this row's anchor?**", one
``summary?event=<id>`` call per row.  That is the only way the December anchor
on a September row is ever seen.

═══ WHAT IT WRITES, AND THE THREE THINGS IT WILL NOT ═══

One column, plus its provenance: ``commence_time`` and
``commence_time_source``.  Not the status, not the scores, not
``completed_at``, and it never deletes or merges a row (ruling 079) — a start
time that disagrees with the authority is a start-time defect, and a rail that
starts fixing adjacent things is how a repair becomes an incident.

It also will not write when the teams disagree with the anchor.  That is a
different defect (the anchor is wrong, not the clock) and it belongs to
``authority-id-collisions``; the verdict is reported so the two rails can be
read together.

ATTENDED ONLY.  ``apply`` defaults to False and this is deliberately not wired
to a beat: the population it moves is small, the moves are large (98 days in
the charter case), and a reviewer should see the plan.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select, update

from app.utils.anchor_schedule import (
    AUTHORITY_MOVES_US,
    AnchoredRow,
    SCHEDULE_VERDICTS,
    schedule_decision,
    summarize_decisions,
)
from app.utils.espn_tennis_anchor import SETTLED_STATUSES

logger = logging.getLogger(__name__)

#: Rows are read forward from a little before now. A row whose own start is in
#: the past and which never settled is a different defect (#2772, the stale
#: ghost) and moving its clock would not make it a game again; a day of slack
#: keeps a fixture that started an hour ago inside the window without opening
#: the rail onto history.
DEFAULT_LOOKBACK = timedelta(days=1)

#: How far ahead to look. A season, not a slate — the whole point is that the
#: defect hides at horizons no scoreboard pass reaches.
DEFAULT_HORIZON = timedelta(days=120)

#: One ESPN call per row, so the bound is a *wall-clock* bound before it is
#: anything else — and the wall clock that matters is Heroku's 30-second router
#: timeout, because the only caller today is an admin endpoint.
#:
#: Measured 2026-09-03: ~0.2s per ``summary?event=`` call, so the original 200
#: would have spent ~45s and been killed with an H12 *after the writes had
#: already committed* — the worst shape a destructive endpoint can have. 100 is
#: ~20s, inside the window with room for the query and the JSON.
#:
#: It is SMALLER THAN THE POPULATION and that is the point of ``eligible``:
#: the window held 685 anchored rows that day (239 NFL alone), so even an
#: unfiltered run at any router-safe limit sees a minority of them. Scope with
#: ``sport`` rather than raising this. See :func:`_count_eligible` for why the
#: shortfall is reported rather than left for the reader to notice.
DEFAULT_LIMIT = 100

#: What separates the two halves of a cursor. A kickoff renders as ISO-8601,
#: which already contains ``-``, ``:`` and ``+``; ``|`` appears in none of them.
CURSOR_SEPARATOR = "|"


def encode_cursor(commence_time: datetime, event_id: int) -> str:
    """Name the last row a page examined, so the next page can start after it.

    The cursor is **both** sort keys, because ``commence_time`` alone does not
    identify a row: the NFL slate puts twelve fixtures on the same 17:00
    kickoff, and a cursor that carried only the clock would either re-examine
    all twelve or skip the ones it had not reached. That is the same class of
    bug as an OFFSET over a moving population, arrived at from the other side.
    """
    return f"{commence_time.isoformat()}{CURSOR_SEPARATOR}{event_id}"


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    """Read a cursor back, or raise ``ValueError`` naming what was wrong.

    A malformed cursor is refused rather than ignored. Ignoring it would
    silently restart the sweep at the oldest row, and the caller — a script
    looping until ``next_cursor`` is None — would loop over page one forever
    while every page reported a healthy census.
    """
    moment, separator, event_id = str(cursor).rpartition(CURSOR_SEPARATOR)
    if not separator or not moment:
        raise ValueError(
            f"cursor must be '<iso8601>{CURSOR_SEPARATOR}<event_id>', got {cursor!r}"
        )
    try:
        parsed = datetime.fromisoformat(moment)
    except ValueError:
        raise ValueError(f"cursor kickoff {moment!r} is not ISO-8601") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        return parsed, int(event_id)
    except ValueError:
        raise ValueError(f"cursor event id {event_id!r} is not an integer") from None


def _after_cursor(cursor: Optional[str]):
    """The keyset predicate: strictly after ``(commence_time, event_id)``.

    Keyset rather than OFFSET, and the reason is gotcha #41. This window's
    floor is ``now - lookback``, so it MOVES between one page and the next: a
    fixture that has since kicked off drops out from underneath, every later
    row shifts down by one, and an OFFSET would step straight over a row that
    was never examined. A keyset cursor names a position in the ordering rather
    than a count from the start, so rows leaving the floor cannot displace it.

    Written as the expanded ``a > t OR (a = t AND b > i)`` rather than a row
    comparison ``(a, b) > (t, i)``. The two are the same predicate; the expanded
    form is the one the read-only twin can also write into plain SQL, and the
    two rails agreeing is worth more here than the tidier syntax.
    """
    from app.models.models import Event

    if not cursor:
        return ()
    moment, event_id = decode_cursor(cursor)
    return (
        or_(
            Event.commence_time > moment,
            and_(Event.commence_time == moment, Event.id > event_id),
        ),
    )


def _window(
    *,
    lookback: timedelta,
    horizon: timedelta,
    now: Optional[datetime] = None,
):
    """The predicates that define "an anchored row this rail may consider".

    One definition, used by both the count and the fetch. Two copies of a
    population filter is how a census comes to disagree with the thing it is
    counting.
    """
    from app.models.models import Event

    now = now or datetime.now(timezone.utc)
    return (
        Event.espn_id.isnot(None),
        Event.completed_at.is_(None),
        Event.status.notin_(tuple(SETTLED_STATUSES)),
        Event.commence_time >= now - lookback,
        Event.commence_time < now + horizon,
    )


async def _count_eligible(
    session,
    *,
    sport: Optional[str],
    lookback: timedelta,
    horizon: timedelta,
    now: Optional[datetime] = None,
    cursor: Optional[str] = None,
) -> int:
    """How many rows the window holds, ignoring ``limit``.

    ``examined`` alone cannot tell a complete pass from a truncated one: a run
    that saw all 34 rows and a run that saw the first 200 of 685 both report a
    number and both look finished. That is gotcha #53 in its second form —
    not an empty answer read as health, but a *partial* one. So the shortfall
    is measured and named, and a truncated run may not terminate ``complete``.

    With ``cursor`` set this counts the rows AT OR AFTER that position, which
    is what ``remaining`` means. Called both ways on every paged run: without
    the cursor it is ``eligible``, the whole window, whose meaning must not
    drift because a caller started paging.
    """
    from app.models.models import Event, Sport

    query = (
        select(func.count())
        .select_from(Event)
        .join(Sport, Sport.id == Event.sport_id)
        .where(*_window(lookback=lookback, horizon=horizon, now=now))
        .where(*_after_cursor(cursor))
    )
    if sport:
        query = query.where(Sport.key == sport)
    return int((await session.execute(query)).scalar() or 0)


async def _load_rows(
    session,
    *,
    sport: Optional[str],
    limit: int,
    lookback: timedelta,
    horizon: timedelta,
    now: Optional[datetime] = None,
    cursor: Optional[str] = None,
) -> list[AnchoredRow]:
    """The anchored, unfinished, near-future rows — oldest kickoff first.

    Oldest-first is the ordering that matters here: the rows closest to
    kickoff are the ones a user is about to see, and a truncated run should
    have spent its budget on them (gotcha #41 asks what the ordering starts on;
    this population does not expire, so a floor is enough and a ceiling is not
    needed).

    **The ordering carries ``Event.id`` as a tiebreaker and that is load-bearing
    now that a cursor exists.** ``commence_time`` is not unique — an NFL Sunday
    puts a dozen fixtures on one 17:00 kickoff — so ``ORDER BY commence_time``
    alone leaves the order within a tie up to the plan. Two pages either side of
    such a tie could then repeat rows or step over them, and the skipped row is
    invisible: it is simply never examined, and the sweep reports a clean census
    of the rows it did see.
    """
    from app.models.models import Event, Sport

    query = (
        select(
            Event.id,
            Event.espn_id,
            Event.commence_time,
            Event.home_team_name,
            Event.away_team_name,
            Event.status,
            Event.completed_at,
            Event.commence_time_source,
            Sport.key,
        )
        .join(Sport, Sport.id == Event.sport_id)
        .where(*_window(lookback=lookback, horizon=horizon, now=now))
        .where(*_after_cursor(cursor))
        .order_by(Event.commence_time, Event.id)
        .limit(limit)
    )
    if sport:
        query = query.where(Sport.key == sport)

    result = await session.execute(query)
    return [
        AnchoredRow(
            event_id=row.id,
            sport_key=row.key,
            home_team_name=row.home_team_name or "",
            away_team_name=row.away_team_name or "",
            espn_id=str(row.espn_id),
            commence_time=row.commence_time,
            status=row.status,
            completed_at=row.completed_at,
            commence_time_source=row.commence_time_source,
        )
        # Scalars, not ORM rows: this loop commits per move, and a live ORM
        # object does not survive that boundary (gotcha #6).
        for row in result.all()
    ]


async def _apply_move(session, decision) -> bool:
    """Write one move, and prove it landed on the row we decided about.

    The ``espn_id`` and ``commence_time`` in the WHERE clause are the compare:
    they are the two facts the decision was made from, so a row whose anchor or
    clock moved since the read is skipped rather than overwritten. ``rowcount``
    0 is therefore a real finding — the plan was stale — and not a silent pass.
    """
    from app.models.models import Event

    result = await session.execute(
        update(Event)
        .where(
            Event.id == decision.event_id,
            Event.espn_id == decision.espn_id,
            Event.commence_time == decision.ours,
        )
        .values(**decision.write)
    )
    return bool(result.rowcount)


async def reconcile(
    session,
    *,
    apply: bool = False,
    limit: int = DEFAULT_LIMIT,
    sport: Optional[str] = None,
    lookback: timedelta = DEFAULT_LOOKBACK,
    horizon: timedelta = DEFAULT_HORIZON,
    cursor: Optional[str] = None,
) -> dict[str, Any]:
    """Ask the authority about every anchored near-future row's kickoff.

    Returns a summary carrying an explicit ``terminal`` so ``task_verdict`` can
    read it, and a run that finds nothing to move reports ``no_work`` with the
    verdict census that explains the zero — "it returned" is not "it worked"
    (gotcha #53), and a rail that cannot tell a healthy population from an
    authority outage is a rail that reports health during an outage.

    ═══ PAGING, AND THE ONE WORD A PAGE MAY NOT SAY ═══

    ``limit`` is a router-timeout bound well under the population (100 against
    685), so an unattended sweep is necessarily several calls. ``next_cursor``
    makes them *consecutive* instead of each restarting at the oldest row; pass
    it back as ``cursor`` until it comes back ``None``.

    Three counts, and they are three different questions:

    ``eligible``   the whole window, ignoring both cursor and limit. Its
                   meaning is unchanged by paging — deliberately, because it is
                   what a reviewer compares ``examined`` against.
    ``remaining``  the rows at or after the cursor. Equal to ``eligible`` on the
                   first page, which is why ``truncated`` keeps its old value
                   on every call that does not page.
    ``examined``   what THIS call looked at.

    **``truncated`` stays ``eligible > examined``, and that is what stops a page
    from reporting an all-clear.** Any call carrying a cursor has rows behind it
    by construction, so ``examined`` is always short of ``eligible`` and the
    terminal is always ``partial`` — including on the final page, which really
    did examine only its own tail. ``no_work`` and ``complete`` remain reachable
    only from a single unpaged call that saw the entire window, which is the
    only situation in which either is true. Whether a *sweep* finished is the
    driver's finding to report, not any one page's; ``has_more`` is what the
    driver loops on.
    """
    from app.services.espn_api import get_espn_service
    from app.tasks.repair_authority_id_collisions import _fetch_record

    eligible = await _count_eligible(
        session, sport=sport, lookback=lookback, horizon=horizon
    )
    remaining = (
        eligible
        if not cursor
        else await _count_eligible(
            session, sport=sport, lookback=lookback, horizon=horizon, cursor=cursor
        )
    )
    rows = await _load_rows(
        session,
        sport=sport,
        limit=limit,
        lookback=lookback,
        horizon=horizon,
        cursor=cursor,
    )
    if not rows:
        return {
            "measured": True,
            # A cursor that has run off the end of the window is the NORMAL way
            # a sweep stops, not an empty population — so it may not borrow the
            # word for one. `no_work` here would tell a driver that the whole
            # window was clean when all it learned is that it reached the end.
            "terminal": "no_work" if not cursor else "partial",
            "reason": (
                "no anchored, unfinished rows inside the window"
                if not cursor
                else "the cursor is past the last row in the window"
            ),
            "applied": apply,
            "eligible": eligible,
            "remaining": remaining,
            "truncated": bool(cursor),
            "has_more": False,
            "next_cursor": None,
            **summarize_decisions([]),
        }

    service = get_espn_service()
    decisions = []
    for row in rows:
        record = await _fetch_record(service, [row.sport_key], row.espn_id)
        decisions.append(schedule_decision(row, record))

    summary = summarize_decisions(decisions)
    moved, stale = 0, 0
    if apply:
        for decision in decisions:
            if decision.verdict != AUTHORITY_MOVES_US:
                continue
            if await _apply_move(session, decision):
                moved += 1
                logger.info(
                    "anchor-schedule: event %d moved %s -> %s (%.1f days) on "
                    "authority %s",
                    decision.event_id,
                    decision.ours,
                    decision.theirs,
                    (decision.delta_seconds or 0) / 86400.0,
                    decision.espn_id,
                )
            else:
                stale += 1
                logger.warning(
                    "anchor-schedule: event %d NOT moved — its anchor or clock "
                    "changed since the read (plan stale)",
                    decision.event_id,
                )

    pending = summary["by_verdict"][AUTHORITY_MOVES_US]
    truncated = eligible > summary["examined"]
    # `has_more` is about the CURSOR's tail; `truncated` is about the whole
    # window. On the last page of a sweep they disagree — nothing follows, yet
    # this call still saw a minority of the window — and both readings are true.
    has_more = remaining > summary["examined"]
    last = rows[-1]
    next_cursor = encode_cursor(last.commence_time, last.event_id) if has_more else None
    # An authority that answered for nothing is not a clean population. The
    # terminal has to be able to say so, or a dark ESPN reads as "all agree".
    if summary["by_verdict"]["no_answer"] == summary["examined"]:
        terminal = "authority_dark"
    elif truncated:
        # A run that did not see the whole window has not finished, whatever it
        # found in the part it saw — and "no_work" would be the worst of the
        # three readings, because it is the one that sounds like an all-clear.
        # `partial` is chosen over a new word so `task_verdict` keeps reading it
        # as PARTIAL rather than UNKNOWN.
        terminal = "partial"
    elif not pending:
        terminal = "no_work"
    elif apply:
        terminal = "complete" if not stale else "partial"
    else:
        terminal = "plan_only"

    return {
        "measured": True,
        "terminal": terminal,
        "applied": apply,
        "moved": moved,
        "stale": stale,
        "eligible": eligible,
        "remaining": remaining,
        "truncated": truncated,
        "has_more": has_more,
        "next_cursor": next_cursor,
        **summary,
    }


def summarize_for_operator(result: dict[str, Any]) -> str:
    """One line an operator can act on. Never reads a dark authority as clean.

    ``examined`` is printed against ``eligible`` because the two differ far more
    often than they look like they should — the default limit is 200 and the
    window held 685 rows the day this was measured. A reviewer who is told only
    the first number will read a truncated pass as the whole story.

    A truncated call has two different remedies and printing the wrong one
    wastes the reader's next command: mid-sweep the answer is the cursor, and on
    the last page there is no remedy at all because nothing is left to see. So
    the advice is chosen on ``has_more``, not on ``truncated``.

    **A result with no ``has_more`` at all keeps the pre-paging wording.** An
    absent key is not a ``False`` one, and reading it as False would print "this
    page ends the window" — the one sentence that says a sweep is finished — on
    a summary that never measured whether it was. That is gotcha #53 in the
    shape this module keeps meeting: a missing signal answered as a definite no.
    """
    unknown = object()
    if not result.get("measured"):
        return f"UNMEASURED — {result.get('reason')}"
    verdicts = result.get("by_verdict") or {}
    counts = " ".join(f"{name}={verdicts.get(name, 0)}" for name in SCHEDULE_VERDICTS)
    examined = result.get("examined")
    eligible = result.get("eligible")
    reach = (
        f"examined={examined}/{eligible}"
        if eligible is not None
        else f"examined={examined}"
    )
    has_more = result.get("has_more", unknown)
    if has_more is True:
        reach += (
            f" MORE ({result.get('remaining', 0) - (examined or 0)} after this page; "
            f"pass cursor={result.get('next_cursor')})"
        )
    elif result.get("truncated"):
        reach += (
            " TAIL (this page ends the window; earlier pages hold the rest)"
            if has_more is False
            else f" TRUNCATED (raise limit above {eligible} to see the rest)"
        )
    return (
        f"{result.get('terminal')}: {reach} "
        f"moved={result.get('moved', 0)} stale={result.get('stale', 0)} · {counts}"
    )
