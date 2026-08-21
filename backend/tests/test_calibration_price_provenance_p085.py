"""CAL-P085 (#2087) — the fold at the granularity the apply actually runs at.

The defect this file exists for
-------------------------------
``C-APPLY-PRE-WHICHPRICE-R2`` returned **BLOCK** on 2026-08-21. Its load-bearing
finding was not an arithmetic slip; it was that the number and the decision were
about **different predicates**:

* Ruling 103 approves an exclusion that drops **whole markets** — "winners and
  losers together" — and prices the ``101 mixed markets in 464,777`` explicitly.
* ``PROVENANCE_FOLD_SQL`` ends ``GROUP BY 1, 2, 3, 4``. Market identity is gone
  **in SQL**, before any Python selector runs, so ``FoldRow`` carries none and
  ``POLICIES["C_exclude_hindsight"]`` decides one leg at a time.

So ``3.7630 -> 1.7662 pp`` measured a row-level policy and was quoted for a
whole-market one. Not merely unimplemented — **not expressible** on that
structure, which is why the repair is a second fold and not a second selector.

What makes this suite different from CAL-P077's
------------------------------------------------
CAL-P077's suite is 41 green tests over the row-level fold, and **every one of
them still passes against the defect**, because they all test the row-level
object faithfully. A suite cannot catch its subject's premise being the wrong
premise. The only test that could was one that states the two granularities
**side by side and demands they differ where the mixed markets are** —
:meth:`TestTheAdversarialSpecimen.test_the_R2_specimen_separates_the_two_policies`
is R2's synthetic specimen, executable, and it is the anchor of this file.

The second thing this suite pins is the one the repair could get silently wrong:
the market-aware statement must read **exactly the population the row-level one
reads**. If its extra CTE quietly changes what is counted, every number below it
moves in the same direction and nothing looks wrong. ``A_today`` is the key —
untouched by any policy, market-level already — so it must agree to the row.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.calibration_price_provenance import (  # noqa: E402
    CAPTURE_AFTER_COMMENCE,
    CAPTURE_AFTER_RESOLUTION,
    CAPTURE_NO_TS,
    CAPTURE_PREGAME,
    GRADE_COMPLETE,
    GRADE_INCOMPLETE,
    GRADE_NEVER,
    MARKET_CAPTURE_LEVELS,
    MARKET_LEVEL_UNKNOWN,
    MARKET_PRICE_LEVELS,
    POLICIES,
    PRICE_CP_ABSENT,
    PRICE_CP_EQ_OPEN,
    PRICE_CP_MOVED,
    PROPOSED_POLICY,
    PROVENANCE_FOLD_SQL,
    WHOLE_MARKET_FOLD_SQL,
    WHOLE_MARKET_POLICIES,
    WHOLE_MARKET_POPULATION_LEG_POLICIES,
    FoldRow,
    MarketFoldRow,
    ece,
    market_level_shares,
    market_policy_table,
    reconciles_with_row_fold,
    render_sql,
)


def mrow(
    price_level: str,
    capture_level: str,
    bin_: int,
    n: int,
    mean_price: float,
    winners: int,
    *,
    grade: str = GRADE_COMPLETE,
    capture_level_pop: str | None = None,
) -> MarketFoldRow:
    """A market-fold row written the way a person thinks about it (mean, not sum)."""
    return MarketFoldRow(
        grade,
        bin_,
        price_level,
        capture_level,
        capture_level_pop if capture_level_pop is not None else capture_level,
        n,
        mean_price * n,
        winners,
    )


# ---------------------------------------------------------------------------
# R2's specimen, made executable
# ---------------------------------------------------------------------------


class TestTheAdversarialSpecimen:
    """R2's own counterexample, run against the real selectors of both granularities.

    From the BLOCK verdict, verbatim in effect: *"one synthetic two-leg market
    with one hindsight leg and one pregame leg passed through the real
    ``policy_table``. Policy C retained the pregame leg (n=1); the approved
    whole-market policy would retain neither (n=0)."*

    A mixed market is the ONLY place the two policies can disagree, so this is
    not an illustration — it is the whole of #2087 in four rows.
    """

    #: One market, two legs. Row-level sees two independent rows; whole-market
    #: sees one condemned market. Same underlying legs both times, which is what
    #: makes the comparison fair rather than rigged.
    MIXED_MARKET_ROWS = [
        FoldRow(PRICE_CP_MOVED, CAPTURE_PREGAME, GRADE_COMPLETE, 4, 1, 0.45, 1),
        FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 5, 1, 0.55, 0),
    ]
    MIXED_MARKET_ROWS_WHOLE = [
        # Both legs carry their MARKET's level, and the market has a hindsight
        # leg, so both are ``has_after_res`` — including the pregame one.
        mrow("all_moved", "has_after_res", 4, 1, 0.45, 1),
        mrow("all_moved", "has_after_res", 5, 1, 0.55, 0),
    ]

    def test_the_R2_specimen_separates_the_two_policies(self):
        row_level = ece(self.MIXED_MARKET_ROWS, POLICIES[PROPOSED_POLICY])
        whole = ece(self.MIXED_MARKET_ROWS_WHOLE, WHOLE_MARKET_POLICIES[PROPOSED_POLICY])

        assert row_level["n"] == 1, "row-level policy C keeps the pregame leg"
        assert whole["n"] == 0, "whole-market policy C keeps neither leg"

    def test_the_two_granularities_agree_when_no_market_is_mixed(self):
        """The control. They must differ ONLY on mixed markets, or the lift is wrong.

        With 101 mixed markets in 464,777 the expectation is that the pooled
        numbers land close together — but "close" has to be a CONSEQUENCE of the
        mixed markets being rare, not a property of the lift. If an unmixed
        population also moved, the lift would be doing something else.
        """
        clean_rows = [
            FoldRow(PRICE_CP_MOVED, CAPTURE_PREGAME, GRADE_COMPLETE, 4, 10, 4.5, 5),
            FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 8, 6, 5.1, 0),
        ]
        clean_whole = [
            mrow("all_moved", "all_pregame_or_nots", 4, 10, 0.45, 5),
            mrow("all_moved", "has_after_res", 8, 6, 0.85, 0),
        ]
        assert ece(clean_rows, POLICIES[PROPOSED_POLICY]) == ece(
            clean_whole, WHOLE_MARKET_POLICIES[PROPOSED_POLICY]
        )

    def test_the_whole_market_lift_can_only_drop_more_never_less(self):
        """Every whole-market policy is a SUBSET of its row-level twin.

        "Keep the market iff every leg passes" cannot keep a leg the row-level
        selector rejected. A lift that ever kept MORE would be a different
        policy wearing the same name — and it would move the headline in the
        reassuring direction, which is the direction nobody audits.
        """
        for name in WHOLE_MARKET_POLICIES:
            row_n = ece(self.MIXED_MARKET_ROWS, POLICIES[name])["n"]
            whole_n = ece(self.MIXED_MARKET_ROWS_WHOLE, WHOLE_MARKET_POLICIES[name])["n"]
            assert whole_n <= row_n, f"{name} kept more legs whole-market than row-level"


# ---------------------------------------------------------------------------
# The ladders
# ---------------------------------------------------------------------------


class TestTheLevelLadders:
    """Both market-level columns are ORDERED ladders, and policies rely on it."""

    def test_the_two_ladders_have_the_levels_the_policies_compare_against(self):
        # Written out rather than derived: a policy comparing to a level that
        # the SQL never emits is a policy that silently keeps everything.
        assert MARKET_PRICE_LEVELS == ("all_moved", "no_absent", "has_absent")
        assert MARKET_CAPTURE_LEVELS == (
            "all_pregame_or_nots",
            "no_after_res",
            "has_after_res",
        )

    @pytest.mark.parametrize(
        "name,level_attr,kept_levels",
        [
            ("B_exclude_cp_absent", "price", ("all_moved", "no_absent")),
            ("D_moved_price_only", "price", ("all_moved",)),
            ("C_exclude_hindsight", "capture", ("all_pregame_or_nots", "no_after_res")),
            ("E_pregame_or_unknown_ts", "capture", ("all_pregame_or_nots",)),
        ],
    )
    def test_each_policy_keeps_exactly_the_rungs_it_should(self, name, level_attr, kept_levels):
        levels = MARKET_PRICE_LEVELS if level_attr == "price" else MARKET_CAPTURE_LEVELS
        for level in levels:
            candidate = (
                mrow(level, "all_pregame_or_nots", 4, 1, 0.45, 0)
                if level_attr == "price"
                else mrow("all_moved", level, 4, 1, 0.45, 0)
            )
            kept = WHOLE_MARKET_POLICIES[name](candidate)
            assert kept is (level in kept_levels), f"{name} on rung {level}"

    def test_the_top_rung_of_each_ladder_implies_the_middle_one(self):
        """``all_moved`` => not ``has_absent``; ``all_pregame`` => not ``has_after_res``.

        The implication is what makes each policy one comparison. It lives in
        the SQL's ``CASE`` ordering, so it is asserted through the policies that
        depend on it: the strict policy's keep-set must be inside the loose one's.
        """
        for strict, loose, attr in (
            ("D_moved_price_only", "B_exclude_cp_absent", "price"),
            ("E_pregame_or_unknown_ts", "C_exclude_hindsight", "capture"),
        ):
            levels = MARKET_PRICE_LEVELS if attr == "price" else MARKET_CAPTURE_LEVELS
            for level in levels:
                candidate = (
                    mrow(level, "all_pregame_or_nots", 4, 1, 0.45, 0)
                    if attr == "price"
                    else mrow("all_moved", level, 4, 1, 0.45, 0)
                )
                if WHOLE_MARKET_POLICIES[strict](candidate):
                    assert WHOLE_MARKET_POLICIES[loose](candidate)

    def test_grade_still_gates_every_policy(self):
        for grade in (GRADE_INCOMPLETE, GRADE_NEVER):
            candidate = mrow(
                "all_moved", "all_pregame_or_nots", 4, 1, 0.45, 0, grade=grade
            )
            for name, selector in WHOLE_MARKET_POLICIES.items():
                assert not selector(candidate), f"{name} admitted a {grade} market"


# ---------------------------------------------------------------------------
# The row object
# ---------------------------------------------------------------------------


class TestMarketFoldRow:
    def test_an_unknown_population_ladder_raises_rather_than_folding(self):
        """The one value the SQL emits ONLY when an assumption broke.

        ``mkt_capture_level_pop`` is ``unknown`` exactly when a market reached
        the outer SELECT with no population leg — which the outer predicate makes
        impossible, since it IS the FILTER's predicate. Gotcha #53: a reading
        that can only exist after a contradiction must not resolve to the
        reassuring rung. It is louder than a wrong number because a wrong number
        here is invisible.
        """
        with pytest.raises(ValueError, match=MARKET_LEVEL_UNKNOWN):
            MarketFoldRow(
                GRADE_COMPLETE, 4, "all_moved", "all_pregame_or_nots",
                MARKET_LEVEL_UNKNOWN, 1, 0.45, 0,
            )

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"grade": "half"},
            {"mkt_price_level": "mostly_moved"},
            {"mkt_capture_level": "sort_of_pregame"},
            {"bin_": 10},
            {"bin_": -1},
            {"n": 0},
            {"winners": 5},
        ],
    )
    def test_a_malformed_row_raises_rather_than_folding(self, kwargs):
        base: dict[str, Any] = {
            "grade": GRADE_COMPLETE,
            "bin_": 4,
            "mkt_price_level": "all_moved",
            "mkt_capture_level": "all_pregame_or_nots",
            "mkt_capture_level_pop": "all_pregame_or_nots",
            "n": 2,
            "sum_prob": 0.9,
            "winners": 1,
        }
        base.update(kwargs)
        with pytest.raises(ValueError):
            MarketFoldRow(**base)

    def test_numeric_sum_prob_arrives_as_a_string_over_the_wire(self):
        """``db-query`` returns ``numeric`` as a JSON string. A silent str here folds wrong."""
        built = MarketFoldRow.from_row(
            [GRADE_COMPLETE, 4, "all_moved", "no_after_res", "no_after_res", 2, "0.900000", 1]
        )
        assert isinstance(built.sum_prob, float)
        assert built.sum_prob == pytest.approx(0.9)

    def test_from_row_rejects_the_wrong_column_count(self):
        with pytest.raises(ValueError, match="expected 8 columns"):
            MarketFoldRow.from_row([GRADE_COMPLETE, 4, "all_moved", "no_after_res", 2, "0.9", 1])


# ---------------------------------------------------------------------------
# Population identity — the check that catches a silent, uniform error
# ---------------------------------------------------------------------------


class TestThePopulationIsUnchanged:
    """The market-aware statement must read the SAME rows as the row-level one."""

    def _where_of(self, template: str) -> str:
        """The OUTER ``WHERE`` block, normalised for whitespace."""
        tail = template[template.rindex("\nWHERE ") :]
        tail = tail[: tail.index("\nGROUP BY")]
        return " ".join(tail.split())

    def test_the_outer_predicate_is_the_row_folds_predicate_verbatim(self):
        """Not "equivalent" — the same text.

        The reconciliation in the artifact compares two numbers and can only
        catch a difference big enough to move an ECE. This catches the predicate
        drifting at all, which is the form the error would actually take: a
        clause added to the CTE and forgotten in the outer query, or vice versa.
        """
        assert self._where_of(WHOLE_MARKET_FOLD_SQL) == self._where_of(PROVENANCE_FOLD_SQL)

    def test_the_cte_deliberately_does_NOT_carry_the_curve_filters(self):
        """The market ladders vote with EVERY leg, not just the curve's legs.

        This is the apply's own reading: its CTE is an unfiltered ``EXISTS`` over
        ``futures_outcomes``, and ruling 103's ``101 mixed markets in 464,777``
        came from ``LEG_SPLIT_SQL``, which is likewise unfiltered. If the CTE
        ever grew the curve filters, the fold would quietly start measuring the
        population-legs variant while still being labelled all-legs.
        """
        cte = WHOLE_MARKET_FOLD_SQL[: WHOLE_MARKET_FOLD_SQL.index("\n)\nSELECT")]
        unfiltered = cte[: cte.index("BOOL_OR(fo.opening_captured_at IS NOT NULL\n"
                                     "                   AND fm.resolution_date IS NOT NULL\n"
                                     "                   AND fo.opening_captured_at > fm.resolution_date)\n"
                                     "               FILTER")]
        assert "is_winner IS NOT NULL" not in unfiltered
        # ...and the population variant gets them, via FILTER and only via FILTER.
        assert cte.count("FILTER (WHERE") == 2

    def test_reconciliation_passes_when_the_two_folds_see_the_same_population(self):
        row_rows = [
            FoldRow(PRICE_CP_MOVED, CAPTURE_PREGAME, GRADE_COMPLETE, 4, 100, 45.0, 50),
            FoldRow(PRICE_CP_ABSENT, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 0, 60, 0.6, 60),
        ]
        market_rows = [
            mrow("all_moved", "all_pregame_or_nots", 4, 100, 0.45, 50),
            mrow("has_absent", "has_after_res", 0, 60, 0.01, 60),
        ]
        result = reconciles_with_row_fold(market_rows, row_rows)
        assert result["reconciled"] is True
        assert result["n_delta"] == 0

    def test_reconciliation_FAILS_on_a_single_row_of_drift(self):
        """One row, not one percent. There is no population slack here.

        ``futures_outcomes`` for RESOLVED markets do not move between two reads
        minutes apart, so any ``n_delta`` is the new CTE counting differently —
        exactly the failure this exists to catch. Absorbing it into a tolerance
        would hide the only symptom it has.
        """
        row_rows = [FoldRow(PRICE_CP_MOVED, CAPTURE_PREGAME, GRADE_COMPLETE, 4, 40, 18.0, 20)]
        market_rows = [mrow("all_moved", "all_pregame_or_nots", 4, 39, 0.45, 20)]
        result = reconciles_with_row_fold(market_rows, row_rows)
        assert result["reconciled"] is False
        assert result["n_delta"] == -1

    def test_reconciliation_below_the_floor_is_an_absence_not_a_pass(self):
        row_rows = [FoldRow(PRICE_CP_MOVED, CAPTURE_PREGAME, GRADE_COMPLETE, 4, 2, 0.9, 1)]
        market_rows = [mrow("all_moved", "all_pregame_or_nots", 4, 2, 0.45, 1)]
        assert reconciles_with_row_fold(market_rows, row_rows)["reconciled"] is None

    def test_n_delta_survives_an_unmeasurable_ECE(self):
        """An unmeasurable ECE does not make the ROW COUNTS unmeasurable.

        Found by the impure tests below, not by reasoning: on a sweep where every
        market-aware read failed, ``pooled_market_rows`` was empty, this function
        took its early-out branch, and the reader's own closing summary died on
        ``KeyError: 'n_delta'`` — AFTER the artifact was already on disk. A run
        that succeeded then crashed reporting, with a traceback where the honest
        "1 = partial sweep" exit should have been.
        """
        result = reconciles_with_row_fold(
            [], [FoldRow(PRICE_CP_MOVED, CAPTURE_PREGAME, GRADE_COMPLETE, 4, 40, 18.0, 20)]
        )
        assert result["reconciled"] is None
        assert result["n_delta"] == -40


# ---------------------------------------------------------------------------
# Which legs vote
# ---------------------------------------------------------------------------


class TestWhichLegsVote:
    """The sensitivity nobody had written down until #2087 forced the question."""

    #: A market whose only hindsight leg is one the CURVE NEVER READS — priced
    #: at exactly 1.0, or with a NULL ``is_winner``. All-legs condemns the
    #: market; population-legs does not see the offending leg at all.
    SPLIT_VOTE = [mrow("all_moved", "has_after_res", 4, 8, 0.45, 4,
                       capture_level_pop="all_pregame_or_nots")]

    def test_the_two_readings_can_disagree_and_the_artifact_says_which_ran(self):
        all_legs = ece(self.SPLIT_VOTE, WHOLE_MARKET_POLICIES[PROPOSED_POLICY])
        pop_legs = ece(self.SPLIT_VOTE, WHOLE_MARKET_POPULATION_LEG_POLICIES[PROPOSED_POLICY])
        assert all_legs["n"] == 0, "all-legs condemns the market"
        assert pop_legs["n"] == 8, "population-legs never sees the offending leg"

    def test_the_table_reports_the_gap_between_them_rather_than_picking_one(self):
        table = market_policy_table(self.SPLIT_VOTE)
        assert set(table) == {"all_legs", "population_legs"}
        pop = table["population_legs"][PROPOSED_POLICY]
        assert pop["delta_vs_all_legs_n"] == 8
        # And the all-legs table is the one carrying every policy A-E.
        assert set(table["all_legs"]) == set(WHOLE_MARKET_POLICIES)


# ---------------------------------------------------------------------------
# The table and the shares
# ---------------------------------------------------------------------------


class TestTheTable:
    CELL = [
        mrow("all_moved", "all_pregame_or_nots", 2, 100, 0.25, 24),
        mrow("has_absent", "has_after_res", 0, 60, 0.02, 55),
        mrow("no_absent", "no_after_res", 8, 40, 0.85, 33),
    ]

    def test_every_policy_is_reported_with_a_delta_against_the_control(self):
        table = market_policy_table(self.CELL)["all_legs"]
        assert table["A_today"]["delta_ece"] == 0.0
        for name in WHOLE_MARKET_POLICIES:
            assert table[name]["ece"] is not None
            assert table[name]["delta_ece"] is not None

    def test_dropping_the_hindsight_market_is_the_move_the_ruling_claims(self):
        table = market_policy_table(self.CELL)["all_legs"]
        assert table[PROPOSED_POLICY]["delta_ece"] < 0
        assert table[PROPOSED_POLICY]["n"] == 140

    def test_shares_are_reported_on_all_three_ladders(self):
        shares = market_level_shares(self.CELL)
        assert set(shares) == {"price", "capture", "capture_population_legs"}
        assert shares["capture"]["has_after_res"] == pytest.approx(60 / 200)
        assert sum(shares["price"].values()) == pytest.approx(1.0)

    def test_shares_of_an_empty_cell_are_empty_not_zeroes(self):
        assert market_level_shares([])["capture"] == {}


class TestTheSqlIsRenderedNotConcatenated:
    def test_the_whole_market_template_renders_and_leaves_no_placeholder(self):
        rendered = render_sql(WHOLE_MARKET_FOLD_SQL, cat="hockey", mt="container_member", k=4, m=2)
        assert "{" not in rendered and "}" not in rendered
        assert "MOD(fm.id, 4) = 2" in rendered

    @pytest.mark.parametrize("bad", ["hockey'; DROP TABLE", "hock ey", "", "a/b"])
    def test_a_cell_name_that_is_not_a_slug_is_refused_at_render_time(self, bad):
        with pytest.raises(ValueError):
            render_sql(WHOLE_MARKET_FOLD_SQL, cat=bad, mt="quantity")

    def test_partitioning_is_safe_because_it_partitions_on_the_MARKET_key(self):
        """``MOD(fm.id, k)`` — the market's id, so no market spans two statements.

        This is what makes a ``k=4`` run and a ``k=1`` run the same fold. Had the
        partition keyed on ``fo.id``, a market's legs would scatter across
        statements and every market-level aggregate would be computed over a
        fraction of its legs — silently, and differently at every ``k``.
        """
        rendered = render_sql(WHOLE_MARKET_FOLD_SQL, cat="hockey", mt="quantity", k=4, m=1)
        assert rendered.count("MOD(fm.id, 4) = 1") == 2  # the CTE and the outer query
        assert "MOD(fo.id" not in rendered


# ---------------------------------------------------------------------------
# RULING (a) — the impure half. This STARTS the reader.
# ---------------------------------------------------------------------------


class TestTheReaderActuallyRunsWholeMarket:
    """CAL-P077 ruling (a), applied to the new path: ``main()``, end to end.

    The row-level reader has this and it earned it — the census worker shipped
    37 pure tests and died in 73 ms on every real call. ``--whole-market`` is a
    new argparse flag, a new template, a new row class and a new pooled section;
    all four are between the CLI and the artifact, which is exactly the stretch
    a pure test cannot reach.
    """

    ROW_FOLD = [
        FoldRow(PRICE_CP_MOVED, CAPTURE_PREGAME, GRADE_COMPLETE, 4, 100, 45.0, 40),
        FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 8, 60, 51.0, 1),
        FoldRow(PRICE_CP_ABSENT, CAPTURE_NO_TS, GRADE_COMPLETE, 0, 40, 0.4, 2),
    ]
    MARKET_FOLD = [
        mrow("all_moved", "all_pregame_or_nots", 4, 100, 0.45, 40),
        mrow("no_absent", "has_after_res", 8, 60, 0.85, 1),
        mrow("has_absent", "all_pregame_or_nots", 0, 40, 0.01, 2),
    ]

    @pytest.fixture
    def stub_transport(self, monkeypatch):
        import urllib.request

        calls: list[str] = []

        def rows_for(sql: str) -> dict[str, Any]:
            if "mkt_capture_level_pop" in sql:
                return {
                    "columns": [
                        "grade", "bin", "mkt_price_level", "mkt_capture_level",
                        "mkt_capture_level_pop", "n", "sum_prob", "winners",
                    ],
                    "rows": [
                        [r.grade, r.bin, r.mkt_price_level, r.mkt_capture_level,
                         r.mkt_capture_level_pop, r.n, str(r.sum_prob), r.winners]
                        for r in self.MARKET_FOLD
                    ],
                    "duration_ms": 2.0,
                    "sql_fingerprint": "stub-whole-market",
                }
            return {
                "columns": [
                    "price_class", "capture_class", "grade", "bin", "n", "sum_prob", "winners",
                ],
                "rows": [
                    [r.price_class, r.capture_class, r.grade, r.bin, r.n, str(r.sum_prob), r.winners]
                    for r in self.ROW_FOLD
                ],
                "duration_ms": 1.0,
                "sql_fingerprint": "stub-fold",
            }

        class _Response:
            def __init__(self, payload: dict[str, Any]) -> None:
                self._body = json.dumps(payload).encode()

            def read(self) -> bytes:
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        def fake_urlopen(request, timeout=None):  # noqa: ANN001
            sql = json.loads(request.data.decode())["sql"]
            calls.append(sql)
            return _Response(rows_for(sql))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setenv("BAINLUCK_API", "https://stub.invalid")
        monkeypatch.setenv("ADMIN_TOKEN", "stub-token")
        return calls

    def _run(self, monkeypatch, tmp_path, extra: list[str]) -> tuple[int, dict[str, Any]]:
        from scripts import measure_price_provenance as reader

        out = tmp_path / "artifact.json"
        monkeypatch.setattr(
            sys, "argv",
            ["measure_price_provenance.py", "--cell", "hockey/container_member",
             "--out", str(out), *extra],
        )
        code = reader.main()
        return code, json.loads(out.read_text())

    def test_main_runs_both_folds_and_writes_the_whole_market_headline(
        self, stub_transport, tmp_path, monkeypatch
    ):
        code, artifact = self._run(monkeypatch, tmp_path, ["--whole-market"])
        assert code == 0
        assert artifact["schema"] == "calibration-price-provenance/v2"

        cell = artifact["cells"]["hockey/container_member"]
        assert "policies" in cell, "the row-level fold still runs"
        assert set(cell["whole_market"]["policies"]["all_legs"]) == set(WHOLE_MARKET_POLICIES)
        assert cell["whole_market"]["row_fold_reconciliation"]["reconciled"] is True

        pooled = artifact["pooled_whole_market"]["all_legs"]
        assert pooled["A_today"]["n"] == 200
        assert pooled[PROPOSED_POLICY]["n"] == 140
        assert artifact["whole_market_cells_unmeasured"] == 0

    def test_the_flag_is_opt_in_and_the_v1_artifact_is_unchanged_without_it(
        self, stub_transport, tmp_path, monkeypatch
    ):
        """The row-level artifact must stay byte-comparable to CAL-P077's.

        A repair that quietly rewrites the thing it is being compared against
        removes the comparison. ``--whole-market`` adds sections; it never
        touches the ones the P077 cert already read.
        """
        code, artifact = self._run(monkeypatch, tmp_path, [])
        assert code == 0
        assert artifact["schema"] == "calibration-price-provenance/v1"
        assert "whole_market" not in artifact["cells"]["hockey/container_member"]
        assert "pooled_whole_market" not in artifact
        assert all("mkt_capture_level_pop" not in sql for sql in stub_transport)

    def test_a_failed_whole_market_read_is_named_and_does_not_kill_the_row_fold(
        self, stub_transport, tmp_path, monkeypatch
    ):
        """An unmeasured cell that VANISHES reads as a cell with nothing wrong.

        And it is worse than that here: the pooled headline is re-folded over
        whatever was measured, so a silently-dropped cell MOVES the number the
        apply is authorised against. CAL-P077 measured that exactly — a 47-cell
        pool read 5.02 pp where the 49-cell pool read 3.78 pp.
        """
        import urllib.request

        real = urllib.request.urlopen

        def selective(request, timeout=None):  # noqa: ANN001
            if "mkt_capture_level_pop" in json.loads(request.data.decode())["sql"]:
                raise RuntimeError("canceling statement due to statement timeout")
            return real(request, timeout=timeout)

        monkeypatch.setattr(urllib.request, "urlopen", selective)
        code, artifact = self._run(monkeypatch, tmp_path, ["--whole-market"])

        assert code == 1, "a partial sweep must not exit clean"
        assert "hockey/container_member" in artifact["whole_market_unmeasured"]
        assert artifact["cells"]["hockey/container_member"]["policies"]["A_today"]["n"] == 200

    def test_a_truncated_whole_market_read_is_an_error_not_a_short_fold(
        self, tmp_path, monkeypatch
    ):
        """1,000 rows back means the fold is WRONG, not small (the ``db-query`` cap)."""
        import urllib.request

        class _Response:
            def read(self) -> bytes:
                return json.dumps(
                    {"columns": [], "rows": [], "truncated": True, "duration_ms": 1.0}
                ).encode()

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Response())
        monkeypatch.setenv("BAINLUCK_API", "https://stub.invalid")
        monkeypatch.setenv("ADMIN_TOKEN", "stub-token")
        code, artifact = self._run(monkeypatch, tmp_path, ["--whole-market"])
        assert code == 1
        assert "truncated" in artifact["unmeasured"]["hockey/container_member"]

    def test_the_read_path_never_sends_timeout_ms(self, stub_transport, tmp_path, monkeypatch):
        """MEASURED 2026-08-21: ``db-query`` 400s on ``timeout_ms`` off the explain path.

        ``{"detail": "`timeout_ms` is only supported with `explain: true`"}``. The
        documented 500 ms-25 s band is real and unreachable from here, so the row
        path is fixed at 10 s and partition escalation is the only budget control
        this fold has. Pinned because the docs read the other way and the next
        reader will try it again.
        """
        import urllib.request

        sent: list[dict[str, Any]] = []
        real = urllib.request.urlopen

        def capture(request, timeout=None):  # noqa: ANN001
            sent.append(json.loads(request.data.decode()))
            return real(request, timeout=timeout)

        monkeypatch.setattr(urllib.request, "urlopen", capture)
        self._run(monkeypatch, tmp_path, ["--whole-market"])
        assert sent, "the reader made no request at all"
        assert all("timeout_ms" not in body for body in sent)
