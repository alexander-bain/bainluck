"""Guard: the list rails stop printing a ghost the event page already folded (#6231).

THE CARD THIS EXISTS FOR. iPhone build 1.0 (10), Sports tab, 2026-09-14 22:07Z.
The tab was topped by a "Live Now (1)" card for a game that had finished nearly
two hours earlier:

     ● Live Now  (1)
       La Liga - Spain    ● LIVE
       EIB  Eibar
       FOR  Celta Fortuna

No score, no clock, no probability. Directly beneath it the "Just Happened"
FINAL cards all carried scores and percentages, so the one card claiming to be
live was the only one with nothing in it.

    id        teams                     sport_key                      status     score
    15308951  Celta Fortuna v Eibar     soccer_spain_la_liga           live       null
    15306978  Celta Fortuna v SD Eibar  soccer_spain_segunda_division  completed  0-4

`GET /api/events/15308951` **already returned 15306978** — the event page has
resolved this class since Q050. The list rails did not:

    GET /api/events/search?q=Celta Fortuna  ->  served BOTH rows
    GET /api/events?status=live             ->  served the ghost

So a reader who tapped the dead card landed on the right game, and the tab that
sent them there was advertising a row we already knew was not a fixture.

🔴 THE SIBLING FOLD CANNOT REACH THIS, AND NO WIDENING OF ITS KEY WOULD.
`fold_twin_events` is a pure IN-PAGE fold — it needs both rows in the same
result set. On `status=live` the canonical is `completed`, so the very filter
that selects the ghost excludes its twin. The two rows also agree on neither
name (`Eibar` / `SD Eibar`), league, nor minute (21:30Z is Kalshi's expected
expiration, 18:30Z the kick-off), so the fold correctly declined on search too.
The Q050 verdict has no such limit: it is id-keyed and asks the database, so the
canonical need not be on the page — or be renderable at all.

WHAT EACH TEST HERE IS DEFENDING. Not "a route returns a list":

* the ship — the dead card is gone from both rails
  (`test_the_live_now_ghost_is_off_the_events_list`,
  `test_the_ghost_is_off_the_search_page`);
* the thing a careless fix breaks — the REAL row must survive, on both rails.
  A suppression keyed on the wrong side of the pair would empty the fixture
  instead of de-duplicating it
  (`test_the_real_match_survives_on_both_rails`);
* the cost — a page of ordinary fixtures must not pay a query for a verdict none
  of its rows can pass (`test_an_ordinary_page_issues_no_verdict_query`);
* the belt — a verdict that raises serves the unsuppressed page, never a 500
  (`test_a_failing_verdict_serves_the_page_rather_than_an_error`).

The verdict's own seven refusals are pinned in
`test_market_born_duplicate_reads_as_canonical_q050.py`, including the set-form
arms. This file is about DELIVERY: that the two rails call it, act on it, and
report honestly.

REAL `Event` OBJECTS, NOT MagicMock, for the reason
`test_events_list_twin_fold_4100.py` records at length: the sibling fold stage
delivers its union through `set_committed_value`, which reaches through
`_sa_instance_state` and is silently absorbed by a MagicMock.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import Event, Sport
from app.routes.events import list_events, search_events

LA_LIGA = Sport(
    id=90, key="soccer_spain_la_liga", name="La Liga", group="Soccer", active=True
)
SEGUNDA = Sport(
    id=91,
    key="soccer_spain_segunda_division",
    name="Segunda División",
    group="Soccer",
    active=True,
)

GHOST = 15308951
CANONICAL = 15306978
TICKER = "KXLALIGAGAME-26SEP14CELEIB"

KICKOFF = datetime(2026, 9, 14, 18, 30, tzinfo=timezone.utc)
# Kalshi's expected expiration, exactly three hours later — gotcha #14, and the
# reason the two rows never shared a fold key.
EXPIRATION = KICKOFF + timedelta(hours=3)


def _ghost() -> Event:
    """The row the reader saw: live, scoreless, priceless, wrong league."""
    e = Event(
        id=GHOST,
        sport_id=LA_LIGA.id,
        home_team_name="Celta Fortuna",
        away_team_name="Eibar",
        commence_time=EXPIRATION,
        commence_time_source="kalshi",
        status="live",
        home_score=None,
        away_score=None,
        completed_at=None,
        win_probability_sources={},
    )
    e.sport = LA_LIGA
    return e


def _canonical() -> Event:
    """The match that was actually played, 0-4, in the league it belongs to."""
    e = Event(
        id=CANONICAL,
        sport_id=SEGUNDA.id,
        home_team_name="Celta Fortuna",
        away_team_name="SD Eibar",
        commence_time=KICKOFF,
        commence_time_source="odds_api",
        external_id="247343bc379dfe120732d07d0106e412",
        status="completed",
        home_score=0,
        away_score=4,
        completed_at=datetime(2026, 9, 14, 20, 27, 27, tzinfo=timezone.utc),
        win_probability_sources={"betting": 0.31},
    )
    e.sport = SEGUNDA
    return e


def _ordinary_fixture(event_id: int = 15399001) -> Event:
    """A row a real schedule timed — excluded by the cheap gate, so it is free."""
    e = Event(
        id=event_id,
        sport_id=SEGUNDA.id,
        home_team_name="Real Zaragoza",
        away_team_name="Albacete",
        commence_time=KICKOFF,
        commence_time_source="odds_api",
        status="scheduled",
        win_probability_sources={"betting": 0.5},
    )
    e.sport = SEGUNDA
    return e


class _VerdictRow:
    """One row of `_DRAIN_VERDICT_SQL`, read through `._mapping` as the code does."""

    def __init__(self, mapping):
        self._mapping = mapping


def _verdict_mapping(event_id: int, *, candidate, sport_key, **overrides):
    mapping = {
        "event_id": event_id,
        "provenance": "kalshi",
        "sport_key": sport_key,
        "carries_truth": False,
        "game_anchors": 0,
        "market_anchors": 1,
        "unresolved": 0,
        "other_targets": 1 if candidate is not None else 0,
        "candidate_id": candidate,
        "holds_markets": False,
        # #6262 gap B added refusal 6's second witness. It is planted ABSENT
        # here on purpose: this file is about the list rails, not about the
        # verdict, and an absent market witness reproduces exactly the
        # pre-gap-B behaviour these cases were written against. The witness
        # itself is graded against the real SQL in
        # `test_market_born_duplicate_cross_sport_witness_6262.py` — a
        # hand-built mapping cannot grade a statement.
        "market_ids": 0,
        "market_id": None,
    }
    mapping.update(overrides)
    return _VerdictRow(mapping)


def _mock_db(events, *, verdict_rows=None, verdict_raises=False, statements=None):
    """A session that answers the page query AND the drain verdict.

    The verdict is discriminated on `event_provider_anchors`, which appears in
    no other statement on either route — matching on `from events` would catch
    the verdict's own `cand` CTE and hand it the page.
    """
    db = AsyncMock()
    seen = statements if statements is not None else []

    def make_result(rows, *, fetched=None):
        """`fetched` is deliberately separate from `rows`.

        Only the two statements this file is about read `.fetchall()`; the page
        stages read `.scalars().all()` and every other enrichment stage expects
        `.fetchall()` to be a list of TUPLES it can unpack. Returning the ORM
        rows from both accessors makes the enrichment stages explode on an
        `Event`, which is a harness story, not a result.
        """
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.fetchall.return_value = list(fetched or [])
        r.all.return_value = list(fetched or [])
        r.scalar.return_value = len(events)
        r.scalar_one_or_none.return_value = None
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        seen.append(s)
        if "event_provider_anchors" in s:
            if verdict_raises:
                raise RuntimeError("verdict query exploded")
            return make_result([], fetched=list(verdict_rows or []))
        # The canonical-sport lookup: `SELECT e.id, s.key ... WHERE e.id IN ...`
        if s.startswith("select e.id, s.key"):
            return make_result(
                [], fetched=[(CANONICAL, SEGUNDA.key), (GHOST, LA_LIGA.key)]
            )
        if "count(" in s:
            return make_result([])
        if "futures_markets" in s or "odds_snapshots" in s or "teams" in s:
            return make_result([])
        if "win_prob_snapshots" in s:
            return make_result([])
        if "from events" in s:
            return make_result(events)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


_PATCHES = (
    "app.routes.events._load_gei_percentiles",
    "app.routes.events._build_team_lookup",
    "app.routes.events.folded_probability_sources_batch",
)


async def _list_payload(rows, *, status=None, **db_kwargs):
    with (
        patch(_PATCHES[0], new=AsyncMock(return_value={})),
        patch(_PATCHES[1], new=AsyncMock(return_value={})),
        patch(_PATCHES[2], new=AsyncMock(return_value={})),
    ):
        return await list_events(
            sport=None,
            status=status,
            days=7,
            limit=200,
            offset=0,
            db=_mock_db(rows, **db_kwargs),
        )


async def _search_payload(rows, q="celta fortuna", **db_kwargs):
    rc = MagicMock()
    rc.get.return_value = None  # always a cache MISS, so the route does the work
    with (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch(_PATCHES[0], new=AsyncMock(return_value={})),
        patch(_PATCHES[1], new=AsyncMock(return_value={})),
        patch(_PATCHES[2], new=AsyncMock(return_value={})),
        patch("app.routes.events._record_trending", new=MagicMock()),
    ):
        return await search_events(
            request=MagicMock(),
            response=MagicMock(),
            q=q,
            sport=None,
            tags=None,
            page=1,
            per_page=25,
            days_back=30,
            include_upcoming=True,
            debug_timing=False,
            current_user=None,
            db=_mock_db(rows, **db_kwargs),
        )


def _ids(payload):
    """The two routes name their list differently — `events` vs `results`."""
    rows = payload["events"] if "events" in payload else payload["results"]
    return [r["id"] for r in rows]


def _resolves_ghost():
    return [_verdict_mapping(GHOST, candidate=CANONICAL, sport_key=LA_LIGA.key)]


# =============================================================================
# The ship
# =============================================================================


@pytest.mark.asyncio
async def test_the_live_now_ghost_is_off_the_events_list():
    """The card Alex saw. `GET /api/events` stops serving 15308951."""
    payload = await _list_payload(
        [_ghost(), _canonical()], verdict_rows=_resolves_ghost()
    )

    assert GHOST not in _ids(payload), (
        "the scoreless LIVE ghost is still on the events list — this is the "
        f"Sports tab bug, served ids {_ids(payload)}"
    )


@pytest.mark.asyncio
async def test_a_status_filtered_page_holding_ONLY_the_ghost_serves_nothing():
    """CERT-2882's named follow-up, `6231-STATUS-FILTERED-SINGLETON-GUARD`.

    🔴 **THE SHIP'S OWN SHAPE, WHICH THE TESTS ABOVE DO NOT EXERCISE.** They
    pass `status=None` and put BOTH rows on the page, so an in-page fold keyed
    on names or kickoff could pass them. The reader's actual request was
    `GET /api/events?status=live`, and on that page **the canonical is excluded
    by the filter itself** — it is `completed`. One row in, and the only correct
    answer is zero rows out.

    That is the whole argument for a DB-backed id-keyed verdict over a better
    fold key: with nothing to fold against, an in-page algorithm has no
    information at all, while the verdict asks the database which row a market
    already decided this one belongs to. If this ever passes because the
    canonical was quietly added to the page, the assertion below has stopped
    testing the ship — hence `rows` is a one-element list, asserted as such.
    """
    rows = [_ghost()]
    assert len(rows) == 1, "this guard is about a SINGLETON page"

    payload = await _list_payload(
        rows, status="live", verdict_rows=_resolves_ghost()
    )

    assert _ids(payload) == [], (
        "the Sports tab's 'Live Now' still has a card in it — the ghost was "
        f"the only row on the page, served ids {_ids(payload)}"
    )
    assert payload["count"] == 0, (
        f"'Live Now ({payload['count']})' over an empty list is the header "
        "Alex saw; count must follow the served rows"
    )


@pytest.mark.asyncio
async def test_a_status_filtered_singleton_that_RESOLVES_NOTHING_survives():
    """The other direction, so the guard above cannot pass by emptying pages.

    Same page, same filter, same single row — and a verdict that refuses. An
    implementation that drops every candidate it queried passes the test above
    and fails this one.
    """
    payload = await _list_payload(
        [_ghost()],
        status="live",
        verdict_rows=[_verdict_mapping(GHOST, candidate=None,
                                       sport_key=LA_LIGA.key)],
    )

    assert _ids(payload) == [GHOST], (
        "a row the verdict refused was suppressed anyway — the rail is "
        f"dropping candidates, not duplicates; served ids {_ids(payload)}"
    )
    assert payload["count"] == 1


@pytest.mark.asyncio
async def test_the_ghost_is_off_the_search_page():
    """`q=Celta Fortuna` served both rows; it must serve one."""
    payload = await _search_payload(
        [_ghost(), _canonical()], verdict_rows=_resolves_ghost()
    )

    assert GHOST not in _ids(payload), (
        f"search is still serving the ghost, ids {_ids(payload)}"
    )


@pytest.mark.asyncio
async def test_the_real_match_survives_on_both_rails():
    """The row with the 0-4 in it is the one that must NOT disappear.

    The failure this guards is the one worth more than the bug: a suppression
    reading the pair from the wrong side empties the fixture instead of
    de-duplicating it, and the reader loses the score as well as the ghost.
    """
    for name, payload in (
        ("list", await _list_payload(
            [_ghost(), _canonical()], verdict_rows=_resolves_ghost())),
        ("search", await _search_payload(
            [_ghost(), _canonical()], verdict_rows=_resolves_ghost())),
    ):
        assert CANONICAL in _ids(payload), (
            f"the {name} rail lost the real match — the fixture is now empty, "
            f"served ids {_ids(payload)}"
        )


@pytest.mark.asyncio
async def test_the_list_count_reports_what_was_actually_served():
    """`count` shrinks WITH the list. A count of 2 over one row is a lie."""
    payload = await _list_payload(
        [_ghost(), _canonical()], verdict_rows=_resolves_ghost()
    )

    assert payload["count"] == len(payload["events"])


# =============================================================================
# What a careless change breaks
# =============================================================================


@pytest.mark.asyncio
async def test_a_row_the_verdict_refuses_is_still_served():
    """No verdict, no suppression — the refusal direction is the safe one.

    A missed ghost renders, which is today's behaviour. A wrong suppression
    takes a real fixture off the site.
    """
    refused = [_verdict_mapping(GHOST, candidate=None, sport_key=LA_LIGA.key)]

    payload = await _list_payload([_ghost(), _canonical()], verdict_rows=refused)

    assert GHOST in _ids(payload)


@pytest.mark.asyncio
async def test_an_ordinary_page_issues_no_verdict_query():
    """A page of rows a real schedule timed must not pay for this.

    `is_drain_candidate_row` runs in Python over columns the rows already hold,
    so the query is never issued. A regression here is a silent latency defect
    on `/api/events`, hence an assertion on the statements rather than a timing.
    """
    statements = []
    await _list_payload(
        [_ordinary_fixture(), _canonical()], statements=statements
    )

    assert not [s for s in statements if "event_provider_anchors" in s], (
        "an ordinary page issued the drain verdict query"
    )


@pytest.mark.asyncio
async def test_a_failing_verdict_serves_the_page_rather_than_an_error():
    """Gotcha #42 applied to a stage: the page is never a casualty of the fix."""
    payload = await _list_payload(
        [_ghost(), _canonical()], verdict_raises=True
    )

    assert set(_ids(payload)) == {GHOST, CANONICAL}
