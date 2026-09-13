"""#5835: OPEN and LATEST are one comparison, so they are one scale.

WHAT A READER SAW. `/futures/109564` (*2026 Oscar for Best Animated Feature
Film?*) printed `KPop Demon Hunters  OPEN 92%  LATEST 61%`, and the caption under
the hero said it in words. The stored price went 0.915 -> 0.925 — it went UP one
point. Every rung on that board read as a fall and not one of them fell.

The cause is a denominator, not a price: `normalize_display_probs` squeezes the
`probability` column of a mutually-exclusive field whose raw prices sum into the
band, and is never called for `opening_probability`. The divisor is always above
1.05, so the artifact is one-directional — the page can only ever invent a fall.

THE INVARIANT THESE TESTS DEFEND IS NOT THE REMEDY. `test_every_served_pair_is
_on_one_scale` asks only that a served opening be comparable with the served
current price. Withholding satisfies it; so would a future decision to rescale
both columns. The tests are about the reader's subtraction, not about which
statement we wrote.
"""

from __future__ import annotations

import pytest

from app.utils.outcome_display import normalize_display_probs


# The production specimen, 2026-09-13 — market 109564, verbatim from the rows.
OSCAR_ANIMATED_CURRENT = [0.925, 0.500, 0.065, 0.015, 0.015, 0.005, 0.005]
OSCAR_ANIMATED_OPENING = [0.915, 0.500, 0.075, 0.035, 0.005, 0.005, 0.005]


def _market(currents, openings, *, mutually_exclusive=True):
    """A market shaped like the serializer's input. Mirrors the #5539 harness."""
    from types import SimpleNamespace

    outcomes = [
        SimpleNamespace(
            id=i,
            name=f"Entrant {i}",
            external_id=f"ENT-{i}",
            current_probability=cur,
            current_american_odds=400,
            rank=i,
            rank_change_24h=None,
            probability_change_24h=None,
            opening_probability=op,
            opening_american_odds=-9900,
            is_winner=None,
            resolution_source=None,
            last_updated=None,
        )
        for i, (cur, op) in enumerate(zip(currents, openings), start=1)
    ]
    return SimpleNamespace(
        id=109564,
        name="2026 Oscar for Best Animated Feature Film?",
        description=None,
        category="championship",
        source="kalshi",
        external_id="KXOSCARANIM-26",
        status="open",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=1,
        llm_sport_category="entertainment",
        mutually_exclusive=mutually_exclusive,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=outcomes,
    )


def _detail(market):
    from app.routes.futures import _format_market_detail

    return _format_market_detail(market)


class TestTheReadersSubtraction:
    """The one property the page depends on, stated without naming a remedy."""

    def test_every_served_pair_is_on_one_scale(self):
        """A served opening must be comparable with the served current price.

        THE KILLING ASSERTION. On the shipped code this fails on six of seven
        rungs: `probability` comes back divided by 1.53 while
        `opening_probability` is the raw stored price.
        """
        detail = _detail(_market(OSCAR_ANIMATED_CURRENT, OSCAR_ANIMATED_OPENING))
        for served, raw in zip(detail["outcomes"], OSCAR_ANIMATED_CURRENT):
            if served["opening_probability"] is None:
                continue  # no comparison is offered, so none can be wrong
            assert served["probability"] == pytest.approx(raw, abs=1e-4), (
                "an opening is served beside a RESCALED current price — the "
                "reader's subtraction is an artifact of the denominator"
            )

    def test_the_leader_that_rose_is_never_printed_as_a_fall(self):
        """0.915 -> 0.925 is up one point, whatever the page decides to print."""
        detail = _detail(_market(OSCAR_ANIMATED_CURRENT, OSCAR_ANIMATED_OPENING))
        leader = detail["outcomes"][0]
        if leader["opening_probability"] is None:
            return  # the page makes no claim about the move
        move = leader["probability"] - leader["opening_probability"]
        assert move > 0, (
            f"the page prints a {abs(move) * 100:.1f}-point FALL for an outcome "
            "whose price rose"
        )


class TestTheSerializerWithholdsWhatItCannotCompare:
    """The remedy actually shipped, and the flag a probe reads."""

    def test_a_squeezed_field_withholds_its_openings(self):
        detail = _detail(_market(OSCAR_ANIMATED_CURRENT, OSCAR_ANIMATED_OPENING))
        assert detail["openings_withheld"] is True
        for o in detail["outcomes"]:
            assert "opening_probability" in o, "the key must be PRESENT, not omitted"
            assert o["opening_probability"] is None
            assert o["opening_american_odds"] is None, (
                "the American-odds twin reconstructs exactly the comparison "
                "this rule just refused"
            )

    def test_the_squeezed_field_still_serves_its_current_prices(self):
        """The withhold is about the opening column only."""
        detail = _detail(_market(OSCAR_ANIMATED_CURRENT, OSCAR_ANIMATED_OPENING))
        assert [o["probability"] for o in detail["outcomes"]][:2] == [0.605, 0.327]


class TestTheOtherDirection:
    """Three populations that must keep printing their openings exactly as today.

    Each is a real reason the squeeze does not fire, and each is a column the
    reader keeps.
    """

    def test_a_coherent_field_under_the_threshold_keeps_its_openings(self):
        detail = _detail(_market([0.5, 0.3, 0.2], [0.45, 0.35, 0.2]))
        assert detail["openings_withheld"] is False
        assert [o["opening_probability"] for o in detail["outcomes"]] == [
            0.45,
            0.35,
            0.2,
        ]
        assert all(o["opening_american_odds"] == -9900 for o in detail["outcomes"])

    def test_an_overrounded_field_left_raw_keeps_its_openings(self):
        """Past `_FIELD_SUM_MAX` #1200 serves raw prices, so both columns are raw.

        Sum 2.4 — well past the 1.60 bail. Nothing is rescaled, so nothing is
        incomparable, and withholding here would delete an honest column.
        """
        detail = _detail(_market([0.8, 0.8, 0.8], [0.7, 0.8, 0.9]))
        assert detail["openings_withheld"] is False
        assert [o["probability"] for o in detail["outcomes"]] == [0.8, 0.8, 0.8]
        assert [o["opening_probability"] for o in detail["outcomes"]] == [0.7, 0.8, 0.9]

    def test_a_non_exclusive_participation_family_keeps_its_openings(self):
        """Golf make-cut/top-N (#199) is never squeezed, so it is never affected."""
        detail = _detail(
            _market([0.86, 0.80, 0.75], [0.80, 0.78, 0.70], mutually_exclusive=False)
        )
        assert detail["openings_withheld"] is False
        assert [o["probability"] for o in detail["outcomes"]] == [0.86, 0.80, 0.75]
        assert [o["opening_probability"] for o in detail["outcomes"]] == [
            0.80,
            0.78,
            0.70,
        ]

    def test_the_5539_refusal_is_unchanged_and_not_double_counted(self):
        """A field refused for #5539's reason is still refused, once."""
        detail = _detail(_market([0.2] * 35, [0.99] * 35))
        assert detail["openings_withheld"] is True
        assert all(o["opening_probability"] is None for o in detail["outcomes"])


class TestTheAnswerIsAskedNotRederived:
    """The call site must not carry its own copy of the squeeze threshold."""

    def test_openings_survive_when_the_normalizer_moves_nothing(self, monkeypatch):
        """THE MUTATION KILLER, and the reason the return value exists.

        A call site that re-derived "did it fire?" from the field sum would need
        the `> 105` test that lives in `app.routes.politics`, free to drift from
        it. Here the shared normalizer is neutered while the field sum stays at
        1.53, squarely inside the band. Nothing the reader is handed has moved,
        so the openings are comparable and must be served. A re-derived
        threshold withholds them and this test goes red.
        """
        import app.routes.politics as politics

        monkeypatch.setattr(politics, "_normalize_outcome_probs", lambda *a, **k: None)
        detail = _detail(_market(OSCAR_ANIMATED_CURRENT, OSCAR_ANIMATED_OPENING))
        assert detail["openings_withheld"] is False
        assert [o["probability"] for o in detail["outcomes"]] == OSCAR_ANIMATED_CURRENT
        assert [
            o["opening_probability"] for o in detail["outcomes"]
        ] == OSCAR_ANIMATED_OPENING


class TestTheNormalizerReportsWhatItDid:
    """`normalize_display_probs` returns whether the PRINTED values moved."""

    def test_it_reports_true_when_it_squeezes(self):
        outcomes = [{"probability": p} for p in OSCAR_ANIMATED_CURRENT]
        assert normalize_display_probs(outcomes) is True
        assert outcomes[0]["probability"] == 0.605

    def test_it_reports_false_for_a_non_exclusive_family(self):
        outcomes = [{"probability": p} for p in (0.86, 0.80, 0.75)]
        assert normalize_display_probs(outcomes, mutually_exclusive=False) is False
        assert outcomes[0]["probability"] == 0.86

    def test_it_reports_false_when_it_bails_on_an_overround(self):
        outcomes = [{"probability": 0.8} for _ in range(3)]
        assert normalize_display_probs(outcomes) is False
        assert all(o["probability"] == 0.8 for o in outcomes)

    def test_it_reports_false_for_a_field_already_under_the_threshold(self):
        outcomes = [{"probability": p} for p in (0.5, 0.3, 0.2)]
        assert normalize_display_probs(outcomes) is False
        assert [o["probability"] for o in outcomes] == [0.5, 0.3, 0.2]

    def test_a_field_it_reaches_but_cannot_move_reports_false(self):
        """Measured, not predicted — and this is the branch that proves it.

        A field of zeros passes both gates and reaches the shared normalizer,
        which finds no sum to divide and writes nothing (the write-back is
        skipped on a falsy value). Nothing the reader is handed moved, so the
        answer is False even though every threshold said "proceed". A return
        value derived from the thresholds instead of from the values would say
        True here.
        """
        outcomes = [{"probability": 0.0} for _ in range(3)]
        assert normalize_display_probs(outcomes) is False
        assert all(o["probability"] == 0.0 for o in outcomes)

    def test_the_squeeze_rounds_on_the_percent_scale_and_can_zero_a_longshot(self):
        """The reader-visible coarseness of the shared normalizer, pinned.

        `_normalize_outcome_probs` rounds to ONE decimal as a percentage before
        this function converts back, so 0.925 in a 1.53 field prints 0.605 and
        not 0.6046 — and a 0.0005 longshot in a squeezed field collapses to 0.
        Not this ship's to change; pinned so a later change to that rounding
        cannot pass unnoticed through the return value above.
        """
        outcomes = [{"probability": 1.06}] + [{"probability": 0.0005}] * 10
        assert normalize_display_probs(outcomes) is True
        assert outcomes[0]["probability"] == 0.995
        assert outcomes[1]["probability"] == 0.0

    def test_it_reports_a_move_that_leaves_the_FIELD_SUM_untouched(self, monkeypatch):
        """The measurement is per ROW, because the reader's comparison is per row.

        THIS TEST EXISTS BECAUSE A MUTANT SURVIVED. Swapping `any(...)` for
        "did the field sum change?" passed all sixteen other tests: today's
        normalizer divides by a sum above 1.05, so the sum always moves when the
        values do, and the two rules are indistinguishable on every field
        production can produce. They are not the same rule. The contract this
        function advertises — and the only one its caller can use — is *did the
        number printed on this row stop being the raw price*, and a row's
        opening is comparable or not regardless of what the column totals.

        Probed with a sum-preserving permutation, which is the smallest change
        that separates them.
        """
        import app.routes.politics as politics

        def _permute(outcomes, key="prob"):
            values = [o[key] for o in outcomes]
            for o, v in zip(outcomes, reversed(values)):
                o[key] = v

        monkeypatch.setattr(politics, "_normalize_outcome_probs", _permute)
        outcomes = [{"probability": p} for p in OSCAR_ANIMATED_CURRENT]
        assert normalize_display_probs(outcomes) is True, (
            "every row now prints another row's price and the field sum is "
            "unchanged — a sum-keyed answer calls this 'nothing moved'"
        )
        assert outcomes[0]["probability"] == 0.005

    def test_the_return_value_does_not_disturb_existing_callers(self):
        """Six concept adapters call this for its side effect and ignore it."""
        outcomes = [{"probability": p} for p in OSCAR_ANIMATED_CURRENT]
        normalize_display_probs(outcomes)
        assert [o["probability"] for o in outcomes][:2] == [0.605, 0.327]
