"""Tests for #11942: refuse out-of-order deadline/threshold ladders, serve legs with own age, count ladder_refused, and log daily sentinel line."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks.flow_sentinel import discover_ladder_order_failures
from app.tasks.polymarket import sub_market_metadata
from app.utils.deadline_family_story import (
    build_deadline_member_contract,
    build_polymarket_submarket_deadline_contract,
    verify_and_select_deadline_family,
)
from app.utils.discover_bundles import assemble_deadline_family_bundles
from app.utils.discover_card_archetypes import classify_discover_card_archetype
from app.utils.feed_quality_debug import diagnose_feed_items, summarize_feed_diagnostics
from app.utils.outcome_display import (
    drop_incoherent_ladder_outcomes,
    ladder_rungs_out_of_order,
    ladder_treatment_collapsed,
)

NOW = datetime(2026, 11, 3, 20, 0, 0, tzinfo=timezone.utc)


def _make_contract(
    market_id: int,
    name: str,
    group_item_title: str,
    resolution_iso: str,
    yes_prob: float,
    observed_iso: str,
) -> dict:
    res_dt = datetime.fromisoformat(resolution_iso.replace("Z", "+00:00"))
    obs_dt = datetime.fromisoformat(observed_iso.replace("Z", "+00:00"))
    obs_epoch = int(obs_dt.timestamp())
    description = (
        f'This market will resolve to "Yes" if the Kansas Governor loser concedes '
        f"between market creation and {group_item_title}, 2026, 11:59 PM ET. "
        f'Otherwise, this market will resolve to "No".\n\n'
        f"The primary resolution source for this market will be official statements "
        f"and credible media reporting."
    )
    event = SimpleNamespace(
        id="1304497",
        title="Kansas Governor loser concedes by...?",
        neg_risk=False,
        active=True,
        closed=False,
        markets=[SimpleNamespace(), SimpleNamespace()],
    )
    market = SimpleNamespace(
        id=str(market_id),
        question=name,
        description=description,
        group_item_title=group_item_title,
        end_date=res_dt,
        closed=False,
        active=True,
        uma_resolution_status="unresolved",
        outcome_prices=[yes_prob, round(1.0 - yes_prob, 4)],
        outcomes=["Yes", "No"],
    )
    meta = (
        sub_market_metadata(
            event_id=event.id,
            matchup_title=None,
            deadline_rule_contract=build_polymarket_submarket_deadline_contract(
                event, market
            ),
        )
        or {}
    )
    meta["polymarket_event_id"] = "1304497"
    meta["market_count"] = 2
    contract = build_deadline_member_contract(
        market_id=market_id,
        name=name,
        source="polymarket",
        external_id=f"0x{market_id:064x}",
        group_id="polymarket:1304497",
        status="open",
        resolution_date=res_dt.isoformat(),
        description=description,
        market_metadata=meta,
        outcomes=[
            {
                "id": market_id * 10 + 1,
                "name": "Yes",
                "external_id": f"cond-{market_id}-yes",
                "current_probability": yes_prob,
                "probability_change_24h": None,
                "price_observed_epoch": obs_epoch,
                "rank": 1,
            },
            {
                "id": market_id * 10 + 2,
                "name": "No",
                "external_id": f"cond-{market_id}-no",
                "current_probability": round(1.0 - yes_prob, 4),
                "probability_change_24h": None,
                "price_observed_epoch": obs_epoch,
                "rank": 2,
            },
        ],
        now=NOW,
    )
    assert contract is not None
    return contract


def test_kansas_concedes_two_rung_reversal_refused_and_expanded_to_plain_legs():
    outcomes = [
        {"name": "November 3", "probability": 0.90, "rendered_percent": 90},
        {"name": "November 4", "probability": 0.815, "rendered_percent": 82},
    ]
    assert (
        ladder_rungs_out_of_order(
            outcomes,
            lambda o: o["name"],
            lambda o: o["probability"],
            "Kansas Governor loser concedes?",
        )
        is True
    )
    assert (
        ladder_treatment_collapsed(
            outcomes,
            lambda o: o["name"],
            lambda o: o["probability"],
            "Kansas Governor loser concedes?",
        )
        is True
    )

    card = classify_discover_card_archetype(
        name="Kansas Governor loser concedes?",
        category="politics",
        outcomes=outcomes,
        outcome_count=2,
        group_id="polymarket:1304497",
        ladder_treatment_refused=True,
        resolution_date="2026-11-05T04:59:00+00:00",
    )
    assert card["threshold_points"] == []
    assert card["suggested_format"] != "threshold_heatmap"
    assert card["distribution_order"] == "probability"
    assert card["ladder_treatment_refused"] is True

    feed_item = {
        "type": "futures",
        "score": 88,
        "headline": "November 3 leads at 90%",
        "reason": "Big odds movement",
        "_refused_ladder_leg_ages": {
            "November 3": "2026-11-03T18:10:00+00:00",
            "November 4": "2026-11-03T19:45:00+00:00",
        },
        "data": {
            "id": 68845561,
            "name": "Kansas Governor loser concedes?",
            "source": "polymarket",
            "group_id": "polymarket:1304497",
            "group_type": None,
            "llm_sport_category": "politics",
            "status": "open",
            "price_observed_at": "2026-11-03T19:45:00+00:00",
            "top_outcomes": outcomes,
            "outcome_count": 2,
            "discover_card": card,
        },
    }

    served = assemble_deadline_family_bundles([feed_item], now=NOW)
    assert len(served) == 2
    assert [it["data"]["name"] for it in served] == [
        "Kansas Governor loser concedes by November 3?",
        "Kansas Governor loser concedes by November 4?",
    ]
    assert [it["data"]["leg_key"] for it in served] == [
        "November 3",
        "November 4",
    ]
    assert [it["data"]["price_observed_at"] for it in served] == [
        "2026-11-03T18:10:00+00:00",
        "2026-11-03T19:45:00+00:00",
    ]
    assert all(
        it["data"]["discover_card"]["suggested_format"] == "binary_probability"
        for it in served
    )

    summary = summarize_feed_diagnostics(diagnose_feed_items(served, now=NOW))
    assert summary["ladder_refused"] == 1


def test_within_whole_number_rounding_is_not_refused():
    outcomes = [
        {"name": "November 3", "probability": 0.816},
        {"name": "November 4", "probability": 0.815},
    ]
    assert (
        ladder_rungs_out_of_order(
            outcomes,
            lambda o: o["name"],
            lambda o: o["probability"],
            "Kansas Governor loser concedes by...?",
        )
        is False
    )
    c1 = _make_contract(
        101,
        "Kansas Governor loser concedes by November 3?",
        "November 3",
        "2026-11-04T04:59:00Z",
        0.816,
        "2026-11-03T18:00:00Z",
    )
    c2 = _make_contract(
        102,
        "Kansas Governor loser concedes by November 4?",
        "November 4",
        "2026-11-05T04:59:00Z",
        0.815,
        "2026-11-03T19:00:00Z",
    )
    family, err = verify_and_select_deadline_family([c1, c2], now=NOW)
    assert err is None
    assert family is not None


def test_deadline_family_out_of_order_refuses_bundle_and_serves_plain_legs():
    c1 = _make_contract(
        201,
        "Kansas Governor loser concedes by November 3?",
        "November 3",
        "2026-11-04T04:59:00Z",
        0.90,
        "2026-11-03T18:00:00Z",
    )
    c2 = _make_contract(
        202,
        "Kansas Governor loser concedes by November 4?",
        "November 4",
        "2026-11-05T04:59:00Z",
        0.815,
        "2026-11-03T19:30:00Z",
    )
    family, err = verify_and_select_deadline_family([c1, c2], now=NOW)
    assert family is None
    assert err == "ladder_refused"

    parent_item = {
        "type": "futures",
        "score": 90,
        "headline": "November 3 leads at 90%",
        "reason": "Big odds movement",
        "data": {
            "id": 68845561,
            "name": "Kansas Governor loser concedes?",
            "source": "polymarket",
            "group_id": "polymarket:1304497",
            "group_type": "polymarket_event",
            "llm_sport_category": "politics",
            "status": "open",
            "price_observed_at": "2026-11-03T19:30:00Z",
            "top_outcomes": [
                {"name": "November 3", "probability": 0.90},
                {"name": "November 4", "probability": 0.815},
            ],
            "discover_card": {"ladder_treatment_refused": True},
        },
        "_grouped_members": [
            {
                "type": "futures",
                "score": 82,
                "headline": "90% chance",
                "reason": "Resolving soon",
                "data": {
                    "id": 201,
                    "name": "Kansas Governor loser concedes by November 3?",
                    "source": "polymarket",
                    "group_id": "polymarket:1304497",
                    "group_type": "polymarket_sub_market",
                    "llm_sport_category": "politics",
                    "status": "open",
                    "price_observed_at": "2026-11-03T18:00:00Z",
                    "top_outcomes": [{"name": "Yes", "probability": 0.90}],
                    "deadline_member": c1,
                },
            },
            {
                "type": "futures",
                "score": 80,
                "headline": "82% chance",
                "reason": "Resolving soon",
                "data": {
                    "id": 202,
                    "name": "Kansas Governor loser concedes by November 4?",
                    "source": "polymarket",
                    "group_id": "polymarket:1304497",
                    "group_type": "polymarket_sub_market",
                    "llm_sport_category": "politics",
                    "status": "open",
                    "price_observed_at": "2026-11-03T19:30:00Z",
                    "top_outcomes": [{"name": "Yes", "probability": 0.815}],
                    "deadline_member": c2,
                },
            },
        ],
    }

    served = assemble_deadline_family_bundles([parent_item], now=NOW)
    assert [it["data"]["id"] for it in served] == [201, 202]
    assert [it["data"]["price_observed_at"] for it in served] == [
        "2026-11-03T18:00:00Z",
        "2026-11-03T19:30:00Z",
    ]
    summary = summarize_feed_diagnostics(diagnose_feed_items(served, now=NOW))
    assert summary["ladder_refused"] == 1


def test_denver_december_snow_ladder_refusal_and_drop_incoherent_rung():
    from app.routes.futures import _format_market_detail, _format_market_summary

    outcomes = [
        {"id": 246319890, "name": "Above 2 inches", "probability": 0.795},
        {"id": 246319889, "name": "Above 6 inches", "probability": 0.64},
        {"id": 246319891, "name": "Above 4 inches", "probability": 0.595},
        {"id": 246319892, "name": "Above 8 inches", "probability": 0.40},
        {"id": 246319893, "name": "Above 10 inches", "probability": 0.37},
        {"id": 246319894, "name": "Above 12 inches", "probability": 0.28},
    ]
    assert ladder_rungs_out_of_order(
        outcomes,
        lambda o: o["name"],
        lambda o: o["probability"],
        "Snow in Denver in Dec 2026?",
    ) is True

    cleaned = drop_incoherent_ladder_outcomes(
        outcomes,
        lambda o: o["name"],
        lambda o: o["probability"],
        "Snow in Denver in Dec 2026?",
    )
    cleaned_names = [o["name"] for o in cleaned]
    assert "Above 6 inches" not in cleaned_names
    assert cleaned_names == [
        "Above 2 inches",
        "Above 4 inches",
        "Above 8 inches",
        "Above 10 inches",
        "Above 12 inches",
    ]

    meta = classify_discover_card_archetype(
        name="Snow in Denver in Dec 2026?",
        category="weather",
        outcomes=cleaned,
        outcome_count=len(cleaned),
        group_id="kalshi:KXDENSNOWM-26DEC",
        group_type=None,
        canonical_market_key=None,
    )
    assert meta["suggested_format"] == "threshold_heatmap"
    assert [p["label"] for p in meta["threshold_points"]] == [
        "Above 2 inches",
        "Above 4 inches",
        "Above 8 inches",
        "Above 10 inches",
        "Above 12 inches",
    ]

    stale_ts = datetime(2026, 10, 30, 19, 45, tzinfo=timezone.utc)
    fresh_ts = datetime(2026, 11, 3, 19, 45, tzinfo=timezone.utc)
    orm_outcomes = [
        SimpleNamespace(
            id=o["id"],
            name=o["name"],
            external_id=f"KXDENSNOWM-26DEC-{o['id']}",
            current_probability=o["probability"],
            current_american_odds=None,
            rank=idx + 1,
            rank_change_24h=None,
            probability_change_24h=None,
            opening_probability=o["probability"],
            opening_american_odds=None,
            is_winner=False,
            resolution_source=None,
            last_updated=stale_ts if o["name"] == "Above 6 inches" else fresh_ts,
            price_changed_at=stale_ts if o["name"] == "Above 6 inches" else fresh_ts,
            outcome_metadata={},
        )
        for idx, o in enumerate(outcomes)
    ]
    market = SimpleNamespace(
        id=65536371,
        name="Snow in Denver in Dec 2026?",
        description=None,
        sport=None,
        sport_id=None,
        event_id=None,
        category="weather",
        llm_sport_category="weather",
        status="open",
        source="kalshi",
        external_id="KXDENSNOWM-26DEC",
        market_type="quantity",
        market_tier=2,
        mutually_exclusive=False,
        commence_time=None,
        resolution_date=datetime(2027, 1, 1, 0, 0, tzinfo=timezone.utc),
        outcomes=orm_outcomes,
        category_tags=["weather"],
        created_at=fresh_ts,
        updated_at=fresh_ts,
        group_id="kalshi:KXDENSNOWM-26DEC",
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        market_metadata={},
    )
    summary = _format_market_summary(market)
    assert "Above 6 inches" not in [o["name"] for o in summary["top_outcomes"]]

    detail = _format_market_detail(market)
    assert detail["ladder_treatment_refused"] is True
    assert detail["lead_outcome_id"] is None
    assert len(detail["outcomes"]) == 6
    by_name = {o["name"]: o for o in detail["outcomes"]}
    assert by_name["Above 6 inches"]["probability"] == pytest.approx(0.64)
    assert by_name["Above 6 inches"]["last_updated"] == stale_ts.isoformat()


def test_flow_sentinel_detects_out_of_order_ladder_and_counts_refused():
    items = [
        {
            "type": "futures",
            "data": {
                "id": 68845561,
                "name": "Kansas Governor loser concedes?",
                "discover_card": {
                    "suggested_format": "threshold_heatmap",
                    "ladder_treatment_refused": False,
                    "threshold_points": [
                        {
                            "source": "date_bucket",
                            "label": "November 3",
                            "value": 20261103,
                            "probability": 0.90,
                        },
                        {
                            "source": "date_bucket",
                            "label": "November 4",
                            "value": 20261104,
                            "probability": 0.815,
                        },
                    ],
                },
            },
        },
        {
            "type": "futures",
            "data": {
                "id": 999999,
                "name": "Refused ladder leg",
                "discover_card": {
                    "suggested_format": "binary_probability",
                    "ladder_treatment_refused": True,
                    "threshold_points": [],
                },
            },
        },
    ]
    failures, refused_count = discover_ladder_order_failures(items)
    assert refused_count == 1
    assert len(failures) == 1
    assert failures[0]["market_id"] == 68845561
