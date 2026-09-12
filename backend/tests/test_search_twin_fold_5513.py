"""Guard: the SEARCH front door folds twin rows too (#5513).

THE PAGE THIS EXISTS FOR. `GET /api/events/search?q=red sox`, read on production
2026-09-12 05:52Z. Page one, 25 results, **three** duplicate
`(commence_time, home, away)` groups out of 22:

    2026-09-12 20:10Z  Red Sox-Royals    15310368 (espn id)  + 15305549 (no ids)
    2026-09-04 23:05Z  Orioles-Red Sox   15295059 (suspended) + 15302361 (completed)
    2026-08-29 17:05Z  Yankees-Red Sox   15295242 (completed) + 14877917 (closed)

A fan searching their own club is shown tomorrow's 1:10 game twice (the second
card reading "No price yet"), a 0-0 MLB FINAL, and an undated "No result
reported" row.

WHY SEARCH WAS LAST. `/api/feed`, `GET /api/events` (#4100) and
`/api/teams/{identifier}` (#5487) all fold already. Search runs a DIFFERENT
collapse — `collapse_duplicate_fixtures` (#2623) — and that helper
*deliberately declines this population*. Its own docstring:

    "The duplicate rows that pass 5 found in MLB are real ... but they are a
     DIFFERENT shape: equally specific, equally scored, so no dominance test can
     pick a survivor and none should try."

It is right: it is a dominance test, and it is scoped to individual sports
because running it on team sports ate consecutive games of an MLB series.
`fold_twin_events` is the helper written for the declined shape — it elects
rather than ranks by specificity, and its minute-key is what makes it safe where
dominance is not. So the two stages are complementary, and this file's job is to
prove BOTH still fire and neither displaced the other.

WHAT EACH TEST IS DEFENDING. Not "a route returns a list":

* the ship itself — Alex's club stops appearing twice
  (`test_the_production_red_sox_pair_is_served_as_one_row`);
* the thing a careless fix breaks — a real doubleheader is two real games
  (`test_a_doubleheader_survives_as_two_rows`), and so are two different
  fixtures at one instant (`test_two_different_fixtures_are_never_folded`);
* the stage it was added NEXT TO — the tennis ghost must still collapse, or the
  new stage silently replaced #2623 rather than joining it
  (`test_the_tennis_ghost_still_collapses`);
* the number beside the rows (`test_total_results_counts_what_was_served`);
* the page surviving a bad fold (`test_a_raising_fold_serves_the_unfolded_page`);
* the venue union actually landing (`test_the_survivor_keeps_the_dropped_rows_venue`).

🔴 REAL `Event` OBJECTS, NEVER MagicMock — the same warning
`test_team_page_twin_fold_5487.py` carries. The union is delivered with
`set_committed_value`, which reaches through `_sa_instance_state`; on a MagicMock
that call is absorbed into an auto-attribute, raising nothing and doing nothing,
and the union test would pass against a fold that merged none.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import Event, Sport
from app.routes.events import search_events

MLB = Sport(id=1, key="baseball_mlb", name="MLB", group="Baseball", active=True)
WTA = Sport(id=2, key="tennis_wta", name="WTA", group="Tennis", active=True)
WTA_OPEN = Sport(
    id=3, key="tennis_wta_us_open", name="WTA US Open", group="Tennis", active=True
)

#: The production pair, verbatim (read 2026-09-12 05:52Z).
ESPN_ROW = 15310368
STATPAL_ROW = 15305549
RED_SOX = "Boston Red Sox"
ROYALS = "Kansas City Royals"

FIRST_PITCH = datetime(2026, 9, 12, 20, 10, tzinfo=timezone.utc)


def _event(
    id,
    *,
    sport=MLB,
    away=ROYALS,
    home=RED_SOX,
    commence=FIRST_PITCH,
    status="scheduled",
    espn_id=None,
    home_score=None,
    away_score=None,
    sources=None,
):
    e = Event(
        id=id,
        sport_id=sport.id,
        away_team_name=away,
        home_team_name=home,
        commence_time=commence,
        status=status,
        home_score=home_score,
        away_score=away_score,
        espn_id=espn_id,
        win_probability_sources=sources,
    )
    e.sport = sport
    return e


def _production_pair():
    """The Red Sox-Royals pair as production holds it.

    `15310368` carries the ESPN id and the odds history; `15305549` is the
    id-less statpal claim that ruling 048 correctly CREATED rather than
    absorbed. Equally specific and equally scoreless, which is precisely why
    `collapse_duplicate_fixtures` leaves both standing.
    """
    return [
        _event(ESPN_ROW, espn_id="401816907", sources={"betting": 0.58, "espn": 0.57}),
        _event(STATPAL_ROW, sources={"kalshi": 0.61}),
    ]


def _mock_db(events, *, total=None):
    db = AsyncMock()
    count = len(events) if total is None else total

    def make_result(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.fetchall.return_value = []
        r.all.return_value = []
        r.scalar.return_value = count
        r.scalar_one_or_none.return_value = None
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        # Only the event page query yields rows. The count is read off
        # `.scalar()`, which every result carries, and every other stage
        # (futures, outcomes, teams, snapshots) returns nothing — the shape of
        # an unenriched page.
        if "count(" in s:
            return make_result([])
        if "futures_markets" in s or "odds_snapshots" in s or "teams" in s:
            return make_result([])
        if "from events" in s:
            return make_result(events)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _payload(rows, *, total=None, q="red sox", **kwargs):
    """Drive the real route. Called directly, so every `Query(...)` default has
    to be passed explicitly or the route receives `Query` objects for ints."""
    rc = MagicMock()
    rc.get.return_value = None  # always a cache MISS, so the route does the work

    with (
        # Imported INSIDE the route from `app.tasks.redis_state`, so that is
        # where it has to be patched. A miss every time keeps the route doing
        # the work the assertions are about.
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch(
            "app.routes.events.folded_probability_sources_batch",
            new=AsyncMock(return_value={}),
        ),
        patch("app.routes.events._record_trending", new=MagicMock()),
    ):
        params = {
            "sport": None,
            "tags": None,
            "page": 1,
            "per_page": 25,
            "days_back": 30,
            "include_upcoming": True,
            "debug_timing": False,
            "current_user": None,
        }
        params.update(kwargs)
        return await search_events(
            request=MagicMock(),
            response=MagicMock(),
            q=q,
            db=_mock_db(rows, total=total),
            **params,
        )


def _ids(payload):
    return [r["id"] for r in payload["results"]]


@pytest.mark.asyncio
async def test_the_production_red_sox_pair_is_served_as_one_row():
    """🔴 THE SHIP. A fan searching their own club stops seeing one game twice."""
    payload = await _payload(_production_pair())

    assert len(payload["results"]) == 1, (
        "search served both rows for one fixture — this is the production bug, "
        f"got ids {_ids(payload)}"
    )


@pytest.mark.asyncio
async def test_the_surviving_row_is_the_anchored_one():
    """Which row survives is not arbitrary and must not flicker.

    `twin_identity_rank` elects on an ESPN id before source count, so the card a
    reader keeps is the one the event page, the chart and the settlement path
    can all still reach. Serving `15305549` would be one row — and a row that
    leads nowhere.
    """
    payload = await _payload(_production_pair())

    assert _ids(payload) == [ESPN_ROW]


@pytest.mark.asyncio
async def test_the_survivor_keeps_the_dropped_rows_venue():
    """The fold is a union, not a deletion — "the blend is the product".

    Electing a winner and discarding the loser's sources would delete Kalshi's
    price for this game from the page, which is the ruling's own counter-case.
    """
    rows = _production_pair()
    await _payload(rows)

    survivor = next(r for r in rows if r.id == ESPN_ROW)
    assert survivor.win_probability_sources.get("kalshi") == 0.61, (
        "the statpal row's Kalshi price did not reach the surviving card: "
        f"{survivor.win_probability_sources}"
    )
    # Additive only: the survivor's own readings are never overwritten.
    assert survivor.win_probability_sources["betting"] == 0.58


@pytest.mark.asyncio
async def test_a_doubleheader_survives_as_two_rows():
    """🔴 THE CONTROL. Two real games, same clubs, same day.

    This is the case a looser key eats, and it is not hypothetical: #2623's
    first cut ate consecutive games of an MLB series. The fold's key carries the
    commence MINUTE for exactly this reason — authority/148 measured the delta-t
    distribution across the twin population and found a 220x gap, nothing at all
    between 300s and 66,000s, so the minute is measured and not tuned.
    """
    rows = [
        _event(1, commence=FIRST_PITCH),
        _event(2, commence=FIRST_PITCH + timedelta(hours=3, minutes=30)),
    ]
    payload = await _payload(rows)

    assert len(payload["results"]) == 2, (
        "the fold ate a doubleheader — same clubs, different first pitch: "
        f"{_ids(payload)}"
    )


@pytest.mark.asyncio
async def test_two_different_fixtures_are_never_folded():
    """Same minute, different opponents — nothing here is a twin."""
    rows = [
        _event(1, away=ROYALS),
        _event(2, away="New York Yankees"),
    ]
    payload = await _payload(rows)

    assert len(payload["results"]) == 2


@pytest.mark.asyncio
async def test_the_tennis_ghost_still_collapses():
    """🔴 The stage this was added NEXT TO must still fire.

    #2623's population is a different shape: a rich tournament row and a
    scoreless surname-only ghost from the generic per-tour bucket, start times
    hours apart. The twin fold's minute-key cannot reach that pair at all, so if
    it stops collapsing, the new stage displaced the old one rather than joining
    it — a regression this file would otherwise not see.
    """
    rows = [
        _event(
            1,
            sport=WTA_OPEN,
            away="Aryna Sabalenka",
            home="Iga Swiatek",
            status="completed",
            home_score=1,
            away_score=2,
        ),
        _event(
            2,
            sport=WTA,
            away="Sabalenka",
            home="Swiatek",
            commence=FIRST_PITCH + timedelta(hours=6),
            status="scheduled",
        ),
    ]
    payload = await _payload(rows)

    assert len(payload["results"]) == 1, (
        "the tennis ghost survived — #2623's dominance pass stopped firing: "
        f"{_ids(payload)}"
    )
    assert _ids(payload) == [1], "the scored tournament row must be the survivor"


@pytest.mark.asyncio
async def test_total_results_counts_what_was_served():
    """The number beside the rows must not contradict the rows.

    `total_results` is what the page prints as "· 16 games" (#2623). It is
    floored at what is rendered, so it can never claim fewer games than the
    reader can count, and it under-counts the collapse on later pages rather
    than over-counting it.
    """
    payload = await _payload(_production_pair(), total=2)

    assert payload["pagination"]["total_results"] == 1
    assert len(payload["results"]) == 1


@pytest.mark.asyncio
async def test_the_sport_count_follows_the_surviving_rows():
    """`sports[].count` is built in the format loop, so it must see the fold."""
    payload = await _payload(_production_pair(), total=2)

    mlb = next(s for s in payload["sports"] if s["key"] == "baseball_mlb")
    assert mlb["count"] == 1


@pytest.mark.asyncio
async def test_a_raising_fold_serves_the_unfolded_page():
    """Gotcha #42 applied to a whole stage.

    The fold improves the page; it is never a precondition for having one. If it
    raises, the reader gets today's bug — two cards — and not an error.
    """
    with patch(
        "app.routes.events.fold_twin_events", side_effect=RuntimeError("boom")
    ):
        payload = await _payload(_production_pair())

    assert len(payload["results"]) == 2, (
        "a raising fold took the page down with it instead of degrading"
    )


@pytest.mark.asyncio
async def test_a_single_row_page_is_untouched():
    """The stage is skipped below two rows and must not disturb the one row."""
    payload = await _payload([_event(ESPN_ROW, espn_id="401816907")])

    assert _ids(payload) == [ESPN_ROW]


@pytest.mark.asyncio
async def test_a_folded_first_page_keeps_the_next_distinct_raw_row_reachable_5513():
    """🔴 CERT-2694. A collapse that removes a DUPLICATE must not remove a GAME.

    The arithmetic that adjusts `total_results` (#2623, extended by #5513) used
    to feed `total_pages` as well, and the two are not the same question.
    `offset = (page - 1) * per_page` indexes the UNFOLDED result set — folding
    happens after the limit precisely to keep it there — so every page boundary
    is a raw-row boundary. Subtracting the page's collapsed rows from the count
    the pager is built on retires a page that still holds rows.

    The specimen the grader reproduced: 26 raw matches, `per_page` 25, one twin
    pair on page one. 24 rows served, `total_results` 25, and the old code then
    reported ONE page with `has_next` false — while the distinct 26th row sits
    at raw offset 25. `search/page.tsx` renders no pager at all when
    `total_pages` is 1, so that row is not merely un-hinted, it is unreachable.
    """
    page_one = _production_pair() + [
        _event(9000 + i, away=f"Away {i}", home=f"Home {i}",
               commence=FIRST_PITCH + timedelta(days=i + 1))
        for i in range(23)
    ]
    assert len(page_one) == 25, "the fixture must fill a whole raw page"

    payload = await _payload(page_one, total=26, per_page=25)

    # The fold fired: one of the 25 raw rows went.
    assert len(payload["results"]) == 24, _ids(payload)

    pag = payload["pagination"]
    # #5559 moved this line, and only this line. The corpus does not fit on one
    # page, so the page's own fold is a SAMPLE and is no longer extrapolated to
    # the corpus count — otherwise the same query prints a different, rising
    # number on each page. #2623's exactness is kept where the reader can check
    # it (`test_total_results_counts_what_was_served`, one page, still 1). What
    # this test is FOR is untouched below: the pager still counts raw rows.
    assert pag["total_results"] == 26

    # And the pager still reaches the row the fold never touched.
    assert pag["total_pages"] == 2, (
        "the page count was derived from the adjusted total, so the 26th raw "
        f"row is unreachable: {pag}"
    )
    assert pag["has_next"] is True


@pytest.mark.asyncio
async def test_the_final_distinct_row_is_served_on_the_page_the_pager_offers():
    """The other half of reachability: page two must actually hold the row.

    The test above proves the NEXT button appears. This one walks through it —
    same corpus, `page=2`, the raw tail — because a pager that offers a page the
    route serves empty is the same defect wearing a different number.
    """
    tail = [_event(9999, away="Tail Away", home="Tail Home",
                   commence=FIRST_PITCH + timedelta(days=40))]

    payload = await _payload(tail, total=26, page=2, per_page=25)

    assert _ids(payload) == [9999]
    assert payload["pagination"]["has_next"] is False
    assert payload["pagination"]["has_prev"] is True


@pytest.mark.asyncio
async def test_an_unfolded_page_count_is_unchanged():
    """CONTROL: the repair may not move the page count where nothing collapsed.

    Two distinct fixtures, 26 in the corpus: two pages before and after. A fix
    that reached for the raw count in the wrong place — or that stopped
    adjusting `total_results` at all — is visible here and in the assertion on
    `total_results` above, which still reads the FOLDED number.
    """
    rows = [
        _event(1, away=ROYALS, home=RED_SOX, commence=FIRST_PITCH),
        _event(2, away="Yankees", home=RED_SOX, commence=FIRST_PITCH + timedelta(days=1)),
    ]

    payload = await _payload(rows, total=26, per_page=25)

    assert len(payload["results"]) == 2
    assert payload["pagination"]["total_results"] == 26
    assert payload["pagination"]["total_pages"] == 2
    assert payload["pagination"]["has_next"] is True
