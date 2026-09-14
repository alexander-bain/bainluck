"""#6050 — a decomposed Polymarket sub-market price is labelled with its side.

THE DEFECT (measured on production 2026-09-14 02:45–02:52Z, master `b0b75f642`).
`GET /api/events/14638896/game-markets` — Broncos at Chiefs, an upcoming marquee
NFL game — served, inside a card headed with the matchup and nothing else:

    Broncos vs. Chiefs        Yes   43.5%
    Broncos vs. Chiefs        No    56.5%

Which team is "Yes"? Nothing on the page lets the reader recover it, and the
answer was one field away in the payload we had already fetched. The venue's own
record for that condition
(`gamma-api.polymarket.com/markets?condition_ids=0x…`, read in the same pass —
standing notice 26) reads:

    outcomes:      ["Broncos", "Chiefs"]
    outcomePrices: ["0.435", "0.565"]

Same shape on tonight's live Cowboys–Giants (`outcomes: ["Cowboys", "Giants"]`)
and on every finished game of the slate: the CLOB record for Falcons–Steelers
returns `tokens: [("Falcons", 0, False), ("Steelers", 1, True)]`. Twenty
bare-matchup markets carried it in the ±3-day window at the time of the census.

The contrast that makes this unambiguous is on the same page: the Kalshi row for
the identical question reads `Washington vs Philadelphia | Philadelphia | 1.0`.
One source names the side; the other says "No".

THIS IS Q492's DEFECT ON THE SIBLING WRITER. `_leg_label` settled it for the
PARENT writer — "``outcomes`` is the parallel array to ``outcome_prices``, so
``outcomes[0]`` is the only label that is definitionally the leg this price
belongs to" — and the decomposed sub-market writer never inherited the rule. It
named both sides positionally: `"Over"/"Under"` when the name said "o/u",
`"Yes"/"No"` otherwise.

THE CONTROLS MATTER MORE THAN THE SHIP ASSERTION. "Always use ``outcomes[i]``"
would pass the ship test and wreck the large majority of sub-markets, which are
genuine Yes/No questions whose own name asks the question ("Both Teams to
Score", "D/ST Touchdown", "Safety"). So the rescue is asserted to be
*conditional*, from both directions, and the fallback path is pinned verbatim.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from app.tasks import polymarket as poly
from app.tasks.polymarket import _sub_market_side_label

MATCHUP = "Broncos vs. Chiefs"


class _Market:
    """The one field the label helper reads, shaped like ``PolymarketMarket``."""

    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])


# ---------------------------------------------------------------------------
# The ship: a game moneyline names the two teams.
# ---------------------------------------------------------------------------


def test_the_moneyline_sides_are_labelled_with_the_two_teams():
    """Gamma condition 0x18afd…/0x…, verbatim: the sub-market's question IS the
    matchup and the sides live in ``outcomes``."""
    moneyline = _Market(outcomes=["Broncos", "Chiefs"])

    assert _sub_market_side_label(moneyline, 0, MATCHUP, "Yes") == "Broncos"
    assert _sub_market_side_label(moneyline, 1, MATCHUP, "No") == "Chiefs"


def test_the_two_sides_do_not_collapse_onto_one_label():
    """The index is load-bearing: both sides reading "Broncos" would be a worse
    card than the one we are replacing."""
    moneyline = _Market(outcomes=["Broncos", "Chiefs"])

    over = _sub_market_side_label(moneyline, 0, MATCHUP, "Yes")
    under = _sub_market_side_label(moneyline, 1, MATCHUP, "No")

    assert over != under


@pytest.mark.parametrize(
    "outcomes, expected",
    [
        # Tonight's live NFL game, verbatim.
        (["Cowboys", "Giants"], ("Cowboys", "Giants")),
        # The finished game whose CLOB record carries the winner flag.
        (["Falcons", "Steelers"], ("Falcons", "Steelers")),
        # A soccer three-way decomposed to a two-sided sub-market.
        (["Servette Geneva", "FC Thun"], ("Servette Geneva", "FC Thun")),
    ],
)
def test_production_specimens_are_labelled_from_the_venue(outcomes, expected):
    market = _Market(outcomes=outcomes)

    assert (
        _sub_market_side_label(market, 0, MATCHUP, "Yes"),
        _sub_market_side_label(market, 1, MATCHUP, "No"),
    ) == expected


def test_the_rescue_survives_whitespace_on_the_venue_token():
    assert _sub_market_side_label(_Market(["  Broncos  "]), 0, MATCHUP, "Yes") == "Broncos"


# ---------------------------------------------------------------------------
# Non-vacuity control 1 — a genuine Yes/No sub-market is untouched. This is the
# large majority of the population; "always use outcomes[i]" fails here.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sub_name",
    [
        "Denver vs Kansas City: D/ST Touchdown",
        "Denver vs Kansas City: Safety",
        "FC Thun vs. Servette Geneva: Both Teams to Score",
        "Spread: Hartford Athletic (-1.5)",
        "Anisio: Anytime Goalscorer",
    ],
)
def test_a_real_yes_no_question_keeps_yes_and_no(sub_name):
    """The venue sends ``["Yes", "No"]`` for these, and "Yes" is the correct
    label — the sub-market's own name carries the question."""
    market = _Market(outcomes=["Yes", "No"])

    assert _sub_market_side_label(market, 0, sub_name, "Yes") == "Yes"
    assert _sub_market_side_label(market, 1, sub_name, "No") == "No"


@pytest.mark.parametrize("tokens", [["yes", "no"], ["YES", "NO"], ["  Yes ", "No"]])
def test_a_yes_no_token_is_rejected_case_and_space_insensitively(tokens):
    """Trading "Yes" for "yes" is not a rescue."""
    market = _Market(outcomes=tokens)

    assert _sub_market_side_label(market, 0, MATCHUP, "Yes") == "Yes"
    assert _sub_market_side_label(market, 1, MATCHUP, "No") == "No"


# ---------------------------------------------------------------------------
# Non-vacuity control 2 — Over/Under already names its side and is never
# second-guessed, whatever the venue's token array happens to hold.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "outcomes",
    [["Over", "Under"], ["Broncos", "Chiefs"], ["Yes", "No"], []],
)
def test_an_over_under_sub_market_keeps_over_and_under(outcomes):
    market = _Market(outcomes=outcomes)
    sub_name = "Broncos vs. Chiefs O/U 48.5"

    assert _sub_market_side_label(market, 0, sub_name, "Over") == "Over"
    assert _sub_market_side_label(market, 1, sub_name, "Under") == "Under"


# ---------------------------------------------------------------------------
# Non-vacuity control 3 — degenerate venue shapes fall back rather than crash.
# This helper runs inside the hourly poll's per-event loop.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "outcomes, index",
    [
        ([], 0),
        (["Broncos"], 1),  # one-sided array, Under side asked for
        ([""], 0),
        ([None], 0),
        (["   "], 0),
    ],
)
def test_a_degenerate_outcomes_array_falls_back(outcomes, index):
    fallback = "Yes" if index == 0 else "No"

    assert _sub_market_side_label(_Market(outcomes), index, MATCHUP, fallback) == fallback


def test_a_market_with_no_outcomes_attribute_does_not_crash():
    class _Bare:
        pass

    assert _sub_market_side_label(_Bare(), 0, MATCHUP, "Yes") == "Yes"


def test_a_token_echoing_the_sub_markets_own_name_is_not_a_rescue():
    """Relabelling the side with the matchup reproduces exactly the collapse
    Q492 named — a number that names no side."""
    echoed = _Market(outcomes=[MATCHUP, "Chiefs"])

    assert _sub_market_side_label(echoed, 0, MATCHUP, "Yes") == "Yes"


# ---------------------------------------------------------------------------
# The ship must actually be WIRED. A pure function nobody calls fixes nothing,
# and BOTH sides are written by separate statements in the poll.
# ---------------------------------------------------------------------------


def _side_name_assignments() -> dict[str, ast.expr]:
    """The value expression of every ``over_name``/``under_name`` assignment in
    the decomposed sub-market writer.

    Read from the source rather than asserted in prose: the defect this file
    exists for was two hard-coded conditional expressions, so a regression is
    most likely to look like one of them coming back.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(poly._process_event_batch)))
    found: dict[str, ast.expr] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in {"over_name", "under_name"}:
                found[target.id] = node.value
    return found


def test_both_sides_are_labelled_through_the_helper():
    assignments = _side_name_assignments()

    assert set(assignments) == {"over_name", "under_name"}, (
        "the sub-market writer no longer assigns both side names; re-point this guard"
    )

    for name, value in assignments.items():
        assert isinstance(value, ast.Call), f"{name} is not a call — the hard-coded label is back"
        assert getattr(value.func, "id", None) == "_sub_market_side_label", (
            f"{name} does not route through _sub_market_side_label"
        )


def test_each_side_reads_its_own_index():
    """``over_name`` must take index 0 and ``under_name`` index 1; one wrong
    literal here silently swaps the two teams on every card."""
    assignments = _side_name_assignments()
    expected = {"over_name": 0, "under_name": 1}

    for name, index in expected.items():
        arg = assignments[name].args[1]
        assert isinstance(arg, ast.Constant) and arg.value == index, (
            f"{name} reads index {ast.dump(arg)}, expected {index}"
        )
