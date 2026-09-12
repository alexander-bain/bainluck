"""CU-1 clause (4), #5273 — the venue's own semantics survive the parse.

WHAT THIS PROTECTS.  Gamma publishes `sportsMarketType`, `line`, `description`
and `resolutionSource`; `PolymarketMarket` retained none of them, so every
consumer re-derived what a market asks from its title.  That is how a
derivative's price got published as a match winner (#5432, #5311).  Retaining
the venue's own label gives a deterministic classifier the second, independent
signal standing notice 40 requires.

THE ONE THAT MATTERS.  `child_moneyline` is winner-shaped and is NOT a
full-contest winner.  `"moneyline" in "child_moneyline"` is True, so any
containment test admits map and period winners into the winner slot — the exact
defect CU-1 exists to stop.  `test_child_moneyline_is_refused` is the guard for
that class; it fails if `is_full_contest_winner_type` is ever loosened to
`in`, `startswith` or `endswith`.
"""

import inspect

import pytest

from app.services.polymarket_api import (
    GAMMA_FULL_CONTEST_WINNER_TYPES,
    PolymarketAPIService,
    PolymarketMarket,
    is_full_contest_winner_type,
)


def _parse(**overrides) -> PolymarketMarket:
    """Parse a Gamma-shaped payload through the real construction site."""
    payload = {
        "conditionId": "0xcond",
        "question": "Barcelona vs. Feyenoord",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.65", "0.35"]',
        "clobTokenIds": '["111", "222"]',
    }
    payload.update(overrides)
    market = PolymarketAPIService()._parse_market(payload)
    assert market is not None, "the parse returned None — the fixture is wrong"
    return market


# ── the winner-slot guard ──────────────────────────────────────────────────


def test_child_moneyline_is_refused():
    """A map/period winner must never satisfy the full-contest winner test.

    Observed on Gamma 2026-09-12: `child_moneyline` on
    `Counter-Strike: Nemiga vs Just Players - Map 1 Winner`.
    """
    assert is_full_contest_winner_type("moneyline") is True
    assert is_full_contest_winner_type("child_moneyline") is False


def test_the_winner_test_is_not_a_containment_test():
    """Kill every substring form, not just the one value we happened to see.

    A containment/prefix/suffix implementation passes the two-value test above
    only by luck of which side the affix lands on; these synthetic values close
    that off, so loosening the comparison reddens this test.
    """
    for impostor in (
        "child_moneyline",
        "moneyline_child",
        "first_half_moneyline",
        "moneyline_first_half",
        "MONEYLINE",
        " moneyline",
        "moneyline ",
    ):
        assert is_full_contest_winner_type(impostor) is False, impostor


def test_an_absent_label_refuses_rather_than_convicts():
    """None is "cannot corroborate", and callers may not read it as evidence.

    The field is absent on 21% of markets, so a False here must never be
    allowed to mean "this is a derivative".
    """
    assert is_full_contest_winner_type(None) is False


def test_an_unseen_value_fails_closed():
    """The vocabulary is an open set; a value we have never seen is not a winner."""
    assert is_full_contest_winner_type("some_market_type_invented_next_week") is False


def test_the_winner_set_holds_exactly_one_value():
    """Widening the winner slot must be a deliberate, visible edit."""
    assert GAMMA_FULL_CONTEST_WINNER_TYPES == frozenset({"moneyline"})


def test_the_predicate_does_not_use_a_substring_operator():
    """Source-level backstop: the comparison is membership, not containment.

    Paired with the behavioural tests above rather than standing alone — a
    source scan on its own is a vacuous guard.
    """
    src = inspect.getsource(is_full_contest_winner_type)
    body = src.split('"""')[-1]
    for banned in ("startswith", "endswith", ".find(", "in sports_market_type"):
        assert banned not in body, f"{banned} reintroduces the containment defect"


# ── the four fields survive the parse ──────────────────────────────────────


def test_all_four_venue_fields_are_retained():
    market = _parse(
        sportsMarketType="moneyline",
        line="-1.5",
        description="In the upcoming Ukraine Premier Liha game between …",
        resolutionSource="https://upl.ua/",
    )
    assert market.sports_market_type == "moneyline"
    assert market.line == -1.5
    assert market.description.startswith("In the upcoming")
    assert market.resolution_source == "https://upl.ua/"


def test_absent_fields_are_none_and_do_not_break_the_parse():
    """21% of markets carry no `sportsMarketType`; they must still parse."""
    market = _parse()
    assert market.sports_market_type is None
    assert market.line is None
    assert market.description is None
    assert market.resolution_source is None
    # the market itself is intact — absence costs us nothing else
    assert market.condition_id == "0xcond"
    assert market.outcome_prices == [0.65, 0.35]


# ── `line` is a string at the venue, and "0" is a real line ────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [("-1.5", -1.5), ("1.5", 1.5), ("0", 0.0), ("0.0", 0.0), (2.5, 2.5)],
)
def test_line_is_coerced_explicitly(raw, expected):
    assert _parse(line=raw).line == expected


def test_a_zero_line_is_kept_and_is_distinguishable_from_absence():
    """`"0"` is a legitimate pick'em line.

    Both a 0.0 line and an absent line are falsy, so a consumer that tests
    truthiness reads every pick'em as "no line". This asserts the two states
    are actually different values, which is what makes `is not None` the
    correct test for a consumer to write.
    """
    zero = _parse(line="0").line
    absent = _parse().line
    assert zero == 0.0
    assert zero is not None
    assert absent is None
    assert zero != absent


def test_an_unparseable_line_costs_the_line_not_the_market():
    """A bad line must never lose us the market's price (gotcha #36 shape)."""
    market = _parse(line="not-a-number")
    assert market.line is None
    assert market.outcome_prices == [0.65, 0.35]


# ── empty string is not absence ────────────────────────────────────────────


def test_empty_strings_are_preserved_rather_than_collapsed_to_none():
    """"The venue published a blank" and "the venue said nothing" differ.

    Collapsing them destroys a signal quarantine may need, so the parse keeps
    them apart.
    """
    market = _parse(description="", resolutionSource="", sportsMarketType="")
    assert market.description == ""
    assert market.resolution_source == ""
    assert market.sports_market_type == ""
    assert market.description is not None
    assert market.resolution_source is not None
    # an empty label still cannot corroborate a winner
    assert is_full_contest_winner_type(market.sports_market_type) is False


# ── the fields are additive ────────────────────────────────────────────────


def test_existing_fields_are_untouched_by_the_addition():
    """Clause (4) is additive: nothing that parsed before parses differently."""
    market = _parse(
        groupItemTitle="33°F or below",
        negRisk=True,
        volume="1234.5",
        sportsMarketType="spreads",
    )
    assert market.group_item_title == "33°F or below"
    assert market.neg_risk is True
    assert market.volume == 1234.5
    assert market.question == "Barcelona vs. Feyenoord"
    assert market.clob_token_ids == ["111", "222"]
