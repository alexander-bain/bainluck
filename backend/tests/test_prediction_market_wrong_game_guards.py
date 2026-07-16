"""Guard tests for the #210 write-path wrong-game matching pack.

One guard per gap that Queue #210 Item 1 closed against the hot matching path
(`app/tasks/prediction_market_matching.py`):

  (a) `_find_event_by_sport_and_time` single-candidate branch now team-gates.
  (b) `_check_duplicate_kalshi_linkage` guards esports map/game tickers, not
      just `…game`-suffixed ones (via `_is_game_winner_kalshi_prefix`).
  (c) Phase 1.5 re-link + the historical backfill both route through the
      duplicate-linkage guard (regression guard on the source).
  (d) The Phase-2 date-mismatch unlink uses a shared HHMM-aware threshold
      (`_ticker_date_far_from_event`) and runs over all linked markets.
  (e) `WRONG_GAME_PREFIXES` covers NCAAMB / college basketball + esports.
"""

import inspect
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks.prediction_market_matching import (
    _is_game_winner_kalshi_prefix,
    _ticker_date_far_from_event,
    _check_duplicate_kalshi_linkage,
    _find_event_by_sport_and_time,
    _phase15_revalidate,
    _backfill_historical_links,
    WRONG_GAME_PREFIXES,
)


# ── Gap (b): the game-level prefix predicate ────────────────────────────────
class TestIsGameWinnerKalshiPrefix:
    def test_traditional_game_prefix(self):
        assert _is_game_winner_kalshi_prefix("kxnbagame") is True

    def test_esports_game_prefix(self):
        assert _is_game_winner_kalshi_prefix("kxcs2game") is True
        assert _is_game_winner_kalshi_prefix("kxlolgame") is True

    def test_esports_map_prefix_now_guarded(self):
        # The old endswith("game") gate silently exempted every map ticker.
        assert _is_game_winner_kalshi_prefix("kxcs2map") is True
        assert _is_game_winner_kalshi_prefix("kxlolmap") is True
        assert _is_game_winner_kalshi_prefix("kxvalorantmap") is True

    def test_esports_mapwinner_prefix_guarded(self):
        assert _is_game_winner_kalshi_prefix("kxcs2mapwinner") is True

    def test_totalmaps_prop_not_guarded(self):
        # Plural "…maps" is an over/under prop, not a per-map winner.
        assert _is_game_winner_kalshi_prefix("kxcs2totalmaps") is False
        assert _is_game_winner_kalshi_prefix("kxloltotalmaps") is False

    def test_props_not_guarded(self):
        assert _is_game_winner_kalshi_prefix("kxnbaspread") is False
        assert _is_game_winner_kalshi_prefix("kxnbatotal") is False
        assert _is_game_winner_kalshi_prefix("kxnbamention") is False


# ── Gap (b): the duplicate-linkage guard now catches esports maps ───────────
class TestDuplicateLinkageEsports:
    def _existing_row(self, external_id, mid=999):
        return SimpleNamespace(id=mid, external_id=external_id, name="existing")

    def _session_with_existing(self, rows):
        session = AsyncMock()
        result = MagicMock()
        result.all.return_value = rows
        session.execute.return_value = result
        return session

    @pytest.mark.asyncio
    async def test_esports_map_wrong_date_blocked(self):
        # A CS2 map ticker for a 07-15 match must NOT link to an event that
        # already holds a CS2 game ticker for a DIFFERENT day (07-10).
        # Before #210 the "kxcs2map" prefix escaped the endswith("game") gate.
        session = self._session_with_existing(
            [self._existing_row("KXCS2GAME-25JUL10FNCVIT")]
        )
        market = SimpleNamespace(
            id=1, source="kalshi", external_id="KXCS2MAP-25JUL15FNCVIT",
        )
        ok = await _check_duplicate_kalshi_linkage(
            session, event_id=42, market=market,
            ticker_game_date=datetime(2025, 7, 15, tzinfo=timezone.utc),
        )
        assert ok is False  # blocked

    @pytest.mark.asyncio
    async def test_esports_map_same_date_allowed(self):
        # Same-day maps of the same series are legitimate — allow.
        session = self._session_with_existing(
            [self._existing_row("KXCS2GAME-25JUL15FNCVIT")]
        )
        market = SimpleNamespace(
            id=1, source="kalshi", external_id="KXCS2MAP-25JUL15FNCVIT",
        )
        ok = await _check_duplicate_kalshi_linkage(
            session, event_id=42, market=market,
            ticker_game_date=datetime(2025, 7, 15, tzinfo=timezone.utc),
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_non_kalshi_short_circuits(self):
        session = self._session_with_existing([])
        market = SimpleNamespace(id=1, source="polymarket", external_id="abc")
        ok = await _check_duplicate_kalshi_linkage(
            session, event_id=42, market=market, ticker_game_date=None,
        )
        assert ok is True
        session.execute.assert_not_called()


# ── Gap (a): single-candidate team gate ─────────────────────────────────────
class TestSportTimeFallbackTeamGate:
    def _session_returning(self, events):
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = events
        session.execute.return_value = result
        return session

    def _market(self):
        return SimpleNamespace(
            external_id="KXNCAABGAME-26FEB21STACAL",
            name="Professional Basketball Game",
            commence_time=datetime(2026, 2, 21, tzinfo=timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_single_candidate_wrong_teams_rejected(self):
        # Ticker fragments STA/CAL match NEITHER of the lone candidate's teams.
        wrong_event = SimpleNamespace(
            id=7, sport_id=3,
            home_team_name="Duke Blue Devils",
            away_team_name="North Carolina Tar Heels",
        )
        session = self._session_returning([wrong_event])
        out = await _find_event_by_sport_and_time(
            session, self._market(), datetime.now(timezone.utc),
            game_date_override=datetime(2026, 2, 21, tzinfo=timezone.utc),
        )
        assert out is None  # wrong-game gate fires

    @pytest.mark.asyncio
    async def test_single_candidate_right_teams_linked(self):
        right_event = SimpleNamespace(
            id=9, sport_id=3,
            home_team_name="Stanford Cardinal",
            away_team_name="California Golden Bears",
        )
        session = self._session_returning([right_event])
        out = await _find_event_by_sport_and_time(
            session, self._market(), datetime.now(timezone.utc),
            game_date_override=datetime(2026, 2, 21, tzinfo=timezone.utc),
        )
        assert out is not None
        assert out["event_id"] == 9


# ── Gap (c): both bypass paths now route through the guard ───────────────────
class TestDuplicateGuardRoutedFromBypassPaths:
    def test_phase15_calls_duplicate_guard(self):
        src = inspect.getsource(_phase15_revalidate)
        assert "_check_duplicate_kalshi_linkage" in src

    def test_backfill_calls_duplicate_guard(self):
        src = inspect.getsource(_backfill_historical_links)
        assert "_check_duplicate_kalshi_linkage" in src


# ── Gap (d): the shared HHMM-aware date threshold ───────────────────────────
class TestTickerDateFarFromEvent:
    def test_date_only_within_window(self):
        base = datetime(2026, 2, 21, tzinfo=timezone.utc)
        assert _ticker_date_far_from_event(base, base) is False

    def test_date_only_next_day_is_far(self):
        base = datetime(2026, 2, 21, tzinfo=timezone.utc)
        assert _ticker_date_far_from_event(base + timedelta(hours=24), base) is True

    def test_hhmm_doubleheader_is_far(self):
        # With a start time, the tight ±3h window separates ~5h-apart games.
        ec = datetime(2026, 2, 21, 18, 0, tzinfo=timezone.utc)
        td = datetime(2026, 2, 21, 23, 30, tzinfo=timezone.utc)  # 5.5h later, HHMM
        assert _ticker_date_far_from_event(td, ec) is True

    def test_hhmm_same_game_not_far(self):
        ec = datetime(2026, 2, 21, 18, 0, tzinfo=timezone.utc)
        td = datetime(2026, 2, 21, 19, 30, tzinfo=timezone.utc)  # 1.5h, within ±3h
        assert _ticker_date_far_from_event(td, ec) is False

    def test_missing_inputs_never_far(self):
        base = datetime(2026, 2, 21, tzinfo=timezone.utc)
        assert _ticker_date_far_from_event(None, base) is False
        assert _ticker_date_far_from_event(base, None) is False

    def test_naive_datetimes_handled(self):
        base = datetime(2026, 2, 21)  # naive
        assert _ticker_date_far_from_event(base, base) is False


# ── Gap (e): the wrong-game prefix allowlist covers NCAAMB + esports ────────
class TestWrongGamePrefixSet:
    def test_ncaamb_included(self):
        assert "kxncaambgame" in WRONG_GAME_PREFIXES

    def test_college_basketball_siblings_included(self):
        assert {"kxncaabbgame", "kxncaabgame", "kxncaawbgame"} <= WRONG_GAME_PREFIXES

    def test_esports_included(self):
        assert {"kxcs2game", "kxcs2map", "kxlolgame", "kxvalorantmap"} <= WRONG_GAME_PREFIXES

    def test_traditional_still_included(self):
        assert {"kxnbagame", "kxmlbgame", "kxnflgame", "kxnhlgame"} <= WRONG_GAME_PREFIXES

    def test_props_and_combat_excluded(self):
        # Props share the game's date; combat is fighter-disambiguated — never
        # date-unlink these.
        for p in ("kxnbaspread", "kxcs2totalmaps", "kxufcfight", "kxboxingfight"):
            assert p not in WRONG_GAME_PREFIXES
