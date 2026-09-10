"""#4629 — an outcome named with the WHOLE matchup is not a home-side moneyline.

Two live UFC cards printed 50% / 50%, an orange "Coin flip" chip and the reason
"Virtually even" over fights whose own books were 0.17/0.83 and 0.75/0.26.

The 0.5 was not ingested. Every stored Polymarket outcome on both events was
tight and liquid — bid .16 / ask .18 and bid .74 / ask .76 — and none of them
was anywhere near 0.5. The value was COMPUTED, and the arithmetic is the tell:

    (p + (1 - p)) / 2 == 0.5,  exactly, for every p

`compute_source_home_probability` devigs a two-market group by averaging the
speaking market's home reading with its sibling's. When those two readings are
complements of each other, the mean is exactly 0.5 — so a confident coin flip
on the page is the signature of an INVERTED PAIR, never of an even market.

The inversion enters in `find_moneyline_outcome`. Polymarket publishes the
match twice: an `unshaped` row whose single outcome is named with the full
`"A vs. B"` string, and a `container_member` row with `Yes`/`No`. Both carry the
same market name, so both parse the same matchup, and `yes_team` is the
first-named participant.

* The `Yes`/`No` row reaches the generic last resort and is oriented from the
  matchup parse — correct.
* The full-matchup row does not, because `_fuzzy_team_match` is a substring
  test and `"Tai Tuivasa vs. Robelis Despaigne"` CONTAINS the home team's name.
  It is classified as a home-side outcome and returned with `yes_is_home=True`,
  which reads the first-named participant's price as the home team's.

The module already has a purpose-built branch for this exact shape — "Fallback:
outcome name is the full matchup (Polymarket pattern)" — and it orients from
the matchup, correctly. It was simply unreachable: the substring classifier
above it claimed the outcome and returned first.

So this is a documented defense bypassed by another reading, not a missing one.
"""

from types import SimpleNamespace

import pytest

from app.utils.prediction_market_matching import (
    extract_matchup,
    find_moneyline_outcome,
)


def _outcome(name, prob, rank=1):
    return SimpleNamespace(name=name, current_probability=prob, rank=rank)


def _home_prob(outcomes, market_name, home, away):
    """The home probability this market asserts, or None."""
    matchup = extract_matchup(market_name)
    assert matchup is not None, f"matchup did not parse from {market_name!r}"
    found = find_moneyline_outcome(outcomes, matchup, home, away)
    if found is None:
        return None
    outcome, yes_is_home = found
    yes = float(outcome.current_probability)
    return yes if yes_is_home else 1.0 - yes


# The two live specimens, verbatim from production 2026-09-10 03:45Z.
DESPAIGNE = dict(
    market_name="UFC 331: Tai Tuivasa vs. Robelis Despaigne (Heavyweight, Prelims)",
    home="Robelis Despaigne",
    away="Tai Tuivasa",
    yes_price=0.17,
    no_price=0.83,
)
TSARUKYAN = dict(
    market_name="UFC 331: Arman Tsarukyan vs. Mauricio Ruffy (Lightweight, Main Card)",
    home="Mauricio Ruffy",
    away="Arman Tsarukyan",
    yes_price=0.75,
    no_price=0.26,
)
SPECIMENS = [
    pytest.param(DESPAIGNE, id="15190802-despaigne-tuivasa"),
    pytest.param(TSARUKYAN, id="15190830-ruffy-tsarukyan"),
]


@pytest.mark.parametrize("spec", SPECIMENS)
def test_the_yes_no_row_is_oriented_from_the_matchup(spec):
    """The control. This half was always right and must stay right."""
    got = _home_prob(
        [_outcome("Yes", spec["yes_price"], 1), _outcome("No", spec["no_price"], 2)],
        spec["market_name"], spec["home"], spec["away"],
    )
    # The matchup names the AWAY fighter first on both specimens, so `Yes` is
    # the away side and the home reading is its complement.
    assert got == pytest.approx(1.0 - spec["yes_price"])


@pytest.mark.parametrize("spec", SPECIMENS)
def test_a_full_matchup_outcome_is_not_read_as_the_home_side(spec):
    """THE DEFECT. A `"A vs. B"` outcome name contains BOTH names, so the
    substring classifier called it a home-side moneyline and handed back the
    first-named participant's price as the home team's."""
    matchup_name = spec["market_name"].split(": ", 1)[1].split(" (")[0]
    got = _home_prob(
        [_outcome(matchup_name, spec["yes_price"])],
        spec["market_name"], spec["home"], spec["away"],
    )
    assert got == pytest.approx(1.0 - spec["yes_price"]), (
        "the full-matchup outcome was oriented as the HOME side; it carries "
        "the first-named participant's price (#4629)"
    )


@pytest.mark.parametrize("spec", SPECIMENS)
def test_the_two_rows_agree_so_the_devig_cannot_average_to_a_coin_flip(spec):
    """The user-visible claim, stated as arithmetic.

    This is the assertion that would have caught #4629 on the page: the two
    rows Polymarket publishes for one fight must not be complements of each
    other, because `compute_source_home_probability` averages them and the mean
    of `p` and `1 - p` is exactly 0.5 — printed to a reader as "Coin flip ·
    Virtually even" over a book quoting 84/16.
    """
    matchup_name = spec["market_name"].split(": ", 1)[1].split(" (")[0]
    unshaped = _home_prob(
        [_outcome(matchup_name, spec["yes_price"])],
        spec["market_name"], spec["home"], spec["away"],
    )
    container = _home_prob(
        [_outcome("Yes", spec["yes_price"], 1), _outcome("No", spec["no_price"], 2)],
        spec["market_name"], spec["home"], spec["away"],
    )

    assert unshaped is not None and container is not None
    assert unshaped == pytest.approx(container), (
        f"the two rows disagree ({unshaped} vs {container}) — their mean is "
        f"{(unshaped + container) / 2}, which is what the card printed"
    )
    assert (unshaped + container) / 2 != pytest.approx(0.5), (
        "the devig produced exactly 0.5, the arithmetic signature of averaging "
        "a reading with its own complement (#4629)"
    )


def test_a_single_sided_outcome_name_is_still_read_as_that_side():
    """The guard on the fix's blast radius.

    The skip must only reach names that match BOTH teams. Kalshi's per-team
    pair names each outcome after ONE team, and those must keep resolving
    exactly as they did.
    """
    got = _home_prob(
        [_outcome("Boston Celtics", 0.62, 1), _outcome("Philadelphia 76ers", 0.38, 2)],
        "Boston Celtics vs. Philadelphia 76ers",
        "Boston Celtics",
        "Philadelphia 76ers",
    )
    assert got == pytest.approx(0.62)
