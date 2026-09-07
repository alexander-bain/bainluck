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

    def __init__(self, *, population: int, backup_rows: int = 0):
        self.population = population
        self.backup_rows = backup_rows
        self.statements: list[str] = []
        self._pending = None

    def execute(self, sql, params=None):
        self.statements.append(sql)
        if mod.BACKUP_TABLE in sql and "count(*)" in sql:
            self._pending = ("one", (self.backup_rows,))
        elif "END AS shape" in sql:
            self._pending = ("all", [("live_space (10-digit)", self.population)])
        elif "win_probability_sources->>'statpal_fixture_id' ~" in sql:
            self._pending = ("one", (0,))
        elif "FILTER (WHERE" in sql:
            # apply_clear's own plan query: (planned, planned_jsonb).
            self._pending = ("one", (self.population, 0))
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

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def run_main(monkeypatch, argv, *, population):
    cur = FakeCursor(population=population)
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
        cur = FakeCursor(population=364, backup_rows=0)

        with pytest.raises(SystemExit) as excinfo:
            mod.apply_clear(cur, dry_run=False)

        assert mod.BACKUP_TABLE in str(excinfo.value)
        # And it refused BEFORE the clear, which is the whole claim.
        assert not any("UPDATE events" in s for s in cur.statements), cur.statements

    def test_a_populated_backup_proceeds(self):
        cur = FakeCursor(population=364, backup_rows=364)
        done = mod.apply_clear(cur, dry_run=False)
        assert done["backed_up"] == 364
        assert any("UPDATE events" in s for s in cur.statements)

    def test_nothing_to_clear_does_not_trip_the_guard(self):
        # The legitimate no-op re-run: zero planned, zero backed up. Refusing
        # here would make every post-apply invocation raise.
        cur = FakeCursor(population=0, backup_rows=0)
        assert mod.apply_clear(cur, dry_run=False)["cleared"] == 0
