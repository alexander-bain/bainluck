"""#3026 — the repair that unmakes the events a question minted, and its undo.

The prevention is tested in `test_question_is_not_a_game_3026.py`. This file is
about the CLEANUP: that its population is the shipped predicate's and not a
second regex that can drift, that every delete branch is EARNED rather than
assumed, that the one row shape #2871 protects is held back, that every
statement it runs is valid Postgres, and that the D51 undo can put back the
win-probability series as well as the row that carried it.

Three lessons re-armed rather than assumed:

  * CERT-903 — #2947's pair shipped importing `app.database`, a module that has
    never existed. Every unit test passed against a fake session while the real
    entrypoint died on import. `test_the_entrypoint_resolves_for_real` is the
    only test here that touches the real module.
  * CERT-907 — an untyped bind beside an interval is resolved BY POSTGRES as an
    interval, and sqlglot is perfectly happy with it. This repair does its date
    arithmetic in Python; the test asserts that stays true.
  * gotcha #45 — `(?:` inside `text()` is read as a bind parameter. All three
    patterns cross into SQL, so all three are checked.
"""

import asyncio
import datetime as dt
import importlib.util
import os

import pytest

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_SCRIPTS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repair = _load("repair_3026_question_events")
restore = _load("restore_3026_question_events")


# The real production strings, read 2026-09-04.
EMBED_HOME = "Announcers"
EMBED_AWAY = "Duke vs Virginia"
EMBED_MARKET = "Announcers at Duke vs Virginia"
EMBED_TICKER = "pm_kalshi_KXNCAABMENTION-26FEB28UVADUKE"

QUESTION_HOME = "What will the announcers say during PSG"
QUESTION_AWAY = "Arsenal"

WSOP_HOME = "Will Greg Mueller Finish Top 3"
WSOP_AWAY = "the 2026 WSOP Main Event"

COMMENCE = dt.datetime(2026, 2, 28, 22, 0, tzinfo=dt.timezone.utc)


# ── the population is the shipped predicate's ────────────────────────────────

def test_the_population_predicate_is_the_shipped_fix():
    """Imported, not restated — the repair cannot drift from the guard."""
    from app.utils import prediction_market_matching as fix

    assert repair.question_refusal_reason is fix.question_refusal_reason
    assert repair.name_embeds_a_matchup is fix.name_embeds_a_matchup


def test_the_sql_prefilter_is_only_a_prefilter():
    """Whatever SQL selects, the shipped predicate decides. A row the guard
    would allow must never be planned, however the prefilter matched it."""
    session = _FakeSession([(1, "Paper Rex", "NRG", COMMENCE, None, "closed")])
    assert asyncio.run(repair.build_plan(session)) == []


@pytest.mark.parametrize(
    "attr,source",
    [
        ("EMBED_RE_SQL", "_EMBEDDED_MATCHUP_RE"),
        ("OPENER_RE_SQL", "_QUESTION_OPENER_RE"),
        ("WILL_RE_SQL", "_WILL_CLAUSE_RE"),
    ],
)
def test_no_pattern_reaching_postgres_has_a_bind_eating_group(attr, source):
    """gotcha #45 — `(?:who|what)` inside `text()` is read as a bind `:who`."""
    from app.utils import prediction_market_matching as fix

    pattern = getattr(repair, attr)
    assert "(?:" not in pattern
    assert pattern == getattr(fix, source).pattern.replace("(?:", "(")


def test_the_prefilter_selects_every_shape_the_predicate_refuses():
    """A shape the SQL misses is a row the repair silently never sees."""
    import re

    for home, away in (
        (EMBED_HOME, EMBED_AWAY),
        (QUESTION_HOME, QUESTION_AWAY),
        (WSOP_HOME, WSOP_AWAY),
    ):
        assert repair.question_refusal_reason(home, away)
        matched = any(
            re.search(pattern, name, re.IGNORECASE)
            for pattern in (repair.EMBED_RE_SQL, repair.OPENER_RE_SQL, repair.WILL_RE_SQL)
            for name in (home, away)
        )
        assert matched, f"prefilter misses {home!r} / {away!r}"


# ── reconstruction: deterministic, or refused ────────────────────────────────

@pytest.mark.parametrize(
    "home,away,expected",
    [
        (EMBED_HOME, EMBED_AWAY, ("Duke", "Virginia")),
        (
            "Announcers",
            "Denver vs Golden State Professional Basketball Game",
            ("Denver", "Golden State"),
        ),
        ("Announcers", "UConn vs St. John's", ("UConn", "St. John's")),
        (QUESTION_HOME, QUESTION_AWAY, ("PSG", "Arsenal")),
        (
            "What will the announcers say during Fares Ziam",
            "Tom Nolan UFC Fight",
            ("Fares Ziam", "Tom Nolan"),
        ),
        ("Who will win Bucks", "Heat: Game 2?", ("Bucks", "Heat")),
    ],
)
def test_the_row_reconstructs_the_matchup_it_still_names(home, away, expected):
    assert repair.reconstruct_matchup(home, away) == expected


@pytest.mark.parametrize(
    "home,away,why",
    [
        (WSOP_HOME, WSOP_AWAY, "a poker prop names no matchup"),
        ("Will LAG Make the Grand Finals", "FRAG Midwest", "not a matchup"),
        ("Announcers", "Cutelaba vs Sy", "'Sy' is too short to look up"),
        (
            "Will more or less than 221 total points be scored in Suns",
            "Clippers",
            "an unlisted question opener is not stripped on a guess",
        ),
        ("", "", "empty"),
    ],
)
def test_an_unreconstructible_row_is_refused_not_guessed(home, away, why):
    assert repair.reconstruct_matchup(home, away) is None, why


def test_a_three_way_name_is_not_a_matchup():
    """"A vs B vs C" splits three ways; picking two of them would be a guess."""
    assert repair.reconstruct_matchup("Announcers", "A vs B vs C") is None


# ── provenance: the ticker's date beats an ingestion stamp ───────────────────

def test_the_ticker_carries_the_games_own_date():
    assert repair.ticker_date(EMBED_TICKER) == dt.datetime(2026, 2, 28)
    assert repair.ticker_date("pm_kalshi_KXNBAMENTION-26FEB22DENGSW") == dt.datetime(
        2026, 2, 22
    )


@pytest.mark.parametrize(
    "external_id", [None, "", "pm_kalshi_KXNBAMENTION", "pm_kalshi_KX-26XXX99"]
)
def test_a_ticker_with_no_readable_date_falls_back(external_id):
    assert repair.ticker_date(external_id) is None
    low, high = repair.counterpart_window(COMMENCE, external_id)
    assert (low, high) == (
        COMMENCE - repair._COMMENCE_WINDOW,
        COMMENCE + repair._COMMENCE_WINDOW,
    )


def test_the_ticker_window_is_anchored_on_the_ticker_not_the_stamp():
    """50 rows carry a sub-second ingestion stamp where a kickoff should be, so
    a window drawn round `commence_time` can look at the wrong day entirely."""
    stamp = dt.datetime(2026, 4, 26, 2, 20, 40, tzinfo=dt.timezone.utc)
    low, high = repair.counterpart_window(stamp, EMBED_TICKER)
    assert low.date() == dt.date(2026, 2, 27)
    assert high.date() == dt.date(2026, 3, 2)


# ── the four branches, each earned ───────────────────────────────────────────

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


class _FakeSession:
    """Answers by looking at the SQL, so it is order-independent."""

    def __init__(self, events, markets=None, counterparts=None, child_counts=None):
        self.events = events
        self.markets = markets or {}
        self.counterparts = counterparts or []
        self.child_counts = child_counts or {}
        self.statements = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        self.statements.append((sql, params))
        if sql.startswith("SELECT e.id, e.home_team_name"):
            return _Result(self.events)
        if sql.startswith("SELECT id, name FROM futures_markets"):
            return _Result(self.markets.get(params["eid"], []))
        if sql.startswith("SELECT id, home_team_name, away_team_name FROM events"):
            return _Result(self.counterparts)
        for table, count in self.child_counts.items():
            if f"FROM {table} WHERE event_id" in sql:
                return _Result([(count,)])
        if "count(*)" in sql:
            return _Result([(0,)])
        return _Result([])

    async def commit(self):
        pass


def _plan_one(home, away, **kwargs):
    session = _FakeSession([(1, home, away, COMMENCE, kwargs.pop("external_id", None),
                            kwargs.pop("status", "closed"))], **kwargs)
    return asyncio.run(repair.build_plan(session))[0]


def test_a_row_whose_match_already_exists_is_deleted_as_a_duplicate():
    entry = _plan_one(
        EMBED_HOME, EMBED_AWAY,
        external_id=EMBED_TICKER,
        counterparts=[(6547703, "Duke Blue Devils", "Virginia Cavaliers")],
    )
    assert (entry["action"], entry["why"]) == ("delete", "duplicate")
    assert entry["counterpart"] == 6547703


def test_a_second_fictional_row_is_not_a_counterpart():
    """Two mention props for one fixture would otherwise vouch for each other
    and both be deleted as duplicates of nothing."""
    entry = _plan_one(
        EMBED_HOME, EMBED_AWAY,
        external_id=EMBED_TICKER,
        counterparts=[(99, "Announcers", "Duke vs Virginia")],
    )
    assert entry["counterpart"] is None
    assert (entry["action"], entry["why"]) == ("delete", "last_trace") or (
        entry["action"] == "hold"
    )


def test_a_row_whose_market_still_names_the_fixture_is_deleted():
    """The market is UNLINKED, never deleted, so the fixture stays named."""
    entry = _plan_one(
        EMBED_HOME, EMBED_AWAY, markets={1: [(11, EMBED_MARKET)]}
    )
    assert (entry["action"], entry["why"]) == ("delete", "trace_survives")
    assert entry["market_ids"] == [11]


def test_a_row_that_names_no_fixture_is_deleted():
    """All seven live rows are this shape."""
    entry = _plan_one(WSOP_HOME, WSOP_AWAY, status="suspended")
    assert (entry["action"], entry["why"]) == ("delete", "no_fixture_named")
    assert entry["recovered"] is None


def test_the_last_trace_of_a_real_fixture_is_HELD_not_deleted():
    """#2871's rule, applied per row: reconstructible, no counterpart, and no
    surviving market means deleting the row really does lose the fixture."""
    entry = _plan_one(EMBED_HOME, EMBED_AWAY, external_id=EMBED_TICKER)
    assert (entry["action"], entry["why"]) == ("hold", "last_trace")
    assert entry["recovered"] == ("Duke", "Virginia")


def test_a_row_that_absorbed_a_real_market_is_HELD():
    """Unlinking a genuine soccer prop degrades it rather than fixing it —
    re-pointing is matching work (D39, lane1, #2693)."""
    entry = _plan_one(
        "What will the announcers say during New Zealand", "Egypt",
        markets={1: [(11, "New Zealand vs Egypt: Correct Score")]},
    )
    assert (entry["action"], entry["why"]) == ("hold", "owns_real_markets")


def test_a_held_row_is_never_written_to():
    """A hold that still unlinks its markets is not a hold."""
    session = _FakeSession(
        [(1, EMBED_HOME, EMBED_AWAY, COMMENCE, EMBED_TICKER, "closed")]
    )
    plan = asyncio.run(repair.build_plan(session))
    assert plan[0]["action"] == "hold"
    session.statements.clear()
    written = asyncio.run(repair.apply_plan(session, plan))
    assert written == {"deleted": 0, "held": 1, "markets_unlinked": 0, "lma_deleted": 0}
    assert not [s for s, _ in session.statements if s.startswith(("UPDATE", "DELETE"))]


def test_the_counterpart_check_reads_both_orientations():
    """"Virginia at Duke" is the same game as "Duke at Virginia"."""
    session = _FakeSession([])
    asyncio.run(
        repair.find_clean_counterpart(session, "Duke", "Virginia", COMMENCE, None, 1)
    )
    sql = session.statements[-1][0]
    assert "home_team_name ILIKE :first AND away_team_name ILIKE :second" in sql
    assert "home_team_name ILIKE :second AND away_team_name ILIKE :first" in sql
    assert "id <> :self" in sql, "the row would find ITSELF and never be held"


def test_a_name_cannot_smuggle_its_own_wildcard():
    """'%' in a team name would otherwise turn containment into match-anything."""
    assert repair._ilike_term("100% Sure") == "%100\\% Sure%"
    assert repair._ilike_term("A_B") == "%A\\_B%"


# ── the statements ───────────────────────────────────────────────────────────

def _all_statements():
    session = _FakeSession(
        [
            (1, EMBED_HOME, EMBED_AWAY, COMMENCE, EMBED_TICKER, "closed"),
            (2, WSOP_HOME, WSOP_AWAY, COMMENCE, None, "suspended"),
            (3, EMBED_HOME, EMBED_AWAY, COMMENCE, None, "closed"),
        ],
        markets={3: [(99, EMBED_MARKET)]},
    )
    plan = asyncio.run(repair.build_plan(session))
    asyncio.run(repair.unhandled_child_rows(session, [2, 3]))
    asyncio.run(repair.ensure_backup(session, plan))
    asyncio.run(repair.apply_plan(session, plan))
    return session.statements


def test_every_statement_parses_as_postgres():
    """A syntax error here is otherwise only found by an unreadable dyno run."""
    sqlglot = pytest.importorskip("sqlglot")
    statements = _all_statements()
    assert len(statements) >= 10, f"only captured {len(statements)} statements"
    for sql, _ in statements:
        try:
            parsed = sqlglot.parse(sql, dialect="postgres")
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"not valid Postgres: {exc}\n{sql}")
        assert parsed and parsed[0] is not None


def test_no_bind_does_interval_arithmetic_in_sql():
    """CERT-907 — `:c - interval '36 hours'` types `:c` AS AN INTERVAL, and the
    predicate dies with "operator does not exist". sqlglot parses it happily, so
    the test above cannot see it. This repair does the arithmetic in Python."""
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
        "a bind parameter is doing interval arithmetic with no CAST:\n  "
        + "\n  ".join(offenders)
    )


def test_the_window_is_computed_in_python_and_passed_as_two_values():
    session = _FakeSession([])
    asyncio.run(repair.find_clean_counterpart(session, "A", "B", COMMENCE, None, 1))
    _, params = session.statements[-1]
    assert params["lo"] == COMMENCE - repair._COMMENCE_WINDOW
    assert params["hi"] == COMMENCE + repair._COMMENCE_WINDOW


def test_markets_are_unlinked_before_the_row_is_deleted():
    """`futures_markets.event_id` is NO ACTION: the wrong order is an error,
    not a silent partial repair.

    Checked PER EVENT, not across the run: row 2 owns nothing and is deleted
    before row 3 is ever touched, so a global "first unlink before first delete"
    assertion would fail on a correct repair.
    """
    statements = _all_statements()
    unlink = next(
        i for i, (sql, p) in enumerate(statements)
        if sql.startswith("UPDATE futures_markets") and p.get("eid") == 3
    )
    delete = next(
        i for i, (sql, p) in enumerate(statements)
        if sql.startswith("DELETE FROM events") and p.get("eid") == 3
    )
    assert unlink < delete


def test_the_taxonomy_cache_row_is_deleted_before_its_event():
    """`line_movement_analyses` is NO ACTION too, and it blocks the delete."""
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


def test_the_repair_never_updates_the_events_table():
    """Nothing is renamed. A rename here mints a blank card or a twin."""
    assert not [
        sql for sql, _ in _all_statements() if sql.startswith("UPDATE events")
    ]


def test_the_backup_banks_the_row_and_every_cascade_child():
    """win_prob_snapshots is CASCADE: 1,156 rows go with the events silently.
    An undo that cannot put the curve back is not an undo."""
    inserts = [
        sql for sql, _ in _all_statements()
        if sql.startswith(f"INSERT INTO {repair.BAK_EVENTS}")
    ]
    assert inserts, "nothing was banked"
    assert all("to_jsonb(e)" in sql for sql in inserts), "row not banked whole"
    for table in repair.CASCADE_CHILD_TABLES:
        assert any(table in sql for sql in inserts), f"{table} not banked"
    assert any("lma_rows" in sql for sql in inserts)


def test_only_rows_being_deleted_are_banked():
    """Banking a held row would let the undo re-insert something still present."""
    banked = [
        params["eid"] for sql, params in _all_statements()
        if sql.startswith(f"INSERT INTO {repair.BAK_EVENTS}")
    ]
    assert 1 not in banked, "the held row was banked"
    assert sorted(banked) == [2, 3]


def test_the_market_links_are_banked_too():
    links = [
        params for sql, params in _all_statements()
        if sql.startswith(f"INSERT INTO {repair.BAK_LINKS}")
    ]
    assert [(p["mid"], p["eid"]) for p in links] == [(99, 3)]


# ── the gates ────────────────────────────────────────────────────────────────

def test_the_population_floor_exists_so_an_empty_run_cannot_report_success():
    assert repair.MIN_EXPECTED_POPULATION >= 200


def test_the_disposition_is_pre_registered_and_adds_up():
    expected = repair.EXPECTED
    assert (
        expected["delete_duplicate"]
        + expected["delete_trace_survives"]
        + expected["delete_no_fixture_named"]
        + expected["hold_last_trace"]
        + expected["hold_owns_real_markets"]
    ) == expected["population"]


def test_a_run_matching_the_registered_disposition_has_no_drift():
    assert repair.disposition_drift(dict(repair.EXPECTED)) == {}


@pytest.mark.parametrize("bucket", sorted(repair.EXPECTED))
def test_any_bucket_moving_is_drift(bucket):
    measured = dict(repair.EXPECTED)
    measured[bucket] += 1
    assert bucket in repair.disposition_drift(measured)


def test_the_observed_production_drift_is_permitted():
    """The exact drift the 2026-09-05 dry run refused itself on.

    One row moved `delete_duplicate` 156→155 and `hold_last_trace` 34→35 — a
    single row that stopped being deletable. The old exact-match gate returned
    exit 3 on it, and the only way past was `--allow-drift`, which would have
    run a 224-row production delete in a mode nobody reviewed.
    """
    measured = dict(repair.EXPECTED)
    measured["delete_duplicate"] = 155
    measured["hold_last_trace"] = 35
    assert repair.disposition_drift(measured)  # it IS drift
    assert repair.unsafe_disposition_drift(measured) == {}  # and it is safe


@pytest.mark.parametrize("bucket", sorted(repair._UNSAFE_WHEN_HIGHER))
def test_a_delete_bucket_growing_still_refuses(bucket):
    measured = dict(repair.EXPECTED)
    measured[bucket] += 1
    assert bucket in repair.unsafe_disposition_drift(measured)


@pytest.mark.parametrize("bucket", sorted(repair._UNSAFE_WHEN_HIGHER))
def test_a_delete_bucket_shrinking_is_permitted(bucket):
    measured = dict(repair.EXPECTED)
    measured[bucket] -= 1
    assert repair.unsafe_disposition_drift(measured) == {}


@pytest.mark.parametrize("bucket", sorted(repair._UNSAFE_WHEN_LOWER))
def test_a_hold_bucket_shrinking_refuses(bucket):
    """A held row that stopped being held has become a delete somewhere."""
    measured = dict(repair.EXPECTED)
    measured[bucket] -= 1
    assert bucket in repair.unsafe_disposition_drift(measured)


@pytest.mark.parametrize("bucket", sorted(repair._UNSAFE_WHEN_LOWER))
def test_a_hold_bucket_growing_is_permitted(bucket):
    measured = dict(repair.EXPECTED)
    measured[bucket] += 1
    assert repair.unsafe_disposition_drift(measured) == {}


def test_population_alone_never_refuses_in_either_direction():
    """`population` is the sum of the gated buckets, so gating it as well would
    refuse the safe direction too — which is the pressure toward
    `--allow-drift` this change exists to remove."""
    for delta in (+10, -10):
        measured = dict(repair.EXPECTED)
        measured["population"] += delta
        assert repair.unsafe_disposition_drift(measured) == {}
    assert "population" not in repair._UNSAFE_WHEN_HIGHER
    assert "population" not in repair._UNSAFE_WHEN_LOWER


def test_every_gated_bucket_has_a_direction():
    """The hole this class of gate fails through: a bucket in the census that
    nobody classified, so it drifts either way unwatched."""
    classified = set(repair._UNSAFE_WHEN_HIGHER) | set(repair._UNSAFE_WHEN_LOWER)
    unclassified = set(repair.EXPECTED) - classified - {"population"}
    assert unclassified == set(), unclassified


def test_a_delete_bucket_the_census_never_named_refuses():
    """Population can grow through a NEW delete reason without moving any named
    delete bucket. `population` is not gated, so this is the one way destructive
    growth could slip past the direction gate."""
    measured = dict(repair.EXPECTED)
    measured["population"] += 40
    measured["delete_some_new_reason"] = 40
    assert repair.unsafe_disposition_drift(measured) == {}
    assert "delete_some_new_reason" in repair.unknown_destructive_buckets(measured)


def test_an_unknown_bucket_that_is_not_a_delete_is_not_a_refusal():
    measured = dict(repair.EXPECTED)
    measured["hold_some_new_reason"] = 40
    assert repair.unknown_destructive_buckets(measured) == {}


def test_the_uncomfortable_number_is_registered_too():
    """34 rows are the last record of a real fixture and are NOT deleted. That
    is the number the delete branch is justified by, so it gates like any
    other — if it grows, the repair stops and someone looks."""
    assert repair.EXPECTED["hold_last_trace"] == 34


def test_the_docstring_claim_matches_the_registered_numbers():
    doc = repair.__doc__
    assert "274 rows" in doc
    assert "counterpart already exists (156)" in doc
    assert "trace survives in the market (57)" in doc
    assert "no fixture at all (12)" in doc
    assert "last trace (34)" in doc
    assert "absorbed REAL derivatives (15)" in doc
    assert "225 deleted, 49 held" in doc


def test_the_unhandled_child_tables_are_the_no_action_ones_left_over():
    """These five hold a NO ACTION FK and are not cleared here. A row in one of
    them turns the DELETE into an error mid-loop, so it must REFUSE first."""
    assert set(repair.UNHANDLED_CHILD_TABLES) == {
        "odds_snapshots",
        "odds_aggregated",
        "ranking_judgments",
        "score_snapshots",
        "scoring_plays",
    }


def test_an_unhandled_child_row_is_found_and_named():
    session = _FakeSession([], child_counts={"scoring_plays": 3})
    found = asyncio.run(repair.unhandled_child_rows(session, [1, 2]))
    assert found == {"scoring_plays": 3}


def test_no_unhandled_children_reads_as_clear():
    session = _FakeSession([])
    assert asyncio.run(repair.unhandled_child_rows(session, [1, 2])) == {}


# ── the undo ─────────────────────────────────────────────────────────────────

class _RestoreSession:
    def __init__(self, rows, current, links=None, market_state=None):
        self.rows = rows
        self.current = current
        self.links = links or []
        self.market_state = market_state or {}
        self.statements = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        self.statements.append((sql, params))
        if sql.startswith("SELECT to_regclass"):
            return _Result([("x",)])
        if sql.startswith("SELECT event_id, why"):
            return _Result(self.rows)
        if sql.startswith("SELECT 1 FROM events WHERE id"):
            return _Result([(1,)] if params["eid"] in self.current else [])
        if sql.startswith("SELECT market_id"):
            return _Result(self.links)
        if sql.startswith("SELECT event_id FROM futures_markets"):
            if params["mid"] not in self.market_state:
                return _Result([])
            return _Result([(self.market_state[params["mid"]],)])
        return _Result([])

    async def commit(self):
        pass


def test_restore_reinserts_a_deleted_row_with_its_original_id():
    """Every child in the backup points at that id — a new id restores nothing."""
    session = _RestoreSession(
        rows=[(7, "duplicate", {"id": 7, "home_team_name": EMBED_HOME}, [], {})],
        current={},
    )
    report = asyncio.run(restore.restore_events(session, apply=True))
    assert report["reinserted"] == 1
    insert = [s for s, _ in session.statements if s.startswith("INSERT INTO events")][0]
    assert "jsonb_populate_record" in insert, (
        "a column added to events since the backup would break a positional insert"
    )


def test_restore_puts_the_win_probability_series_back_too():
    """The curve is the loudest thing a user saw on the fake card; an undo that
    brings back the row without it restores a different event."""
    session = _RestoreSession(
        rows=[(
            7, "no_fixture_named", {"id": 7},
            [{"id": 1, "event_id": 7}],
            {"win_prob_snapshots": [{"id": 5, "event_id": 7}],
             "event_provider_anchors": [{"id": 9, "event_id": 7}]},
        )],
        current={},
    )
    report = asyncio.run(restore.restore_events(session, apply=True))
    assert report["children_reinserted"] == 3
    tables = [
        s.split("INSERT INTO ")[1].split(" ")[0]
        for s, _ in session.statements if s.startswith("INSERT INTO ")
    ]
    assert "win_prob_snapshots" in tables
    assert "event_provider_anchors" in tables
    assert "line_movement_analyses" in tables


def test_restore_only_reinserts_tables_it_names():
    """`cascade_rows` keys come out of a jsonb document and are interpolated
    into SQL, so an unexpected key must be ignored rather than executed."""
    session = _RestoreSession(
        rows=[(7, "duplicate", {"id": 7}, [], {"users; DROP TABLE events": [{"id": 1}]})],
        current={},
    )
    report = asyncio.run(restore.restore_events(session, apply=True))
    assert report["children_reinserted"] == 0
    assert not [s for s, _ in session.statements if "DROP TABLE" in s]


def test_restore_does_not_reinsert_a_row_that_is_already_back():
    session = _RestoreSession(
        rows=[(7, "duplicate", {"id": 7}, [], {})], current={7: True}
    )
    report = asyncio.run(restore.restore_events(session, apply=True))
    assert report["already_present"] == 1 and report["reinserted"] == 0


def test_restore_leaves_a_market_that_moved_on_alone():
    session = _RestoreSession(
        rows=[], current={}, links=[(99, 3)], market_state={99: 12345}
    )
    report = asyncio.run(restore.restore_links(session, apply=True))
    assert report["diverged"] == 1 and report["relinked"] == 0


def test_restore_relinks_a_market_that_is_still_detached():
    session = _RestoreSession(
        rows=[], current={3: True}, links=[(99, 3)], market_state={99: None}
    )
    report = asyncio.run(restore.restore_links(session, apply=True))
    assert report["relinked"] == 1
    update = [s for s, _ in session.statements if s.startswith("UPDATE futures_markets")][0]
    assert "event_id IS NULL" in update


def test_restore_is_dry_by_default_and_drop_backups_is_explicit():
    import inspect

    source = inspect.getsource(restore.main)
    assert '"--apply"' in source and '"--drop-backups"' in source
    body = inspect.getsource(restore.run)
    assert "if not args.apply" in body


def test_the_undo_says_why_its_preview_under_reports():
    """#2993's undo previews `relinked: 0` because the events are not back yet.
    Said out loud rather than patched — a certified script does not get a cert
    round to improve a preview."""
    assert "under-reports" in restore.__doc__.lower()
    assert "missing_event" in restore.__doc__


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
