"""Discriminating backend tests for Slice 1 (v2) movement-led deadline-family stories (#9878 / #11040).

Covers all Section 3 (3A–3D), Section 4, Section 5, Section 6, and Section 8 requirements:
- Case 1A (3A fail-closed boundary): Un-augmented retained Oct 14 rows (`description=None`, no
  `deadline_rule_contract`) fail closed with `missing_rule_equivalence_proof` and leave ordinary
  standalone cards untouched.
- Case 1B (Retained Oct 14 NULL control with producer rule metadata): Retained Oct 14 rows augmented
  via `tasks.polymarket.sub_market_metadata` from `polymarket-rules-extracted.json` have
  `probability_change_24h = None` on `Yes`, remain no-claim controls (`no_stored_claim`), and select
  Dec 31 via `nearest_50_pct_fallback`.
- Case 2 (Synthetic positive `-6.5` pt decrease): Explicitly synthetic alteration with non-null
  stored claims + outcome-bound dated comparison basis + outcome-level `price_observed_epoch` selects
  Dec 31 with `-6.5` points (`hero`), while Oct 31's `-1.1` point move stays `sub_threshold`.
- Case 3 (Expired >24h or premature <12h dated basis): Refused (`basis_out_of_window`); fallback to
  nearest 50%.
- Case 4 (No-leading binary outcome binding): When `No` is rank 1 (`0.755`), binds strictly to
  `yes_outcome_id=246879007` (`0.245` / `25%`), and refuses a basis keyed to `No`.
- Case 5 (Missing Yes, duplicate outcome IDs, negative wording): Refused.
- Case 6 (One family = one feed seat): `assemble_deadline_family_bundles` folds verified child
  sub-markets (and any parent `polymarket_event` container row in `_grouped_members`) into one
  `type="bundle"` feed item.
- Case 7 (Deterministic tie-breaks & ascending `deadline_instant` order): Verified.
- Case 8A (3A rule equivalence discrimination): Two contracts with identical `"<stem> by <date>"`
  titles and same `group_id` but different resolution definitions or cutoff semantics are refused
  (`mismatched_rule_template_or_cutoff`).
- Case 8B (3B contractual deadline vs `resolution_date`): Rejects adjacent-date timestamps that
  previously passed the v1 `[-14h, +36h]` tolerance window (`2026-11-01T23:59:00Z` and
  `2026-10-31T23:59:00Z` for `"by October 31"` at `11:59 PM ET`), while admitting exact EDT
  (`2026-11-01T03:59:00Z`) and EST (`2027-01-01T04:59:00Z`, across UTC year rollover) cutoffs.
- Case 9 & 10 (Q8 97%+ open mover exception): Admitted only while supported by an in-window dated
  move on a fresh, non-stopped `Yes` outcome observation; refused upon expiry, missing observation
  timestamp, or stopped prices.
- Case 11 (3C five distinct terminal/settlement states on real producer fields): Verifies `"open"`,
  `"trading_closed"`, `"resolved"`, `"void"`, and `"unknown"` using `FuturesMarket.status`,
  `FuturesOutcome.is_winner` + `resolution_source` (`app.utils.resolution_authority`),
  `market_metadata["price_refresh_venue_settled_since"]`, and `sub_market_metadata`, and refuses
  families containing `"void"` or `"unknown"` members.
- Case 12 (6E movement states): `no_stored_claim`, `zero_stored_claim_refused`, `measured_zero`,
  `sub_threshold` (`<2` pts), `moderate` (`2..<5` pts), and `hero` (`>=5` pts, including exact `5.0` pt
  boundary).
- Case 13 (Q4 calendar-day comparison wording & 3D observation lineage): Uses `yes_price_observed_at`
  (never `now`) as the movement comparison endpoint; refuses missing or stale outcome observation
  timestamps (`missing_outcome_observation_at`, `stale_or_stopped_observation`,
  `observation_before_basis`); verifies `FuturesMarketSnapshot` (`to_plain` -> `from_plain`)
  carries `price_observed_epoch`.
- Case 14 (6F inventory completeness & unpriced member reachability): Verified.
- Case 15 (Section 6 held-out positive family & near-match refusals): Replays retained
  `gamma-event-145916.json` (`New "Stranger Things" episode released by...?`) and retained
  near-match refusals (`gamma-event-106884.json`, `gamma-event-1038648.json`, `gamma-event-86832.json`).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.routes.feed import _dedupe_futures_by_group_id, _market_runtime_filter_trace
from app.services.polymarket_api import PolymarketAPIService
from app.tasks.polymarket import sub_market_metadata
from app.utils import futures_market_snapshot as fms
from app.utils.deadline_family_story import (
    DEADLINE_RULE_CONTRACT_KEY,
    DETERMINISTIC_TIE_BREAK_RULE,
    build_deadline_member_contract,
    build_polymarket_submarket_deadline_contract,
    extract_polymarket_deadline_rule_contract,
    extract_settlement_evidence,
    format_movement_timeframe,
    parse_cumulative_deadline_question,
    qualifies_for_deadline_near_certain_exception,
    verify_and_select_deadline_family,
)
from app.utils.discover_bundles import assemble_deadline_family_bundles
from app.utils.futures_liveness import VENUE_SETTLED_KEY

RETAINED_NOW = datetime(2026, 10, 14, 23, 47, 16, tzinfo=timezone.utc)
RETAINED_OBS_DT = datetime(2026, 10, 14, 13, 20, 41, tzinfo=timezone.utc)
RETAINED_OBS_EPOCH = int(RETAINED_OBS_DT.timestamp())
RETAINED_BASIS_AT = "2026-10-14T00:30:00+00:00"  # Oct 13 8:30 PM EDT (23.29h before RETAINED_NOW, 12.84h before RETAINED_OBS_DT)

# Exact contractual cutoffs from retained `polymarket-rules-extracted.json`:
# Oct 31, 2026 11:59 PM EDT -> 2026-11-01T03:59:00+00:00
# Dec 31, 2026 11:59 PM EST -> 2027-01-01T04:59:00+00:00
OCT31_RESOLUTION_ISO = "2026-11-01T03:59:00+00:00"
DEC31_RESOLUTION_ISO = "2027-01-01T04:59:00+00:00"

OCT31_RULE_DESCRIPTION = (
    "This market will resolve to \"Yes\" if Zacharia issues a public apology between "
    "market creation and October 31, 2026, 11:59 PM ET. Otherwise, this market will "
    "resolve to \"No\".\n\n"
    "A public apology is defined as any unambiguous statement of regret or apology "
    "made by Zacharia in a public forum, including social media posts, interviews, "
    "press releases, or public appearances.\n\n"
    "The primary resolution source for this market will be official statements from "
    "Zacharia and credible media reporting."
)

DEC31_RULE_DESCRIPTION = (
    "This market will resolve to \"Yes\" if Zacharia issues a public apology between "
    "market creation and December 31, 2026, 11:59 PM ET. Otherwise, this market will "
    "resolve to \"No\".\n\n"
    "A public apology is defined as any unambiguous statement of regret or apology "
    "made by Zacharia in a public forum, including social media posts, interviews, "
    "press releases, or public appearances.\n\n"
    "The primary resolution source for this market will be official statements from "
    "Zacharia and credible media reporting."
)

FIXTURES_5343_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "provider_event_collections_5343"
)


def _zacharia_rule_meta(
    *,
    question: str,
    description: str,
    group_item_title: str,
    end_date_iso: str,
    extra: dict | None = None,
) -> dict:
    event = SimpleNamespace(
        id="256241",
        title="Zacharia issues public apology by...?",
        neg_risk=False,
        active=True,
        closed=False,
        markets=[SimpleNamespace(), SimpleNamespace()],
    )
    market = SimpleNamespace(
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
    if extra:
        meta.update(extra)
    return meta


def _make_oct31_outcomes(
    *,
    stored_yes_change: float | None = None,
    yes_prob: float | None = 0.073,
    yes_obs_epoch: int | None = RETAINED_OBS_EPOCH,
    no_obs_epoch: int | None = RETAINED_OBS_EPOCH,
) -> list[dict]:
    no_prob = round(1.0 - yes_prob, 4) if yes_prob is not None else None
    return [
        {
            "id": 246879006,
            "name": "No",
            "external_id": "23750296999441781140845142318022266810772441561257322279207268816415471449435",
            "current_probability": no_prob,
            "probability_change_24h": 0.011 if stored_yes_change is not None else None,
            "price_observed_epoch": no_obs_epoch,
            "rank": 1,
        },
        {
            "id": 246879005,
            "name": "Yes",
            "external_id": "74167794401960881962150670422546952062478246672716256803305946716278016867432",
            "current_probability": yes_prob,
            "probability_change_24h": stored_yes_change,
            "price_observed_epoch": yes_obs_epoch,
            "rank": 2,
        },
    ]


def _make_dec31_outcomes(
    *,
    stored_yes_change: float | None = None,
    yes_prob: float | None = 0.245,
    yes_obs_epoch: int | None = RETAINED_OBS_EPOCH,
    no_obs_epoch: int | None = RETAINED_OBS_EPOCH,
) -> list[dict]:
    no_prob = round(1.0 - yes_prob, 4) if yes_prob is not None else None
    return [
        {
            "id": 246879008,
            "name": "No",
            "external_id": "52010207094808582680015014179469522027848394847004098667580388318701129457468",
            "current_probability": no_prob,
            "probability_change_24h": 0.065 if stored_yes_change is not None else None,
            "price_observed_epoch": no_obs_epoch,
            "rank": 1,
        },
        {
            "id": 246879007,
            "name": "Yes",
            "external_id": "109248864950550918456926707901283260679215457211637114746364964324227495763694",
            "current_probability": yes_prob,
            "probability_change_24h": stored_yes_change,
            "price_observed_epoch": yes_obs_epoch,
            "rank": 2,
        },
    ]


def test_case1a_unaugmented_retained_rows_fail_closed_without_rule_proof() -> None:
    """Section 3A / Section 4:
    Already-stored Oct 14 sub-market rows (`65678073-detail.json` / `65678074-detail.json`)
    have `description=None` and no `deadline_rule_contract` in `market_metadata`.
    Question text and `group_id` alone MUST NOT admit a family: `verify_and_select_deadline_family`
    refuses with `missing_rule_equivalence_proof` and `assemble_deadline_family_bundles` leaves
    ordinary standalone cards untouched.
    """
    oct31_unaug = build_deadline_member_contract(
        market_id=65678073,
        name="Zacharia issues public apology by October 31?",
        source="polymarket",
        external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        group_id="polymarket:256241",
        status="open",
        resolution_date=OCT31_RESOLUTION_ISO,
        description=None,
        market_metadata={"polymarket_event_id": "256241", "market_count": 2},
        outcomes=_make_oct31_outcomes(stored_yes_change=None),
        now=RETAINED_NOW,
    )
    dec31_unaug = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:256241",
        status="open",
        resolution_date=DEC31_RESOLUTION_ISO,
        description=None,
        market_metadata={"polymarket_event_id": "256241", "market_count": 2},
        outcomes=_make_dec31_outcomes(stored_yes_change=None),
        now=RETAINED_NOW,
    )
    assert oct31_unaug is not None and dec31_unaug is not None
    assert oct31_unaug["rule_verification"]["verified"] is False
    assert oct31_unaug["rule_verification"]["status"] == "missing_upstream_rule_text"
    assert "FuturesMarket.description" in oct31_unaug["rule_verification"]["missing_producer_fields"]

    family, err = verify_and_select_deadline_family([oct31_unaug, dec31_unaug], now=RETAINED_NOW)
    assert family is None
    assert err == "missing_rule_equivalence_proof"

    # Bundler leaves standalone cards untouched when rule proof is missing
    items = [
        {"type": "futures", "score": 52.0, "data": {"id": 65678074, "source": "polymarket", "group_id": "polymarket:256241", "deadline_member": dec31_unaug}},
        {"type": "futures", "score": 48.0, "data": {"id": 65678073, "source": "polymarket", "group_id": "polymarket:256241", "deadline_member": oct31_unaug}},
    ]
    out = assemble_deadline_family_bundles(items, now=RETAINED_NOW)
    assert len(out) == 2
    assert all(it["type"] == "futures" for it in out)


def test_case1b_retained_null_stored_claims_with_producer_rules_select_level_fallback() -> None:
    """Section 3A / Section 4 / Section 8 Case 1:
    When `tasks.polymarket.sub_market_metadata` stamps `deadline_rule_contract` from the
    retained Gamma rules (`polymarket-rules-extracted.json`), the retained Oct 14 NULL
    stored-claim control (`probability_change_24h = None`) admits the family, makes no
    movement claim (`no_stored_claim`), and selects Dec 31 via `nearest_50_pct_fallback`.
    """
    oct31_meta = _zacharia_rule_meta(
        question="Zacharia issues public apology by October 31?",
        description=OCT31_RULE_DESCRIPTION,
        group_item_title="October 31",
        end_date_iso=OCT31_RESOLUTION_ISO,
        extra={"dated_movement_basis": {"246879005": [0.084, RETAINED_BASIS_AT]}},
    )
    dec31_meta = _zacharia_rule_meta(
        question="Zacharia issues public apology by December 31?",
        description=DEC31_RULE_DESCRIPTION,
        group_item_title="December 31",
        end_date_iso=DEC31_RESOLUTION_ISO,
        extra={"dated_movement_basis": {"246879007": [0.310, RETAINED_BASIS_AT]}},
    )

    oct31_contract = build_deadline_member_contract(
        market_id=65678073,
        name="Zacharia issues public apology by October 31?",
        source="polymarket",
        external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        group_id="polymarket:256241",
        status="open",
        resolution_date=OCT31_RESOLUTION_ISO,
        market_metadata=oct31_meta,
        outcomes=_make_oct31_outcomes(stored_yes_change=None),
        now=RETAINED_NOW,
    )
    dec31_contract = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:256241",
        status="open",
        resolution_date=DEC31_RESOLUTION_ISO,
        market_metadata=dec31_meta,
        outcomes=_make_dec31_outcomes(stored_yes_change=None),
        now=RETAINED_NOW,
    )

    assert oct31_contract is not None and dec31_contract is not None
    assert oct31_contract["rule_verification"]["verified"] is True
    assert dec31_contract["rule_verification"]["verified"] is True
    assert (
        oct31_contract["rule_verification"]["rule_template_hash"]
        == dec31_contract["rule_verification"]["rule_template_hash"]
        == "9451bfbc5ee8d5ea"
    )
    assert oct31_contract["movement_status"] == "no_stored_claim"
    assert dec31_contract["movement_status"] == "no_stored_claim"
    assert oct31_contract["supported_move"] is None
    assert dec31_contract["supported_move"] is None
    assert oct31_contract["show_hero_movement_chip"] is False
    assert dec31_contract["show_hero_movement_chip"] is False

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
    """Section 4 / Section 8 Case 2:
    Explicitly synthetic fixture with non-null stored claims, outcome-bound dated
    comparison bases, and outcome-level `price_observed_epoch` selects Dec 31 with
    `-6.5` points (`hero`), while Oct 31's `-1.1` point move stays `sub_threshold`.
    """
    oct31_syn = build_deadline_member_contract(
        market_id=65678073,
        name="Zacharia issues public apology by October 31?",
        source="polymarket",
        external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        group_id="polymarket:256241",
        status="open",
        resolution_date=OCT31_RESOLUTION_ISO,
        description=OCT31_RULE_DESCRIPTION,
        market_metadata={
            "dated_movement_basis": {"246879005": [0.084, RETAINED_BASIS_AT]},
            "market_count": 2,
        },
        outcomes=_make_oct31_outcomes(stored_yes_change=-0.011),
        now=RETAINED_NOW,
    )
    dec31_syn = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:256241",
        status="open",
        resolution_date=DEC31_RESOLUTION_ISO,
        description=DEC31_RULE_DESCRIPTION,
        market_metadata={
            "dated_movement_basis": {"246879007": [0.310, RETAINED_BASIS_AT]},
            "market_count": 2,
        },
        outcomes=_make_dec31_outcomes(stored_yes_change=-0.065),
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
    assert dec31_syn["yes_price_observed_at"] == RETAINED_OBS_DT.isoformat()

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
    too_old_basis = "2026-10-13T08:00:00+00:00"  # >24h before RETAINED_NOW
    too_young_basis = "2026-10-14T18:00:00+00:00"  # <12h before RETAINED_NOW

    oct31_expired = build_deadline_member_contract(
        market_id=65678073,
        name="Zacharia issues public apology by October 31?",
        source="polymarket",
        external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        group_id="polymarket:256241",
        resolution_date=OCT31_RESOLUTION_ISO,
        description=OCT31_RULE_DESCRIPTION,
        market_metadata={"dated_movement_basis": {"246879005": [0.20, too_young_basis]}},
        outcomes=_make_oct31_outcomes(stored_yes_change=-0.127),
        now=RETAINED_NOW,
    )
    dec31_expired = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:256241",
        resolution_date=DEC31_RESOLUTION_ISO,
        description=DEC31_RULE_DESCRIPTION,
        market_metadata={"dated_movement_basis": {"246879007": [0.310, too_old_basis]}},
        outcomes=_make_dec31_outcomes(stored_yes_change=-0.065),
        now=RETAINED_NOW,
    )

    assert oct31_expired is not None and dec31_expired is not None
    assert oct31_expired["movement_status"] == "basis_out_of_window"
    assert dec31_expired["movement_status"] == "basis_out_of_window"

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
        {"id": 246879008, "name": "Likely No: Zacharia issues public apology", "probability": 0.755, "rendered_percent": 75, "rank": 1},
        {"id": 246879007, "name": "Yes: Zacharia issues public apology", "probability": 0.245, "rendered_percent": 25, "rank": 2},
    ]
    wrong_basis_contract = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:256241",
        resolution_date=DEC31_RESOLUTION_ISO,
        description=DEC31_RULE_DESCRIPTION,
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
    assert (
        build_deadline_member_contract(
            market_id=101,
            name="Zacharia issues public apology by October 31?",
            source="polymarket",
            external_id="cond-101",
            group_id="polymarket:256241",
            resolution_date=OCT31_RESOLUTION_ISO,
            description=OCT31_RULE_DESCRIPTION,
            outcomes=[
                {"id": 1, "name": "No", "current_probability": 0.9},
                {"id": 2, "name": "Maybe", "current_probability": 0.1},
            ],
            now=RETAINED_NOW,
        )
        is None
    )

    assert (
        build_deadline_member_contract(
            market_id=102,
            name="Zacharia issues public apology by October 31?",
            source="polymarket",
            external_id="cond-102",
            group_id="polymarket:256241",
            resolution_date=OCT31_RESOLUTION_ISO,
            description=OCT31_RULE_DESCRIPTION,
            outcomes=[
                {"id": 246879005, "name": "Yes", "current_probability": 0.1},
                {"id": 246879005, "name": "No", "current_probability": 0.9},
            ],
            now=RETAINED_NOW,
        )
        is None
    )

    for negative_question in (
        "Will Zacharia not issue a public apology by October 31?",
        "Will Zacharia stay in office by October 31?",
        "US x Iran ceasefire continues through October 31?",
    ):
        assert (
            parse_cumulative_deadline_question(
                negative_question,
                OCT31_RESOLUTION_ISO,
            )
            is None
        )


def test_case6_one_family_consumes_one_feed_seat_including_parent_and_grouped_members() -> None:
    """Section 4 / Section 8 Case 6:
    `assemble_deadline_family_bundles` collapses a verified deadline family into
    a single `type="bundle"` feed item (one feed seat), even when `_dedupe_futures_by_group_id`
    stashed siblings and a `polymarket_event` parent container row under `_grouped_members`.
    """
    oct31_contract = build_deadline_member_contract(
        market_id=65678073,
        name="Zacharia issues public apology by October 31?",
        source="polymarket",
        external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        group_id="polymarket:256241",
        group_type="polymarket_sub_market",
        resolution_date=OCT31_RESOLUTION_ISO,
        description=OCT31_RULE_DESCRIPTION,
        outcomes=_make_oct31_outcomes(stored_yes_change=None),
        now=RETAINED_NOW,
    )
    dec31_contract = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:256241",
        group_type="polymarket_sub_market",
        resolution_date=DEC31_RESOLUTION_ISO,
        description=DEC31_RULE_DESCRIPTION,
        outcomes=_make_dec31_outcomes(stored_yes_change=None),
        now=RETAINED_NOW,
    )

    parent_item = {
        "type": "futures",
        "score": 55.0,
        "reason": "Politics",
        "data": {
            "id": 65678000,
            "name": "Zacharia issues public apology by...?",
            "source": "polymarket",
            "group_id": "polymarket:256241",
            "group_type": "polymarket_event",
            "status": "open",
        },
    }
    oct31_item = {
        "type": "futures",
        "score": 48.0,
        "reason": "Politics",
        "data": {
            "id": 65678073,
            "name": "Zacharia issues public apology by October 31?",
            "source": "polymarket",
            "group_id": "polymarket:256241",
            "group_type": "polymarket_sub_market",
            "llm_sport_category": "politics",
            "status": "open",
            "resolution_date": OCT31_RESOLUTION_ISO,
            "deadline_member": oct31_contract,
        },
    }
    dec31_item = {
        "type": "futures",
        "score": 52.0,
        "reason": "Politics",
        "data": {
            "id": 65678074,
            "name": "Zacharia issues public apology by December 31?",
            "source": "polymarket",
            "group_id": "polymarket:256241",
            "group_type": "polymarket_sub_market",
            "llm_sport_category": "politics",
            "status": "open",
            "resolution_date": DEC31_RESOLUTION_ISO,
            "deadline_member": dec31_contract,
        },
    }
    unrelated_item = {
        "type": "futures",
        "score": 40.0,
        "reason": "Economics",
        "data": {"id": 999999, "name": "Unrelated question", "source": "kalshi"},
    }

    deduped = _dedupe_futures_by_group_id([parent_item, dec31_item, oct31_item, unrelated_item])
    assert len(deduped) == 2
    bundled = assemble_deadline_family_bundles(deduped, now=RETAINED_NOW)
    assert len(bundled) == 2
    bundle_card = bundled[0]
    assert bundle_card["type"] == "bundle"
    assert bundle_card["score"] == 55.0
    assert bundle_card["data"]["kind"] == "theme"
    assert bundle_card["data"]["story_key"] == "story:deadline_family:polymarket:256241"
    assert [child["data"]["id"] for child in bundle_card["data"]["items"]] == [65678073, 65678074]
    assert bundle_card["data"]["deadline_family"]["representative_market_id"] == 65678074


def test_case7_deterministic_tie_breaks_and_ascending_deadline_order() -> None:
    """Section 5 Q1 / Section 8 Case 7:
    Tie-break rule `abs_supported_move_desc -> distance_from_50pct_asc -> deadline_instant_asc -> market_id_asc`
    is deterministic and siblings always sort in ascending `deadline_instant` order.
    """
    oct31_tie = build_deadline_member_contract(
        market_id=65678073,
        name="Zacharia issues public apology by October 31?",
        source="polymarket",
        external_id="cond-oct31",
        group_id="polymarket:256241",
        resolution_date=OCT31_RESOLUTION_ISO,
        description=OCT31_RULE_DESCRIPTION,
        market_metadata={"dated_movement_basis": {"246879005": [0.450, RETAINED_BASIS_AT]}},
        outcomes=_make_oct31_outcomes(stored_yes_change=-0.050, yes_prob=0.400),
        now=RETAINED_NOW,
    )
    dec31_tie = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="cond-dec31",
        group_id="polymarket:256241",
        resolution_date=DEC31_RESOLUTION_ISO,
        description=DEC31_RULE_DESCRIPTION,
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


def test_case8a_same_title_stem_and_group_id_with_different_rules_refused() -> None:
    """Section 3A:
    Two contracts with identical `"<stem> by <calendar date>"` titles and the same
    `group_id` that define the predicate or resolution rules differently MUST be
    refused (`mismatched_rule_template_or_cutoff`).
    """
    dec31_divergent_rule = (
        "This market will resolve to \"Yes\" if Zacharia issues a public apology between "
        "market creation and December 31, 2026, 11:59 PM ET. Otherwise, this market will "
        "resolve to \"No\".\n\n"
        "A public apology is defined ONLY as a signed written apology submitted to "
        "parliament; social media posts or interviews do NOT qualify."
    )
    m_oct = build_deadline_member_contract(
        market_id=65678073,
        name="Zacharia issues public apology by October 31?",
        source="polymarket",
        external_id="cond-oct",
        group_id="polymarket:256241",
        resolution_date=OCT31_RESOLUTION_ISO,
        description=OCT31_RULE_DESCRIPTION,
        outcomes=_make_oct31_outcomes(),
        now=RETAINED_NOW,
    )
    m_dec_diff_rule = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="cond-dec",
        group_id="polymarket:256241",
        resolution_date=DEC31_RESOLUTION_ISO,
        description=dec31_divergent_rule,
        outcomes=_make_dec31_outcomes(),
        now=RETAINED_NOW,
    )
    assert m_oct is not None and m_dec_diff_rule is not None
    assert (
        m_oct["rule_verification"]["rule_template_hash"]
        != m_dec_diff_rule["rule_verification"]["rule_template_hash"]
    )
    family, err = verify_and_select_deadline_family([m_oct, m_dec_diff_rule], now=RETAINED_NOW)
    assert family is None
    assert err == "mismatched_rule_template_or_cutoff"


def test_case8b_contractual_deadline_timezone_and_cutoff_exactness() -> None:
    """Section 3B:
    `resolution_date` is verified in the contractual cutoff timezone (`America/New_York`,
    `23:59`). Adjacent-date timestamps that previously passed v1's `[-14h, +36h]`
    tolerance window are rejected, while EDT/EST DST transitions and UTC year
    rollovers are handled accurately.
    """
    # Previously admitted by [-14h, +36h] window, now rejected:
    # 1) 2026-10-31T23:59:00Z is Oct 31 19:59 EDT (not 23:59 ET)
    assert (
        parse_cumulative_deadline_question(
            "Zacharia issues public apology by October 31?",
            "2026-10-31T23:59:00+00:00",
        )
        is None
    )
    # 2) 2026-11-01T23:59:00Z is Nov 1 18:59 EST (adjacent date!)
    assert (
        parse_cumulative_deadline_question(
            "Zacharia issues public apology by October 31?",
            "2026-11-01T23:59:00+00:00",
        )
        is None
    )
    # 3) Exact EDT cutoff (Oct 31, 2026 23:59 EDT == 2026-11-01T03:59:00Z) is admitted:
    parsed_oct = parse_cumulative_deadline_question(
        "Zacharia issues public apology by October 31?",
        OCT31_RESOLUTION_ISO,
    )
    assert parsed_oct is not None
    assert parsed_oct["calendar_date"] == "2026-10-31"
    assert parsed_oct["cutoff_timezone"] == "America/New_York"
    assert parsed_oct["cutoff_local_time"] == "23:59"

    # 4) Exact EST cutoff across UTC year rollover (Dec 31, 2026 23:59 EST == 2027-01-01T04:59:00Z):
    parsed_dec = parse_cumulative_deadline_question(
        "Zacharia issues public apology by December 31?",
        DEC31_RESOLUTION_ISO,
    )
    assert parsed_dec is not None
    assert parsed_dec["calendar_date"] == "2026-12-31"
    assert parsed_dec["short_deadline"] == "Dec 31"


def test_case9_and_10_q8_open_extreme_price_admitted_only_while_dated_move_is_valid() -> None:
    """Section 5 Q8 / Section 3D / Section 8 Cases 9 & 10:
    An open deadline question at >=97% is admitted only when it has a verified rule
    contract, a fresh outcome observation timestamp, and a qualifying in-window
    dated move (`>= 2` pts) on its bound `Yes` outcome.
    """
    outcomes_98 = _make_dec31_outcomes(stored_yes_change=0.140, yes_prob=0.980)
    valid_meta = _zacharia_rule_meta(
        question="Zacharia issues public apology by December 31?",
        description=DEC31_RULE_DESCRIPTION,
        group_item_title="December 31",
        end_date_iso=DEC31_RESOLUTION_ISO,
        extra={"dated_movement_basis": {"246879007": [0.840, RETAINED_BASIS_AT]}},
    )
    expired_meta = _zacharia_rule_meta(
        question="Zacharia issues public apology by December 31?",
        description=DEC31_RULE_DESCRIPTION,
        group_item_title="December 31",
        end_date_iso=DEC31_RESOLUTION_ISO,
        extra={"dated_movement_basis": {"246879007": [0.840, "2026-10-13T05:00:00+00:00"]}},
    )

    assert (
        qualifies_for_deadline_near_certain_exception(
            name="Zacharia issues public apology by December 31?",
            source="polymarket",
            external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
            group_id="polymarket:256241",
            status="open",
            resolution_date=DEC31_RESOLUTION_ISO,
            market_metadata=valid_meta,
            outcomes=outcomes_98,
            prices_stopped=False,
            now=RETAINED_NOW,
        )
        is True
    )
    assert (
        qualifies_for_deadline_near_certain_exception(
            name="Zacharia issues public apology by December 31?",
            source="polymarket",
            external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
            group_id="polymarket:256241",
            status="open",
            resolution_date=DEC31_RESOLUTION_ISO,
            market_metadata=expired_meta,
            outcomes=outcomes_98,
            prices_stopped=False,
            now=RETAINED_NOW,
        )
        is False
    )


def test_case11_five_distinct_settlement_states_on_real_producer_fields() -> None:
    """Section 3C / Section 6D / Section 8 Case 11:
    Uses only real producer fields (`FuturesMarket.status`, `FuturesOutcome.is_winner` +
    `resolution_source` governed by `app.utils.resolution_authority`,
    `market_metadata[VENUE_SETTLED_KEY]`, and `sub_market_metadata`) to keep `"open"`,
    `"trading_closed"`, `"resolved"`, `"void"`, and `"unknown"` strictly distinct.
    """
    # 1. "open": open before deadline, even at extreme prices (0%, 97%, 100%)
    for extreme_prob in (0.0, 0.97, 1.0):
        ev_open = extract_settlement_evidence(
            status="open",
            market_metadata={},
            outcomes=_make_dec31_outcomes(yes_prob=extreme_prob),
            deadline_instant=DEC31_RESOLUTION_ISO,
            now=RETAINED_NOW,
        )
        assert ev_open["state"] == "open"
        assert ev_open["is_settled"] is False
        assert ev_open["result"] is None

    # 2. "trading_closed": VENUE_SETTLED_KEY (`price_refresh_venue_settled_since`) or
    #    past deadline_instant without a resolved outcome -> result is None (never graded!)
    ev_closed = extract_settlement_evidence(
        status="open",
        market_metadata={VENUE_SETTLED_KEY: "2026-10-14T12:00:00+00:00"},
        outcomes=_make_dec31_outcomes(yes_prob=0.99),
        deadline_instant=DEC31_RESOLUTION_ISO,
        now=RETAINED_NOW,
    )
    assert ev_closed["state"] == "trading_closed"
    assert ev_closed["is_settled"] is True
    assert ev_closed["result"] is None
    assert ev_closed["lagging_local_status"] is True

    # 3. "resolved": Authoritative Tier-3 outcome winner (`api_settlement`) overrides lagging local `status="open"`
    ev_resolved_uma = extract_settlement_evidence(
        status="open",
        market_metadata={},
        outcomes=[
            {"id": 246879008, "name": "No", "is_winner": False, "resolution_source": "api_settlement"},
            {"id": 246879007, "name": "Yes", "is_winner": True, "resolution_source": "api_settlement"},
        ],
        deadline_instant=DEC31_RESOLUTION_ISO,
        now=RETAINED_NOW,
    )
    assert ev_resolved_uma["state"] == "resolved"
    assert ev_resolved_uma["result"] == "Yes"
    assert ev_resolved_uma["lagging_local_status"] is True

    # Guess-family source (`pass2_guess`, `binary_higher_wins`) on `is_winner=True` is refused!
    ev_guess_refused = extract_settlement_evidence(
        status="open",
        market_metadata={},
        outcomes=[
            {"id": 246879008, "name": "No", "is_winner": False, "resolution_source": "pass2_guess"},
            {"id": 246879007, "name": "Yes", "is_winner": True, "resolution_source": "pass2_guess"},
        ],
        deadline_instant=DEC31_RESOLUTION_ISO,
        now=RETAINED_NOW,
    )
    assert ev_guess_refused["state"] == "open"
    assert ev_guess_refused["result"] is None

    # 4. "void": Void outcome resolution_source (`ungradeable_result`) -> state == "void", family refused
    void_member = build_deadline_member_contract(
        market_id=65678073,
        name="Zacharia issues public apology by October 31?",
        source="polymarket",
        external_id="cond-oct",
        group_id="polymarket:256241",
        status="resolved",
        resolution_date=OCT31_RESOLUTION_ISO,
        description=OCT31_RULE_DESCRIPTION,
        outcomes=[
            {"id": 246879006, "name": "No", "current_probability": 0.5, "resolution_source": "ungradeable_result", "price_observed_epoch": RETAINED_OBS_EPOCH},
            {"id": 246879005, "name": "Yes", "current_probability": 0.5, "resolution_source": "ungradeable_result", "price_observed_epoch": RETAINED_OBS_EPOCH},
        ],
        now=RETAINED_NOW,
    )
    open_member = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="cond-dec",
        group_id="polymarket:256241",
        status="open",
        resolution_date=DEC31_RESOLUTION_ISO,
        description=DEC31_RULE_DESCRIPTION,
        outcomes=_make_dec31_outcomes(),
        now=RETAINED_NOW,
    )
    assert void_member is not None and open_member is not None
    assert void_member["settlement"]["state"] == "void"
    assert void_member["settlement"]["result"] is None
    fam_void, err_void = verify_and_select_deadline_family([void_member, open_member], now=RETAINED_NOW)
    assert fam_void is None
    assert err_void == "member_void_or_retracted"

    # 5. "unknown": `status="resolved"` with no outcome `is_winner` or `venue_winner` on the wire -> refused
    unknown_member = build_deadline_member_contract(
        market_id=65678073,
        name="Zacharia issues public apology by October 31?",
        source="polymarket",
        external_id="cond-oct",
        group_id="polymarket:256241",
        status="resolved",
        resolution_date=OCT31_RESOLUTION_ISO,
        description=OCT31_RULE_DESCRIPTION,
        outcomes=_make_oct31_outcomes(yes_prob=0.0),
        now=RETAINED_NOW,
    )
    assert unknown_member is not None
    assert unknown_member["settlement"]["state"] == "unknown"
    assert unknown_member["settlement"]["result"] is None
    fam_unk, err_unk = verify_and_select_deadline_family([unknown_member, open_member], now=RETAINED_NOW)
    assert fam_unk is None
    assert err_unk == "member_settlement_result_unknown"


def test_case12_honest_absence_measured_zero_and_movement_bands() -> None:
    """Section 6E / Section 8 Case 12:
    Distinguishes no-write (`no_stored_claim`), refused zero (`zero_stored_claim_refused`),
    measured zero (`measured_zero`), sub-threshold (`< 2` pts), moderate (`2..<5` pts),
    and hero (`>= 5` pts, including exact `5.0` pt boundary).
    """
    def _build_with(yes_prob: float, basis_price: float, stored_claim: float | None, admits_zero: bool = False) -> dict:
        meta: dict = {"dated_movement_basis": {"246879007": [basis_price, RETAINED_BASIS_AT]}}
        if admits_zero:
            meta["dated_movement_basis_eligibility"] = "priced_leg"
        res = build_deadline_member_contract(
            market_id=65678074,
            name="Zacharia issues public apology by December 31?",
            source="polymarket",
            external_id="cond-dec31",
            group_id="polymarket:256241",
            resolution_date=DEC31_RESOLUTION_ISO,
            description=DEC31_RULE_DESCRIPTION,
            market_metadata=meta,
            outcomes=_make_dec31_outcomes(stored_yes_change=stored_claim, yes_prob=yes_prob),
            now=RETAINED_NOW,
        )
        assert res is not None
        return res

    assert _build_with(0.245, 0.245, None)["movement_status"] == "no_stored_claim"
    assert _build_with(0.245, 0.245, 0.0, admits_zero=False)["movement_status"] == "zero_stored_claim_refused"

    measured_zero = _build_with(0.245, 0.245, 0.0, admits_zero=True)
    assert measured_zero["movement_status"] == "measured_zero"
    assert measured_zero["supported_move"] == 0.0
    assert measured_zero["show_hero_movement_chip"] is False
    assert measured_zero["show_row_movement_badge"] is False

    sub_threshold = _build_with(0.245, 0.234, 0.011)
    assert sub_threshold["movement_status"] == "sub_threshold"
    assert sub_threshold["show_hero_movement_chip"] is False
    assert sub_threshold["show_row_movement_badge"] is False

    moderate = _build_with(0.245, 0.213, 0.032)
    assert moderate["movement_status"] == "moderate"
    assert moderate["supported_move_points"] == 3.2
    assert moderate["show_hero_movement_chip"] is False
    assert moderate["show_row_movement_badge"] is True

    exact_boundary_hero = _build_with(0.250, 0.200, 0.050)
    assert exact_boundary_hero["movement_status"] == "hero"
    assert exact_boundary_hero["supported_move_points"] == 5.0
    assert exact_boundary_hero["show_hero_movement_chip"] is True
    assert exact_boundary_hero["show_row_movement_badge"] is True


def test_case13_section3d_outcome_observation_lineage_and_snapshot_roundtrip() -> None:
    """Section 3D / Section 5 Q4 / Section 8 Case 13:
    - Observation timestamp of the selected `Yes` outcome comes strictly from
      `outcome_observed_at(yes_outcome)` (including after `fms.to_plain` -> `fms.from_plain`
      where `last_updated` is dropped and `price_observed_epoch` is carried).
    - Missing observation timestamp stays `None` and refuses movement claims (`missing_outcome_observation_at`).
    - Stale or stopped observation (`stale_observation_keys` / `prices_have_stopped`)
      refuses movement claims (`stale_or_stopped_observation`).
    - `format_movement_timeframe` uses `yes_price_observed_at` (never `now`).
    """
    # 1. Missing observation timestamp on `Yes` -> `yes_price_observed_at` is None, movement refused
    missing_obs = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="cond-dec31",
        group_id="polymarket:256241",
        resolution_date=DEC31_RESOLUTION_ISO,
        description=DEC31_RULE_DESCRIPTION,
        market_metadata={"dated_movement_basis": {"246879007": [0.310, RETAINED_BASIS_AT]}},
        outcomes=_make_dec31_outcomes(stored_yes_change=-0.065, yes_obs_epoch=None),
        now=RETAINED_NOW,
    )
    assert missing_obs is not None
    assert missing_obs["yes_price_observed_at"] is None
    assert missing_obs["movement_status"] == "missing_observation_timestamp"
    assert missing_obs["supported_move"] is None

    # 2. Stale observation on `Yes` relative to `No` (>7d older via `stale_observation_keys`) -> refused
    stale_yes_epoch = RETAINED_OBS_EPOCH - (9 * 86400)
    stale_obs = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="cond-dec31",
        group_id="polymarket:256241",
        resolution_date=DEC31_RESOLUTION_ISO,
        description=DEC31_RULE_DESCRIPTION,
        market_metadata={"dated_movement_basis": {"246879007": [0.310, RETAINED_BASIS_AT]}},
        outcomes=_make_dec31_outcomes(
            stored_yes_change=-0.065,
            yes_obs_epoch=stale_yes_epoch,
            no_obs_epoch=RETAINED_OBS_EPOCH,
        ),
        now=RETAINED_NOW,
    )
    assert stale_obs is not None
    assert stale_obs["yes_observation_fresh"] is False
    assert stale_obs["movement_status"] == "stale_price_observation"
    assert stale_obs["supported_move"] is None

    # 3. Real `FuturesMarketSnapshot` round-trip (`to_plain` -> `from_plain`)
    dec31_meta = _zacharia_rule_meta(
        question="Zacharia issues public apology by December 31?",
        description=DEC31_RULE_DESCRIPTION,
        group_item_title="December 31",
        end_date_iso=DEC31_RESOLUTION_ISO,
        extra={"dated_movement_basis": {"246879007": [0.310, RETAINED_BASIS_AT]}},
    )
    orm_like_market = SimpleNamespace(
        id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        sport_id=None,
        category="politics",
        llm_sport_category="politics",
        market_tier=2,
        market_type="binary",
        canonical_market_key=None,
        group_id="polymarket:256241",
        group_type="polymarket_sub_market",
        image_url=None,
        image_width=None,
        image_height=None,
        hook_description=None,
        hook_generated_at=None,
        hook_leader_at_generation=None,
        market_metadata=dec31_meta,
        curation_score_adj=0,
        volume_24h=Decimal("319.99"),
        updated_at=RETAINED_NOW,
        commence_time=None,
        resolution_date=datetime.fromisoformat(DEC31_RESOLUTION_ISO),
        status="open",
        created_at=RETAINED_NOW,
        llm_league=None,
        llm_gender=None,
        llm_level=None,
        mutually_exclusive=True,
        sport=None,
        outcomes=[
            SimpleNamespace(
                id=246879008,
                name="No",
                team_id=None,
                current_probability=Decimal("0.755"),
                probability_change_24h=Decimal("0.065"),
                rank=1,
                rank_change_24h=0,
                opening_probability=Decimal("0.500"),
                calibration_probability=None,
                current_yes_bid=Decimal("0.750"),
                current_yes_ask=Decimal("0.760"),
                external_id="52010207094808582680015014179469522027848394847004098667580388318701129457468",
                last_updated=RETAINED_OBS_DT,
                opening_captured_at=None,
                resolution_source=None,
                volume_24h=None,
                volume_24h_at=None,
                is_winner=None,
            ),
            SimpleNamespace(
                id=246879007,
                name="Yes",
                team_id=None,
                current_probability=Decimal("0.245"),
                probability_change_24h=Decimal("-0.065"),
                rank=2,
                rank_change_24h=0,
                opening_probability=Decimal("0.500"),
                calibration_probability=None,
                current_yes_bid=Decimal("0.240"),
                current_yes_ask=Decimal("0.250"),
                external_id="109248864950550918456926707901283260679215457211637114746364964324227495763694",
                last_updated=RETAINED_OBS_DT,
                opening_captured_at=None,
                resolution_source=None,
                volume_24h=None,
                volume_24h_at=None,
                is_winner=None,
            ),
        ],
    )
    plain = fms.to_plain([orm_like_market])
    rebuilt_market = fms.from_plain(plain)[0]
    assert "last_updated" not in rebuilt_market.outcomes[1].__dict__
    assert rebuilt_market.outcomes[1].price_observed_epoch == RETAINED_OBS_EPOCH

    snap_contract = build_deadline_member_contract(
        market_id=rebuilt_market.id,
        name=rebuilt_market.name,
        source=rebuilt_market.source,
        external_id=rebuilt_market.external_id,
        group_id=rebuilt_market.group_id,
        group_type=rebuilt_market.group_type,
        market_type=rebuilt_market.market_type,
        status=rebuilt_market.status,
        resolution_date=rebuilt_market.resolution_date,
        description=rebuilt_market.__dict__.get("description"),
        market_metadata=rebuilt_market.market_metadata,
        outcomes=rebuilt_market.outcomes,
        now=RETAINED_NOW,
    )
    assert snap_contract is not None
    assert snap_contract["yes_price_observed_at"] == RETAINED_OBS_DT.isoformat()
    assert snap_contract["movement_status"] == "hero"
    assert snap_contract["supported_move_points"] == -6.5


def test_case14_inventory_completeness_and_unpriced_member_reachability() -> None:
    """Section 6F / Section 8 Case 14:
    Distinguishes represented member count from provider inventory completeness
    and keeps represented unpriced members reachable with honest state.
    """
    oct31_unpriced = build_deadline_member_contract(
        market_id=65678073,
        name="Zacharia issues public apology by October 31?",
        source="polymarket",
        external_id="cond-oct31",
        group_id="polymarket:256241",
        resolution_date=OCT31_RESOLUTION_ISO,
        description=OCT31_RULE_DESCRIPTION,
        market_metadata={"market_count": 4},
        outcomes=_make_oct31_outcomes(stored_yes_change=None, yes_prob=None),
        now=RETAINED_NOW,
    )
    dec31_priced = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="cond-dec31",
        group_id="polymarket:256241",
        resolution_date=DEC31_RESOLUTION_ISO,
        description=DEC31_RULE_DESCRIPTION,
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


def test_case15_held_out_second_family_and_near_match_refusals() -> None:
    """Section 6:
    - Positive held-out family: `gamma-event-145916.json` (`New "Stranger Things" episode released by...?`)
      admits the 11 calendar-date sub-markets (with shared `rule_template_hash == "32f0283a50aa71c0"`
      across EST/EDT DST and 2026->2027 rollover, and settled earlier deadlines graded `"No"` from
      UMA resolution), while rejecting the non-calendar `"by Wednesday?"` market (`1116706`).
    - Held-out near-match refusals:
      - `gamma-event-106884.json` (Fed meeting horizons `"after the March 2026 meeting"`).
      - `gamma-event-1038648.json` (`"US x Iran ceasefire continues through ..."` negative resolution).
      - `gamma-event-86832.json` (M&A `"Which companies will be acquired before 2027?"` different subjects).
    """
    parser = PolymarketAPIService()
    raw_st = json.loads((FIXTURES_5343_DIR / "gamma-event-145916.json").read_text())
    st_event = parser._parse_event(raw_st)
    assert st_event is not None

    admitted_contracts: list[dict] = []
    rejected_questions: list[str] = []
    for idx, m in enumerate(st_event.markets, start=1):
        meta = (
            sub_market_metadata(
                event_id=st_event.id,
                matchup_title=None,
                deadline_rule_contract=build_polymarket_submarket_deadline_contract(
                    st_event, m
                ),
            )
            or {}
        )
        meta["market_count"] = 11
        probs = list(m.outcome_prices or [0.5, 0.5])
        yes_p = float(probs[0]) if len(probs) >= 2 else 0.5
        no_p = float(probs[1]) if len(probs) >= 2 else 0.5
        c = build_deadline_member_contract(
            market_id=14591600 + idx,
            name=m.question,
            source="polymarket",
            external_id=m.condition_id,
            group_id=f"polymarket:{st_event.id}",
            group_type="polymarket_sub_market",
            status="open" if not m.closed else "resolved",
            resolution_date=m.end_date,
            market_metadata=meta,
            outcomes=[
                {"id": idx * 10 + 1, "name": "Yes", "external_id": f"{m.condition_id}_yes", "current_probability": yes_p, "price_observed_epoch": RETAINED_OBS_EPOCH},
                {"id": idx * 10 + 2, "name": "No", "external_id": f"{m.condition_id}_no", "current_probability": no_p, "price_observed_epoch": RETAINED_OBS_EPOCH},
            ],
            now=RETAINED_NOW,
        )
        if c is None:
            rejected_questions.append(m.question)
        else:
            admitted_contracts.append(c)

    # "by Wednesday?" is rejected; the 11 calendar-date sub-markets are admitted
    assert len(rejected_questions) == 1
    assert "by Wednesday?" in rejected_questions[0]
    assert len(admitted_contracts) == 11

    family, err = verify_and_select_deadline_family(admitted_contracts, now=RETAINED_NOW)
    assert err is None
    assert family is not None
    assert family["shared_question"] == 'New "Stranger Things" episode released by…?'
    assert family["represented_count"] == 11
    # Settled earlier deadlines are graded "No" via UMA resolution; open Dec 31 & Mar 31, 2027 remain open
    open_members = [m for m in family["members"] if not m["settlement"]["is_settled"]]
    settled_members = [m for m in family["members"] if m["settlement"]["is_settled"]]
    assert len(open_members) == 2
    assert len(settled_members) == 9
    assert all(m["settlement"]["state"] == "resolved" and m["settlement"]["result"] == "No" for m in settled_members)
    # Representative is selected from open members (March 31, 2027 at 19.5% is closer to 50% than Dec 31 at 6.5%)
    assert family["selection_reason"] == "nearest_50_pct_fallback"
    assert family["representative_deadline_label"] == "By Mar 31, 2027"

    # Near-match refusal 1: gamma-event-106884.json (Fed meetings)
    raw_fed = json.loads((FIXTURES_5343_DIR / "gamma-event-106884.json").read_text())
    fed_event = parser._parse_event(raw_fed)
    assert fed_event is not None
    assert all(
        build_polymarket_submarket_deadline_contract(fed_event, m) is None
        for m in fed_event.markets
    )

    # Near-match refusal 2: gamma-event-1038648.json (US x Iran ceasefire "continues through" negative clause)
    raw_iran = json.loads(
        (
            FIXTURES_5343_DIR.parent
            / "polymarket_leg_dates_8466"
            / "gamma-event-1038648.json"
        ).read_text()
    )
    iran_event = parser._parse_event(raw_iran)
    assert iran_event is not None
    assert all(
        build_polymarket_submarket_deadline_contract(iran_event, m) is None
        for m in iran_event.markets
    )

    # Near-match refusal 3: gamma-event-86832.json (M&A different company subjects "before 2027")
    raw_ma = json.loads((FIXTURES_5343_DIR / "gamma-event-86832.json").read_text())
    ma_event = parser._parse_event(raw_ma)
    assert ma_event is not None
    assert all(
        build_polymarket_submarket_deadline_contract(ma_event, m) is None
        for m in ma_event.markets
    )
