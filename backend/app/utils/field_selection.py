"""A dated field's confirmed members followed by its title market (#11935, 65-A)."""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from app.utils.container_presentation import MEMBER_MARKET, market_destination
from app.utils.futures_liveness import SETTLEMENT_SOURCE


def _rc() -> Any:
    return importlib.import_module("app.utils.roundup_containers")


def _confirmed_members(market: Mapping[str, Any], count: int) -> Any:
    """A full venue grade establishes the field. Prices and dates play no part."""
    from app.utils.field_band import _is_placeholder_name

    outcomes = market.get("outcomes")
    if (
        not isinstance(outcomes, Sequence)
        or isinstance(outcomes, (str, bytes))
        or not outcomes
    ):
        return _rc().RoundupRefusal((("selection", "outcomes_missing"),))
    identifiers = set()
    names = set()
    selected = []
    for outcome in outcomes:
        if not isinstance(outcome, Mapping):
            return _rc().RoundupRefusal((("selection", "malformed_outcome"),))
        identifier = outcome.get("id")
        name = str(outcome.get("name") or "").strip()
        if (
            isinstance(identifier, bool)
            or not isinstance(identifier, int)
            or identifier <= 0
            or identifier in identifiers
            or _is_placeholder_name(name)
            or name.casefold() in names
        ):
            return _rc().RoundupRefusal((("selection", "invalid_outcome_identity"),))
        identifiers.add(identifier)
        names.add(name.casefold())
        if outcome.get("resolution_source") != SETTLEMENT_SOURCE or not isinstance(
            outcome.get("is_winner"), bool
        ):
            return _rc().RoundupRefusal((("selection", "venue_result_pending"),))
        if outcome["is_winner"]:
            selected.append(outcome)
    if len(selected) != count:
        return _rc().RoundupRefusal(
            (("selection", f"winner_count_{len(selected)}_expected_{count}"),)
        )
    return sorted(
        selected, key=lambda outcome: (str(outcome["name"]).casefold(), outcome["id"])
    )


def _result_member(
    market: Mapping[str, Any], selected: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Use the field kind's card envelope, carrying source-confirmed results."""
    from app.utils.field_band import (
        _PricedOutcome,
        _build_section_market_card,
        _iso_utc,
    )

    outcomes = [
        _PricedOutcome(
            int(row["id"]),
            str(row["name"]),
            1.0,
            None,
            _iso_utc(row.get("last_updated")),
        )
        for row in selected
    ]
    card = _build_section_market_card(
        market,
        market_id=int(market["id"]),
        source=str(market["source"]),
        category="ncaaf",
        shown_outcomes=outcomes,
        board_outcomes=(),
        total_outcome_count=len(outcomes),
        mutually_exclusive=bool(market.get("mutually_exclusive")),
    )
    card["status"] = "resolved"
    for outcome in card["top_outcomes"]:
        outcome.update(
            probability=None,
            movement=None,
            rank=None,
            is_winner=True,
            resolution_source=SETTLEMENT_SOURCE,
        )
    return {
        "type": MEMBER_MARKET,
        "id": int(market["id"]),
        "destination": market_destination(int(market["id"])),
        "card": card,
        "event_id": None,
    }


def select_field_selection(
    markets: Mapping[int, Mapping[str, Any]],
    *,
    definition: Mapping[str, Any],
    withheld: Mapping[int, set[int]] | None = None,
) -> Any:
    """One reproducible set supplies the result section and the current title field."""
    from app.utils.field_band import (
        _extract_market_outcomes,
        parse_market_ref,
        select_field_band,
    )

    RoundupRefusal = _rc().RoundupRefusal
    rule = definition["rule"]
    refs = [rule["field"], rule["second_section"]]
    chosen = []
    for reference in refs:
        source, identifier, token = parse_market_ref(reference)
        market = (
            markets.get(identifier)
            if identifier is not None
            else next(
                (
                    row
                    for row in markets.values()
                    if row.get("source") == source and row.get("external_id") == token
                ),
                None,
            )
        )
        if market is None or market.get("source") != source:
            return RoundupRefusal((("selection", "market_missing_or_wrong_source"),))
        chosen.append(market)
    field, title = chosen
    if (
        field["id"] == title["id"]
        or field.get("mutually_exclusive") is not False
        or title.get("mutually_exclusive") is not True
    ):
        return RoundupRefusal((("selection", "incompatible_fields"),))
    selected = _confirmed_members(field, int(rule["selected_count"]))
    if isinstance(selected, RoundupRefusal):
        return selected
    if len(field["outcomes"]) < int(
        rule.get("min_field_outcomes", rule["selected_count"])
    ):
        return RoundupRefusal((("selection", "field_incomplete"),))
    field_member = _result_member(field, selected)
    title_outcomes = title.get("outcomes")
    if (
        not isinstance(title_outcomes, Sequence)
        or isinstance(title_outcomes, (str, bytes))
        or any(not isinstance(row, Mapping) for row in title_outcomes)
    ):
        return RoundupRefusal((("title", "outcomes_missing_or_malformed"),))
    # A championship winner withdraws its remaining price rows until the full
    # venue result is available. An open clock-expired field remains ungraded.
    if title.get("status") != "open" or any(
        row.get("is_winner") is True for row in title_outcomes
    ):
        champions = _confirmed_members(title, 1)
        if isinstance(champions, RoundupRefusal):
            return champions
        title_member = _result_member(title, champions)
        title_heading = "Champion"
        footer = "Venue-confirmed playoff field · Champion confirmed"
    else:
        priced, reason = _extract_market_outcomes(
            title,
            expected_source=str(title["source"]),
            withheld_ids=(withheld or {}).get(int(title["id"])),
        )
        if not priced:
            return RoundupRefusal((("title", reason or "no_current_prices"),))
        title_set = select_field_band(
            markets,
            field_spec=rule["second_section"],
            band=(0, 1),
            section_titles=(definition["section_title"][1],),
            card_rows=min(4, len(priced)),
            min_field_outcomes=1,
            min_band_outcomes=1,
            normalize=True,
            withheld_by_market=withheld,
        )
        if isinstance(title_set, RoundupRefusal):
            return title_set
        title_member = title_set.members[0]
        title_heading = definition["section_title"][1]
        footer = definition["footer"]
    members = [field_member, title_member]
    sections = [
        {"class": key, "title": heading, "layout": "field", "members": [member]}
        for key, heading, member in zip(
            ("selection", "title"),
            (definition["section_title"][0], title_heading),
            members,
        )
    ]
    return _rc().RoundupMembers(
        members,
        sections=sections,
        footer=footer,
        revision_ids=[int(row["id"]) for row in selected]
        + [int(row["id"]) for row in title_member["card"]["top_outcomes"]],
        feed_item={
            "type": "bundle",
            "score": 0,
            "headline": definition["name"],
            "reason": definition["name"],
            "data": {
                "id": "roundup:" + definition["slug"].removeprefix("roundup-"),
                "title": definition["name"],
                "kind": "theme",
                "item_count": len(members),
                "member_ids": [member["id"] for member in members],
                "relations": definition["relations"],
                "level": definition["level"],
            },
        },
    )


def build_field_selection_producer(
    definition: Mapping[str, Any], *, load_markets: Any = None
) -> Any:
    """The shared folder factory is the registration path for the dated successor."""
    from app.utils.field_band import _load_markets_from_db, parse_market_ref

    definition = _rc().validate_roundup_definition(deepcopy(definition))
    rule = definition["rule"]
    if (
        rule.get("producer") != "field_selection"
        or isinstance(rule.get("selected_count"), bool)
        or not isinstance(rule.get("selected_count"), int)
        or rule["selected_count"] <= 0
        or not isinstance(definition.get("section_title"), list)
        or len(definition["section_title"]) != 2
        or not isinstance(definition.get("enabled"), bool)
        or definition["relations"] != ["same_event", "same_window"]
        or definition["level"] != "member"
    ):
        raise ValueError(
            "A field-selection definition needs its result count, two sections and enabled boolean"
        )
    references = [parse_market_ref(rule[key]) for key in ("field", "second_section")]

    async def produce(db):
        ids = [identifier for _, identifier, _ in references if identifier is not None]
        tokens = [token for _, _, token in references if token is not None]
        if load_markets is None:
            markets, withheld = await _load_markets_from_db(
                db, ids, tokens, sources=[source for source, _, _ in references]
            )
        else:
            markets, withheld = await load_markets(db, ids, tokens)
        return select_field_selection(markets, definition=definition, withheld=withheld)

    return _rc().RoundupProducer(
        slug=definition["slug"],
        name=definition["name"],
        category=definition["category"],
        section_title=definition["section_title"],
        footer=definition["footer"],
        produce=produce,
        relations=definition["relations"],
        level=definition["level"],
        rule=rule,
        enabled=lambda: definition["enabled"],
    )
