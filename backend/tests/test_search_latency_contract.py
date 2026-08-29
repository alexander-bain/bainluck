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
from sqlalchemy.sql import operators

from app.models import Event, FuturesMarket, Sport
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

# LAT-P013: the shortest term the OLD `len(term) < 3` gate would still admit. Any
# case used to prove the new predicate catches something the old one missed has to
# be at least this long, or it proves nothing.
_MIN_LEN_THE_OLD_GATE_ADMITTED = events_route._SEARCH_MIN_OUTCOME_MATCH_CHARS


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
    `to_tsvector(col) @@ tsquery` arm OR-ED into the WHERE forces a seq scan for
    the whole OR — defeating the trigram index the ILIKE arm would otherwise use.

    LAT-P034 AMENDED THIS TEST, so read why before widening it again. The event
    predicate now DOES contain an FTS arm (`_event_name_match`'s word-boundary
    half), and the original assertion — a text grep for `_fts_filter(Event...` in
    the route body — would have kept passing purely because the arm moved into a
    module-level helper. A guard that a refactor can walk out of is not a guard, so
    the assertion is now on the COMPILED predicate and tests the property that
    actually costs money: **AND-ed, not OR-ed.** AND lets the trigram GIN drive the
    scan and makes `to_tsvector` a recheck over the rows it returned (measured: fed
    4.5ms -> 2.4ms, `re` 150ms -> 117ms). OR is what forced the seq scan.
    """
    where_region = SEARCH_CODE.split("query = (")[0]
    assert "_fts_filter(Event.home_team_name" not in where_region, (
        "an unindexable FTS arm is back in the event WHERE; it forces a seq scan "
        "of events for every search"
    )
    assert "_fts_filter(Event.away_team_name" not in where_region

    # LAT-P035 AMENDED THIS AGAIN, and moved it off string surgery onto the
    # expression tree. The word arm legitimately gained a third disjunct — the
    # `numnode(...) = 0` lexeme-less guard — which sorts BEFORE the first
    # `to_tsvector` in the compiled text, so the old "no OR between the ILIKE and
    # the FTS" slice began failing on a change that preserved the exact property it
    # was defending. A guard that a legal edit trips is a guard that gets deleted.
    #
    # The property is structural, so assert it structurally: the top level is AND,
    # one side is the substring arm, the other is the word arm. Internal ORs inside
    # either side are fine and always were (home OR away); a top-level OR is what
    # costs the seq scan.
    expr = events_route._event_name_match("fed", None)
    assert expr.operator is operators.and_, (
        "the event name match is no longer a top-level AND. If the FTS arm is "
        "OR-ed in, every search seq-scans events — that was the 20s median."
    )
    substring_arm, word_arm = list(expr.clauses)
    assert substring_arm.operator is operators.or_
    substring_sql, word_sql = _compile(substring_arm), _compile(word_arm)
    assert "ILIKE" in substring_sql and "to_tsvector" not in substring_sql
    assert "to_tsvector" in word_sql and "ILIKE" not in word_sql


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
    an INSERT+COMMIT before responding, and held a third pooled connection.

    LAT-P090 moved the dispatch one level down, into `_record_search_query`, and
    this assertion follows it rather than being relaxed. The route now has TWO
    exits — a response-cache hit and a full build — and #2117 is the named case
    for what happens when only one of them counts: on `/typeahead` a warmed term
    became invisible to the counter that decides what to warm, so the head could
    only ever drain toward the queries we had failed to serve fast. One recorder,
    called from both exits, is the fix; the not-awaited contract is unchanged and
    is asserted here on the recorder that now owns it.
    """
    assert "await _log_search_query(" not in SEARCH_CODE, (
        "ANALYTICS_ON_CRITICAL_PATH reintroduced: the search-query log write is "
        "awaited on the request path again"
    )
    recorder = _source_of(events_route._record_search_query)
    assert "_dispatch_search_log(" in recorder
    assert "await _log_search_query(" not in recorder, (
        "the recorder awaits the write, which puts the INSERT+COMMIT back on "
        "the request path one indirection further away"
    )


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
    query must be independently attributable.

    LAT-P013 split the old single `event_enrichment` mark. That one label bundled
    FOUR things — the odds query, its Python aggregation, the GEI percentiles and
    the team lookup — so when it measured 16,516ms on `q=la` in production it could
    not say which of the four. The same complaint this test was written to answer,
    one level down."""
    for stage in ("event_count", "event_page",
                  "event_odds_query", "event_odds_aggregate",
                  "event_gei", "event_teams",
                  "futures", "teams"):
        assert f'_mark("{stage}")' in SEARCH_CODE, f"stage {stage} is not timed"


def _enrichment_source() -> str:
    """The statement that enriches a page of events with their latest odds.

    LAT-P030 lifted this out of `search_events` into a module-level helper so CI can
    execute the REAL query against real Postgres rather than a copy of it. Comments
    are stripped because the block deliberately quotes both anti-patterns it replaced.
    """
    return _strip_comments(_source_of(events_route.latest_odds_per_bookmaker_query))


def test_the_route_uses_the_shared_enrichment_query():
    """If the route stops calling the helper, every guard below is asserting the shape
    of dead code while the live path does whatever it likes."""
    assert "latest_odds_per_bookmaker_query(event_ids)" in SEARCH_CODE, (
        "search_events no longer builds its odds enrichment from the shared helper — "
        "the shape guards and the real-Postgres equivalence test now cover nothing"
    )


def test_the_odds_enrichment_query_reads_bookmakers_not_snapshot_history():
    """LAT-P013 then LAT-P030, both on #1494. `event_odds_query` is the entire cost of
    every search that returns real team events and ~0ms for one that returns none.

    Two shapes have now been retired here, and BOTH are asserted gone, because the
    second one looked like the fix for the first:

    1. `row_number() OVER (PARTITION BY event_id, bookmaker ORDER BY captured_at DESC)`
       over the full history of all ~25 result events, joined back by id.
    2. `DISTINCT ON (bookmaker)` inside a per-event LATERAL. This removed the window
       and the join-back, and LAT-P013's comment claimed it walked
       `ix_odds_snapshots_bookmaker_closing` in index order with "no sort". Postgres
       never chose that plan. Measured on production 2026-08-10, it took
       `ix_odds_snapshots_event_id` and **sorted 2,702 rows per event**, because
       DISTINCT ON cannot skip: keeping one row per bookmaker still requires reading
       every snapshot of every event. 78,800 rows read to return 299; 6,724ms.

    The property that makes this fast is not the absence of a sort — it is that the
    number of rows read scales with DISTINCT BOOKMAKERS (~19) instead of SNAPSHOT
    DEPTH (13,522 on one measured Red Sox event). A recursive loose index scan
    enumerates the bookmakers, then exactly one row is fetched per pair: 947 rows,
    185ms, byte-identical output. So assert the bound, not the syntax."""
    enrich = _enrichment_source()

    assert "row_number()" not in enrich, (
        "the window-function scan over full snapshot history is back — it reads and "
        "sorts every snapshot of every event on the page to keep one row per bookmaker"
    )
    assert ".distinct(OddsSnapshot.bookmaker)" not in enrich, (
        "DISTINCT ON (bookmaker) is back. It reads the FULL snapshot history of every "
        "event on the page (measured: 78,800 rows for 299 results, 6,724ms) because it "
        "cannot skip. It is not a top-1; it is a full scan that discards."
    )
    assert "recursive=True" in enrich, (
        "the loose index scan is gone — without it nothing bounds the read to the "
        "number of distinct bookmakers"
    )
    assert ".limit(1)" in enrich, (
        "the per-(event, bookmaker) fetch must be a top-1; without LIMIT 1 the lateral "
        "returns that bookmaker's entire history"
    )
    assert "OddsSnapshot.captured_at.desc()" in enrich, "latest-first ordering is gone"
    assert "OddsSnapshot.id.desc()" in enrich, (
        "the id tiebreak is what makes the pick deterministic among equal "
        "captured_at, where row_number() left it arbitrary"
    )


def test_the_bookmaker_walk_advances_strictly_and_terminates():
    """A recursive CTE that does not strictly advance does not return — it spins until
    the statement timeout, turning the fastest stage into the slowest failure.

    `OddsSnapshot.bookmaker > prev` is the termination proof: each step takes the
    MINIMUM bookmaker strictly greater than the previous, so the sequence is strictly
    increasing over a finite set and `min()` returns NULL exactly once per event. `>=`
    would re-select the same bookmaker forever."""
    enrich = _enrichment_source()

    assert "OddsSnapshot.bookmaker > _prev.c.bookmaker" in enrich, (
        "the walk must advance STRICTLY (`>`); `>=` re-selects the same bookmaker and "
        "the recursive CTE never terminates"
    )
    # BOTH arms, counted. A first version of this guard asserted only that the
    # substring appeared somewhere, and a mutation that turned the RECURSIVE arm's
    # `min()` into `max()` sailed through it — the seed arm's `min()` satisfied the
    # assertion while the walk jumped straight to the last bookmaker and dropped every
    # one in between. That is a silent wrong answer (a book's odds simply missing),
    # which is exactly the class this file exists to catch.
    assert enrich.count("func.min(OddsSnapshot.bookmaker)") == 2, (
        "both the seed and the recursive arm must take the MINIMUM of the remaining "
        "bookmakers; anything else skips bookmakers and silently drops their odds"
    )
    assert "func.max(" not in enrich, (
        "a max() anywhere in the walk reverses it: the seed starts at the last "
        "bookmaker and the walk terminates immediately, returning one book instead "
        "of all of them"
    )
    assert "_prev.c.bookmaker.isnot(None)" in enrich, (
        "the recursive term must stop descending once a NULL terminator is produced"
    )
    assert "bookmakers.c.bookmaker.isnot(None)" in enrich, (
        "the NULL terminator row must be filtered out of the final select"
    )


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
        # LAT-P111 re-pointed the anchor: the execute moved into
        # `_fetch_futures_window`, so the call site is now what the re-arm must
        # precede. The property guarded is unchanged.
        futures_at = src.find("await _fetch_futures_window(")
        assert futures_at > 0, "futures stage not found — update this guard"

        window = src[:futures_at]
        rearm = window.rfind("_apply_search_statement_timeout(db, _deadline)")
        assert rearm > 0, "futures stage does not re-arm the statement timeout"

        # ...and the re-arm is close to the stage, not left far upstream.
        assert src[rearm:futures_at].count("await db.execute(") <= 1, (
            "another query runs between the re-arm and the futures stage"
        )

    def test_the_second_futures_query_rearms_the_bound_too(self):
        """LAT-P111: the tier split made the futures stage TWO statements.

        The whole point of the LAT-P005 re-arm is that a later query must not
        inherit a bound chosen for an earlier, cheaper one. The outcome-arm
        query is now exactly that — it runs after the tier<=1 query has already
        spent part of the budget, and it is the EXPENSIVE half. A re-arm that
        covered only the first statement would restore the original defect
        inside the stage that was fixed for it.
        """
        import inspect

        from app.routes import events

        src = inspect.getsource(events._fetch_futures_window)
        outcome_at = src.find("candidates_in([outcome_arm])")
        assert outcome_at > 0, "outcome-arm query not found — update this guard"

        rearm = src[:outcome_at].rfind("_apply_search_statement_timeout(db, deadline)")
        assert rearm > 0, (
            "the outcome-arm query does not re-arm the statement timeout — it is "
            "running on whatever the tier<=1 query left behind"
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
        # LAT-P111 re-pointed the ANCHOR, not the assertion. The arms are still
        # UNIONed; the construction moved into `_futures_candidates_in` so the
        # full arm set and the tier-ordered subsets share one builder. Combining
        # them with a top-level OR is still the failure, and the sibling test
        # above still catches it.
        assert "union(*_selects)" in SEARCH_CODE, (
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
        # Assert the EFFECTIVE RULE, not the literal and not the constant's name.
        # LAT-P010 moved the 3 into a shared module constant so /search and
        # /typeahead cannot drift on where the cliff is; pinning the literal made
        # this guard fail on that correct change. LAT-P013 then found that a shared
        # CONSTANT was still the wrong thing to pin, because `len(q)` is the wrong
        # PREDICATE: `d'or` is 4 characters and pg_trgm can serve neither surface.
        # So pin the rule both surfaces must obey.
        from app.routes.events import _SEARCH_MIN_OUTCOME_MATCH_CHARS, _has_extractable_trigram

        assert _SEARCH_MIN_OUTCOME_MATCH_CHARS == 3, (
            "the threshold must be 3 — that is where the pg_trgm cliff is"
        )
        assert not _has_extractable_trigram("re"), "`re` must still be gated"
        assert _has_extractable_trigram("rec"), "`rec` must still be servable"

        assert "_has_extractable_trigram(_ta_q_compact)" in TYPEAHEAD_CODE, (
            "/typeahead must use the SHARED predicate — the two surfaces drifting "
            "is how /search kept this defect for three cycles after /typeahead's "
            "twin was fixed, and sharing only a CONSTANT was not enough to stop "
            "them both admitting `d'or`"
        )
        gate_at = TYPEAHEAD_CODE.find("if _has_extractable_trigram(_ta_q_compact)")
        arm_at = TYPEAHEAD_CODE.find("select(FuturesOutcome.market_id).where(")
        assert 0 < gate_at < arm_at, (
            "the outcome arm is not inside the unservable-pattern gate"
        )

    def test_the_gate_is_on_the_whole_query_not_on_individual_terms(self):
        """Must NOT contradict LAT-P006's guard.

        LAT-P006 pins that a short term still FILTERS inside a multi-term AND
        (`us recession` must not admit "Euro area growth"). /typeahead matches
        the WHOLE query string as one pattern, so the gate is on `q`, not on a
        per-term loop. A per-term version here would be the candidate LAT-P006
        measured and rejected.
        """
        assert "_has_extractable_trigram(_ta_q_compact)" in TYPEAHEAD_CODE, (
            "the unservable-pattern gate must test the whole query, not per-term"
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

        AMENDED BY LAT-P050, and the amendment is the point. This asserted the
        exact substring ``if not _ta_degraded:``. When the guard was STRENGTHENED
        to ``if not _ta_degraded and not debug_evidence:`` — same promise, plus a
        second answer shape that must never be cached — the test went red while
        the contract it names got stronger.

        Read the assertion as a sentence and ask whether you would sign it as a
        product claim (gotcha #130). "The source contains this exact substring"
        is not signable. "A degraded answer is never cached" is. So the sentence
        is what is asserted now: the cache write is guarded, and ``_ta_degraded``
        is part of that guard, however many other conditions join it.
        """
        setex_at = TYPEAHEAD_CODE.find("setex(_cache_key")
        assert setex_at > 0, "the cache write disappeared entirely"

        # The nearest `if` above the write, whatever its full condition.
        guard_at = TYPEAHEAD_CODE.rfind("\n    if ", 0, setex_at)
        assert guard_at > 0, "the cache write is not under any guard"
        guard_line = TYPEAHEAD_CODE[guard_at:TYPEAHEAD_CODE.find(":", guard_at)]

        assert "not _ta_degraded" in guard_line, (
            "CACHE_DECISION_DISHONEST: a degraded typeahead answer is being "
            "written to Redis and will be served for the full 45s TTL. "
            f"guard found: {guard_line.strip()!r}"
        )

    def test_a_debug_evidence_answer_is_never_cached(self):
        """The mirror image, LAT-P050. A debug answer is not incomplete, it is
        EXTRA — and caching it would serve `_evidence` to every normal user
        typing that prefix for the full TTL. It must also never READ the cache,
        or it returns a normal entry with no echo and the eval capture silently
        records low fidelity while believing it asked for high.

        Behaviour is covered by
        `tests/integration/test_route_typeahead_evidence_echo.py::TestCacheIsolation`
        against a seeded route; this is the cheap structural companion.
        """
        setex_at = TYPEAHEAD_CODE.find("setex(_cache_key")
        guard_at = TYPEAHEAD_CODE.rfind("\n    if ", 0, setex_at)
        guard_line = TYPEAHEAD_CODE[guard_at:TYPEAHEAD_CODE.find(":", guard_at)]
        assert "not debug_evidence" in guard_line, (
            "a debug-evidence answer is being written to the shared cache"
        )
        assert "not debug_timing" in guard_line, (
            "a debug-timing answer is being written to the shared cache — every "
            "normal user typing that prefix would be served per-stage server "
            f"timings for the full TTL (#1866). guard found: {guard_line.strip()!r}"
        )

        # Read the CONTRACT, not a literal — gotcha #130, and this is its second
        # instance in the same test. LAT-P050 converted the WRITE assertion above
        # to "nearest `if`, whatever its full condition, then substring" after a
        # strengthening turned it red; it left this one pinned to
        # `"if not debug_evidence:"`, and LAT-P054 turned it red again by adding
        # `and not debug_timing`. A guard that gets STRONGER must never fail the
        # test that exists to keep it strong, so this now uses the same shape.
        read_at = TYPEAHEAD_CODE.find("_rc.get(_cache_key)")
        assert read_at > 0, "the cache read disappeared"
        guard_at = TYPEAHEAD_CODE.rfind("\n    if ", 0, read_at)
        assert guard_at > 0, "the cache read is not under any guard"
        read_guard = TYPEAHEAD_CODE[guard_at:TYPEAHEAD_CODE.find(":", guard_at)]
        assert "not debug_evidence" in read_guard, (
            "the cache READ is not gated on debug_evidence — a debug request "
            f"can be served a normal cached answer with no `_evidence`. "
            f"guard found: {read_guard.strip()!r}"
        )
        assert "not debug_timing" in read_guard, (
            "the cache READ is not gated on debug_timing (#1866) — a cached "
            "entry carries no `debug_timing` key, so serving one answers a "
            "timing request with SILENCE, which reads exactly like a stage that "
            "cost nothing (gotcha #53), on the very miss path #1866 measures. "
            f"guard found: {read_guard.strip()!r}"
        )

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
        assert "_has_extractable_trigram(_ta_q_compact)" in TYPEAHEAD_CODE
        assert "if not _has_extractable_trigram(term):" in SEARCH_CODE, (
            "/search no longer gates its outcome arm on the shared predicate"
        )

    def test_the_gate_is_only_on_the_single_term_path(self):
        """Must not contradict LAT-P006's multi-term guard.

        LAT-P006 pins that a short term still FILTERS inside a multi-term AND
        (`us recession` must not admit "Euro area growth"). Applying this gate
        per-term would break that. The multi-term branch stays untouched.
        """
        # Anchor on the FUTURES block, not on `if len(terms) > 1:`. There are two
        # of those in search_events and the first belongs to the EVENT team filter,
        # so this slice used to start ~11k characters early: `head` was the events
        # branch and `tail` swallowed the whole futures block, which made the
        # "not in head" half of this test vacuous. LAT-P013 caught it by mutation —
        # leaking the gate into the multi-term futures branch stayed green.
        assert SEARCH_CODE.count("futures_name_conditions = [") == 1
        multi = SEARCH_CODE[
            SEARCH_CODE.find("futures_name_conditions = [") : SEARCH_CODE.find("futures_name_match = futures_name_ilike")
        ]
        head, sep, tail = multi.partition("    else:")
        assert sep, "the single-term futures branch is gone — slice anchors are stale"
        assert "_has_extractable_trigram" not in head, (
            "the unservable-pattern gate leaked into the MULTI-term branch — that "
            "is the candidate LAT-P006 measured and rejected, and it would break "
            "the `us recession` / 'Euro area growth' guard.\n"
            "LAT-P013 re-verified the scoping against a control rather than "
            "inheriting it: `ballon or` — an explicit 2-char token inside a "
            "multi-term AND — measured 85ms in production against a 36ms control, "
            "because the ANDed arms let the selective term drive. The multi-term "
            "path does not have this defect and must not be 'fixed'."
        )
        assert "_has_extractable_trigram" in tail, (
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

    def test_the_predicate_is_the_alnum_run_not_the_length(self):
        """LAT-P013/#1494 — `len(term) < 3` is the wrong proxy for "unservable".

        pg_trgm splits a pattern on non-alphanumerics before extracting trigrams,
        so what decides servability is the longest ALPHANUMERIC RUN, not the
        length. `d'or` is 4 characters and yields no trigram at all.

        MEASURED in production 2026-08-09, paired against a LENGTH-MATCHED control
        4s apart so length is held constant and the run is the only variable:
            q=d'or  (len 4, run 2)  futures 19,171ms / 13,677ms
            q=dora  (len 4, run 4)  futures      615ms
        22-31x, and `d'or` blew the deadline outright: HTTP 200 with
        `degraded: [futures, teams]` — a wrong answer, not merely a slow one.
        """
        from app.routes.events import _has_extractable_trigram as servable

        # Unservable — no run of 3 alphanumerics. All four are len >= 4, so the
        # OLD length gate admitted every one of them.
        for q in ("d'or", "u.s.", "a.i.", "a.j.", "a-b-c", "30-30"):
            assert not servable(q), f"{q!r} yields no pg_trgm trigram but is admitted"
            assert len(q) >= _MIN_LEN_THE_OLD_GATE_ADMITTED, (
                f"{q!r} must be a case the old len() gate could not catch, "
                "otherwise it proves nothing"
            )

        # Servable — a run of >= 3 survives punctuation around it.
        for q in ("dora", "o'neal", "l.a. lakers", "nba", "2026", "José"):
            assert servable(q), f"{q!r} is servable and must not be gated"

    def test_the_new_predicate_still_gates_everything_the_old_one_did(self):
        """A widening, never a narrowing.

        LAT-P010's gate must keep firing on exactly what it fired on before, or
        this queue silently re-opens the defect it was written to close. A term
        under 3 characters cannot contain a run of 3, so the new rule is a strict
        superset — asserted, not argued.
        """
        from app.routes.events import (
            _SEARCH_MIN_OUTCOME_MATCH_CHARS as FLOOR,
            _has_extractable_trigram as servable,
        )
        import itertools
        import string

        alphabet = string.ascii_lowercase[:6] + string.digits[:3] + ".'- "
        for n in range(1, FLOOR):
            for combo in itertools.product(alphabet, repeat=n):
                term = "".join(combo)
                assert not servable(term), (
                    f"{term!r} is under the {FLOOR}-char floor that LAT-P010 "
                    "gated, but the new predicate would let it through"
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
        assert "_has_extractable_trigram(term)" in SEARCH_CODE
        assert "_has_extractable_trigram(_ta_q_compact)" in TYPEAHEAD_CODE


# ---------------------------------------------------------------------------
# LAT-P030 — the CI rail that runs the real-Postgres gates.
#
# Both search gates that need a real database live in ONE job (`search-recall`),
# because it is the only job with a Postgres service. Nothing asserted that the
# job existed, that it pointed at those files, or that it still failed on a skip
# — so the entire rail could be deleted, or quietly reduced to a no-op, without
# a single test going red.
#
# That is not a hypothetical failure mode for this lane. It is the SAME failure
# the job's own inline comments were written to prevent one level down ("pytest
# exits 0 when every test skips, and a silently-skipped gate reads exactly like
# a passing one"). The step defends itself against skipping; nothing defended
# the step.
# ---------------------------------------------------------------------------
class TestTheRealPostgresRailExists:
    """The gates only mean something if a job still runs them."""

    @staticmethod
    def _job():
        import pathlib

        import yaml

        ci = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
        assert ci.exists(), f"ci.yml not found at {ci}"
        jobs = yaml.safe_load(ci.read_text())["jobs"]
        assert "search-recall" in jobs, (
            "the `search-recall` job is gone — every real-Postgres search gate now "
            "skips, and pytest exits 0 on an all-skipped run, so CI stays green "
            "while nothing is checked"
        )
        return jobs["search-recall"]

    def test_the_job_still_provides_a_real_postgres(self):
        job = self._job()
        services = job.get("services") or {}
        assert "postgres" in services, (
            "the Postgres service container is gone; the gates will skip"
        )
        env = job.get("env") or {}
        assert "SEARCH_TEST_DATABASE_URL" in env, (
            "SEARCH_TEST_DATABASE_URL is what arms both gates — without it they skip"
        )

    @pytest.mark.parametrize("gate", [
        "tests/integration/test_search_recall_contract.py",
        "tests/integration/test_search_odds_enrichment_equivalence.py",
    ])
    def test_every_real_postgres_gate_is_actually_invoked(self, gate):
        """A gate file that no job names is a file that never runs."""
        steps = self._job().get("steps") or []
        runs = "\n".join(s.get("run", "") for s in steps)
        assert gate in runs, (
            f"{gate} is not invoked by the search-recall job. It requires real "
            "Postgres, so it skips everywhere else — adding the file without "
            "adding it here means it has never once executed."
        )

    def test_every_gate_step_still_fails_on_a_silent_skip(self):
        """`pytest` exits 0 when every test skips. Each gate step must detect that
        itself; otherwise a dropped service container reads as a pass."""
        steps = self._job().get("steps") or []
        gate_steps = [
            s for s in steps
            if "tests/integration/test_search" in (s.get("run") or "")
        ]
        assert len(gate_steps) >= 2, (
            f"expected both real-Postgres gate steps, found {len(gate_steps)}"
        )
        for step in gate_steps:
            assert "skipped" in step["run"], (
                f"step {step.get('name')!r} does not fail on an all-skipped run"
            )


# ---------------------------------------------------------------------------
# LAT-P031 / #1494 — the EVENT recall arms, same defect one table over.
#
# `or_(team_filter, Sport.key.in_(sport_alias_keys))` puts a trigram-servable
# ILIKE and a joined-column IN inside one top-level OR. No single index serves
# both, so the planner abandons both and drives off `ix_events_status_commence`,
# heap-scanning the whole 30-day window and filtering row by row.
#
# The tell is that the cost does not depend on the answer. MEASURED in production
# 2026-08-11 (`db-query` EXPLAIN ANALYZE/BUFFERS, two warm passes each): the OR
# form touches **6,416 shared blocks for every league query**, whether it returns
# 0 rows (`golf`) or 2,013 (`tennis`). The UNION form touches 59 / 584 / 1,522.
#
#     query     OR (exec / blocks)      UNION (exec / blocks)
#     golf       65.6-176.8ms / 6,416     6.8-11.7ms /    59
#     nfl         79.5-95.7ms / 6,416     4.1-48.8ms /   584
#     tennis      53.6-59.6ms / 6,416     9.7-10.2ms / 1,522
#
# End to end that was `event_count` = 932ms of a 1,097ms `golf` request, to count
# ZERO events. Recall is preserved by construction (A OR B and A UNION B select
# the same set) and was verified against production anyway: 8/8 league queries
# returned identical counts through both forms.
# ---------------------------------------------------------------------------
class TestEventRecallArmsAreUnionedNotOred:
    """Guard the SHAPE. LAT-P006 proved it for futures; this is the event half."""

    def test_league_arm_is_not_ored_into_the_team_filter(self):
        assert "or_(team_filter, league_scope)" not in SEARCH_CODE, (
            "EVENT_ARMS_ORED reintroduced: the league arm is being OR'd into the "
            "event predicate again. Measured 6,416 shared blocks on EVERY league "
            "query regardless of the answer (golf 932ms of a 1,097ms request, for "
            "zero events) versus 59-1,522 blocks for the set-identical UNION."
        )

    def test_recall_arms_are_combined_with_a_union(self):
        assert "union(*_event_arm_selects)" in SEARCH_CODE, (
            "the UNION of the event recall arms is gone — if the arms are "
            "combined some other way, re-point this guard deliberately"
        )

    def test_scope_conditions_are_pushed_into_each_arm(self):
        """AND distributes over UNION. An unfiltered arm hands the outer query
        every out-of-window event it matches."""
        assert "select(Event.id)" in SEARCH_CODE, (
            "the per-arm id select is gone from the event candidate filter"
        )
        assert ".where(arm, *event_scope_conditions)" in SEARCH_CODE, (
            "the scope conditions (window, status, sport, tags) are no longer "
            "pushed into each UNION arm"
        )

    def test_the_outer_query_still_carries_the_scope_conditions(self):
        """Deliberate redundancy, matching the futures precedent: the predicate
        stays correct if the push-down is ever removed."""
        assert "*event_scope_conditions," in SEARCH_CODE

    def test_recall_is_not_narrowed_because_both_arms_survive(self):
        """The league arm must be ADDED to the arm list, never replace the name arm.

        A UNION that lost an arm is the silent failure this whole class of change
        risks: it reads fine, compiles fine, and halves recall.
        """
        assert "_event_recall_arms = [team_filter]" in SEARCH_CODE, (
            "the name arm must be the base of the arm list"
        )
        assert "_event_recall_arms.append(league_scope)" in SEARCH_CODE, (
            "the league arm must be APPENDED — if it replaces team_filter, a "
            "league query stops matching by team name entirely"
        )

    def test_the_no_league_token_path_is_a_single_bare_arm(self):
        """The common path (no sport alias in the query) must compile to exactly
        what it did before this change — one predicate, no UNION, no id-IN."""
        assert "event_conditions = [_event_recall_arms[0], *event_scope_conditions]" in SEARCH_CODE, (
            "the no-alias path no longer bypasses the UNION machinery; every "
            "ordinary query would pay for a subquery it does not need"
        )
        assert "if len(_event_recall_arms) > 1:" in SEARCH_CODE, (
            "the single-arm fast path is gone"
        )

    def test_the_ored_shape_would_fail_this_guard(self):
        """Mutation check — the guard must reject the shape it replaced.

        A guard that passes on the defect is not a guard. This reconstructs the
        exact pre-LAT-P031 line and asserts the check above discriminates.
        """
        reverted_shape = "        team_filter = or_(team_filter, league_scope)\n"
        assert "or_(team_filter, league_scope)" in reverted_shape
        assert "or_(team_filter, league_scope)" not in SEARCH_CODE, (
            "the mutation check and the live source disagree — the guard is not "
            "actually discriminating"
        )

    def test_the_union_survives_compilation_as_a_single_scalar_subquery(self):
        """Compiled, not source-matched: `union()` of one arm, or a stray
        `intersect()`, reads fine and silently halves recall.

        Also pins that BOTH arms reach the SQL — the name arm's ILIKE and the
        league arm's `sports.key IN` must each appear.
        """
        from sqlalchemy import union as _union

        team_arm = Event.home_team_name.ilike("%golf%")
        league_arm = Sport.key.in_(["golf_pga", "golf_lpga"])
        scope = (Event.status.in_(["scheduled", "live"]),)
        candidates = _union(
            *[
                select(Event.id).join(Sport, Event.sport_id == Sport.id).where(arm, *scope)
                for arm in (team_arm, league_arm)
            ]
        ).subquery()
        sql = _compile(
            select(Event).where(Event.id.in_(select(candidates.c.id)), *scope)
        ).upper()

        assert " UNION " in sql, "the arms did not compile to a UNION"
        assert "INTERSECT" not in sql, "an INTERSECT would silently halve recall"
        assert "EXCEPT" not in sql, "an EXCEPT would silently subtract an arm"
        assert "ILIKE" in sql or "LIKE" in sql, "the name arm vanished from the UNION"
        assert "SPORTS.KEY" in sql, "the league arm vanished from the UNION"
        # status appears once per arm plus once on the outer query.
        assert sql.count("EVENTS.STATUS") >= 3, (
            "the scope filter is not present in every arm plus the outer query"
        )

    def test_union_and_or_are_set_identical_on_the_same_arms(self):
        """The recall argument this change rests on, asserted rather than trusted.

        Not a database test — a set-algebra one. If someone later swaps the UNION
        for something that is not set-identical to the OR it replaced, the premise
        of the whole change is void and this fails.
        """
        universe = list(range(60))
        arm_a = {n for n in universe if n % 3 == 0}
        arm_b = {n for n in universe if n % 5 == 0}
        ored = {n for n in universe if n in arm_a or n in arm_b}
        unioned = arm_a | arm_b
        assert ored == unioned
        # and an event matching BOTH arms is counted once, which is why the
        # implementation uses UNION and not UNION ALL.
        both = arm_a & arm_b
        assert both and len(unioned) == len(arm_a) + len(arm_b) - len(both)


# ---------------------------------------------------------------------------
# LAT-P034 / #1732 (events half) — word about-ness in the events results bucket
# ---------------------------------------------------------------------------

class TestEventsBucketRequiresWordAboutness:
    """`fed` must stop returning twenty-five people named Federico.

    The futures half of #1732 was a ranking bug — the right rows were present and
    scored zero. The events half is not: no event is about the Fed, so there is
    nothing to promote, and the only honest fix is to stop calling a spelling
    coincidence a match. See `_event_name_match` for the measured recall delta and
    for the two losses this knowingly accepts.
    """

    def _sql(self, term, expansion=None):
        return _compile(
            select(Event.id).where(events_route._event_name_match(term, expansion))
        )

    def _literal_sql(self, term, expansion=None):
        """`_compile` keeps bind params, which is right for shape assertions but
        hides the VALUES — and the expansion bug this guards is about a value
        reaching one half and not the other."""
        return str(
            select(Event.id)
            .where(events_route._event_name_match(term, expansion))
            .compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )

    def test_both_halves_are_present(self):
        sql = self._sql("fed")
        assert "ILIKE" in sql, (
            "the substring arm is gone — that is the trigram-indexable half, and "
            "without it the predicate cannot use ix_events_home_trgm at all"
        )
        assert "to_tsvector" in sql and "websearch_to_tsquery" in sql, (
            "the word-boundary arm is gone; `fed` matches Federico again"
        )

    def test_both_columns_are_covered_on_both_halves(self):
        """Qualified as `events.<col>`, and counted per HALF.

        A bare `sql.count("away_team_name")` does not work and the mutation run
        proved it: with bind params the placeholder is itself named
        `%(away_team_name_1)s`, so one arm reads as two and dropping the away FTS
        arm sailed through.
        """
        sql = self._sql("fed")
        ilike_half, _, fts_half = sql.partition("to_tsvector")
        for half, name in ((ilike_half, "ILIKE"), ("to_tsvector" + fts_half, "FTS")):
            for col in ("events.home_team_name", "events.away_team_name"):
                assert col in half, (
                    f"{col} is missing from the {name} half — a match on that "
                    "column would be silently dropped or silently admitted"
                )

    def test_an_expansion_widens_both_halves_identically(self):
        """Rank and recall agreeing was LAT-P033's whole finding (`exp if exp else
        term` REPLACED a term instead of widening it). The same trap is available
        here: an expansion that reaches the ILIKE half but not the FTS half would
        AND itself away to nothing."""
        sql = self._literal_sql("fed", "federal reserve")
        ilike_half, _, fts_half = sql.partition("to_tsvector")
        # Per-half tokens, because the two halves render the same term
        # differently: ILIKE wraps it (`'%%fed%%'`), FTS passes it whole
        # (`'fed'`). Both must be QUOTED and not bare — "federal reserve" contains
        # the letters "fed", so a bare substring count reads the expansion as the
        # term and the replacement bug passes unnoticed. Both traps were found by
        # the mutation run, one of them after a first fix that only looked right.
        halves = (
            (ilike_half, "ILIKE", "'%%fed%%'", "'%%federal reserve%%'"),
            ("to_tsvector" + fts_half, "FTS", "'fed'", "'federal reserve'"),
        )
        for half, name, term_tok, exp_tok in halves:
            assert half.count(exp_tok) == 2, (
                f"the expansion reaches {half.count(exp_tok)} of the two columns "
                f"on the {name} half — an expansion that widens only one half "
                "ANDs itself away to nothing"
            )
            assert half.count(term_tok) == 2, (
                f"the ORIGINAL term appears {half.count(term_tok)} of the expected "
                f"2 times on the {name} half. That is LAT-P033's exact bug "
                "(`exp if exp else term`) arriving on a new surface."
            )

    def test_the_predicate_is_used_by_every_event_recall_arm(self):
        """Including the league arm's remaining terms. `nba fed` must not smuggle
        the substring match back in through the UNION's league side."""
        assert "team_filter = _event_name_match(term, expansion)" in SEARCH_CODE
        assert "_event_name_match(t, e) for t, e in expanded" in SEARCH_CODE
        assert "_event_name_match(t, e) for t, e in non_league_expanded" in SEARCH_CODE

    def test_no_minimum_length_constant_gates_the_rule(self):
        """A length threshold was measured and rejected: it lets `apple` ->
        Appleton straight back in while looking principled."""
        src = inspect.getsource(events_route._event_name_match)
        body = src.split('"""')[-1]
        assert not re.search(r"len\(\s*term\s*\)", body), (
            "a minimum-length gate is back in _event_name_match"
        )

    def test_typeahead_keeps_its_substring_recall(self):
        """Progressive typing is the surface where a prefix SHOULD match — it is
        the reason the truncation loss (`yank` -> Yankees) is acceptable here. If
        typeahead ever adopts this rule too, that argument is void."""
        ta = _strip_comments(_source_of(events_route.typeahead_search))
        assert "_build_expanded_ilike(Event.home_team_name" in ta, (
            "typeahead lost its substring recall; the events-bucket word rule is "
            "no longer safe, because nothing serves partial typing"
        )
        assert "_event_name_match" not in ta


class TestDidYouMeanDoesNotSubstituteForFilteredRows:
    """A correction is for "your query matched nothing", not for "your query
    matched things we judged irrelevant".

    Measured on production 2026-08-11: the queries the word rule newly empties draw
    corrections of `ipo` -> IPK, `yank` -> Petr Yan, `pats` -> Paterno, `sox` ->
    Sora. Firing there would trade one noise class for a worse one — worse because
    a substitution is asserted to the user as an answer.
    """

    def test_the_guard_runs_before_the_correction(self):
        assert "had_substring_match" in SEARCH_CODE
        guard_at = SEARCH_CODE.index("had_substring_match = await db.scalar")
        use_at = SEARCH_CODE.index("and not had_substring_match")
        assert guard_at < use_at

    def test_the_correction_is_gated_on_the_guard(self):
        """Not just computed — actually consulted."""
        assert "and not had_substring_match" in SEARCH_CODE, (
            "the substring guard is computed and then ignored, so did-you-mean "
            "still substitutes a fuzzy team for rows we deliberately filtered"
        )

    def test_the_guard_tests_substring_recall_not_the_filtered_predicate(self):
        """If the guard used `_event_name_match` it would be asking the question we
        already know the answer to (zero) and would always fire the correction."""
        region = SEARCH_CODE[
            SEARCH_CODE.index("substring_only = ["):
            SEARCH_CODE.index("had_substring_match = await db.scalar")
        ]
        assert "_build_expanded_ilike" in region
        assert "_event_name_match" not in region
        assert "to_tsvector" not in region

    def test_the_guard_fails_closed(self):
        """An unknown answer must NOT license a substitution — the guard exists to
        prevent one. Failing open would silently restore the behaviour it removes."""
        src = SEARCH_SRC
        region = src[src.index("search word-boundary guard failed"):]
        handler = region.split("if (")[0]
        assert "had_substring_match = True" in handler, (
            "the guard fails open on error, so a failure re-enables the very "
            "substitution it was added to prevent"
        )
        assert "_recover_search_session" in handler, (
            "the guard's handler does not roll back. ANY error here — not only a "
            "timeout — leaves the transaction aborted, and every later stage then "
            "fails on InFailedSqlTransaction (#1494 1e)."
        )

    def test_the_guard_is_confined_to_the_already_empty_path(self):
        """It must never run on the hot path — it is an extra query."""
        guard_at = SEARCH_CODE.index("substring_only = [")
        trigger_at = SEARCH_CODE.index("if total_count == 0 and not degraded")
        assert trigger_at < guard_at, (
            "the substring guard moved outside the total_count == 0 branch and "
            "now costs every search an extra EXISTS"
        )


# ---------------------------------------------------------------------------
# LAT-P035 / #1758 (futures half) + the empty-tsquery hole it exposed
# ---------------------------------------------------------------------------

class TestFuturesNameArmRequiresWordAboutness:
    """`nba champion` must stop returning nine ITF tennis set markets.

    Measured live on v3775: rank 1 was the real "NBA: 2027 Champion" and ranks
    2-10 were "Set N Winner: … vs Zhiyenbayeva" — `nba` is spelled inside the
    surname and `champion` expands to `winner`. See `_futures_name_match_term`
    for why this had to be the WHERE and not the tier (only THREE of the twelve
    name-arm rows pass the word test, so sinking the rest still fills the page
    with them).
    """

    def _sql(self, term, expansion=None):
        return _compile(
            select(FuturesMarket.id).where(
                events_route._futures_name_match_term(term, expansion)
            )
        )

    def test_both_halves_are_present_and_anded(self):
        """AND-ed, never OR-ed — 1c's lesson, restated for futures.

        One unindexable arm inside a top-level OR forces a seq scan for the whole
        predicate. AND-ed, the trigram GIN drives and `to_tsvector` is a recheck
        over the rows it already returned. Measured on production: blocks were
        IDENTICAL (1,234) before and after, warm exec 9.8ms -> 4.8ms.
        """
        sql = self._sql("nba")
        assert "ILIKE" in sql, (
            "the substring arm is gone — that is the half ix_futures_markets_name_trgm "
            "can actually serve"
        )
        assert "to_tsvector" in sql and "websearch_to_tsquery" in sql, (
            "the word-boundary arm is gone; `nba champion` returns Zhiyenbayeva again"
        )
        ilike_at = sql.index("ILIKE")
        fts_at = sql.index("to_tsvector")
        assert " AND " in sql[ilike_at:fts_at], (
            "the FTS arm is no longer AND-ed to the ILIKE arm. OR-ed at the top "
            "level it defeats the trigram index for the whole predicate."
        )

    def test_the_arm_is_used_on_both_the_single_and_multi_term_paths(self):
        """The two branches are easy to fix by halves — `nba champion` is
        multi-term, so a single-term-only fix would look green on the very query
        that motivated the change while leaving `champion` alone broken."""
        body = _strip_comments(inspect.getsource(events_route.search_events))
        # Anchored on the futures block specifically: `if len(terms) > 1:` also
        # appears earlier for the EVENT team filter, and partitioning on the first
        # one silently tested the wrong region (caught on the first run of this test).
        region = body[body.index("def _outcome_id_match"):]
        region = region[region.index("if len(terms) > 1:"):]
        multi, sep, single = region.partition("\n    else:")
        assert sep, "the futures single/multi-term branch structure changed"
        assert region.count("_futures_name_match_term(") == 2, (
            "the futures name arm is built somewhere other than the two known "
            "call sites — one path is not word-tested"
        )
        assert "_futures_name_match_term(" in multi, "the MULTI-term path lost the word test"
        assert "_futures_name_match_term(" in single, "the SINGLE-term path lost the word test"

    def test_a_lexemeless_term_cannot_zero_the_conjunction(self):
        """The empty-tsquery hole, which is a FALSE match and not a skipped one.

        `websearch_to_tsquery('english','and')` is EMPTY and `tsvector @@ ''` is
        FALSE, so an AND-ed word test over a stopword rejects every row. Confirmed
        live on v3775 BEFORE the guard: `q=dodgers` returned 25 events and
        `q=dodgers and cubs` returned 0. Without this the futures half also loses
        gold probe `taylor swift pregnant by...?`, whose market matches only
        through the literal term `by...?`.
        """
        for term in ("and", "nba"):
            assert "numnode" in self._sql(term), (
                f"the lexeme-less guard is missing for {term!r}; a stopword or "
                "punctuation-only term now rejects every row instead of abstaining"
            )
        # `by...?` reaches the same safety by the OTHER door since LAT-P037: its
        # longest alphanumeric run is 2, so it is a FRAGMENT and the word test does
        # not vote on it at all. Assert the stronger property rather than the
        # guard's presence — a term with no word arm cannot zero a conjunction that
        # does not exist. (Asserting `numnode` here is what this test did before the
        # exemption, and it would now fail on a change that made the probe SAFER.)
        assert "to_tsvector" not in self._sql("by...?"), (
            "gold probe `taylor swift pregnant by...?` matches market 112868 ONLY "
            "through the literal term `by...?`; word-testing a fragment drops it"
        )
        assert "numnode" in _compile(
            select(Event.id).where(events_route._event_name_match("and", None))
        ), "the events arm lost the guard — `dodgers and cubs` returns zero events again"

    def test_the_guard_abstains_rather_than_matches(self):
        """`numnode(...) = 0` must be OR-ed IN BESIDE the FTS arms, not AND-ed.

        AND-ed it would require the term to be lexeme-less, inverting the rule and
        rejecting every real query.
        """
        sql = str(
            select(FuturesMarket.id)
            .where(events_route._futures_name_match_term("and", None))
            .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )
        guard = "numnode(websearch_to_tsquery('english', 'and')) = 0"
        assert guard in sql
        after = sql[sql.index(guard) + len(guard):]
        assert after.lstrip().startswith("OR"), (
            "the lexeme-less guard is AND-ed, not OR-ed — that inverts it into a "
            "requirement that the term be a stopword"
        )

    def test_the_outcome_arm_is_deliberately_not_word_tested(self):
        """A DECISION, guarded so the next cycle makes it on purpose.

        LAT-P035 measured that applying this rule to the outcome arm would cut its
        candidate markets by ~95% (`fed`: 1,027 -> 47). Its page-level junk was
        already removed by LAT-P033's tiering (verified live: `fed` returns 10/10
        real Fed markets), so what remains is COST, not correctness — a separate
        change needing its own before/after. If you are here because this failed,
        you are changing recall on the arm whose emptying got LAT-P002 reverted.
        """
        body = _strip_comments(inspect.getsource(events_route.search_events))
        outcome_def = body[body.index("def _outcome_id_match"):]
        outcome_def = outcome_def[:outcome_def.index("\n    if len(terms)")]
        # Every spelling of "word test", not just the compiled-SQL one. The first
        # draft asserted only `to_tsvector`, and the mutation run walked straight
        # through it: the route calls `_build_expanded_fts`, so the literal string
        # `to_tsvector` never appears in this source at all.
        for banned in ("_build_expanded_fts", "_fts_filter", "_term_has_no_lexemes",
                       "_futures_name_match_term", "to_tsvector"):
            assert banned not in outcome_def, (
                f"the outcome arm gained a word test ({banned}). That is a ~95% "
                "recall cut (measured on `fed`: 1,027 candidate markets -> 47) on an "
                "arm whose contribution is already invisible at the page boundary — "
                "measure it and give it its own gate, do not inherit this one's."
            )


class TestTheWordTestDoesNotVoteOnAFragment:
    """LAT-P037/#1758 — the boundary whose absence got LAT-P035 reverted whole.

    This is the oracle that could have caught it **here**, in the sandbox, with
    no Postgres. The test that actually caught it —
    `test_short_single_term_search_still_answers` — needs a real database, so it
    runs only in CI's `search-recall` job, and the lane shipped green and blind.
    A compiled-SQL assertion cannot prove RECALL, but the thing that broke was
    not recall in general: it was a RULE'S BOUNDARY, and a boundary is exactly
    what compiled SQL can prove.

    The failure it reproduces, from CI 31532329159::

        'a 2-char query lost its name matches too: got []. Only the OUTCOME arm
         should be dropped below 3 characters.'
    """

    def _futures_sql(self, term, expansion=None):
        return _compile(
            select(FuturesMarket.id).where(
                events_route._futures_name_match_term(term, expansion)
            )
        )

    def test_a_two_character_term_keeps_its_name_arm(self):
        """`re` must still be able to find "US Recession in 2026?".

        The word test cannot: `re` produces the lexeme `re`, "Recession" stems to
        `recess`, so AND-ing it returns FALSE for every row and the bucket empties.
        """
        sql = self._futures_sql("re")
        assert "ILIKE" in sql, "the 2-char name arm lost its substring recall"
        assert "to_tsvector" not in sql, (
            "the word test votes at two characters again. It can only ever vote "
            "FALSE there (`re` -> lexeme `re`, `Recession` -> `recess`), so the "
            "futures bucket returns EMPTY for a legal query. This is the exact "
            "defect that reverted LAT-P035 as e22576db."
        )
        assert "numnode" not in sql, (
            "the lexeme-less guard is pointless below the boundary — there is no "
            "conjunction left for it to rescue"
        )

    def test_the_expansion_of_a_short_term_is_not_word_tested_either(self):
        """`la` -> `los angeles` takes the fragment's exemption with it.

        The exemption is a property of the TERM the user typed, not of the phrase
        we substituted for it. Word-testing only the expansion would reintroduce
        the empty bucket for every short query that happens to carry a synonym.
        """
        assert "to_tsvector" not in self._futures_sql("la", "los angeles")

    def test_three_characters_still_votes(self):
        """The boundary has to hold in BOTH directions or it is not a boundary.

        `nba` is three characters and IS word-tested — that is what stops
        `nba champion` from answering with nine "… vs Zhiyenbayeva" set markets.
        A blanket exemption would look green on the test above and quietly undo
        the entire queue.
        """
        sql = self._futures_sql("nba")
        assert "to_tsvector" in sql and "numnode" in sql

    def test_the_boundary_is_the_shared_helper_and_not_a_second_constant(self):
        """One cliff, one definition.

        `/search` and `/typeahead` drifted for three cycles because the sub-3-char
        rule was written twice; LAT-P013 then replaced `len(term)` with the
        alphanumeric-run rule after measuring `d'or` at 19,171ms against its own
        length-matched control (`dora`, 615ms). A re-hand-rolled `len(term) < 3`
        here would be the third copy and would be wrong about `u.s.`, `a.i.` and
        `d'or` — all length 4, all fragments.
        """
        # Body only — split off the docstring, which discusses `len(term)` at
        # length precisely because it is the wrong proxy. A source assertion that
        # reads its own subject's prose fails on the explanation of the rule it is
        # enforcing (this test did, on its first run).
        src = _strip_comments(
            inspect.getsource(events_route._futures_name_match_term).split('"""')[2]
        )
        assert "_has_extractable_trigram(term)" in src, (
            "the fragment boundary is no longer the shared helper"
        )
        assert "len(term)" not in src, (
            "length is back as the proxy. It cannot see `u.s.`/`a.i.`/`d'or` — "
            "measured 22-31x their own length-matched controls (LAT-P013)."
        )

    def test_a_short_term_still_filters_inside_a_multi_term_and(self):
        """The exemption must not become LAT-P010's leak.

        In `us recession`, `us` is exempt from the WORD test but keeps its
        substring ILIKE, so a market matching only `%recession%` still stays out.
        `test_multi_term_short_token_still_filters_after_lat_p010` asserts the same
        property against real Postgres; this asserts it against the predicate.
        """
        sql = self._futures_sql("us")
        assert "ILIKE" in sql and "to_tsvector" not in sql

    def test_the_events_arm_is_left_alone_on_purpose(self):
        """A DECISION, pinned so it is made deliberately rather than by symmetry.

        `_event_name_match` has no fragment exemption, and that is the SHIPPED,
        measured LAT-P034 behaviour: `re` went 6,597 events -> 0, one row of the
        "6 ZEROED" table that queue published. It is on master and deployed. Adding
        the exemption here would be a recall change to a live surface with no
        before/after — the LAT-P002 shape. Measure it, file it, then change it.
        """
        sql = _compile(
            select(Event.id).where(events_route._event_name_match("re", None))
        )
        assert "to_tsvector" in sql, (
            "the events name arm gained the futures fragment exemption without a "
            "measurement. It may well deserve one — `re` returns 0 events today — "
            "but that is its own before/after, not a symmetry argument."
        )


def test_numnode_stays_readable_by_the_query_plan_rail():
    """The plan rail must be able to EXPLAIN ANALYZE the search path's own SQL.

    `db-query`'s `analyze` mode refuses any function not on the pure-function
    allowlist BY NAME. The search predicate now calls `numnode`, so without this
    entry the lane cannot measure the very query it just shipped — which is how a
    latency lane goes blind. Found the hard way in this queue: the first
    EXPLAIN ANALYZE of the new predicate was refused.
    """
    from app.utils import sql_read_guard

    assert "numnode" in sql_read_guard._PURE_FUNCTIONS
    assert "numnode" in sql_read_guard._ANALYZE_CALLABLE
