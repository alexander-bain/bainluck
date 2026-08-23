"""The DB-direct twin of the published curve (CAL-P078, Gate 0's last blocker).

Two jobs, and the second is the one ruling 102 insists on:

1. **Pin the population.** The twin uses ``_calibration_population_ctes``
   verbatim. If anyone ever forks that predicate into a copy, this suite reds —
   in both directions — the technique CAL-P034 used for
   ``DECLARED_CENSUS_COLUMNS``.
2. **Start the reader.** ``measure_published_twin.main()`` is driven over stubs,
   including the paths that fail. CAL-P077's own sweep died in an uncovered
   branch after thirty cells and moved a pooled headline 3.76 -> 5.02 pp purely
   by absence; the lesson is that the failure paths are the ones worth starting.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.utils.calibration_published_twin import (
    FOLD_TAIL_SQL,
    TIGHT_TOLERANCE_PP,
    VERDICT_AGREES,
    VERDICT_DISAGREES,
    VERDICT_UNMEASURABLE,
    fold_rows_to_cells,
    observed_rate,
    published_population_fold_sql,
    reconcile,
    tolerance_pp,
)


def _strip_sql_comments(sql: str) -> str:
    """``--`` line comments and ``/* */`` blocks removed. Nothing else."""
    import re

    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return "\n".join(line.split("--", 1)[0] for line in sql.split("\n"))


class TestThePopulationIsTheCanonicalOne:
    def test_the_twin_is_built_on_the_frozen_builder_verbatim(self):
        """Not a copy. If it ever becomes one, this fails."""
        from app.tasks.precompute_calibration import _calibration_population_ctes

        sql = published_population_fold_sql()
        canonical = _calibration_population_ctes()
        assert sql == "WITH " + canonical + FOLD_TAIL_SQL
        assert canonical in sql, "the twin must carry the canonical chain byte-for-byte"

    def test_it_folds_the_published_row_cte_and_the_published_price(self):
        """``deduped`` and ``adj_opening_probability`` are the two names the
        route's own debug sampler reads. Counting anything else would be a
        lookalike population, which is the failure Gate 0 exists to catch."""
        sql = published_population_fold_sql()
        assert "FROM deduped d" in sql
        assert "d.adj_opening_probability" in sql
        assert "d.is_winner" in sql

    def test_it_groups_per_cell_so_two_cells_cannot_cancel(self):
        """A pooled comparison is how a 41 pp cell hid behind a -6.58 pp gap."""
        sql = published_population_fold_sql()
        assert "d.source" in sql and "d.category" in sql
        # CAL-P088 / #2111: FOUR grouping dimensions now. ``price_moved`` is the
        # payload's fourth key, and folding by three compared a pooled DB rate
        # against one arbitrary stratum.
        assert "d.price_moved" in sql
        assert "GROUP BY 1, 2, 3, 4" in sql

    def test_it_is_a_read(self):
        """Comments are stripped FIRST, and finding that out was the point.

        The canonical chain's own commentary contains the sentence "IT WOULD
        DELETE 81% OF HOCKEY", so a naive substring scan calls this statement a
        write. A guard that reds on prose is a guard people learn to skip.
        """
        sql = _strip_sql_comments(published_population_fold_sql()).upper()
        for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE"):
            assert forbidden not in sql, f"the twin issued a {forbidden.strip()}"

    def test_the_comment_stripper_does_not_hide_a_real_write(self):
        """Non-vacuity. A stripper that ate everything would pass the test above."""
        assert "DELETE" in _strip_sql_comments("SELECT 1; DELETE FROM t -- a comment").upper()
        assert "COMMENT" not in _strip_sql_comments("SELECT 1 -- a comment").upper()
        assert "BLOCK" not in _strip_sql_comments("SELECT /* a block */ 1").upper()


class TestTheBoundIsEarnedNotChosen:
    def test_an_undisclosed_bank_has_no_bound_and_no_verdict(self):
        """THE property. A curve that will not say how stale it is cannot be
        checked, and reporting that as agreement is gotcha #53 on the gate."""
        assert tolerance_pp(None) is None
        assert tolerance_pp({"measured": False, "reason": "served_at_absent"}) is None
        assert tolerance_pp({"measured": True}) is None

    def test_zero_drift_earns_the_tight_bound(self):
        staged = {"measured": True, "units_banked": 128,
                  "units_drifted": 0, "units_drift_unknown": 0}
        assert tolerance_pp(staged) == TIGHT_TOLERANCE_PP

    def test_the_bound_scales_with_disclosed_drift(self):
        staged = {"measured": True, "units_banked": 128,
                  "units_drifted": 115, "units_drift_unknown": 0}
        bound = tolerance_pp(staged)
        assert bound is not None and bound > 80, "a 90%-drifted bank proves little"

    def test_an_unknown_remainder_counts_as_drift(self):
        """CAL-P069: six unmeasurable units published as ``drifted: 0``. The
        unknown must widen the bound, never tighten it."""
        known = {"measured": True, "units_banked": 128,
                 "units_drifted": 0, "units_drift_unknown": 0}
        unknown = {"measured": True, "units_banked": 128,
                   "units_drifted": 0, "units_drift_unknown": 6}
        assert tolerance_pp(unknown) > tolerance_pp(known)

    def test_the_bound_never_exceeds_the_whole_range(self):
        staged = {"measured": True, "units_banked": 10,
                  "units_drifted": 40, "units_drift_unknown": 40}
        assert tolerance_pp(staged) == 100.0


class TestTheReconciliation:
    @staticmethod
    def _cells(rate: float, n: int = 100):
        # CAL-P088 / #2111: the bucket key is (bucket_idx, price_moved). These
        # fixtures do not set ``price_moved`` on the published side either, so
        # both sides normalize to ``None`` and every assertion below is
        # unchanged in meaning — only the key's SHAPE moved.
        return {("kalshi", "sports"): {(3, None): {"n": n, "winners": int(n * rate),
                                                   "sum_prob": n * 0.35}}}

    @staticmethod
    def _published(rate: float):
        return [{"source": "kalshi", "category": "sports", "bucket_idx": 3,
                 "actual_rate": rate}]

    def _staged(self, drifted=0):
        return {"measured": True, "units_banked": 128,
                "units_drifted": drifted, "units_drift_unknown": 0}

    def test_agreement_within_the_bound(self):
        out = reconcile(db_cells=self._cells(0.35),
                        published_buckets=self._published(0.35),
                        staged=self._staged())
        assert out["verdict"] == VERDICT_AGREES
        assert out["compared"] == 1
        assert out["outside"] == []

    def test_a_real_disagreement_is_reported(self):
        out = reconcile(db_cells=self._cells(0.35),
                        published_buckets=self._published(0.60),
                        staged=self._staged())
        assert out["verdict"] == VERDICT_DISAGREES
        assert len(out["outside"]) == 1
        assert out["outside"][0]["delta_pp"] == pytest.approx(25.0)

    def test_the_same_gap_is_within_bound_on_a_heavily_drifted_bank(self):
        """Not a weaker test — an honest one. A 90%-drifted census cannot be
        held to a half-point, and pretending otherwise files false findings."""
        out = reconcile(db_cells=self._cells(0.35),
                        published_buckets=self._published(0.60),
                        staged=self._staged(drifted=115))
        assert out["verdict"] == VERDICT_AGREES
        assert out["worst_delta_pp"] == pytest.approx(25.0), (
            "the delta is still reported — it is the VERDICT that is bounded"
        )

    def test_an_undisclosed_bank_is_unmeasurable_not_agreeing(self):
        out = reconcile(db_cells=self._cells(0.35),
                        published_buckets=self._published(0.35),
                        staged={"measured": False, "reason": "served_at_absent"})
        assert out["verdict"] == VERDICT_UNMEASURABLE
        assert out["tolerance_pp"] is None

    def test_a_cell_on_only_one_side_is_counted_never_skipped(self):
        """An instrument that quietly compares the intersection reports its
        cleanest number on its worst day.

        ⚠️ **The verdict on this fixture CHANGED in CAL-P086B, deliberately.**
        It used to assert ``AGREES`` with the comment *"nothing compared,
        nothing outside"* — and that was the defect, stated out loud in an
        assertion: the payload here carries a ``polymarket`` cell, polymarket
        is a source the fold's population DOES cover, and the fold produced no
        row for it. That is the twin and the producer disagreeing about the
        population, over a run that compared zero buckets. ``agrees`` is the
        word a certifier reads.

        The counting half of this test's point is unchanged and still asserted:
        both sides are still counted, neither is skipped. What changed is that
        an IN-SCOPE published-only cell now reaches the verdict. See
        ``tests/test_calibration_twin_scope_p086b.py`` for the split and the
        measurement (203 of 285 published cells are structurally out of scope,
        which is why the out-of-scope half must NOT do this)."""
        out = reconcile(
            db_cells=self._cells(0.35),
            published_buckets=[{"source": "polymarket", "category": "politics",
                                "bucket_idx": 7, "actual_rate": 0.7}],
            staged=self._staged(),
        )
        assert out["compared"] == 0
        assert len(out["db_only"]) == 1
        assert len(out["published_only"]) == 1
        assert out["verdict"] == VERDICT_DISAGREES, (
            "polymarket is IN the fold's population, so a published cell with "
            "no twin row is a population disagreement, not a scope limit"
        )
        assert len(out["published_only_in_scope"]) == 1
        assert out["published_only_out_of_scope"] == []
        assert out["cells_db"] == 1 and out["cells_published"] == 1

    def test_winners_over_n_is_accepted_when_no_rate_is_given(self):
        out = reconcile(
            db_cells=self._cells(0.35),
            published_buckets=[{"source": "kalshi", "category": "sports",
                                "bucket_idx": 3, "n": 200, "winners": 70}],
            staged=self._staged(),
        )
        assert out["compared"] == 1
        assert out["verdict"] == VERDICT_AGREES

    def test_an_empty_bucket_has_no_rate_rather_than_a_zero_one(self):
        assert observed_rate({"n": 0, "winners": 0}) is None
        assert observed_rate({"n": 4, "winners": 1}) == 0.25


class TestTheFold:
    def test_rows_become_cells_from_either_row_shape(self):
        rows = [
            SimpleNamespace(source="kalshi", category="sports", bucket_idx=2,
                            n=10, winners=3, sum_prob=2.5),
            SimpleNamespace(source="kalshi", category="sports", bucket_idx=3,
                            n=20, winners=8, sum_prob=7.0),
        ]
        cells = fold_rows_to_cells(rows)
        assert set(cells) == {("kalshi", "sports")}
        # CAL-P088 / #2111: these rows carry no ``price_moved`` attribute, so it
        # normalizes to ``None`` — the CELL key is unchanged, the BUCKET key is
        # now a pair.
        assert cells[("kalshi", "sports")][(3, None)]["winners"] == 8

    def test_a_null_bucket_row_is_not_a_bucket(self):
        rows = [SimpleNamespace(source="kalshi", category="sports", bucket_idx=None,
                                n=5, winners=1, sum_prob=1.0)]
        assert fold_rows_to_cells(rows) == {}


# =============================================================================
# Ruling 102 — start the reader
# =============================================================================


class TestTheReaderRuns:
    @pytest.mark.asyncio
    async def test_plan_only_prints_the_sql_and_exits_clean(self, capsys):
        from scripts.measure_published_twin import main

        code = await main(["--plan-only"])
        assert code == 0
        assert "FROM deduped d" in capsys.readouterr().out

    @pytest.mark.asyncio
    async def test_a_full_run_over_stubs_produces_an_artifact(
        self, monkeypatch, tmp_path, capsys
    ):
        import scripts.measure_published_twin as mod

        async def fake_fold(*, timeout_ms):
            return (
                [SimpleNamespace(source="kalshi", category="sports", bucket_idx=3,
                                 n=100, winners=35, sum_prob=35.0)],
                1.5,
                None,
            )

        monkeypatch.setattr(mod, "_fold", fake_fold)
        monkeypatch.setattr(
            mod, "_load_payload",
            lambda args: (
                {
                    "generated_at": "2026-08-20T06:00:00Z",
                    "availability": "fresh",
                    "buckets": [{"source": "kalshi", "category": "sports",
                                 "bucket_idx": 3, "actual_rate": 0.35}],
                    "staged": {"measured": True, "units_banked": 128,
                               "units_drifted": 0, "units_drift_unknown": 0},
                },
                None,
            ),
        )
        out = tmp_path / "twin.json"
        code = await mod.main(["--out", str(out)])
        assert code == 0
        artifact = json.loads(out.read_text())
        assert artifact["verdict"] == "agrees"
        assert artifact["db_rows"] == 100
        assert artifact["fold_error"] is None

    @pytest.mark.asyncio
    async def test_a_failed_fold_can_never_present_as_agreement(
        self, monkeypatch, tmp_path
    ):
        """The branch that matters. Zero rows compared against a payload agrees
        vacuously; the artifact must say the read DIED, and exit non-zero."""
        import scripts.measure_published_twin as mod

        async def dead_fold(*, timeout_ms):
            return [], 240.0, "OperationalError: canceling statement due to statement timeout"

        monkeypatch.setattr(mod, "_fold", dead_fold)
        monkeypatch.setattr(
            mod, "_load_payload",
            lambda args: (
                {"buckets": [], "staged": {"measured": True, "units_banked": 128,
                                           "units_drifted": 0, "units_drift_unknown": 0}},
                None,
            ),
        )
        out = tmp_path / "dead.json"
        code = await mod.main(["--out", str(out)])
        assert code == 2, "could-not-check is its own exit code, not a failure and not a pass"
        artifact = json.loads(out.read_text())
        assert artifact["verdict"] == "unmeasurable"
        assert "statement timeout" in artifact["unmeasurable_reason"]

    @pytest.mark.asyncio
    async def test_an_unreachable_api_is_unmeasurable_not_a_disagreement(
        self, monkeypatch, tmp_path
    ):
        import scripts.measure_published_twin as mod

        async def fake_fold(*, timeout_ms):
            return (
                [SimpleNamespace(source="kalshi", category="sports", bucket_idx=3,
                                 n=100, winners=35, sum_prob=35.0)],
                1.0,
                None,
            )

        monkeypatch.setattr(mod, "_fold", fake_fold)
        monkeypatch.setattr(mod, "_load_payload", lambda args: ({}, "api_unreachable: URLError"))
        code = await mod.main(["--out", str(tmp_path / "x.json")])
        assert code == 2

    @pytest.mark.asyncio
    async def test_a_real_disagreement_exits_one(self, monkeypatch, tmp_path):
        """Exit 1 is reserved for 'what you asked me to check failed'
        (gotcha #54's amendment). Everything else is a story about the harness."""
        import scripts.measure_published_twin as mod

        async def fake_fold(*, timeout_ms):
            return (
                [SimpleNamespace(source="kalshi", category="sports", bucket_idx=3,
                                 n=100, winners=90, sum_prob=35.0)],
                1.0,
                None,
            )

        monkeypatch.setattr(mod, "_fold", fake_fold)
        monkeypatch.setattr(
            mod, "_load_payload",
            lambda args: (
                {
                    "buckets": [{"source": "kalshi", "category": "sports",
                                 "bucket_idx": 3, "actual_rate": 0.35}],
                    "staged": {"measured": True, "units_banked": 128,
                               "units_drifted": 0, "units_drift_unknown": 0},
                },
                None,
            ),
        )
        code = await mod.main(["--out", str(tmp_path / "d.json")])
        assert code == 1

    @pytest.mark.asyncio
    async def test_the_real_fold_path_imports_and_opens_a_session(self, monkeypatch):
        """THE branch every other test in this class stubs out — and the one
        that was broken.

        Ruling 102, paying out against its own use for the second window running.
        Every test above monkeypatches ``_fold``, so ``from app.database import
        get_task_session`` — a module that does not exist; it is
        ``app.tasks.base`` — was never executed. The reader died on line 63 the
        first time a human ran it, exactly as ``cohort_cell_census`` died in
        73 ms with 37 green tests behind it.

        So this test starts the REAL ``_fold``, with only the session boundary
        stubbed. It fails if the import moves again.
        """
        import contextlib

        import scripts.measure_published_twin as mod
        from app.tasks import base as task_base

        executed: list[str] = []

        class _Session:
            async def execute(self, statement, params=None):
                executed.append(str(statement))
                return SimpleNamespace(all=lambda: [])

        @contextlib.asynccontextmanager
        async def fake_session():
            yield _Session()

        monkeypatch.setattr(task_base, "get_task_session", fake_session)

        rows, duration_s, error = await mod._fold(timeout_ms=1234)
        assert error is None, f"the real fold path raised: {error}"
        assert rows == []
        assert duration_s >= 0
        assert any("statement_timeout = 1234" in s for s in executed), (
            "the read must be bounded — an unbounded fold is how a sweep dies "
            "after thirty cells and moves a headline by absence"
        )
        assert any("FROM deduped d" in s for s in executed)

    @pytest.mark.asyncio
    async def test_a_raising_session_is_returned_not_thrown(self, monkeypatch):
        """The error is RETURNED so the artifact records that the read was
        ATTEMPTED and failed — a different fact from a read never made."""
        import contextlib

        import scripts.measure_published_twin as mod
        from app.tasks import base as task_base

        @contextlib.asynccontextmanager
        async def dead_session():
            raise RuntimeError("connection refused")
            yield  # pragma: no cover

        monkeypatch.setattr(task_base, "get_task_session", dead_session)
        rows, _duration, error = await mod._fold(timeout_ms=1000)
        assert rows == []
        assert "RuntimeError: connection refused" == error
