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

The narrow re-review of f8354ae264 (R1a, R1b, R6') adds three holds: every
gate statement runs with no parallel workers (before PostgreSQL 18 a parallel
bitmap heap scan prints the leader's heap blocks only), the one cold reader
check has a bound in the acceptance table, and the rollback and the A2 failure
path are bounded, attended passes with no retry-until instruction.
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
    "max_parallel_workers_per_gather": "0",
    "every_index_valid": "yes",
    "seq_scan_on_futures_markets": "none",
    "parallel_bitmap_heap_scan": "none",
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
    "reader_check_reads": "1",
    "reader_check_taken_by": "latency",
    "reader_check_inside_window": "yes",
    "reader_check_max_maxq_ms": "2000",
    "reader_check_none_in_window": "UNMEASURED",
    "on_failure": "section 4 rollback",
}
# R6': the rollback's attempt bounds, the third copy.
ROLLBACK_BOUNDS = {
    "attended_passes": "1",
    "build_in_flight_at_start": "HOLD, drop nothing",
    "max_drop_attempts_per_index": "2",
    "drop_lock_timeout": "60s",
    "max_lock_waits_per_drop": "3",
    "pass_minutes_if_one_holder_per_wait": "18",
    "each_further_holder_adds": "60s",
    "a2_p1c_reread_max_minutes": "10",
    "a2_p1c_reread_every_minutes": "1",
    "a2_build_still_in_flight": "HOLD, drop nothing",
    "a2_step2_max_repeats": "1",
    "leftover_after_final_read": "ROLLBACK INCOMPLETE",
    "rollback_incomplete_operator": "Alex",
    "next_admission": "latency asks Root for the next attended slot, P1 P1b P1c first",
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
    # R1a: no workers, so `Heap Blocks:` counts every page on PostgreSQL 17.
    serial = at("SET max_parallel_workers_per_gather = '0';")
    assert len(serial) == 1
    assert serial[0] < at("PREPARE ")[0] < at("EXPLAIN ")[0]
    assert not [ln for ln in lines if "parallel" in ln.lower() and ln.startswith("SET ")
                and ln != lines[serial[0]]]
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
    assert gate.count("SET max_parallel_workers_per_gather = '0';") == len(GATE_SPORTS)
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


def test_the_gate_sets_what_its_criteria_name():
    """R1a: the two session criteria are SET lines, not prose a reader checks."""
    gen = _generator()
    assert tuple(gen.GATE_SESSION_SETTINGS) == (
        "statement_timeout",
        "max_parallel_workers_per_gather",
    )
    for name in gen.GATE_SESSION_SETTINGS:
        assert f"SET {name} = '{GATE_CRITERIA[name]}';" in _block()


def test_the_final_keep_is_a_cold_path_acceptance_written_down_before_the_build():
    assert _fenced("acceptance-criteria") == ACCEPTANCE_CRITERIA
    assert _generator().ACCEPTANCE_CRITERIA == ACCEPTANCE_CRITERIA
    # R1b: the cold reader check is bounded by the gate's own budget and has
    # the same failure action as the mean.
    assert ACCEPTANCE_CRITERIA["reader_check_max_maxq_ms"] == GATE_CRITERIA["max_execution_ms"]


def test_the_rollback_bounds_are_one_table_in_three_places():
    """R6': loosening an attempt bound in one copy only fails here."""
    assert _fenced("rollback-bounds") == ROLLBACK_BOUNDS
    assert _generator().ROLLBACK_BOUNDS == ROLLBACK_BOUNDS
    # lane1b N3: one DROP waits up to three times, and lock_timeout restarts for
    # each transaction a wait is behind, so names x attempts x waits x 60 s is
    # the pass with one holder per wait, not a bound on the pass.
    assert ROLLBACK_BOUNDS["drop_lock_timeout"] == "60s"
    assert ROLLBACK_BOUNDS["each_further_holder_adds"] == "60s"
    worst = (
        len(INDEX_NAMES)
        * int(ROLLBACK_BOUNDS["max_drop_attempts_per_index"])
        * int(ROLLBACK_BOUNDS["max_lock_waits_per_drop"])
    )
    assert int(ROLLBACK_BOUNDS["pass_minutes_if_one_holder_per_wait"]) == worst
    assert not any("worst" in k for k in ROLLBACK_BOUNDS)
    text = " ".join(_section("4.").split())
    assert "one DROP waits up to three times" in text
    # lane1b N3a: lock_timeout bounds each lock REQUEST; a wait can outlast it.
    assert "`lock_timeout` bounds each lock request, and one DROP waits up to three times" in text
    assert "bounds each *wait*" not in RUNBOOK.read_text()
    assert "`lock_timeout` restarts for each transaction a wait is behind" in text
    assert "a wait behind k transactions can last up to k × 60 s" in text
    assert (
        f"{worst} minutes (3 names × 2 attempts × 3 waits × 60 s) is the pass when "
        "each wait is behind one transaction. Each further one can add up to 60 s."
    ) in text
    assert "its end state is the final read, not a clock" in text
    assert "at worst" not in text and "worst case" not in text
    assert "(`indisvalid = f, indisready = f`) takes no writes" in text


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
    # P2, the A2 build read, the rollback's between-attempts read and its final read.
    assert len(lists) == 4
    for found in lists:
        assert set(re.findall(r"'(\w+)'", found)) == INDEX_NAMES
    assert "LIKE 'ix_fm_t14_" not in text
    rollback = _section("4.")
    drops = re.findall(r"DROP INDEX CONCURRENTLY IF EXISTS (\w+);", rollback)
    attempts = int(ROLLBACK_BOUNDS["max_drop_attempts_per_index"])
    assert set(drops) == INDEX_NAMES
    assert all(drops.count(name) == attempts for name in INDEX_NAMES)


def _rollback_sql() -> list[str]:
    return re.search(r"```sql\n(.*?)```", _section("4."), re.S).group(1).splitlines()


def test_the_rollback_holds_on_a_live_build_and_proves_the_drop_last():
    """R6': P1c gates both attempts mechanically; the final read is last."""
    lines = _rollback_sql()
    # lane1b N1: a .psqlrc or earlier step with ON_ERROR_STOP on would end the
    # pass at a cancelled attempt 1, before attempt 2 and the final read.
    assert lines[0] == "\\set ON_ERROR_STOP off"
    assert lines[1] == "SET statement_timeout = 0;"
    first_drop = next(i for i, ln in enumerate(lines) if ln.startswith("DROP"))
    last_drop = max(i for i, ln in enumerate(lines) if ln.startswith("DROP"))
    gset = next(i for i, ln in enumerate(lines) if ln.rstrip().endswith("\\gset"))
    assert lines.index("\\unset no_build_in_flight") < gset
    assert "pg_stat_progress_create_index" in " ".join(lines[gset - 1 : gset + 1])
    # lane1b N2: `count(*) >= 0` would disable the mechanical HOLD.
    assert lines[gset - 1] == (
        "SELECT count(*) = 0 AS no_build_in_flight FROM pg_stat_progress_create_index"
    )
    assert lines[gset + 1] == "\\if :no_build_in_flight"
    els, endif = lines.index("\\else"), lines.index("\\endif")
    assert gset + 1 < first_drop and last_drop < els < endif
    assert lines[els + 1].startswith("\\echo HOLD")
    assert not [ln for ln in lines[els:endif] if ln.startswith("DROP")]
    # The final read follows \endif, so a HOLD records what exists too, and
    # nothing executes after it.
    statements_after = [ln for ln in lines[endif + 1 :] if ln and not ln.startswith("--")]
    assert statements_after[0].startswith("SELECT c.relname, i.indisvalid, i.indisready")
    assert statements_after[-1].startswith(" WHERE c.relname IN (")
    assert len(statements_after) == 2
    attempts = int(ROLLBACK_BOUNDS["max_drop_attempts_per_index"])
    for n in range(1, attempts + 1):
        assert sum(ln.startswith(f"-- Attempt {n} of {attempts}") for ln in lines) == 1
    assert f"SET lock_timeout      = '{ROLLBACK_BOUNDS['drop_lock_timeout']}';" in "\n".join(lines)


def _a2_failure_path() -> str:
    text = RUNBOOK.read_text()
    start = text.index("**If any CREATE errors")
    return text[start : text.index("**A3.", start)]


UNBOUNDED = re.compile(r"\b(until|repeat\w*|loop\w*|keep (?:re-?)?trying|again and again)\b", re.I)


@pytest.mark.parametrize("where", ["section 4", "A2 failure path"])
def test_no_rollback_step_repeats_without_a_bound(where):
    """R6': completion is the catalog reading 0 rows, never a retry-until loop."""
    text = _section("4.") if where == "section 4" else _a2_failure_path()
    assert UNBOUNDED.findall(text) == [], f"{where} carries an unbounded instruction"


def test_the_a2_failure_path_states_its_bounds():
    text = " ".join(_a2_failure_path().split())
    assert f"for at most {ROLLBACK_BOUNDS['a2_p1c_reread_max_minutes']} minutes" in text
    assert "once a minute" in text and ROLLBACK_BOUNDS["a2_p1c_reread_every_minutes"] == "1"
    assert "**HOLD**. Drop nothing" in text
    assert "a second time, once" in text and ROLLBACK_BOUNDS["a2_step2_max_repeats"] == "1"
    assert "bounds each of its lock requests; §4 says how long a DROP can wait" in text
    assert "`lock_timeout = '60s'` bounds it)" not in text
    assert "run §4 once" in text


def test_the_rollback_names_its_end_states_operator_and_next_admission():
    text = " ".join(_section("4.").split())
    assert "Final read, 0 rows: `ROLLED BACK`." in text
    assert "Final read, any row: `ROLLBACK INCOMPLETE`." in text
    assert "The operator is Alex." in text
    assert "latency asks Root for the next attended slot" in text
    assert "starts with P1, P1b and P1c again" in text
    assert "ON_ERROR_STOP` **off**" in text
    assert "The block's first line sets it" in text


def test_the_acceptance_prose_states_the_table_s_bounds():
    """lane1b N2: prose beside a held table cannot drift from it."""
    text = " ".join(_section("6.").split())
    maxq = f"{int(ACCEPTANCE_CRITERIA['reader_check_max_maxq_ms']):,}"
    assert f"**Pass: `maxq` ≤ {maxq} ms**" in text
    assert f"Over {maxq} ms is a failure." in text
    assert len(re.findall(r"`maxq` ≤ ([\d,]+) ms", text)) == 1
    hours = ACCEPTANCE_CRITERIA["window_starts_hours_after_build"]
    assert f"(at least {hours} h after the build)" in text
    assert "It is not retried for a better number." in text
    assert "**On failure** (mean, size or reader check over its bound)" in text
    where = " ".join(_section("3.").split())
    assert "no `Parallel Bitmap Heap Scan` and no `Gather` in any plan" in where


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
    m = re.search(
        r"^\*\*Index state: (PROPOSED|KEPT|ROLLED BACK|ROLLBACK INCOMPLETE)\*\*$",
        RUNBOOK.read_text(),
        re.M,
    )
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
