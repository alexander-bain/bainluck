"""#2408: the A11 outer-population index is DECLARED in the model and BUILT only by hand.

PILLAR: TRUTH. SHIP: futures rows and Discover cards show a truthful dated 24-hour
move within the task budget.

The dated-24h statement (A11) reads every ungraded, priced `futures_outcomes`
row touched in the last 24 hours. Production's plan reaches that population
through the full `ix_futures_outcomes_last_updated`, so every re-stamped graded
row costs a heap visit too. On 2026-10-16 that outer read alone hit the 25 s
statement timeout. `ix_fo_unresolved_priced_last_updated` is the attended
substrate for it. The local rig is in artifacts/2408-index-prereq-20261016.

Three things are pinned here, and each one is a way the substrate can quietly
stop being the thing that was reviewed:

1. The declared definition: key, predicate, no INCLUDE, non-unique. The
   predicate has to stay A11's own two clauses verbatim. Any drift can stop the
   planner proving the index is usable, and nothing fails when that happens.
2. A plain key. A covering variant was measured and rejected: it skips the heap
   only on all-visible pages, a re-stamp clears that bit until vacuum sets it
   again, and in the rig's churn state it saved nothing. That is the tested
   state, not an invariant.
3. No migration executes it. Gotcha #31: a concurrent build inside the release
   phase is the May 22 outage. A non-concurrent one locks the pollers out.

No database is needed. A guard for an attended index must not skip on the
machine that would change it.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateIndex

from app.models.models import FuturesOutcome

INDEX_NAME = "ix_fo_unresolved_priced_last_updated"
PREDICATE = "resolution_source IS NULL AND current_probability IS NOT NULL"
# The exact statement the attended packet runs (without CONCURRENTLY, which the
# compiler does not emit for a declared index).
EXPECTED_PG_DDL = (
    "CREATE INDEX ix_fo_unresolved_priced_last_updated ON futures_outcomes "
    "(last_updated) WHERE resolution_source IS NULL AND current_probability IS NOT NULL"
)

BACKEND = Path(__file__).resolve().parents[1]


def _the_index():
    matches = [i for i in FuturesOutcome.__table__.indexes if i.name == INDEX_NAME]
    assert len(matches) == 1, (
        f"{INDEX_NAME} must be declared exactly once on FuturesOutcome; found "
        f"{len(matches)}. Without the declaration the first --autogenerate after "
        "the attended build proposes dropping it."
    )
    return matches[0]


def _squash(sql: str) -> str:
    return " ".join(sql.split())


def test_the_declared_index_is_the_reviewed_definition() -> None:
    idx = _the_index()
    assert [c.name for c in idx.columns] == ["last_updated"]
    assert idx.unique is False
    assert _squash(str(idx.dialect_options["postgresql"]["where"])) == PREDICATE
    assert _squash(str(idx.dialect_options["sqlite"]["where"])) == PREDICATE


def test_the_compiled_postgres_ddl_is_the_packet_statement() -> None:
    ddl = _squash(str(CreateIndex(_the_index()).compile(dialect=postgresql.dialect())))
    assert ddl == EXPECTED_PG_DDL


def test_the_index_is_a_plain_key_not_a_covering_one() -> None:
    idx = _the_index()
    assert not idx.dialect_options["postgresql"]["include"], (
        "a covering INCLUDE was measured and rejected for #2408: it saves heap "
        "visits only on all-visible pages, and every row in A11's range was "
        "written inside the last 24 hours"
    )
    ddl = str(CreateIndex(idx).compile(dialect=postgresql.dialect()))
    assert "INCLUDE" not in ddl.upper()


def test_the_sqlite_declaration_compiles_with_the_same_predicate() -> None:
    ddl = _squash(str(CreateIndex(_the_index()).compile(dialect=sqlite.dialect())))
    assert ddl.endswith(f"WHERE {PREDICATE}")


def _executed(src: str) -> str:
    """Source without docstrings and comments, i.e. the code that runs."""
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = re.sub(r"'''(?:.|\n)*?'''", "", src)
    return "\n".join(re.sub(r"#.*$", "", line) for line in src.split("\n"))


def test_no_migration_builds_it() -> None:
    versions = BACKEND / "alembic" / "versions"
    files = sorted(versions.glob("*.py"))
    assert files, f"no migrations found under {versions}; the scan would be vacuous"
    offenders = [
        p.name
        for p in files
        if INDEX_NAME in _executed(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        f"{INDEX_NAME} is built by a migration: {offenders}. Gotcha #31: build it "
        "by the attended CREATE INDEX CONCURRENTLY packet, never in the release phase."
    )
