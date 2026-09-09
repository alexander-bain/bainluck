"""Guard: `GET /api/events` serves one row per fixture (#4100, list half).

`tests/test_event_twin_fold.py` proves the decision and
`tests/test_feed_twin_fold_route_4100.py` proves the feed's delivery. This file
proves the LIST route's delivery, which shipped separately and was still serving
both twins after the feed stopped: measured on production 2026-09-09 04:33Z,
`?sport=baseball_mlb&limit=60` answered with 18 duplicated fixtures in a 60-row
page — including `15300848`/`15307210`, the Cardinals pair the feed had just
folded away.

🔴 REAL `Event` OBJECTS, NOT MagicMock, AND THESE TESTS ARE WORTHLESS WITHOUT
THEM. The union is delivered with `sqlalchemy.orm.attributes.set_committed_value`,
which reaches through `_sa_instance_state`. On a MagicMock that call chain is
absorbed into auto-attributes: it raises nothing, does nothing, and
`test_survivor_carries_the_dropped_rows_venue` would pass on a fold that merged
nothing. Detached declarative instances are the cheapest thing that exercises it.

The venue lists below are the real ones those two production rows carried, and
they are DISJOINT — `{kalshi, mlb}` against `{betting, espn, mlb, stat_model}`.
That is why the union is load-bearing rather than cosmetic: whichever row wins
the election, a reader who is served only that row loses either Kalshi's price
or the sportsbook price. Picking a survivor is half the fix; carrying the other
row's venues across is the other half.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import Event, Sport
from app.routes.events import list_events

MLB = Sport(id=1, key="baseball_mlb", name="MLB", group="Baseball", active=True)

# The two production rows, by id, with the venues each actually carried.
STATPAL_VENUES = {"kalshi": 0.38, "mlb": 0.38}
ODDS_API_VENUES = {
    "betting": 0.24,
    "espn": 0.26,
    "mlb": 0.25,
    "stat_model": 0.25,
}

COMMENCE = datetime(2026, 9, 9, 1, 45, tzinfo=timezone.utc)


def _event(
    id,
    *,
    away="St. Louis Cardinals",
    home="San Francisco Giants",
    commence=COMMENCE,
    espn_id=None,
    home_score=None,
    away_score=None,
    sources=None,
):
    e = Event(
        id=id,
        sport_id=MLB.id,
        away_team_name=away,
        home_team_name=home,
        commence_time=commence,
        status="scheduled",
        home_score=home_score,
        away_score=away_score,
        espn_id=espn_id,
        win_probability_sources=sources,
    )
    e.sport = MLB
    return e


def _twin_pair():
    """The Cardinals pair as production held it — two spellings, one fixture.

    `St. Louis` against `St.Louis` is the real difference between the two rows
    and is exactly what a normaliser that only strips a period before a SPACE
    leaves standing, so the pair also guards the squash.
    """
    return [
        _event(15300848, away="St. Louis Cardinals", sources=dict(STATPAL_VENUES)),
        _event(
            15307210,
            away="St.Louis Cardinals",
            espn_id="401858999",
            sources=dict(ODDS_API_VENUES),
        ),
    ]


def _mock_db(events):
    db = AsyncMock()

    def make_result(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.fetchall.return_value = []
        r.all.return_value = []
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        # Only the page query returns rows; odds snapshots and the time-series
        # probe return nothing, which is the shape of an unenriched page.
        if "odds_snapshots" in s or "win_prob_snapshots" in s:
            return make_result([])
        if "from events" in s:
            return make_result(events)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _payload(rows, **kwargs):
    with (
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch(
            "app.routes.events.folded_probability_sources_batch",
            new=AsyncMock(return_value={}),
        ),
    ):
        # Called directly, so FastAPI's `Query(...)` defaults are never
        # resolved — every parameter is passed explicitly or the route receives
        # `Query` objects where it expects ints.
        params = {"status": None, "days": 7, "limit": 200, "offset": 0}
        params.update(kwargs)
        return await list_events(sport="baseball_mlb", db=_mock_db(rows), **params)


@pytest.mark.asyncio
async def test_twin_rows_are_served_as_one_row():
    """The headline: two rows for one game come back as one."""
    payload = await _payload(_twin_pair())

    assert len(payload["events"]) == 1, (
        "both Cardinals rows were served — this is the production bug, "
        f"got ids {[e['id'] for e in payload['events']]}"
    )


@pytest.mark.asyncio
async def test_count_reports_what_was_actually_served():
    """`count` is the honest length of the list, never the pre-fold number.

    The route folds AFTER the DB `limit` deliberately, so `count` shrinking is
    the contract, not a defect — but it must shrink WITH the list. A `count` of
    2 over a one-row list would tell a client to expect a row that is not there.
    """
    payload = await _payload(_twin_pair())

    assert payload["count"] == len(payload["events"]) == 1


@pytest.mark.asyncio
async def test_survivor_carries_the_dropped_rows_venue():
    """The union reaches the SERVED payload, not just the helper's return value.

    The two rows' venues are disjoint, so a survivor that carries only its own
    is a reader losing a real price. Kalshi lives only on the statpal row;
    betting and espn live only on the odds_api row. One card, every venue.
    """
    payload = await _payload(_twin_pair())

    served = payload["events"][0]["win_probability_sources"] or {}

    assert "kalshi" in served, (
        "the survivor lost Kalshi's price — the union did not reach the payload "
        f"(served venues: {sorted(served)})"
    )
    for venue in ("betting", "espn", "stat_model"):
        assert venue in served, f"the survivor lost {venue} (served: {sorted(served)})"


@pytest.mark.asyncio
async def test_the_union_is_additive_and_never_overwrites_the_survivor():
    """A venue the survivor already reports keeps the survivor's own reading.

    Draining the other way would let a stale duplicate overwrite a live price.
    Both rows carry `mlb`; the survivor's value is the one that must survive.
    """
    payload = await _payload(_twin_pair())

    # Precondition, asserted rather than assumed: without it this test passes
    # vacuously on an unfolded page, where `events[0]` is simply the statpal row
    # reporting its own reading and nothing was ever merged.
    assert len(payload["events"]) == 1, "nothing was folded, so nothing was merged"

    served = payload["events"][0]["win_probability_sources"] or {}
    survivor_id = payload["events"][0]["id"]
    own = ODDS_API_VENUES if survivor_id == 15307210 else STATPAL_VENUES

    # The route serializes each venue into a display dict
    # (`{"value": …, "display_name": …}`) rather than a bare float, so the
    # reading is read through that shape rather than compared to it.
    reading = served["mlb"]
    value = reading.get("value") if isinstance(reading, dict) else reading

    assert value == own["mlb"], (
        f"the dropped row's `mlb` reading overwrote the survivor's own "
        f"(served {value}, survivor {survivor_id} holds {own['mlb']})"
    )


@pytest.mark.asyncio
async def test_two_different_fixtures_are_never_folded():
    """The false-positive direction: same teams, different games, both served.

    A doubleheader is the case that matters — same teams, same day, different
    start. The key carries the commence MINUTE precisely so this stays two rows.
    """
    rows = [
        _event(1, sources=dict(STATPAL_VENUES)),
        _event(2, commence=COMMENCE + timedelta(hours=3), sources=dict(STATPAL_VENUES)),
    ]

    payload = await _payload(rows)

    assert len(payload["events"]) == 2, "a doubleheader was collapsed into one game"
    assert payload["count"] == 2


@pytest.mark.asyncio
async def test_a_raising_fold_serves_the_unfolded_page():
    """Gotcha #42 over a whole stage: the fold improves the page, it is never a
    precondition for having one. If it raises, the reader gets today's bug — two
    cards — rather than an error or an empty list."""
    with patch(
        "app.routes.events.fold_twin_events", side_effect=RuntimeError("boom")
    ):
        payload = await _payload(_twin_pair())

    assert len(payload["events"]) == 2
    assert payload["count"] == 2
