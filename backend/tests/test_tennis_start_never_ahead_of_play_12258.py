"""A match ESPN scores is never given a start still ahead of now (#12258).

At 07:31Z on Nov 7 the Flow Sentinel found two tennis rows live with their
start 2.5 h and 7.5 h in the future: Kabbaj v Blinkova (15342993) and
Andreescu v Tubello (15343148), both stamped ``commence_time_source='espn'``.
Each was the one match of its round not played on Nov 6, and ESPN dated it to
Nov 7 (10:05Z and 15:05Z). The tennis anchor writes ESPN's ``date`` as the start
whenever it moves, so a match already in play took the next session's time and
became live before its own start. A start the pass refuses here is one the row
already holds: nothing else on the row changes.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.espn_tennis_anchor import authority_write
from tests.test_espn_tennis_anchor import (
    _Event,
    _competition,
    _install,
    _lost,
    _payload,
    _won,
)

NOW = datetime(2026, 11, 7, 7, 31, 12, tzinfo=timezone.utc)
BEGAN = datetime(2026, 11, 6, 11, 0, tzinfo=timezone.utc)


def _write(state, date, *, our_status="live", ours=BEGAN, completed=None, now=NOW, games=2):
    return authority_write(
        our_status=our_status,
        our_completed_at=completed,
        our_commence_time=ours,
        our_commence_time_source="espn",
        competition={"state": state, "date": date, "start_is_tbd": False, "sets_with_play": games},
        now=now,
        our_home_score=1,
        our_away_score=0,
    )


class TestTheStartNeverMovesAheadOfPlay:
    def test_a_match_in_play_is_not_given_the_next_sessions_start(self):
        """The specimen: in play since Nov 6, ESPN now dates it 10:05Z Nov 7."""
        changes = _write("in_progress", "2026-11-07T10:05Z")
        assert "commence_time" not in changes
        assert "commence_time_source" not in changes

    def test_the_row_stays_live_on_the_start_it_already_holds(self):
        assert "status" not in _write("in_progress", "2026-11-07T10:05Z")
        assert _write("in_progress", "2026-11-07T10:05Z", our_status="scheduled")["status"] == "live"

    def test_a_decided_match_is_not_given_a_start_after_now_either(self):
        """A match finished before its listed time (a retirement, a walkover)
        would otherwise be settled before its own start."""
        assert "commence_time" not in _write("decided", "2026-11-07T15:05Z", our_status="completed")

    def test_the_date_is_taken_once_it_has_passed(self):
        """Then it is a time the match was being played at, and the correction
        runs as before (the slid-start rule, #5971)."""
        changes = _write("in_progress", "2026-11-07T07:20Z", ours=datetime(2026, 11, 7, 7, 0, tzinfo=timezone.utc))
        assert changes["commence_time"] == datetime(2026, 11, 7, 7, 20, tzinfo=timezone.utc)
        assert changes["commence_time_source"] == "espn"

    def test_an_upcoming_match_still_takes_a_future_start(self):
        """The control: ESPN's clock for a match nobody has started is its start."""
        changes = _write("upcoming", "2026-11-07T10:05Z", our_status="scheduled",
                         ours=datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc))
        assert changes["commence_time"] == datetime(2026, 11, 7, 10, 5, tzinfo=timezone.utc)

    @pytest.mark.parametrize("state", ["in_progress", "decided"])
    @pytest.mark.parametrize("ahead", [timedelta(minutes=6), timedelta(hours=2, minutes=30), timedelta(hours=7, minutes=30)])
    def test_no_scored_state_leaves_a_start_ahead_of_now(self, state, ahead):
        date = (NOW + ahead).strftime("%Y-%m-%dT%H:%MZ")
        changes = _write(state, date, our_status="live" if state == "in_progress" else "completed")
        assert changes.get("commence_time", BEGAN) <= NOW


class TestTheInFlagAloneDoesNotStartAMatch:
    """ESPN's `in` with no game on the board and its own start still ahead."""

    def test_a_scheduled_row_is_not_made_live(self):
        assert _write("in_progress", "2026-11-07T10:05Z", our_status="scheduled",
                      ours=datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc), games=0) == {}

    def test_once_espns_start_has_passed_the_flag_is_taken(self):
        changes = _write("in_progress", "2026-11-07T07:25Z", our_status="scheduled",
                         ours=datetime(2026, 11, 7, 7, 25, tzinfo=timezone.utc), games=0)
        assert changes["status"] == "live"

    def test_a_game_on_the_board_is_play_whatever_the_clock_says(self):
        """lane1/054: Taberner v Bergs was three sets deep while ESPN still
        listed a start 40 minutes ahead."""
        changes = _write("in_progress", "2026-11-07T08:10Z", our_status="scheduled", games=3)
        assert changes["status"] == "live"
        assert "commence_time" not in changes

    def test_a_board_without_the_count_keeps_the_old_behaviour(self):
        """No `sets_with_play` is not zero games: the flag is taken, as before."""
        changes = authority_write(
            our_status="scheduled", our_completed_at=None,
            our_commence_time=datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc),
            competition={"state": "in_progress", "date": "2026-11-07T10:05Z", "start_is_tbd": False},
            now=NOW,
        )
        assert changes["status"] == "live"


class TestThroughThePass:
    """End to end through ``_sync_tennis_from_espn``, which reads the wall
    clock, so the board's dates are offsets from it."""

    async def test_a_match_rescheduled_mid_play_keeps_its_start(self, monkeypatch):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        now = datetime.now(timezone.utc)
        began = now - timedelta(hours=20)
        resumes = (now + timedelta(hours=2, minutes=30)).strftime("%Y-%m-%dT%H:%MZ")
        event = _Event(
            15342993, "Anna Blinkova", "Yasmine Kabbaj", "live", began,
            espn_id="186688", home_score=1, away_score=0, commence_time_source="espn",
        )
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "186688", ["Anna Blinkova", "Yasmine Kabbaj"], state="pre", period=2,
                date=resumes, linescores=[_won(6), _lost(2)],
            )], slug="womens-singles")],
            errors=[],
            sport_keys=["tennis_wta_us_open", "tennis_wta"],
            events=[event],
        )

        stats = await _sync_tennis_from_espn()

        assert event.commence_time == began
        assert event.commence_time_source == "espn"
        assert event.status == "live"
        assert stats["commence_writes"] == 0

    async def test_once_the_session_has_begun_the_pass_takes_its_time(self, monkeypatch):
        """The control: the same board an hour into the resumed session."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        now = datetime.now(timezone.utc)
        began = now - timedelta(hours=20)
        resumed = (now - timedelta(hours=1)).replace(second=0, microsecond=0)
        event = _Event(
            15342993, "Anna Blinkova", "Yasmine Kabbaj", "live", began,
            espn_id="186688", home_score=1, away_score=0, commence_time_source="espn",
        )
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "186688", ["Anna Blinkova", "Yasmine Kabbaj"], state="in", period=2,
                date=resumed.strftime("%Y-%m-%dT%H:%MZ"), linescores=[_won(6), _lost(2)],
            )], slug="womens-singles")],
            errors=[],
            sport_keys=["tennis_wta_us_open", "tennis_wta"],
            events=[event],
        )

        stats = await _sync_tennis_from_espn()

        assert event.commence_time == resumed
        assert stats["commence_writes"] == 1

    async def test_the_in_flag_before_espns_start_with_no_game_leaves_the_row(self, monkeypatch):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        now = datetime.now(timezone.utc)
        listed = (now + timedelta(minutes=40)).replace(second=0, microsecond=0)
        event = _Event(
            15343148, "Bianca Andreescu", "Alice Tubello", "scheduled", listed,
            espn_id="186735", commence_time_source="espn",
        )
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "186735", ["Bianca Andreescu", "Alice Tubello"], state="in", period=1,
                date=listed.strftime("%Y-%m-%dT%H:%MZ"),
            )], slug="womens-singles")],
            errors=[],
            sport_keys=["tennis_wta_us_open", "tennis_wta"],
            events=[event],
        )

        await _sync_tennis_from_espn()

        assert event.status == "scheduled"
        assert event.commence_time == listed
