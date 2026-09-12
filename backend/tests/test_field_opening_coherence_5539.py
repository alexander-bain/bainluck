"""#5539 — a one-winner field's openings are published only if they could be real.

Every specimen below is a production row measured 2026-09-12, named by market id,
so a future reader can re-read the row rather than trust the fixture. The two
ceilings are asserted through BEHAVIOUR on real fields, and each has at least one
specimen that only it spares — a mutation that deletes either condition, or that
loosens it, fails a test here.
"""

import pytest

from app.utils.field_opening_coherence import (
    FIELD_MEAN_CEILING,
    FIELD_SUM_CEILING,
    MIN_FIELD_LEGS,
    NOT_APPLICABLE_FIELD_TOO_SMALL,
    NOT_APPLICABLE_NOT_EXCLUSIVE,
    OK,
    REFUSED_FIELD_NOT_A_DISTRIBUTION,
    classify_field_openings,
    field_openings_publishable,
)


class TestTheDefectIsRefused:
    """The fields a reader met, and what the page must stop printing."""

    def test_womens_2027_college_basketball_champion_is_refused(self):
        """Market 12337998: 35 teams, every stored opening 0.99, sum 34.65.

        The page printed OPEN 99% on all 35 rows and captioned the chart "South
        Carolina down 74.4 pts from opening". This is the filing specimen.
        """
        assert classify_field_openings([0.99] * 35, mutually_exclusive=True) == (
            REFUSED_FIELD_NOT_A_DISTRIBUTION
        )

    def test_chess_olympiad_winner_is_refused(self):
        """Market 13492442: 40 legs, sum 39.60 — every entrant 'opened' at 99%."""
        assert not field_openings_publishable([0.99] * 40, mutually_exclusive=True)

    def test_republican_vp_nominee_2028_is_refused(self):
        """Market 11020528 (polymarket): 127 legs, sum 104.57, mean 0.82.

        Exactly one person is the nominee, so a field averaging 0.82 is not a
        distribution however it was assembled.
        """
        openings = [0.82] * 127
        assert not field_openings_publishable(openings, mutually_exclusive=True)

    def test_the_untraded_half_cent_seed_is_refused(self):
        """The 0.495 cohort: the midpoint of an untraded 0.49/0.50 book.

        Mean 0.495 clears the mean ceiling only just, which is the point — this
        is the shape that would survive a rule keyed on 'looks near certain'.
        """
        assert not field_openings_publishable([0.495] * 31, mutually_exclusive=True)

    def test_a_refused_field_is_refused_whole_not_leg_by_leg(self):
        """One honestly-priced leg does not rescue the field, and is not spared.

        Market 364227's shape: 18 legs at the seed and one real price. The
        verdict is about the field, so the surface withholds every opening in it
        — a lone survivor in an OPEN column is a comparison with no partner to
        check it against, which is the half-open state the sibling pair rule
        exists to prevent.
        """
        assert not field_openings_publishable(
            [0.495] * 18 + [0.75], mutually_exclusive=True
        )


class TestHonestFieldsAreUntouched:
    """The populations a value rule or a single-condition rule would have taken."""

    def test_a_coherent_field_publishes(self):
        assert classify_field_openings([0.5, 0.3, 0.2], mutually_exclusive=True) == OK

    def test_oscar_best_picture_is_spared_by_the_mean_condition(self):
        """Market 6173044: 35 legs, sum 2.04, mean 0.058.

        Openings are captured per leg as legs are added, so a field assembled
        over months drifts past a coherent sum while every price in it is real.
        The SUM alone is over any '1.0 plus vig' reading; only the mean condition
        keeps this field published.
        """
        openings = [2.04 / 35] * 35
        assert sum(openings) > 2.0, "specimen must be sum-incoherent to be the test"
        assert field_openings_publishable(openings, mutually_exclusive=True)

    def test_a_large_honest_field_past_the_sum_ceiling_is_spared(self):
        """100 real longshots summing to 4.0 — over the sum ceiling, mean 0.04.

        This is the population the sum condition alone would wrongly refuse: 76
        Kalshi and 79 Polymarket markets on production.
        """
        openings = [0.04] * 100
        assert sum(openings) > FIELD_SUM_CEILING
        assert field_openings_publishable(openings, mutually_exclusive=True)

    def test_a_small_field_with_ordinary_overround_is_spared_by_the_sum_condition(self):
        """Three legs at a mean 0.42 sum to 1.26 — a vig story, not a fabrication.

        This is the population the mean condition alone would wrongly refuse: 91
        Kalshi and 203 Polymarket markets on production.
        """
        openings = [0.42, 0.42, 0.42]
        assert (sum(openings) / len(openings)) >= FIELD_MEAN_CEILING
        assert field_openings_publishable(openings, mutually_exclusive=True)

    def test_honest_longshots_sharing_one_value_are_spared(self):
        """The 19,095 legs a 'too many legs share this opening' rule would take.

        Production's biggest shared-value groups are 0.005/0.015/0.025/0.030/
        0.035 — real prices on big fields, not seeds.
        """
        assert field_openings_publishable([0.015] * 137, mutually_exclusive=True)

    def test_a_two_leg_coin_flip_is_out_of_scope(self):
        """31 production markets open 0.50/0.50 and sum to exactly 1."""
        assert classify_field_openings([0.5, 0.5], mutually_exclusive=True) == (
            NOT_APPLICABLE_FIELD_TOO_SMALL
        )

    def test_a_non_exclusive_field_is_out_of_scope(self):
        """Golf make-cut/top-N and 'which players transfer' are not one-winner.

        Their legs are independent binaries, so a sum over 1 says nothing
        (gotcha #23). Market 364227 is one of these, which is why the arithmetic
        rule cannot be the whole of #5539.
        """
        assert classify_field_openings([0.99] * 35, mutually_exclusive=False) == (
            NOT_APPLICABLE_NOT_EXCLUSIVE
        )

    def test_odds_api_style_fields_are_untouched(self):
        """Measured: 0 of 12 odds_api ME open markets fire, max sum 1.32."""
        assert field_openings_publishable(
            [0.40, 0.32, 0.25, 0.20, 0.15], mutually_exclusive=True
        )


class TestTheCeilingsAreWhereTheyClaimToBe:
    def test_the_mean_ceiling_sits_above_the_loosest_honest_mean(self):
        """1/MIN_FIELD_LEGS bounds the mean of every field this rule can see.

        A ceiling at or below it could refuse a field that sums to exactly 1,
        which is the definition of coherent. This is why the constant is derived
        rather than tuned.
        """
        assert FIELD_MEAN_CEILING > 1.0 / MIN_FIELD_LEGS

    def test_the_sum_ceiling_admits_a_coherent_field_with_room(self):
        assert FIELD_SUM_CEILING > 1.0

    def test_a_field_needs_both_conditions_to_be_refused(self):
        """Neither condition alone is the rule, asserted on the boundary."""
        over_sum_only = [0.04] * 100
        over_mean_only = [0.42, 0.42, 0.42]
        both = [0.99] * 35
        assert field_openings_publishable(over_sum_only, mutually_exclusive=True)
        assert field_openings_publishable(over_mean_only, mutually_exclusive=True)
        assert not field_openings_publishable(both, mutually_exclusive=True)


class TestUnpricedLegs:
    def test_a_none_opening_is_ignored_not_counted_as_zero(self):
        """gotcha #53: 'nobody recorded an opening' is not 'the opening was 0'.

        Counting None as 0 would drag the mean down and let a seeded field with
        a few unpriced legs publish.
        """
        assert classify_field_openings(
            [0.99] * 35 + [None] * 40, mutually_exclusive=True
        ) == REFUSED_FIELD_NOT_A_DISTRIBUTION

    def test_a_field_with_too_few_priced_legs_is_out_of_scope(self):
        assert classify_field_openings(
            [0.99, 0.99, None, None], mutually_exclusive=True
        ) == NOT_APPLICABLE_FIELD_TOO_SMALL

    def test_no_openings_at_all_is_out_of_scope(self):
        assert classify_field_openings([None] * 12, mutually_exclusive=True) == (
            NOT_APPLICABLE_FIELD_TOO_SMALL
        )

    def test_an_empty_field_is_out_of_scope(self):
        assert classify_field_openings([], mutually_exclusive=True) == (
            NOT_APPLICABLE_FIELD_TOO_SMALL
        )


class TestTheSerializerWithholdsWhatTheRuleRefuses:
    """The rule is only a ship if the payload carries it — and carries NULL.

    `OutcomeRow` gates its column on `opening_probability !== null`, so an
    OMITTED key renders `undefined` rather than nothing. These assert the key is
    present and null, which is the contract the client actually reads.
    """

    @staticmethod
    def _detail(market, bookmakers=None):
        from app.routes.futures import _format_market_detail

        return _format_market_detail(market, bookmakers)

    @staticmethod
    def _market(openings, mutually_exclusive=True):
        from types import SimpleNamespace

        outcomes = [
            SimpleNamespace(
                id=i,
                name=f"Entrant {i}",
                external_id=f"ENT-{i}",
                current_probability=0.2,
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
            for i, op in enumerate(openings, start=1)
        ]
        return SimpleNamespace(
            id=12337998,
            name="Women's 2027 College Basketball Champion",
            description=None,
            category="championship",
            source="kalshi",
            external_id="KXNCAAWBB-27",
            status="open",
            sport=None,
            sport_id=None,
            event_id=None,
            market_type=None,
            market_tier=1,
            llm_sport_category="basketball",
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

    def test_a_refused_field_serves_null_openings_and_says_so(self):
        detail = self._detail(self._market([0.99] * 35))
        assert detail["openings_withheld"] is True
        assert detail["outcomes"], "the outcomes themselves must still be served"
        for o in detail["outcomes"]:
            assert "opening_probability" in o, "the key must be PRESENT, not omitted"
            assert o["opening_probability"] is None
            assert o["opening_american_odds"] is None

    def test_a_refused_field_still_serves_its_current_prices(self):
        """The refusal is about the opening only — the page keeps its answer."""
        detail = self._detail(self._market([0.99] * 35))
        assert any(o["probability"] is not None for o in detail["outcomes"])

    def test_an_honest_field_keeps_its_openings(self):
        detail = self._detail(self._market([0.5, 0.3, 0.2]))
        assert detail["openings_withheld"] is False
        assert [o["opening_probability"] for o in detail["outcomes"]] == [0.5, 0.3, 0.2]
        assert all(o["opening_american_odds"] == -9900 for o in detail["outcomes"])

    def test_a_non_exclusive_field_keeps_its_openings(self):
        detail = self._detail(self._market([0.99] * 35, mutually_exclusive=False))
        assert detail["openings_withheld"] is False
        assert all(o["opening_probability"] == 0.99 for o in detail["outcomes"])

    def test_the_flag_is_always_present(self):
        """Absence must mean 'old build', never 'coherent field'."""
        assert "openings_withheld" in self._detail(self._market([0.5, 0.3, 0.2]))


@pytest.mark.parametrize(
    "openings,me,expected",
    [
        ([0.99] * 35, True, REFUSED_FIELD_NOT_A_DISTRIBUTION),
        ([0.99] * 35, False, NOT_APPLICABLE_NOT_EXCLUSIVE),
        ([0.5, 0.5], True, NOT_APPLICABLE_FIELD_TOO_SMALL),
        ([0.5, 0.3, 0.2], True, OK),
        ([0.04] * 100, True, OK),
        ([0.42] * 3, True, OK),
    ],
)
def test_verdict_table(openings, me, expected):
    assert classify_field_openings(openings, mutually_exclusive=me) == expected
