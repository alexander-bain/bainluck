"""Ruling 301: A (#12538): End-to-end Discover display-chain proofs on real shapes.

Tests all required behaviors from Fable's 3:50 PM PT brief (Nov 20, 2026):
1. A followed team's game stays on Discover (standing follow/local/alma_mater; never rival alone).
2. An unfollowed live game with a huge win-probability swing goes.
3. An unfollowed finished upset goes, and the Sep 10 guaranteed first-page seat for finished games is ended.
4. A game inside tonight's slate grouping (`type == "bundle"`) still shows there.
5. A signed-out reader sees zero single game cards across the returned Discover list.
6. The first twenty seats stay full and non-event order is preserved.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from app.routes.feed import PersonalizationContext, apply_discover_display_chain
from app.utils import discover_game_reason as gr

NOW = datetime(2025, 2, 15, 23, 30, tzinfo=timezone.utc)
FOLLOWED_TEAM_ID = 701
OTHER_HOME_ID = 702
SWING_AWAY_ID = 703
SWING_HOME_ID = 704
UPSET_AWAY_ID = 705
UPSET_HOME_ID = 706
RIVAL_TEAM_ID = 707


def _futures_card(idx: int, *, category: str, score: float) -> dict:
    return {
        "type": "futures",
        "score": int(round(score)),
        "_rank_score": float(score),
        "_sort_time": NOW.timestamp() - idx,
        "headline": f"Futures Question {idx}?",
        "reason": "Resolving soon",
        "data": {
            "id": 20_000 + idx,
            "name": f"Market Question {idx}?",
            "llm_sport_category": category,
            "status": "open",
            "outcomes": [{"name": "Yes", "probability": 0.42}],
        },
    }


def _slate_bundle_card(*, score: float = 91.0) -> dict:
    member_game = {
        "type": "event",
        "data": {
            "id": 9101,
            "sport": "basketball_nba",
            "status": "live",
            "home_team": "Boston Celtics",
            "away_team": "Miami Heat",
            "home_team_data": {"team_id": 801, "abbreviation": "BOS"},
            "away_team_data": {"team_id": 802, "abbreviation": "MIA"},
        },
    }
    return {
        "type": "bundle",
        "score": int(round(score)),
        "_rank_score": float(score),
        "_sort_time": NOW.timestamp(),
        "headline": "Tonight's NBA Slate",
        "reason": "3 games tipping off tonight",
        "data": {
            "id": "roundup-nba-slate-tonight",
            "slug": "nba-slate-tonight",
            "name": "Tonight's NBA Slate",
            "llm_sport_category": "basketball_nba",
            "items": [member_game],
        },
    }


def _game_card(
    event_id: int,
    *,
    home_team: str,
    away_team: str,
    home_id: int,
    away_id: int,
    status: str = "live",
    score: float = 88.0,
    pregame_home: float = 0.50,
    now_home: float = 0.50,
    home_score: int = 0,
    away_score: int = 0,
    sport: str = "basketball_nba",
    hours_ago: float = 0.5,
    tags: list[str] | None = None,
    use_private_team_ids_only: bool = False,
) -> dict:
    commence = NOW - timedelta(hours=hours_ago)
    home_data = {"abbreviation": home_team[:3].upper(), "logo_small": "h"}
    away_data = {"abbreviation": away_team[:3].upper(), "logo_small": "a"}
    if not use_private_team_ids_only:
        home_data["team_id"] = home_id
        away_data["team_id"] = away_id
    card = {
        "type": "event",
        "score": int(round(score)),
        "_rank_score": float(score),
        "_admission_score": int(round(score)),
        "_sort_time": commence.timestamp(),
        "_home_team_id": home_id,
        "_away_team_id": away_id,
        "headline": f"{away_team} at {home_team}",
        "reason": "Close matchup",
        "data": {
            "id": event_id,
            "sport": sport,
            "status": status,
            "commence_time": commence.isoformat().replace("+00:00", "Z"),
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "hero_probability": now_home,
            "opening_odds": {"home_probability": pregame_home},
            "prematch_odds": {"home_probability": pregame_home},
            "home_team_data": home_data,
            "away_team_data": away_data,
            "event_tags": list(tags if tags is not None else ["tier:1"]),
        },
    }
    return card


def _discover_deck() -> list[dict]:
    cats = ["politics", "tech", "entertainment", "weather", "economics", "geopolitics", "culture"]
    items: list[dict] = [
        _slate_bundle_card(score=91.0),
        # Followed team live game (using private _home/_away team id fields as _personalize_events builds).
        _game_card(
            1001,
            home_team="Golden State Warriors",
            away_team="Sacramento Kings",
            home_id=FOLLOWED_TEAM_ID,
            away_id=OTHER_HOME_ID,
            status="live",
            score=90.0,
            use_private_team_ids_only=True,
        ),
        # Unfollowed live game with massive swing (16% -> 71%).
        _game_card(
            1002,
            home_team="Louisville Cardinals",
            away_team="UConn Huskies",
            home_id=SWING_HOME_ID,
            away_id=SWING_AWAY_ID,
            status="live",
            score=94.0,
            pregame_home=0.84,
            now_home=0.29,
            sport="basketball_ncaab",
        ),
        # Unfollowed finished huge upset (21% underdog wins cleanly).
        _game_card(
            1003,
            home_team="Vegas Golden Knights",
            away_team="Vancouver Canucks",
            home_id=UPSET_HOME_ID,
            away_id=UPSET_AWAY_ID,
            status="completed",
            score=89.0,
            pregame_home=0.79,
            now_home=0.0,
            home_score=2,
            away_score=5,
            sport="icehockey_nhl",
            hours_ago=5.0,
            tags=["tier:1", "excitement:high"],
        ),
        # Unfollowed regular-season scheduled game.
        _game_card(
            1004,
            home_team="Edmonton Oilers",
            away_team="Florida Panthers",
            home_id=RIVAL_TEAM_ID,
            away_id=708,
            status="scheduled",
            score=87.0,
            hours_ago=-2.0,
        ),
    ]
    for i in range(25):
        items.append(_futures_card(i, category=cats[i % len(cats)], score=86.0 - i * 0.5))
    return items


class TestDiscoverSingleGames301:
    def test_signed_out_reader_sees_zero_single_games_and_full_top_20_and_keeps_slate_grouping(self):
        deck = _discover_deck()
        signed_out = PersonalizationContext(is_authenticated=False)
        out, meta = apply_discover_display_chain(
            copy.deepcopy(deck),
            limit=20,
            ctx=signed_out,
            event_pct=0.15,
            include_events=True,
            my_teams_only=False,
            sports_mode=False,
            now=NOW,
        )

        # Signed-out reader sees ZERO single game cards anywhere on Discover.
        assert [it for it in out if it.get("type") == "event"] == []
        # First twenty seats remain completely full.
        assert len(out[:20]) == 20
        # Unfollowed live swing (1002), finished upset (1003), and scheduled (1004) are all out.
        served_ids = {(it.get("data") or {}).get("id") for it in out}
        assert {1001, 1002, 1003, 1004}.isdisjoint(served_ids)
        # Tonight's slate grouping card stays in Discover with its member game intact.
        bundles = [it for it in out if it.get("type") == "bundle"]
        assert len(bundles) == 1
        assert bundles[0]["data"]["items"][0]["data"]["id"] == 9101
        # Sep 10 finished-game guaranteed seating is ended.
        assert meta["final_seating"]["seated"] == 0

    def test_non_event_order_is_unchanged(self):
        deck = _discover_deck()
        signed_out = PersonalizationContext(is_authenticated=False)
        out_301, _ = apply_discover_display_chain(
            copy.deepcopy(deck),
            limit=20,
            ctx=signed_out,
            event_pct=0.15,
            include_events=True,
            now=NOW,
        )
        # Same non-event relative order as running only non-events through the chain.
        non_events_only = [copy.deepcopy(it) for it in deck if it.get("type") != "event"]
        out_non_events, _ = apply_discover_display_chain(
            non_events_only,
            limit=20,
            ctx=signed_out,
            event_pct=0.15,
            include_events=True,
            now=NOW,
        )
        assert [it["data"]["id"] for it in out_301] == [it["data"]["id"] for it in out_non_events]

    def test_followed_team_game_stays_and_unfollowed_games_drop(self):
        deck = _discover_deck()
        follower = PersonalizationContext(
            team_relations={FOLLOWED_TEAM_ID: {"follow"}},
            is_authenticated=True,
        )
        out, _ = apply_discover_display_chain(
            copy.deepcopy(deck),
            limit=20,
            ctx=follower,
            event_pct=0.15,
            include_events=True,
            now=NOW,
        )
        served_events = [it for it in out if it.get("type") == "event"]
        assert [it["data"]["id"] for it in served_events] == [1001]
        assert served_events[0]["headline"] == "Sacramento Kings at Golden State Warriors"
        # Rival relation alone does not admit a single game to Discover.
        rival_ctx = PersonalizationContext(
            team_relations={RIVAL_TEAM_ID: {"rival"}},
            is_authenticated=True,
        )
        out_rival, _ = apply_discover_display_chain(
            copy.deepcopy(deck),
            limit=20,
            ctx=rival_ctx,
            event_pct=0.15,
            include_events=True,
            now=NOW,
        )
        assert [it for it in out_rival if it.get("type") == "event"] == []

    def test_sep10_guaranteed_finished_game_seat_is_ended_even_for_followed_final(self):
        # Put a followed-team completed marquee game below page 1 (low score, hours ago).
        followed_final = _game_card(
            1099,
            home_team="Golden State Warriors",
            away_team="Los Angeles Clippers",
            home_id=FOLLOWED_TEAM_ID,
            away_id=OTHER_HOME_ID,
            status="completed",
            score=42.0,
            pregame_home=0.60,
            now_home=1.0,
            home_score=115,
            away_score=102,
            sport="basketball_nba",
            hours_ago=4.0,
            tags=["tier:1", "excitement:high"],
        )
        cats = [
            "politics",
            "tech",
            "entertainment",
            "weather",
            "economics",
            "geopolitics",
            "culture",
            "golf",
            "tennis",
        ]
        deck = [_futures_card(i, category=cats[i % len(cats)], score=92.0 - i * 0.5) for i in range(32)]
        deck.append(followed_final)
        follower = PersonalizationContext(
            team_relations={FOLLOWED_TEAM_ID: {"follow"}},
            is_authenticated=True,
        )
        out, meta = apply_discover_display_chain(
            deck,
            limit=20,
            ctx=follower,
            event_pct=0.15,
            include_events=True,
            now=NOW,
        )
        assert meta["final_seating"]["seated"] == 0
        kept = next(it for it in out if it.get("type") == "event")
        assert kept["data"].get("discover_marquee_final") is False
        # Not forced into slot 10 (`DISCOVER_FINAL_SEAT_FLOOR`) — stays below higher-scored futures.
        assert out.index(kept) >= 20

    def test_sports_tab_and_my_stuff_are_unaffected(self):
        deck = _discover_deck()
        signed_out = PersonalizationContext(is_authenticated=False)
        sports_out, _ = apply_discover_display_chain(
            copy.deepcopy(deck),
            limit=20,
            ctx=signed_out,
            event_pct=0.6,
            include_events=True,
            my_teams_only=False,
            sports_mode=True,
            now=NOW,
        )
        assert {it["data"]["id"] for it in sports_out if it.get("type") == "event"} >= {1001, 1002, 1003, 1004}

        my_stuff_out, _ = apply_discover_display_chain(
            copy.deepcopy(deck),
            limit=20,
            ctx=PersonalizationContext(team_relations={FOLLOWED_TEAM_ID: {"follow"}}, is_authenticated=True),
            event_pct=None,
            include_events=True,
            my_teams_only=True,
            sports_mode=False,
            now=NOW,
        )
        assert {it["data"]["id"] for it in my_stuff_out if it.get("type") == "event"} >= {1001, 1002, 1003, 1004}

    def test_stated_stake_switch_lets_playoffs_back_in_while_refusing_swings(self, monkeypatch):
        playoff_game = _game_card(
            1050,
            home_team="Boston Celtics",
            away_team="New York Knicks",
            home_id=810,
            away_id=811,
            status="scheduled",
            score=89.0,
            hours_ago=-3.0,
            tags=["tier:1", "importance:playoff"],
        )
        deck = _discover_deck() + [playoff_game]
        signed_out = PersonalizationContext(is_authenticated=False)

        # Even if someone lists swing/upset, chance swings never earn a seat.
        monkeypatch.setenv(gr.ALLOWED_REASONS_ENV, "swing,fast_swing,upset")
        out_swings, _ = apply_discover_display_chain(
            copy.deepcopy(deck),
            limit=20,
            ctx=signed_out,
            event_pct=0.15,
            include_events=True,
            now=NOW,
        )
        assert [it for it in out_swings if it.get("type") == "event"] == []

        # Turning on `stakes` admits only the playoff game with its stated stake copy.
        monkeypatch.setenv(gr.ALLOWED_REASONS_ENV, "stakes")
        out_stakes, _ = apply_discover_display_chain(
            copy.deepcopy(deck),
            limit=20,
            ctx=signed_out,
            event_pct=0.15,
            include_events=True,
            now=NOW,
        )
        kept = [it for it in out_stakes if it.get("type") == "event"]
        assert [it["data"]["id"] for it in kept] == [1050]
        assert kept[0]["headline"] == "Playoff game"
