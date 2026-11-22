"""Tests for Decisions 329: A & 333: A (#13400) — Discover opening-ten 9:1 + topic-mix + Seat 10 PWM."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.utils.discover_opening_mix import (
    PACIFIC_TZ,
    PWM_SUBTOPIC_MONEY,
    PWM_SUBTOPIC_POLITICS_WORLD,
    TOPIC_ENTERTAINMENT,
    TOPIC_ODD,
    TOPIC_PWM,
    TOPIC_SPORTS,
    TOPIC_TECH_BUSINESS,
    apply_discover_opening_mix,
    classify_discover_opening_topic,
    classify_discover_pwm_subtopic,
    discover_opening_pwm_kind_for_date,
)
from app.utils.discover_opening_seating import (
    COMPLIANT,
    OPENING_SEATS,
    seat_opening,
)
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupProducer,
    _is_grouped_feed_card,
    _is_roundup_bundle_card,
    add_roundup_feed_items,
    compose_roundup_feed_item,
    render_machinery_prewarm_bundle,
)

NOW = datetime(2026, 11, 22, 2, 0, tzinfo=timezone.utc)


def _single(
    mid: int,
    name: str,
    *,
    category: str,
    score: float = 80.0,
) -> dict:
    return {
        "type": "futures",
        "score": score,
        "reason": name,
        "headline": name,
        "data": {
            "id": mid,
            "name": name,
            "status": "open",
            "category": category,
            "llm_sport_category": category,
            "top_outcomes": [{"id": mid * 10, "name": "Yes", "probability": 0.5}],
        },
    }


def _roundup(
    slug: str,
    title: str,
    *,
    kicker: str,
    category: str,
    member_ids: list[int],
    score: float = 0.0,
    live_child: bool = False,
    status: str | None = None,
    relations: list[str] | None = None,
) -> dict:
    children: list[dict] = []
    for mid in member_ids:
        if live_child:
            children.append(
                {
                    "type": "event",
                    "score": 80.0,
                    "data": {
                        "id": mid,
                        "status": "live",
                        "commence_time": (NOW - timedelta(minutes=30)).isoformat(),
                        "is_major": False,
                        "is_marquee": False,
                        "event_tags": [],
                    },
                }
            )
        else:
            children.append(
                {
                    "type": "futures",
                    "score": 80.0,
                    "data": {"id": mid, "name": f"Member {mid}", "status": "open"},
                }
            )
    data: dict = {
        "id": f"roundup:{slug}",
        "title": title,
        "kind": "roundup",
        "story_key": f"roundup:{slug}",
        "category": category,
        "item_count": len(member_ids),
        "member_ids": list(member_ids),
        "items": children,
        "collection_ref": {
            "slug": slug,
            "href": f"/collections/{slug}",
            "name": title,
            "revision": "1",
            "collection_count": len(member_ids),
        },
        "roundup": {
            "kicker": kicker,
            "tag": category.upper(),
            "footer": "",
            "rows": [{"market_id": mid, "label": f"Row {mid}", "probability": 0.5} for mid in member_ids],
            "relations": relations or ["same_subject"],
            "level": "member",
        },
    }
    if status is not None:
        data["status"] = status
    return {
        "type": "bundle",
        "score": score,
        "reason": kicker,
        "headline": title,
        "data": data,
    }


def _theme(theme_key: str, name: str, member_ids: list[int], *, score: float = 86.0) -> dict:
    return {
        "type": "bundle",
        "score": score,
        "reason": name,
        "headline": name,
        "data": {
            "id": f"theme:{theme_key}:{'-'.join(str(m) for m in member_ids)}",
            "title": name,
            "name": name,
            "kind": "theme",
            "story_key": theme_key,
            "items": [
                {"type": "futures", "score": score, "data": {"id": mid, "name": f"M{mid}", "status": "open"}}
                for mid in member_ids
            ],
        },
    }


def _concept(cid: str, name: str, *, live: bool = False, score: float = 99.0) -> dict:
    return {
        "type": "concept",
        "score": score,
        "reason": name,
        "headline": name,
        "data": {
            "id": cid,
            "key": cid,
            "slug": cid,
            "name": name,
            "status": "live" if live else "upcoming",
            "start_date": (NOW - timedelta(hours=1) if live else NOW + timedelta(days=5)).isoformat(),
            "is_major": True,
            "event_tags": [],
        },
    }


def _live_event(eid: int, name: str, *, score: float = 99.0) -> dict:
    return {
        "type": "event",
        "score": score,
        "reason": name,
        "headline": name,
        "data": {
            "id": eid,
            "name": name,
            "status": "live",
            "commence_time": (NOW - timedelta(minutes=20)).isoformat(),
            "is_major": False,
            "is_marquee": False,
            "event_tags": [],
        },
    }


def _representative_deck() -> list[dict]:
    """Mirror production Discover shape before 329: A: PWM-heavy 5:5 top 10, richer groups below."""
    return [
        # Seats 1-10 initially dominated by conflict/macro and singles
        _theme("story:middle_east_conflict", "Middle East", [1001, 1002], score=98.0),
        _roundup("machinery-elon-musk-side-quests", "Musk Side Quests", kicker="ODD · SIDE QUESTS", category="entertainment", member_ids=[2001, 2002], score=87.0, relations=["same_subject", "sibling"]),
        _roundup("machinery-who-gets-engaged", "Celebrity Engagements", kicker="ENTERTAINMENT · COUPLES", category="entertainment", member_ids=[2003, 2004], score=87.0, relations=["same_window", "sibling"]),
        _theme("story:macro_rates", "Fed & Rates", [1003, 1004], score=90.0),
        _single(3001, "Will Russia and Ukraine reach ceasefire?", category="geopolitics", score=98.0),
        _single(3002, "Will China invade Taiwan?", category="geopolitics", score=92.0),
        _single(3003, "Will Boston Bruins advance to Round 2?", category="hockey", score=63.0),
        _single(3004, "Next Prime Minister of Spain?", category="politics", score=63.0),
        _roundup("machinery-2026-summed-up", "2026 Summed Up", kicker="CULTURE · 2026", category="entertainment", member_ids=[2005, 2006], score=85.0, relations=["same_window", "sibling"]),
        _single(3005, "NFL Super Bowl Winner", category="football", score=95.0),
        # Seats 11+ carry rich groups, concepts, live events, and standing roundups
        _roundup("roundup-cfp-picture", "College Football Playoff picture", kicker="SPORTS · CFB", category="football", member_ids=[2007, 2008], score=64.0),
        _single(3006, "Premier League Winner", category="soccer", score=70.0),
        _roundup("machinery-long-shots", "Long Shots", kicker="ODD · LONG SHOTS", category="entertainment", member_ids=[2009, 2010], score=63.0, relations=["same_measure", "sibling"]),
        _single(3007, "Oscar Best Director", category="entertainment", score=72.0),
        _roundup("machinery-white-christmas", "White Christmas", kicker="WEATHER · CHRISTMAS", category="weather", member_ids=[2011, 2012], score=80.0),
        _single(3008, "OpenAI IPO Valuation", category="tech", score=74.0),
        _theme("story:ai", "AI", [2013, 2014], score=86.0),
        _single(3009, "NBA Finals Winner", category="basketball", score=76.0),
        _roundup("machinery-next-james-bond", "Next James Bond", kicker="ENTERTAINMENT · JAMES BOND", category="entertainment", member_ids=[2015, 2016], score=82.0),
        _single(3010, "UFC Lightweight Champion", category="mma", score=60.0),
        _roundup("by-november-30", "Deadlines by Nov 30", kicker="TECH · DEADLINES", category="tech", member_ids=[2017, 2018], score=65.0),
        _single(3011, "Taylor Swift Album Sales", category="culture", score=55.0),
        _roundup("machinery-nba-night", "NBA Tonight", kicker="NBA · THIS SLATE", category="basketball", member_ids=[2019, 2020], score=99.0, live_child=True, status="live"),
        _concept("concept:world-cup-2026", "FIFA World Cup 2026", live=False, score=99.0),
        _live_event(4001, "Live Ordinary Game", score=99.0),
        _roundup("golf-this-week", "Golf This Week", kicker="GOLF · THIS WEEK", category="golf", member_ids=[2021, 2022], score=50.0),
        _single(3012, "Extra single 1", category="sports", score=45.0),
        _roundup("nhl-playoffs-2026-27", "NHL Playoffs", kicker="NHL · PLAYOFFS", category="hockey", member_ids=[2023, 2024], score=44.0),
        _single(3013, "Extra single 2", category="entertainment", score=43.0),
    ]


def test_representative_deck_hits_9_to_1_and_topic_mix_and_passes_seat_opening() -> None:
    deck = _representative_deck()
    mixed = apply_discover_opening_mix(deck, now=NOW)
    seating = seat_opening(mixed, now=NOW)
    assert seating.status == COMPLIANT, seating.detail

    top10 = seating.items[:10]
    assert sum(1 for c in top10 if _is_grouped_feed_card(c)) == 9
    assert sum(1 for c in top10 if c.get("type") == "futures") == 1
    assert sum(1 for c in top10 if c.get("type") in ("concept", "event")) == 0

    topics = Counter(classify_discover_opening_topic(c) for c in top10)
    assert topics[TOPIC_ODD] == 3
    assert 2 <= topics[TOPIC_ENTERTAINMENT] <= 3
    assert topics[TOPIC_SPORTS] == 2
    assert 1 <= topics[TOPIC_TECH_BUSINESS] <= 2
    assert topics[TOPIC_ENTERTAINMENT] + topics[TOPIC_TECH_BUSINESS] == 4
    assert topics[TOPIC_PWM] == 1
    assert classify_discover_opening_topic(top10[0]) != TOPIC_PWM
    # Decision 333: A — Seat 10 holds the grouped PWM card matching the Pacific date.
    assert _is_grouped_feed_card(top10[9])
    assert classify_discover_opening_topic(top10[9]) == TOPIC_PWM
    assert classify_discover_pwm_subtopic(top10[9]) == discover_opening_pwm_kind_for_date(NOW)

    # Single selected is the 95-pt non-conflict NFL Super Bowl Winner, never Russia/Ukraine (98)
    singles = [c for c in top10 if c.get("type") == "futures"]
    assert len(singles) == 1
    assert singles[0]["data"]["id"] == 3005

    # Decision 123-A: no two round-up cards adjacent from seat 11 onward
    for idx in range(OPENING_SEATS + 1, len(seating.items)):
        assert not (
            _is_roundup_bundle_card(seating.items[idx - 1])
            and _is_roundup_bundle_card(seating.items[idx])
        ), f"Adjacent round-up at seat {idx + 1}"

    # Strict idempotency
    mixed_twice = apply_discover_opening_mix(mixed, now=NOW)
    assert [
        (c.get("type"), (c.get("data") or {}).get("id")) for c in mixed_twice
    ] == [(c.get("type"), (c.get("data") or {}).get("id")) for c in mixed]


def test_concept_cards_and_live_games_never_enter_first_ten() -> None:
    deck = [
        _concept("concept:nba-finals", "NBA Finals Hub", live=False, score=99.0),
        _live_event(5001, "Live NBA Game", score=99.0),
        *_representative_deck(),
    ]
    mixed = apply_discover_opening_mix(deck, now=NOW)
    top10_ids = {(c.get("data") or {}).get("id") for c in mixed[:10]}
    assert "concept:nba-finals" not in top10_ids
    assert "concept:world-cup-2026" not in top10_ids
    assert 5001 not in top10_ids
    assert 4001 not in top10_ids
    assert "roundup:machinery-nba-night" not in top10_ids


def test_single_falls_back_to_conflict_only_when_no_other_single_qualifies() -> None:
    # Build a deck where every single futures card is a conflict/PWM market.
    deck = [
        _roundup("machinery-elon-musk-side-quests", "Musk", kicker="ODD · SIDE QUESTS", category="entertainment", member_ids=[1, 2], score=87.0),
        _roundup("machinery-long-shots", "Long Shots", kicker="ODD · LONG SHOTS", category="entertainment", member_ids=[3, 4], score=86.0),
        _roundup("machinery-white-christmas", "White Christmas", kicker="WEATHER · CHRISTMAS", category="weather", member_ids=[5, 6], score=85.0),
        _roundup("machinery-who-gets-engaged", "Engaged", kicker="ENTERTAINMENT · COUPLES", category="entertainment", member_ids=[7, 8], score=84.0),
        _roundup("machinery-2026-summed-up", "2026", kicker="CULTURE · 2026", category="entertainment", member_ids=[9, 10], score=83.0),
        _roundup("machinery-next-james-bond", "Bond", kicker="ENTERTAINMENT · JAMES BOND", category="entertainment", member_ids=[11, 12], score=82.0),
        _roundup("roundup-cfp-picture", "CFP", kicker="SPORTS · CFB", category="football", member_ids=[13, 14], score=81.0),
        _theme("story:ai", "AI", [15, 16], score=80.0),
        _roundup("by-november-30", "Deadlines", kicker="TECH · DEADLINES", category="tech", member_ids=[17, 18], score=79.0),
        _single(999, "Will Russia and Ukraine reach ceasefire?", category="geopolitics", score=98.0),
        _single(998, "Extra conflict market", category="politics", score=70.0),
        _theme("story:middle_east_conflict", "Middle East", [19, 20], score=95.0),
    ]
    mixed = apply_discover_opening_mix(deck, now=NOW)
    top10 = mixed[:10]
    singles = [c for c in top10 if c.get("type") == "futures"]
    assert len(singles) == 1
    assert singles[0]["data"]["id"] == 999
    assert sum(1 for c in top10 if classify_discover_opening_topic(c) == TOPIC_PWM) <= 1


def test_sparse_no_grouped_deck_returns_unchanged() -> None:
    singles_only = [_single(100 + i, f"Market {i}", category="sports", score=90 - i) for i in range(15)]
    out = apply_discover_opening_mix(singles_only, now=NOW)
    assert out is singles_only


@pytest.mark.asyncio
async def test_add_roundup_and_prewarm_bundle_apply_opening_mix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both runtime `add_roundup_feed_items(..., apply_opening_mix=True)` and prewarm
    `render_machinery_prewarm_bundle` emit the 329: A opening mix."""
    saved = dict(ROUNDUP_PRODUCERS)
    try:
        ROUNDUP_PRODUCERS.clear()

        async def _prod_odd(db, *, now=None):
            return RoundupMembers(
                members=[{"type": "market", "id": 8101, "destination": "/futures/8101", "card": {"id": 8101, "name": "Mars"}}],
                rows=[{"market_id": 8101, "outcome_id": 1, "label": "Mars", "probability": 0.4}],
                title="Musk Side Quests",
                kicker="ODD · SIDE QUESTS",
                destination_href="/collections/machinery-elon-musk-side-quests",
            )

        prod = RoundupProducer(
            slug="machinery-elon-musk-side-quests",
            name="Musk Side Quests",
            kind="roundup",
            category="entertainment",
            section_title="Side Quests",
            footer="",
            produce=_prod_odd,
            membership="computed-produced",
            relations=("same_subject",),
            level="member",
            rule={"producer": "container_machinery"},
            enabled=lambda: True,
        )
        ROUNDUP_PRODUCERS[prod.slug] = prod
        monkeypatch.setattr(
            "app.utils.roundup_containers.ensure_optional_roundup_candidates",
            lambda: None,
        )
        monkeypatch.setattr(
            "app.utils.roundup_containers.evaluate_roundup_producer",
            AsyncMock(return_value=(compose_roundup_feed_item(prod, await _prod_odd(None)), {"slug": prod.slug})),
        )

        base = _representative_deck()
        mixed_runtime = await add_roundup_feed_items(
            None,
            list(base),
            include_machinery=True,
            machinery_only=True,
            apply_opening_mix=True,
            now=NOW,
        )
        assert _is_grouped_feed_card(mixed_runtime[0])
        assert (mixed_runtime[0]["data"].get("collection_ref") or {}).get("slug") == "machinery-elon-musk-side-quests"
        assert seat_opening(mixed_runtime, now=NOW).status == COMPLIANT

        fi = compose_roundup_feed_item(prod, await _prod_odd(None))
        assert fi is not None
        bundle = render_machinery_prewarm_bundle(
            mach_base={
                "page_base_body": {"items": base, "total": len(base)},
                "page_base_key": "feed:pagebase:v1:test",
                "age_origin": NOW.timestamp(),
                "opening_seating": True,
                "limit": 20,
                "offset": 0,
                "cache_shape": {"limit": 20, "offset": 0, "event_pct": 0.15, "mode": "discover"},
            },
            produced=[fi],
            oldest_live_built_at=None,
            now_ts=NOW.timestamp(),
        )
        assert bundle is not None
        import json

        page_items = json.loads(bundle["page_json"])["items"]
        assert sum(1 for c in page_items[:10] if _is_grouped_feed_card(c)) == 9
        assert sum(1 for c in page_items[:10] if c.get("type") == "futures") == 1
        assert classify_discover_opening_topic(page_items[0]) != TOPIC_PWM
        assert classify_discover_pwm_subtopic(page_items[9]) == discover_opening_pwm_kind_for_date(NOW)
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)


def _two_day_pwm_deck(*, include_politics: bool = True, include_money: bool = True) -> list[dict]:
    """Deck with rich non-PWM groups plus configurable politics/world vs money groups."""
    cards: list[dict] = []
    if include_politics:
        cards.append(_theme("story:middle_east_conflict", "Middle East", [1001, 1002], score=98.0))
        cards.append(
            _roundup(
                "machinery-2028-presidential",
                "2028 Race",
                kicker="POLITICS · 2028 RACE",
                category="politics",
                member_ids=[1005, 1006],
                score=96.0,
            )
        )
    if include_money:
        cards.append(_theme("story:macro_rates", "Fed & Rates", [1003, 1004], score=90.0))
        cards.append(
            _roundup(
                "for-scale-us-recession-2026",
                "A Russia-Ukraine ceasefire by Nov 30: as likely as a US recession by end of 2026",
                kicker="FOR SCALE",
                category="cross-topic",
                member_ids=[1007, 1008],
                score=86.0,
            )
        )
    cards.extend(
        [
            _roundup("machinery-elon-musk-side-quests", "Musk Side Quests", kicker="ODD · SIDE QUESTS", category="entertainment", member_ids=[2001, 2002], score=87.0, relations=["same_subject", "sibling"]),
            _roundup("machinery-who-gets-engaged", "Celebrity Engagements", kicker="ENTERTAINMENT · COUPLES", category="entertainment", member_ids=[2003, 2004], score=87.0, relations=["same_window", "sibling"]),
            _roundup("machinery-2026-summed-up", "2026 Summed Up", kicker="CULTURE · 2026", category="entertainment", member_ids=[2005, 2006], score=85.0, relations=["same_window", "sibling"]),
            _single(3005, "NFL Super Bowl Winner", category="football", score=95.0),
            _roundup("roundup-cfp-picture", "College Football Playoff picture", kicker="SPORTS · CFB", category="football", member_ids=[2007, 2008], score=64.0),
            _roundup("machinery-long-shots", "Long Shots", kicker="ODD · LONG SHOTS", category="entertainment", member_ids=[2009, 2010], score=63.0, relations=["same_measure", "sibling"]),
            _roundup("machinery-white-christmas", "White Christmas", kicker="WEATHER · CHRISTMAS", category="weather", member_ids=[2011, 2012], score=80.0),
            _theme("story:ai", "AI", [2013, 2014], score=86.0),
            _roundup("machinery-next-james-bond", "Next James Bond", kicker="ENTERTAINMENT · JAMES BOND", category="entertainment", member_ids=[2015, 2016], score=82.0),
            _roundup("by-november-30", "Deadlines by Nov 30", kicker="TECH · DEADLINES", category="tech", member_ids=[2017, 2018], score=65.0),
            _single(3008, "OpenAI IPO Valuation", category="tech", score=74.0),
            _single(3012, "NBA Finals Winner", category="basketball", score=60.0),
            _roundup("by-december-31", "By December 31", kicker="SAME DEADLINE", category="cross-topic", member_ids=[2019, 2020], score=83.0),
            _single(3001, "Will Russia and Ukraine reach ceasefire?", category="geopolitics", score=98.0),
        ]
    )
    return cards


def test_seat10_alternates_by_pacific_date_across_midnight() -> None:
    day_a = datetime(2026, 11, 21, 23, 55, tzinfo=PACIFIC_TZ)
    day_b = datetime(2026, 11, 22, 0, 5, tzinfo=PACIFIC_TZ)
    kind_a = discover_opening_pwm_kind_for_date(day_a)
    kind_b = discover_opening_pwm_kind_for_date(day_b)
    assert {kind_a, kind_b} == {PWM_SUBTOPIC_POLITICS_WORLD, PWM_SUBTOPIC_MONEY}

    politics_day = day_a if kind_a == PWM_SUBTOPIC_POLITICS_WORLD else day_b
    money_day = day_b if politics_day == day_a else day_a

    out_pol = apply_discover_opening_mix(_two_day_pwm_deck(), now=politics_day)
    out_mon = apply_discover_opening_mix(_two_day_pwm_deck(), now=money_day)

    for out, expected_kind, expected_id_prefix in (
        (out_pol, PWM_SUBTOPIC_POLITICS_WORLD, "theme:story:middle_east_conflict:"),
        (out_mon, PWM_SUBTOPIC_MONEY, "theme:story:macro_rates:"),
    ):
        top10 = out[:10]
        assert sum(1 for c in top10 if _is_grouped_feed_card(c)) == 9
        assert sum(1 for c in top10 if c.get("type") == "futures") == 1
        assert sum(1 for c in top10 if classify_discover_opening_topic(c) == TOPIC_PWM) == 1
        assert classify_discover_opening_topic(top10[0]) != TOPIC_PWM
        assert _is_grouped_feed_card(top10[9])
        assert classify_discover_pwm_subtopic(top10[9]) == expected_kind
        assert str(top10[9]["data"]["id"]).startswith(expected_id_prefix)
        assert [c["data"]["id"] for c in out[10:]]  # remainder non-empty
        for i in range(11, len(out)):
            assert not (_is_roundup_bundle_card(out[i - 1]) and _is_roundup_bundle_card(out[i]))


def test_seat10_falls_back_to_other_pwm_kind_when_todays_kind_is_absent() -> None:
    politics_day = next(
        datetime(2026, 11, d, 12, 0, tzinfo=PACIFIC_TZ)
        for d in range(20, 25)
        if discover_opening_pwm_kind_for_date(datetime(2026, 11, d, 12, 0, tzinfo=PACIFIC_TZ))
        == PWM_SUBTOPIC_POLITICS_WORLD
    )
    money_day = politics_day + timedelta(days=1)

    only_money = apply_discover_opening_mix(
        _two_day_pwm_deck(include_politics=False, include_money=True), now=politics_day
    )
    assert classify_discover_pwm_subtopic(only_money[9]) == PWM_SUBTOPIC_MONEY
    assert sum(1 for c in only_money[:10] if _is_grouped_feed_card(c)) == 9

    only_politics = apply_discover_opening_mix(
        _two_day_pwm_deck(include_politics=True, include_money=False), now=money_day
    )
    assert classify_discover_pwm_subtopic(only_politics[9]) == PWM_SUBTOPIC_POLITICS_WORLD
    assert sum(1 for c in only_politics[:10] if _is_grouped_feed_card(c)) == 9


def test_seat10_falls_back_to_ordinary_mix_when_neither_pwm_kind_exists() -> None:
    deck = _two_day_pwm_deck(include_politics=False, include_money=False)
    # Remove any non-grouped conflict impact; by-december-31 is still in deck and must NOT fill Seat 10.
    out = apply_discover_opening_mix(deck, now=NOW)
    top10 = out[:10]
    topics = Counter(classify_discover_opening_topic(c) for c in top10)
    assert sum(1 for c in top10 if _is_grouped_feed_card(c)) == 9
    assert sum(1 for c in top10 if c.get("type") == "futures") == 1
    assert topics[TOPIC_PWM] == 0
    assert topics[TOPIC_ODD] == 3
    assert topics[TOPIC_ENTERTAINMENT] == 3
    assert topics[TOPIC_SPORTS] == 2
    assert topics[TOPIC_TECH_BUSINESS] == 2


def test_seat10_flex_slot_follows_feed_ranking_between_entertainment_and_tech() -> None:
    # Build two decks with identical candidates, flipping relative order of ent#3 vs tech#2.
    ent_3 = _roundup("machinery-next-james-bond", "Bond", kicker="ENTERTAINMENT · JAMES BOND", category="entertainment", member_ids=[2015, 2016], score=82.0)
    tech_2 = _roundup("by-november-30", "Deadlines by Nov 30", kicker="TECH · DEADLINES", category="tech", member_ids=[2017, 2018], score=65.0)
    core = [
        _theme("story:middle_east_conflict", "Middle East", [1001, 1002], score=98.0),
        _roundup("machinery-elon-musk-side-quests", "Musk", kicker="ODD · SIDE QUESTS", category="entertainment", member_ids=[2001, 2002], score=87.0),
        _roundup("machinery-long-shots", "Long Shots", kicker="ODD · LONG SHOTS", category="entertainment", member_ids=[2009, 2010], score=86.0),
        _roundup("machinery-white-christmas", "White Christmas", kicker="WEATHER · CHRISTMAS", category="weather", member_ids=[2011, 2012], score=85.0),
        _roundup("machinery-who-gets-engaged", "Engaged", kicker="ENTERTAINMENT · COUPLES", category="entertainment", member_ids=[2003, 2004], score=84.0),
        _roundup("machinery-2026-summed-up", "2026", kicker="CULTURE · 2026", category="entertainment", member_ids=[2005, 2006], score=83.0),
        _roundup("roundup-cfp-picture", "CFP", kicker="SPORTS · CFB", category="football", member_ids=[2007, 2008], score=82.0),
        _roundup("machinery-ai-and-big-tech-race", "AI Race", kicker="TECH · AI", category="tech", member_ids=[2021, 2022], score=81.0),
        _single(3005, "NFL Super Bowl Winner", category="football", score=95.0),
        _single(3012, "NBA Finals Winner", category="basketball", score=60.0),
    ]

    ent_first = apply_discover_opening_mix([*core, ent_3, tech_2], now=NOW)[:10]
    tech_first = apply_discover_opening_mix([*core, tech_2, ent_3], now=NOW)[:10]

    t_ent = Counter(classify_discover_opening_topic(c) for c in ent_first)
    t_tech = Counter(classify_discover_opening_topic(c) for c in tech_first)
    assert (t_ent[TOPIC_ENTERTAINMENT], t_ent[TOPIC_TECH_BUSINESS]) == (3, 1)
    assert (t_tech[TOPIC_ENTERTAINMENT], t_tech[TOPIC_TECH_BUSINESS]) == (2, 2)


def test_pwm_subtopic_split_and_non_pwm_guards() -> None:
    me = _theme("story:middle_east_conflict", "Middle East", [1, 2])
    race28 = _roundup("machinery-2028-presidential", "2028", kicker="POLITICS · 2028 RACE", category="politics", member_ids=[3, 4])
    announce = _roundup("who-announces-before-2027", "Who announces", kicker="2028", category="politics", member_ids=[5, 6])
    fed_theme = _theme("story:macro_rates", "Fed & Rates", [7, 8])
    fed_ru = _roundup("machinery-fed-and-macro", "Fed & Macro", kicker="ECONOMICS · FEDERAL RESERVE", category="economics", member_ids=[9, 10])
    rec = _roundup("for-scale-us-recession-2026", "A Russia-Ukraine ceasefire by Nov 30: as likely as a US recession by end of 2026", kicker="FOR SCALE", category="cross-topic", member_ids=[11, 12])
    dec31 = _roundup("by-december-31", "By December 31", kicker="SAME DEADLINE", category="cross-topic", member_ids=[13, 14])
    ufc = _theme("story:ufc_events", "UFC", [15, 16])

    assert classify_discover_pwm_subtopic(me) == PWM_SUBTOPIC_POLITICS_WORLD
    assert classify_discover_pwm_subtopic(race28) == PWM_SUBTOPIC_POLITICS_WORLD
    assert classify_discover_pwm_subtopic(announce) == PWM_SUBTOPIC_POLITICS_WORLD
    assert classify_discover_pwm_subtopic(fed_theme) == PWM_SUBTOPIC_MONEY
    assert classify_discover_pwm_subtopic(fed_ru) == PWM_SUBTOPIC_MONEY
    assert classify_discover_pwm_subtopic(rec) == PWM_SUBTOPIC_MONEY
    assert classify_discover_opening_topic(dec31) == TOPIC_PWM
    assert classify_discover_pwm_subtopic(dec31) is None
    assert classify_discover_opening_topic(ufc) == TOPIC_SPORTS
    assert classify_discover_pwm_subtopic(ufc) is None


def test_333a_preserves_all_cards_and_is_idempotent_both_days() -> None:
    day1 = datetime(2026, 11, 21, 12, 0, tzinfo=PACIFIC_TZ)
    day2 = day1 + timedelta(days=1)
    for dt in (day1, day2):
        deck = _two_day_pwm_deck()
        in_ids = sorted(str((c.get("data") or {}).get("id")) for c in deck)
        out1 = apply_discover_opening_mix(deck, now=dt)
        out2 = apply_discover_opening_mix(out1, now=dt)
        out_ids = sorted(str((c.get("data") or {}).get("id")) for c in out1)
        assert len(out1) == len(deck)
        assert out_ids == in_ids
        assert [
            (c.get("type"), (c.get("data") or {}).get("id")) for c in out2
        ] == [(c.get("type"), (c.get("data") or {}).get("id")) for c in out1]
