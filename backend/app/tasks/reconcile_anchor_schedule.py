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

from sqlalchemy import select, update

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

#: One ESPN call per row, so the default bound is an ESPN-politeness bound as
#: much as a database one.
DEFAULT_LIMIT = 200


async def _load_rows(
    session,
    *,
    sport: Optional[str],
    limit: int,
    lookback: timedelta,
    horizon: timedelta,
    now: Optional[datetime] = None,
) -> list[AnchoredRow]:
    """The anchored, unfinished, near-future rows — oldest kickoff first.

    Oldest-first is the ordering that matters here: the rows closest to
    kickoff are the ones a user is about to see, and a truncated run should
    have spent its budget on them (gotcha #41 asks what the ordering starts on;
    this population does not expire, so a floor is enough and a ceiling is not
    needed).
    """
    from app.models.models import Event, Sport

    now = now or datetime.now(timezone.utc)
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
        .where(
            Event.espn_id.isnot(None),
            Event.completed_at.is_(None),
            Event.status.notin_(tuple(SETTLED_STATUSES)),
            Event.commence_time >= now - lookback,
            Event.commence_time < now + horizon,
        )
        .order_by(Event.commence_time)
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
) -> dict[str, Any]:
    """Ask the authority about every anchored near-future row's kickoff.

    Returns a summary carrying an explicit ``terminal`` so ``task_verdict`` can
    read it, and a run that finds nothing to move reports ``no_work`` with the
    verdict census that explains the zero — "it returned" is not "it worked"
    (gotcha #53), and a rail that cannot tell a healthy population from an
    authority outage is a rail that reports health during an outage.
    """
    from app.services.espn_api import get_espn_service
    from app.tasks.repair_authority_id_collisions import _fetch_record

    rows = await _load_rows(
        session, sport=sport, limit=limit, lookback=lookback, horizon=horizon
    )
    if not rows:
        return {
            "measured": True,
            "terminal": "no_work",
            "reason": "no anchored, unfinished rows inside the window",
            "applied": apply,
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
    # An authority that answered for nothing is not a clean population. The
    # terminal has to be able to say so, or a dark ESPN reads as "all agree".
    if summary["by_verdict"]["no_answer"] == summary["examined"]:
        terminal = "authority_dark"
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
        **summary,
    }


def summarize_for_operator(result: dict[str, Any]) -> str:
    """One line an operator can act on. Never reads a dark authority as clean."""
    if not result.get("measured"):
        return f"UNMEASURED — {result.get('reason')}"
    verdicts = result.get("by_verdict") or {}
    counts = " ".join(f"{name}={verdicts.get(name, 0)}" for name in SCHEDULE_VERDICTS)
    return (
        f"{result.get('terminal')}: examined={result.get('examined')} "
        f"moved={result.get('moved', 0)} stale={result.get('stale', 0)} · {counts}"
    )
