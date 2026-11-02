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

from app.routes import feed as feed_route
from app.routes.feed import _dedupe_futures_by_group_id, _market_runtime_filter_trace
from app.services.polymarket_api import PolymarketAPIService
from app.tasks import polymarket as poly_task
from app.tasks.polymarket import sub_market_metadata
from app.utils import futures_market_snapshot as fms
from app.utils.deadline_family_story import (
    DEADLINE_RULE_CONTRACT_KEY,
    DETERMINISTIC_TIE_BREAK_RULE,
    build_deadline_member_contract,
    build_polymarket_submarket_deadline_contract,
    diagnose_polymarket_deadline_rule_refusal,
    extract_polymarket_deadline_rule_contract,
    extract_settlement_evidence,
    format_movement_timeframe,
    is_verified_deadline_rule_contract,
    merge_submarket_metadata_for_upsert,
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
    """Section 3C / Section 6D / Section 8 Case 11 / v3 Gap 2:
    Uses only real producer fields (`FuturesMarket.status`, `FuturesOutcome.is_winner` +
    `resolution_source` governed by `app.utils.resolution_authority`,
    `market_metadata[VENUE_SETTLED_KEY]`, and `sub_market_metadata`) to keep `"open"`,
    `"deadline_passed"` (cutoff passed without venue closure or result), `"trading_closed"`
    (venue closure without result), `"resolved"`, `"void"`, and `"unknown"` strictly distinct.
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
        assert ev_open["is_trading_closed"] is False
        assert ev_open["is_deadline_passed"] is False
        assert ev_open["result"] is None

    # 2a. "deadline_passed": contractual cutoff has passed while `status="open"` and no
    #     venue closure (`VENUE_SETTLED_KEY` or `sub_market_metadata.closed`) or result exists.
    #     Truthful state is `"deadline_passed"`, NEVER `"trading_closed"` or `"resolved"`.
    after_oct31_now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)
    ev_deadline_passed = extract_settlement_evidence(
        status="open",
        market_metadata={},
        outcomes=_make_oct31_outcomes(yes_prob=0.15),
        deadline_instant=OCT31_RESOLUTION_ISO,
        now=after_oct31_now,
    )
    assert ev_deadline_passed["state"] == "deadline_passed"
    assert ev_deadline_passed["is_settled"] is False
    assert ev_deadline_passed["is_trading_closed"] is False
    assert ev_deadline_passed["is_deadline_passed"] is True
    assert ev_deadline_passed["venue_closure_evidence"] is False
    assert ev_deadline_passed["result"] is None

    # A deadline-passed member suppresses movement claims and cannot be selected as the open representative
    oct31_passed_member = build_deadline_member_contract(
        market_id=65678073,
        name="Zacharia issues public apology by October 31?",
        source="polymarket",
        external_id="cond-oct",
        group_id="polymarket:256241",
        status="open",
        resolution_date=OCT31_RESOLUTION_ISO,
        description=OCT31_RULE_DESCRIPTION,
        market_metadata={
            "dated_movement_basis": {
                "246879005": [0.35, "2026-11-01T18:00:00+00:00"]
            }
        },
        outcomes=_make_oct31_outcomes(
            stored_yes_change=-0.12,
            yes_prob=0.48,  # closer to 50% and larger move than Dec 31, yet excluded because deadline passed!
            yes_obs_epoch=int(datetime(2026, 11, 2, 11, 0, 0, tzinfo=timezone.utc).timestamp()),
            no_obs_epoch=int(datetime(2026, 11, 2, 11, 0, 0, tzinfo=timezone.utc).timestamp()),
        ),
        now=after_oct31_now,
    )
    dec31_open_after_oct = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="cond-dec",
        group_id="polymarket:256241",
        status="open",
        resolution_date=DEC31_RESOLUTION_ISO,
        description=DEC31_RULE_DESCRIPTION,
        outcomes=_make_dec31_outcomes(
            yes_prob=0.245,
            yes_obs_epoch=int(datetime(2026, 11, 2, 11, 0, 0, tzinfo=timezone.utc).timestamp()),
            no_obs_epoch=int(datetime(2026, 11, 2, 11, 0, 0, tzinfo=timezone.utc).timestamp()),
        ),
        now=after_oct31_now,
    )
    assert oct31_passed_member is not None and dec31_open_after_oct is not None
    assert oct31_passed_member["settlement"]["state"] == "deadline_passed"
    assert oct31_passed_member["settlement"]["is_settled"] is False
    assert oct31_passed_member["settlement"]["is_trading_closed"] is False
    assert oct31_passed_member["settlement"]["is_deadline_passed"] is True
    assert oct31_passed_member["movement_status"] == "deadline_passed_suppressed"
    assert oct31_passed_member["supported_move"] is None
    assert oct31_passed_member["show_hero_movement_chip"] is False
    assert oct31_passed_member["show_row_movement_badge"] is False
    fam_after_oct, err_after_oct = verify_and_select_deadline_family(
        [oct31_passed_member, dec31_open_after_oct], now=after_oct31_now
    )
    assert err_after_oct is None and fam_after_oct is not None
    assert fam_after_oct["representative_market_id"] == 65678074

    # 2b. "trading_closed": VENUE_SETTLED_KEY (`price_refresh_venue_settled_since`) or
    #     `status="closed"` without a resolved outcome -> `is_trading_closed=True`, `is_settled=False`, `result=None`
    ev_closed = extract_settlement_evidence(
        status="open",
        market_metadata={VENUE_SETTLED_KEY: "2026-10-14T12:00:00+00:00"},
        outcomes=_make_dec31_outcomes(yes_prob=0.99),
        deadline_instant=DEC31_RESOLUTION_ISO,
        now=RETAINED_NOW,
    )
    assert ev_closed["state"] == "trading_closed"
    assert ev_closed["is_settled"] is False
    assert ev_closed["is_trading_closed"] is True
    assert ev_closed["is_deadline_passed"] is False
    assert ev_closed["venue_closure_evidence"] is True
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
    assert ev_resolved_uma["is_settled"] is True
    assert ev_resolved_uma["result"] == "Yes"
    assert ev_resolved_uma["lagging_local_status"] is True
    assert ev_resolved_uma["conflicting_settlement_evidence"] is False

    # Conflicting settlement evidence (stored rule contract says resolved "No" while outcome says "Yes") -> state == "unknown"
    ev_conflict = extract_settlement_evidence(
        status="open",
        market_metadata={
            DEADLINE_RULE_CONTRACT_KEY: {
                "venue_terminal_state": "resolved",
                "venue_winner": "No",
            }
        },
        outcomes=[
            {"id": 246879008, "name": "No", "is_winner": False, "resolution_source": "api_settlement"},
            {"id": 246879007, "name": "Yes", "is_winner": True, "resolution_source": "api_settlement"},
        ],
        deadline_instant=DEC31_RESOLUTION_ISO,
        now=RETAINED_NOW,
    )
    assert ev_conflict["state"] == "unknown"
    assert ev_conflict["is_settled"] is False
    assert ev_conflict["result"] is None
    assert ev_conflict["conflicting_settlement_evidence"] is True

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
        not is_verified_deadline_rule_contract(
            build_polymarket_submarket_deadline_contract(fed_event, m)
        )
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
        not is_verified_deadline_rule_contract(
            build_polymarket_submarket_deadline_contract(iran_event, m)
        )
        for m in iran_event.markets
    )

    # Near-match refusal 3: gamma-event-86832.json (M&A different company subjects "before 2027")
    raw_ma = json.loads((FIXTURES_5343_DIR / "gamma-event-86832.json").read_text())
    ma_event = parser._parse_event(raw_ma)
    assert ma_event is not None
    assert all(
        not is_verified_deadline_rule_contract(
            build_polymarket_submarket_deadline_contract(ma_event, m)
        )
        for m in ma_event.markets
    )


def test_case16_v3_gap1_ingestion_invalidation_and_roundtrip_lifecycle() -> None:
    """v3 Gap 1:
    - Demonstrates the full ingestion lifecycle `valid -> incompatible -> ordinary fallback -> valid again`
      through `build_polymarket_submarket_deadline_contract`, `sub_market_metadata`, and
      `merge_submarket_metadata_for_upsert`, while preserving unrelated `market_metadata` keys
      (`dated_movement_basis`, `clob_token_ids`, `polymarket_event_id`).
    - Verifies both explicit invalidation states (`status="invalidated_incompatible_rule"` when revised
      rule text fails verification vs `status="missing_rule_description"` when description is blank)
      and explicit key removal (`deadline_rule_contract=None` stripping `DEADLINE_RULE_CONTRACT_KEY`).
    - Verifies identity/content binding (`condition_id`, `question_sha256`, `end_date_iso`) rejects stale
      stored proof if question text or resolution date changes without refreshing the contract.
    - Verifies lower-bound window provenance (`window_start_kind="market_creation"`,
      `nested_window_proven=False` when creation timestamps are absent, `nested_window_proven=True`
      when shared creation timestamp is present, and `mismatched_window_start_instant` refusal when
      creation timestamps differ).
    """
    event = SimpleNamespace(
        id="256241",
        title="Zacharia issues public apology by...?",
        neg_risk=False,
        active=True,
        closed=False,
        markets=[SimpleNamespace(), SimpleNamespace()],
    )
    oct31_market = SimpleNamespace(
        id="65678073",
        condition_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        question="Zacharia issues public apology by October 31?",
        description=OCT31_RULE_DESCRIPTION,
        group_item_title="October 31",
        end_date=datetime.fromisoformat(OCT31_RESOLUTION_ISO),
        closed=False,
        active=True,
        uma_resolution_status="unresolved",
        outcome_prices=[0.073, 0.927],
        outcomes=["Yes", "No"],
    )
    dec31_market_v1 = SimpleNamespace(
        id="65678074",
        condition_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        question="Zacharia issues public apology by December 31?",
        description=DEC31_RULE_DESCRIPTION,
        group_item_title="December 31",
        end_date=datetime.fromisoformat(DEC31_RESOLUTION_ISO),
        closed=False,
        active=True,
        uma_resolution_status="unresolved",
        outcome_prices=[0.245, 0.755],
        outcomes=["Yes", "No"],
    )

    # Prior unrelated metadata on both stored rows that must survive every ingestion poll
    existing_oct_meta = {
        "polymarket_event_id": "256241",
        "clob_token_ids": {"Yes": "tok_oct_yes", "No": "tok_oct_no"},
        "dated_movement_basis": {"246879005": [0.084, RETAINED_BASIS_AT]},
        "market_count": 2,
    }
    existing_dec_meta = {
        "polymarket_event_id": "256241",
        "clob_token_ids": {"Yes": "tok_dec_yes", "No": "tok_dec_no"},
        "dated_movement_basis": {"246879007": [0.310, RETAINED_BASIS_AT]},
        "market_count": 2,
    }

    # --- STEP 1: VALID (both Oct 31 and Dec 31 ingest verified rule contracts) ---
    oct_incoming_1 = sub_market_metadata(
        event_id=event.id,
        matchup_title=None,
        deadline_rule_contract=build_polymarket_submarket_deadline_contract(event, oct31_market),
    )
    dec_incoming_1 = sub_market_metadata(
        event_id=event.id,
        matchup_title=None,
        deadline_rule_contract=build_polymarket_submarket_deadline_contract(event, dec31_market_v1),
    )
    oct_meta_step1 = merge_submarket_metadata_for_upsert(existing_oct_meta, oct_incoming_1)
    dec_meta_step1 = merge_submarket_metadata_for_upsert(existing_dec_meta, dec_incoming_1)

    assert is_verified_deadline_rule_contract(oct_meta_step1[DEADLINE_RULE_CONTRACT_KEY]) is True
    assert is_verified_deadline_rule_contract(dec_meta_step1[DEADLINE_RULE_CONTRACT_KEY]) is True
    assert dec_meta_step1["clob_token_ids"] == existing_dec_meta["clob_token_ids"]
    assert dec_meta_step1["dated_movement_basis"] == existing_dec_meta["dated_movement_basis"]
    assert dec_meta_step1[DEADLINE_RULE_CONTRACT_KEY]["window_start_kind"] == "market_creation"

    c_oct_1 = build_deadline_member_contract(
        market_id=65678073,
        name=oct31_market.question,
        source="polymarket",
        external_id=oct31_market.condition_id,
        group_id="polymarket:256241",
        resolution_date=OCT31_RESOLUTION_ISO,
        market_metadata=oct_meta_step1,
        outcomes=_make_oct31_outcomes(stored_yes_change=-0.011),
        now=RETAINED_NOW,
    )
    c_dec_1 = build_deadline_member_contract(
        market_id=65678074,
        name=dec31_market_v1.question,
        source="polymarket",
        external_id=dec31_market_v1.condition_id,
        group_id="polymarket:256241",
        resolution_date=DEC31_RESOLUTION_ISO,
        market_metadata=dec_meta_step1,
        outcomes=_make_dec31_outcomes(stored_yes_change=-0.065),
        now=RETAINED_NOW,
    )
    assert c_oct_1 is not None and c_dec_1 is not None
    fam_step1, err_step1 = verify_and_select_deadline_family([c_oct_1, c_dec_1], now=RETAINED_NOW)
    assert err_step1 is None and fam_step1 is not None
    assert fam_step1["window_start_kind"] == "market_creation"
    assert fam_step1["nested_window_proven"] is False  # creation timestamps absent on retained Oct 14 rows

    # --- STEP 2: INCOMPATIBLE -> ORDINARY FALLBACK ---
    # Provider revises Dec 31 rule text to an incompatible negative/standing-status clause
    dec31_market_incompatible = SimpleNamespace(
        **{
            **dec31_market_v1.__dict__,
            "description": (
                "This market will resolve to \"Yes\" if Zacharia fails to issue a public apology "
                "between market creation and December 31, 2026, 11:59 PM ET. Otherwise, this market "
                "will resolve to \"No\"."
            ),
        }
    )
    inval_contract = build_polymarket_submarket_deadline_contract(event, dec31_market_incompatible)
    assert inval_contract is not None
    assert inval_contract["verified"] is False
    assert inval_contract["status"] == "invalidated_incompatible_rule"
    assert inval_contract["reason"] == "negative_or_inverted_rule_predicate"

    dec_incoming_2 = sub_market_metadata(
        event_id=event.id,
        matchup_title=None,
        deadline_rule_contract=inval_contract,
    )
    assert DEADLINE_RULE_CONTRACT_KEY in (dec_incoming_2 or {})
    dec_meta_step2 = merge_submarket_metadata_for_upsert(dec_meta_step1, dec_incoming_2)
    # Unrelated keys remain intact while the old verified proof is replaced by the invalidation record
    assert dec_meta_step2["clob_token_ids"] == existing_dec_meta["clob_token_ids"]
    assert dec_meta_step2["dated_movement_basis"] == existing_dec_meta["dated_movement_basis"]
    assert dec_meta_step2["polymarket_event_id"] == "256241"
    assert is_verified_deadline_rule_contract(dec_meta_step2.get(DEADLINE_RULE_CONTRACT_KEY)) is False

    # Also verify missing rule description invalidation (`status="missing_rule_description"`)
    dec31_market_no_desc = SimpleNamespace(
        **{**dec31_market_v1.__dict__, "description": ""}
    )
    missing_desc_contract = build_polymarket_submarket_deadline_contract(event, dec31_market_no_desc)
    assert missing_desc_contract is not None
    assert missing_desc_contract["verified"] is False
    assert missing_desc_contract["status"] == "missing_rule_description"
    assert missing_desc_contract["reason"] == "missing_or_empty_description"

    # Also verify that if `deadline_rule_contract=None` is passed to `sub_market_metadata`,
    # `merge_submarket_metadata_for_upsert` strips any stale `DEADLINE_RULE_CONTRACT_KEY`
    dec_incoming_none = sub_market_metadata(
        event_id=event.id,
        matchup_title=None,
        deadline_rule_contract=None,
    )
    dec_meta_stripped = merge_submarket_metadata_for_upsert(dec_meta_step1, dec_incoming_none)
    assert DEADLINE_RULE_CONTRACT_KEY not in dec_meta_stripped
    assert dec_meta_stripped["clob_token_ids"] == existing_dec_meta["clob_token_ids"]
    assert dec_meta_stripped["dated_movement_basis"] == existing_dec_meta["dated_movement_basis"]

    # Build member contract from invalidated row -> `rule_verification.verified` is False -> family refused
    c_dec_2 = build_deadline_member_contract(
        market_id=65678074,
        name=dec31_market_incompatible.question,
        source="polymarket",
        external_id=dec31_market_incompatible.condition_id,
        group_id="polymarket:256241",
        resolution_date=DEC31_RESOLUTION_ISO,
        market_metadata=dec_meta_step2,
        outcomes=_make_dec31_outcomes(stored_yes_change=-0.065),
        now=RETAINED_NOW,
    )
    assert c_dec_2 is not None
    assert c_dec_2["rule_verification"]["verified"] is False
    assert c_dec_2["rule_verification"]["status"] == "invalidated_incompatible_rule"
    assert c_dec_2["rule_verification"]["reason"] == "negative_or_inverted_rule_predicate"
    fam_step2, err_step2 = verify_and_select_deadline_family([c_oct_1, c_dec_2], now=RETAINED_NOW)
    assert fam_step2 is None
    assert err_step2 == "invalidated_incompatible_rule"

    # Bundler leaves the deduplicated winner as an ordinary standalone `type="futures"` card
    deduped_step2 = _dedupe_futures_by_group_id(
        [
            {
                "type": "futures",
                "score": 52,
                "reason": "Politics",
                "headline": c_oct_1["name"],
                "data": {
                    "id": 65678073,
                    "name": c_oct_1["name"],
                    "source": "polymarket",
                    "group_id": "polymarket:256241",
                    "deadline_member": c_oct_1,
                },
            },
            {
                "type": "futures",
                "score": 64,
                "reason": "Politics",
                "headline": c_dec_2["name"],
                "data": {
                    "id": 65678074,
                    "name": c_dec_2["name"],
                    "source": "polymarket",
                    "group_id": "polymarket:256241",
                    "deadline_member": c_dec_2,
                },
            },
        ]
    )
    bundled_step2 = assemble_deadline_family_bundles(deduped_step2, now=RETAINED_NOW)
    assert len(bundled_step2) == 1
    assert bundled_step2[0]["type"] == "futures"
    assert bundled_step2[0]["data"]["id"] == 65678074

    # --- STEP 3: VALID AGAIN (provider restores compatible rule text) ---
    dec_incoming_3 = sub_market_metadata(
        event_id=event.id,
        matchup_title=None,
        deadline_rule_contract=build_polymarket_submarket_deadline_contract(event, dec31_market_v1),
    )
    dec_meta_step3 = merge_submarket_metadata_for_upsert(dec_meta_step2, dec_incoming_3)
    assert is_verified_deadline_rule_contract(dec_meta_step3[DEADLINE_RULE_CONTRACT_KEY]) is True
    assert dec_meta_step3["clob_token_ids"] == existing_dec_meta["clob_token_ids"]
    assert dec_meta_step3["dated_movement_basis"] == existing_dec_meta["dated_movement_basis"]

    c_dec_3 = build_deadline_member_contract(
        market_id=65678074,
        name=dec31_market_v1.question,
        source="polymarket",
        external_id=dec31_market_v1.condition_id,
        group_id="polymarket:256241",
        resolution_date=DEC31_RESOLUTION_ISO,
        market_metadata=dec_meta_step3,
        outcomes=_make_dec31_outcomes(stored_yes_change=-0.065),
        now=RETAINED_NOW,
    )
    assert c_dec_3 is not None and c_dec_3["rule_verification"]["verified"] is True
    fam_step3, err_step3 = verify_and_select_deadline_family([c_oct_1, c_dec_3], now=RETAINED_NOW)
    assert err_step3 is None and fam_step3 is not None
    assert fam_step3["representative_market_id"] == 65678074
    assert fam_step3["selection_reason"] == "largest_supported_dated_move"

    # --- Real `_process_event_batch` SQL upsert verification (RecordingSession) ---
    import asyncio
    import contextlib
    from collections import defaultdict
    from unittest.mock import patch
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.services.polymarket_api import PolymarketEvent, PolymarketMarket
    from app.tasks import polymarket as poly_task
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american
    from tests.test_polymarket_under_snapshot_book_p097 import (
        RecordingSession,
        _bound_params,
    )

    def _build_poly_event(dec_desc: str) -> PolymarketEvent:
        return PolymarketEvent(
            id="256241",
            title="Zacharia issues public apology by...?",
            slug="zacharia-public-apology-by",
            description=OCT31_RULE_DESCRIPTION,
            active=True,
            closed=False,
            neg_risk=False,
            tags=["Politics"],
            end_date=datetime.fromisoformat(DEC31_RESOLUTION_ISO),
            markets=[
                PolymarketMarket(
                    id="65678073",
                    condition_id=oct31_market.condition_id,
                    question=oct31_market.question,
                    description=OCT31_RULE_DESCRIPTION,
                    group_item_title="October 31",
                    end_date=datetime.fromisoformat(OCT31_RESOLUTION_ISO),
                    outcomes=["Yes", "No"],
                    outcome_prices=[0.073, 0.927],
                    clob_token_ids=["tok_oct_yes", "tok_oct_no"],
                    best_bid=0.07,
                    best_ask=0.08,
                    last_trade_price=0.073,
                    volume=1200.0,
                    active=True,
                    closed=False,
                ),
                PolymarketMarket(
                    id="65678074",
                    condition_id=dec31_market_v1.condition_id,
                    question=dec31_market_v1.question,
                    description=dec_desc,
                    group_item_title="December 31",
                    end_date=datetime.fromisoformat(DEC31_RESOLUTION_ISO),
                    outcomes=["Yes", "No"],
                    outcome_prices=[0.245, 0.755],
                    clob_token_ids=["tok_dec_yes", "tok_dec_no"],
                    best_bid=0.24,
                    best_ask=0.25,
                    last_trade_price=0.245,
                    volume=3400.0,
                    active=True,
                    closed=False,
                ),
            ],
        )

    async def _run_batch(ev_obj: PolymarketEvent) -> tuple[dict, str]:
        import contextlib
        from unittest.mock import patch

        rec_session = RecordingSession()

        @contextlib.asynccontextmanager
        async def _fake_session():
            yield rec_session

        stats: dict = defaultdict(int)
        stats["errors"] = []
        with patch.object(poly_task, "get_task_session", _fake_session):
            await poly_task._process_event_batch(
                [ev_obj],
                stats,
                FuturesMarket,
                FuturesOutcome,
                FuturesOddsSnapshot,
                pg_insert,
                probability_to_american,
                compute_market_tier,
            )
        assert not stats["errors"], f"_process_event_batch errors: {stats['errors']}"
        dec_stmt = None
        for stmt in rec_session.statements:
            if getattr(getattr(stmt, "table", None), "name", None) != "futures_markets":
                continue
            if _bound_params(stmt).get("external_id") == dec31_market_v1.condition_id:
                dec_stmt = stmt
        assert dec_stmt is not None
        inserted_md = _bound_params(dec_stmt).get("market_metadata") or {}
        conflict_set = {
            getattr(k, "key", k): v
            for k, v in dec_stmt._post_values_clause.update_values_to_set
        }
        merge_expr = conflict_set["market_metadata"]
        compiled_sql = str(
            merge_expr.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        return inserted_md, compiled_sql

    md_sql_1, sql_1 = asyncio.run(_run_batch(_build_poly_event(DEC31_RULE_DESCRIPTION)))
    assert md_sql_1[DEADLINE_RULE_CONTRACT_KEY]["verified"] is True
    assert "'deadline_rule_contract'" in sql_1
    assert '"verified": true' in sql_1
    assert "'clob_token_ids'" in sql_1
    assert "'polymarket_event_id'" in sql_1

    md_sql_2, sql_2 = asyncio.run(
        _run_batch(_build_poly_event(dec31_market_incompatible.description))
    )
    assert md_sql_2[DEADLINE_RULE_CONTRACT_KEY]["verified"] is False
    assert (
        md_sql_2[DEADLINE_RULE_CONTRACT_KEY]["status"]
        == "invalidated_incompatible_rule"
    )
    assert "'deadline_rule_contract'" in sql_2
    assert '"verified": false' in sql_2
    assert '"status": "invalidated_incompatible_rule"' in sql_2
    assert "'clob_token_ids'" in sql_2

    md_sql_3, sql_3 = asyncio.run(_run_batch(_build_poly_event(DEC31_RULE_DESCRIPTION)))
    assert md_sql_3[DEADLINE_RULE_CONTRACT_KEY]["verified"] is True
    assert '"verified": true' in sql_3

    # Also verify `_process_event_batch` compiles `- 'deadline_rule_contract'` when
    # `deadline_rule_contract` is omitted (`None`) from `sub_meta_insert`
    with patch.object(
        poly_task, "build_polymarket_submarket_deadline_contract", return_value=None
    ):
        md_sql_none, sql_none = asyncio.run(
            _run_batch(_build_poly_event(DEC31_RULE_DESCRIPTION))
        )
    assert DEADLINE_RULE_CONTRACT_KEY not in md_sql_none
    assert "- 'deadline_rule_contract'" in sql_none
    assert "'clob_token_ids'" in sql_none
    assert "'polymarket_event_id'" in sql_none

    # --- Identity/content binding check: stale proof rejected if question or cutoff changes ---
    c_stale_question = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by November 30?",  # changed without refreshing proof
        source="polymarket",
        external_id=dec31_market_v1.condition_id,
        group_id="polymarket:256241",
        resolution_date="2026-12-01T04:59:00+00:00",
        market_metadata=dec_meta_step3,
        outcomes=_make_dec31_outcomes(),
        now=RETAINED_NOW,
    )
    assert c_stale_question is not None
    assert c_stale_question["rule_verification"]["verified"] is False
    assert c_stale_question["rule_verification"]["status"] == "stale_bound_question"
    assert (
        c_stale_question["rule_verification"]["reason"]
        == "stored_contract_question_sha256_mismatch"
    )


def test_case17_v3_gap3_real_feed_serialization_dedup_and_display_chain_integration() -> None:
    """v3 Gap 3:
    Exercises the real backend serialization, deduplication, and Discover display chain
    (`fms.to_plain` -> `fms.from_plain` -> `feed._score_futures` ->
    `feed._dedupe_futures_by_canonical` -> `feed._dedupe_futures_by_group_id` ->
    `feed._suppress_zero_probability_cards` -> `feed.apply_discover_display_chain`)
    without hand-constructing `FeedItem` dicts:
    1. Retained Oct 14 Zacharia no-claim control (`65678073`, `65678074`, plus parent
       `polymarket_event` row `65678000` sharing `group_id="polymarket:256241"`).
    2. Synthetic positive Zacharia (`-6.5` pt move on `65678074` + `-1.1` pt move on `65678073`).
    3. Held-out `gamma-event-145916.json` (`Stranger Things`, 11 verified calendar-date members +
       1 rejected `"by Wednesday?"` market).
    4. Refused group fallback (`65678074` with invalidated rule contract falls back to a single
       ordinary `type="futures"` card; non-deadline multi-market group passes through untouched).
    """
    import asyncio
    from app.utils.personalization import PersonalizationContext

    def _make_orm_market(
        *,
        mid: int,
        name: str,
        external_id: str,
        group_id: str,
        group_type: str,
        resolution_iso: str,
        market_metadata: dict,
        outcomes_spec: list[dict],
        status: str = "open",
        category: str = "politics",
    ) -> SimpleNamespace:
        orm_outcomes = [
            SimpleNamespace(
                id=o["id"],
                name=o["name"],
                team_id=None,
                current_probability=(
                    Decimal(str(o["current_probability"]))
                    if o.get("current_probability") is not None
                    else None
                ),
                probability_change_24h=(
                    Decimal(str(o["probability_change_24h"]))
                    if o.get("probability_change_24h") is not None
                    else None
                ),
                rank=o.get("rank", idx + 1),
                rank_change_24h=0,
                opening_probability=Decimal("0.500"),
                calibration_probability=None,
                current_yes_bid=None,
                current_yes_ask=None,
                external_id=o.get("external_id", f"{external_id}_{idx}"),
                last_updated=RETAINED_OBS_DT,
                opening_captured_at=None,
                resolution_source=o.get("resolution_source"),
                volume_24h=None,
                volume_24h_at=None,
                is_winner=o.get("is_winner"),
            )
            for idx, o in enumerate(outcomes_spec)
        ]
        return SimpleNamespace(
            id=mid,
            name=name,
            source="polymarket",
            external_id=external_id,
            sport_id=None,
            category=category,
            llm_sport_category=category,
            market_tier=2,
            market_type="binary",
            canonical_market_key=None,
            group_id=group_id,
            group_type=group_type,
            image_url=None,
            image_width=None,
            image_height=None,
            hook_description=None,
            hook_generated_at=None,
            hook_leader_at_generation=None,
            market_metadata=market_metadata,
            curation_score_adj=0,
            volume_24h=Decimal("2500.00"),
            updated_at=RETAINED_NOW,
            commence_time=None,
            resolution_date=datetime.fromisoformat(resolution_iso),
            status=status,
            created_at=RETAINED_NOW,
            llm_league=None,
            llm_gender=None,
            llm_level=None,
            mutually_exclusive=True,
            sport=None,
            outcomes=orm_outcomes,
        )

    async def _run_real_discover_pipeline(orm_markets: list[SimpleNamespace]) -> list[dict]:
        # 1. Real snapshot serialization + rehydration (`to_plain` -> `from_plain`)
        rehydrated = fms.from_plain(fms.to_plain(orm_markets))
        # 2. Real `_score_futures` scoring + `deadline_member` serialization
        scored = await feed_route._score_futures(
            db=None,  # type: ignore[arg-type]
            now=RETAINED_NOW,
            sport_filter=None,
            ctx=PersonalizationContext(),
            preloaded_base={"markets": rehydrated, "curator_ids": set()},
        )
        # 3. Real canonical + group_id deduplication + zero-prob suppression
        deduped = feed_route._dedupe_futures_by_canonical(scored)
        deduped = feed_route._dedupe_futures_by_group_id(deduped)
        deduped, _ = feed_route._suppress_zero_probability_cards(deduped)
        # 4. Real `apply_discover_display_chain` in Discover mode (`event_pct=0.15`)
        displayed, _ = feed_route.apply_discover_display_chain(
            deduped,
            limit=20,
            ctx=PersonalizationContext(),
            event_pct=0.15,
            include_events=True,
            my_teams_only=False,
            sports_mode=False,
            now=RETAINED_NOW,
        )
        return displayed

    # --- 1. Retained Oct 14 Zacharia no-claim control (with parent `polymarket_event` container row) ---
    oct31_meta = _zacharia_rule_meta(
        question="Zacharia issues public apology by October 31?",
        description=OCT31_RULE_DESCRIPTION,
        group_item_title="October 31",
        end_date_iso=OCT31_RESOLUTION_ISO,
        extra={"market_count": 2},
    )
    dec31_meta = _zacharia_rule_meta(
        question="Zacharia issues public apology by December 31?",
        description=DEC31_RULE_DESCRIPTION,
        group_item_title="December 31",
        end_date_iso=DEC31_RESOLUTION_ISO,
        extra={"market_count": 2},
    )
    parent_event_row = _make_orm_market(
        mid=65678000,
        name="Zacharia issues public apology by...?",
        external_id="poly_event_256241",
        group_id="polymarket:256241",
        group_type="polymarket_event",
        resolution_iso=DEC31_RESOLUTION_ISO,
        market_metadata={"polymarket_event_id": "256241", "market_count": 2},
        outcomes_spec=[
            {"id": 246879001, "name": "October 31", "current_probability": 0.073, "rank": 2},
            {"id": 246879002, "name": "December 31", "current_probability": 0.245, "rank": 1},
        ],
    )
    oct31_orm_null = _make_orm_market(
        mid=65678073,
        name="Zacharia issues public apology by October 31?",
        external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        group_id="polymarket:256241",
        group_type="polymarket_sub_market",
        resolution_iso=OCT31_RESOLUTION_ISO,
        market_metadata=oct31_meta,
        outcomes_spec=_make_oct31_outcomes(stored_yes_change=None),
    )
    dec31_orm_null = _make_orm_market(
        mid=65678074,
        name="Zacharia issues public apology by December 31?",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:256241",
        group_type="polymarket_sub_market",
        resolution_iso=DEC31_RESOLUTION_ISO,
        market_metadata=dec31_meta,
        outcomes_spec=_make_dec31_outcomes(stored_yes_change=None),
    )

    out_null = asyncio.run(
        _run_real_discover_pipeline([parent_event_row, oct31_orm_null, dec31_orm_null])
    )
    assert len(out_null) == 1
    bundle_null = out_null[0]
    assert bundle_null["type"] == "bundle"
    assert bundle_null["data"]["kind"] == "theme"
    assert bundle_null["data"]["story_key"] == "story:deadline_family:polymarket:256241"
    assert bundle_null["data"]["member_ids"] == [65678073, 65678074]
    assert bundle_null["data"]["deadline_family"]["selection_reason"] == "nearest_50_pct_fallback"
    assert bundle_null["data"]["deadline_family"]["representative_market_id"] == 65678074
    assert bundle_null["data"]["deadline_family"]["verified_family_count"] == 2
    # Exact Yes outcome binding even though No is rank=1 (0.755) in top_outcomes
    rep_item_null = bundle_null["data"]["items"][1]["data"]
    assert rep_item_null["top_outcomes"][0]["id"] == 246879008  # No is rank 1
    assert rep_item_null["deadline_member"]["yes_outcome_id"] == 246879007
    assert rep_item_null["deadline_member"]["yes_probability"] == 0.245
    # In `_score_futures`, largest-remainder rounding on binary `(0.755, 0.245)` produces `(76, 24)`
    assert rep_item_null["deadline_member"]["yes_rendered_percent"] == 24
    assert rep_item_null["deadline_member"]["movement_status"] == "no_stored_claim"

    # --- 2. Synthetic positive Zacharia (`-6.5` pt move on Dec 31) ---
    oct31_orm_syn = _make_orm_market(
        mid=65678073,
        name="Zacharia issues public apology by October 31?",
        external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        group_id="polymarket:256241",
        group_type="polymarket_sub_market",
        resolution_iso=OCT31_RESOLUTION_ISO,
        market_metadata={
            **oct31_meta,
            "dated_movement_basis": {"246879005": [0.084, RETAINED_BASIS_AT]},
        },
        outcomes_spec=_make_oct31_outcomes(stored_yes_change=-0.011),
    )
    dec31_orm_syn = _make_orm_market(
        mid=65678074,
        name="Zacharia issues public apology by December 31?",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:256241",
        group_type="polymarket_sub_market",
        resolution_iso=DEC31_RESOLUTION_ISO,
        market_metadata={
            **dec31_meta,
            "dated_movement_basis": {"246879007": [0.310, RETAINED_BASIS_AT]},
        },
        outcomes_spec=_make_dec31_outcomes(stored_yes_change=-0.065),
    )
    out_syn = asyncio.run(_run_real_discover_pipeline([oct31_orm_syn, dec31_orm_syn]))
    assert len(out_syn) == 1
    bundle_syn = out_syn[0]
    assert bundle_syn["type"] == "bundle"
    assert (
        bundle_syn["data"]["deadline_family"]["selection_reason"]
        == "largest_supported_dated_move"
    )
    assert bundle_syn["data"]["deadline_family"]["representative_market_id"] == 65678074
    rep_item_syn = bundle_syn["data"]["items"][1]["data"]["deadline_member"]
    assert rep_item_syn["movement_status"] == "hero"
    assert rep_item_syn["supported_move_points"] == -6.5
    assert rep_item_syn["show_hero_movement_chip"] is True

    # --- 3. Refused group fallback through the real pipeline ---
    dec31_orm_inval = _make_orm_market(
        mid=65678074,
        name="Zacharia issues public apology by December 31?",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:256241",
        group_type="polymarket_sub_market",
        resolution_iso=DEC31_RESOLUTION_ISO,
        market_metadata={
            "polymarket_event_id": "256241",
            "market_count": 2,
            DEADLINE_RULE_CONTRACT_KEY: {
                "schema": "polymarket_deadline_rule_v1",
                "verified": False,
                "status": "invalidated_incompatible_rule",
                "refusal_reason": "negative_or_inverted_resolution_clause",
            },
        },
        outcomes_spec=_make_dec31_outcomes(stored_yes_change=-0.065),
    )
    out_refused = asyncio.run(
        _run_real_discover_pipeline([oct31_orm_syn, dec31_orm_inval])
    )
    assert len(out_refused) == 1
    assert out_refused[0]["type"] == "futures"
    assert out_refused[0]["data"]["group_id"] == "polymarket:256241"


def test_case18_v3_gap4_reader_local_now_and_verified_family_count() -> None:
    """v3 Gap 4:
    - Verifies `format_movement_timeframe` checks `now` local calendar date before emitting
      `"since yesterday"` or `"today since <time>"` (emitting `"since Oct 13"` when `now` is
      on `2026-10-16` while the observation is on `2026-10-14` and the basis is on `2026-10-13`).
    - Verifies `verified_family_count` vs `provider_market_count` on `gamma-event-145916.json`
      (`Stranger Things`: 12 provider markets, 11 verified deadline-family members, 8 represented
      when capped by `max_items_per_bundle=8`).
    """
    # 1. Reader-local `now` matches observation local date (Oct 14 EDT) -> "since yesterday"
    tf_current = format_movement_timeframe(
        RETAINED_BASIS_AT,
        RETAINED_OBS_DT,
        timezone_name="America/New_York",
        now=RETAINED_NOW,
    )
    assert tf_current["valid"] is True
    assert tf_current["crosses_previous_calendar_day"] is True
    assert tf_current["chip_timeframe"] == "since yesterday"
    assert tf_current["sentence_timeframe"] == "since yesterday"

    # 2. Reader-local `now` is two days later (Oct 16 EDT) -> must NOT claim "since yesterday"
    later_now = datetime(2026, 10, 16, 15, 0, 0, tzinfo=timezone.utc)
    tf_later = format_movement_timeframe(
        RETAINED_BASIS_AT,
        RETAINED_OBS_DT,
        timezone_name="America/New_York",
        now=later_now,
    )
    assert tf_later["valid"] is True
    assert tf_later["crosses_previous_calendar_day"] is False
    assert tf_later["chip_timeframe"] == "since Oct 13"
    assert tf_later["sentence_timeframe"] == "since Oct 13"

    # 3. `verified_family_count` (11) vs `provider_market_count` (12) on `gamma-event-145916.json`
    parser = PolymarketAPIService()
    raw_st = json.loads((FIXTURES_5343_DIR / "gamma-event-145916.json").read_text())
    st_event = parser._parse_event(raw_st)
    assert st_event is not None
    assert len(st_event.markets) == 12  # 11 calendar-date deadlines + 1 "by Wednesday?"

    st_feed_items: list[dict] = []
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
        meta["market_count"] = len(st_event.markets)  # 12 raw provider markets
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
                {
                    "id": idx * 10 + 1,
                    "name": "Yes",
                    "external_id": f"{m.condition_id}_yes",
                    "current_probability": yes_p,
                    "price_observed_epoch": RETAINED_OBS_EPOCH,
                },
                {
                    "id": idx * 10 + 2,
                    "name": "No",
                    "external_id": f"{m.condition_id}_no",
                    "current_probability": no_p,
                    "price_observed_epoch": RETAINED_OBS_EPOCH,
                },
            ],
            now=RETAINED_NOW,
        )
        if c is None:
            continue
        st_feed_items.append(
            {
                "type": "futures",
                "score": 60 if not m.closed else 25,
                "reason": "Entertainment",
                "headline": m.question,
                "data": {
                    "id": 14591600 + idx,
                    "name": m.question,
                    "source": "polymarket",
                    "group_id": f"polymarket:{st_event.id}",
                    "group_type": "polymarket_sub_market",
                    "status": "open" if not m.closed else "resolved",
                    "deadline_member": c,
                },
            }
        )

    deduped_st = _dedupe_futures_by_group_id(st_feed_items)
    assert len(deduped_st) == 1

    # Uncapped (`max_items_per_bundle=12`): all 11 verified members are represented;
    # `verified_family_count == 11` even though `provider_market_count == 12`
    uncapped_st = assemble_deadline_family_bundles(
        [
            {
                **deduped_st[0],
                "_grouped_members": list(deduped_st[0].get("_grouped_members", [])),
            }
        ],
        max_items_per_bundle=12,
        now=RETAINED_NOW,
    )
    assert len(uncapped_st) == 1
    fam_uncapped = uncapped_st[0]["data"]["deadline_family"]
    assert fam_uncapped["represented_count"] == 11
    assert fam_uncapped["verified_family_count"] == 11
    assert fam_uncapped["provider_market_count"] == 12
    assert fam_uncapped["inventory_complete"] is False

    # Default cap (`max_items_per_bundle=8`): 8 of 11 verified members are represented,
    # and `verified_family_count == 11` is propagated onto the family and member contracts
    capped_st = assemble_deadline_family_bundles(
        deduped_st,
        max_items_per_bundle=8,
        now=RETAINED_NOW,
    )
    assert len(capped_st) == 1
    fam_capped = capped_st[0]["data"]["deadline_family"]
    assert fam_capped["represented_count"] == 8
    assert fam_capped["verified_family_count"] == 11
    assert fam_capped["provider_market_count"] == 12
    assert all(
        it["data"]["deadline_member"]["verified_family_count"] == 11
        for it in capped_st[0]["data"]["items"]
    )


def test_case19_v4_b1_b2_b3_b6_fixes() -> None:
    """v4 fixes for Fable review blockers B1, B2, B3, and B6:
    - B1 (D4b / Q8e): Producer and consumer require 12h <= (observed - basis) <= 24h in addition
      to 12h <= (now - basis) <= 24h.
    - B2 (C3 / C4): FuturesMarketSnapshot preserves `is_winner` and `resolution_source` across
      `to_plain` -> `from_plain`, keeping lagging `status='open'` authoritative settlements and
      conflicting-winner refusals identical on direct and cached paths, and attaching
      `deadline_member` on terminal `/api/feed/price-cards` projections.
    - B3 (Q8c / Q8d): Q8 is strictly scoped to open >=97% members of a verified >=2-member
      family that actually forms; lone 98% children are evicted when no family forms, <=3% is
      never exempted, and <=5% legs suppress movement claims (`placeholder_floor_suppressed`).
    """
    import asyncio
    from decimal import Decimal
    from types import SimpleNamespace

    from app.routes import feed as feed_route
    from app.utils.personalization import PersonalizationContext
    from app.utils import futures_market_snapshot as fms
    from app.utils.settled_feed_price_card import settled_feed_price_card

    # --- B1 (Q8e): 11.5h separation between basis (T-12.5h) and fresh observation (T-1h) is rejected ---
    basis_12_5h_ago = "2026-10-14T11:17:16+00:00"
    obs_1h_ago_epoch = int(
        datetime(2026, 10, 14, 22, 47, 16, tzinfo=timezone.utc).timestamp()
    )
    meta_1h_sep = _zacharia_rule_meta(
        question="Zacharia issues public apology by December 31?",
        description=DEC31_RULE_DESCRIPTION,
        group_item_title="December 31",
        end_date_iso=DEC31_RESOLUTION_ISO,
        extra={"dated_movement_basis": {"246879007": [0.850, basis_12_5h_ago]}},
    )
    outcomes_1h_sep = _make_dec31_outcomes(
        stored_yes_change=0.130,
        yes_prob=0.980,
        yes_obs_epoch=obs_1h_ago_epoch,
        no_obs_epoch=obs_1h_ago_epoch,
    )
    member_1h_sep = build_deadline_member_contract(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        group_id="polymarket:256241",
        status="open",
        resolution_date=DEC31_RESOLUTION_ISO,
        market_metadata=meta_1h_sep,
        outcomes=outcomes_1h_sep,
        now=RETAINED_NOW,
    )
    assert member_1h_sep is not None
    assert member_1h_sep["movement_status"] == "stale_price_observation"
    assert member_1h_sep["near_certain_open_eligible"] is False
    assert (
        qualifies_for_deadline_near_certain_exception(
            name="Zacharia issues public apology by December 31?",
            source="polymarket",
            external_id="0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
            group_id="polymarket:256241",
            status="open",
            resolution_date=DEC31_RESOLUTION_ISO,
            market_metadata=meta_1h_sep,
            outcomes=outcomes_1h_sep,
            prices_stopped=False,
            now=RETAINED_NOW,
        )
        is False
    )

    # --- B3: <=5% placeholder floor suppression & <=3% non-exemption ---
    meta_low_prob = _zacharia_rule_meta(
        question="Zacharia issues public apology by October 31?",
        description=OCT31_RULE_DESCRIPTION,
        group_item_title="October 31",
        end_date_iso=OCT31_RESOLUTION_ISO,
        extra={"dated_movement_basis": {"246879005": [0.120, RETAINED_BASIS_AT]}},
    )
    outcomes_2pct = _make_oct31_outcomes(stored_yes_change=-0.100, yes_prob=0.020)
    member_2pct = build_deadline_member_contract(
        market_id=65678073,
        name="Zacharia issues public apology by October 31?",
        source="polymarket",
        external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        group_id="polymarket:256241",
        status="open",
        resolution_date=OCT31_RESOLUTION_ISO,
        market_metadata=meta_low_prob,
        outcomes=outcomes_2pct,
        now=RETAINED_NOW,
    )
    assert member_2pct is not None
    assert member_2pct["movement_status"] == "placeholder_floor_suppressed"
    assert member_2pct["supported_move_points"] is None
    assert member_2pct["is_near_certain"] is False
    assert member_2pct["near_certain_open_eligible"] is False
    assert (
        qualifies_for_deadline_near_certain_exception(
            name="Zacharia issues public apology by October 31?",
            source="polymarket",
            external_id="0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
            group_id="polymarket:256241",
            status="open",
            resolution_date=OCT31_RESOLUTION_ISO,
            market_metadata=meta_low_prob,
            outcomes=outcomes_2pct,
            prices_stopped=False,
            now=RETAINED_NOW,
        )
        is False
    )

    # --- B2 & B6: Snapshot `to_plain -> from_plain` preserves `is_winner` / `resolution_source` ---
    def _orm_market(
        mid: int,
        name: str,
        ext_id: str,
        res_iso: str,
        meta: dict,
        outcomes_spec: list[dict],
        status: str = "open",
    ) -> SimpleNamespace:
        return SimpleNamespace(
            id=mid,
            name=name,
            source="polymarket",
            external_id=ext_id,
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
            market_metadata=dict(meta),
            curation_score_adj=0,
            volume_24h=Decimal("2500.00"),
            updated_at=RETAINED_NOW,
            commence_time=None,
            resolution_date=datetime.fromisoformat(res_iso),
            status=status,
            created_at=RETAINED_NOW,
            llm_league=None,
            llm_gender=None,
            llm_level=None,
            mutually_exclusive=True,
            sport=None,
            outcomes=[
                SimpleNamespace(
                    id=o["id"],
                    name=o["name"],
                    team_id=None,
                    current_probability=Decimal(str(o["current_probability"])),
                    probability_change_24h=(
                        Decimal(str(o["probability_change_24h"]))
                        if o.get("probability_change_24h") is not None
                        else None
                    ),
                    rank=idx + 1,
                    rank_change_24h=0,
                    opening_probability=Decimal("0.500"),
                    calibration_probability=None,
                    current_yes_bid=None,
                    current_yes_ask=None,
                    external_id=o.get("external_id", f"{ext_id}_{idx}"),
                    last_updated=RETAINED_OBS_DT,
                    opening_captured_at=None,
                    resolution_source=o.get("resolution_source"),
                    volume_24h=None,
                    volume_24h_at=None,
                    is_winner=o.get("is_winner"),
                )
                for idx, o in enumerate(outcomes_spec)
            ],
        )

    oct31_meta = _zacharia_rule_meta(
        question="Zacharia issues public apology by October 31?",
        description=OCT31_RULE_DESCRIPTION,
        group_item_title="October 31",
        end_date_iso=OCT31_RESOLUTION_ISO,
        extra={"market_count": 2},
    )
    dec31_meta = _zacharia_rule_meta(
        question="Zacharia issues public apology by December 31?",
        description=DEC31_RULE_DESCRIPTION,
        group_item_title="December 31",
        end_date_iso=DEC31_RESOLUTION_ISO,
        extra={
            "market_count": 2,
            "dated_movement_basis": {"246879007": [0.310, RETAINED_BASIS_AT]},
        },
    )
    oct31_settled_lagging_open = _orm_market(
        65678073,
        "Zacharia issues public apology by October 31?",
        "0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
        OCT31_RESOLUTION_ISO,
        oct31_meta,
        [
            {
                "id": 246879005,
                "name": "Yes",
                "current_probability": 0.48,
                "probability_change_24h": -0.12,
                "is_winner": False,
                "resolution_source": "api_settlement",
            },
            {
                "id": 246879006,
                "name": "No",
                "current_probability": 0.52,
                "probability_change_24h": 0.12,
                "is_winner": True,
                "resolution_source": "api_settlement",
            },
        ],
        status="open",
    )
    dec31_open_mover = _orm_market(
        65678074,
        "Zacharia issues public apology by December 31?",
        "0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        DEC31_RESOLUTION_ISO,
        dec31_meta,
        _make_dec31_outcomes(stored_yes_change=-0.065),
        status="open",
    )
    rehydrated_c3 = fms.from_plain(
        fms.to_plain([oct31_settled_lagging_open, dec31_open_mover])
    )
    assert rehydrated_c3[0].outcomes[0].is_winner is False
    assert rehydrated_c3[0].outcomes[1].is_winner is True
    assert rehydrated_c3[0].outcomes[1].resolution_source == "api_settlement"

    # Price-cards terminal carrier also includes `deadline_member` with `Resolved · No`
    settled_card = settled_feed_price_card(rehydrated_c3[0], {})
    assert settled_card is not None
    assert settled_card["data"]["deadline_member"]["settlement"]["state"] == "resolved"
    assert settled_card["data"]["deadline_member"]["settlement"]["result"] == "No"
    assert (
        settled_card["data"]["deadline_member"]["settlement"]["lagging_local_status"]
        is True
    )

    # --- B3 (Q8c): Lone 98% mover without a forming >=2-member family is evicted ---
    dec31_98_meta = _zacharia_rule_meta(
        question="Zacharia issues public apology by December 31?",
        description=DEC31_RULE_DESCRIPTION,
        group_item_title="December 31",
        end_date_iso=DEC31_RESOLUTION_ISO,
        extra={
            "market_count": 2,
            "dated_movement_basis": {"246879007": [0.850, RETAINED_BASIS_AT]},
        },
    )
    lone_dec31_98 = _orm_market(
        65678074,
        "Zacharia issues public apology by December 31?",
        "0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
        DEC31_RESOLUTION_ISO,
        dec31_98_meta,
        _make_dec31_outcomes(stored_yes_change=0.130, yes_prob=0.980),
        status="open",
    )

    async def _score_and_dedupe(rows: list[SimpleNamespace]) -> list[dict]:
        snaps = fms.from_plain(fms.to_plain(rows))
        scored = await feed_route._score_futures(
            db=None,  # type: ignore[arg-type]
            now=RETAINED_NOW,
            sport_filter=None,
            ctx=PersonalizationContext(),
            preloaded_base={"markets": snaps, "curator_ids": set()},
        )
        deduped = feed_route._dedupe_futures_by_canonical(scored)
        deduped = feed_route._dedupe_futures_by_group_id(deduped)
        deduped, _ = feed_route._suppress_zero_probability_cards(deduped)
        displayed, _ = feed_route.apply_discover_display_chain(
            deduped,
            limit=20,
            ctx=PersonalizationContext(),
            event_pct=0.15,
            include_events=True,
            my_teams_only=False,
            sports_mode=False,
            now=RETAINED_NOW,
        )
        return displayed

    assert asyncio.run(_score_and_dedupe([lone_dec31_98])) == []


