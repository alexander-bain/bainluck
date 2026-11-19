"""A live game's projected final is built from the same current lines as Sportsbooks in Now (#12938).

Alex's bug report, Tue Nov 17: on UC Irvine at Stanford the projected final read
UC Irvine 65, Stanford 68 from the same eight sportsbook lines that had stopped
moving between 9:05 and 9:07 PM. Ruling 233: A's rule (`live_line_is_current`)
now decides which lines project too. The odds job stores the game clock it used
(its last score change, or its start) in the sources bag, and the page and the
cards read it from there, so the card pair's read stays one statement (#2920;
Fable's option A, Nov 18).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils import card_projected_pair as cpp
from app.utils.live_line_clock import (
    LIVE_STATE_CLOCK_KEY,
    apply_live_line_projection,
    event_state_clock,
    stored_state_clock,
)
from tests.test_live_sportsbooks_counts_current_lines_12938 import (  # noqa: F401
    STANFORD_AT_915,
    ingest,
)

NOW = datetime.now(timezone.utc)
SCORE_CHANGE = NOW - timedelta(seconds=101)  # 65-61 at 9:13:19, read at 9:15:00


@pytest.fixture(autouse=True)
def _fresh_clock():
    """Ages are relative to the clock the card code reads (`datetime.now`).

    Built once at import, they aged with the suite: in an eight-minute run every
    line looked old. Rebuilt per test, offset first (gotcha #44).
    """
    global NOW, SCORE_CHANGE, BOARD
    NOW = datetime.now(timezone.utc)
    SCORE_CHANGE = NOW - timedelta(seconds=101)
    BOARD = _board()
    yield


def _snap(book, *, age_s, spread, total, home_prob=0.9, event_id=1):
    s = SimpleNamespace()
    s.bookmaker = book
    s.event_id = event_id
    s.home_win_probability = home_prob
    s.away_win_probability = 1 - home_prob
    s.home_spread = spread
    s.over_under = total
    s.projected_home_score = round((total - spread) / 2, 1)
    s.projected_away_score = round((total + spread) / 2, 1)
    s.captured_at = NOW - timedelta(seconds=age_s)
    s.valid_until = NOW - timedelta(seconds=5)  # every line still re-served
    s.home_moneyline = -2000
    s.away_moneyline = 1000
    return s


def _board():
    """Three current lines (Stanford -4.5 / 133) and eight frozen at 9:05-9:07 PM
    (Stanford -2.5 / 135.5, projecting 68-66 territory)."""
    return [
        _snap("draftkings", age_s=111, spread=-4.5, total=133.0),
        _snap("courtside", age_s=111, spread=-4.5, total=133.0),
        _snap("fanatics", age_s=176, spread=-4.5, total=133.0),
        *[_snap(f"frozen{i}", age_s=480 + i, spread=-2.5, total=135.5) for i in range(8)],
    ]


BOARD = _board()


def _all_lines_mean():
    from app.utils.odds_math import aggregate_bookmaker_odds
    return aggregate_bookmaker_odds(BOARD)


class TestTheStoredClock:
    def test_an_iso_clock_parses(self):
        assert stored_state_clock({LIVE_STATE_CLOCK_KEY: "2026-11-18T05:13:19+00:00"}) == datetime(
            2026, 11, 18, 5, 13, 19, tzinfo=timezone.utc
        )

    @pytest.mark.parametrize("bag", [None, {}, {LIVE_STATE_CLOCK_KEY: 5}, {LIVE_STATE_CLOCK_KEY: "soon"}])
    def test_no_usable_clock_is_none(self, bag):
        assert stored_state_clock(bag) is None

    def test_only_a_live_event_has_one(self):
        bag = {LIVE_STATE_CLOCK_KEY: SCORE_CHANGE.isoformat()}
        assert event_state_clock(SimpleNamespace(status="live", win_probability_sources=bag)) == SCORE_CHANGE
        for status in ("scheduled", "completed", "closed"):
            assert event_state_clock(SimpleNamespace(status=status, win_probability_sources=bag)) is None


class TestThePageProjection:
    def test_frozen_lines_no_longer_project(self):
        base = _all_lines_mean()
        out = apply_live_line_projection(base, BOARD, now=NOW, state_changed_at=SCORE_CHANGE)
        assert out["home_spread"] == -4.5
        assert out["over_under"] == 133.0
        assert (out["projected_home_score"], out["projected_away_score"]) == (68.8, 64.2)
        # control: all eleven lines project the frozen board's numbers
        assert base["home_spread"] != -4.5

    def test_with_no_current_line_the_projection_is_withheld(self):
        frozen = BOARD[3:]
        out = apply_live_line_projection(_all_lines_mean(), frozen, now=NOW, state_changed_at=SCORE_CHANGE)
        for key in ("home_spread", "over_under", "projected_home_score", "projected_away_score"):
            assert out[key] is None

    def test_two_current_lines_still_project(self):
        """No floor: a blowout keeps a spread and total after the moneyline goes (#8922)."""
        out = apply_live_line_projection(_all_lines_mean(), BOARD[:2] + BOARD[3:], now=NOW,
                                         state_changed_at=SCORE_CHANGE)
        assert out["home_spread"] == -4.5

    def test_no_clock_leaves_the_projection_exactly_as_it_was(self):
        base = _all_lines_mean()
        assert apply_live_line_projection(base, BOARD, now=NOW, state_changed_at=None) == base

    def test_probability_and_count_are_not_touched(self):
        base = _all_lines_mean()
        out = apply_live_line_projection(base, BOARD, now=NOW, state_changed_at=SCORE_CHANGE)
        assert out["bookmaker_count"] == base["bookmaker_count"]
        assert out["home_probability"] == base["home_probability"]


class TestTheCardPair:
    def _pair(self, snaps, clock):
        return cpp.card_projected_pair(
            snaps, stored_status="live", served_status="live",
            commence_time=NOW - timedelta(hours=2), sport_key="basketball_ncaab",
            state_changed_at=clock,
        )

    def test_the_card_projects_from_current_lines(self):
        pair = self._pair(BOARD, SCORE_CHANGE)
        assert (pair["projected_home_score"], pair["projected_away_score"]) == (68.8, 64.2)

    def test_no_current_line_means_no_card_pair(self):
        assert self._pair(BOARD[3:], SCORE_CHANGE) is None

    def test_without_a_clock_the_card_is_unchanged(self):
        pair = self._pair(BOARD, None)
        assert pair["projected_home_score"] != 68.8

    def test_the_card_reads_the_clock_from_the_loaded_bag(self):
        bag = {LIVE_STATE_CLOCK_KEY: SCORE_CHANGE.isoformat()}
        ev = SimpleNamespace(id=1, status="live", commence_time=NOW - timedelta(hours=2),
                             win_probability_sources=bag, period=None,
                             start_is_tbd=False, start_is_from_schedule=True)
        card = cpp.card_projection_card(ev, served_status="live", sport_key="basketball_ncaab")
        assert card["state_changed_at"] == SCORE_CHANGE
        ev.status = "scheduled"
        card = cpp.card_projection_card(ev, served_status="scheduled", sport_key="basketball_ncaab")
        assert card["state_changed_at"] is None


class TestTheOddsJobStoresTheClock:
    @pytest.mark.asyncio
    async def test_a_live_write_carries_the_game_clock(self, ingest):  # noqa: F811
        _, calls, now = await ingest(STANFORD_AT_915)
        stored = datetime.fromisoformat(calls[0]["metadata"][LIVE_STATE_CLOCK_KEY])
        assert abs((now - stored).total_seconds() - 101) < 1

    @pytest.mark.asyncio
    async def test_a_live_drop_carries_it_too(self, ingest):  # noqa: F811
        lines = [(b, p, age + 240) for b, p, age in STANFORD_AT_915]
        _, calls, _ = await ingest(lines, score_ago=341)
        assert calls[0]["value"] is None
        assert LIVE_STATE_CLOCK_KEY in calls[0]["metadata"]

    @pytest.mark.asyncio
    async def test_a_pregame_write_does_not(self, ingest):  # noqa: F811
        lines = [(f"b{i}", 0.6, 7200) for i in range(3)]
        _, calls, _ = await ingest(lines, start_ago=-3600, status="scheduled")
        assert LIVE_STATE_CLOCK_KEY not in calls[0]["metadata"]


class TestTheBagKeyIsNotASource:
    BAG = {
        "betting": {"value": 0.96, "updated_at": NOW.isoformat()},
        "polymarket": {"value": 0.995, "updated_at": NOW.isoformat()},
        "betting_book_count": 3,
    }

    def test_the_blend_is_unchanged(self):
        from app.utils.aggregation import compute_aggregate_probability

        def ev(bag):
            return SimpleNamespace(id=1, status="live", win_probability_sources=bag, espn_win_prob_home=None)
        with_clock = dict(self.BAG, **{LIVE_STATE_CLOCK_KEY: SCORE_CHANGE.isoformat()})
        assert compute_aggregate_probability(ev(with_clock), "live") == compute_aggregate_probability(
            ev(self.BAG), "live"
        )

    def test_it_is_never_served_as_a_source_row(self):
        """iOS throws on a source whose value is not a number (#3914's lesson)."""
        from app.utils.probability_source_format import format_probability_sources

        with_clock = dict(self.BAG, **{LIVE_STATE_CLOCK_KEY: SCORE_CHANGE.isoformat()})
        assert LIVE_STATE_CLOCK_KEY not in format_probability_sources(with_clock)
        assert set(format_probability_sources(with_clock)) == set(format_probability_sources(self.BAG))
