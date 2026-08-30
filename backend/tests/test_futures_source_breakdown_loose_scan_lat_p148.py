"""LAT-P148 (#2333) — the market page stops sorting 190,656 rows to print 256.

SHIP: the FIRST open of a big championship market (NFL Super Bowl Winner, MLB
World Series Winner) stops taking four to seven seconds. LAT-P127 fixed the
repeat open with a cache; this fixes the open that no cache can help — the one a
brand-new visitor, and every visitor after a 300 s expiry, actually pays.

WHY P127's INDEX DID NOT DO IT. P127-3 asked for, and Alex built,
``ix_futures_odds_snapshots_outcome_bookmaker_captured (outcome_id, bookmaker,
captured_at DESC)``. The cold read did not move. The index is not at fault and
neither are the stale stats: the statement it was built for carried **no
``bookmaker`` predicate**, and PostgreSQL has no index skip scan, so nothing
could descend past the leading column. Measured on production 2026-08-30,
market 86832:

    Subquery Scan                       actual 9,163 ms     rows out    256
      WindowAgg
        Sort  external merge 7,640 kB DISK      rows in 190,656
          Index Scan ix_..._outcome_id          5,958 rows x 32 loops
    Shared I/O Read Time 7,973 ms

The replacement writes the skip out by hand: walk ``(outcome_id, bookmaker)``
pairs one ``LIMIT 1`` at a time, then take the newest row per pair through a
LATERAL. Same market, same minute:

    | executed row query | 3,533 ms -> 344 ms cold, 51-73 ms warm |
    | rows examined      | 190,656  -> 576 seeks + 256 heap rows  |
    | disk sort          | 7,640 kB -> none                       |

and the plan finally names the index P127 bought.

🔴 WHY THESE GUARDS ARE SHAPE ASSERTIONS AND NOT AN EXECUTED QUERY. There is no
PostgreSQL in this sandbox, and the recursive CTE / LATERAL / ``unnest`` this
statement is made of are not SQLite-expressible, so no local test can run it.
Equivalence was therefore proved where the data is — against production, old
statement vs new, row-for-row across ten markets spanning 2-32 outcomes and
2-256 result rows, all identical (see the audit doc). What the tests below can
still do, and what no production check does, is stop the statement from being
edited back into the shape that cannot use the index. That is their whole job:
every assertion here corresponds to an edit that reads like an improvement and
silently restores a full scan.

🔴 THE THREE EDITS THAT WOULD EACH UNDO THIS, AND WHY EACH LOOKS RIGHT:

  ``captured_at IS NOT NULL``  — the sibling module
      ``app.utils.latest_observation`` (LAT-P147) ADDS this predicate and
      documents it as load-bearing. Here it is a behaviour change, and the
      inversion is the point: P147 replaces a ``max()``, which SKIPS nulls,
      while ``ORDER BY ... DESC`` is NULLS FIRST — so P147 needs the predicate
      to agree with what it replaces. This replaces a WINDOW function, which is
      NULLS FIRST too. A null-``captured_at`` row wins its partition under the
      old statement and must win its pair under this one. ``captured_at`` really
      is nullable on production, so this is reachable, not theoretical.
  ``NULLS LAST``               — reads as defensive, measured by P147 at 19x
      slower, because it stops matching the index's own ordering and turns each
      one-row backward read into a Sort over the whole pair.
  an ``id`` tiebreak           — reads as determinism. Same mechanism: the
      ORDER BY no longer matches the index. It also buys nothing — production
      carries zero multi-row ``(outcome_id, bookmaker, captured_at)`` groups on
      this market, and the window function it replaces broke ties arbitrarily.
"""

import datetime as _dt

import pytest

from app.routes import futures as futures_route


class CapturingDB:
    """Records the statement and the bind dict, hands back canned rows.

    The statement is the artifact under test here — these guards assert on its
    TEXT, so unlike LAT-P127's double this one keeps it.
    """

    def __init__(self, rows=()):
        self._rows = list(rows)
        self.statements = []
        self.params = []

    async def execute(self, stmt, params=None):
        self.statements.append(stmt)
        self.params.append(params)

        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        return _Result(self._rows)


async def _sql_for(outcome_ids):
    """Run the breakdown against a recording double and return (sql, params)."""
    db = CapturingDB()
    await futures_route._get_source_breakdown(db, list(outcome_ids))
    assert len(db.statements) == 1, "the breakdown must stay ONE round trip"
    return str(db.statements[0]), db.params[0]


# Offsets from a single anchor, never literals (gotcha #44). Nothing here
# branches on the wall clock.
_ANCHOR = _dt.datetime.now(_dt.timezone.utc)
_FRESH = _ANCHOR - _dt.timedelta(hours=1)
_STALE = _ANCHOR - _dt.timedelta(days=30)


class TestTheStatementIsTheLooseScan:
    """The shape that can use the index, asserted clause by clause."""

    @pytest.mark.asyncio
    async def test_it_is_a_recursive_pair_walk(self):
        sql, _ = await _sql_for([501, 502])
        assert "WITH RECURSIVE" in sql.upper()
        # The step that makes it a walk rather than a scan: each iteration asks
        # for the next bookmaker STRICTLY GREATER than the one it holds.
        assert "s.bookmaker > p.bookmaker" in sql

    @pytest.mark.asyncio
    async def test_the_recursion_terminates(self):
        """``WHERE p.bookmaker IS NOT NULL`` on the RECURSIVE term.

        The walk ends when the "next bookmaker after this one" subquery returns
        NULL. That NULL row must be the last one fed back in — without this
        predicate the step re-queries for ``bookmaker > NULL``, which is NULL
        again, forever. This is the one mutation here whose failure mode is a
        hung web dyno rather than a wrong answer, which is exactly why it is
        asserted rather than left to review.

        🔴 THE SLICE IS THE ASSERTION. An earlier form of this test split on
        ``UNION ALL`` and searched everything after it — which also contains the
        FINAL select's identical ``WHERE p.bookmaker IS NOT NULL``. Deleting the
        terminator left that copy behind and the test still passed; M-NOTERM
        survived the battery and the survivor was this line. Cut at the LATERAL,
        so only the CTE body is in scope.
        """
        sql, _ = await _sql_for([501])
        cte_body = sql.split("CROSS JOIN LATERAL", 1)[0]
        recursive_term = cte_body.split("UNION ALL", 1)[1]
        assert "p.bookmaker IS NOT NULL" in recursive_term

    @pytest.mark.asyncio
    async def test_the_walk_ascends(self):
        """The seed takes the LOWEST bookmaker and the step goes up from it.

        Flip either to ``DESC`` and the seed lands on the highest name, the
        ``> p.bookmaker`` step immediately finds nothing, and the page silently
        renders exactly ONE source per outcome. It would look like a data gap,
        not a query bug.
        """
        sql, _ = await _sql_for([501])
        # Both halves of the walk — the seed's "lowest" and the step's "next
        # one up" — must ascend, and they must agree with each other.
        assert sql.count("ORDER BY s.bookmaker\n") == 2
        assert "ORDER BY s.bookmaker DESC" not in sql

    @pytest.mark.asyncio
    async def test_each_pair_is_resolved_by_a_lateral_top_one(self):
        sql, _ = await _sql_for([501, 502])
        assert "CROSS JOIN LATERAL" in sql.upper()
        assert "ORDER BY s.captured_at DESC" in sql
        # Two LIMIT 1s in the pair walk (seed + step) and one in the LATERAL.
        # If any of them becomes a LIMIT N or disappears, this is not a seek.
        assert sql.count("LIMIT 1") == 3

    @pytest.mark.asyncio
    async def test_the_old_window_sort_is_gone(self):
        sql, _ = await _sql_for([501, 502])
        upper = sql.upper()
        assert "ROW_NUMBER" not in upper, "the 190,656-row sort is back"
        assert "PARTITION BY" not in upper
        assert "OVER (" not in upper

    @pytest.mark.asyncio
    async def test_outcome_ids_are_bound_not_interpolated(self):
        """A bound array, for the plan cache and because ids are user-reachable.

        ``/api/futures/{id}`` takes the market from the URL and its outcomes
        from the database, so these ids are not attacker-controlled today. The
        assertion is here so they can never BECOME interpolated by a later edit
        that finds string formatting easier than an array bind.
        """
        sql, params = await _sql_for([501, 502])
        assert ":outcome_ids" in sql
        assert params == {"outcome_ids": [501, 502]}
        assert "501" not in sql and "502" not in sql

    @pytest.mark.asyncio
    async def test_the_bind_is_cast_not_double_colon(self):
        """``CAST(x AS integer[])``, never ``x::integer[]`` — asyncpg reads the
        ``::`` spelling as the start of a bind parameter."""
        sql, _ = await _sql_for([501])
        assert "CAST(:outcome_ids AS integer[])" in sql
        assert "::integer[]" not in sql


class TestTheThreeSaferLookingEditsThatWouldUndoIt:
    """Each of these reads as an improvement and restores a full scan."""

    @pytest.mark.asyncio
    async def test_no_captured_at_is_not_null_predicate(self):
        sql, _ = await _sql_for([501])
        assert "captured_at IS NOT NULL" not in sql, (
            "NULLS FIRST is the behaviour being preserved — the window function "
            "this replaces lets a null-captured_at row win its partition. See "
            "the module docstring; app.utils.latest_observation makes the "
            "OPPOSITE call for a good reason that does not apply here."
        )

    @pytest.mark.asyncio
    async def test_no_nulls_last(self):
        sql, _ = await _sql_for([501])
        assert "NULLS LAST" not in sql.upper(), "measured at 19x slower (P147)"

    @pytest.mark.asyncio
    async def test_no_tiebreak_after_captured_at(self):
        """``ORDER BY captured_at DESC`` and then NOTHING.

        A second sort key stops the ORDER BY matching
        ``(outcome_id, bookmaker, captured_at DESC)``, so the probe stops being
        a one-row backward read.
        """
        sql, _ = await _sql_for([501])
        after = sql.split("ORDER BY s.captured_at DESC", 1)[1].strip()
        assert after.startswith("LIMIT 1"), (
            "the only thing allowed after `captured_at DESC` is the LIMIT — a "
            f"second sort key stops the index serving the order: {after[:60]!r}"
        )


class TestNullsFirstRowsSurviveTheAggregation:
    """The reachable null case, end to end through the Python half."""

    @pytest.mark.asyncio
    async def test_a_null_captured_at_row_is_reported_not_dropped(self):
        db = CapturingDB([(501, "kalshi", 0.42, None)])
        out = await futures_route._get_source_breakdown(db, [501])
        assert len(out) == 1
        assert out[0]["source"] == "kalshi"
        assert out[0]["captured_at"] is None
        # Unknown age is not old age: `stale` gates spread math, and a null must
        # not be silently graded fresh-and-usable OR dropped from the page.
        assert out[0]["stale"] is False
        assert out[0]["outcomes"] == {501: 42.0}

    @pytest.mark.asyncio
    async def test_a_real_timestamp_still_beats_a_null_within_one_source(self):
        """Two outcomes, one book: the null must not erase the dated one.

        `captured_at` is per-SOURCE in the payload but rows arrive per
        (outcome, source), so the source's timestamp is the newest it saw.
        """
        db = CapturingDB(
            [
                (501, "kalshi", 0.42, None),
                (502, "kalshi", 0.31, _FRESH),
            ]
        )
        out = await futures_route._get_source_breakdown(db, [501, 502])
        assert out[0]["captured_at"] == _FRESH.isoformat()
        assert out[0]["stale"] is False
        assert out[0]["outcomes"] == {501: 42.0, 502: 31.0}


class TestTheContractTheCallerDependsOn:
    """Shape promises `_load_market_sources` and the route read off this."""

    @pytest.mark.asyncio
    async def test_sources_come_back_sorted_by_name(self):
        db = CapturingDB(
            [
                (501, "polymarket", 0.20, _FRESH),
                (501, "betmgm", 0.30, _FRESH),
                (501, "kalshi", 0.50, _FRESH),
            ]
        )
        out = await futures_route._get_source_breakdown(db, [501])
        assert [s["source"] for s in out] == ["betmgm", "kalshi", "polymarket"]

    @pytest.mark.asyncio
    async def test_a_stale_source_is_flagged_not_omitted(self):
        """The whole reason a time bound was NOT the fix.

        Bounding the scan to SOURCE_STALENESS_DAYS would have been the easy
        speedup and would have deleted these rows from the page. They are meant
        to render, muted.
        """
        db = CapturingDB(
            [
                (501, "betmgm", 0.30, _FRESH),
                (501, "oldbook", 0.70, _STALE),
            ]
        )
        out = await futures_route._get_source_breakdown(db, [501])
        assert [s["source"] for s in out] == ["betmgm", "oldbook"]
        assert out[0]["stale"] is False
        assert out[1]["stale"] is True

    @pytest.mark.asyncio
    async def test_outcome_keys_stay_ints(self):
        """#1587's class, at the source rather than after the JSON round trip."""
        db = CapturingDB([(501, "kalshi", 0.42, _FRESH)])
        out = await futures_route._get_source_breakdown(db, [501])
        assert list(out[0]["outcomes"]) == [501]
        assert all(isinstance(k, int) for k in out[0]["outcomes"])

    @pytest.mark.asyncio
    async def test_no_rows_is_an_empty_list_not_an_error(self):
        db = CapturingDB([])
        assert await futures_route._get_source_breakdown(db, [501]) == []
