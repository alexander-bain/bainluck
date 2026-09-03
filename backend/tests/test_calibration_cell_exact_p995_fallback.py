"""CAL-P995 — guards for the ``fallback`` dimension on ``calibration_cell_exact``.

``fallback`` asks WHERE THE PUBLISHED PRICE CAME FROM. The curve price is
``COALESCE(calibration_probability, opening_probability)`` — a coalesce, not an
exclusion (gotcha #144 / ruling 103) — so a leg with no closing price at all is
published at its OPENING price and graded as though that were a closing line.
Globally 13.3% of markets are served by that fallback arm
(``closing_line_coverage``: 16,172 has / 2,472 needs / 18,644 total).

It exists for one cell and one bin. ``kalshi/entertainment`` is the board's
largest queued cell (ece 6.29, n 8,922, 29,353 excess outcomes, 6.2σ) and
CAL-P994 localized 184 of its 671 error-points into bin 9 alone: 1,104 legs
priced at a mean 95.4% that win 78.7%. Three candidates survive for that bin —
the coalesce fallback, a grading defect, and genuine Kalshi over-confidence —
and the fallback share per bin is the query that separates them.

🔴 **WHY ``price_moved`` COULD NOT ANSWER IT, which is the whole reason this
dimension exists.** The producer projects::

    price_moved = (calibration_probability IS NOT NULL
                   AND calibration_probability IS DISTINCT FROM opening_probability)

so its FALSE arm pools two unrelated populations — a leg with no closing price
at all, and a leg whose closing price genuinely equals its opening. CAL-P994
read ``--by price_moved`` on this cell (True 7.15 on n 6,570, False 6.73 on
n 2,352), concluded it "does not split it", and could not have concluded
anything else: the split it needed was INSIDE the false arm.
:func:`test_the_dimension_separates_what_price_moved_pools` is the arm that says
so, and it is the one to keep if the rest are ever trimmed.

WHAT THESE TESTS DO
---------------------
They EXECUTE the shipped ``FALLBACK_EXPR`` / ``FALLBACK_JOIN`` against a seeded
SQLite table rather than asserting on the text of a string, so a change to the
constants is a change to the answers. The defect arms are pinned in this file
rather than imported, so they cannot agree with their subject by construction.

THE ONE THING THEY DO NOT PROVE. SQLite is not Postgres, and the seeded tables
are not the producer's twenty-CTE chain. What is proved here is the
DIMENSION — its key expression, its join cardinality and its partition. That the
composed statement is valid *Postgres* is proved separately by
:func:`test_the_composed_statement_is_one_postgres_statement`, which parses the
real ``cell_sql`` output with sqlglot. Neither is a substitute for running the
sweep, and this queue deliberately does not run it: under LANE ROLES the sweep
is measurement and belongs to the measurement lane.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cce = _load("calibration_cell_exact")


# ---------------------------------------------------------------------------
# The defect arms. PINNED HERE, never imported — a defect arm that imports its
# subject agrees with it whatever the subject says.
# ---------------------------------------------------------------------------

#: What the dimension would be if it were written off the producer's flag
#: instead of the raw column: the shape CAL-P994 already ran, which cannot see
#: the fallback at all.
PRICE_MOVED_ONLY_DEFECT_EXPR = """
CASE WHEN d.price_moved THEN 'has_closing' ELSE 'fallback_opening' END
|| '|' || CASE WHEN d.price_moved THEN 'moved' ELSE 'flat' END
"""

#: The fan-out defect: the same question joined on the MARKET instead of the
#: outcome. It reads plausibly and silently multiplies every count.
MARKET_JOIN_DEFECT_JOIN = """
JOIN futures_outcomes fbk ON fbk.market_id = d.market_id
"""


# ---------------------------------------------------------------------------
# A seeded population with every case the dimension has to tell apart.
# ---------------------------------------------------------------------------

#: ``(outcome_id, market_id, calibration_probability, opening_probability,
#:   is_winner)`` — and the ``price_moved`` the producer would derive.
#:
#: Rows 1-2 are the case that matters: BOTH are ``price_moved = 0``, and they
#: are different populations. Row 1 has no closing price at all; row 2 has one
#: that happens to equal its opening.
SEED = [
    # id, market, calib_prob, open_prob, is_winner
    (1, 100, None, 0.95, 1),   # fallback, flat  — the bin-9 candidate
    (2, 100, 0.95, 0.95, 0),   # has_closing, flat — a real closing line that held
    (3, 101, 0.80, 0.60, 1),   # has_closing, moved
    (4, 101, None, 0.40, 0),   # fallback, flat
    (5, 102, 0.10, 0.30, 0),   # has_closing, moved
]


def _price_moved(calib, opening) -> int:
    """The producer's own projection, restated so the seed cannot drift.

    ``precompute_calibration.py``: ``(fo.calibration_probability IS NOT NULL AND
    fo.calibration_probability IS DISTINCT FROM fo.opening_probability)``.
    """
    return int(calib is not None and calib != opening)


@pytest.fixture()
def db():
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE futures_outcomes ("
        "  id INTEGER PRIMARY KEY, market_id INTEGER,"
        "  calibration_probability REAL, opening_probability REAL)"
    )
    con.execute(
        "CREATE TABLE deduped ("
        "  outcome_id INTEGER, market_id INTEGER,"
        "  price_moved INTEGER, is_winner INTEGER)"
    )
    for oid, mid, calib, opening, winner in SEED:
        con.execute(
            "INSERT INTO futures_outcomes VALUES (?, ?, ?, ?)",
            (oid, mid, calib, opening),
        )
        con.execute(
            "INSERT INTO deduped VALUES (?, ?, ?, ?)",
            (oid, mid, _price_moved(calib, opening), winner),
        )
    con.commit()
    yield con
    con.close()


def _fold(con, expr: str, join: str) -> dict[str, dict[str, int]]:
    """Run the rail's own SELECT shape and return ``key -> {n, w}``.

    The same ``SELECT <expr> AS k ... FROM deduped d <join> GROUP BY`` the
    shipped :func:`calibration_cell_exact.cell_sql` emits, minus the producer's
    CTE chain, which SQLite cannot run and which this test is not about.
    """
    rows = con.execute(
        f"SELECT {expr} AS k, COUNT(*) AS n,"
        f" SUM(CASE WHEN d.is_winner THEN 1 ELSE 0 END) AS w"
        f" FROM deduped d {join} GROUP BY 1"
    ).fetchall()
    return {k: {"n": n, "w": w} for k, n, w in rows}


# ---------------------------------------------------------------------------
# 1. The standing test for any new dimension on this rail (CAL-P130).
# ---------------------------------------------------------------------------

def test_the_expression_never_reads_a_realized_winner():
    """Leakage. A dimension keyed on the outcome makes the fold circular."""
    blob = (cce.FALLBACK_EXPR + cce.FALLBACK_JOIN).lower()
    for banned in ("is_winner", "winner", "resolution_source", "settled"):
        assert banned not in blob, f"{banned!r} leaks into the fallback key"


# ---------------------------------------------------------------------------
# 2. THE ARM THIS DIMENSION EXISTS FOR.
# ---------------------------------------------------------------------------

def test_the_dimension_separates_what_price_moved_pools(db):
    """Rows 1 and 2 are both ``price_moved = 0`` and must NOT share a key.

    Row 1 has no closing price and is published at its opening; row 2 has a
    closing price that held. Pooling them is exactly what made CAL-P994's
    ``--by price_moved`` read "does not split it".
    """
    got = _fold(db, cce.FALLBACK_EXPR, cce.FALLBACK_JOIN)

    assert got["fallback_opening|flat"]["n"] == 2      # rows 1, 4
    assert got["has_closing|flat"]["n"] == 1           # row 2
    assert got["has_closing|moved"]["n"] == 2          # rows 3, 5

    # And the win counts travel with them — the whole point is a win RATE per
    # half, not just a share.
    assert got["fallback_opening|flat"]["w"] == 1      # row 1 won, row 4 lost
    assert got["has_closing|flat"]["w"] == 0

    # The defect arm, pinned above: it puts rows 1 and 2 in the SAME bucket and
    # therefore answers a different question than the one that was asked.
    defect = _fold(db, PRICE_MOVED_ONLY_DEFECT_EXPR, cce.FALLBACK_JOIN)
    assert defect["fallback_opening|flat"]["n"] == 3, (
        "the price_moved-only shape must pool the no-closing leg with the "
        "closing-price-that-held leg; if it does not, this control is vacuous"
    )
    assert "has_closing|flat" not in defect


# ---------------------------------------------------------------------------
# 3. The self-check the cross was added for.
# ---------------------------------------------------------------------------

def test_a_fallback_leg_can_never_read_as_moved(db):
    """``fallback_opening|moved`` is structurally impossible.

    ``price_moved`` requires ``calibration_probability IS NOT NULL``, so the two
    halves of the key cannot both fire. This is not decoration: if the sweep
    ever prints that key against production, the producer's flag and the raw
    column disagree about the same row, and THAT is the finding — it must be
    read before the numbers are.
    """
    got = _fold(db, cce.FALLBACK_EXPR, cce.FALLBACK_JOIN)
    assert "fallback_opening|moved" not in got

    # Non-vacuous: prove the key is REACHABLE by the expression, so that its
    # absence above is a fact about the data and not about the SQL. A row whose
    # flag lies produces exactly the key the sweep is told to watch for.
    db.execute("INSERT INTO futures_outcomes VALUES (9, 109, NULL, 0.5)")
    db.execute("INSERT INTO deduped VALUES (9, 109, 1, 0)")  # flag lies
    assert "fallback_opening|moved" in _fold(
        db, cce.FALLBACK_EXPR, cce.FALLBACK_JOIN)


# ---------------------------------------------------------------------------
# 4. Join cardinality — the silent one.
# ---------------------------------------------------------------------------

def test_the_join_is_one_to_one_and_does_not_fan_the_fold_out(db):
    """Total ``n`` must equal the row count of ``deduped``, exactly."""
    got = _fold(db, cce.FALLBACK_EXPR, cce.FALLBACK_JOIN)
    assert sum(v["n"] for v in got.values()) == len(SEED)

    # The defect arm: the same dimension joined on the market. Markets 100 and
    # 101 have two outcomes each, so it doubles them — 7 rows where there are 5,
    # and every share and win rate computed off it is wrong.
    fanned = _fold(db, cce.FALLBACK_EXPR, MARKET_JOIN_DEFECT_JOIN)
    assert sum(v["n"] for v in fanned.values()) == 9
    assert sum(v["n"] for v in fanned.values()) > len(SEED)


def test_the_two_price_origin_arms_partition_the_population(db):
    """Every row lands in exactly one arm; neither arm is a filter."""
    got = _fold(db, cce.FALLBACK_EXPR, cce.FALLBACK_JOIN)
    fallback = sum(v["n"] for k, v in got.items() if k.startswith("fallback_"))
    has_closing = sum(v["n"] for k, v in got.items() if k.startswith("has_closing"))
    assert fallback + has_closing == len(SEED)
    assert fallback == 2 and has_closing == 3

    # The plain two-way share the parked question asks for is recoverable by
    # summing over the suffix — the cross must not have cost the answer.
    assert fallback / len(SEED) == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# 5. Wiring, and that the thing we compose is Postgres.
# ---------------------------------------------------------------------------

def test_the_dimension_is_reachable_from_the_command_line():
    assert "fallback" in cce.DIMENSIONS
    # A per-chunk dimension needs a matching PER_CHUNK_CONTEXT entry; this one
    # is static, so it must be in neither table or it is a KeyError at start-up.
    assert "fallback" not in cce.PER_CHUNK_DIMENSIONS
    assert "fallback" not in cce.PER_CHUNK_CONTEXT
    choices = sorted(set(cce.DIMENSIONS) | set(cce.PER_CHUNK_DIMENSIONS))
    assert "fallback" in choices


def test_the_composed_statement_is_one_postgres_statement():
    """The rail sends this verbatim to ``db-query``, which refuses multi-statement.

    ``_strip_sql_comments`` runs first because the producer's SQL carries prose
    comments containing semicolons; a second statement here would be refused at
    the endpoint, and a chunk that never runs reads as a class that is empty.
    """
    sqlglot = pytest.importorskip("sqlglot")
    sql = cce.cell_sql("kalshi", "entertainment", 1, 1000, "fallback")
    assert len(sqlglot.parse(sql, read="postgres")) == 1
    assert ";" not in sql
    assert len(sql) < cce.MAX_SQL_CHARS


def test_the_dimension_is_admissible_on_the_whole_vm_rail():
    """🔴 THE RAIL THIS IS ACTUALLY MEANT TO BE RUN ON.

    ``calibration_cell_exact`` shards on ``fm.id``, and an id-range shard is
    INADMISSIBLE for a curve-price question: ``virtual_market`` counts group and
    event sizes over ``market_info``, so a chunk holding 2 of an event's 4
    markets fails the ``>= 3`` gate and re-assigns them from ``e:`` to ``m:`` —
    which changes ``is_grouped``, the dedup, the ``mex_field_divisor`` and the
    normalization gate, and therefore which bin a leg lands in. CAL-P124
    measured the damage at **-35.85% of published rows** on one cell.

    ``calibration_whole_vm_fold`` (CAL-P125) is the admissible rail: it freezes
    the generation once and replays it per unit through
    ``frozen_vm_roster=True`` + the producer's own ``plan_units``, so a
    ``vm_id`` is never split. It reads ``cce.DIMENSIONS`` directly, so
    registering on the shared table is what makes ``--by fallback`` available
    there — and this test is what stops that being an accident.
    """
    wvf = _load("calibration_whole_vm_fold")
    assert "fallback" in wvf.cce.DIMENSIONS

    # The whole-vm rail REFUSES id-range dimensions by name. If ``fallback``
    # ever became one, the runbook command would start raising instead of
    # quietly returning a wrong answer — but it would still stop working.
    assert "fallback" not in wvf.cce.PER_CHUNK_DIMENSIONS

    class _Unit:
        index = 0
        market_ids = [101, 102, 103]

    assignment = {101: ("g:1", True), 102: ("g:1", True), 103: ("e:2", False)}
    sql = wvf.unit_sql(_Unit(), assignment, "fallback", None)

    sqlglot = pytest.importorskip("sqlglot")
    assert len(sqlglot.parse(sql, read="postgres")) == 1
    assert ";" not in sql
    assert "futures_outcomes fbk" in sql
    # The frozen roster really was inlined — this is what makes the unit a
    # replay of one global derivation rather than a re-derivation on a subset.
    assert "ARRAY[" in sql


def test_the_join_reaches_the_outcome_primary_key():
    """Cardinality is a property of the ON clause, so pin the ON clause.

    ``deduped`` is ``SELECT ro.*`` over ``normalized``, which projects
    ``fo.id AS outcome_id`` — if that projection is ever dropped the join
    silently becomes a cross product against a NULL key, which SQLite cannot
    show us and Postgres will not complain about.
    """
    assert "fbk.id = d.outcome_id" in cce.FALLBACK_JOIN.replace("  ", " ")
    sql = cce.cell_sql("kalshi", "entertainment", 1, 1000, "fallback")
    assert "fo.id AS outcome_id" in sql
