"""Tests for Ruling 242: A + Ruling 265: A, for now (#13007).

Verifies every protection listed on #13007 and Ruling 265: A:
1. Pregame: plain average of clean spreads and clean totals (sportsbooks + clean ladders).
2. Same-line contradiction excluded (not down-weighted).
3. Re-crossing pool excluded (not down-weighted; Texans-Bills / Browns-Jaguars class).
4. Below-bar bracket confidence excluded (not down-weighted).
5. Single clean source stands alone identically to today.
6. No clean source falls back to today's ranked pick (`select_projected_final`).
7. Renderability guard (`projection_is_renderable`) stays on the blended result.
8. Live games (Ruling 265: A, for now): sportsbooks ONLY with Ruling 233: A
   (`live_line_is_current`) applied — prediction-market ladders are never blended
   or used as live fallback; when no book line is current (including when a stale
   pre-cutoff snapshot produces a synthetic `now` point in `history[-1]`), the
   projected final is withheld (`None`).
9. Pinned-handicap sports (NHL ±1.5 puck line, MLB ±1.5 run line, non-margin sports)
   exclude the sportsbook spread from blending and live projection.
10. Source attribution (`spread_sources`, `total_sources`) while keeping legacy
    `spread_source` and `total_source` readable.
11. Feature switch `PROJECTED_FINAL_BLEND_ENABLED` defaults strictly to OFF.
"""

from datetime import datetime, timedelta, timezone

from app.utils.binary_spread import (
    CLEAN_PROJECTION_MIN_CONFIDENCE,
    PROJECTED_FINAL_BLEND_ENV,
    binary_to_implied_spread,
    binary_to_implied_total,
    blend_projected_final,
    projected_final_blend_enabled,
    select_projected_final,
    source_is_clean_for_projection,
)


def test_switch_defaults_strictly_to_off(monkeypatch):
    monkeypatch.delenv(PROJECTED_FINAL_BLEND_ENV, raising=False)
    assert projected_final_blend_enabled() is False

    monkeypatch.setenv(PROJECTED_FINAL_BLEND_ENV, "false")
    assert projected_final_blend_enabled() is False

    monkeypatch.setenv(PROJECTED_FINAL_BLEND_ENV, "true")
    assert projected_final_blend_enabled() is True


def test_plain_average_across_all_clean_sources_and_source_attribution():
    spreads = {
        "sportsbook": {"spread": -2.0, "confidence": 1.0, "contracts": []},
        "kalshi": {"spread": -4.0, "confidence": 0.90, "contracts": []},
        "polymarket": {"spread": -3.0, "confidence": 0.85, "contracts": []},
    }
    totals = {
        "sportsbook": {"total": 230.0, "confidence": 1.0, "contracts": []},
        "kalshi": {"total": 228.0, "confidence": 0.80, "contracts": []},
        "polymarket": {"total": 226.0, "confidence": 0.90, "contracts": []},
    }
    res = blend_projected_final(spreads, totals)
    assert res is not None
    # Mean spread = (-2 - 4 - 3) / 3 = -3.0; mean total = (230 + 228 + 226) / 3 = 228.0
    assert res.projection.spread == -3.0
    assert res.projection.total == 228.0
    assert res.projection.home_score == 115.5
    assert res.projection.away_score == 112.5
    assert res.spread_source == "blend"
    assert res.total_source == "blend"
    assert res.spread_sources == ("sportsbook", "kalshi", "polymarket")
    assert res.total_sources == ("sportsbook", "kalshi", "polymarket")


def test_single_clean_source_stands_alone_identically_to_today():
    spreads = {"sportsbook": {"spread": -3.5, "confidence": 1.0, "contracts": []}}
    totals = {"sportsbook": {"total": 45.0, "confidence": 1.0, "contracts": []}}

    blended = blend_projected_final(spreads, totals)
    today = select_projected_final(spreads, totals)
    assert blended is not None and today is not None
    assert blended.projection.home_score == today[2].home_score
    assert blended.projection.away_score == today[2].away_score
    assert blended.spread_source == "sportsbook"
    assert blended.total_source == "sportsbook"
    assert blended.spread_sources == ("sportsbook",)
    assert blended.total_sources == ("sportsbook",)


def test_same_line_contradiction_ladder_is_excluded_not_downweighted():
    contradictory = binary_to_implied_total(
        [
            {"threshold": 40.5, "probability": 0.65},
            {"threshold": 40.5, "probability": 0.35},
        ]
    )
    assert contradictory is not None
    assert contradictory.same_line_contradiction is True

    spreads = {"sportsbook": {"spread": -3.0, "confidence": 1.0, "contracts": []}}
    totals = {
        "sportsbook": {"total": 47.0, "confidence": 1.0, "contracts": []},
        "polymarket": {
            "total": contradictory.total,
            "confidence": contradictory.confidence,
            "pool_recrosses": contradictory.pool_recrosses,
            "same_line_contradiction": contradictory.same_line_contradiction,
            "contracts": [
                {"threshold": 40.5, "probability": 0.65},
                {"threshold": 40.5, "probability": 0.35},
            ],
        },
    }
    res = blend_projected_final(spreads, totals)
    assert res is not None
    assert res.projection.total == 47.0
    assert res.total_source == "sportsbook"
    assert res.total_sources == ("sportsbook",)


def test_recrossing_pool_is_excluded_not_downweighted():
    # Two families pooled onto one event (Texans-Bills 7-9 / Browns-Jaguars 12-4 class)
    recross_contracts = [
        {"threshold": 15.5, "probability": 0.60},
        {"threshold": 16.5, "probability": 0.40},
        {"threshold": 44.5, "probability": 0.58},
        {"threshold": 45.5, "probability": 0.42},
    ]
    recross = binary_to_implied_total(recross_contracts)
    assert recross is not None
    assert recross.pool_recrosses is True

    spreads = {"sportsbook": {"spread": -2.0, "confidence": 1.0, "contracts": []}}
    totals = {
        "sportsbook": {"total": 44.0, "confidence": 1.0, "contracts": []},
        "kalshi": {
            "total": recross.total,
            "confidence": recross.confidence,
            "pool_recrosses": recross.pool_recrosses,
            "same_line_contradiction": recross.same_line_contradiction,
            "contracts": recross_contracts,
        },
    }
    res = blend_projected_final(spreads, totals)
    assert res is not None
    assert res.projection.total == 44.0
    assert res.total_sources == ("sportsbook",)


def test_below_confidence_bar_ladder_is_excluded_not_downweighted():
    below_bar = round(CLEAN_PROJECTION_MIN_CONFIDENCE - 0.15, 2)
    spreads = {"sportsbook": {"spread": -4.0, "confidence": 1.0, "contracts": []}}
    totals = {
        "sportsbook": {"total": 76.0, "confidence": 1.0, "contracts": []},
        "polymarket": {"total": 67.0, "confidence": below_bar, "contracts": []},
    }
    assert (
        source_is_clean_for_projection("polymarket", totals["polymarket"])
        is False
    )
    res = blend_projected_final(spreads, totals)
    assert res is not None
    assert res.projection.total == 76.0
    assert res.total_source == "sportsbook"
    assert res.total_sources == ("sportsbook",)


def test_no_clean_source_falls_back_to_todays_ranked_pick():
    # Only two demoted/low-confidence ladders, no sportsbook
    spreads = {
        "polymarket": {"spread": -6.0, "confidence": 0.2, "pool_recrosses": True},
        "kalshi": {"spread": -4.0, "confidence": 0.45, "pool_recrosses": False},
    }
    totals = {
        "polymarket": {"total": 140.0, "confidence": 0.40},
        "kalshi": {"total": 144.0, "confidence": 0.30, "same_line_contradiction": True},
    }
    today = select_projected_final(spreads, totals)
    blended = blend_projected_final(spreads, totals)
    assert today is not None and blended is not None
    assert blended.spread_source == today[0]
    assert blended.total_source == today[1]
    assert blended.projection.home_score == today[2].home_score
    assert blended.projection.away_score == today[2].away_score


def test_renderability_guard_rejects_negative_blended_scoreline_and_falls_back():
    # Sportsbook + clean ladder whose average spread exceeds the clean total
    # (negative baseball score class, #3951): blended pair is unrenderable -> falls back
    spreads = {
        "sportsbook": {"spread": -14.0, "confidence": 1.0, "contracts": []},
        "kalshi": {"spread": -2.0, "confidence": 0.95, "contracts": []},
    }
    totals = {
        "sportsbook": {"total": 7.0, "confidence": 1.0, "contracts": []},
    }
    # Blended spread = -8.0, total = 7.0 -> away = -0.5 (unrenderable!).
    # Fallback select_projected_final walks to kalshi (-2.0) + sportsbook (7.0) -> 4.5 - 2.5.
    res = blend_projected_final(spreads, totals)
    assert res is not None
    assert res.projection.home_score >= 0
    assert res.projection.away_score >= 0
    assert (res.projection.home_score, res.projection.away_score) == (4.5, 2.5)
    assert res.spread_source == "kalshi"


def test_live_game_265a_keeps_sportsbooks_only_even_with_fresh_clean_pm_ladders():
    """Ruling 265: A, for now (#13007): during live play, keep the projected final on
    current sportsbooks only — never blend Kalshi or Polymarket during a live game."""
    now = datetime(2026, 11, 19, 2, 15, 0, tzinfo=timezone.utc)
    score_changed_at = now - timedelta(seconds=90)
    fresh_ts = (now - timedelta(seconds=45)).isoformat()

    spreads = {
        "sportsbook": {"spread": -2.2, "confidence": 1.0, "updated_at": fresh_ts},
        "kalshi": {"spread": -6.0, "confidence": 0.95, "updated_at": fresh_ts},
        "polymarket": {"spread": -5.0, "confidence": 0.90, "updated_at": fresh_ts},
    }
    totals = {
        "sportsbook": {"total": 239.0, "confidence": 1.0, "updated_at": fresh_ts},
        "kalshi": {"total": 225.0, "confidence": 0.90, "updated_at": fresh_ts},
        "polymarket": {"total": 220.0, "confidence": 0.90, "updated_at": fresh_ts},
    }

    res = blend_projected_final(
        spreads,
        totals,
        is_live=True,
        now=now,
        state_changed_at=score_changed_at,
        sport_key="basketball_nba",
    )
    assert res is not None
    assert res.spread_source == "sportsbook"
    assert res.total_source == "sportsbook"
    assert res.spread_sources == ("sportsbook",)
    assert res.total_sources == ("sportsbook",)
    assert res.projection.spread == -2.2
    assert res.projection.total == 239.0


def test_live_game_265a_stale_sportsbook_withholds_never_falls_back_to_pm():
    """Ruling 265: A + 233: A: when no sportsbook line is current during a live game,
    withhold the projected final (None) even when Kalshi/Polymarket are fresh and clean."""
    now = datetime(2026, 11, 19, 2, 15, 0, tzinfo=timezone.utc)
    score_changed_at = now - timedelta(seconds=90)
    fresh_ts = (now - timedelta(seconds=30)).isoformat()
    stale_ts = (now - timedelta(minutes=20)).isoformat()

    spreads = {
        "sportsbook": {"spread": -2.0, "confidence": 1.0, "updated_at": stale_ts},
        "kalshi": {"spread": -1.8, "confidence": 0.95, "updated_at": fresh_ts},
        "polymarket": {"spread": -2.0, "confidence": 0.90, "updated_at": fresh_ts},
    }
    totals = {
        "sportsbook": {"total": 239.0, "confidence": 1.0, "updated_at": stale_ts},
        "kalshi": {"total": 237.2, "confidence": 0.90, "updated_at": fresh_ts},
        "polymarket": {"total": 236.0, "confidence": 0.90, "updated_at": fresh_ts},
    }
    res = blend_projected_final(
        spreads,
        totals,
        is_live=True,
        now=now,
        state_changed_at=score_changed_at,
        sport_key="basketball_nba",
    )
    assert res is None

    # Also withheld when sportsbook is completely absent during live play
    res_no_sb = blend_projected_final(
        {"kalshi": spreads["kalshi"]},
        {"kalshi": totals["kalshi"]},
        is_live=True,
        now=now,
        state_changed_at=score_changed_at,
        sport_key="basketball_nba",
    )
    assert res_no_sb is None


def test_live_game_265a_pinned_handicap_sport_withholds_live_projection():
    """Live NHL/MLB must never project from a pinned ±1.5 sportsbook handicap or
    fall back to prediction-market ladders under Ruling 265: A."""
    now = datetime(2026, 11, 19, 2, 15, 0, tzinfo=timezone.utc)
    score_changed_at = now - timedelta(seconds=90)
    fresh_ts = (now - timedelta(seconds=30)).isoformat()

    res = blend_projected_final(
        {
            "sportsbook": {"spread": -1.5, "confidence": 1.0, "updated_at": fresh_ts},
            "kalshi": {"spread": -0.2, "confidence": 0.90, "updated_at": fresh_ts},
        },
        {
            "sportsbook": {"total": 5.5, "confidence": 1.0, "updated_at": fresh_ts},
            "kalshi": {"total": 6.0, "confidence": 0.90, "updated_at": fresh_ts},
        },
        is_live=True,
        now=now,
        state_changed_at=score_changed_at,
        sport_key="icehockey_nhl",
    )
    assert res is None


def test_bracket_updated_at_uses_oldest_bracketing_rung():
    t_old = datetime(2026, 11, 19, 2, 10, 0, tzinfo=timezone.utc)
    t_new = datetime(2026, 11, 19, 2, 14, 30, tzinfo=timezone.utc)
    res = binary_to_implied_spread(
        [
            {"threshold": 1.5, "probability": 0.62, "updated_at": t_old},
            {"threshold": 3.5, "probability": 0.44, "updated_at": t_new},
        ]
    )
    assert res is not None
    assert res.updated_at == t_old.isoformat()


def test_76ers_magic_split_winner_reconciles_with_clean_blend():
    # Sportsbooks slightly favor away (+0.5), while clean Kalshi (-2.5) and Polymarket (-2.0)
    # favor home — blending produces -1.3 (home favored), matching the blended chance.
    spreads = {
        "sportsbook": {"spread": 0.5, "confidence": 1.0},
        "kalshi": {"spread": -2.5, "confidence": 0.90},
        "polymarket": {"spread": -2.0, "confidence": 0.85},
    }
    totals = {
        "sportsbook": {"total": 224.0, "confidence": 1.0},
        "kalshi": {"total": 224.0, "confidence": 0.85},
    }
    res = blend_projected_final(spreads, totals)
    assert res is not None
    assert res.projection.home_score > res.projection.away_score
    assert res.spread_sources == ("sportsbook", "kalshi", "polymarket")


async def test_route_switch_off_vs_on_blends_clean_sources_and_emits_source_lists(
    monkeypatch,
):
    from tests.test_nfl_projected_final_8898 import _all_specimen_markets, _pm_spread_data

    # Default (switch OFF): single ranked source, legacy keys only (no spread_sources/total_sources).
    monkeypatch.delenv(PROJECTED_FINAL_BLEND_ENV, raising=False)
    off_data = await _pm_spread_data(*_all_specimen_markets())
    off_pf = off_data["projected_final"]
    assert off_pf is not None
    assert "spread_sources" not in off_pf
    assert "total_sources" not in off_pf

    # Switch ON: blends both clean totals (kalshi + polymarket), preserves spread_source/total_source,
    # and populates spread_sources / total_sources.
    monkeypatch.setenv(PROJECTED_FINAL_BLEND_ENV, "true")
    on_data = await _pm_spread_data(*_all_specimen_markets())
    on_pf = on_data["projected_final"]
    assert on_pf is not None
    assert on_pf["spread_source"] == "kalshi"
    assert on_pf["spread_sources"] == ["kalshi"]
    assert on_pf["total_source"] == "blend"
    assert on_pf["total_sources"] == ["kalshi", "polymarket"]
    assert on_pf["home_score"] >= 0 and on_pf["away_score"] >= 0


async def test_route_live_game_265a_sportsbooks_only_and_withholds_when_book_stale(
    monkeypatch,
):
    """Route-level Ruling 265: A + 233: A proof on `get_event_odds_history`:
    1. When a live game has only fresh Kalshi/Polymarket ladders and a STALE
       sportsbook snapshot (even one old enough to generate a synthetic `now`
       point in `history[-1]`), `pm_spread_data.projected_final` is withheld (`None`).
    2. When a live game has a CURRENT sportsbook snapshot under 233: A beside
       fresh Kalshi/Polymarket ladders, `pm_spread_data.projected_final` uses the
       sportsbook line ONLY (`spread_sources == ["sportsbook"]`).
    """
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.routes.events import get_event_odds_history
    from app.utils.live_line_clock import LIVE_STATE_CLOCK_KEY
    from tests.test_projection_source_confidence_3921 import _DispatchingSession, _market, _outcome

    now = datetime.now(timezone.utc)
    score_change = now - timedelta(seconds=90)
    fresh = now - timedelta(seconds=30)
    stale_pre_cutoff = now - timedelta(hours=30)

    kalshi_spread = _market(
        "kalshi",
        [
            _outcome("Orlando Magic wins by over 1.5 points", 0.56),
            _outcome("Orlando Magic wins by over 2.5 points", 0.44),
        ],
        name="Spread",
        external_id="KXNBASPREAD-TEST",
    )
    kalshi_total = _market(
        "kalshi",
        [
            _outcome("Over 236.5 points scored", 0.55),
            _outcome("Over 238.5 points scored", 0.45),
        ],
        name="Total",
        external_id="KXNBATOTAL-TEST",
    )
    for m in (kalshi_spread, kalshi_total):
        for o in m.outcomes:
            o.price_changed_at = fresh
            o.last_updated = fresh

    live_event = SimpleNamespace(
        id=15350555,
        status="live",
        commence_time=now - timedelta(hours=1),
        completed_at=None,
        home_team_name="Orlando Magic",
        away_team_name="Philadelphia 76ers",
        home_score=80,
        away_score=78,
        sport=SimpleNamespace(key="basketball_nba"),
        sport_id=2,
        box_score_data=None,
        win_probability_sources={
            "kalshi": {"value": 0.58},
            LIVE_STATE_CLOCK_KEY: score_change.isoformat(),
        },
    )

    def _sb_snap(*, captured_at: datetime, home_proj: float, away_proj: float, ou: float):
        return SimpleNamespace(
            id=1,
            event_id=15350555,
            bookmaker="draftkings",
            captured_at=captured_at,
            valid_until=None,
            home_win_probability=0.58,
            away_win_probability=0.42,
            home_odds=-140,
            away_odds=120,
            home_spread=away_proj - home_proj,
            over_under=ou,
            projected_home_score=home_proj,
            projected_away_score=away_proj,
        )

    class _SessionWithOdds(_DispatchingSession):
        def __init__(self, event, markets, odds_snaps):
            super().__init__(event, markets)
            self._odds_snaps = list(odds_snaps)

        async def execute(self, stmt, *args, **kwargs):
            text = str(stmt)
            if "FROM odds_snapshots" in text:
                class _Res:
                    def __init__(self, rows):
                        self._rows = rows
                    def scalars(self):
                        return self
                    def all(self):
                        return list(self._rows)
                return _Res(self._odds_snaps)
            return await super().execute(stmt, *args, **kwargs)

    monkeypatch.setenv(PROJECTED_FINAL_BLEND_ENV, "true")

    # Case 1: Stale sportsbook (pre-cutoff with valid_until=None, which produces
    # a synthetic `now` bucket in `history[-1]`) + fresh Kalshi ladders -> WITHHELD.
    stale_payload = await get_event_odds_history(
        event_id=15350555,
        hours=24,
        response=MagicMock(headers={}),
        db=_SessionWithOdds(
            live_event,
            (kalshi_spread, kalshi_total),
            [_sb_snap(captured_at=stale_pre_cutoff, home_proj=110.0, away_proj=108.0, ou=218.0)],
        ),
    )
    assert (stale_payload.get("pm_spread_data") or {}).get("projected_final") is None

    # Case 2: Current sportsbook under 233: A (120.0 - 116.0, total 236.0) +
    # fresh Kalshi ladders (spread -2.0, total 237.5) -> SPORTSBOOK ONLY.
    fresh_payload = await get_event_odds_history(
        event_id=15350555,
        hours=24,
        response=MagicMock(headers={}),
        db=_SessionWithOdds(
            live_event,
            (kalshi_spread, kalshi_total),
            [_sb_snap(captured_at=fresh, home_proj=120.0, away_proj=116.0, ou=236.0)],
        ),
    )
    pf = (fresh_payload.get("pm_spread_data") or {}).get("projected_final")
    assert pf is not None
    assert pf["spread_source"] == "sportsbook"
    assert pf["total_source"] == "sportsbook"
    assert pf["spread_sources"] == ["sportsbook"]
    assert pf["total_sources"] == ["sportsbook"]
    assert pf["home_score"] == 120.0
    assert pf["away_score"] == 116.0


def test_pinned_handicap_sports_exclude_sportsbook_spread_from_blend() -> None:
    """#13007 (Fable point 3): NHL ±1.5 puck line and MLB ±1.5 run line are fixed
    handicaps, not expected margins, and must never enter the spread blend as a
    clean source at confidence 1.0."""
    from app.utils.binary_spread import sportsbook_spread_is_implied_margin

    assert sportsbook_spread_is_implied_margin("americanfootball_nfl") is True
    assert sportsbook_spread_is_implied_margin("basketball_nba") is True
    assert sportsbook_spread_is_implied_margin("soccer_epl") is True
    assert sportsbook_spread_is_implied_margin("icehockey_nhl") is False
    assert sportsbook_spread_is_implied_margin("baseball_mlb") is False
    assert sportsbook_spread_is_implied_margin("tennis_atp_us_open") is False

    # Stars @ Golden Knights (NHL): sportsbook has fixed -1.5 puck line (conf 1.0),
    # while Kalshi implies -0.2 margin and 6.0 total. Excluding the pinned puck line
    # leaves Kalshi's -0.2 spread cleanly (2.9-3.1 instead of puck-line 2.0-3.5).
    blended_nhl = blend_projected_final(
        {
            "sportsbook": {"spread": -1.5, "confidence": 1.0},
            "kalshi": {"spread": -0.2, "confidence": 0.85},
        },
        {
            "sportsbook": {"total": 5.5, "confidence": 1.0},
            "kalshi": {"total": 6.0, "confidence": 0.90},
        },
        sport_key="icehockey_nhl",
    )
    assert blended_nhl is not None
    assert blended_nhl.spread_sources == ("kalshi",)
    assert abs(blended_nhl.projection.spread - (-0.2)) <= 0.1

    # NHL with ONLY pinned sportsbook spread -> returns None (no honest spread source)
    nhl_sb_only = blend_projected_final(
        {"sportsbook": {"spread": -1.5, "confidence": 1.0}},
        {"sportsbook": {"total": 5.5, "confidence": 1.0}},
        sport_key="icehockey_nhl",
    )
    assert nhl_sb_only is None
