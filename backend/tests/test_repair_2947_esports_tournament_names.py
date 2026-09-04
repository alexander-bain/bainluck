"""Guards for the #2947 rename repair and its D51 undo.

The repair renames 366 events and writes nothing else. What can go wrong is
narrow and each one is checked here: renaming from a market that did not name
the event, renaming two rows into one identical-looking pair, writing a column
that does not exist, and an undo that stomps a later decision.
"""

import argparse
import asyncio
import datetime as dt
import importlib.util
import pathlib

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load("repair_2947_esports_tournament_names")
restore = _load("restore_2947_esports_tournament_names")

# A real production row: event 15304464, live 2026-09-04.
REAL_MARKET = (
    "Counter-Strike: Fluxo W7M vs Back to Back  (BO3) - PGL Masters Bucharest: "
    "South American Open Qualifier #1 Playoffs"
)
REAL_HOME = "Counter-Strike: Fluxo W7M"
REAL_AWAY = "Back to Back  (BO3) - PGL Masters Bucharest"


# ---------------------------------------------------------------------------
# one vocabulary, not two that drift
# ---------------------------------------------------------------------------

def test_population_predicate_is_the_shipped_fix_marker():
    """If the repair's anchor differs from the fix's, it repairs a different set.

    Identity, not an equality against a copied literal — that is what makes
    drift impossible rather than merely unlikely.
    """
    from app.utils.prediction_market_matching import _ESPORTS_BEST_OF_RE

    assert repair.BO_RE is _ESPORTS_BEST_OF_RE.pattern


def test_names_are_rederived_by_the_fix_not_by_a_second_regex():
    """The repair must call `extract_matchup`, not reimplement the cleaning."""
    source = (_SCRIPTS / "repair_2947_esports_tournament_names.py").read_text()
    assert "extract_matchup(" in source
    assert "_clean_esports_matchup(" not in source, (
        "reaching past the public entry skips the guards that wrap it"
    )


# ---------------------------------------------------------------------------
# the fingerprint: this market named this event, or we do not touch it
# ---------------------------------------------------------------------------

def test_the_real_row_reconstructs():
    assert repair._fingerprint(REAL_HOME, REAL_AWAY, "Fluxo W7M", "Back to Back") is True


@pytest.mark.parametrize(
    "team_a,team_b,why",
    [
        ("Imperial", "Back to Back", "home is a different team"),
        ("Fluxo W7M", "ALKA", "away is a different team"),
        ("Fluxo", "Back to Back", "home is only a prefix of the real name"),
        ("Fluxo W7M", "", "empty away"),
        ("", "Back to Back", "empty home"),
    ],
)
def test_a_market_that_does_not_reconstruct_is_refused(team_a, team_b, why):
    assert repair._fingerprint(REAL_HOME, REAL_AWAY, team_a, team_b) is False, why


def test_a_bare_home_name_with_no_game_title_still_reconstructs():
    """Not every polluted row carries a prefix; the away marker is the anchor."""
    assert repair._fingerprint("Fluxo W7M", REAL_AWAY, "Fluxo W7M", "Back to Back") is True


# ---------------------------------------------------------------------------
# planning, against a fake session
# ---------------------------------------------------------------------------

class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return [r[0] for r in self._rows]


class _Result:
    def __init__(self, rows):
        self._rows = rows
        self.rowcount = len(rows)

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return _Scalars(self._rows)

    def scalar_one(self):
        return self._rows[0][0] if self._rows else 0


class _FakeSession:
    """Answers by looking at the SQL, so it is order-independent."""

    def __init__(self, events, markets, clash=None, backup_covered=None):
        self.events, self.markets = events, markets
        self.clash = clash or {}
        self.backup_covered = backup_covered
        self.statements = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.statements.append((sql, params or {}))
        if "FROM events e WHERE" in sql:
            return _Result(self.events)
        if "FROM futures_markets" in sql:
            return _Result([(n,) for n in self.markets.get(params["eid"], [])])
        if sql.startswith("SELECT id FROM events WHERE id <>"):
            hit = self.clash.get((params["h"].casefold(), params["a"].casefold()))
            return _Result([(hit,)] if hit else [])
        if "count(*)" in sql:
            n = self.backup_covered
            return _Result([(n if n is not None else len(self.events),)])
        return _Result([])

    async def commit(self):
        pass


def _event(event_id, home=REAL_HOME, away=REAL_AWAY, day="2026-09-04"):
    return (event_id, home, away, dt.datetime.fromisoformat(f"{day}T12:00:00"))


def test_a_row_whose_market_names_it_is_planned():
    session = _FakeSession([_event(1)], {1: [REAL_MARKET]})
    plan, skipped = asyncio.run(repair.build_plan(session))
    assert skipped == []
    assert (plan[0]["new_home"], plan[0]["new_away"]) == ("Fluxo W7M", "Back to Back")


def test_a_row_whose_markets_name_someone_else_is_skipped_not_guessed():
    """The market hangs off the event but did not name it. Leave it alone."""
    other = (
        "Counter-Strike: Imperial vs ALKA (BO3) - PGL Masters Bucharest: "
        "South American Open Qualifier #1 Playoffs"
    )
    session = _FakeSession([_event(1)], {1: [other]})
    plan, skipped = asyncio.run(repair.build_plan(session))
    assert plan == []
    assert skipped[0][3] == "NO_MARKET_RECONSTRUCTS_THE_NAME"


def test_a_row_with_no_markets_at_all_is_skipped():
    session = _FakeSession([_event(1)], {})
    plan, skipped = asyncio.run(repair.build_plan(session))
    assert plan == [] and len(skipped) == 1


# ---------------------------------------------------------------------------
# collisions — the CERT-880 lesson
# ---------------------------------------------------------------------------

def _plan_rows(*pairs):
    return [
        {
            "id": i,
            "old_home": REAL_HOME,
            "old_away": REAL_AWAY,
            "new_home": h,
            "new_away": a,
            "commence": dt.datetime.fromisoformat("2026-09-04T12:00:00"),
            "from_market": REAL_MARKET,
        }
        for i, (h, a) in enumerate(pairs, start=1)
    ]


def test_two_rows_cleaning_to_the_same_fixture_are_both_dropped():
    """The five closed twin pairs (#2693, lane1's).

    Renaming both turns two obviously-broken rows into two convincing identical
    ones — worse than leaving them, which is what CERT-880 ruled.
    """
    session = _FakeSession([], {})
    kept, dropped = asyncio.run(
        repair.drop_collisions(session, _plan_rows(("BIG", "Nemiga"), ("BIG", "Nemiga")))
    )
    assert kept == []
    assert [why for _, why in dropped] == ["TWIN_WITHIN_PLAN"] * 2


def test_a_row_that_would_land_on_an_existing_clean_fixture_is_dropped():
    session = _FakeSession([], {}, clash={("big", "nemiga"): 999})
    kept, dropped = asyncio.run(repair.drop_collisions(session, _plan_rows(("BIG", "Nemiga"))))
    assert kept == []
    assert dropped[0][1] == "CLEAN_COUNTERPART_EXISTS:999"


def test_distinct_fixtures_are_all_kept():
    session = _FakeSession([], {})
    kept, dropped = asyncio.run(
        repair.drop_collisions(session, _plan_rows(("BIG", "Nemiga"), ("TYLOO", "Rare Atom")))
    )
    assert len(kept) == 2 and dropped == []


def test_the_collision_window_is_the_one_that_was_measured():
    """+/-2 days, the window the 0-of-366 counterpart rate was measured over."""
    session = _FakeSession([], {})
    asyncio.run(repair.drop_collisions(session, _plan_rows(("BIG", "Nemiga"))))
    clash_sql = [s for s, _ in session.statements if "id <>" in s][0]
    assert "interval '2 days'" in clash_sql


# ---------------------------------------------------------------------------
# what reaches Postgres
# ---------------------------------------------------------------------------

def _all_statements():
    """Every statement the repair actually runs, captured from a full pass."""
    session = _FakeSession([_event(1)], {1: [REAL_MARKET]})
    plan, _ = asyncio.run(repair.build_plan(session))
    plan, _ = asyncio.run(repair.drop_collisions(session, plan))
    asyncio.run(repair.ensure_backup(session, plan))
    asyncio.run(repair.apply_plan(session, plan))
    return session.statements


def test_every_statement_parses_as_postgres():
    """A syntax error here is otherwise only found by an unreadable dyno run."""
    sqlglot = pytest.importorskip("sqlglot")
    statements = _all_statements()
    assert len(statements) >= 6, f"only captured {len(statements)} statements"
    for sql, _ in statements:
        try:
            parsed = sqlglot.parse(sql, dialect="postgres")
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"not valid Postgres: {exc}\n{sql}")
        assert parsed and parsed[0] is not None


def test_no_bind_does_date_arithmetic_without_an_explicit_cast():
    """Postgres types `:c - interval '2 days'` BEFORE it looks at the column.

    An untyped parameter next to an interval has exactly one candidate operator,
    `interval - interval`, so `:c` is resolved as an interval and the predicate
    dies with `operator does not exist: timestamp with time zone >= interval`.
    That is not a syntax error, so `test_every_statement_parses_as_postgres`
    passes and sqlglot is perfectly happy — only real type resolution rejects it.
    It killed the first production dry run of this repair (2026-09-04), in
    `drop_collisions`, which is the collision safety net the whole repair rests on.

    Checked over the whole class rather than the one statement: any interval
    added to or subtracted from a bare placeholder, anywhere in the SQL this
    script executes.
    """
    sqlglot = pytest.importorskip("sqlglot")
    from sqlglot import exp

    offenders = []
    for sql, _ in _all_statements():
        for interval in sqlglot.parse_one(sql, dialect="postgres").find_all(exp.Interval):
            parent = interval.parent
            if not isinstance(parent, (exp.Add, exp.Sub)):
                continue
            other = parent.left if parent.right is interval else parent.right
            if isinstance(other, exp.Placeholder):
                offenders.append(f"{parent.sql(dialect='postgres')}   in: {sql}")

    assert not offenders, (
        "a bind parameter is doing interval arithmetic with no CAST — Postgres "
        "will resolve it as an interval and the predicate will not run:\n  "
        + "\n  ".join(offenders)
    )


def test_the_marker_regex_reaches_postgres_as_a_bind_value_never_as_sql_text():
    """gotcha #45 — a pattern inlined into `text()` is scanned for binds."""
    for sql, params in _all_statements():
        assert repair.BO_RE not in sql, f"pattern was interpolated into SQL: {sql}"
    assert any(params.get("bo_re") == repair.BO_RE for _, params in _all_statements())


def test_the_repair_writes_exactly_two_events_columns():
    """`events` has no `updated_at`; and nothing else here is the repair's to move."""
    updates = [sql for sql, _ in _all_statements() if sql.startswith("UPDATE events")]
    assert len(updates) == 1
    assignments = updates[0].split("SET", 1)[1].split("WHERE")[0]
    assert sorted(a.split("=")[0].strip() for a in assignments.split(",")) == [
        "away_team_name",
        "home_team_name",
    ]


def test_the_update_is_guarded_on_the_pre_repair_values():
    """A row something else renamed first must be left alone, not stomped."""
    update = [sql for sql, _ in _all_statements() if sql.startswith("UPDATE events")][0]
    where = update.split("WHERE", 1)[1]
    assert "home_team_name = :oh" in where and "away_team_name = :oa" in where


def test_the_backup_records_what_the_repair_will_write():
    """Without it the undo has to guess whether a changed name is its own."""
    inserts = [sql for sql, _ in _all_statements() if "INSERT INTO bak_2947" in sql]
    assert inserts and "new_home_team_name" in inserts[0]
    assert "WHERE NOT EXISTS" in inserts[0], "the backup top-up must be idempotent"


# ---------------------------------------------------------------------------
# the D51 undo
# ---------------------------------------------------------------------------

def test_restore_leaves_a_row_that_was_renamed_again_alone():
    """An undo that overwrites a later, unrelated decision is not an undo."""
    source = (_SCRIPTS / "restore_2947_esports_tournament_names.py").read_text()
    assert "(now_home, now_away) == (new_home, new_away)" in source
    assert "diverged" in source


def test_restore_is_dry_by_default_and_drop_backups_is_explicit():
    parser_source = (_SCRIPTS / "restore_2947_esports_tournament_names.py").read_text()
    assert '"--apply"' in parser_source and '"--drop-backups"' in parser_source
    assert "DRY RUN" in parser_source


def test_the_population_floor_exists_so_an_empty_run_cannot_report_success():
    """gotcha #53 — an empty result is a response shape, not an absence."""
    assert repair.MIN_EXPECTED_POPULATION >= 300


# ---------------------------------------------------------------------------
# L1B-030-REPAIR-TAIL-17 — the claim and the result must agree
# ---------------------------------------------------------------------------

def test_the_disposition_is_pre_registered_and_adds_up():
    """Every row of the population lands in exactly one bucket.

    The pre-registered numbers come from CERT-900's production replay. If they
    do not partition the population, the claim is incoherent before the script
    even runs.
    """
    e = repair.EXPECTED
    assert e["plan"] + e["no_reconstruct"] + e["clean_counterpart"] + e["twins"] == (
        e["population"]
    ), f"the pre-registered buckets do not sum to the population: {e}"


def test_the_docstring_claim_matches_the_registered_numbers():
    """The prose and the constant are the same claim, so neither can rot alone."""
    source = (_SCRIPTS / "repair_2947_esports_tournament_names.py").read_text()
    assert "The replay found 3." in source
    assert repair.EXPECTED["clean_counterpart"] == 3
    assert "14 rows do not reconstruct" in source
    assert repair.EXPECTED["no_reconstruct"] == 14


def test_a_run_matching_the_registered_disposition_has_no_drift():
    assert repair.disposition_drift(dict(repair.EXPECTED)) == {}


@pytest.mark.parametrize("bucket", ["population", "plan", "no_reconstruct", "clean_counterpart", "twins"])
def test_any_bucket_moving_is_drift(bucket):
    """BEHAVIOURAL. Every bucket is guarded, not just the plan count."""
    measured = dict(repair.EXPECTED)
    measured[bucket] += 1
    drift = repair.disposition_drift(measured)
    assert bucket in drift, f"{bucket} moved by one and the guard did not notice"


def test_expect_plan_restates_one_number_and_relaxes_nothing_else():
    """--expect-plan is a restated claim, not a blanket --force."""
    measured = {**repair.EXPECTED, "plan": 300}
    assert repair.disposition_drift(measured, expect_plan=300) == {}

    also_twins = {**repair.EXPECTED, "plan": 300, "twins": 2}
    drift = repair.disposition_drift(also_twins, expect_plan=300)
    assert "twins" in drift and "plan" not in drift, (
        "--expect-plan let a twin through; it must only restate the plan count"
    )


def test_a_twin_is_registered_at_zero_so_one_trips_the_guard():
    """The replay reported no twins while a SQL pass found five same-second pairs.

    That contradiction is unresolved, so it is registered at 0 deliberately: the
    run settles it, and a single twin stops the apply instead of being absorbed.
    """
    assert repair.EXPECTED["twins"] == 0


# ---------------------------------------------------------------------------
# L1B-031 — the entrypoint runs, and no refusal loses a race with a write
#
# Everything above this line reaches past `run()` — into `_fingerprint`,
# `build_plan`, `disposition_drift`. That is exactly how this script shipped
# crashing on an import that has never resolved, with a drift guard sitting
# below the backup write and behind an `args.limit` exemption, while the suite
# stayed green (CERT-903). Two of the guards that were supposed to cover this
# asserted on the SOURCE TEXT, which survives any amount of dead or bypassed
# code. These invoke `run()`.
# ---------------------------------------------------------------------------


class _SessionFactory:
    """The shape `run()` uses: call it, then `async with` the result."""

    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _args(**kw):
    return argparse.Namespace(
        **{
            **dict(backup=False, apply=False, limit=0, allow_small=False, expect_plan=None),
            **kw,
        }
    )


def _run(monkeypatch, session, **kw):
    """Run the real `run()` against a fake session; return (exit code, writes).

    `ensure_backup` and `apply_plan` are the only two functions in this script
    that write, so recording their calls records every write the run made.
    """
    writes = []

    async def _backup(_session, plan):
        writes.append("backup")
        return len(plan)

    async def _apply(_session, plan):
        writes.append("apply")
        return len(plan)

    monkeypatch.setattr(repair, "_session_factory", lambda: _SessionFactory(session))
    monkeypatch.setattr(repair, "ensure_backup", _backup)
    monkeypatch.setattr(repair, "apply_plan", _apply)
    return asyncio.run(repair.run(_args(**kw))), writes


def test_the_production_entrypoint_resolves_a_real_session_factory():
    """The smoke guard that would have caught the crash.

    Both scripts imported `app.database.AsyncSessionLocal`. There is no
    `app.database` module and there never has been, so the exact documented
    heroku command died on import — the repair before planning a row, the D51
    undo before restoring one. Identity, so a rename on the app side fails here
    rather than at 2am on a dyno.
    """
    from app.services.database import async_session_maker

    assert repair._session_factory() is async_session_maker
    assert restore._session_factory() is async_session_maker


def test_a_drifted_limited_apply_writes_absolutely_nothing(monkeypatch):
    """The exact invocation that got through: --limit N --backup --apply.

    A limited run plans a subset, so it always disagrees with a disposition
    registered over the whole population — the old exemption turned that
    certainty into a bypass, and the run backed up, renamed and exited 0.
    """
    session = _FakeSession([_event(1)], {1: [REAL_MARKET]})
    code, writes = _run(monkeypatch, session, limit=1, backup=True, apply=True)

    assert code != 0, "a limited apply reported success"
    assert writes == [], f"a limited apply reached a write: {writes}"


def test_a_drifted_full_apply_refuses_before_the_backup_not_after(monkeypatch):
    """Replaces a source-text assertion that the refusal appeared above the write.

    That one passed while the refusal sat BELOW `ensure_backup` — it only ever
    compared two string offsets. This one lets the run decide.
    """
    session = _FakeSession([_event(1)], {1: [REAL_MARKET]})
    code, writes = _run(
        monkeypatch, session, backup=True, apply=True, allow_small=True
    )

    assert code == 6, "a plan of 1 against a registered 349 did not trip the drift guard"
    assert writes == [], f"the drift guard let a write through first: {writes}"


def test_an_apply_without_a_backup_refuses_before_the_rename(monkeypatch):
    session = _FakeSession([_event(1)], {1: [REAL_MARKET]})
    code, writes = _run(monkeypatch, session, apply=True, allow_small=True)

    assert code == 4
    assert writes == []


def test_an_apply_that_matches_its_claim_backs_up_and_then_renames(monkeypatch):
    """The green arm. Without it every refusal above could be unconditional."""
    session = _FakeSession([_event(1)], {1: [REAL_MARKET]})
    monkeypatch.setattr(
        repair,
        "EXPECTED",
        {"population": 1, "plan": 1, "no_reconstruct": 0, "clean_counterpart": 0, "twins": 0},
    )
    code, writes = _run(
        monkeypatch, session, backup=True, apply=True, allow_small=True
    )

    assert code == 0, "a run agreeing with its own claim was refused"
    assert writes == ["backup", "apply"], "the backup must land before the rename"


# ---------------------------------------------------------------------------
# the D51 undo, at run level — the reason an unattended repair is permitted
# ---------------------------------------------------------------------------


class _FakeRestoreSession:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        if "to_regclass" in sql:
            return _Result([(restore.BAK_TABLE,)])
        if sql.startswith("SELECT b.event_id"):
            return _Result(self.rows)
        if sql.startswith("UPDATE events SET"):
            self.updates.append(params)
            return _Result([("written",)])
        return _Result([])

    async def commit(self):
        pass


def test_the_undo_puts_back_what_the_repair_wrote_and_nothing_else(monkeypatch):
    """Three rows, one of each disposition, through the real `run()`.

    D51 permits an unattended production repair BECAUSE this command exists, so
    "it exists" has to mean more than "the file is on disk".
    """
    repaired = ("Fluxo W7M", "Back to Back")
    rows = [
        # event_id, pre-repair pair, what the repair wrote, what is there now
        (1, REAL_HOME, REAL_AWAY, *repaired, *repaired),  # the repair's: restore
        (2, REAL_HOME, REAL_AWAY, *repaired, "Someone", "Else"),  # moved on: leave
        (3, REAL_HOME, REAL_AWAY, *repaired, REAL_HOME, REAL_AWAY),  # already back
    ]
    session = _FakeRestoreSession(rows)
    monkeypatch.setattr(restore, "_session_factory", lambda: _SessionFactory(session))

    code = asyncio.run(restore.run(argparse.Namespace(apply=True, drop_backups=False)))

    assert code == 0
    assert [u["eid"] for u in session.updates] == [1], (
        "the undo stomped a row it had not renamed, or missed one it had"
    )
