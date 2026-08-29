"""CAL-P106 — the ladder-coherence predicate, pinned including its exemptions.

WHY THE FIRST TEST CLASS IS ABOUT THE FIXTURE. CAL-P105's finding was that the
one pin guarding ``ece_from_bins`` compared a function with itself on a fixture
that returned the same number under every treatment — so it was green for
reasons unrelated to the property it claimed. The remedy is the order used here:
**prove the specimens SEPARATE the treatments before using them to prove
anything.** ``TestTheSpecimensCanTellTheTreatmentsApart`` runs first and fails if
the ladder-unit and rung-unit readings of the specimen population ever coincide.

The specimens are production rows, quoted from CAL-P106's whole-population pull
(``artifacts/cal-p106/ladder_rows2_soccer_q.json``, 2,867 markets, 100 shards,
0 irreducible), so a future reader can find them again.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils import ladder_coherence
from app.utils.calibration_ece import calibration_error
from app.utils.ladder_coherence import (
    LADDER_ADJACENT_STEP,
    LADDER_COHERENCE_RULE_TEXT,
    OU_LINE_RE,
    adjacent_violations,
    ambiguous_families,
    cell_ece_pp,
    incoherent_families,
    ladder_family_key,
    ladder_is_incoherent,
    parse_ou_line,
    read_ladders,
)

# --- production specimens ---------------------------------------------------
# Over prices, by line. Every one of these was read out of production by
# CAL-P106; the comment on each is what makes it worth pinning.

#: A ladder that ran out of real prices at 5.5 and then flattened at ~0.49 for
#: three more rungs. The healthy half is genuinely monotone, so a rule that
#: condemns this ladder is condemning real rungs too — which is the ladder-unit
#: decision, taken deliberately.
SCOTLAND_BRAZIL = {1.5: 0.7750, 2.5: 0.5300, 3.5: 0.3000, 4.5: 0.1550,
                   5.5: 0.0700, 6.5: 0.4750, 7.5: 0.4900, 8.5: 0.4950}

#: The template. THREE different Bolivian league fixtures carry this ladder
#: byte-identically, with calibration_probability == opening_probability on
#: every rung. Its only violation is the flat 4.5/5.5 pair.
BOLIVIAN_TEMPLATE = {0.5: 0.6800, 1.5: 0.6050, 2.5: 0.5200,
                     3.5: 0.4050, 4.5: 0.2800, 5.5: 0.2800}

#: A ladder with no shape at all: six rungs inside 0.445-0.535.
PARAGUAY_FLAT = {0.5: 0.5100, 1.5: 0.5350, 2.5: 0.5300,
                 3.5: 0.5100, 4.5: 0.4450, 5.5: 0.4950}

#: A healthy ladder — strictly falling at every step. Must survive.
HEALTHY = {0.5: 0.9350, 1.5: 0.7100, 2.5: 0.4450, 3.5: 0.2300, 4.5: 0.0700}


def _rows(specimens: dict[str, dict[float, float]]) -> list[dict]:
    out = []
    for game, rungs in specimens.items():
        for line, price in rungs.items():
            out.append({
                "name": f"{game}: O/U {line}",
                "over_price": price,
                # Deliberately present and deliberately never read.
                "over_win": 1 if price > 0.5 else 0,
            })
    return out


ALL_SPECIMENS = {
    "Scotland vs. Brazil": SCOTLAND_BRAZIL,
    "Club The Strongest vs. Club Bolivar": BOLIVIAN_TEMPLATE,
    "Paraguay vs. Nicaragua": PARAGUAY_FLAT,
    "DR Congo vs. Uzbekistan": HEALTHY,
}


def _rung_unit_condemned(rows: list[dict]) -> set[tuple[str, float]]:
    """The rejected sibling rule: condemn only the rungs in a violating pair."""
    ladders: dict[str, dict[float, float]] = {}
    for row in rows:
        key = ladder_family_key(row["name"])
        line = parse_ou_line(row["name"])
        ladders.setdefault(key, {})[line] = row["over_price"]
    condemned: set[tuple[str, float]] = set()
    for key, rungs in ladders.items():
        for low, _lp, high, _hp in adjacent_violations(rungs):
            condemned.add((key, low))
            condemned.add((key, high))
    return condemned


class TestTheSpecimensCanTellTheTreatmentsApart:
    """The fixture check. If these fail, nothing below proves anything."""

    def test_the_population_contains_both_verdicts(self):
        condemned = incoherent_families(_rows(ALL_SPECIMENS))
        assert condemned, "no ladder is condemned — the fixture cannot see the rule"
        assert len(condemned) < len(ALL_SPECIMENS), (
            "every ladder is condemned — the fixture cannot see the exemption"
        )

    def test_ladder_unit_and_rung_unit_disagree_on_this_fixture(self):
        """The two units must give DIFFERENT answers here, or the ladder-unit
        decision is untested by these specimens."""
        rows = _rows(ALL_SPECIMENS)
        condemned_families = incoherent_families(rows)
        ladder_unit = {
            (ladder_family_key(r["name"]), parse_ou_line(r["name"]))
            for r in rows
            if ladder_family_key(r["name"]) in condemned_families
        }
        rung_unit = _rung_unit_condemned(rows)
        assert rung_unit < ladder_unit, (
            "the rung-unit rule must condemn a STRICT subset here; "
            f"ladder={len(ladder_unit)} rung={len(rung_unit)}"
        )

    def test_the_fixture_separates_ece_too(self):
        """A separation in membership that does not move the score would leave
        the ECE claims unexercised."""
        prices = [0.28, 0.28, 0.4950, 0.0700]
        keep = [1, 0, 0, 0]
        flip = [0, 1, 1, 1]
        assert cell_ece_pp(prices, keep) != cell_ece_pp(prices, flip)


class TestParseOuLine:
    def test_half_integer(self):
        assert parse_ou_line("Team A vs. Team B: O/U 2.5") == 2.5

    def test_integer_and_two_digit(self):
        assert parse_ou_line("A vs. B: O/U 3") == 3.0
        assert parse_ou_line("A vs. B: O/U 12.5") == 12.5

    def test_qualifier_before_the_token(self):
        assert parse_ou_line("IR Iran vs. New Zealand: 1st Half O/U 1.5") == 1.5

    def test_absent(self):
        assert parse_ou_line("Who wins the Premier League?") is None
        assert parse_ou_line("") is None
        assert parse_ou_line(None) is None

    def test_regex_needs_the_slash(self):
        """``OU 2.5`` is a different naming and is NOT silently accepted —
        widening the token is a population change, not a typo fix."""
        assert parse_ou_line("A vs. B: OU 2.5") is None
        assert OU_LINE_RE.search("O/U 2.5") is not None


class TestLadderFamilyKey:
    def test_rungs_of_one_game_share_a_key(self):
        a = ladder_family_key("CD Nublense vs. CD Palestino: O/U 2.5")
        b = ladder_family_key("CD Nublense vs. CD Palestino: O/U 5.5")
        assert a == b

    def test_a_qualifier_makes_a_DIFFERENT_ladder(self):
        """The 1st-half ladder and the full-match ladder price different
        events. Truncating at ``O/U`` would merge them; deleting the token
        keeps them apart."""
        half = ladder_family_key("IR Iran vs. New Zealand: 1st Half O/U 1.5")
        full = ladder_family_key("IR Iran vs. New Zealand: O/U 1.5")
        assert half != full
        assert "1st half" in half

    def test_text_AFTER_the_rung_also_identifies_the_ladder(self):
        """The mutant that found this test missing: truncating the name at the
        ``O/U`` token instead of deleting the token passes every other case in
        this class, and silently MERGES two ladders whose qualifier sits after
        the line. A corners ladder and a goals ladder on the same fixture would
        then be compared rung-for-rung and condemn each other."""
        goals = ladder_family_key("A vs. B: O/U 2.5")
        corners = ladder_family_key("A vs. B: O/U 2.5 Corners")
        assert goals != corners
        assert corners.endswith("corners")

    def test_whitespace_and_case_normalised(self):
        assert (ladder_family_key("A  vs.  B:   O/U 2.5")
                == ladder_family_key("a vs. b: O/U 3.5"))

    def test_none_for_a_non_ladder(self):
        assert ladder_family_key("Who wins the World Cup?") is None
        assert ladder_family_key(None) is None


class TestAdjacentViolations:
    def test_healthy_ladder_has_none(self):
        assert adjacent_violations(HEALTHY) == []

    def test_equal_adjacent_rungs_are_a_violation(self):
        """Two rungs one goal apart cannot carry the same probability: the
        difference between them is a real outcome."""
        violations = adjacent_violations(BOLIVIAN_TEMPLATE)
        assert [(v[0], v[2]) for v in violations] == [(4.5, 5.5)]

    def test_increasing_adjacent_rungs_are_a_violation(self):
        violations = adjacent_violations(SCOTLAND_BRAZIL)
        assert (5.5, 6.5) in [(v[0], v[2]) for v in violations]

    def test_non_adjacent_rungs_are_not_compared(self):
        """0.5 and 2.5 are two units apart. A real outcome sits between them
        twice over, and comparing them would import an assumption the step of
        one does not need."""
        assert adjacent_violations({0.5: 0.20, 2.5: 0.90}) == []
        assert LADDER_ADJACENT_STEP == 1.0

    def test_a_missing_rung_breaks_the_chain_rather_than_bridging_it(self):
        assert adjacent_violations({0.5: 0.20, 1.5: 0.10, 3.5: 0.95}) == []

    def test_a_none_price_takes_no_part(self):
        assert adjacent_violations({0.5: 0.20, 1.5: None}) == []

    def test_violations_carry_their_evidence(self):
        low, low_p, high, high_p = adjacent_violations(PARAGUAY_FLAT)[0]
        assert (low, high) == (0.5, 1.5)
        assert (low_p, high_p) == (0.51, 0.535)


class TestLadderIsIncoherent:
    def test_family_of_one_is_never_condemned(self):
        """Ruling 105's clause, carried across surfaces: a family of one is
        never structural, at any price. Here it is also simply untestable."""
        assert ladder_is_incoherent({5.5: 0.5000}) is False
        assert ladder_is_incoherent({0.5: 0.9999}) is False

    def test_empty_is_not_incoherent(self):
        assert ladder_is_incoherent({}) is False

    def test_healthy_survives(self):
        assert ladder_is_incoherent(HEALTHY) is False

    def test_each_production_specimen(self):
        assert ladder_is_incoherent(SCOTLAND_BRAZIL) is True
        assert ladder_is_incoherent(BOLIVIAN_TEMPLATE) is True
        assert ladder_is_incoherent(PARAGUAY_FLAT) is True

    def test_no_tolerance_at_the_price_floor(self):
        """Deliberate, and measured: over all 631 violating adjacent pairs in
        soccer/quantity, ZERO had both prices below 0.02, and ZERO ladders had
        only floor-level violations. A floor exemption would be a knob with no
        population behind it (ruling 083). Counts re-run on the shipped key by
        CAL-P107: `artifacts/cal-p106/violation_detail_soccer_q.json`."""
        assert ladder_is_incoherent({4.5: 0.0050, 5.5: 0.0050}) is True


class TestIncoherentFamilies:
    def test_end_to_end(self):
        condemned = incoherent_families(_rows(ALL_SPECIMENS))
        assert ladder_family_key("Scotland vs. Brazil: O/U 1.5") in condemned
        assert ladder_family_key("Paraguay vs. Nicaragua: O/U 0.5") in condemned
        assert ladder_family_key("DR Congo vs. Uzbekistan: O/U 0.5") not in condemned

    def test_condemns_the_WHOLE_ladder_including_its_healthy_rungs(self):
        """Scotland/Brazil's 1.5-5.5 rungs are individually monotone. They go
        too. This is the ladder-unit decision and it is asserted, not implied."""
        condemned = incoherent_families(_rows({"Scotland vs. Brazil": SCOTLAND_BRAZIL}))
        assert ladder_family_key("Scotland vs. Brazil: O/U 1.5") in condemned

    def test_a_row_with_no_rung_takes_no_part(self):
        rows = [{"name": "Who wins the league?", "over_price": 0.5}]
        assert incoherent_families(rows) == set()

    def test_a_row_with_no_price_takes_no_part(self):
        rows = [
            {"name": "A vs. B: O/U 0.5", "over_price": None},
            {"name": "A vs. B: O/U 1.5", "over_price": 0.9},
        ]
        assert incoherent_families(rows) == set()

    def test_a_duplicate_line_makes_the_family_UNREADABLE_not_condemned(self):
        """Two rows on the same (family, line) prove the KEY is wrong, never
        that the ladder is. This family would be condemned on its 0.5/1.5 pair
        if the duplicate were resolved by picking a winner; it is left alone."""
        rows = [
            {"name": "A vs. B: O/U 0.5", "over_price": 0.40},
            {"name": "A vs. B: O/U 0.5", "over_price": 0.90},
            {"name": "A vs. B: O/U 1.5", "over_price": 0.50},
        ]
        ladders = read_ladders(rows)
        assert ambiguous_families(ladders) == set(ladders)
        assert incoherent_families(rows) == set()

    def test_without_the_duplicate_the_same_family_IS_condemned(self):
        """The control for the test above: the exemption must be doing work,
        not agreeing with a verdict the rule would have reached anyway."""
        rows = [
            {"name": "A vs. B: O/U 0.5", "over_price": 0.40},
            {"name": "A vs. B: O/U 1.5", "over_price": 0.50},
        ]
        assert incoherent_families(rows) == {ladder_family_key("A vs. B: O/U 0.5")}


class TestTheKeyCollapseGuard:
    """The esports specimen. CAL-P106 ran this rule over ``esports/quantity``
    and the family key put **231 markets in ONE family** — those names do not
    carry the fixture. Without the guard the rule condemned the entire cell off
    ten arbitrary rows. A row-deleting rule fails toward keeping rows when its
    own premise is disproven."""

    def _collapsed(self, n: int = 40) -> list[dict]:
        # Many distinct matches, all named identically apart from the line.
        return [
            {"name": f"Map winner: O/U {1.5 + (i % 4)}", "over_price": 0.5 + 0.01 * i}
            for i in range(n)
        ]

    def test_the_collapse_is_detected(self):
        ladders = read_ladders(self._collapsed())
        assert len(ladders) == 1
        assert ambiguous_families(ladders) == set(ladders)
        assert ladders[next(iter(ladders))]["rows"] == 40

    def test_the_collapse_condemns_nothing(self):
        assert incoherent_families(self._collapsed()) == set()

    def test_a_clean_population_is_not_ambiguous(self):
        ladders = read_ladders(_rows(ALL_SPECIMENS))
        assert ambiguous_families(ladders) == set()

    def test_custom_keys(self):
        rows = [
            {"title": "A vs. B: O/U 0.5", "p": 0.30},
            {"title": "A vs. B: O/U 1.5", "p": 0.40},
        ]
        assert incoherent_families(rows, name_key="title", price_key="p")


class TestThePredicateNeverReadsAnOutcome:
    """A predicate fitted to is_winner cannot be holdout-validated, so the
    label-independence is a property worth pinning behaviourally rather than by
    reading the source."""

    def test_permuting_every_outcome_changes_nothing(self):
        rows = _rows(ALL_SPECIMENS)
        before = incoherent_families(rows)
        for row in rows:
            row["over_win"] = 1 - row["over_win"]
        assert incoherent_families(rows) == before

    def test_deleting_the_outcome_field_entirely_changes_nothing(self):
        rows = _rows(ALL_SPECIMENS)
        before = incoherent_families(rows)
        stripped = [{"name": r["name"], "over_price": r["over_price"]} for r in rows]
        assert incoherent_families(stripped) == before


class TestCellEce:
    def test_delegates_to_the_canonical_definition(self):
        prices = [0.05, 0.15, 0.15, 0.95, 0.95, 0.55]
        winners = [0, 0, 1, 1, 1, 0]
        expected = calibration_error(
            [
                {"n": 1, "winners": 0, "sum_prob": 0.05},
                {"n": 2, "winners": 1, "sum_prob": 0.30},
                {"n": 1, "winners": 0, "sum_prob": 0.55},
                {"n": 2, "winners": 2, "sum_prob": 1.90},
            ],
            min_bin_n=0,
        )
        assert cell_ece_pp(prices, winners) == expected

    def test_p_equals_one_lands_in_bin_nine_not_an_eleventh_bin(self):
        assert cell_ece_pp([1.0], [1]) == 0.0

    def test_empty_is_none_never_zero(self):
        assert cell_ece_pp([], []) is None

    def test_mismatched_lengths_raise(self):
        with pytest.raises(ValueError):
            cell_ece_pp([0.5], [1, 0])


class TestRuleText:
    def test_names_the_unit_and_the_exemption(self):
        text = LADDER_COHERENCE_RULE_TEXT.lower()
        assert "ladder is the unit" in text
        assert "family of one" in text
        assert "read-side only" in text


class TestTheDocstringTableMatchesItsArtifact:
    """The headline table is the thing people quote, so it is pinned to the run.

    CAL-P107 found this table had been written from an exploratory ``game_key``
    grouping while the module shipped ``ladder_family_key`` — 3.42 pp advertised
    against 3.76 pp delivered. Nothing failed, because no test read the prose.
    That is CAL-P105's defect exactly: a number whose producing code is not
    named cannot be re-found, and a docstring is where they go to rot.

    This binds the two together in both directions. Re-run the fold and the
    artifact moves -> red. Edit the table by hand -> red. The only green is
    editing both to the same measured value.
    """

    ARTIFACT = (
        Path(__file__).resolve().parents[2]
        / "artifacts" / "cal-p106" / "rule_a_vs_b_soccer_q.json"
    )

    def _artifact(self) -> dict:
        if not self.ARTIFACT.exists():  # pragma: no cover - see the skip reason
            pytest.skip(f"artifact not present: {self.ARTIFACT}")
        return json.loads(self.ARTIFACT.read_text())

    def test_the_artifact_is_a_complete_sweep(self):
        """A partial sweep would make every row below it a smaller population's
        number wearing the whole population's label (gotcha #53)."""
        data = self._artifact()
        assert data["irreducible"] == []
        assert data["population_markets"] == 2854

    @pytest.mark.parametrize("treatment", ["baseline", "ruleA_keep", "ruleB_keep"])
    def test_each_row_of_the_table_is_in_the_docstring(self, treatment):
        row = self._artifact()[treatment]
        doc = ladder_coherence.__doc__ or ""
        legs = f"{row['legs']:,}"
        assert legs in doc, f"{treatment}: legs {legs} absent from the docstring"
        assert f"{row['ece']:.2f}" in doc, (
            f"{treatment}: ECE {row['ece']:.2f} absent from the docstring"
        )

    def test_the_ladder_unit_still_beats_the_rung_unit(self):
        """The module's whole design decision. If this ever inverts, the
        docstring's argument is wrong and the prose must go, not the test."""
        data = self._artifact()
        assert data["ruleA_keep"]["ece"] < data["ruleB_keep"]["ece"]
        assert data["ruleB_keep"]["ece"] < data["baseline"]["ece"]

    def test_the_kept_cell_is_not_claimed_to_be_under_the_bar(self):
        """3.76 pp is still over Alex's 3.0 bar. The docstring says so; a future
        edit that rounds this into a success story goes red here."""
        assert self._artifact()["ruleA_keep"]["ece"] > 3.0
        assert "still over Alex's bar" in (ladder_coherence.__doc__ or "")
