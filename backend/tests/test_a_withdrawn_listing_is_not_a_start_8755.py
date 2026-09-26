"""A start the only source has withdrawn does not make a game LIVE (#8755).

PILLAR: TRUTH.  SHIP: a playoff game that hasn't started stops showing as LIVE
under a two-day-old price.

## The specimen, production 2026-09-26

``/events/15318133`` Liberty @ Lynx read **LIVE** from 00:30Z 9/26 with no score
and no clock, over a FanDuel line captured at 02:19-02:36Z on **9/24**. ESPN has
the game on Sunday 9/27 18:00Z (we hold it correctly as 15318132). The row's only
source was the Odds API (``commence_time_source='odds_api'``, no ``espn_id``, no
StatPal id), and the Odds API stopped listing its id at 02:36Z 9/24 while it went
on listing every other WNBA game. ``transition_event_statuses`` promoted it at
its made-up start anyway, because an odds_api start counts as a reported one.

The extra row itself is lane1's half (PR #8771, a duplicate-of label). This file
guards the class: a row nothing but a withdrawn listing speaks for does not go
LIVE on the clock.

The SQL that produces the two sightings is exercised against real Postgres in
``tests/integration/test_a_withdrawn_listing_is_not_a_start_pg_8755.py``; here
the predicate and the loop are driven with the sightings handed in.
"""

from __future__ import annotations

import contextlib
import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.utils.event_completion import (
    ODDS_API_COMMENCE_SOURCE,
    WITHDRAWN_LISTING_GAP,
    odds_api_listing_withdrawn,
)

NOW = datetime(2026, 9, 26, 0, 31, tzinfo=timezone.utc)
#: The specimen's own last sighting and the sport's, as production held them.
ROW_LAST_SEEN = datetime(2026, 9, 24, 2, 36, 13, tzinfo=timezone.utc)
SPORT_LAST_SEEN = datetime(2026, 9, 26, 0, 25, tzinfo=timezone.utc)


def _withdrawn(**overrides):
    args = dict(
        commence_time_source=ODDS_API_COMMENCE_SOURCE,
        espn_id=None,
        statpal_fixture_id=None,
        has_play_evidence=False,
        listing_last_seen=ROW_LAST_SEEN,
        sport_last_seen=SPORT_LAST_SEEN,
    )
    args.update(overrides)
    return odds_api_listing_withdrawn(**args)


class TestThePredicate:
    def test_the_specimen_is_a_withdrawn_listing(self):
        assert _withdrawn() is True

    def test_the_boundary_is_the_gap_itself(self):
        """Exactly the gap holds; a second under it does not. Pinned on the
        constant so a retune moves this file instead of silently passing."""
        seen = SPORT_LAST_SEEN - WITHDRAWN_LISTING_GAP
        assert _withdrawn(listing_last_seen=seen) is True
        assert _withdrawn(listing_last_seen=seen + timedelta(seconds=1)) is False

    def test_a_row_the_feed_still_lists_is_not_withdrawn(self):
        assert _withdrawn(listing_last_seen=SPORT_LAST_SEEN - timedelta(minutes=5)) is False

    @pytest.mark.parametrize(
        "source", ["espn", "statpal", "kalshi_occurrence", "polymarket_venue", None]
    )
    def test_only_the_odds_api_provenance_is_read(self, source):
        """The sightings are Odds API sightings; they say nothing about a start
        another source reported."""
        assert _withdrawn(commence_time_source=source) is False

    @pytest.mark.parametrize(
        "ids", [{"espn_id": "401918014"}, {"statpal_fixture_id": "88123"}]
    )
    def test_an_authority_id_fails_open(self, ids):
        """An anchored row's state belongs to the authority's own passes."""
        assert _withdrawn(**ids) is False

    def test_an_empty_string_id_is_not_an_anchor(self):
        assert _withdrawn(espn_id="", statpal_fixture_id="  ") is True

    def test_play_evidence_fails_open(self):
        assert _withdrawn(has_play_evidence=True) is False

    def test_no_sighting_of_the_row_fails_open(self):
        """Rows born from the scores path carry no odds and do get results."""
        assert _withdrawn(listing_last_seen=None) is False

    def test_no_pregame_sighting_of_the_sport_fails_open(self):
        """An unpolled sport (quota FULL_STOP / LIVE_ONLY) says nothing about
        this row."""
        assert _withdrawn(sport_last_seen=None) is False


# ---------------------------------------------------------------------------
# The loop. Same fake-session shape as test_a_derived_start_is_not_a_start_q076,
# extended to answer the sightings read with rows this file chooses.
# ---------------------------------------------------------------------------


class _Row:
    def __init__(self, id, *, source=ODDS_API_COMMENCE_SOURCE, espn_id=None):
        self.id = id
        self.status = "scheduled"
        self.commence_time = NOW - timedelta(minutes=1)
        self.commence_time_source = source
        self.completed_at = None
        self.home_score = None
        self.away_score = None
        self.period = None
        self.game_clock = None
        self.espn_id = espn_id
        self.statpal_fixture_id = None
        self.win_probability_sources = {}
        self.home_team_name = "Minnesota Lynx"
        self.away_team_name = "New York Liberty"
        self.sport = type("S", (), {"key": "basketball_wnba"})()


class _Sighting:
    def __init__(self, event_id, row_seen, sport_seen):
        self.listing_event_id = event_id
        self.listing_last_seen = row_seen
        self.sport_last_seen = sport_seen


class _NetSession:
    def __init__(self, scheduled, sightings):
        self._selects = [scheduled, [], [], [], [], []]
        self._sightings = sightings
        self.sighting_params = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "AS listing_last_seen" in sql:
            self.sighting_params.append(params)
            asked = set(params["event_ids"])
            rows = [s for s in self._sightings if s.listing_event_id in asked]
            return type("R", (), {"all": lambda _s: rows})()
        if "AS winner_source" in sql or "GROUP BY x.event_id" in sql:
            return type("R", (), {"all": lambda _s: []})()
        if sql.startswith("UPDATE"):
            return None
        rows = self._selects.pop(0)
        return type(
            "R", (), {"scalars": lambda _s: type("S", (), {"all": lambda _x: rows})()}
        )()

    async def commit(self):
        pass


async def _run_net(scheduled, sightings=()):
    session = _NetSession(scheduled, list(sightings))

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.espn_sync as mod

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    with patch("app.tasks.base.get_task_session", _fake_session), patch.object(
        mod, "datetime", _FrozenNow
    ):
        stats = await mod._transition_event_statuses_impl()
    return stats, session


class TestTheLoop:
    @pytest.mark.asyncio
    async def test_the_specimen_is_held_scheduled(self):
        row = _Row(15318133)
        stats, _ = await _run_net(
            [row], [_Sighting(15318133, ROW_LAST_SEEN, SPORT_LAST_SEEN)]
        )
        assert row.status == "scheduled"
        assert stats["held_withdrawn_listing"] == 1
        assert stats["scheduled_to_live"] == 0

    @pytest.mark.asyncio
    async def test_a_listed_sibling_promotes_in_the_same_pass(self):
        """The regression arm, in one run with the held row (gotcha #42): a
        fix that stopped promoting odds_api rows at all fails here."""
        held, listed = _Row(15318133), _Row(15318134)
        stats, _ = await _run_net(
            [held, listed],
            [
                _Sighting(15318133, ROW_LAST_SEEN, SPORT_LAST_SEEN),
                _Sighting(15318134, NOW - timedelta(minutes=3), None),
            ],
        )
        assert (held.status, listed.status) == ("scheduled", "live")
        assert (stats["held_withdrawn_listing"], stats["scheduled_to_live"]) == (1, 1)

    @pytest.mark.asyncio
    async def test_a_relisted_row_promotes_on_the_next_pass(self):
        """The hold ends on evidence: the Odds API listing the id again."""
        row = _Row(15318133)
        await _run_net([row], [_Sighting(15318133, ROW_LAST_SEEN, SPORT_LAST_SEEN)])
        assert row.status == "scheduled"
        stats, _ = await _run_net(
            [row], [_Sighting(15318133, NOW - timedelta(minutes=2), None)]
        )
        assert row.status == "live"
        assert stats["held_withdrawn_listing"] == 0

    @pytest.mark.asyncio
    async def test_an_anchored_row_is_never_asked_about(self):
        """An espn_id row does not enter the read at all, and a pass with no
        candidate issues no read — a listed night costs nothing."""
        anchored = _Row(15318132, espn_id="401918014")
        stats, session = await _run_net(
            [anchored], [_Sighting(15318132, ROW_LAST_SEEN, SPORT_LAST_SEEN)]
        )
        assert anchored.status == "live"
        assert session.sighting_params == []
        assert stats["held_withdrawn_listing"] == 0

    @pytest.mark.asyncio
    async def test_the_read_is_bounded_by_the_gap(self):
        row = _Row(15318133)
        _, session = await _run_net([row])
        (params,) = session.sighting_params
        assert params["event_ids"] == [15318133]
        assert params["stale_before"] == NOW - WITHDRAWN_LISTING_GAP

    @pytest.mark.asyncio
    async def test_a_row_the_read_did_not_return_promotes(self):
        row = _Row(15318133)
        stats, _ = await _run_net([row], [])
        assert row.status == "live"
        assert stats["held_withdrawn_listing"] == 0

    def test_the_hold_is_in_the_log_trigger(self):
        from app.tasks.espn_sync import _transition_event_statuses_impl

        src = inspect.getsource(_transition_event_statuses_impl)
        trigger = src[src.index('if (stats["scheduled_to_live"] > 0') :]
        trigger = trigger[: trigger.index("logger.info")]
        assert 'stats["held_withdrawn_listing"] > 0' in trigger
