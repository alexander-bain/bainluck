"""#8237 — a one-winner field with WITHHELD legs is not divided by what survives.

#8224 gave `_feed_display_scale` the detail page's overround CEILING and closed on
it. But `normalize_display_probs` refuses a one-winner field for two independent
reasons and the ceiling is the second: #7103's ``field_complete=False`` says a
field with withheld members is not a proved-complete distribution, so the sum of
the legs that survive is not a divisor. The card never had that clause.

WHAT A READER SAW, measured on production 2026-09-23 14:20Z on v4970 — the release
that carries #8224 — page read from `/api/futures/{id}`:

    52755536  Who will host the 2031 Pro Football Championship?   `New Orleans`
        card  9.4%    page  13%     <- 3.6 points apart, live today
    2417016   Pro Baseball Championship Series Matchup  `Tampa Bay vs Los Angeles`
        card  9.3%    page  12.0%

🔴 THE CEILING CANNOT EXPLAIN EITHER, and that is why this suite exists rather
than a wider band. `52755536`'s priced legs sum to 1.3800 — BELOW `_FIELD_SUM_MAX`
— so a page obeying only the ceiling would have squeezed New Orleans to 0.0942 and
agreed with the card. It prints 0.13. Only the withheld gate returns raw here.

🔴 AND THE DROP IS WHAT PUTS THE FIELD IN THE BAND. The market stores 26 legs
summing 1.7900, which is ABOVE the ceiling and already agrees. #7632 removes the
seven legs the page refuses (0.41 of mass) and the nineteen survivors sum to
1.3800, inside the squeeze band. `TestTheDropIsWhatCreatesTheDefect` pins that,
because a fixture that did not actually reach the band would pass on a function
that does nothing.

Every row below is the row production served, read from market 52755536 by
`db-query` (stored price and book) and `/api/futures/52755536` (which of them the
page refuses), never invented.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.routes.feed import (
    _feed_display_scale,
    _field_has_withheld_legs,
    _normalize_feed_probabilities,
)

# Market 52755536 as production stored it on 2026-09-23: (id, name, stored prob).
# The seven the detail page refuses are listed second and carry `withheld=True`;
# `/api/futures/52755536` serves each of them a null `probability` and counts them
# in `prices_withheld: 7`.
HOST_2031: tuple[tuple[int, str, float, bool], ...] = (
    (198631345, "New Orleans", 0.130, False),
    (198631344, "Jacksonville", 0.100, False),
    (198631348, "Cleveland", 0.090, False),
    (198631346, "Carolina", 0.090, False),
    (198631347, "Dallas", 0.080, False),
    (198631350, "Seattle", 0.080, False),
    (198631352, "Las Vegas", 0.075, False),
    (198631353, "Los Angeles C / Los Angeles R", 0.075, False),
    (198631340, "Miami", 0.070, False),
    (198631364, "Minnesota", 0.070, False),
    (198631357, "San Francisco", 0.070, False),
    (198631356, "Washington", 0.070, False),
    (198631339, "Buffalo", 0.060, False),
    (198631355, "Tampa Bay", 0.060, False),
    (198631342, "Baltimore", 0.060, False),
    (198631343, "Cincinnati", 0.050, False),
    (198631341, "New England", 0.050, False),
    (198631362, "New York G / New York J", 0.050, False),
    (198631363, "Pittsburgh", 0.050, False),
    # The seven the page refuses a price on.
    (198631349, "Arizona", 0.080, True),
    (198631351, "Atlanta", 0.070, True),
    (198631354, "Houston", 0.060, True),
    (198631361, "Kansas City", 0.050, True),
    (198631358, "Indianapolis", 0.050, True),
    (198631359, "Detroit", 0.050, True),
    (198631360, "Denver", 0.050, True),
)

WITHHELD_IDS = [row[0] for row in HOST_2031 if row[3]]
PAGE_NEW_ORLEANS = 0.13  # what `/api/futures/52755536` prints for the leader
SURVIVING_SUM = 1.3800  # the nineteen the card keeps
STORED_SUM = 1.7900  # all twenty-six, above `_FIELD_SUM_MAX`


def _legs(rows=HOST_2031):
    return [
        SimpleNamespace(id=i, name=n, current_probability=p) for i, n, p, _w in rows
    ]


def _survivors(rows=HOST_2031):
    """What #7632's drop hands the divisor."""
    return _legs([r for r in rows if not r[3]])


def _market(status="open", withheld=WITHHELD_IDS):
    m = SimpleNamespace(
        id=52755536, name="Who will host the 2031 Pro Football Championship?"
    )
    m.status = status
    if withheld is not None:
        m.__dict__["withheld_outcome_ids"] = list(withheld)
    return m


class TestTheDropIsWhatCreatesTheDefect:
    """The fixture reaches the squeeze band, so the assertions below can fail."""

    def test_the_stored_field_is_above_the_ceiling_and_would_already_agree(self):
        assert sum(r[2] for r in HOST_2031) == pytest.approx(STORED_SUM, abs=1e-9)
        assert _feed_display_scale(_legs(), mutually_exclusive=True) == 1.0

    def test_but_the_survivors_land_inside_the_band(self):
        assert sum(r[2] for r in HOST_2031 if not r[3]) == pytest.approx(
            SURVIVING_SUM, abs=1e-9
        )
        # Without the gate this is exactly the production defect: 1.38, and
        # 0.13 / 1.38 = 0.0942 — the 9.4% the card printed beside a 13% page.
        scale = _feed_display_scale(_survivors(), mutually_exclusive=True)
        assert scale == pytest.approx(SURVIVING_SUM, abs=1e-9)
        assert round(PAGE_NEW_ORLEANS / scale, 4) == 0.0942


class TestTheCardStopsDividingAWithheldField:
    def test_the_leader_prints_the_page_number(self):
        scale = _feed_display_scale(
            _survivors(), mutually_exclusive=True, field_complete=False
        )
        assert scale == 1.0
        assert round(PAGE_NEW_ORLEANS / scale, 4) == PAGE_NEW_ORLEANS

    def test_the_mini_list_shares_the_same_basis(self):
        """`top_outcomes` must not re-derive the divisor (Queue 283)."""
        top = [{"name": "New Orleans", "probability": PAGE_NEW_ORLEANS}]
        out = _normalize_feed_probabilities(
            top,
            _survivors(),
            "Who will host the 2031 Pro Football Championship?",
            mutually_exclusive=True,
            field_complete=False,
        )
        assert out[0]["probability"] == PAGE_NEW_ORLEANS

    def test_a_complete_field_still_divides(self):
        """The gate fires on withholding, never on being mutually exclusive."""
        assert _feed_display_scale(
            _survivors(), mutually_exclusive=True, field_complete=True
        ) == pytest.approx(SURVIVING_SUM, abs=1e-9)

    def test_the_default_preserves_every_existing_caller(self):
        assert _feed_display_scale(
            _survivors(), mutually_exclusive=True
        ) == pytest.approx(SURVIVING_SUM, abs=1e-9)


class TestTheNonExclusiveFieldIsLeftAlone:
    """gotcha #58 / #4079's `test_7`: dividing an independent-binary field is the
    entire reason this function exists, and the page keeps such a field raw for a
    DIFFERENT reason (#199). Widening the gate to non-ME would flip that
    population for something the page never asserted about it."""

    @pytest.mark.parametrize("exclusivity", [False, None])
    def test_it_still_divides_even_with_withheld_legs(self, exclusivity):
        assert _feed_display_scale(
            _survivors(), mutually_exclusive=exclusivity, field_complete=False
        ) == pytest.approx(SURVIVING_SUM, abs=1e-9)


class TestTheGateIsAskedBeforeTheDrop:
    """🔴 THE LOAD-BEARING CLASS. #7632 DELETES the refused legs from the card, so
    a gate asked after the drop answers `False` on precisely the boards it exists
    to catch — a wiring that passes every arithmetic test above and ships inert."""

    def test_the_pre_drop_field_reports_withheld_legs(self):
        assert _field_has_withheld_legs(_market(), _legs()) is True

    def test_the_post_drop_field_cannot_see_them(self):
        assert _field_has_withheld_legs(_market(), _survivors()) is False

    def test_every_serializer_asks_before_it_drops(self):
        """And the two above only DOCUMENT the hazard — this one catches it.

        CERT-3330 blocked the first cut of #7632 for being inert on exactly one of
        these two serializers while a source-order guard reported it present, so
        the ordering is asserted per enclosing function rather than file-wide."""
        source = Path(inspect.getsourcefile(_feed_display_scale)).read_text()
        offenders = []
        for fn in ast.walk(ast.parse(source)):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = {}
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "id", None)
                    if name in (
                        "_field_has_withheld_legs",
                        "_drop_withheld_price_legs",
                    ):
                        calls.setdefault(name, []).append(node.lineno)
            drops = calls.get("_drop_withheld_price_legs")
            if not drops:
                continue
            asks = calls.get("_field_has_withheld_legs") or []
            if not asks or min(asks) > min(drops):
                offenders.append((fn.name, asks, drops))
        assert not offenders, (
            "a serializer drops the refused legs before asking whether any were "
            f"refused — the gate is wired inert: {offenders}"
        )


class TestWhichLegsTheGateDescribes:
    def test_an_intersection_not_the_sets_truthiness(self):
        """`withheld_outcome_ids` is computed over the WHOLE market and may name
        legs this card was never built from — `league_futures.py` draws the same
        distinction for its own copy of this gate."""
        assert (
            _field_has_withheld_legs(_market(withheld=[999_000_001]), _survivors())
            is False
        )

    def test_none_is_not_empty_and_neither_refuses(self):
        """`None` = the arms never ran for this carrier (the pre-#7632 card)."""
        assert _field_has_withheld_legs(_market(withheld=None), _legs()) is False
        assert _field_has_withheld_legs(_market(withheld=[]), _legs()) is False

    def test_a_carrier_with_no_instance_dict_does_not_raise(self):
        assert _field_has_withheld_legs(object(), _legs()) is False

    def test_a_settled_board_keeps_every_leg(self):
        assert _field_has_withheld_legs(_market(status="settled"), _legs()) is False

    def test_the_passed_set_wins_over_the_carrier(self):
        """Sports mode computes the set and has nowhere to put it (CERT-3330)."""
        assert (
            _field_has_withheld_legs(_market(withheld=[]), _legs(), [198631349]) is True
        )


class TestEveryDivisorCallSiteIsWired:
    """A census question, so it is asked of the SET of call sites rather than of a
    list someone remembered to update: any call that threads `mutually_exclusive`
    is on the #8224/#8237 per-class path and must thread `field_complete` too.
    A new serializer that copies an old call site is the way this regresses."""

    def test_no_call_site_passes_exclusivity_without_completeness(self):
        source = Path(inspect.getsourcefile(_feed_display_scale)).read_text()
        tree = ast.parse(source)
        wired = {"_feed_display_scale", "_normalize_feed_probabilities"}
        missing = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in wired:
                continue
            kwargs = {k.arg for k in node.keywords}
            if "mutually_exclusive" in kwargs and "field_complete" not in kwargs:
                missing.append((name, node.lineno))
        assert not missing, (
            "call sites thread the #8224 ceiling but not #8237's withheld gate, "
            f"so the card still divides a partial field: {missing}"
        )

    def test_the_census_can_fail(self):
        """The check above is worthless if `wired` never matches anything."""
        source = Path(inspect.getsourcefile(_feed_display_scale)).read_text()
        tree = ast.parse(source)
        seen = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
            in {"_feed_display_scale", "_normalize_feed_probabilities"}
            and {"mutually_exclusive", "field_complete"}
            <= {k.arg for k in node.keywords}
        ]
        assert len(seen) >= 5, f"expected the wired call sites, found {seen}"
