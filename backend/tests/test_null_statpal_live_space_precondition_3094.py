"""#3094 — `--apply`'s frozen-count precondition is enforced, not just printed.

The header of `scripts/null_statpal_live_space_ids_3094.py` has always carried
the rule: re-read the live-space count before applying, and if it has moved off
364 the mechanism fix is incomplete and the repair waits. Clearing rows while a
writer is still refilling them is a loop, not a repair.

Until the commit these tests arrived with, `--apply` printed the measured count
and then cleared whatever it found. The rule was real and the enforcement was an
operator's memory — and the operator least likely to be reading stdout is the
one running a detached dyno, whose stdout is not reliably readable from the
sandbox at all (gotcha #48). The exit code is the signal that survives.

These run in the FAST suite on purpose. The same refusals are proved over real
statements in
`tests/integration/test_null_statpal_live_space_3094_real_postgres.py`, but that
gate needs a server and so runs in one CI job and skips everywhere else — and a
guard whose only proof is a gate you have watched skip is a guard you have not
seen work. So the decisions are pinned three ways here:

* `population_verdict` is pure, so every branch — including the ones that must
  NOT refuse — is one integer call.
* `main()` is driven over a fake connection, because the verdict is not the
  guard, the WIRING is: a function can return MOVED all day while the
  entrypoint reads it into a variable and clears the rows anyway, which is
  precisely the defect being fixed.
* the fake records every statement, so "it refused" is asserted as *no write
  was reached*, not merely as an exit code.
"""

import sys

import pytest

import scripts.null_statpal_live_space_ids_3094 as mod
from scripts.null_statpal_live_space_ids_3094 import (
    EXPECTED_POPULATION,
    population_verdict,
)


class FakeCursor:
    """Answers the three reads `main()` does before it decides, and records
    every statement so a test can assert no WRITE was reached.

    Dispatch is on SQL content rather than call order: an order-keyed fake
    passes even when the statements are reordered underneath it, which is the
    one change most likely to move a guard to the wrong side of a write.
    """

    def __init__(
        self,
        *,
        population: int,
        backup_rows: int = 0,
        backup_exists: bool = False,
        uncovered: int = 0,
        population_at_clear: int | None = None,
    ):
        self.population = population
        self.backup_rows = backup_rows
        self.backup_exists = backup_exists
        self.uncovered = uncovered
        #: What `apply_clear`'s OWN plan query answers, when a test wants it to
        #: disagree with the count the precondition was computed from. That
        #: disagreement is what READ COMMITTED makes possible between the guard
        #: and the write, and a fake that cannot express it cannot test for it.
        self.population_at_clear = (
            population if population_at_clear is None else population_at_clear
        )
        self.statements: list[str] = []
        self._pending = None

    def execute(self, sql, params=None):
        self.statements.append(sql)
        # Most specific first. `COUNT_UNCOVERED_BY_BACKUP` names the backup table
        # AND counts, so it has to be matched before the plain backup count or it
        # silently answers with the wrong number.
        if "NOT EXISTS" in sql and mod.BACKUP_TABLE in sql:
            self._pending = ("one", (self.uncovered,))
        elif "to_regclass" in sql:
            self._pending = ("one", (self.backup_exists,))
        elif mod.BACKUP_TABLE in sql and "count(*)" in sql:
            self._pending = ("one", (self.backup_rows,))
        elif "END AS shape" in sql:
            self._pending = ("all", [("live_space (10-digit)", self.population)])
        elif "win_probability_sources->>'statpal_fixture_id' ~" in sql:
            self._pending = ("one", (0,))
        elif "FILTER (WHERE" in sql:
            # apply_clear's own plan query: (planned, planned_jsonb).
            self._pending = ("one", (self.population_at_clear, 0))
        elif "ORDER BY e.commence_time" in sql:
            self._pending = ("all", [])  # the dry run's sample listing
        elif "count(*)" in sql:
            self._pending = ("one", (self.population,))
        else:  # pragma: no cover — a write; the tests assert we never get here
            self._pending = ("one", (0,))

    def fetchall(self):
        return self._pending[1]

    def fetchone(self):
        return self._pending[1]

    @property
    def rowcount(self):  # pragma: no cover — only reached on a write path
        return 0

    def wrote(self) -> bool:
        """Did anything that changes state run?"""
        return any(
            verb in sql.upper()
            for sql in self.statements
            for verb in ("CREATE TABLE", "UPDATE ", "INSERT ", "DELETE ")
        )


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False
        #: What `pin_isolation` asked for, and WHEN. The level alone is not the
        #: claim: `set_session` raises inside an open transaction, so a pin that
        #: lands after the first statement is not a pin at all.
        self.isolation = None
        self.statements_before_pin = None

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def set_session(self, isolation_level=None):
        self.isolation = isolation_level
        self.statements_before_pin = len(self._cursor.statements)


def run_main(monkeypatch, argv, *, population, **cursor_kwargs):
    cur = FakeCursor(population=population, **cursor_kwargs)
    conn = FakeConn(cur)
    monkeypatch.setattr(mod, "_connect", lambda: conn)
    monkeypatch.setattr(sys, "argv", ["null_statpal_live_space_ids_3094.py", *argv])
    return mod.main(), conn, cur


class TestTheEntrypointActsOnTheVerdict:
    """The verdict is not the guard — the wiring is.

    `population_verdict` can return MOVED all day while `main()` reads it into a
    variable and clears the rows regardless, and that is the exact shape of the
    defect this work fixes: the count was measured, printed, and then not acted
    on. Every test here goes through `main()`.

    The real-Postgres file proves the same thing over real statements, but it
    runs in one CI job and skips everywhere else; a guard whose only proof is a
    gate you have watched skip is a guard you have not seen work.
    """

    def test_apply_refuses_a_moved_population_before_writing_anything(
        self, monkeypatch
    ):
        rc, conn, cur = run_main(monkeypatch, ["--apply"], population=378)
        assert rc == 1
        assert not cur.wrote(), cur.statements
        assert not conn.committed

    def test_the_dry_run_refuses_too(self, monkeypatch):
        rc, _, cur = run_main(monkeypatch, [], population=378)
        assert rc == 1
        assert not cur.wrote()

    def test_report_never_refuses(self, monkeypatch):
        rc, _, cur = run_main(monkeypatch, ["--report"], population=378)
        assert rc == 0
        assert not cur.wrote()

    def test_report_exits_zero_on_the_frozen_count_too(self, monkeypatch):
        assert run_main(monkeypatch, ["--report"], population=364)[0] == 0

    def test_a_stated_expectation_gets_past_the_guard(self, monkeypatch):
        # Reaching the dry-run plan is the proof it was not refused; the dry run
        # then writes nothing of its own accord.
        rc, _, cur = run_main(
            monkeypatch, ["--expect-population", "378"], population=378
        )
        assert rc == 0
        assert not cur.wrote()

    def test_the_applied_state_is_not_treated_as_a_mismatch(self, monkeypatch):
        assert run_main(monkeypatch, [], population=0)[0] == 0


class TestTheFrozenCountIsEnforced:
    def test_the_frozen_count_is_the_measured_364(self):
        # Not decoration: every other test here is stated relative to it, and a
        # silent edit to the constant would otherwise quietly re-point them all.
        assert EXPECTED_POPULATION == 364

    def test_the_frozen_count_proceeds(self):
        verdict, message = population_verdict(364)
        assert verdict == "FROZEN", message
        assert "364" in message

    def test_a_population_that_has_grown_refuses(self):
        # The live case the rule exists for: the writer is still refilling, so
        # clearing is a loop. 378 = 364 + the ~14 the header says one day adds
        # back under the old code.
        verdict, message = population_verdict(378)
        assert verdict == "MOVED", message
        assert "378" in message and "364" in message

    def test_a_population_that_has_shrunk_also_refuses(self):
        # The half a "has it grown?" check would miss. A fall means something
        # cleared rows this script never backed up — not a measured state, and
        # the header's rule is "moved off 364", not "grown past 364".
        verdict, _ = population_verdict(200)
        assert verdict == "MOVED"

    def test_one_row_off_in_either_direction_refuses(self):
        assert population_verdict(363)[0] == "MOVED"
        assert population_verdict(365)[0] == "MOVED"

    def test_zero_is_not_a_mismatch_it_is_the_applied_state(self):
        # The apply has run. A re-run must stay a harmless no-op: CLEAR_BOTH
        # matches nothing and CREATE TABLE IF NOT EXISTS does not refresh the
        # snapshot. Refusing here would make the script cry wolf on every
        # post-apply invocation, which is how a guard gets overridden by habit.
        verdict, message = population_verdict(0)
        assert verdict == "ALREADY-APPLIED", message

    def test_zero_stays_frozen_rather_than_applied_when_zero_is_expected(self):
        # An explicit --expect-population 0 is a claim about the population, and
        # it is satisfied. The ALREADY-APPLIED arm must not shadow the match.
        assert population_verdict(0, expected=0)[0] == "FROZEN"

    @pytest.mark.parametrize("planned", [1, 2, 91, 363, 365, 1653])
    def test_every_other_count_refuses(self, planned):
        assert population_verdict(planned)[0] == "MOVED"

    def test_an_explicit_expectation_is_honoured(self):
        # The sanctioned way past the guard, and the reason it is a flag rather
        # than a code edit: proceeding costs the operator a stated number.
        assert population_verdict(378, expected=378)[0] == "FROZEN"
        assert population_verdict(364, expected=378)[0] == "MOVED"

    def test_the_refusal_names_both_numbers_and_the_way_forward(self):
        # A refusal an operator cannot act on gets worked around. This one has
        # to carry the measured count, the expected count, and the flag.
        _, message = population_verdict(378)
        assert "378" in message
        assert "364" in message
        assert "--expect-population 378" in message

    def test_the_refusal_says_why_rather_than_only_that(self):
        _, message = population_verdict(378)
        assert "loop" in message.lower()


class TestAnEmptyBackupIsNotASnapshot:
    """`CREATE TABLE IF NOT EXISTS` not refreshing the backup is a feature — the
    first run's snapshot is the one that predates every change — and it is also
    a trap. A run that found nothing to clear leaves the table behind EMPTY, and
    a later run with real rows then clears them against a snapshot of nothing.

    Nothing else notices: both statements succeed, the census reads perfectly
    repaired, and the only symptom is that D51's undo restores zero rows, found
    out at the one moment it is too late to matter.

    The real-Postgres file proves this over real DDL; this pins the decision
    itself in the fast suite.
    """

    def test_apply_refuses_when_an_existing_backup_holds_nothing(self):
        # `backup_exists` is the load-bearing half: the guard is about a table an
        # EARLIER run left behind. A table this run creates holds exactly this
        # run's rows and there is nothing for the guard to see.
        cur = FakeCursor(population=364, backup_exists=True, backup_rows=0)

        with pytest.raises(SystemExit) as excinfo:
            mod.apply_clear(cur, dry_run=False)

        assert mod.BACKUP_TABLE in str(excinfo.value)
        # And it refused BEFORE the clear, which is the whole claim.
        assert not any("UPDATE events" in s for s in cur.statements), cur.statements

    def test_a_populated_backup_that_covers_the_run_proceeds(self):
        cur = FakeCursor(
            population=364, backup_exists=True, backup_rows=364, uncovered=0
        )
        done = mod.apply_clear(cur, dry_run=False)
        assert done["backed_up"] == 364
        assert done["uncovered"] == 0
        assert any("UPDATE events" in s for s in cur.statements)

    def test_nothing_to_clear_does_not_trip_the_guard(self):
        # The legitimate no-op re-run: zero planned, zero backed up. Refusing
        # here would make every post-apply invocation raise.
        cur = FakeCursor(population=0, backup_exists=True, backup_rows=0)
        assert mod.apply_clear(cur, dry_run=False)["cleared"] == 0

    def test_a_first_run_has_no_preserved_backup_to_answer_for(self):
        """No table yet, so `preserved_backup` is None and neither arm fires.

        This is the ONLY state in which coverage needs no check, and it needs
        none because `CREATE_BACKUP` selects the same population the clear runs
        on, under the same snapshot. Stated as a test because the guard is
        written to skip on `None`, and a `None` that meant "unknown" rather than
        "total by construction" would be a hole rather than an exemption.
        """
        cur = FakeCursor(population=364, backup_exists=False)
        assert mod.preserved_backup(cur) is None
        done = mod.apply_clear(cur, dry_run=False)
        assert done["uncovered"] == 0
        assert any("UPDATE events" in s for s in cur.statements)


class TestThePreservedBackupMustCoverEveryRowTheRunClears:
    """CERT-2171 follow-up `MLB-3094-BACKUP-COVERS-EVERY-CLEARED-EVENT`.

    The empty-table case above is one edge of "CREATE TABLE IF NOT EXISTS
    deliberately does not refresh". This is the other, and it is the one with no
    symptom at all: the preserved backup is real, populated and a perfectly good
    undo — for a DIFFERENT set of rows.

    The sequence is the one production is actually set up for. The apply clears
    364 and banks them. A writer later refills rows, or an operator states a new
    number with `--expect-population`. The table exists and is not empty, so the
    emptiness guard is satisfied; the new rows are cleared against a snapshot
    taken before they were ever in this shape; and `--rollback` then restores
    364 rows verbatim and reports a CLEAN undo while the new rows stay cleared
    with nothing holding them. D51's grant is written against a repair that can
    be undone, and after that run part of it cannot be.
    """

    def test_apply_refuses_candidates_the_preserved_backup_does_not_hold(self):
        cur = FakeCursor(
            population=10, backup_exists=True, backup_rows=364, uncovered=10
        )

        with pytest.raises(SystemExit) as excinfo:
            mod.apply_clear(cur, dry_run=False, gated_on=10)

        message = str(excinfo.value)
        # Both numbers, because the operator's next decision depends on the
        # difference between them, not on the fact that something was refused.
        assert "10" in message and "364" in message
        # And the remedy must not be the one the emptiness guard prescribes:
        # dropping this table discards a real undo for the 364 it does hold.
        assert "DO NOT DROP" in message
        assert not any("UPDATE events" in s for s in cur.statements), cur.statements

    def test_a_partially_covered_run_refuses_too(self):
        """Nine of ten covered is not covered. The guard counts rows, not runs."""
        cur = FakeCursor(
            population=10, backup_exists=True, backup_rows=364, uncovered=1
        )

        with pytest.raises(SystemExit) as excinfo:
            mod.apply_clear(cur, dry_run=False, gated_on=10)

        assert "1 of the 10" in str(excinfo.value)

    def test_the_dry_run_refuses_it_before_creating_anything(self):
        """The pre-flight answers "will the apply run?", so it refuses too.

        And it refuses EARLIER than the apply does — a dry run reaches this
        before `CREATE_BACKUP`, so nothing at all is written, which is the one
        thing a dry run promises unconditionally.
        """
        cur = FakeCursor(
            population=10, backup_exists=True, backup_rows=364, uncovered=10
        )

        with pytest.raises(SystemExit):
            mod.apply_clear(cur, dry_run=True, gated_on=10)

        assert not cur.wrote(), cur.statements

    def test_a_re_run_over_rows_the_backup_already_holds_is_allowed(self):
        """The legitimate repeat: rollback put the rows back, so re-clearing
        them is covered by the snapshot that is already banked. Refusing here
        would make the undo a one-way door — you could restore, but never
        re-apply — and the guard's question is coverage, not novelty.
        """
        cur = FakeCursor(
            population=364, backup_exists=True, backup_rows=364, uncovered=0
        )
        done = mod.apply_clear(cur, dry_run=False, gated_on=364)
        assert done["cleared"] == 0  # the fake reports no rowcount
        assert any("UPDATE events" in s for s in cur.statements)


class TestThePreconditionAndTheClearAreOnePopulation:
    """CERT-2171 follow-up `MLB-3094-POPULATION-CHECK-AND-CLEAR-ATOMICITY`.

    `main()` counts the population, grades it, and then `apply_clear` clears it.
    Under READ COMMITTED those are two statements at two moments: a writer
    refilling rows in between gets a `FROZEN 364` verdict and a wider clear —
    the exact loop the frozen count exists to refuse, waved through by the guard
    that was supposed to stop it.

    Two defenses, and they are not redundant. `SNAPSHOT_ISOLATION` is what makes
    the two counts one number; the equality check is what makes a future loss of
    that isolation LOUD instead of silent. Testing only the second would pass on
    a script with no isolation at all.
    """

    def test_a_population_that_moved_between_the_guard_and_the_write_refuses(self):
        cur = FakeCursor(population=364, population_at_clear=374)

        with pytest.raises(SystemExit) as excinfo:
            mod.apply_clear(cur, dry_run=False, gated_on=364)

        message = str(excinfo.value)
        assert "364" in message and "374" in message
        assert not any("UPDATE events" in s for s in cur.statements), cur.statements

    def test_a_population_that_shrank_refuses_as_well(self):
        # Symmetry with `population_verdict`: a FALL means something cleared
        # rows this run has not backed up, which is not a state it has measured.
        cur = FakeCursor(population=364, population_at_clear=350)
        with pytest.raises(SystemExit):
            mod.apply_clear(cur, dry_run=False, gated_on=364)

    def test_an_ungated_caller_is_not_second_guessed(self):
        # `gated_on=None` is the round-trip tests driving the statements
        # directly. There is no verdict to disagree with, so there is nothing
        # to assert; inventing one would make the helper untestable in isolation.
        cur = FakeCursor(population=2, population_at_clear=2)
        assert mod.apply_clear(cur, dry_run=False)["planned"] == 2

    def test_every_writing_mode_runs_on_one_snapshot(self, monkeypatch):
        for argv in (["--apply"], [], ["--report"]):
            _, conn, cur = run_main(monkeypatch, argv, population=364)
            assert conn.isolation == mod.SNAPSHOT_ISOLATION, argv
            # A pin is only a pin if it lands before the first statement:
            # `set_session` raises inside an open transaction, so a pin placed
            # after the census would fail on a real connection and silently do
            # nothing on a forgiving one.
            assert conn.statements_before_pin == 0, argv

    def test_the_rollback_is_deliberately_left_unpinned(self, monkeypatch):
        """The way OUT of a bad state must not be blockable by that state.

        At REPEATABLE READ a concurrent write to a row being restored aborts the
        UPDATE with a serialization failure. That is the correct answer for the
        apply — it means the writer this repair waits on is live — and the wrong
        one for the undo, which has to be able to run *while* the damage it is
        undoing is still being written to.
        """
        rc, conn, _ = run_main(
            monkeypatch, ["--rollback"], population=0, backup_exists=True
        )
        assert rc == 0
        assert conn.isolation == mod.ROLLBACK_ISOLATION
        assert mod.ROLLBACK_ISOLATION != mod.SNAPSHOT_ISOLATION
