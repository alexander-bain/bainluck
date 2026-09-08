"""#4047 — "Other" appears once in the category grid, and its panel holds what its tile counted.

WHAT A PERSON SAW. `/search` at phone width, production, 2026-09-08 19:27Z: the
**Browse by category** grid contained two tiles both labelled "Other", same 📋 icon,
counts `216` and `9`. The API agreed — `GET /api/futures/categories` returned the key
`other` twice, `[('other', 206), ('other', 9)]`.

THE CAUSE IS THE ORDER OF TWO OPERATIONS. `_build_futures_categories` grouped by
`FuturesMarket.llm_sport_category` and then wrote `row.llm_sport_category or "other"`.
`'other'` and `NULL` are two groups; the rename gave them one name, AFTER the grouping
that would have merged them. An absence was renamed to a real category's key at
serialisation time.

WHY IT COST MORE THAN A REPEATED TILE. `CategoryBrowser` renders `key={cat.key}` and
tracks expansion as `expandedCategory === cat.key`, so tapping either tile highlighted
both and opened one panel — and that panel asks `/api/futures/browse?category=other`,
which matched `llm_sport_category == 'other'` and therefore could never show the nine
rows behind the second tile. **They were counted and unreachable.**

SO THE GUARD IS AN AGREEMENT, NOT A DEDUPE. Making the census emit one key is half a
fix: if the tile then says 215 and the panel shows 206, the number beside the heading is
a formatting lie. `test_every_key_the_census_emits_selects_exactly_what_it_counted` is
the test that matters here — it drives the census and the browse filter over one corpus
and compares them key by key.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, FuturesMarket  # noqa: E402
from app.routes.futures import (  # noqa: E402
    _UNCLASSIFIED_CATEGORY,
    _build_futures_categories,
    _category_condition,
)


class _AsyncShim:
    """Async surface over a real sync session — the repo's established shape.

    No aiosqlite in this sandbox. The statement executed is production's own and
    the rows come back through the real result API, which is what this file
    needs: the defect is in a GROUP BY, and a mocked session cannot group.
    """

    def __init__(self, session):
        self._s = session

    async def execute(self, statement):
        return self._s.execute(statement)


#: The production shape, in miniature: a real category, the literal `other`
#: category, and the unclassified rows that were wearing its name.
_CORPUS = (
    ("politics", 3),
    (_UNCLASSIFIED_CATEGORY, 2),
    (None, 4),
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[FuturesMarket.__table__])
    s = Session(engine, expire_on_commit=False)
    mid = 0
    for category, n in _CORPUS:
        for _ in range(n):
            mid += 1
            s.add(
                FuturesMarket(
                    id=mid,
                    source="kalshi",
                    external_id=f"MKT-{mid}",
                    name=f"Who wins thing {mid}?",
                    status="open",
                    event_id=None,
                    resolution_date=None,
                    llm_sport_category=category,
                )
            )
    s.commit()
    yield s
    s.close()


def _census(session):
    return asyncio.run(_build_futures_categories(_AsyncShim(session)))


# ---------------------------------------------------------------------------
# 1 — the defect
# ---------------------------------------------------------------------------


def test_the_census_never_emits_one_key_twice(session):
    """The whole visible bug, in one assertion.

    Pre-fix this returned `other` twice — 2 and 4 — and the grid drew two tiles.
    """
    cats = _census(session)["categories"]
    keys = [c["key"] for c in cats]
    assert len(keys) == len(set(keys)), f"duplicate category key in the census: {keys}"


def test_an_unclassified_market_is_counted_under_other_and_not_beside_it(session):
    cats = {c["key"]: c["count"] for c in _census(session)["categories"]}
    assert cats == {"politics": 3, _UNCLASSIFIED_CATEGORY: 6}, (
        "the four NULL rows and the two literal `other` rows are one tile of six"
    )


def test_the_total_still_counts_every_market_exactly_once(session):
    """A dedupe that drops rows would pass the test above and lose four markets."""
    census = _census(session)
    assert census["total"] == sum(n for _, n in _CORPUS) == 9
    assert census["total"] == sum(c["count"] for c in census["categories"])


# ---------------------------------------------------------------------------
# 2 — the half that makes the count true
# ---------------------------------------------------------------------------


def test_every_key_the_census_emits_selects_exactly_what_it_counted(session):
    """🔴 THE ONE THAT MATTERS. The tile's number and the panel's contents are
    two different queries, and the bug was that they disagreed silently.

    The count beside a category heading is PRINTED to the reader ("(6,611)",
    "Load more (N remaining)"), so a census that says 215 in front of a panel
    holding 206 is a formatting lie shipped as a bug fix.
    """
    for cat in _census(session)["categories"]:
        n = session.execute(
            select(func.count(FuturesMarket.id)).where(_category_condition(cat["key"]))
        ).scalar()
        assert n == cat["count"], (
            f"the `{cat['key']}` tile counts {cat['count']} and its panel would "
            f"hold {n}"
        )


def test_a_null_row_does_not_leak_into_every_category(session):
    """The obvious over-fix: widen the filter for all keys, not just one."""
    n = session.execute(
        select(func.count(FuturesMarket.id)).where(_category_condition("politics"))
    ).scalar()
    assert n == 3, "an unclassified market showed up under Politics"


def test_a_key_nothing_is_classified_under_selects_nothing(session):
    n = session.execute(
        select(func.count(FuturesMarket.id)).where(_category_condition("curling"))
    ).scalar()
    assert n == 0


# ---------------------------------------------------------------------------
# 3 — the cost, which is why the filter is a branch and not one expression
# ---------------------------------------------------------------------------


def test_an_ordinary_category_keeps_its_plain_equality():
    """🔴 `coalesce(llm_sport_category, 'other') == category` is the tidy spelling
    and it puts an unindexable expression on the left of EVERY comparison.

    This route's own comment records the measurement: the uncategorised call
    reads 38,990 shared blocks (~305 MB) because its negated `ILIKE`s are
    unindexable already. Only `other` needs the widening, so only `other` pays.
    Asserted on the compiled SQL, because it is a plan property and no
    behavioural test can see it.
    """
    sql = str(_category_condition("politics").compile()).lower()
    assert "coalesce" not in sql, sql
    assert "is null" not in sql, sql

    widened = str(_category_condition(_UNCLASSIFIED_CATEGORY).compile()).lower()
    assert "is null" in widened, widened


def test_the_key_is_one_constant_and_not_a_string_in_three_places():
    """The census, the filter and the frontend all have to agree on the word.

    Asserted on the source, because three separate `"other"` literals is exactly
    the shape that let the census and the browse filter drift apart in the first
    place.
    """
    import ast
    import inspect
    import textwrap

    from app.routes import futures as futures_routes

    src = textwrap.dedent(inspect.getsource(futures_routes._category_condition))
    assert "_UNCLASSIFIED_CATEGORY" in src

    # Over the AST, not the text: the docstring above quotes the key while
    # explaining the trade, and a substring check would read that as the defect.
    fn = ast.parse(src).body[0]
    literals = [
        node.value
        for node in ast.walk(ast.Module(body=fn.body[1:], type_ignores=[]))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert _UNCLASSIFIED_CATEGORY not in literals, (
        f"the filter spells the key itself instead of reading the constant: {literals}"
    )
