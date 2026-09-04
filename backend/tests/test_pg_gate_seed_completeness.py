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

CAL-P157 added the second half — `test_every_real_postgres_gate_is_wired_into_ci`.
A complete seed proves the gate CAN run; it says nothing about whether anything
ever runs it, and `search-recall` names its gate files one hand-written step at a
time. The discovery arm found `test_feed_static_tag_filter_pg.py`, which is
gated on `SEARCH_TEST_DATABASE_URL`, skips everywhere else, and is named by no
step — so it has never executed once. It is allowlisted rather than wired here
(turning on a gate that has never run belongs to whoever owns the feed, not to a
model-parity queue) and reported, but nothing NEW can join it.
"""

import re
from pathlib import Path

import pytest
import yaml

from app.models.models import Base

#: The raw-INSERT gate files this check covers. Add a file here when you add a
#: real-Postgres gate that seeds with `session.execute(text("INSERT ..."))` —
#: the discovery arm below fails if such a gate grows an INSERT and is not
#: listed, so this list cannot silently fall behind.
COVERED = (
    "test_bookmaker_count_real_postgres.py",
    "test_calibration_mode_price_source_scope_pg.py",
    "test_calibration_mode_price_source_scope_peers_pg.py",
    "test_calibration_vm_variant_join_pg.py",
    "test_create_wave_insert_bind_contract.py",
    "test_feed_static_tag_filter_pg.py",
    "test_futures_outcome_grade_schema_parity_pg.py",
    "test_kalshi_cliff_bind_contract.py",
    "test_rekey_statpal_anchors_real_postgres.py",
)

INTEGRATION_DIR = Path(__file__).parent / "integration"

#: Adjacent Python string literals, so the source is un-concatenated ONCE up
#: front instead of the pattern below having to tolerate a `" "` join at each
#: place one might appear.
#:
#: 🔴 LAT-P163: it used to tolerate the join only INSIDE the column list, so
#: `"INSERT INTO t "` newline `"(a, b) VALUES ..."` — the join sitting between
#: the table name and the opening paren — matched nothing. That is not a
#: cosmetic miss. `test_bookmaker_count_real_postgres.py` was written that way
#: and this file parsed **1 of its 3 INSERTs**, silently skipping the two that
#: carried the client-side-default columns, which is exactly the defect class
#: this file is named after. The "no INSERT was parsed" tripwire could not fire,
#: because one statement HAD parsed. A guard that checks a subset is worse than
#: no guard: it is counted.
_LITERAL_JOIN_RE = re.compile(r'"\s*(?:\n\s*)?"')

#: `INSERT INTO <table> (<cols>) VALUES`, against already-joined source.
_INSERT_RE = re.compile(r"INSERT\s+INTO\s+(\w+)\s*\(([^()]*)\)\s*VALUES", re.IGNORECASE)

#: Every literal `INSERT INTO` in the source, matched or not. The count of these
#: must equal the count the pattern above extracts, or the pattern is reading a
#: subset and nothing else in this file can tell.
_INSERT_ANY_RE = re.compile(r"INSERT\s+INTO", re.IGNORECASE)


def _columns(raw: str) -> set[str]:
    """Column names out of an INSERT's column list."""
    return {c.strip() for c in raw.split(",") if c.strip()}


def _joined_source(path: Path) -> str:
    return _LITERAL_JOIN_RE.sub("", path.read_text())


def _inserts(path: Path):
    return [
        (m.group(1).lower(), _columns(m.group(2)))
        for m in _INSERT_RE.finditer(_joined_source(path))
    ]


def _insert_keywords(path: Path) -> int:
    return len(_INSERT_ANY_RE.findall(_joined_source(path)))


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

    # LAT-P163: and silently checking SOME of it is the outcome the assertion
    # above cannot see. Parsing one statement out of three satisfies "not empty"
    # while leaving the other two unchecked, which is how this file was green
    # over `test_bookmaker_count_real_postgres.py` while two of its INSERTs were
    # invisible to it.
    keywords = _insert_keywords(path)
    assert len(statements) == keywords, (
        f"{filename} contains {keywords} `INSERT INTO` statements but only "
        f"{len(statements)} parsed. The unparsed ones are NOT being checked and "
        "nothing else here can tell. Fix the pattern rather than the file — a "
        "seed that this check cannot read is a seed it is not guarding."
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


#: Real-Postgres gates that exist, cannot run outside CI, and that no CI step
#: invokes. Every name here has NEVER EXECUTED. This is a disclosure, not a
#: permission: it is frozen at the set CAL-P157 measured, so a new gate cannot
#: join it silently.
#:
#: `test_feed_static_tag_filter_pg.py` — found by the arm below, owned by the
#: feed, not wired here because switching on a never-run gate is a change whose
#: blast radius belongs to the lane that can read its failures.
_NEVER_WIRED = {"test_feed_static_tag_filter_pg.py"}

CI_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def test_every_real_postgres_gate_is_wired_into_ci():
    """A gate no CI step names is a gate that has never once run.

    These files skip on every machine a human or an agent uses — `initdb` dies on
    `shmget` in the sandbox — so `search-recall` is their only reader, and it
    names each file in a hand-written step. Adding the file is therefore not
    adding the gate, and the difference is invisible: the suite goes green either
    way, and "0 skipped" is only asserted inside the step that does not exist.

    `test_search_latency_contract.py` already makes this check, parametrized over
    two hardcoded search gates. Hardcoding is what let a third slip past, so this
    one DISCOVERS instead.
    """
    workflow = yaml.safe_load(CI_WORKFLOW.read_text())
    job = workflow["jobs"]["search-recall"]
    invoked = "\n".join(s.get("run") or "" for s in job["steps"])

    unwired = sorted(
        p.name
        for p in INTEGRATION_DIR.glob("test_*.py")
        if p.name not in _NEVER_WIRED
        and "TEST_DATABASE_URL" in p.read_text()
        and f"tests/integration/{p.name}" not in invoked
    )
    assert not unwired, (
        f"these gates require a real Postgres and no `search-recall` step runs "
        f"them: {unwired}. They skip everywhere else, so they have never "
        f"executed — add a step (with the all-skipped detector its neighbours "
        f"carry) rather than letting the file's existence read as coverage."
    )


def test_the_never_wired_allowlist_has_not_grown_stale():
    """An allowlist that outlives its entries is the next silent gap.

    If a name here gets wired, or deleted, this fails and the disclosure comes
    out with it.
    """
    workflow = yaml.safe_load(CI_WORKFLOW.read_text())
    invoked = "\n".join(
        s.get("run") or "" for s in workflow["jobs"]["search-recall"]["steps"]
    )
    stale = sorted(
        name
        for name in _NEVER_WIRED
        if not (INTEGRATION_DIR / name).exists()
        or f"tests/integration/{name}" in invoked
    )
    assert not stale, (
        f"these names are allowlisted as never-wired but are now wired or gone: "
        f"{stale}. Remove them from _NEVER_WIRED."
    )
