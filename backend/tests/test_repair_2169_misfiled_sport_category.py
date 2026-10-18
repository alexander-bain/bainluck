"""#2169 — the guards the category backfill has to hold, with no server.

1. **The population is the issue's table, verbatim** — 23 writes, one no-op, no
   row added by a re-census and none dropped.
2. **The plan's evidence is the deployed classifier**: F3's
   ``categorize_by_rules()`` answers each row's ``after`` for its full live name,
   and still answers ``golf`` for the no-op (which is why it is one).
3. **Per-row compare-and-set**: a row already repaired, moved by another writer,
   renamed out of the classifier's answer, or missing is skipped, never written.
4. **The apply writes exactly the reviewed plan**: a plan-hash mismatch, or a
   statement that changes other than one row, stops the run before commit.
5. **The undo only undoes what the apply wrote**: it needs the id list and never
   touches a row the pipeline repaired on its own.
6. **The write re-states the name the classifier judged**: a rename between the
   read and the UPDATE changes zero rows and the run refuses before commit.
7. **The attended run is bounded**: ``main()`` arms short lock and statement
   budgets on the session, and a budget firing refuses with a rollback, never a
   commit.
8. **A COMMIT that does not return is UNKNOWN** (exit 3, mode + plan hash + the
   exact writes), never "rolled back, nothing committed": no second COMMIT, retry
   or restore follows it — including the one ``get_task_session``'s normal exit
   would send, so these arms drive the PRODUCTION wrapper with an inert engine and
   session — a cancel on it keeps its type, a failing cleanup changes neither, and
   a refusal or cancel BEFORE the COMMIT keeps its definite answer.
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys

import pytest

from app.utils.futures_categorization import categorize_by_rules

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scripts"
    / "repair_2169_misfiled_sport_category.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("repair_2169", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def repair():
    return _load()


# The #2169 table, copied by hand from the issue body (2026-08-24) so a constant
# edited in the script cannot also edit its own reference.
ISSUE_TABLE = {
    59304735: ("baseball", "darts"),
    59304736: ("baseball", "darts"),
    59304737: ("baseball", "darts"),
    59304738: ("baseball", "darts"),
    59304739: ("baseball", "darts"),
    59304740: ("baseball", "darts"),
    59304741: ("baseball", "darts"),
    59304742: ("baseball", "darts"),
    59374602: ("baseball", "darts"),
    59374603: ("baseball", "darts"),
    59374604: ("baseball", "darts"),
    59374605: ("baseball", "darts"),
    59428372: ("baseball", "darts"),
    58416367: ("golf", "darts"),
    35418786: ("golf", "esports"),
    31169677: ("golf", "entertainment"),
    58015857: ("golf", "tech"),
    58728438: ("basketball", "entertainment"),
    59170844: ("basketball", "entertainment"),
    59170845: ("basketball", "entertainment"),
    59170847: ("basketball", "entertainment"),
    59520510: ("basketball", "politics"),
    59165075: ("basketball", "politics"),
}

# Full live names and stored values, production read 2026-10-13 07:35Z
# (`artifacts-calibration-2169/live-read-1.json`). 58015857 and 59520510 had
# already been repaired by the pipeline; everything else held its `before`.
LIVE_2026_10_13 = {
    31169677: ("golf", '"Masters of the Universe" Opening Weekend Box Office'),
    35418786: ("golf", "Most kills on a single map at Masters London 2026?"),
    38277227: ("golf", "Asia Masters 2026 Winner"),
    58015857: (
        "tech",
        "Will Anthropic sign the Open Weights and American AI Leadership letter?",
    ),
    58416367: ("golf", "New Zealand Darts Masters: Winner"),
    58728438: ("basketball", "Practical Magic 2 · Rotten Tomatoes score"),
    59165075: ("basketball", "Los Angeles L next governor before Jan 1, 2027?"),
    59170844: ("basketball", '"The Magic Faraway Tree" Rotten Tomatoes Score?'),
    59170845: (
        "basketball",
        'Will "The Magic Faraway Tree" score at least 80 on the Rotten Tomatoes Tomatometer?',
    ),
    59170847: (
        "basketball",
        'Will "The Magic Faraway Tree" score at least 90 on the Rotten Tomatoes Tomatometer?',
    ),
    59304735: ("baseball", "World Series of Darts: Jonny Clayton vs Ben Robb"),
    59304736: ("baseball", "World Series of Darts: Damon Heta vs Joe Comito"),
    59304737: ("baseball", "World Series of Darts: Gian van Veen vs Raymond Smith"),
    59304738: ("baseball", "World Series of Darts: Ross Smith vs Brody Klinge"),
    59304739: ("baseball", "World Series of Darts: Stephen Bunting vs Mal Cuming"),
    59304740: ("baseball", "World Series of Darts: James Wade vs Tim Pusey"),
    59304741: ("baseball", "World Series of Darts: Josh Rock vs Adam Leek"),
    59304742: ("baseball", "World Series of Darts: Gerwyn Price vs Simon Whitlock"),
    59374602: ("baseball", "World Series of Darts: Jonny Clayton vs Damon Heta"),
    59374603: ("baseball", "World Series of Darts: Gerwyn Price vs Josh Rock"),
    59374604: ("baseball", "World Series of Darts: Gian van Veen vs Brody Klinge"),
    59374605: ("baseball", "World Series of Darts: James Wade vs Stephen Bunting"),
    59428372: ("baseball", "World Series of Darts: Gerwyn Price vs James Wade"),
    59520510: ("politics", "Thunder Bay, ON Mayoral Election Winner"),
}

ALREADY_REPAIRED = {58015857, 59520510}


# ── 1. population ────────────────────────────────────────────────────────────


def test_pinned_is_the_issue_table_verbatim(repair):
    assert repair.PINNED == ISSUE_TABLE
    assert len(repair.PINNED) == 23


def test_the_no_op_is_read_never_written(repair):
    assert repair.NO_OP == {38277227: "golf"}
    assert not set(repair.NO_OP) & set(repair.PINNED)


def test_every_pinned_write_moves_the_value(repair):
    assert all(before != after for before, after in repair.PINNED.values())


# ── 2. the deployed classifier is the evidence ───────────────────────────────


@pytest.mark.parametrize("market_id", sorted(ISSUE_TABLE))
def test_fixed_classifier_answers_after_for_the_live_name(market_id):
    _, name = LIVE_2026_10_13[market_id]
    assert categorize_by_rules(name) == ISSUE_TABLE[market_id][1]


def test_no_op_stays_unreachable_by_rules():
    assert categorize_by_rules(LIVE_2026_10_13[38277227][1]) == "golf"


def test_plan_runs_the_real_classifier_on_the_live_read(repair):
    out = repair.plan(LIVE_2026_10_13, categorize_by_rules)
    written = {i for i, _, _ in out["write"]}
    assert written == set(ISSUE_TABLE) - ALREADY_REPAIRED
    assert len(out["write"]) == 21
    assert {i for i, _ in out["skip"]} == ALREADY_REPAIRED
    assert all("already" in reason for _, reason in out["skip"])
    assert out["no_op"] == {38277227: "golf"}
    assert all((f, t) == ISSUE_TABLE[i] for i, f, t in out["write"])


# ── 3. per-row compare-and-set ───────────────────────────────────────────────


def test_a_row_another_writer_moved_is_skipped(repair):
    rows = dict(LIVE_2026_10_13)
    rows[59304735] = ("soccer", rows[59304735][1])
    out = repair.plan(rows, categorize_by_rules)
    assert 59304735 not in {i for i, _, _ in out["write"]}
    reason = dict(out["skip"])[59304735]
    assert "another writer" in reason


def test_a_null_category_is_drift_not_a_write(repair):
    rows = dict(LIVE_2026_10_13)
    rows[59165075] = (None, rows[59165075][1])
    out = repair.plan(rows, categorize_by_rules)
    assert 59165075 not in {i for i, _, _ in out["write"]}


def test_a_row_whose_name_moved_off_the_classifier_answer_is_skipped(repair):
    rows = dict(LIVE_2026_10_13)
    rows[59304736] = ("baseball", "World Series: Yankees vs Dodgers Game 7")
    out = repair.plan(rows, categorize_by_rules)
    assert 59304736 not in {i for i, _, _ in out["write"]}
    assert "classifier" in dict(out["skip"])[59304736]


def test_classifier_gate_uses_the_injected_function(repair):
    out = repair.plan(LIVE_2026_10_13, lambda name: "baseball")
    assert out["write"] == []


def test_a_missing_row_is_skipped(repair):
    rows = dict(LIVE_2026_10_13)
    del rows[58416367]
    out = repair.plan(rows, categorize_by_rules)
    assert dict(out["skip"])[58416367] == "row missing"


# ── 4. the apply writes exactly the reviewed plan ────────────────────────────


class _Result:
    def __init__(self, rows=(), rowcount=1):
        self._rows = list(rows)
        self.rowcount = rowcount

    def __iter__(self):
        return iter(self._rows)


class _Row:
    def __init__(self, id, cat, name):
        self.id, self.llm_sport_category, self.name = id, cat, name


class FakeSession:
    def __init__(self, live, rowcount=1):
        self.live = {i: list(v) for i, v in live.items()}
        self.rowcount = rowcount
        self.updates: list[dict] = []
        self.committed = False
        # What the session saw, in order, and which writes a COMMIT carried — so a
        # test driving the REAL ``get_task_session`` can see its exit path too.
        self.calls: list[str] = []
        self.commits = 0
        self.pending: list[tuple] = []
        self.durable_writes: list[tuple] = []

    async def execute(self, stmt, params):
        sql = str(stmt)
        self.calls.append("execute")
        if sql.lstrip().upper().startswith("SELECT"):
            ids = set(params["ids"])
            got = _Result(_Row(i, c, n) for i, (c, n) in self.live.items() if i in ids)
            self.after_read()
            return got
        assert sql.lstrip().upper().startswith("UPDATE")
        self.updates.append(dict(params, sql=sql))
        row = self.live[params["id"]]
        # The fake honours only the predicates the SQL TEXT states, so a clause
        # dropped from `_CAS_SQL` is a clause this fake stops enforcing.
        matches = row[0] == params["source"]
        if "name IS NOT DISTINCT FROM :name" in " ".join(sql.split()):
            matches = matches and row[1] == params["name"]
        if self.rowcount == 1 and matches:
            row[0] = params["target"]
            self.pending.append((params["id"], params["source"], params["target"]))
            return _Result(rowcount=1)
        return _Result(rowcount=0 if self.rowcount == 1 else self.rowcount)

    def after_read(self):
        """A concurrent writer's hook: runs between the read and the first UPDATE."""

    async def commit(self):
        self.calls.append("commit")
        self.commits += 1
        self.committed = True
        self.durable_writes += self.pending
        self.pending = []

    async def rollback(self):
        self.calls.append("rollback")
        self.rolled_back = True
        self.pending = []

    async def close(self):
        self.calls.append("close")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _run(repair, session, **kw):
    return asyncio.run(repair.run(session, categorize_by_rules, **kw))


def test_dry_run_writes_nothing(repair):
    s = FakeSession(LIVE_2026_10_13)
    out = _run(repair, s, apply=False)
    assert s.updates == [] and not s.committed
    assert out["mode"] == "dry-run" and out["written"] == 0
    assert len(out["write"]) == 21


def test_apply_with_the_wrong_plan_hash_writes_nothing(repair):
    s = FakeSession(LIVE_2026_10_13)
    with pytest.raises(repair.Refused):
        _run(repair, s, apply=True, expect_plan_hash="0" * 16)
    assert s.updates == [] and not s.committed


def test_apply_with_the_dry_run_hash_writes_the_plan_and_only_the_plan(repair):
    h = _run(repair, FakeSession(LIVE_2026_10_13), apply=False)["plan_hash"]
    s = FakeSession(LIVE_2026_10_13)
    out = _run(repair, s, apply=True, expect_plan_hash=h)
    assert out["written"] == 21 and s.committed
    assert {u["id"] for u in s.updates} == set(ISSUE_TABLE) - ALREADY_REPAIRED
    for i, (before, after) in ISSUE_TABLE.items():
        assert s.live[i][0] == after
    assert s.live[38277227][0] == "golf"


def test_a_cas_that_changes_zero_rows_stops_before_commit(repair):
    h = _run(repair, FakeSession(LIVE_2026_10_13), apply=False)["plan_hash"]
    s = FakeSession(LIVE_2026_10_13, rowcount=0)
    with pytest.raises(repair.Refused):
        _run(repair, s, apply=True, expect_plan_hash=h)
    assert not s.committed


def test_plan_hash_is_order_free_and_content_bound(repair):
    a = [(1, "golf", "darts"), (2, "baseball", "darts")]
    assert repair.plan_hash(a) == repair.plan_hash(list(reversed(a)))
    assert repair.plan_hash(a) != repair.plan_hash([(1, "golf", "esports"), a[1]])


def test_the_write_moves_the_category_alone(repair):
    sql = " ".join(repair._CAS_SQL.split())
    assert "SET llm_sport_category = :target WHERE" in sql
    assert sql.endswith(
        "WHERE id = :id AND llm_sport_category = :source "
        "AND name IS NOT DISTINCT FROM :name"
    )
    set_clause = sql.split(" WHERE ")[0]
    assert set_clause == "UPDATE futures_markets SET llm_sport_category = :target"
    for column in ("canonical_market_key", "updated_at", "category_tags", "llm_league"):
        assert column not in sql


# ── 6. the name the classifier judged is the name the write lands on ─────────


class RenamedAfterRead(FakeSession):
    """The open Kalshi row is renamed between `_read()` and its UPDATE; its
    category stays `basketball`, so only the name half of the CAS can see it."""

    RENAMED = "Los Angeles Lakers win the 2027 NBA Finals?"

    def after_read(self):
        self.live[59165075][1] = self.RENAMED


def test_a_rename_between_read_and_write_refuses_before_commit(repair):
    assert categorize_by_rules(RenamedAfterRead.RENAMED) != "politics"
    h = _run(repair, FakeSession(LIVE_2026_10_13), apply=False)["plan_hash"]
    s = RenamedAfterRead(LIVE_2026_10_13)
    with pytest.raises(repair.Refused, match="59165075"):
        _run(repair, s, apply=True, expect_plan_hash=h)
    assert not s.committed
    assert s.live[59165075] == ["basketball", RenamedAfterRead.RENAMED]
    # The UPDATE carried the name the plan read, not the one it found.
    sent = [u for u in s.updates if u["id"] == 59165075]
    assert sent and sent[0]["name"] == LIVE_2026_10_13[59165075][1]


def test_every_update_binds_the_observed_name(repair):
    h = _run(repair, FakeSession(LIVE_2026_10_13), apply=False)["plan_hash"]
    s = FakeSession(LIVE_2026_10_13)
    _run(repair, s, apply=True, expect_plan_hash=h)
    assert {u["id"]: u["name"] for u in s.updates} == {
        i: LIVE_2026_10_13[i][1] for i in set(ISSUE_TABLE) - ALREADY_REPAIRED
    }


def test_a_null_name_is_compared_null_safely(repair):
    # Plain `=` against NULL is never true, so a NULL-named row read as NULL could
    # never be written (nor undone); the CAS must say IS NOT DISTINCT FROM.
    sql = " ".join(repair._CAS_SQL.split())
    assert "name IS NOT DISTINCT FROM :name" in sql
    assert "name = :name" not in sql
    rows = dict(LIVE_2026_10_13)
    rows[59304735] = ("darts", None)
    s = FakeSession(rows)
    out = _run(repair, s, apply=False, restore_ids=frozenset({59304735}))
    assert out["written"] == 1 and s.updates[0]["name"] is None
    assert s.live[59304735][0] == "baseball"


# ── 5. the undo ──────────────────────────────────────────────────────────────


def test_restore_reverts_only_the_named_ids(repair):
    h = _run(repair, FakeSession(LIVE_2026_10_13), apply=False)["plan_hash"]
    s = FakeSession(LIVE_2026_10_13)
    applied = _run(repair, s, apply=True, expect_plan_hash=h)
    ids = frozenset(i for i, _, _ in applied["write"])
    s.updates.clear()
    out = _run(repair, s, apply=False, restore_ids=ids)
    assert out["mode"] == "restore" and out["written"] == 21
    for i in ids:
        assert s.live[i][0] == ISSUE_TABLE[i][0]
    # The pipeline's own repairs survive the undo.
    assert s.live[58015857][0] == "tech"
    assert s.live[59520510][0] == "politics"


def test_restore_skips_a_row_moved_after_the_apply(repair):
    rows = dict(LIVE_2026_10_13)
    rows[59304735] = ("tennis", rows[59304735][1])
    out = repair.plan(rows, categorize_by_rules, restore_ids=frozenset({59304735}))
    assert out["write"] == []


def test_restore_refuses_unpinned_or_empty_ids(repair):
    with pytest.raises(repair.Refused):
        repair.parse_ids("38277227")
    with pytest.raises(repair.Refused):
        repair.parse_ids(" , ")
    assert repair.parse_ids("59304735,59165075") == frozenset({59304735, 59165075})


# ── refusals at the door ─────────────────────────────────────────────────────


@pytest.mark.parametrize("app", ["", "bainluck-staging", "local"])
def test_refuses_off_production(repair, app):
    with pytest.raises(repair.Refused):
        repair.refuse_unless_production({"HEROKU_APP_NAME": app})


@pytest.mark.parametrize("app", ["bainluck", "bainluck-heavy"])
def test_permits_production(repair, app):
    repair.refuse_unless_production({"HEROKU_APP_NAME": app})


@pytest.mark.parametrize(
    "argv",
    [
        ["--apply"],
        ["--restore"],
        ["--ids", "59304735"],
        ["--restore", "--ids", "38277227"],
    ],
)
def test_main_refuses_unsafe_flag_shapes_before_any_session(
    repair, monkeypatch, argv, capsys
):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    monkeypatch.setattr(sys, "argv", ["repair_2169", *argv])
    assert asyncio.run(repair.main()) == 2
    assert capsys.readouterr().out.startswith("REFUSED:")


# ── 7. the attended run is bounded ───────────────────────────────────────────


def _fake_task_session(session, seen):
    import contextlib

    @contextlib.asynccontextmanager
    async def fake(**kwargs):
        seen.append(kwargs)
        yield session

    return fake


def test_main_arms_short_lock_and_statement_budgets(repair, monkeypatch, capsys):
    import app.tasks.base as base

    seen: list[dict] = []
    monkeypatch.setattr(
        base, "get_task_session", _fake_task_session(FakeSession(LIVE_2026_10_13), seen)
    )
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    monkeypatch.setattr(sys, "argv", ["repair_2169"])
    assert asyncio.run(repair.main()) == 0
    assert seen == [
        {
            "statement_timeout_ms": repair.STATEMENT_TIMEOUT_MS,
            "lock_timeout_ms": repair.LOCK_TIMEOUT_MS,
        }
    ]
    # Short: seconds, not the 30-minute resting bound, and a lock bound exists.
    assert 0 < repair.LOCK_TIMEOUT_MS <= 10_000
    assert 0 < repair.STATEMENT_TIMEOUT_MS <= 30_000
    assert '"mode": "dry-run"' in capsys.readouterr().out


class _LockNotAvailable(Exception):
    sqlstate = "55P03"


class LockedOnThirdWrite(FakeSession):
    """A contended row: the third UPDATE waits out `lock_timeout` and the server
    cancels it, after two earlier writes have already executed in the txn."""

    def __init__(self, live):
        super().__init__(live)
        self.rolled_back = False

    async def execute(self, stmt, params):
        if str(stmt).lstrip().upper().startswith("UPDATE") and len(self.updates) == 2:
            from sqlalchemy.exc import OperationalError

            self.updates.append(dict(params, sql=str(stmt)))
            raise OperationalError(str(stmt), params, _LockNotAvailable("lock timeout"))
        return await super().execute(stmt, params)


def test_a_lock_timeout_refuses_and_rolls_back_without_commit(
    repair, monkeypatch, capsys
):
    import app.tasks.base as base

    h = _run(repair, FakeSession(LIVE_2026_10_13), apply=False)["plan_hash"]
    s = LockedOnThirdWrite(LIVE_2026_10_13)
    monkeypatch.setattr(base, "get_task_session", _fake_task_session(s, []))
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    monkeypatch.setattr(
        sys, "argv", ["repair_2169", "--apply", "--expect-plan-hash", h]
    )
    assert asyncio.run(repair.main()) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED:") and "55P03" in out and "nothing committed" in out
    assert "UNDO" not in out
    assert len(s.updates) == 3
    assert s.rolled_back and not s.committed


# ── 8. a COMMIT that does not return is UNKNOWN, never "nothing committed" ───
#
# Root's counterexample (2026-10-18, script blob 3da6215c): the server makes the
# COMMIT durable and the acknowledgement is lost (SQLSTATE 08006). The client's
# rollback afterwards cannot undo or disprove a durable commit, so a CLI that
# prints "rolled back, nothing committed" after it is a false zero-write claim.
# These fakes mark their state durable FIRST and then lose the acknowledgement.
#
# Every ``main()`` arm here runs through the PRODUCTION ``get_task_session``; only
# the engine and session factory it builds are inert recorders. That wrapper
# COMMITs again on a NORMAL exit, and a ``return 3`` inside its ``async with`` is
# a normal exit (Root's hold on ca5ba491 / CERT-4215). A yielding fake context has
# no such exit, so it cannot see that second COMMIT.


class _ConnectionFailure(Exception):
    sqlstate = "08006"


def _lost_ack():
    from sqlalchemy.exc import OperationalError

    return OperationalError("COMMIT", {}, _ConnectionFailure("connection lost"))


class LostCommitAck(FakeSession):
    """COMMIT becomes durable on the server; its acknowledgement never arrives.

    ``then`` is what a SECOND commit would do if anything sent one: ``"lost"``
    (the dead connection refuses again) or ``"ack"`` (it answers). Either way the
    repair must never send it. ``rollback_raises`` / ``close_raises`` make the
    wrapper's cleanup fail on the dead connection.
    """

    def __init__(
        self, live, raises=None, then="lost", rollback_raises=None, close_raises=None
    ):
        super().__init__(live)
        self.durable = False
        self.rolled_back = False
        self._raises = raises
        self._then = then
        self._rollback_raises = rollback_raises
        self._close_raises = close_raises

    async def commit(self):
        self.calls.append("commit")
        self.commits += 1
        if self.commits > 1 and self._then == "ack":
            self.committed = True
            return
        self.durable = True  # the server applied it ...
        self.durable_writes += self.pending
        self.pending = []
        # ... and the connection died before the client heard back.
        raise self._raises if self._raises is not None else _lost_ack()

    async def rollback(self):
        # A client rollback cannot reach a COMMIT the server already made durable.
        self.calls.append("rollback")
        self.rolled_back = True
        if self._rollback_raises is not None:
            raise self._rollback_raises

    async def close(self):
        self.calls.append("close")
        if self._close_raises is not None:
            raise self._close_raises


class _InertEngine:
    def __init__(self, calls, raises=None):
        self._calls, self._raises = calls, raises

    async def dispose(self):
        self._calls.append("dispose")
        if self._raises is not None:
            raise self._raises


def _wire_real_task_session(monkeypatch, session, dispose_raises=None) -> dict:
    """Keep ``app.tasks.base.get_task_session`` itself; make only what it builds inert.

    Returns the kwargs the wrapper handed its engine factory.
    """
    import app.tasks.base as base

    engine = _InertEngine(session.calls, dispose_raises)
    seen: dict = {}

    def engine_factory(**kwargs):
        seen.update(kwargs)
        return engine

    def session_maker(bound, **kwargs):
        assert bound is engine
        return lambda: session

    monkeypatch.setattr(base, "_get_task_engine", engine_factory)
    monkeypatch.setattr(base, "async_sessionmaker", session_maker)
    return seen


def _main(repair, monkeypatch, session, argv, dispose_raises=None):
    import app.tasks.base as base

    # The production wrapper, not a test double left behind by another arm.
    assert base.get_task_session.__module__ == "app.tasks.base"
    assert base.get_task_session.__wrapped__.__qualname__ == "get_task_session"
    seen = _wire_real_task_session(monkeypatch, session, dispose_raises)
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    monkeypatch.setattr(sys, "argv", ["repair_2169", *argv])
    code = asyncio.run(repair.main())
    assert seen == {
        "statement_timeout_ms": repair.STATEMENT_TIMEOUT_MS,
        "lock_timeout_ms": repair.LOCK_TIMEOUT_MS,
    }
    return code


def _hash(repair):
    return _run(repair, FakeSession(LIVE_2026_10_13), apply=False)["plan_hash"]


def _json_tail(out: str) -> dict:
    import json

    return json.loads(out[out.index("{") :])


def _after_first_commit(s) -> list[str]:
    return s.calls[s.calls.index("commit") + 1 :]


#: The wrapper's EXCEPTION exit: cleanup only. Its NORMAL exit is ["commit", ...].
_CLEANUP = ["rollback", "close", "dispose"]

_PLAN_WRITES = sorted((i, *ISSUE_TABLE[i]) for i in set(ISSUE_TABLE) - ALREADY_REPAIRED)


def test_the_rig_is_the_production_wrapper_and_its_normal_exit_commits(
    repair, monkeypatch, capsys
):
    # The rig's own control: if the inert wiring dropped the after-yield COMMIT,
    # every "no second COMMIT" arm below would pass for the wrong reason.
    s = FakeSession(LIVE_2026_10_13)
    assert _main(repair, monkeypatch, s, []) == 0
    assert s.calls == ["execute", "commit", "close", "dispose"]
    assert s.durable_writes == [] and s.updates == []
    assert '"mode": "dry-run"' in capsys.readouterr().out


@pytest.mark.parametrize("then", ["lost", "ack"])
def test_a_lost_commit_ack_on_apply_is_unknown_not_nothing_committed(
    repair, monkeypatch, capsys, then
):
    h = _hash(repair)
    s = LostCommitAck(LIVE_2026_10_13, then=then)
    code = _main(repair, monkeypatch, s, ["--apply", "--expect-plan-hash", h])
    captured = capsys.readouterr()
    out = captured.out
    assert s.durable  # the specimen: the writes ARE durable
    assert code == 3  # neither success (0) nor a definite refusal (2)
    assert "nothing committed" not in out and "rolled back" not in out
    assert "REFUSED" not in out and "UNDO" not in out
    assert "Traceback" not in captured.err
    report = _json_tail(out)
    assert report["outcome"] == "UNKNOWN"
    assert report["mode"] == "apply"
    assert report["plan_hash"] == h
    assert report["statements_changed"] == 21
    assert sorted(tuple(w) for w in report["write"]) == _PLAN_WRITES
    assert "08006" in report["unknown"]
    assert report["readback"].endswith(
        "python3 scripts/repair_2169_misfiled_sport_category.py"
    )
    assert "-a bainluck-heavy" in report["readback"]
    assert "written" not in report


@pytest.mark.parametrize("then", ["lost", "ack"])
def test_a_lost_commit_ack_is_never_followed_by_a_second_write_commit_or_restore(
    repair, monkeypatch, capsys, then
):
    h = _hash(repair)
    s = LostCommitAck(LIVE_2026_10_13, then=then)
    _main(repair, monkeypatch, s, ["--apply", "--expect-plan-hash", h])
    capsys.readouterr()
    assert s.commits == 1
    # After the COMMIT: only the wrapper's exception-path cleanup. No second
    # COMMIT from the wrapper's normal exit, no retry, no restore write, and the
    # repair itself issues no rollback dressed up as evidence about the COMMIT.
    assert _after_first_commit(s) == _CLEANUP
    assert len(s.updates) == 21
    assert sorted(s.durable_writes) == _PLAN_WRITES  # carried once, by the one COMMIT
    assert all(s.live[i][0] == ISSUE_TABLE[i][1] for i in ISSUE_TABLE)


def test_a_lost_commit_ack_on_restore_is_unknown_too(repair, monkeypatch, capsys):
    rows = {
        i: ((ISSUE_TABLE[i][1], n) if i in ISSUE_TABLE else (c, n))
        for i, (c, n) in LIVE_2026_10_13.items()
    }
    ids = "59304735,59165075"
    s = LostCommitAck(rows)
    code = _main(repair, monkeypatch, s, ["--restore", "--ids", ids])
    out = capsys.readouterr().out
    assert code == 3
    assert "nothing committed" not in out and "REFUSED" not in out
    report = _json_tail(out)
    assert report["outcome"] == "UNKNOWN" and report["mode"] == "restore"
    assert sorted(report["write"]) == [
        [59165075, "politics", "basketball"],
        [59304735, "darts", "baseball"],
    ]
    assert s.commits == 1 and _after_first_commit(s) == _CLEANUP


def test_run_raises_unknown_at_the_commit_boundary_with_the_plan_identity(repair):
    h = _hash(repair)
    s = LostCommitAck(LIVE_2026_10_13)
    with pytest.raises(repair.Unknown) as caught:
        _run(repair, s, apply=True, expect_plan_hash=h)
    assert not isinstance(caught.value, repair.Refused)
    report = caught.value.report
    assert report["outcome"] == "UNKNOWN" and report["mode"] == "apply"
    assert report["plan_hash"] == h and report["statements_changed"] == 21
    assert s.calls[-1] == "commit" and not s.rolled_back


def _broken(what: str):
    from sqlalchemy.exc import OperationalError

    return OperationalError(
        what, {}, _ConnectionFailure(f"{what} on a dead connection")
    )


@pytest.mark.parametrize("fails", ["rollback", "close", "dispose", "all"])
def test_a_cleanup_failure_after_unknown_keeps_the_report_and_exit_3(
    repair, monkeypatch, capsys, fails
):
    h = _hash(repair)
    s = LostCommitAck(
        LIVE_2026_10_13,
        rollback_raises=_broken("ROLLBACK") if fails in ("rollback", "all") else None,
        close_raises=_broken("close") if fails in ("close", "all") else None,
    )
    dispose = _broken("dispose") if fails in ("dispose", "all") else None
    code = _main(
        repair,
        monkeypatch,
        s,
        ["--apply", "--expect-plan-hash", h],
        dispose_raises=dispose,
    )
    captured = capsys.readouterr()
    assert code == 3
    report = _json_tail(captured.out)
    assert report["outcome"] == "UNKNOWN" and report["mode"] == "apply"
    assert report["plan_hash"] == h and report["statements_changed"] == 21
    assert sorted(tuple(w) for w in report["write"]) == _PLAN_WRITES
    assert "nothing committed" not in captured.out
    assert "OperationalError" in captured.err and "proves nothing" in captured.err
    assert s.commits == 1 and "commit" not in _after_first_commit(s)


@pytest.mark.parametrize("raised", ["cancelled", "interrupt"])
def test_an_interrupted_commit_keeps_its_type_and_still_says_unknown(
    repair, monkeypatch, capsys, raised
):
    exc = asyncio.CancelledError() if raised == "cancelled" else KeyboardInterrupt()
    h = _hash(repair)
    s = LostCommitAck(LIVE_2026_10_13, raises=exc)
    with pytest.raises(type(exc)):
        _main(repair, monkeypatch, s, ["--apply", "--expect-plan-hash", h])
    out = capsys.readouterr().out
    assert "nothing committed" not in out and "REFUSED" not in out
    report = _json_tail(out)
    assert report["outcome"] == "UNKNOWN" and report["plan_hash"] == h
    # The wrapper's BaseException exit: no rollback, no COMMIT — close and dispose.
    assert s.commits == 1 and _after_first_commit(s) == ["close", "dispose"]


@pytest.mark.parametrize("raised", ["cancelled", "interrupt"])
def test_a_cleanup_failure_never_replaces_an_interrupted_commit(
    repair, monkeypatch, capsys, raised
):
    exc = asyncio.CancelledError() if raised == "cancelled" else KeyboardInterrupt()
    h = _hash(repair)
    s = LostCommitAck(LIVE_2026_10_13, raises=exc, close_raises=_broken("close"))
    with pytest.raises(type(exc)) as caught:
        _main(repair, monkeypatch, s, ["--apply", "--expect-plan-hash", h])
    assert caught.value is exc
    captured = capsys.readouterr()
    assert _json_tail(captured.out)["outcome"] == "UNKNOWN"
    assert "proves nothing" in captured.err
    assert s.commits == 1


def test_an_interrupt_during_the_cleanup_after_unknown_propagates_as_itself(
    repair, monkeypatch, capsys
):
    h = _hash(repair)
    s = LostCommitAck(LIVE_2026_10_13, rollback_raises=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        _main(repair, monkeypatch, s, ["--apply", "--expect-plan-hash", h])
    assert _json_tail(capsys.readouterr().out)["outcome"] == "UNKNOWN"
    assert s.commits == 1


def test_a_cancel_before_the_commit_is_not_reported_unknown(
    repair, monkeypatch, capsys
):
    class CancelledMidWrites(FakeSession):
        async def execute(self, stmt, params):
            if str(stmt).lstrip().upper().startswith("UPDATE") and self.updates:
                raise asyncio.CancelledError()
            return await super().execute(stmt, params)

    s = CancelledMidWrites(LIVE_2026_10_13)
    with pytest.raises(asyncio.CancelledError):
        _main(repair, monkeypatch, s, ["--apply", "--expect-plan-hash", _hash(repair)])
    assert "UNKNOWN" not in capsys.readouterr().out
    assert s.commits == 0 and s.durable_writes == []
    assert s.calls[-2:] == ["close", "dispose"]


@pytest.mark.parametrize("refusal", ["lock-timeout", "wrong-plan-hash"])
def test_a_refusal_before_the_commit_still_says_nothing_committed(
    repair, monkeypatch, capsys, refusal
):
    # The control for the arms above: a refusal BEFORE COMMIT is sent is a definite
    # rollback, and keeps its exit 2 and its words. The wrapper's normal exit still
    # COMMITs afterwards, but after the rollback that COMMIT carries nothing.
    if refusal == "lock-timeout":
        s, h, words = (
            LockedOnThirdWrite(LIVE_2026_10_13),
            _hash(repair),
            "nothing committed",
        )
    else:
        s, h, words = FakeSession(LIVE_2026_10_13), "0" * 16, "plan hash is"
    code = _main(repair, monkeypatch, s, ["--apply", "--expect-plan-hash", h])
    out = capsys.readouterr().out
    assert code == 2 and out.startswith("REFUSED:") and words in out
    assert "UNKNOWN" not in out
    assert s.rolled_back and s.durable_writes == []
    assert s.calls[-4:] == ["rollback", "commit", "close", "dispose"]


def test_an_acknowledged_commit_still_reports_the_original_success(
    repair, monkeypatch, capsys
):
    h = _hash(repair)
    s = FakeSession(LIVE_2026_10_13)
    code = _main(repair, monkeypatch, s, ["--apply", "--expect-plan-hash", h])
    out = capsys.readouterr().out
    assert code == 0 and s.committed
    assert "UNKNOWN" not in out
    report = _json_tail(out[: out.index("UNDO:")])
    assert report["mode"] == "apply" and report["written"] == 21
    assert report["plan_hash"] == h
    assert "--restore --ids" in out
    # The repair's COMMIT carried the plan; the wrapper's exit COMMIT carried nothing.
    assert sorted(s.durable_writes) == _PLAN_WRITES
    assert s.calls[-4:] == ["commit", "commit", "close", "dispose"]
