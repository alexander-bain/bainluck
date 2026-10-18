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

The second half holds the attended packet together (lane1b's review of
5d5854e5c1, R1-R10): the gate criteria cannot be loosened in one copy only,
the rollback cannot name an index the build did not create, the gate file
never inherits the build's `statement_timeout = 0` and observes the sixth
prepared execution, and `models.py` declares the indexes exactly when the
runbook says they are KEPT.
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
MODELS = BACKEND / "app/models/models.py"

INDEX_NAMES = {
    "ix_fm_t14_external_id_trgm",
    "ix_fm_t14_llm_sport_category",
    "ix_fm_t14_sport_id",
}
# R2: one statement per distinct arm shape the claim covers.
GATE_SPORTS = ("americanfootball_ncaaf", "baseball_mlb", "soccer_epl", "basketball_other")
# R1/R7: written out here a third time on purpose. Loosening the gate means
# editing the runbook, the generator AND this literal.
GATE_CRITERIA = {
    "statement_timeout": "30s",
    "every_index_valid": "yes",
    "seq_scan_on_futures_markets": "none",
    "bitmapor_lists_all_three_indexes": "yes",
    "lossy_heap_blocks": "0",
    "max_exact_heap_blocks": "3000",
    "max_execution_ms": "2000",
    "generic_plans_after_sixth": "0",
    "max_trgm_bytes_per_t14_row_at_build": "330",
    "max_btree_bytes_per_t14_row_at_build": "40",
}
ACCEPTANCE_CRITERIA = {
    "window_starts_hours_after_build": "6",
    "window_hours": "24",
    "window_may_extend_to_hours": "72",
    "min_finished_shape_calls": "10",
    "max_mean_exec_ms": "2000",
    "max_trgm_bytes_per_t14_row_steady": "1000",
    "on_failure": "section 4 rollback",
}

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
        # R10: the pending list stays on, pinned at 4 MB on the index itself.
        "ix_fm_t14_external_id_trgm": (
            "USING gin (external_id gin_trgm_ops) "
            "WITH (fastupdate = on, gin_pending_list_limit = 4096)"
        ),
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


def _block(sport_key="americanfootball_ncaaf", finished=True):
    gen = _generator()
    session = asyncio.run(gen.capture(sport_key, finished))
    return gen.psql_block(session, sport_key, finished)


def test_the_generator_prints_a_psql_block_with_the_route_s_sport_ids_variable():
    block = _block()
    assert "\\gset" in block
    assert "sport_id IN (:sport_ids)" in block
    assert str(_generator().SENTINEL_SPORT_ID) not in block
    assert "'americanfootball_ncaaf%'" in block  # no `%%` from a pyformat dialect
    assert "market_tier IN ($" in block  # the tier list stays a bind, as asyncpg sends it


def test_the_prepared_statement_s_binds_and_arguments_line_up():
    lines = _block().splitlines()
    body = "\n".join(lines[lines.index("PREPARE season_discovery_2316 AS") + 1:])
    body = body[: body.index(";\n")]
    numbers = sorted({int(n) for n in re.findall(r"\$(\d+)", body)})
    assert numbers == list(range(1, len(numbers) + 1))
    analyze = next(ln for ln in lines if ln.startswith("EXPLAIN (ANALYZE, BUFFERS) EXECUTE"))
    args = analyze[analyze.index("(", len("EXPLAIN (ANALYZE, BUFFERS) EXECUTE")) + 1 : -2]
    # Every argument is a quoted literal, a number or a typed timestamp, so a
    # plain split on ", " outside quotes counts them.
    count = len(re.findall(r"'(?:[^']|'')*'(?:::timestamptz)?|\b\d+\b", args))
    assert count == len(numbers)
    assert args.endswith("1, 2, 3, 4")  # the tier binds come last, in order


def test_the_gate_block_never_inherits_the_build_timeout_and_reads_the_sixth_execution():
    """R3 + R4 + nit (a), in the order psql runs them."""
    lines = _block().splitlines()
    idx = {ln: i for i, ln in enumerate(lines)}

    def at(prefix):
        hits = [i for i, ln in enumerate(lines) if ln.startswith(prefix)]
        assert hits, f"no line starting {prefix!r}"
        return hits

    timeout = at("SET statement_timeout = '30s';")
    assert len(timeout) == 1
    assert timeout[0] < at("PREPARE ")[0] < at("EXPLAIN ")[0]
    assert idx["\\unset sport_ids"] < at("SELECT string_agg(")[0]
    assert lines[idx["\\if :{?sport_ids}"] - 1].endswith("\\gset")
    assert idx["\\if :{?sport_ids}"] < at("PREPARE ")[0] < idx["\\else"] < idx["\\endif"]
    assert lines[idx["\\else"] + 1].startswith("\\echo ABORT americanfootball_ncaaf")
    plans = at("EXPLAIN EXECUTE season_discovery_2316(")
    assert len(plans) == 5
    assert idx["\\o /dev/null"] < plans[0] and plans[-1] < idx["\\o"]
    analyze = at("EXPLAIN (ANALYZE, BUFFERS) EXECUTE season_discovery_2316(")
    assert analyze == [idx["\\o"] + 1]
    assert "pg_prepared_statements" in lines[analyze[0] + 1]
    assert "generic_plans" in lines[analyze[0] + 1]


def test_the_gate_set_covers_every_arm_shape_the_claim_covers():
    gen = _generator()
    assert tuple(gen.GATE_SPORTS) == GATE_SPORTS
    gate = gen.gate_set()
    assert gate.count("SET statement_timeout = '30s';") == len(GATE_SPORTS)
    for sport_key in GATE_SPORTS:
        assert f"-- #2316 season-market discovery, {sport_key} / finished shape." in gate
    # The two generic-prefix shapes: every sport id of the family plus a
    # family-wide LIKE, the broadest bitmaps.
    assert "WHERE sports.key LIKE 'soccer%' \\gset" in gate
    assert "WHERE sports.key LIKE 'basketball%' \\gset" in gate
    assert "'soccer%'" in gate and "'basketball%'" in gate
    assert "'KXMLB%'" in gate


def _fenced(tag: str) -> dict[str, str]:
    m = re.search(rf"```text {tag}\n(.*?)```", RUNBOOK.read_text(), re.S)
    assert m, f"the runbook has no `{tag}` block"
    pairs = [ln.split(" = ", 1) for ln in m.group(1).strip().splitlines()]
    return {k.strip(): v.strip() for k, v in pairs}


def test_the_gate_criteria_are_one_table_in_three_places():
    """R1/R7: loosening a bound, or deleting one, fails here."""
    gen = _generator()
    assert _fenced("gate-criteria") == GATE_CRITERIA
    assert gen.GATE_CRITERIA == GATE_CRITERIA
    block = _block()
    for key, value in GATE_CRITERIA.items():
        assert f"--   {key} = {value}" in block


def test_the_final_keep_is_a_cold_path_acceptance_written_down_before_the_build():
    assert _fenced("acceptance-criteria") == ACCEPTANCE_CRITERIA
    assert _generator().ACCEPTANCE_CRITERIA == ACCEPTANCE_CRITERIA


def _section(title_start: str) -> str:
    text = RUNBOOK.read_text()
    start = text.index(f"\n## {title_start}")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_every_name_list_in_the_runbook_is_the_create_set():
    """R6: a misspelt DROP succeeds silently under IF EXISTS."""
    text = RUNBOOK.read_text()
    assert set(_runbook_indexes()) == INDEX_NAMES
    assert set(_generator().INDEX_NAMES) == INDEX_NAMES
    lists = re.findall(r"c\.relname IN \(([^)]*)\)", text)
    # P2, the A2 build read, and the rollback's final read.
    assert len(lists) == 3
    for found in lists:
        assert set(re.findall(r"'(\w+)'", found)) == INDEX_NAMES
    assert "LIKE 'ix_fm_t14_" not in text
    rollback = _section("4.")
    drops = re.findall(r"DROP INDEX CONCURRENTLY IF EXISTS (\w+);", rollback)
    assert sorted(drops) == sorted(INDEX_NAMES)


def test_the_rollback_checks_for_a_live_build_first_and_proves_the_drop_last():
    sql = re.search(r"```sql\n(.*?)```", _section("4."), re.S).group(1)
    statements = [st.strip() for st in sql.split(";") if st.strip()]
    selects = [i for i, st in enumerate(statements) if "SELECT" in st]
    drops = [i for i, st in enumerate(statements) if st.startswith("DROP")]
    assert "pg_stat_progress_create_index" in statements[selects[0]]
    assert selects[0] < drops[0]
    assert statements[-1].splitlines()[-1].startswith(" WHERE c.relname IN (")
    assert drops[-1] < len(statements) - 1


def test_the_preconditions_cover_what_concurrently_waits_on():
    a1 = re.search(r"\*\*A1\..*?```sql\n(.*?)```", RUNBOOK.read_text(), re.S).group(1)
    for needle in (
        "pg_stat_activity",
        "pg_prepared_xacts",  # R5: a prepared transaction holds a snapshot no session shows
        "pg_stat_progress_create_index",
        "pg_get_indexdef",  # nit (c): the live index list goes in the receipt
        "n_tup_hot_upd",  # R10: the write premise
    ):
        assert needle in a1, needle
    # R9: P3 estimates at the steady-state ceilings and prints its own verdict;
    # missing statistics abort.
    assert "(1000 + 2 * 40)" in a1
    assert "coalesce(rows <= 0 OR" in a1 and "AS abort" in a1
    assert "> 300, true) AS abort" in a1
    a2 = re.search(r"\*\*A2\..*?```sql\n(.*?)```", RUNBOOK.read_text(), re.S).group(1)
    assert a2.count("THEN 330 ELSE 40 END") == 2


def _index_state() -> str:
    m = re.search(r"^\*\*Index state: (PROPOSED|KEPT|ROLLED BACK)\*\*$", RUNBOOK.read_text(), re.M)
    assert m, "the runbook has no Index state line"
    return m.group(1)


def test_models_declare_the_indexes_exactly_when_the_runbook_says_kept():
    """R8. Declared too early, autogenerate CREATEs them in a release (gotcha
    #31); left undeclared after a KEEP, autogenerate DROPs them in one."""
    declared = {name for name in INDEX_NAMES if f'"{name}"' in MODELS.read_text()}
    if _index_state() == "KEPT":
        assert declared == INDEX_NAMES
    else:
        assert declared == set()
