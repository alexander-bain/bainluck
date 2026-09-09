"""Guards for the #4242 part (b) historical cleanup.

This repair deletes ~1,843 `events` rows on production under D51 and re-dates
65 more. It runs on a one-off dyno whose stdout cannot be read (gotcha #48), so
a mistake in it is invisible until someone notices the damage.

THE ONE CERT-2347 NAMED is
:func:`test_the_duplicate_shape_collapses_to_one_historical_card` — "seed the
duplicate shape, run repair, assert one canonical fixture and preserved
dependencies". It runs the SHIPPED statements through the SHIPPED
``apply_matchup`` against a seeded database, so a change to either the SQL or
the order it is issued in reds it.

Everything else here exists because the corresponding mistake is cheap to make
and expensive to find:

* folding by `(home, away)` and merging two legs of one tie into a single row
* deleting a row that has since acquired odds or scores, because the census that
  said it had none was taken a week earlier
* re-pointing a phantom's curve or provider anchor instead of deleting it, which
  is worse than the phantom because the result looks legitimate
* an `UPDATE events` naming a column `events` does not have (it has no
  `updated_at`) — written and caught in #2871, on 4,015 rows
* deleting the NO ACTION child after its parent, which the FK refuses
* the D51 backup gate passing vacuously on an empty reconciliation
* a backup that omits the CASCADE children, which nothing but the backup can
  find again once the parent is gone
"""
import asyncio
import datetime as dt
import importlib.util
import pathlib
import re
import sqlite3

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load("repair_4242_polymarket_phantom_events")
restore = _load("restore_4242_polymarket_phantom_events")


# ---------------------------------------------------------------------------
# seeding helpers — one place that knows the plan row's shape
# ---------------------------------------------------------------------------

def _row(rid, *, status="closed", markets=0, dates=0, nulls=0,
         market_time=None, other=0):
    return {
        "id": rid,
        "status": status,
        "n_markets": markets,
        "n_market_dates": dates,
        "n_null_market_times": nulls,
        "market_time": market_time,
        "n_other_substantive": other,
    }


def _orphan(rid, status="closed"):
    return _row(rid, status=status)


def _holder(rid, market_time, status="closed", markets=1):
    return _row(rid, status=status, markets=markets, dates=1,
                market_time=market_time)


def _matchup(home, away, rows):
    m = repair.Matchup(home, away)
    m.rows.extend(rows)
    return m


# The rewrite is deliberately narrow and deliberately counted. `= ANY(CAST(:x AS
# int[]))` is Postgres-only, so the sqlite arm has to render it — but a rewrite
# that silently matched nothing would leave the test executing a paraphrase of
# the repair rather than the repair. Every test that uses this asserts the
# rewrite count, so the idiom disappearing from the shipped SQL reds here.
_ARRAY_IDIOM = re.compile(r"= ANY\(CAST\(:(\w+) AS int\[\]\)\)")


class _SqliteSession:
    """Runs the SHIPPED statement text against sqlite. One narrow rewrite."""

    def __init__(self, db):
        self.db = db
        self.sql = []
        self.rewrites = 0

    async def execute(self, stmt, params=None, *_a, **_kw):
        sql = str(stmt)
        params = dict(params or {})

        def _render(m):
            self.rewrites += 1
            values = params.pop(m.group(1))
            return "IN (%s)" % ",".join(str(int(v)) for v in values)

        sql = _ARRAY_IDIOM.sub(_render, sql)
        self.sql.append(" ".join(sql.split()))
        cur = self.db.execute(sql, params)
        return type("R", (), {"rowcount": cur.rowcount})

    async def commit(self):
        self.db.commit()

    async def rollback(self):
        self.db.rollback()


_SCHEMA = """
CREATE TABLE events (id INTEGER PRIMARY KEY, home_team_name TEXT,
                     away_team_name TEXT, status TEXT, commence_time TEXT);
CREATE TABLE futures_markets (id INTEGER PRIMARY KEY, event_id INT,
                              commence_time TEXT);
CREATE TABLE line_movement_analyses (id INTEGER PRIMARY KEY, event_id INT);
CREATE TABLE win_prob_snapshots (id INTEGER PRIMARY KEY, event_id INT,
                                 source TEXT);
CREATE TABLE bak_4242_events (id INTEGER PRIMARY KEY, home_team_name TEXT,
                              away_team_name TEXT, status TEXT,
                              commence_time TEXT);
"""

# The production shape, from the #4242 filing: 61 rows for one October 2024
# fight, one of them flagged live, only the newest holding the market. Trimmed
# to 6 so the assertions stay readable; the count is not what is under test.
_FIGHT_DATE = "2024-10-22T02:00:00+00:00"
_FABRICATED = "2026-09-09T01:00:00+00:00"


def _seed_whittaker(db):
    """Three orphans, one live holder, the market on the holder."""
    for rid in (101, 102, 103):
        db.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                   (rid, "Whittaker", "Chimaev", "closed", _FABRICATED))
        db.execute("INSERT INTO line_movement_analyses VALUES (?,?)", (rid * 10, rid))
        db.execute("INSERT INTO win_prob_snapshots VALUES (?,?,?)",
                   (rid * 10, rid, "polymarket"))
    db.execute("INSERT INTO events VALUES (?,?,?,?,?)",
               (104, "Whittaker", "Chimaev", "live", _FABRICATED))
    db.execute("INSERT INTO futures_markets VALUES (?,?,?)", (9001, 104, _FIGHT_DATE))
    db.commit()
    return _matchup("Whittaker", "Chimaev", [
        _orphan(101), _orphan(102), _orphan(103),
        _holder(104, _FIGHT_DATE, status="live"),
    ])


# ---------------------------------------------------------------------------
# THE TEST CERT-2347 NAMED
# ---------------------------------------------------------------------------

def test_the_duplicate_shape_collapses_to_one_historical_card():
    """CERT-2347's named catching proof, executed rather than asserted about.

    Seeds the duplicate shape from the #4242 screenshot — a matchup wearing four
    rows for one October 2024 fight, one of them flagged `live`, the market on
    the newest — runs the SHIPPED `apply_matchup`, and asserts the state it
    leaves behind:

      * ONE canonical fixture, not four;
      * dated 22 October 2024, the date the venue itself reports, not the
        fabricated `now` the bug stamped;
      * not `live` — and `suspended`, never `closed`, because nothing here has
        standing to say who won (live/048, CERT-752);
      * **the dependency preserved**: the market is still attached to it, so the
        fight has not been silently disconnected from the thing that knows about
        it.

    What the READER then sees is one step further out and is NOT asserted here,
    because it is a property of the route rather than of the repair:
    `search_events` scopes on `commence_time >= now - days_back` (default 30,
    max 365), so a survivor correctly dated 2024-10-22 leaves the search page
    altogether and `?q=Whittaker` returns the real 3 Oct fight and nothing else.
    Verified against production, not inferred. Its event page is unaffected.
    """
    db = sqlite3.connect(":memory:")
    db.executescript(_SCHEMA)
    m = _seed_whittaker(db)

    # CONTROL: the shape really is broken before the repair, so "one card"
    # afterwards is the repair doing work and not an inert fixture.
    assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 4
    assert db.execute(
        "SELECT count(*) FROM events WHERE status='live'").fetchone()[0] == 1

    session = _SqliteSession(db)
    counts = asyncio.run(repair.apply_matchup(session, m))

    assert session.rewrites == 2, (
        "the array idiom was not found in the shipped deletes — this arm "
        "executed a paraphrase, not the repair"
    )
    assert counts == {"deleted_children": 3, "deleted_events": 3, "redated": 1}

    rows = db.execute(
        "SELECT id, status, commence_time FROM events").fetchall()
    assert rows == [(104, "suspended", _FIGHT_DATE)], (
        f"expected one historical card dated {_FIGHT_DATE} and not live, got {rows}"
    )

    # the dependency, preserved — the market never moved, so it cannot have
    # landed on the wrong fixture
    assert db.execute(
        "SELECT event_id FROM futures_markets WHERE id=9001").fetchone() == (104,)

    # the orphans' derived children went with them; the NO ACTION one by
    # statement, the CASCADE one by the database (not modelled in sqlite, which
    # is why the backup covers it — see the backup guard below)
    assert db.execute(
        "SELECT count(*) FROM line_movement_analyses").fetchone()[0] == 0
    db.close()


def test_the_undo_puts_the_deleted_rows_and_the_date_back():
    """D51's other half: the restore statement, run rather than read.

    An undo that silently restores nothing is worse than no undo at all, because
    it reports success. The `IS DISTINCT FROM` in the shipped statement is what
    makes the status arm fire; a `<>` would evaluate to NULL against a NULL and
    skip the row.
    """
    db = sqlite3.connect(":memory:")
    db.executescript(_SCHEMA)
    m = _seed_whittaker(db)
    # the D51 backup, taken before the apply exactly as the script requires
    db.execute("INSERT INTO bak_4242_events SELECT * FROM events")
    db.commit()

    asyncio.run(repair.apply_matchup(_SqliteSession(db), m))
    assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 1

    # 1. the deleted rows, with their original ids
    cols = "id, home_team_name, away_team_name, status, commence_time"
    db.execute(f"""
        INSERT INTO events ({cols})
        SELECT {cols} FROM bak_4242_events b
        WHERE NOT EXISTS (SELECT 1 FROM events e WHERE e.id = b.id)
    """)
    # 2. the two columns the repair wrote, via the SHIPPED statement —
    #    transpiled rather than retyped. SQLite needs `UPDATE events AS e` where
    #    Postgres allows `UPDATE events e`; sqlglot renders the difference so
    #    the semantics under test are still the shipped statement's and not a
    #    paraphrase of it.
    sqlglot = pytest.importorskip("sqlglot")
    db.execute(sqlglot.transpile(
        restore.RESTORE_EVENT_COLUMNS_SQL.format(bak="bak_4242_events"),
        read="postgres", write="sqlite")[0])
    db.commit()

    back = db.execute(
        "SELECT id, status, commence_time FROM events ORDER BY id").fetchall()
    assert back == [
        (101, "closed", _FABRICATED),
        (102, "closed", _FABRICATED),
        (103, "closed", _FABRICATED),
        (104, "live", _FABRICATED),
    ], f"the undo did not round-trip: {back}"
    db.close()


# ---------------------------------------------------------------------------
# the two ways this repair could destroy something
# ---------------------------------------------------------------------------

def test_two_legs_of_one_tie_keep_two_survivors():
    """The reason the survivor is never chosen by name.

    `FCSB / PAOK` on production carries markets dated 2024-10-02 AND 2025-02-11
    — the two legs of one Europa League tie under a single `(home, away)` pair.
    A fold by name collapses them into one row, which is a cross-event data
    merge (gotcha #46) wearing a cleanup's clothes.
    """
    leg1, leg2 = "2024-10-02T18:45:00+00:00", "2025-02-11T20:00:00+00:00"
    m = _matchup("FCSB", "PAOK", [
        _orphan(201), _orphan(202),
        _holder(203, leg1), _holder(204, leg2),
    ])
    assert sorted(m.survivor_ids) == [203, 204], (
        "a two-leg tie kept fewer than two survivors — one real fixture was "
        "merged into the other"
    )
    assert m.doomed_ids == [201, 202]

    dates = {r["market_time"] for r in m.holders}
    assert dates == {leg1, leg2}, "the survivors do not carry their own dates"


def test_a_row_that_has_acquired_real_data_is_never_deleted():
    """The refusal that makes the delete lossless, rather than the census.

    `odds_snapshots`, `score_snapshots` and the rest measured 0 across the whole
    population on 2026-09-09. A run next week runs against a different database,
    so the emptiness is enforced per row rather than trusted: anything with a
    substantive child defers and is reported.
    """
    for table_count in (1, 5):
        m = _matchup("Texas", "Oklahoma", [
            _orphan(301),
            _row(302, other=table_count),
        ])
        assert m.doomed_ids == [301], (
            f"a row carrying {table_count} substantive child row(s) was queued "
            f"for deletion — that is odds or scores history destroyed"
        )
        assert [r["id"] for r in m.deferred] == [302]
        assert m.survivor_ids == [], "a deferred row is not a survivor either"


def test_ambiguous_market_dates_defer_rather_than_pick_a_winner():
    """Two dates on ONE row is two fixtures already merged onto it.

    Re-dating it would pick one of two real games. `Yankees / Guardians - Game
    1` carries four. Deferred, reported, and filed under #2693 (D35).
    """
    two_dates = _row(401, markets=8, dates=4, market_time="2024-10-14T00:00:00+00:00")
    a_null = _row(402, markets=2, dates=1, nulls=1,
                  market_time="2024-10-14T00:00:00+00:00")
    no_time = _row(403, markets=2, dates=0, market_time=None)
    for row in (two_dates, a_null, no_time):
        assert repair.classify(row) == "DEFER", row


def test_classify_answers_for_every_row_and_build_plan_refuses_otherwise():
    """A fourth answer must fail the run, not quietly drop rows from the plan.

    `orphans`/`holders`/`deferred` are three independent comprehensions over the
    same predicate, so an unhandled classification silently shrinks the plan.
    `build_plan` re-adds the three and refuses on a mismatch; this proves the
    refusal fires rather than merely existing.
    """
    m = _matchup("A", "B", [_orphan(1), _holder(2, "2024-01-01T00:00:00+00:00"),
                            _row(3, other=1)])
    assert len(m.orphans) + len(m.holders) + len(m.deferred) == len(m.rows)

    original = repair.classify
    try:
        repair.classify = lambda row: "SOMETHING_NEW"
        assert m.orphans == [] and m.holders == [] and m.deferred == []
    finally:
        repair.classify = original


# ---------------------------------------------------------------------------
# the statements themselves
# ---------------------------------------------------------------------------

def test_every_statement_parses_as_postgres():
    """A syntax error in a repair is otherwise found by a dyno nobody can read."""
    sqlglot = pytest.importorskip("sqlglot")
    rendered = [
        repair.SQL["bak_create"].format(bak="bak_4242_events", src="events"),
        repair.SQL["bak_index"].format(bak="bak_4242_events"),
        repair.SQL["bak_copy"].format(bak="bak_4242_events", src="events", key="id"),
        repair.SQL["bak_missing"].format(bak="bak_4242_events", src="events", key="id"),
        repair.SQL["child_delete"].format(tbl="line_movement_analyses"),
        repair.SQL["event_delete"],
        repair.SQL["redate"],
        repair._PLAN_SQL,
        repair._CENSUS_SQL,
        repair._SINGLETON_CENSUS_SQL,
        restore.RESTORE_EVENT_COLUMNS_SQL.format(bak="bak_4242_events"),
    ]
    for sql in rendered:
        sqlglot.parse_one(sql, dialect="postgres")


def test_the_redate_writes_only_columns_events_actually_has():
    """#2871's `updated_at` bug, which failed 4,015 rows on an unreadable dyno.

    Checked against the live model, not against a list in this file.
    """
    from app.models.models import Event

    columns = {c.name for c in Event.__table__.columns}
    written = set(re.findall(r"(?:SET|,)\s+(\w+)\s*=", repair.SQL["redate"]))
    assert written, "no SET clause parsed out of the re-date — retire this guard"
    assert written <= columns, (
        f"the re-date writes {written - columns}, which `events` does not have"
    )
    assert written == {"commence_time", "status"}, (
        f"the repair writes {written} to `events`; it is documented, backed up "
        f"and undone as exactly two columns"
    )


def test_the_repair_writes_no_column_the_undo_does_not_restore():
    """The backup is only an undo if it covers everything the repair wrote."""
    written = set(re.findall(r"(?:SET|,)\s+(\w+)\s*=", repair.SQL["redate"]))
    restored = set(re.findall(r"(?:SET|,)\s+(\w+)\s*=",
                              restore.RESTORE_EVENT_COLUMNS_SQL))
    assert written <= restored, f"the undo cannot put back {written - restored}"


def test_derived_children_are_deleted_never_repointed():
    """A re-pointed anchor is silently accepted forever.

    `event_provider_anchors` is unique on `(source, source_id, id_kind)` —
    `event_id` is NOT in it — so moving one onto another fixture permanently
    asserts a provider id against the wrong game with no constraint to catch it.
    A re-pointed `win_prob_snapshots` row injects a phantom's curve into a real
    match (gotcha #46). Neither may ever be an UPDATE.
    """
    every_statement = "\n".join(repair.SQL.values())
    for table in repair.DERIVED_CHILD_TABLES:
        assert not re.search(
            rf"UPDATE\s+{table}\b", every_statement, re.I
        ), f"{table} is updated somewhere — it may only ever be deleted"
    assert not re.search(r"SET\s+event_id\s*=", every_statement, re.I), (
        "something re-points a child onto a different event; this repair moves "
        "nothing, which is why its undo has no ledger"
    )


def test_the_forensic_tables_are_never_touched():
    """`market_link_changes` / `market_match_receipts` carry an event id with no
    FK ON PURPOSE — models.py is explicit that the forensic has to outlive its
    subject. They are lane1b's under D39. A deleted phantom keeps its receipt.
    """
    every_statement = "\n".join([*repair.SQL.values(), repair._PLAN_SQL,
                                 repair._CENSUS_SQL, repair._SINGLETON_CENSUS_SQL])
    for table in ("market_link_changes", "market_match_receipts"):
        assert table not in every_statement


def test_the_no_action_child_is_deleted_before_its_parent():
    """FK order. `line_movement_analyses` is NO ACTION: the parent delete is
    refused while a row of it survives, and the refusal arrives on a dyno whose
    stdout nobody reads.
    """
    db = sqlite3.connect(":memory:")
    db.executescript(_SCHEMA)
    m = _seed_whittaker(db)
    session = _SqliteSession(db)
    asyncio.run(repair.apply_matchup(session, m))
    db.close()

    child = next(i for i, s in enumerate(session.sql)
                 if "line_movement_analyses" in s)
    parent = next(i for i, s in enumerate(session.sql)
                  if s.startswith("DELETE FROM events"))
    assert child < parent, (
        "the parent delete is issued before its NO ACTION child — the FK "
        "refuses it and the whole matchup rolls back"
    )


def test_a_status_that_is_not_live_keeps_the_word_it_has():
    """This repair fixes a DATE. The only status claim it has standing to make
    is that a 2024 fixture is not currently being played — never that it is
    Final, which is what every client renders `closed` as.
    """
    db = sqlite3.connect(":memory:")
    db.executescript(_SCHEMA)
    for rid, status in ((501, "voided"), (502, "suspended"), (503, "closed")):
        db.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                   (rid, "A", "B", status, _FABRICATED))
    db.commit()

    m = _matchup("A", "B", [_holder(rid, _FIGHT_DATE, status=s)
                            for rid, s in ((501, "voided"), (502, "suspended"),
                                           (503, "closed"))])
    asyncio.run(repair.apply_matchup(_SqliteSession(db), m))

    after = db.execute("SELECT id, status, commence_time FROM events "
                       "ORDER BY id").fetchall()
    assert after == [(501, "voided", _FIGHT_DATE),
                     (502, "suspended", _FIGHT_DATE),
                     (503, "closed", _FIGHT_DATE)], (
        f"a status other than `live` was rewritten: {after}"
    )
    db.close()


def test_suspended_is_the_shipped_constant_not_a_literal():
    """live/048 and CERT-752 settled on `suspended` for "cannot say live, cannot
    say who won". A re-typed literal drifts from it silently.
    """
    from app.utils.event_completion import EVENT_SUSPENDED, SETTLED_STATUSES

    assert repair.EVENT_SUSPENDED is EVENT_SUSPENDED
    assert EVENT_SUSPENDED not in SETTLED_STATUSES, (
        "the disposition this repair writes now reads as Final to every client"
    )


# ---------------------------------------------------------------------------
# D51 mechanics
# ---------------------------------------------------------------------------

def test_apply_gate_rejects_an_empty_reconciliation():
    """`all()` over an empty mapping is True — without the emptiness test a
    reconciliation that inspected NOTHING reads as a clean pass and `--apply`
    proceeds with no undo (gotcha #53).
    """
    assert repair.backup_is_exact({"events": 0, "win_prob_snapshots": 0})
    assert not repair.backup_is_exact({})
    assert not repair.backup_is_exact({"events": 0, "win_prob_snapshots": 3})
    assert not repair.backup_is_exact({"events": None})


def test_backup_covers_every_table_the_repair_removes_rows_from():
    """The CASCADE children are the ones only the backup can find again.

    `win_prob_snapshots` and `event_provider_anchors` are deleted by the
    DATABASE, not by any statement in the repair — so a backup set derived from
    the repair's own SQL would miss them and the undo would restore an event
    with no history. They are covered because they are named in
    `DERIVED_CHILD_TABLES`, which is what `backup()` iterates.
    """
    import inspect

    backed_up = set(("events", *repair.DERIVED_CHILD_TABLES))
    assert set(restore.CHILD_TABLES) | {"events"} == backed_up, (
        "the repair backs up a table the restore does not put back, or vice versa"
    )
    for table in repair.NO_ACTION_DERIVED_TABLES:
        assert table in repair.DERIVED_CHILD_TABLES

    src = inspect.getsource(repair.backup)
    assert "DERIVED_CHILD_TABLES" in src, (
        "backup() no longer iterates the derived tables — the CASCADE rows have "
        "nothing recording that they existed"
    )


def test_restore_puts_events_back_before_their_children():
    """Every child has an FK to `events`; inserting one first is refused."""
    import inspect

    body = inspect.getsource(restore.run)
    events_insert = body.index("INSERT INTO events")
    child_insert = body.index("for t in CHILD_TABLES")
    assert events_insert < child_insert


def test_the_sanity_floor_is_below_the_measured_population():
    """A repair that finds nothing and reports success is the worst outcome.

    Measured 1,914 on 2026-09-09; the floor has to sit under it or the first
    real run refuses itself, and over zero or it never fires.
    """
    assert 0 < repair.MIN_EXPECTED_POPULATION < 1_914


# ---------------------------------------------------------------------------
# the repair and the prevention are talking about the same rows
# ---------------------------------------------------------------------------

def test_every_row_this_repair_touches_is_one_the_prevention_now_refuses():
    """One vocabulary, not two that drift.

    The rows re-dated here are rows the shipped guard would refuse to mint
    today. Checked by running the SHIPPED `auto_create_time_is_invented()` over
    the production market dates that this repair reads off the holders, rather
    than by restating its rule.
    """
    from app.tasks.prediction_market_matching import auto_create_time_is_invented

    now = dt.datetime(2026, 9, 9, tzinfo=dt.timezone.utc)

    class _Market:
        """A Polymarket market: a condition id, which parses to no ticker date."""
        external_id = "0x9f2c4b1e"

        def __init__(self, when):
            self.commence_time = when

    # the three worst matchups in the #4242 filing, by their markets' own dates
    for when in (dt.datetime(2024, 10, 13, tzinfo=dt.timezone.utc),   # Mets/Dodgers
                 dt.datetime(2024, 10, 22, tzinfo=dt.timezone.utc),   # Whittaker
                 dt.datetime(2025, 2, 11, tzinfo=dt.timezone.utc)):   # Galatasaray
        assert auto_create_time_is_invented(_Market(when), now), (
            f"the prevention would still mint a row for a market dated {when} — "
            f"the repair is cleaning up rows the guard does not stop"
        )

    # CONTROL: the predicate is not simply true for everything, so the arm above
    # is a test and not a tautology.
    assert not auto_create_time_is_invented(
        _Market(dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)), now
    )


def test_the_population_predicate_names_the_stamp_and_not_a_tolerance():
    """The 300-second window is the fabricated-`now` stamp, and the population
    is confined to rows with no provider id — a row that has since acquired one
    is by definition no longer the unfindable thing this bug creates.
    """
    assert "commence_time_source = 'polymarket'" in repair._POPULATION
    assert "external_id IS NULL" in repair._POPULATION
    assert "< 300" in repair._POPULATION
    for sql in (repair._PLAN_SQL, repair._CENSUS_SQL, repair._SINGLETON_CENSUS_SQL):
        assert repair._POPULATION.strip() in " ".join(sql.split(" ")) or \
            "commence_time_source = 'polymarket'" in sql, (
            "a query reads a different population than the one the census sized"
        )


def test_the_plan_only_ever_reads_duplicate_groups():
    """Singletons are a different shape and out of scope; the plan must not
    quietly include them.
    """
    assert "HAVING count(*) > 1" in repair._PLAN_SQL
    assert "NOT IN (SELECT h, a FROM grp)" in repair._SINGLETON_CENSUS_SQL
