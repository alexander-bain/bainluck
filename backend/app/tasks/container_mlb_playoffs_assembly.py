"""Assemble one MLB postseason through the shared container pipeline. #9650 (v3, #9217).

**SHIP: a reader opening this year's MLB playoffs sees every playoff game we
hold and the questions on it.** (Pillar: MATCHING / TRUTH.) The membership rule
is `app/utils/container_mlb_playoffs.py`; this module reads ESPN's boards and
the rows it needs and hands the candidates to
`container_assembly.assemble_container`, which writes the `contains` edges and
receipts exactly as it does for a tennis draw or an NFL week.

DARK. Nothing schedules this and nothing reads its edges yet. It creates no
container, claims no anchor, writes no event and no market: the one write it
can cause is `assemble_container`'s own, and only with ``apply=True`` on a
container the caller already resolved. The caller owns the transaction — this
never commits — and `container_assembly.UNDO_LINE` undoes it.

READ-ONLY QUERIES, ALL ID-KEYED EXCEPT ONE REPORT.
* our MLB events holding the postseason's ESPN ids (the membership join);
* the markets whose `event_id` is a member or a refused duplicate;
* our MLB events inside the postseason's kickoff span that hold NO ESPN id the
  boards listed, with how many markets each holds. That read admits nothing.
  It exists because MLB's real duplicate is not two rows sharing an ESPN id
  (`uq_events_espn_id` forbids it) but a StatPal or Odds API row for the same
  game with no ESPN id at all — the pairs `event_twin_fold` folds at serve time
  by name and minute. Membership may not use names, so such a row is named in
  the report, and if it holds questions the pass is `partial`.

THE BOARD DAYS ARE THE CALLER'S. The dispatch entry reads ESPN's dated MLB board
for each day it is given (the container's declared window), at most
`MAX_BOARD_DAYS`. A day ESPN does not answer is recorded as unread, never as an
empty day (`get_scoreboard` returns None for dark, ``[]`` for empty).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy import text

from app.tasks.container_assembly import (
    UNDO_LINE,
    VENUE_FETCH_LIMIT,
    assemble_container,
)
from app.utils.container_mlb_playoffs import (
    MLB_SPORT_KEY,
    EventRow,
    MarketRow,
    MlbPostseason,
    PostseasonMembers,
    PostseasonSelection,
    postseason_incompleteness,
    resolve_postseason_members,
    select_postseason_games,
)

logger = logging.getLogger(__name__)

#: Our rows that hold one of the postseason's ESPN ids. Every status, on
#: purpose: a postponed, live or final game is still a playoff game.
EVENTS_FOR_ESPN_IDS_SQL = (
    "SELECT e.id, e.espn_id, e.status, e.commence_time, "
    "       e.home_team_name, e.away_team_name "
    "FROM events e JOIN sports s ON s.id = e.sport_id "
    "WHERE s.key = :sport_key AND e.espn_id = ANY(:espn_ids) "
    "ORDER BY e.id"
)

#: Every market on those rows, resolved ones included — a finished series still
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

#: Report only — see the module note. Bounded by the postseason's own known
#: kickoffs plus `REPORT_SLACK`, never a calendar guess. `listed_ids` is every
#: id the boards named, regular-season games included, so a September game ESPN
#: listed as regular season is accounted for and never reads as unidentified.
UNIDENTIFIED_IN_SPAN_SQL = (
    "SELECT e.id, e.espn_id, e.status, e.commence_time, "
    "       e.home_team_name, e.away_team_name, "
    "       (SELECT count(*) FROM futures_markets fm WHERE fm.event_id = e.id) "
    "FROM events e JOIN sports s ON s.id = e.sport_id "
    "WHERE s.key = :sport_key "
    "  AND e.commence_time >= :span_start AND e.commence_time <= :span_end "
    "  AND (e.espn_id IS NULL OR NOT (e.espn_id = ANY(:listed_ids))) "
    "ORDER BY e.id "
    "LIMIT :limit"
)

#: How far from a listed first pitch a row can sit and still be the same slate:
#: the registry's same-game window for a claim ESPN placed (#9216 is 12h).
REPORT_SLACK = timedelta(hours=12)

REPORT_LIMIT = 200

#: A postseason runs about five weeks (Wild Card to the World Series). A longer
#: request is a mistake in the declaration, refused rather than read.
MAX_BOARD_DAYS = 45


def _event_row(row) -> EventRow:
    return EventRow(
        id=int(row[0]),
        espn_id=row[1],
        status=row[2],
        commence_time=row[3],
        home=row[4],
        away=row[5],
    )


def board_days(start: date, end: date) -> list[str]:
    """ESPN board days (``YYYYMMDD``) from ``start`` through ``end`` inclusive."""
    if end < start:
        return []
    return [
        (start + timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range((end - start).days + 1)
    ]


@dataclass
class PostseasonHarvest:
    """What one read of the postseason produced, members and refusals together."""

    selection: PostseasonSelection
    members: PostseasonMembers
    unidentified_in_span: list = field(default_factory=list)
    markets_truncated: bool = False

    @property
    def candidates(self) -> list:
        return self.members.candidates

    @property
    def stranded_questions(self) -> int:
        return sum(u["markets"] for u in self.unidentified_in_span)

    @property
    def incomplete(self) -> list[str]:
        return postseason_incompleteness(
            self.selection,
            self.members,
            markets_truncated=self.markets_truncated,
            stranded_questions=self.stranded_questions,
        )

    def summary(self) -> dict:
        by_type: dict = {}
        for candidate in self.members.candidates:
            by_type[candidate.child_type] = by_type.get(candidate.child_type, 0) + 1
        excluded = {**self.selection.excluded, **self.members.excluded}
        return {
            "season": self.selection.target.season,
            "days_read": len(self.selection.days_read),
            "days_unread": self.selection.days_dark,
            "games": len(self.selection.games),
            "candidates": by_type,
            "unavailable": self.selection.unavailable,
            "games_without_event_row": len(self.members.unavailable),
            "not_yet_certain": len(self.members.not_yet_certain),
            "excluded": {k: len(v) for k, v in sorted(excluded.items())},
            "unidentified_in_span": len(self.unidentified_in_span),
            "stranded_questions": self.stranded_questions,
            "markets_truncated": self.markets_truncated,
            "incomplete": self.incomplete,
        }


async def gather_mlb_postseason_candidates(
    session,
    boards: Iterable[tuple[str, Optional[list]]],
    target: MlbPostseason,
    *,
    limit: int = VENUE_FETCH_LIMIT,
) -> PostseasonHarvest:
    """Read our rows for ``target``'s postseason games and resolve the members."""
    selection = select_postseason_games(boards, target)
    if selection.unavailable:
        return PostseasonHarvest(selection=selection, members=PostseasonMembers())

    espn_ids = sorted({g.espn_id for g in selection.games})
    event_rows = [
        _event_row(r)
        for r in (
            await session.execute(
                text(EVENTS_FOR_ESPN_IDS_SQL),
                {"sport_key": MLB_SPORT_KEY, "espn_ids": espn_ids},
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
                "MLB postseason %s market read truncated at %s rows — members "
                "beyond the cap are invisible to this pass",
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

    members = resolve_postseason_members(selection, event_rows, market_rows)

    unidentified: list = []
    if selection.games:
        kickoffs = [g.date for g in selection.games]
        rows = (
            await session.execute(
                text(UNIDENTIFIED_IN_SPAN_SQL),
                {
                    "sport_key": MLB_SPORT_KEY,
                    "span_start": min(kickoffs) - REPORT_SLACK,
                    "span_end": max(kickoffs) + REPORT_SLACK,
                    "listed_ids": sorted(selection.listed_ids),
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
                    "espn_id": row.espn_id,
                    "markets": int(r[6] or 0),
                }
            )

    return PostseasonHarvest(
        selection=selection,
        members=members,
        unidentified_in_span=unidentified,
        markets_truncated=truncated,
    )


async def run_mlb_postseason_assembly(
    session,
    container,
    boards: Iterable[tuple[str, Optional[list]]],
    target: MlbPostseason,
    *,
    apply: bool = False,
    limit: int = VENUE_FETCH_LIMIT,
) -> dict:
    """One MLB postseason, gathered and — with ``apply=True`` — assembled.

    ``container`` is an existing container row (``id``, ``slug``); its slug must
    be ``target.slug``, so one season's games can never be written into another
    season's container. ``apply=False`` writes nothing and still reports every
    member and refusal. Never commits.
    """
    report: dict = {
        "slug": target.slug,
        "apply": apply,
        "target": {"season": target.season},
        "undo": {"edges": UNDO_LINE},
    }
    if getattr(container, "slug", None) != target.slug:
        report.update(
            terminal="refused",
            reason="container_slug_mismatch",
            container_slug=getattr(container, "slug", None),
        )
        return report

    harvest = await gather_mlb_postseason_candidates(session, boards, target, limit=limit)
    report["harvest"] = harvest.summary()
    report["games"] = harvest.members.games
    report["games_without_event_row"] = harvest.members.unavailable
    report["not_yet_certain"] = harvest.members.not_yet_certain
    report["excluded"] = {**harvest.selection.excluded, **harvest.members.excluded}
    report["unidentified_in_span"] = harvest.unidentified_in_span

    if harvest.selection.unavailable:
        report.update(terminal="unavailable", reason=harvest.selection.unavailable)
        return report

    # Members admitted around a gap are still right, so they are kept; a gap
    # changes the claim, below — the same shape as the tennis and NFL passes.
    if apply and harvest.candidates:
        result = await assemble_container(session, container, harvest.candidates)
        report["assembly"] = result.as_dict()

    # gotcha #53: `complete` means every board day was read, every game owed a
    # row is a member, and its questions were read in full. Anything else with
    # members is `partial`, and zero members is `partial` too.
    incomplete = harvest.incomplete
    report["incomplete"] = incomplete
    if not harvest.candidates:
        report.update(terminal="partial", reason="no_member_found")
    elif incomplete:
        report.update(terminal="partial", reason=incomplete[0])
    else:
        report.update(terminal="complete", reason=None)
    return report


async def read_mlb_boards(espn, days: list[str]) -> list[tuple[str, Optional[list]]]:
    """``[(day, entries-or-None)]``. A raise or a None is an unread day."""
    boards: list[tuple[str, Optional[list]]] = []
    for day in days:
        try:
            board = await espn.get_scoreboard(MLB_SPORT_KEY, date=day)
        except Exception as exc:  # noqa: BLE001 — one day must not cost the rest
            logger.warning("MLB postseason board %s unreadable: %s", day, exc)
            board = None
        boards.append((day, board))
    return boards


async def assemble_mlb_postseason(
    session,
    container,
    target: MlbPostseason,
    start: date,
    end: date,
    *,
    apply: bool = False,
    espn=None,
) -> dict:
    """Read ESPN's MLB boards for ``start``..``end``, then run the postseason.

    The dispatch entry. ``start``/``end`` are the container's declared window;
    a window longer than `MAX_BOARD_DAYS` or empty is refused before any read.
    """
    days = board_days(start, end)
    if not days or len(days) > MAX_BOARD_DAYS:
        return {
            "slug": target.slug,
            "apply": apply,
            "terminal": "refused",
            "reason": "board_window_out_of_bounds",
            "days": len(days),
        }

    owned = espn is None
    if owned:
        from app.services.espn_api import ESPNAPIService

        espn = ESPNAPIService()
    try:
        boards = await read_mlb_boards(espn, days)
    finally:
        if owned:
            await espn.close()
    return await run_mlb_postseason_assembly(session, container, boards, target, apply=apply)
