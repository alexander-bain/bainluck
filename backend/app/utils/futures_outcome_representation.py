"""The full eligible futures field, represented before surface selection (#11616).

Extracted from futures detail without changing its admission or numerical policy.
No database/network access, ORM writes or visible-row limit. Callers supply the
existing asynchronous refusal set and any already-read grid/fleet context.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.utils.futures_liveness import leg_is_graded
from app.utils.futures_market_snapshot import dated_movement_points
from app.utils.futures_unsupported_price import WITHHELD_PRICE_FIELDS
from app.utils.grid_out_division_legs import drop_out_division_legs
from app.utils.series_card_labels import market_threshold_label, reader_outcome_name
from app.utils.settlement_display import (
    applies_to_market as settlement_display_applies,
    settlement_display,
)


@dataclass
class FuturesOutcomeRepresentation:
    outcomes: list[dict]
    source_outcomes: list[Any]
    prices_withheld: int
    openings_withheld: bool
    expired_rungs_dropped: int
    concept_outcome_count: int


def _board_has_a_verdict(outcomes) -> bool:
    return any(
        leg_is_graded(
            getattr(o, "is_winner", None), getattr(o, "resolution_source", None)
        )
        for o in outcomes
    )


def _leg_side_label(side: str, question: str) -> str:
    return f"{side} — {question}"


def eligible_futures_outcomes(market, out_division_labels=None) -> list:
    """The destination's admitted source universe, before price refusal."""
    from app.utils.duplicate_condition_outcomes import drop_duplicate_legs
    from app.utils.superseded_name_twins import drop_superseded_name_twins
    from app.utils.outcome_display import (
        drop_unbacked_legs,
        is_placeholder_outcome_name,
    )

    valid_outcomes = [
        o
        for o in drop_unbacked_legs(
            drop_superseded_name_twins(
                drop_duplicate_legs(
                    market.outcomes, lambda o: getattr(o, "external_id", None)
                ),
                name_of=lambda o: getattr(o, "name", None),
                external_id_of=lambda o: getattr(o, "external_id", None),
                is_winner_of=lambda o: getattr(o, "is_winner", None),
                resolution_source_of=lambda o: getattr(o, "resolution_source", None),
            ),
            lambda o: getattr(o, "external_id", None),
            market_is_open=getattr(market, "status", None) == "open",
            is_winner_of=lambda o: bool(getattr(o, "is_winner", None)),
        )
        if not is_placeholder_outcome_name(getattr(o, "name", None))
    ]
    valid_outcomes = drop_out_division_legs(valid_outcomes, out_division_labels)
    return valid_outcomes


def local_futures_withheld_ids(
    market,
    source_outcomes,
    unsupported_price_outcome_ids=None,
    *,
    fleet_newest_observation=None,
) -> set[int]:
    """Same local age/verdict policy for search refusal and detail rendering."""
    from app.utils.odds_api_retirement import WITHDRAWN_STATUS
    from app.utils.market_staleness import (
        stale_observation_keys,
        board_touched_at,
        unobserved_board_keys,
    )

    withheld = unsupported_price_outcome_ids or set()
    _board_status = getattr(market, "status", None)
    _board_verdict = _board_has_a_verdict(source_outcomes)
    if _board_status == "open":
        withheld = withheld | stale_observation_keys(
            ((o.id, getattr(o, "last_updated", None)) for o in source_outcomes)
        )
    if _board_status in ("open", "resolved"):
        withheld = withheld | unobserved_board_keys(
            ((o.id, getattr(o, "last_updated", None)) for o in source_outcomes),
            board_touched_at=board_touched_at(market),
            fleet_newest_observation=fleet_newest_observation,
            board_has_a_verdict=_board_verdict,
        )
    if _board_status == WITHDRAWN_STATUS:
        withheld = withheld | {o.id for o in source_outcomes}
    return withheld


def represent_futures_outcomes(
    market,
    unsupported_price_outcome_ids=None,
    *,
    fleet_newest_observation=None,
    leg_sides=None,
    out_division_labels=None,
    now=None,
) -> FuturesOutcomeRepresentation:
    """Keep detail's full-field sequence; select or pin visible rows afterward."""
    from app.utils.field_opening_coherence import field_openings_publishable
    from app.utils.market_staleness import (
        expired_ladder_rungs,
    )
    from app.utils.outcome_display import (
        assign_display_ranks,
        normalize_display_probs,
        leader_pick_order,
        drop_dominant_field_outcomes,
        drop_incoherent_near_certain,
    )

    valid_outcomes = eligible_futures_outcomes(market, out_division_labels)
    sorted_outcomes = sorted(
        valid_outcomes, key=lambda o: o.current_probability or 0, reverse=True
    )
    targets_settlement_display = settlement_display_applies(market)
    outcomes = [
        {
            "id": o.id,
            "name": (
                _leg_side_label(leg_sides[o.external_id], o.name)
                if leg_sides and o.external_id in leg_sides
                else reader_outcome_name(
                    o.external_id, o.name, market_threshold_label(market)
                )
                or o.name
            ),
            "probability": (
                float(o.current_probability)
                if o.current_probability is not None
                else None
            ),
            "american_odds": getattr(o, "current_american_odds", None),
            "rank": getattr(o, "rank", None),
            "rank_change_24h": None,
            "probability_change_24h": dated_movement_points(
                market,
                o.id,
                o.current_probability,
                getattr(o, "probability_change_24h", None),
            ),
            "opening_probability": (
                float(getattr(o, "opening_probability", None))
                if getattr(o, "opening_probability", None)
                else None
            ),
            "opening_american_odds": getattr(o, "opening_american_odds", None),
            "is_winner": getattr(o, "is_winner", None),
            "resolution_source": getattr(o, "resolution_source", None),
            "last_updated": (
                getattr(o, "last_updated", None).isoformat()
                if getattr(o, "last_updated", None)
                else None
            ),
            "price_changed_at": (
                stamp.isoformat()
                if (stamp := getattr(o, "price_changed_at", None))
                else None
            ),
            **(
                {
                    "settlement_display": settlement_display(
                        is_winner=getattr(o, "is_winner", None),
                        resolution_source=getattr(o, "resolution_source", None),
                        stored_probability=o.current_probability,
                    )
                }
                if targets_settlement_display
                else {}
            ),
        }
        for o in sorted_outcomes
    ]
    expired_rungs_dropped = 0
    if getattr(market, "status", None) == "open":
        expired_rung_names = expired_ladder_rungs(
            [
                (
                    o["name"],
                    o.get("probability"),
                    o.get("last_updated"),
                    o.get("is_winner"),
                )
                for o in outcomes
            ],
            now or datetime.now(timezone.utc),
        )
        if expired_rung_names:
            live_rungs = [o for o in outcomes if o["name"] not in expired_rung_names]
            if live_rungs:
                expired_rungs_dropped = len(outcomes) - len(live_rungs)
                outcomes = live_rungs
    withheld = local_futures_withheld_ids(
        market,
        sorted_outcomes,
        unsupported_price_outcome_ids,
        fleet_newest_observation=fleet_newest_observation,
    )
    prices_withheld = 0
    if withheld:
        for o in outcomes:
            if o["id"] in withheld:
                for field in WITHHELD_PRICE_FIELDS:
                    o[field] = None
                prices_withheld += 1

    def _withhold_openings() -> None:
        for o in outcomes:
            o["opening_probability"] = None
            o["opening_american_odds"] = None

    openings_withheld = not field_openings_publishable(
        [o["opening_probability"] for o in outcomes],
        mutually_exclusive=getattr(market, "mutually_exclusive", True),
    )
    if openings_withheld:
        _withhold_openings()
    if normalize_display_probs(
        outcomes,
        mutually_exclusive=getattr(market, "mutually_exclusive", True),
        field_complete=prices_withheld == 0,
    ):
        _withhold_openings()
        openings_withheld = True
        for o in outcomes:
            o["probability_change_24h"] = None
    concept_outcome_count = len(outcomes) + expired_rungs_dropped
    outcomes = drop_incoherent_near_certain(
        outcomes,
        lambda o: o.get("probability"),
        mutually_exclusive=getattr(market, "mutually_exclusive", True),
        market_is_open=getattr(market, "status", None) == "open",
        is_winner_of=lambda o: bool(o.get("is_winner")),
    )

    def _is_graded_winner(o: dict) -> bool:
        return bool(o.get("is_winner")) and o.get("resolution_source") is not None

    outcomes = drop_dominant_field_outcomes(
        outcomes,
        lambda o: o.get("name"),
        lambda o: o.get("probability"),
        is_winner_of=_is_graded_winner,
    )
    leader_pick_order(outcomes, is_winner_of=_is_graded_winner)
    assign_display_ranks(outcomes)
    return FuturesOutcomeRepresentation(
        outcomes,
        sorted_outcomes,
        prices_withheld,
        openings_withheld,
        expired_rungs_dropped,
        concept_outcome_count,
    )
