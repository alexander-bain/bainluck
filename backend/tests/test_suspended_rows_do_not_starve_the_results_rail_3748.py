"""RECENT RESULTS STOPS BEING MADE ENTIRELY OF ROWS THAT REPORT NO RESULT — #3748.

═══ WHAT A READER SAW ═══

`/sport/tennis/atp`, section headed "Recent Results", opened with three cards
reading "No result reported". That is the filed symptom and it is the small
half. Simulating the real rail against production on 2026-09-06 — the same
`ORDER BY commence_time DESC LIMIT 8` over the same 14-day window, with the
duplicate-tag filter included — across all 29 leagues:

    28 leagues had at least one scoreless `suspended` row in their 8 slots
    13 of them had ALL EIGHT

KBO, NPB, MiLB, AFLW, boxing, MMA, Liiga, esports and five more rendered a
"Recent Results" section containing not one result. Confirmed against the
SERVING ENDPOINT rather than the query alone: `/api/leagues/baseball_kbo` and
`/api/leagues/baseball_npb` each returned 8/8 scoreless `suspended` rows **while
their own `unreported_games` rail came back EMPTY**. The rail that exists to
hold result-less rows was empty; the rail headed "Recent Results" held nothing
else. In the window: 1,618 scoreless suspended rows against 54 with a score.

═══ THE MECHANISM — #3211's STARVATION, THE THIRD STATUS THROUGH IT ═══

`event_rails.unreported_rail_condition` already said, in as many words, that a
result-less `scheduled` row "has the same standing as a `suspended` one — its
clock ran out and nothing reported an ending". #3211 acted on that for
`scheduled` and gave it a rail with a cap of its own. `suspended` was left on
the settled rail, where it shares the property that caused the starvation: it is
stamped midnight UTC of the current day (gotcha #14), so under
`commence_time DESC` it sorts above every real Final.

🔴 AND THE FIX IS NOT A REORDER OR A BIGGER CAP. That is the shared-cap trap the
sibling docstring already rules out by name: one cap over two populations of
very different size starves the smaller one whichever way it is sorted. Sorting
settled-first would have hidden all 1,618 behind eight slots of Finals, which is
#3211 inverted. The bound is split instead.

═══ EVERY SUSPENDED ROW, NOT ONLY THE SCORELESS ONES — CERT-2167 ═══

This suite first shipped guarding a SCORE SPLIT: scoreless suspended rows to the
unreported rail, the 54 scored ones left under "Recent Results" on the reasoning
that they have something to show. CERT-2167 blocked it, and the argument is the
one that decides this file's shape:

    the rail a row sits on has to agree with the words its own card prints

`eventState.hasNoReportedResult` is true for EVERY suspended row, so all 54
scored ones rendered "No result reported · last score 1-2" under a heading
saying "Recent Results" — the same contradiction the issue was filed about, at
54 rows instead of 1,618. And a score does not stop a row being stamped midnight
UTC, so those 54 can still CONSUME THE CAPPED SLOTS.
`TestEightNewerScoredSuspendedRowsCannotTakeTheSlots` is that case, and the
version of this file that shipped first could not have passed it.

Nothing is lost by moving them: both rails render the same shared card via
`LeagueGameRail`, so a scored row keeps its `· last score` label verbatim.

═══ RED-FIRST ═══

`TestTheDefectReproduces` rebuilds the PRE-FIX settled condition over the same
corpus and shows the Finals pushed off the page by it. The scored-flood class
carries its own red-first for the same reason, over its own corpus. Without
them, every assertion below could be passing over a slate that never starved.

═══ BOTH DIRECTIONS (gotcha #43) ═══

The flood being capped and the adjacent surface being populated are two claims
and this file asserts both: the Finals come back on `recent_results`, AND the
suspended rows are on `unreported_games`. A test that only checked the first
would be satisfied by the rows being deleted, which is the #3211 disappearance
wearing the repair's clothes.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

# SQLite cannot render Postgres-native column types. DDL shims for the sqlite
# dialect ONLY — production is Postgres and never reaches them.


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.routes.league_futures import (  # noqa: E402
    RESULTS_LIMIT,
    RESULTS_LOOKBACK_DAYS,
    recent_results_query,
    unreported_games_query,
)
from app.utils.event_completion import EVENT_SUSPENDED  # noqa: E402
from app.utils.event_rails import unreported_rail_condition  # noqa: E402

#: A fixed anchor. Offsets from it, never a branch on the clock (gotcha #44).
NOW = datetime(2026, 9, 6, 18, 0, 0, tzinfo=timezone.utc)

S_KBO = 1
LEAGUE = "baseball_kbo"

#: The starving population, drawn to production's shape: scoreless `suspended`
#: rows stamped at MIDNIGHT UTC of a recent day (gotcha #14 — a Kalshi ticker
#: date, not a real start time). Midnight of a later day beats any real Final
#: of an earlier one under `commence_time DESC`, which is the whole mechanism.
SCORELESS_SUSPENDED = [
    (101, datetime(2026, 9, 6, 8, 1, tzinfo=timezone.utc)),
    (102, datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)),
    (103, datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)),
    (104, datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)),
    (105, datetime(2026, 9, 6, 5, 1, tzinfo=timezone.utc)),
    (106, datetime(2026, 9, 5, 8, 1, tzinfo=timezone.utc)),
    (107, datetime(2026, 9, 5, 8, 0, tzinfo=timezone.utc)),
    (108, datetime(2026, 9, 5, 8, 0, tzinfo=timezone.utc)),
]

#: The results that were pushed off the page. Older, and every one of them
#: carries a scoreline — these are real Finals.
FINALS = [
    (201, datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc), "completed", (5, 3)),
    (202, datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc), "completed", (1, 2)),
    (203, datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc), "closed", (7, 7)),
    (204, datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc), "completed", (0, 4)),
    (205, datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc), "completed", (2, 1)),
]

#: live/056's population, kept where live/056 put it: `suspended` WITH a score.
#: It is the control that fails if the repair is written one arm too wide.
SCORED_SUSPENDED_ID = 301
SCORED_SUSPENDED_TIME = datetime(2026, 9, 6, 7, 0, tzinfo=timezone.utc)


def _row(eid, commence_time, status, score=(None, None)):
    home_score, away_score = score
    return Event(
        id=eid,
        sport_id=S_KBO,
        external_id=f"ext-{eid}",
        home_team_name="Doosan Bears",
        away_team_name="LG Twins",
        commence_time=commence_time,
        status=status,
        home_score=home_score,
        away_score=away_score,
    )


@pytest.fixture
def session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_KBO, key=LEAGUE, name="KBO"))
        for eid, commence in SCORELESS_SUSPENDED:
            s.add(_row(eid, commence, EVENT_SUSPENDED))
        for eid, commence, status, score in FINALS:
            s.add(_row(eid, commence, status, score))
        s.add(_row(SCORED_SUSPENDED_ID, SCORED_SUSPENDED_TIME, EVENT_SUSPENDED, (1, 2)))
        s.commit()
        yield s


def _ids(session, query):
    return [e.id for e in session.execute(query).scalars().all()]


def _results(session):
    return _ids(session, recent_results_query(LEAGUE, NOW))


def _unreported(session):
    return _ids(session, unreported_games_query(LEAGUE, NOW))


class TestTheDefectReproduces:
    """🔴 RED-FIRST. The pre-#3748 settled condition, over this same corpus."""

    def test_the_old_rail_showed_eight_rows_and_not_one_result(self, session):
        from sqlalchemy import and_

        pre_fix = and_(
            Event.commence_time >= NOW - timedelta(days=14),
            Event.status.in_(["completed", "closed", EVENT_SUSPENDED]),
        )
        shown = (
            session.execute(
                select(Event.id)
                .where(Event.sport_id == S_KBO, pre_fix)
                .order_by(Event.commence_time.desc())
                .limit(RESULTS_LIMIT)
            )
            .scalars()
            .all()
        )

        scoreless = {eid for eid, _ in SCORELESS_SUSPENDED}
        assert set(shown) <= scoreless | {SCORED_SUSPENDED_ID}, (
            "the corpus does not reproduce the starvation, so every green "
            f"below is free: {shown}"
        )
        assert not (set(shown) & {eid for eid, _, _, _ in FINALS}), (
            "a Final was visible before the fix — wrong corpus, and this suite "
            "would be certifying nothing"
        )


class TestTheShip:
    """Both directions, per gotcha #43."""

    def test_the_finals_are_back_on_recent_results(self, session):
        results = _results(session)
        for eid, _, _, _ in FINALS:
            assert (
                eid in results
            ), f"Final {eid} is still off the Recent Results rail: {results}"

    def test_NO_suspended_row_is_on_recent_results(self, session):
        """Scored or scoreless — CERT-2167's correction. The card calls every
        suspended row result-less, so none of them belongs under a heading that
        promises results."""
        results = set(_results(session))
        intruders = sorted(
            results & ({eid for eid, _ in SCORELESS_SUSPENDED} | {SCORED_SUSPENDED_ID})
        )
        assert intruders == [], (
            "these rows report no result and are on the rail headed "
            f"'Recent Results': {intruders}"
        )

    def test_every_scoreless_row_is_ADMITTED_by_the_unreported_rail(self, session):
        """The direction a deletion would also satisfy, which is why it is
        asserted separately and by name.

        Against the rail's CONDITION, not its capped query, and the distinction
        is load-bearing rather than pedantic: `unreported_games_query` stops at
        `UNREPORTED_LIMIT + 1`, so a row can be absent from its result while
        being perfectly well routed — it is simply on page two. Asserting
        routing against the capped query would make this test fail the moment
        the population exceeds the cap, i.e. exactly when the rail matters
        most, and the "fix" would be to raise the cap. That is the trap the
        sibling docstring rules out by name.
        """
        admitted = set(
            session.execute(
                select(Event.id).where(
                    Event.sport_id == S_KBO,
                    unreported_rail_condition(
                        NOW, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)
                    ),
                )
            )
            .scalars()
            .all()
        )
        missing = sorted({eid for eid, _ in SCORELESS_SUSPENDED} - admitted)
        assert missing == [], (
            "these rows left the results rail and are admitted by NO rail — "
            f"that is the #3211 disappearance, not a repair: {missing}"
        )

    def test_the_unreported_rail_actually_renders_them(self, session):
        """And the capped query is not empty, which is the half the reader
        sees. Every row it returns is one of the suspended population."""
        unreported = _unreported(session)
        assert unreported, "the unreported rail came back empty"
        assert set(unreported) <= (
            {eid for eid, _ in SCORELESS_SUSPENDED} | {SCORED_SUSPENDED_ID}
        ), f"the unreported rail is holding something else: {unreported}"

    def test_a_scored_suspended_row_moves_too_and_keeps_its_score(self, session):
        """CERT-2167's correction, and the row that first attempt left behind.

        It renders "No result reported · last score 1-2" — the words are the
        frontend's and are true of it — so a rail headed "Recent Results" is the
        wrong place for it however much of a scoreline it carries.

        Nothing is lost by the move: both rails render the same shared card via
        `LeagueGameRail`, so the `· last score` label survives verbatim. Asserted
        here by checking the scoreline is still ON the row, since this suite
        cannot see a React tree.
        """
        assert SCORED_SUSPENDED_ID not in _results(session)
        assert SCORED_SUSPENDED_ID in _unreported(session)

        row = session.get(Event, SCORED_SUSPENDED_ID)
        assert (row.home_score, row.away_score) == (1, 2), (
            "the move must not cost the row its last score — that is what the "
            "card prints beside 'No result reported'"
        )


class TestTheCapIsSplitRatherThanShared:
    """The half the sibling docstring says a reorder cannot buy."""

    def test_every_visible_results_slot_now_carries_a_scoreline(self, session):
        """The user-visible claim, stated as the reader would: the section
        headed 'Recent Results' contains results."""
        rows = (
            session.execute(select(Event).where(Event.id.in_(_results(session))))
            .scalars()
            .all()
        )
        unscored = sorted(
            e.id for e in rows if e.home_score is None or e.away_score is None
        )
        assert (
            unscored == []
        ), f"these Recent Results rows have no scoreline to show: {unscored}"

    def test_the_two_rails_do_not_share_a_row(self, session):
        overlap = sorted(set(_results(session)) & set(_unreported(session)))
        assert overlap == [], f"these rows are on both rails at once: {overlap}"


class TestEightNewerScoredSuspendedRowsCannotTakeTheSlots:
    """🔴 CERT-2167's named regression, and the one the first attempt could not
    have passed.

    The BLOCK's argument was not that scored suspended rows look wrong — it was
    that they can still CONSUME THE CAPPED RESULT SLOTS. A score does not stop a
    row being stamped midnight UTC (gotcha #14), so a league with eight scored
    suspended rows newer than its Finals starves exactly as hard as one with
    eight scoreless ones, and every one of those eight prints "No result
    reported".

    So this is the same starvation with the score column filled in. Its own
    corpus rather than the shared fixture, because the shared one has a single
    scored row and this needs a full cap's worth to prove the cap.
    """

    #: Eight scored `suspended` rows, all NEWER than every Final in `FINALS`,
    #: so under `commence_time DESC LIMIT 8` they would take all eight slots.
    SCORED_FLOOD = [
        (401 + i, datetime(2026, 9, 6, 12 - i, 0, tzinfo=timezone.utc))
        for i in range(8)
    ]

    @pytest.fixture
    def flooded(self):
        eng = create_engine("sqlite://")
        Base.metadata.create_all(eng)
        with Session(eng) as s:
            s.add(Sport(id=S_KBO, key=LEAGUE, name="KBO"))
            for eid, commence in self.SCORED_FLOOD:
                s.add(_row(eid, commence, EVENT_SUSPENDED, (4, 2)))
            for eid, commence, status, score in FINALS:
                s.add(_row(eid, commence, status, score))
            s.commit()
            yield s

    def test_the_flood_would_have_taken_every_slot(self, flooded):
        """🔴 RED-FIRST for this corpus specifically. Without it the three
        assertions below could be passing over a slate that never starved."""
        from sqlalchemy import and_

        pre_fix = and_(
            Event.commence_time >= NOW - timedelta(days=14),
            Event.status.in_(["completed", "closed", EVENT_SUSPENDED]),
        )
        shown = (
            flooded.execute(
                select(Event.id)
                .where(Event.sport_id == S_KBO, pre_fix)
                .order_by(Event.commence_time.desc())
                .limit(RESULTS_LIMIT)
            )
            .scalars()
            .all()
        )
        assert set(shown) == {eid for eid, _ in self.SCORED_FLOOD}, (
            "the scored flood does not fill all eight slots under the pre-fix "
            f"rail, so this corpus proves nothing: {shown}"
        )

    def test_no_suspended_row_is_admitted_to_the_results_card_rail(self, flooded):
        results = set(_results(flooded))
        intruders = sorted(results & {eid for eid, _ in self.SCORED_FLOOD})
        assert intruders == [], (
            "scored suspended rows are consuming Recent Results slots while "
            f"their own cards say 'No result reported': {intruders}"
        )

    def test_the_finals_are_visible(self, flooded):
        results = _results(flooded)
        for eid, _, _, _ in FINALS:
            assert eid in results, f"Final {eid} is off the rail: {results}"

    def test_the_flood_is_reachable_on_the_unreported_rail(self, flooded):
        """Not deleted — the direction that separates a repair from #3211."""
        admitted = set(
            flooded.execute(
                select(Event.id).where(
                    Event.sport_id == S_KBO,
                    unreported_rail_condition(
                        NOW, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)
                    ),
                )
            )
            .scalars()
            .all()
        )
        missing = sorted({eid for eid, _ in self.SCORED_FLOOD} - admitted)
        assert missing == [], f"these rows are admitted by NO rail: {missing}"
