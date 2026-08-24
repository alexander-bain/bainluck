"""The real-Postgres gates seed with raw INSERT — so their columns must be complete.

WHY THIS EXISTS. The `*_pg.py` gates under `tests/integration/` are skipped
unless a throwaway Postgres is reachable, and there is none in the agent sandbox
(`initdb` dies on `shmget`). So a seed statement that is missing a NOT NULL
column is invisible locally: the file collects, the tests skip, the run is
green, and the defect surfaces for the first time inside CI's `search-recall`
job — which `deploy` needs, so it turns a DEPLOY GATE red for a reason with
nothing to do with what the gate is guarding.

That is not hypothetical. CAL-P090 shipped
`test_calibration_mode_price_source_scope_pg.py` with `futures_markets.external_id`,
`futures_markets.name` and `futures_outcomes.external_id` absent from its
INSERTs — all three NOT NULL with no default. CAL-P090's own report recorded the
file as "COLLECTED but never EXECUTED", which is precisely why nobody found out.
CAL-P091 repaired it.

WHAT THIS CHECKS, and what it deliberately does not. It is a STATIC check: it
reads the INSERT statements out of the gate files and compares their column
lists against the ORM metadata. It cannot tell you the gate passes. It tells you
the gate will get far enough to fail for its own reasons — which is the entire
gap that let the last instance through.

A raw INSERT bypasses SQLAlchemy's Python-side `default=`, so a column carrying
one is NOT excused here the way it would be on an ORM insert; only a
`server_default` is. That asymmetry is the trap this file is named after.
"""

import re
from pathlib import Path

import pytest

from app.models.models import Base

#: The raw-INSERT gate files this check covers. Add a file here when you add a
#: real-Postgres gate that seeds with `session.execute(text("INSERT ..."))` —
#: the discovery arm below fails if such a gate grows an INSERT and is not
#: listed, so this list cannot silently fall behind.
COVERED = (
    "test_calibration_mode_price_source_scope_pg.py",
    "test_calibration_mode_price_source_scope_peers_pg.py",
    "test_create_wave_insert_bind_contract.py",
    "test_kalshi_cliff_bind_contract.py",
)

INTEGRATION_DIR = Path(__file__).parent / "integration"

#: `INSERT INTO <table> (<cols>)`, tolerating the string concatenation these
#: statements are written with (`"INSERT INTO t (a, b, " "c) VALUES ..."`).
_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+(\w+)\s*\(((?:[^()]|\"\s*\")*)\)\s*(?:\"\s*\")?\s*VALUES",
    re.IGNORECASE,
)


def _columns(raw: str) -> set[str]:
    """Column names out of an INSERT's column list, un-concatenating the source."""
    joined = re.sub(r'"\s*\n?\s*"', "", raw)
    return {c.strip() for c in joined.split(",") if c.strip()}


def _inserts(path: Path):
    return [
        (m.group(1).lower(), _columns(m.group(2)))
        for m in _INSERT_RE.finditer(path.read_text())
    ]


def _required(table_name: str) -> set[str]:
    """NOT NULL columns a raw INSERT must supply itself.

    Excused: anything with a `server_default` (the database fills it) and
    primary keys the database can autoincrement. NOT excused: a Python-side
    `default=`, because `text("INSERT ...")` never runs it.
    """
    table = Base.metadata.tables[table_name]
    required = set()
    for col in table.columns:
        if col.nullable or col.server_default is not None:
            continue
        if col.primary_key and col.autoincrement is not False:
            continue
        required.add(col.name)
    return required


@pytest.mark.parametrize("filename", COVERED)
def test_pg_gate_inserts_supply_every_not_null_column(filename):
    path = INTEGRATION_DIR / filename
    assert path.exists(), f"{filename} is listed in COVERED but does not exist"

    statements = _inserts(path)
    assert statements, (
        f"{filename} is listed as a raw-INSERT gate but no INSERT was parsed out "
        "of it. Either it stopped seeding that way (drop it from COVERED) or the "
        "regex stopped matching (fix the regex) — silently checking nothing is "
        "the one outcome this file exists to prevent."
    )

    missing = []
    for table, provided in statements:
        assert table in Base.metadata.tables, (
            f"{filename} inserts into unknown table {table!r}"
        )
        gap = _required(table) - provided
        if gap:
            missing.append((table, sorted(gap)))

    assert not missing, (
        f"{filename} seeds with raw INSERT and omits NOT NULL columns with no "
        f"server default: {missing}. This gate cannot run — it dies on "
        "NotNullViolationError before reaching its assertion, and because it is "
        "skipped without a Postgres you will only find out in CI, on a job "
        "`deploy` needs."
    )


def test_every_raw_insert_gate_is_covered():
    """No real-Postgres gate may seed with raw INSERT and escape the check above.

    A gate is identified by its `*TEST_DATABASE_URL` env gate, NOT by filename —
    `*_pg.py` is a convention several of these gates predate. Do NOT widen this
    to every file containing an INSERT: `test_route_admin_db_query.py` carries
    `"INSERT INTO events (id) VALUES (1)"` as a rejection fixture, an INSERT
    that is SUPPOSED to be invalid, and flagging it would be a false red on a
    test doing its job.
    """
    uncovered = sorted(
        p.name
        for p in INTEGRATION_DIR.glob("test_*.py")
        if p.name not in COVERED
        and "TEST_DATABASE_URL" in p.read_text()
        and _inserts(p)
    )
    assert not uncovered, (
        f"these real-Postgres gates seed with raw INSERT but are not in COVERED: "
        f"{uncovered}. Add them — a gate whose seed is unchecked is a gate that "
        "will first report its own bug as a red deploy."
    )
