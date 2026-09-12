"""#5077 — a page stops promising liveness it cannot back.

The defect: an event reads ``live`` with a 20s refresh ticker, no score at all,
a hero at 99% and a dead-straight chart, hours after the venue settled every
market on the match.

Two halves are guarded here and they fail differently, so they are tested apart:

* the FLOORS (``probability_series_is_pinned``) — the thing a careless tune
  breaks. The rejected alternative floor is in the table below on purpose.
* the SCOPE (``league_may_be_judged_by_flatness``) — the thing a careless
  widening breaks, and the more dangerous of the two: fired at MLB this rule
  would "resolve" the ghost half of a twin whose anchored copy is already right.

Then the serving helper, which is where the two meet and where the ordering
claim (coverage is consulted only for rows that already passed flatness) is
either true or is a latency regression on every live page.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.pinned_live_probability import (
    a_score_is_evidence_of_play,
    MIN_OBSERVATIONS,
    MIN_SPAN_SECONDS,
    SLOWEST_MEASURED_CADENCE_SECONDS,
    league_may_be_judged_by_flatness,
    probability_series_is_pinned,
)

# ── The measured cohorts, production 2026-09-11 ─────────────────────────────
# Cohort A is reported as BOUNDS in the measurement (13 events; rows 6-20,
# SUM(reading_count) 13-27, span 66.3-118.7 min), not per-event, so the corners
# of that box are what is asserted rather than thirteen invented rows.
_COHORT_A_THINNEST = {"observations": 13, "span_seconds": 66.3 * 60, "rows": 6}
_COHORT_A_THICKEST = {"observations": 27, "span_seconds": 118.7 * 60, "rows": 20}

#: Distinct-value counts measured on cohort B, the events genuinely being played.
_COHORT_B_DISTINCT = (2, 5, 35)

#: The floor that was honestly measured, shipped nowhere, and would have caught
#: nothing: ``>= 25 rows``. See `test_the_rejected_row_floor_is_not_what_ships`.
_REJECTED_ROW_FLOOR = 25


class TestTheFloors:
    """`probability_series_is_pinned` — both sides of every constant."""

    @pytest.mark.parametrize(
        "member", [_COHORT_A_THINNEST, _COHORT_A_THICKEST], ids=["thinnest", "thickest"]
    )
    def test_the_measured_flat_cohort_passes(self, member):
        assert probability_series_is_pinned(
            distinct_values=1,
            total_observations=member["observations"],
            span_seconds=member["span_seconds"],
        )

    @pytest.mark.parametrize("distinct", _COHORT_B_DISTINCT)
    def test_a_moving_series_is_never_pinned(self, distinct):
        """Cohort B — generously over both floors, and still refused."""
        assert not probability_series_is_pinned(
            distinct_values=distinct,
            total_observations=200,
            span_seconds=2 * 60 * 60,
        )

    def test_an_absent_series_is_not_a_pinned_one(self):
        """Cohort C (no series at all) is a different defect (#5158).

        Silence is not evidence the game is over, and a rule written as
        ``distinct > 1`` would quietly claim it is — on 10 of 22 events in the
        measurement that first found this cohort.

        OBSERVATIONS ARE OVER THE FLOOR ON PURPOSE. Written the natural way —
        cohort C's real shape, ``distinct=0`` with ``observations=0`` — this test
        passes against a `distinct > 1` mutant, because the observations floor
        refuses it first and the distinct arm is never reached. It looked like a
        guard on the distinct check and was a second guard on the floor. Holding
        the other two inputs valid is what makes it test its own subject.
        """
        assert not probability_series_is_pinned(
            distinct_values=0,
            total_observations=MIN_OBSERVATIONS + 17,
            span_seconds=2 * 60 * 60,
        )

    def test_observations_floor_refuses_one_below_and_admits_the_floor(self):
        below = probability_series_is_pinned(
            distinct_values=1,
            total_observations=MIN_OBSERVATIONS - 1,
            span_seconds=MIN_SPAN_SECONDS,
        )
        at = probability_series_is_pinned(
            distinct_values=1,
            total_observations=MIN_OBSERVATIONS,
            span_seconds=MIN_SPAN_SECONDS,
        )
        assert (below, at) == (False, True)

    def test_span_floor_refuses_one_second_below_and_admits_the_floor(self):
        below = probability_series_is_pinned(
            distinct_values=1,
            total_observations=MIN_OBSERVATIONS,
            span_seconds=MIN_SPAN_SECONDS - 1,
        )
        at = probability_series_is_pinned(
            distinct_values=1,
            total_observations=MIN_OBSERVATIONS,
            span_seconds=MIN_SPAN_SECONDS,
        )
        assert (below, at) == (False, True)

    def test_the_rejected_row_floor_is_not_what_ships(self):
        """The floor is in OBSERVATIONS. A row floor is anti-correlated with the
        target population and passes none of it.

        ``snapshots.py`` writes no row when the value is unchanged — it bumps
        ``reading_count`` — so a flat series' row count measures how often the
        poll REACHED the event, not how flat it is. And the flat cohort is
        reached less (zero open markets to price): 10.8 rows/2h against cohort
        B's 73.3. Every member of cohort A is under 25 rows while every member
        clears 10 observations, so the two rules do not merely differ, they
        invert.

        This is the guard for the mutation "state the floor in rows" — the one
        shape of this fix that measures clean and ships inert.
        """
        for member in (_COHORT_A_THINNEST, _COHORT_A_THICKEST):
            assert member["rows"] < _REJECTED_ROW_FLOOR
            assert probability_series_is_pinned(
                distinct_values=1,
                total_observations=member["observations"],
                span_seconds=member["span_seconds"],
            )
        assert MIN_OBSERVATIONS != _REJECTED_ROW_FLOOR

    def test_the_two_floors_are_mutually_satisfiable(self):
        """The observation floor must be REACHABLE inside the span floor.

        This is the guard for the subtler version of the row-count defect, and
        the reason `MIN_OBSERVATIONS` is 5 rather than the 10 the issue's own
        derivation arrived at.

        If a series flat for exactly `MIN_SPAN_SECONDS` cannot accumulate
        `MIN_OBSERVATIONS` at the slowest cadence the poll has been measured at,
        then the span floor is decorative and the observation floor is silently
        acting as a cadence proxy — which is precisely what disqualified the row
        floor. Worse, it is one slow pass from inert: at the 2-hour window
        ceiling, a cadence of 13 min/observation caps the count at 9, and a rule
        needing 10 stops firing on everything with nothing to show for it.

        Measured 2026-09-12 00:40Z the cadence was 11.9 min/observation, so 60
        minutes of flatness delivers ~5 observations and no more.
        """
        reachable_within_the_span_floor = (
            MIN_SPAN_SECONDS / SLOWEST_MEASURED_CADENCE_SECONDS
        )
        assert MIN_OBSERVATIONS <= reachable_within_the_span_floor


class TestAScoreIsEvidenceOfPlay:
    """CERT-2669's BLOCK. #5077 is "live, with NO SCORE, and the number has not
    moved" — the predicate shipped without the second half of its own subject."""

    def test_no_score_at_all_leaves_the_rule_free_to_speak(self):
        assert not a_score_is_evidence_of_play(None, None)

    @pytest.mark.parametrize(
        "home,away",
        [(1, 0), (0, 1), (0, 0), (3, 2), (1, None), (None, 1)],
        ids=["1-0", "0-1", "0-0", "3-2", "home-only", "away-only"],
    )
    def test_any_reported_score_is_evidence_of_play(self, home, away):
        """EITHER side is enough, and 0-0 counts.

        `0` is a score and `None` is the absence of one — a rule written with
        truthiness (`if home_score or away_score`) reads 0-0 as no score, which
        is the one scoreline a real game spends its first minutes at.

        A half-populated score is still a report of play, so requiring both sides
        would admit a `1-None` row on exactly the reasoning this refuses.
        """
        assert a_score_is_evidence_of_play(home, away)


class TestTheScope:
    """`league_may_be_judged_by_flatness` — the ruling's load-bearing half."""

    def test_an_anchorless_row_in_an_unanchored_league_may_be_judged(self):
        assert league_may_be_judged_by_flatness(
            league_has_espn_anchors=False, event_has_espn_anchor=False
        )

    def test_a_row_with_its_own_anchor_is_never_judged_by_flatness(self):
        """An authority can speak for this row, so a heuristic does not get to."""
        assert not league_may_be_judged_by_flatness(
            league_has_espn_anchors=False, event_has_espn_anchor=True
        )

    def test_an_anchorless_row_in_an_ANCHORED_league_is_refused(self):
        """The MLB case, and the reason the scope exists at all.

        MLB is 66% ESPN-anchored, so an anchorless live MLB row is usually the
        ghost half of a twin (#2057 / #3622 / #5277) whose anchored copy already
        carries the right state. Judging it by flatness would put an unbacked
        claim on the wrong row of a pair. MLB is out of scope by this test, not
        by name — nothing here enumerates a league.
        """
        assert not league_may_be_judged_by_flatness(
            league_has_espn_anchors=True, event_has_espn_anchor=False
        )

    def test_unknown_coverage_refuses_rather_than_defaulting(self):
        """`None` is "we could not tell", and it must not read as "no coverage".

        An unbacked live claim is a smaller defect than a wrong one, so the
        unknown case fails closed.
        """
        assert not league_may_be_judged_by_flatness(
            league_has_espn_anchors=None, event_has_espn_anchor=False
        )


# ── The serving helper ──────────────────────────────────────────────────────


def _now():
    return datetime.now(timezone.utc)


def _event(
    *,
    status="live",
    completed_at=None,
    espn_id=None,
    sport_key="tennis_atp",
    event_id=15309549,
    hours_past_kickoff=3.0,
    home_score=None,
    away_score=None,
):
    ev = MagicMock()
    ev.id = event_id
    ev.status = status
    ev.completed_at = completed_at
    ev.espn_id = espn_id
    ev.commence_time = _now() - timedelta(hours=hours_past_kickoff)
    ev.home_score = home_score
    ev.away_score = away_score
    ev.sport = MagicMock()
    ev.sport.key = sport_key
    return ev


def _session(*, agg, league_anchored=False, coverage_raises=False):
    """A session that answers the two queries the helper makes, and counts them.

    `agg` is the tuple the win-prob aggregate returns, or an exception to raise.
    """
    session = AsyncMock()
    session.coverage_calls = 0
    session.flatness_sql = None

    async def execute(stmt, *args, **kwargs):
        sql = str(stmt).lower()
        if "win_prob_snapshots" in sql:
            session.flatness_sql = sql
            if isinstance(agg, Exception):
                raise agg
            result = MagicMock()
            result.one.return_value = agg
            return result
        if "espn_id is not null" in sql:
            session.coverage_calls += 1
            if coverage_raises:
                raise RuntimeError("coverage query failed")
            result = MagicMock()
            result.scalar.return_value = league_anchored
            return result
        raise AssertionError(f"unexpected query: {sql[:120]}")

    session.execute = AsyncMock(side_effect=execute)
    return session


#: Kept clear of the 2-hour window edge so a test asserting a span is asserting
#: the helper's arithmetic and not its clipping.
_FLAT_SPAN_MINUTES = 110


def _flat_agg(*, distinct=1, observations=10, span_minutes=_FLAT_SPAN_MINUTES, value=0.99):
    """The aggregate a genuinely pinned in-play series produces.

    Anchored on the wall clock because the helper's window is: ten observations
    over 110 minutes ending a minute ago is the measured shape of the firing
    population (2026-09-12 00:40Z — 10 events, 118 min, newest 1-2 min old).
    """
    last = _now() - timedelta(minutes=1)
    return (
        distinct,
        observations,
        last - timedelta(minutes=span_minutes),
        last,
        value,
    )


@pytest.fixture(autouse=True)
def _clear_coverage_cache():
    from app.routes.events import _league_anchor_coverage_cache

    _league_anchor_coverage_cache.clear()
    yield
    _league_anchor_coverage_cache.clear()


class TestTheServedSignal:
    @pytest.mark.asyncio
    async def test_a_pinned_live_event_gets_the_signal(self):
        from app.routes.events import _pinned_live_probability

        session = _session(agg=_flat_agg())
        signal = await _pinned_live_probability(session, _event())

        assert signal is not None
        assert signal["pinned"] is True
        assert signal["probability"] == pytest.approx(0.99)
        assert signal["observations"] == 10
        assert signal["span_seconds"] == pytest.approx(_FLAT_SPAN_MINUTES * 60, abs=2)

    @pytest.mark.asyncio
    async def test_a_moving_series_gets_nothing(self):
        from app.routes.events import _pinned_live_probability

        session = _session(agg=_flat_agg(distinct=35))
        assert await _pinned_live_probability(session, _event()) is None

    @pytest.mark.asyncio
    async def test_the_coverage_query_is_not_run_for_a_moving_series(self):
        """The ordering claim, asserted rather than described.

        Coverage is 60-150ms. If it ran before flatness it would run on every
        live event page instead of on the handful that are already candidates,
        which is a latency regression wearing a correctness fix.
        """
        from app.routes.events import _pinned_live_probability

        session = _session(agg=_flat_agg(distinct=35))
        await _pinned_live_probability(session, _event())
        assert session.coverage_calls == 0

    @pytest.mark.asyncio
    async def test_an_anchored_league_gets_nothing_even_when_flat(self):
        """A flat anchorless row in MLB — the ghost-twin case, end to end."""
        from app.routes.events import _pinned_live_probability

        session = _session(agg=_flat_agg(), league_anchored=True)
        event = _event(sport_key="baseball_mlb")
        assert await _pinned_live_probability(session, event) is None
        assert session.coverage_calls == 1

    @pytest.mark.asyncio
    async def test_a_failed_coverage_query_refuses_the_signal(self):
        from app.routes.events import _pinned_live_probability

        session = _session(agg=_flat_agg(), coverage_raises=True)
        assert await _pinned_live_probability(session, _event()) is None

    @pytest.mark.asyncio
    async def test_a_failed_flatness_query_refuses_the_signal(self):
        from app.routes.events import _pinned_live_probability

        session = _session(agg=RuntimeError("boom"))
        assert await _pinned_live_probability(session, _event()) is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "event_kwargs",
        [
            {"status": "scheduled"},
            {"status": "completed"},
            {"status": "suspended"},
            {"completed_at": datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc)},
            {"espn_id": "401584923"},
        ],
        ids=["scheduled", "completed", "suspended", "has-completed-at", "has-anchor"],
    )
    async def test_out_of_scope_rows_are_never_signalled(self, event_kwargs):
        from app.routes.events import _pinned_live_probability

        session = _session(agg=_flat_agg())
        assert await _pinned_live_probability(session, _event(**event_kwargs)) is None

    @pytest.mark.asyncio
    async def test_an_anchored_row_costs_no_queries_at_all(self):
        from app.routes.events import _pinned_live_probability

        session = _session(agg=_flat_agg())
        await _pinned_live_probability(session, _event(espn_id="401584923"))
        assert session.execute.await_count == 0

    @pytest.mark.asyncio
    async def test_span_comes_from_valid_until_not_from_captured_at(self):
        """A series held in ONE deduped row still has a span.

        `valid_until` is set to `now` on every dedup bump, so it is the last time
        we looked and the value was still this one. Reading the span off
        `max(captured_at)` instead would give zero on exactly the flattest rows —
        the ones that never moved enough to create a second row — and the rule
        would refuse its own cleanest specimens.
        """
        from app.routes.events import _pinned_live_probability

        last = _now() - timedelta(minutes=1)
        one_row_series = (1, 10, last - timedelta(minutes=90), last, 0.99)
        session = _session(agg=one_row_series)

        signal = await _pinned_live_probability(session, _event())
        assert signal is not None
        assert signal["span_seconds"] == pytest.approx(90 * 60, abs=2)

        # The assertion above rides on an aggregate this test supplies, so on its
        # own it cannot tell a `coalesce(valid_until, captured_at)` end-bound from
        # a `max(captured_at)` one. This reads the statement the helper actually
        # built and handed to the session — not the source text, the compiled
        # query — so the two are distinguishable.
        assert "coalesce" in session.flatness_sql
        assert "valid_until" in session.flatness_sql

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "home,away",
        [(1, 0), (0, 0), (2, None)],
        ids=["1-0", "0-0", "home-only"],
    )
    async def test_a_scored_live_event_is_never_signalled_as_unbacked_5077(
        self, home, away
    ):
        """The repair CERT-2669 named, end to end through the helper.

        A live event with a score is visibly being played and reported, whatever
        its price is doing — a 1-0 grind over a market that has stopped moving is
        a quiet market, not an unbacked live claim. Measured 2026-09-12 01:40Z, 4
        of 40 live anchorless rows carry a score, so this arm has a population.

        Series held at the fully qualifying shape so the refusal can only be
        coming from the score.
        """
        from app.routes.events import _pinned_live_probability

        session = _session(agg=_flat_agg())
        event = _event(home_score=home, away_score=away)

        assert await _pinned_live_probability(session, event) is None
        assert session.execute.await_count == 0

    @pytest.mark.asyncio
    async def test_a_pregame_flat_stretch_does_not_make_a_match_look_finished(self):
        """The window is floored at kickoff. Measured specimen, 2026-09-12 00:40Z.

        Event 15310172 (WTA) was 48 minutes past its own commence time and
        carried 110 minutes of unbroken flatness at 0.0100 — 62 of which were
        before the match started. Without the floor it is the single row the
        rule fires on all night, and what it would be reporting is a quiet
        pre-game market, not a finished game. #1999 is the standing lesson that
        pre-game and in-play series are different populations.
        """
        from app.routes.events import _pinned_live_probability

        session = _session(agg=_flat_agg(span_minutes=110, value=0.01))
        event = _event(sport_key="tennis_wta", hours_past_kickoff=0.8)

        assert await _pinned_live_probability(session, event) is None

    @pytest.mark.asyncio
    async def test_the_window_filter_is_interval_overlap_not_captured_at(self):
        """A pinned series lives in ONE row created BEFORE the window.

        Dedup writes no row when the value is unchanged, so the row carrying the
        pinned value and its `reading_count` was created when that value first
        appeared. A `captured_at >= window_start` filter discards exactly that
        row and keeps only the heartbeat rows inside the window — measured on
        production as 2 observations over 12 minutes, and the rule fired on 0 of
        44 live events instead of 10.

        Read off the statement the helper built and executed, so the two filters
        are distinguishable — the aggregate itself is supplied by this test and
        cannot tell them apart.
        """
        from app.routes.events import _pinned_live_probability

        session = _session(agg=_flat_agg())
        await _pinned_live_probability(session, _event())

        where = session.flatness_sql.split("where", 1)[1]
        assert "coalesce" in where and "valid_until" in where

    @pytest.mark.asyncio
    async def test_the_league_coverage_answer_is_cached(self):
        """Six hours per league, so the 60-150ms is paid once, not per request."""
        from app.routes.events import _pinned_live_probability

        session = _session(agg=_flat_agg())
        await _pinned_live_probability(session, _event())
        await _pinned_live_probability(session, _event())
        assert session.coverage_calls == 1
