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
    # LAT-P005: the call now carries the live deadline. Match on the call name
    # rather than an exact arg list so the guard pins "it is armed", not a
    # signature — pinning the signature is what made this test fail on a fix.
    assert "await _apply_search_statement_timeout(db" in SEARCH_SRC
    src = _source_of(events_route._apply_search_statement_timeout)
    assert "SET LOCAL statement_timeout" in src, (
        "must be SET LOCAL — a session-level timeout would leak to the next "
        "borrower of the pooled connection"
    )


def test_budget_is_below_the_heroku_h12_boundary():
    """The whole point: the request must end before the router kills it at 30s."""
    assert events_route._SEARCH_DEADLINE_MS < 30_000
    # LAT-P005: the per-stage bound is derived from the deadline remaining rather
    # than a fixed constant (the fixed 4s is what reverted LAT-P002 — see
    # TestBudgetCannotStarveAHealthyStage). It can never exceed the deadline by
    # construction; assert that, instead of comparing against a constant that is
    # now deliberately unset.
    assert events_route._stage_timeout_ms(None) <= events_route._SEARCH_DEADLINE_MS
    if events_route._SEARCH_STATEMENT_TIMEOUT_MS is not None:
        assert (
            events_route._SEARCH_STATEMENT_TIMEOUT_MS
            < events_route._SEARCH_DEADLINE_MS
        )


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
    assert "_apply_search_statement_timeout(db" in src, (
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


# ---------------------------------------------------------------------------
# LAT-P005/#1494 — the budget defect that caused the revert.
#
# LAT-P002's 4000ms fixed statement timeout fired on HEALTHY futures queries:
# 3 of 8 sampled production queries returned HTTP 200 with ZERO futures, and the
# whole change was reverted (f98d8104). These pin the reasoning, not the number.
# ---------------------------------------------------------------------------
class TestBudgetCannotStarveAHealthyStage:
    def test_deadline_exceeds_the_worst_measured_stage(self):
        """The budget is the anti-503 guard; it buys no speed.

        1a/1b/1c make the query fast. 1e only stops the request riding to H12.
        So the bound must be as LOOSE as it can be while beating Heroku's 30s —
        not as tight as it can be. The worst measured real request was 13.75s
        (`nba champion`, pre-fix); a budget under that kills healthy queries.
        """
        from app.routes.events import _SEARCH_DEADLINE_MS

        WORST_MEASURED_REQUEST_MS = 13_750
        HEROKU_H12_MS = 30_000

        assert _SEARCH_DEADLINE_MS > WORST_MEASURED_REQUEST_MS, (
            f"deadline {_SEARCH_DEADLINE_MS}ms is below the worst measured healthy "
            f"request ({WORST_MEASURED_REQUEST_MS}ms) — it will cancel good queries "
            "and return empty 200s, which is what reverted LAT-P002"
        )
        assert _SEARCH_DEADLINE_MS < HEROKU_H12_MS, (
            "deadline must still beat H12, or the 503s come back"
        )

    def test_no_fixed_statement_timeout_by_default(self):
        """A single fixed bound cannot be right for two stages of different cost.

        Any value tight enough to feel protective on the events query is too
        tight for the futures query. That mismatch IS the bug, so the fixed
        override is off by default.
        """
        from app.routes.events import _SEARCH_STATEMENT_TIMEOUT_MS

        assert _SEARCH_STATEMENT_TIMEOUT_MS is None

    def test_stage_timeout_is_the_remaining_budget(self):
        """Each stage gets the time actually left, not a constant."""
        import time as _t

        from app.routes.events import _SEARCH_DEADLINE_MS, _stage_timeout_ms

        fresh = _stage_timeout_ms(_t.monotonic() + (_SEARCH_DEADLINE_MS / 1000.0))
        assert fresh > _SEARCH_DEADLINE_MS * 0.9

        # A later stage gets less — but never so little that a healthy query is
        # started only to be killed.
        late = _stage_timeout_ms(_t.monotonic() + 0.05)
        assert late >= 2000

    def test_the_reverted_4s_budget_would_now_fail_this_suite(self):
        """The specific regression, named.

        `nba champion`'s futures query alone exceeded 4s, so the old constant
        aborted it on every single request. Guard the class, not the incident.
        """
        from app.routes.events import _SEARCH_DEADLINE_MS

        NBA_CHAMPION_FUTURES_MS = 4_000
        assert _SEARCH_DEADLINE_MS > NBA_CHAMPION_FUTURES_MS * 2

    def test_futures_stage_is_rearmed_with_the_live_deadline(self):
        """The futures stage must re-arm the bound, not inherit the events one.

        Asserted on source because the failure is structural: the old code armed
        `statement_timeout` once, up front, and every later stage silently
        inherited a bound chosen for a cheaper query.
        """
        import inspect

        from app.routes import events

        src = inspect.getsource(events.search_events)
        futures_at = src.find("futures_result = await db.execute(futures_query)")
        assert futures_at > 0, "futures stage not found — update this guard"

        window = src[:futures_at]
        rearm = window.rfind("_apply_search_statement_timeout(db, _deadline)")
        assert rearm > 0, "futures stage does not re-arm the statement timeout"

        # ...and the re-arm is close to the stage, not left far upstream.
        assert src[rearm:futures_at].count("await db.execute(") <= 1, (
            "another query runs between the re-arm and the futures stage"
        )


# ---------------------------------------------------------------------------
# LAT-P006 — the COST bound the recall gate structurally cannot provide.
#
# The missing half of the CI rail, named in test_search_recall_contract.py's
# SCOPE LIMIT: on the LAT-P005 re-land that gate reported `SEARCH RECALL 5/5`
# and CI went green while production returned ZERO futures for
# `us recession 2026`. Both were correct — the predicate matched, the query was
# too slow to finish (23.57s, dropped at the 20s deadline).
#
# A recall assertion cannot detect a timeout, and neither can a plan assertion
# or a wall-clock assertion on a seeded CI database: both are functions of data
# volume, and the seed is always small. So the bound is asserted on SQL SHAPE —
# the one property that is volume-independent and still causally tied to the
# cost.
#
# MEASURED in production 2026-08-08 (`futures_outcomes` 3.2M rows / 3 GB):
#
#   us recession 2026   name arm alone  159ms | outcome arm alone  123ms
#                       OR of the two   >10,000ms TIMEOUT
#                       UNION           437ms          (same 1 row)
#   nba champion        OR              >10,000ms TIMEOUT
#                       UNION           701ms          (same 46 rows)
#
# ANDed `IN`-subqueries become hash semi-joins the planner orders by
# selectivity. A top-level OR blocks that transformation, so they degrade to
# subplans probed against a seq scan of `futures_markets`. ONE arm that defeats
# the planner inside a top-level OR poisons the whole predicate — 1c's lesson,
# restated for subqueries.
# ---------------------------------------------------------------------------
class TestFuturesRecallArmsAreUnionedNotOred:
    """Guard the SHAPE whose absence cost 23.57s and a wrong answer."""

    def test_recall_arms_are_not_combined_with_a_top_level_or(self):
        assert "or_(*_futures_where_or)" not in SEARCH_CODE, (
            "FUTURES_ARMS_ORED reintroduced: the futures recall arms are being "
            "combined with a top-level OR again. Measured >10s (production "
            "23.57s, zero futures returned for a market that exists) versus "
            "437ms for the set-identical UNION. Use union() of per-arm id "
            "selects."
        )

    def test_recall_arms_are_combined_with_a_union(self):
        assert "union(*_futures_arm_selects)" in SEARCH_CODE, (
            "the UNION of the futures recall arms is gone — if the arms are "
            "combined some other way, re-point this guard deliberately"
        )

    def test_open_and_unresolved_filters_are_pushed_into_each_arm(self):
        """AND distributes over UNION, and it is worth 9x.

        Unfiltered arms hand the outer query every RESOLVED market they match:
        `nba champion` measured 6,387ms with the filters only on the outer query
        versus 701ms with them pushed into each arm.
        """
        assert "select(FuturesMarket.id).where(arm, *_futures_open_now)" in SEARCH_CODE, (
            "the open/unresolved filters are no longer pushed into each UNION "
            "arm — measured 6,387ms -> 701ms on `nba champion`"
        )

    def test_the_outer_query_still_carries_the_filters_too(self):
        """Deliberate redundancy: the predicate stays correct if the push-down
        is ever removed. Cheap, because the outer query sees only candidate ids."""
        assert "*_futures_open_now," in SEARCH_CODE

    def test_the_ored_shape_would_fail_this_guard(self):
        """Mutation check — the guard must reject the shape it replaced.

        A guard that passes on the defect is not a guard. This reconstructs
        LAT-P005's exact line and asserts the check above catches it.
        """
        reverted_shape = "        .where(\n            or_(*_futures_where_or),\n"
        assert "or_(*_futures_where_or)" in reverted_shape
        assert "or_(*_futures_where_or)" not in SEARCH_CODE, (
            "the mutation check and the live source disagree — the guard is "
            "not actually discriminating"
        )

    def test_the_union_survives_compilation_as_a_single_scalar_subquery(self):
        """The compiled form must be `id IN (SELECT ... UNION SELECT ...)`.

        Compiled rather than source-matched, because the failure mode a UNION
        introduces is silent: `union()` of one arm, or a stray `intersect()`,
        reads fine and halves recall.
        """
        from sqlalchemy import union as _union

        from app.models import FuturesMarket

        arm_a = FuturesMarket.name.ilike("%recession%")
        arm_b = FuturesMarket.id.in_(select(FuturesMarket.id).where(
            FuturesMarket.name.ilike("%us%")
        ))
        open_now = (FuturesMarket.status == "open",)
        candidates = _union(
            *[select(FuturesMarket.id).where(arm, *open_now) for arm in (arm_a, arm_b)]
        ).subquery()
        sql = _compile(
            select(FuturesMarket).where(
                FuturesMarket.id.in_(select(candidates.c.id)), *open_now
            )
        ).upper()

        assert " UNION " in sql, "the arms did not compile to a UNION"
        assert "INTERSECT" not in sql, "an INTERSECT would silently halve recall"
        # status appears once per arm plus once on the outer query.
        assert sql.count("FUTURES_MARKETS.STATUS") >= 3, (
            "the open filter is not present in every arm plus the outer query"
        )


TYPEAHEAD_SRC = _source_of(events_route.typeahead_search)
TYPEAHEAD_CODE = _strip_comments(TYPEAHEAD_SRC)


# ---------------------------------------------------------------------------
# LAT-P007 — /typeahead. The SAME defects as /search, never propagated.
#
# `/typeahead` fires on every keystroke and had NO bound of any kind. Measured in
# production 2026-08-08:
#
#   q=re    12.06s     q=ni  11.06s     q=la  10.99s      <- 2 chars
#   q=rec    7.08s     q=nik  2.67s     q=lak  2.58s      <- 3 chars
#
# `min_length=2`, so the endpoint's MINIMUM allowed query is its worst case and
# it is the first thing every user fires. The cliff sits exactly at the pg_trgm
# boundary across six independent stems, so it is pattern length, not popularity.
#
# Three causes, all already solved in /search and none propagated here:
#   1. `outcomes.any(...)` — a CORRELATED EXISTS over 3.2M rows. /search moved to
#      a non-correlated IN in #993. Measured 3,468ms -> 66.8ms, IDENTICAL results.
#   2. a top-level OR over the recall arms (LAT-P006). 9,682ms -> 2,414ms, same
#      990 rows.
#   3. no request budget at all.
# ---------------------------------------------------------------------------
class TestTypeaheadIsBoundedAndIndexable:
    def test_outcome_arm_is_not_correlated(self):
        """`.any()` re-probes per candidate row; the IN form scans once.

        52x on identical results. This is the #993 Slice-Speed change that
        /search got and /typeahead did not.
        """
        assert "FuturesMarket.outcomes.any(" not in TYPEAHEAD_CODE, (
            "CORRELATED_OUTCOME_ARM reintroduced in /typeahead: measured 3,468ms "
            "vs 66.8ms for the set-identical non-correlated IN form"
        )
        assert "select(FuturesOutcome.market_id).where(" in TYPEAHEAD_CODE, (
            "the non-correlated outcome subquery is gone from /typeahead"
        )

    def test_outcome_arm_is_skipped_for_sub_three_char_queries(self):
        """A 2-char infix pattern is unservable by a pg_trgm GIN.

        That arm alone measured 8,633ms for `%re%`. It is not a recall trade:
        17 of the 20 visible rows for `re` came from this arm and all 17 were
        substring accidents (Lamprecht, Baltimore, Guterres, Villarreal).
        """
        # Assert the EFFECTIVE value, not the literal. LAT-P010 moved the 3 into a
        # shared module constant so /search and /typeahead cannot drift on where
        # the cliff is; pinning the literal made this guard fail on that correct
        # change, which is the LAT-P005 lesson about pinning the wrong thing.
        from app.routes.events import _SEARCH_MIN_OUTCOME_MATCH_CHARS

        assert _SEARCH_MIN_OUTCOME_MATCH_CHARS == 3, (
            "the threshold must be 3 — that is where the pg_trgm cliff is"
        )
        assert "_TA_MIN_OUTCOME_MATCH_CHARS = _SEARCH_MIN_OUTCOME_MATCH_CHARS" in TYPEAHEAD_CODE, (
            "/typeahead must use the SHARED threshold — the two surfaces drifting "
            "is how /search kept this defect for three cycles after /typeahead's "
            "twin was fixed"
        )
        # Defined is not enough; it must GATE the arm. An earlier version of this
        # guard passed while the arm ran unconditionally, because the constant was
        # still sitting there unused.
        assert TYPEAHEAD_CODE.count("_TA_MIN_OUTCOME_MATCH_CHARS") >= 2, (
            "the sub-3-char threshold is defined but never used — `q=re` goes "
            "back to seq-scanning 3 GB of futures_outcomes for 8.6s of noise"
        )
        gate_at = TYPEAHEAD_CODE.find("if len(_ta_q_compact) >= _TA_MIN_OUTCOME_MATCH_CHARS")
        arm_at = TYPEAHEAD_CODE.find("select(FuturesOutcome.market_id).where(")
        assert 0 < gate_at < arm_at, (
            "the outcome arm is not inside the sub-3-char gate"
        )

    def test_the_gate_is_on_the_whole_query_not_on_individual_terms(self):
        """Must NOT contradict LAT-P006's guard.

        LAT-P006 pins that a short term still FILTERS inside a multi-term AND
        (`us recession` must not admit "Euro area growth"). /typeahead matches
        the WHOLE query string as one pattern, so the gate is on `q`, not on a
        per-term loop. A per-term version here would be the candidate LAT-P006
        measured and rejected.
        """
        assert "len(_ta_q_compact) >= _TA_MIN_OUTCOME_MATCH_CHARS" in TYPEAHEAD_CODE, (
            "the sub-3-char gate must test the whole query, not per-term"
        )

    def test_typeahead_recall_arms_are_unioned_not_ored(self):
        assert "or_(*ta_futures_where)" not in TYPEAHEAD_CODE, (
            "FUTURES_ARMS_ORED in /typeahead: measured 9,682ms vs 2,414ms for "
            "the set-identical UNION"
        )
        assert "union(*_ta_arm_selects)" in TYPEAHEAD_CODE

    def test_typeahead_has_a_request_budget(self):
        """It had none at all — nothing stopped it riding to H12 at 12s."""
        from app.routes.events import _TYPEAHEAD_DEADLINE_MS

        assert _TYPEAHEAD_DEADLINE_MS < 30_000, "must beat Heroku H12"
        assert _TYPEAHEAD_DEADLINE_MS > 2_400 * 2, (
            "the bound must be LOOSE relative to the worst healthy stage "
            "(~2.4s measured post-fix). A tight bound cancels good queries and "
            "returns empty 200s — that is what reverted LAT-P002."
        )
        assert "_apply_search_statement_timeout(db, _ta_deadline)" in TYPEAHEAD_CODE

    def test_the_budget_starts_after_the_cache_read(self):
        """A cache hit returns before touching the DB and must not be charged."""
        cache_at = TYPEAHEAD_CODE.find("_cached")
        deadline_at = TYPEAHEAD_CODE.find("_ta_deadline = time.monotonic()")
        assert 0 < cache_at < deadline_at, (
            "the deadline is being started before the cache read"
        )

    def test_a_degraded_answer_is_never_cached(self):
        """A 45s TTL turns one slow moment into a sticky wrong answer.

        Without this, a single futures timeout writes a futures-less dropdown
        into Redis and everyone typing that prefix gets it for the full TTL.
        """
        assert "if not _ta_degraded:" in TYPEAHEAD_CODE, (
            "CACHE_DECISION_DISHONEST: a degraded typeahead answer is being "
            "written to Redis and will be served for the full 45s TTL"
        )
        setex_at = TYPEAHEAD_CODE.find("setex(_cache_key")
        guard_at = TYPEAHEAD_CODE.find("if not _ta_degraded:")
        assert 0 < guard_at < setex_at, "the cache write is not under the guard"

    def test_timeout_recovery_is_present_because_queries_follow(self):
        """Two fuzzy-fallback queries run after the futures stage.

        A timed-out statement aborts the transaction, so without a rollback those
        would fail on a poisoned session.
        """
        assert "_recover_search_session(db, _ta_deadline)" in TYPEAHEAD_CODE
        assert "_is_query_timeout(exc)" in TYPEAHEAD_CODE, (
            "a non-timeout error must still propagate, not be swallowed"
        )


# ---------------------------------------------------------------------------
# LAT-P010 — /search's single sub-3-char term. #1494 GAP 1.
#
# INT-019's control pass found /search slower than /typeahead on EVERY short stem
# tested. LAT-P006 closed /search for named MULTI-WORD queries; the single-term
# path was never touched, so /search kept the exact defect LAT-P007 had just
# removed from /typeahead — the mirror image of LAT-P007 itself.
#
# MEASURED in production 2026-08-08:
#   %re%            374,988 outcome rows   6,830ms
#   %la%            192,448 outcome rows   4,917ms
#   %los angeles%     7,726 outcome rows     657ms   (the expansion IS servable)
#   /search q=re    20.4s wall on TWO passes; futures stage 7.5s of an 8.4s request
#   /search q=la    1.9-3.1s; futures 1.4-2.4s
#
# And it buys nothing: for BOTH `re` and `la`, 0 of the 10 visible futures come
# from the outcome arm. Futures are ordered by ts_rank_cd over the NAME vector, so
# an outcome-only match scores ~0 and sorts below every name match; with a 2-char
# term there are always thousands of name matches, so the arm cannot reach the
# page.
# ---------------------------------------------------------------------------
class TestSearchSkipsTheUnservableOutcomeArm:
    def test_threshold_is_shared_between_search_and_typeahead(self):
        """One constant, both surfaces. Drift is how this defect survived.

        /typeahead was fixed at LAT-P007 and /search was not, because nothing
        tied them together. A shared constant makes the next change land on both.
        """
        from app.routes.events import _SEARCH_MIN_OUTCOME_MATCH_CHARS

        assert _SEARCH_MIN_OUTCOME_MATCH_CHARS == 3
        assert "_TA_MIN_OUTCOME_MATCH_CHARS = _SEARCH_MIN_OUTCOME_MATCH_CHARS" in TYPEAHEAD_CODE
        assert "len(term) < _SEARCH_MIN_OUTCOME_MATCH_CHARS" in SEARCH_CODE, (
            "/search no longer gates its outcome arm on the shared threshold"
        )

    def test_the_gate_is_only_on_the_single_term_path(self):
        """Must not contradict LAT-P006's multi-term guard.

        LAT-P006 pins that a short term still FILTERS inside a multi-term AND
        (`us recession` must not admit "Euro area growth"). Applying this gate
        per-term would break that. The multi-term branch stays untouched.
        """
        multi = SEARCH_CODE[
            SEARCH_CODE.find("if len(terms) > 1:") : SEARCH_CODE.find("futures_name_match = futures_name_ilike")
        ]
        head, _, tail = multi.partition("    else:")
        assert "_SEARCH_MIN_OUTCOME_MATCH_CHARS" not in head, (
            "the sub-3-char gate leaked into the MULTI-term branch — that is the "
            "candidate LAT-P006 measured and rejected, and it would break the "
            "`us recession` / 'Euro area growth' guard"
        )
        assert "_SEARCH_MIN_OUTCOME_MATCH_CHARS" in tail, (
            "the gate is not on the single-term path"
        )

    def test_the_expansion_survives_when_the_base_term_is_dropped(self):
        """`la` -> `los angeles` is meaningful, servable and cheap.

        Dropping the whole arm would lose real recall; dropping only the
        unindexable base term keeps it. 4,917ms -> 657ms on the outcome scan.
        """
        assert "_outcome_id_match(exp, None) if exp else None" in SEARCH_CODE, (
            "the expansion is being dropped along with the base term — `la` loses "
            "its `los angeles` outcome recall for no latency gain"
        )

    def test_a_dropped_arm_cannot_reach_the_union_as_none(self):
        """The arm list is FILTERED, not conditionally appended.

        `or_(None, ...)`/`union(select().where(None))` would be a silent
        correctness bug rather than a loud one.
        """
        assert "if arm is not None" in SEARCH_CODE, (
            "a None arm can reach the UNION"
        )

    def test_search_and_typeahead_now_agree_on_the_cliff(self):
        """The parity assertion this whole gap was: both surfaces gate, both at 3.

        INT-019 found /search slower than /typeahead on all 13 stems it tried.
        This is the test that fails if they diverge again.
        """
        assert "_SEARCH_MIN_OUTCOME_MATCH_CHARS" in SEARCH_CODE
        assert "_TA_MIN_OUTCOME_MATCH_CHARS" in TYPEAHEAD_CODE
