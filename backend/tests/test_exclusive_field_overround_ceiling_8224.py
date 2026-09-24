"""#8224 — a one-winner field is kept raw by the card at the same sum the page keeps it raw.

The #7641 / #7650 / #7674 family were all "the card reads the field wrong". This one
is not: both surfaces read the field correctly and still print different numbers,
because they disagreed on WHERE AN OVER-ROUNDED FIELD STOPS BEING ONE WINNER.

    `outcome_display.normalize_display_probs`  raw sum > _FIELD_SUM_MAX (1.60) -> keep raw
    `feed._feed_display_scale`                 norm_threshold < sum <= 2.0     -> divide

So a field summing in (1.60, 2.0] was kept raw by the page and divided by the card.

WHAT A READER SAW, measured on production 2026-09-23 11:26Z and again at 12:0xZ,
market `60607786` (*UEFA Champions League: League Phase Winner*), `mutually_exclusive`
true, 30/30 legs priced, raw sum 1.8600:

    page  34.00%    card  18.28%    <- 15.7 points apart, live today
    page  34.00%    card  34.00%    <- with this fix

1/1.86 = .5376 and .34 x .5376 = .1828, so the divisor IS the split, to four decimals.
`UCL_LEGS` below is that market's own 30 rows copied off `futures_outcomes`, not
invented — a reconstructed field summed to 2.0000 instead of 1.8600 on the first
attempt and would have exercised a different branch while looking right.

🔴 `TestTheNonExclusiveCeilingIsUntouched` IS THE LOAD-BEARING CLASS. A build that
simply lowered the ceiling to 1.60 for everything passes every assertion about the
specimen and silently stops normalizing gotcha #58's independent-binary field, which
is the entire reason `_feed_display_scale` exists. Codex's disposition is explicit —
use detail's 1.60 for the named exclusive class, do NOT globally replace feed's 2.0.
Measured over every open market with priced legs: 116 exclusive fields in the band
(repaired) against 381 non-exclusive ones (which must not move).

#7586 (2026-09-24, Codex Direction B, Discover's ruling (a)): a field flagged
`mutually_exclusive=False` now prints RAW on the card, as it always did on the page —
so the "keeps dividing" arm below is re-pinned on `None` ("caller does not know"),
which is the arm that still carries the historical 2.0, and each test also pins
False -> raw. Nothing was deleted; a build that lowered the ceiling for everything
still fails every `None` assertion. `test_card_keeps_non_exclusive_field_raw_7586.py`
owns the False arm.

🔴 `TestEveryCallSiteIsWired` PINS THE SET, NOT A COUNT. #8187's lesson (trap K-C): a
guard that asserts three NAMED call sites read a flag is green on the day a fourth
site is shipped unwired. The rule here is "every call in feed.py to either function
passes `mutually_exclusive`", derived from the AST, with a fabricated violation as a
control so a matcher that silently matches nothing cannot pass as a clean scan.
"""

from __future__ import annotations

import ast
import inspect
from types import SimpleNamespace

import pytest

from app.routes import feed as feed_module
from app.routes.feed import _feed_display_scale, _normalize_feed_probabilities
from app.utils.outcome_display import _FIELD_SUM_MAX

# `60607786` UEFA Champions League: League Phase Winner, read off `futures_outcomes`
# 2026-09-23. Raw sum 1.8600 — inside (1.60, 2.0], which is the whole defect.
UCL_LEGS = [
    ("Barcelona", 0.34),
    ("Manchester United", 0.07),
    ("Napoli", 0.06),
    ("Lille", 0.06),
    ("Lens", 0.06),
    ("Inter Milan", 0.06),
    ("Como", 0.06),
    ("Roma", 0.06),
    ("VfB Stuttgart", 0.06),
    ("Porto", 0.055),
    ("Real Betis", 0.055),
    ("Aston Villa", 0.055),
    ("Borussia Dortmund", 0.055),
    ("Sporting CP", 0.055),
    ("Galatasaray", 0.055),
    ("Shakhtar Donetsk", 0.055),
    ("Slovan Bratislava", 0.055),
    ("Atlético Madrid", 0.05),
    ("Sabah", 0.05),
    ("LASK", 0.05),
    ("Viking", 0.05),
    ("Slavia Prague", 0.05),
    ("AEK Athens", 0.05),
    ("Club Brugge", 0.045),
    ("Fenerbahçe", 0.045),
    ("Villarreal", 0.04),
    ("Feyenoord", 0.04),
    ("Bodø/Glimt", 0.04),
    ("RB Leipzig", 0.04),
    ("PSV Eindhoven", 0.04),
]
UCL_QUESTION = "UEFA Champions League: League Phase Winner"

# `62003056` Will Ukraine target Moscow on...? — non-exclusive, 7 priced legs, raw
# sum 1.9250, also inside the band. It must KEEP dividing: `on <date>` legs are
# per-day independent binaries, not a nested ladder, and the page keeps them raw for
# #199's reason rather than #1200's. Also today's Arm B control for #7667.
UKRAINE_LEGS = [
    ("September 30", 0.325),
    ("September 27", 0.305),
    ("September 28", 0.305),
    ("September 29", 0.280),
    ("September 26", 0.265),
    ("September 25", 0.235),
    ("September 24", 0.210),
]
UKRAINE_QUESTION = "Will Ukraine target Moscow on...?"


def _legs(rows):
    return [
        SimpleNamespace(name=n, current_probability=p, id=i)
        for i, (n, p) in enumerate(rows)
    ]


def _flat(n, each, prefix="c"):
    """n legs at `each`, named so no ladder/date grammar can read them."""
    return _legs([(f"{prefix}{i}", each) for i in range(n)])


class TestTheSpecimen:
    """The row a reader is looking at."""

    def test_the_fixture_is_the_market_not_a_reconstruction(self):
        assert len(UCL_LEGS) == 30
        assert round(sum(p for _, p in UCL_LEGS), 4) == 1.8600
        assert _FIELD_SUM_MAX < 1.86 <= 2.0, "specimen must sit inside the band"

    def test_exclusive_field_in_the_band_is_no_longer_divided(self):
        assert _feed_display_scale(
            _legs(UCL_LEGS), UCL_QUESTION, mutually_exclusive=True
        ) == pytest.approx(1.0)

    def test_barcelona_prints_the_page_value(self):
        scale = _feed_display_scale(
            _legs(UCL_LEGS), UCL_QUESTION, mutually_exclusive=True
        )
        assert round(0.34 / scale, 4) == 0.3400

    def test_and_the_defect_is_reproduced_when_the_ceiling_is_not_applied(self):
        """Red-first: the measured BEFORE, to the digit the reader saw. Taken on the
        `None` arm since #7586 — False no longer reaches the 2.0 ceiling at all."""
        scale = _feed_display_scale(
            _legs(UCL_LEGS), UCL_QUESTION, mutually_exclusive=None
        )
        assert scale == pytest.approx(1.86)
        assert round(0.34 / scale, 4) == 0.1828

    def test_the_mini_list_shares_the_same_basis(self):
        """`_normalize_feed_probabilities` must not keep its own opinion."""
        top = [{"name": "Barcelona", "probability": 0.34}]
        out = _normalize_feed_probabilities(
            top, _legs(UCL_LEGS), UCL_QUESTION, mutually_exclusive=True
        )
        assert out[0]["probability"] == pytest.approx(0.34)


class TestTheNonExclusiveCeilingIsUntouched:
    """🔴 LOAD-BEARING. A build that lowered the ceiling for everything passes
    every assertion above and deletes gotcha #58's normalization.

    Re-pinned on `None` by #7586 (Discover's ruling (a)): the 2.0 ceiling is now
    the unknown-exclusivity arm's, and a flagged-False field prints raw like the
    page. Each test pins both, so neither arm can move silently."""

    def test_the_same_legs_still_divide_when_the_field_is_not_exclusive(self):
        assert _feed_display_scale(
            _legs(UCL_LEGS), UCL_QUESTION, mutually_exclusive=None
        ) == pytest.approx(1.86)
        assert _feed_display_scale(
            _legs(UCL_LEGS), UCL_QUESTION, mutually_exclusive=False
        ) == pytest.approx(1.0)

    def test_the_ukraine_field_keeps_its_divisor(self):
        legs = _legs(UKRAINE_LEGS)
        assert round(sum(o.current_probability for o in legs), 4) == 1.9250
        assert _feed_display_scale(
            legs, UKRAINE_QUESTION, mutually_exclusive=None
        ) == pytest.approx(1.925)
        assert _feed_display_scale(
            legs, UKRAINE_QUESTION, mutually_exclusive=False
        ) == pytest.approx(1.0)

    def test_a_non_exclusive_field_between_1_60_and_2_0_is_the_population(self):
        """381 open markets live here; unknown exclusivity keeps dividing them,
        a flagged-False field prints raw (#7586)."""
        for total in (1.61, 1.75, 1.99, 2.0):
            legs = _flat(10, total / 10)
            assert _feed_display_scale(
                legs, "an independent binary field", mutually_exclusive=None
            ) == pytest.approx(total), f"unknown-exclusivity sum {total} must keep dividing"
            assert _feed_display_scale(
                legs, "an independent binary field", mutually_exclusive=False
            ) == pytest.approx(1.0), f"non-exclusive sum {total} must print raw"

    def test_4079_test_7s_independent_field_still_divides(self):
        """The 1.40-sum field pinned by #4079 — below 1.60 either way. Divides for
        None and True; raw for False since #7586."""
        legs = _flat(4, 0.35)
        assert _feed_display_scale(
            legs, "independent", mutually_exclusive=None
        ) == pytest.approx(1.4)
        assert _feed_display_scale(
            legs, "independent", mutually_exclusive=True
        ) == pytest.approx(1.4)
        assert _feed_display_scale(
            legs, "independent", mutually_exclusive=False
        ) == pytest.approx(1.0)


class TestTheCeilingIsPerClassAtTheBoundary:
    def test_exclusive_at_or_below_1_60_still_divides(self):
        legs = _flat(8, 0.2)  # 1.60 exactly
        assert round(sum(o.current_probability for o in legs), 4) == 1.6
        assert _feed_display_scale(
            legs, "one winner", mutually_exclusive=True
        ) == pytest.approx(1.6)

    def test_exclusive_just_above_1_60_is_raw(self):
        legs = _flat(9, 0.18)  # 1.62
        assert _feed_display_scale(
            legs, "one winner", mutually_exclusive=True
        ) == pytest.approx(1.0)

    def test_above_2_0_is_raw_for_both_classes_as_before(self):
        legs = _flat(10, 0.25)  # 2.50
        for me in (True, False, None):
            assert _feed_display_scale(
                legs, "big field", mutually_exclusive=me
            ) == pytest.approx(1.0)

    def test_at_or_under_the_low_threshold_is_raw_for_both_classes_as_before(self):
        legs = _flat(4, 0.25)  # 1.00
        for me in (True, False, None):
            assert _feed_display_scale(
                legs, "coherent", mutually_exclusive=me
            ) == pytest.approx(1.0)

    def test_the_ceiling_is_the_detail_pages_constant_not_a_second_copy(self):
        """If the page's boundary moves, the card's must move with it — that the two
        agree is the entire ship, so a literal 1.60 here would be the defect again."""
        src = inspect.getsource(feed_module._feed_display_scale)
        assert "_FIELD_SUM_MAX" in src
        just_over = _flat(9, (_FIELD_SUM_MAX + 0.02) / 9)
        assert _feed_display_scale(
            just_over, "one winner", mutually_exclusive=True
        ) == pytest.approx(1.0)


class TestUnknownExclusivityKeepsTodaysBehaviour:
    """A v6 snapshot payload predating #7808 carries no `mutually_exclusive`."""

    def test_none_reads_as_the_historical_2_0_ceiling(self):
        assert _feed_display_scale(
            _legs(UCL_LEGS), UCL_QUESTION, mutually_exclusive=None
        ) == pytest.approx(1.86)

    def test_the_default_is_none_so_untouched_callers_do_not_move(self):
        assert _feed_display_scale(
            _legs(UCL_LEGS), UCL_QUESTION
        ) == pytest.approx(1.86)

    def test_a_rehydrated_market_without_the_column_does_not_raise(self):
        """A bare attribute read would take the card out (gotcha #42)."""
        v6 = SimpleNamespace(name=UCL_QUESTION)  # no `mutually_exclusive` at all
        assert feed_module._market_exclusivity(v6) is None
        v7 = SimpleNamespace(name=UCL_QUESTION, mutually_exclusive=True)
        assert feed_module._market_exclusivity(v7) is True


class TestTheLadderGateStillRunsFirst:
    """The new ceiling must not shadow the #7641/#7650/#7674 grammar."""

    def test_an_exclusive_ladder_in_the_band_is_raw_via_the_ladder_gate(self):
        legs = _legs([("Before October", 0.30), ("Before 2027", 0.95)])  # 1.25
        assert _feed_display_scale(
            legs, "When will Apple release the iPhone 18?", mutually_exclusive=True
        ) == pytest.approx(1.0)

    def test_and_the_same_sum_without_the_grammar_still_divides(self):
        """Control: 1.25 is below 1.60, so only the ladder gate can make it raw —
        which is what proves the assertion above is about the grammar."""
        legs = _legs([("Aston Villa", 0.30), ("Barcelona", 0.95)])
        assert _feed_display_scale(
            legs, "League Phase Winner", mutually_exclusive=True
        ) == pytest.approx(1.25)


class TestEveryCallSiteIsWired:
    """🔴 PIN THE SET, NOT A COUNT (#8187's trap K-C). A guard naming today's four
    sites is green the day a fifth is added unwired."""

    WIRED = ("_feed_display_scale", "_normalize_feed_probabilities")

    @staticmethod
    def _unwired_calls(source: str, names) -> list[str]:
        tree = ast.parse(source)
        bad = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name not in names:
                continue
            if not any(kw.arg == "mutually_exclusive" for kw in node.keywords):
                bad.append(f"{name} at line {node.lineno}")
        return bad

    def test_no_call_in_feed_py_omits_the_exclusivity(self):
        src = inspect.getsource(feed_module)
        assert self._unwired_calls(src, self.WIRED) == []

    def test_the_set_is_not_empty(self):
        """A walk that found nothing passes the assertion above identically."""
        src = inspect.getsource(feed_module)
        wired = [
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call)
            and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
            in self.WIRED
            and any(kw.arg == "mutually_exclusive" for kw in n.keywords)
        ]
        assert len(wired) >= 4, f"expected the four known sites, found {len(wired)}"

    def test_the_matcher_catches_a_fabricated_violation(self):
        """CONTROL — a scan over a clean tree passes identically to a broken one."""
        fabricated = (
            "def f(market, outs):\n"
            "    a = _feed_display_scale(outs, market.name)\n"
            "    b = _normalize_feed_probabilities(t, outs, market.name)\n"
            "    return a, b\n"
        )
        assert len(self._unwired_calls(fabricated, self.WIRED)) == 2

    def test_the_matcher_does_not_fire_on_a_near_miss(self):
        clean = (
            "def f(market, outs):\n"
            "    return _feed_display_scale(\n"
            "        outs, market.name, mutually_exclusive=_market_exclusivity(market)\n"
            "    )\n"
            "def g(outs):\n"
            "    return _feed_display_scale_helper(outs)\n"
        )
        assert self._unwired_calls(clean, self.WIRED) == []
