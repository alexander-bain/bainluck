"""CAL-P077 — the price-provenance instrument, and the rule that it be STARTED.

Fable's ruling (a), CAL-P077, standing from this window:

    Every worker/consumer ships with at least one IMPURE smoke test that STARTS
    it. Caller-not-helper applies to us, not just codex.

The named failure behind it is one queue old. ``cohort_cell_census`` merged with
**37 tests, all pure** — SQL-string invariants and the pure fold — and died in
73 ms on every real invocation with
``'_AsyncGeneratorContextManager' object has no attribute '__anext__'``. It
shipped green through a 17,093-test suite and a clean integration, and nobody
learned it had never run until somebody ran it. Pure tests prove the decisions;
only an impure one proves the wiring, and the wiring is where that defect lived.

So this file is deliberately in two halves:

* :class:`TestTheFold` and friends — pure, no I/O, the decisions.
* :class:`TestTheReaderActuallyRuns` — drives ``main()`` end to end over a
  stubbed transport, so argparse -> render -> read -> fold -> policy table ->
  artifact all execute. It would have caught the census worker's defect class,
  because it calls the thing a human calls.

The subject: ``app.utils.calibration_price_provenance`` +
``scripts/measure_price_provenance.py``, the substitute reader that measured the
hindsight-capture mechanism behind the 41 pp hockey cell (CAL-P077 item 1/4).
"""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.calibration_price_provenance import (  # noqa: E402
    CAPTURE_AFTER_COMMENCE,
    CAPTURE_AFTER_RESOLUTION,
    CAPTURE_NO_TS,
    CAPTURE_PREGAME,
    CURVE_PRICE,
    GRADE_COMPLETE,
    GRADE_NEVER,
    LEG_SPLIT_SQL,
    MIN_CELL_N,
    POLICIES,
    PROPOSED_POLICY,
    PROVENANCE_FOLD_SQL,
    PRICE_CP_ABSENT,
    PRICE_CP_EQ_OPEN,
    PRICE_CP_MOVED,
    REPRICE_FEASIBILITY_SQL,
    FoldRow,
    class_shares,
    ece,
    policy_table,
    reconciles_with_census,
    render_sql,
)


def row(
    price: str,
    capture: str,
    bin_: int,
    n: int,
    mean_price: float,
    winners: int,
    grade: str = GRADE_COMPLETE,
) -> FoldRow:
    """A fold row written the way a person thinks about it (mean, not sum)."""
    return FoldRow(price, capture, grade, bin_, n, mean_price * n, winners)


# ---------------------------------------------------------------------------
# The production measurement, frozen as a fixture
# ---------------------------------------------------------------------------

#: ``hockey/container_member`` as measured against production 2026-08-20, the
#: 41 pp cell #1912 called "NO known mechanism". Real numbers, so a regression in
#: the fold shows up as this cell no longer reproducing its own census entry.
HOCKEY_CM = [
    # 45 grouped rows, verbatim from the production fold 2026-08-20:
    # n=1,514  winners=467  ECE 41.00  gap -6.58 — identical to the #1978
    # census entry for this cell, which is what makes it a reconciliation and
    # not an illustration.
    #
    # The whole 41 pp is legible in the fixture. Read the two AFTER_RESOLUTION
    # blocks against each other: cp_absent bin 0 is 363 outcomes priced at
    # 0.0067 that ALL won; cp_eq_open bins 7-9 are 193 outcomes priced
    # 0.74-0.92 of which ONE won. Opposite signs, and they nearly cancel.
    FoldRow(PRICE_CP_ABSENT, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 9, 1, 0.9945, 1),
    FoldRow(PRICE_CP_ABSENT, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 0, 363, 2.433, 363),
    FoldRow(PRICE_CP_ABSENT, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 9, 4, 3.945, 4),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 0, 6, 0.1335, 0),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 1, 6, 0.69, 2),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 2, 3, 0.77, 0),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 3, 5, 1.73, 2),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 4, 27, 13.035, 9),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 5, 11, 5.695, 9),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 6, 3, 1.855, 1),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 7, 3, 2.275, 3),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 8, 4, 3.405, 1),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 9, 2, 1.835, 2),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 0, 409, 5.638, 0),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 1, 96, 13.562, 0),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 2, 46, 11.101, 0),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 3, 28, 9.321, 0),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 4, 41, 18.31, 0),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 5, 41, 22.195, 1),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 6, 26, 16.779, 0),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 7, 44, 32.599, 0),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 8, 92, 77.938, 0),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 9, 57, 52.49, 1),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_NO_TS, GRADE_COMPLETE, 0, 40, 0.118, 1),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_NO_TS, GRADE_COMPLETE, 4, 5, 2.34, 0),
    FoldRow(PRICE_CP_EQ_OPEN, CAPTURE_NO_TS, GRADE_COMPLETE, 5, 5, 2.66, 5),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 0, 21, 0.4765, 5),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 1, 7, 1.24, 1),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 2, 8, 2.235, 2),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 3, 23, 8.08, 7),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 4, 16, 7.2055, 5),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 5, 22, 11.5, 12),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 6, 12, 7.835, 9),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 7, 6, 4.32, 5),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 8, 4, 3.345, 3),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_COMMENCE, GRADE_COMPLETE, 9, 10, 9.783, 7),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 0, 5, 0.007, 0),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 4, 2, 0.985, 0),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 5, 1, 0.5, 0),
    FoldRow(PRICE_CP_MOVED, CAPTURE_AFTER_RESOLUTION, GRADE_COMPLETE, 9, 4, 3.998, 4),
    FoldRow(PRICE_CP_MOVED, CAPTURE_NO_TS, GRADE_COMPLETE, 0, 1, 0.0005, 0),
    FoldRow(PRICE_CP_MOVED, CAPTURE_NO_TS, GRADE_COMPLETE, 3, 1, 0.305, 0),
    FoldRow(PRICE_CP_MOVED, CAPTURE_NO_TS, GRADE_COMPLETE, 4, 1, 0.475, 0),
    FoldRow(PRICE_CP_MOVED, CAPTURE_NO_TS, GRADE_COMPLETE, 5, 1, 0.525, 1),
    FoldRow(PRICE_CP_MOVED, CAPTURE_NO_TS, GRADE_COMPLETE, 6, 1, 0.695, 1),
]


class TestTheFold:
    """ECE arithmetic, and the shapes that must not be silently accepted."""

    def test_ece_is_the_bin_pooled_weighted_gap(self):
        rows = [
            row(PRICE_CP_MOVED, CAPTURE_PREGAME, 2, 100, 0.25, 25),  # perfect
            row(PRICE_CP_MOVED, CAPTURE_PREGAME, 8, 100, 0.85, 35),  # 50 pp off
        ]
        result = ece(rows)
        assert result["n"] == 200
        assert result["ece"] == pytest.approx(25.0, abs=1e-6)

    def test_two_opposite_errors_cancel_in_gap_but_not_in_ece(self):
        """The whole reason hockey/container_member hid for months.

        A -98 pp class and a +29 pp class pool to a gap of -6.6 pp, which reads
        like a mildly optimistic cell. ECE, being an absolute value per bin,
        cannot be cancelled the same way. Any future alarm built on ``gap``
        alone re-acquires this blind spot, so the property is pinned.
        """
        result = ece(HOCKEY_CM)
        assert abs(result["gap"]) < 8.0, "gap looks nearly honest"
        assert result["ece"] > 35.0, "ECE does not"

    def test_below_min_cell_n_is_an_absence_with_a_reason_not_a_zero(self):
        result = ece([row(PRICE_CP_MOVED, CAPTURE_PREGAME, 5, MIN_CELL_N - 1, 0.55, 3)])
        assert result["ece"] is None
        assert "below_min_cell_n" in result["reason"]
        assert result["n"] == MIN_CELL_N - 1

    def test_empty_selection_is_an_absence_not_a_zero(self):
        assert ece(HOCKEY_CM, lambda r: False) == {
            "ece": None,
            "gap": None,
            "n": 0,
            "reason": "empty",
        }

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"price_class": "nope"},
            {"capture_class": "nope"},
            {"grade": "nope"},
            {"bin_": 10},
            {"n": 0},
            {"winners": 999},
        ],
    )
    def test_a_malformed_row_raises_rather_than_folding(self, kwargs):
        base = dict(
            price_class=PRICE_CP_MOVED,
            capture_class=CAPTURE_PREGAME,
            grade=GRADE_COMPLETE,
            bin_=5,
            n=10,
            sum_prob=5.0,
            winners=5,
        )
        base.update(kwargs)
        with pytest.raises(ValueError):
            FoldRow(**base)

    def test_numeric_sum_prob_arrives_as_a_string_over_the_wire(self):
        """``db-query`` serialises ``SUM(numeric)`` as a string. It must coerce.

        A ``str`` in an arithmetic position is the failure that produces a wrong
        number instead of a loud error, so the boundary coerces once, here.
        """
        parsed = FoldRow.from_row(
            [PRICE_CP_MOVED, CAPTURE_PREGAME, GRADE_COMPLETE, 5, 10, "5.500000", 5]
        )
        assert parsed.sum_prob == pytest.approx(5.5)

    def test_from_row_rejects_the_wrong_column_count(self):
        with pytest.raises(ValueError, match="7 columns"):
            FoldRow.from_row([PRICE_CP_MOVED, CAPTURE_PREGAME, GRADE_COMPLETE, 5, 10])


class TestGradeFiltering:
    def test_only_complete_rows_reach_every_policy(self):
        rows = HOCKEY_CM + [
            row(PRICE_CP_MOVED, CAPTURE_PREGAME, 0, 5_000, 0.02, 0, grade=GRADE_NEVER)
        ]
        for name, selector in POLICIES.items():
            kept = [r for r in rows if selector(r)]
            assert all(r.grade == GRADE_COMPLETE for r in kept), name


class TestTheProposedPolicy:
    """The claim CAL-P077 takes to pre-cert, and the controls that could sink it."""

    def test_hockey_reproduces_its_own_census_entry(self):
        """Ruling (e)'s substitute-reader standard, applied to this reader.

        Production census: ``ece_complete 41.00``, ``n_complete 1514``. The fold
        must land on it, or the two extra axes are decorating a different
        population.
        """
        verdict = reconciles_with_census(
            HOCKEY_CM, {"ece_complete": 41.00, "n_complete": 1514}
        )
        assert verdict["reconciled"] is True, verdict
        assert verdict["mine"]["n"] == 1514

    def test_excluding_hindsight_is_the_largest_single_move(self):
        table = policy_table(HOCKEY_CM)
        proposed = table[PROPOSED_POLICY]["delta_ece"]
        assert proposed < -25.0, table
        # It beats the read-side-only probe codex ran, which is the point: the
        # writer-side fallback is the larger class and `cp IS NULL` cannot see it.
        assert proposed < table["B_exclude_cp_absent"]["delta_ece"]

    def test_the_kept_population_is_calibrated_not_merely_less_bad(self):
        kept = ece(HOCKEY_CM, POLICIES[PROPOSED_POLICY])
        assert abs(kept["gap"]) < 5.0, kept

    def test_the_dropped_population_is_the_corrupt_one(self):
        dropped = ece(
            HOCKEY_CM,
            lambda r: r.grade == GRADE_COMPLETE
            and r.capture_class == CAPTURE_AFTER_RESOLUTION,
        )
        assert dropped["ece"] > 40.0, dropped

    def test_a_cell_without_the_mechanism_does_not_move(self):
        """The non-vacuity control, as a test rather than as a paragraph.

        Dropping rows can always lower ECE by dropping hard rows. If a cell with
        no hindsight capture at all still improved under the policy, the account
        would be wrong and this would be a row-count effect. Measured in
        production on 10 such cells (n>=1,000, hindsight share <2%): all move by
        |ΔECE| < 0.20 pp. Here it must be exactly zero, because the selector
        removes nothing.
        """
        clean = [
            row(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_COMMENCE, 3, 2_000, 0.35, 640),
            row(PRICE_CP_MOVED, CAPTURE_AFTER_COMMENCE, 7, 1_200, 0.74, 800),
            row(PRICE_CP_ABSENT, CAPTURE_NO_TS, 1, 300, 0.12, 40),
        ]
        table = policy_table(clean)
        assert table[PROPOSED_POLICY]["delta_ece"] == 0.0
        assert table[PROPOSED_POLICY]["n"] == table["A_today"]["n"]

    def test_dropping_every_fallback_price_can_make_a_cell_worse(self):
        """Why ``D_moved_price_only`` is measured and rejected, not assumed.

        On cells whose fallback prices are honest (tennis: +6.0 pp and +5.4 pp
        measured), throwing them away removes real information. A policy is
        chosen on the number, not on how principled it sounds.
        """
        honest_fallback = [
            row(PRICE_CP_EQ_OPEN, CAPTURE_AFTER_COMMENCE, 3, 5_000, 0.35, 1_750),
            row(PRICE_CP_MOVED, CAPTURE_AFTER_COMMENCE, 8, 400, 0.85, 200),
        ]
        table = policy_table(honest_fallback)
        assert table["D_moved_price_only"]["delta_ece"] > 0

    def test_class_shares_expose_the_cell_s_exposure(self):
        shares = class_shares(HOCKEY_CM)
        assert shares["capture"][CAPTURE_AFTER_RESOLUTION] > 0.8
        assert sum(shares["price"].values()) == pytest.approx(1.0, abs=1e-5)
        assert sum(shares["capture"].values()) == pytest.approx(1.0, abs=1e-5)


class TestTheSqlIsRenderedNotConcatenated:
    @pytest.mark.parametrize(
        "template", [PROVENANCE_FOLD_SQL, LEG_SPLIT_SQL, REPRICE_FEASIBILITY_SQL]
    )
    def test_every_template_renders_and_leaves_no_placeholder(self, template):
        sql = render_sql(template, cat="hockey", mt="container_member")
        assert "{" not in sql and "}" not in sql
        assert "polymarket" in sql and "'resolved'" in sql

    @pytest.mark.parametrize(
        "bad", ["hockey'; DROP TABLE futures_markets --", "", "a b", None, 7]
    )
    def test_a_cell_name_that_is_not_a_slug_is_refused_at_render_time(self, bad):
        """These strings are interpolated, because the read rail takes text and
        no parameters. So the validation is the boundary, and it is here."""
        with pytest.raises(ValueError):
            render_sql(PROVENANCE_FOLD_SQL, cat=bad, mt="quantity")

    @pytest.mark.parametrize("k,m", [(0, 0), (2, 2), (2, -1), (1.5, 0)])
    def test_a_nonsense_partition_is_refused(self, k, m):
        with pytest.raises(ValueError):
            render_sql(PROVENANCE_FOLD_SQL, cat="hockey", mt="quantity", k=k, m=m)

    def test_partitions_cover_the_cell_exactly_once(self):
        rendered = [
            render_sql(PROVENANCE_FOLD_SQL, cat="hockey", mt="quantity", k=4, m=m)
            for m in range(4)
        ]
        assert len({r for r in rendered}) == 4
        for m in range(4):
            assert f"MOD(fm.id, 4) = {m}" in rendered[m]

    def test_curve_price_still_matches_the_frozen_files_default(self):
        """The duplication guard.

        ``CURVE_PRICE`` is a copy of ``_calibration_population_ctes``' default,
        held outside ``precompute_calibration.py`` under ruling (e). A copy that
        can drift silently is worse than no copy: this reader would keep
        reproducing a census of a population the curve no longer prices. If the
        curve's default moves, this fails by name and someone decides on purpose.
        """
        import inspect

        from app.tasks.precompute_calibration import _calibration_population_ctes

        signature = inspect.signature(_calibration_population_ctes)
        assert signature.parameters["curve_price"].default == CURVE_PRICE


class TestTheReaderActuallyRuns:
    """RULING (a). The impure half — this STARTS the consumer.

    Not a helper, not a fragment: ``main()``, through argparse, over a stubbed
    transport, writing a real file. Everything between the CLI and the artifact
    executes. The census worker's 73-ms death was in exactly this stretch and
    37 pure tests never touched it.
    """

    @pytest.fixture
    def stub_transport(self, monkeypatch):
        """Answer ``db-query`` with the frozen hockey fold."""
        import urllib.request

        calls: list[dict[str, Any]] = []

        def rows_for(sql: str) -> dict[str, Any]:
            if "legs_after_resolution" in sql:
                return {
                    "columns": ["markets", "all_after", "none_after", "mixed"],
                    "rows": [[1304, 633, 671, 0]],
                    "duration_ms": 1.0,
                    "sql_fingerprint": "stub-legsplit",
                }
            if "with_pre_commence_snapshot" in sql:
                return {
                    "columns": [
                        "n_after_resolution",
                        "with_pre_commence_snapshot",
                        "with_pre_resolution_snapshot",
                        "with_any_snapshot",
                    ],
                    "rows": [[1259, 0, 0, 633]],
                    "duration_ms": 1.0,
                    "sql_fingerprint": "stub-feasibility",
                }
            return {
                "columns": [
                    "price_class",
                    "capture_class",
                    "grade",
                    "bin",
                    "n",
                    "sum_prob",
                    "winners",
                ],
                "rows": [
                    [r.price_class, r.capture_class, r.grade, r.bin, r.n, str(r.sum_prob), r.winners]
                    for r in HOCKEY_CM
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
            calls.append({"sql": sql})
            return _Response(rows_for(sql))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setenv("BAINLUCK_API", "https://stub.invalid")
        monkeypatch.setenv("ADMIN_TOKEN", "stub-token")
        return calls

    def test_main_runs_end_to_end_and_writes_an_artifact(
        self, stub_transport, tmp_path, monkeypatch
    ):
        from scripts import measure_price_provenance as reader

        out = tmp_path / "pp.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "measure_price_provenance.py",
                "--cell",
                "hockey/container_member",
                "--feasibility",
                "--leg-split",
                "--out",
                str(out),
            ],
        )
        assert reader.main() == 0

        artifact = json.loads(out.read_text())
        cell = artifact["cells"]["hockey/container_member"]
        assert cell["policies"]["A_today"]["n"] == 1514
        assert cell["policies"][PROPOSED_POLICY]["delta_ece"] < -25
        assert cell["reprice_feasibility"]["totals"]["with_pre_resolution_snapshot"] == 0
        assert cell["leg_split"]["totals"]["mixed"] == 0
        assert artifact["pooled"]["A_today"]["n"] == 1514
        assert artifact["cells_unmeasured"] == 0
        # Three distinct statements actually went to the transport.
        assert len(stub_transport) == 3

    def test_a_failed_read_is_named_not_silently_dropped(
        self, stub_transport, tmp_path, monkeypatch
    ):
        """A cell that could not be measured must not vanish into a clean run.

        Gotcha #53 at the artifact level: a cell absent from the output reads
        exactly like a cell with nothing wrong with it.
        """
        import urllib.request

        def always_timeout(request, timeout=None):  # noqa: ANN001
            return type(
                "R",
                (),
                {
                    "read": lambda self: json.dumps(
                        {"detail": {"error": "query_failed", "reason": "statement_timeout"}}
                    ).encode(),
                    "__enter__": lambda self: self,
                    "__exit__": lambda self, *a: False,
                },
            )()

        monkeypatch.setattr(urllib.request, "urlopen", always_timeout)
        out = tmp_path / "pp.json"
        monkeypatch.setattr(
            sys,
            "argv",
            ["measure_price_provenance.py", "--cell", "hockey/container_member", "--out", str(out)],
        )
        assert reader_main_nonzero(out)

    def test_a_timing_out_cell_escalates_the_partition_instead_of_vanishing(
        self, tmp_path, monkeypatch
    ):
        """A partial sweep is not a smaller sweep — it MOVES the headline.

        The first real 49-cell run lost `soccer/quantity` (189K outcomes) and
        `weather/quantity` (64K) to `statement_timeout` at k=1. Both are large
        and well calibrated, so the pooled figure re-folded over the surviving
        47 read 5.02 pp where the full 49 read 3.78 pp. The absence did not
        leave a hole; it biased the pool toward the cells that were cheap to
        measure, which is codex's round-1 head-sample bias arriving by a
        different door.
        """
        import urllib.request

        seen: list[str] = []

        def timeout_at_k1(request, timeout=None):  # noqa: ANN001
            sql = json.loads(request.data.decode())["sql"]
            seen.append(sql)
            if "MOD(fm.id, 1)" in sql:
                raise urllib.error.HTTPError(
                    "u", 400, "Bad Request", {},  # type: ignore[arg-type]
                    __import__("io").BytesIO(
                        json.dumps({"detail": {"reason": "statement_timeout"}}).encode()
                    ),
                )
            payload = {
                "columns": ["price_class", "capture_class", "grade", "bin", "n", "sum_prob", "winners"],
                # one partition carries the whole fixture; the other three are empty
                "rows": (
                    [[r.price_class, r.capture_class, r.grade, r.bin, r.n, str(r.sum_prob), r.winners]
                     for r in HOCKEY_CM]
                    if "MOD(fm.id, 4) = 0" in sql
                    else []
                ),
                "duration_ms": 1.0,
                "sql_fingerprint": "stub",
            }
            return type("R", (), {
                "read": lambda self: json.dumps(payload).encode(),
                "__enter__": lambda self: self,
                "__exit__": lambda self, *a: False,
            })()

        monkeypatch.setattr(urllib.request, "urlopen", timeout_at_k1)
        monkeypatch.setenv("BAINLUCK_API", "https://stub.invalid")
        monkeypatch.setenv("ADMIN_TOKEN", "stub-token")
        out = tmp_path / "pp.json"
        monkeypatch.setattr(
            sys,
            "argv",
            ["measure_price_provenance.py", "--cell", "hockey/container_member", "--out", str(out)],
        )
        from scripts import measure_price_provenance as reader

        assert reader.main() == 0
        artifact = json.loads(out.read_text())
        cell = artifact["cells"]["hockey/container_member"]
        assert cell["read"]["partition_k"] == 4
        assert cell["read"]["partitions_attempted"] == [1, 4]
        assert cell["policies"]["A_today"]["n"] == 1514, "the whole cell still folded"
        assert artifact["cells_unmeasured"] == 0

    def test_escalation_is_bounded_and_ends_in_a_named_absence(
        self, tmp_path, monkeypatch
    ):
        """It must not retry forever, and giving up must be LOUD."""
        import urllib.request

        def always_timeout(request, timeout=None):  # noqa: ANN001
            raise urllib.error.HTTPError(
                "u", 400, "Bad Request", {},  # type: ignore[arg-type]
                __import__("io").BytesIO(
                    json.dumps({"detail": {"reason": "statement_timeout"}}).encode()
                ),
            )

        monkeypatch.setattr(urllib.request, "urlopen", always_timeout)
        monkeypatch.setenv("BAINLUCK_API", "https://stub.invalid")
        monkeypatch.setenv("ADMIN_TOKEN", "stub-token")
        out = tmp_path / "pp.json"
        monkeypatch.setattr(
            sys,
            "argv",
            ["measure_price_provenance.py", "--cell", "hockey/container_member", "--out", str(out)],
        )
        from scripts import measure_price_provenance as reader

        assert reader.main() == 1
        artifact = json.loads(out.read_text())
        assert "hockey/container_member" in artifact["unmeasured"]
        assert "hockey/container_member" not in artifact["cells"]

    def test_a_non_timeout_error_does_not_escalate(self, tmp_path, monkeypatch):
        """Escalating a 403 sixteen times is a retry storm, not a measurement."""
        import urllib.request

        calls: list[int] = []

        def forbidden(request, timeout=None):  # noqa: ANN001
            calls.append(1)
            raise urllib.error.HTTPError(
                "u", 403, "Forbidden", {},  # type: ignore[arg-type]
                __import__("io").BytesIO(b'{"detail":"bad token"}'),
            )

        monkeypatch.setattr(urllib.request, "urlopen", forbidden)
        monkeypatch.setenv("BAINLUCK_API", "https://stub.invalid")
        monkeypatch.setenv("ADMIN_TOKEN", "stub-token")
        out = tmp_path / "pp.json"
        monkeypatch.setattr(
            sys,
            "argv",
            ["measure_price_provenance.py", "--cell", "hockey/container_member", "--out", str(out)],
        )
        from scripts import measure_price_provenance as reader

        assert reader.main() == 1
        assert len(calls) == 1, "a 403 must be reported, not retried at four partitions"

    def test_a_failing_SIDE_probe_does_not_kill_the_run(
        self, stub_transport, tmp_path, monkeypatch
    ):
        """The defect the first real sweep found, in the reader's own code.

        A ``statement_timeout`` on the feasibility probe — a correlated EXISTS
        into ``futures_odds_snapshots``, much heavier than the fold — aborted a
        49-cell walk that had already measured 30 cells, because only
        ``fold_cell``'s ``ReadError`` was caught. Ruling (a) landing on its own
        author: the impure test covered one failure path and the bug was in the
        other one. So both are covered now, and the cell survives with its probe
        marked unmeasured BY NAME rather than the run dying or the probe
        silently reading as "nothing found".
        """
        import urllib.request

        real = urllib.request.urlopen

        def fail_only_feasibility(request, timeout=None):  # noqa: ANN001
            sql = json.loads(request.data.decode())["sql"]
            if "with_pre_commence_snapshot" in sql:
                raise urllib.error.HTTPError(
                    "u", 400, "Bad Request", {},  # type: ignore[arg-type]
                    __import__("io").BytesIO(
                        json.dumps({"detail": {"reason": "statement_timeout"}}).encode()
                    ),
                )
            return real(request, timeout=timeout)

        monkeypatch.setattr(urllib.request, "urlopen", fail_only_feasibility)
        out = tmp_path / "pp.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "measure_price_provenance.py",
                "--cell",
                "hockey/container_member",
                "--feasibility",
                "--leg-split",
                "--out",
                str(out),
            ],
        )
        from scripts import measure_price_provenance as reader

        assert reader.main() == 0
        cell = json.loads(out.read_text())["cells"]["hockey/container_member"]
        assert cell["policies"]["A_today"]["n"] == 1514, "the fold still landed"
        assert cell["reprice_feasibility"]["measured"] is False
        assert "statement_timeout" in cell["reprice_feasibility"]["reason"]
        assert cell["leg_split"]["totals"]["mixed"] == 0, "the other probe still ran"

    def test_a_truncated_read_is_an_error_not_a_short_fold(
        self, stub_transport, tmp_path, monkeypatch
    ):
        """1,000 rows back with ``truncated: true`` is a WRONG fold.

        ``db-query`` truncates silently at its cap. Folding the first 1,000
        groups of a cell and publishing the result as the cell is the exact
        shape of a measurement that looks fine and is not.
        """
        import urllib.request

        def truncating(request, timeout=None):  # noqa: ANN001
            payload = {
                "columns": ["price_class", "capture_class", "grade", "bin", "n", "sum_prob", "winners"],
                "rows": [],
                "truncated": True,
            }
            return type(
                "R",
                (),
                {
                    "read": lambda self: json.dumps(payload).encode(),
                    "__enter__": lambda self: self,
                    "__exit__": lambda self, *a: False,
                },
            )()

        monkeypatch.setattr(urllib.request, "urlopen", truncating)
        out = tmp_path / "pp.json"
        monkeypatch.setattr(
            sys,
            "argv",
            ["measure_price_provenance.py", "--cell", "hockey/container_member", "--out", str(out)],
        )
        assert reader_main_nonzero(out)


def reader_main_nonzero(out_path) -> bool:
    """Run ``main()``; assert it reported the cell as unmeasured, by name."""
    from scripts import measure_price_provenance as reader

    code = reader.main()
    artifact = json.loads(out_path.read_text())
    return (
        code == 1
        and artifact["cells_unmeasured"] == 1
        and "hockey/container_member" in artifact["unmeasured"]
    )
