"""#6881 — a paginated futures list orders on a UNIQUE key, so paging is exhaustive.

THE CLASS THIS GUARDS
=====================
`ORDER BY <non-unique column>` + `LIMIT/OFFSET` is not a page-able order. Rows
inside a tie block have no defined relative order, and Postgres may resolve that
block DIFFERENTLY for each `OFFSET+LIMIT` — a top-N sort only has to produce the
first `offset+limit` rows correctly. So the same row can be served on two pages
while the row it displaced is served on none.

The reader consequence is NOT "a list looks untidy": it is that a market becomes
unreachable. Measured on production 2026-09-18 at the readers' own page sizes,
paging until the list said it was exhausted:

    /api/futures/browse  (web /search CategoryBrowser, limit=20)
        golf   total 88   88 slots ->  79 distinct   9 UNREACHABLE
        mma    total 93   93 slots ->  85 distinct   8 UNREACHABLE

    /api/futures/faceted (native futures browser, per_page=20)
        golf   sort=soonest    88 slots -> 79 distinct
        golf   sort=trending   88 slots -> 78 distinct
        mma    sort=newest    100 slots -> 90 distinct

    economics, 10 "Load more" clicks: 200 slots -> 93 distinct;
        "S&P 500 (SPX) Up or Down on September 18?" served SEVEN times.

`motorsports` is the control that names the mechanism instead of correlating
with it: 87 markets, 0 unreachable, because its largest tie block (11) is
smaller than the page size, so no tie block ever straddles a page boundary.

WHY THE ASSERTIONS ARE ON THE EMITTED SQL
=========================================
The defect is a property of the statement, and the fixtures here mock the
database, so a row-level assertion would be asserting the mock. Compiling the
statement the route actually built is the closest thing to the production query
that runs in CI, and it is what the sibling LAT-P123 suite already does.

The last test is the recurrence guard and is deliberately not specimen-shaped:
it walks the module for EVERY offset-paged query, so a new paginated endpoint
added to this file inherits the rule without anyone remembering this file.
"""

import ast
import pathlib
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

FUTURES_ROUTES = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "routes" / "futures.py"
)


def _market(market_id, *, name="Open Championship Winner", llm_sport_category="golf"):
    return SimpleNamespace(
        id=market_id,
        name=name,
        llm_sport_category=llm_sport_category,
        source="kalshi",
        resolution_date=None,
        updated_at=None,
        market_tags=[],
        status="open",
        outcomes=[],
        image_url=None,
        hook_description=None,
    )


def _page_result(markets, total):
    result = MagicMock()
    result.unique.return_value.all.return_value = [(m, total) for m in markets]
    return result


def _scalars_result(markets):
    result = MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = markets
    return result


def _count_result(total):
    result = MagicMock()
    result.scalar.return_value = total
    return result


def _sql(call):
    return str(call.args[0].compile()).lower()


def _order_by_clause(sql):
    """The ORDER BY text, up to the LIMIT/OFFSET that always follows it here."""
    match = re.search(r"order by (.+?)(?:\s+limit|\s+offset|$)", sql, re.S)
    assert match, f"no ORDER BY found in statement:\n{sql}"
    return " ".join(match.group(1).split())


class TestBrowsePagesOnATotalOrder:
    """`/api/futures/browse` — the web /search category browser."""

    async def test_browse_order_by_ends_on_the_primary_key(self, client, mock_db):
        mock_db.execute.side_effect = [
            _page_result([_market(i) for i in range(20)], 88)
        ]

        resp = await client.get("/api/futures/browse?category=golf&limit=20")

        assert resp.status_code == 200
        order_by = _order_by_clause(_sql(mock_db.execute.call_args_list[0]))
        assert order_by.rstrip().endswith("futures_markets.id asc"), (
            "browse's ORDER BY does not END on a unique key, so a tie block is "
            "ordered arbitrarily and OFFSET paging both repeats and skips rows. "
            f"Got: ORDER BY {order_by}"
        )

    async def test_browse_still_sorts_by_resolution_date_first(self, client, mock_db):
        """The tiebreaker is a tiebreaker: it must not become the sort."""
        mock_db.execute.side_effect = [_page_result([_market(1)], 88)]

        await client.get("/api/futures/browse?category=golf&limit=20")

        order_by = _order_by_clause(_sql(mock_db.execute.call_args_list[0]))
        assert order_by.startswith("futures_markets.resolution_date asc"), (
            "browse no longer leads on resolution_date — soonest-first is the "
            f"product order, `id` only breaks its ties. Got: ORDER BY {order_by}"
        )


class TestFacetedPagesOnATotalOrder:
    """`/api/futures/faceted` — the native futures browser (per_page=20)."""

    @pytest.mark.parametrize(
        "sort,leading",
        [
            ("soonest", "futures_markets.resolution_date asc"),
            ("newest", "futures_markets.updated_at desc"),
            ("trending", "max_move desc"),
        ],
    )
    async def test_every_sort_ends_on_the_primary_key(
        self, client, mock_db, sort, leading
    ):
        facet_rows = MagicMock()
        facet_rows.all.return_value = []
        mock_db.execute.side_effect = [
            _count_result(88),
            _scalars_result([_market(i) for i in range(20)]),
            facet_rows,
        ]

        resp = await client.get(
            f"/api/futures/faceted?category=golf&page=1&per_page=20&sort={sort}"
        )

        assert resp.status_code == 200
        # The route runs count -> page -> facets. Pick the PAGE statement by its
        # shape rather than its index, so adding a statement to the route does
        # not silently re-point this assertion at some other query.
        paged = [
            call
            for call in mock_db.execute.call_args_list
            if "order by" in _sql(call) and "limit" in _sql(call)
        ]
        assert len(paged) == 1, (
            f"expected exactly one offset-paged statement, found {len(paged)}"
        )
        order_by = _order_by_clause(_sql(paged[0]))
        assert order_by.rstrip().endswith("futures_markets.id asc"), (
            f"faceted sort={sort} pages on a non-unique order, so the native "
            f"browser repeats and skips markets. Got: ORDER BY {order_by}"
        )
        assert leading in order_by, (
            f"faceted sort={sort} lost its actual sort key; `id` must break the "
            f"tie, not replace it. Got: ORDER BY {order_by}"
        )


class TestNoOffsetPagedQueryInThisModuleLacksATiebreak:
    """The recurrence guard — the rule, not the two specimens.

    `trending`'s NULL block, `browse`'s 26-row golf tie and economics' ~1,500
    same-instant daily markets are three faces of one rule, and the next
    paginated endpoint added to this file will have the same one. So this walks
    the module rather than naming routes: any query chaining `.offset(...)` must
    carry a final ORDER BY key that is unique.
    """

    # A row-level query breaks its ties on the PK. A GROUPED query cannot —
    # `id` is not in its GROUP BY — so its unique key is its grouping key, and
    # `/groups` ends on `group_type` behind `group_id`. Both are recorded here
    # deliberately rather than the guard matching any bare column: the point is
    # that the final key is UNIQUE for that query's row shape, and a reviewer
    # adding a name to this tuple has to say which of the two cases it is.
    UNIQUE_FINAL_KEYS = ("id", "group_type")

    def _offset_paged_order_bys(self):
        """Every `.order_by(...)` that shares a call chain with `.offset(...)`."""
        tree = ast.parse(FUTURES_ROUTES.read_text())
        found = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # Walk down one chained expression collecting its method names.
            chain, cursor = {}, node
            while isinstance(cursor, ast.Call) and isinstance(
                cursor.func, ast.Attribute
            ):
                chain[cursor.func.attr] = cursor
                cursor = cursor.func.value
            if "offset" in chain and "order_by" in chain:
                found.append((chain["order_by"], node.lineno))
        return found

    def test_the_guard_can_see_the_paged_queries(self):
        """A walker that finds nothing would pass the next test vacuously."""
        assert len(self._offset_paged_order_bys()) >= 4, (
            "the AST walk stopped finding offset-paged queries in futures.py — "
            "the chain shape changed and the guard below is now vacuous"
        )

    def test_every_offset_paged_query_breaks_its_ties(self):
        offenders = []

        for order_by_call, lineno in self._offset_paged_order_bys():
            if not order_by_call.args:
                continue
            final = order_by_call.args[-1]
            # Unwrap `.asc()` / `.desc()` / `.nulls_last()` down to the column.
            while isinstance(final, ast.Call) and isinstance(
                final.func, ast.Attribute
            ):
                final = final.func.value
            attr = final.attr if isinstance(final, ast.Attribute) else None
            if attr not in self.UNIQUE_FINAL_KEYS:
                offenders.append(f"  futures.py:{lineno} ends on {attr!r}")

        assert not offenders, (
            "an offset-paged query in routes/futures.py does not end on a unique "
            "ORDER BY key. Rows inside a tie block have no defined order, so "
            "paging will serve some markets twice and others never:\n"
            + "\n".join(offenders)
        )
