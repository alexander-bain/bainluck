"""Assemble one NFL week through the shared container pipeline. #9649 (v3, #9217).

**SHIP: a reader opening one NFL week sees exactly that week's games and the
questions we hold on them.** (Pillar: MATCHING / DISCOVER.) The membership rule
is `app/utils/container_nfl.py`; this module reads the rows it needs and hands
the candidates to `container_assembly.assemble_container`, which writes the
`contains` edges and receipts exactly as it does for a tennis draw.

DARK. Nothing schedules this and nothing reads its edges yet. It creates no
container, claims no anchor, writes no event and no market: the one write it
can cause is `assemble_container`'s own, and only with ``apply=True`` on a
container the caller already resolved — plus, only with
``CONTAINER_NFL_AUTO_PUBLISH_ENABLED`` on, the publication of a week this pass
proved complete (`app/utils/container_nfl_publication.py`, #5341). The caller owns the transaction — this
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

import json
import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import text

from app.tasks.container_assembly import (
    UNDO_LINE,
    VENUE_FETCH_LIMIT,
    assemble_container,
)
from app.utils.container_corrections import (
    bump_revision,
    correction_schema_present,
    lock_container_chain,
)
from app.utils.container_nfl import (
    ADMIT,
    DECISION_RELOCATED,
    DECISION_RELOCATED_WITHDRAWN,
    NFL_SPORT_KEY,
    OWNED_EDGE_SOURCES,
    RELOCATION_RULE_VERSION,
    RELOCATION_SOURCE_KEY,
    EventRow,
    MarketRow,
    UNAVAILABLE_WEEK_NOT_SCHEDULED,
    NflWeek,
    PlacementSnapshot,
    PriorDecision,
    WeekMembers,
    WeekSelection,
    admission_verdict,
    placement_snapshot,
    resolve_week_members,
    select_week_contests,
    week_incompleteness,
)
from app.utils.container_nfl_publication import publish_complete_week

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
    #: ``{market_id: event_id}`` for every question read (#5344: a question
    #: leaves or arrives with the game it is on).
    market_events: dict = field(default_factory=dict)

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
    session,
    fixtures: Iterable,
    target: NflWeek,
    *,
    limit: int = VENUE_FETCH_LIMIT,
    only_contests: Optional[frozenset] = None,
) -> NflWeekHarvest:
    """Read our rows for ``target``'s contests and resolve the week's members.

    ``only_contests`` (#5344) narrows the week to the contests a relocation is
    bringing in, for a destination week outside the window: the move lands, and
    the rest of that week waits for its own window.
    """
    selection = select_week_contests(fixtures, target)
    if only_contests is not None and not selection.unavailable:
        selection.contests = [c for c in selection.contests if c.contest_id in only_contests]
        if not selection.contests:
            selection.unavailable = UNAVAILABLE_WEEK_NOT_SCHEDULED
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
        market_events={m.id: m.event_id for m in market_rows},
    )


async def run_nfl_week_assembly(
    session,
    container,
    fixtures: Iterable,
    target: NflWeek,
    *,
    apply: bool = False,
    limit: int = VENUE_FETCH_LIMIT,
    relocation: Optional["NflRelocation"] = None,
) -> dict:
    """One NFL week, gathered and — with ``apply=True`` — assembled.

    ``container`` is an existing container row (``id``, ``slug``); its slug must
    be ``target.slug``, so one week's games can never be written into another
    week's container. ``apply=False`` writes nothing and still reports every
    member and refusal. Never commits.

    ``relocation`` (#5344) is the season pass's read and barrier: the pass is
    gated on it and moves into this week every game the read places here that
    another week still holds (`relocate_into_week`). None assembles exactly as
    before.
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

    fixtures = list(fixtures)  # read twice: the harvest, then the publication policy
    only = relocation.only_contests if relocation is not None else None
    harvest = await gather_nfl_week_candidates(
        session, fixtures, target, limit=limit, only_contests=only
    )
    report["harvest"] = harvest.summary()
    report["games"] = harvest.members.games
    report["contests_without_event_row"] = harvest.members.unavailable
    report["excluded"] = {**harvest.selection.excluded, **harvest.members.excluded}
    report["unidentified_in_span"] = harvest.unidentified_in_span

    if harvest.selection.unavailable:
        report.update(terminal="unavailable", reason=harvest.selection.unavailable)
        if only is not None:
            report["publication"] = _publication_not_evaluated(RELOCATION_ONLY)
            return report
        # #5341: an unreadable week publishes nothing and unpublishes nothing.
        report["publication"] = await publish_complete_week(
            session, container, target, harvest, None,
            fixtures=fixtures, unidentified_limit=REPORT_LIMIT, apply=apply,
        )
        return report

    # Members admitted around a gap are still right, so they are kept; what a
    # gap changes is the claim, below — the same shape as the tennis pass, which
    # assembles what it has and says `partial` when that is not everything.
    assembly = None
    if apply and harvest.candidates:
        if relocation is None:
            result = await assemble_container(session, container, harvest.candidates)
        else:
            report["relocation"], result = await relocate_into_week(
                session, container, target, harvest, relocation
            )
            if result is None:
                # The barrier gate refused: nothing changed anywhere, so there
                # is nothing for the publication policy to judge.
                gate = report["relocation"]["state"]
                report.update(terminal="partial", reason=gate, incomplete=[gate])
                report["publication"] = _publication_not_evaluated(gate)
                return report
        assembly = report["assembly"] = result.as_dict()
    elif relocation is not None:
        report["relocation"] = {**relocation.summary(), "state": RELOCATION_NOT_APPLIED}

    # gotcha #53: `complete` means every game the authority files under this
    # week is a member and its questions were read in full. Zero members, a
    # game with no row, two rows for one game, a game also filed under another
    # week, or a capped market read are each `partial`.
    incomplete = harvest.incomplete
    report["incomplete"] = incomplete
    if only is not None:
        # A destination outside the window, assembled only for the games moving
        # in: the move is whole, the week is not, and it is not for readers yet.
        report.update(terminal="partial", reason=RELOCATION_ONLY)
        report["publication"] = _publication_not_evaluated(RELOCATION_ONLY)
        return report
    if not harvest.candidates:
        report.update(terminal="partial", reason="no_member_found")
    elif incomplete:
        report.update(terminal="partial", reason=incomplete[0])
    else:
        report.update(terminal="complete", reason=None)
    # #5341: dark unless CONTAINER_NFL_AUTO_PUBLISH_ENABLED; same transaction.
    report["publication"] = await publish_complete_week(
        session, container, target, harvest, assembly,
        fixtures=fixtures, unidentified_limit=REPORT_LIMIT, apply=apply,
    )
    return report


def _publication_not_evaluated(reason: str) -> dict:
    return {"decision": "not_evaluated", "reason": reason}


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


# ---------------------------------------------------------------------------
# #5344: a game the authority moved to another week moves hubs, atomically
# ---------------------------------------------------------------------------
#
# SHIP: when the authoritative schedule moves a game to another week, the next
# complete automatic pass moves it and its questions to the correct hub; old
# links stay truthful and a person's withdrawal is never undone. (Pillars:
# MATCHING / DISCOVER / TRUTH.) Policy A
# (`release-1.0.4-pickup-20261011/5344-CORRECTION-POLICY-DECISION.md`).
#
# THE BARRIER IS TAKEN BEFORE THE FETCH. `read_admission_barrier` reads the
# database clock and ends its transaction, and only then does the pass call
# StatPal: no transaction and no lock is held across the HTTP read. Every
# decision this rule writes carries that barrier, and a container that already
# holds a decision with a LATER barrier refuses an older read outright
# (`container_nfl.admission_verdict`). So a read that stalled on StatPal while a
# later-started read moved the game cannot move it back. It orders OUR reads
# only: StatPal serves no generation, so a replica handing a later read an older
# schedule (residual RA) is a real move back — attributable, revision-bumped,
# never silent.
#
# THE MOVE IS ONE TRANSACTION OVER EVERY CONTAINER IT TOUCHES. The destination
# week's pass finds every other week of the season (by slug, as this read names
# them) holding one of its games, locks the destination and those weeks in
# ascending id order, gates each, removes the game and the questions on it from
# the old weeks (only edges this adapter owns), edges them into the destination
# through `assemble_container`, writes a decision row on both sides and bumps
# each changed revision once. A person's correction locks one week, so it
# queues behind the move or the move queues behind it; it cannot deadlock it.
#
# A MOVE IS NOT A HUMAN VETO. The old week's row is a
# `container_member_decisions` decision (`excluded/authority_relocated`), never
# a `container_corrections` withdrawal, so a later newer read can bring the game
# back. A person's withdrawal stays where it is and still binds: a game
# withdrawn from its destination never arrives there, and a game withdrawn from
# a week never returns to it.

#: The decisions table (#9935, migrated). Without it nothing is moved and no
#: barrier is gated; the pass assembles exactly as before.
DECISIONS_REGCLASS_SQL = (
    "SELECT to_regclass('public.container_member_decisions') IS NOT NULL"
)

#: Every week of the season (as this read names them) holding one of these
#: games, or a question whose CURRENT event is one of them, other than the week
#: being assembled. A question row carries no source here: only the game's own
#: edge can make another writer the holder.
HOLDERS_SQL = (
    "SELECT ee.parent_id, c.slug, ee.child_id, ee.source "
    "FROM event_edges ee JOIN containers c ON c.id = ee.parent_id "
    "WHERE ee.parent_type = 'container' AND ee.kind = 'contains' "
    "  AND ee.child_type = 'event' AND ee.child_id = ANY(:event_ids) "
    "  AND c.slug = ANY(:slugs) AND ee.parent_id <> :cid "
    "UNION ALL "
    "SELECT ee.parent_id, c.slug, fm.event_id, NULL "
    "FROM event_edges ee JOIN containers c ON c.id = ee.parent_id "
    "JOIN futures_markets fm ON fm.id = ee.child_id "
    "WHERE ee.parent_type = 'container' AND ee.kind = 'contains' "
    "  AND ee.child_type = 'market' AND fm.event_id = ANY(:event_ids) "
    "  AND c.slug = ANY(:slugs) AND ee.parent_id <> :cid "
    "ORDER BY 1, 3"
)

#: The games stored in these weeks, with the contest id that names each — the
#: read a pass makes to find games whose new week is outside its window.
STORED_GAMES_SQL = (
    "SELECT c.slug, ev.statpal_fixture_id "
    "FROM containers c "
    "JOIN event_edges ee ON ee.parent_type = 'container' AND ee.parent_id = c.id "
    "     AND ee.kind = 'contains' AND ee.child_type = 'event' "
    "JOIN events ev ON ev.id = ee.child_id "
    "WHERE c.slug = ANY(:slugs) AND ev.statpal_fixture_id IS NOT NULL "
    "ORDER BY c.slug, ev.statpal_fixture_id"
)

PRIOR_DECISIONS_SQL = (
    "SELECT container_id, child_type, child_id, outcome, reason, evidence "
    "FROM container_member_decisions "
    "WHERE container_id = ANY(:cids) AND rule_version = :rule"
)

#: The game's own edge in an old week, owned sources only.
DELETE_EVENT_EDGES_SQL = (
    "DELETE FROM event_edges "
    "WHERE parent_type = 'container' AND parent_id = :cid AND kind = 'contains' "
    "  AND child_type = 'event' AND child_id = ANY(:event_ids) "
    "  AND source = ANY(:owned) "
    "RETURNING child_id"
)

#: The questions that leave with it: only those whose CURRENT event is the moved
#: game (a question relinked elsewhere since stays — contract R5), owned only.
DELETE_MARKET_EDGES_SQL = (
    "DELETE FROM event_edges ee USING futures_markets fm "
    "WHERE ee.parent_type = 'container' AND ee.parent_id = :cid "
    "  AND ee.kind = 'contains' AND ee.child_type = 'market' "
    "  AND fm.id = ee.child_id AND fm.event_id = ANY(:event_ids) "
    "  AND ee.source = ANY(:owned) "
    "RETURNING ee.child_id, fm.event_id"
)

REMAINING_MEMBERS_SQL = (
    "SELECT count(*) FROM event_edges "
    "WHERE parent_type = 'container' AND parent_id = :cid AND kind = 'contains'"
)

RELOCATION_APPLIED = "applied"
RELOCATION_INACTIVE = "inactive"
RELOCATION_NOT_APPLIED = "not_applied"

#: A destination week outside the window is assembled only for the games moving
#: into it; its report says so, and it is never evaluated for publication.
RELOCATION_ONLY = "relocation_only"

#: Why a pass relocates nothing (closed; reports and tests read these names).
INACTIVE_SCHEMA_ABSENT = "decision_schema_absent"
INACTIVE_MARKETS_TRUNCATED = "market_read_truncated"
#: The game left a week by a move; a read that cannot vouch for the whole
#: schedule does not bring it back.
WITHHELD_RELOCATED_AWAY = "relocated_away_needs_complete_read"


@dataclass(frozen=True)
class NflRelocation:
    """What one season pass carries into each week: its read and its barrier."""

    snapshot: PlacementSnapshot
    #: `container_member_decisions` and #9651's ledger + columns are present.
    schema: bool
    #: Set for a destination week outside the window (`RELOCATION_ONLY`).
    only_contests: Optional[frozenset] = None

    @property
    def active(self) -> bool:
        """Moves are allowed: the schema is there and the read is complete."""
        return self.schema and self.snapshot.complete

    def summary(self) -> dict:
        snap = self.snapshot
        return {
            "rule": RELOCATION_RULE_VERSION,
            "source_key": RELOCATION_SOURCE_KEY,
            "barrier": snap.barrier.isoformat() if snap.barrier else None,
            "complete": snap.complete,
            "refusals": list(snap.refusals),
            "placements": len(snap.placements),
            "refused": len(snap.refused),
        }


async def read_admission_barrier(session) -> datetime:
    """The database instant a season read STARTS at, then end the transaction.

    One clock for every dyno. Taken before the HTTP fetch, never after the
    parse (a read that finished late is not a newer read). The transaction is
    rolled back at once — nothing was written — so no connection waits inside
    a transaction while StatPal answers.
    """
    value = (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()
    await session.rollback()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RuntimeError(f"database clock returned {value!r}, not a tz-aware instant")
    return value.astimezone(timezone.utc)


async def relocation_schema_present(session) -> bool:
    if not (await correction_schema_present(session)).complete:
        return False
    row = (await session.execute(text(DECISIONS_REGCLASS_SQL))).fetchone()
    return bool(row and row[0])


async def prepare_nfl_relocation(
    session, read, *, edition: int, barrier: datetime, weeks: list
) -> list:
    """The season pass's runs, in order, each with the relocation it carries.

    ``read`` is a `StatPalNflScheduleRead`; ``weeks`` the current weeks.
    Returns ``[(NflWeek, NflRelocation)]``:

    1. weeks OUTSIDE the window that a game stored in a current week now belongs
       to, each narrowed to those contests (``only_contests``) — the move lands
       in one transaction even though its destination is not a current week;
    2. current weeks a game is moving INTO, so the week it leaves is judged by
       the publication policy after the move, not before;
    3. every other current week.
    """
    duplicates = [d.contest_id for d in getattr(read, "duplicates", ())]
    snapshot = placement_snapshot(
        read.fixtures,
        edition=edition,
        barrier=barrier,
        parse_complete=bool(read.parse_complete),
        duplicate_contest_ids=duplicates,
    )
    relocation = NflRelocation(
        snapshot=snapshot, schema=await relocation_schema_present(session)
    )
    if not relocation.active:
        return [(week, relocation) for week in weeks]

    in_window = {w.slug for w in weeks}
    rows = (
        await session.execute(text(STORED_GAMES_SQL), {"slugs": sorted(in_window)})
    ).fetchall()
    extra: dict[NflWeek, set] = {}
    receiving: set[str] = set()
    for slug, contest_id in rows:
        week = snapshot.placements.get((contest_id or "").strip())
        if week is None or week.slug == slug:
            continue
        if week.slug in in_window:
            receiving.add(week.slug)
        else:
            extra.setdefault(week, set()).add(contest_id.strip())
    plan = [
        (w, replace(relocation, only_contests=frozenset(extra[w])))
        for w in sorted(extra, key=lambda w: w.slug)
    ]
    plan += [(w, relocation) for w in weeks if w.slug in receiving]
    plan += [(w, relocation) for w in weeks if w.slug not in receiving]
    return plan


def _decision_evidence(
    relocation: NflRelocation, contest_id: str, from_slugs, to_slug: str, round_info
) -> dict:
    return {
        "rule": RELOCATION_RULE_VERSION,
        "source_key": RELOCATION_SOURCE_KEY,
        "barrier": relocation.snapshot.barrier.isoformat(),
        "contest_id": contest_id,
        "from_slugs": sorted(from_slugs),
        "to_slug": to_slug,
        "round": round_info,
    }


def _upsert_decision_sql() -> str:
    """Built from the decisions table's one declaration (`theme_definitions`)."""
    from app.utils.theme_definitions import decisions_table

    table = decisions_table()
    columns = [
        "container_id", "child_type", "child_id", "outcome", "reason",
        "rule_version", "evidence", "revision",
    ]
    missing = set(columns) - {c.name for c in table.c}
    if missing:
        raise RuntimeError(f"decisions_table() lacks {sorted(missing)}")
    values = ", ".join(
        "CAST(:evidence AS jsonb)" if c == "evidence" else f":{c}" for c in columns
    )
    return (
        f"INSERT INTO {table.name} ({', '.join(columns)}) VALUES ({values}) "
        "ON CONFLICT ON CONSTRAINT uq_cmd_member DO UPDATE SET "
        "outcome = EXCLUDED.outcome, reason = EXCLUDED.reason, "
        "rule_version = EXCLUDED.rule_version, evidence = EXCLUDED.evidence, "
        "revision = EXCLUDED.revision, last_decided_at = now(), "
        f"attempt_count = {table.name}.attempt_count + 1"
    )


def _evidence(value) -> dict:
    if isinstance(value, (str, bytes)):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


async def _prior_decisions(session, container_ids) -> dict:
    by_container: dict[int, list] = {cid: [] for cid in container_ids}
    if not container_ids:
        return by_container
    rows = (
        await session.execute(
            text(PRIOR_DECISIONS_SQL),
            {"cids": sorted(container_ids), "rule": RELOCATION_RULE_VERSION},
        )
    ).fetchall()
    for cid, child_type, child_id, outcome, reason, evidence in rows:
        by_container.setdefault(int(cid), []).append(
            PriorDecision(child_type, int(child_id), outcome, reason, _evidence(evidence))
        )
    return by_container


async def _holders(session, container_id, event_ids, slugs) -> dict:
    """``{container_id: {"slug", "events": {event_id: {game edge sources}}}}``.

    An empty source set: the week holds only questions on that game (a person
    withdrew the game itself there) — they still leave with the move."""
    held: dict[int, dict] = {}
    if not event_ids or not slugs:
        return held
    rows = (
        await session.execute(
            text(HOLDERS_SQL),
            {"event_ids": sorted(event_ids), "slugs": sorted(slugs), "cid": container_id or 0},
        )
    ).fetchall()
    for parent_id, slug, child_id, source in rows:
        entry = held.setdefault(int(parent_id), {"slug": slug, "events": {}})
        sources = entry["events"].setdefault(int(child_id), set())
        if source is not None:
            sources.add(source)
    return held


def _event_contests(harvest) -> dict:
    """``{event_id: (contest_id, round_info)}`` for the week's member games."""
    rounds = {c.contest_id: c.round_info for c in harvest.selection.contests}
    return {
        c.child_id: (c.external_id, rounds.get(c.external_id))
        for c in harvest.candidates
        if c.child_type == "event"
    }


def _without_events(candidates: list, event_ids: set, market_events: dict) -> list:
    """Drop these games and the questions on them from the candidates."""
    if not event_ids:
        return candidates
    return [
        c
        for c in candidates
        if not (c.child_type == "event" and c.child_id in event_ids)
        and not (c.child_type == "market" and market_events.get(c.child_id) in event_ids)
    ]


async def relocate_into_week(session, container, target: NflWeek, harvest, relocation: NflRelocation):
    """Assemble ``target`` with every move into it, in the caller's transaction.

    Returns ``(relocation_report, assembly_report_or_None)``. ``None`` means the
    barrier gate refused the pass: nothing in any container it touches changed.
    Never commits.
    """
    report: dict = {**relocation.summary(), "state": RELOCATION_APPLIED}
    if relocation.only_contests is not None:
        report["only_contests"] = sorted(relocation.only_contests)
    if not relocation.schema:
        report.update(state=RELOCATION_INACTIVE, reason=INACTIVE_SCHEMA_ABSENT)
        return report, await assemble_container(session, container, harvest.candidates)

    contests = _event_contests(harvest)
    snapshot = relocation.snapshot
    movable: set[int] = set()
    inactive_reason = None
    if not snapshot.complete:
        inactive_reason = snapshot.refusals[0]
    elif harvest.markets_truncated:
        inactive_reason = INACTIVE_MARKETS_TRUNCATED
    else:
        movable = {
            eid for eid, (cid, _) in contests.items() if snapshot.destination(cid) == target.slug
        }
    if inactive_reason:
        report.update(state=RELOCATION_INACTIVE, reason=inactive_reason)

    # Unlocked: who else holds the games moving in. Re-read under the locks.
    first = await _holders(session, container.id, movable, snapshot.week_slugs)
    target_ids = sorted({container.id, *first})
    locked: dict[int, tuple] = {}
    for cid in target_ids:
        row = await lock_container_chain(session, cid)
        if row is not None:
            locked[cid] = row
    if container.id not in locked:
        raise RuntimeError(f"NFL week {target.slug} vanished under the lock")
    holders = await _holders(session, container.id, movable, snapshot.week_slugs)
    unlocked = sorted(h["slug"] for cid, h in holders.items() if cid not in locked)
    if unlocked:
        report["holders_unlocked"] = unlocked
    holders = {cid: h for cid, h in holders.items() if cid in locked}

    # The gate, on every container the pass would touch, before any write.
    priors = await _prior_decisions(session, list(locked))
    for cid in sorted(locked):
        verdict, detail = admission_verdict(priors.get(cid, ()), snapshot)
        if verdict != ADMIT:
            slug = target.slug if cid == container.id else holders.get(cid, first.get(cid, {})).get("slug")
            report.update(state=verdict, reason=verdict, container=slug, detail=detail)
            logger.warning("NFL week %s: %s at %s (%s)", target.slug, verdict, slug, detail)
            return report, None

    market_events = harvest.market_events

    # A game that left this week by a move comes back only on a complete read.
    dest_priors = {
        p.child_id: p for p in priors.get(container.id, ()) if p.child_type == "event"
    }
    away = {
        eid
        for eid in contests
        if (p := dest_priors.get(eid)) is not None
        and p.outcome == "excluded"
        and p.reason == DECISION_RELOCATED
        and eid not in movable
    }
    if away:
        report["withheld_relocated_away"] = sorted(away)
    candidates = _without_events(harvest.candidates, away, market_events)

    # Remove from every old week: owned edges only; a foreign edge holds.
    moved_from: dict[int, set] = {}
    foreign: list = []
    removed: dict[int, dict] = {}
    for cid in sorted(holders):
        holder = holders[cid]
        own = {e for e, sources in holder["events"].items() if sources <= OWNED_EDGE_SOURCES}
        for e, sources in holder["events"].items():
            if e not in own:
                foreign.append(
                    {"event_id": e, "container": holder["slug"], "sources": sorted(sources)}
                )
        if not own:
            continue
        gone = (
            await session.execute(
                text(DELETE_EVENT_EDGES_SQL),
                {"cid": cid, "event_ids": sorted(own), "owned": sorted(OWNED_EDGE_SOURCES)},
            )
        ).fetchall()
        markets = (
            await session.execute(
                text(DELETE_MARKET_EDGES_SQL),
                {"cid": cid, "event_ids": sorted(own), "owned": sorted(OWNED_EDGE_SOURCES)},
            )
        ).fetchall()
        left = {int(r[0]) for r in gone} | {int(r[1]) for r in markets}
        by_event: dict[int, int] = {}
        for r in markets:
            by_event[int(r[1])] = by_event.get(int(r[1]), 0) + 1
        removed[cid] = {"events": left, "markets": len(markets), "by_event": by_event}
        for e in left:
            moved_from.setdefault(e, set()).add(cid)
    if foreign:
        report["foreign_source_holds"] = foreign

    assembly = await assemble_container(session, container, candidates, skip_unchanged=True)
    withdrawn_here = {w["child_id"] for w in assembly.withdrawn if w["child_type"] == "event"}

    # One bump per changed old week; the destination's is assembly's own.
    revisions: dict[int, int] = {}
    emptied: list = []
    for cid, gone in sorted(removed.items()):
        if not gone["events"] and not gone["markets"]:
            continue
        revisions[cid] = await bump_revision(session, cid)
        remaining = (
            await session.execute(text(REMAINING_MEMBERS_SQL), {"cid": cid})
        ).scalar()
        if not remaining and locked[cid][1] == "published":
            emptied.append(holders[cid]["slug"])
    if emptied:
        # Nothing auto-withdraws a hub: a person decides (contract, retirement).
        report["published_hub_emptied_by_relocation"] = emptied
    dest_revision = assembly.revision if assembly.revision is not None else locked[container.id][2]

    # Decision rows, written only when their content changes.
    rows: list[dict] = []
    moved: list = []
    for e in sorted(set(moved_from) | (movable & set(dest_priors))):
        contest_id, round_info = contests[e]
        from_slugs = {holders[c]["slug"] for c in moved_from.get(e, ())}
        prior = dest_priors.get(e)
        if e in withdrawn_here:
            outcome, reason = "withheld", DECISION_RELOCATED_WITHDRAWN
        else:
            outcome, reason = "admitted", DECISION_RELOCATED
        if not from_slugs and (prior is None or (prior.outcome, prior.reason) == (outcome, reason)):
            # Nothing moved, and this week's row already says so: no write.
            continue
        evidence = _decision_evidence(relocation, contest_id, from_slugs, target.slug, round_info)
        if prior is None or (prior.outcome, prior.reason, prior.evidence) != (outcome, reason, evidence):
            rows.append(_decision_row(container.id, e, outcome, reason, evidence, dest_revision))
        for c in sorted(moved_from.get(e, ())):
            rows.append(
                _decision_row(c, e, "excluded", DECISION_RELOCATED, evidence, revisions.get(c, locked[c][2]))
            )
        moved.append(
            {
                "event_id": e,
                "contest_id": contest_id,
                "from_slugs": sorted(from_slugs),
                "to_slug": target.slug,
                "outcome": outcome,
                "markets_removed": sum(
                    removed[c]["by_event"].get(e, 0) for c in moved_from.get(e, ())
                ),
            }
        )
    if rows:
        await session.execute(text(_upsert_decision_sql()), rows)

    report.update(
        moved=moved,
        decisions_written=len(rows),
        revisions={holders[c]["slug"]: r for c, r in revisions.items()},
    )
    if withdrawn_here & set(moved_from):
        report["destination_withdrawn"] = sorted(withdrawn_here & set(moved_from))
    return report, assembly


def _decision_row(container_id, event_id, outcome, reason, evidence, revision) -> dict:
    return {
        "container_id": container_id,
        "child_type": "event",
        "child_id": event_id,
        "outcome": outcome,
        "reason": reason,
        "rule_version": RELOCATION_RULE_VERSION,
        "evidence": json.dumps(evidence, sort_keys=True),
        "revision": int(revision or 0),
    }
