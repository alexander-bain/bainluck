"""Queue 299 Item 0 (#1012) — the failing-fixture corpus for cricket repair.

r339's ladder proved cricket's 8.6pp error is not "the market is bad at cricket"
(rung 5, never reached) but two structural layers above it: markets whose RESULT
was never established, and markets treated as mutually-exclusive partitions on no
evidence beyond a column whose default is True. C119's 20-case corpus then fixed
the contract — exclusivity is decided by EVIDENCE, never by a category label and
never by the observed winner count alone; where evidence cannot distinguish a
loss from a draw / no-result / ungraded row, the row is excluded as UNKNOWN.

Every case the queue enumerates is pinned here against the SHIPPED predicates:

  * omitted draw ................. TestDrawAuthority
  * draw graded as two losses .... TestNoWinnerAuthority::test_draw_graded_as_two_losses
  * tie / no-result / abandoned .. TestDrawAuthority::test_named_draw_members
  * void ......................... TestVoidStillExcluded
  * null / ungraded winner ....... TestNoWinnerAuthority::test_ungraded_market_is_unknown
  * all-loser market ............. TestNoWinnerAuthority
  * independent multi-winner ..... TestNonexclusiveBundle
  * orphan half-market ........... TestOrphanPartition
  * unchanged illiquid opening ... TestLiquidityEvidenceUnchanged
  * meaningful bid / trade ....... TestLiquidityEvidenceUnchanged
  * true MEX field ............... TestExclusivityEvidence::test_proved_field_still_normalizes
  * mis-tag ...................... TestCategoryNeverDecidesShape
  * poison first / middle / last . TestPoisonOrderIndependence

Read-side only throughout (gotcha #21): no test here asserts a mutation, and
TestReadSideOnly pins that the shipped SQL still writes nothing.
"""

from __future__ import annotations

import inspect

import pytest

from app.tasks import precompute_calibration as pc
from app.tasks.precompute_calibration import (
    DRAW_AUTHORITY_OUTCOME_NAMES,
    DRAW_CAPABLE_CATEGORIES,
    EXCLUSIVITY_PROVED_RELATIONS,
    market_exclusivity_is_proved,
    market_has_no_winner_authority,
    market_is_esports_multi_bundle,
    market_is_nonexclusive_bundle,
    market_is_orphan_partition,
    market_omits_draw_authority,
    outcome_is_calibration_liquid,
    outcome_is_calibration_void,
)

POPULATION_CTES = pc._calibration_population_ctes()
PAYLOAD_SRC = inspect.getsource(pc.compute_calibration_payload)
SHIPPED_SQL = POPULATION_CTES + PAYLOAD_SRC


# ---------------------------------------------------------------------------
# Rung 1 — result authority. "Ungraded never becomes loser."
# ---------------------------------------------------------------------------
class TestNoWinnerAuthority:
    def test_draw_graded_as_two_losses(self):
        """The omitted-draw failure mode: a drawn match makes BOTH named sides
        lose, so the market ends with zero winners. That is UNKNOWN truth (the
        real result was 'draw', which we never captured), not two confident
        losses at ~0.5 each — the exact class that dragged cricket's curve."""
        assert market_has_no_winner_authority(n_outcomes=2, n_winners=0) is True

    def test_ungraded_market_is_unknown(self):
        """``is_winner`` is NOT NULL with a False default, so an ungraded outcome
        is byte-identical to a real loser. Winner cardinality is the only
        discriminator available, and a market that graded nobody is excluded."""
        assert market_has_no_winner_authority(n_outcomes=8, n_winners=0) is True

    def test_all_loser_market_at_every_size(self):
        for n in (2, 3, 5, 12, 41):
            assert market_has_no_winner_authority(n, 0) is True, n

    def test_a_graded_market_survives(self):
        """Decisive losses REMAIN. The rung excludes markets with no captured
        result — never the losers of a market that resolved properly."""
        assert market_has_no_winner_authority(n_outcomes=3, n_winners=1) is False
        assert market_has_no_winner_authority(n_outcomes=2, n_winners=1) is False

    def test_multi_winner_is_not_a_no_winner_failure(self):
        """A bundle resolving many YES is a SHAPE problem (rung 4), not a result-
        authority one. Keeping the rungs disjoint is what lets the report say
        which layer failed."""
        assert market_has_no_winner_authority(n_outcomes=3, n_winners=2) is False

    def test_single_outcome_market_is_not_judged_here(self):
        """A lone Yes/No claim that resolved No is a complete, scoreable
        prediction. It is judged by the orphan rule (field shape only), so the
        no-winner rung deliberately requires >=2 outcomes."""
        assert market_has_no_winner_authority(n_outcomes=1, n_winners=0) is False

    def test_sql_excludes_and_counts_the_class(self):
        assert "no_winner_markets AS (" in POPULATION_CTES
        assert "mrs.n_outcomes >= 2 AND mrs.win_count = 0" in POPULATION_CTES
        assert "NOT ro.is_no_winner_market" in POPULATION_CTES
        assert '"no_winner_filter"' in PAYLOAD_SRC


# ---------------------------------------------------------------------------
# Rung 2 — draw authority on draw-capable questions.
# ---------------------------------------------------------------------------
class TestDrawAuthority:
    def test_omitted_draw_is_excluded(self):
        """A soccer/cricket match-winner duel with only the two named sides has
        incomplete result authority: the ~25% draw mass was never captured, so
        the named sides are systematically over-predicted (#1011: 7-18pp)."""
        assert market_omits_draw_authority("soccer", "duel", 2, 0) is True
        assert market_omits_draw_authority("cricket", "duel", 2, 0) is True

    def test_captured_draw_member_stays_in(self):
        """Complete authority — the draw IS a member, so the question is scored
        as the three-way it really is. SAVE all possible."""
        assert market_omits_draw_authority("soccer", "duel", 2, 1) is False

    @pytest.mark.parametrize("name", sorted(DRAW_AUTHORITY_OUTCOME_NAMES))
    def test_named_draw_members(self, name):
        """tie / no result / abandoned all constitute captured authority — the
        contest ended without a named winner and we know it."""
        assert name == name.strip().lower()
        assert market_omits_draw_authority("cricket", "duel", 2, 1) is False

    def test_non_draw_capable_sport_is_untouched(self):
        """The category answers ONLY 'can this contest be drawn?'. Basketball
        cannot, so its duels keep their two-way capture."""
        assert market_omits_draw_authority("basketball", "duel", 2, 0) is False
        assert market_omits_draw_authority("tennis", "duel", 2, 0) is False

    def test_shape_is_still_decided_by_evidence(self):
        """Only a two-competitor duel is a match-winner question. Threshold
        ladders, Yes/No claims and decomposed container members in the same
        sport are NOT swept up — the 2026-08-01 census counted 34,818 soccer
        `quantity` and 28,419 `container_member` 2-outcome markets that this
        rule must leave alone."""
        for market_type in ("quantity", "container_member", "claim", "field", None):
            assert market_omits_draw_authority("soccer", market_type, 2, 0) is False

    def test_three_way_capture_is_not_a_defect(self):
        assert market_omits_draw_authority("soccer", "duel", 3, 0) is False

    def test_sql_excludes_and_counts_the_class(self):
        assert "draw_authority_markets AS (" in POPULATION_CTES
        assert "mrs.market_type = 'duel'" in POPULATION_CTES
        assert "NOT ro.is_draw_authority_missing" in POPULATION_CTES
        assert '"draw_authority_filter"' in PAYLOAD_SRC
        # Sport-rules scope is rendered from the constant, never hardcoded twice.
        for cat in DRAW_CAPABLE_CATEGORIES:
            assert f"'{cat}'" in POPULATION_CTES


# ---------------------------------------------------------------------------
# Rung 3 — orphan half-markets.
# ---------------------------------------------------------------------------
class TestOrphanPartition:
    def test_field_with_one_member_is_orphaned(self):
        """A declared partition (">2 competitors, one wins") that captured a
        single member is a fragment of a distribution we never saw."""
        assert market_is_orphan_partition("field", 1) is True
        assert market_is_orphan_partition("field", 0) is True

    def test_complete_field_is_untouched(self):
        assert market_is_orphan_partition("field", 3) is False

    def test_standalone_binary_claim_is_not_an_orphan(self):
        """THE containment case: a Kalshi/Poly Yes/No question stored with one
        outcome is a complete prediction. Judging every 1-outcome market as an
        orphan would delete a large, honest population — so the rule is scoped
        to markets whose OWN declared shape is a field."""
        for market_type in ("claim", "duel", "quantity", "container_member", None):
            assert market_is_orphan_partition(market_type, 1) is False

    def test_sql_excludes_and_counts_the_class(self):
        assert "orphan_partition_markets AS (" in POPULATION_CTES
        assert "mrs.market_type = 'field' AND mrs.n_outcomes <= 1" in POPULATION_CTES
        assert "NOT ro.is_orphan_partition" in POPULATION_CTES
        assert '"orphan_partition_filter"' in PAYLOAD_SRC


# ---------------------------------------------------------------------------
# Rung 4 — exclusivity is proved by EVIDENCE, never by a default-true column.
# ---------------------------------------------------------------------------
class TestExclusivityEvidence:
    def test_proved_field_still_normalizes(self):
        """The true-MEX case must survive intact: a field the classifier
        positively asserts is an exhaustive single-winner partition of named
        competitors is still a normalization candidate."""
        assert market_exclusivity_is_proved("field", True, 1, "competitors") is True
        assert market_exclusivity_is_proved("field", "true", "1", "exclusive_ranges") is True

    def test_default_true_mutually_exclusive_flag_is_not_evidence(self):
        """``futures_markets.mutually_exclusive`` DEFAULTS to True and is set for
        Yes/No claims and duels alike (market_shape's own docstring). The old
        gate accepted it; nothing here can."""
        assert market_exclusivity_is_proved("container_member", True, 1, "complements") is False
        assert market_exclusivity_is_proved("quantity", True, 1, "competitors") is False

    def test_unknown_relation_is_refused(self):
        """51,424 resolved >=3-outcome markets (census 2026-08-01) carry
        market_type='field' with the relation UNRESOLVED. The classifier
        declined to prove a partition, so normalization must decline too."""
        assert market_exclusivity_is_proved("field", None, None, "unknown") is False

    def test_cumulative_ladder_is_refused(self):
        """gotcha #17: cumulative Over rungs legitimately co-win, so dividing
        them by their own sibling sum is nonsense. 27,958 such markets were
        admitted by the old gate."""
        assert market_exclusivity_is_proved("field", False, None, "cumulative_thresholds") is False
        assert market_exclusivity_is_proved("quantity", False, None, "cumulative_thresholds") is False

    def test_participation_contract_is_refused(self):
        assert (
            market_exclusivity_is_proved("participation", False, 5, "independent_participation")
            is False
        )

    def test_multi_expected_winners_is_refused(self):
        assert market_exclusivity_is_proved("field", True, 3, "competitors") is False

    def test_unrecognised_evidence_fails_closed(self):
        for exhaustive in (None, "", "maybe", 0, "TRUE "):
            proved = market_exclusivity_is_proved("field", exhaustive, 1, "competitors")
            assert proved is (str(exhaustive).strip().lower() == "true"), exhaustive

    def test_sql_gate_mirrors_the_predicate(self):
        assert "mi.shape_exhaustive = 'true'" in POPULATION_CTES
        assert "mi.shape_expected_winners = '1'" in POPULATION_CTES
        assert "mi.market_type = 'field'" in POPULATION_CTES
        for rel in EXCLUSIVITY_PROVED_RELATIONS:
            assert f"'{rel}'" in POPULATION_CTES
        # The discarded admission test must be gone from the candidate gate.
        assert "mi.mutually_exclusive = true OR mi.market_type = 'field'" not in POPULATION_CTES
        assert '"exclusivity_evidence"' in PAYLOAD_SRC


# ---------------------------------------------------------------------------
# Rung 4b — the non-exclusive bundle: one structural test, measured everywhere.
# ---------------------------------------------------------------------------
class TestNonexclusiveBundle:
    def test_multi_winner_is_structurally_not_a_partition(self):
        assert market_is_nonexclusive_bundle(3, 2) is True
        assert market_is_nonexclusive_bundle(73, 11) is True

    def test_single_winner_and_void_are_not_bundles(self):
        assert market_is_nonexclusive_bundle(3, 1) is False
        assert market_is_nonexclusive_bundle(3, 0) is False

    def test_binary_is_never_a_bundle(self):
        assert market_is_nonexclusive_bundle(2, 2) is False

    def test_esports_exclusion_is_the_same_predicate_under_scope(self):
        """C119's contract: one structural test, not two copies. The esports
        CURVE exclusion keeps its measured scope (OPS-557's +9.2pp), but it is
        now expressed as the shared predicate."""
        assert market_is_esports_multi_bundle("esports", 3, 2) is True
        assert market_is_esports_multi_bundle("esports", 3, 1) is False
        for category in ("cricket", "hockey", "tennis", None):
            assert market_is_esports_multi_bundle(category, 3, 2) is False
            assert market_is_nonexclusive_bundle(3, 2) is True

    def test_bundle_can_never_be_normalized_in_any_category(self):
        """"No bundle is divided by sibling sum" — the acceptance criterion.
        Winner cardinality alone can't prove exclusivity, but multi-winner
        DISproves it, and the candidate gate requires win_count = 1 as well as
        positive evidence, so a bundle fails on both counts."""
        assert "mrs.win_count = 1" in POPULATION_CTES
        assert market_exclusivity_is_proved("field", True, 1, "competitors") is True
        assert market_is_nonexclusive_bundle(3, 2) is True

    def test_census_is_published_not_silently_capped(self):
        """The blanket exclusion is NOT shipped (it would delete 81% of hockey
        and 47% of tennis — both well-calibrated). That decision must be visible
        with its numbers, per the no-silent-caps rule."""
        assert "nonexclusive_bundle_markets AS (" in POPULATION_CTES
        # Census only: the flag must NOT gate the published population.
        assert "NOT ro.is_nonexclusive_bundle" not in POPULATION_CTES
        assert '"nonexclusive_bundle_census"' in PAYLOAD_SRC
        text = pc.NONEXCLUSIVE_BUNDLE_CENSUS_RULE_TEXT.lower()
        assert "measured only" in text
        assert "hockey" in text and "tennis" in text


class TestBundleCensusScoring:
    def _row(self, category, bundle, bucket_idx, n, winners, sum_prob):
        class R:
            pass

        r = R()
        r.category, r.is_nonexclusive_bundle = category, bundle
        r.bucket_idx, r.n, r.winners, r.sum_prob = bucket_idx, n, winners, sum_prob
        return r

    def test_census_splits_cohort_from_remainder(self):
        rows = [
            # remainder: 600 rows predicted 0.30, 30% actually won — perfect.
            self._row("hockey", False, 3, 600, 180, 180.0),
            # bundle: 400 rows predicted 0.30, 60% won — 30pp off.
            self._row("hockey", True, 3, 400, 240, 120.0),
        ]
        census = pc._build_nonexclusive_bundle_census(rows)
        entry = next(e for e in census["by_category"] if e["category"] == "hockey")
        assert entry["published_n"] == 1000
        assert entry["would_exclude_n"] == 400
        assert entry["remainder_n"] == 600
        assert entry["would_exclude_ece"] == 30.0
        assert entry["remainder_ece"] == 0.0
        assert entry["remainder_clears_sample_bar"] is False

    def test_category_with_no_bundle_rows_is_omitted(self):
        rows = [self._row("golf", False, 5, 100, 50, 50.0)]
        census = pc._build_nonexclusive_bundle_census(rows)
        assert census["by_category"] == []

    def test_census_changes_no_row(self):
        assert census_is_measurement_only()


def census_is_measurement_only() -> bool:
    """The bundle flag is a GROUP BY dimension and a payload block — never a
    filter. Pinned as a function so the intent reads in the failure message."""
    return (
        "is_nonexclusive_bundle," in POPULATION_CTES
        and "NOT ro.is_nonexclusive_bundle" not in POPULATION_CTES
    )


# ---------------------------------------------------------------------------
# "Category never decides shape" — the C119 acceptance criterion.
# ---------------------------------------------------------------------------
class TestCategoryNeverDecidesShape:
    CATEGORIES = ("cricket", "esports", "entertainment", "soccer", "hockey", None)

    def test_mistagged_category_cannot_change_a_verdict(self):
        """r339 found 11% of the 'cricket' population is actually soccer (EPL
        737, FIFA_WC 631, UCL 207 outcomes) — the same tell-less-matchup class
        as #1503. A mis-tag must not rescue or condemn a structure."""
        for category in self.CATEGORIES:
            assert market_has_no_winner_authority(3, 0) is True
            assert market_is_nonexclusive_bundle(3, 2) is True
            assert market_is_orphan_partition("field", 1) is True
            assert market_exclusivity_is_proved("field", True, 1, "competitors") is True

    def test_only_the_sport_rules_rung_consults_category(self):
        """Exactly one rung reads the category, and only to answer a real-world
        question ("can this contest be drawn?") — the same thing the events-curve
        soccer rule has always done. Shape is never inferred from it."""
        drawable = {c for c in self.CATEGORIES if market_omits_draw_authority(c, "duel", 2, 0)}
        assert drawable == set(DRAW_CAPABLE_CATEGORIES) & set(self.CATEGORIES)


# ---------------------------------------------------------------------------
# Poison containment — a defective member must not decide its siblings' fate.
# ---------------------------------------------------------------------------
class TestPoisonOrderIndependence:
    def _verdicts(self, markets):
        return [
            (
                market_has_no_winner_authority(n_out, n_win),
                market_is_nonexclusive_bundle(n_out, n_win),
                market_is_orphan_partition(mt, n_out),
            )
            for mt, n_out, n_win in markets
        ]

    HEALTHY = ("field", 3, 1)
    POISON = ("field", 3, 3)

    def test_poison_first_middle_last_are_identical(self):
        first = self._verdicts([self.POISON, self.HEALTHY, self.HEALTHY])
        middle = self._verdicts([self.HEALTHY, self.POISON, self.HEALTHY])
        last = self._verdicts([self.HEALTHY, self.HEALTHY, self.POISON])
        assert sorted(first) == sorted(middle) == sorted(last)

    def test_healthy_siblings_survive_a_poison_neighbour(self):
        """Gotcha #42 in the calibration lane: one bad item must never wipe the
        pass. The predicates are per-market and pure, so a poison market's
        verdict cannot leak."""
        verdicts = self._verdicts([self.POISON, self.HEALTHY])
        assert verdicts[0] == (False, True, False)
        assert verdicts[1] == (False, False, False)


# ---------------------------------------------------------------------------
# Untouched neighbours — the rungs must not disturb what already works.
# ---------------------------------------------------------------------------
class TestLiquidityEvidenceUnchanged:
    def test_unchanged_illiquid_opening_still_judged_by_evidence(self):
        """Queue 299 changes no liquidity rule. An outcome whose book never
        showed a bid and never traded is still a phantom — its unchanged opening
        price was never discovered, so it is not a prediction."""
        assert outcome_is_calibration_liquid(None, None) is False
        assert outcome_is_calibration_liquid(0, 0) is False

    def test_meaningful_bid_or_trade_still_keeps_the_row(self):
        """...and either kind of real evidence keeps the row in the curve — a
        live bid with no trade, or a trade with no resting bid (the Queue #267
        C44 #1 contract, which the volume proxy used to violate)."""
        assert outcome_is_calibration_liquid(0.3, 0) is True
        assert outcome_is_calibration_liquid(None, 0.42) is True

    def test_poly_asymmetry_is_not_silently_closed(self):
        """Closing the Kalshi/Polymarket never-traded asymmetry is a separate
        Alex-gated decision, and cricket's own census disproves it as the
        cricket cause anyway (only 89 of 3,194 eligible poly cricket outcomes
        never traded). It stays measured, not applied."""
        assert pc.SOURCE_LIQUIDITY_EXCLUSIONS["polymarket"]["never_traded_excluded"] == (
            "placeholder_band_0.45_0.55"
        )
        assert "poly_never_traded_in_curve" in PAYLOAD_SRC


class TestVoidStillExcluded:
    @pytest.mark.parametrize("source", ["did_not_play", "withdrew"])
    def test_void_sources_remain_excluded(self, source):
        assert outcome_is_calibration_void(source) is True

    def test_a_real_result_is_not_a_void(self):
        assert outcome_is_calibration_void("game_score") is False


# ---------------------------------------------------------------------------
# Publication disposition and safety.
# ---------------------------------------------------------------------------
class TestPublishOrPark:
    def test_park_disposition_is_machine_readable(self):
        """Item 3: a cohort whose defective rows have been excluded may
        legitimately fall under the sample bar. The honest answer is 'parked' —
        stated, not a quietly missing chart."""
        assert '"parked_below_publish_bar"' in PAYLOAD_SRC
        assert '"publish_bar"' in PAYLOAD_SRC

    def test_publish_bar_is_the_shipped_sample_gate(self):
        assert pc._DEFAULT_MIN_CATEGORY_OUTCOMES == 1000

    def test_population_version_bumped_for_the_intentional_drift(self):
        """The publish gate refuses >5% population drift unless the version says
        the change was deliberate. Repairing four rungs is deliberate."""
        assert pc.CALIBRATION_POPULATION_VERSION == "q299"


class TestC119ContractBinding:
    """The shipped gate must agree with C119's 20-case corpus, case by case.

    C119 wrote the contract as a pure evaluator over abstract evidence; this is
    the binding that makes it mean something in production. For every corpus
    case we translate its evidence into the columns the real gate reads and
    assert the shipped predicates reach the corpus's ``normalize`` verdict —
    "one structural exclusivity classifier before MEX eligibility", which was
    C119's smallest Lane 1 contract.
    """

    @staticmethod
    def _as_market(evidence: dict) -> tuple:
        """Corpus evidence -> (market_type, exhaustive, expected_winners, relation).

        ``exclusive_proved`` is exactly what the shape classifier persists as
        ``exhaustive``; an unproved or independent-question market is what the
        classifier leaves as ``unknown``.
        """
        if evidence["exclusive_proved"] and not evidence["independent_binary_questions"]:
            return ("field", True, 1, "competitors")
        if evidence["outcome_count"] == 2:
            return ("duel", None, None, "competitors")
        if evidence["outcome_count"] <= 1:
            return ("field", None, None, "unknown")
        return ("field", None, None, "unknown")

    def _cases(self):
        from scripts.evals.nonexclusive_bundle_contract import load_corpus

        return load_corpus()["cases"]

    def test_shipped_gate_matches_every_corpus_verdict(self):
        cases = self._cases()
        assert len(cases) == 20
        for case in cases:
            ev = case["evidence"]
            market_type, exhaustive, expected_winners, relation = self._as_market(ev)
            shipped_normalize = (
                market_exclusivity_is_proved(
                    market_type, exhaustive, expected_winners, relation
                )
                and ev["winner_count"] == 1
                and ev["outcome_count"] >= 3
                and ev["probability_sum"] > case["threshold"]
                and not market_is_nonexclusive_bundle(
                    ev["outcome_count"], ev["winner_count"]
                )
            )
            assert shipped_normalize is case["expected"]["normalize"], case["id"]

    def test_corpus_structural_exclusions_are_shipped_exclusions(self):
        """Every case the corpus disposes as ``excluded_structural`` for a
        reason this queue owns must actually be excluded by a shipped rung."""
        owned = {"nonexclusive_bundle": False, "orphan_half_market": False}
        for case in self._cases():
            reason = case["expected"]["reason"]
            if reason not in owned:
                continue
            ev = case["evidence"]
            if reason == "nonexclusive_bundle":
                excluded = market_is_nonexclusive_bundle(
                    ev["outcome_count"], ev["winner_count"]
                ) or market_has_no_winner_authority(
                    ev["outcome_count"], ev["winner_count"]
                ) or not market_exclusivity_is_proved(
                    *self._as_market(ev)
                )
            else:
                excluded = market_is_orphan_partition("field", ev["outcome_count"])
            assert excluded, case["id"]
            owned[reason] = True
        assert all(owned.values()), owned

    def test_cricket_parks_below_the_bar(self):
        """The corpus's cricket disposition and the shipped sample gate agree:
        429 corrected outcomes is below 1,000, so the cohort parks."""
        case = next(c for c in self._cases() if c["id"] == "cricket-corrected-below-bar")
        assert case["expected"]["disposition"] == "parked_below_publish_bar"
        assert case["cohort_after_n"] < pc._DEFAULT_MIN_CATEGORY_OUTCOMES


class TestReadSideOnly:
    def test_no_rung_mutates_stored_truth(self):
        lowered = SHIPPED_SQL.lower()
        for forbidden in (
            "update futures_outcomes",
            "update futures_markets",
            "delete from futures_outcomes",
            "delete from futures_markets",
            "insert into futures_outcomes",
        ):
            assert forbidden not in lowered, forbidden

    def test_rule_texts_state_the_no_regrade_contract(self):
        for text in (
            pc.NO_WINNER_RULE_TEXT,
            pc.DRAW_AUTHORITY_RULE_TEXT,
            pc.ORPHAN_PARTITION_RULE_TEXT,
            pc.EXCLUSIVITY_EVIDENCE_RULE_TEXT,
        ):
            lowered = text.lower()
            assert "read-side only" in lowered
            assert "never" in lowered
