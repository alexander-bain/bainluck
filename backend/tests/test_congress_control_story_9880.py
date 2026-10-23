"""Regression tests for US Congress control story grouping (#9880 / #9237 / #10354).

Covers Acceptance Cases A1-A11 from FABLE-CONGRESS-GROUPING-HANDOFF.md /
ACCEPTANCE-CASES.md and the mandatory technical tightening controls from
CONGRESS-SCOPING-REVIEW.md:
- Kalshi provenance + exact CONTROL(S|H)-<YYYY> anchor identity (Rule S)
- Inconsistent carried identity, wrong source, malformed anchor, title/chamber mismatch
- Explicit persisted-key precedence and forged-persisted-key rejection
- Exact chamber completeness (1 Senate + 1 House per edition; 2-Senate, 2-House,
  and conflicting same-chamber clusters fail closed and preserve standalone items)
- Upstream story-cap of 2 + overflow reserve interaction
"""

from __future__ import annotations

import copy
from typing import Any

from app.utils.congress_control_story import (
    US_CONGRESS_CONTROL_QUESTION,
    US_CONGRESS_CONTROL_TITLE,
    congress_control_bundle_members,
    congress_control_member_identity,
    congress_control_story_key_for_item,
    congress_control_story_key_for_market,
    has_two_distinct_us_parties,
    is_congress_control_story_key,
    recognized_us_party,
)
from app.utils.discover_bundles import (
    _dedupe_same_question_members,
    _member_answers_story_question,
    _theme_story_key,
    assemble_story_theme_bundles,
    resolve_story_question,
    story_family_label,
)
from app.utils.feed_market_quality import (
    classify_market_quality,
    diversify_quality_families,
)

# Exact served Discover feed items from fixtures/congress-real-20261021T231833Z.json
# (fetched 2026-10-21T23:18:33Z, feed edition d4d0da04e5966408).
REAL_SENATE_108620: dict[str, Any] = {
    "type": "futures",
    "score": 94,
    "reason": "Democratic Party is up 26 points since Feb 18 in Which party will win the U.S. Senate?",
    "headline": "Democratic Party leads at 66%, up 26 points since Feb 18",
    "context_summary": "Democratic Party leads at 66%, up 26 points since Feb 18",
    "data": {
        "id": 108620,
        "name": "Which party will win the U.S. Senate?",
        "sport": None,
        "sport_name": None,
        "llm_sport_category": "politics",
        "source": "kalshi",
        "source_count": 2,
        "sources": ["kalshi", "polymarket"],
        "market_tier": 2,
        "market_type": "duel",
        "status": "open",
        "resolution_date": "2027-02-01T15:00:00+00:00",
        "price_observed_at": "2026-10-21T23:11:46+00:00",
        "top_outcomes": [
            {
                "id": 1593959,
                "name": "Democratic Party",
                "probability": 0.655,
                "rank": 1,
                "movement": None,
                "rendered_percent": 66,
            },
            {
                "id": 1593958,
                "name": "Republican Party",
                "probability": 0.335,
                "rank": 2,
                "movement": None,
                "rendered_percent": 34,
            },
        ],
        "card_sum_reason": None,
        "outcome_count": 2,
        "canonical_market_key": "politics:US:championship:2027",
        "group_id": "kalshi:CONTROLS-2026",
        "group_type": "kalshi_event",
        "discover_card": {
            "suggested_format": "binary_probability",
            "bundle_candidate": False,
            "comparison_theme": None,
            "threshold_points": [],
            "ladder_treatment_refused": False,
            "field_is_a_race": True,
            "distribution_outcomes": [
                {"label": "Democratic Party", "probability": 0.655, "movement": None},
                {"label": "Republican Party", "probability": 0.335, "movement": None},
            ],
            "distribution_order": "probability",
            "remaining_outcome_count": 0,
            "qa_signals": ["multi_source_consistency_check"],
            "public_source_disagreement": False,
            "reasons": [],
        },
    },
}

REAL_HOUSE_108621: dict[str, Any] = {
    "type": "futures",
    "score": 92,
    "reason": "Democratic Party is up 13.7 points since Feb 18 in Which party will win the U.S. House?",
    "headline": "Democratic Party leads at 91%, up 13.7 points since Feb 18",
    "context_summary": "Democratic Party leads at 91%, up 13.7 points since Feb 18",
    "data": {
        "id": 108621,
        "name": "Which party will win the U.S. House?",
        "sport": None,
        "sport_name": None,
        "llm_sport_category": "politics",
        "source": "kalshi",
        "source_count": 1,
        "sources": ["kalshi"],
        "market_tier": 2,
        "market_type": "duel",
        "status": "open",
        "resolution_date": "2027-02-01T15:00:00+00:00",
        "price_observed_at": "2026-10-21T23:11:47+00:00",
        "top_outcomes": [
            {
                "id": 1593960,
                "name": "Democratic Party",
                "probability": 0.9125,
                "rank": 1,
                "movement": None,
                "rendered_percent": 91,
            },
            {
                "id": 1593961,
                "name": "Republican Party",
                "probability": 0.0875,
                "rank": 2,
                "movement": None,
                "rendered_percent": 9,
            },
        ],
        "card_sum_reason": None,
        "outcome_count": 2,
        "canonical_market_key": "politics::championship:2027",
        "group_id": "kalshi:CONTROLH-2026",
        "group_type": "kalshi_event",
        "discover_card": {
            "suggested_format": "binary_probability",
            "bundle_candidate": False,
            "comparison_theme": None,
            "threshold_points": [],
            "ladder_treatment_refused": False,
            "field_is_a_race": True,
            "distribution_outcomes": [
                {"label": "Democratic Party", "probability": 0.9125, "movement": None},
                {"label": "Republican Party", "probability": 0.0875, "movement": None},
            ],
            "distribution_order": "probability",
            "remaining_outcome_count": 0,
            "qa_signals": [],
            "public_source_disagreement": False,
            "reasons": [],
        },
    },
}

JOINT_CONTROL_108619: dict[str, Any] = {
    "type": "futures",
    "score": 89,
    "reason": "Democrats sweep leads at 66%",
    "headline": "Democrats sweep leads at 66%",
    "context_summary": "Democrats sweep leads at 66%",
    "data": {
        "id": 108619,
        "name": "2026 Midterms: Congress Balance of Power?",
        "sport": None,
        "sport_name": None,
        "llm_sport_category": "politics",
        "source": "kalshi",
        "source_count": 1,
        "sources": ["kalshi"],
        "market_tier": 2,
        "market_type": "field",
        "status": "open",
        "resolution_date": "2027-02-08T15:00:00+00:00",
        "external_id": "KXBALANCEPOWERCOMBO-27FEB",
        "group_id": "kalshi:KXBALANCEPOWERCOMBO-27FEB",
        "group_type": "kalshi_event",
        "outcome_count": 4,
        "canonical_market_key": "politics:US:championship:2026",
        "top_outcomes": [
            {
                "id": 1593955,
                "name": "Democrats sweep",
                "probability": 0.655,
                "rank": 1,
                "movement": None,
                "rendered_percent": 66,
            },
            {
                "id": 1593954,
                "name": "D-House, R-Senate",
                "probability": 0.265,
                "rank": 2,
                "movement": None,
                "rendered_percent": 27,
            },
            {
                "id": 1593956,
                "name": "Republicans sweep",
                "probability": 0.0885,
                "rank": 3,
                "movement": None,
                "rendered_percent": 9,
            },
        ],
        "discover_card": {
            "remaining_outcome_count": 1,
            "public_source_disagreement": False,
        },
    },
}


def _clone(item: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(item)


def test_a1_both_chambers_present_and_eligible_form_one_congress_bundle() -> None:
    """Case A1: REAL Senate + House fold into one authored Congress theme bundle."""
    senate = _clone(REAL_SENATE_108620)
    house = _clone(REAL_HOUSE_108621)

    q_senate = classify_market_quality(
        market_name=senate["data"]["name"],
        sport_category="politics",
        outcome_names=["Democratic Party", "Republican Party"],
        external_id="CONTROLS-2026",
    )
    q_house = classify_market_quality(
        market_name=house["data"]["name"],
        sport_category="politics",
        outcome_names=["Democratic Party", "Republican Party"],
        external_id="CONTROLH-2026",
    )
    assert q_senate.story_key == "story:us_congress_control:2026"
    assert q_house.story_key == "story:us_congress_control:2026"

    senate["_quality_class"] = q_senate.quality_class
    senate["_quality_story_key"] = q_senate.story_key
    house["_quality_class"] = q_house.quality_class
    house["_quality_story_key"] = q_house.story_key

    out = assemble_story_theme_bundles([senate, house])
    assert len(out) == 1
    bundle = out[0]
    assert bundle["type"] == "bundle"
    assert bundle["score"] == 94
    assert bundle["headline"] == US_CONGRESS_CONTROL_TITLE
    assert bundle["reason"] == US_CONGRESS_CONTROL_QUESTION

    bdata = bundle["data"]
    assert bdata["kind"] == "theme"
    assert bdata["story_key"] == "story:us_congress_control:2026"
    assert bdata["title"] == "Congress"
    assert bdata["shared_question"] == "Who wins control of Congress?"
    assert bdata["member_ids"] == [108620, 108621]
    assert bdata["item_count"] == 2
    assert bdata["debug_bundles"]["title_source"] == "authored"
    assert bdata["debug_bundles"]["question_source"] == "authored"
    assert story_family_label("story:us_congress_control:2026", []) == "Congress"
    assert resolve_story_question("story:us_congress_control:2026", []) == (
        "Who wins control of Congress?",
        "authored",
    )


def test_a2_identity_not_title_rejects_non_control_ticker() -> None:
    """Case A2: Senate title with a non-CONTROL external_id does not key into Congress."""
    q = classify_market_quality(
        market_name="Which party will win the U.S. Senate?",
        sport_category="politics",
        outcome_names=["Democratic Party", "Republican Party"],
        external_id="KXSENATETX-26",
    )
    assert q.story_key != "story:us_congress_control:2026"

    # Even if cloned from REAL_SENATE_108620 (which still carries group_id
    # "kalshi:CONTROLS-2026") and given a forged _quality_story_key, inconsistent
    # external_id "KXSENATETX-26" disqualifies the item.
    fake_senate = _clone(REAL_SENATE_108620)
    fake_senate["data"]["external_id"] = "KXSENATETX-26"
    fake_senate["_quality_story_key"] = "story:us_congress_control:2026"
    house = _clone(REAL_HOUSE_108621)

    assert congress_control_story_key_for_item(fake_senate) is None
    assert _theme_story_key(fake_senate) is None

    out = assemble_story_theme_bundles([fake_senate, house])
    assert len(out) == 2
    assert all(item["type"] == "futures" for item in out)


def test_a3_one_chamber_only_does_not_bundle() -> None:
    """Case A3: One chamber alone in the pool stays a standalone card."""
    senate = _clone(REAL_SENATE_108620)
    out = assemble_story_theme_bundles([senate])
    assert len(out) == 1
    assert out[0]["type"] == "futures"
    assert out[0]["data"]["id"] == 108620


def test_a4_joint_control_108619_never_enters_bundle() -> None:
    """Case A4: Joint balance-of-power market 108619 stays separate."""
    senate = _clone(REAL_SENATE_108620)
    house = _clone(REAL_HOUSE_108621)
    joint = _clone(JOINT_CONTROL_108619)
    # Even if a forged _quality_story_key were attached, joint control is rejected.
    joint["_quality_story_key"] = "story:us_congress_control:2026"

    q_joint = classify_market_quality(
        market_name=joint["data"]["name"],
        sport_category="politics",
        outcome_names=[o["name"] for o in joint["data"]["top_outcomes"]],
        external_id="KXBALANCEPOWERCOMBO-27FEB",
    )
    assert q_joint.story_key is None
    assert congress_control_story_key_for_item(joint) is None

    out = assemble_story_theme_bundles([senate, joint, house])
    assert len(out) == 2
    assert out[0]["type"] == "bundle"
    assert out[0]["data"]["member_ids"] == [108620, 108621]
    assert out[1]["type"] == "futures"
    assert out[1]["data"]["id"] == 108619


def test_a5_another_edition_does_not_mix() -> None:
    """Case A5: 2026 and 2028 pairs get distinct edition keys and never cross-bundle."""
    senate_2026 = _clone(REAL_SENATE_108620)
    house_2026 = _clone(REAL_HOUSE_108621)

    senate_2028 = _clone(REAL_SENATE_108620)
    senate_2028["data"]["id"] = 208620
    senate_2028["data"]["group_id"] = "kalshi:CONTROLS-2028"
    senate_2028["data"]["external_id"] = "CONTROLS-2028"
    senate_2028["data"]["canonical_market_key"] = "politics:US:championship:2029"
    senate_2028["data"]["resolution_date"] = "2029-02-01T15:00:00+00:00"

    house_2028 = _clone(REAL_HOUSE_108621)
    house_2028["data"]["id"] = 208621
    house_2028["data"]["group_id"] = "kalshi:CONTROLH-2028"
    house_2028["data"]["external_id"] = "CONTROLH-2028"
    house_2028["data"]["canonical_market_key"] = "politics::championship:2029"
    house_2028["data"]["resolution_date"] = "2029-02-01T15:00:00+00:00"

    # Cross-edition pair (2026 Senate + 2028 House) never bundles
    cross = assemble_story_theme_bundles([senate_2026, house_2028])
    assert len(cross) == 2
    assert all(it["type"] == "futures" for it in cross)

    # Both complete pairs form two separate edition-scoped bundles
    both = assemble_story_theme_bundles(
        [senate_2026, house_2026, senate_2028, house_2028]
    )
    assert len(both) == 2
    assert both[0]["data"]["story_key"] == "story:us_congress_control:2026"
    assert both[0]["data"]["member_ids"] == [108620, 108621]
    assert both[1]["data"]["story_key"] == "story:us_congress_control:2028"
    assert both[1]["data"]["member_ids"] == [208620, 208621]


def test_a6_negative_specimens_retain_existing_keys() -> None:
    """Case A6: State races, state legislatures, demographics, counts, superlatives excluded."""
    tx_senate = classify_market_quality(
        market_name="Texas Senate winner?",
        sport_category="politics",
        outcome_names=["James Talarico", "Ken Paxton"],
        external_id="KXSENATETX-26",
    )
    assert tx_senate.story_key == "story:us_state_races"

    az_state_senate = classify_market_quality(
        market_name="Which party will win the Arizona State Senate?",
        sport_category="politics",
        outcome_names=["Democratic Party", "Republican Party"],
        external_id="KXAZSENATE-26",
    )
    assert az_state_senate.story_key == "story:regional_us_elections"

    latino_men = classify_market_quality(
        market_name="Which party will win Latino men in the 2026 midterms?",
        sport_category="politics",
        outcome_names=["Democratic Party", "Republican Party"],
        external_id="KXLATINOMEN-26",
    )
    assert latino_men.story_key is None

    independents_count = classify_market_quality(
        market_name="How many Independents will caucus with Democrats in the U.S. Senate?",
        sport_category="politics",
        outcome_names=["0", "1", "2", "3+"],
        external_id="KXSENATEIND-26",
    )
    assert independents_count.story_key is None

    bluest_state = classify_market_quality(
        market_name="Bluest state to elect a Republican senator in 2026?",
        sport_category="politics",
        outcome_names=["Maine", "Ohio"],
        external_id="KXBLUESTSEN-26",
    )
    assert not is_congress_control_story_key(bluest_state.story_key)

    philippine_senate = classify_market_quality(
        market_name="Which party will win the Philippine Senate?",
        sport_category="politics",
        outcome_names=["Democratic Party", "Republican Party"],
        external_id="CONTROLS-2026",
    )
    assert not is_congress_control_story_key(philippine_senate.story_key)


def test_a7_ineligible_member_never_folds() -> None:
    """Case A7: low_quality or public_source_disagreement member prevents bundle formation."""
    senate = _clone(REAL_SENATE_108620)
    house_low = _clone(REAL_HOUSE_108621)
    house_low["_quality_class"] = "low_quality"

    out_low = assemble_story_theme_bundles([senate, house_low])
    assert len(out_low) == 2
    assert all(it["type"] == "futures" for it in out_low)

    house_disagree = _clone(REAL_HOUSE_108621)
    house_disagree["data"]["discover_card"]["public_source_disagreement"] = True
    out_disagree = assemble_story_theme_bundles([senate, house_disagree])
    assert len(out_disagree) == 2
    assert all(it["type"] == "futures" for it in out_disagree)


def test_a8_candidacy_denylist_evicts_non_victory_question() -> None:
    """Case A8: Candidacy prompt is refused by both _member_answers_story_question and Rule S."""
    candidacy = _clone(REAL_SENATE_108620)
    candidacy["data"]["id"] = 999001
    candidacy["data"]["name"] = "Will X announce a run for U.S. Senate?"
    candidacy["_quality_story_key"] = "story:us_congress_control:2026"

    assert not _member_answers_story_question(
        "story:us_congress_control:2026", candidacy
    )
    assert congress_control_story_key_for_item(candidacy) is None

    out = assemble_story_theme_bundles([candidacy, _clone(REAL_HOUSE_108621)])
    assert len(out) == 2
    assert all(it["type"] == "futures" for it in out)


def test_a9_persisted_key_precedence_and_forged_key_rejection() -> None:
    """Case A9: Computed Congress key overrides stale persisted key; forged persisted key rejected."""
    q_real = classify_market_quality(
        market_name="Which party will win the U.S. Senate?",
        sport_category="politics",
        outcome_names=["Democratic Party", "Republican Party"],
        external_id="CONTROLS-2026",
        persisted_story_key="story:senate_control",
    )
    assert q_real.story_key == "story:us_congress_control:2026"

    # Even if an item carries a stale _quality_story_key, _theme_story_key
    # resolves the verified Congress control key so scoring caps and bundling stay coherent.
    senate = _clone(REAL_SENATE_108620)
    senate["_quality_story_key"] = "story:senate_control"
    house = _clone(REAL_HOUSE_108621)
    out = assemble_story_theme_bundles([senate, house])
    assert len(out) == 1
    assert out[0]["data"]["story_key"] == "story:us_congress_control:2026"

    # Forged persisted Congress key on a non-CONTROL market is stripped.
    q_forged = classify_market_quality(
        market_name="Texas Senate winner?",
        sport_category="politics",
        outcome_names=["Democratic Party", "Republican Party"],
        external_id="KXSENATETX-26",
        persisted_story_key="story:us_congress_control:2026",
    )
    assert q_forged.story_key == "story:us_state_races"


def test_a10_wrong_source_and_cross_venue_duplicate_controls() -> None:
    """Case A10 + Tightening #1: Polymarket lookalike never keys into Congress; dedupe folds cross-venue."""
    assert (
        congress_control_story_key_for_market(
            market_name="Which party will win the U.S. Senate?",
            external_id="CONTROLS-2026",
            outcome_names=["Democratic Party", "Republican Party"],
            source="polymarket",
        )
        is None
    )

    poly_senate = _clone(REAL_SENATE_108620)
    poly_senate["data"]["id"] = 308620
    poly_senate["data"]["source"] = "polymarket"
    poly_senate["data"]["group_id"] = "polymarket:CONTROLS-2026"
    poly_senate["_quality_story_key"] = "story:us_congress_control:2026"

    assert congress_control_story_key_for_item(poly_senate) is None
    assert _theme_story_key(poly_senate) is None

    # In assemble_story_theme_bundles, poly_senate is refused Congress membership,
    # leaving the Kalshi Senate+House pair intact and poly_senate separate.
    out = assemble_story_theme_bundles(
        [_clone(REAL_SENATE_108620), poly_senate, _clone(REAL_HOUSE_108621)]
    )
    assert len(out) == 2
    assert out[0]["type"] == "bundle"
    assert out[0]["data"]["member_ids"] == [108620, 108621]
    assert out[1]["data"]["id"] == 308620

    # Direct check on _dedupe_same_question_members: folds cross-venue same title to one row.
    kept, folded = _dedupe_same_question_members(
        [_clone(REAL_SENATE_108620), poly_senate, _clone(REAL_HOUSE_108621)]
    )
    assert [it["data"]["id"] for it in kept] == [108620, 108621]
    assert [it["data"]["id"] for it in folded] == [308620]


def test_a11_and_tightening_2_chamber_completeness_and_story_cap() -> None:
    """Case A11 + Tightening #2: Cap is 2; 2-Senate, 2-House, and conflicting same-chamber fail closed."""
    senate = _clone(REAL_SENATE_108620)
    senate["_quality_story_key"] = "story:us_congress_control:2026"
    senate["_quality_family_key"] = "fam:senate"

    house = _clone(REAL_HOUSE_108621)
    house["_quality_story_key"] = "story:us_congress_control:2026"
    house["_quality_family_key"] = "fam:house"

    third = _clone(REAL_SENATE_108620)
    third["score"] = 80
    third["data"]["id"] = 999999
    third["data"]["name"] = "Which party will control the U.S. Senate in 2026?"
    third["_quality_story_key"] = "story:us_congress_control:2026"
    third["_quality_family_key"] = "fam:third"

    # prefix_story_caps caps story:us_congress_control: at 2 and puts the 3rd into overflow
    capped = diversify_quality_families([senate, house, third])
    assert [it["data"]["id"] for it in capped] == [108620, 108621]
    assert [
        it["data"]["id"] for it in capped[0].get("_story_overflow_members", [])
    ] == [999999]

    # 2 Senate / no House -> refused (never forms a false Congress group of two Senate rows)
    senate_dup = _clone(REAL_SENATE_108620)
    senate_dup["data"]["id"] = 1086202
    senate_dup["data"]["name"] = (
        "Which party will hold a majority of seats in the United States Senate?"
    )
    two_senate_out = assemble_story_theme_bundles([_clone(REAL_SENATE_108620), senate_dup])
    assert len(two_senate_out) == 2
    assert all(it["type"] == "futures" for it in two_senate_out)

    # 2 House / no Senate -> refused
    house_dup = _clone(REAL_HOUSE_108621)
    house_dup["data"]["id"] = 1086212
    house_dup["data"]["name"] = (
        "Which party will hold a majority of seats in the United States House?"
    )
    two_house_out = assemble_story_theme_bundles([_clone(REAL_HOUSE_108621), house_dup])
    assert len(two_house_out) == 2
    assert all(it["type"] == "futures" for it in two_house_out)

    # Conflicting same-chamber (2 Kalshi Senate rows + 1 Kalshi House row, including via overflow):
    # duplicate same-venue Senate identity cannot be resolved by _dedupe_same_question_members,
    # so folding is refused and originals are preserved rather than hiding the House or picking arbitrarily.
    conflicting = assemble_story_theme_bundles(
        [_clone(REAL_SENATE_108620), senate_dup, _clone(REAL_HOUSE_108621)]
    )
    assert len(conflicting) == 3
    assert all(it["type"] == "futures" for it in conflicting)


def test_anchor_and_outcome_validation_mutants() -> None:
    """Tightening #1 & #6: Malformed anchors, chamber mismatches, and non-party outcomes rejected."""
    # Malformed tickers
    for bad_ticker in ("CONTROLS-26", "CONTROLX-2026", "CONTROLS-2026-D", ""):
        assert (
            congress_control_story_key_for_market(
                market_name="Which party will win the U.S. Senate?",
                external_id=bad_ticker,
                outcome_names=["Democratic Party", "Republican Party"],
            )
            is None
        )

    # Ticker/title chamber mismatch (Senate ticker with House title, or vice versa)
    assert (
        congress_control_story_key_for_market(
            market_name="Which party will win the U.S. House?",
            external_id="CONTROLS-2026",
            outcome_names=["Democratic Party", "Republican Party"],
        )
        is None
    )
    assert (
        congress_control_story_key_for_market(
            market_name="Which party will win the U.S. Senate?",
            external_id="CONTROLH-2026",
            outcome_names=["Democratic Party", "Republican Party"],
        )
        is None
    )

    # Inconsistent external_id vs group_id (chamber or edition mismatch)
    mismatch_chamber = _clone(REAL_SENATE_108620)
    mismatch_chamber["data"]["external_id"] = "CONTROLH-2026"
    assert congress_control_member_identity(mismatch_chamber) is None

    mismatch_edition = _clone(REAL_SENATE_108620)
    mismatch_edition["data"]["external_id"] = "CONTROLS-2028"
    assert congress_control_member_identity(mismatch_edition) is None

    # Outcome party validation: duplicate party alias ("Democrats" + "Dem") or 3 outcomes rejected
    assert recognized_us_party("Democratic Party") == "democratic"
    assert recognized_us_party("The Republicans") == "republican"
    assert recognized_us_party("GOP") == "republican"
    assert recognized_us_party("Dem") is None
    assert recognized_us_party("Independent") is None
    assert not has_two_distinct_us_parties(["Democrats", "Democratic Party"])
    assert not has_two_distinct_us_parties(["Democrats", "Dem"])
    assert not has_two_distinct_us_parties(
        ["Democratic Party", "Republican Party", "Independent"]
    )
    assert congress_control_bundle_members("story:us_congress_control:2026", []) is None
