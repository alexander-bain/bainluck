"""A venue stamp does not make a match LIVE a day before it is played (#9588).

PILLAR: TRUTH.  SHIP: a China Open doubles match that is played tomorrow stops
reading LIVE today.

## The specimen, production 2026-09-29 09:22Z

``/events/15320754`` Bublik / Shang v Cerundolo / Rinderknech read **LIVE**, no
score, flat Kalshi line, from 05:00Z 9/29. That instant is Kalshi's
``expected_expiration_time`` (``commence_time_source='kalshi'``). The row is
anchored to StatPal ``tennis:2638141``, whose recorded start is 02:00Z 9/30,
the next day's Beijing session. ESPN has it at 05:30Z 9/30. Six sibling rows
had the same shape.

``transition_event_statuses`` promoted all seven on the clock. This file guards
the class. A venue-stamped row whose own StatPal anchor names a materially
later session is held ``scheduled`` until that session, and a row already
promoted goes back.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.utils.event_completion import (
    STATPAL_LATER_SESSION_MARGIN,
    VENUE_STAMP_COMMENCE_SOURCES,
    statpal_names_a_later_session,
    statpal_start_from_anchors,
)

NOW = datetime(2026, 9, 29, 9, 22, tzinfo=timezone.utc)
KALSHI_STAMP = datetime(2026, 9, 29, 5, 0, tzinfo=timezone.utc)
STATPAL_START = datetime(2026, 9, 30, 2, 0, tzinfo=timezone.utc)
FIXTURE = "2638141"


def _later(**overrides):
    args = dict(
        commence_time_source="kalshi",
        statpal_fixture_id=FIXTURE,
        has_play_evidence=False,
        commence_time=KALSHI_STAMP,
        statpal_start=STATPAL_START,
        now=NOW,
    )
    args.update(overrides)
    return statpal_names_a_later_session(**args)


class TestThePredicate:
    def test_the_specimen_is_a_later_session(self):
        assert _later() is True

    @pytest.mark.parametrize("source", sorted(VENUE_STAMP_COMMENCE_SOURCES))
    def test_every_venue_stamp_is_read(self, source):
        assert _later(commence_time_source=source) is True

    def test_the_venue_stamp_set_is_pinned(self):
        """A widening is a new population, measured before it lands."""
        assert VENUE_STAMP_COMMENCE_SOURCES == {
            "kalshi",
            "kalshi_occurrence",
            "polymarket",
        }

    @pytest.mark.parametrize(
        "source",
        ["polymarket_venue", "odds_api", "espn", "statpal", "kalshi_ticker", None],
    )
    def test_a_reported_start_is_not_overruled(self, source):
        """odds_api is the census's counterexample: two Guadalajara singles
        were played a day BEFORE StatPal's stamp. A reported start stands."""
        assert _later(commence_time_source=source) is False

    @pytest.mark.parametrize("fixture", [None, "", "   "])
    def test_no_statpal_fixture_fails_open(self, fixture):
        assert _later(statpal_fixture_id=fixture) is False

    def test_play_evidence_fails_open(self):
        assert _later(has_play_evidence=True) is False

    def test_no_recorded_start_fails_open(self):
        assert _later(statpal_start=None) is False

    def test_the_margin_is_a_strict_disagreement(self):
        """Exactly the margin is one session read twice; a second more is a
        disagreement. Pinned on the constant."""
        at = KALSHI_STAMP + STATPAL_LATER_SESSION_MARGIN
        assert _later(statpal_start=at, now=KALSHI_STAMP) is False
        assert _later(
            statpal_start=at + timedelta(seconds=1), now=KALSHI_STAMP
        ) is True

    def test_the_hold_ends_at_statpals_start(self):
        assert _later(now=STATPAL_START - timedelta(seconds=1)) is True
        assert _later(now=STATPAL_START) is False


def _anchor(source_id, start, seen):
    return SimpleNamespace(
        source_id=source_id, statpal_start_time=start, first_seen_at=seen
    )


class TestTheAnchorRead:
    SEEN = datetime(2026, 9, 28, 10, 54, tzinfo=timezone.utc)

    def test_the_rows_own_fixture_answers(self):
        rows = [_anchor(f"tennis:{FIXTURE}", "2026-09-30T02:00:00+00:00", self.SEEN)]
        assert statpal_start_from_anchors(rows, FIXTURE) == STATPAL_START

    def test_an_anchor_for_another_fixture_says_nothing(self):
        rows = [_anchor("tennis:999", "2026-09-30T02:00:00+00:00", self.SEEN)]
        assert statpal_start_from_anchors(rows, FIXTURE) is None

    def test_the_newest_anchor_wins(self):
        rows = [
            _anchor(f"tennis:{FIXTURE}", "2026-09-30T02:00:00+00:00", self.SEEN),
            _anchor(
                f"tennis:{FIXTURE}",
                "2026-10-01T02:00:00+00:00",
                self.SEEN + timedelta(hours=1),
            ),
        ]
        assert statpal_start_from_anchors(rows, FIXTURE) == STATPAL_START + timedelta(
            days=1
        )

    def test_an_unparseable_start_is_no_start(self):
        rows = [_anchor(f"tennis:{FIXTURE}", "TBA", self.SEEN)]
        assert statpal_start_from_anchors(rows, FIXTURE) is None

    def test_a_naive_start_is_utc(self):
        rows = [_anchor(f"tennis:{FIXTURE}", "2026-09-30T02:00:00", self.SEEN)]
        assert statpal_start_from_anchors(rows, FIXTURE) == STATPAL_START


# ---------------------------------------------------------------------------
# The loop. Same fake-session shape as test_a_withdrawn_listing_is_not_a_start_8755,
# answering the anchor read with rows this file chooses.
# ---------------------------------------------------------------------------


class _Row:
    def __init__(self, id, *, status="scheduled", source="kalshi", fixture=FIXTURE):
        self.id = id
        self.status = status
        self.commence_time = KALSHI_STAMP
        self.commence_time_source = source
        self.completed_at = None
        self.home_score = None
        self.away_score = None
        self.period = None
        self.game_clock = None
        self.espn_id = None
        self.statpal_fixture_id = fixture
        self.win_probability_sources = {}
        self.home_team_name = "Bublik / Shang"
        self.away_team_name = "Cerundolo / Rinderknech"
        self.sport = type("S", (), {"key": "tennis_atp"})()


class _NetSession:
    def __init__(self, scheduled, live, anchors):
        self._selects = [scheduled, live, [], [], [], []]
        self._anchors = anchors
        self.anchor_reads = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "AS statpal_start_time" in sql:
            self.anchor_reads.append(sorted(params["event_ids"]))
            asked = set(params["event_ids"])
            rows = [a for a in self._anchors if a.event_id in asked]
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


def _anchor_for(event_id, fixture=FIXTURE, start="2026-09-30T02:00:00+00:00"):
    return SimpleNamespace(
        event_id=event_id,
        source_id=f"tennis:{fixture}",
        first_seen_at=datetime(2026, 9, 28, 10, 54, tzinfo=timezone.utc),
        statpal_start_time=start,
    )


async def _run_net(scheduled=(), live=(), anchors=()):
    session = _NetSession(list(scheduled), list(live), list(anchors))

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
    async def test_the_specimen_is_held_and_a_sibling_promotes(self):
        """Both arms in one run (gotcha #42): a fix that stopped promoting
        Kalshi-stamped rows at all fails on the sibling."""
        held = _Row(15320754)
        sibling = _Row(15320999, fixture=None)
        stats, session = await _run_net(
            scheduled=[held, sibling], anchors=[_anchor_for(15320754)]
        )
        assert held.status == "scheduled"
        assert sibling.status == "live"
        assert stats["held_statpal_later_session"] == 1
        assert stats["scheduled_to_live"] == 1
        assert session.anchor_reads == [[15320754]]

    @pytest.mark.asyncio
    async def test_a_session_already_reached_promotes(self):
        row = _Row(15320754)
        stats, _ = await _run_net(
            scheduled=[row],
            anchors=[_anchor_for(15320754, start="2026-09-29T09:00:00+00:00")],
        )
        assert row.status == "live"
        assert stats["held_statpal_later_session"] == 0

    @pytest.mark.asyncio
    async def test_a_promoted_row_goes_back_to_scheduled(self):
        row = _Row(15320754, status="live")
        stats, _ = await _run_net(live=[row], anchors=[_anchor_for(15320754)])
        assert row.status == "scheduled"
        assert stats["demoted_statpal_later_session"] == 1
        assert stats["live_to_suspended"] == 0

    @pytest.mark.asyncio
    async def test_a_live_row_with_play_is_never_demoted(self):
        row = _Row(15320754, status="live")
        row.home_score, row.away_score = 1, 0
        _, session = await _run_net(live=[row], anchors=[_anchor_for(15320754)])
        assert row.status != "scheduled"
        assert session.anchor_reads == []

    @pytest.mark.asyncio
    async def test_no_candidate_costs_no_query(self):
        rows = [_Row(1, source="odds_api"), _Row(2, fixture=None)]
        _, session = await _run_net(scheduled=rows)
        assert session.anchor_reads == []
        assert all(r.status == "live" for r in rows)
