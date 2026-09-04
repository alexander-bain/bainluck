"""Stamp every NBA and NHL row with the StatPal contest it is. #2867 / D50, step 3.

**SHIP: an NBA or NHL game page can eventually show StatPal's period-by-period
truth instead of a second-hand score, because the game on screen is now joined to
the StatPal contest that carries it. The join is DARK — nothing reads it — and it
is the measurement that decides whether it may ever be read.** (Pillar: MATCHING.)

Program step 2 did this for the NFL (`tasks/stamp_nfl_statpal_fixtures`). Step 3
does it for the two sports that share StatPal's *flat v1 season-schedule* shape,
and one module serves both because they are the same problem: one call returns
the whole season as `scores.tournament.match[]`, both sides spell the franchises
identically, and `time` is UTC on both. NFL keeps its own module — its payload
nests three levels deeper, it is the only sport with `datetime_utc`, and it is in
front of the bus.

WHAT WAS MEASURED FIRST, 2026-09-04 ~5:10am PT
══════════════════════════════════════════════
The directive for this step says: *do the NFL lesson first, not last — measure
how far apart the two sides' start times actually are before choosing a window.*
Live `GET /v1/{nba,nhl}/season-schedule` against production `events`:

    league  StatPal  ours in-window  same-orientation join  swapped  no key
    NBA      1206         41               41 / 41              0       0
    NHL      1404         32               32 / 32              0       0

    kickoff delta, StatPal minus ours
    NBA   41 of 41 agree TO THE MINUTE
    NHL   25 of 32 to the minute, 1 at +0:30, 1 at +1:00, and FIVE at +18:30…+22:00

Three findings came out of that table, and each one is a decision below.

1. **±1 HOUR IS THE MEASURED CEILING, NOT A HABIT INHERITED FROM THE NFL.**
   In both leagues the same pair meets twice, in the same orientation, **23 hours
   apart** — NBA `Oklahoma City @ Portland` on 2026-11-11 04:00Z and 2026-11-12
   03:00Z; NHL `Dallas @ Winnipeg` on 2026-12-20 00:00Z and 23:00Z. Those are real
   back-to-backs at one venue. A window wider than **11.5h** can therefore reach
   both meetings of a back-to-back and stamp a game with the next night's contest.
   ±1h is well inside that and captures every honest kickoff either side serves.

2. **The five NHL outliers are OUR clock, and they are above the safe ceiling.**
   All five sit at exactly `04:00:00Z` — midnight US Eastern — on 2026-10-01 and
   2026-10-02 preseason rows, against StatPal times 18.5–22h later. That is our
   placeholder for a start time nobody has set, not a broadcast correction. They
   cannot be stamped by ANY window that is safe against finding 1, so they are
   receipted as unmatched rows and filed. Saying so here is the point: NFL's
   equivalent — 30 rows behind an unset Weeks 16–18 kickoff — was discovered as a
   76%-vs-99% surprise, and this one is stated before it can be one.

3. **The agreement number for these two sports is NOT about identity, and the
   ledger spec's denominator makes it unreachable.** StatPal publishes the whole
   season on day one (1206 / 1404); we hold only games that have odds posted
   (41 / 32). Under `ARTIFACT-AUTHORITY-LEDGER-SPEC.md`'s NBA rule 5 — *denominator:
   all 1206 scheduled games* — identity reads **3.40%** for NBA and **2.28%** for
   NHL and can never approach D50's 99.5%, for a reason that is not a disagreement.
   Of the games WE hold, StatPal has **41/41 and 32/32**. Both numbers are
   published, neither is blended, and which one should govern is a question for
   Alex, raised in the artifact — not something this file quietly decides.

WHAT "SHADOW" MEANS HERE, PRECISELY
═══════════════════════════════════
Identity, never content. No score, no status, no start time, no team, and **it
never creates a row.** Every write is an `UPDATE` of an event that already exists,
plus its anchor. A StatPal fixture we hold no row for is a *receipt*, not an
insert: ruling 048 is unmoved, and the honest answer to "StatPal has a game we
don't" is to say so, because that is a finding about our ingestion.

THE STATE THESE TWO SPORTS ARE ALREADY IN, WHICH THE NFL WAS NOT
════════════════════════════════════════════════════════════════
`tasks/statpal_sync` already writes `events.statpal_fixture_id` for NBA and NHL —
the shared ingestion parser was never blind to them the way it was to the NFL.
Measured on production 2026-09-04:

    NBA  324 of 783 rows hold a real digit id      NHL  367 of 705
    StatPal anchors for either sport                0

So the majority state for these sports is *column set, anchor absent* — precisely
the state `anchor_channel.anchor_is_current` reads as STALE, which resolves
nothing while looking like a link. A stamper that treated a correct column as
"already linked" and moved on would leave that state forever. Hence
:data:`VERDICT_ANCHOR_ONLY`: when the column already holds exactly this contest's
id, the anchor alone is written and the pair is completed.

(The 691 already-populated rows are last season's — games from 2026-02 to 2026-06 —
and StatPal's `season-schedule` serves only 2026/2027, so no pass can verify or
anchor them. They are out of every window this task will ever see.)

FOUR THINGS ONE STATPAL CONTEST CAN BE AGAINST OUR TABLE
════════════════════════════════════════════════════════
    column is empty                    -> STAMP          write column + anchor
    column == this contest's id        -> ANCHOR_ONLY    write the anchor
    column is a digit id, but another  -> CONTRADICTION   write nothing, receipt
    column is not an id at all (#2963) -> POLLUTED_COLUMN write nothing, receipt

`CONTRADICTION` is a bucket the NFL module has no use for and this one needs: the
ingestion path picks its match by its own rule, so a disagreement between its
answer and ours is the first evidence that one of the two rules is wrong. Folding
it into "already linked" would spend that evidence.

THE SECOND ID, AND WHY IT IS LOGGED RATHER THAN ANCHORED
════════════════════════════════════════════════════════
NHL serves `stats_id` on 1404/1404 games and it is a genuinely different number
from `id` (`649052` ↔ `68933`). NBA serves the key on all 1206 games and **empty
on all 1206** — `docs/statpal-capabilities.md`'s joint "`id` + `stats_id`" credit
is wrong for NBA. Which of the two anchors a game is program step 5's question
(the MLB three-id problem), so this task anchors on `id`, carries `stats_id` into
the anchor's claim context where it is visible, and receipts the day either
league's coverage of it changes.

Related, and measured because D55 forbids guessing it: our column holds 6-digit
NBA ids on games up to 2026-04-11 and 7-digit ids from 2026-04-12 on. That is not
two namespaces — it is **one counter that crossed 1,000,000 on 2026-04-05**. The
digit count is a function of the date, which is exactly why the anchor key is
qualified by sport and never derived from the id's length.

RECEIPTS RUN IN BOTH DIRECTIONS
════════════════════════════════
A StatPal contest we hold no row for is an *ingestion gap*. One of our rows that
no contest matched is a *candidate phantom* — and for these two sports it is also
where the five midnight-placeholder NHL rows show up. Reporting only the first
direction would hide them.
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
from app.utils.authority_agreement import Side, build_agreement_row
from app.utils.nfl_team_matching import normalize_team, pair_matches
from app.utils.provider_anchor_keys import statpal_anchor_key, statpal_id_space
from app.utils.statpal_league_rosters import is_known_league_team

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LeagueSpec:
    """One league's answers to the four questions this task asks per sport.

    A dataclass rather than four parallel dicts so that adding MLB (step 5) is
    one literal with every question answered, and a half-configured sport cannot
    exist.
    """

    #: Our `sports.key`, and — because both leagues are 1:1 with StatPal's own
    #: sport name — the id space too. `statpal_id_space` is still asked rather
    #: than assumed, so the day a sport stops being 1:1 there is one place to fix.
    sport_key: str
    #: StatPal's sport token: the `{sport}` in `/v1/{sport}/season-schedule`.
    statpal_sport: str
    #: For logs and receipts.
    label: str
    #: Does this league serve `stats_id`? Measured 2026-09-04: NHL 1404/1404,
    #: NBA 0/1206. Recorded as an EXPECTATION, so the pass reports the day the
    #: answer changes instead of silently absorbing it.
    serves_stats_id: bool


NBA = LeagueSpec(
    sport_key="basketball_nba",
    statpal_sport="nba",
    label="NBA",
    serves_stats_id=False,
)
NHL = LeagueSpec(
    sport_key="icehockey_nhl",
    statpal_sport="nhl",
    label="NHL",
    serves_stats_id=True,
)

#: By our `sports.key`, which is how the beat entries and the agreement endpoint
#: name a sport.
LEAGUES: dict[str, LeagueSpec] = {NBA.sport_key: NBA, NHL.sport_key: NHL}

#: How far apart a StatPal start and ours may be and still be one game.
#:
#: **Measured, and bounded from above by the schedule itself.** Both leagues run
#: back-to-backs where the same pair meets twice in the same orientation 23 hours
#: apart, so any window over 11.5h can reach the wrong meeting. Inside that
#: bound, ±1h covers every honest disagreement observed: NBA agrees to the minute
#: on 41 of 41, NHL on 25 of 32 with two more inside the hour.
#:
#: It is NOT a knob to widen when something fails to match. The five NHL rows it
#: misses are 18.5–22h out because OUR side stamped midnight-Eastern on a start
#: nobody has set; widening past 11.5h to catch them would buy those five at the
#: price of every back-to-back in two leagues.
MATCH_WINDOW = timedelta(hours=1)

#: The largest window that is still safe against a 23h back-to-back, stated so
#: the reasoning above is a constant a test can pin rather than a paragraph.
BACK_TO_BACK_SEPARATION = timedelta(hours=23)
MAX_SAFE_WINDOW = BACK_TO_BACK_SEPARATION / 2

#: How far either side of the read fixtures the candidate query reaches.
CANDIDATE_SLACK = MATCH_WINDOW

#: Every row for the league in the window, linked or not, with its column value.
#: Deliberately NOT filtered to `statpal_fixture_id IS NULL` — that guard is what
#: makes an already-populated column invisible, and for these two sports the
#: populated column is the majority state.
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

    All-digits, which is what every measured StatPal id space is. Deliberately
    not a length check: NBA's own ids are 6 digits before 2026-04-05 and 7 after,
    because the counter crossed a million — a length rule would give a confident
    wrong answer on one side of that date.
    """
    if value is None:
        return False
    token = str(value).strip()
    return bool(token) and token.isdigit()


#: The five things one StatPal contest can be against our table. A verdict, not
#: a score.
VERDICT_STAMP = "STAMP"
VERDICT_ANCHOR_ONLY = "ANCHOR_ONLY"
VERDICT_CONTRADICTION = "CONTRADICTION"
VERDICT_POLLUTED = "POLLUTED_COLUMN"
VERDICT_AMBIGUOUS = "AMBIGUOUS"
VERDICT_UNMATCHED = "UNMATCHED"

#: `_write_link`'s own outcome for "the column was claimed between the candidate
#: query and the write". Not an anchor outcome — `anchor_channel` never returns
#: it — so it is named here rather than borrowed from there.
LOST_RACE = "LOST_RACE"

#: The ONLY two anchor outcomes that mean the anchor names this event, so the
#: only two under which a column write may be committed. A whitelist, not a
#: blacklist: a new outcome added to `anchor_channel` must be considered here
#: explicitly, and until it is, it refuses and is receipted.
COMMITTABLE_OUTCOMES = frozenset({WROTE, CONFIRMED})


@dataclass
class StampRun:
    """What one pass did, in terms a receipt can be written from.

    Every fixture read and every candidate row lands in exactly one bucket. A run
    that reports only its successes cannot tell "StatPal published nothing" from
    "we matched nothing", and those need different fixes.
    """

    sport_key: str = ""
    fixtures_read: int = 0
    rows_in_window: int = 0
    stamped: int = 0
    #: Column already held this exact contest; the missing anchor was written.
    anchored_only: int = 0
    #: Column already held this contest AND the anchor already named this event.
    already_linked: int = 0
    #: Column holds a DIFFERENT digit id from the contest that matched. The
    #: ingestion path and this task disagree; neither is overruled here.
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    #: Column holds a fabricated `statpal_live_...` value (#2963). Never written.
    polluted_column: list[dict[str, Any]] = field(default_factory=list)
    #: Two of our rows for one StatPal contest. D35: filed, not resolved.
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    #: StatPal has this contest and we hold no row for it — an ingestion gap.
    unmatched_fixtures: list[dict[str, Any]] = field(default_factory=list)
    #: We hold this row and no StatPal contest matched it — a candidate phantom,
    #: or a row whose start time nobody has set.
    unmatched_rows: list[dict[str, Any]] = field(default_factory=list)
    collisions: list[dict[str, Any]] = field(default_factory=list)
    #: Candidate found, write went through, ANCHOR write refused. Rolled back.
    write_refusals: list[dict[str, Any]] = field(default_factory=list)
    #: A team name on either side that is not one of the measured 30/32.
    #: Reporting only — the match never consults the roster.
    unknown_team_names: list[str] = field(default_factory=list)
    #: `stats_id` coverage against what this league was measured to serve. A
    #: change in either direction is a finding about the provider, not noise.
    stats_id_present: int = 0
    stats_id_absent: int = 0
    #: Set from the spec by the runner, so `summary()` can state the expectation
    #: next to the measurement instead of publishing a bare count.
    stats_id_expected: bool = False
    sources_read: list[str] = field(default_factory=list)
    read_failures: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "sport_key": self.sport_key,
            "fixtures_read": self.fixtures_read,
            "rows_in_window": self.rows_in_window,
            "stamped": self.stamped,
            "anchored_only": self.anchored_only,
            "already_linked": self.already_linked,
            "contradictions": len(self.contradictions),
            "polluted_column": len(self.polluted_column),
            "ambiguous": len(self.ambiguous),
            "unmatched_fixtures": len(self.unmatched_fixtures),
            "unmatched_rows": len(self.unmatched_rows),
            "collisions": len(self.collisions),
            "write_refusals": len(self.write_refusals),
            "unknown_team_names": sorted(set(self.unknown_team_names)),
            "stats_id": {
                "present": self.stats_id_present,
                "absent": self.stats_id_absent,
                "expected": (
                    "on every fixture" if self.stats_id_expected else "on none"
                ),
                "as_expected": self.stats_id_as_expected,
            },
            "sources_read": self.sources_read,
            "read_failures": self.read_failures,
        }

    @property
    def stats_id_as_expected(self) -> bool:
        """Did `stats_id` coverage match what this league was measured to serve?

        All-or-nothing on purpose. NHL serves it on 1404/1404 and NBA on 0/1206;
        a partial answer from either is a change worth a receipt, and a
        "mostly" threshold would be a number nobody measured.
        """
        if self.stats_id_expected:
            return self.stats_id_absent == 0
        return self.stats_id_present == 0


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
        # No start is not a wide window, it is no window. Two teams meet two to
        # four times a season; matching on names alone would pair November with
        # March.
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
        # Two of our rows for one contest is a duplicate, proven by something
        # better than a name window, and not this task's to resolve (D35, #2693).
        return VERDICT_AMBIGUOUS, matches

    row = matches[0]
    current = row.get("statpal_fixture_id")
    if current is None or not str(current).strip():
        return VERDICT_STAMP, matches
    if not is_statpal_contest_id(current):
        # #2963. The column says linked and holds a sentence. Not ours to repair.
        return VERDICT_POLLUTED, matches
    if str(current).strip() == str(fixture.fixture_id):
        # `statpal_sync` got here first and agrees with us. The column is right
        # and — measured 2026-09-04, 691 such rows and zero anchors — the anchor
        # is almost certainly missing, so this is work, not a skip.
        return VERDICT_ANCHOR_ONLY, matches
    return VERDICT_CONTRADICTION, matches


def _fixture_receipt(fixture: StatPalFixture, **extra: Any) -> dict[str, Any]:
    """One fixture-side finding, with enough in it to act on.

    "1043639 did not match" is not a receipt. The two teams and the start are
    what a person needs to decide whether the miss is our gap or StatPal's.
    """
    return {
        "statpal_id": fixture.fixture_id,
        "statpal_stats_id": fixture.stats_id,
        "teams": [fixture.away_team, fixture.home_team],
        "start": fixture.start_time.isoformat() if fixture.start_time else None,
        "status": fixture.status,
        **extra,
    }


def _row_receipt(row: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """One of our rows that no StatPal contest claimed."""
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


async def _read_fixtures(
    service, spec: LeagueSpec, run: StampRun
) -> list[StatPalFixture]:
    """Every contest StatPal will tell us about right now, deduped by id.

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
            logger.warning("StatPal %s %s unreadable: %s", spec.label, label, e)
            return
        run.sources_read.append(label)
        for f in batch:
            if not f.fixture_id or f.fixture_id in seen:
                continue
            seen.add(f.fixture_id)
            fixtures.append(f)

    await _collect(
        "season-schedule", service.get_schedule_fixtures(spec.statpal_sport)
    )
    # `livescores` is the only endpoint that knows a game while it is being
    # played, and a game that goes live unlinked is exactly the case the eventual
    # reader cares about. NBA opens 10/3 and NHL 9/19, so today it is legitimately
    # empty on both — which is a different fact from a failed read, and
    # `sources_read` is what tells them apart.
    await _collect("livescores", service.get_live_fixtures(spec.statpal_sport))

    run.fixtures_read = len(fixtures)
    for f in fixtures:
        if f.stats_id and str(f.stats_id).strip():
            run.stats_id_present += 1
        else:
            run.stats_id_absent += 1
    return fixtures


async def _candidates(
    session, spec: LeagueSpec, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(CANDIDATES),
            {
                "sport_key": spec.sport_key,
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


def _claim_context(spec: LeagueSpec, fixture: StatPalFixture) -> dict[str, Any]:
    """What the anchor records about how this claim was reached.

    `statpal_stats_id` is in here and nowhere else that matters: NHL's second id
    is real and different from the one being anchored, and which of the two
    should anchor a game is program step 5's question. Carried where it is
    visible, never substituted for the id in the key.
    """
    return {
        "written_by": "stamp_v1_statpal_fixtures",
        "league": spec.label,
        "statpal_start": (
            fixture.start_time.isoformat() if fixture.start_time else None
        ),
        "statpal_stats_id": fixture.stats_id,
    }


async def _write_link(
    session, spec: LeagueSpec, fixture: StatPalFixture, candidate: dict
) -> str:
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

    written = await record_anchor(
        session,
        event_id=candidate["id"],
        key=statpal_anchor_key(
            fixture.fixture_id, statpal_id_space(spec.sport_key)
        ),
        claim_context=_claim_context(spec, fixture),
    )
    return written.outcome


async def _write_anchor_only(
    session, spec: LeagueSpec, fixture: StatPalFixture, candidate: dict
) -> str:
    """Complete the pair for a row whose column is already correct.

    No column write, so there is nothing to roll back on a refusal and nothing
    to race for: `record_anchor` is the whole transaction. This is the path that
    exists because `statpal_sync` writes the column for these two sports and has
    never written an anchor — 691 rows, 0 anchors, measured 2026-09-04 — and a
    column with no anchor reads as STALE on every lookup.
    """
    written = await record_anchor(
        session,
        event_id=candidate["id"],
        key=statpal_anchor_key(
            fixture.fixture_id, statpal_id_space(spec.sport_key)
        ),
        claim_context=_claim_context(spec, fixture) | {"column_was_already_set": True},
    )
    return written.outcome


def _note_unknown_names(run: StampRun, spec: LeagueSpec, *names: Optional[str]) -> None:
    for name in names:
        if name and not is_known_league_team(spec.sport_key, name):
            run.unknown_team_names.append(str(name))


async def _run_stamp_v1_statpal_fixtures(
    spec: LeagueSpec, *, apply: bool = True, now: Optional[datetime] = None
) -> dict[str, Any]:
    """One pass for one league. `apply=False` plans and writes nothing."""
    from app.tasks.base import get_task_session

    now = now or datetime.now(timezone.utc)
    run = StampRun(sport_key=spec.sport_key, stats_id_expected=spec.serves_stats_id)

    service = get_statpal_service()
    try:
        fixtures = await _read_fixtures(service, spec, run)
    finally:
        await service.close()

    if not fixtures:
        # Loud, not silent. Zero fixtures with no read failure means StatPal has
        # no games for this league at all — which for a SEASON schedule would be
        # remarkable. Zero WITH failures means we could not ask, and reporting
        # those identically is gotcha #53.
        logger.warning(
            "StatPal %s stamper read 0 fixtures (sources=%s, failures=%s)",
            spec.label,
            run.sources_read,
            run.read_failures,
        )
        # Zero yield is a ROW, not a skip (spec rule 6): a day the read failed
        # pauses the seven-day count, a day StatPal genuinely served nothing does
        # not, and the bus must tell them apart without reading the logs.
        return {
            **run.summary(),
            "agreement": build_agreement_row(
                sport_key=spec.sport_key,
                fixtures=[],
                rows=[],
                normalize=normalize_team,
                read_failures=run.read_failures,
                sources_read=run.sources_read,
                is_anchor_id=is_statpal_contest_id,
            ),
        }

    starts = [f.start_time for f in fixtures if f.start_time]
    window_start = (min(starts) if starts else now) - CANDIDATE_SLACK
    window_end = (max(starts) if starts else now) + CANDIDATE_SLACK

    async with get_task_session() as session:
        pool = await _candidates(session, spec, window_start, window_end)
        run.rows_in_window = len(pool)
        #: The pool as it was read, kept because `pool` is pruned as rows are
        #: claimed. The agreement row is measured over EVERY row in the window,
        #: including the ones this pass stamped — a denominator that shrinks as
        #: the task succeeds cannot be compared to yesterday's, and the seven-day
        #: count is exactly that comparison.
        all_rows = list(pool)
        #: Which of our rows some contest claimed, so the leftovers can be
        #: reported as candidate phantoms. Claimed covers every verdict that
        #: names a row, not only the ones written: a contradicted or polluted row
        #: is accounted for, and calling it a phantom would be a second wrong
        #: answer on top of the first.
        claimed: set[int] = set()

        for fixture in fixtures:
            _note_unknown_names(run, spec, fixture.home_team, fixture.away_team)
            verdict, matches = classify_fixture(fixture, pool)

            if verdict == VERDICT_UNMATCHED:
                run.unmatched_fixtures.append(_fixture_receipt(fixture))
                continue

            for c in matches:
                claimed.add(c["id"])

            if verdict == VERDICT_AMBIGUOUS:
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

            if verdict == VERDICT_CONTRADICTION:
                # The ingestion path chose a different contest for this row. One
                # of the two rules is wrong and this task does not get to say
                # which — overwriting would destroy the evidence that they
                # disagreed at all.
                run.contradictions.append(
                    _fixture_receipt(
                        fixture,
                        event_id=candidate["id"],
                        column_holds=candidate["statpal_fixture_id"],
                    )
                )
                continue

            if not apply:
                if verdict == VERDICT_ANCHOR_ONLY:
                    run.anchored_only += 1
                else:
                    run.stamped += 1
                continue

            try:
                if verdict == VERDICT_ANCHOR_ONLY:
                    outcome = await _write_anchor_only(
                        session, spec, fixture, candidate
                    )
                else:
                    outcome = await _write_link(session, spec, fixture, candidate)
            except Exception as e:  # one bad row never wipes the pass (#42)
                await session.rollback()
                logger.exception(
                    "StatPal %s stamp failed for contest %s -> event %s: %s",
                    spec.label, fixture.fixture_id, candidate["id"], e,
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
            if verdict == VERDICT_ANCHOR_ONLY:
                # CONFIRMED here means the anchor already named this event, so
                # nothing was missing and nothing was written; WROTE means the
                # pair is complete for the first time. Counting them apart is
                # what makes "the backfill is done" a readable state.
                if outcome == WROTE:
                    run.anchored_only += 1
                else:
                    run.already_linked += 1
            else:
                run.stamped += 1
            # The agreement row is built after this loop and asks each row what
            # its column holds. A row this pass just stamped holds the id now,
            # and reading the pre-pass value would report the task's own success
            # as an unanchored game.
            candidate["statpal_fixture_id"] = fixture.fixture_id
            # The pool is per-pass, so a row claimed by this pass must not be
            # offered to the next contest — otherwise two contests can both
            # "match" it and the second silently loses the race instead of being
            # reported as the ambiguity it is.
            pool = [c for c in pool if c["id"] != candidate["id"]]
            if outcome != WROTE:
                logger.info(
                    "StatPal %s anchor for contest %s on event %s: %s",
                    spec.label, fixture.fixture_id, candidate["id"], outcome,
                )

        # The other direction. A row inside the window that no contest claimed is
        # a candidate phantom — or, for NHL today, one of the five rows whose
        # start time is our midnight-Eastern placeholder.
        for row in pool:
            if row["id"] in claimed:
                continue
            _note_unknown_names(run, spec, row.get("home"), row.get("away"))
            run.unmatched_rows.append(_row_receipt(row))

    agreement = build_agreement_row(
        sport_key=spec.sport_key,
        fixtures=[
            Side(
                ref=f.fixture_id,
                home=f.home_team,
                away=f.away_team,
                start=f.start_time,
                label=f.status,
            )
            for f in fixtures
        ],
        rows=[
            Side(
                ref=str(r["id"]),
                home=r["home"],
                away=r["away"],
                start=r["commence_time"],
                label=r.get("status"),
                held_id=r.get("statpal_fixture_id"),
            )
            for r in all_rows
        ],
        normalize=normalize_team,
        read_failures=run.read_failures,
        sources_read=run.sources_read,
        window=(window_start, window_end),
        is_anchor_id=is_statpal_contest_id,
    )

    summary = run.summary()
    logger.info("StatPal %s stamper: %s", spec.label, summary)
    return {
        **summary,
        # The ledger row bus bucket M-R-AUTHORITY reads (D50's flip gate). Built
        # here rather than by a script because this pass already holds both sides
        # of the comparison at the same moment, and a script asking again an hour
        # later is comparing two different afternoons (precedent D46).
        "agreement": agreement,
        "contradiction_receipts": run.contradictions,
        "polluted_column_receipts": run.polluted_column,
        "ambiguous_receipts": run.ambiguous,
        "unmatched_fixture_receipts": run.unmatched_fixtures,
        "unmatched_row_receipts": run.unmatched_rows,
        "collision_receipts": run.collisions,
        "write_refusal_receipts": run.write_refusals,
    }


async def _run_stamp_nba_statpal_fixtures(
    *, apply: bool = True, now: Optional[datetime] = None
) -> dict[str, Any]:
    return await _run_stamp_v1_statpal_fixtures(NBA, apply=apply, now=now)


async def _run_stamp_nhl_statpal_fixtures(
    *, apply: bool = True, now: Optional[datetime] = None
) -> dict[str, Any]:
    return await _run_stamp_v1_statpal_fixtures(NHL, apply=apply, now=now)
