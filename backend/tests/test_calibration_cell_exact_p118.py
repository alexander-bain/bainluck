"""CAL-P118 — guards for the LADDER dimension, and for the pre-pass it needs.

CAL-P117's suite guards that a dimension's ``CASE`` still says what the rule it
benches says. This one guards a different property, and the reason it needs its
own suite is that the ladder dimension is the first on this rail whose verdict
is **not** computable inside the chunked query at all.

An Over/Under ladder is a set of markets sharing a name modulo the rung. Nothing
makes their ids contiguous, so a verdict computed inside a chunk is a verdict
computed on whichever rungs happened to fall on this side of the boundary — and
a partial ladder is systematically MORE coherent than the whole one, because
the violating pair may be the one that got cut. That failure is silent, it is
one-directional, and it makes a rule look smaller than it is. The pre-pass
exists to make it impossible, and these tests exist to keep the pre-pass.

The tests marked **SILENT** below are the ones whose breakage still produces a
complete, plausible, well-formed table.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cce = _load("calibration_cell_exact")


#: One synthetic cell exercising every arm the rule can produce. Prices are the
#: Over leg, which is the only leg the predicate reads.
#:
#:   1-3   one family, rungs 0.5/1.5/2.5 priced 0.9/0.7/0.7 — the equal adjacent
#:         pair is the flat templated ladder, the largest violating shape
#:   4-5   one family, strictly falling — the KEEP control
#:   6     a family of one rung — never condemned (ruling 105)
#:   7-9   a family whose key carries two rows on the same line — AMBIGUOUS, so
#:         the rule's own premise is disproven and it fails toward keeping
#:   10    no rung token at all
#:   11    a rung with no Over price
SPECIMENS = [
    {"market_id": 1, "name": "A vs. B: O/U 0.5", "over_price": 0.9},
    {"market_id": 2, "name": "A vs. B: O/U 1.5", "over_price": 0.7},
    {"market_id": 3, "name": "A vs. B: O/U 2.5", "over_price": 0.7},
    {"market_id": 4, "name": "C vs. D: O/U 0.5", "over_price": 0.9},
    {"market_id": 5, "name": "C vs. D: O/U 1.5", "over_price": 0.6},
    {"market_id": 6, "name": "E vs. F: O/U 1.5", "over_price": 0.6},
    {"market_id": 7, "name": "G vs. H: O/U 1.5", "over_price": 0.6},
    {"market_id": 8, "name": "G vs. H: O/U 1.5", "over_price": 0.9},
    {"market_id": 9, "name": "G vs. H: O/U 2.5", "over_price": 0.99},
    {"market_id": 10, "name": "no rung in this name", "over_price": 0.5},
    {"market_id": 11, "name": "I vs. J: O/U 1.5", "over_price": None},
]


class TestThePredicateIsTheShippedOne:
    """CAL-P097's hazard: a fold that paraphrases its rule benches a rule
    nobody will ship. CERT-403B blocked a whole apply on exactly that."""

    def test_the_verdict_functions_are_the_modules_own_objects(self):
        from app.utils import ladder_coherence as lc

        assert cce.incoherent_families is lc.incoherent_families
        assert cce.ambiguous_families is lc.ambiguous_families
        assert cce.ladder_family_key is lc.ladder_family_key
        assert cce.parse_ou_line is lc.parse_ou_line
        assert cce.read_ladders is lc.read_ladders

    def test_the_script_does_not_compile_a_rung_regex_of_its_own(self):
        """SILENT. A second copy of ``O/U (\\d+...)`` in this file would keep
        working and would stop tracking the module on the next edit to either.

        The rung is parsed in exactly one place — ``parse_ou_line`` — and this
        file is not allowed to own a pattern at all. The single ``O/U`` string
        literal it may carry is the SQL PREFILTER, which is a coarse superset
        and is guarded separately in ``TestThePrefilterCannotHideARung``.
        """
        src = (SCRIPTS / "calibration_cell_exact.py").read_text()
        assert "re.compile" not in src
        # Prose mentions "O/U" freely; a PATTERN is the one that also carries a
        # metacharacter, and there may be exactly one of those.
        quoted = [m for m in re.findall(r"'[^'\n]*'|\"[^\"\n]*\"", src)
                  if "O/U" in m and re.search(r"[\[\\+*?]", m)]
        assert quoted == ["'O/U[[:space:]]+[0-9]'"], quoted

    def test_the_copied_module_still_carries_the_clause_it_was_copied_for(self):
        """The predicate was taken from ``program/calibration-99`` verbatim, and
        the whole reason to prefer it over a rung-level rule is one clause."""
        from app.utils import ladder_coherence as lc

        assert lc.LADDER_ADJACENT_STEP == 1.0
        assert ("EVERY rung of that ladder is excluded"
                in lc.LADDER_COHERENCE_RULE_TEXT)
        assert ("A family of one rung is never condemned"
                in lc.LADDER_COHERENCE_RULE_TEXT)


class TestThePartitionIsTheRule:
    """Every arm, on specimens that can tell the arms apart."""

    @pytest.fixture(scope="class")
    def part(self):
        return cce.ladder_partition(SPECIMENS)

    def test_the_whole_family_falls_not_only_the_violating_pair(self, part):
        """Ruling 111's clause, and the 5.95-vs-3.76 measurement behind it.
        Market 1 is in no violating pair of its own; it falls because its
        ladder does."""
        assert part["drop"] == {1, 2, 3}

    def test_a_coherent_ladder_and_a_family_of_one_are_kept(self, part):
        assert part["coherent"] == {4, 5, 6}

    def test_an_ambiguous_family_is_kept_and_named(self, part):
        """SILENT, and the one that already bit: on ``esports/quantity`` this
        key collapsed 231 markets into one family. Folding ambiguous into
        ``coherent`` would hide a key collapse behind a clean-looking KEEP."""
        assert part["ambiguous"] == {7, 8, 9}
        assert part["census"]["families_ambiguous"] == 1

    def test_the_three_arms_are_disjoint(self, part):
        assert not (part["drop"] & part["ambiguous"])
        assert not (part["drop"] & part["coherent"])
        assert not (part["ambiguous"] & part["coherent"])

    def test_a_row_the_predicate_cannot_place_is_in_no_arm(self, part):
        """A market with no rung or no Over price is not a row the rule kept.
        gotcha #53: "it returned" is not "it worked"."""
        placed = part["drop"] | part["ambiguous"] | part["coherent"]
        assert 10 not in placed and 11 not in placed
        assert part["census"]["no_over_price"] == 2

    def test_the_census_accounts_for_every_scanned_row(self, part):
        c = part["census"]
        assert c["ou_markets_scanned"] == len(SPECIMENS)
        assert c["ou_markets_usable"] + c["no_over_price"] == c["ou_markets_scanned"]
        assert (c["markets_drop"] + c["markets_ambiguous"] + c["markets_coherent"]
                == c["ou_markets_usable"])

    def test_a_singleton_family_is_counted_as_one(self, part):
        assert part["census"]["families_singleton"] == 1


class TestTheChunkArraysCannotLie:
    """The dimension's only input is a set of ids; every way that set can be
    mis-rendered into SQL produces a table, not an error."""

    def test_only_the_chunks_own_ids_are_emitted(self):
        assert cce._id_array({1, 50, 99, 100, 250}, 50, 100) == "ARRAY[50,99]::bigint[]"

    def test_an_empty_arm_is_a_TYPED_empty_array(self):
        """Postgres cannot infer the element type of a bare ``ARRAY[]`` and
        errors — which in a chunked sweep is retried, split, and eventually
        reported as an irreducible chunk rather than as the bug it is."""
        assert cce._id_array(set(), 0, 10) == "ARRAY[]::bigint[]"

    def test_the_dimension_refuses_to_run_before_the_pre_pass(self):
        """SILENT if removed: with no context every row falls to
        ``z_not_a_ladder`` and the rule reads as finding nothing at all."""
        saved = cce._LADDER
        cce._LADDER = None
        try:
            with pytest.raises(RuntimeError, match="ladder_context"):
                cce.ladder_dim(0, 10)
        finally:
            cce._LADDER = saved

    def test_the_case_carries_the_untouchable_control_arm(self):
        """Doctrine 18 / ruling 103: a row-dropping fix is graded on the cells
        and classes where its mechanism is ABSENT."""
        saved = cce._LADDER
        cce._LADDER = {"drop": {1}, "ambiguous": {2}, "coherent": {3}}
        try:
            expr, _, _ = cce.ladder_dim(0, 10)
        finally:
            cce._LADDER = saved
        for arm in ("a_drop_incoherent", "b_ambiguous_kept",
                    "c_ladder_coherent", "z_not_a_ladder"):
            assert arm in expr

    def test_a_statement_over_the_length_cap_is_split_not_sent(self):
        """SILENT. An oversized body comes back as an unclassified 4xx, and
        ``db_query`` retries it three times and then raises — which in a sweep
        of sixty chunks reads as one bad range rather than as a whole class of
        ranges that can never be measured."""
        src = (SCRIPTS / "calibration_cell_exact.py").read_text()
        collect = src.split("def collect(")[1].split("\ndef ")[0]
        assert "MAX_SQL_CHARS" in collect
        assert "_split(" in collect.split("MAX_SQL_CHARS")[1].split("\n")[1]


class TestThePrefilterCannotHideARung:
    """The SQL ``~`` prefilter decides which rows the Python predicate ever
    sees. A prefilter narrower than the predicate is a silent under-count."""

    PREFILTER = re.compile(r"O/U[ \t\r\n\f\v]+[0-9]")

    @pytest.mark.parametrize("name", [
        "Real Madrid vs. Barcelona: O/U 2.5",
        "IR Iran vs. New Zealand: 1st Half O/U 1.5",
        "Team A vs. Team B: O/U 0.5",
        "Some Match O/U 10",
    ])
    def test_every_name_the_predicate_parses_survives_the_prefilter(self, name):
        assert cce.parse_ou_line(name) is not None
        assert self.PREFILTER.search(name), name

    def test_the_prefilter_pattern_in_the_sql_is_the_one_tested(self):
        assert "O/U[[:space:]]+[0-9]" in cce.LADDER_ROWS_SQL


class TestThePriceIsTheCurvesPrice:
    def test_the_over_leg_is_read_through_the_published_coalesce(self):
        """SILENT. Reading ``opening_probability`` alone would bench the rule
        on prices the curve does not publish — gotcha #144 / ruling 103's
        exact class, arriving in an instrument instead of in the producer."""
        sql = " ".join(cce.LADDER_ROWS_SQL.split())
        assert ("COALESCE(fo.calibration_probability, fo.opening_probability)"
                in sql)

    def test_the_over_leg_is_selected_by_name_not_by_position(self):
        sql = " ".join(cce.LADDER_ROWS_SQL.split())
        assert "lower(btrim(fo.name)) = 'over'" in sql


class TestTheDimensionIsReachable:
    def test_ladder_is_offered_as_a_by_choice(self):
        assert "ladder" in cce.PER_CHUNK_DIMENSIONS

    def test_a_per_chunk_dimension_does_not_shadow_a_static_one(self):
        assert not (set(cce.PER_CHUNK_DIMENSIONS) & set(cce.DIMENSIONS))

    def test_cell_sql_routes_the_per_chunk_dimension(self):
        saved = cce._LADDER
        cce._LADDER = {"drop": {7}, "ambiguous": set(), "coherent": set()}
        try:
            sql = cce.cell_sql("polymarket", "soccer", 0, 10, "ladder")
        finally:
            cce._LADDER = saved
        assert "a_drop_incoherent" in sql
        assert "ARRAY[7]::bigint[]" in sql
