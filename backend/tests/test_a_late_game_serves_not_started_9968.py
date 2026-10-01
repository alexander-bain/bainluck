"""#9968 — a game past its listed time that ESPN still reads `pre` is LATE, not STARTED.

    cd backend && python3 -m pytest tests/test_a_late_game_serves_not_started_9968.py

Production, 2026-10-01: BOS @ NYY 15321907 (Wild Card G2), listed 00:00Z, served
`status: scheduled` at 00:07:47Z with no score, first pitch ≈00:15Z. The web hero
printed "Started": inside the 2h grace `started_without_result` is false whether
or not ESPN has spoken, so the payload carried no fact that told "late" from
"under way". ESPN's live pass already stamps `espn_not_started_at` on exactly that
row every 60 s (#5324); the event payload now serves it as
`authority_not_started: true`, present only when true.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Event, Sport
from app.utils.event_completion import (
    AUTHORITY_NOT_STARTED_HORIZON,
    AUTHORITY_NOT_STARTED_TTL,
    ESPN_NOT_STARTED_KEY,
    UPCOMING_GRACE,
    authority_not_started_past_schedule,
    started_without_result,
)

UTC = timezone.utc
LISTED = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)                  # 15321907 commence_time
SEEN = datetime(2026, 10, 1, 0, 7, 47, tzinfo=UTC)                # ux's API read
FRESH = (SEEN - timedelta(seconds=40)).isoformat()                # a 60 s pass's stamp


def _sources(stamp):
    return {} if stamp is None else {ESPN_NOT_STARTED_KEY: stamp}


class TestTheSpecimen:
    def test_late_and_espn_says_pre_is_not_started(self):
        assert authority_not_started_past_schedule("scheduled", LISTED, SEEN, _sources(FRESH)) is True

    def test_the_old_key_could_not_say_it(self):
        """Why a new key: inside the grace the existing one is false with or without ESPN."""
        assert started_without_result("scheduled", LISTED, SEEN, _sources(FRESH)) is False
        assert started_without_result("scheduled", LISTED, SEEN, _sources(None)) is False

    def test_control_no_stamp_says_nothing(self):
        assert authority_not_started_past_schedule("scheduled", LISTED, SEEN, _sources(None)) is False


class TestItClaimsNothingItCannotBack:
    def test_a_stamp_espn_stopped_refreshing_is_no_statement(self):
        stale = (SEEN - AUTHORITY_NOT_STARTED_TTL - timedelta(seconds=1)).isoformat()
        assert authority_not_started_past_schedule("scheduled", LISTED, SEEN, _sources(stale)) is False

    def test_at_the_ttl_it_still_counts(self):
        at_ttl = (SEEN - AUTHORITY_NOT_STARTED_TTL).isoformat()
        assert authority_not_started_past_schedule("scheduled", LISTED, SEEN, _sources(at_ttl)) is True

    def test_a_row_whose_start_is_still_ahead_is_not_late(self):
        """The stamp is also written on future-dated tennis rows (production 10/01 00:51Z)."""
        ahead = SEEN + timedelta(hours=31)
        assert authority_not_started_past_schedule("scheduled", ahead, SEEN, _sources(FRESH)) is False

    def test_at_the_listed_instant_it_counts(self):
        assert authority_not_started_past_schedule("scheduled", SEEN, SEEN, _sources(FRESH)) is True

    def test_past_the_horizon_no_stamp_holds(self):
        old = SEEN - AUTHORITY_NOT_STARTED_HORIZON - timedelta(minutes=1)
        assert authority_not_started_past_schedule("scheduled", old, SEEN, _sources(FRESH)) is False

    @pytest.mark.parametrize("status", ["live", "completed", "closed", "suspended", None])
    def test_only_a_scheduled_row_is_asked(self, status):
        assert authority_not_started_past_schedule(status, LISTED, SEEN, _sources(FRESH)) is False

    @pytest.mark.parametrize(
        "bad", ["not-a-time", 12345, None, (SEEN + timedelta(minutes=1)).isoformat()]
    )
    def test_an_unreadable_stamp_is_no_statement(self, bad):
        assert authority_not_started_past_schedule(
            "scheduled", LISTED, SEEN, {ESPN_NOT_STARTED_KEY: bad}
        ) is False

    def test_no_sources_is_no_statement(self):
        assert authority_not_started_past_schedule("scheduled", LISTED, SEEN, None) is False

    def test_a_naive_start_fails_closed(self):
        assert authority_not_started_past_schedule(
            "scheduled", LISTED.replace(tzinfo=None), SEEN, _sources(FRESH)
        ) is False

    @pytest.mark.parametrize("missing", ["commence", "now"])
    def test_an_absent_clock_fails_closed(self, missing):
        commence = None if missing == "commence" else LISTED
        now = None if missing == "now" else SEEN
        assert authority_not_started_past_schedule("scheduled", commence, now, _sources(FRESH)) is False


class TestItAgreesWithTheNoResultHold:
    """Past the grace the #9195 hold flips `started_without_result` to false on the
    same stamp; the two keys must be one claim (key true ⇔ hold engaged)."""

    STAMPS = {
        "fresh": lambda now: (now - timedelta(seconds=40)).isoformat(),
        "stale": lambda now: (now - AUTHORITY_NOT_STARTED_TTL - timedelta(seconds=1)).isoformat(),
        "future": lambda now: (now + timedelta(minutes=1)).isoformat(),
        "absent": lambda now: None,
    }

    @pytest.mark.parametrize("stamp_name", list(STAMPS))
    @pytest.mark.parametrize(
        "past", [UPCOMING_GRACE + timedelta(minutes=1), timedelta(hours=5),
                 AUTHORITY_NOT_STARTED_HORIZON + timedelta(minutes=1)]
    )
    def test_past_the_grace(self, stamp_name, past):
        commence = SEEN - past
        sources = _sources(self.STAMPS[stamp_name](SEEN))
        held = (
            started_without_result("scheduled", commence, SEEN)
            and not started_without_result("scheduled", commence, SEEN, sources)
        )
        assert authority_not_started_past_schedule("scheduled", commence, SEEN, sources) == held


class TestTheServedPayload:
    """`_format_event` — the base of `/api/events/{id}`, `/api/events` and search."""

    @staticmethod
    def _event(minutes_past_listing, sources, status="scheduled"):
        now = datetime.now(UTC)
        return Event(
            id=15321907, sport_id=1, sport=Sport(id=1, key="baseball_mlb", name="MLB"),
            home_team_name="New York Yankees", away_team_name="Boston Red Sox",
            commence_time=now - timedelta(minutes=minutes_past_listing), status=status,
            home_score=None, away_score=None, win_probability_sources=sources,
        )

    @staticmethod
    def _fresh():
        return {ESPN_NOT_STARTED_KEY: (datetime.now(UTC) - timedelta(seconds=40)).isoformat()}

    def test_the_specimen_serves_it(self):
        from app.routes.events import _format_event

        data = _format_event(self._event(7, self._fresh()))
        assert data["authority_not_started"] is True
        assert data["status"] == "scheduled"
        assert data["started_without_result"] is False

    def test_control_no_stamp_the_key_is_absent(self):
        """What production served at 00:07:47Z: nothing between "scheduled" and the clock."""
        from app.routes.events import _format_event

        assert "authority_not_started" not in _format_event(self._event(7, {}))

    def test_a_game_under_way_never_carries_it(self):
        from app.routes.events import _format_event

        assert "authority_not_started" not in _format_event(self._event(20, self._fresh(), "live"))

    def test_a_fixture_still_ahead_never_carries_it(self):
        from app.routes.events import _format_event

        assert "authority_not_started" not in _format_event(self._event(-90, self._fresh()))
