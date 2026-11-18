"""In a live game only current sportsbook lines count toward Now (#12938, ruling 233: A).

SPECIMEN, Alex's bug report, Tue Nov 17. UC Irvine at Stanford (15350027),
Stanford up 65-61 late. Now read 93.2% while Polymarket read 99.5% and our model
99.89%. Sportsbooks was 81.03%: the median of twelve lines, eight of which had
last moved between 9:05 and 9:07 PM and were still being re-served unchanged by
The Odds API at 9:15 (stored `valid_until` ran to 9:19-9:21 PM). Nothing dropped
a quiet book; only a pulled line (no moneyline) left the count.

The rule (`live_line_is_current`): a live line counts while its price changed in
the last three minutes, or changed after the game's last score change (the start
before any score). Below the existing floor of three, Sportsbooks leaves Now.

The ingest tests drive the real `_ingest_event_odds` with the twelve lines'
stored prices and their ages at 9:15:00 PM, read from the public history.
"""

import statistics
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.odds_polling import (
    BETTING_BOOK_FLOOR,
    _game_state_changed_at,
    _ingest_event_odds,
    _is_live_game,
)
from app.utils.odds_filtering import LIVE_LINE_CURRENT_SECONDS, live_line_is_current
from tests.nonvenue_writer_seam import portable_nonvenue_write
from tests.test_discovery_advances_betting_consensus_5426 import (
    _FakeEvent,
    _RecordingSession,
)

#: The twelve lines counted at 9:15:00 PM PT: (book, Stanford chance, seconds
#: since the price last changed). Public history, /api/events/15350027/history.
STANFORD_AT_915 = [
    ("draftkings", 0.9686, 111),   # 9:13:09
    ("courtside", 0.954, 111),     # 9:13:09
    ("fanatics", 0.9626, 176),     # 9:12:04
    ("bovada", 0.895, 221),        # 9:11:19
    ("fanduel", 0.7857, 425),      # 9:07:55
    ("espnbet", 0.8152, 475),      # 9:07:05
    ("fliff", 0.8219, 475),        # 9:07:05
    ("betwhale", 0.7692, 476),     # 9:07:04
    ("ballybet", 0.7127, 540),     # 9:06:00
    ("betparx", 0.8054, 540),      # 9:06:00
    ("betrivers", 0.7095, 540),    # 9:06:00
    ("hardrockbet", 0.7059, 591),  # 9:05:09
]
#: 65-61 arrived at 9:13:19 PM, 101 s before 9:15:00.
SCORE_CHANGE_AGO = 101
#: Tip-off 7:00 PM.
START_AGO = 2 * 3600 + 15 * 60


class _Snap:
    def __init__(self, home, changed_at, spread=None, over_under=None):
        self.home_win_probability = home
        self.away_win_probability = 1 - home
        self.home_spread = spread
        self.over_under = over_under
        self.captured_at = changed_at


class _Session(_RecordingSession):
    """Answers the score read; records every other statement as the parent does."""

    def __init__(self, last_score_at, status="live"):
        super().__init__(status=status)
        self.last_score_at = last_score_at
        self.score_reads = 0

    async def execute(self, stmt):
        if "score_snapshots" in str(stmt):
            self.score_reads += 1
            last = self.last_score_at

            class _R:
                def scalar(self):
                    return last

            return _R()
        return await super().execute(stmt)


@pytest.fixture
def ingest(monkeypatch):
    """Run the real ingest over (book, chance, age) lines; return what it wrote."""
    calls: list[dict] = []

    async def _recording_write(session, event, source, value, **kwargs):
        calls.append({"source": source, "value": value, **kwargs})
        kwargs.pop("price_read_at", None)
        return await portable_nonvenue_write(session, event, source, value, **kwargs)

    monkeypatch.setattr(
        "app.utils.nonvenue_live_push.write_nonvenue_probability", _recording_write
    )

    async def _run(lines, *, start_ago=START_AGO, score_ago=SCORE_CHANGE_AGO,
                   status="live", sources=None, drop_below_floor=True):
        now = datetime.now(timezone.utc)
        queue = [_Snap(p, now - timedelta(seconds=age)) for _, p, age in lines]

        async def _fake(session, event_id, bookmaker, event_data, snapshot_cache=None):
            return queue.pop(0), False

        monkeypatch.setattr("app.tasks.odds_polling._create_or_update_snapshot", _fake)
        event = _FakeEvent(sources if sources is not None else {
            "betting": {"value": 0.8103, "updated_at": now.isoformat()},
            "polymarket": {"value": 0.995, "updated_at": now.isoformat()},
        }, status=status)
        session = _Session(
            None if score_ago is None else now - timedelta(seconds=score_ago),
            status=status,
        )
        await _ingest_event_odds(
            session, event, {"bookmakers": [{"key": b} for b, _, _ in lines]},
            now - timedelta(seconds=start_ago), {},
            drop_below_floor=drop_below_floor,
        )
        return session, calls, now

    return _run


class TestTheRule:
    NOW = datetime(2026, 11, 18, 5, 15, tzinfo=timezone.utc)

    def test_a_line_that_moved_in_the_last_three_minutes_counts(self):
        at = self.NOW - timedelta(seconds=LIVE_LINE_CURRENT_SECONDS)
        assert live_line_is_current(at, now=self.NOW, state_changed_at=self.NOW)

    def test_an_older_line_priced_before_the_score_changed_does_not(self):
        at = self.NOW - timedelta(seconds=LIVE_LINE_CURRENT_SECONDS + 1)
        assert not live_line_is_current(
            at, now=self.NOW, state_changed_at=at + timedelta(seconds=1)
        )

    def test_an_older_line_priced_after_the_last_score_change_still_counts(self):
        """Hockey: a line resting between goals has seen the current score."""
        at = self.NOW - timedelta(minutes=8)
        assert live_line_is_current(
            at, now=self.NOW, state_changed_at=at - timedelta(minutes=1)
        )

    def test_an_undated_line_never_counts(self):
        assert not live_line_is_current(None, now=self.NOW, state_changed_at=None)

    def test_without_a_state_clock_only_the_window_admits(self):
        assert not live_line_is_current(
            self.NOW - timedelta(minutes=4), now=self.NOW, state_changed_at=None
        )

    def test_the_window_is_three_minutes(self):
        assert LIVE_LINE_CURRENT_SECONDS == 180


class TestTheSpecimen:
    def test_today_the_twelve_lines_median_to_the_served_81_percent(self):
        """The replay's baseline reproduces the number Alex saw behind 93.2%."""
        assert round(statistics.median(p for _, p, _ in STANFORD_AT_915), 4) == 0.8103

    @pytest.mark.asyncio
    async def test_at_915_sportsbooks_is_the_three_current_lines(self, ingest):
        """DraftKings, Courtside and Fanatics moved in the last three minutes.

        The other nine last moved before 65-61 arrived at 9:13:19 and longer
        than three minutes ago, so they do not count: 96.26%, not 81.03%.
        """
        session, calls, now = await ingest(STANFORD_AT_915)
        betting = [c for c in calls if c["source"] == "betting"]
        assert len(betting) == 1
        assert betting[0]["value"] == pytest.approx(0.9626)
        assert betting[0]["metadata"]["betting_book_count"] == 3
        assert betting[0]["evidence"]["live"]["quoting"] == 12
        assert betting[0]["evidence"]["live"]["current"] == 3
        assert {b["book"] for b in betting[0]["evidence"]["population"]} == {
            "draftkings", "courtside", "fanatics",
        }
        assert session.score_reads == 1

    @pytest.mark.asyncio
    async def test_sportsbooks_is_dated_by_its_oldest_counted_line(self, ingest):
        """Fanatics, 176 s old: not the poll that carried it (#12938 item 2)."""
        _, calls, now = await ingest(STANFORD_AT_915)
        read_at = calls[0]["price_read_at"]
        assert abs((now - read_at).total_seconds() - 176) < 1

    @pytest.mark.asyncio
    async def test_with_two_current_lines_sportsbooks_leaves_now(self, ingest):
        """9:16: only the two 9:13:09 lines are current. The floor drops it."""
        lines = [(b, p, age + 60) for b, p, age in STANFORD_AT_915]
        session, calls, _ = await ingest(lines, score_ago=SCORE_CHANGE_AGO + 60)
        assert calls[0]["value"] is None
        assert calls[0]["metadata"]["betting_book_count"] == 2
        written = session.sources_writes[-1]
        assert "betting" not in written
        assert written["polymarket"]["value"] == 0.995

    @pytest.mark.asyncio
    async def test_when_every_line_is_quiet_sportsbooks_leaves_now(self, ingest):
        """9:17: no line is current. The old 81% must not stay in place."""
        lines = [(b, p, age + 240) for b, p, age in STANFORD_AT_915]
        session, calls, _ = await ingest(lines, score_ago=SCORE_CHANGE_AGO + 240)
        assert [c["value"] for c in calls] == [None]
        assert calls[0]["metadata"]["betting_book_count"] == 0
        assert calls[0]["evidence"]["live"]["current"] == 0
        assert "betting" not in session.sources_writes[-1]


class TestWhatStaysTheSame:
    @pytest.mark.asyncio
    async def test_a_quiet_line_that_has_seen_the_current_score_counts(self, ingest):
        """Hockey: no goal for ten minutes, lines resting for eight."""
        lines = [(f"b{i}", 0.55 + i / 100, 480) for i in range(5)]
        _, calls, _ = await ingest(lines, score_ago=600)
        assert calls[0]["value"] == pytest.approx(0.57)
        assert calls[0]["metadata"]["betting_book_count"] == 5

    @pytest.mark.asyncio
    async def test_before_any_score_the_start_is_the_clock(self, ingest):
        """A scoreless first period: lines priced after tip-off count."""
        lines = [(f"b{i}", 0.6, 400) for i in range(3)]
        session, calls, _ = await ingest(lines, start_ago=900, score_ago=None)
        assert calls[0]["value"] == pytest.approx(0.6)
        assert session.score_reads == 1

    @pytest.mark.asyncio
    async def test_pregame_lines_are_untouched(self, ingest):
        """Before the start a resting line is still the book's opinion."""
        lines = [(f"b{i}", 0.6 + i / 100, 7200) for i in range(3)]
        session, calls, _ = await ingest(lines, start_ago=-3600, status="scheduled")
        assert calls[0]["value"] == pytest.approx(0.61)
        assert "price_read_at" not in calls[0]
        assert "live" not in calls[0]["evidence"]
        assert session.score_reads == 0

    @pytest.mark.asyncio
    async def test_a_finished_game_is_untouched(self, ingest):
        lines = [(f"b{i}", 0.9, 7200) for i in range(3)]
        session, calls, _ = await ingest(lines, status="completed")
        assert calls[0]["value"] == pytest.approx(0.9)
        assert session.score_reads == 0

    @pytest.mark.asyncio
    async def test_a_partial_caller_under_the_floor_still_leaves_it_alone(self, ingest):
        """#5426: a narrow fetch's count is not market evidence, quiet or not."""
        lines = [(b, p, age + 240) for b, p, age in STANFORD_AT_915]
        session, calls, _ = await ingest(lines, drop_below_floor=False)
        assert calls == []
        assert session.sources_writes == []


class TestTheGameClock:
    class _S:
        def __init__(self, value):
            self.value = value

        async def execute(self, stmt):
            value = self.value

            class _R:
                def scalar(self):
                    return value

            return _R()

    @pytest.mark.asyncio
    async def test_the_last_score_change_after_the_start_is_the_clock(self):
        start = datetime(2026, 11, 18, 3, 0, tzinfo=timezone.utc)
        score = datetime(2026, 11, 18, 5, 13, 19, tzinfo=timezone.utc)
        assert await _game_state_changed_at(self._S(score), 1, start) == score

    @pytest.mark.asyncio
    async def test_a_score_row_before_the_start_yields_the_start(self):
        start = datetime(2026, 11, 18, 3, 0, tzinfo=timezone.utc)
        assert await _game_state_changed_at(
            self._S(start - timedelta(hours=1)), 1, start
        ) == start

    @pytest.mark.asyncio
    async def test_no_score_row_yields_the_start(self):
        start = datetime(2026, 11, 18, 3, 0, tzinfo=timezone.utc)
        assert await _game_state_changed_at(self._S(None), 1, start) == start

    def test_live_means_started_and_not_finished(self):
        now = datetime.now(timezone.utc)
        assert _is_live_game(_FakeEvent(status="live"), now - timedelta(minutes=5))
        assert _is_live_game(_FakeEvent(status="scheduled"), now - timedelta(minutes=5))
        assert not _is_live_game(_FakeEvent(status="scheduled"), now + timedelta(minutes=5))
        assert not _is_live_game(_FakeEvent(status="completed"), now - timedelta(hours=3))
        assert not _is_live_game(_FakeEvent(status="live"), None)


def test_the_floor_is_still_three():
    assert BETTING_BOOK_FLOOR == 3
