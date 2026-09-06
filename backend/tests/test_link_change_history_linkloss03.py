"""LINKLOSS-03 — a link change is HISTORY, not a row the next pass overwrites.

WHAT CERT-791 MEASURED. LINKLOSS-02 gave the matcher a vocabulary for a link
that ends (``unlinked``, ``superseded_by_twin_merge``, ``previous_event_id``,
``actor``) and wrote it onto ``market_match_receipts`` — which is, by design,
ONE upserted row per market. A market the matcher has just unlinked sits at
``event_id IS NULL``, and that is precisely the population the scheduled pass
re-scans every 15 minutes. So the next ordinary attempt upserted
``{rejected, null, null}`` over ``{unlinked, previous_event_id: 42,
matcher_pass}``, and the record of why a price left a card was gone, usually
inside the hour. The 24-hour census then counted only the changes nobody had
re-attempted — a number that SHRINKS as the matcher works, so a night that lost
links reads as a quiet one.

Three things had to be true for the ship ("one query says why a price
disappeared"), and this file holds each of them:

1.  a link change is appended to an immutable table and the census reads that
    table — Parts 1 and 2;
2.  EVERY writer that clears ``futures_markets.event_id`` receipts it, not just
    the matcher's own passes — Part 3, which scans the whole of ``app/``
    because the guard CERT-791 found hollow scanned one module and therefore
    certified a narrower population than the ship claimed;
3.  a fabricated link loss stays impossible — a rolled-back or rejected attempt
    must append nothing, since an invented loss in the one table the census
    reads is worse than no table at all.

THE END-TO-END GUARD RUNS REAL SQL. ``test_an_unlink_survives_the_next_failed_
rematch`` takes the statements the real writer emits, executes them against
stdlib sqlite3, and then runs the real census query over the result. It is red
on the pre-repair code for the measured reason: the second flush overwrites the
first and the census returns nothing.
"""

from __future__ import annotations

import ast
import asyncio
import json
import pathlib
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql as pg_dialect

from app.utils import match_receipts as mr

APP_ROOT = pathlib.Path(mr.__file__).resolve().parents[1]

T0 = datetime(2026, 9, 2, 19, 0, tzinfo=timezone.utc)


def _receipt(market_id: int = 1, **kw):
    base = dict(
        market_id=market_id,
        source="kalshi",
        external_id="KXNFLGAME-25SEP07DALPHI-DAL",
        market_name="Dallas Cowboys vs Philadelphia Eagles",
        phase=mr.PHASE_PHASE15_REVALIDATE,
        attempted_at=T0,
    )
    base.update(kw)
    return mr.MatchReceipt(**base)


# =============================================================================
# Part 1 — what appends, and what must never append
# =============================================================================


def test_an_unlink_appends_a_change():
    row = mr.link_change_row(_receipt().unlink(42))
    assert row["outcome"] == mr.OUTCOME_UNLINKED
    assert row["previous_event_id"] == 42
    assert row["new_event_id"] is None
    assert row["actor"] == mr.ACTOR_MATCHER_PASS
    assert row["changed_at"] == T0


def test_a_relink_appends_the_move_it_made():
    row = mr.link_change_row(_receipt().link(91, previous_event_id=42))
    assert (row["previous_event_id"], row["new_event_id"]) == (42, 91)
    assert row["outcome"] == mr.OUTCOME_LINKED


def test_a_twin_merge_appends_its_own_outcome():
    row = mr.link_change_row(_receipt().supersede(42, 91))
    assert row["outcome"] == mr.OUTCOME_SUPERSEDED_BY_TWIN_MERGE
    assert row["actor"] == mr.ACTOR_TWIN_CLEANUP


def test_a_first_attach_appends_nothing():
    """A market that was on nothing did not LOSE a link. Counting it would
    inflate the census with losses that never happened."""
    assert mr.link_change_row(_receipt().link(91)) is None


def test_an_ordinary_reject_appends_nothing():
    assert mr.link_change_row(_receipt().reject(mr.REJECT_NO_CANDIDATE)) is None


def test_an_outcome_that_asserts_nothing_appends_nothing():
    """The outcome filter carries its own weight, and this test exists because
    a mutation proved it otherwise.

    ``reject()`` clears ``previous_event_id``, so on the normal path either
    check alone would keep a rejected receipt out of the history — which means
    neither is tested by the normal path. Here the fields are set directly, the
    way a future caller building a receipt by hand would: an outcome that
    asserts nothing about ``futures_markets.event_id`` must never become a
    permanent claim that a link ended.
    """
    hand_built = _receipt()
    hand_built.outcome = mr.OUTCOME_REJECTED
    hand_built.reject_reason = mr.REJECT_LINK_NOT_DURABLE
    hand_built.previous_event_id = 42
    hand_built.actor = mr.ACTOR_MATCHER_PASS

    assert mr.link_change_row(hand_built) is None


def test_a_downgraded_unlink_appends_nothing():
    """The worst failure this table can have is a link loss that never happened.

    ``verify_links_are_durable`` downgrades an ``unlinked`` receipt whose row is
    still attached. That downgrade has to reach the PERMANENT record too — an
    invented loss in an append-only table cannot be corrected by the next pass
    the way a wrong receipt could.
    """
    ghost = _receipt(market_id=1).unlink(42)
    real = _receipt(market_id=2).unlink(42)

    class _Session:
        async def execute(self, stmt):
            class _R:
                def all(self_inner):
                    return [(1, 42), (2, None)]
            return _R()

    asyncio.run(mr.verify_links_are_durable(_Session(), [ghost, real]))

    assert mr.link_change_row(ghost) is None
    assert mr.link_change_row(real) is not None


def test_a_downgraded_receipt_stops_claiming_a_departure():
    """The receipt row itself must not keep pointing at an event it never left.

    ``previous_event_id`` is what the by-event lookup reads to answer "what came
    off this card". Leaving it set on a downgraded claim reports a departure
    that did not happen; the claimed ids survive in ``detail``, as evidence.
    """
    ghost = _receipt().unlink(42)
    ghost.reject(mr.REJECT_LINK_NOT_DURABLE, previous_event_id=42)
    assert ghost.previous_event_id is None
    assert ghost.actor is None
    assert ghost.detail["previous_event_id"] == 42


def test_the_history_table_has_nothing_to_upsert_on():
    """The absence of a unique key is the design, not an omission.

    With no unique constraint there is no ``ON CONFLICT`` for a later writer to
    reach for, so "append-only" is a property of the schema rather than a habit
    of the code.
    """
    from app.models.models import MarketLinkChange

    for index in MarketLinkChange.__table__.indexes:
        assert not index.unique, f"{index.name} is unique — an upsert key"
    for constraint in MarketLinkChange.__table__.constraints:
        assert type(constraint).__name__ != "UniqueConstraint", (
            f"{constraint.name} makes the history table upsertable"
        )

    migration = (
        APP_ROOT.parent / "alembic" / "versions" / "link_change_history.py"
    ).read_text()
    assert "unique=True" not in migration


def test_the_append_is_a_plain_insert_and_the_flush_always_calls_it():
    import inspect

    append = inspect.getsource(mr.append_link_changes)
    assert "on_conflict" not in append, (
        "an upsert in the history writer is the exact defect this table "
        "exists to fix, one table over"
    )
    flush = inspect.getsource(mr.flush_receipts)
    assert "append_link_changes" in flush, (
        "history is appended from flush_receipts because that is the one "
        "function every receipt in the system passes through; anywhere else "
        "is a path a future writer can forget"
    )


# =============================================================================
# Part 2 — the end-to-end guard: real statements, real SQL engine
#
# An unlink, then a FAILED rematch of the same market, then the real census.
# =============================================================================

_DDL = (
    """
    CREATE TABLE market_match_receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id INTEGER NOT NULL UNIQUE,
        source TEXT, external_id TEXT, market_name TEXT, phase TEXT,
        outcome TEXT, reject_reason TEXT,
        linked_event_id INTEGER, previous_event_id INTEGER, actor TEXT,
        candidates TEXT, detail TEXT,
        first_attempted_at TEXT, last_attempted_at TEXT, attempt_count INTEGER,
        container_id INTEGER
    )
    """,
    """
    CREATE TABLE market_link_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id INTEGER NOT NULL,
        source TEXT, external_id TEXT, market_name TEXT, phase TEXT,
        outcome TEXT NOT NULL, actor TEXT NOT NULL,
        previous_event_id INTEGER NOT NULL, new_event_id INTEGER,
        detail TEXT, changed_at TEXT NOT NULL
    )
    """,
)

#: The two dialect differences between the statements the writer emits and what
#: sqlite will take. Both are rewrites of FORM, not of meaning: the JSONB cast
#: is a no-op in a store with no JSONB type, and ``least``/``min`` are the same
#: two-argument function under two names. Anything else appearing in the SQL
#: makes :func:`_sqlite` raise rather than quietly run different SQL than
#: production does.
_PG_ONLY = (("::JSONB", ""), ("least(", "min("))


def _sqlite(stmt) -> tuple[str, dict]:
    compiled = stmt.compile(dialect=pg_dialect.dialect(paramstyle="named"))
    sql = str(compiled)
    for postgres, sqlite in _PG_ONLY:
        sql = sql.replace(postgres, sqlite)
    assert "::" not in sql, (
        f"an unrendered Postgres cast survived the rewrite: {sql[:200]}. The "
        f"harness would be running different SQL from production."
    )

    params = {}
    for key, value in compiled.params.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        elif isinstance(value, datetime):
            # The dialect's own textual form, so the >= comparisons in the
            # census sort as timestamps rather than as arbitrary strings.
            value = value.strftime("%Y-%m-%d %H:%M:%S.%f")
        params[key] = value
    return sql, params


class _Capturing:
    """Collects the statements the real writer emits, executes none of them."""

    def __init__(self):
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return None


def _flush_into(conn, receipts):
    session = _Capturing()
    written = asyncio.run(mr.flush_receipts(session, receipts))
    for stmt in session.statements:
        sql, params = _sqlite(stmt)
        conn.execute(sql, params)
    conn.commit()
    return written, session.statements


def _fetch(conn, stmt):
    sql, params = _sqlite(stmt)
    return conn.execute(sql, params).fetchall()


@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    for ddl in _DDL:
        conn.execute(ddl)
    yield conn
    conn.close()


def test_the_hand_written_schema_still_covers_the_model(db):
    """The DDL above is hand-written, so it DRIFTS — and the drift is silent
    until the day it isn't.

    ``_flush_into`` runs the statements the real writer emits, which name every
    column the ORM model declares. The table those statements land on is the
    string literal above, maintained by hand. Add a column to
    ``MarketMatchReceipt`` and the two come apart; nothing in this file notices
    until five unrelated end-to-end tests go red at once with
    ``sqlite3.OperationalError: table market_match_receipts has no column named
    <x>`` — an error that points at the harness and says nothing about the
    column, the change that added it, or which of the two sides is wrong.

    MEASURED, 2026-09-06 (#2927 Phase 1): that is exactly what happened.
    ``container_id`` was added to the model and the migration; this file's DDL
    was not touched, and CI backend shard 1 went red on five tests whose subject
    is link-loss history and which have nothing to do with containers. The
    repair is one word in the DDL. THIS test is the part that makes the next one
    cost one word too, and name itself.

    It asserts COVERAGE, not equality: the harness is free to carry a scratch
    column the model does not have (none does today), but every column the
    writer can name must exist, or the statement it appears in cannot run.
    """
    from app.models.models import MarketLinkChange, MarketMatchReceipt

    for model in (MarketMatchReceipt, MarketLinkChange):
        declared = {c.name for c in model.__table__.columns}
        rows = db.execute(f"PRAGMA table_info({model.__tablename__})").fetchall()
        assert rows, (
            f"{model.__tablename__} is not in `_DDL` at all — the fixture above "
            f"creates the tables this suite writes to, so a model with no table "
            f"here has no end-to-end coverage."
        )
        present = {row[1] for row in rows}
        missing = declared - present
        assert not missing, (
            f"`_DDL` has drifted from {model.__name__}: the model declares "
            f"{sorted(missing)}, which the hand-written {model.__tablename__} "
            f"does not have. Every statement the real writer emits names these "
            f"columns, so each one is an OperationalError in every test that "
            f"flushes. Add them to `_DDL` above (the type only has to be one "
            f"sqlite affinity can store — this harness rewrites form, not "
            f"meaning)."
        )


def test_an_unlink_survives_the_next_failed_rematch(db):
    """THE GUARD CERT-791 ASKED FOR.

    Phase 1.5 unlinks market 1 off event 42. Fifteen minutes later the ordinary
    pass picks the same market up — it is unlinked, so of course it does — and
    refuses it for want of a candidate. The receipt is now a ``rejected``, which
    is correct and is what the receipt is for. The question "what happened to
    this market's link" must still have its answer.
    """
    unlink = _receipt(market_id=1).unlink(42, cause="phase15_wrong_game")
    _flush_into(db, [unlink])

    rematch = _receipt(
        market_id=1, phase=mr.PHASE_PASS2_GENERAL,
        attempted_at=T0 + timedelta(minutes=15),
    ).reject(mr.REJECT_NO_CANDIDATE)
    _flush_into(db, [rematch])

    # The receipt is the LATEST ATTEMPT, and says so. Nothing is wrong here.
    receipts = db.execute(
        "SELECT outcome, previous_event_id, actor, attempt_count "
        "FROM market_match_receipts"
    ).fetchall()
    assert receipts == [("rejected", None, None, 2)]

    # The history is untouched, and the census still counts the loss.
    census = _fetch(db, mr.link_change_census_query(T0 - timedelta(hours=24)))
    assert census == [(mr.OUTCOME_UNLINKED, mr.ACTOR_MATCHER_PASS,
                       mr.PHASE_PHASE15_REVALIDATE, 1)], (
        "the link loss was erased by the next ordinary matching attempt — the "
        "census now under-reports by everything the matcher has re-tried, "
        "which is everything it unlinked (CERT-791)"
    )


def test_the_event_that_lost_the_price_can_still_name_what_left(db):
    """The other half of the ship: asked by EVENT id, not by market id."""
    _flush_into(db, [_receipt(market_id=1).unlink(42)])
    _flush_into(db, [
        _receipt(
            market_id=1, phase=mr.PHASE_PASS2_GENERAL,
            attempted_at=T0 + timedelta(minutes=15),
        ).reject(mr.REJECT_NO_CANDIDATE)
    ])

    departed = _fetch(db, mr.link_changes_off_event_query(42, 50))
    assert len(departed) == 1
    assert _fetch(db, mr.link_changes_off_event_query(91, 50)) == []

    history = _fetch(db, mr.link_changes_for_market_query(1, 50))
    assert len(history) == 1


def test_every_change_appends_a_row_of_its_own(db):
    """Three changes to one market's link are three rows, not one survivor."""
    _flush_into(db, [_receipt(market_id=1).unlink(42)])
    _flush_into(db, [
        _receipt(market_id=1, attempted_at=T0 + timedelta(minutes=15))
        .link(91, previous_event_id=42)
    ])
    _flush_into(db, [
        _receipt(market_id=1, attempted_at=T0 + timedelta(minutes=30))
        .supersede(91, 77)
    ])

    outcomes = [
        r[0] for r in db.execute(
            "SELECT outcome FROM market_link_changes ORDER BY id"
        ).fetchall()
    ]
    assert outcomes == [
        mr.OUTCOME_UNLINKED, mr.OUTCOME_LINKED,
        mr.OUTCOME_SUPERSEDED_BY_TWIN_MERGE,
    ]


def test_the_census_window_excludes_what_it_should(db):
    _flush_into(db, [_receipt(market_id=1).unlink(42)])
    assert _fetch(db, mr.link_change_census_query(T0 + timedelta(hours=1))) == []
    assert _fetch(db, mr.link_change_census_query(T0 - timedelta(hours=1)))


def test_a_rejected_attempt_writes_no_history_row_at_all(db):
    """The control. Without it, a census that counted every receipt would pass
    every test above."""
    _flush_into(db, [_receipt(market_id=7).reject(mr.REJECT_NO_CANDIDATE)])
    assert db.execute("SELECT COUNT(*) FROM market_link_changes").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM market_match_receipts").fetchone()[0] == 1


def test_the_census_endpoint_reads_the_history_table():
    """The route must not have kept its own copy of the old GROUP BY."""
    import inspect

    from app.routes import admin_matching

    source = inspect.getsource(admin_matching)
    census = source[source.index("The link-loss census"):]
    census = census[:census.index("def ", 1)] if "def " in census[1:] else census
    assert "link_change_census_query" in census
    assert "MarketMatchReceipt.outcome.in_(" not in census, (
        "the census is counting receipts again — the number shrinks as the "
        "matcher re-attempts the markets it unlinked"
    )


# =============================================================================
# Part 3 — EVERY writer, not just the matcher's
#
# CERT-791: three raw-SQL unlink endpoints committed with no receipt while the
# LINKLOSS-02 guard scanned one module and reported a clean zero. This scan
# reads every file under app/.
# =============================================================================

#: Any of these in the enclosing function is a receipt. The list is of the
#: functions that WRITE a link change; a call site naming one of them has
#: handed the change to the one code path that appends history.
_RECEIPT_MARKERS = (
    "_record_link_change",
    "_receipt_bulk_moves",
    "record_link_change_receipts",
    "record_twin_merge_receipts",
    "record_link_losses",
)

#: The raw-SQL shape. ``\s+`` spans newlines, because every current site wraps
#: the statement across lines.
_SQL_UNLINK = re.compile(
    r"futures_markets\s+SET\s+event_id\s*=\s*NULL", re.IGNORECASE
)
_ATTR_UNLINK = re.compile(r"\.event_id\s*=\s*None\b")
_VALUES_UNLINK = re.compile(r"\.values\(\s*event_id\s*=\s*None\s*\)")


def _app_files() -> list[pathlib.Path]:
    files = sorted(APP_ROOT.rglob("*.py"))
    assert len(files) > 50, (
        f"the sweep found only {len(files)} files under {APP_ROOT} — it is "
        f"not looking at the application"
    )
    return files


def _ast_sites(tree: ast.AST) -> set[int]:
    """Line numbers of every write that clears a market's event link.

    Three shapes: the ORM attribute assignment, the Core ``values`` keyword, and
    the raw ``UPDATE futures_markets SET event_id = NULL`` — the shape the
    LINKLOSS-02 scan could not see, which is how three endpoints passed it.
    """
    sites: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if node.value.value is None and any(
                isinstance(t, ast.Attribute) and t.attr == "event_id"
                for t in node.targets
            ):
                sites.add(node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "values":
                for kw in node.keywords:
                    if (
                        kw.arg == "event_id"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is None
                    ):
                        sites.add(node.lineno)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _SQL_UNLINK.search(node.value):
                sites.add(node.lineno)
    return sites


def _text_sites(source: str) -> int:
    """A second, independent reading. Counts the same three shapes off the raw
    text, so a write in a shape the AST pass has stopped recognising makes the
    scan RAISE instead of reporting the clean zero a silent skip produces."""
    body = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    return (
        len(_ATTR_UNLINK.findall(body))
        + len(_VALUES_UNLINK.findall(body))
        + len(_SQL_UNLINK.findall(body))
    )


def _enclosing_sources(tree: ast.AST, source: str, line: int) -> list[str]:
    """The source of every function enclosing ``line``, innermost first."""
    import ast as _ast

    enclosing = []
    for node in _ast.walk(tree):
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            if node.lineno <= line <= (node.end_lineno or node.lineno):
                enclosing.append(node)
    enclosing.sort(key=lambda n: n.lineno, reverse=True)
    return [_ast.get_source_segment(source, n) or "" for n in enclosing] or [source]


def _files_with_an_unlink() -> list[pathlib.Path]:
    """Every file the TEXT reading flags, whatever the AST pass makes of it.

    Deliberately the weaker, dumber reading. If the file list came from the AST
    pass, a file whose only unlink is in a shape that pass has stopped
    recognising would drop out of the sweep entirely — and the cross-check
    below would then compare nothing and pass. (Measured: mutation M14 of this
    change's battery survived exactly that, against the earlier version of this
    function.)
    """
    return [p for p in _app_files() if _text_sites(p.read_text())]


def _unlink_sites_across_the_app() -> list[tuple[pathlib.Path, int, list[str]]]:
    found = []
    for path in _files_with_an_unlink():
        source = path.read_text()
        tree = ast.parse(source)
        for line in sorted(_ast_sites(tree)):
            found.append((path, line, _enclosing_sources(tree, source, line)))
    return found


def test_every_unlink_writer_in_the_app_records_a_link_change():
    """The scope CERT-791 found hollow. One module was scanned; the endpoints
    that actually dropped links without a receipt were in three others."""
    unreceipted = []
    for path, line, scopes in _unlink_sites_across_the_app():
        if not any(
            marker in scope for scope in scopes for marker in _RECEIPT_MARKERS
        ):
            unreceipted.append(f"{path.relative_to(APP_ROOT.parent)}:{line}")

    assert not unreceipted, (
        "these writes clear a market's event link and nothing in their "
        "function records the change, so the price leaves a card with no "
        "explanation anywhere in the system: " + ", ".join(unreceipted)
    )


def test_the_scan_is_not_vacuous():
    """A scan that finds nothing passes for the wrong reason. Name the files
    this repair wired, and require the sweep to still see them."""
    sites = _unlink_sites_across_the_app()
    by_file = {p.name for p, _line, _s in sites}
    for expected in (
        "prediction_market_matching.py", "admin_matching.py",
        "admin_events.py", "source_intelligence.py",
    ):
        assert expected in by_file, (
            f"the sweep no longer sees the unlink writes in {expected} — it "
            f"has stopped matching the code it guards"
        )
    assert len(sites) >= 8, f"only {len(sites)} unlink sites found"


def test_the_scan_refuses_a_shape_it_cannot_classify():
    """Two readings of every file that contains an unlink, and they must agree.

    A scanner that silently skips an unrecognised write reports zero for
    exactly the case it exists to catch.
    """
    for path in _files_with_an_unlink():
        source = path.read_text()
        ast_count = len(_ast_sites(ast.parse(source)))
        text_count = _text_sites(source)
        assert ast_count == text_count, (
            f"{path.name}: the AST sees {ast_count} event_id-clearing writes "
            f"and the text scan sees {text_count}. A write in a shape one of "
            f"them cannot see is a write nobody will demand a receipt for."
        )


# =============================================================================
# Part 4 — the three endpoints CERT-791 named, in order of operations
# =============================================================================


def _endpoint(module, name: str) -> str:
    import inspect

    source = inspect.getsource(module)
    start = source.index(f"def {name}(")
    end = source.find("\n@router", start)
    return source[start: end if end != -1 else len(source)]


ENDPOINTS = [
    ("admin_events", "delete_duplicate_events"),
    ("admin_events", "merge_duplicate_events_sql"),
    ("source_intelligence", "fix_date_mismatches"),
]


@pytest.mark.parametrize("module_name,func_name", ENDPOINTS)
def test_the_repair_endpoints_read_the_link_before_they_destroy_it(
    module_name, func_name
):
    """``event_id`` is the thing the UPDATE removes. Read after, and the
    receipt cannot name which event lost the price — and two of these three
    then DELETE that event, so nothing later can reconstruct it."""
    import importlib

    module = importlib.import_module(f"app.routes.{module_name}")
    body = _endpoint(module, func_name)

    read = min(
        (m.start() for m in re.finditer(r"SELECT id, source, external_id, name, event_id|SELECT fm\.id, fm\.source", body)),
        default=-1,
    )
    unlink = _SQL_UNLINK.search(body)
    assert read != -1, f"{func_name} does not read the markets it is about to unlink"
    assert unlink and read < unlink.start(), (
        f"{func_name} reads the markets after clearing their event_id — the "
        f"previous event id does not survive that UPDATE"
    )


@pytest.mark.parametrize("module_name,func_name", ENDPOINTS)
def test_the_repair_endpoints_publish_after_their_commit(module_name, func_name):
    """A receipt published before the commit is re-read against the pre-change
    row by ``verify_links_are_durable`` and downgraded — turning a real link
    loss into a report that the unlink failed."""
    import importlib

    module = importlib.import_module(f"app.routes.{module_name}")
    body = _endpoint(module, func_name)

    receipt = body.index("record_link_losses(")
    commit = body.rindex("await db.commit()", 0, receipt)
    assert commit < receipt


@pytest.mark.parametrize("module_name,func_name", ENDPOINTS)
def test_the_repair_endpoints_report_what_they_receipted(module_name, func_name):
    """A count in the response, because a receipt write that silently returns
    zero is exactly the failure that hid these three endpoints for a week."""
    import importlib

    module = importlib.import_module(f"app.routes.{module_name}")
    assert "link_change_receipts" in _endpoint(module, func_name)


def test_the_merge_rail_receipts_its_losses_as_a_merge_not_a_hand_repair():
    """`merge-duplicates-sql` NULLs every market on the loser rather than
    repointing it, so the merge really does drop the links. The actor has to
    say that: `admin_repair` would send the next investigation looking for a
    person, and one merge must not read as N hand edits."""
    from app.routes import admin_events

    body = _endpoint(admin_events, "merge_duplicate_events_sql")
    assert "ACTOR_TWIN_CLEANUP" in body and "PHASE_TWIN_MERGE" in body


# =============================================================================
# Part 5 — one repair, many events
# =============================================================================


def test_each_market_is_receipted_against_the_event_it_actually_left():
    """The date-mismatch sweep unlinks markets scattered over hundreds of
    events. Naming one of them for all is worse than naming none: every row
    but one then accuses an event that never held that market."""
    calls = []

    async def _spy(rows, **kw):
        calls.append((kw["previous_event_id"], [r["id"] for r in rows]))
        return len(rows)

    original = mr.record_link_change_receipts
    mr.record_link_change_receipts = _spy
    try:
        written = asyncio.run(mr.record_link_losses(
            [
                {"id": 1, "source": "kalshi", "external_id": "a", "name": "A",
                 "event_id": 42},
                {"id": 2, "source": "kalshi", "external_id": "b", "name": "B",
                 "event_id": 91},
                {"id": 3, "source": "kalshi", "external_id": "c", "name": "C",
                 "event_id": 42},
            ],
            actor=mr.ACTOR_ADMIN_REPAIR, phase=mr.PHASE_ADMIN_REPAIR,
        ))
    finally:
        mr.record_link_change_receipts = original

    assert written == 3
    assert sorted(calls) == [(42, [1, 3]), (91, [2])]


def test_a_market_with_no_previous_event_is_skipped_not_guessed():
    async def _spy(rows, **kw):  # pragma: no cover - must not be called
        raise AssertionError("receipted a market that had no link to lose")

    original = mr.record_link_change_receipts
    mr.record_link_change_receipts = _spy
    try:
        written = asyncio.run(mr.record_link_losses(
            [{"id": 1, "source": "kalshi", "external_id": "a", "name": "A",
              "event_id": None}],
            actor=mr.ACTOR_ADMIN_REPAIR, phase=mr.PHASE_ADMIN_REPAIR,
        ))
    finally:
        mr.record_link_change_receipts = original
    assert written == 0
