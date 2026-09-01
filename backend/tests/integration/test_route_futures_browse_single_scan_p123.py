"""LAT-P123 — /api/futures/browse pays for ONE scan, and still prints the exact count.

THE CLASS THIS GUARDS
=====================
A paginated route that computes `total` with a separate `COUNT(*)` over the same
predicate as its page query, when the page query's `ORDER BY` already forces a
full scan of the matching population. The two statements are the identical scan,
run twice, in the same request.

Measured on production 2026-08-29 (`EXPLAIN (ANALYZE, BUFFERS)` via
`/api/admin/db-query`, slug `d9b76e9b`):

    category=politics   COUNT  8,410 shared blocks / 209.6 ms
                        page   8,410 shared blocks / 222.6 ms   <- same scan
                        window 8,410 shared blocks / 138.3 ms   <- both answers

    no category         COUNT 38,990 shared blocks / 1,270.5 ms  (~305 MB)
                        page  39,002 shared blocks /   445.6 ms
                        window 39,002 shared blocks /  801.7 ms  <- both answers

`count(*) OVER ()` is evaluated before LIMIT/OFFSET, above the scan the sort was
already going to pay for. The plan gains a `WindowAgg` node and loses an entire
statement. `total` is the SAME INTEGER — this is a cost change, not a precision
change, and that distinction is load-bearing: the number is PRINTED to the user
("(6,611)" beside the category header, "Load more (N remaining)"), so an
approximate count would have been a FORMATTING lie shipped as a latency win.

WHY THESE ASSERTIONS AND NOT A TIMER
====================================
A wall-clock assertion in CI measures the CI box. What must not regress is the
SHAPE: one statement, a window with no PARTITION BY, and a `total` that is the
population size rather than the page size. Every assertion below is on the
emitted SQL, the call COUNT, or the response value — none reads a clock
(gotcha #44).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock


def _market(market_id, *, name="World Series Winner", llm_sport_category="politics"):
    return SimpleNamespace(
        id=market_id,
        name=name,
        llm_sport_category=llm_sport_category,
        source="kalshi",
        resolution_date=None,
        outcomes=[],
    )


def _page_result(markets, total):
    """Rows of ``(FuturesMarket, total)`` — what the single query now returns."""
    result = MagicMock()
    result.unique.return_value.all.return_value = [(m, total) for m in markets]
    return result


def _count_result(total):
    result = MagicMock()
    result.scalar.return_value = total
    return result


def _sql(call):
    return str(call.args[0].compile()).lower()


class TestBrowsePaysForOneScan:
    """The ship: the second scan is gone."""

    async def test_a_full_page_issues_exactly_one_query(self, client, mock_db):
        mock_db.execute.side_effect = [_page_result([_market(i) for i in range(50)], 6611)]

        resp = await client.get("/api/futures/browse?category=politics&limit=50")

        assert resp.status_code == 200
        assert mock_db.execute.call_count == 1, (
            "browse issued more than one statement — the separate COUNT is back, "
            "and it is the same scan as the page query"
        )

    async def test_the_one_query_carries_a_count_window(self, client, mock_db):
        """Call count alone would stay green if someone swapped in a cached
        approximation. This asserts the MECHANISM that keeps `total` exact."""
        mock_db.execute.side_effect = [_page_result([_market(1)], 6611)]

        await client.get("/api/futures/browse?category=politics")

        sql = _sql(mock_db.execute.call_args_list[0])
        assert "count(*) over ()" in sql, sql

    async def test_the_window_has_no_partition_by(self, client, mock_db):
        """`OVER (PARTITION BY ...)` would make `total` a per-group count — a
        smaller number, printed with total's meaning."""
        mock_db.execute.side_effect = [_page_result([_market(1)], 6611)]

        await client.get("/api/futures/browse?category=politics")

        sql = _sql(mock_db.execute.call_args_list[0])
        assert "partition by" not in sql, sql

    async def test_the_page_bounds_ride_the_same_statement_as_the_window(
        self, client, mock_db
    ):
        """LIMIT/OFFSET must be on the windowed statement. Splitting them back
        into two statements is exactly the defect."""
        mock_db.execute.side_effect = [_page_result([_market(1)], 6611)]

        await client.get("/api/futures/browse?category=politics&limit=20&offset=40")

        sql = _sql(mock_db.execute.call_args_list[0])
        assert "count(*) over ()" in sql
        assert "limit" in sql
        assert "offset" in sql


class TestTheCountStaysExact:
    """The formatting half. These numbers are rendered; they may not drift."""

    async def test_total_is_the_population_not_the_page(self, client, mock_db):
        mock_db.execute.side_effect = [_page_result([_market(i) for i in range(50)], 6611)]

        body = (await client.get("/api/futures/browse?category=politics&limit=50")).json()

        assert body["total"] == 6611, "the page size was printed as the population size"
        assert len(body["items"]) == 50

    async def test_total_is_an_int_not_the_raw_window_value(self, client, mock_db):
        mock_db.execute.side_effect = [_page_result([_market(1)], 42)]

        body = (await client.get("/api/futures/browse")).json()

        assert body["total"] == 42
        assert isinstance(body["total"], int)

    async def test_has_more_is_true_below_the_boundary(self, client, mock_db):
        mock_db.execute.side_effect = [_page_result([_market(1)], 12)]

        body = (await client.get("/api/futures/browse?limit=5&offset=5")).json()

        assert body["has_more"] is True

    async def test_has_more_is_false_exactly_at_the_boundary(self, client, mock_db):
        """offset + limit == total. Off by one here re-opens "Load more" on an
        exhausted category and the next tap returns an empty list."""
        mock_db.execute.side_effect = [_page_result([_market(1)], 12)]

        body = (await client.get("/api/futures/browse?limit=6&offset=6")).json()

        assert body["has_more"] is False

    async def test_load_more_remaining_arithmetic_is_reproducible(self, client, mock_db):
        """The UI prints `total - items.length` as "N remaining". That is only
        honest if `total` counts the population the same filters selected."""
        mock_db.execute.side_effect = [_page_result([_market(i) for i in range(20)], 6611)]

        body = (await client.get("/api/futures/browse?category=politics&limit=20")).json()

        assert body["total"] - len(body["items"]) == 6591

    async def test_the_window_column_never_reaches_the_response(self, client, mock_db):
        mock_db.execute.side_effect = [_page_result([_market(1)], 7)]

        body = (await client.get("/api/futures/browse")).json()

        assert set(body) == {"items", "total", "limit", "offset", "has_more"}
        assert "browse_total" not in body["items"][0]


class TestTheEmptyPageCases:
    """A window function that produced no rows cannot report a population."""

    async def test_empty_at_offset_zero_reports_zero_with_no_extra_query(
        self, client, mock_db
    ):
        """An empty first page IS an empty population. Paying for a COUNT to
        confirm it would put the second scan back on the commonest cold path."""
        mock_db.execute.side_effect = [_page_result([], 0)]

        body = (await client.get("/api/futures/browse?category=politics")).json()

        assert body["total"] == 0
        assert body["items"] == []
        assert body["has_more"] is False
        assert mock_db.execute.call_count == 1

    async def test_empty_past_the_end_falls_back_to_a_real_count(self, client, mock_db):
        """offset beyond the population: no rows, so no window value. Printing 0
        would tell a reader the category is empty when it holds 6,611 markets."""
        mock_db.execute.side_effect = [_page_result([], 0), _count_result(6611)]

        body = (await client.get("/api/futures/browse?category=politics&offset=9000")).json()

        assert mock_db.execute.call_count == 2
        assert body["total"] == 6611
        assert body["items"] == []
        assert body["has_more"] is False

    async def test_the_fallback_count_selects_the_same_population(self, client, mock_db):
        """Filter drift between the page query and the fallback would print a
        total for a different set of markets than the one being browsed."""
        mock_db.execute.side_effect = [_page_result([], 0), _count_result(3)]

        await client.get("/api/futures/browse?category=politics&q=Senate&offset=9000")

        page_sql, count_sql = (_sql(c) for c in mock_db.execute.call_args_list)
        for fragment in (
            "futures_markets.status",
            "futures_markets.event_id is null",
            "lower(futures_markets.name) not like lower",
        ):
            assert fragment in page_sql, fragment
            assert fragment in count_sql, fragment

        count_params = mock_db.execute.call_args_list[1].args[0].compile().params.values()
        assert "politics" in count_params
        assert "%Senate%" in count_params

    async def test_the_fallback_is_a_count_and_not_a_second_page_fetch(
        self, client, mock_db
    ):
        mock_db.execute.side_effect = [_page_result([], 0), _count_result(6611)]

        await client.get("/api/futures/browse?offset=9000")

        count_sql = _sql(mock_db.execute.call_args_list[1])
        assert "count(futures_markets.id)" in count_sql
        assert "count(*) over ()" not in count_sql

    async def test_a_falsy_fallback_count_still_yields_zero_not_none(
        self, client, mock_db
    ):
        """`.scalar()` returns None on some mock/driver paths; `total` is typed
        `int` in the client contract and None would render as `null`."""
        mock_db.execute.side_effect = [_page_result([], 0), _count_result(None)]

        body = (await client.get("/api/futures/browse?offset=9000")).json()

        assert body["total"] == 0


class TestTheOtherRoutesInThisFileAreUntouched:
    """Ordering guard: `program/ux-122` is also editing `routes/futures.py`,
    inside `browse_futures`' item loop. This ship does not touch that loop —
    these assert the item projection still holds so a merge that silently drops
    one side is visible here rather than in production."""

    async def test_item_projection_keys_are_unchanged(self, client, mock_db):
        market = _market(42, name="Next President", llm_sport_category="politics")
        market.outcomes = [
            SimpleNamespace(
                id=1, name="Alpha", current_probability=0.6, probability_change_24h=0.01,
                external_id=None,
            )
        ]
        mock_db.execute.side_effect = [_page_result([market], 1)]

        body = (await client.get("/api/futures/browse")).json()

        assert set(body["items"][0]) == {
            "id",
            "name",
            "llm_sport_category",
            "source",
            "resolution_date",
            "top_outcomes",
            "outcome_count",
        }
        assert body["items"][0]["top_outcomes"][0]["name"] == "Alpha"
