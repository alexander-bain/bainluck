"""#7586 remainder — a non-exclusive card prints the same per-leg percent as its page.

The page and the card read the same `FuturesMarket.mutually_exclusive` flag and, for
a field the market says is NOT one winner, did opposite things with it:

    `outcome_display.normalize_display_probs`  mutually_exclusive False -> keep raw (#199)
    `feed._feed_display_scale`                 mutually_exclusive False -> divide by the
                                               all-leg sum anywhere in (1.05, 2.0]

So an independent-binary field summing 1.40 printed a leg at 60% on the page and at
43% on the Discover card behind it (0.60 / 1.40 = .4286). #4079's `test_7` is that
fixture, and it pinned the split as its PRECONDITION.

Codex's Direction B (`artifacts/other-model-7586-eligibility-finish/CODEX-REVIEW.md`):
for a proven non-exclusive family the card preserves each supported leg's raw
probability, just as the page already does. Discover (the issue's owner) ruled the
reconciliation on 2026-09-24 20:52Z: every test that pinned the non-exclusive divide
is re-pinned on the `None` arm, never deleted.

WHAT THIS PINS, AND WHAT IT DELIBERATELY LEAVES ALONE:

  False  -> raw (1.0), card == page, at every sum the old band divided
  None   -> today's divide, unchanged ("caller does not know" — never a silent widening)
  True   -> unchanged: #8224's 1.60 ceiling, #8237's withheld gate, the squeeze below
  ladder -> the ladder gate still runs first; `62003056`'s per-day legs are NOT a ladder
            and go raw through the False clause, never through that gate

The four call sites in `feed.py` all pass `_market_exclusivity(market)` into this one
function; that SET is pinned by `test_exclusive_field_overround_ceiling_8224.py::
TestEveryCallSiteIsWired`, and the served path for both the Discover and the
`mode=sports` scorer is exercised end to end by #4079's `test_7` / `test_7b`.
"""

from __future__ import annotations

import inspect
import textwrap
from types import SimpleNamespace

import pytest

from app.routes import feed as feed_module
from app.routes.feed import (
    _dated_movement_on_card_scale,
    _feed_display_scale,
    _normalize_feed_probabilities,
    _outcomes_are_cumulative_ladder,
    _scale_display_probability,
)
from app.utils.outcome_display import normalize_display_probs

# #4079 `test_7`'s field after its poll write: independent legs summing to 1.40.
INDEPENDENT_140 = [("Studio Aster", 0.60), ("Studio Birch", 0.50), ("Studio Cedar", 0.30)]
INDEPENDENT_140_Q = "Which studios announce a release delay by October 31?"

# `62003056` Will Ukraine target Moscow on...? — non-exclusive, 7 priced legs, raw sum
# 1.9250 (the same rows #8224 pins). Per-day binaries: none implies another.
UKRAINE_LEGS = [
    ("September 30", 0.325),
    ("September 27", 0.305),
    ("September 28", 0.305),
    ("September 29", 0.280),
    ("September 26", 0.265),
    ("September 25", 0.235),
    ("September 24", 0.210),
]
UKRAINE_Q = "Will Ukraine target Moscow on...?"


def _legs(rows):
    return [
        SimpleNamespace(name=n, current_probability=p, id=i, probability_change_24h=None)
        for i, (n, p) in enumerate(rows)
    ]


def _flat(n, each, prefix="c"):
    """n legs at `each`, named so no ladder/date grammar can read them."""
    return _legs([(f"{prefix}{i}", each) for i in range(n)])


def _page(rows, *, exclusive, field_complete=True):
    """What the page prints per leg — `normalize_display_probs` itself, not a copy."""
    outs = [{"name": n, "probability": p} for n, p in rows]
    normalize_display_probs(
        outs, mutually_exclusive=exclusive, field_complete=field_complete
    )
    return {o["name"]: o["probability"] for o in outs}


def _card(rows, question, *, exclusive, field_complete=True):
    """What the card prints per leg, through the card's own scale helper."""
    scale = _feed_display_scale(
        _legs(rows),
        question,
        mutually_exclusive=exclusive,
        field_complete=field_complete,
    )
    return {n: _scale_display_probability(p, scale) for n, p in rows}


class TestTheCardPrintsThePageValue:
    def test_4079s_independent_field_prints_60_on_both_surfaces(self):
        card = _card(INDEPENDENT_140, INDEPENDENT_140_Q, exclusive=False)
        page = _page(INDEPENDENT_140, exclusive=False)
        assert card == page
        assert card["Studio Aster"] == pytest.approx(0.60)

    def test_the_ukraine_field_is_raw_on_both_surfaces(self):
        assert round(sum(p for _, p in UKRAINE_LEGS), 4) == 1.9250
        assert _card(UKRAINE_LEGS, UKRAINE_Q, exclusive=False) == _page(
            UKRAINE_LEGS, exclusive=False
        )

    @pytest.mark.parametrize("total", [1.06, 1.20, 1.40, 1.60, 1.61, 1.86, 1.99, 2.0])
    def test_every_sum_the_old_band_divided_is_raw(self, total):
        """The population is (1.05, 2.0], wider than the 381 in (1.60, 2.0]."""
        legs = _flat(10, total / 10)
        assert _feed_display_scale(
            legs, "an independent binary field", mutually_exclusive=False
        ) == pytest.approx(1.0), f"non-exclusive sum {total} must print raw"

    def test_a_two_leg_non_exclusive_card_is_raw_too(self):
        """Control on the 1.01 two-leg threshold, the other `norm_threshold` arm."""
        rows = [("Yes side A", 0.55), ("Yes side B", 0.50)]  # 1.05 > 1.01
        assert _card(rows, "two independent binaries", exclusive=False) == _page(
            rows, exclusive=False
        )

    def test_the_mini_list_shares_the_same_basis(self):
        top = [{"name": "Studio Aster", "probability": 0.60}]
        out = _normalize_feed_probabilities(
            top, _legs(INDEPENDENT_140), INDEPENDENT_140_Q, mutually_exclusive=False
        )
        assert out[0]["probability"] == pytest.approx(0.60)

    def test_withheld_legs_do_not_bring_the_divide_back(self):
        """The page returns raw for non-ME BEFORE it asks about withheld legs."""
        assert _card(
            INDEPENDENT_140, INDEPENDENT_140_Q, exclusive=False, field_complete=False
        ) == _page(INDEPENDENT_140, exclusive=False, field_complete=False)


class TestTheUkraineFieldIsNotALadder:
    """Codex: no misclassification of `62003056` as cumulative. It goes raw through
    the False clause; the ladder gate must still decline it."""

    def test_the_ladder_gate_declines_it(self):
        assert _outcomes_are_cumulative_ladder(_legs(UKRAINE_LEGS), UKRAINE_Q) is False

    def test_so_unknown_exclusivity_still_divides_it(self):
        assert _feed_display_scale(
            _legs(UKRAINE_LEGS), UKRAINE_Q, mutually_exclusive=None
        ) == pytest.approx(1.925)


class TestUnknownExclusivityIsUnchanged:
    """`None` = "caller does not know": today's divide, never a widened repair."""

    def test_none_still_divides_the_independent_field(self):
        assert _feed_display_scale(
            _legs(INDEPENDENT_140), INDEPENDENT_140_Q, mutually_exclusive=None
        ) == pytest.approx(1.40)

    def test_the_default_is_none(self):
        assert _feed_display_scale(
            _legs(INDEPENDENT_140), INDEPENDENT_140_Q
        ) == pytest.approx(1.40)


class TestTheOneWinnerArmIsUnchanged:
    def test_an_exclusive_field_in_the_band_still_squeezes_like_the_page(self):
        card = _card(INDEPENDENT_140, "one winner", exclusive=True)
        page = _page(INDEPENDENT_140, exclusive=True)
        assert card["Studio Aster"] == pytest.approx(0.4286)
        # the page rounds its squeeze to 3dp, the card to 4dp; both print 43%
        for name in card:
            assert round(card[name] * 100) == round(page[name] * 100)

    def test_8224s_ceiling_still_keeps_an_overrounded_one_winner_field_raw(self):
        assert _feed_display_scale(
            _flat(10, 0.186), "one winner", mutually_exclusive=True
        ) == pytest.approx(1.0)

    def test_8237s_withheld_gate_still_keeps_a_one_winner_field_raw(self):
        assert _feed_display_scale(
            _flat(10, 0.138), "one winner", mutually_exclusive=True, field_complete=False
        ) == pytest.approx(1.0)
        assert _feed_display_scale(
            _flat(10, 0.138), "one winner", mutually_exclusive=True
        ) == pytest.approx(1.38)


class TestTheMovementBesideThePercentFollows:
    """At scale 1.0 the card serves the dated raw-to-raw move — the 2026-09-19
    scale ruling's own raw arm — where it used to serve null. That is a second
    reader-visible change and it is pinned, not incidental."""

    @pytest.fixture
    def dated(self, monkeypatch):
        calls = []

        def fake(market, outcome_id, current, delta, now=None):
            calls.append(outcome_id)
            return 0.10

        monkeypatch.setattr(feed_module, "dated_movement_points", fake)
        return calls

    def _move(self, exclusive):
        legs = _legs(INDEPENDENT_140)
        scale = _feed_display_scale(
            legs, INDEPENDENT_140_Q, mutually_exclusive=exclusive
        )
        return _dated_movement_on_card_scale(object(), legs[0], scale, now=None)

    def test_a_non_exclusive_card_serves_the_dated_move(self, dated):
        assert self._move(False) == pytest.approx(0.10)
        assert dated == [0]

    def test_an_unknown_card_is_still_normalized_so_serves_none(self, dated):
        assert self._move(None) is None
        assert dated == []


class TestTheDefectIsReproducedWithoutTheClause:
    """STRAWMAN. The function recompiled with the #7586 clause cut out must print
    the split a reader saw — .4286 on the card against .60 on the page."""

    CLAUSE = "    if mutually_exclusive is False:\n        return 1.0\n"

    def _without_the_clause(self):
        src = textwrap.dedent(inspect.getsource(feed_module._feed_display_scale))
        assert src.count(self.CLAUSE) == 1, "the clause moved; re-aim this strawman"
        ns = dict(vars(feed_module))
        exec(compile(src.replace(self.CLAUSE, ""), "<strawman>", "exec"), ns)
        return ns["_feed_display_scale"]

    def test_the_strawman_splits_the_card_from_the_page(self):
        stripped = self._without_the_clause()
        scale = stripped(
            _legs(INDEPENDENT_140), INDEPENDENT_140_Q, mutually_exclusive=False
        )
        assert scale == pytest.approx(1.40)
        assert round(0.60 / scale, 4) == 0.4286
        assert _page(INDEPENDENT_140, exclusive=False)["Studio Aster"] == 0.60

    def test_and_the_shipped_function_does_not(self):
        assert _feed_display_scale(
            _legs(INDEPENDENT_140), INDEPENDENT_140_Q, mutually_exclusive=False
        ) == pytest.approx(1.0)
