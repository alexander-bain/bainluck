"""#4028 — a dead source stops transmitting freshness it did not observe.

═══ THE SPECIMEN ═══

Production, 2026-09-08 18:34Z. Event 15307196, Mets @ Marlins, first pitch
22:40Z — four hours away — renders `Marlins 1% – 99% Mets` under the caption
"18 sportsbooks", and `GET /api/leagues/baseball_mlb` serves the same 0.008 to
every card.

    events.win_probability_sources (15307196)
      betting     value=0.5327  updated_at=2026-09-08T17:35:26Z
      polymarket  value=0.008   updated_at=2026-09-08T18:30:36Z   <- 4 min old

    futures_markets 59997543  (polymarket container 947631, the SEPT 1 game)
      outcome 225132364 "New York Mets"  current_probability=0.992
        last_updated     = 2026-09-07 20:07:25Z                   <- 22 h old
        price_changed_at = NULL

`0.992` is the Mets' settled price from September 1. Home is Miami, so the hero
is `1 - 0.992`. **The stamp is not a lie about the price. It is a lie about the
observation.** `_phase2_persist_group_reading` runs every fifteen minutes over
rows it already has — it re-derives a number, it does not re-observe a venue —
and it let `stamp_source_reading` default its own `now()`. So a frozen price was
re-declared fresh four times an hour, and because the hero's decay is relative
to the freshest stamp ON THE SAME EVENT (deliberately clock-free, gotcha #44),
the ghost's heartbeat decayed the honest source instead of itself:

    betting     3.0 -> 0.6084     (34 min "behind" a market that had not moved
    polymarket  0.8 -> 0.8         since the previous evening)
    divergence: spread=0.5247  primary='polymarket'  -> hero 0.008

═══ WHY THE FIX IS NOT WHERE IT LOOKS ═══

Not the divergence gate. "Prefer the sportsbook" inverts a rule that was
measured and is right in the general case — a base-weight primary prints the
stale pregame line over a live blowout, which is #240 rebuilt.

Not an exclusion of settled markets, however much that is the right sentence in
principle: measured on production, all three ghost containers on this event read
`futures_markets.status='open'`, `settled_at IS NULL` and every
`futures_outcomes.is_winner` ungraded. Nothing on our side knows they settled —
gotcha #33's Kalshi rule extends to Polymarket. Their one honest tell is
`last_updated`, the column documented as "when did the poller last SEE this row".

Not an extremity screen. #4024 measured it: `pm > 0.97 OR pm < 0.03` on unstarted
games returns 22 rows and most are correct (FCS-vs-P5 body-bag games where 99% is
a true price). Extremity is a claim about the world; disagreement is a claim
about us.

So: stamp the observation time, not the recompute time.

═══ WHAT THESE TESTS PIN, AND WHICH ARMS CROSS ═══

1. `source_observation_time` in isolation: reads it, clamps a future one, and
   returns None — never a fabricated old value — when the row cannot answer.
2. THE WRITER (red on master): the matcher stamps the originating outcome's
   observation time on a frozen row, and ~now on a live one. The third arm here
   is the one that keeps every OTHER suite honest — a row with no `last_updated`
   at all must still stamp ~now, which is why `test_phase2_writer_group_reading_
   cert767.py` stays green unchanged.
3. THE COMPOSED CHAIN, writer into reader, on the production shape — and its
   BOTH-ARM CONTROL. `test_the_ghost_wins_when_the_stamp_is_now` drives the same
   composition with the pre-fix stamp and asserts the hero reads 0.008: it passes
   on master and on this branch, which is what makes arm 3's 0.5327 mean
   something rather than merely being green.

The general clause, because the decay is not the thing that is wrong: a recency
rule assumes A SOURCE STOPS PUBLISHING WHEN IT STOPS KNOWING, and that assumption
was written down nowhere. A re-stamp is only honest when it records a
re-OBSERVATION.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.aggregation import (
    compute_aggregate_probability,
    stamp_source_reading,
)

# `source_observation_time` is imported INSIDE each test that needs it, for the
# reason cert767's header gives: on master the symbol does not exist, and a
# module-level import turns every red arm in this file into one collection error
# instead of a failure per behaviour. A red arm you cannot read is not a red arm.

from tests.test_phase2_writer_group_reading_cert767 import (
    _EventRow,
    _FakeSession,
    _Outcome,
)

# The production instant, to the second, from the db-query in #4028.
NOW = datetime(2026, 9, 8, 18, 30, 36, tzinfo=timezone.utc)
BETTING_STAMP = datetime(2026, 9, 8, 17, 35, 26, tzinfo=timezone.utc)
GHOST_OBSERVED = datetime(2026, 9, 7, 20, 7, 25, tzinfo=timezone.utc)

BETTING_VALUE = 0.5327
GHOST_HOME_VALUE = 0.008  # 1 - 0.992, the Mets' settled Sept-1 price


class _StampedOutcome(_Outcome):
    """cert767's outcome plus the column this ship reads."""

    def __init__(self, market_id, rank, name, probability, last_updated):
        super().__init__(market_id, rank, name, probability)
        self.last_updated = last_updated


def _ghost_group():
    """Event 15307196's polymarket container, as one linked-market group."""
    from app.tasks.prediction_market_matching import _LinkedMarketRef

    return [
        _LinkedMarketRef(
            market_id=59997543,
            source="polymarket",
            external_id="947631",
            name="New York Mets vs. Miami Marlins",
            event_id=15307196,
            event_commence_time=datetime(2026, 9, 8, 22, 40, tzinfo=timezone.utc),
            home_team_name="Miami Marlins",
            away_team_name="New York Mets",
        )
    ]


def _ghost_outcomes(last_updated):
    return [
        _StampedOutcome(59997543, 1, "New York Mets", 0.992, last_updated),
        _StampedOutcome(59997543, 2, "Miami Marlins", 0.008, last_updated),
    ]


def _event_with_betting():
    """15307196 as the matcher finds it: a live sportsbook line, no PM key yet."""
    return _EventRow(
        15307196,
        wps={
            "betting": {
                "value": BETTING_VALUE,
                "updated_at": BETTING_STAMP.isoformat(),
            },
            "betting_book_count": 11,
        },
    )


def _hero_from(sources, status="scheduled"):
    """The number the page prints, off exactly the JSONB the writer wrote.

    `status` is a parameter since #1999: the recency decay is now an in-play
    rule, so "what would the page print" has two answers for one JSONB and a
    test that cannot say which one it is asking for is asking for neither.
    The specimen is pre-game (first pitch was four hours out), so that stays
    the default.
    """
    return compute_aggregate_probability(
        SimpleNamespace(
            win_probability_sources=sources,
            status=status,
            espn_win_prob_home=None,
            opening_home_probability=None,
        ),
        status,
    )


# =============================================================================
# 1. The helper in isolation
# =============================================================================


class TestSourceObservationTime:
    @staticmethod
    def _fn():
        from app.utils.aggregation import source_observation_time

        return source_observation_time

    def test_it_reads_the_rows_own_observation_stamp(self):
        source_observation_time = self._fn()
        row = SimpleNamespace(last_updated=GHOST_OBSERVED)
        assert source_observation_time(row, now=NOW) == GHOST_OBSERVED

    def test_a_future_stamp_is_clamped_to_now(self):
        """A skewed clock must not hand a source the freshest slot on the event.

        Unclamped, this is the bug with its sign flipped: the row would decay
        every honest sibling against a time that never happened.
        """
        source_observation_time = self._fn()
        row = SimpleNamespace(last_updated=NOW + timedelta(hours=3))
        assert source_observation_time(row, now=NOW) == NOW

    def test_a_row_that_cannot_answer_returns_none_never_an_old_value(self):
        """None means "use your own clock", and it must never mean "old".

        Fabricating an age here would demote a source for the crime of being
        loaded by a caller that does not carry the column (gotcha #53).
        """
        source_observation_time = self._fn()
        assert source_observation_time(SimpleNamespace(), now=NOW) is None
        assert (
            source_observation_time(SimpleNamespace(last_updated=None), now=NOW) is None
        )
        assert (
            source_observation_time(SimpleNamespace(last_updated="not a date"), now=NOW)
            is None
        )

    def test_a_naive_stamp_is_read_as_utc_and_still_compares(self):
        source_observation_time = self._fn()
        row = SimpleNamespace(last_updated=GHOST_OBSERVED.replace(tzinfo=None))
        assert source_observation_time(row, now=NOW) == GHOST_OBSERVED

    def test_none_flows_through_stamp_source_reading_as_the_writers_own_clock(self):
        """The fallback has to be a real fallback, not an unstamped entry."""
        before = datetime.now(timezone.utc)
        stamped = stamp_source_reading({}, "polymarket", 0.5, now=None)
        written = datetime.fromisoformat(stamped["polymarket"]["updated_at"])
        assert before <= written <= datetime.now(timezone.utc)


# =============================================================================
# 2. The writer — red on master
# =============================================================================


@pytest.mark.asyncio
class TestTheMatcherStampsWhatItObserved:
    async def _stamp_written(self, last_updated):
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        session = _FakeSession(_ghost_outcomes(last_updated), _event_with_betting())
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}
        await _phase2_persist_group_reading(session, _ghost_group(), stats)

        stamped = session.stamped_sources()
        assert stamped is not None, "no win_probability_sources UPDATE was recorded"
        assert "polymarket" in stamped, "the polymarket source key was not persisted"
        return stamped, datetime.fromisoformat(stamped["polymarket"]["updated_at"])

    async def test_a_frozen_row_is_stamped_at_its_own_last_observation(self):
        """RED ON MASTER: master writes `now()` and calls a 22-hour-old price fresh."""
        _, written = await self._stamp_written(GHOST_OBSERVED)

        assert written == GHOST_OBSERVED, (
            f"the matcher stamped {written.isoformat()} for a price it last saw at "
            f"{GHOST_OBSERVED.isoformat()} — a re-read is not a re-observation"
        )

    async def test_a_live_row_is_still_stamped_now_so_healthy_sources_do_not_decay(
        self,
    ):
        """The inertness claim, stated as a test rather than asserted in a comment."""
        fresh = datetime.now(timezone.utc) - timedelta(seconds=20)
        _, written = await self._stamp_written(fresh)

        assert written == fresh
        assert (datetime.now(timezone.utc) - written) < timedelta(minutes=1), (
            "a currently-polled source must keep a current stamp, or this ship "
            "decays every live venue it was supposed to leave alone"
        )

    async def test_a_row_without_the_column_falls_back_to_the_writers_clock(self):
        """Why every other suite in this repo stays green unchanged.

        cert767's `_Outcome` has no `last_updated`. If the fallback were anything
        but "now", this ship would silently re-date every fixture in the codebase.
        """
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        session = _FakeSession(
            [
                _Outcome(59997543, 1, "New York Mets", 0.992),
                _Outcome(59997543, 2, "Miami Marlins", 0.008),
            ],
            _event_with_betting(),
        )
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}
        before = datetime.now(timezone.utc)
        await _phase2_persist_group_reading(session, _ghost_group(), stats)

        written = datetime.fromisoformat(
            session.stamped_sources()["polymarket"]["updated_at"]
        )
        assert before <= written <= datetime.now(timezone.utc)


# =============================================================================
# 3. The composed chain — writer into reader, on the production shape
# =============================================================================


class TestTheHeroThePageWouldPrint:
    @pytest.mark.asyncio
    async def test_the_sportsbook_survives_a_ghost_that_stopped_publishing(self):
        """RED ON MASTER: the page prints 0.008, four hours before first pitch."""
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        session = _FakeSession(_ghost_outcomes(GHOST_OBSERVED), _event_with_betting())
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}
        await _phase2_persist_group_reading(session, _ghost_group(), stats)

        hero = _hero_from(session.stamped_sources())

        assert hero == pytest.approx(
            BETTING_VALUE
        ), f"hero is {hero}; the ghost is still arbitrating an unstarted game"

    def test_the_ghost_wins_when_the_stamp_is_now(self):
        """BOTH-ARM CONTROL — green on master AND here. Not a regression guard.

        It states the pre-fix behaviour as an executable fact, so the arm above
        is a measured difference rather than a green light. Deliberately built
        from `stamp_source_reading` directly: the writer no longer produces this
        shape, and pinning it any other way would pin nothing.

        ASKED IN PLAY SINCE #1999. This control used to be asked pre-game, via
        `_hero_from`'s `status="scheduled"`. It cannot be asked there any more,
        because the pre-game recency gate makes the outcome it describes
        unreachable before kickoff — a ghost holding the freshest stamp on an
        unstarted game no longer outvotes the books at all
        (`test_pregame_recency_gate_1999.py` pins that as its own ship). Moving
        the control in-play keeps it doing the only job it has: proving the arm
        above measures a real difference rather than an inert code path. The
        pre-game half of this same shape is now the STRONGER claim and lives
        beside the gate.
        """
        sources = stamp_source_reading(
            _event_with_betting().win_probability_sources,
            "polymarket",
            GHOST_HOME_VALUE,
            now=NOW,
        )

        assert _hero_from(sources, status="live") == pytest.approx(GHOST_HOME_VALUE)

    def test_the_ghost_is_demoted_not_deleted(self):
        """The floor is 0.1, and "we stopped hearing from Polymarket" is not
        "Polymarket does not exist" — the source key must survive in the column.

        ASKED IN PLAY SINCE #1999, for the same reason as the control above:
        demotion is what happens while a game is running. The pre-game arm of
        the same invariant — the key survives there too, at FULL weight, because
        nothing has gone stale before kickoff — is the test below.
        """
        from app.utils.aggregation import effective_source_weights

        sources = stamp_source_reading(
            _event_with_betting().win_probability_sources,
            "polymarket",
            GHOST_HOME_VALUE,
            now=GHOST_OBSERVED,
        )
        keys, _, weights = effective_source_weights(
            SimpleNamespace(win_probability_sources=sources, status="live"),
            "live",
        )

        assert "polymarket" in keys, "the demoted source was dropped, not decayed"
        assert weights[keys.index("polymarket")] == pytest.approx(0.08)
        assert weights[keys.index("betting")] == pytest.approx(3.0)

    def test_pregame_the_ghost_is_not_demoted_at_all_and_still_loses(self):
        """#1999's half of the same guarantee, so the pair reads as one rule.

        Before kickoff the ghost keeps its full 0.8 — a five-day-old sportsbook
        line and a fresh market price are not evidence about each other when
        nothing is moving — and it loses anyway, on the base weights, which is
        the outcome #4028 exists to protect.
        """
        from app.utils.aggregation import effective_source_weights

        sources = stamp_source_reading(
            _event_with_betting().win_probability_sources,
            "polymarket",
            GHOST_HOME_VALUE,
            now=GHOST_OBSERVED,
        )
        keys, _, weights = effective_source_weights(
            SimpleNamespace(win_probability_sources=sources, status="scheduled"),
            "scheduled",
        )

        assert weights[keys.index("polymarket")] == pytest.approx(0.8)
        assert weights[keys.index("betting")] == pytest.approx(3.0)
        assert _hero_from(sources) == pytest.approx(BETTING_VALUE)
