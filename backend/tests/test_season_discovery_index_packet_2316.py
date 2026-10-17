"""#2316 / P144-1: the proposed discovery indexes still fit the route's statement.

The runbook (`docs/audits/latency/2316-p144-1-season-discovery-index-runbook.md`)
proposes three partial indexes, one per kind of arm in the season-discovery
sport OR, all `WHERE market_tier IN (1, 2, 3, 4)`. The planner can only swap
the full-table scan for them while BOTH of these hold:

* every arm of the OR is one the three indexes serve. One extra arm kind, such
  as a `name ILIKE`, puts the whole statement back on a Seq Scan, and nothing
  else would notice;
* the statement ANDs the same tier list the partial predicate names, so the
  planner can prove each index covers it.

These checks drive the REAL `_build_related_futures`, through the runbook's own
generator, and inspect the statement it issues. They are not reading source
text. If one fails, the runbook's index set has to be re-derived before anyone
builds or keeps those indexes.
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
from pathlib import Path

import pytest
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList, Grouping

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
RUNBOOK = REPO / "docs/audits/latency/2316-p144-1-season-discovery-index-runbook.md"
GENERATOR = BACKEND / "scripts/season_discovery_admission_sql.py"

TIER_LIST = [1, 2, 3, 4]
# (column, operator) arm kinds -> the runbook index that serves them.
SERVED_ARMS = {
    ("external_id", operators.like_op): "ix_fm_t14_external_id_trgm",
    ("external_id", operators.ilike_op): "ix_fm_t14_external_id_trgm",
    ("llm_sport_category", operators.eq): "ix_fm_t14_llm_sport_category",
    ("sport_id", operators.in_op): "ix_fm_t14_sport_id",
}
# One key per sport family the route maps, plus both gendered/mens-specific
# branches of `ext_id_patterns`.
SPORT_KEYS = [
    "americanfootball_ncaaf",
    "americanfootball_nfl",
    "baseball_mlb",
    "basketball_nba",
    "basketball_wnba",
    "basketball_ncaab",
    "icehockey_nhl",
    "soccer_epl",
    "tennis_atp_us_open",
    "mma_mixed_martial_arts",
    "boxing_boxing",
    "golf_masters_tournament_winner",
]


def _generator():
    spec = importlib.util.spec_from_file_location("season_discovery_admission_sql", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _discovery(sport_key: str, finished: bool):
    session = asyncio.run(_generator().capture(sport_key, finished))
    assert session.discovery_stmt is not None, (
        f"{sport_key}: the route issued no season-discovery statement"
    )
    return session.discovery_stmt


def _column(expr) -> str | None:
    return getattr(expr, "name", None) if getattr(expr, "table", None) is not None else None


def _bare(clause):
    """Strip the parentheses SQLAlchemy adds around a nested OR."""
    while isinstance(clause, Grouping):
        clause = clause.element
    return clause


def _and_clauses(stmt):
    where = _bare(stmt.whereclause)
    if isinstance(where, BooleanClauseList) and where.operator is operators.and_:
        return [_bare(c) for c in where.clauses]
    return [where]


def _sport_or(stmt) -> BooleanClauseList:
    """The OR whose arms include the category arm (the status OR has none)."""
    for clause in _and_clauses(stmt):
        if isinstance(clause, BooleanClauseList) and clause.operator is operators.or_:
            if any(
                isinstance(arm, BinaryExpression) and _column(arm.left) == "llm_sport_category"
                for arm in map(_bare, clause.clauses)
            ):
                return clause
    raise AssertionError("no sport OR (one carrying the llm_sport_category arm) in the statement")


def _runbook_indexes() -> dict[str, str]:
    text = RUNBOOK.read_text()
    found = {}
    for m in re.finditer(
        r"CREATE INDEX CONCURRENTLY\s+(?P<if>IF NOT EXISTS\s+)?(?P<name>\w+)\s+ON futures_markets"
        r"(?P<body>[^;]*);",
        text,
    ):
        assert not m.group("if"), (
            f"{m.group('name')}: IF NOT EXISTS silently skips an INVALID leftover"
        )
        body = " ".join(m.group("body").split())
        assert found.setdefault(m.group("name"), body) == body, (
            f"{m.group('name')} is written two different ways in the runbook"
        )
    return found


@pytest.mark.parametrize("finished", [True, False], ids=["finished", "live"])
@pytest.mark.parametrize("sport_key", SPORT_KEYS)
def test_every_arm_of_the_sport_or_is_one_the_runbook_indexes_serve(sport_key, finished):
    arms = _sport_or(_discovery(sport_key, finished)).clauses
    kinds = []
    for arm in map(_bare, arms):
        assert isinstance(arm, BinaryExpression), f"{sport_key}: unrecognised arm {arm}"
        kind = (_column(arm.left), arm.operator)
        assert kind in SERVED_ARMS, (
            f"{sport_key}: arm {arm} is not served by any runbook index, so the "
            "planner falls back to a full scan; re-derive the index set"
        )
        kinds.append(kind)
    # The category arm is the one P144-1 as filed left unserved; it must be here.
    assert ("llm_sport_category", operators.eq) in kinds


@pytest.mark.parametrize("finished", [True, False], ids=["finished", "live"])
@pytest.mark.parametrize("sport_key", ["americanfootball_ncaaf", "baseball_mlb", "golf_masters_tournament_winner"])
def test_the_statement_ands_the_tier_list_the_partial_predicates_name(sport_key, finished):
    tiers = [
        c
        for c in _and_clauses(_discovery(sport_key, finished))
        if isinstance(c, BinaryExpression)
        and _column(c.left) == "market_tier"
        and c.operator is operators.in_op
    ]
    assert len(tiers) == 1, "the discovery statement no longer ANDs one market_tier IN (...)"
    assert list(tiers[0].right.value) == TIER_LIST


def test_the_runbook_defines_one_partial_index_per_served_arm_kind():
    indexes = _runbook_indexes()
    assert set(indexes) == set(SERVED_ARMS.values())
    expected_columns = {
        "ix_fm_t14_external_id_trgm": "USING gin (external_id gin_trgm_ops)",
        "ix_fm_t14_llm_sport_category": "(llm_sport_category)",
        "ix_fm_t14_sport_id": "(sport_id)",
    }
    tier_sql = "WHERE market_tier IN (" + ", ".join(map(str, TIER_LIST)) + ")"
    for name, body in indexes.items():
        assert body.startswith(expected_columns[name]), f"{name}: {body}"
        assert body.endswith(tier_sql), f"{name} must be partial on exactly {tier_sql}"


def test_none_of_these_indexes_is_built_by_an_alembic_migration():
    """Gotcha #31: CONCURRENTLY inside the release phase hangs it."""
    versions = BACKEND / "alembic/versions"
    hits = [
        p.name
        for p in versions.glob("*.py")
        if "ix_fm_t14_" in p.read_text(errors="ignore")
    ]
    assert hits == []


def test_the_generator_prints_a_psql_block_with_the_route_s_sport_ids_variable():
    gen = _generator()
    session = asyncio.run(gen.capture("americanfootball_ncaaf", True))
    block = gen.psql_block(session, "americanfootball_ncaaf", True)
    assert "\\gset" in block
    assert "sport_id IN (:sport_ids)" in block
    assert str(gen.SENTINEL_SPORT_ID) not in block
    assert "LIKE 'americanfootball_ncaaf%'" in block  # no `%%` from a pyformat dialect
    assert "market_tier IN (1, 2, 3, 4)" in block
