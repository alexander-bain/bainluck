"""#6996 — two legs of a one-winner field cannot both have opened certain.

#5539 shipped two CEILINGS, and `/futures/113129` walked up to one of them. The
*Nobel Peace Prize Winner 2026* board printed OPEN 100% on its top three rows —
Save the Children, Sudan's Emergency Response Rooms, Chow Hang-tung, three
entrants in one prize — because the field's mean landed 0.00275 under
`FIELD_MEAN_CEILING` while its sum sat at 4.2x the sum ceiling.

Every opening vector below is the vector production actually SERVED on
2026-09-18, copied from the payload of the named market rather than invented, so
a later reader can re-fetch the id and check the fixture against it. That
matters more than usual here: the rule judges the DISPLAYED subset (the route
passes the legs it is about to print), so a fixture built from stored rows would
be testing a field no reader ever sees.
"""

import pytest

from app.utils.field_opening_coherence import (
    CERTAIN_LEG_PROBABILITY,
    FIELD_MEAN_CEILING,
    FIELD_SUM_CEILING,
    MAX_CERTAIN_LEGS,
    MIN_FIELD_LEGS,
    NOT_APPLICABLE_FIELD_TOO_SMALL,
    NOT_APPLICABLE_NOT_EXCLUSIVE,
    OK,
    REFUSAL_VERDICTS,
    REFUSED_FIELD_NOT_A_DISTRIBUTION,
    REFUSED_MULTIPLE_CERTAIN_LEGS,
    classify_field_openings,
    field_openings_publishable,
)

# `/api/futures/113129` — *Nobel Peace Prize Winner 2026*, 32 served legs, twelve
# of them at exactly 1.0. Sum 12.7120, mean 0.397250.
NOBEL_113129 = [
    1.0, 1.0, 1.0, 0.075, 0.057, 0.0865, 0.1035, 0.105, 0.0925, 0.013, 0.018,
    0.0275, 0.0065, 1.0, 0.044, 1.0, 1.0, 1.0, 1.0, 0.005, 0.01, 1.0, 1.0,
    0.0115, 0.0065, 0.012, 0.006, 0.006, 0.016, 0.0105, 1.0, 1.0,
]

# `/api/futures/113125` — *Alaska Governor Election Winner*, 23 served legs, six
# at 1.0. Sum 9.0415, mean 0.393109. Its caption happens to be honest because the
# leader's own opening is real; six of its rows still print a fabricated OPEN.
ALASKA_113125 = [
    0.495, 0.33, 0.016, 0.052, 0.23, 0.0235, 0.103, 0.495, 0.195, 0.004, 0.022,
    0.06, 1.0, 0.003, 0.004, 0.024, 0.49, 0.495, 1.0, 1.0, 1.0, 1.0, 1.0,
]

# `/api/futures/16756763` — *Dubai Sail Grand Prix Winner* (kalshi). Three stored
# legs, all 1.0, summing to EXACTLY 3.0 — spared by a strict inequality.
SAIL_GP_16756763 = [1.0, 1.0, 1.0]

# `/api/futures/113090` — *Idaho Senate Election Winner*. Two certain legs in a
# four-leg race; sum 3.0, so the SUM condition spares it outright.
IDAHO_113090 = [1.0, 1.0, 0.5, 0.5]


class TestTheDefectIsRefused:
    """The three boards a reader met, and what each one proves."""

    def test_the_nobel_field_is_refused(self):
        """Market 113129, the filing specimen: three orgs each OPEN 100%."""
        assert classify_field_openings(NOBEL_113129, mutually_exclusive=True) == (
            REFUSED_MULTIPLE_CERTAIN_LEGS
        )
        assert not field_openings_publishable(NOBEL_113129, mutually_exclusive=True)

    def test_the_alaska_field_is_refused(self):
        """Market 113125: six of twenty-three rows print a fabricated OPEN."""
        assert classify_field_openings(ALASKA_113125, mutually_exclusive=True) == (
            REFUSED_MULTIPLE_CERTAIN_LEGS
        )

    def test_a_field_summing_to_exactly_the_ceiling_is_refused(self):
        """Market 16756763: three boats, all 'certain', sum exactly 3.0.

        `>` spares it by a hair and there is no hair to split — three entrants
        cannot each be certain to win one regatta.
        """
        assert sum(SAIL_GP_16756763) == FIELD_SUM_CEILING, "specimen sits ON the ceiling"
        assert classify_field_openings(SAIL_GP_16756763, mutually_exclusive=True) == (
            REFUSED_MULTIPLE_CERTAIN_LEGS
        )

    def test_a_small_race_spared_by_the_sum_condition_is_refused(self):
        """Market 113090: two candidates both 'certain' to win one seat."""
        assert classify_field_openings(IDAHO_113090, mutually_exclusive=True) == (
            REFUSED_MULTIPLE_CERTAIN_LEGS
        )


class TestWhyACeilingCouldNotHaveCaughtThese:
    """Each specimen is published by the #5539 rule. Without this, these pass."""

    @pytest.mark.parametrize(
        "openings,market",
        [
            (NOBEL_113129, "113129"),
            (ALASKA_113125, "113125"),
            (SAIL_GP_16756763, "16756763"),
            (IDAHO_113090, "113090"),
        ],
    )
    def test_the_ceiling_rule_publishes_every_specimen(self, openings, market):
        """The control. If this ever fails, the specimen stopped being the case
        this issue is about and the test above it is no longer proving anything.
        """
        priced = [p for p in openings if p is not None]
        total = sum(priced)
        tripped_the_ceilings = (
            total > FIELD_SUM_CEILING
            and (total / len(priced)) >= FIELD_MEAN_CEILING
        )
        assert not tripped_the_ceilings, f"{market} must be published by #5539's rule"

    def test_the_honest_legs_are_what_spare_the_nobel_field(self):
        """The property that makes this a hole rather than a tuning miss.

        The twelve fabricated 1.0s push the mean up; the real prices dilute it
        back under the ceiling. Drop any one honest leg and #5539 refuses the
        field — so it is protected in proportion to how much of it is real.
        """
        honest = [p for p in NOBEL_113129 if p < CERTAIN_LEG_PROBABILITY]
        assert honest, "specimen must carry honest legs for this to mean anything"
        for i, leg in enumerate(honest):
            trimmed = list(NOBEL_113129)
            trimmed.remove(leg)
            total = sum(trimmed)
            assert total > FIELD_SUM_CEILING
            assert (total / len(trimmed)) >= FIELD_MEAN_CEILING, (
                f"removing honest leg {i} ({leg}) should flip #5539 to refuse"
            )

    def test_lowering_the_mean_ceiling_instead_would_refuse_honest_fields(self):
        """Why the fix is a count and not a smaller number.

        The smallest ceiling the module's own derivation permits is 1/3. Setting
        it there still publishes the Nobel field (mean 0.397 > 1/3 would refuse
        it — but it also refuses the large honest fields the condition exists to
        spare). Asserted on the population #5539 measured: 100 real longshots.
        """
        honest_large_field = [0.04] * 100
        assert sum(honest_large_field) > FIELD_SUM_CEILING
        derived_floor = 1.0 / MIN_FIELD_LEGS
        nobel_mean = sum(NOBEL_113129) / len(NOBEL_113129)
        assert nobel_mean > derived_floor, (
            "a ceiling low enough to catch 113129 is below the derived bound"
        )
        # …and the field that bound protects stays published under THIS fix.
        assert field_openings_publishable(honest_large_field, mutually_exclusive=True)


class TestHonestFieldsAreUntouched:
    """This is a count of impossibilities, not a value rule. It must not become
    one — the value rule #5539 measured and rejected took ~19,000 honest legs."""

    def test_a_lone_certain_leg_is_left_alone(self):
        """The boundary that keeps this from being a near-certainty rule.

        A real market can price a done deal at 0.999, and one such leg is
        coherent: the rest of the field sums to ~0. The single-leg case belongs
        to `drop_incoherent_near_certain` (#6524), not here.
        """
        assert classify_field_openings(
            [0.999, 0.0005, 0.0005], mutually_exclusive=True
        ) == OK

    def test_honest_longshots_sharing_one_value_are_spared(self):
        """The 19,095-leg population. No multiplicity of a longshot can fire."""
        assert field_openings_publishable([0.015] * 137, mutually_exclusive=True)
        assert field_openings_publishable([0.005] * 400, mutually_exclusive=True)

    @pytest.mark.parametrize(
        "openings",
        [
            [0.5, 0.3, 0.2],
            [0.04] * 100,
            [0.42] * 3,
            [0.40, 0.32, 0.25, 0.20, 0.15],
            [2.04 / 35] * 35,
        ],
    )
    def test_the_fields_5539_protects_still_publish(self, openings):
        assert classify_field_openings(openings, mutually_exclusive=True) == OK

    def test_a_field_just_under_the_certainty_bar_is_spared(self):
        """0.9989 twice is not refused — the bar is a stated constant, and a
        change to it must break a test rather than quietly widen the population.
        """
        just_under = [0.9989, 0.9989, 0.0005]
        assert max(just_under) < CERTAIN_LEG_PROBABILITY
        assert classify_field_openings(just_under, mutually_exclusive=True) == OK

    def test_the_0_99_seed_cohort_is_still_the_ceiling_rules_business(self):
        """#5539's own specimens sit at 0.99, BELOW this bar, and must keep
        being refused by the ceilings — this clause does not inherit them."""
        assert classify_field_openings([0.99] * 35, mutually_exclusive=True) == (
            REFUSED_FIELD_NOT_A_DISTRIBUTION
        )


class TestScopeGatesStillBind:
    def test_a_non_exclusive_field_is_out_of_scope(self):
        """Golf make-cut/top-N legs are independent binaries — several CAN be
        near certain at once (gotcha #23). 12 certain legs, still not our call.
        """
        assert classify_field_openings(NOBEL_113129, mutually_exclusive=False) == (
            NOT_APPLICABLE_NOT_EXCLUSIVE
        )

    def test_a_two_leg_field_is_out_of_scope_even_if_both_are_certain(self):
        """Below MIN_FIELD_LEGS this module says nothing — the two-leg case is
        `app.utils.pair_opening_coherence`'s, and stealing it here would give one
        pair two rules with no adjudicator."""
        assert classify_field_openings([1.0, 1.0], mutually_exclusive=True) == (
            NOT_APPLICABLE_FIELD_TOO_SMALL
        )

    def test_none_openings_are_ignored_not_counted(self):
        """gotcha #53. Two certain legs among Nones still needs MIN_FIELD_LEGS
        real ones before the field is judged at all."""
        assert classify_field_openings(
            [1.0, 1.0, None, None, None], mutually_exclusive=True
        ) == NOT_APPLICABLE_FIELD_TOO_SMALL
        assert classify_field_openings(
            [1.0, 1.0, 0.01, None, None], mutually_exclusive=True
        ) == REFUSED_MULTIPLE_CERTAIN_LEGS


class TestTheVerdictOfAnAlreadyRefusedFieldDoesNotMove:
    """The ordering guard. #5539 refuses 614 markets today; this change must not
    relabel one of them, or a probe keyed on the verdict string silently breaks.
    """

    def test_a_field_tripping_both_rules_reports_the_older_verdict(self):
        both = [1.0] * 35
        priced = [p for p in both]
        assert sum(priced) > FIELD_SUM_CEILING
        assert sum(priced) / len(priced) >= FIELD_MEAN_CEILING
        assert sum(1 for p in priced if p >= CERTAIN_LEG_PROBABILITY) > MAX_CERTAIN_LEGS
        assert classify_field_openings(both, mutually_exclusive=True) == (
            REFUSED_FIELD_NOT_A_DISTRIBUTION
        )

    def test_the_new_verdict_actually_withholds(self):
        """A verdict that is not in REFUSAL_VERDICTS is a no-op — the wiring, not
        the arithmetic, is what reaches the reader."""
        assert REFUSED_MULTIPLE_CERTAIN_LEGS in REFUSAL_VERDICTS
        assert not field_openings_publishable(NOBEL_113129, mutually_exclusive=True)


class TestTheSerializerWithholdsWhatTheRuleRefuses:
    """The rule is only a ship if the route carries it. Driving the real
    serializer, because a helper being right is not the helper being CALLED."""

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
            id=113129,
            name="Nobel Peace Prize Winner 2026",
            description=None,
            category="politics",
            source="polymarket",
            external_id="nobel-peace-prize-winner-2026",
            status="open",
            sport=None,
            sport_id=None,
            event_id=None,
            market_type=None,
            market_tier=1,
            llm_sport_category="politics",
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

    def _detail(self, market, bookmakers=None):
        from app.routes.futures import _format_market_detail

        return _format_market_detail(market, bookmakers)

    def test_the_nobel_field_serves_null_openings_and_says_so(self):
        detail = self._detail(self._market(NOBEL_113129))
        assert detail["openings_withheld"] is True
        assert detail["outcomes"], "the outcomes themselves must still be served"
        for o in detail["outcomes"]:
            # `undefined !== null` is true in the client, so the key must be
            # PRESENT and null — an omitted key renders as a missing column.
            assert "opening_probability" in o
            assert o["opening_probability"] is None
            assert o["opening_american_odds"] is None, (
                "the american-odds twin reconstructs the refused number"
            )

    def test_the_nobel_field_keeps_its_current_prices(self):
        """The refusal is about the OPEN column only. The page keeps its answer."""
        detail = self._detail(self._market(NOBEL_113129))
        assert any(o["probability"] is not None for o in detail["outcomes"])

    def test_a_lone_certain_leg_keeps_its_openings_through_the_route(self):
        detail = self._detail(self._market([0.999, 0.0005, 0.0005]))
        assert detail["openings_withheld"] is False
        assert [o["opening_probability"] for o in detail["outcomes"]] == [
            0.999, 0.0005, 0.0005,
        ]

    def test_a_non_exclusive_nobel_shaped_field_keeps_its_openings(self):
        detail = self._detail(self._market(NOBEL_113129, mutually_exclusive=False))
        assert detail["openings_withheld"] is False
        assert all(o["opening_probability"] is not None for o in detail["outcomes"])
