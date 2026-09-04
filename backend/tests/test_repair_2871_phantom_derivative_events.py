"""Guards for the #2871 historical cleanup (lane1b).

This repair deletes 8,600+ `events` rows and ~289,000 child rows on production
under D51. It runs on a one-off dyno whose stdout cannot be read (gotcha #48),
so a mistake in it is invisible until someone notices the damage. Everything
here exists because the corresponding mistake is cheap to make and expensive to
find:

* the population predicate silently drifting from the prevention's vocabulary
* an `UPDATE events` naming a column `events` does not have (it does not have
  `updated_at` — this bug was written and caught here)
* a Branch B survivor landing in the delete list, which is the data loss the
  whole two-branch design exists to avoid
* the D51 backup gate passing vacuously on an empty reconciliation
* re-pointing an anchor or a win-prob curve instead of deleting it, which is
  worse than the phantom because the result looks legitimate
"""
import asyncio
import datetime as dt
import importlib.util
import pathlib
import re

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load("repair_2871_phantom_derivative_events")
restore = _load("restore_2871_phantom_derivative_events")


# ---------------------------------------------------------------------------
# the population predicate IS the prevention's vocabulary
# ---------------------------------------------------------------------------

def test_population_predicate_is_the_shipped_prevention_vocabulary():
    """One vocabulary, not two that drift.

    If the repair's net differs from `is_derivative_market_name()`'s net it
    either leaves phantoms behind or eats rows the fix would have allowed. The
    identity check (not an equality on a copied literal) is what makes drift
    impossible rather than merely unlikely.
    """
    from app.utils.prediction_market_matching import _DERIVATIVE_SUFFIX_RE

    assert repair.DERIV_RE is _DERIVATIVE_SUFFIX_RE.pattern


def test_regex_reaches_postgres_as_a_bind_value_never_as_sql_text():
    """gotcha #45: `(?:` inside `text()` is parsed as a bind param `:Exact`.

    The query then dies as a bare `query_failed` with no hint. The pattern must
    travel as a *value* bound to `:deriv_re`, so it is never scanned for binds.
    """
    assert "(?:" in repair.DERIV_RE, "regex has no non-capturing group — retire this guard"

    sql_text = "\n".join([repair._PLAN_SQL, repair._CENSUS_SQL, *repair.SQL.values()])
    assert "(?:" not in sql_text, (
        "a non-capturing group leaked into literal SQL — SQLAlchemy will read "
        "it as a bind parameter and the statement will fail with no hint"
    )
    assert ":deriv_re" in repair._PLAN_SQL and ":deriv_re" in repair._CENSUS_SQL


@pytest.mark.parametrize("raw,clean", [
    # Straight off the production /search?q=Thun screenshot that opened #2871.
    ("Lausanne-Sport - Total Corners", "Lausanne-Sport"),
    ("Lausanne-Sport - Exact Score", "Lausanne-Sport"),
    ("Lausanne-Sport - First Team to Score", "Lausanne-Sport"),
    ("Lausanne-Sport - Halftime Result", "Lausanne-Sport"),
    ("Lausanne-Sport - Second Half Result", "Lausanne-Sport"),
    ("PFC Slavia Sofia - Second Half Result", "PFC Slavia Sofia"),
    ("Araz Nakhchivan PFK - 1st Half First Team to Score", "Araz Nakhchivan PFK"),
])
def test_cleaning_recovers_the_real_away_team(raw, clean):
    """The rename has to produce the fixture, not a differently-broken string."""
    assert repair.is_derivative_market_name(raw)
    assert repair._DERIVATIVE_SUFFIX_RE.sub("", raw).strip() == clean


def test_a_club_name_containing_a_hyphen_is_not_a_derivative():
    """`Lausanne-Sport` must survive: the suffix is dash-INTRODUCED, not any dash."""
    assert not repair.is_derivative_market_name("FC Thun vs. Lausanne-Sport")
    assert not repair.is_derivative_market_name("Lausanne-Sport")


# ---------------------------------------------------------------------------
# the statements are valid Postgres and write only columns that exist
# ---------------------------------------------------------------------------

def _rendered_statements():
    """Every template rendered with the real identifiers it runs against."""
    out = {}
    for name, tmpl in repair.SQL.items():
        out[name] = tmpl.format(
            bak="bak_2871_events", src="events", key="event_id",
            ledger=repair.LEDGER, tbl="win_prob_snapshots",
        )
    out["_plan"] = repair._PLAN_SQL
    out["_census"] = repair._CENSUS_SQL
    return out


def test_every_statement_parses_as_postgres():
    """A syntax error here is only ever found by an unreadable dyno run."""
    sqlglot = pytest.importorskip("sqlglot")
    rendered = _rendered_statements()
    assert len(rendered) >= 11, f"expected the full statement set, scanned {len(rendered)}"
    for name, sql in rendered.items():
        try:
            parsed = sqlglot.parse(sql, dialect="postgres")
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"{name} is not valid Postgres: {exc}\n{sql}")
        assert parsed and parsed[0] is not None, f"{name} parsed to nothing"


def test_update_events_only_writes_columns_that_exist():
    """The `updated_at` class of bug, caught generically.

    `events` has `created_at` and no `updated_at`. The first draft of the rename
    wrote `SET away_team_name = :clean, updated_at = NOW()`, which would have
    failed on every Branch B fixture — 4,015 of them — on a dyno whose output
    nobody can read.
    """
    from app.models.models import Event

    real = {c.name for c in Event.__table__.columns}
    assert "created_at" in real and "updated_at" not in real, (
        "the events schema changed; re-derive this guard rather than relaxing it"
    )

    targets = [s for s in _rendered_statements().values()
               if re.match(r"\s*UPDATE\s+events\b", s, re.I)]
    assert targets, "scanned no `UPDATE events` statement — the scan is broken, not clean"
    for sql in targets:
        assigned = set(re.findall(r"(\w+)\s*=", sql.split("WHERE")[0].split("SET", 1)[1]))
        unknown = assigned - real
        assert not unknown, f"UPDATE events writes non-existent column(s) {unknown}: {sql}"


def test_the_repair_writes_exactly_two_events_columns_and_no_others():
    """`away_team_name` (the rename) and `win_probability_sources` (the blend
    clear, CERT-880) — nothing else.

    `home_team_name` is polluted 0 times out of 12,746, because extract_matchup
    splits on " vs. " so the suffix can only ride on team_b; widening the write
    to it is always a mistake. And measured on the 4,024 Branch B survivors, no
    other probability column is populated at all — `opening_home_probability`,
    `closing_home_probability`, `espn_win_prob_home`, `home_score` and
    `box_score_data` are 0 of 4,024 — so these two columns are the whole
    exposure.
    """
    assigned = set()
    for sql in _rendered_statements().values():
        if re.match(r"\s*UPDATE\s+events\b", sql, re.I):
            assigned |= set(re.findall(
                r"(\w+)\s*=", sql.split("WHERE")[0].split("SET", 1)[1]))
    assert assigned == {"away_team_name", "win_probability_sources"}


def test_the_blend_clear_is_scoped_to_the_survivor_row():
    """A `WHERE` that lost its `:survivor` would blank the blend on every event
    in the database. It is keyed by primary key and nothing else."""
    sql = repair.SQL["clear_blend"]
    assert ":survivor" in sql
    where = sql.split("WHERE", 1)[1]
    assert "id = :survivor" in where
    assert ":doomed" not in sql and ":members" not in sql


# ---------------------------------------------------------------------------
# child dispositions are not interchangeable
# ---------------------------------------------------------------------------

def test_anchors_and_win_prob_curves_are_deleted_never_repointed():
    """Re-pointing either one is worse than leaving the phantom.

    A win-prob curve is event-level with no `market_id`, so moving it injects a
    corners-derived probability into the real match's chart (gotcha #46, and
    against "the blend is the product"). An anchor's uniqueness is
    `(source, source_id, id_kind)` with `event_id` NOT in it, so a wrong
    re-point is silently accepted forever and no constraint catches it.
    """
    assert "win_prob_snapshots" in repair.CHILD_DELETE_TABLES
    assert "event_provider_anchors" in repair.CHILD_DELETE_TABLES
    assert "line_movement_analyses" in repair.CHILD_DELETE_TABLES
    assert set(repair.CHILD_DELETE_TABLES) & set(repair.CHILD_REPOINT_TABLES) == set()
    assert repair.CHILD_REPOINT_TABLES == ("futures_markets",)

    repoint_sql = repair.SQL["repoint"] + repair.SQL["ledger_insert"]
    for never_moved in ("win_prob_snapshots", "event_provider_anchors",
                        "line_movement_analyses"):
        assert never_moved not in repoint_sql


def test_child_deletes_cover_every_member_including_the_branch_b_survivor():
    """A survivor renamed correctly but still carrying a corners curve looks
    legitimate, which is strictly worse than the phantom it replaced."""
    assert ":members" in repair.SQL["child_delete"]
    assert ":doomed" not in repair.SQL["child_delete"]


# ---------------------------------------------------------------------------
# the plan: grouping, branches, survivors
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


def _row(id, home, away, clean, real=None, status="closed", day="2026-08-30"):
    d = dt.date.fromisoformat(day)
    return {
        "id": id, "status": status, "home_team_name": home,
        "away_team_name": away, "clean_away": clean,
        "commence_time": dt.datetime.combine(d, dt.time(12, 0)),
        "d": d, "real_event_id": real,
    }


class _FakeSession:
    """Serves `_PLAN_SQL` rows first, then `_ALIAS_SQL` rows."""

    def __init__(self, rows, alias=()):
        self.rows, self.alias, self.n = rows, list(alias), 0

    async def execute(self, *_a, **_kw):
        self.n += 1
        return _FakeResult(self.rows if self.n == 1 else self.alias)


def _plan(rows, alias=(), include_live=False):
    actionable, live, deferred, n = asyncio.run(
        repair.build_plan(_FakeSession(rows, alias), include_live=include_live))
    return actionable, live, deferred, n


# The Aug 30 group from the #2871 BEFORE screenshot: one Swiss fixture printed
# five times, no real counterpart. Textbook Branch B.
THUN = [
    _row(1, "FC Thun", "Lausanne-Sport - Total Corners", "Lausanne-Sport"),
    _row(2, "FC Thun", "Lausanne-Sport - Exact Score", "Lausanne-Sport"),
    _row(3, "FC Thun", "Lausanne-Sport - First Team to Score", "Lausanne-Sport"),
    _row(4, "FC Thun", "Lausanne-Sport - Halftime Result", "Lausanne-Sport"),
    _row(5, "FC Thun", "Lausanne-Sport - Second Half Result", "Lausanne-Sport"),
]


def test_five_rows_for_one_swiss_fixture_collapse_to_one():
    actionable, live, deferred, n = _plan(THUN)
    assert n == 5 and live == []
    assert len(actionable) == 1
    g = actionable[0]
    assert g.branch == "B"
    assert g.survivor_id == 1, "the oldest row survives"
    assert g.doomed_ids == [2, 3, 4, 5]


def test_branch_b_survivor_is_never_in_the_delete_list():
    """The data loss the two-branch design exists to prevent: for 68% of these
    rows the phantom is the ONLY record of the fixture."""
    actionable, _, _, _ = _plan(THUN)
    for g in actionable:
        assert g.survivor_id not in g.doomed_ids


def test_branch_a_deletes_every_member_and_keeps_the_real_event():
    rows = [
        _row(11, "Como 1907", "US Lecce - Exact Score", "US Lecce", real=900),
        _row(12, "Como 1907", "US Lecce - Total Corners", "US Lecce", real=900),
    ]
    g = _plan(rows)[0][0]
    assert g.branch == "A"
    assert g.survivor_id == 900, "the survivor is the REAL event, not a bogus row"
    assert sorted(g.doomed_ids) == [11, 12], "every bogus member goes"
    assert 900 not in g.doomed_ids


def test_every_member_is_either_the_survivor_or_deleted():
    """No row may be silently left behind still carrying a phantom name."""
    rows = THUN + [
        _row(11, "Como 1907", "US Lecce - Exact Score", "US Lecce", real=900),
        _row(12, "Como 1907", "US Lecce - Total Corners", "US Lecce", real=900),
    ]
    for g in _plan(rows)[0]:
        accounted = set(g.doomed_ids) | ({g.survivor_id} & set(g.member_ids))
        assert accounted == set(g.member_ids)


def test_a_group_never_splits_across_branches():
    """`bool_or`: if ANY member found the real fixture the whole group is
    Branch A. Splitting one fixture across branches would rename a phantom into
    a twin of the real event — Alex's bar."""
    rows = [
        _row(21, "Real", "Away - Exact Score", "Away", real=None),
        _row(22, "Real", "Away - Total Corners", "Away", real=777),
    ]
    g = _plan(rows)[0][0]
    assert g.branch == "A" and g.survivor_id == 777
    assert sorted(g.doomed_ids) == [21, 22]


def test_different_dates_are_different_fixtures():
    """The group key includes the date precisely so the real Sep 5 Thun fixture
    is not merged into the bogus Aug 30 group."""
    rows = THUN + [
        _row(6, "FC Thun", "Lausanne-Sport - Exact Score", "Lausanne-Sport",
             day="2026-09-05"),
    ]
    actionable, _, _, _ = _plan(rows)
    assert len(actionable) == 2
    assert {g.date for g in actionable} == {
        dt.date(2026, 8, 30), dt.date(2026, 9, 5)}


def test_live_fixtures_are_deferred_by_default_and_opt_in_with_a_flag():
    rows = THUN + [
        _row(31, "FK Zemun", "FK Vojvodina - Exact Score", "FK Vojvodina",
             status="live", day="2026-09-04"),
    ]
    actionable, live, _, _ = _plan(rows)
    assert len(live) == 1 and live[0].home == "FK Zemun"
    assert all(not g.has_live for g in actionable), "a live fixture was swept in"

    actionable_incl, live_incl, _, _ = _plan(rows, include_live=True)
    assert len(actionable_incl) == 2 and len(live_incl) == 1


def test_plan_refuses_when_postgres_and_python_disagree_about_the_predicate():
    """A red arm: Postgres returning a name Python calls clean means the two
    regexes have drifted, and the repair would operate on a set nobody sized."""
    rows = [_row(41, "Mets", "Dodgers - Game 4", "Dodgers - Game 4")]
    with pytest.raises(RuntimeError, match="predicate disagreement"):
        _plan(rows)


def test_series_game_numbers_are_not_in_the_population():
    """`- Game 4` designates a distinct real game in a series. Sweeping it in
    would merge Games 1-5 into one event — the opposite of this repair."""
    assert not repair.is_derivative_market_name("Mets vs. Dodgers - Game 4")
    assert not repair.is_derivative_market_name("A vs. B - More Markets")


# ---------------------------------------------------------------------------
# D51: the backup gate
# ---------------------------------------------------------------------------

def test_apply_gate_rejects_an_empty_reconciliation():
    """`all()` over an empty mapping is True. Without the emptiness test a
    reconciliation that inspected nothing reads as a clean pass and `--apply`
    proceeds with no undo — gotcha #53 in its most expensive form."""
    assert repair.backup_is_exact({}) is False


def test_apply_gate_rejects_a_missing_or_unbacked_table():
    assert repair.backup_is_exact({"events": 0, "win_prob_snapshots": 3}) is False
    assert repair.backup_is_exact({"events": 0, "win_prob_snapshots": None}) is False
    assert repair.backup_is_exact({"events": 0, "win_prob_snapshots": 0}) is True


def test_backup_covers_every_table_the_repair_writes():
    """A table written but not backed up has no undo, which fails D51."""
    written = {"events", *repair.CHILD_DELETE_TABLES, *repair.CHILD_REPOINT_TABLES}
    backed_up = {"events", *restore.CHILD_TABLES, "futures_markets"}
    assert written == backed_up, (
        f"repair writes {written - backed_up} with no restore path"
    )


def test_restore_moves_a_market_back_only_if_it_is_still_where_the_repair_put_it():
    """An undo that stomps a later, unrelated matcher decision is not an undo."""
    src = (_SCRIPTS / "restore_2871_phantom_derivative_events.py").read_text()
    stmt = src.split("UPDATE futures_markets f SET event_id = r.old_event_id", 1)
    assert len(stmt) == 2, "restore no longer moves markets back — re-derive this guard"
    assert "f.event_id = r.new_event_id" in stmt[1].split('"""')[0]


def test_restore_puts_events_back_before_their_children():
    """`win_prob_snapshots`, `event_provider_anchors` and
    `line_movement_analyses` all carry an FK to `events`; inserting a child
    first fails on the constraint."""
    src = (_SCRIPTS / "restore_2871_phantom_derivative_events.py").read_text()
    body = src.split('async def run(', 1)[1]
    ev = body.index("INSERT INTO events")
    # The children are restored by one loop over CHILD_TABLES; it must come
    # after the parents are back.
    children = body.index("for t in CHILD_TABLES:")
    assert ev < children, "children are restored before their parent events"
    # ...and the markets move back last, once every event they point at exists.
    assert children < body.index("UPDATE futures_markets f SET event_id")


# ---------------------------------------------------------------------------
# CERT-880's two required tests
# ---------------------------------------------------------------------------

def _alias(home, clean_away, day, n3, n7, alias_id):
    return {"home": home, "clean_away": clean_away, "d": dt.date.fromisoformat(day),
            "n3": n3, "n7": n7, "alias_id": alias_id}


def test_cert880_the_fc_thun_date_and_alias_case_leaves_one_real_fixture():
    """CERT-880 required test #1.

    Production, verified: the five `FC Thun / Lausanne-Sport` phantoms are
    stamped Aug 30; the real fixture is `Thun / Lausanne-Sport` (id 15297290) on
    Sep 2 — **2.29 days** away and under a variant home name, so the strict
    Branch A test (exact home, ±2 days) does not reach it. Before the alias arm
    this group renamed itself into a clean-looking Aug 30 `FC Thun /
    Lausanne-Sport` sitting beside the real Sep 2 fixture: two rows for one
    game, and the fake now looks legitimate.

    With the alias arm there is exactly ONE candidate, so the group resolves
    onto the real event and every phantom is deleted. One real fixture, nothing
    renamed, nothing invented.
    """
    alias = [_alias("FC Thun", "Lausanne-Sport", "2026-08-30",
                    n3=1, n7=1, alias_id=15297290)]
    actionable, _, deferred, _ = _plan(THUN, alias=alias)

    assert deferred == []
    assert len(actionable) == 1
    g = actionable[0]
    assert g.branch == "A'", "the alias arm did not fire — Thun renamed into a fake"
    assert g.survivor_id == 15297290, "survivor must be the REAL Sep 2 fixture"
    assert sorted(g.doomed_ids) == [1, 2, 3, 4, 5], "every phantom must go"
    assert 15297290 not in g.doomed_ids


def test_cert880_two_candidates_defer_rather_than_guess():
    """The uniqueness guard. Clubs do meet twice in a week (cup + league), and
    picking one of two candidates would merge two distinct fixtures — the
    data-destroying merge this repair exists to avoid."""
    alias = [_alias("FC Thun", "Lausanne-Sport", "2026-08-30",
                    n3=2, n7=2, alias_id=15297290)]
    actionable, _, deferred, _ = _plan(THUN, alias=alias)
    assert actionable == []
    assert len(deferred) == 1 and deferred[0].branch == "DEFER"


def test_cert880_a_plausible_but_unresolvable_neighbour_defers_not_renames():
    """A candidate 3-7 days out is too far to resolve and too close to ignore.
    Renaming would put a clean-looking fake beside the real fixture; the group
    is left obviously broken instead, and reported."""
    alias = [_alias("FC Thun", "Lausanne-Sport", "2026-08-30",
                    n3=0, n7=1, alias_id=None)]
    actionable, _, deferred, _ = _plan(THUN, alias=alias)
    assert actionable == []
    assert deferred[0].branch == "DEFER"

    # ...and if one is handed to apply_group anyway, it issues NO statement.
    # The classification and the write have to agree, or a caller that skips
    # the `actionable` filter silently renames the group after all.
    class _Recorder:
        def __init__(self):
            self.stmts = []

        async def execute(self, stmt, *_a, **_kw):
            self.stmts.append(str(stmt))
            raise AssertionError("apply_group wrote for a DEFER fixture")

        async def commit(self):
            raise AssertionError("apply_group committed for a DEFER fixture")

    rec = _Recorder()
    counts = asyncio.run(repair.apply_group(rec, deferred[0]))
    assert rec.stmts == []
    assert all(v == 0 for v in counts.values())


def test_cert880_no_neighbour_at_all_still_renames():
    """The control arm. 3,552 groups have no candidate within ±7 days under any
    home-name variant, so renaming them cannot manufacture a fake beside
    anything — that is the whole Branch B population and it must still work."""
    actionable, _, deferred, _ = _plan(THUN, alias=[
        _alias("FC Thun", "Lausanne-Sport", "2026-08-30", n3=0, n7=0, alias_id=None)])
    assert deferred == []
    assert len(actionable) == 1 and actionable[0].branch == "B"
    assert actionable[0].survivor_id == 1


def test_cert880_branch_b_apply_clears_the_hero_and_the_undo_restores_it_exactly():
    """CERT-880 required test #2, executed rather than asserted about.

    Runs the SHIPPED statement text — `SQL["rename"]`, `SQL["clear_blend"]` and
    the restore's `RESTORE_EVENT_COLUMNS_SQL` — against a seeded row, and feeds
    the before/after values through the REAL
    `compute_aggregate_probability()`, which is what search emits as
    `hero_probability`.

    Seed is CERT-880's: `{"polymarket": 0.9995}`.

    STATUS MATTERS, and the control arm is what found it. `polymarket` is in
    `_EXCLUDE_WHEN_COMPLETED`, so on a `closed` event the blend never reaches
    the hero at all — the first version of this test seeded `status="closed"`
    and got `None` BEFORE the repair, which would have made the whole arm
    vacuous. Measured on the 4,025 Branch B survivors: 1,278 carry a blend,
    of which **1,213 are `closed`** (hidden by that gate today) and **65 are
    `suspended`** (rendered). The repair clears all of them: leaving
    corners-derived data on a fixture row and relying on a status gate to hide
    it is protection by accident, and a status flip re-exposes it.
    """
    import json
    import sqlite3

    from app.utils.aggregation import compute_aggregate_probability

    class _Ev:
        """Whatever `compute_aggregate_probability` reads off an event row."""
        def __init__(self, wps, status="suspended"):
            self.win_probability_sources = wps
            self.espn_win_prob_home = None
            self.opening_home_probability = None
            self.status = status

    seed = {"polymarket": 0.9995}

    # CONTROL: the seed really does produce a hero, so "no hero" after the
    # apply is the clear doing work and not an inert fixture.
    assert compute_aggregate_probability(_Ev(seed)) is not None, (
        "the seed produces no hero even before the repair — the arm is vacuous"
    )
    # ...and the production shape, which is nested rather than flat. Event
    # 15298202 holds exactly this, and it is the "Corners 54%" on the screenshot.
    nested = {"polymarket": {"value": 0.445,
                             "updated_at": "2026-08-30T23:46:04.344770+00:00"}}
    assert compute_aggregate_probability(_Ev(nested)) is not None

    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE events (id INTEGER PRIMARY KEY, away_team_name TEXT,
                             win_probability_sources TEXT);
        CREATE TABLE bak_2871_events (id INTEGER PRIMARY KEY, away_team_name TEXT,
                                      win_probability_sources TEXT);
    """)
    row = (7, "Lausanne-Sport - Total Corners", json.dumps(seed))
    db.execute("INSERT INTO events VALUES (?,?,?)", row)
    db.execute("INSERT INTO bak_2871_events VALUES (?,?,?)", row)  # D51 backup

    # ---- apply: the two shipped statements, verbatim, in the order
    #      apply_group runs them. SQLite takes `:name` binds natively, so the
    #      text under test is byte-identical to the text that runs on production.
    params = {"clean": "Lausanne-Sport", "survivor": 7}
    for key in ("rename", "clear_blend"):
        db.execute(repair.SQL[key], params)

    after = db.execute(
        "SELECT away_team_name, win_probability_sources FROM events WHERE id=7"
    ).fetchone()
    assert after[0] == "Lausanne-Sport", "the rename did not apply"
    assert after[1] is None, "the blend survived the apply — the hero is still rendered"
    assert compute_aggregate_probability(_Ev(after[1])) is None, "NO HERO after apply"

    # ---- undo: the shipped restore statement, transpiled rather than retyped.
    #      SQLite needs `UPDATE events AS e` where Postgres allows
    #      `UPDATE events e`; sqlglot renders the difference so the semantics
    #      under test are still the shipped statement's and not a paraphrase.
    sqlglot = pytest.importorskip("sqlglot")
    undo = sqlglot.transpile(
        restore.RESTORE_EVENT_COLUMNS_SQL.format(bak="bak_2871_events"),
        read="postgres", write="sqlite")[0]
    db.execute(undo)
    back = db.execute(
        "SELECT away_team_name, win_probability_sources FROM events WHERE id=7"
    ).fetchone()
    assert back[0] == "Lausanne-Sport - Total Corners"
    assert json.loads(back[1]) == seed, "the blend did not round-trip exactly"
    assert compute_aggregate_probability(_Ev(json.loads(back[1]))) is not None
    db.close()


class _StmtRecorder:
    """Captures the statements `apply_group` actually issues."""

    def __init__(self):
        self.sql = []

    async def execute(self, stmt, params=None, *_a, **_kw):
        self.sql.append(" ".join(str(stmt).split()))

        class _R:
            rowcount = 1
        return _R()

    async def commit(self):
        pass


def _apply_sql_for(group):
    rec = _StmtRecorder()
    counts = asyncio.run(repair.apply_group(rec, group))
    return rec.sql, counts


def test_apply_group_actually_issues_the_blend_clear_for_branch_b():
    """CERT-880 required test #2, driven through the REAL `apply_group`.

    The statement-level round-trip above proves `clear_blend` does the right
    thing when it runs; this proves `apply_group` runs it. Deleting the call
    leaves that round-trip green — it did, which is how this arm got written.
    """
    g = _plan(THUN, alias=[_alias("FC Thun", "Lausanne-Sport", "2026-08-30",
                                  n3=0, n7=0, alias_id=None)])[0][0]
    assert g.branch == "B"

    sql, counts = _apply_sql_for(g)
    cleared = [s for s in sql if "win_probability_sources = NULL" in s]
    assert len(cleared) == 1, (
        f"apply_group did not clear the blend for a Branch B survivor "
        f"— the renamed fixture keeps its corners-derived hero. Issued: {sql}"
    )
    assert counts["blend_cleared"] == 1

    # ...and the rename must be in the same transaction as the clear: one
    # commit, both writes. A survivor renamed but not cleared is the exact
    # "worse because it now looks legitimate" state CERT-880 blocked on.
    renamed = [s for s in sql if "away_team_name = :clean" in s]
    assert len(renamed) == 1 and counts["renamed"] == 1


def test_apply_group_never_clears_a_blend_on_a_real_event():
    """Branch A/A' survivors are REAL events with a legitimate blend of their
    own. Clearing it would delete good data from a fixture this repair is only
    supposed to be merging phantoms into."""
    rows = [_row(11, "Como 1907", "US Lecce - Exact Score", "US Lecce", real=900)]
    g = _plan(rows)[0][0]
    assert g.branch == "A" and g.survivor_id == 900

    sql, counts = _apply_sql_for(g)
    assert not [s for s in sql if "win_probability_sources = NULL" in s]
    assert counts["blend_cleared"] == 0 and counts["renamed"] == 0


def test_the_undo_restores_a_blend_even_when_the_name_is_already_back():
    """`IS DISTINCT FROM`, not `<>`, and this is the case that needs it.

    The repair sets `win_probability_sources` to NULL. `NULL <> '{...}'` is
    NULL, not true — so a `<>` predicate matches nothing and the blend is
    silently never restored. It is invisible in the normal path because the name
    changed too and the `OR` carries the row.

    This is the partial state: a re-run, or a restore after a restore, where the
    name is already back and ONLY the blend is still missing. A `<>` undo leaves
    that row blend-less forever, which is the one failure an undo cannot afford.
    """
    import json
    import sqlite3

    sqlglot = pytest.importorskip("sqlglot")
    seed = {"polymarket": {"value": 0.445}}

    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE events (id INTEGER PRIMARY KEY, away_team_name TEXT,
                             win_probability_sources TEXT);
        CREATE TABLE bak_2871_events (id INTEGER PRIMARY KEY, away_team_name TEXT,
                                      win_probability_sources TEXT);
    """)
    # name ALREADY matches the backup; only the blend is missing.
    db.execute("INSERT INTO events VALUES (?,?,?)", (7, "Lausanne-Sport", None))
    db.execute("INSERT INTO bak_2871_events VALUES (?,?,?)",
               (7, "Lausanne-Sport", json.dumps(seed)))

    db.execute(sqlglot.transpile(
        restore.RESTORE_EVENT_COLUMNS_SQL.format(bak="bak_2871_events"),
        read="postgres", write="sqlite")[0])

    got = db.execute(
        "SELECT win_probability_sources FROM events WHERE id=7").fetchone()[0]
    assert got is not None, (
        "the undo matched no row — `<>` against a NULL is NULL, not true, so "
        "the blend was silently never restored"
    )
    assert json.loads(got) == seed
    db.close()
