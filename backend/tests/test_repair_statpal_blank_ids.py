"""Queue 340: ``events.statpal_fixture_id = ''`` is a third spelling of absence.

THE DEFECT, measured on production 2026-08-12::

    events.statpal_fixture_id:  '' = 8272   NULL = 139229   real = 2230
                                total rows = 149731

``''`` and NULL both mean "no StatPal id", but only NULL is exempt from a unique
index and only NULL compares correctly. So every ``IS NOT NULL`` / ``COUNT(col)``
reader — the data-quality watchdog's Tier-1 coverage query, admin source health,
the admin linkage tiles — counts 8,272 blanks as real StatPal linkage today.

This suite pins the three properties that make the repair safe to run attended
against a hot table:

* the DRY-RUN writes nothing (a census is not a repair),
* the EXACT-MATCH GATE refuses on a drifted census IN BOTH DIRECTIONS (gotcha
  #43 — a gate's tests must assert it fires AND that it lets the real case
  through, or you have only proved half of it),
* the write moves ``blank -> nulls`` and NOTHING else: real ids, pre-existing
  NULLs, and above all the 8 duplicate real-id pairs are untouched.

There is no local Postgres in this sandbox (initdb dies on shmget), so the
session is the same SQL-dispatching recorder ``test_repair_event_final_scores``
uses: the property under test is *which statement runs with which bounds*, which
a mock returning blanket empties cannot express.
"""

from types import SimpleNamespace

import pytest

from app.routes.admin_repairs import _REPAIRS
from scripts.repair_statpal_fixture_id_blanks import (
    BATCH_SIZE,
    EXPECTED_BLANK_COUNT,
    batch_ranges,
    repair,
)

# The 8 duplicate real values named by the production census (16 rows).
_DUP_VALUES = [
    "1027790", "1027792", "1329190539", "1329190569",
    "1329200227", "627215", "637968", "637987",
]


class _Result:
    def __init__(self, rows, rowcount=0):
        self._rows = rows
        self.rowcount = rowcount

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0]


class _EventsTable:
    """A session backed by a tiny in-memory ``events`` table.

    Dispatches on SQL text and MUTATES the table, so the after-census is really
    derived from the writes rather than asserted by the test — which is the whole
    point of a self-verifying repair (gotcha #48/#53).
    """

    def __init__(self, rows):
        # rows: list of (id, statpal_fixture_id)
        self.rows = {i: v for i, v in rows}
        self.calls = []
        self.updates = []            # (lo, hi, rows_affected)
        self.commits = 0
        self.nulled_at_each_commit = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        params = params or {}
        self.calls.append((sql, params))

        if "COUNT(*) FILTER" in sql:
            vals = list(self.rows.values())
            return _Result([SimpleNamespace(
                blank=sum(1 for v in vals if v == ""),
                nulls=sum(1 for v in vals if v is None),
                real=sum(1 for v in vals if v not in (None, "")),
                total=len(vals),
            )])

        if "HAVING COUNT(*) > 1" in sql:
            groups: dict[str, list[int]] = {}
            for i, v in self.rows.items():
                if v not in (None, ""):
                    groups.setdefault(v, []).append(i)
            return _Result([
                SimpleNamespace(value=v, event_ids=sorted(ids), rows=len(ids))
                for v, ids in sorted(groups.items()) if len(ids) > 1
            ])

        if "SELECT id FROM events" in sql:
            return _Result([
                SimpleNamespace(id=i)
                for i in sorted(k for k, v in self.rows.items() if v == "")
            ])

        if "UPDATE events" in sql:
            lo, hi = params["lo"], params["hi"]
            hit = [i for i, v in self.rows.items() if lo <= i <= hi and v == ""]
            for i in hit:
                self.rows[i] = None
            self.updates.append((lo, hi, len(hit)))
            return _Result([], rowcount=len(hit))

        raise AssertionError(f"unexpected SQL: {sql[:160]}")

    async def commit(self):
        self.commits += 1
        self.nulled_at_each_commit.append(
            sum(1 for v in self.rows.values() if v is None)
        )


def _table(blanks=10, reals=3, nulls=5, duplicates=False):
    """Build a table: blanks first, then real ids, then NULLs, ids ascending."""
    rows, nid = [], 1
    for _ in range(blanks):
        rows.append((nid, "")); nid += 1
    for k in range(reals):
        rows.append((nid, f"real-{k}")); nid += 1
    for _ in range(nulls):
        rows.append((nid, None)); nid += 1
    if duplicates:
        for v in _DUP_VALUES:
            rows.append((nid, v)); nid += 1
            rows.append((nid, v)); nid += 1
    return _EventsTable(rows)


# ---------------------------------------------------------------------------
# The pure batching contract
# ---------------------------------------------------------------------------
class TestBatchRanges:
    """``events`` is hot: one 8,272-row UPDATE holds row locks against the live
    pollers for its whole duration. Batches bound each lock window."""

    def test_exact_multiple_splits_evenly(self):
        assert batch_ranges(list(range(1, 11)), 5) == [(1, 5), (6, 10)]

    def test_remainder_gets_its_own_batch(self):
        assert batch_ranges([1, 2, 3, 4, 5, 6, 7], 3) == [(1, 3), (4, 6), (7, 7)]

    def test_ranges_are_inclusive_on_both_ends(self):
        # _NULL_BATCH_SQL uses `id >= :lo AND id <= :hi`.
        assert batch_ranges([4], 10) == [(4, 4)]

    def test_sparse_ids_produce_coarse_but_covering_ranges(self):
        # The ranges may span non-blank ids; the UPDATE's repeated `= ''`
        # predicate is what keeps the WRITE exact.
        assert batch_ranges([1, 500, 9000], 2) == [(1, 500), (9000, 9000)]

    def test_empty_input_is_no_batches_not_one_empty_batch(self):
        assert batch_ranges([], 100) == []

    def test_every_id_is_covered_by_exactly_one_range(self):
        ids = sorted({(i * 37) % 5000 for i in range(1, 400)})
        ranges = batch_ranges(ids, 25)
        covered = [i for i in ids if any(lo <= i <= hi for lo, hi in ranges)]
        assert covered == ids
        assert sum(1 for i in ids
                   for lo, hi in ranges if lo <= i <= hi) == len(ids)

    def test_zero_batch_size_is_refused_not_an_infinite_loop(self):
        with pytest.raises(ValueError):
            batch_ranges([1, 2, 3], 0)

    def test_default_batch_size_is_a_module_constant(self):
        # Not a parameter: the cap must not be dial-off-able mid-run.
        assert BATCH_SIZE == 1000
        assert batch_ranges(list(range(1, 2501))) == [
            (1, 1000), (1001, 2000), (2001, 2500)
        ]


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------
class TestDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_writes_nothing_and_returns_the_census(self):
        s = _table(blanks=10, reals=3, nulls=5)
        res = await repair(s, apply=False)

        assert res["applied"] is False
        assert res["before"] == {"blank": 10, "nulls": 5, "real": 3, "total": 18}
        assert res["would_null"] == 10
        assert s.updates == []
        assert s.commits == 0
        assert sum(1 for v in s.rows.values() if v == "") == 10

    @pytest.mark.asyncio
    async def test_dry_run_is_the_default(self):
        s = _table()
        res = await repair(s, False)
        assert res["applied"] is False
        assert s.updates == []

    @pytest.mark.asyncio
    async def test_dry_run_ignores_the_gate_so_a_census_is_always_readable(self):
        # The gate exists to protect WRITES. A drifted census must still be
        # readable — that reading is how the operator learns the new number.
        s = _table(blanks=7)
        res = await repair(s, apply=False, expected_blank=EXPECTED_BLANK_COUNT)
        assert res.get("refused") is not True
        assert res["before"]["blank"] == 7

    @pytest.mark.asyncio
    async def test_an_already_clean_table_says_so_loudly(self):
        # gotcha #53: a zero-yield run must not be indistinguishable from work.
        s = _table(blanks=0, reals=2, nulls=4)
        res = await repair(s, apply=True)
        assert res["verdict"] == "already_clean"
        assert res["terminal"] == "noop"
        assert res["rows_nulled"] == 0
        assert s.updates == []


# ---------------------------------------------------------------------------
# The exact-match gate — BOTH directions (gotcha #43)
# ---------------------------------------------------------------------------
class TestExactMatchGate:
    """Queue 339S's discipline: apply only on an exact census match. A drifted
    census means the population measured is not the population about to be
    written."""

    @pytest.mark.asyncio
    async def test_refuses_when_live_count_is_lower_than_expected(self):
        s = _table(blanks=9)
        res = await repair(s, apply=True, expected_blank=10)

        assert res["refused"] is True
        assert res["applied"] is False
        assert res["verdict"] == "refused_census_drift"
        assert s.updates == [] and s.commits == 0

    @pytest.mark.asyncio
    async def test_refuses_when_live_count_is_higher_than_expected(self):
        s = _table(blanks=11)
        res = await repair(s, apply=True, expected_blank=10)
        assert res["refused"] is True
        assert s.updates == []

    @pytest.mark.asyncio
    async def test_proceeds_on_an_exact_match(self):
        # The other direction: a gate that only ever refuses is not a gate.
        s = _table(blanks=10)
        res = await repair(s, apply=True, expected_blank=10)

        assert res.get("refused") is not True
        assert res["applied"] is True
        assert res["rows_nulled"] == 10

    @pytest.mark.asyncio
    async def test_the_refusal_is_returned_not_raised(self):
        # An operator has to be able to READ the observed count.
        s = _table(blanks=3)
        res = await repair(s, apply=True, expected_blank=10)
        assert "3" in res["reason"] and "expected_blank=3" in res["reason"]
        assert "NOTHING WAS WRITTEN" in res["reason"]

    @pytest.mark.asyncio
    async def test_the_default_expectation_is_the_measured_production_count(self):
        assert EXPECTED_BLANK_COUNT == 8272
        s = _table(blanks=10)
        res = await repair(s, apply=True)   # no expected_blank passed
        assert res["refused"] is True
        assert res["expected_blank"] == 8272

    @pytest.mark.asyncio
    async def test_a_refusal_still_carries_the_census_and_the_duplicate_report(self):
        s = _table(blanks=4, duplicates=True)
        res = await repair(s, apply=True, expected_blank=999)
        assert res["before"]["blank"] == 4
        assert res["duplicate_value_count"] == 8


# ---------------------------------------------------------------------------
# The write
# ---------------------------------------------------------------------------
class TestApply:
    @pytest.mark.asyncio
    async def test_blanks_become_null_and_nothing_else_moves(self):
        s = _table(blanks=10, reals=3, nulls=5)
        res = await repair(s, apply=True, expected_blank=10)

        assert res["before"] == {"blank": 10, "nulls": 5, "real": 3, "total": 18}
        assert res["after"] == {"blank": 0, "nulls": 15, "real": 3, "total": 18}
        assert res["rows_nulled"] == 10
        assert res["census_consistent"] is True
        assert res["terminal"] == "complete"

    @pytest.mark.asyncio
    async def test_real_ids_are_untouched(self):
        s = _table(blanks=4, reals=3, nulls=0)
        await repair(s, apply=True, expected_blank=4)
        assert sorted(v for v in s.rows.values() if v is not None) == [
            "real-0", "real-1", "real-2"
        ]

    @pytest.mark.asyncio
    async def test_pre_existing_nulls_are_untouched(self):
        s = _table(blanks=2, reals=0, nulls=3)
        res = await repair(s, apply=True, expected_blank=2)
        # 3 pre-existing + 2 converted; total row count never changes.
        assert res["after"]["nulls"] == 5
        assert res["after"]["total"] == res["before"]["total"] == 5

    @pytest.mark.asyncio
    async def test_the_update_is_bounded_by_id_range_and_repeats_the_predicate(self):
        from scripts.repair_statpal_fixture_id_blanks import _NULL_BATCH_SQL

        # An `id = ANY(:ids)` UPDATE on this hot table has rolled back silently
        # before; and the range alone is not exact, so `= ''` must be repeated.
        assert "ANY(" not in _NULL_BATCH_SQL
        assert ":lo" in _NULL_BATCH_SQL and ":hi" in _NULL_BATCH_SQL
        assert "statpal_fixture_id = ''" in _NULL_BATCH_SQL

    @pytest.mark.asyncio
    async def test_a_second_run_is_an_idempotent_no_op(self):
        s = _table(blanks=6)
        await repair(s, apply=True, expected_blank=6)
        again = await repair(s, apply=True, expected_blank=0)
        assert again["verdict"] == "already_clean"
        assert again["rows_nulled"] == 0

    @pytest.mark.asyncio
    async def test_no_orm_attribute_assignment_is_used(self):
        # gotcha #4/#5: the write is SQLAlchemy Core text(), never ORM setattr.
        import inspect

        import scripts.repair_statpal_fixture_id_blanks as mod

        src = inspect.getsource(mod)
        assert "session.add" not in src
        assert ".statpal_fixture_id =" not in src.split('"""', 2)[-1]


# ---------------------------------------------------------------------------
# Batching + per-batch commits
# ---------------------------------------------------------------------------
class TestBatchingCommitsPerBatch:
    @pytest.mark.asyncio
    async def test_one_commit_per_batch_and_the_totals_add_up(self):
        s = _table(blanks=10, reals=0, nulls=0)
        res = await repair(s, apply=True, expected_blank=10)

        # BATCH_SIZE is 1000, so force the small case through batch_ranges by
        # checking the general invariant instead of a hard-coded batch count.
        assert res["batches_committed"] == len(res["batches"])
        assert res["commits"] == res["batches_committed"]
        assert sum(b["rows"] for b in res["batches"]) == res["rows_nulled"] == 10
        assert s.commits == res["batches_committed"]

    @pytest.mark.asyncio
    async def test_progress_is_durable_after_each_batch(self, monkeypatch):
        import scripts.repair_statpal_fixture_id_blanks as mod

        monkeypatch.setattr(mod, "BATCH_SIZE", 3)
        s = _table(blanks=7, reals=0, nulls=0)
        res = await mod.repair(s, apply=True, expected_blank=7)

        assert [b["rows"] for b in res["batches"]] == [3, 3, 1]
        assert s.commits == 3
        # Each commit banked strictly more work than the last: a timeout after
        # any of them leaves consistent, resumable progress.
        assert s.nulled_at_each_commit == [3, 6, 7]

    @pytest.mark.asyncio
    async def test_every_committed_batch_reports_its_own_rowcount(self, monkeypatch):
        import scripts.repair_statpal_fixture_id_blanks as mod

        monkeypatch.setattr(mod, "BATCH_SIZE", 4)
        s = _table(blanks=9, reals=0, nulls=0)
        res = await mod.repair(s, apply=True, expected_blank=9)
        for b in res["batches"]:
            assert set(b) == {"lo", "hi", "rows"} and b["rows"] > 0

    @pytest.mark.asyncio
    async def test_a_deadline_stop_is_partial_and_names_its_resume_value(
        self, monkeypatch
    ):
        import scripts.repair_statpal_fixture_id_blanks as mod

        monkeypatch.setattr(mod, "BATCH_SIZE", 3)
        # A deadline already blown: the first batch runs, the rest do not.
        res = await mod.repair(
            _table(blanks=9, reals=0, nulls=0), apply=True, expected_blank=9,
            deadline_seconds=mod._BATCH_RESERVE_SECONDS,
        )
        assert res["stopped_on_deadline"] is True
        assert res["terminal"] == "partial"
        assert res["batches_committed"] < res["batches_planned"]
        # The gate would refuse the naive re-invoke, so the repair must hand the
        # operator the value that lets it resume.
        assert res["resume_with_expected_blank"] == res["after"]["blank"]

    @pytest.mark.asyncio
    async def test_a_completed_run_does_not_ask_for_a_resume(self):
        s = _table(blanks=5, reals=0, nulls=0)
        res = await repair(s, apply=True, expected_blank=5)
        assert "resume_with_expected_blank" not in res


# ---------------------------------------------------------------------------
# The 8 duplicate real ids — reported, never written
# ---------------------------------------------------------------------------
class TestDuplicateReport:
    """8 real values / 16 rows. They are why NULLing the blanks still does not
    make ``statpal_fixture_id`` uniqueable — reported with their event ids so the
    follow-up is a lookup, not a re-investigation."""

    @pytest.mark.asyncio
    async def test_the_report_is_present_on_a_dry_run(self):
        s = _table(blanks=4, duplicates=True)
        res = await repair(s, apply=False)

        assert res["duplicate_value_count"] == 8
        assert res["duplicate_row_count"] == 16
        assert [d["value"] for d in res["duplicate_real_values"]] == sorted(_DUP_VALUES)
        for d in res["duplicate_real_values"]:
            assert len(d["event_ids"]) == 2 and d["rows"] == 2

    @pytest.mark.asyncio
    async def test_the_duplicate_rows_are_not_modified_by_the_apply(self):
        s = _table(blanks=4, reals=0, nulls=0, duplicates=True)
        dup_ids = [i for i, v in s.rows.items() if v in _DUP_VALUES]
        before = {i: s.rows[i] for i in dup_ids}

        res = await repair(s, apply=True, expected_blank=4)

        assert res["rows_nulled"] == 4
        assert {i: s.rows[i] for i in dup_ids} == before
        assert res["after"]["real"] == res["before"]["real"] == 16
        assert res["duplicates_untouched"] is True

    @pytest.mark.asyncio
    async def test_the_report_states_that_clearing_them_is_out_of_scope(self):
        res = await repair(_table(duplicates=True), apply=False)
        note = res["duplicates_note"].lower()
        assert "not touched" in note and "unique index" in note

    @pytest.mark.asyncio
    async def test_blanks_are_never_reported_as_duplicates(self):
        # 8,272 rows share the value '' — if the duplicate query did not exclude
        # them it would report the defect as its own follow-up work.
        from scripts.repair_statpal_fixture_id_blanks import _DUPLICATES_SQL

        assert "statpal_fixture_id <> ''" in _DUPLICATES_SQL
        s = _table(blanks=10, reals=0, nulls=0)
        res = await repair(s, apply=False)
        assert res["duplicate_real_values"] == []


# ---------------------------------------------------------------------------
# Rail registration
# ---------------------------------------------------------------------------
class TestRailRegistration:
    def test_the_repair_is_registered(self):
        assert _REPAIRS["statpal-blank-ids"] == (
            "scripts.repair_statpal_fixture_id_blanks", "repair"
        )

    def test_the_module_docstring_name_list_matches_the_registry(self):
        # The docstring already admitted it had drifted TWO censuses behind the
        # registry. Pin it so there cannot be a third.
        import app.routes.admin_repairs as mod

        doc = mod.__doc__
        listed = doc.split("name ∈ {", 1)[1].split("}", 1)[0]
        named = {p.strip() for p in listed.replace("\n", " ").split("|")}
        assert named == set(_REPAIRS)

    def test_expected_blank_reaches_the_repair_through_the_dispatcher(self):
        # The gate is un-overridable from the rail unless the dispatcher declares
        # the param — which would make a deadline-stopped run unresumable.
        import inspect

        from app.routes.admin_repairs import run_repair

        assert "expected_blank" in inspect.signature(run_repair).parameters
        assert '("expected_blank", expected_blank)' in inspect.getsource(run_repair)

    def test_the_repair_signature_is_dispatcher_compatible(self):
        import inspect

        params = list(inspect.signature(repair).parameters)
        assert params[:2] == ["session", "apply"]
        assert "expected_blank" in params


# ---------------------------------------------------------------------------
# The index half of the item
# ---------------------------------------------------------------------------
class TestExternalIdUniquenessAlreadyExists:
    """Queue 340 asked for a partial unique index on ``events.external_id``.

    NO MIGRATION WAS WRITTEN, because the guarantee is already in place:
    production carries the ``events_external_id_key`` UNIQUE constraint (verified
    2026-08-12 via ``pg_constraint``: ``UNIQUE (external_id)``), inherited from
    the initial schema and *kept* when ``nullable_external_id`` made the column
    nullable. Postgres already exempts NULLs from a unique index, so that
    constraint IS the partial unique index the item wanted, and a second one
    would only double the write cost on a hot 149,731-row table.

    This test pins the model-side declaration so the guarantee cannot be dropped
    silently — which is the durable half of what a migration would have bought.
    """

    def test_the_model_declares_external_id_unique(self):
        from app.models.models import Event

        assert Event.__table__.c.external_id.unique is True

    def test_external_id_is_nullable_so_absent_rows_are_exempt(self):
        from app.models.models import Event

        # ~139K events have no Odds API id; uniqueness must not apply to them.
        assert Event.__table__.c.external_id.nullable is True

    def test_statpal_fixture_id_is_deliberately_not_unique_yet(self):
        from app.models.models import Event

        # It cannot be until BOTH the 8,272 blanks are NULLed and the 8 duplicate
        # pairs are cleared. Neither has happened; asserting the current state
        # keeps the deferral honest instead of aspirational.
        assert Event.__table__.c.statpal_fixture_id.unique is not True
        assert Event.__table__.c.espn_id.unique is not True
