"""Guard: the search header's game count does not MOVE as the reader pages (#5559).

THE PAGE THIS EXISTS FOR. `GET /api/events/search?q=red sox`, read on production
2026-09-12 ~11:00Z. 61 raw rows over three pages. The dedup stages collapse three
duplicate groups on page one, one on page two and none on page three — and
because `total_results` was the corpus count minus *this page's* collapse, the
header printed a different number each time:

    page 1   "· 58 games"
    page 2   "· 60 games"
    page 3   "· 61 games"

A reader who presses Next watches the result count GROW. Whichever of the three
numbers is the right one, a total that rises as you page is read as a bug, and it
contradicts the pager standing beside it: since #5513 `total_pages`/`has_next`
are derived from the RAW count, so the header and the pager were answering the
same question with two different numbers.

WHAT CHANGED, AND WHAT DID NOT. #2623's adjustment is an observation about the
rows we actually looked at — the count query cannot see the pairing without
joining every candidate row. That observation is complete exactly when the page
IS the corpus, and it is a sample otherwise. So the adjustment now applies only
while `total_pages <= 1`. On one page the count still equals the cards the reader
can literally count (#2623's ship, and the case where they can catch us); on a
paginated query the raw count stands, stable on every page and equal to the
number the pager is built on.

WHAT EACH TEST IS DEFENDING. Not "the route returns a pagination dict":

* the ship — the same query prints the same count on page one and page two
  (`test_the_header_count_does_not_rise_as_the_reader_pages`);
* the thing a careless fix breaks — deleting the adjustment outright, which
  regresses #2623 where it is verifiable
  (`test_a_single_page_query_still_counts_the_cards_it_serves`);
* the disagreement itself, made assertable
  (`test_the_header_and_the_pager_now_answer_with_the_same_number`);
* the reachability #5513 bought, which must survive this
  (`test_the_next_button_still_reaches_the_row_the_fold_never_touched`);
* the control — a paginated query that folds NOTHING may not move
  (`test_a_paginated_query_with_no_fold_is_unchanged`).

🔴 REAL `Event` objects, never MagicMock: the fold stages reach through
`_sa_instance_state` (`set_committed_value`) to union the dropped row's sources,
and on a MagicMock that call is absorbed silently — the page would read as folded
when nothing folded, and every count below would be measuring the mock.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import Event, Sport
from app.routes.events import search_events

MLB = Sport(id=1, key="baseball_mlb", name="MLB", group="Baseball", active=True)

RED_SOX = "Boston Red Sox"
ROYALS = "Kansas City Royals"
FIRST_PITCH = datetime(2026, 9, 12, 20, 10, tzinfo=timezone.utc)

#: The production twin pair, verbatim: the ESPN-anchored row and the id-less
#: statpal claim ruling 048 correctly created rather than absorbed.
ESPN_ROW = 15310368
STATPAL_ROW = 15305549

PER_PAGE = 25
#: One row more than a page holds, so the corpus spans exactly two pages.
RAW_TOTAL = 26


def _event(
    id,
    *,
    away=ROYALS,
    home=RED_SOX,
    commence=FIRST_PITCH,
    espn_id=None,
    sources=None,
):
    e = Event(
        id=id,
        sport_id=MLB.id,
        away_team_name=away,
        home_team_name=home,
        commence_time=commence,
        status="scheduled",
        home_score=None,
        away_score=None,
        espn_id=espn_id,
        win_probability_sources=sources,
    )
    e.sport = MLB
    return e


def _twin_pair():
    return [
        _event(ESPN_ROW, espn_id="401816907", sources={"betting": 0.58}),
        _event(STATPAL_ROW, sources={"kalshi": 0.61}),
    ]


def _filler(n, *, start=0):
    """`n` distinct fixtures no dedup stage can pair: different clubs, different days."""
    return [
        _event(
            9000 + start + i,
            away=f"Away {start + i}",
            home=f"Home {start + i}",
            commence=FIRST_PITCH + timedelta(days=start + i + 1),
        )
        for i in range(n)
    ]


def _page_one():
    """A full raw page of 25 whose first two rows are one game twice."""
    rows = _twin_pair() + _filler(23)
    assert len(rows) == PER_PAGE, "the fixture must fill a whole raw page"
    return rows


def _page_two():
    """The raw 26th row — distinct, so nothing on page two folds."""
    return _filler(1, start=500)


def _mock_db(events, *, total):
    db = AsyncMock()

    def make_result(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.fetchall.return_value = []
        r.all.return_value = []
        r.scalar.return_value = total
        r.scalar_one_or_none.return_value = None
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "count(" in s:
            return make_result([])
        if "futures_markets" in s or "odds_snapshots" in s or "teams" in s:
            return make_result([])
        if "from events" in s:
            return make_result(events)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _payload(rows, *, total, page=1, per_page=PER_PAGE, q="red sox"):
    """Drive the real route. Called directly, so every `Query(...)` default has to
    be passed explicitly or the route receives `Query` objects where it wants ints."""
    rc = MagicMock()
    rc.get.return_value = None  # a cache MISS every time, so the route does the work

    with (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch(
            "app.routes.events.folded_probability_sources_batch",
            new=AsyncMock(return_value={}),
        ),
        patch("app.routes.events._record_trending", new=MagicMock()),
    ):
        return await search_events(
            request=MagicMock(),
            response=MagicMock(),
            q=q,
            db=_mock_db(rows, total=total),
            sport=None,
            tags=None,
            page=page,
            per_page=per_page,
            days_back=30,
            include_upcoming=True,
            debug_timing=False,
            current_user=None,
        )


@pytest.mark.asyncio
async def test_the_header_count_does_not_rise_as_the_reader_pages():
    """🔴 THE SHIP. One query, two pages, one number.

    Page one folds a twin pair; page two folds nothing. Before #5559 that made
    the header read 25 then 26 — the count GREW when the reader pressed Next.
    """
    one = await _payload(_page_one(), total=RAW_TOTAL, page=1)
    two = await _payload(_page_two(), total=RAW_TOTAL, page=2)

    # The fold really did fire on page one; without this the equality below is
    # satisfied by two pages that both collapsed nothing.
    assert len(one["results"]) == 24, [r["id"] for r in one["results"]]
    assert len(two["results"]) == 1

    assert one["pagination"]["total_results"] == two["pagination"]["total_results"], (
        "the header count moved between page one and page two of the same query: "
        f"{one['pagination']['total_results']} then "
        f"{two['pagination']['total_results']}"
    )
    # And it never claims fewer games than the reader can already see.
    assert one["pagination"]["total_results"] >= len(one["results"])


@pytest.mark.asyncio
async def test_a_single_page_query_still_counts_the_cards_it_serves():
    """🔴 THE CONTROL #2623 OWNS. The cheap fix is "stop adjusting at all".

    That is invisible on a paginated query and wrong on a short one, which is the
    only shape where the reader can count the cards and catch us: two raw rows,
    one game, one card — the header may not say two.
    """
    payload = await _payload(_twin_pair(), total=2)

    assert len(payload["results"]) == 1
    assert payload["pagination"]["total_pages"] == 1, "the fixture must be one page"
    assert payload["pagination"]["total_results"] == 1, (
        "a one-page query printed a count the reader can see is wrong: "
        f"{payload['pagination']}"
    )


@pytest.mark.asyncio
async def test_the_header_and_the_pager_now_answer_with_the_same_number():
    """The disagreement named in #5559, made assertable.

    `total_pages` has counted RAW rows since #5513 (that is what keeps the tail
    row reachable). A header derived from a different count than the pager means
    "26 games" over "Page 1 of 1", or the 25/2 pair this produced before.
    """
    pag = (await _payload(_page_one(), total=RAW_TOTAL, page=1))["pagination"]

    implied_pages = -(-pag["total_results"] // PER_PAGE)  # ceil
    assert implied_pages == pag["total_pages"], (
        "the count in the header implies a different number of pages than the "
        f"pager offers: {pag}"
    )


@pytest.mark.asyncio
async def test_the_next_button_still_reaches_the_row_the_fold_never_touched():
    """CERT-2694's reachability must survive this — it is the ship #5513 bought.

    `offset` indexes the UNFOLDED set, so every page boundary is a raw-row
    boundary and the 26th row sits at raw offset 25.
    """
    pag = (await _payload(_page_one(), total=RAW_TOTAL, page=1))["pagination"]

    assert pag["total_pages"] == 2
    assert pag["has_next"] is True


@pytest.mark.asyncio
async def test_a_paginated_query_with_no_fold_is_unchanged():
    """CONTROL: where nothing collapses, nothing about this may move."""
    pag = (await _payload(_filler(PER_PAGE), total=RAW_TOTAL, page=1))["pagination"]

    assert pag["total_results"] == RAW_TOTAL
    assert pag["total_pages"] == 2
    assert pag["has_next"] is True
