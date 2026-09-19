"""Guard: the search sport pills count the whole matched set, not the page (#5514).

THE PAGE THIS EXISTS FOR. `GET /api/events/search?q=red sox`, read at 390px on
production 2026-09-12 05:37Z. The header says:

    73 results · 2 teams · 61 games · 10 markets

and a centimetre underneath it the sport filter pills say:

    [MLB (24)]  [MiLB (1)]

24 + 1 = 25, which is `per_page`. It is not a count of anything a reader asked
for. `sports[].count` was tallied in the format loop — over the rows of the
CURRENT PAGE — while `total_results` counted the whole matched set, so the two
numbers sat beside each other disagreeing, and the pill under-reported by more
the deeper the result set ran. A query returning 300 games still showed a pill
capped at 25.

It also made the pill's own behaviour a promise it could not keep: tapping
"MLB (24)" re-queries with `sport=baseball_mlb` and returns every MLB row in the
set, which is far more than 24.

WHAT CHANGED. The count query became a `GROUP BY sport` over the same predicate
(`_search_sport_facets`), so `total_results` is the SUM of the pills rather than
a number computed next to them. One statement, so they cannot drift.

🔴 WHAT MUST NOT COME BACK WITH IT, and it is the reason this file has a control
section. The page-local tally was not merely wrong — in ONE regime it was the
only right answer. `collapse_duplicate_fixtures` and `fold_twin_events` run
AFTER the limit, in Python, so a grouped count over the corpus cannot see them:
it counts both halves of a folded twin. #5513's
`test_the_sport_count_follows_the_surviving_rows` pins "MLB (1)" for a folded
pair, and a naive whole-set count reads "MLB (2)" there.

So the boundary is the same one #5559 drew for `total_results`, for the same
reason and in the same branch: while the set fits on one page the page IS the
set, and its tally is the grouped count minus duplicates the reader cannot see.
Past that the collapse is a sample and the raw grouped count stands. The pills
therefore track `total_results` in both regimes by construction.

WHAT EACH TEST IS DEFENDING. Not "the route returns a sports list":

* the ship — a paginated query's pill reports the set, not `per_page`
  (`test_the_pill_counts_the_whole_set_not_the_page`);
* the arithmetic a reader can do on screen — the pills sum to the header
  (`test_the_pills_sum_to_the_header_count`);
* the sport that is not on page one at all, which the old tally could not
  mention (`test_a_sport_absent_from_page_one_still_gets_a_pill`);
* 🔴 the control, and the thing a careless fix breaks — a single-page folded
  result still follows the SURVIVING rows
  (`test_a_single_page_result_still_counts_survivors_not_raw_rows`);
* the order, which is a contract here and not a detail, because
  `frontend/app/search/page.tsx` renders `results.sports` with no sort, filter
  or slice of its own (`test_the_pills_are_ordered_biggest_first`);
* the degradation — a count that timed out leaves a tappable pill rather than
  an empty filter bar (`test_a_degraded_count_still_serves_a_pill`).

🔴 REAL `Event` objects, never MagicMock — the same warning
`test_search_twin_fold_5513.py` carries. The fold unions the dropped row's
sources with `set_committed_value`, which reaches through `_sa_instance_state`;
on a MagicMock that call is absorbed into an auto-attribute and does nothing, so
the single-page control below would pass against a fold that folded nothing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import Event, Sport
from app.routes.events import search_events

MLB = Sport(id=1, key="baseball_mlb", name="MLB", group="Baseball", active=True)
MILB = Sport(id=2, key="baseball_milb", name="MiLB", group="Baseball", active=True)

RED_SOX = "Boston Red Sox"
FIRST_PITCH = datetime(2026, 9, 12, 20, 10, tzinfo=timezone.utc)
PER_PAGE = 25

#: The production specimen: 61 games over three pages.
RAW_TOTAL = 61


def _event(event_id, *, sport=MLB, home=RED_SOX, away="Texas Rangers", commence=None,
           espn_id=None):
    e = Event(
        id=event_id,
        sport_id=sport.id,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence or FIRST_PITCH,
        status="scheduled",
        espn_id=espn_id,
    )
    e.sport = sport
    return e


def _page_of(n, *, sport=MLB, start=1000):
    """`n` distinct fixtures — distinct minute AND distinct opponent, so neither
    collapse stage has anything to elect. A page that folds by accident would
    make every count below measure the fold instead of the pills."""
    return [
        _event(start + i, sport=sport, away=f"Away {i}",
               commence=FIRST_PITCH + timedelta(days=i + 1))
        for i in range(n)
    ]


class _QueryCanceled(Exception):
    """What `_is_query_timeout` recognises — SQLSTATE 57014, the authority.

    A bare `TimeoutError` is NOT a statement timeout to that helper and the
    route re-raises it, which is correct behaviour and would have made the
    degradation test below pass for the wrong reason (it never reached the
    fallback at all).
    """

    sqlstate = "57014"


def _mock_db(events, *, grouped, raise_on_count=False):
    """`grouped` is the corpus, stated outright as `(key, name, count)` rows.

    Stated rather than derived from `events`: this file is about the number the
    pill gets when the page CANNOT see the corpus, so a stub that computes the
    corpus from the page would assert nothing.
    """
    db = AsyncMock()
    total = sum(row[2] for row in grouped)

    def make_result(rows, *, all_rows=None):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.fetchall.return_value = []
        r.all.return_value = all_rows or []
        r.scalar.return_value = total
        r.scalar_one_or_none.return_value = None
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "count(" in s:
            if raise_on_count:
                raise _QueryCanceled("canceling statement due to statement timeout")
            return make_result([], all_rows=list(grouped))
        if "futures_markets" in s or "odds_snapshots" in s or "teams" in s:
            return make_result([])
        if "from events" in s:
            return make_result(events)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _payload(rows, *, grouped, page=1, per_page=PER_PAGE, q="red sox",
                   raise_on_count=False):
    """Drive the real route. Called directly, so every `Query(...)` default has
    to be passed explicitly or the route receives `Query` objects for ints."""
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
            db=_mock_db(rows, grouped=grouped, raise_on_count=raise_on_count),
            sport=None,
            tags=None,
            page=page,
            per_page=per_page,
            days_back=30,
            include_upcoming=True,
            debug_timing=False,
            current_user=None,
        )


def _pill(payload, key):
    return next((s for s in payload["sports"] if s["key"] == key), None)


# ---------------------------------------------------------------------------
# THE SHIP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_pill_counts_the_whole_set_not_the_page():
    """🔴 THE SHIP. "MLB (24)" under "61 games" becomes "MLB (60)"."""
    payload = await _payload(
        _page_of(24) + _page_of(1, sport=MILB, start=2000),
        grouped=[("baseball_mlb", "MLB", 60), ("baseball_milb", "MiLB", 1)],
    )

    # The page really is a page — without this the assertion below is satisfied
    # by a "page" that happened to hold the whole set.
    assert len(payload["results"]) == PER_PAGE
    assert payload["pagination"]["total_pages"] > 1

    assert _pill(payload, "baseball_mlb")["count"] == 60, (
        "the pill is reporting the page again — 24 is `per_page` minus the one "
        "MiLB row, not a count of anything the reader asked for"
    )


@pytest.mark.asyncio
async def test_the_pills_sum_to_the_header_count():
    """The two numbers sit a centimetre apart on screen, so a reader can add up
    the pills and check us. Before #5514 they summed to `per_page`."""
    payload = await _payload(
        _page_of(24) + _page_of(1, sport=MILB, start=2000),
        grouped=[("baseball_mlb", "MLB", 60), ("baseball_milb", "MiLB", 1)],
    )

    assert sum(s["count"] for s in payload["sports"]) == (
        payload["pagination"]["total_results"]
    ) == RAW_TOTAL


@pytest.mark.asyncio
async def test_a_sport_absent_from_page_one_still_gets_a_pill():
    """The old tally could only name sports it had a row for, so a filter the
    reader needed most — the one whose rows are all on page three — was the one
    it could not offer."""
    payload = await _payload(
        _page_of(25),
        grouped=[("baseball_mlb", "MLB", 60), ("baseball_milb", "MiLB", 1)],
    )

    assert {r["sport"] for r in payload["results"]} == {"baseball_mlb"}, (
        "the fixture leaked a MiLB row onto page one, so this proves nothing"
    )
    assert _pill(payload, "baseball_milb") is not None, (
        "a sport in the result set but not on this page got no pill, so the "
        "reader has no way to filter to it"
    )
    assert _pill(payload, "baseball_milb")["count"] == 1


# ---------------------------------------------------------------------------
# 🔴 THE CONTROL — what a careless whole-set count breaks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_single_page_result_still_counts_survivors_not_raw_rows():
    """🔴 #5513's `test_the_sport_count_follows_the_surviving_rows`, restated
    here because THIS change is the one that would break it.

    Two rows for one fixture — same minute, same teams — fold to one card. The
    grouped corpus count still says 2, because the collapse happens after the
    limit and in Python. While the set fits on one page the page IS the set, so
    the survivor tally is the right answer and the raw count is an over-count of
    what the reader can see.
    """
    pair = [
        _event(15310368, espn_id="401816907"),
        _event(15305549),
    ]
    payload = await _payload(pair, grouped=[("baseball_mlb", "MLB", 2)])

    assert payload["pagination"]["total_pages"] <= 1
    assert len(payload["results"]) == 1, (
        "the twin pair did not fold, so this test is not measuring what it says"
    )
    assert _pill(payload, "baseball_mlb")["count"] == 1, (
        "the pill counted both halves of a folded twin — the reader sees one "
        "card and a pill claiming two"
    )


@pytest.mark.asyncio
async def test_a_single_page_result_that_folds_nothing_is_unchanged():
    """CONTROL on the control: the single-page branch may not move a count where
    nothing collapsed. Catches a fix that reaches for the page tally in the
    wrong place and starts under-reporting whole sports."""
    payload = await _payload(_page_of(3), grouped=[("baseball_mlb", "MLB", 3)])

    assert payload["pagination"]["total_pages"] <= 1
    assert _pill(payload, "baseball_mlb")["count"] == 3
    assert payload["pagination"]["total_results"] == 3


# ---------------------------------------------------------------------------
# ORDER AND DEGRADATION
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_pills_are_ordered_biggest_first():
    """The order is a CONTRACT, not a detail.

    `frontend/app/search/page.tsx` renders `results.sports` with no `.sort()`,
    `.filter()` or `.slice()` of its own, so whatever the route emits is the
    order of the pills on screen — and a bare `GROUP BY` lets Postgres shuffle
    them between two identical requests.
    """
    payload = await _payload(
        _page_of(25),
        grouped=[
            ("baseball_milb", "MiLB", 1),
            ("baseball_mlb", "MLB", 60),
        ],
    )

    assert [s["key"] for s in payload["sports"]] == [
        "baseball_mlb",
        "baseball_milb",
    ], "the pills came back in the corpus query's own order"


@pytest.mark.asyncio
async def test_a_degraded_count_still_serves_a_pill():
    """Gotcha #42 applied to the filter bar: an approximate pill a reader can
    still tap beats an empty one.

    🪤 WHAT THIS DOES AND DOES NOT PIN, because it was written believing the
    stronger thing. Mutating the route's `except` arm to serve an empty facet
    list does NOT fail this test, and that is not a hole in the assertion — a
    degraded count is 0, so `total_pages` is 0, so the `total_pages <= 1` branch
    reaches the page tally regardless of what the `except` arm bound. The
    degraded case is structurally single-page and cannot be made otherwise from
    here.

    So this pins the reader-visible OUTCOME across both mechanisms, which is the
    thing worth defending, and deliberately not the line that happens to deliver
    it. Left in rather than deleted: "the filter bar does not blank when the
    count times out" is exactly the regression nobody would notice in review.
    """
    payload = await _payload(
        _page_of(24) + _page_of(1, sport=MILB, start=2000),
        grouped=[("baseball_mlb", "MLB", 60), ("baseball_milb", "MiLB", 1)],
        raise_on_count=True,
    )

    assert "event_count" in payload.get("degraded", []), (
        "the count did not actually degrade, so this proves nothing"
    )
    assert _pill(payload, "baseball_mlb") is not None
    assert _pill(payload, "baseball_mlb")["count"] == 24
