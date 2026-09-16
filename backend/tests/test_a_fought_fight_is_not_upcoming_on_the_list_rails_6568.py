"""#6568 acceptance 2, the LIST half — search stops leading with a fight already fought.

THE PAGE THIS EXISTS FOR. `https://bainluck.com/search?q=Orobio`, 390px,
2026-09-16, banked at `artifacts-lane1-380/BEFORE-search-orobio-390.png`:

    Results for "Orobio"
    2 results · 2 games

    BOXING                                          Tomorrow 3:00 PM
    JO  Jhon Orobio        No price yet
    AM  Antonio Moran

    BOXING                                  No result reported · Sep 3
    JO  Jhon Orobio    90%
    AM  Antonio Moran  10%
    Pre-match · sportsbooks

One fight, two cards. The card promising "Tomorrow" is the one with nothing in
it; the honest card below it carries the real pre-match reading. Kalshi fought
and graded that bout on **September 3**. The lie sorts ABOVE the truth for one
reason only — its date is fabricated fourteen days into the future — so the
surface whose whole job is to answer a question leads with the wrong answer.

WHERE THE FOURTEEN DAYS COME FROM. `events.commence_time` on `15293327` is
byte-identical to its attached Kalshi contract's `expiration_time`: the ~14-day
settlement backstop Kalshi hangs on a combat card (gotcha #14), copied into the
start column by the auto-create path. The row refutes itself, which is what
`app/utils/kalshi_expiration_start` requires before it moves anything, and the
unit-level proof of that module lives in
`test_a_fought_fight_is_not_upcoming_6568.py`.

🔴 WHY THE SIBLING MECHANISM COULD NOT CARRY THIS. `fold_twin_events` already
recovers a kick-off at its own top (#5905) and every list rail runs it — but it
is SYNCHRONOUS, and this correction needs the event's Kalshi markets, i.e. a
query. So the fold structurally cannot host it and each route must. That is the
honest remaining half #6568 was merged with, written on the issue at the time,
and it is what this file closes for the two surfaces that measurably carry it.

REACH, MEASURED ON PRODUCTION BEFORE A LINE WAS WRITTEN (2026-09-16):

    surface                                      cohort rows served
    ─────────────────────────────────────────────────────────────────
    /api/events/search?q=<fighter>                8 of 8 probed, all
                                                  with the fabricated
                                                  date; 4 of the 8 sat
                                                  directly above their
                                                  honest twin
    /api/events?sport=boxing_boxing&days=14      10 of 10 — the entire
                                                  cohort, in 30 rows
    /api/feed (top 60)                            0
    ─────────────────────────────────────────────────────────────────

So this file is about `search_events` and `list_events` and deliberately not
about the feed, which does not carry the class.

WHAT EACH TEST HERE IS DEFENDING. Not "a route returns a list":

* the ship — the fabricated date is gone from both rails
  (`test_search_stops_dating_a_september_3_fight_september_17`,
  `test_the_events_list_stops_dating_the_september_3_fights_september_17`);
* **that the specimen was ever defective** — every ship test asserts the stored
  value IS the fabricated one before asserting it moved, because a fixture that
  never carried the defect passes a correction test by doing nothing
  (`test_the_specimen_really_does_carry_the_defect_before_the_route_runs`);
* **that the row is PRESENT**, before anything is asserted about its fields. A
  route-level specimen can pass on an empty payload: an assertion over "every
  row that is a cohort row" is vacuously true of no rows, and that is how a
  green test proves nothing (`_row`, which raises rather than returning None);
* the thing a careless fix breaks — nothing may be DROPPED from either rail.
  This route already ruled that question against dropping, in its own words, and
  `not_a_blank_card` cannot reach a `scheduled` row
  (`test_search_answers_with_the_fight_rather_than_with_silence`,
  `test_the_events_list_serves_every_row_it_served_before`);
* the neighbour — the honest twin sitting beside the specimen, and an ordinary
  fixture, must be untouched
  (`test_the_honest_twin_beside_it_is_never_moved`,
  `test_an_ordinary_fixture_is_never_moved`);
* the cost — a page with no candidate row must not pay for the query
  (`test_a_page_of_ordinary_fixtures_issues_no_correction_query`);
* the belt — a correction that raises serves the stored page, never a 500
  (`test_a_correction_that_raises_serves_the_page_rather_than_an_error`);
* the wiring, which no behavioural test can see — a call site that was never
  added, and an ordering that silently moved after the fold
  (`test_both_list_rails_run_the_correction`,
  `test_the_correction_runs_before_the_fold_on_both_rails`).

REAL `Event` OBJECTS, NOT MagicMock, for the reason
`test_events_list_twin_fold_4100.py` records at length and this correction
shares: it delivers through `set_committed_value`, which reaches through
`_sa_instance_state` and is silently absorbed by a MagicMock. A mock would make
every assertion here green against a function that does nothing.

Refs #6568 (acceptance 2), #2693, #5905, #3016. Gotchas #4, #14, #42.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import Event, Sport
from app.routes.events import list_events, search_events
from app.utils.kalshi_expiration_start import TICKER_CONTEST_DATE_SOURCE

BOXING = Sport(id=77, key="boxing_boxing", name="Boxing", group="Boxing", active=True)

#: The specimen, from production. Kalshi's ticker names September 3; the stored
#: hour is the contract's expiration instant, fourteen days later.
GHOST = 15293327
GHOST_TICKER = "KXBOXING-26SEP03OROBIOMORAN"
FABRICATED = datetime(2026, 9, 17, 22, 0, tzinfo=timezone.utc)
CONTEST_DATE = datetime(2026, 9, 3, 0, 0, tzinfo=timezone.utc)

#: The honest twin that sits directly beneath it in the search results: a real
#: schedule provider reported this one, so nothing here may move it.
TWIN = 15294115
TWIN_TIME = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)

ORDINARY = 15313010


def _ghost() -> Event:
    """The card promising "Tomorrow" for a fight fought a fortnight ago."""
    e = Event(
        id=GHOST,
        sport_id=BOXING.id,
        home_team_name="Jhon Orobio",
        away_team_name="Antonio Moran",
        commence_time=FABRICATED,
        commence_time_source="kalshi",
        external_id=None,
        status="scheduled",
        home_score=None,
        away_score=None,
        win_probability_sources={},
    )
    e.sport = BOXING
    return e


def _twin() -> Event:
    """The honest row beneath it — odds-api anchored, with the real reading."""
    e = Event(
        id=TWIN,
        sport_id=BOXING.id,
        home_team_name="Jhon Orobio",
        away_team_name="Antonio Moran",
        commence_time=TWIN_TIME,
        commence_time_source="odds_api",
        external_id="45c0d271c7cba6b9683aae58312a83b5",
        status="suspended",
        win_probability_sources={"betting": 0.9},
    )
    e.sport = BOXING
    return e


def _ordinary(event_id: int = ORDINARY) -> Event:
    """A fight a real schedule timed — refused by the cheap gate, so it is free.

    The names are DERIVED FROM THE ID, and that is not cosmetic. Two of these
    built with the same names and the same minute are a genuine twin pair, and
    `fold_twin_events` — which runs on both of these routes — correctly collapses
    them. A "nothing was dropped" test built on identical fixtures therefore
    fails on the sibling stage doing its job, which is a fixture defect wearing
    this ship's name.
    """
    suffix = event_id - ORDINARY
    e = Event(
        id=event_id,
        sport_id=BOXING.id,
        home_team_name=f"Garan Croft {suffix}",
        away_team_name=f"Alfie Middlemiss {suffix}",
        commence_time=datetime(2026, 9, 19, 16, 0, tzinfo=timezone.utc),
        commence_time_source="odds_api",
        external_id="9f2f0a1c4b7d",
        status="scheduled",
        win_probability_sources={"betting": 0.5},
    )
    e.sport = BOXING
    return e


def _is_correction_query(sql: str) -> bool:
    """The correction's own statement, and nothing else that touches the table.

    Both routes query `futures_markets` for other reasons, so matching the table
    name alone would count an enrichment stage as the correction and make
    `test_a_page_of_ordinary_fixtures_issues_no_correction_query` a test of
    something else entirely. The projection is the discriminator: no other
    statement on either route selects exactly these three columns.
    """
    return (
        "futures_markets.expiration_time" in sql
        and "futures_markets.external_id" in sql
        and "select futures_markets.event_id" in sql
    )


def _mock_db(events, *, markets=None, correction_raises=False, statements=None):
    """A session that answers the page query AND the correction's market lookup.

    `markets` are `(event_id, external_id, expiration_time)` tuples, delivered
    through `.all()` because that is what the correction reads. They are kept
    separate from the page rows for the reason the #6231 rig gives: the
    enrichment stages expect `.fetchall()` to yield unpackable tuples and
    explode on an `Event`, which is a harness story rather than a result.
    """
    db = AsyncMock()
    seen = statements if statements is not None else []

    def make_result(rows, *, fetched=None):
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
        if _is_correction_query(s):
            if correction_raises:
                raise RuntimeError("the market lookup exploded")
            return make_result([], fetched=list(markets or []))
        if "event_provider_anchors" in s:
            return make_result([])
        if s.startswith("select e.id, s.key"):
            return make_result(
                [], fetched=[(e.id, BOXING.key) for e in events]
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


async def _list_payload(rows, **db_kwargs):
    with (
        patch(_PATCHES[0], new=AsyncMock(return_value={})),
        patch(_PATCHES[1], new=AsyncMock(return_value={})),
        patch(_PATCHES[2], new=AsyncMock(return_value={})),
    ):
        return await list_events(
            sport=None,
            status=None,
            days=14,
            limit=200,
            offset=0,
            db=_mock_db(rows, **db_kwargs),
        )


async def _search_payload(rows, q="orobio", **db_kwargs):
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


def _rows(payload):
    """The two routes name their list differently — `events` vs `results`."""
    return payload["events"] if "events" in payload else payload["results"]


def _row(payload, event_id: int) -> dict:
    """The served row, or a failure naming what was served instead.

    RAISES rather than returning None, and that is the whole reason it exists.
    A route-level specimen can pass on an empty payload: `[r for r in rows if
    r["id"] == GHOST]` is an empty list on a route that served nothing, and every
    assertion written over it is then vacuously true. Asserting presence first is
    what makes the field assertions mean anything.
    """
    for row in _rows(payload):
        if row["id"] == event_id:
            return row
    raise AssertionError(
        f"event {event_id} was not served at all — the payload held "
        f"{[r['id'] for r in _rows(payload)]}. Nothing below this line can be "
        "true of a row that is absent."
    )


def _served_at(payload, event_id: int) -> datetime:
    raw = _row(payload, event_id)["commence_time"]
    parsed = datetime.fromisoformat(raw) if isinstance(raw, str) else raw
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _ghost_market():
    return [(GHOST, GHOST_TICKER, FABRICATED)]


# =============================================================================
# The specimen is defective before anything runs
# =============================================================================


def test_the_specimen_really_does_carry_the_defect_before_the_route_runs():
    """A fixture that never carried the defect passes a correction test by doing
    nothing at all. This pins the BEFORE so the ship tests below cannot be green
    on a healthy row: the stored hour is the fabricated one, it is EQUAL to the
    contract's expiration instant (which is the module's proof, not an
    inference), and the ticker names an earlier day.
    """
    ghost = _ghost()
    assert ghost.commence_time == FABRICATED
    assert ghost.commence_time_source == "kalshi"
    assert ghost.external_id is None
    # The equality that makes this provable rather than inferred (gotcha #14).
    (_event_id, _ticker, expiration), = _ghost_market()
    assert expiration == ghost.commence_time
    assert "26SEP03" in _ticker
    assert FABRICATED.date() > datetime(2026, 9, 3).date()


# =============================================================================
# The ship
# =============================================================================


@pytest.mark.asyncio
async def test_search_stops_dating_a_september_3_fight_september_17():
    """The card Alex would see. `q=Orobio` stops promising "Tomorrow"."""
    payload = await _search_payload([_ghost(), _twin()], markets=_ghost_market())

    assert _served_at(payload, GHOST) == CONTEST_DATE, (
        "search is still serving the contract's expiration instant as a "
        "kick-off — the top card still counts down to a fight already fought"
    )


@pytest.mark.asyncio
async def test_the_corrected_search_row_says_where_its_date_came_from():
    """A recovered value still wearing `kalshi` would be a value disagreeing with
    the column that names its writer. The pair — `kalshi_ticker` at midnight UTC
    — is what `event_twin_fold.is_kalshi_date_only` reads as "a DATE and no
    kick-off hour", which is exactly the claim this correction is entitled to.
    """
    payload = await _search_payload([_ghost(), _twin()], markets=_ghost_market())
    row = _row(payload, GHOST)

    source = row.get("commence_time_source") or getattr(
        row.get("metadata") or {}, "get", lambda _k: None
    )("commence_time_source")
    if source is not None:
        assert source == TICKER_CONTEST_DATE_SOURCE
    # The serializer need not expose the provenance; the instant it exposes must
    # still be the date-only one, which is the half a reader sees.
    assert _served_at(payload, GHOST).hour == 0
    assert _served_at(payload, GHOST).minute == 0


@pytest.mark.asyncio
async def test_the_events_list_stops_dating_the_september_3_fights_september_17():
    """`GET /api/events` — where all ten cohort rows were measured."""
    payload = await _list_payload([_ghost(), _ordinary()], markets=_ghost_market())

    assert _served_at(payload, GHOST) == CONTEST_DATE


# =============================================================================
# Nothing is withheld — the route already ruled this, against dropping
# =============================================================================


@pytest.mark.asyncio
async def test_search_answers_with_the_fight_rather_than_with_silence():
    """A reader who searches a fighter's name wants the fight, and this bout is
    real and was fought. Withholding it would answer the question with silence
    in order to avoid answering it wrongly — so both cards survive, and the
    correction's whole effect is on the date.
    """
    payload = await _search_payload([_ghost(), _twin()], markets=_ghost_market())

    served = {r["id"] for r in _rows(payload)}
    assert served == {GHOST, TWIN}, (
        f"search dropped a row it used to serve: {served}. The correction "
        "re-dates, it does not suppress."
    )


@pytest.mark.asyncio
async def test_the_events_list_serves_every_row_it_served_before():
    """`list_events` rules this question against dropping forty lines above the
    correction, in its own words: a `scheduled` row past its own kickoff "may yet
    be played, and suppressing it would empty the front door instead of cleaning
    it. Those rows stay, and #3016 stays open for them."

    I checked that predicate rather than assuming it — `not_a_blank_card`
    requires `status IN TERMINAL_STATUSES` and every cohort row is `scheduled`,
    so the route's existing suppression cannot reach them and a drop here would
    be a NEW policy against a decision this route already took.
    """
    rows = [_ghost(), _ordinary(), _ordinary(ORDINARY + 1)]
    payload = await _list_payload(rows, markets=_ghost_market())

    assert {r["id"] for r in _rows(payload)} == {e.id for e in rows}


# =============================================================================
# The neighbours
# =============================================================================


@pytest.mark.asyncio
async def test_the_honest_twin_beside_it_is_never_moved():
    """The second card in the screenshot. A schedule provider reported that start
    (`external_id` set), so it is not ours to move — and a correction that moved
    it would be re-dating the only honest row on the page.
    """
    payload = await _search_payload([_ghost(), _twin()], markets=_ghost_market())

    assert _served_at(payload, TWIN) == TWIN_TIME


@pytest.mark.asyncio
async def test_an_ordinary_fixture_is_never_moved():
    """A real September 19 fight on the same list stays on September 19."""
    ordinary = _ordinary()
    payload = await _list_payload([_ghost(), ordinary], markets=_ghost_market())

    assert _served_at(payload, ORDINARY) == ordinary.commence_time


@pytest.mark.asyncio
async def test_a_market_belonging_to_another_event_never_dates_this_one():
    """The correction keys the market rows back to their own event. A ticker
    hanging off a different fight must not re-date this one, which is the
    difference between a correction and a swap.
    """
    payload = await _search_payload(
        [_ghost(), _twin()],
        markets=[(TWIN, "KXBOXING-26AUG01SOMEONEELSE", TWIN_TIME)],
    )

    assert _served_at(payload, GHOST) == FABRICATED
    assert _served_at(payload, TWIN) == TWIN_TIME


# =============================================================================
# Cost and belt
# =============================================================================


@pytest.mark.asyncio
async def test_a_page_of_ordinary_fixtures_issues_no_correction_query():
    """Almost no row on almost any page is a candidate, and the cheap pure gate
    is what keeps the other pages free. A page whose rows are all schedule-timed
    must not spend a round trip discovering that.
    """
    seen: list[str] = []
    await _list_payload(
        [_ordinary(), _ordinary(ORDINARY + 1)], statements=seen
    )

    assert not [s for s in seen if _is_correction_query(s)], (
        "an ordinary page paid for the correction's market lookup"
    )


@pytest.mark.asyncio
async def test_a_correction_that_raises_serves_the_page_rather_than_an_error():
    """Gotcha #42 applied to a stage: the correction improves the page and is
    never a precondition for having one. A database that will not answer leaves
    every row exactly as stored — today's bug — rather than a 500.
    """
    payload = await _search_payload(
        [_ghost(), _twin()], correction_raises=True
    )

    assert {r["id"] for r in _rows(payload)} == {GHOST, TWIN}
    assert _served_at(payload, GHOST) == FABRICATED


# =============================================================================
# The wiring, which no behavioural test above can see
# =============================================================================


def test_both_list_rails_run_the_correction():
    """The failure this guards is a call site that was never added, which no test
    of the wired sites can see. `/api/feed` is deliberately NOT asserted: it was
    measured to carry 0 of the cohort, and a guard demanding a call site no
    reader needs is a guard that will one day be satisfied by adding cost.
    """
    import inspect

    for route in (search_events, list_events):
        body = inspect.getsource(route)
        assert "await recover_kalshi_expiration_starts(db, events)" in body, (
            f"{route.__name__} no longer corrects a Kalshi expiration start; "
            "it will serve a settlement backstop as a kick-off again"
        )


def test_the_correction_runs_before_the_fold_on_both_rails():
    """`fold_twin_events` keys on the commence MINUTE, so a fold computed on a
    fabricated minute can only mis-group. This is the ordering #5905 chose when
    it put the soccer pad at the fold's own top, and the reason the correction
    could not simply go there is that it needs a query and the fold is
    synchronous.
    """
    import inspect

    for route in (search_events, list_events):
        body = inspect.getsource(route)
        assert body.index("await recover_kalshi_expiration_starts(db, events)") < (
            body.index("fold_twin_events(events)")
        ), (
            f"in {route.__name__} the correction moved after the twin fold; the "
            "fold's minute key is now computed on a fabricated minute"
        )


def test_neither_wiring_logs_the_readers_own_words():
    """Notice 32: CodeQL grades changed code, and a user-provided value in a log
    entry is `py/log-injection` at medium severity. `q` and `sport` are both
    user-supplied on these two routes, and the first version of the sibling
    wiring in `league_futures.py` was caught by exactly this.

    Asserted as "the handler formats NOTHING", not as "the handler does not
    mention `q`". A substring test for a one-letter parameter name matches
    almost any English sentence and would pass whatever the handler did — the
    format placeholder is the thing that can actually carry a reader's words
    into a log line, so it is the thing to forbid.
    """
    import inspect

    for route in (search_events, list_events):
        body = inspect.getsource(route)
        start = body.index("await recover_kalshi_expiration_starts(db, events)")
        window = body[start : start + 900]
        assert "logger.exception(" in window, (
            f"{route.__name__}'s recovery no longer reports its own failure"
        )
        handler = window[window.index("logger.exception(") :]
        call = handler[: handler.index(")")]
        assert "%" not in call, (
            f"{route.__name__}'s recovery handler now formats a value into its "
            "log line; on this route the values in scope are user-supplied "
            "(py/log-injection, notice 32)"
        )
