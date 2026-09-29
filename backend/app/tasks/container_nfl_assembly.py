"""Assemble one NFL week through the shared container pipeline. #9649 (v3, #9217).

**SHIP: a reader opening one NFL week sees exactly that week's games and the
questions we hold on them.** (Pillar: MATCHING / DISCOVER.) The membership rule
is `app/utils/container_nfl.py`; this module reads the rows it needs and hands
the candidates to `container_assembly.assemble_container`, which writes the
`contains` edges and receipts exactly as it does for a tennis draw.

DARK. Nothing schedules this and nothing reads its edges yet. It creates no
container, claims no anchor, writes no event and no market: the one write it
can cause is `assemble_container`'s own, and only with ``apply=True`` on a
container the caller already resolved. The caller owns the transaction — this
never commits — so the dispatch that eventually runs it decides when a pass is
kept, and `container_assembly.UNDO_LINE` undoes it.

READ-ONLY QUERIES, ALL ID-KEYED EXCEPT ONE REPORT.
* our events holding the week's contest ids (the membership join);
* the markets whose `event_id` is a member or a refused duplicate;
* our NFL events inside the week's kickoff span that hold NONE of its contest
  ids. That last read admits nothing. It exists so a phantom — the
  Rams–Cardinals row at the Chargers–Cardinals kickoff — is named in the report
  instead of being silently absent from the week.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Iterable

from sqlalchemy import text

from app.tasks.container_assembly import (
    UNDO_LINE,
    VENUE_FETCH_LIMIT,
    assemble_container,
)
from app.utils.container_nfl import (
    NFL_SPORT_KEY,
    EventRow,
    MarketRow,
    NflWeek,
    WeekMembers,
    WeekSelection,
    resolve_week_members,
    select_week_contests,
    week_incompleteness,
)

logger = logging.getLogger(__name__)

#: Our rows that hold one of the week's contest ids. Every status, on purpose:
#: a postponed, live or final game is still the week's game.
EVENTS_FOR_CONTESTS_SQL = (
    "SELECT e.id, e.statpal_fixture_id, e.status, e.commence_time, "
    "       e.home_team_name, e.away_team_name "
    "FROM events e JOIN sports s ON s.id = e.sport_id "
    "WHERE s.key = :sport_key AND e.statpal_fixture_id = ANY(:contest_ids) "
    "ORDER BY e.id"
)

#: Every market on those rows, resolved ones included — a finished week still
#: shows what its questions settled at. Ordered by id so a truncation is
#: deterministic and re-runnable.
MARKETS_FOR_EVENTS_SQL = (
    "SELECT fm.id, fm.event_id, fm.name, fm.external_id, fm.source, "
    "       fm.market_type, fm.status "
    "FROM futures_markets fm "
    "WHERE fm.event_id = ANY(:event_ids) "
    "ORDER BY fm.id "
    "LIMIT :limit"
)

#: Report only — see the module note. Bounded by the week's own known kickoffs
#: plus `REPORT_SLACK`, never a calendar guess.
UNIDENTIFIED_IN_SPAN_SQL = (
    "SELECT e.id, e.statpal_fixture_id, e.status, e.commence_time, "
    "       e.home_team_name, e.away_team_name "
    "FROM events e JOIN sports s ON s.id = e.sport_id "
    "WHERE s.key = :sport_key "
    "  AND e.commence_time >= :span_start AND e.commence_time <= :span_end "
    "  AND (e.statpal_fixture_id IS NULL "
    "       OR NOT (e.statpal_fixture_id = ANY(:contest_ids))) "
    "ORDER BY e.id "
    "LIMIT :limit"
)

#: The NFL stamper's own match window (`stamp_nfl_statpal_fixtures.MATCH_WINDOW`).
REPORT_SLACK = timedelta(hours=1)

REPORT_LIMIT = 200


def _event_row(row) -> EventRow:
    return EventRow(
        id=int(row[0]),
        statpal_fixture_id=row[1],
        status=row[2],
        commence_time=row[3],
        home=row[4],
        away=row[5],
    )


@dataclass
class NflWeekHarvest:
    """What one read of the week produced, members and refusals together."""

    selection: WeekSelection
    members: WeekMembers
    unidentified_in_span: list = field(default_factory=list)
    markets_truncated: bool = False

    @property
    def candidates(self) -> list:
        return self.members.candidates

    @property
    def incomplete(self) -> list[str]:
        return week_incompleteness(
            self.selection, self.members, markets_truncated=self.markets_truncated
        )

    def summary(self) -> dict:
        by_type: dict = {}
        for candidate in self.members.candidates:
            by_type[candidate.child_type] = by_type.get(candidate.child_type, 0) + 1
        excluded = {**self.selection.excluded, **self.members.excluded}
        return {
            "season": self.selection.season,
            "contests": len(self.selection.contests),
            "candidates": by_type,
            "unavailable": self.selection.unavailable,
            "contests_without_event_row": len(self.members.unavailable),
            "excluded": {k: len(v) for k, v in sorted(excluded.items())},
            "unidentified_in_span": len(self.unidentified_in_span),
            "markets_truncated": self.markets_truncated,
            "incomplete": self.incomplete,
        }


async def gather_nfl_week_candidates(
    session, fixtures: Iterable, target: NflWeek, *, limit: int = VENUE_FETCH_LIMIT
) -> NflWeekHarvest:
    """Read our rows for ``target``'s contests and resolve the week's members."""
    selection = select_week_contests(fixtures, target)
    if selection.unavailable:
        return NflWeekHarvest(selection=selection, members=WeekMembers())

    contest_ids = [c.contest_id for c in selection.contests]
    event_rows = [
        _event_row(r)
        for r in (
            await session.execute(
                text(EVENTS_FOR_CONTESTS_SQL),
                {"sport_key": NFL_SPORT_KEY, "contest_ids": contest_ids},
            )
        ).fetchall()
    ]

    market_rows: list[MarketRow] = []
    truncated = False
    if event_rows:
        fetched = (
            await session.execute(
                text(MARKETS_FOR_EVENTS_SQL),
                {"event_ids": [r.id for r in event_rows], "limit": limit + 1},
            )
        ).fetchall()
        truncated = len(fetched) > limit
        if truncated:
            logger.error(
                "NFL week %s market read truncated at %s rows — members beyond "
                "the cap are invisible to this pass",
                target.slug,
                limit,
            )
        market_rows = [
            MarketRow(
                id=int(r[0]),
                event_id=r[1],
                name=r[2],
                external_id=r[3],
                source=r[4],
                market_type=r[5],
                status=r[6],
            )
            for r in fetched[:limit]
        ]

    members = resolve_week_members(selection, event_rows, market_rows)

    kickoffs = [c.kickoff for c in selection.contests if c.start_known]
    unidentified: list = []
    if kickoffs:
        rows = (
            await session.execute(
                text(UNIDENTIFIED_IN_SPAN_SQL),
                {
                    "sport_key": NFL_SPORT_KEY,
                    "span_start": min(kickoffs) - REPORT_SLACK,
                    "span_end": max(kickoffs) + REPORT_SLACK,
                    "contest_ids": contest_ids,
                    "limit": REPORT_LIMIT,
                },
            )
        ).fetchall()
        for r in rows:
            row = _event_row(r)
            unidentified.append(
                {
                    "event_id": row.id,
                    "teams": [row.away, row.home],
                    "commence_time": row.commence_time.isoformat() if row.commence_time else None,
                    "status": row.status,
                    "statpal_fixture_id": row.statpal_fixture_id,
                }
            )

    return NflWeekHarvest(
        selection=selection,
        members=members,
        unidentified_in_span=unidentified,
        markets_truncated=truncated,
    )


async def run_nfl_week_assembly(
    session,
    container,
    fixtures: Iterable,
    target: NflWeek,
    *,
    apply: bool = False,
    limit: int = VENUE_FETCH_LIMIT,
) -> dict:
    """One NFL week, gathered and — with ``apply=True`` — assembled.

    ``container`` is an existing container row (``id``, ``slug``); its slug must
    be ``target.slug``, so one week's games can never be written into another
    week's container. ``apply=False`` writes nothing and still reports every
    member and refusal. Never commits.
    """
    report: dict = {
        "slug": target.slug,
        "apply": apply,
        "target": {"season": target.season, "stage": target.stage, "week": target.week},
        "undo": {"edges": UNDO_LINE},
    }
    if getattr(container, "slug", None) != target.slug:
        report.update(
            terminal="refused",
            reason="container_slug_mismatch",
            container_slug=getattr(container, "slug", None),
        )
        return report

    harvest = await gather_nfl_week_candidates(session, fixtures, target, limit=limit)
    report["harvest"] = harvest.summary()
    report["games"] = harvest.members.games
    report["contests_without_event_row"] = harvest.members.unavailable
    report["excluded"] = {**harvest.selection.excluded, **harvest.members.excluded}
    report["unidentified_in_span"] = harvest.unidentified_in_span

    if harvest.selection.unavailable:
        report.update(terminal="unavailable", reason=harvest.selection.unavailable)
        return report

    # Members admitted around a gap are still right, so they are kept; what a
    # gap changes is the claim, below — the same shape as the tennis pass, which
    # assembles what it has and says `partial` when that is not everything.
    if apply and harvest.candidates:
        result = await assemble_container(session, container, harvest.candidates)
        report["assembly"] = result.as_dict()

    # gotcha #53: `complete` means every game the authority files under this
    # week is a member and its questions were read in full. Zero members, a
    # game with no row, two rows for one game, a game also filed under another
    # week, or a capped market read are each `partial`.
    incomplete = harvest.incomplete
    report["incomplete"] = incomplete
    if not harvest.candidates:
        report.update(terminal="partial", reason="no_member_found")
    elif incomplete:
        report.update(terminal="partial", reason=incomplete[0])
    else:
        report.update(terminal="complete", reason=None)
    return report


async def assemble_nfl_week(
    session, container, target: NflWeek, *, apply: bool = False, service=None
) -> dict:
    """Read the authority's NFL schedule, then run the week. The dispatch entry.

    A schedule that cannot be read is ``unavailable``, not an empty week: the
    authority door raises instead of returning an empty slate (gotcha #53).
    """
    from app.services.statpal_api import StatPalUpstreamError, get_statpal_service

    service = service or get_statpal_service()
    try:
        fixtures = await service.get_schedule_fixtures("nfl")
    except StatPalUpstreamError as exc:
        logger.warning("NFL week %s: schedule unreadable: %s", target.slug, exc)
        return {
            "slug": target.slug,
            "apply": apply,
            "terminal": "unavailable",
            "reason": "schedule_unreadable",
            "error": str(exc),
        }
    return await run_nfl_week_assembly(session, container, fixtures, target, apply=apply)
