"""#2993 — the repair that unmakes the events a bracket minted, and its undo.

The prevention is tested in `test_bracket_is_not_a_game_2993.py`. This file is
about the CLEANUP: that its population is the shipped predicate's and not a
second regex that can drift, that a rename is earned by provenance rather than
by resemblance, that every statement it runs is valid Postgres, and that the
D51 undo can actually put back what the repair took away.

Two lessons from the #2947 pair are re-armed here rather than assumed:

  * CERT-903 — both scripts shipped importing `app.database`, a module that has
    never existed. Every unit test passed against a fake session while the real
    entrypoint died on import. `test_the_entrypoint_resolves_for_real` is the
    only test in this file that touches the real module.
  * CERT-907 — an untyped bind next to an interval is resolved BY POSTGRES as
    an interval, which sqlglot is perfectly happy with. This repair does its
    date arithmetic in Python and passes timestamps as values; the test asserts
    that stays true.
"""

import asyncio
import datetime as dt
import importlib.util
import os

import pytest

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_SCRIPTS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repair = _load("repair_2993_bracket_events")
restore = _load("restore_2993_bracket_events")


# The real production strings, read 2026-09-04.
CUT_HOME = "VALORANT Masters"
CUT_AWAY = "Masters Santiago (Playoffs"
CUT_MARKET = (
    "VALORANT Masters - Masters Santiago (Playoffs: Playoffs): "
    "Paper Rex vs. NRG Map 1"
)
STAGE_HOME = "FNCS Major 2: Europe"
STAGE_AWAY = "Grand Finals"

COMMENCE = dt.datetime(2026, 3, 28, 17, 0, tzinfo=dt.timezone.utc)


# ── the population is the shipped predicate's ────────────────────────────────

def test_the_population_predicate_is_the_shipped_fix():
    """Imported, not restated — the repair cannot drift from the guard."""
    from app.utils import prediction_market_matching as fix

    assert repair.bracket_refusal_reason is fix.bracket_refusal_reason


def test_the_sql_prefilter_is_only_a_prefilter():
    """Whatever SQL selects, the shipped predicate decides. A row the guard
    would allow must never be planned, however the prefilter matched it."""
    session = _FakeSession([(1, "Paper Rex", "NRG", COMMENCE, None, "closed")])
    assert asyncio.run(repair.build_plan(session)) == []


def test_the_stage_pattern_reaching_postgres_has_no_bind_eating_group():
    """gotcha #45 — `(?:` inside `text()` is read as a bind named `:Exact`."""
    assert "(?:" not in repair.STAGE_RE_SQL
    from app.utils.prediction_market_matching import _TOURNAMENT_STAGE_RE

    assert repair.STAGE_RE_SQL == _TOURNAMENT_STAGE_RE.pattern.replace("(?:", "(")


# ── reconstruction: earned by provenance, never by resemblance ───────────────

def test_the_real_market_name_reconstructs_the_real_matchup():
    assert repair.reconstruct_matchup(CUT_MARKET) == ("Paper Rex", "NRG")


@pytest.mark.parametrize(
    "name,why",
    [
        ("FNCS Major 2: Europe - Grand Finals: Winner", "the tail is another bracket"),
        ("VALORANT Masters - Masters Santiago (Playoffs: Playoffs)", "no tail at all"),
        ("", "empty"),
        ("Paper Rex wins the whole thing", "not a matchup"),
    ],
)
def test_an_unreconstructible_name_is_refused_not_guessed(name, why):
    assert repair.reconstruct_matchup(name) is None, why


def test_a_reconstructed_bracket_is_still_refused():
    """The tail must be a MATCHUP. A tail that is itself two bracket words
    would otherwise be laundered into a clean-looking rename."""
    assert repair.reconstruct_matchup(
        "Something (X: Y): Upper Bracket vs. Grand Finals"
    ) is None


# ── the plan ─────────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, rows):
        self._rows = rows
        self.rowcount = len(rows)

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0][0] if self._rows else None

    def scalars(self):
        return _Scalars(self._rows)


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return [r[0] for r in self._rows]


class _FakeSession:
    """Answers by looking at the SQL, so it is order-independent."""

    def __init__(self, events, markets=None, market_names=None, counterparts=None):
        self.events = events
        self.markets = markets or {}
        self.market_names = market_names or {}
        self.counterparts = counterparts or {}
        self.statements = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        self.statements.append((sql, params))
        if sql.startswith("SELECT e.id, e.home_team_name"):
            return _Result(self.events)
        if sql.startswith("SELECT id FROM futures_markets WHERE event_id"):
            return _Result([(m,) for m in self.markets.get(params["eid"], [])])
        if sql.startswith("SELECT name FROM futures_markets"):
            name = self.market_names.get(params["mid"])
            return _Result([(name,)] if name else [])
        if sql.startswith("SELECT name, commence_time FROM futures_markets"):
            return _Result([])
        if sql.startswith("SELECT id FROM events WHERE id <>"):
            hit = self.counterparts.get(
                (params["h"].casefold(), params["a"].casefold())
            )
            return _Result([(hit,)] if hit else [])
        if "count(*)" in sql:
            return _Result([(0,)])
        return _Result([])

    async def commit(self):
        pass


def _cut_event(event_id, external_id=None):
    return (event_id, CUT_HOME, CUT_AWAY, COMMENCE, external_id, "closed")


def test_a_stage_row_is_planned_for_delete():
    session = _FakeSession([(1, STAGE_HOME, STAGE_AWAY, COMMENCE, None, "suspended")])
    plan = asyncio.run(repair.build_plan(session))
    assert [(e["id"], e["action"]) for e in plan] == [(1, "delete")]


def test_a_row_with_no_external_id_cannot_be_renamed():
    """10 of the 15 production rows are in exactly this state."""
    session = _FakeSession([_cut_event(1)])
    plan = asyncio.run(repair.build_plan(session))
    assert plan[0]["action"] == "delete"
    assert plan[0]["new_home"] is None


def test_a_row_whose_ticker_names_it_and_has_no_counterpart_is_renamed():
    """The real 14546060: provenance identifies the match, nothing holds it."""
    session = _FakeSession(
        [_cut_event(1, "pm_kalshi_KXVALORANTMAP-26MAR14PRNRG-1")],
        market_names={"KXVALORANTMAP-26MAR14PRNRG-1": CUT_MARKET},
    )
    plan = asyncio.run(repair.build_plan(session))
    assert plan[0]["action"] == "rename"
    assert (plan[0]["new_home"], plan[0]["new_away"]) == ("Paper Rex", "NRG")


def test_a_row_whose_match_already_exists_is_deleted_not_renamed():
    """The rename must never mint a lookalike of a game we already hold."""
    session = _FakeSession(
        [_cut_event(1, "pm_kalshi_KXVALORANTMAP-26MAR14PRNRG-1")],
        market_names={"KXVALORANTMAP-26MAR14PRNRG-1": CUT_MARKET},
        counterparts={("paper rex", "nrg"): 8083763},
    )
    plan = asyncio.run(repair.build_plan(session))
    assert plan[0]["action"] == "delete"
    assert plan[0]["counterpart"] == 8083763


def test_the_counterpart_check_reads_both_orientations():
    """"NRG at Paper Rex" is the same game as "Paper Rex at NRG", so a rename
    must not fire just because the stored row has the teams the other way up."""
    session = _FakeSession([], counterparts={})
    asyncio.run(repair._clean_counterpart(session, "Paper Rex", "NRG", COMMENCE, 1))
    sql = session.statements[-1][0]
    forward = "lower(home_team_name) = lower(:h) AND lower(away_team_name) = lower(:a)"
    reverse = "lower(home_team_name) = lower(:a) AND lower(away_team_name) = lower(:h)"
    assert forward in sql, "forward arm missing"
    assert reverse in sql, "reverse arm missing — a flipped fixture reads as absent"
    assert "id <> :self" in sql, "the row would find ITSELF and never be renamed"


def test_an_unidentifiable_row_keeps_its_markets_in_the_plan():
    """The markets must be unlinked before the row can be deleted at all —
    `futures_markets.event_id` is NO ACTION, so a bare DELETE is refused."""
    session = _FakeSession([_cut_event(1)], markets={1: [11, 22, 33]})
    plan = asyncio.run(repair.build_plan(session))
    assert plan[0]["market_ids"] == [11, 22, 33]


# ── the statements ───────────────────────────────────────────────────────────

def _all_statements():
    session = _FakeSession(
        [
            _cut_event(1, "pm_kalshi_KXVALORANTMAP-26MAR14PRNRG-1"),
            (2, STAGE_HOME, STAGE_AWAY, COMMENCE, None, "suspended"),
        ],
        markets={2: [99]},
        market_names={"KXVALORANTMAP-26MAR14PRNRG-1": CUT_MARKET},
    )
    plan = asyncio.run(repair.build_plan(session))
    asyncio.run(repair.count_matches_without_counterpart(session, plan))
    asyncio.run(repair.ensure_backup(session, plan))
    asyncio.run(repair.apply_plan(session, plan))
    return session.statements


def test_every_statement_parses_as_postgres():
    """A syntax error here is otherwise only found by an unreadable dyno run."""
    sqlglot = pytest.importorskip("sqlglot")
    statements = _all_statements()
    assert len(statements) >= 8, f"only captured {len(statements)} statements"
    for sql, _ in statements:
        try:
            parsed = sqlglot.parse(sql, dialect="postgres")
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"not valid Postgres: {exc}\n{sql}")
        assert parsed and parsed[0] is not None


def test_no_bind_does_interval_arithmetic_in_sql():
    """CERT-907 — `:c - interval '6 hours'` types `:c` AS AN INTERVAL.

    Postgres resolves an untyped parameter beside an interval against the only
    candidate operator, `interval - interval`, and the predicate dies with
    "operator does not exist: timestamp with time zone >= interval". sqlglot
    parses it happily, so the test above cannot see it. This repair does the
    arithmetic in Python (`commence - _WINDOW`) and passes both bounds as
    values; this asserts nobody moves it back into the SQL.
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


def test_the_window_is_computed_in_python_and_passed_as_two_values():
    session = _FakeSession([], counterparts={})
    asyncio.run(repair._clean_counterpart(session, "A", "B", COMMENCE, 1))
    _, params = session.statements[-1]
    assert params["lo"] == COMMENCE - repair._WINDOW
    assert params["hi"] == COMMENCE + repair._WINDOW


def test_markets_are_unlinked_before_the_row_is_deleted():
    """`futures_markets.event_id` is NO ACTION: the wrong order is an error,
    not a silent partial repair."""
    statements = [sql for sql, _ in _all_statements()]
    unlink = next(
        i for i, s in enumerate(statements) if s.startswith("UPDATE futures_markets")
    )
    delete = next(
        i for i, s in enumerate(statements) if s.startswith("DELETE FROM events")
    )
    assert unlink < delete


def test_the_taxonomy_cache_row_is_deleted_before_its_event():
    """`line_movement_analyses` is NO ACTION too, and it blocked the delete."""
    statements = [sql for sql, _ in _all_statements()]
    lma = next(
        i for i, s in enumerate(statements)
        if s.startswith("DELETE FROM line_movement_analyses")
    )
    delete = next(
        i for i, s in enumerate(statements) if s.startswith("DELETE FROM events")
    )
    assert lma < delete


def test_the_unlink_is_guarded_on_the_event_it_is_detaching_from():
    """A market that moved to a real event since planning must not be cleared."""
    unlink = [
        sql for sql, _ in _all_statements() if sql.startswith("UPDATE futures_markets")
    ][0]
    assert "event_id = :eid" in unlink.split("WHERE", 1)[1]


def test_the_repair_writes_exactly_two_events_columns():
    updates = [
        sql for sql, _ in _all_statements() if sql.startswith("UPDATE events")
    ]
    assert len(updates) == 1
    assignments = updates[0].split("SET", 1)[1].split("WHERE")[0]
    assert sorted(a.split("=")[0].strip() for a in assignments.split(",")) == [
        "away_team_name",
        "home_team_name",
    ]


def test_the_backup_records_what_the_repair_will_write():
    """Without `applied_names` the undo cannot tell "as I left it" from
    "something else moved this on", and would stomp the latter."""
    inserts = [
        (sql, params)
        for sql, params in _all_statements()
        if sql.startswith(f"INSERT INTO {repair.BAK_EVENTS}")
    ]
    assert inserts, "nothing was banked"
    assert any("Paper Rex" in (p.get("applied") or "") for _, p in inserts)
    assert all("to_jsonb(e)" in sql for sql, _ in inserts), "row not banked whole"
    assert any("lma_rows" in sql for sql, _ in inserts)
    assert any("anchor_rows" in sql for sql, _ in inserts)


def test_the_market_links_are_banked_too():
    links = [
        params for sql, params in _all_statements()
        if sql.startswith(f"INSERT INTO {repair.BAK_LINKS}")
    ]
    assert [(p["mid"], p["eid"]) for p in links] == [(99, 2)]


# ── the gates ────────────────────────────────────────────────────────────────

def test_the_population_floor_exists_so_an_empty_run_cannot_report_success():
    assert repair.MIN_EXPECTED_POPULATION >= 10


def test_the_disposition_is_pre_registered_and_adds_up():
    assert repair.EXPECTED["rename"] + repair.EXPECTED["delete"] == (
        repair.EXPECTED["population"]
    )


def test_a_run_matching_the_registered_disposition_has_no_drift():
    assert repair.disposition_drift(dict(repair.EXPECTED)) == {}


@pytest.mark.parametrize("bucket", sorted(repair.EXPECTED))
def test_any_bucket_moving_is_drift(bucket):
    measured = dict(repair.EXPECTED)
    measured[bucket] += 1
    assert bucket in repair.disposition_drift(measured)


def test_the_uncomfortable_number_is_registered_too():
    """Two real matches keep no event row after this runs. That is the number
    the delete branch is justified by, so it gates like any other."""
    assert repair.EXPECTED["matches_without_counterpart"] == 2


def test_the_docstring_claim_matches_the_registered_numbers():
    doc = repair.__doc__
    assert "17 rows" in doc
    assert "RENAME (1 row)" in doc
    assert "DELETE (16 rows)" in doc
    assert "32" in doc


# ── the undo ─────────────────────────────────────────────────────────────────

def test_restore_leaves_a_row_that_was_renamed_again_alone():
    session = _RestoreSession(
        rows=[
            (
                1,
                "rename",
                {"home_team_name": CUT_HOME, "away_team_name": CUT_AWAY},
                [],
                [],
                {"home": "Paper Rex", "away": "NRG"},
            )
        ],
        current={1: ("Someone Else", "Entirely")},
    )
    report = asyncio.run(restore.restore_events(session, apply=True))
    assert report["diverged"] == 1 and report["renamed_back"] == 0


def test_restore_puts_back_a_rename_it_still_owns():
    session = _RestoreSession(
        rows=[
            (
                1,
                "rename",
                {"home_team_name": CUT_HOME, "away_team_name": CUT_AWAY},
                [],
                [],
                {"home": "Paper Rex", "away": "NRG"},
            )
        ],
        current={1: ("Paper Rex", "NRG")},
    )
    report = asyncio.run(restore.restore_events(session, apply=True))
    assert report["renamed_back"] == 1 and report["diverged"] == 0
    update = [s for s, _ in session.statements if s.startswith("UPDATE events")][0]
    assert "home_team_name = :h" in update


def test_restore_reinserts_a_deleted_row_with_its_original_id():
    """Every child in the backup points at that id — a new id restores nothing."""
    session = _RestoreSession(
        rows=[(7, "delete", {"id": 7, "home_team_name": CUT_HOME}, [], [], None)],
        current={},
    )
    report = asyncio.run(restore.restore_events(session, apply=True))
    assert report["reinserted"] == 1
    insert = [s for s, _ in session.statements if s.startswith("INSERT INTO events")][0]
    assert "jsonb_populate_record" in insert, (
        "a column added to events since the backup would break a positional insert"
    )


def test_restore_does_not_reinsert_a_row_that_is_already_back():
    session = _RestoreSession(
        rows=[(7, "delete", {"id": 7, "home_team_name": CUT_HOME}, [], [], None)],
        current={7: (CUT_HOME, CUT_AWAY)},
    )
    report = asyncio.run(restore.restore_events(session, apply=True))
    assert report["already_present"] == 1 and report["reinserted"] == 0


def test_restore_is_dry_by_default_and_drop_backups_is_explicit():
    import inspect

    source = inspect.getsource(restore.main)
    assert '"--apply"' in source and '"--drop-backups"' in source
    body = inspect.getsource(restore.run)
    assert "if not args.apply" in body


class _RestoreSession:
    def __init__(self, rows, current):
        self.rows = rows
        self.current = current
        self.statements = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        self.statements.append((sql, params))
        if sql.startswith("SELECT to_regclass"):
            return _Result([("x",)])
        if sql.startswith("SELECT event_id, action"):
            return _Result(self.rows)
        if sql.startswith("SELECT home_team_name, away_team_name FROM events"):
            hit = self.current.get(params["eid"])
            return _Result([hit] if hit else [])
        if sql.startswith("SELECT market_id"):
            return _Result([])
        return _Result([])

    async def commit(self):
        pass


# ── the entrypoint, for real ─────────────────────────────────────────────────

@pytest.mark.parametrize("module", [repair, restore])
def test_the_entrypoint_resolves_for_real(module):
    """CERT-903 — the only test here that touches the real app.

    #2947's pair shipped importing `app.database`, a module that has never
    existed. Every unit test above would pass against a fake session while the
    production run died before planning a row. This calls the real factory.
    """
    factory = module._session_factory()
    assert callable(factory)

    from app.services.database import async_session_maker

    assert factory is async_session_maker

