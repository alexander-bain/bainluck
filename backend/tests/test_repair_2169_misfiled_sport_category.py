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

    async def execute(self, stmt, params):
        sql = str(stmt)
        if sql.lstrip().upper().startswith("SELECT"):
            ids = set(params["ids"])
            return _Result(_Row(i, c, n) for i, (c, n) in self.live.items() if i in ids)
        assert sql.lstrip().upper().startswith("UPDATE")
        self.updates.append(dict(params, sql=sql))
        if self.rowcount == 1 and self.live[params["id"]][0] == params["source"]:
            self.live[params["id"]][0] = params["target"]
            return _Result(rowcount=1)
        return _Result(rowcount=0 if self.rowcount == 1 else self.rowcount)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


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


def test_the_write_is_a_compare_and_set_on_the_category_alone(repair):
    sql = " ".join(repair._CAS_SQL.split())
    assert "SET llm_sport_category = :target WHERE" in sql
    assert sql.endswith("WHERE id = :id AND llm_sport_category = :source")
    for column in ("canonical_market_key", "updated_at", "category_tags", "llm_league"):
        assert column not in sql


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
