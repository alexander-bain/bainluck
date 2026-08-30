"""Q446 — a field nobody has bid on is a price list, not a forecast.

THE SPECIMEN, production 2026-08-29. `GET /api/golf` served, under PGA Tour:

    Omega European Masters   4 golfers
      Andreas Halvorsen 10%  ·  Adrian Meronk 10%
      Eddie Pepperell   10%  ·  Antoine Rozner 10%

Four of a ~156-player field, each at an identical 10%, summing to 0.4. Behind every
one of them, `futures_outcomes` holds `yes_bid 0.0000 / yes_ask 0.1000`, and every
snapshot the market has ever taken holds `last_price 0.0000`:

    outcome_id  captured_at                  probability  yes_bid  yes_ask  last_price
    222605753   2026-08-29 16:51:58+00       0.100000     0.0000   0.1000   0.0000
    222605754   2026-08-29 16:51:58+00       0.100000     0.0000   0.1000   0.0000
    222605755   2026-08-29 16:51:58+00       0.100000     0.0000   0.1000   0.0000
    222605756   2026-08-29 16:51:58+00       0.100000     0.0000   0.1000   0.0000

Nobody has bid on any golfer in this tournament and nobody has ever traded one. The
10% is Kalshi's ask, published as a probability by the ask-only arm of
`_kalshi_yes_probability`.

THE CONTROLS ARE THE POINT. Two other open golf fields also have no bid on any
outcome — `CPKC Women's Open End of Round 3 Leader` (154 priced) and
`FM Championship End of Round 3 Leader` (144 priced) — and both must survive,
because their prices are `last_price`: real trades, on a book that has since gone
one-sided. "No bid" alone is not the rule. "Every number here is an unaccepted
offer" is.

Measured over all 112 open golf-identity markets on 2026-08-29 by driving this
predicate against their real books: it fires on one, the specimen.
"""

import types

import pytest

from app.routes.golf import _field_is_offer_sheet


def _o(prob, bid, ask, name="Someone"):
    return types.SimpleNamespace(
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        name=name,
    )


# --------------------------------------------------------------------------
# The specimen
# --------------------------------------------------------------------------


def test_omega_european_masters_is_an_offer_sheet():
    """market 59759220, verbatim."""
    field = [
        _o(0.10, 0.0, 0.10, "Andreas Halvorsen"),
        _o(0.10, 0.0, 0.10, "Adrian Meronk"),
        _o(0.10, 0.0, 0.10, "Eddie Pepperell"),
        _o(0.10, 0.0, 0.10, "Antoine Rozner"),
    ]
    assert _field_is_offer_sheet(field) is True


def test_renormalizing_it_would_have_made_it_look_more_confident():
    """Why the field is dropped WHOLE rather than renormalized.

    `_golf_winner_renorm_factor` scales a winner field to sum 1.0. Four identical
    10% offers renormalize to four identical 25% "forecasts" — the same
    non-information, wearing a bigger number. Recording the arithmetic here so the
    next reader does not reach for the renormalizer as the gentler fix.
    """
    from app.routes.golf import _golf_winner_renorm_factor

    # Sum is 0.4, so the <=1.5 early return hands back 1.0 and the offers are
    # printed as-is today. Above 1.5 it would have scaled them instead.
    assert _golf_winner_renorm_factor("Omega European Masters Winner", 4, 0.4) == 1.0
    scaled = _golf_winner_renorm_factor("Some Winner", 4, 4 * 0.10 * 10)
    assert scaled is not None
    assert round(0.10 * 10 * scaled, 4) == 0.25


# --------------------------------------------------------------------------
# The controls
# --------------------------------------------------------------------------


def test_no_bid_but_traded_prices_survive():
    """CPKC Women's Open R3 Leader / FM Championship R3 Leader.

    No bid on any outcome, but the printed number is `last_price` — a real trade —
    and so differs from the ask. These fields carry information and must render.
    """
    field = [
        _o(0.05, 0.0, 0.09),
        _o(0.03, 0.0, 0.08),
        _o(0.05, 0.0, 0.11),
    ]
    assert _field_is_offer_sheet(field) is False


def test_one_real_bid_anywhere_saves_the_field():
    """A single competitor with a genuine bid means the field is being traded."""
    field = [
        _o(0.10, 0.0, 0.10),
        _o(0.10, 0.0, 0.10),
        _o(0.12, 0.08, 0.14),
    ]
    assert _field_is_offer_sheet(field) is False


def test_a_bookless_model_field_is_never_an_offer_sheet():
    """DataGolf and odds_api carry no book at all — by construction, not exemption.

    Both are large uniform-looking fields of small numbers, which is exactly the
    shape a careless version of this rule would eat.
    """
    field = [_o(0.02, None, None) for _ in range(50)]
    assert _field_is_offer_sheet(field) is False


def test_a_mixed_field_with_one_bookless_outcome_survives():
    """One outcome with no ask is enough: we cannot say every number is an offer."""
    field = [_o(0.10, 0.0, 0.10), _o(0.10, 0.0, 0.10), _o(0.10, None, None)]
    assert _field_is_offer_sheet(field) is False


def test_a_lone_longshot_is_not_a_field():
    """A single no-bid binary is a normal thing for a real market to contain."""
    assert _field_is_offer_sheet([_o(0.02, 0.0, 0.02)]) is False
    assert _field_is_offer_sheet([]) is False


def test_unpriced_outcomes_do_not_count_toward_the_field():
    """Two priced offers plus padding is still a two-outcome offer sheet."""
    field = [_o(None, None, None), _o(0.10, 0.0, 0.10), _o(0.10, 0.0, 0.10)]
    assert _field_is_offer_sheet(field) is True


def test_a_null_bid_counts_as_no_bid():
    """`bid IS NULL` and `bid = 0` are the same fact on a Kalshi/Polymarket book.

    `_is_placeholder_price` deliberately fails OPEN on a NULL side (gotcha #53). This
    rule does not need that caution, because it never judges an outcome alone: a NULL
    bid only matters here when EVERY outcome's number is also its own ask.
    """
    field = [_o(0.10, None, 0.10), _o(0.10, None, 0.10)]
    assert _field_is_offer_sheet(field) is True


@pytest.mark.parametrize("prob", [0.099, 0.101, 0.05])
def test_a_price_that_is_not_the_ask_breaks_the_rule(prob):
    field = [_o(0.10, 0.0, 0.10), _o(prob, 0.0, 0.10)]
    assert _field_is_offer_sheet(field) is False


def test_decimal_strings_from_the_database_are_handled():
    """`current_probability` is `Numeric` and arrives as Decimal, not float."""
    from decimal import Decimal

    field = [
        _o(Decimal("0.100000"), Decimal("0.0000"), Decimal("0.1000")),
        _o(Decimal("0.100000"), Decimal("0.0000"), Decimal("0.1000")),
    ]
    assert _field_is_offer_sheet(field) is True
