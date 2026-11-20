"""#11937 (Ruling 277: A): Unit tests and freeze guard for Candidate 3."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.utils import discover_rank_c3 as c3

FROZEN_NOW = datetime(2025, 5, 1, 15, 15, tzinfo=timezone.utc)
FUN_IDS = frozenset({1001, 1002, 1003, 1004, 1005})
LONG_SHOT_IDS = frozenset({1004, 1005})


def _card(
    item_key: str,
    *,
    served_position: int,
    kind: str = "futures",
    score: float = 80.0,
    category: str = "tech",
    title: str = "Sample market",
    market_id: int | None = None,
    days_until: float | None = 30.0,
    hours_until_start: float | None = None,
    movement: float | None = None,
    story_key: str | None = None,
    entities: list[str] | None = None,
    settled: bool = False,
    stale: bool = False,
    blend_missing: bool = False,
) -> dict:
    res_iso = (
        (FROZEN_NOW + timedelta(days=days_until)).isoformat()
        if days_until is not None
        else None
    )
    start_iso = (
        (FROZEN_NOW + timedelta(hours=hours_until_start)).isoformat()
        if hours_until_start is not None
        else None
    )
    outcomes = (
        [{"name": "Yes", "probability": 0.45, "movement": movement}]
        if movement is not None
        else [{"name": "Yes", "probability": 0.45, "movement": None}]
    )
    data: dict = {
        "name": title,
        "title": title,
        "llm_sport_category": category,
        "resolution_date": res_iso,
        "top_outcomes": outcomes,
    }
    if kind == "futures":
        data["id"] = market_id if market_id is not None else 9000 + served_position
    elif kind == "bundle":
        data["story_key"] = story_key or ""
        data["member_ids"] = [market_id] if market_id is not None else [9000 + served_position]
        data["items"] = [
            {
                "type": "futures",
                "data": {
                    "id": data["member_ids"][0],
                    "resolution_date": res_iso,
                    "top_outcomes": outcomes,
                },
            }
        ]
    return {
        "item_key": item_key,
        "type": kind,
        "title": title,
        "category": category,
        "score": score,
        "entities": entities or [],
        "served_position": served_position,
        "resolution_time": res_iso,
        "start_time": start_iso,
        "price_observed_at": FROZEN_NOW.isoformat(),
        "settled": settled,
        "stale": stale,
        "blend_missing": blend_missing,
        "settled_without_result": False,
        "card": {"type": kind, "data": data},
    }


def test_bounded_grouped_lift_replaces_flat_plus_one():
    """A quiet 59-pt bundle must not beat an 85-pt lone card (unlike Candidate 2's +1.0)."""
    quiet_bundle = _card("b1", served_position=1, kind="bundle", score=59.0, category="tech")
    strong_single = _card("f1", served_position=2, kind="futures", score=85.0, category="tech")
    assert c3.worth_c3(strong_single, FROZEN_NOW, fun_ids=FUN_IDS) > c3.worth_c3(
        quiet_bundle, FROZEN_NOW, fun_ids=FUN_IDS
    )


def test_static_story_bundle_loses_to_moving_story_bundle():
    """Quiet standing story bundles (Fed & Rates, AI, Middle East) lose to moving bundles."""
    static_bundle = _card(
        "b_static",
        served_position=1,
        kind="bundle",
        score=90.0,
        category="economics",
        story_key="fed-rates",
        movement=0.0,
    )
    moving_bundle = _card(
        "b_moving",
        served_position=2,
        kind="bundle",
        score=88.0,
        category="economics",
        story_key="fed-rates",
        movement=0.06,
    )
    assert c3.worth_c3(moving_bundle, FROZEN_NOW, fun_ids=FUN_IDS) > c3.worth_c3(
        static_bundle, FROZEN_NOW, fun_ids=FUN_IDS
    )


def test_far_horizon_discount_exempts_fun_tagged_and_ignores_past_dates():
    """Ruling 277: A + #13106 item 4: >60d non-fun markets take a discount, fun
    markets are exempt, and past-date markets (days < 0) earn zero near credit."""
    near_plain = _card("near", served_position=1, score=80.0, days_until=10.0, market_id=5001)
    past_plain = _card("past", served_position=2, score=80.0, days_until=-5.0, market_id=5002)
    far_plain = _card("far", served_position=3, score=80.0, days_until=120.0, market_id=5003)
    far_fun = _card("fun", served_position=4, score=80.0, days_until=400.0, market_id=1001)

    w_near = c3.worth_c3(near_plain, FROZEN_NOW, fun_ids=FUN_IDS)
    w_past = c3.worth_c3(past_plain, FROZEN_NOW, fun_ids=FUN_IDS)
    w_far = c3.worth_c3(far_plain, FROZEN_NOW, fun_ids=FUN_IDS)
    w_fun = c3.worth_c3(far_fun, FROZEN_NOW, fun_ids=FUN_IDS)

    assert w_near > w_past  # past-date gets no near-resolution credit
    assert w_past - w_far >= 0.17  # >60d non-fun discount applied
    assert w_fun > w_near  # fun-tagged far market is completely exempt from discount


def test_opening_ten_enforces_mix_caps_adjacency_and_blocks_minor_foreign_politics():
    """Candidate 3 promotes fun/entertainment from beyond seat 20, blocks quiet
    minor foreign politics (Gambia/Spain), caps weekly Netflix at 1, caps sports
    at 1 per sport, caps fun at 3 (<=1 long-shot), and avoids adjacent grouped cards."""
    slate = [
        # Quiet foreign politics in seats 1-2
        _card("pol_gambia", served_position=1, score=63.0, category="politics", title="Gambia presidential election"),
        _card("pol_spain", served_position=2, score=65.0, category="politics", title="Next Prime Minister of Spain?"),
        # Major politics headline (score 96)
        _card("pol_me", served_position=3, kind="bundle", score=96.0, category="politics", title="Middle East", story_key="middle-east", movement=0.05),
        # Second major politics headline (should be capped at <=1 in top 10)
        _card("pol_ru", served_position=4, kind="bundle", score=95.0, category="politics", title="Russia-Ukraine", story_key="russia-ukraine", movement=0.04),
        # Two weekly Netflix movie cards (only 1 allowed in top 10)
        _card("nflx_us", served_position=5, score=88.0, category="entertainment", title="What will be the top US Netflix movie this week?"),
        _card("nflx_gl", served_position=6, score=88.0, category="entertainment", title="What will be the top global Netflix movie this week?"),
        # Three golf cards (only 1 golf allowed in top 10)
        _card("golf_b", served_position=7, kind="bundle", score=98.0, category="golf", title="Two tournaments", movement=0.10),
        _card("golf_1", served_position=8, kind="tournament", score=99.0, category="golf", title="The RSM Classic", days_until=2.0),
        _card("golf_2", served_position=9, kind="tournament", score=97.0, category="golf", title="CME Group Tour Championship", days_until=2.0),
        # Distinct live/imminent sports events
        _card("nhl_1", served_position=10, kind="event", score=95.0, category="icehockey_nhl", title="Stars @ Knights", hours_until_start=2.0),
        _card("nba_1", served_position=11, kind="event", score=93.0, category="basketball_nba", title="Lakers @ Celtics", hours_until_start=3.0),
        _card("nfl_1", served_position=12, kind="bundle", score=96.0, category="football", title="CFP picture"),
        # Economics & Tech non-grouped singles (enough to fill opening ten without Pass 2)
        _card("econ_1", served_position=13, score=82.0, category="economics", title="Panama Canal traffic", days_until=7.0),
        _card("tech_1", served_position=14, score=83.0, category="tech", title="Next frontier model", days_until=10.0),
        _card("econ_2", served_position=15, score=81.0, category="economics", title="CPI print", days_until=12.0),
        _card("tech_2", served_position=16, score=80.0, category="tech", title="Chip supply", days_until=14.0),
        # Fun cards seated beyond 20 (including 2 long-shot singles; only 1 long-shot allowed)
        _card("fun_1", served_position=25, kind="bundle", score=92.0, category="politics", title="Aliens & UFOs", market_id=1001, days_until=200.0),
        _card("fun_2", served_position=30, score=86.0, category="entertainment", title="TIME Person of the Year", market_id=1002, days_until=220.0),
        _card("fun_3", served_position=35, score=85.0, category="entertainment", title="Katy Perry engaged?", market_id=1003, days_until=40.0),
        _card("fun_ls1", served_position=40, score=88.0, category="culture", title="Musk buys sports team?", market_id=1004, days_until=150.0),
        _card("fun_ls2", served_position=45, score=87.0, category="entertainment", title="Musk cast in Superman?", market_id=1005, days_until=150.0),
    ]

    ordered = c3.rank_c3_mix(slate, now=FROZEN_NOW, fun_ids=FUN_IDS, long_shot_ids=LONG_SHOT_IDS)
    top10 = ordered[:10]
    top10_keys = [c["item_key"] for c in top10]

    # Minor foreign politics kept out
    assert "pol_gambia" not in top10_keys
    assert "pol_spain" not in top10_keys

    # Politics capped at <= 1
    pol_cards = [c for c in top10 if c3.is_politics(c, fun_ids=FUN_IDS)]
    assert len(pol_cards) <= 1

    # Weekly Netflix capped at <= 1
    netflix_cards = [c for c in top10 if c3.is_weekly_chart(c)]
    assert len(netflix_cards) <= 1

    # Fun cards promoted from >20, capped at <= 3, long-shot singles <= 1
    fun_cards = [c for c in top10 if c3.is_fun_tagged(c, fun_ids=FUN_IDS)]
    ls_cards = [c for c in top10 if c3.is_long_shot_single(c, long_shot_ids=LONG_SHOT_IDS)]
    assert len(fun_cards) == 3
    assert len(ls_cards) <= 1

    # Golf does not triple up (<= 1 per sport), total sports capped at <= 2,
    # non-fun entertainment is not starved by fun-tagged entertainment, and money <= 1
    golf_cards = [c for c in top10 if c3._sport_bucket(c) == "golf"]
    assert len(golf_cards) == 1
    sports_cards = [c for c in top10 if c3.is_sports(c)]
    assert len(sports_cards) <= 2
    money_cards = [c for c in top10 if c3.is_money(c, fun_ids=FUN_IDS)]
    assert len(money_cards) <= 1
    non_fun_ent_cards = [c for c in top10 if c3.is_entertainment(c, fun_ids=FUN_IDS)]
    assert len(non_fun_ent_cards) >= 1

    # Never two grouped cards adjacent
    for a, b in zip(top10, top10[1:]):
        assert not (c3.is_grouped(a) and c3.is_grouped(b))


def test_fixed_finished_game_and_blank_category_sports_bundle_count_toward_sports_cap():
    """A finished game pinned in the opening ten and a blank-category team-schedule
    bundle (member items with type='event') both count toward MAX_SPORTS_OPENING=2."""
    team_bundle = _card("nba_bundle", served_position=1, kind="bundle", score=98.0, category="", title="Boston Celtics: next 3 games")
    team_bundle["card"]["data"]["items"] = [
        {"type": "event", "data": {"sport": "basketball_nba"}},
    ]
    slate = [
        team_bundle,
        _card("golf_1", served_position=2, kind="tournament", score=99.0, category="golf", title="The RSM Classic", days_until=2.0),
        _card("nfl_1", served_position=3, kind="bundle", score=96.0, category="football", title="CFP picture"),
        _card("tech_1", served_position=4, score=83.0, category="tech", title="Next frontier model"),
        _card("tech_2", served_position=5, score=82.0, category="tech", title="Chip supply"),
        _card("econ_1", served_position=6, score=81.0, category="economics", title="Inflation print"),
        _card("econ_2", served_position=7, score=80.0, category="economics", title="Yield curve"),
        _card("nhl_fin", served_position=8, kind="event", score=63.0, category="NHL", title="Canadiens @ Hurricanes", settled=True),
        _card("ent_1", served_position=9, score=84.0, category="entertainment", title="Box office lead"),
        _card("ent_2", served_position=10, score=83.0, category="entertainment", title="Album debut"),
        _card("tech_3", served_position=11, score=79.0, category="tech", title="Cloud spend"),
        _card("tech_4", served_position=12, score=78.0, category="tech", title="Robotics rollout"),
        _card("ent_3", served_position=13, score=77.0, category="entertainment", title="Festival premiere"),
    ]
    ordered = c3.rank_c3_mix(slate, now=FROZEN_NOW, fun_ids=FUN_IDS, long_shot_ids=LONG_SHOT_IDS)
    top10 = ordered[:10]
    assert ordered[7]["item_key"] == "nhl_fin"
    assert c3.is_sports(team_bundle)
    assert c3._sport_bucket(team_bundle) == "basketball"
    assert sum(1 for c in top10 if c3.is_sports(c)) == 2


def test_truth_gate_failures_leave_page_and_finished_games_keep_seat():
    slate = [
        _card("c1", served_position=1, score=90.0, category="tech"),
        _card("c2_finished", served_position=2, kind="event", score=40.0, category="nba", settled=True),
        _card("c3_stale", served_position=3, score=99.0, category="tech", stale=True),
        _card("c4", served_position=4, score=85.0, category="economics"),
    ]
    ordered = c3.rank_c3_mix(slate, now=FROZEN_NOW, fun_ids=FUN_IDS, long_shot_ids=LONG_SHOT_IDS)
    assert ordered[1]["item_key"] == "c2_finished"
    assert ordered[-1]["item_key"] == "c3_stale"


def test_frozen_discover_rank_c3_sha256_matches_recorded_freeze():
    rank_path = Path(c3.__file__).resolve()
    digest = hashlib.sha256(rank_path.read_bytes()).hexdigest()
    assert digest == "87d87057221acda6de19d45e3073473a07193bd8e67fc1619ee8717e8e4ad9a6"
