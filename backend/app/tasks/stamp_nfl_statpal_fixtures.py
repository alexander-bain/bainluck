"""Stamp every NFL row with the StatPal contest it is, and receipt the rest. #2867 / D50.

**SHIP: an NFL game page can eventually show StatPal's drive-by-drive truth
instead of a second-hand score, because the game on screen is now joined to the
StatPal contest that carries it. Today that join is DARK — nothing reads it — and
this is the measurement that decides whether it may ever be read.** (Pillar: TRUTH.)

D50 (Alex, 2026-09-03) commissions StatPal-as-canonical **dark, NFL first**, and
sets the gate in one sentence: *nothing user-visible flips without a measured
7-day ≥99.5% agreement row from the bus AND a YOUR-TURN entry Alex has seen.*
That measurement needs a per-game correspondence to measure over. There isn't
one. Measured on production 2026-09-04, of 322 NFL rows:

    statpal_fixture_id IS NULL                          274
    statpal_fixture_id holds a real StatPal id            0
    statpal_fixture_id holds `statpal_live_<home>_<away>` 48   (#2963)

Zero NFL rows carry a StatPal contest id and zero NFL anchors exist, so
"do StatPal and we agree about this game?" has no join to ask it over. This task
writes that join and nothing else.

WHAT "SHADOW" MEANS HERE, PRECISELY
═══════════════════════════════════
It writes identity, never content. No score, no status, no start time, no team,
and — the one that matters most — **it never creates a row.** Every write is an
`UPDATE` of an event that already exists, plus its anchor. A StatPal fixture we
do not hold is a *receipt*, not an insert: ruling 048 is unmoved by this file,
and the honest answer to "StatPal has a game we don't" is to say so, because that
is a finding about our ingestion and inventing the row would erase it.

WHAT IT READS
═════════════
`season-schedule` and `livescores`, through the authority door
(`get_schedule_fixtures` / `get_live_fixtures`) so a failed read raises instead of
arriving as an empty slate (gotcha #53).

`season-schedule` is the whole season in one call — Pre, Regular and Post,
374 games measured 2026-09-03 — which is why this runs hourly and not every ten
minutes like tennis. There is no per-day endpoint to walk and nothing to gain
from walking one. `livescores` is added for the same reason it is in the tennis
linker: it is the only endpoint that knows a game while it is being played, and
a game that goes live unlinked is exactly the case the eventual reader cares
about.

HOW A LINK IS DECIDED
═════════════════════
**Both team names, exactly, plus kickoff within ±1 hour.** Nothing else.

The names are equality after normalization and not a similarity — StatPal's 32
NFL team names and ours are the *same 32 strings* (`app/utils/nfl_team_matching`
carries the measurement). A looser rule buys nothing and costs a great deal:
production holds two Week-1 rows at 2026-09-13 20:25, `Los Angeles Rams v
Arizona Cardinals` and `Los Angeles Chargers v Arizona Cardinals`, where StatPal
has only the Chargers game. Exact matching links the real one and leaves the
phantom visible; a city-token fallback would link whichever it reached first.

**±1 hour is generous, not tight.** Measured over the 16 Week-1 games in the
banked `season-schedule` body against production rows, StatPal's kickoff and ours
agree **to the minute on all 16**. The hour is there for a broadcast-window
correction, not because anything needs it. This is the opposite of the tennis
±36h, and for a stated reason: tennis start times are session placeholders on
both sides, NFL kickoffs are scheduled facts that both sides already agree on.

**Exactly one candidate, or nothing is written.** Two of our rows matching one
StatPal contest is a duplicate — proven by something better than a name window —
and picking one hides the finding while stamping half of it. Reported with both
row ids and left alone (D35: matching symptoms are filed until lane1/#2693
lands; this task may not fix them).

WHAT IT WRITES
══════════════
Per link, both shapes, for the reason
`scripts/link_tennis_statpal_anchors_2867.py` documents at length: an anchor over
a NULL column is refused as STALE by `anchor_channel.anchor_is_current` on every
read, so writing only the anchor stamps nothing.

    events.statpal_fixture_id = '280445'
    event_provider_anchors      ('statpal', 'americanfootball_nfl:280445', 'game')

The qualifier is our `sports.key` and that is `statpal_id_space`'s answer, not an
assumption: NFL is 1:1 between StatPal's `nfl` and our `americanfootball_nfl`, so
passing the key through names the space exactly. (Tennis is the sport where that
is false, and `statpal_id_space` is where the difference lives.)

**A link is both shapes or neither.** Only `WROTE` and `CONFIRMED` mean the
anchor names this event; every other outcome rolls the column write back and is
receipted (CERT-871 FOLLOW-UP `AUTHORITY-006-LINK-WRITE-OUTCOMES`, generalised
here from the start rather than learned again).

THE POLLUTED COLUMN, AND WHY IT IS A RECEIPT AND NOT A REPAIR
══════════════════════════════════════════════════════════════
All 48 NFL rows that already hold a `statpal_fixture_id` hold a *fabricated*
one — `statpal_live_Las Vegas Raiders_Arizona Cardinals`, from
`statpal_sync.py:337`'s `or` fallback (#2963). Two consequences this task has to
handle rather than trip over:

  * the usual `statpal_fixture_id IS NULL` candidate guard skips them, so they
    can never receive a real contest id and would silently never appear;
  * their value cannot be anchored — a `game` anchor keyed on team names is the
    one thing in this system that can merge two real fixtures.

So they are selected deliberately, classified `POLLUTED_COLUMN`, receipted with
the offending value, and **not written to**. Overwriting the column is a repair
with its own blast radius (a live-ingestion path reads it) and belongs to #2963
under D51, not to a stamper.

RECEIPTS RUN IN BOTH DIRECTIONS
════════════════════════════════
The directive asks for receipts for misses, and a miss has two shapes. A StatPal
contest we hold no row for is an *ingestion gap*. One of our rows that no StatPal
contest matches is a *candidate phantom* — which is how the two Los Angeles
duplicates above become visible without anyone going looking. Reporting only the
first direction would have hidden them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text

from app.services.anchor_channel import (
    COLLISION,
    CONFIRMED,
    WROTE,
    record_anchor,
)
from app.services.statpal_api import StatPalFixture, get_statpal_service
from app.utils.nfl_team_matching import is_known_nfl_team, pair_matches
from app.utils.provider_anchor_keys import statpal_anchor_key, statpal_id_space

logger = logging.getLogger(__name__)

#: Our `sports.key` for the NFL, and — because NFL is 1:1 with StatPal's `nfl` —
#: also the StatPal id space. `statpal_id_space` is still asked rather than
#: assumed, so the day a sport stops being 1:1 there is one place to change.
NFL_SPORT_KEY = "americanfootball_nfl"

#: How far apart a StatPal kickoff and ours may be and still be one game.
#:
#: Measured, not tuned: all 16 Week-1 games agree to the minute. The hour absorbs
#: a broadcast-window correction on one side. It is NOT a knob to widen when
#: something fails to match — a two-hour gap between two scheduled NFL kickoffs is
#: evidence they are different games, and the next-cheapest reading of a miss is
#: that one of the two rows is wrong.
MATCH_WINDOW = timedelta(hours=1)

#: How far either side of the read fixtures the candidate query reaches. One
#: window's slack past the outermost kickoff and no further: the season schedule
#: already spans August to January, so a wider reach would pull in rows no
#: fixture could possibly claim.
CANDIDATE_SLACK = MATCH_WINDOW

#: Every NFL row in the window, linked or not, with the value of its column.
#:
#: Deliberately NOT filtered to `statpal_fixture_id IS NULL`. That guard is what
#: makes the 48 polluted rows (#2963) invisible, and invisible is the one thing
#: they must not be. Classification decides what each row is; the query's job is
#: to leave nothing out. The window keeps it bounded — a few hundred rows, never
#: the whole table.
CANDIDATES = """
SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time,
       e.statpal_fixture_id, e.status
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key = :sport_key
   AND e.commence_time >= :window_start
   AND e.commence_time <= :window_end
"""

SET_FIXTURE_ID = """
UPDATE events
   SET statpal_fixture_id = :fixture_id
 WHERE id = :event_id
   AND statpal_fixture_id IS NULL
"""


def is_statpal_contest_id(value: Optional[str]) -> bool:
    """Is this column value a StatPal id at all, or `statpal_live_...` (#2963)?

    All-digits, which is what every measured StatPal id space is: NFL 6-digit
    `contestid`, MLB 6- and 10-digit, NBA 6- and 7-digit, NHL 6-digit, tennis
    7-digit. Deliberately not a length check — D55 removed digit-counting from
    the anchor key precisely because a length rule gives a confident wrong answer
    the moment a new sport arrives, and this predicate only has to separate "an
    id" from "a sentence containing team names".
    """
    if value is None:
        return False
    token = str(value).strip()
    return bool(token) and token.isdigit()


@dataclass
class StampRun:
    """What one pass did, in terms a receipt can be written from.

    Every fixture read and every candidate row lands in exactly one bucket. A run
    that reports only its successes cannot tell "StatPal published nothing" from
    "we matched nothing", and those need different fixes.
    """

    fixtures_read: int = 0
    rows_in_window: int = 0
    already_linked: int = 0
    stamped: int = 0
    #: A StatPal contest matched exactly one of our rows, but that row already
    #: holds a fabricated `statpal_fixture_id` (#2963). Never written to.
    polluted_column: list[dict[str, Any]] = field(default_factory=list)
    #: Two of our rows for one StatPal contest. D35: filed, not resolved.
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    #: StatPal has this contest and we hold no row for it — an ingestion gap.
    unmatched_fixtures: list[dict[str, Any]] = field(default_factory=list)
    #: We hold this row and no StatPal contest matches it — a candidate phantom.
    unmatched_rows: list[dict[str, Any]] = field(default_factory=list)
    collisions: list[dict[str, Any]] = field(default_factory=list)
    #: Candidate found, column write went through, ANCHOR write refused. Rolled
    #: back, never committed (CERT-871 FOLLOW-UP `AUTHORITY-006-LINK-WRITE-OUTCOMES`).
    write_refusals: list[dict[str, Any]] = field(default_factory=list)
    #: A team name on either side that is not one of the measured 32. Reporting
    #: only — the match never consults the roster.
    unknown_team_names: list[str] = field(default_factory=list)
    sources_read: list[str] = field(default_factory=list)
    read_failures: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "fixtures_read": self.fixtures_read,
            "rows_in_window": self.rows_in_window,
            "already_linked": self.already_linked,
            "stamped": self.stamped,
            "polluted_column": len(self.polluted_column),
            "ambiguous": len(self.ambiguous),
            "unmatched_fixtures": len(self.unmatched_fixtures),
            "unmatched_rows": len(self.unmatched_rows),
            "collisions": len(self.collisions),
            "write_refusals": len(self.write_refusals),
            "unknown_team_names": sorted(set(self.unknown_team_names)),
            "sources_read": self.sources_read,
            "read_failures": self.read_failures,
        }


#: `_stamp_one`'s own outcome for "the column was claimed between the candidate
#: query and the write". Not an anchor outcome — `anchor_channel` never returns
#: it — so it is named here rather than borrowed from there.
LOST_RACE = "LOST_RACE"

#: The ONLY two anchor outcomes that mean the anchor names this event, so the
#: only two under which the column write may be committed. A whitelist, not a
#: blacklist: a new outcome added to `anchor_channel` must be considered here
#: explicitly, and until it is, it refuses and is receipted.
COMMITTABLE_OUTCOMES = frozenset({WROTE, CONFIRMED})

#: The five things one StatPal contest can be against our table. A verdict, not
#: a score.
VERDICT_STAMP = "STAMP"
VERDICT_ALREADY_LINKED = "ALREADY_LINKED"
VERDICT_POLLUTED = "POLLUTED_COLUMN"
VERDICT_AMBIGUOUS = "AMBIGUOUS"
VERDICT_UNMATCHED = "UNMATCHED"


def classify_fixture(
    fixture: StatPalFixture, pool: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    """Which of our rows, if any, is this StatPal contest?

    Pure: no session, no clock, no network. This is the whole decision the task
    makes, hoisted so it can be driven by real StatPal payloads and real event
    rows rather than by a mock that agrees with whatever it is told.

    Returns the verdict and the candidates it was reached on. `AMBIGUOUS` carries
    all of them, because "two rows matched" without saying which two is a count,
    and a receipt has to be actionable.
    """
    if fixture.start_time is None:
        # No kickoff is not a wide window, it is no window. Two teams meet twice
        # a season; matching on names alone would pair Week 3 with Week 14.
        return VERDICT_UNMATCHED, []

    matches = [
        c
        for c in pool
        if c.get("commence_time") is not None
        and abs(c["commence_time"] - fixture.start_time) <= MATCH_WINDOW
        and pair_matches(
            (fixture.home_team, fixture.away_team), (c["home"], c["away"])
        )
    ]
    if not matches:
        return VERDICT_UNMATCHED, []
    if len(matches) > 1:
        return VERDICT_AMBIGUOUS, matches

    row = matches[0]
    current = row.get("statpal_fixture_id")
    if current is None or not str(current).strip():
        return VERDICT_STAMP, matches
    if not is_statpal_contest_id(current):
        # #2963. The column says linked and holds a sentence. Not ours to repair.
        return VERDICT_POLLUTED, matches
    return VERDICT_ALREADY_LINKED, matches


def _fixture_receipt(fixture: StatPalFixture, **extra: Any) -> dict[str, Any]:
    """One fixture-side finding, with enough in it to act on.

    "280445 did not match" is not a receipt. The two teams and the kickoff are
    what a person needs to decide whether the miss is our gap or StatPal's.
    """
    return {
        "statpal_id": fixture.fixture_id,
        "teams": [fixture.away_team, fixture.home_team],
        "kickoff": fixture.start_time.isoformat() if fixture.start_time else None,
        "round": fixture.round_info,
        "status": fixture.status,
        **extra,
    }


def _row_receipt(row: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """One of our rows that no StatPal contest claimed — a candidate phantom."""
    return {
        "event_id": row["id"],
        "teams": [row["away"], row["home"]],
        "commence_time": (
            row["commence_time"].isoformat() if row.get("commence_time") else None
        ),
        "status": row.get("status"),
        "statpal_fixture_id": row.get("statpal_fixture_id"),
        **extra,
    }


async def _read_fixtures(service, run: StampRun) -> list[StatPalFixture]:
    """Every NFL contest StatPal will tell us about right now, deduped by id.

    Each source is read in its own try/except so one endpoint failing does not
    cost the other (gotcha #42) — but the failure is RECORDED, not swallowed. A
    run that read one of two endpoints and stamped what it could is a different
    fact from a run that read both, and only the receipt can say which happened.
    """
    from app.services.statpal_api import StatPalUpstreamError

    seen: set[str] = set()
    fixtures: list[StatPalFixture] = []

    async def _collect(label: str, coro) -> None:
        try:
            batch = await coro
        except StatPalUpstreamError as e:
            run.read_failures.append(f"{label}: {e}")
            logger.warning("StatPal NFL %s unreadable: %s", label, e)
            return
        run.sources_read.append(label)
        for f in batch:
            if not f.fixture_id or f.fixture_id in seen:
                continue
            seen.add(f.fixture_id)
            fixtures.append(f)

    await _collect("season-schedule", service.get_schedule_fixtures("nfl"))
    await _collect("livescores", service.get_live_fixtures("nfl"))

    run.fixtures_read = len(fixtures)
    return fixtures


async def _candidates(session, start: datetime, end: datetime) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(CANDIDATES),
            {
                "sport_key": NFL_SPORT_KEY,
                "window_start": start,
                "window_end": end,
            },
        )
    ).fetchall()
    return [
        {
            "id": r[0],
            "home": r[1],
            "away": r[2],
            "commence_time": r[3],
            "statpal_fixture_id": r[4],
            "status": r[5],
        }
        for r in rows
    ]


async def _stamp_one(session, fixture: StatPalFixture, candidate: dict) -> str:
    """Write both shapes for one game. Returns the anchor outcome.

    The column is written FIRST and guarded by `statpal_fixture_id IS NULL`, so
    two concurrent passes cannot both claim it: the loser's UPDATE touches no row
    and it stops before writing an anchor for a link it did not make.
    """
    result = await session.execute(
        text(SET_FIXTURE_ID),
        {"event_id": candidate["id"], "fixture_id": fixture.fixture_id},
    )
    if not (result.rowcount or 0):
        return LOST_RACE

    key = statpal_anchor_key(fixture.fixture_id, statpal_id_space(NFL_SPORT_KEY))
    written = await record_anchor(
        session,
        event_id=candidate["id"],
        key=key,
        claim_context={
            "written_by": "stamp_nfl_statpal_fixtures",
            "round": fixture.round_info,
            "statpal_kickoff": (
                fixture.start_time.isoformat() if fixture.start_time else None
            ),
        },
    )
    return written.outcome


def _note_unknown_names(run: StampRun, *names: Optional[str]) -> None:
    for name in names:
        if name and not is_known_nfl_team(name):
            run.unknown_team_names.append(str(name))


async def _run_stamp_nfl_statpal_fixtures(
    *, apply: bool = True, now: Optional[datetime] = None
) -> dict[str, Any]:
    """One pass. `apply=False` plans and writes nothing — the dark-run arm."""
    from app.tasks.base import get_task_session

    now = now or datetime.now(timezone.utc)
    run = StampRun()

    service = get_statpal_service()
    try:
        fixtures = await _read_fixtures(service, run)
    finally:
        await service.close()

    if not fixtures:
        # Loud, not silent. Zero fixtures with no read failure means StatPal has
        # no NFL at all — a real answer in June. Zero WITH failures means we could
        # not ask, and reporting those identically is gotcha #53.
        logger.warning(
            "StatPal NFL stamper read 0 fixtures (sources=%s, failures=%s)",
            run.sources_read,
            run.read_failures,
        )
        return run.summary()

    kickoffs = [f.start_time for f in fixtures if f.start_time]
    window_start = (min(kickoffs) if kickoffs else now) - CANDIDATE_SLACK
    window_end = (max(kickoffs) if kickoffs else now) + CANDIDATE_SLACK

    async with get_task_session() as session:
        pool = await _candidates(session, window_start, window_end)
        run.rows_in_window = len(pool)
        #: Which of our rows some StatPal contest claimed, so the leftovers can be
        #: reported as candidate phantoms. Claimed covers every verdict that names
        #: a row, not only the ones we wrote: an already-linked or polluted row is
        #: accounted for, and calling it a phantom would be a second wrong answer.
        claimed: set[int] = set()

        for fixture in fixtures:
            _note_unknown_names(run, fixture.home_team, fixture.away_team)
            verdict, matches = classify_fixture(fixture, pool)

            if verdict == VERDICT_UNMATCHED:
                run.unmatched_fixtures.append(_fixture_receipt(fixture))
                continue

            for c in matches:
                claimed.add(c["id"])

            if verdict == VERDICT_AMBIGUOUS:
                # Two of our rows for one StatPal contest — a duplicate, proven by
                # something better than a name window, and not this task's to
                # resolve (D35, #2693). Write nothing; say exactly which rows.
                run.ambiguous.append(
                    _fixture_receipt(
                        fixture,
                        candidates=[
                            {
                                "event_id": c["id"],
                                "teams": [c["away"], c["home"]],
                                "commence_time": c["commence_time"].isoformat(),
                                "statpal_fixture_id": c["statpal_fixture_id"],
                            }
                            for c in matches
                        ],
                    )
                )
                continue

            candidate = matches[0]

            if verdict == VERDICT_ALREADY_LINKED:
                run.already_linked += 1
                continue

            if verdict == VERDICT_POLLUTED:
                # #2963. Receipted with the offending value and left alone: the
                # repair has a blast radius this task is not carrying.
                run.polluted_column.append(
                    _fixture_receipt(
                        fixture,
                        event_id=candidate["id"],
                        column_holds=candidate["statpal_fixture_id"],
                    )
                )
                continue

            if not apply:
                run.stamped += 1
                continue

            try:
                outcome = await _stamp_one(session, fixture, candidate)
            except Exception as e:  # one bad row never wipes the pass (#42)
                await session.rollback()
                logger.exception(
                    "StatPal NFL stamp failed for contest %s -> event %s: %s",
                    fixture.fixture_id, candidate["id"], e,
                )
                run.unmatched_fixtures.append(_fixture_receipt(fixture, error=str(e)))
                continue

            if outcome == LOST_RACE:
                run.already_linked += 1
                await session.rollback()
                continue

            if outcome not in COMMITTABLE_OUTCOMES:
                # A whitelist, not a blacklist. `STALE_INCUMBENT` and `NO_KEY`
                # would otherwise leave the column set with NO ANCHOR AT ALL — a
                # row whose column says linked while the anchor table says
                # nothing, which no reader can see.
                await session.rollback()
                run.write_refusals.append(
                    _fixture_receipt(
                        fixture, event_id=candidate["id"], outcome=outcome
                    )
                )
                if outcome == COLLISION:
                    run.collisions.append(
                        _fixture_receipt(
                            fixture, event_id=candidate["id"], outcome=outcome
                        )
                    )
                continue

            await session.commit()
            run.stamped += 1
            # The pool is per-pass, so a row stamped by this pass must not be
            # offered to the next contest — otherwise two StatPal games can both
            # "match" it and the second silently loses the race instead of being
            # reported as the ambiguity it is.
            pool = [c for c in pool if c["id"] != candidate["id"]]
            if outcome != WROTE:
                logger.info(
                    "StatPal NFL anchor for contest %s on event %s: %s",
                    fixture.fixture_id, candidate["id"], outcome,
                )

        # The other direction. A row inside the window that no contest claimed is
        # a candidate phantom, and it is the only way the two Los Angeles
        # duplicates in Week 1 become visible without someone going to look.
        for row in pool:
            if row["id"] in claimed:
                continue
            _note_unknown_names(run, row.get("home"), row.get("away"))
            run.unmatched_rows.append(_row_receipt(row))

    summary = run.summary()
    logger.info("StatPal NFL stamper: %s", summary)
    return {
        **summary,
        "polluted_column_receipts": run.polluted_column,
        "ambiguous_receipts": run.ambiguous,
        "unmatched_fixture_receipts": run.unmatched_fixtures,
        "unmatched_row_receipts": run.unmatched_rows,
        "collision_receipts": run.collisions,
        "write_refusal_receipts": run.write_refusals,
    }
