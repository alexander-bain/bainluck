"""CAL-P092 — the evidence the WHICHPRICE cert's attacks 1, 3 and 7 each demand.

``C-APPLY-PRE-WHICHPRICE-R3`` returned BLOCK on three findings, all of the same
family: the fold is right, and the artifact cannot prove it.

* **[P1] attack 1** — "the artifact contains zero ``rows``, ``bins``,
  ``sum_prob``, or ``winners`` fields … for policy C, the committed pooled value
  is ``1.7422 pp``, while the only available aggregation of cell ECEs is
  ``4.2831 pp``; bin-level cancellation is unknowable from the artifact." Fix:
  commit the grouped inputs AND a recomputation receipt that proves the displayed
  table from them.
* **[P1] attack 3** — "the R3 artifact contains neither ``leg_split`` nor
  ``reprice_feasibility`` … Repeating a prior full-population count after the
  certified population moved is not a current measurement." Fix: re-run
  ``LEG_SPLIT_SQL`` on the same 49-cell snapshot and commit per-cell totals.
* **[P1] attack 7** — "``partition_k: 4`` … There is no successful ``k=1`` table
  and no ``k=16`` read anywhere in the artifact. The committed test only proves
  the SQL text partitions on ``fm.id``; it does not compare two database
  results." Fix: execute both and compare the tables.

**Nothing in this file modifies the fold.** ``app/utils/calibration_price_provenance.py``
is untouched by CAL-P092 — this is an evidence round. Everything here is in the
reader (``scripts/measure_price_provenance.py``) and in the independent verifier
(``scripts/verify_price_provenance_artifact.py``), which is deliberately barred
from importing the fold at all.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import measure_price_provenance as reader  # noqa: E402
from scripts import verify_price_provenance_artifact as receipt  # noqa: E402


# =============================================================================
# Attack 1a — the committed inputs
# =============================================================================


class TestTheCommittedInputsAreTheInputsAndNotTheAnswers:
    def test_canonical_raw_stringifies_and_sorts(self):
        rows = [
            ["cp_moved", "pregame", "complete", 7, 10, 0.7, 6],
            ["cp_absent", "pregame", "complete", 1, 5, 0.1, 0],
        ]
        out = reader.canonical_raw(rows)
        assert out == [
            ["cp_absent", "pregame", "complete", "1", "5", "0.1", "0"],
            ["cp_moved", "pregame", "complete", "7", "10", "0.7", "6"],
        ]

    def test_the_committed_value_is_the_string_the_rail_returned(self):
        """Not a float round-trip.

        ``sum_prob`` arrives as a numeric string. Parsing it to a double and
        re-serialising would make the receipt re-derive from the producer's
        rounding rather than from the database's answer — a receipt that agrees
        with the producer because it inherited its arithmetic proves nothing.
        """
        rows = [["a", "b", "complete", "3", "7", "1.234567890123456789", "2"]]
        assert reader.canonical_raw(rows)[0][5] == "1.234567890123456789"

    def test_a_row_order_change_does_not_change_the_fingerprint(self):
        rows = [
            ["cp_moved", "pregame", "complete", "7", "10", "0.7", "6"],
            ["cp_absent", "pregame", "complete", "1", "5", "0.1", "0"],
        ]
        assert reader.raw_fingerprint(rows) == reader.raw_fingerprint(rows[::-1])

    def test_a_single_changed_count_does_change_it(self):
        rows = [["cp_moved", "pregame", "complete", "7", "10", "0.7", "6"]]
        other = [["cp_moved", "pregame", "complete", "7", "11", "0.7", "6"]]
        assert reader.raw_fingerprint(rows) != reader.raw_fingerprint(other)


class TestReAggregationIsExactAndPartitionOrderFree:
    """Attack 7's comparison rests on this, so it is tested on its own.

    A ``k``-way partition emits the same ``(grade, bin, level…)`` key once per
    partition. Comparing the verbatim rows across ``k`` would report "the
    partitions disagree" for every cell that was ever partitioned — a false
    alarm, and the wrong kind: it would make the invariance check look executed
    while measuring nothing about the fold.
    """

    def test_duplicate_keys_from_two_partitions_sum(self):
        rows = [
            ["complete", "5", "2", "1.010000", "1"],
            ["complete", "5", "3", "1.490000", "2"],
        ]
        assert reader.aggregate_raw(rows) == [["complete", "5", "5", "2.5", "3"]]

    def test_the_sum_is_decimal_exact_not_float(self):
        """0.1 + 0.2 must be 0.3, or a partitioned read never matches a whole one."""
        rows = [
            ["complete", "1", "1", "0.1", "0"],
            ["complete", "1", "1", "0.2", "1"],
        ]
        assert reader.aggregate_raw(rows) == [["complete", "1", "2", "0.3", "1"]]

    def test_a_whole_read_and_its_partitions_agree(self):
        whole = [["complete", "5", "5", "2.500000", "3"]]
        parts = [
            ["complete", "5", "2", "1.010000", "1"],
            ["complete", "5", "3", "1.490000", "2"],
        ]
        assert reader.aggregate_fingerprint(whole) == reader.aggregate_fingerprint(parts)
        # ...and the verbatim form does NOT, which is why the comparison moved.
        assert reader.raw_fingerprint(whole) != reader.raw_fingerprint(parts)

    def test_a_real_disagreement_is_still_caught(self):
        whole = [["complete", "5", "5", "2.500000", "3"]]
        parts = [
            ["complete", "5", "2", "1.010000", "1"],
            ["complete", "5", "3", "1.490000", "3"],
        ]
        assert reader.aggregate_fingerprint(whole) != reader.aggregate_fingerprint(parts)


# =============================================================================
# Attack 1b — the recomputation receipt
# =============================================================================


def _artifact(**overrides: Any) -> dict[str, Any]:
    """A two-cell artifact whose pooled ECE is NOT the average of its cells.

    The bins are chosen so cell-level cancellation is real: cell one is
    over-priced in bin 8 and cell two is under-priced in the same bin, so the
    pooled fold partly cancels and the unweighted cell average does not.
    """
    schema = {
        "row_fold": ["price_class", "capture_class", "grade", "bin", "n", "sum_prob", "winners"],
        "whole_market": [
            "grade", "bin", "mkt_price_level", "mkt_capture_level",
            "mkt_capture_level_pop", "n", "sum_prob", "winners",
        ],
    }
    cells = {
        "alpha/quantity": {
            "raw_rows": [
                ["cp_moved", "pregame", "complete", "8", "100", "85.0", "40"],
                ["cp_moved", "after_resolution", "complete", "9", "50", "47.5", "50"],
            ]
        },
        "beta/quantity": {
            "raw_rows": [
                ["cp_moved", "pregame", "complete", "8", "100", "85.0", "100"],
                ["cp_absent", "pregame", "complete", "2", "60", "15.0", "6"],
            ]
        },
    }
    art: dict[str, Any] = {"raw_rows_schema": schema, "cells": cells}
    art.update(overrides)
    return art


def _fill_committed(art: dict[str, Any]) -> dict[str, Any]:
    """Compute the tables the producer WOULD commit, using the receipt's own fold.

    Circular on purpose: these fixtures test the receipt's ability to detect a
    DIFFERENCE. The non-circular proof is the live artifact, checked in
    ``TestTheLiveArtifactCarriesItsOwnEvidence``.
    """
    schema = art["raw_rows_schema"]
    pooled: list[dict[str, str]] = []
    for cell in art["cells"].values():
        rows = receipt.as_dicts(cell["raw_rows"], schema["row_fold"])
        pooled.extend(rows)
        cell["policies"] = receipt.table(rows, receipt.ROW_POLICIES)
    art["pooled"] = receipt.table(pooled, receipt.ROW_POLICIES)
    return art


class TestTheReceiptProvesTheTableFromTheInputs:
    def test_a_faithful_artifact_verifies(self):
        result = receipt.verify(_fill_committed(_artifact()))
        assert result["verdict"] is True, result["problems"]
        assert result["checked"]["cells_row_fold"] == 2
        assert result["checked"]["pooled"] == 1

    def test_the_pooled_figure_is_not_the_cell_average(self):
        """The cert's own arithmetic, reproduced on a fixture.

        R3 could offer only ``4.2831`` against a committed ``1.7422``. That gap is
        not an error — it is what a pooled ECE and a cell average ARE. The
        receipt exists because only the bins can tell them apart.
        """
        art = _fill_committed(_artifact())
        pooled = art["pooled"]["A_today"]["ece"]
        cells = [c["policies"]["A_today"]["ece"] for c in art["cells"].values()]
        assert pooled != round(sum(cells) / len(cells), 4)

    def test_a_tampered_headline_is_caught(self):
        art = _fill_committed(_artifact())
        art["pooled"]["C_exclude_hindsight"]["ece"] += 0.5
        result = receipt.verify(art)
        assert result["verdict"] is False
        assert any("pooled.C_exclude_hindsight.ece" in p for p in result["problems"])

    def test_a_tampered_cell_is_caught(self):
        art = _fill_committed(_artifact())
        art["cells"]["alpha/quantity"]["policies"]["A_today"]["n"] += 1
        result = receipt.verify(art)
        assert result["verdict"] is False
        assert any("alpha/quantity.policies.A_today.n" in p for p in result["problems"])

    def test_an_artifact_of_answers_only_is_REFUSED_not_passed(self):
        """The R3 artifact's exact shape. Absence of inputs is a failure, not a pass.

        Gotcha #53, applied to a verifier: "nothing to check" and "everything
        checked out" must never return the same verdict.
        """
        art = _fill_committed(_artifact())
        del art["raw_rows_schema"]
        result = receipt.verify(art)
        assert result["verdict"] is False
        assert "commits answers, not inputs" in result["reason"]

    def test_an_artifact_with_a_schema_but_no_rows_is_also_refused(self):
        art = _artifact()
        for cell in art["cells"].values():
            del cell["raw_rows"]
        result = receipt.verify(art)
        assert result["verdict"] is False
        assert any("nothing was re-derived" in p for p in result["problems"])

    def test_a_shifted_column_raises_rather_than_re_deriving_a_plausible_table(self):
        art = _fill_committed(_artifact())
        art["cells"]["alpha/quantity"]["raw_rows"][0].append("extra")
        with pytest.raises(ValueError, match="row width"):
            receipt.verify(art)

    def test_the_receipt_does_not_import_the_fold(self):
        """Independence, asserted rather than intended.

        If the verifier imported ``calibration_price_provenance`` it would be the
        producer checking itself — the self-oracle family this whole round is
        about.
        """
        import ast

        tree = ast.parse(Path(receipt.__file__).read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any("calibration_price_provenance" in m for m in imported), imported
        assert not any(m.startswith("app.") for m in imported), imported

    def test_the_exact_and_float_passes_are_both_reported(self):
        rows = receipt.as_dicts(
            _artifact()["cells"]["alpha/quantity"]["raw_rows"],
            _artifact()["raw_rows_schema"]["row_fold"],
        )
        folded = receipt.fold(rows, receipt.ROW_POLICIES["A_today"])
        assert folded["ece"] is not None and folded["ece_exact"] is not None
        assert abs(folded["ece"] - folded["ece_exact"]) <= receipt.ROUNDING_SLACK_PP

    def test_below_the_floor_the_ece_is_absent_with_a_reason(self):
        art = {
            "raw_rows_schema": _artifact()["raw_rows_schema"],
            "cells": {
                "tiny/quantity": {
                    "raw_rows": [["cp_moved", "pregame", "complete", "5", "4", "2.0", "2"]]
                }
            },
        }
        _fill_committed(art)
        assert art["cells"]["tiny/quantity"]["policies"]["A_today"]["ece"] is None
        assert "below_min_cell_n" in art["cells"]["tiny/quantity"]["policies"]["A_today"]["reason"]
        assert receipt.verify(art)["verdict"] is True


# =============================================================================
# Attack 3 — the leg split, pooled, on THIS population
# =============================================================================


class TestTheLegSplitPoolsOnlyWhenItIsComplete:
    def test_the_pool_sums_every_measured_cell(self, stub_leg_split, tmp_path, monkeypatch):
        code, artifact = stub_leg_split(tmp_path, monkeypatch, ["--leg-split"])
        assert code == 0
        pooled = artifact["pooled_leg_split"]
        assert pooled["totals"] == {"markets": 8, "all_after": 2, "none_after": 4, "mixed": 2}
        assert pooled["complete"] is True
        assert pooled["cells_unmeasured"] == []

    def test_an_unmeasured_cell_makes_the_pool_incomplete_by_name(
        self, stub_leg_split, tmp_path, monkeypatch
    ):
        """A partial sum presented as a population count is attack 3's defect.

        The original ``101 / 464,777`` was a whole-population number carried
        forward onto a population that had moved by 1,616 rows. A pool that
        silently omits a timed-out cell repeats that in miniature.
        """
        code, artifact = stub_leg_split(
            tmp_path, monkeypatch, ["--leg-split"], fail_cell="beta/quantity"
        )
        pooled = artifact["pooled_leg_split"]
        assert pooled["complete"] is False
        assert pooled["cells_unmeasured"] == ["beta/quantity"]
        assert pooled["cells_measured"] == 1
        assert code == 0, "a side-probe timeout must not kill the fold (CAL-P077 ruling (a))"


# =============================================================================
# Attack 7 — two database results, compared
# =============================================================================


class TestPartitionInvarianceComparesResultsNotSqlText:
    def test_agreeing_partitions_produce_a_true_verdict(self, stub_invariance, tmp_path, monkeypatch):
        code, artifact = stub_invariance(tmp_path, monkeypatch, ks=[1, 4, 16])
        assert code == 0
        inv = artifact["partition_invariance"]["alpha/quantity"]
        assert inv["verdict"] is True
        assert set(inv["policy_tables_byte_equal"]) == {"1", "16", "4"}
        assert all(inv["policy_tables_byte_equal"].values())
        assert all(inv["raw_rows_equal"].values())

    def test_a_disagreeing_partition_produces_a_false_verdict(
        self, stub_invariance, tmp_path, monkeypatch
    ):
        code, artifact = stub_invariance(tmp_path, monkeypatch, ks=[1, 4], corrupt_k=4)
        inv = artifact["partition_invariance"]["alpha/quantity"]
        assert inv["verdict"] is False
        assert inv["policy_tables_byte_equal"]["4"] is False
        assert code == 1, "the run must exit non-zero when the fold is not invariant"

    def test_a_timed_out_k_is_unmeasured_and_never_agreement(
        self, stub_invariance, tmp_path, monkeypatch
    ):
        """Gotcha #53's rule applied to attack 7's own instrument.

        The R3 run's ``k=1`` timed out and the artifact recorded ``partition_k:
        4``. Two reads never happened, and nothing in the artifact said so in the
        verdict. Here an unmeasured ``k`` is named and forces the verdict false.
        """
        code, artifact = stub_invariance(tmp_path, monkeypatch, ks=[1, 4], timeout_k=1)
        inv = artifact["partition_invariance"]["alpha/quantity"]
        assert "1" in inv["unmeasured"]
        assert inv["verdict"] in (False, None)
        assert code == 1

    def test_one_measured_k_cannot_be_a_verdict(self, stub_invariance, tmp_path, monkeypatch):
        code, artifact = stub_invariance(tmp_path, monkeypatch, ks=[1, 4], timeout_k=4)
        inv = artifact["partition_invariance"]["alpha/quantity"]
        assert inv["verdict"] is None
        assert "needs two measured k" in inv["reason"]


# =============================================================================
# The live artifact — this round's actual deliverable
# =============================================================================


R4 = Path(__file__).resolve().parents[2] / "artifacts" / "cal-p092" / (
    "price-provenance-whole-market-r4.json"
)


@pytest.mark.skipif(not R4.exists(), reason="the R4 sweep artifact is not in this tree")
class TestTheLiveArtifactCarriesItsOwnEvidence:
    @pytest.fixture(scope="class")
    def artifact(self) -> dict[str, Any]:
        return json.loads(R4.read_text())

    def test_attack_1_the_receipt_reproduces_the_committed_tables(self, artifact):
        result = receipt.verify(artifact)
        assert result["verdict"] is True, result["problems"][:10]
        assert result["checked"]["cells_row_fold"] >= 40

    def test_attack_1_the_cell_average_is_recorded_as_the_counter_example(self, artifact):
        result = receipt.verify(artifact)
        pooled = artifact["pooled_whole_market"]["all_legs"]["C_exclude_hindsight"]["ece"]
        assert result["unweighted_cell_average_C_whole_market"] != pooled

    def test_attack_3_the_leg_split_is_measured_on_this_population(self, artifact):
        pooled = artifact["pooled_leg_split"]
        assert pooled["complete"] is True, pooled["cells_unmeasured"]
        assert pooled["totals"]["markets"] > 0
        assert "mixed" in pooled["totals"]

    def test_attack_7_two_reads_were_compared_at_k_1_and_k_16(self, artifact):
        tables = artifact["partition_invariance"]
        proved = [
            cell
            for cell, inv in tables.items()
            if inv.get("verdict") and {"1", "16"} <= set(inv["policy_tables_byte_equal"])
        ]
        assert proved, "no cell has a successful k=1 AND k=16 comparison"

    def test_the_fold_module_is_unchanged_by_this_round(self):
        """An evidence round that edits the fold is a fix round wearing its badge."""
        import subprocess

        root = Path(__file__).resolve().parents[2]
        base = "e03076ae"  # CAL-P091's head, this round's base
        known = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{base}^{{commit}}"],
            capture_output=True, text=True,
        )
        if known.returncode != 0:
            pytest.skip(f"{base} is not in this clone — nothing to compare against")
        diff = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", base, "--",
             "backend/app/utils/calibration_price_provenance.py"],
            capture_output=True, text=True,
        )
        assert diff.stdout.strip() == "", (
            "CAL-P092 modified the fold; the directive says evidence, not fix"
        )


# =============================================================================
# Fixtures
# =============================================================================


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


ROW_COLUMNS = ["price_class", "capture_class", "grade", "bin", "n", "sum_prob", "winners"]
MARKET_COLUMNS = [
    "grade", "bin", "mkt_price_level", "mkt_capture_level",
    "mkt_capture_level_pop", "n", "sum_prob", "winners",
]
ROW_PAYLOAD = [
    ["cp_moved", "pregame", "complete", 8, 100, "85.0", 40],
    ["cp_moved", "after_resolution", "complete", 9, 50, "47.5", 50],
]


@pytest.fixture
def stub_leg_split(monkeypatch):
    import urllib.request

    def run(tmp_path, mp, extra: list[str], fail_cell: str | None = None):
        def fake_urlopen(request, timeout=None):  # noqa: ANN001
            sql = json.loads(request.data.decode())["sql"]
            if fail_cell and f"= '{fail_cell.split('/')[0]}'" in sql and "per_market" in sql:
                raise reader.ReadError("statement timeout")
            if "per_market" in sql:
                return _Response({
                    "columns": ["markets", "all_after", "none_after", "mixed"],
                    "rows": [[4, 1, 2, 1]],
                    "duration_ms": 1.0, "sql_fingerprint": "stub-leg-split",
                })
            return _Response({
                "columns": ROW_COLUMNS, "rows": [list(r) for r in ROW_PAYLOAD],
                "duration_ms": 1.0, "sql_fingerprint": "stub-fold",
            })

        mp.setattr(urllib.request, "urlopen", fake_urlopen)
        mp.setenv("BAINLUCK_API", "https://stub.invalid")
        mp.setenv("ADMIN_TOKEN", "stub-token")
        out = tmp_path / "artifact.json"
        mp.setattr(sys, "argv", [
            "measure_price_provenance.py",
            "--cell", "alpha/quantity", "--cell", "beta/quantity",
            "--out", str(out), *extra,
        ])
        code = reader.main()
        return code, json.loads(out.read_text())

    return run


@pytest.fixture
def stub_invariance(monkeypatch):
    import urllib.request

    def run(tmp_path, mp, ks: list[int], corrupt_k: int | None = None,
            timeout_k: int | None = None):
        def market_rows(k: int, m: int) -> list[list[Any]]:
            # One market per partition slot, so every k covers the same population
            # and a k-way read is genuinely the same fold split k ways.
            rows = []
            for i in range(4):
                if i % k != m:
                    continue
                winners = 1 if i < 2 else 0
                if corrupt_k == k and i == 0:
                    winners = 0
                rows.append([
                    "complete", 8, "all_moved", "all_pregame_or_nots",
                    "all_pregame_or_nots", 10, "8.5", winners,
                ])
            return rows

        def fake_urlopen(request, timeout=None):  # noqa: ANN001
            body = json.loads(request.data.decode())
            sql = body["sql"]
            if "mkt_capture_level_pop" in sql:
                k = int(sql.split("MOD(fm.id, ")[1].split(")")[0])
                m = int(sql.split("MOD(fm.id, ")[1].split("= ")[1].split("\n")[0])
                if timeout_k == k:
                    raise reader.ReadError("statement timeout")
                return _Response({
                    "columns": MARKET_COLUMNS, "rows": market_rows(k, m),
                    "duration_ms": 1.0, "sql_fingerprint": f"stub-wm-{k}-{m}",
                })
            return _Response({
                "columns": ROW_COLUMNS, "rows": [list(r) for r in ROW_PAYLOAD],
                "duration_ms": 1.0, "sql_fingerprint": "stub-fold",
            })

        mp.setattr(urllib.request, "urlopen", fake_urlopen)
        mp.setenv("BAINLUCK_API", "https://stub.invalid")
        mp.setenv("ADMIN_TOKEN", "stub-token")
        out = tmp_path / "artifact.json"
        spec = "alpha/quantity:" + ",".join(str(k) for k in ks)
        mp.setattr(sys, "argv", [
            "measure_price_provenance.py",
            "--invariance", spec, "--out", str(out),
        ])
        code = reader.main()
        return code, json.loads(out.read_text())

    return run
