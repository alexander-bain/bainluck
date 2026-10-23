"""Discriminating backend tests for Slice 1 movement-led deadline-family stories (#9878 / #11040).

Covers all Section 5, 6, 7, and 8 requirements:
- Case 1: Actual retained Oct 14 NULL stored-claim control (markets 65678073 & 65678074).
- Case 2: Explicitly synthetic valid stored claim + outcome-bound dated comparison basis.
- Case 3: Expired (>24h) or too-young (<12h) dated basis refused; fallback to nearest 50%.
- Case 4: No-leading binary outcomes — exact Yes outcome ID supplies every value without complementing No.
- Case 5: Missing Yes, duplicate outcome IDs, and negatively worded questions refused.
- Case 6: One family consumes one feed seat via `assemble_deadline_family_bundles` (including `_grouped_members`).
- Case 7: Deterministic representative tie-breaks and ascending `deadline_instant` ordering.
- Case 8: Mixed predicates, exclusive date buckets, mention-only markets, and timezone-naive/mismatched dates refused.
- Case 9 & 10: Q8 local 97%+ open-mover exception admitted when supported by in-window dated move and refused upon expiry.
- Case 11: 6D authoritative venue/outcome settlement overrides lagging local `status="open"`; extreme prices alone do not settle.
- Case 12: 6E five movement states (no-write/refused, sub-threshold <2pt, moderate 2..<5pt, hero >=5pt, measured zero).
- Case 13: Direct User Decision Q4 reader-local calendar-day comparison wording ("since yesterday" vs same-day time).
- Case 14: 6F represented count vs provider inventory completeness and unpriced member reachability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.routes.feed import _market_runtime_filter_trace
from app.utils.deadline_family_story import (
    DETERMINISTIC_TIE_BREAK_RULE,
    build_deadline_member_contract,
    extract_settlement_evidence,
    format_movement_timeframe,
    parse_cumulative_deadline_question,
    qualifies_for_deadline_near_certain_exception,
    verify_and_select_deadline_family,
)
from app.utils.discover_bundles import assemble_deadline_family_bundles

RETAINED_NOW = datetime(2026, 10, 14, 13, 34, 0, tzinfo=timezone.utc)
RETAINED_BASIS_AT = "2026-10-13T16:10:00+00:00"  # 21.4 hours before RETAINED_NOW


def _make_oct31_outcomes(*, stored_yes_change: float | None = None, yes_prob: float | None = 0.073) -> list[dict]:
    no_prob = round(1.0 - yes_prob, 4) if yes_prob is not None else None
    return [
        {
            "id": 246879006,
            "name": "No",
            "external_id": "23750296999441781140845142318022266810772441561257322279207268816415471449435",
            "current_probability": no_prob,
            "probability_change_24h": 0.011 if stored_yes_change is not None else None,
            "rank": 1,
        },
        {
            "id": 246879005,
            "name": "Yes",
            "external_id": "74167794401960881962150670422546952062478246672716256803305946716278016867432",
            "current_probability": yes_prob,
            "probability_change_24h": stored_yes_change,
            "rank": 2,
        },
    ]


def _make_dec31_outcomes(*, stored_yes_change: float | None = None, yes_prob: float | None = 0.245) -> list[dict]:
    no_prob = round(1.0 - yes_prob, 4) if yes_prob is not None else None
    return [
        {
            "id": 246879008,
            "name": "No",
            "external_id": "52010207094808582680015014179469522027848394847004098667580388318701129457468",
            "current_probability": no_prob,
            "probability_change_24h": 0.065 if stored_yes_change is not None else None,
            "rank": 1,
        },
        {
            "id": 246879007,
            "name": "Yes",
            "external_id": "109248864950550918456926707901283260679215457211637114746364964324227495763694",
            "current_probability": yes_prob,
            "probability_change_24h": stored_yes_change,
            "rank": 2,
        },
    ]


def test_case1_retained_null_stored_claims_remain_no_claim_controls() -> None:
    """Section 6A / Section 8 Case 1:
    Actual retained Oct 14 rows have `probability_change_24h = None` on `Yes`.
    Even when offline/banked observations exist, they must remain no-claim controls
    and select Dec 31 via the nearest-50% fallback.
    """
    oct31_contract = build_deadline_member_contract(
        market_id=65678073,
        name="Will Zacharia be out as Prime Minister of Israel by October 31?",
        source="polymarket",
        external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        group_id="polymarket:1183118",
        status="open",
        resolution_date="2026-10-31T23:59:00+00:00",
        market_metadata={
            "dated_movement_basis": {"246879005": [0.084, RETAINED_BASIS_AT]},
            "market_count": 2,
        },
        outcomes=_make_oct31_outcomes(stored_yes_change=None),
        price_observed_at="2026-10-14T13:20:00+00:00",
        now=RETAINED_NOW,
    )
    dec31_contract = build_deadline_member_contract(
        market_id=65678074,
        name="Will Zacharia be out as Prime Minister of Israel by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:1183118",
        status="open",
        resolution_date="2026-12-31T23:59:00+00:00",
        market_metadata={
            "dated_movement_basis": {"246879007": [0.310, RETAINED_BASIS_AT]},
            "market_count": 2,
        },
        outcomes=_make_dec31_outcomes(stored_yes_change=None),
        price_observed_at="2026-10-14T13:20:00+00:00",
        now=RETAINED_NOW,
    )

    assert oct31_contract is not None
    assert dec31_contract is not None
    assert oct31_contract["movement_status"] == "no_stored_claim"
    assert dec31_contract["movement_status"] == "no_stored_claim"
    assert oct31_contract["supported_move"] is None
    assert dec31_contract["supported_move"] is None
    assert oct31_contract["show_hero_movement_chip"] is False
    assert dec31_contract["show_hero_movement_chip"] is False
    assert oct31_contract["show_row_movement_badge"] is False
    assert dec31_contract["show_row_movement_badge"] is False

    family, err = verify_and_select_deadline_family(
        [dec31_contract, oct31_contract],
        now=RETAINED_NOW,
    )
    assert err is None
    assert family is not None
    assert family["representative_market_id"] == 65678074
    assert family["representative_outcome_id"] == 246879007
    assert family["selection_reason"] == "nearest_50_pct_fallback"
    assert [m["market_id"] for m in family["members"]] == [65678073, 65678074]


def test_case2_synthetic_valid_stored_claim_plus_dated_bank_selects_dec31_move() -> None:
    """Section 6A / Section 8 Case 2:
    Explicitly synthetic fixture with BOTH non-null stored claims AND outcome-bound
    dated comparison bases selects Dec 31 with -6.5 points (`hero`), while Oct 31's
    -1.1 point move stays `sub_threshold` (< 2 pts).
    """
    oct31_syn = build_deadline_member_contract(
        market_id=65678073,
        name="Will Zacharia be out as Prime Minister of Israel by October 31?",
        source="polymarket",
        external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        group_id="polymarket:1183118",
        status="open",
        resolution_date="2026-10-31T23:59:00+00:00",
        market_metadata={
            "dated_movement_basis": {"246879005": [0.084, RETAINED_BASIS_AT]},
            "market_count": 2,
        },
        outcomes=_make_oct31_outcomes(stored_yes_change=-0.011),
        price_observed_at="2026-10-14T13:20:00+00:00",
        now=RETAINED_NOW,
    )
    dec31_syn = build_deadline_member_contract(
        market_id=65678074,
        name="Will Zacharia be out as Prime Minister of Israel by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:1183118",
        status="open",
        resolution_date="2026-12-31T23:59:00+00:00",
        market_metadata={
            "dated_movement_basis": {"246879007": [0.310, RETAINED_BASIS_AT]},
            "market_count": 2,
        },
        outcomes=_make_dec31_outcomes(stored_yes_change=-0.065),
        price_observed_at="2026-10-14T13:20:00+00:00",
        now=RETAINED_NOW,
    )

    assert oct31_syn is not None and dec31_syn is not None
    assert oct31_syn["movement_status"] == "sub_threshold"
    assert oct31_syn["supported_move_points"] == -1.1
    assert oct31_syn["show_hero_movement_chip"] is False
    assert oct31_syn["show_row_movement_badge"] is False

    assert dec31_syn["movement_status"] == "hero"
    assert dec31_syn["supported_move"] == -0.065
    assert dec31_syn["supported_move_points"] == -6.5
    assert dec31_syn["show_hero_movement_chip"] is True
    assert dec31_syn["show_row_movement_badge"] is True

    family, err = verify_and_select_deadline_family(
        [oct31_syn, dec31_syn],
        now=RETAINED_NOW,
        reader_tz="America/New_York",
    )
    assert err is None
    assert family is not None
    assert family["representative_market_id"] == 65678074
    assert family["selection_reason"] == "largest_supported_dated_move"
    assert family["representative_timeframe"]["chip_timeframe"] == "since yesterday"


def test_case3_expired_or_premature_dated_basis_is_refused() -> None:
    """Section 8 Case 3:
    A dated comparison basis older than 24h or younger than 12h is refused (`basis_out_of_window`),
    and the family falls back to the open priced deadline nearest 50%.
    """
    too_old_basis = "2026-10-13T08:00:00+00:00"  # 29.5h before RETAINED_NOW
    too_young_basis = "2026-10-14T08:00:00+00:00"  # 5.5h before RETAINED_NOW

    oct31_expired = build_deadline_member_contract(
        market_id=65678073,
        name="Will Zacharia be out as Prime Minister of Israel by October 31?",
        source="polymarket",
        external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        group_id="polymarket:1183118",
        resolution_date="2026-10-31T23:59:00+00:00",
        market_metadata={"dated_movement_basis": {"246879005": [0.20, too_young_basis]}},
        outcomes=_make_oct31_outcomes(stored_yes_change=-0.127),
        now=RETAINED_NOW,
    )
    dec31_expired = build_deadline_member_contract(
        market_id=65678074,
        name="Will Zacharia be out as Prime Minister of Israel by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:1183118",
        resolution_date="2026-12-31T23:59:00+00:00",
        market_metadata={"dated_movement_basis": {"246879007": [0.310, too_old_basis]}},
        outcomes=_make_dec31_outcomes(stored_yes_change=-0.065),
        now=RETAINED_NOW,
    )

    assert oct31_expired is not None and dec31_expired is not None
    assert oct31_expired["movement_status"] == "basis_out_of_window"
    assert dec31_expired["movement_status"] == "basis_out_of_window"
    assert oct31_expired["supported_move"] is None
    assert dec31_expired["supported_move"] is None

    family, err = verify_and_select_deadline_family(
        [oct31_expired, dec31_expired],
        now=RETAINED_NOW,
    )
    assert err is None
    assert family is not None
    assert family["selection_reason"] == "nearest_50_pct_fallback"
    assert family["representative_market_id"] == 65678074


def test_case4_no_leading_binary_binds_strictly_to_yes_outcome_id() -> None:
    """Section 6C / Section 8 Case 4:
    Even when `No` is rank 1 (`0.755`) and `top_outcomes_data` lists `No` first
    with humanized label `"Likely No: ..."`, the contract binds strictly to
    `yes_outcome_id=246879007` (`0.245` / `25%`), and refuses a basis keyed to `No`.
    """
    top_outcomes_data = [
        {"id": 246879008, "name": "Likely No: Zacharia be out", "probability": 0.755, "rendered_percent": 75, "rank": 1},
        {"id": 246879007, "name": "Yes: Zacharia be out", "probability": 0.245, "rendered_percent": 25, "rank": 2},
    ]
    # Basis wrongly keyed to `No` outcome 246879008 must be refused for `Yes`
    wrong_basis_contract = build_deadline_member_contract(
        market_id=65678074,
        name="Will Zacharia be out as Prime Minister of Israel by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:1183118",
        resolution_date="2026-12-31T23:59:00+00:00",
        market_metadata={"dated_movement_basis": {"246879008": [0.690, RETAINED_BASIS_AT]}},
        outcomes=_make_dec31_outcomes(stored_yes_change=-0.065),
        top_outcomes_data=top_outcomes_data,
        now=RETAINED_NOW,
    )
    assert wrong_basis_contract is not None
    assert wrong_basis_contract["yes_outcome_id"] == 246879007
    assert wrong_basis_contract["yes_probability"] == 0.245
    assert wrong_basis_contract["yes_rendered_percent"] == 25
    assert wrong_basis_contract["movement_status"] == "missing_or_invalid_basis"
    assert wrong_basis_contract["supported_move"] is None


def test_case5_missing_yes_duplicate_outcomes_and_negative_wording_refused() -> None:
    """Section 6B / 6C / Section 8 Case 5:
    Missing `Yes` outcome, duplicate outcome IDs, and negatively worded questions
    are rejected.
    """
    # Missing Yes outcome
    assert (
        build_deadline_member_contract(
            market_id=101,
            name="Will Zacharia be out as Prime Minister of Israel by October 31?",
            source="polymarket",
            external_id="cond-101",
            group_id="polymarket:1183118",
            resolution_date="2026-10-31T23:59:00+00:00",
            outcomes=[
                {"id": 1, "name": "No", "current_probability": 0.9},
                {"id": 2, "name": "Maybe", "current_probability": 0.1},
            ],
            now=RETAINED_NOW,
        )
        is None
    )

    # Duplicate outcome IDs
    assert (
        build_deadline_member_contract(
            market_id=102,
            name="Will Zacharia be out as Prime Minister of Israel by October 31?",
            source="polymarket",
            external_id="cond-102",
            group_id="polymarket:1183118",
            resolution_date="2026-10-31T23:59:00+00:00",
            outcomes=[
                {"id": 246879005, "name": "Yes", "current_probability": 0.1},
                {"id": 246879005, "name": "No", "current_probability": 0.9},
            ],
            now=RETAINED_NOW,
        )
        is None
    )

    # Negatively worded / inverted predicates
    for negative_question in (
        "Will Zacharia not be out as Prime Minister of Israel by October 31?",
        "Will Zacharia stay in office by October 31?",
        "Will Zacharia remain in office by October 31?",
    ):
        assert (
            parse_cumulative_deadline_question(
                negative_question,
                "2026-10-31T23:59:00+00:00",
            )
            is None
        )


def test_case6_one_family_consumes_one_feed_seat_including_grouped_members() -> None:
    """Section 4 / Section 8 Case 6:
    `assemble_deadline_family_bundles` collapses a verified deadline family into
    a single `theme_bundle` feed item (one feed seat), both when siblings are
    top-level items and when `_dedupe_futures_by_group_id` stashed siblings on
    `_grouped_members`.
    """
    oct31_contract = build_deadline_member_contract(
        market_id=65678073,
        name="Will Zacharia be out as Prime Minister of Israel by October 31?",
        source="polymarket",
        external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        group_id="polymarket:1183118",
        resolution_date="2026-10-31T23:59:00+00:00",
        outcomes=_make_oct31_outcomes(stored_yes_change=None),
        now=RETAINED_NOW,
    )
    dec31_contract = build_deadline_member_contract(
        market_id=65678074,
        name="Will Zacharia be out as Prime Minister of Israel by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:1183118",
        resolution_date="2026-12-31T23:59:00+00:00",
        outcomes=_make_dec31_outcomes(stored_yes_change=None),
        now=RETAINED_NOW,
    )

    oct31_item = {
        "type": "futures",
        "score": 48.0,
        "reason": "Politics",
        "explanation": None,
        "data": {
            "id": 65678073,
            "name": "Will Zacharia be out as Prime Minister of Israel by October 31?",
            "source": "polymarket",
            "group_id": "polymarket:1183118",
            "llm_sport_category": "politics",
            "status": "open",
            "resolution_date": "2026-10-31T23:59:00+00:00",
            "deadline_member": oct31_contract,
            "top_outcomes": [{"id": 246879005, "name": "Yes", "probability": 0.073, "rank": 2, "movement": None}],
            "outcome_count": 2,
        },
    }
    dec31_item = {
        "type": "futures",
        "score": 52.0,
        "reason": "Politics",
        "explanation": None,
        "data": {
            "id": 65678074,
            "name": "Will Zacharia be out as Prime Minister of Israel by December 31?",
            "source": "polymarket",
            "group_id": "polymarket:1183118",
            "llm_sport_category": "politics",
            "status": "open",
            "resolution_date": "2026-12-31T23:59:00+00:00",
            "deadline_member": dec31_contract,
            "top_outcomes": [{"id": 246879007, "name": "Yes", "probability": 0.245, "rank": 2, "movement": None}],
            "outcome_count": 2,
        },
        "_grouped_members": [oct31_item],
    }
    unrelated_item = {
        "type": "futures",
        "score": 40.0,
        "reason": "Economics",
        "explanation": None,
        "data": {"id": 999999, "name": "Unrelated question", "source": "kalshi"},
    }

    bundled = assemble_deadline_family_bundles([dec31_item, unrelated_item], now=RETAINED_NOW)
    assert len(bundled) == 2
    bundle_card = bundled[0]
    assert bundle_card["type"] == "bundle"
    assert bundle_card["data"]["kind"] == "theme"
    assert bundle_card["data"]["story_key"] == "story:deadline_family:polymarket:1183118"
    assert [child["data"]["id"] for child in bundle_card["data"]["items"]] == [65678073, 65678074]
    assert bundle_card["data"]["deadline_family"]["representative_market_id"] == 65678074


def test_case7_deterministic_tie_breaks_and_ascending_deadline_order() -> None:
    """Section 5 Q1 / Section 8 Case 7:
    Tie-break rule `abs_supported_move_desc -> distance_from_50pct_asc -> deadline_instant_asc -> market_id_asc`
    is deterministic and siblings always sort in ascending `deadline_instant` order.
    """
    # Equal move (-5.0 pts) and equal distance from 50% (0.40 vs 0.60, both 0.10 away)
    # -> earlier deadline_instant wins (Oct 31 over Dec 31).
    oct31_tie = build_deadline_member_contract(
        market_id=65678073,
        name="Will Zacharia be out as Prime Minister of Israel by October 31?",
        source="polymarket",
        external_id="cond-oct31",
        group_id="polymarket:1183118",
        resolution_date="2026-10-31T23:59:00+00:00",
        market_metadata={"dated_movement_basis": {"246879005": [0.450, RETAINED_BASIS_AT]}},
        outcomes=_make_oct31_outcomes(stored_yes_change=-0.050, yes_prob=0.400),
        now=RETAINED_NOW,
    )
    dec31_tie = build_deadline_member_contract(
        market_id=65678074,
        name="Will Zacharia be out as Prime Minister of Israel by December 31?",
        source="polymarket",
        external_id="cond-dec31",
        group_id="polymarket:1183118",
        resolution_date="2026-12-31T23:59:00+00:00",
        market_metadata={"dated_movement_basis": {"246879007": [0.650, RETAINED_BASIS_AT]}},
        outcomes=_make_dec31_outcomes(stored_yes_change=-0.050, yes_prob=0.600),
        now=RETAINED_NOW,
    )
    assert oct31_tie is not None and dec31_tie is not None

    family, err = verify_and_select_deadline_family([dec31_tie, oct31_tie], now=RETAINED_NOW)
    assert err is None
    assert family is not None
    assert family["tie_break_rule"] == DETERMINISTIC_TIE_BREAK_RULE
    assert family["representative_market_id"] == 65678073
    assert [m["market_id"] for m in family["members"]] == [65678073, 65678074]


def test_case8_mixed_predicates_exclusive_buckets_and_bad_dates_refused() -> None:
    """Section 6B / Section 7 / Section 8 Case 8:
    Rejects exclusive date buckets, mention-only questions, timezone-naive or
    mismatched deadline instants, mixed predicates, and cross-provider/Kalshi blends.
    """
    # Exclusive buckets & mention-only questions rejected at member parse
    for rejected_q in (
        "Will Zacharia be out as Prime Minister of Israel in October?",
        "Will Zacharia be out as Prime Minister of Israel between October 1 and October 31?",
        "Will Zacharia say ceasefire by October 31?",
        "Will Zacharia be out as Prime Minister of Israel by end of term?",
    ):
        assert parse_cumulative_deadline_question(rejected_q, "2026-10-31T23:59:00+00:00") is None

    # Timezone-naive resolution_date rejected
    assert (
        parse_cumulative_deadline_question(
            "Will Zacharia be out as Prime Minister of Israel by October 31?",
            "2026-10-31T23:59:00",
        )
        is None
    )

    # Resolution instant that contradicts the stated calendar deadline rejected
    assert (
        parse_cumulative_deadline_question(
            "Will Zacharia be out as Prime Minister of Israel by October 31?",
            "2026-12-31T23:59:00+00:00",
        )
        is None
    )

    # Mixed predicate within same provider group rejected
    m1 = build_deadline_member_contract(
        market_id=65678073,
        name="Will Zacharia be out as Prime Minister of Israel by October 31?",
        source="polymarket",
        external_id="cond-1",
        group_id="polymarket:1183118",
        resolution_date="2026-10-31T23:59:00+00:00",
        outcomes=_make_oct31_outcomes(),
        now=RETAINED_NOW,
    )
    m2_diff_pred = build_deadline_member_contract(
        market_id=65678074,
        name="Will Zacharia visit Washington by December 31?",
        source="polymarket",
        external_id="cond-2",
        group_id="polymarket:1183118",
        resolution_date="2026-12-31T23:59:00+00:00",
        outcomes=_make_dec31_outcomes(),
        now=RETAINED_NOW,
    )
    assert m1 is not None and m2_diff_pred is not None
    family, err = verify_and_select_deadline_family([m1, m2_diff_pred], now=RETAINED_NOW)
    assert family is None
    assert err == "mixed_subject_or_predicate"


def test_case9_and_10_q8_open_extreme_price_admitted_only_while_dated_move_is_valid() -> None:
    """Section 5 Q8 / Section 8 Cases 9 & 10:
    An open deadline question at >=97% is admitted when it has a qualifying in-window
    dated move (`>= 2` pts) on its bound `Yes` outcome, and refused once that
    dated basis expires or when prices are stopped.
    """
    outcomes_98 = _make_dec31_outcomes(stored_yes_change=0.140, yes_prob=0.980)
    valid_meta = {"dated_movement_basis": {"246879007": [0.840, RETAINED_BASIS_AT]}}
    expired_meta = {"dated_movement_basis": {"246879007": [0.840, "2026-10-13T05:00:00+00:00"]}}

    assert (
        qualifies_for_deadline_near_certain_exception(
            name="Will Zacharia be out as Prime Minister of Israel by December 31?",
            source="polymarket",
            external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
            group_id="polymarket:1183118",
            status="open",
            resolution_date="2026-12-31T23:59:00+00:00",
            market_metadata=valid_meta,
            outcomes=outcomes_98,
            prices_stopped=False,
            now=RETAINED_NOW,
        )
        is True
    )
    assert (
        qualifies_for_deadline_near_certain_exception(
            name="Will Zacharia be out as Prime Minister of Israel by December 31?",
            source="polymarket",
            external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
            group_id="polymarket:1183118",
            status="open",
            resolution_date="2026-12-31T23:59:00+00:00",
            market_metadata=expired_meta,
            outcomes=outcomes_98,
            prices_stopped=False,
            now=RETAINED_NOW,
        )
        is False
    )

    # Verify integration with `_market_runtime_filter_trace` in `routes/feed.py`
    def _make_runtime_market(meta: dict) -> SimpleNamespace:
        ns_outcomes = [
            SimpleNamespace(
                id=246879008,
                name="No",
                external_id="ext-no",
                current_probability=0.020,
                probability_change_24h=-0.140,
                price_observed_epoch=int(RETAINED_NOW.timestamp()) - 600,
                last_updated=RETAINED_NOW,
            ),
            SimpleNamespace(
                id=246879007,
                name="Yes",
                external_id="ext-yes",
                current_probability=0.980,
                probability_change_24h=0.140,
                price_observed_epoch=int(RETAINED_NOW.timestamp()) - 600,
                last_updated=RETAINED_NOW,
            ),
        ]
        return SimpleNamespace(
            id=65678074,
            name="Will Zacharia be out as Prime Minister of Israel by December 31?",
            source="polymarket",
            external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
            group_id="polymarket:1183118",
            status="open",
            resolution_date=datetime(2026, 12, 31, 23, 59, 0, tzinfo=timezone.utc),
            market_metadata=meta,
            outcomes=ns_outcomes,
            sport=None,
            llm_sport_category="politics",
            market_type="binary",
            group_type=None,
            commence_time=None,
            updated_at=RETAINED_NOW,
            created_at=RETAINED_NOW,
            price_polled_at=RETAINED_NOW.isoformat(),
            withheld_outcome_ids=[],
        )

    trace_outcomes = [
        {
            "id": 246879007,
            "name": "Yes",
            "probability": 0.980,
            "opening_probability": 0.500,
            "probability_change_24h": 0.140,
            "rank": 1,
            "movement": 0.140,
        },
        {
            "id": 246879008,
            "name": "No",
            "probability": 0.020,
            "opening_probability": 0.500,
            "probability_change_24h": -0.140,
            "rank": 2,
            "movement": -0.140,
        },
    ]

    admitted_trace = _market_runtime_filter_trace(
        _make_runtime_market(valid_meta),
        trace_outcomes,
        "Yes",
        0.980,
        RETAINED_NOW,
        sport_category="politics",
        newest_outcome_at=RETAINED_NOW,
    )
    assert admitted_trace["eligible"] is True
    assert "locked_market" not in admitted_trace["blockers"]
    assert "all_outcomes_settled" not in admitted_trace["blockers"]
    assert admitted_trace["checks"]["deadline_family_near_certain_mover_exception"] is True

    expired_trace = _market_runtime_filter_trace(
        _make_runtime_market(expired_meta),
        trace_outcomes,
        "Yes",
        0.980,
        RETAINED_NOW,
        sport_category="politics",
        newest_outcome_at=RETAINED_NOW,
    )
    assert expired_trace["eligible"] is False
    assert "locked_market" in expired_trace["blockers"]
    assert "all_outcomes_settled" in expired_trace["blockers"]
    assert expired_trace["checks"]["deadline_family_near_certain_mover_exception"] is False


def test_case11_authoritative_venue_settlement_overrides_lagging_local_open_status() -> None:
    """Section 6D / Section 8 Case 11:
    Authoritative venue settlement (`market_metadata.resolved = True` or outcome `is_winner = True`)
    overrides a lagging local `status="open"` and suppresses live movement claims.
    Conversely, extreme prices (`0%`, `97%`, `100%`) alone never mark a question settled.
    """
    lagging_contract = build_deadline_member_contract(
        market_id=65678074,
        name="Will Zacharia be out as Prime Minister of Israel by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:1183118",
        status="open",
        winner=None,
        resolution_date="2026-12-31T23:59:00+00:00",
        market_metadata={
            "resolved": True,
            "winning_outcome": "Yes",
            "dated_movement_basis": {"246879007": [0.140, RETAINED_BASIS_AT]},
        },
        outcomes=_make_dec31_outcomes(stored_yes_change=0.840, yes_prob=0.980),
        now=RETAINED_NOW,
    )
    assert lagging_contract is not None
    assert lagging_contract["settlement"]["is_settled"] is True
    assert lagging_contract["settlement"]["result"] == "Yes"
    assert lagging_contract["settlement"]["lagging_local_status"] is True
    assert lagging_contract["movement_status"] == "settled_suppressed"
    assert lagging_contract["supported_move"] is None
    assert lagging_contract["show_hero_movement_chip"] is False
    assert lagging_contract["near_certain_open_eligible"] is False

    # Extreme prices alone do NOT establish settlement
    for extreme_prob in (0.0, 0.97, 1.0):
        ev = extract_settlement_evidence(
            status="open",
            resolved=False,
            winner=None,
            market_metadata={},
            outcomes=_make_dec31_outcomes(stored_yes_change=None, yes_prob=extreme_prob),
        )
        assert ev["is_settled"] is False


def test_case12_honest_absence_measured_zero_and_movement_bands() -> None:
    """Section 6E / Section 8 Case 12:
    Distinguishes no-write (`no_stored_claim`), refused zero (`zero_stored_claim_refused`),
    measured zero (`measured_zero`), sub-threshold (`< 2` pts), moderate (`2..<5` pts),
    and hero (`>= 5` pts).
    """
    def _build_with(yes_prob: float, basis_price: float, stored_claim: float | None, admits_zero: bool = False) -> dict:
        meta: dict = {"dated_movement_basis": {"246879007": [basis_price, RETAINED_BASIS_AT]}}
        if admits_zero:
            meta["dated_movement_basis_eligibility"] = "priced_leg"
        res = build_deadline_member_contract(
            market_id=65678074,
            name="Will Zacharia be out as Prime Minister of Israel by December 31?",
            source="polymarket",
            external_id="cond-dec31",
            group_id="polymarket:1183118",
            resolution_date="2026-12-31T23:59:00+00:00",
            market_metadata=meta,
            outcomes=_make_dec31_outcomes(stored_yes_change=stored_claim, yes_prob=yes_prob),
            now=RETAINED_NOW,
        )
        assert res is not None
        return res

    no_write = _build_with(0.245, 0.245, None)
    assert no_write["movement_status"] == "no_stored_claim"
    assert no_write["supported_move"] is None

    unverified_zero = _build_with(0.245, 0.245, 0.0, admits_zero=False)
    assert unverified_zero["movement_status"] == "zero_stored_claim_refused"
    assert unverified_zero["supported_move"] is None

    measured_zero = _build_with(0.245, 0.245, 0.0, admits_zero=True)
    assert measured_zero["movement_status"] == "measured_zero"
    assert measured_zero["supported_move"] == 0.0
    assert measured_zero["show_hero_movement_chip"] is False
    assert measured_zero["show_row_movement_badge"] is False

    sub_threshold = _build_with(0.245, 0.234, 0.011)
    assert sub_threshold["movement_status"] == "sub_threshold"
    assert sub_threshold["supported_move_points"] == 1.1
    assert sub_threshold["show_hero_movement_chip"] is False
    assert sub_threshold["show_row_movement_badge"] is False

    moderate = _build_with(0.245, 0.213, 0.032)
    assert moderate["movement_status"] == "moderate"
    assert moderate["supported_move_points"] == 3.2
    assert moderate["show_hero_movement_chip"] is False
    assert moderate["show_row_movement_badge"] is True

    hero = _build_with(0.245, 0.310, -0.065)
    assert hero["movement_status"] == "hero"
    assert hero["supported_move_points"] == -6.5
    assert hero["show_hero_movement_chip"] is True
    assert hero["show_row_movement_badge"] is True


def test_case13_q4_reader_local_calendar_day_wording() -> None:
    """Section 5 Q4 / Section 8 Case 13:
    Uses `"since yesterday"` ONLY when the comparison crosses from the previous
    reader-local calendar day (`calendar_day_diff == 1`). Same-day 13h comparisons
    use truthful same-day clock wording.
    """
    # Previous reader-local calendar day in America/New_York (Oct 13 5:00 PM EDT -> Oct 14 9:30 AM EDT)
    prev_day = format_movement_timeframe(
        "2026-10-13T21:00:00+00:00",
        "2026-10-14T13:30:00+00:00",
        tz_name="America/New_York",
    )
    assert prev_day["valid"] is True
    assert prev_day["calendar_day_diff"] == 1
    assert prev_day["crosses_previous_calendar_day"] is True
    assert prev_day["chip_timeframe"] == "since yesterday"
    assert prev_day["sentence_timeframe"] == "since yesterday"

    # Same reader-local calendar day in America/New_York despite 13h age (Oct 14 1:15 AM EDT -> Oct 14 2:15 PM EDT)
    same_day = format_movement_timeframe(
        "2026-10-14T05:15:00+00:00",
        "2026-10-14T18:15:00+00:00",
        tz_name="America/New_York",
    )
    assert same_day["valid"] is True
    assert same_day["calendar_day_diff"] == 0
    assert same_day["crosses_previous_calendar_day"] is False
    assert same_day["chip_timeframe"] == "since 1:15 AM"
    assert same_day["sentence_timeframe"] == "today since 1:15 AM"


def test_case14_inventory_completeness_and_unpriced_member_reachability() -> None:
    """Section 6F / Section 8 Case 14:
    Distinguishes represented member count from provider inventory completeness
    and keeps represented unpriced members reachable with honest state.
    """
    oct31_unpriced = build_deadline_member_contract(
        market_id=65678073,
        name="Will Zacharia be out as Prime Minister of Israel by October 31?",
        source="polymarket",
        external_id="cond-oct31",
        group_id="polymarket:1183118",
        resolution_date="2026-10-31T23:59:00+00:00",
        market_metadata={"market_count": 4},
        outcomes=_make_oct31_outcomes(stored_yes_change=None, yes_prob=None),
        now=RETAINED_NOW,
    )
    dec31_priced = build_deadline_member_contract(
        market_id=65678074,
        name="Will Zacharia be out as Prime Minister of Israel by December 31?",
        source="polymarket",
        external_id="cond-dec31",
        group_id="polymarket:1183118",
        resolution_date="2026-12-31T23:59:00+00:00",
        market_metadata={"market_count": 4},
        outcomes=_make_dec31_outcomes(stored_yes_change=None, yes_prob=0.245),
        now=RETAINED_NOW,
    )
    assert oct31_unpriced is not None and dec31_priced is not None
    assert oct31_unpriced["yes_probability"] is None
    assert oct31_unpriced["movement_status"] == "unpriced"

    family, err = verify_and_select_deadline_family([oct31_unpriced, dec31_priced], now=RETAINED_NOW)
    assert err is None
    assert family is not None
    assert family["represented_count"] == 2
    assert family["provider_market_count"] == 4
    assert family["inventory_complete"] is False
    assert family["representative_market_id"] == 65678074
    assert len(family["members"]) == 2
    assert family["members"][0]["market_id"] == 65678073
    assert family["members"][0]["detail_href"] == "/futures/65678073"
