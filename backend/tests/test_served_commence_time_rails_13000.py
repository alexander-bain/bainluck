"""#13000 — League and team upcoming rails serve StatPal's held start time, not the stale venue stamp.

Specimen (production, Wed Nov 18, 2026):
  Event 15349294 (Arribage / Olivetti vs Heliovaara / Patten, ``tennis_atp``)
  carried Kalshi's initial ``commence_time`` of Tue Nov 17 13:30 UTC alongside
  StatPal's later-session hold (``statpal_later_session_start``) of
  Thu Nov 19 17:00 UTC (#9613).

  - ``GET /api/events/15349294`` routed through ``served_commence_time`` (#9634)
    and served Thu Nov 19 17:00 UTC.
  - ``GET /api/leagues/tennis_atp`` admitted the match via
    ``upcoming_rail_condition`` -> ``statpal_later_session_rows``, then
    serialized raw ``event.commence_time`` (Tue Nov 17) and sorted it first
    ahead of tonight's matches.
  - ``routes/teams.py`` (the other caller of ``upcoming_rail_condition``) had
    the same omission.

This suite pins ``served_commence_time`` and chronological ordering on both
upcoming rails.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.league_futures import _format_game_brief, _order_upcoming_briefs
from app.routes.teams import _format_event_brief, _order_upcoming_team_briefs
from app.utils.event_completion import (
    STATPAL_LATER_SESSION_KEY,
    statpal_later_session_value,
)
from app.utils.proven_duplicates import FoldedBlendView

UTC = timezone.utc


def _tennis_event(*, stored_start: datetime, sources: dict | None, status: str = "scheduled", event_id: int = 15349294):
    sport = SimpleNamespace(id=1, key="tennis_atp", name="ATP")
    return SimpleNamespace(
        id=event_id,
        external_id=None,
        sport_id=1,
        sport=sport,
        home_team_id=10,
        away_team_id=20,
        home_team_name="Heliovaara / Patten",
        away_team_name="Arribage / Olivetti",
        commence_time=stored_start,
        completed_at=None,
        status=status,
        home_score=None,
        away_score=None,
        period=None,
        game_clock=None,
        broadcast_info=None,
        event_tags=None,
        opening_home_probability=None,
        opening_away_probability=None,
        espn_win_prob_home=None,
        win_probability_sources=sources,
    )


class TestLeagueRailServedCommenceTime:
    def test_held_match_serves_statpal_future_start(self):
        now = datetime.now(UTC).replace(microsecond=0)
        stale_venue_start = now - timedelta(hours=36)
        statpal_future_start = now + timedelta(hours=16)
        sources = {
            "kalshi": {"value": 0.58},
            STATPAL_LATER_SESSION_KEY: statpal_later_session_value(statpal_future_start),
        }
        ev = _tennis_event(stored_start=stale_venue_start, sources=sources)
        brief = _format_game_brief(ev, "tennis_atp", {})
        assert brief["status"] == "scheduled"
        assert datetime.fromisoformat(brief["commence_time"]) == statpal_future_start

    def test_folded_blend_view_also_serves_statpal_future_start(self):
        now = datetime.now(UTC).replace(microsecond=0)
        stale_venue_start = now - timedelta(hours=36)
        statpal_future_start = now + timedelta(hours=16)
        sources = {
            "kalshi": {"value": 0.58},
            STATPAL_LATER_SESSION_KEY: statpal_later_session_value(statpal_future_start),
        }
        ev = _tennis_event(stored_start=stale_venue_start, sources=sources)
        wrapped = FoldedBlendView(ev, dict(sources))
        brief = _format_game_brief(wrapped, "tennis_atp", {})
        assert datetime.fromisoformat(brief["commence_time"]) == statpal_future_start

    def test_unheld_and_non_scheduled_rows_keep_stored_start(self):
        now = datetime.now(UTC).replace(microsecond=0)
        stale = now - timedelta(hours=12)
        future = now + timedelta(hours=16)
        sources = {STATPAL_LATER_SESSION_KEY: statpal_later_session_value(future)}

        unheld = _tennis_event(stored_start=stale, sources={"kalshi": {"value": 0.58}})
        assert datetime.fromisoformat(_format_game_brief(unheld, "tennis_atp", {})["commence_time"]) == stale

        live = _tennis_event(stored_start=stale, sources=sources, status="live")
        assert datetime.fromisoformat(_format_game_brief(live, "tennis_atp", {})["commence_time"]) == stale

        completed = _tennis_event(stored_start=stale, sources=sources, status="completed")
        assert datetime.fromisoformat(_format_game_brief(completed, "tennis_atp", {})["commence_time"]) == stale


class TestTeamRailServedCommenceTime:
    def test_held_match_serves_statpal_future_start(self):
        now = datetime.now(UTC).replace(microsecond=0)
        stale_venue_start = now - timedelta(hours=36)
        statpal_future_start = now + timedelta(hours=16)
        sources = {
            "kalshi": {"value": 0.58},
            STATPAL_LATER_SESSION_KEY: statpal_later_session_value(statpal_future_start),
        }
        team = SimpleNamespace(id=10, name="Heliovaara / Patten")
        ev = _tennis_event(stored_start=stale_venue_start, sources=sources)
        brief = _format_event_brief(ev, team)
        assert brief["status"] == "scheduled"
        assert datetime.fromisoformat(brief["commence_time"]) == statpal_future_start


class TestUpcomingRailOrdering:
    @pytest.mark.parametrize("order_fn", [_order_upcoming_briefs, _order_upcoming_team_briefs])
    def test_live_order_preserved_and_held_match_sorted_into_future_slot(self, order_fn):
        # Input order mimics SQL ORDER BY live_first_order(now), Event.commence_time ASC:
        # two live cards in SQL order, then the held match first (because its raw DB
        # commence_time was yesterday), followed by tonight's and tomorrow's matches.
        cards = [
            {"id": 1, "status": "live", "commence_time": "2026-09-15T20:00:00+00:00"},
            {"id": 2, "status": "live", "commence_time": "2026-09-15T19:00:00+00:00"},
            {"id": 15349294, "status": "scheduled", "commence_time": "2026-09-17T17:00:00+00:00"},
            {"id": 3, "status": "scheduled", "commence_time": "2026-09-16T01:30:00+00:00"},
            {"id": 4, "status": "scheduled", "commence_time": "2026-09-17T13:00:00+00:00"},
            {"id": 5, "status": "scheduled", "commence_time": "2026-09-17T19:30:00+00:00"},
        ]
        ordered = order_fn(cards)
        # Live rows keep their exact SQL order (1 before 2); held match lands between 4 (13:00) and 5 (19:30).
        assert [c["id"] for c in ordered] == [1, 2, 3, 4, 15349294, 5]
