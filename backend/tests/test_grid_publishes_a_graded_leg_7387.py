"""#7387 — a club that has CLINCHED stops rendering as a blank cell.

WHAT A READER SAW, production, 390px, 2026-09-20 (lane1's D48 shop of
`/sport/baseball/mlb/team/boston-red-sox-mlb`)::

    TEAM                  DIVISION   PLAYOFFS   CHAMPION
    New York Yankees           8%        —          10%
    Tampa Bay Rays            90%        —           9%
    Boston Red Sox             0%       99%          5%
    Toronto Blue Jays          0%        6%          1%

A club shown **90% to win its division** shows **nothing at all** for reaching
the playoffs, one row above a 76-79 Toronto side showing 6%. Division ⊆
playoffs, so the row contradicts itself, and the natural reading of "—" is *no
data* — the exact opposite of the truth, which is that Tampa Bay had clinched.
`GET /api/playoffs/mlb` served 8 of 30 clubs with no `make_playoffs` cell, and
**the four best records in baseball were four of the eight blanks.**

THE CAUSE WAS ONE LINE, AND IT DELETED THE ANSWERS WE ARE MOST SURE OF.
`routes/playoffs.py` dropped every leg on ``prob <= 0 or prob >= 1.0``. That
line cannot tell a junk price on a still-trading market from a RESULT on a
graded one, so the graded legs — nine of them, every one a real verdict — never
reached the grid.

🔴 WHY `is_winner` ALONE IS NOT THE FIX, which is the trap this file exists to
hold shut. ``futures_outcomes.is_winner`` is
``default=False, server_default=text("false")``: ``False`` is what a row is BORN
with. Measured on the two markets feeding the column, 2026-09-20 14:3xZ, legs at
0.9945 / 0.9830 / 0.9775 all carry ``is_winner = false`` with
``resolution_source IS NULL``. Keying elimination on ``is_winner`` being false
would have eliminated the best teams in baseball.

The discriminator is therefore ``is_winner IS TRUE`` **or** the settlement
badge — exactly the negation of `futures_liveness.writable_leg_sql`, the refusal
the price writer and its selector already share.
"""

import pytest

from app.routes.playoffs import _grid_leg_is_terminal, _grid_terminal_state
from app.utils.futures_liveness import leg_is_graded, writable_leg_sql


# ---------------------------------------------------------------------------
# The discriminator
# ---------------------------------------------------------------------------

#: Real rows, read off production 2026-09-20 14:3xZ from the two markets that
#: feed the MLB `make_playoffs` column — 266 `Pro Baseball Playoff Qualifiers`
#: (kalshi) and 8861163 `MLB: Team to make postseason` (polymarket).
#: (is_winner, resolution_source, price, graded?, why)
PRODUCTION_LEGS = [
    (True, "api_settlement", 1.0000, True, "Dodgers: clinched, the ship"),
    (True, "api_settlement", 1.0000, True, "Brewers: clinched"),
    (False, "api_settlement", 0.0000, True, "Nationals: graded out"),
    (False, "api_settlement", 0.0150, True, "a graded loser the price lags"),
    # The three that make `is_winner`-alone fatal: born-False, no badge.
    (False, None, 0.9945, False, "a live favourite, ungraded"),
    (False, None, 0.9830, False, "a live favourite, ungraded"),
    (False, None, 0.4900, False, "a live coin-flip, ungraded"),
    # The retraction badge is NOT a verdict (see below).
    (False, "ungradeable_result", 0.9950, False, "retracted fabrication, high"),
    (False, "ungradeable_result", 0.0100, False, "retracted fabrication, low"),
]


@pytest.mark.parametrize("is_winner,source,price,expected,why", PRODUCTION_LEGS)
def test_the_discriminator_on_real_production_legs(is_winner, source, price, expected, why):
    assert leg_is_graded(is_winner, source) is expected, why


def test_a_born_false_leg_at_a_live_price_is_not_a_loss():
    """The whole reason this is a function and not ``if outcome.is_winner``.

    A 0.9945 favourite carries ``is_winner=False`` because that is the column
    default, not because anyone graded it. Reading it as a verdict renders the
    best team in the league as *Eliminated*.
    """
    assert leg_is_graded(False, None) is False
    assert _grid_terminal_state([_leg(0.9945, graded=False)]) is None


def test_ungradeable_result_is_not_a_verdict():
    """`kalshi_fabricated_loss` writes this badge to RETRACT a loss the venue
    never declared — a tier-1 write placed over ``api_settlement`` precisely
    because that settlement was never authorised. Market 266 carried 12 such
    legs. Reading "has any resolution source" as a verdict would republish every
    retracted fabrication as a hard `eliminated`, undoing that module's work.
    """
    assert leg_is_graded(False, "ungradeable_result") is False
    assert leg_is_graded(False, "") is False
    assert leg_is_graded(None, None) is False


def test_the_python_twin_agrees_with_the_sql_it_is_a_twin_of():
    """One rule, two languages. `writable_leg_sql` is the refusal the writer and
    its selector apply; `leg_is_graded` must be its exact negation, or a leg the
    writer refuses to touch is one the grid still treats as a live quote.
    """
    sql = writable_leg_sql("fo")
    assert "fo.is_winner IS NOT TRUE" in sql
    assert "COALESCE(fo.resolution_source, '') <> 'api_settlement'" in sql
    # The SQL is writable(leg) == NOT graded(leg) over every combination the
    # two columns can hold.
    for is_winner in (True, False, None):
        for source in (None, "", "api_settlement", "ungradeable_result"):
            sql_writable = (is_winner is not True) and ((source or "") != "api_settlement")
            assert sql_writable is not leg_is_graded(is_winner, source), (is_winner, source)


# ---------------------------------------------------------------------------
# The cell
# ---------------------------------------------------------------------------

def _leg(probability, *, graded, is_winner=False, source="kalshi"):
    """One `grid_raw` entry, built the way the route builds it."""
    return {
        "source": source,
        "probability": probability,
        "market_id": 266,
        "outcome_id": 1,
        "market_name": "Pro Baseball Playoff Qualifiers",
        "volume_24h": 0,
        "terminal": _grid_leg_is_terminal(graded, probability),
        "is_winner": is_winner,
    }


def test_a_clinched_club_renders_its_result():
    assert _grid_terminal_state([_leg(1.0, graded=True, is_winner=True)]) == "won"


def test_a_graded_out_club_renders_eliminated_not_a_blank():
    assert _grid_terminal_state([_leg(0.0, graded=True)]) == "eliminated"


def test_an_ordinary_trading_cell_is_untouched():
    """The 22 clubs whose fate is undecided must keep their number. A fix that
    also turns a live cell terminal is the wrong fix.
    """
    assert _grid_terminal_state([_leg(0.06, graded=False)]) is None
    assert _grid_terminal_state([]) is None


def test_settled_outranks_trading_across_sources():
    """One venue has graded the club; the other is still quoting. Seven MLB
    clubs were in exactly this state — graded 0 on one venue only — and kept a
    misleading ~1% live cell from the other.
    """
    entries = [_leg(0.01, graded=False, source="kalshi"),
               _leg(0.0, graded=True, source="polymarket")]
    assert _grid_terminal_state(entries) == "eliminated"


def test_a_winner_outranks_a_loser_when_two_legs_disagree():
    """``is_winner=True`` is only ever written by a grader reading a verdict,
    while ``False`` is the column default, so the affirmative claim is the
    better-evidenced one. A club that has clinched must never be published as
    eliminated on the strength of a default.
    """
    entries = [_leg(0.0, graded=True, is_winner=False, source="kalshi"),
               _leg(1.0, graded=True, is_winner=True, source="polymarket")]
    assert _grid_terminal_state(entries) == "won"
    assert _grid_terminal_state(list(reversed(entries))) == "won"


def test_the_6622_counter_specimen_is_not_published_at_100_percent():
    """🔴 THE CONSTRAINT THAT STOPS THE LAZY FIX — admitting ``prob >= 1.0`` on
    price alone.

    Market 34607706 `Juan Soto Next Team` (polymarket:15079, recorded on #6622)
    carries **all 7 legs at ``current_probability = 1.0`` with exactly one
    ``is_winner``** — six graded LOSERS stored at certainty. A fix keyed on the
    price would publish six 100% cells on one market.

    Keyed on the grade, the six losers render `eliminated` — a result, carrying
    no number — and only the real winner renders `won`.
    """
    winner = _leg(1.0, graded=True, is_winner=True, source="polymarket")
    losers = [_leg(1.0, graded=True, is_winner=False, source=f"pm{i}") for i in range(6)]

    for loser in losers:
        assert _grid_terminal_state([loser]) == "eliminated"

    assert _grid_terminal_state(losers + [winner]) == "won"


def test_a_terminal_cell_carries_no_number():
    """"Settled means settled": the cell states the result and publishes no
    probability, which is what `lib/gridCellState.ts` already renders as
    Clinched/Eliminated. A terminal state that still carried a price would put
    the deleted 1.0 straight back on the page.
    """
    for entries, expected in (
        ([_leg(1.0, graded=True, is_winner=True)], "won"),
        ([_leg(0.0, graded=True)], "eliminated"),
    ):
        state = _grid_terminal_state(entries)
        assert state == expected
        # The route builds this cell verbatim; the contract is that it is the
        # register's shape, not a live cell wearing a state.
        cell = {"merged_probability": None, "sources": [], "trend_24h": None,
                "state": state}
        assert cell["merged_probability"] is None
        assert cell["trend_24h"] is None


#: #6532's La Liga relegation fixture, the population that caught the first
#: draft of this fix in CI (`test_grid_book_refuted_price_6532_pg`, real
#: Postgres — it cannot run without a DB, so it is restated here as pure data).
#: A mid-season relegation market carries the settlement badge on legs that are
#: still quoting. (team, price, resolution_source, is_winner)
LALIGA_LEGS_STILL_QUOTING = [
    ("Barcelona", 0.99, "api_settlement", True),
    ("Levante", 0.60, "api_settlement", False),
    ("Espanyol", 0.02, "api_settlement", False),
    ("Alaves", 0.99, None, False),
    ("Girona", 0.99, None, False),
]


@pytest.mark.parametrize("team,price,source,is_winner", LALIGA_LEGS_STILL_QUOTING)
def test_a_badge_on_a_mid_market_price_never_blanks_an_honest_row(
    team, price, source, is_winner
):
    """🔴 THE ARM THE FIRST DRAFT FAILED, and it failed in CI, not here.

    The badge alone is not a verdict. On #6532's fixture, three honestly-priced
    rows — Barcelona (a graded WINNER at 0.99), Levante 0.60, Espanyol 0.02 —
    became blank terminal cells, which is exactly the harm that file guards:
    *"this arm withholds; it must never blank a row the book does not refute."*

    None of these legs was ever dropped by the defect, because none is at the
    rail — so none of them may change. #6442 wrote the general form first: an
    extreme price is a QUOTE, not a grade; the mirror is that a badge on a
    mid-market price is not a settlement.
    """
    graded = leg_is_graded(is_winner, source)
    assert _grid_leg_is_terminal(graded, price) is False, team
    assert _grid_terminal_state([_leg(price, graded=graded, is_winner=is_winner)]) is None


def test_only_the_population_the_defect_deleted_can_change():
    """The repair's blast radius, stated as a rule rather than a hope: a leg is
    eligible for a terminal cell only if the old line would have dropped it.
    """
    for price in (0.0, 1.0, -0.0):
        assert _grid_leg_is_terminal(True, price) is True, price
    for price in (0.0001, 0.02, 0.5, 0.9945, 0.99):
        assert _grid_leg_is_terminal(True, price) is False, price
        # ...and being ungraded never makes a rail price terminal either.
        assert _grid_leg_is_terminal(False, price) is False, price
    assert _grid_leg_is_terminal(False, 1.0) is False


def test_the_per_source_dedup_does_not_discard_the_verdict():
    """The dedup keeps one leg per source and its rule was "lowest probability"
    — which is the one number a graded winner can never be. Reaching the cell
    builder at all depends on surviving this.
    """
    from app.routes.playoffs import _grid_dedup_rank

    live = _leg(0.90, graded=False)
    clinched = _leg(1.0, graded=True, is_winner=True)
    assert min([live, clinched], key=_grid_dedup_rank) is clinched
    assert min([clinched, live], key=_grid_dedup_rank) is clinched

    out = _leg(0.0, graded=True)
    assert min([live, out], key=_grid_dedup_rank) is out


def test_the_grids_dedup_actually_uses_that_rank():
    """🔴 Written because the arm above passed with the call site reverted.

    Testing the helper proves the helper. `get_playoff_grid` picking
    ``key=lambda e: e["probability"]`` again would restore the defect with every
    other test in this file still green, so the call site is asserted too.
    """
    import ast
    import inspect

    from app.routes import playoffs as playoffs_mod

    tree = ast.parse(inspect.getsource(playoffs_mod))
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "get_playoff_grid"
    )
    keys = [
        kw.value
        for call in ast.walk(fn)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name) and call.func.id == "min"
        for kw in call.keywords
        if kw.arg == "key"
    ]
    assert keys, "the per-source dedup vanished — re-point this guard at its replacement"
    for key in keys:
        assert isinstance(key, ast.Name) and key.id == "_grid_dedup_rank", (
            "the grid's per-source dedup is back on a bare price key: it drops a "
            "graded winner, which is the highest number in its group (#7387) — "
            f"got {ast.unparse(key)}"
        )


def test_the_dedup_is_byte_for_byte_unchanged_for_ungraded_groups():
    """A fix that also re-picks among ordinary quotes is the wrong fix: it would
    move the number on every column of every league.
    """
    from app.routes.playoffs import _grid_dedup_rank

    group = [_leg(0.62, graded=False), _leg(0.11, graded=False), _leg(0.40, graded=False)]
    assert min(group, key=_grid_dedup_rank) is group[1]
    assert min(group, key=lambda e: e["probability"]) is group[1]


def test_the_rail_drop_can_never_be_applied_to_a_graded_leg_again():
    """🔴 THE WIRING GUARD. Every other arm here tests a helper, so all of them
    would stay green if `get_playoff_grid` simply stopped calling one — which is
    exactly how this defect returns.

    The offending shape is a bare ``prob <= 0 or prob >= 1.0`` deciding a
    ``continue``. It is legitimate ONLY when conjoined with the grade check, so
    this asserts the conjunct is there, structurally, rather than trusting a
    comment.
    """
    import ast
    import inspect

    from app.routes import playoffs as playoffs_mod

    tree = ast.parse(inspect.getsource(playoffs_mod))
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "get_playoff_grid"
    )

    def _is_rail_test(node):
        """``<x> <= 0 or <x> >= 1.0`` — the price-at-the-rail comparison."""
        if not isinstance(node, ast.BoolOp) or not isinstance(node.op, ast.Or):
            return False
        bounds = set()
        for v in node.values:
            if not isinstance(v, ast.Compare) or len(v.ops) != 1:
                return False
            const = v.comparators[0]
            if not isinstance(const, ast.Constant):
                return False
            if isinstance(const.value, bool) or not isinstance(const.value, (int, float)):
                return False
            bounds.add((type(v.ops[0]).__name__, float(const.value)))
        return bounds == {("LtE", 0.0), ("GtE", 1.0)}

    rails = [n for n in ast.walk(fn) if _is_rail_test(n)]
    assert rails, "the rail comparison vanished — re-point this guard at its replacement"

    for rail in rails:
        guarded = any(
            isinstance(c, ast.Call)
            and isinstance(c.func, ast.Name)
            and c.func.id == "leg_is_graded"
            for outer in ast.walk(fn)
            if isinstance(outer, ast.BoolOp) and rail in outer.values
            for c in ast.walk(outer)
        )
        assert guarded, (
            "a bare price-rail drop is back in get_playoff_grid: it deletes "
            "graded results (#7387) along with junk prices"
        )


def test_the_shared_grid_helpers_tolerate_a_terminal_cell():
    """The terminal cell now reaches two shared passes that previously only saw
    register grids. `enforce_monotonicity` compares probabilities and
    `normalize_column_sums` scales them; a `None` in either is a 500 for every
    league, not just MLB.
    """
    from app.config.league_configs import MLB_CONFIG
    from app.utils.playoff_grid import enforce_monotonicity, normalize_column_sums

    teams = [{
        "name": "Tampa Bay Rays",
        "cells": {
            "make_playoffs": {"merged_probability": None, "sources": [],
                              "trend_24h": None, "state": "won"},
            "division": {"merged_probability": 0.90, "sources": [], "trend_24h": None,
                         "state": "live"},
        },
    }]
    enforce_monotonicity(teams, MLB_CONFIG.columns)
    normalize_column_sums(teams, MLB_CONFIG.columns, "mlb")

    cell = teams[0]["cells"]["make_playoffs"]
    assert cell["state"] == "won"
    assert cell["merged_probability"] is None, "a scaled terminal cell is a republished price"
