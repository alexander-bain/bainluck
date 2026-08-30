"""UX-P196: the /entertainment hero stops leading with a market nobody is trading.

`_score_for_trending` pays up to 100 points for sitting near 50% and at most 50
for volume — in practice under 6, since the live median 24h volume is ~360. So a
market with NO reported trading outscored actively-traded ones, and the hero grid
at the top of the page called it trending.

Measured on production 2026-08-30 (`GET /api/entertainment`): the fifth hero card
was *"#1 on the Billboard 200 chart for the Week of Sep 12, 2026?"* with
`volume_24h = None` and `prob` exactly 50.0.

The repair is a preference, not an exclusion: traded candidates are considered
first, untraded ones BACKFILL. The count of rows returned is unchanged, which is
load-bearing — `TrendingHero` renders nothing at all below two rows, so a fix
that could shorten the list would be a way of emptying the section.

These tests are clock-free by construction: no date, age or `now` reaches the
ranking (gotcha #44 does not apply, and must not start applying).
"""

import random

from collections import defaultdict

from app.routes.entertainment import (
    _build_trending,
    _has_reported_trading,
    _score_for_trending,
)


def _row(market_id, prob, kind, volume_24h, outcome_count=3, **kw):
    row = {
        "market_id": market_id,
        "q": f"market {market_id}",
        "prob": prob,
        "kind": kind,
        "volume_24h": volume_24h,
        "outcome_count": outcome_count,
    }
    row.update(kw)
    return row


def _legacy_build_trending(all_rows, limit=5):
    """The ranking exactly as it shipped before UX-P196.

    Kept here so the count-preservation property is checked against the real
    previous behaviour rather than against a hand-copied expectation.
    """
    scored = sorted(all_rows, key=_score_for_trending, reverse=True)
    result = []
    kind_counts = defaultdict(int)
    for row in scored:
        if len(result) >= limit:
            break
        if kind_counts[row["kind"]] >= 2:
            continue
        result.append(row)
        kind_counts[row["kind"]] += 1
    return result


class TestTheProductionRegression:
    """The exact five rows production served, and what changes about them."""

    # The five rows `GET /api/entertainment` served as the hero on 2026-08-30,
    # verbatim, PLUS the traded row the fix promotes in place of the untraded
    # one. ⚠️ This six-row fixture is NOT claimed to reproduce production's
    # ordering — adding the sixth row changes it, which is why the untraded row
    # sits at index 3 here and at index 4 live. The fidelity evidence is
    # separate and stronger: replaying the pre-fix ranking over the full
    # 108-row rendered corpus returned production's five hero rows in exactly
    # production's order (UX-P196 report). What this fixture pins is the
    # BEHAVIOUR CHANGE, not the live ordering.
    LIVE = [
        _row(59172870, 55.5, "multi", 32727, outcome_count=7),
        _row(12194657, 64.5, "multi", 107680, outcome_count=12),
        _row(59172867, 47.5, "reality", 5678, outcome_count=6),
        _row(52756014, 48.0, "billboard", 48, outcome_count=7),
        _row(59700007, 50.0, "billboard", None, outcome_count=3),
        # The traded row that the untraded one was keeping out.
        _row(58800001, 20.5, "reality", 152185, outcome_count=5),
    ]

    def test_the_untraded_row_led_the_hero_before_the_fix(self):
        """The bug is real: pin it, so the fix cannot be graded against nothing."""
        before = _legacy_build_trending(self.LIVE)
        assert len(before) == 5
        untraded = [r for r in before if not _has_reported_trading(r)]
        assert [r["market_id"] for r in untraded] == [59700007], (
            "the pre-fix ranking is expected to seat exactly the Billboard 200 "
            "row, which reported no trading at all"
        )

    def test_no_untraded_row_reaches_the_hero_when_traded_ones_are_available(self):
        after = _build_trending(self.LIVE)
        # VACUITY COMPANION: an empty or short result would satisfy the
        # "no untraded row" assertion below for the wrong reason.
        assert len(after) == 5
        assert all(_has_reported_trading(r) for r in after), [
            (r["market_id"], r["volume_24h"]) for r in after
        ]

    def test_the_displaced_slot_is_filled_by_the_traded_row(self):
        after = _build_trending(self.LIVE)
        assert 59700007 not in [r["market_id"] for r in after]
        assert 58800001 in [r["market_id"] for r in after]

    def test_the_traded_rows_keep_their_order_among_themselves(self):
        """A ranking change that reshuffles the whole hero is a different ship.

        The fix promotes the traded pool wholesale; it must not re-rank inside
        it. So the traded rows the previous ranking chose have to come out in
        the same relative order, with the untraded one simply gone.
        """
        before = _legacy_build_trending(self.LIVE)
        after = _build_trending(self.LIVE)
        traded_before = [
            r["market_id"] for r in before if _has_reported_trading(r)
        ]
        # VACUITY COMPANION: an empty list would make the prefix check hollow.
        assert len(traded_before) == 4
        assert [r["market_id"] for r in after[: len(traded_before)]] == traded_before


class TestTheBackfillNeverEmptiesTheSection:
    """The untraded pool is a backfill, never a cap."""

    def test_untraded_rows_still_fill_the_hero_when_nothing_is_traded(self):
        rows = [_row(i, 50.0, f"k{i}", None) for i in range(5)]
        result = _build_trending(rows)
        assert len(result) == 5, "the hero must not empty because nothing traded"

    def test_untraded_rows_backfill_behind_a_short_traded_pool(self):
        rows = [_row(1, 50.0, "a", 9999), _row(2, 50.0, "b", None), _row(3, 50.0, "c", None)]
        result = _build_trending(rows)
        assert [r["market_id"] for r in result] == [1, 2, 3]

    def test_the_traded_row_leads_even_when_it_scores_far_lower(self):
        """The whole point: score alone must not seat an untraded market first."""
        rows = [
            _row(1, 50.0, "a", None),  # perfect coin-flip score, nothing traded
            _row(2, 3.0, "b", 10),  # terrible score, but it trades
        ]
        assert [r["market_id"] for r in _build_trending(rows)] == [2, 1]

    def test_returns_the_same_number_of_rows_as_the_previous_ranking(self):
        """Randomised property — the repair may reorder, never shorten.

        `TrendingHero` returns null below two rows, so a fix that could shorten
        the list would be a way of blanking the top of the page.
        """
        rng = random.Random(11)
        checked = 0
        for _ in range(2000):
            pool = [
                _row(
                    i,
                    rng.uniform(0, 100),
                    rng.choice("abcd"),
                    rng.choice([None, 0, 1, 50, 9999]),
                    outcome_count=rng.randint(1, 9),
                )
                for i in range(rng.randint(0, 14))
            ]
            limit = rng.randint(1, 7)
            assert len(_build_trending(pool, limit)) == len(
                _legacy_build_trending(pool, limit)
            ), pool
            checked += 1
        # VACUITY COMPANION: a loop that never ran would pass in silence.
        assert checked == 2000

    def test_a_zero_volume_row_is_backfill_not_a_leader(self):
        """Behavioural, not just the helper — the CERT-483 class.

        `_has_reported_trading` has its own unit tests below, but those stay
        green if the partition stops going THROUGH it. A build that inlined
        `row.get("volume_24h") is not None` would seat a zero-volume row ahead
        of a traded one while every helper test still passed: the thing under
        test present, but not the thing that runs. This asserts the behaviour
        at the call site instead.
        """
        rows = [_row(1, 50.0, "a", 0), _row(2, 3.0, "b", 10)]
        assert [r["market_id"] for r in _build_trending(rows)] == [2, 1]

    def test_the_kind_ceiling_still_holds(self):
        rows = [_row(i, 50.0, "same", 100) for i in range(6)]
        assert len(_build_trending(rows)) == 2


class TestWhatCountsAsTrading:
    def test_absent_or_none_volume_is_not_trading(self):
        assert _has_reported_trading(_row(1, 50, "a", None)) is False
        assert _has_reported_trading({"prob": 50, "kind": "a"}) is False

    def test_zero_volume_is_not_trading(self):
        # No live row carries a literal 0 today, but a venue that starts
        # reporting 0 instead of omitting the field must not read as traded.
        assert _has_reported_trading(_row(1, 50, "a", 0)) is False
        assert _has_reported_trading(_row(1, 50, "a", 0.0)) is False

    def test_a_negative_figure_is_not_trading(self):
        assert _has_reported_trading(_row(1, 50, "a", -5)) is False

    def test_a_boolean_is_not_a_volume(self):
        # bool is an int subclass; True must not slip through as "traded".
        assert _has_reported_trading(_row(1, 50, "a", True)) is False

    def test_a_non_numeric_figure_is_not_trading(self):
        # A payload that hands us a string must not crash the hero, and must
        # not be believed either.
        assert _has_reported_trading(_row(1, 50, "a", "9999")) is False

    def test_any_positive_figure_is_trading(self):
        assert _has_reported_trading(_row(1, 50, "a", 1)) is True
        assert _has_reported_trading(_row(1, 50, "a", 0.5)) is True
        assert _has_reported_trading(_row(1, 50, "a", 152185)) is True


class TestTheScoreItselfIsUnchanged:
    """UX-P196 changes WHICH rows are eligible first, not how they are scored."""

    def test_scoring_is_untouched_across_a_spread_of_rows(self):
        cases = [
            (_row(1, 50.0, "billboard", None, outcome_count=3), 100 + 15 + 10),
            (_row(2, 50.0, "multi", None, outcome_count=2), 100),
            (_row(3, 0.0, "binary", 2000, outcome_count=2), 0 + 2),
            (_row(4, 55.5, "multi", 32727, outcome_count=7), 89 + 32.727 + 15),
        ]
        for row, expected in cases:
            assert _score_for_trending(row) == expected, row

    def test_the_hook_and_image_bonuses_still_apply(self):
        base = _row(1, 50.0, "multi", None, outcome_count=2)
        assert _score_for_trending(base) == 100
        assert _score_for_trending({**base, "hook": "x"}) == 105
        assert _score_for_trending({**base, "image_url": "u"}) == 103
