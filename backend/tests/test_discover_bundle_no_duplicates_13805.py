"""#13805: A grouped card never repeats a market, and never pairs a field's
leader with that leader's own yes-or-no binary market as two rows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.feed import _dedupe_futures_by_group_id
from app.tasks.polymarket import sub_market_metadata
from app.utils.deadline_family_story import (
    build_deadline_member_contract,
    build_polymarket_submarket_deadline_contract,
)
from app.utils.discover_bundles import (
    _sanitize_bundle_members,
    assemble_awards_theme_bundles,
    assemble_deadline_family_bundles,
    assemble_discover_comparison_bundles,
    assemble_story_theme_bundles,
    assemble_swings_theme_bundles,
)


def _time_field_market(score: float = 87.0) -> dict:
    return {
        "type": "futures",
        "score": score,
        "reason": "James Talarico (29%) leads TIME Person of the Year 2026",
        "headline": "James Talarico leads at 29%",
        "_sort_time": 100.0,
        "data": {
            "id": 27467306,
            "name": "TIME Person of the Year 2026",
            "llm_sport_category": "entertainment",
            "source": "polymarket",
            "market_type": "field",
            "status": "open",
            "outcome_count": 35,
            "group_id": "polymarket:528018",
            "group_type": "polymarket_event",
            "top_outcomes": [
                {"id": 130735777, "name": "James Talarico", "probability": 0.2925, "rendered_percent": 29},
                {"id": 260026199, "name": "Abdul El-Sayed", "probability": 0.225, "rendered_percent": 23},
                {"id": 130735781, "name": "Zohran Mamdani", "probability": 0.205, "rendered_percent": 21},
            ],
            "discover_card": {"suggested_format": "outcome_distribution"},
        },
    }


def _time_binary_market(
    market_id: int = 27467317,
    candidate: str = "James Talarico",
    prob: float = 0.29,
    score: float = 75.0,
) -> dict:
    return {
        "type": "futures",
        "score": score,
        "reason": f"{int(round(prob * 100))}% chance {candidate}",
        "headline": f"{candidate} at {int(round(prob * 100))}%",
        "_sort_time": float(market_id),
        "data": {
            "id": market_id,
            "name": f"Will {candidate} be TIME Person of the Year 2026?",
            "llm_sport_category": "entertainment",
            "source": "polymarket",
            "market_type": "unshaped",
            "status": "open",
            "outcome_count": 2,
            "group_id": "polymarket:528018",
            "group_type": "polymarket_sub_market",
            "top_outcomes": [
                {"id": market_id * 10 + 1, "name": "Yes", "probability": prob, "rendered_percent": int(round(prob * 100))},
                {"id": market_id * 10 + 2, "name": "No", "probability": 1 - prob, "rendered_percent": 100 - int(round(prob * 100))},
            ],
            "discover_card": {"suggested_format": "binary_probability"},
        },
    }


def _assert_grouped_card_invariants(bundle: dict) -> None:
    assert bundle["type"] == "bundle"
    members = bundle["data"]["items"]
    ids = [m["data"]["id"] for m in members]
    # 1. No repeated market inside the grouped card
    assert len(ids) == len(set(ids)), f"Duplicate market ids in bundle: {ids}"
    # 2. If only 1 distinct row remains, a grouped card must not form
    assert len(members) >= 2
    # 3. Never pair a field's leader with that leader's own yes-or-no binary market
    sanitized_again = _sanitize_bundle_members(members)
    assert [m["data"]["id"] for m in sanitized_again] == ids


def test_dedupe_futures_by_group_id_is_idempotent_across_dual_passes_and_never_repeats() -> None:
    """Reproduces the dual strict/broadened pass mutation in feed.py (#13805)."""
    parent = _time_field_market(score=87.0)
    talarico_bin = _time_binary_market(27467317, "James Talarico", 0.29, score=75.0)
    el_sayed_bin = _time_binary_market(27467318, "Abdul El-Sayed", 0.225, score=70.0)

    strict_items = [parent, talarico_bin]
    relaxed_pool = [parent, talarico_bin, el_sayed_bin]

    strict_deduped = _dedupe_futures_by_group_id(strict_items)
    relaxed_deduped = _dedupe_futures_by_group_id(relaxed_pool)

    strict_ids = [m["data"]["id"] for m in strict_deduped[0].get("_grouped_members", [])]
    relaxed_ids = [m["data"]["id"] for m in relaxed_deduped[0].get("_grouped_members", [])]
    assert strict_ids == [27467317]
    assert relaxed_ids == [27467317, 27467318]
    assert len(relaxed_ids) == len(set(relaxed_ids))


def test_time_person_of_the_year_specimen_refuses_duplicate_and_leader_binary() -> None:
    """Live bug #13805: 27467306 + repeated 27467317 collapses instead of forming a 3-row 29% card."""
    survivor = _time_field_market()
    dup_bin_a = _time_binary_market(27467317, "James Talarico", 0.29)
    dup_bin_b = _time_binary_market(27467317, "James Talarico", 0.29)
    survivor["_grouped_members"] = [dup_bin_a, dup_bin_b]

    out = assemble_awards_theme_bundles([survivor])
    assert len(out) == 1
    # Only the field survives sanitization (< 2 rows), so NO bundle is emitted.
    assert out[0]["type"] == "futures"
    assert out[0]["data"]["id"] == 27467306


def test_time_person_of_the_year_with_non_leader_candidate_drops_only_leader_binary() -> None:
    survivor = _time_field_market()
    dup_bin_a = _time_binary_market(27467317, "James Talarico", 0.29)
    dup_bin_b = _time_binary_market(27467317, "James Talarico", 0.29)
    other_bin = _time_binary_market(27467325, "Pope Leo XIV", 0.14)
    survivor["_grouped_members"] = [dup_bin_a, dup_bin_b, other_bin]

    out = assemble_awards_theme_bundles([survivor])
    assert len(out) == 1
    assert out[0]["type"] == "bundle"
    _assert_grouped_card_invariants(out[0])
    assert [m["data"]["id"] for m in out[0]["data"]["items"]] == [27467306, 27467325]


@pytest.mark.parametrize("assembler_name", ["comparison", "story", "awards", "deadline", "swings"])
def test_every_grouped_card_bundler_enforces_no_duplicates_and_no_leader_binary(assembler_name: str) -> None:
    if assembler_name == "awards":
        survivor = _time_field_market()
        survivor["_grouped_members"] = [
            _time_binary_market(27467317, "James Talarico", 0.29),
            _time_binary_market(27467317, "James Talarico", 0.29),
            _time_binary_market(27467325, "Pope Leo XIV", 0.14),
            _time_binary_market(27467325, "Pope Leo XIV", 0.14),
        ]
        out = assemble_awards_theme_bundles([survivor])
    elif assembler_name == "story":
        field = _time_field_market(score=95.0)
        field["data"]["llm_sport_category"] = "politics"
        field["data"]["name"] = "2028 US Presidential Nominee"
        field["data"]["top_outcomes"][0]["name"] = "Gavin Newsom"
        field["_quality_story_key"] = "story:us_2028_election"
        leader_bin = _time_binary_market(91002, "Will Gavin Newsom win 2028 US Presidential Nominee?", 0.29, score=88.0)
        leader_bin["data"]["name"] = "Will Gavin Newsom be 2028 US Presidential Nominee?"
        leader_bin["data"]["llm_sport_category"] = "politics"
        leader_bin["_quality_story_key"] = "story:us_2028_election"
        other = _time_binary_market(91003, "JD Vance", 0.24, score=84.0)
        other["data"]["name"] = "Will JD Vance be 2028 US Presidential Nominee?"
        other["data"]["llm_sport_category"] = "politics"
        other["_quality_story_key"] = "story:us_2028_election"
        out = assemble_story_theme_bundles([field, leader_bin, other, dict(other)])
    elif assembler_name == "comparison":
        m1 = {
            "type": "futures",
            "score": 85.0,
            "reason": "r",
            "headline": "OpenAI IPO Closing Market Cap",
            "_sort_time": 1.0,
            "data": {
                "id": 701,
                "name": "OpenAI IPO Closing Market Cap",
                "llm_sport_category": "tech",
                "source": "kalshi",
                "status": "open",
                "discover_card": {
                    "suggested_format": "threshold_heatmap",
                    "bundle_candidate": True,
                    "comparison_theme": "ipo_valuation",
                    "threshold_points": [
                        {"label": "$500B", "value": 500, "probability": 0.6, "source": "outcome"},
                        {"label": "$1T", "value": 1000, "probability": 0.3, "source": "outcome"},
                    ],
                },
            },
        }
        m2 = {
            "type": "futures",
            "score": 82.0,
            "reason": "r",
            "headline": "Anthropic IPO Closing Market Cap",
            "_sort_time": 2.0,
            "data": {
                "id": 702,
                "name": "Anthropic IPO Closing Market Cap",
                "llm_sport_category": "tech",
                "source": "kalshi",
                "status": "open",
                "discover_card": {
                    "suggested_format": "threshold_heatmap",
                    "bundle_candidate": True,
                    "comparison_theme": "ipo_valuation",
                    "threshold_points": [
                        {"label": "$250B", "value": 250, "probability": 0.7, "source": "outcome"},
                        {"label": "$500B", "value": 500, "probability": 0.4, "source": "outcome"},
                    ],
                },
            },
        }
        out = assemble_discover_comparison_bundles([m1, dict(m1), m2])
    elif assembler_name == "deadline":
        now_dl = datetime(2026, 10, 14, 23, 47, 16, tzinfo=timezone.utc)
        obs_epoch = int(datetime(2026, 10, 14, 13, 20, 41, tzinfo=timezone.utc).timestamp())
        rule_oct = (
            'This market will resolve to "Yes" if Zacharia issues a public apology between '
            "market creation and October 31, 2026, 11:59 PM ET. Otherwise, this market will "
            'resolve to "No".\n\n'
            "A public apology is defined as any unambiguous statement of regret or apology "
            "made by Zacharia in a public forum, including social media posts, interviews, "
            "press releases, or public appearances.\n\n"
            "The primary resolution source for this market will be official statements from "
            "Zacharia and credible media reporting."
        )
        rule_dec = (
            'This market will resolve to "Yes" if Zacharia issues a public apology between '
            "market creation and December 31, 2026, 11:59 PM ET. Otherwise, this market will "
            'resolve to "No".\n\n'
            "A public apology is defined as any unambiguous statement of regret or apology "
            "made by Zacharia in a public forum, including social media posts, interviews, "
            "press releases, or public appearances.\n\n"
            "The primary resolution source for this market will be official statements from "
            "Zacharia and credible media reporting."
        )
        ev_stub = SimpleNamespace(
            id="256241",
            title="Zacharia issues public apology by...?",
            neg_risk=False,
            active=True,
            closed=False,
            markets=[SimpleNamespace(), SimpleNamespace()],
        )

        def _dl_meta(question: str, description: str, group_item_title: str, end_date_iso: str) -> dict:
            m_stub = SimpleNamespace(
                id="m1",
                question=question,
                description=description,
                group_item_title=group_item_title,
                end_date=datetime.fromisoformat(end_date_iso),
                closed=False,
                active=True,
                uma_resolution_status="unresolved",
                outcome_prices=[0.1, 0.9],
                outcomes=["Yes", "No"],
            )
            return (
                sub_market_metadata(
                    event_id=ev_stub.id,
                    matchup_title=None,
                    deadline_rule_contract=build_polymarket_submarket_deadline_contract(ev_stub, m_stub),
                )
                or {}
            )

        oct_iso = "2026-11-01T03:59:00+00:00"
        dec_iso = "2027-01-01T04:59:00+00:00"
        c1 = build_deadline_member_contract(
            market_id=801,
            name="Zacharia issues public apology by October 31?",
            source="polymarket",
            external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
            group_id="polymarket:256241",
            status="open",
            resolution_date=oct_iso,
            description=rule_oct,
            market_metadata=_dl_meta("Zacharia issues public apology by October 31?", rule_oct, "October 31", oct_iso),
            outcomes=[
                {"id": 8011, "name": "Yes", "external_id": "yes-801", "current_probability": 0.25, "price_observed_epoch": obs_epoch, "rank": 2},
                {"id": 8012, "name": "No", "external_id": "no-801", "current_probability": 0.75, "price_observed_epoch": obs_epoch, "rank": 1},
            ],
            now=now_dl,
        )
        c2 = build_deadline_member_contract(
            market_id=802,
            name="Zacharia issues public apology by December 31?",
            source="polymarket",
            external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
            group_id="polymarket:256241",
            status="open",
            resolution_date=dec_iso,
            description=rule_dec,
            market_metadata=_dl_meta("Zacharia issues public apology by December 31?", rule_dec, "December 31", dec_iso),
            outcomes=[
                {"id": 8021, "name": "Yes", "external_id": "yes-802", "current_probability": 0.55, "price_observed_epoch": obs_epoch, "rank": 2},
                {"id": 8022, "name": "No", "external_id": "no-802", "current_probability": 0.45, "price_observed_epoch": obs_epoch, "rank": 1},
            ],
            now=now_dl,
        )
        assert c1 is not None and c2 is not None
        d1 = {
            "type": "futures",
            "score": 80.0,
            "reason": "r",
            "headline": "Oct 31",
            "_sort_time": 1.0,
            "data": {
                "id": 801,
                "name": "Zacharia issues public apology by October 31?",
                "source": "polymarket",
                "group_id": "polymarket:256241",
                "group_type": "polymarket_sub_market",
                "outcome_count": 2,
                "deadline_member": c1,
            },
        }
        d2 = {
            "type": "futures",
            "score": 78.0,
            "reason": "r",
            "headline": "Dec 31",
            "_sort_time": 2.0,
            "data": {
                "id": 802,
                "name": "Zacharia issues public apology by December 31?",
                "source": "polymarket",
                "group_id": "polymarket:256241",
                "group_type": "polymarket_sub_market",
                "outcome_count": 2,
                "deadline_member": c2,
            },
        }
        d1["_grouped_members"] = [dict(d1), d2, dict(d2)]
        out = assemble_deadline_family_bundles([d1], now=now_dl)
    else:
        s1 = _time_field_market(score=92.0)
        s1["data"]["top_outcomes"][0]["probability_change_24h"] = 0.25
        s2 = _time_binary_market(27467317, "James Talarico", 0.29, score=86.0)
        s2["data"]["top_outcomes"][0]["probability_change_24h"] = 0.22
        s3 = _time_binary_market(27467325, "Pope Leo XIV", 0.22, score=81.0)
        s3["data"]["top_outcomes"][0]["probability_change_24h"] = 0.19
        out = assemble_swings_theme_bundles([s1, s2, s3, dict(s3)])

    bundles = [it for it in out if it.get("type") == "bundle"]
    assert bundles, f"Expected a bundle from assembler={assembler_name}"
    for bundle in bundles:
        _assert_grouped_card_invariants(bundle)
