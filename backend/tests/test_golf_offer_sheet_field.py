"""Q446 / CERT-450 — an unaccepted offer is not a price, one outcome at a time.

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

WHAT CERT-450 CHANGED. This rule used to be `_field_is_offer_sheet`, asked of the
whole field: a field was refused only when NOT ONE competitor carried a bid. On the
138-outcome Nexo round-leader shape that meant 137 ask-only rows kept printing
because one golfer had a real bid — and the branch pinned it, in a test named
`test_one_real_bid_anywhere_saves_the_field`. That test is now
`test_one_real_bid_does_not_launder_its_neighbours_asks` and asserts the opposite.
A bid on one golfer is not evidence about another; provenance belongs to the number.

THE CONTROLS ARE STILL THE POINT. Two other open golf fields also have no bid on any
outcome — `CPKC Women's Open End of Round 3 Leader` (154 priced) and
`FM Championship End of Round 3 Leader` (144 priced) — and both must survive,
because their prices are `last_price`: real trades, on a book that has since gone
one-sided. "No bid" alone is not the rule. "This number IS an unaccepted offer" is,
and it is now asked of each number separately.
"""

import types

import pytest

from app.routes.golf import _is_placeholder_price, _price_is_unaccepted_offer


def _o(prob, bid, ask, name="Someone"):
    return types.SimpleNamespace(
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        name=name,
    )


def _offers(field):
    return [_price_is_unaccepted_offer(o) for o in field]


# --------------------------------------------------------------------------
# The specimen
# --------------------------------------------------------------------------


def test_omega_european_masters_is_all_unaccepted_offers():
    """market 59759220, verbatim. Every row goes dark, so the field renders empty
    and the tournament drops — the same end state the field rule produced."""
    field = [
        _o(0.10, 0.0, 0.10, "Andreas Halvorsen"),
        _o(0.10, 0.0, 0.10, "Adrian Meronk"),
        _o(0.10, 0.0, 0.10, "Eddie Pepperell"),
        _o(0.10, 0.0, 0.10, "Antoine Rozner"),
    ]
    assert _offers(field) == [True, True, True, True]


def test_renormalizing_it_would_have_made_it_look_more_confident():
    """Why an offer is dropped rather than rescaled.

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
# CERT-450 — the laundering
# --------------------------------------------------------------------------


def test_one_real_bid_does_not_launder_its_neighbours_asks():
    """CERT-450's BLOCK, and the inversion of the test that used to live here.

    `test_one_real_bid_anywhere_saves_the_field` asserted that this field was NOT an
    offer sheet, because one competitor carried a genuine bid — and on the real
    138-outcome Nexo shape that single bid certified 137 ask-only placeholder rows
    straight onto the page. The named ship is that readers stop seeing placeholder
    prices; keeping 137 of 138 of them was the same user-visible false-number class
    on the same page.

    Somebody bidding on the third golfer says nothing whatever about the first two.
    """
    field = [
        _o(0.10, 0.0, 0.10),
        _o(0.10, 0.0, 0.10),
        _o(0.12, 0.08, 0.14),
    ]
    assert _offers(field) == [True, True, False]


def test_the_nexo_shape_darkens_137_and_keeps_the_one_real_quote():
    """The cert's specimen at its real size: 137 ask-only rows, one genuine bid."""
    field = [_o(0.01, 0.0, 0.01) for _ in range(137)] + [_o(0.12, 0.08, 0.14)]
    flags = _offers(field)
    assert sum(flags) == 137
    assert flags[-1] is False


def test_the_survivor_is_not_rescaled_onto_the_whole_fields_sum():
    """The remainder is honest because it is UNDERSTATED, never inflated.

    `outcome_prob_sum` is taken over every priced outcome before any darkening, so
    the one survivor of a thinned field is scaled by the full field's sum. Scaling to
    the survivors instead would print a 12% quote as 100% — a fabricated certainty
    replacing a fabricated tail, which is a worse trade than the bug.
    """
    from app.routes.golf import _golf_winner_renorm_factor

    survivor, offer_each = 0.12, 0.02
    full_sum = 137 * offer_each + survivor  # 2.86 — every priced outcome, offers included
    assert full_sum > 1.5, "below the early return this rule would not engage at all"

    factor = _golf_winner_renorm_factor("Some Winner", 138, full_sum)
    assert factor is not None
    # What the route actually prints: scaled by the WHOLE field's sum.
    assert round(survivor * factor, 4) == 0.042
    # What scaling to the survivors instead would have printed: total certainty,
    # invented out of a single 12% quote. Understated beats fabricated.
    assert round(survivor * (1.0 / survivor), 4) == 1.0


# --------------------------------------------------------------------------
# The controls
# --------------------------------------------------------------------------


def test_traded_prices_with_no_bid_survive():
    """CPKC Women's Open R3 Leader / FM Championship R3 Leader.

    No bid on any outcome, but the printed number is `last_price` — a real trade —
    and so differs from the ask. These carry information and must render. This is the
    control that stops "no bid" from becoming the rule, and it holds per outcome
    exactly as it held per field.
    """
    field = [
        _o(0.05, 0.0, 0.09),
        _o(0.03, 0.0, 0.08),
        _o(0.05, 0.0, 0.11),
    ]
    assert _offers(field) == [False, False, False]


def test_a_bookless_model_outcome_is_never_an_offer():
    """DataGolf and odds_api carry no book at all — by construction, not exemption.

    Both are large uniform-looking fields of small numbers, which is exactly the
    shape a careless version of this rule would eat. With no ask there is no offer.
    """
    assert _offers([_o(0.02, None, None) for _ in range(50)]) == [False] * 50


def test_a_bookless_outcome_beside_offers_keeps_only_itself():
    """The mixed field. Under the field rule one bookless outcome rescued the two
    offers beside it; now each answers for itself and the bookless one is the only
    survivor."""
    field = [_o(0.10, 0.0, 0.10), _o(0.10, 0.0, 0.10), _o(0.10, None, None)]
    assert _offers(field) == [True, True, False]


def test_a_lone_longshot_offer_is_still_an_offer():
    """The other half of the CERT-450 inversion, stated plainly.

    The field rule needed >= 2 priced outcomes because "a single binary is not a
    field". But 2% that nobody will pay a cent for is a fabricated number whether it
    stands in a field of 138 or on its own. What darkening it costs is completeness,
    not a reading — and the callers already present these as partial lists.
    """
    assert _price_is_unaccepted_offer(_o(0.02, 0.0, 0.02)) is True


def test_an_unpriced_outcome_is_not_an_offer():
    """No number printed, nothing to be wrong about."""
    assert _price_is_unaccepted_offer(_o(None, None, None)) is False
    assert _price_is_unaccepted_offer(_o(None, 0.0, 0.10)) is False


def test_a_null_bid_counts_as_no_bid():
    """`bid IS NULL` and `bid = 0` are the same fact on a Kalshi/Polymarket book.

    This is NOT the gotcha #53 hazard that makes `_is_placeholder_price` fail open on
    an absent side. The ASK is present, so this book was read; a book we read that
    quotes an offer and reports nothing on the bid side has no bid. An outcome we
    were told nothing about at all has no ask either, and is handled above.
    """
    assert _offers([_o(0.10, None, 0.10), _o(0.10, None, 0.10)]) == [True, True]


@pytest.mark.parametrize("prob", [0.099, 0.101, 0.05])
def test_a_price_that_is_not_the_ask_is_not_an_offer(prob):
    assert _price_is_unaccepted_offer(_o(prob, 0.0, 0.10)) is False


def test_decimal_values_from_the_database_are_handled():
    """`current_probability` is `Numeric` and arrives as Decimal, not float."""
    from decimal import Decimal

    field = [
        _o(Decimal("0.100000"), Decimal("0.0000"), Decimal("0.1000")),
        _o(Decimal("0.100000"), Decimal("0.0000"), Decimal("0.1000")),
    ]
    assert _offers(field) == [True, True]


# --------------------------------------------------------------------------
# Wiring — the rule has to reach the render, not just exist
# --------------------------------------------------------------------------


def test_the_route_reaches_the_offer_rule_through_is_placeholder_price():
    """A predicate no caller asks is a predicate that changes nothing.

    Both golf render paths (`_extract_prop_market` and the winner aggregation) dark
    outcomes via `_is_placeholder_price`, so that is where the offer arm has to be
    wired for the 137 rows to actually leave the page.
    """
    assert _is_placeholder_price(_o(0.10, 0.0, 0.10), "kalshi") is True
    assert _is_placeholder_price(_o(0.10, 0.0, 0.10), "polymarket") is True
    # And the control still survives the wiring, not just the predicate.
    assert _is_placeholder_price(_o(0.05, 0.0, 0.09), "kalshi") is False


def test_the_offer_arm_only_ever_adds_a_skip():
    """`_is_placeholder_price` is monotone by construction and must stay that way:
    no outcome that rendered before may render now."""
    cases = [
        _o(0.05, 0.0, 0.09), _o(0.12, 0.08, 0.14), _o(0.02, None, None),
        _o(None, None, None), _o(0.5, 0.0, 0.10), _o(0.10, 0.0, 0.10),
    ]
    for source in ("kalshi", "polymarket", "datagolf", None):
        for o in cases:
            if not _price_is_unaccepted_offer(o):
                continue
            # Every outcome the new arm skips must be one the arm itself justifies;
            # it never rescues an outcome the old arms had already skipped.
            assert _is_placeholder_price(o, source) is True
