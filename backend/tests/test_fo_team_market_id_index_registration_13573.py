"""#13573: `ix_fo_team_market_id` is DECLARED in the model and BUILT only by hand.

`futures_outcomes` (~8.8 M rows / 9.4 GB) cannot take an Alembic index build
during the release phase (gotcha #31). Declaring `ix_fo_team_market_id` on
`FuturesOutcome` keeps future `--autogenerate` revisions from proposing a drop
once the attended `CREATE INDEX CONCURRENTLY` runbook runs.
"""

from __future__ import annotations

import ast
from pathlib import Path

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateIndex

from app.models.models import FuturesOutcome

INDEX_NAME = "ix_fo_team_market_id"
PREDICATE = "team_id IS NOT NULL"
EXPECTED_PG_DDL = (
    "CREATE INDEX ix_fo_team_market_id ON futures_outcomes (team_id, market_id) "
    "INCLUDE (id) WHERE team_id IS NOT NULL"
)

BACKEND = Path(__file__).resolve().parents[1]
RUNBOOK = (
    BACKEND.parent
    / "artifacts"
    / "speed-index-13573"
    / "RUNBOOK-ix_fo_team_market_id.md"
)


def _the_index():
    matches = [i for i in FuturesOutcome.__table__.indexes if i.name == INDEX_NAME]
    assert len(matches) == 1, (
        f"{INDEX_NAME} must be declared once on FuturesOutcome; found {len(matches)}"
    )
    return matches[0]


def _squash(sql: str) -> str:
    return " ".join(sql.split())


def test_the_declared_index_is_the_reviewed_definition() -> None:
    idx = _the_index()
    assert [c.name for c in idx.columns] == ["team_id", "market_id"]
    assert idx.unique is False
    assert list(idx.dialect_options["postgresql"]["include"]) == ["id"]
    assert _squash(str(idx.dialect_options["postgresql"]["where"])) == PREDICATE
    assert _squash(str(idx.dialect_options["sqlite"]["where"])) == PREDICATE


def test_the_compiled_postgres_ddl_is_the_runbook_statement() -> None:
    ddl = _squash(str(CreateIndex(_the_index()).compile(dialect=postgresql.dialect())))
    assert ddl == EXPECTED_PG_DDL
    runbook = _squash(RUNBOOK.read_text(encoding="utf-8"))
    expected_with_concurrently = EXPECTED_PG_DDL.replace(
        "CREATE INDEX ", "CREATE INDEX CONCURRENTLY IF NOT EXISTS ", 1
    )
    assert expected_with_concurrently in runbook


def test_sqlite_declaration_compiles_cleanly() -> None:
    ddl = _squash(str(CreateIndex(_the_index()).compile(dialect=sqlite.dialect())))
    assert ddl.endswith(f"WHERE {PREDICATE}")


def _executed_strings(src: str) -> list[str]:
    tree = ast.parse(src)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and id(n) not in docstrings
    ]


def test_no_migration_builds_it() -> None:
    versions = BACKEND / "alembic" / "versions"
    files = sorted(versions.glob("*.py"))
    assert files, f"no migrations found under {versions}"
    offenders = [
        p.name
        for p in files
        if any(
            INDEX_NAME in s for s in _executed_strings(p.read_text(encoding="utf-8"))
        )
    ]
    assert offenders == [], (
        f"{INDEX_NAME} must NOT be executed inside an Alembic migration: {offenders}"
    )
