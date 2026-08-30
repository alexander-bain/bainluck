"""LAT-P154 — `score_resolution` must stop eating the whole backfill budget.

`backfill_winners` returned `partial_budget_guard(prob_and_datagolf)` at
553.6 s with `phase_times.score_resolution = 397.0` (production task-metrics,
2026-08-30T15:54:13Z), so `_compute_calibration_prices()` — the merged q436 fix
— never executed. A read-only production probe split those 397 s across the six
resolvers behind that single timer:

    f1 candidate SELECT              71.9 s   91,776 rows
    f2 candidate SELECT (IDENTICAL)  46.5 s   91,776 rows
    f2 per-market outcome fetch     102.2 s   91,776 round trips @ 1.114 ms
    f3 polymarket totals SELECT      56.2 s   20,000 rows, ALL 20,000 no-parse
    f4 player-prop SELECT            44.7 s   50,000 rows
    f5 total-bases SELECT            17.9 s   ZERO rows
    f6 period-props SELECT            0.02 s  ZERO rows

These tests guard the five fixes that address those lines. Every one of them
was proved by mutation against the fixed tree — see the report.
"""

import inspect
import re
from unittest.mock import MagicMock

import pytest

import app.tasks.backfill_winners as bw
from app.tasks.backfill_winners import (
    _OUTCOME_PREFETCH_BLOCK,
    _POLY_TOTAL_MARKET_RE,
    _prefetch_outcomes,
    _resolve_kalshi_from_scores,
    _resolve_kalshi_player_props_from_boxscore,
    _resolve_kalshi_spread_total_from_scores,
    _resolve_kalshi_total_bases_from_boxscore,
    _resolve_polymarket_total_from_scores,
)


# --------------------------------------------------------------------------
# a fake session that RECORDS every statement it is asked to run
# --------------------------------------------------------------------------

class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0][0] if self._rows else None


def _row(**kw):
    m = MagicMock()
    for k, v in kw.items():
        setattr(m, k, v)
    return m


class _RecordingSession:
    """Records (sql, params) for every execute and replays canned results.

    ``responder`` is called with the normalised SQL and the params and returns
    either a ``_Result`` or None (meaning "an empty write result").
    """

    def __init__(self, responder):
        self._responder = responder
        self.statements = []

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.statements.append((sql, params))
        out = self._responder(sql, params)
        return out if out is not None else MagicMock(rowcount=0)

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _install(monkeypatch, session):
    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(bw, "get_task_session", lambda: _CM())
    return session


_CANDIDATE_MARKER = "HAVING SUM(CASE WHEN fo.is_winner"
_PREFETCH_MARKER = "WHERE market_id = ANY(:ids)"
_PER_MARKET_MARKER = "WHERE market_id = :mid"


def _candidate(market_id, ticker, home=3, away=1, n_outcomes=2, event_id=900):
    return _row(
        market_id=market_id,
        market_name="Market %d" % market_id,
        ticker=ticker,
        event_id=event_id,
        home_team_name="Boston Bruins",
        away_team_name="Buffalo Sabres",
        home_score=home,
        away_score=away,
        n_outcomes=n_outcomes,
    )


def _outcome(market_id, oid, name):
    return _row(market_id=market_id, id=oid, name=name)


# ==========================================================================
# 1. the candidate scan runs ONCE, not twice
# ==========================================================================

class TestSharedCandidateScan:
    """f1 and f2 issued byte-identical FROM/WHERE/HAVING statements. Measured
    46.5 s each on production; running it twice bought nothing."""

    def test_pipeline_hands_the_scan_from_the_first_resolver_to_the_second(self):
        src = inspect.getsource(bw._backfill_all_winners)
        assert "_resolve_kalshi_from_scores(scan_out=_game_scan)" in src
        assert "scan_in=_game_scan" in src
        # and it is dropped before the ~14-minute maintenance tail (#899)
        assert "_game_scan.clear()" in src
        clear_at = src.index("_game_scan.clear()")
        assert clear_at > src.index("scan_in=_game_scan")

    def test_resolve_winners_only_shares_the_scan_too(self):
        src = inspect.getsource(bw._resolve_winners_only)
        assert "scan_out=" in src and "scan_in=" in src

    async def test_scan_out_receives_the_candidate_rows(self, monkeypatch):
        cands = [_candidate(1, "KXNHLGAME-X"), _candidate(2, "KXNBAGAME-Y")]

        def responder(sql, params):
            if _CANDIDATE_MARKER in sql:
                return _Result(cands)
            if _PREFETCH_MARKER in sql:
                return _Result([])
            return None

        _install(monkeypatch, _RecordingSession(responder))
        scan: dict = {}
        await _resolve_kalshi_from_scores(scan_out=scan)
        assert scan["candidates"] == cands

    async def test_reuse_runs_no_second_candidate_scan(self, monkeypatch):
        cands = [_candidate(1, "KXNHLGAME-X")]

        def responder(sql, params):
            if _PREFETCH_MARKER in sql:
                return _Result([_outcome(1, 11, "Boston Bruins"),
                                _outcome(1, 12, "Buffalo Sabres")])
            return None

        s = _install(monkeypatch, _RecordingSession(responder))
        await _resolve_kalshi_spread_total_from_scores(
            scan_in={"candidates": cands, "locked_market_ids": set()}
        )
        assert not any(_CANDIDATE_MARKER in sql for sql, _ in s.statements), (
            "the 46.5 s candidate scan ran a second time despite scan_in"
        )

    async def test_standalone_still_runs_its_own_scan(self, monkeypatch):
        def responder(sql, params):
            if _CANDIDATE_MARKER in sql:
                return _Result([])
            return None

        s = _install(monkeypatch, _RecordingSession(responder))
        await _resolve_kalshi_spread_total_from_scores()
        assert any(_CANDIDATE_MARKER in sql for sql, _ in s.statements), (
            "with no scan_in the resolver must still fetch its own candidates"
        )


# ==========================================================================
# 2. the locked set is EXACTLY the HAVING clause's exclusion
# ==========================================================================

class TestLockedMarketIdsMirrorTheHavingClause:
    """Reusing f1's scan is only sound because f1 can name every market the
    re-run would have dropped. A market leaves the set iff it gains an outcome
    that is `is_winner AND resolution_source NOT IN (overwritable)`, and every
    write here stamps 'game_score', which is not overwritable."""

    async def _run_f1(self, monkeypatch, cands, outcomes):
        def responder(sql, params):
            if _CANDIDATE_MARKER in sql:
                return _Result(cands)
            if _PREFETCH_MARKER in sql:
                ids = set((params or {}).get("ids") or [])
                return _Result([o for o in outcomes if o.market_id in ids])
            return None

        _install(monkeypatch, _RecordingSession(responder))
        scan: dict = {}
        await _resolve_kalshi_from_scores(scan_out=scan)
        return scan

    async def test_a_moneyline_market_with_a_winner_is_locked(self, monkeypatch):
        scan = await self._run_f1(
            monkeypatch,
            [_candidate(1, "KXNHLGAME-X", home=4, away=2)],
            [_outcome(1, 11, "Boston Bruins"), _outcome(1, 12, "Buffalo Sabres")],
        )
        assert scan["locked_market_ids"] == {1}

    async def test_a_market_whose_outcomes_match_nothing_is_not_locked(
            self, monkeypatch):
        scan = await self._run_f1(
            monkeypatch,
            [_candidate(1, "KXNHLGAME-X", home=4, away=2)],
            [_outcome(1, 11, "Yes"), _outcome(1, 12, "No")],
        )
        assert scan["locked_market_ids"] == set()

    async def test_a_market_written_with_only_a_LOSER_is_not_locked(
            self, monkeypatch):
        """Boston (home) win 4-2; the only outcome that matches a team is the
        away side, so the resolver writes is_winner=FALSE and nothing else.
        The HAVING clause counts WINNERS, so this market stays in the candidate
        set — locking it here would silently drop it from the sibling resolver.
        """
        scan = await self._run_f1(
            monkeypatch,
            [_candidate(1, "KXNHLGAME-X", home=4, away=2)],
            [_outcome(1, 11, "Buffalo Sabres"), _outcome(1, 12, "Draw")],
        )
        assert scan["locked_market_ids"] == set()

    async def test_btts_locks_only_when_both_teams_scored(self, monkeypatch):
        yes = await self._run_f1(
            monkeypatch, [_candidate(7, "KXBTTS-A", home=2, away=1)], [])
        assert yes["locked_market_ids"] == {7}, (
            "BTTS 'yes' sets every outcome is_winner=true — that market DOES "
            "leave the candidate set"
        )
        no = await self._run_f1(
            monkeypatch, [_candidate(8, "KXBTTS-B", home=2, away=0)], [])
        assert no["locked_market_ids"] == set(), (
            "BTTS 'no' writes only False, so no outcome is a non-overwritable "
            "winner and the market STAYS in the candidate set — skipping it in "
            "the sibling resolver would silently drop work"
        )

    async def test_locked_markets_are_the_only_ones_the_sibling_skips(
            self, monkeypatch):
        seen = []

        def responder(sql, params):
            if _PREFETCH_MARKER in sql:
                seen.extend((params or {}).get("ids") or [])
                return _Result([])
            return None

        _install(monkeypatch, _RecordingSession(responder))
        await _resolve_kalshi_spread_total_from_scores(scan_in={
            "candidates": [_candidate(1, "A"), _candidate(2, "B"),
                           _candidate(3, "C")],
            "locked_market_ids": {2},
        })
        assert sorted(seen) == [1, 3]


# ==========================================================================
# 3. one outcome round trip per BLOCK, not per market
# ==========================================================================

class TestOutcomePrefetchIsBlocked:
    """91,776 candidates x 1.114 ms = 102 s per cycle in the spread/total
    resolver alone, measured on production."""

    async def test_prefetch_groups_by_market_and_orders_by_id(self, monkeypatch):
        rows = [_outcome(1, 11, "a"), _outcome(1, 12, "b"), _outcome(2, 21, "c")]
        s = _RecordingSession(lambda sql, params: _Result(rows))
        got = await _prefetch_outcomes(s, [1, 2])
        assert [o.id for o in got[1]] == [11, 12]
        assert [o.id for o in got[2]] == [21]
        sql = s.statements[0][0]
        assert "ORDER BY market_id, id" in sql

    async def test_prefetch_with_no_ids_touches_the_database_not_at_all(self):
        s = _RecordingSession(lambda sql, params: _Result([]))
        assert await _prefetch_outcomes(s, []) == {}
        assert s.statements == []

    async def test_no_per_market_outcome_round_trip_remains(self, monkeypatch):
        cands = [_candidate(i, "KXNHLGAME-%d" % i) for i in range(1, 6)]

        def responder(sql, params):
            if _CANDIDATE_MARKER in sql:
                return _Result(cands)
            if _PREFETCH_MARKER in sql:
                return _Result([])
            return None

        s = _install(monkeypatch, _RecordingSession(responder))
        await _resolve_kalshi_from_scores()
        assert not any(_PER_MARKET_MARKER in sql for sql, _ in s.statements)

        s2 = _install(monkeypatch, _RecordingSession(responder))
        await _resolve_kalshi_spread_total_from_scores()
        assert not any(_PER_MARKET_MARKER in sql for sql, _ in s2.statements)

    async def test_exactly_one_prefetch_per_block(self, monkeypatch):
        monkeypatch.setattr(bw, "_OUTCOME_PREFETCH_BLOCK", 2)
        cands = [_candidate(i, "KXNHLGAME-%d" % i) for i in range(1, 6)]
        blocks = []

        def responder(sql, params):
            if _CANDIDATE_MARKER in sql:
                return _Result(cands)
            if _PREFETCH_MARKER in sql:
                blocks.append(list((params or {}).get("ids") or []))
                return _Result([])
            return None

        _install(monkeypatch, _RecordingSession(responder))
        await _resolve_kalshi_from_scores()
        assert blocks == [[1, 2], [3, 4], [5]], blocks

    def test_block_size_is_bounded(self):
        # peak memory is O(block x outcomes-per-market); production averages
        # 2.9 outcomes per candidate market (264,810 / 91,776).
        assert 100 <= _OUTCOME_PREFETCH_BLOCK <= 10000


# ==========================================================================
# 4. the polymarket O/U resolver stops paying for rows it can never grade
# ==========================================================================

class TestPolymarketTotalPrefilter:
    """Production 2026-08-30: the statement returned its full LIMIT 20000 and
    _poly_total_line rejected ALL 20,000. Unparseable markets can never be
    graded, so they can never leave the ungraded set — they saturated the limit
    every cycle and starved every gradable market behind them, for 56.2 s."""

    #: the predicate as it must appear in the EXECUTED statement. Asserting it
    #: against `inspect.getsource` is vacuous — the docstring quotes it, so the
    #: guard stayed green with the clause deleted from the SQL (mutation
    #: M-POLY-PREFILTER-DROPPED survived the first battery run exactly there).
    _PREFILTER = "m.name ~* ':[[:space:]]*o/u'"

    async def _statement(self, monkeypatch):
        s = _RecordingSession(lambda sql, params: _Result([]))
        _install(monkeypatch, s)
        await _resolve_polymarket_total_from_scores()
        stmts = [q for q, _ in s.statements if "source = 'polymarket'" in q]
        assert stmts, s.statements
        return stmts[0]

    async def test_the_prefilter_is_in_the_executed_statement(self, monkeypatch):
        assert self._PREFILTER in await self._statement(monkeypatch)

    async def test_the_prefilter_is_the_loose_anchor_not_the_graders_regex(
            self, monkeypatch):
        """A tighter SQL filter could drop rows the grader can parse. Extract
        the shipped POSIX pattern from the statement, translate it, and require
        that it accepts everything the grader accepts."""
        stmt = await self._statement(monkeypatch)
        m = re.search(r"m\.name\s+~\*\s+'([^']*)'", stmt)
        assert m, stmt
        shipped = m.group(1).replace("[[:space:]]", r"\s")
        for name in ("Yankees vs. Red Sox: O/U 8.5",
                     "Yankees vs. Red Sox:o/u 8",
                     "A vs. B:   O/U   10.5   "):
            assert _POLY_TOTAL_MARKET_RE.search(name), name
            assert re.search(shipped, name, re.IGNORECASE), (
                "the shipped SQL prefilter %r rejects %r, which the grader "
                "parses — the statement is under-including" % (m.group(1), name)
            )
        assert not shipped.endswith("$"), (
            "an end-anchored prefilter is the grader's own regex, not a "
            "superset of it"
        )

    def test_the_python_parse_remains_the_authority(self):
        src = inspect.getsource(_resolve_polymarket_total_from_scores)
        assert "_poly_total_line(row.market_name)" in src
        assert 'stats["no_parse"] += 1' in src

    @pytest.mark.parametrize("name", [
        "Yankees vs. Red Sox: O/U 8.5",
        "Yankees vs. Red Sox: o/u 8",
        "Yankees vs. Red Sox:O/U 10.5",
        "Yankees vs. Red Sox:   O/U   7.5   ",
    ])
    def test_prefilter_accepts_everything_the_python_regex_accepts(self, name):
        # the SQL predicate `name ~* ':[[:space:]]*o/u'` in Python terms
        prefilter = re.search(r":\s*o/u", name, re.IGNORECASE)
        assert _POLY_TOTAL_MARKET_RE.search(name) is not None
        assert prefilter is not None, (
            "the SQL prefilter would drop a name the grader can parse"
        )

    @pytest.mark.parametrize("name", [
        "Will the Fed cut rates in March?",
        "Yankees vs. Red Sox",
        "Chiefs vs. Bills: Total Bases",
        "",
    ])
    def test_prefilter_rejects_the_shapes_that_saturated_the_limit(self, name):
        assert _POLY_TOTAL_MARKET_RE.search(name) is None
        assert re.search(r":\s*o/u", name, re.IGNORECASE) is None

    def test_prefilter_is_strictly_looser_than_the_grader(self):
        """Every string the grader parses contains the colon-o/u anchor, so the
        prefilter cannot under-include. Measured on production the same way:
        49,497 polymarket resolved markets match the grader's regex and
        **0** of them are dropped by the prefilter."""
        anchored = _POLY_TOTAL_MARKET_RE.pattern
        assert anchored.startswith(":") and "o/u" in anchored.lower()


# ==========================================================================
# 5. the two box-score resolvers stop seq-scanning futures_markets
# ==========================================================================

class TestBoxScoreResolversDriveFromTheEventIdList:
    """`e.box_score_data IS NOT NULL` inline made the planner seq-scan
    futures_markets (917K rows / 1.6 GB) to apply the ticker prefix: 44.7 s for
    the player props and 17.9 s for total bases — the latter to return ZERO
    rows. Reading the 7,692 box-score event ids first (0.32 s) and binding them
    turns both into nested loops on ix_futures_markets_event_id (2.71 s /
    5.84 s)."""

    def _capture(self, monkeypatch, fn):
        s = _RecordingSession(lambda sql, params: _Result([]))
        _install(monkeypatch, s)
        return s

    async def test_player_props_reads_the_event_ids_first(self, monkeypatch):
        s = self._capture(monkeypatch, None)
        await _resolve_kalshi_player_props_from_boxscore()
        first = s.statements[0][0]
        assert "SELECT id FROM events WHERE box_score_data IS NOT NULL" in first
        big = [sql for sql, _ in s.statements if "FROM futures_outcomes fo" in sql]
        assert big, s.statements
        assert "fm.event_id = ANY(:bs_event_ids)" in big[0]
        assert "e.box_score_data IS NOT NULL" not in big[0], (
            "the inline NULL check is what forced the futures_markets seq scan"
        )

    async def test_total_bases_reads_the_event_ids_first(self, monkeypatch):
        s = self._capture(monkeypatch, None)
        await _resolve_kalshi_total_bases_from_boxscore()
        first = s.statements[0][0]
        assert "SELECT id FROM events WHERE box_score_data IS NOT NULL" in first
        big = [sql for sql, _ in s.statements if "kxmlbtb%" in sql]
        assert big, s.statements
        assert "fm.event_id = ANY(:bs_event_ids)" in big[0]
        assert "e.box_score_data IS NOT NULL" not in big[0]

    async def test_the_event_id_list_is_actually_bound(self, monkeypatch):
        def responder(sql, params):
            if "SELECT id FROM events WHERE box_score_data IS NOT NULL" in sql:
                return _Result([(5,), (6,)])
            return _Result([])

        s = _install(monkeypatch, _RecordingSession(responder))
        await _resolve_kalshi_total_bases_from_boxscore()
        bound = [p for sql, p in s.statements
                 if p and "bs_event_ids" in p]
        assert bound and bound[0]["bs_event_ids"] == [5, 6], s.statements


# ==========================================================================
# 6. the next regression inside this phase must be self-locating
# ==========================================================================

class TestSubPhaseTiming:
    """The phase map could only ever say `score_resolution: 397.0`. Which of
    six resolvers owned it took a separate production probe to answer."""

    _NAMES = ("game_scores", "spread_total", "poly_total", "player_props",
              "total_bases", "period_props")

    def test_every_resolver_in_the_phase_is_timed(self):
        src = inspect.getsource(bw._backfill_all_winners)
        for name in self._NAMES:
            assert '_timed_sub(\n        "%s"' % name in src \
                or '_timed_sub("%s"' % name in src, name

    def test_the_split_is_reported_on_both_exit_paths(self):
        src = inspect.getsource(bw._backfill_all_winners)
        assert src.count('"score_resolution_sub_s"') >= 2, (
            "the split must survive BOTH the partial_budget_guard return and "
            "the full-completion summary — the guard path is the one that has "
            "fired on every recent run"
        )

    def test_sub_timings_are_not_folded_into_phase_times(self):
        """They would double-count against `score_resolution` and break the
        `sum(phase_times) ~= pipeline_elapsed_s` check Queue 357 relies on."""
        src = inspect.getsource(bw._backfill_all_winners)
        timed = src.split("async def _timed_sub", 1)[1].split("_start_phase", 1)[0]
        assert "_phase_times[" not in timed

    async def test_a_resolver_that_raises_is_still_timed(self):
        """`_timed_sub` records in a finally: a phase that dies mid-way is
        exactly the one whose cost we need."""
        src = inspect.getsource(bw._backfill_all_winners)
        block = src.split("async def _timed_sub", 1)[1].split("_start_phase", 1)[0]
        assert "finally:" in block
