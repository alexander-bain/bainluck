"""#7665 — Phase 0c-repair must run somewhere other than the starved pipeline.

`PHASE_0C_REPAIR_SQL` is correct, covered, and — in production — dead. Its one
in-pipeline call site, `retro_repair_tagging`, sits five `_cannot_afford` gates
below an exit `backfill_winners`' own source calls "not the rare path, the ONLY
path" (#4658), so #7648's clause was merged, released, live in the slug and
promoting nothing. That is #5111's lesson arriving a second time: a repair can
be perfectly correct and never run, and every unit test of the repair passes
throughout. So the assertions here are about DISPATCH and about the cursor,
not about whether the promotion grades correctly — the CAL-P1086 and #7648
integration gates already execute the shipped statement against a real Postgres
and this file must not restate them.

WHY THE CURSOR IS THE THING UNDER TEST. The four precedents this beat copies
(`compute_calibration_prices` #180, `regrade_polymarket_under_signflip` #145,
`null_impossible_both_sides_openings` #146, `correct_both_winner_guess_side`
#997) need no cursor, because every row they select is changed and the
population shrinks. This one's population does not: a resolved outcome with no
honest snapshot at or before its `resolution_date` is unrepairable and keeps
matching `opening_probability IS NULL` forever. Advance the cursor only over
rows the UPDATE changed and the beat re-grinds the same dead prefix on every
run and never reaches the tail — gotcha #34's starved tail, arriving through a
filter instead of a counter, and invisible to any test that only feeds it
repairable rows. `test_the_cursor_advances_over_rows_the_repair_could_not_fix`
is that test, and it is the one a "tidy-up" to `rowcount`-based advancement
fails.
"""

from unittest.mock import patch

import pytest

import app.tasks.backfill_winners as bw


# ---------------------------------------------------------------------------
# one statement, two bounds
# ---------------------------------------------------------------------------


def test_the_two_phase_0c_constants_differ_only_by_the_id_bound():
    """The beat must not carry a hand-typed second copy of the promotion.

    CAL-P1086 hoisted this statement to module level precisely so a test could
    execute THE SHIPPED ONE; a retyped variant for the beat would restore the
    hole from the other end, with the integration gates certifying the copy
    nothing runs. Both constants are `.format()`ed from one template, and this
    reconstructs the unbounded one from the bounded one to prove it — deleting
    the single line that carries the bind, and asserting byte-equality on
    everything else. It does not hardcode the bound's text, so it stays honest
    if the clause is rewritten.
    """
    lines = bw.PHASE_0C_REPAIR_SQL_BOUNDED.splitlines(keepends=True)
    bound = [i for i, line in enumerate(lines) if ":outcome_ids" in line]

    assert len(bound) == 1, (
        f"expected exactly one line to carry the id bind, found {len(bound)}"
    )
    del lines[bound[0]]

    assert "".join(lines) == bw.PHASE_0C_REPAIR_SQL, (
        "the bounded and unbounded Phase 0c statements differ by more than the "
        "id bound — they have been allowed to drift apart"
    )


def test_the_unbounded_statement_still_takes_no_parameters():
    """The pipeline phase and both integration gates call `text(sql)` bare.

    If the id bind ever leaks into the unbounded constant, those three call
    sites raise at execute time — in the gates as a red, in production as a
    phase that was already unreachable and now cannot even be un-starved.
    """
    from sqlalchemy import text

    assert ":outcome_ids" not in bw.PHASE_0C_REPAIR_SQL
    compiled = text(bw.PHASE_0C_REPAIR_SQL).compile()
    assert compiled.params == {}, f"unbounded Phase 0c grew binds: {compiled.params}"


# ---------------------------------------------------------------------------
# the position that makes this ship necessary (#7665 acceptance 2)
# ---------------------------------------------------------------------------


def test_the_in_pipeline_call_site_is_below_the_first_budget_gate():
    """Stated against the FIRST gate in the source, never against a named one.

    #7665 asks for it this way on purpose. Pinning "below `bookmaker_closing`"
    would go green the day somebody renames or reorders the gates while leaving
    the phase exactly as starved; pinning "below the first `_cannot_afford`"
    cannot. This test is the reason the beat exists, so if it ever fails the
    honest response is to re-read the pipeline, not to delete the beat: the
    beat is bounded and idempotent and costs nothing when there is nothing to
    promote.
    """
    with open(bw.__file__) as handle:
        lines = handle.read().splitlines()

    # CODE lines only. The prose around this statement necessarily describes
    # the gates and the call, and an anchor that matches its own explanation
    # reads the comment block at the top of the file as the call site — which
    # is above every gate, so the assertion inverts and passes for the wrong
    # reason. The closing paren matters too: `text(PHASE_0C_REPAIR_SQL_BOUNDED)`
    # in the beat contains `text(PHASE_0C_REPAIR_SQL` as a substring.
    code = [
        (n, line) for n, line in enumerate(lines) if not line.lstrip().startswith("#")
    ]
    first_gate = next(
        (n for n, line in code if "if _cannot_afford(" in line), None
    )
    call_site = next(
        (n for n, line in code if "text(PHASE_0C_REPAIR_SQL)" in line), None
    )

    assert first_gate is not None, "no `_cannot_afford` gate in the pipeline source"
    assert call_site is not None, "the pipeline no longer executes the hoisted constant"
    assert call_site > first_gate, (
        "Phase 0c-repair is now ABOVE the first budget gate. If that was "
        "deliberate, #7665's premise changed and this file needs re-reading — "
        "do not simply relax the assertion"
    )


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


def test_the_beat_is_scheduled_on_the_app_that_carries_every_release():
    """Scheduled, and on `background` — which is the main app, not `heavy`.

    The ship is "the phase actually runs". `heavy` converges to master on its
    own cadence (notice 48), so routing this there would trade a budget gate
    for a deployment lag and the read-back would be unpayable for the same
    reason all over again.
    """
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["repair-openings-from-first-snapshot"]

    assert entry["task"] == "app.tasks.repair_openings_from_first_snapshot"
    assert entry["options"]["queue"] == "background"


def test_the_task_dispatches_the_drain_and_not_the_pipeline():
    """#5111's assertion, transposed: prove the wire, not the repair.

    `hasattr(bw, "_repair_openings_from_first_snapshot")` would have passed
    throughout the nine-week outage #5111 records. This drives the registered
    task and observes the drain being called.
    """
    from app.tasks import repair_openings_from_first_snapshot

    with patch.object(
        bw, "_repair_openings_from_first_snapshot", autospec=True
    ) as drain:
        drain.return_value = _Awaited({"restored": 0})
        repair_openings_from_first_snapshot(scan=7)

    drain.assert_called_once()
    assert drain.call_args.kwargs["scan"] == 7, (
        "the task swallowed its own `scan` argument, so the operator dial is "
        "inert and a first production run cannot be made small"
    )


# ---------------------------------------------------------------------------
# the cursor
# ---------------------------------------------------------------------------


class _Awaited:
    """A plain value that can be awaited once, for patching an async callee."""

    def __init__(self, value):
        self._value = value

    def __await__(self):
        async def _inner():
            return self._value

        return _inner().__await__()


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def all(self):
        return self._rows


class _FakeSession:
    """Answers the drain's two statements and records what it was asked.

    It keys on the statement text rather than on call order, so a reordering of
    the drain's two executes cannot silently make the SELECT read the UPDATE's
    answer.
    """

    def __init__(self, script):
        #: list of (ids_to_return, rowcount_for_the_update)
        self._script = list(script)
        self.selected = []
        self.repaired_with = []
        self.committed = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        if ":outcome_ids" in sql:
            self.repaired_with.append(list(params["outcome_ids"]))
            return _Result(rowcount=self._last_rowcount)
        self.selected.append(dict(params))
        if not self._script:
            self._last_rowcount = 0
            return _Result(rows=[])
        ids, self._last_rowcount = self._script.pop(0)
        return _Result(rows=[(i,) for i in ids])

    async def commit(self):
        self.committed += 1


class _FakeRedis:
    def __init__(self, initial=None):
        self.value = initial
        self.deleted = False
        self.writes = []

    def get(self, key):
        return self.value

    def setex(self, key, ttl, value):
        self.value = value
        self.writes.append(value)

    def delete(self, key):
        self.value = None
        self.deleted = True


def _drive(script, initial_cursor=None, **kwargs):
    """Run the drain against the fakes and hand back (stats, session, redis)."""
    import contextlib

    session = _FakeSession(script)
    redis = _FakeRedis(initial_cursor)

    @contextlib.asynccontextmanager
    async def _session():
        yield session

    import asyncio

    with patch.object(bw, "get_task_session", _session), patch(
        "app.tasks.redis_state.get_redis_client", return_value=redis
    ):
        stats = asyncio.run(bw._repair_openings_from_first_snapshot(**kwargs))

    return stats, session, redis


def test_the_cursor_advances_over_rows_the_repair_could_not_fix():
    """THE assertion of this file. Every row examined, nothing repaired.

    This is the shape of the real tail: resolved outcomes whose only snapshots
    are dated after their own `resolution_date`, which #7648 now refuses and
    which the `CROSS JOIN LATERAL` therefore drops. They are not a failure —
    "we never saw a price for it" is the true answer — but they never leave the
    selector, so a cursor keyed on `rowcount` would sit at zero forever and the
    beat would re-scan the same dead prefix every six hours and never reach the
    far end of the table.

    `restored == 0` here is deliberate and load-bearing: a version of this test
    where the UPDATE reports work done would pass against both the correct
    implementation and the broken one.
    """
    stats, session, redis = _drive(
        [([11, 12, 13], 0), ([21, 22], 0)], scan=3
    )

    assert stats["restored"] == 0
    assert stats["examined"] == 5
    assert session.repaired_with == [[11, 12, 13], [21, 22]], (
        "the drain did not hand the UPDATE the slice it selected"
    )
    assert [c["cursor"] for c in session.selected] == [0, 13, 22], (
        "the cursor did not advance over unrepaired rows: the beat will "
        "re-grind this prefix on every run and never reach the tail"
    )
    assert redis.writes == ["13", "22"], (
        "the resume point was not persisted per batch, so a kill between "
        "batches re-does work already examined"
    )


def test_exhausting_the_table_clears_the_cursor_so_the_next_run_restarts():
    """The wrap is not tidiness — it is what makes the skip temporary.

    `backfill_polymarket_history` and `kalshi_cliff_drain` both insert
    snapshots dated BEFORE a row's `resolution_date` long after it resolved, so
    a row this beat honestly passed over can become promotable later. Without
    the wrap, advancing over it is permanent and those promotions are lost.
    """
    stats, _session, redis = _drive([([5], 1)], initial_cursor="4", scan=1)

    assert stats["wrapped"] is True
    assert stats["restored"] == 1
    assert redis.deleted is True, (
        "the cursor survived the end of the table, so every row a history "
        "backfill makes promotable is skipped forever"
    )


def test_a_deadline_already_passed_does_no_work_at_all():
    """The wall is checked before the first batch, not only between them.

    The pipeline this beat routes around dies `SoftTimeLimitExceeded` for the
    mirror-image reason (#4740: a phase admitted on remaining budget outran its
    price). A drain that always runs one batch before looking at the clock has
    no wall on its first batch, which is the expensive one.
    """
    import time

    stats, session, _redis = _drive(
        [([1, 2, 3], 3)], deadline=time.monotonic() - 1.0
    )

    assert stats["deadline_hit"] is True
    assert stats["examined"] == 0
    assert session.selected == [], "a passed deadline still selected a slice"


def test_an_unreadable_cursor_is_reported_rather_than_silently_restarting():
    """A corrupt cursor means a full re-scan; it must not be a quiet one.

    Falling back to the head is right — the alternative is a beat that never
    runs again — but a run that silently re-grinds three million rows looks
    exactly like a healthy one, which is gotcha #53 in the shape this repo
    keeps meeting it.
    """
    stats, _session, _redis = _drive([], initial_cursor="not-an-id")

    assert stats["cursor_from"] == 0
    assert any("unreadable cursor" in e for e in stats["errors"]), (
        f"a corrupt cursor was swallowed: {stats['errors']}"
    )


def test_the_beats_own_wall_leaves_room_under_the_tasks_soft_limit():
    """A wall at or above the soft limit is not a wall.

    The drain checks the clock between batches, so the task must survive the
    longest batch that can start just under the wall. Read from the registered
    task rather than retyped, so moving one and not the other fails here.
    """
    from app.tasks import celery_app

    task = celery_app.tasks["app.tasks.repair_openings_from_first_snapshot"]

    assert bw._PHASE_0C_MAX_RUNTIME < task.soft_time_limit, (
        "the drain's wall is not below the soft limit, so the batch running "
        "when the wall fires is killed rather than finished"
    )
    assert task.soft_time_limit - bw._PHASE_0C_MAX_RUNTIME >= 120, (
        "less than two minutes of margin for the final batch to commit"
    )


@pytest.mark.parametrize("name", ["examined", "restored", "batches", "wrapped"])
def test_the_stats_carry_the_numbers_that_mean_the_ship_is_happening(name):
    """`app.utils.task_verdict`'s rule, and gotcha #53's: "it returned" is not
    "it worked". A run reporting healthy with `examined` and `restored` both
    zero forever has recovered nothing, and the only way anybody notices is if
    the numbers are in the summary."""
    stats, _session, _redis = _drive([([1], 1)], scan=1)
    assert name in stats
