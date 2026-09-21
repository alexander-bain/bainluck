"""#6739 — the single-market Polymarket writer names its side instead of "Yes".

THE DEFECT (measured on production 2026-09-19, master `2174003b3`).

A Polymarket event carrying exactly ONE market falls to the last branch of
:func:`~app.tasks.polymarket._parent_outcome_data`, which hardcoded
``"name": "Yes"``. That is right for a genuine binary question and wrong for a
game whose venue listing holds only the moneyline — those arrive here too, with
``question`` set to the matchup and the two sides in ``outcomes``.

Measured over 240 stored single-leg rows named "Yes" (their condition ids read
back against the venue itself — standing notice 26 —
``gamma-api.polymarket.com/markets?condition_ids=…``, both ``closed=false`` and
``closed=true`` because the default read silently drops settled rows):

    ==================================================  ===
    venue names the two sides (``["Jukurit Mikkeli",
    "Vaasan Sport"]``) — the leg is mislabelled "Yes"    223
    venue outcomes really are ``["Yes","No"]``            17
    ==================================================  ===

The reader-visible cost has two halves. Live, a card under a matchup heading
reads "Yes 62%" — 62% of *what*? And once the match settles, the graded leg is
still called "Yes", so ``venue_settlement._names_a_participant`` cannot orient
it and the page draws a bare "Settled" chip over a win-probability hero with no
winner named: **32 such events** on 2026-09-19, arriving at ~9/day.

THIS IS #6050's DEFECT ON THE THIRD WRITER. ``_leg_label`` settled it for the
parent writer (Q492) and ``_sub_market_side_label`` for the decomposed
sub-market writer (#6050) — "``outcomes`` is the parallel array to
``outcome_prices``, so ``outcomes[index]`` is definitionally the side this price
belongs to". This branch never inherited the rule. It therefore CALLS the #6050
helper rather than growing a third label rule (#1951: one classifier, never a
second copy), and a guard below fails the build if it ever grows one.

🔴 THE CONTROLS MATTER MORE THAN THE SHIP ASSERTION, for the same reason they
did on #6050. "Always use ``outcomes[0]``" passes the ship test and renames
every genuine Yes/No question — the 17 above, and the whole politics/econ/crypto
single-market population behind them. So the rescue is asserted to be
*conditional*, from both directions, and the "Yes" fallback is pinned verbatim.

🔴 AND IT IS NOT ``_leg_label``, WHICH WOULD HAVE BEEN THE OBVIOUS REUSE.
``_leg_label`` falls back to ``_extract_outcome_name(question, title)``, whose
"short enough, use it directly" arm would rename a genuine binary question leg
to a fragment of its own question. That is tested below on a real-shaped row, so
the choice between the two helpers is pinned rather than remembered.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from app.services.polymarket_api import PolymarketEvent, PolymarketMarket
from app.tasks.polymarket import _parent_outcome_data


def _single_market_event(
    *,
    title: str,
    question: str,
    outcomes: list[str],
    prices: list[float],
    group_item_title: str | None = None,
) -> PolymarketEvent:
    """One event, one market — the shape that reaches the last branch.

    Built from the real pydantic models rather than a stub so a field this
    branch reads cannot drift out from under the test.
    """
    return PolymarketEvent(
        id="966542",
        title=title,
        markets=[
            PolymarketMarket(
                condition_id="0x7e6cf23d5a4d9419368610b2489da98ce641a668f3218c7f006843721bdd91d0",
                question=question,
                outcomes=outcomes,
                outcome_prices=prices,
                group_item_title=group_item_title,
                best_bid=0.60,
                best_ask=0.64,
                last_trade_price=0.62,
            )
        ],
    )


# ---------------------------------------------------------------------------
# The ship: a one-market game moneyline names the side its price belongs to.
# ---------------------------------------------------------------------------


def test_the_single_moneyline_leg_is_labelled_with_the_winning_side():
    """Gamma condition 0x7e6cf…, verbatim (read 2026-09-19): the question IS the
    matchup and the sides live in ``outcomes``. Event 15304802 on our side stored
    that leg as "Yes" and its settled page named no winner."""
    event = _single_market_event(
        title="Jukurit Mikkeli vs. Vaasan Sport",
        question="Jukurit Mikkeli vs. Vaasan Sport",
        outcomes=["Jukurit Mikkeli", "Vaasan Sport"],
        prices=[1.0, 0.0],
    )

    rows = _parent_outcome_data(event)

    assert len(rows) == 1
    assert rows[0]["name"] == "Jukurit Mikkeli"


def test_the_label_is_the_side_the_price_belongs_to_not_the_first_named_team():
    """The warrant is index-parallelism, not word order, so the test pins it on a
    payload where the two differ: ``outcomes[0]`` is the AWAY side here.

    A positional rule ("Yes" means the first team in the title) would answer
    "Alvark Tokyo" and be wrong about which number it just labelled.
    """
    event = _single_market_event(
        title="Alvark Tokyo vs. Ryukyu Golden Kings",
        question="Alvark Tokyo vs. Ryukyu Golden Kings",
        outcomes=["Ryukyu Golden Kings", "Alvark Tokyo"],
        prices=[0.62, 0.38],
    )

    rows = _parent_outcome_data(event)

    assert rows[0]["name"] == "Ryukyu Golden Kings"


def test_the_competition_prefix_is_not_carried_into_the_label():
    """Verbatim from the venue read: 46 of the 223 wear a tournament prefix.

    The venue's own ``outcomes[0]`` is the clean side name, which is the whole
    reason to take it rather than to split the question on " vs ".
    """
    event = _single_market_event(
        title="Davis Cup: Jurij Rodionov vs. Zizou Bergs",
        question="Davis Cup: Jurij Rodionov vs. Zizou Bergs",
        outcomes=["Jurij Rodionov", "Zizou Bergs"],
        prices=[0.55, 0.45],
    )

    rows = _parent_outcome_data(event)

    assert rows[0]["name"] == "Jurij Rodionov"
    assert "Davis Cup" not in rows[0]["name"]


# ---------------------------------------------------------------------------
# The controls: every shape that must stay byte-identical.
# ---------------------------------------------------------------------------


def test_a_genuine_yes_no_question_keeps_yes():
    """17 of the 240 measured rows, and the entire non-sports single-market
    population behind them. The venue says ``["Yes","No"]``; there is no side to
    name and the fallback must survive."""
    event = _single_market_event(
        title="Will the Fed cut rates in October?",
        question="Will the Fed cut rates in October?",
        outcomes=["Yes", "No"],
        prices=[0.71, 0.29],
    )

    rows = _parent_outcome_data(event)

    assert rows[0]["name"] == "Yes"


@pytest.mark.parametrize(
    "outcomes",
    [
        pytest.param([], id="outcomes-absent"),
        pytest.param(["", "No"], id="token-blank"),
        pytest.param(["   ", "No"], id="token-whitespace"),
        pytest.param(["yes", "no"], id="token-lowercase-yes"),
        pytest.param(["NO", "YES"], id="token-uppercase-no"),
    ],
)
def test_every_degenerate_venue_payload_keeps_yes(outcomes):
    """A malformed payload must never be able to invent a label. This is the
    direction that matters: the rescue is allowed to fail, never to guess."""
    event = _single_market_event(
        title="Will the Fed cut rates in October?",
        question="Will the Fed cut rates in October?",
        outcomes=outcomes,
        prices=[0.71, 0.29],
    )

    rows = _parent_outcome_data(event)

    assert rows[0]["name"] == "Yes"


def test_a_token_echoing_the_question_keeps_yes():
    """Relabelling a leg with its own market's name reproduces the collapse Q492
    exists to undo — "89.5% of what?" — so it is refused rather than served."""
    event = _single_market_event(
        title="Jukurit Mikkeli vs. Vaasan Sport",
        question="Jukurit Mikkeli vs. Vaasan Sport",
        outcomes=["Jukurit Mikkeli vs. Vaasan Sport", "No"],
        prices=[0.5, 0.5],
    )

    rows = _parent_outcome_data(event)

    assert rows[0]["name"] == "Yes"


def test_nothing_but_the_name_changed_on_a_rescued_row():
    """The claim is "a label moved", not "a price moved". Every other key this
    branch emits is asserted, because a pricing change wearing a naming change's
    clothes is the failure that would not show up on the page until it settled.

    CERT-3202 added one key, ``market`` — a reference to the sub-market the leg
    was priced FROM, so the parent-field writers can ask whether THIS child has
    settled rather than only whether its parent has. It is provenance, not a
    priced value, so it is asserted by identity and excluded from the value
    comparison. The KEY SET is asserted as well, which makes this guard
    strictly stronger than the bare equality it replaces: a new priced key
    cannot enter through either half.
    """
    event = _single_market_event(
        title="Jukurit Mikkeli vs. Vaasan Sport",
        question="Jukurit Mikkeli vs. Vaasan Sport",
        outcomes=["Jukurit Mikkeli", "Vaasan Sport"],
        prices=[0.62, 0.38],
    )

    rows = _parent_outcome_data(event)

    assert rows[0]["market"] is event.markets[0], (
        "the carried provenance is not the market this leg was priced from"
    )
    assert set(rows[0]) == {
        "external_id",
        "name",
        "prob",
        "yes_bid",
        "yes_ask",
        "last_price",
        "market",
    }, "this branch emits a key that is neither priced above nor provenance"
    assert {k: v for k, v in rows[0].items() if k != "market"} == {
        "external_id": "0x7e6cf23d5a4d9419368610b2489da98ce641a668f3218c7f006843721bdd91d0",
        "name": "Jukurit Mikkeli",
        "prob": 0.62,
        "yes_bid": 0.60,
        "yes_ask": 0.64,
        "last_price": 0.62,
    }


def test_an_informative_group_item_title_is_still_not_consulted_here():
    """This branch has never read ``groupItemTitle`` and still does not.

    The helper keys on ``outcomes[0]`` alone, so a market carrying both keeps the
    venue's side name; pinning it stops a later "while we're here" edit from
    quietly turning this branch into ``_leg_label``.
    """
    event = _single_market_event(
        title="Jukurit Mikkeli vs. Vaasan Sport",
        question="Jukurit Mikkeli vs. Vaasan Sport",
        outcomes=["Jukurit Mikkeli", "Vaasan Sport"],
        prices=[0.62, 0.38],
        group_item_title="Moneyline",
    )

    rows = _parent_outcome_data(event)

    assert rows[0]["name"] == "Jukurit Mikkeli"


def test_leg_label_would_have_renamed_a_genuine_binary_question():
    """Why the reuse is ``_sub_market_side_label`` and not ``_leg_label``.

    ``_leg_label`` is the parent writer's helper and falls back to
    ``_extract_outcome_name``, which for a question that is not a matchup returns
    something OTHER than "Yes" — so reusing it here would rename the entire
    genuine-binary population. Asserted rather than remembered.
    """
    from app.tasks.polymarket import _leg_label

    market = PolymarketMarket(
        condition_id="0xdeadbeef",
        question="Will the Fed cut rates in October?",
        outcomes=["Yes", "No"],
        outcome_prices=[0.71, 0.29],
    )

    assert _leg_label(market, "Will the Fed cut rates in October?") != "Yes"


# ---------------------------------------------------------------------------
# The structural guard: no third label rule, ever.
# ---------------------------------------------------------------------------


def test_the_single_market_branch_grows_no_label_rule_of_its_own():
    """#1951. The branch may CALL the shared helper and may not re-implement it.

    A matchup-splitting rule here could not tell which of X and Y the price
    belongs to — the exact shortcut Q499's drain refuses in its own docstring —
    so the failure mode is a confident wrong winner, not an ugly label.
    """
    source = textwrap.dedent(inspect.getsource(_parent_outcome_data))
    tree = ast.parse(source)

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_sub_market_side_label" in called

    # No splitting of a name on the matchup grammar anywhere in the function.
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert " vs" not in node.value.lower(), (
                f"matchup grammar {node.value!r} in _parent_outcome_data: "
                "derive the side from outcomes[index], never from the name"
            )
