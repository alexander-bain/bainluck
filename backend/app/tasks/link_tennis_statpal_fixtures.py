"""Link each new StatPal tennis fixture to our row, as StatPal publishes it. #2867.

**SHIP: a live tennis card can show the real score line — sets, games, points,
who is serving — because the match on screen is now joined to the StatPal match
that carries them.** (Pillar: TRUTH.)

D59 (Alex, 2026-09-03): a live tennis card's whole score line comes from StatPal
when the match is LINKED, and from ESPN when it is not, never mixed. The live
lane can only build that branch if "linked" has a representation. Measured on
production the same day: **0 of 30,115 tennis rows carried a StatPal id** and no
tennis anchor existed, so the branch had one arm.

`scripts/link_tennis_statpal_anchors_2867.py` writes the link for the matches the
measurement bus already swept (the past, 204 rows, once). **This is the forward
half**: the recurring task that links each fixture as StatPal publishes it, so
the coverage the sweep bought does not decay to zero over the next tournament.

WHAT IT READS, AND WHY ALL THREE
════════════════════════════════
`daily/d1`, `daily/d2` and `livescores`, through the authority door
(`get_schedule_fixtures` / `get_live_fixtures`) so a failed read raises instead
of arriving as an empty slate.

**There is no `daily/d0`** — it answers HTTP 500, not 404 and not an empty
envelope (ARTIFACT-AUTHORITY-20260903-TENNIS §1a). Today's order of play is
unobtainable from `daily`, and today is exactly when a live card needs its link.
`livescores` is the only endpoint that knows a match on the day it is played, so
it is not an optimisation here; it is the arm that covers the day the ship is
about.

`d1`/`d2` are the forward reach and it is genuinely shallow — 70 fixtures on d1,
1 on d2, 0 beyond, because the draw past the next round does not exist yet. A
linker that only looked forward would link tomorrow and never today.

HOW A LINK IS DECIDED
═════════════════════
Normalized player pair (`app/utils/tennis_name_matching`) plus a date window.
Nothing else, and specifically **not** the tournament: our own `sports.key` is
not reliable enough to filter on — a live US Open singles match was sitting under
`tennis_other` on the day this was written — so the tournament is recorded in the
receipt and never used to exclude a candidate.

**±36 hours, and the width is forced.** StatPal stamps `15:00` UTC as a session
placeholder for tennis and backfills the true minute only after the match is
played; we carry our own midnight-UTC placeholder on unlinked rows. Two
placeholders that do not coincide are not a disagreement about when the match is,
and a tight window would read them as one. Measured over 75 real StatPal singles
against 1,026 of our tennis rows on 2026-09-03: 74 matched 1:1, 1 ambiguous, 0
unmatched.

**Exactly one candidate, or nothing is written.** Two candidates is not a tie to
break — it is two of our rows for one match, which is a duplicate, and picking
one hides the finding while stamping half of it. It is reported and left alone
(D35: matching symptoms are filed until lane1/#2693 lands; this task is not
allowed to fix them).

**Doubles are refused before the question is asked.** StatPal writes a pair as
`"Galloway/ Goransson"`; the sweep's token fallback caught 30+ false
doubles-to-singles hits before doubles were excluded. All 32 doubles fixtures on
the measurement day matched nothing.

WHAT IT WRITES
══════════════
Per link, both shapes, for the reason
`scripts/link_tennis_statpal_anchors_2867.py` documents at length: an anchor over
a NULL `events.statpal_fixture_id` is refused as STALE by
`anchor_channel.anchor_is_current` on every read, so writing only the anchor
stamps nothing.

    events.statpal_fixture_id = '2631673'
    event_provider_anchors      ('statpal', 'tennis:2631673', 'game')

The qualifier is `tennis:`, not our `sports.key` — `provider_anchor_keys.
statpal_id_space` carries the argument. Writes go through
`anchor_channel.record_anchor`, so a fixture already claimed by a DIFFERENT event
comes back as `COLLISION` and is reported rather than overwritten.

It never re-links a row that already holds a StatPal id, and it never touches a
row outside tennis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text

from app.services.anchor_channel import COLLISION, WROTE, record_anchor
from app.services.statpal_api import StatPalFixture, get_statpal_service
from app.utils.provider_anchor_keys import statpal_anchor_key, statpal_id_space
from app.utils.tennis_name_matching import DOUBLES_MARKER, pair_matches

logger = logging.getLogger(__name__)

#: The three reads. `d0` is absent because StatPal has no `d0` — see the module
#: docstring. Forward reach beyond `d2` is empty upstream (measured), so asking
#: for it spends a call to learn nothing.
SCHEDULE_DAY_OFFSETS: tuple[int, ...] = (1, 2)

#: How far apart a StatPal start time and ours may be and still be one match.
#:
#: Wide on purpose and NOT a threshold to tune. Both sides carry placeholder
#: start times — StatPal's `15:00` session stamp, our midnight-UTC row — so the
#: honest reading of a gap inside this window is "neither side has committed to a
#: minute yet". Narrowing it would not buy precision; it would silently drop the
#: unplayed fixtures, which are most of what `d1` serves. Precision comes from
#: the name pair and from refusing every ambiguity, not from the clock.
MATCH_WINDOW = timedelta(hours=36)

#: Every tennis row in the window that has no StatPal id yet, with its sport key.
#:
#: `statpal_fixture_id IS NULL` is the whole of the re-link guard: a row that
#: already carries an id is not revisited, so a task that runs every 15 minutes
#: does not re-derive 30,000 rows' worth of decisions to write nothing.
CANDIDATES = """
SELECT e.id, s.key, e.home_team_name, e.away_team_name, e.commence_time,
       e.sport_id
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key LIKE 'tennis%'
   AND e.statpal_fixture_id IS NULL
   AND e.commence_time >= :window_start
   AND e.commence_time <= :window_end
"""

SET_FIXTURE_ID = """
UPDATE events
   SET statpal_fixture_id = :fixture_id
 WHERE id = :event_id
   AND statpal_fixture_id IS NULL
"""


@dataclass
class LinkRun:
    """What one pass did, in terms a receipt can be written from.

    Every fixture the task looked at lands in exactly one bucket. A run that
    reports only its successes cannot tell "StatPal published nothing" from "we
    matched nothing", and those need different fixes.
    """

    fixtures_read: int = 0
    doubles_skipped: int = 0
    already_linked: int = 0
    linked: int = 0
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    unmatched: list[dict[str, Any]] = field(default_factory=list)
    collisions: list[dict[str, Any]] = field(default_factory=list)
    sources_read: list[str] = field(default_factory=list)
    read_failures: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "fixtures_read": self.fixtures_read,
            "doubles_skipped": self.doubles_skipped,
            "already_linked": self.already_linked,
            "linked": self.linked,
            "ambiguous": len(self.ambiguous),
            "unmatched": len(self.unmatched),
            "collisions": len(self.collisions),
            "sources_read": self.sources_read,
            "read_failures": self.read_failures,
        }


def _is_doubles(fixture: StatPalFixture) -> bool:
    return DOUBLES_MARKER in (fixture.home_team or "") or DOUBLES_MARKER in (
        fixture.away_team or ""
    )


#: The four things one fixture can be. A verdict, not a score.
VERDICT_DOUBLES = "DOUBLES"
VERDICT_LINK = "LINK"
VERDICT_AMBIGUOUS = "AMBIGUOUS"
VERDICT_UNMATCHED = "UNMATCHED"


def classify_fixture(
    fixture: StatPalFixture, pool: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    """Which of our rows, if any, is this StatPal fixture?

    Pure: no session, no clock, no network. This is the whole decision the task
    makes, hoisted so it can be driven by real StatPal payloads and real event
    rows rather than by a mock that agrees with whatever it is told.

    Returns the verdict and the candidates it was reached on — `AMBIGUOUS`
    carries all of them, because "two rows matched" without saying which two is
    a count, and the receipt has to be actionable.
    """
    if _is_doubles(fixture):
        return VERDICT_DOUBLES, []

    if fixture.start_time is None:
        # No start time is not a wide window, it is no window. Matching on names
        # alone across a whole tournament would pair a first-round match with the
        # same two players' meeting a year later.
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
    return VERDICT_LINK, matches


def _receipt(fixture: StatPalFixture, **extra: Any) -> dict[str, Any]:
    """One unmatched or ambiguous fixture, with enough to act on it.

    The directive asks for receipts for every unmatched row, and a receipt that
    says "2631673 did not match" is not one. The two names and the start time are
    what a person needs to decide whether the miss is our gap or StatPal's.
    """
    return {
        "statpal_id": fixture.fixture_id,
        "players": [fixture.home_team, fixture.away_team],
        "start_time": fixture.start_time.isoformat() if fixture.start_time else None,
        "tournament": fixture.league,
        "status": fixture.status,
        **extra,
    }


async def _read_fixtures(service, run: LinkRun) -> list[StatPalFixture]:
    """Every tennis fixture StatPal will tell us about right now, deduped by id.

    Each source is read in its own try/except so one endpoint failing does not
    cost the others (gotcha #42) — but the failure is RECORDED, not swallowed. A
    run that read one of three endpoints and linked what it could is a different
    fact from a run that read all three, and only the receipt can say which one
    happened.
    """
    from app.services.statpal_api import StatPalUpstreamError

    seen: set[str] = set()
    fixtures: list[StatPalFixture] = []

    async def _collect(label: str, coro) -> None:
        try:
            batch = await coro
        except StatPalUpstreamError as e:
            run.read_failures.append(f"{label}: {e}")
            logger.warning("StatPal tennis %s unreadable: %s", label, e)
            return
        run.sources_read.append(label)
        for f in batch:
            if not f.fixture_id or f.fixture_id in seen:
                continue
            seen.add(f.fixture_id)
            fixtures.append(f)

    await _collect("livescores", service.get_live_fixtures("tennis"))
    for offset in SCHEDULE_DAY_OFFSETS:
        await _collect(
            f"daily/d{offset}", service.get_schedule_fixtures("tennis", offset)
        )

    run.fixtures_read = len(fixtures)
    return fixtures


async def _candidates(session, start: datetime, end: datetime) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(CANDIDATES), {"window_start": start, "window_end": end}
        )
    ).fetchall()
    return [
        {
            "id": r[0],
            "sport_key": r[1],
            "home": r[2],
            "away": r[3],
            "commence_time": r[4],
            "sport_id": r[5],
        }
        for r in rows
    ]


async def _link_one(session, fixture: StatPalFixture, candidate: dict) -> str:
    """Write both shapes for one match. Returns the anchor outcome.

    The column is written FIRST and guarded by `statpal_fixture_id IS NULL`, so
    two concurrent passes cannot both claim it: the loser's UPDATE touches no row
    and it stops before writing an anchor for a link it did not make.
    """
    result = await session.execute(
        text(SET_FIXTURE_ID),
        {"event_id": candidate["id"], "fixture_id": fixture.fixture_id},
    )
    if not (result.rowcount or 0):
        return "LOST_RACE"

    key = statpal_anchor_key(
        fixture.fixture_id, statpal_id_space(candidate["sport_key"])
    )
    written = await record_anchor(
        session,
        event_id=candidate["id"],
        key=key,
        claim_context={
            "written_by": "link_tennis_statpal_fixtures",
            "tournament": fixture.league,
            "statpal_start_time": (
                fixture.start_time.isoformat() if fixture.start_time else None
            ),
        },
    )
    return written.outcome


async def _run_link_tennis_statpal_fixtures(
    *, apply: bool = True, now: Optional[datetime] = None
) -> dict[str, Any]:
    """One pass. `apply=False` plans and writes nothing — the dark-run arm."""
    from app.tasks.base import get_task_session

    now = now or datetime.now(timezone.utc)
    run = LinkRun()

    service = get_statpal_service()
    try:
        fixtures = await _read_fixtures(service, run)
    finally:
        await service.close()

    if not fixtures:
        # Loud, not silent. Zero fixtures with no read failure means StatPal has
        # no tennis at all — a real off-season answer. Zero WITH failures means
        # we could not ask, and reporting those identically is gotcha #53.
        logger.warning(
            "StatPal tennis linker read 0 fixtures (sources=%s, failures=%s)",
            run.sources_read,
            run.read_failures,
        )
        return run.summary()

    starts = [f.start_time for f in fixtures if f.start_time]
    window_start = (min(starts) if starts else now) - MATCH_WINDOW
    window_end = (max(starts) if starts else now) + MATCH_WINDOW

    async with get_task_session() as session:
        pool = await _candidates(session, window_start, window_end)

        for fixture in fixtures:
            verdict, matches = classify_fixture(fixture, pool)

            if verdict == VERDICT_DOUBLES:
                run.doubles_skipped += 1
                continue
            if verdict == VERDICT_UNMATCHED:
                run.unmatched.append(_receipt(fixture))
                continue
            if verdict == VERDICT_AMBIGUOUS:
                # Two of our rows for one StatPal match. A duplicate, proven by
                # something better than a name window — and not this task's to
                # resolve (D35, #2693). Write nothing; say exactly which rows.
                run.ambiguous.append(
                    _receipt(
                        fixture,
                        candidates=[
                            {
                                "event_id": c["id"],
                                "sport_key": c["sport_key"],
                                "teams": [c["home"], c["away"]],
                                "commence_time": c["commence_time"].isoformat(),
                            }
                            for c in matches
                        ],
                    )
                )
                continue

            candidate = matches[0]
            if not apply:
                run.linked += 1
                continue

            try:
                outcome = await _link_one(session, fixture, candidate)
            except Exception as e:  # one bad row never wipes the pass (#42)
                await session.rollback()
                logger.exception(
                    "StatPal tennis link failed for fixture %s -> event %s: %s",
                    fixture.fixture_id, candidate["id"], e,
                )
                run.unmatched.append(_receipt(fixture, error=str(e)))
                continue

            if outcome == COLLISION:
                await session.rollback()
                run.collisions.append(
                    _receipt(fixture, event_id=candidate["id"], outcome=outcome)
                )
                continue
            if outcome == "LOST_RACE":
                run.already_linked += 1
                await session.rollback()
                continue

            await session.commit()
            run.linked += 1
            # The pool is per-pass, so a row linked by this pass must not be
            # offered to the next fixture — otherwise two StatPal matches can
            # both "match" it and the second one silently loses the race
            # instead of being reported as the ambiguity it is.
            pool = [c for c in pool if c["id"] != candidate["id"]]
            if outcome != WROTE:
                logger.info(
                    "StatPal tennis anchor for fixture %s on event %s: %s",
                    fixture.fixture_id, candidate["id"], outcome,
                )

    summary = run.summary()
    logger.info("StatPal tennis linker: %s", summary)
    return {
        **summary,
        "ambiguous_receipts": run.ambiguous,
        "unmatched_receipts": run.unmatched,
        "collision_receipts": run.collisions,
    }
