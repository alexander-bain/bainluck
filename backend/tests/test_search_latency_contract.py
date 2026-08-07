"""LAT-P002 / #1494 — regression guard for the /api/events/search latency contract.

The endpoint sat at a ~20s median and rode the Heroku 30s H12 boundary, returning
real 503s on the primary "find any entity" surface. Five properties of the query
shape caused it. Each is cheap to reintroduce by accident and invisible in a unit
test that only checks the response body, so this file asserts the SHAPE.

Deliberately NOT wall-clock assertions: a timing test on CI hardware is flaky and
proves nothing about production. These assert the structural properties whose
absence made the route slow, which is what actually regresses.

Refusal codes mirror backend/tests/evals/fixtures/search_latency_budget_contract.json.
"""

import inspect
import re

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from app.models import Event, Sport
from app.routes import events as events_route


def _source_of(fn) -> str:
    return inspect.getsource(fn)


def _strip_comments(src: str) -> str:
    """Drop `#` comment lines.

    The fixes are heavily commented and those comments QUOTE the anti-patterns they
    replaced, so a naive substring check on raw source matches the explanation rather
    than live code. Only whole-line comments are stripped — enough here, and it avoids
    mangling a `#` inside a string literal.
    """
    return "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )


SEARCH_SRC = _source_of(events_route.search_events)
SEARCH_CODE = _strip_comments(SEARCH_SRC)


def _compile(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(),
                            compile_kwargs={"literal_binds": False}))


# ---------------------------------------------------------------------------
# 1a — COUNT_HAS_ORDERING / COUNT_HAS_UNUSED_WORK / COUNT_SHAPE_WIDE
# ---------------------------------------------------------------------------

def test_count_is_not_built_from_the_ordered_entity_query():
    """The count must not be `select(count()).select_from(query.subquery())`.

    `query` carries ORDER BY (ts_rank_cd, a 9-arm event_tags JSONB CASE, a status
    CASE and two commence_time CASEs) and a full `select(Event)` projection.
    Postgres does not strip a subquery's ORDER BY, so that form made the count pay
    every sort key per candidate row to produce a number nobody sorts.
    """
    assert "select_from(query.subquery())" not in SEARCH_CODE, (
        "COUNT_SHAPE_WIDE reintroduced: the count is being built from the ordered "
        "entity query again. Build it from the shared predicate list instead."
    )


def test_count_query_shape_has_no_ordering_and_no_entity_projection():
    """The identity-only count shape compiles without ORDER BY or entity columns."""
    conditions = [Event.commence_time.isnot(None), Event.status == "live"]
    count_sql = _compile(
        select(func.count())
        .select_from(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .where(*conditions)
    )
    assert "ORDER BY" not in count_sql.upper()
    assert "ts_rank_cd" not in count_sql
    assert "events.home_team_name" not in count_sql, (
        "count_has_entity_projection must be false — count identity only"
    )
    assert count_sql.upper().count("SELECT") == 1, "no subquery wrapper"


def test_both_count_sites_use_the_predicate_list():
    """Primary AND fuzzy-fallback counts. The fallback was the second instance."""
    assert SEARCH_SRC.count("select_from(Event)") >= 2, (
        "expected an identity count at BOTH the primary and fuzzy-fallback sites"
    )


# ---------------------------------------------------------------------------
# 1b — LEAGUE_TERM_BROADENS_EVENT_SCOPE
# ---------------------------------------------------------------------------

def test_league_token_does_not_widen_the_event_predicate_bare():
    """`nba champion` must not match every basketball_nba event.

    The old code OR'd `Sport.key.in_(sport_alias_keys)` into the event filter
    unconditionally, so the non-league term was not required at all — the dominant
    cost for the single slowest gold query.
    """
    # The league arm must be conjoined with the remaining terms.
    assert "non_league_expanded" in SEARCH_SRC, (
        "the league/non-league term split is gone; the league arm cannot be "
        "constrained without it"
    )
    assert re.search(r"and_\(\s*league_scope,\s*\*remaining\s*\)", SEARCH_SRC), (
        "LEAGUE_TERM_BROADENS_EVENT_SCOPE reintroduced: the league scope is no "
        "longer AND-ed with the remaining query terms"
    )


def test_league_only_query_keeps_the_bare_league_arm():
    """A league-only query IS asking for the league (`league_only_explicit`)."""
    assert "if non_league_expanded:" in SEARCH_SRC, (
        "the bare league arm must survive for a league-only query like 'nba'"
    )


def test_sport_alias_split_covers_every_alias_token():
    """The split keys off the same map that builds sport_alias_keys, so a new
    alias cannot be a league token for widening but not for the guard."""
    aliases = events_route._SPORT_SEARCH_ALIASES
    assert "nba" in aliases and "soccer" in aliases
    for token in aliases:
        assert token == token.lower(), (
            f"{token!r} must be lowercase — the split compares t.lower()"
        )


# ---------------------------------------------------------------------------
# 1c — the event WHERE must stay index-servable
# ---------------------------------------------------------------------------

def test_event_where_has_no_unindexable_fts_arm():
    """No tsvector index exists on events (only gin_trgm_ops trigram GINs), so a
    `to_tsvector(col) @@ tsquery` arm in the WHERE forces a seq scan for the whole
    OR — defeating the trigram index the ILIKE arm would otherwise use."""
    where_region = SEARCH_CODE.split("query = (")[0]
    assert "_fts_filter(Event.home_team_name" not in where_region, (
        "an unindexable FTS arm is back in the event WHERE; it forces a seq scan "
        "of events for every search"
    )
    assert "_fts_filter(Event.away_team_name" not in where_region


def test_ts_rank_cd_still_orders_results():
    """Dropping FTS from the WHERE must not drop RANKING — ts_rank_cd still
    orders, computed only over the rows the trigram WHERE returned."""
    assert "search_rank = _search_rank(_event_search_vector(), q)" in SEARCH_SRC
    assert "search_rank.desc()" in SEARCH_SRC


def test_fuzzy_fallback_uses_the_indexable_similarity_operator():
    """`similarity(a,b) > 0.25` is the function form and cannot use
    ix_teams_name_trgm; the `%` operator can."""
    assert 'Team.name.op("%")(q)' in SEARCH_SRC, (
        "the fuzzy fallback is back on the unindexable similarity() function form"
    )


def test_fuzzy_threshold_is_pinned_so_recall_is_unchanged():
    """`%` tests `>= pg_trgm.similarity_threshold`, which defaults to 0.3 —
    STRICTER than the 0.25 this path has always used. Without pinning it, switching
    to the operator would silently narrow "did you mean"."""
    assert "SET LOCAL pg_trgm.similarity_threshold = 0.25" in SEARCH_SRC
    assert "func.similarity(Team.name, q) > 0.25" in SEARCH_SRC, (
        "the exact boundary check must stay: `%` is >=, the contract is >"
    )


# ---------------------------------------------------------------------------
# 1d — ANALYTICS_ON_CRITICAL_PATH
# ---------------------------------------------------------------------------

def test_search_query_log_is_not_awaited_on_the_request_path():
    """It opens a SECOND session and COMMITs. Awaiting it made every search pay for
    an INSERT+COMMIT before responding, and held a third pooled connection."""
    assert "await _log_search_query(" not in SEARCH_CODE, (
        "ANALYTICS_ON_CRITICAL_PATH reintroduced: the search-query log write is "
        "awaited on the request path again"
    )
    assert "_dispatch_search_log(" in SEARCH_SRC


def test_dispatched_log_task_is_strongly_referenced():
    """asyncio holds only a WEAK reference to a task; a fire-and-forget write can
    be garbage-collected mid-await and vanish silently."""
    src = _source_of(events_route._dispatch_search_log)
    assert "_SEARCH_LOG_TASKS.add(task)" in src
    assert "add_done_callback(_SEARCH_LOG_TASKS.discard)" in src, (
        "the task set must be drained on completion or it grows unbounded"
    )


def test_dispatch_survives_having_no_running_loop():
    """Logging is optional instrumentation and must never raise into search."""
    events_route._dispatch_search_log(
        query="x", result_count=0, top_result_id=None, user_id=None, session_id=None
    )


# ---------------------------------------------------------------------------
# 1e — the request must be bounded (no SUCCESS_AFTER_DEADLINE / H12 503)
# ---------------------------------------------------------------------------

def test_statement_timeout_is_armed_before_the_first_query():
    assert "await _apply_search_statement_timeout(db)" in SEARCH_SRC
    src = _source_of(events_route._apply_search_statement_timeout)
    assert "SET LOCAL statement_timeout" in src, (
        "must be SET LOCAL — a session-level timeout would leak to the next "
        "borrower of the pooled connection"
    )


def test_budget_is_below_the_heroku_h12_boundary():
    """The whole point: the request must end before the router kills it at 30s."""
    assert events_route._SEARCH_DEADLINE_MS < 30_000
    assert events_route._SEARCH_STATEMENT_TIMEOUT_MS < events_route._SEARCH_DEADLINE_MS


def test_every_unbounded_stage_is_guarded():
    """The three stages whose cost is not bounded by an id lookup."""
    for stage in ("event_count", "events", "futures", "teams"):
        assert f'degraded.append("{stage}")' in SEARCH_SRC, (
            f"the {stage} stage is no longer degradable — it can ride to H12"
        )


def test_timeout_recovery_rolls_back_and_rearms():
    """A timed-out statement ABORTS the transaction; without a rollback every later
    stage fails with InFailedSqlTransaction, turning one slow stage into a 500."""
    src = _source_of(events_route._recover_search_session)
    assert "await db.rollback()" in src
    assert "_apply_search_statement_timeout(db)" in src, (
        "rollback clears SET LOCAL — the timeout must be re-armed"
    )


@pytest.mark.parametrize("sqlstate_attr", ["sqlstate", "pgcode"])
def test_query_timeout_is_detected_through_the_sqlalchemy_wrapper(sqlstate_attr):
    """57014 is query_canceled. It arrives wrapped in a DBAPIError, so a naive
    isinstance check misses it and the route 500s instead of degrading."""
    class _Driver(Exception):
        pass

    inner = _Driver("canceling statement due to statement timeout")
    setattr(inner, sqlstate_attr, "57014")

    class _Wrapper(Exception):
        def __init__(self, orig):
            super().__init__("wrapped")
            self.orig = orig

    assert events_route._is_query_timeout(_Wrapper(inner)) is True


def test_query_timeout_detection_by_driver_class_name():
    """asyncpg does not always surface a sqlstate through SQLAlchemy's wrapper."""
    class QueryCanceledError(Exception):
        pass

    assert events_route._is_query_timeout(QueryCanceledError("cancelled")) is True


def test_non_timeout_errors_are_not_swallowed():
    """A genuine bug must still surface as an error, not a silent empty result."""
    assert events_route._is_query_timeout(ValueError("boom")) is False
    assert events_route._is_query_timeout(RuntimeError("no")) is False


def test_non_timeout_errors_are_reraised_by_each_stage_guard():
    """`if not _is_query_timeout(exc): raise` must gate every stage guard, or the
    guards become a catch-all that hides real failures as empty results."""
    assert SEARCH_SRC.count("if not _is_query_timeout(exc):") >= 4


def test_degraded_is_additive_and_absent_on_a_complete_answer():
    """A stage we could not complete must be distinguishable from one that honestly
    found nothing — missing evidence is not GREEN. And an untouched response shape
    for the normal path: the key is absent, not an empty list."""
    assert '**({"degraded": degraded} if degraded else {})' in SEARCH_SRC


# ---------------------------------------------------------------------------
# debug_timing — the #1197 lever, so the NEXT measurement is decisive
# ---------------------------------------------------------------------------

def test_debug_timing_is_opt_in_and_absent_by_default():
    """The normal response shape must be untouched: no key unless asked for."""
    assert '"debug_timing"' in SEARCH_CODE
    assert "if debug_timing else {}" in SEARCH_CODE, (
        "debug_timing must be opt-in; an always-present key changes the payload"
    )


def test_every_db_stage_is_timed_separately():
    """The 2026-08-07 baseline could not say WHICH stage was slow — the two slowest
    gold queries returned the two smallest payloads. Each stage that issues its own
    query must be independently attributable."""
    for stage in ("event_count", "event_page", "event_enrichment",
                  "futures", "teams"):
        assert f'_mark("{stage}")' in SEARCH_CODE, f"stage {stage} is not timed"
