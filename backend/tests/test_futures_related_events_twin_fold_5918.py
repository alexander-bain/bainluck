"""#5918/#5905 — "Games This Week" stops printing one game twice, three hours apart.

WHAT A READER SAW, on 2026-09-14 00:2xZ, on `/futures/400` — **La Liga Winner** —
under the heading "Games This Week". Copied off the live
`GET /api/futures/400/related-events` payload, not reconstructed:

    15312069  Sevilla v Barcelona     19:00Z     "Sat 12:00 PM  Barcelona at Sevilla"
    15307701  Sevilla v Barcelona     22:00Z     "Sat  3:00 PM  Barcelona at Sevilla"
    15312070  Getafe v Málaga         12:00Z
    15307708  Getafe v Malaga         15:00Z
    15312067  Celta Vigo v Santander  16:30Z
    15307700  Celta Vigo v Santander  19:30Z

Three pairs, each the same fixture twice, each separated by EXACTLY three hours.

═══ WHY THE THREE HOURS ARE THE WHOLE STORY ═══

The second row of each pair is Kalshi-minted, and a Kalshi soccer row's
`commence_time` is that market's expected expiration, not kick-off (gotcha #14)
— `KALSHI_EXPECTED_EXPIRATION_PAD`, 180 minutes exactly, venue-read on 11 of 11
anchored comparisons.

So these are not near-miss twins that some tolerance has to be widened to catch.
They are the SAME MINUTE the moment the pad is subtracted, and they read as two
different games only because it never was. That is why
`recover_kalshi_occurrence_starts` runs at the TOP of `fold_twin_events`: the
correction is what makes the strict same-minute key able to see one fixture.

Every other list surface gets both from that one call — `/api/feed`,
`GET /api/events`, search, `/api/teams/{identifier}`, the three
`/api/leagues/{sport_key}` rails. This strip called neither, so it had neither:
the duplicate AND the three-hour-late clock, on a marquee fixture, on the page a
reader reaches from the La Liga hub.

═══ WHAT THE ARMS ARE ═══

  * **RED-FIRST, EXECUTED**: with the fold stubbed out, both rows come back.
    The "before" is run, not remembered.
  * **THE SHIP**: one card, and it is the row whose clock was already right.
  * **THE LOADER, off the statement the route actually built**: `Event.sport`
    must be eagerly loaded or `loaded_sport_key` answers `None`, the soccer pass
    skips every row on a soccer strip, and the fold reads as having run.
    CERT-2805 caught exactly this on the league rails; a mock session can never
    witness it, because the object the test built already carries its sport.
  * **NON-VACUITY** for that probe — a bare `select(Event)` must report nothing.
  * **THE CAP IS SPENT ON GAMES, NOT ON DROPPED ROWS**: the fold runs before the
    twenty-card cap, so a strip holding duplicates still serves twenty fixtures.
  * **THE CLOCK ITSELF**, independent of the fold: a Kalshi row with NO twin is
    not duplicated, it is simply advertised three hours late — 16 of the 29
    reader-visible rows are that shape and no fold could ever reach them.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Event, FuturesMarket, FuturesOutcome, Sport
from app.routes.futures import (
    RELATED_EVENTS_LIMIT,
    get_related_events,
)

LA_LIGA = Sport(id=7731, key="soccer_spain_la_liga", name="La Liga")

# Anchored to a fixed instant and offset FIRST, never truncated from "now"
# (gotcha #44): this file must not branch on the clock it runs at.
_BASE = datetime(2026, 9, 19, 19, 0, tzinfo=timezone.utc)

SEVILLA_ID = 2210
BARCELONA_ID = 2206


def _market(category: str | None = "soccer") -> FuturesMarket:
    market = FuturesMarket(
        id=400,
        source="kalshi",
        external_id="LALIGA-26",
        name="La Liga Winner",
        category="championship",
        llm_sport_category=category,
        status="open",
    )
    market.outcomes = [
        FuturesOutcome(
            id=1,
            market_id=400,
            name="Barcelona",
            team_id=BARCELONA_ID,
            current_probability=0.99,
            rank=1,
        ),
        FuturesOutcome(
            id=2,
            market_id=400,
            name="Sevilla",
            team_id=SEVILLA_ID,
            current_probability=0.01,
            rank=11,
        ),
    ]
    return market


def _event(
    event_id: int,
    commence: datetime,
    *,
    kalshi: bool,
    home: str = "Sevilla",
    away: str = "Barcelona",
) -> Event:
    """One row of the pair.

    `external_id` is the switch that decides whether the recovery may touch the
    row at all, and it is the honest one: a row a schedule provider reported is
    never moved. The Kalshi row carries none, which is the production shape —
    all 29 reader-visible rows do.
    """
    event = Event(
        id=event_id,
        sport_id=LA_LIGA.id,
        home_team_id=SEVILLA_ID,
        away_team_id=BARCELONA_ID,
        home_team_name=home,
        away_team_name=away,
        status="scheduled",
        commence_time=commence,
        external_id=None if kalshi else f"espn:{event_id}",
        commence_time_source="kalshi" if kalshi else "odds_api",
    )
    event.sport = LA_LIGA
    return event


def _the_production_pair() -> list[Event]:
    """The two rows a reader saw, in the order the database returned them.

    The uncorrected Kalshi row sorts LATER, because the column it is sorted on
    is the one that is wrong — which is also why the survivor below needs no
    re-sorting to land in the right slot.
    """
    return [
        _event(15312069, _BASE, kalshi=False),
        _event(15307701, _BASE + timedelta(hours=3), kalshi=True),
    ]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Answers the two statements the route builds, and keeps them.

    Deliberately does NOT filter: this fake cannot execute SQL, and every row it
    is given is one the real query would have returned (same sport, both teams
    linked to an outcome, both inside the week window). Keeping the statements
    is what lets the loader arm read the route's real `select`.

    🔴 IT DOES HONOUR `LIMIT`, and that is not decoration. A fake that returns
    every row it holds cannot tell a route that over-fetches from one that does
    not, so the "a duplicate does not cost the reader a card" arm below would
    pass against a route whose cap is applied by the database — the exact defect
    the headroom exists to prevent. Measured: with the limit ignored, deleting
    the headroom left that arm green and only the statement-reading arm caught
    it. A cap is a thing a database does; a fake standing in for one has to.
    """

    def __init__(self, market, events):
        self._market = market
        self._events = events
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _Result([self._market])
        limit = getattr(statement, "_limit", None)
        rows = self._events if limit is None else self._events[:limit]
        return _Result(rows)


def _eager_paths(statement):
    """The relationship names the loader options on `statement` will load.

    Reads `_with_options`, not the SQL text: `selectinload` emits a SECOND
    statement and leaves no trace in this one, so a text assertion would pass
    with the option deleted — worse than no guard at all.
    """
    names = set()
    for option in getattr(statement, "_with_options", ()) or ():
        for element in getattr(option, "path", ()) or ():
            key = getattr(element, "key", None)
            if isinstance(key, str):
                names.add(key)
    return names


# ── THE SHIP ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_marquee_fixture_appears_once():
    session = _FakeSession(_market(), _the_production_pair())

    payload = await get_related_events(400, db=session)

    served = [
        f"{e['home_team']} v {e['away_team']} @ {e['commence_time']}"
        for e in payload["events"]
    ]
    assert len(payload["events"]) == 1, (
        "Sevilla v Barcelona is on the La Liga Winner strip twice, three hours "
        f"apart: {served}"
    )
    # The survivor is the row whose clock was already right, in the slot the
    # database put it in — so nothing had to be re-sorted to make the strip read
    # chronologically.
    assert payload["events"][0]["event_id"] == 15312069
    assert payload["events"][0]["commence_time"] == _BASE.isoformat()
    assert payload["total_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label,survivor_id,dropped_id,home,away_reported,away_kalshi",
    [
        # Verbatim from the production payload. The three pairs are NOT the same
        # difficulty, and the easy one alone would have been a weak guard:
        ("identical names", 15312069, 15307701, "Sevilla", "Barcelona", "Barcelona"),
        ("accent only", 15312070, 15307708, "Getafe", "Málaga", "Malaga"),
        (
            "club name written out in full",
            15312067,
            15307700,
            "Celta Vigo",
            "Real Racing Club de Santander",
            "Santander",
        ),
    ],
)
async def test_each_pair_a_reader_actually_saw_collapses(
    label, survivor_id, dropped_id, home, away_reported, away_kalshi
):
    """THE THREE REAL PAIRS, with the names production actually carries.

    Written out rather than folded into the fixture because the name shapes are
    the risk: one pair differs only by an accent, and one has the same club as
    "Santander" on one row and "Real Racing Club de Santander" on the other. A
    guard built only on the identical-name pair would pass while the strip still
    printed two of the other two.

    The survivor is asserted BY ID in every case: it must be the provider-
    reported row, which is the one already sitting in its correct chronological
    slot — that is what lets this route fold without recomputing an order it has
    no business owning.
    """
    rows = [
        _event(survivor_id, _BASE, kalshi=False, home=home, away=away_reported),
        _event(
            dropped_id,
            _BASE + timedelta(hours=3),
            kalshi=True,
            home=home,
            away=away_kalshi,
        ),
    ]
    session = _FakeSession(_market(), rows)

    payload = await get_related_events(400, db=session)

    assert [e["event_id"] for e in payload["events"]] == [survivor_id], (
        f"the {label} pair is still two cards on the La Liga Winner strip"
    )
    assert payload["events"][0]["commence_time"] == _BASE.isoformat()


@pytest.mark.asyncio
async def test_without_the_fold_the_duplicate_returns(monkeypatch):
    """RED-FIRST, executed: remove the stage and the reader's defect reappears."""
    from app.routes import futures as futures_module

    monkeypatch.setattr(
        futures_module,
        "fold_twin_events",
        lambda events: (_ for _ in ()).throw(AssertionError("fold disabled")),
    )
    session = _FakeSession(_market(), _the_production_pair())

    payload = await get_related_events(400, db=session)

    assert [e["event_id"] for e in payload["events"]] == [15312069, 15307701], (
        "the red-first arm did not reproduce the duplicate, so the green arm "
        "above is not evidence of anything"
    )
    # And it reproduces the OTHER half at the same time: the surviving duplicate
    # is the three-hour-late clock, which is what made it look like a new game.
    assert payload["events"][1]["commence_time"] == (
        _BASE + timedelta(hours=3)
    ).isoformat()


@pytest.mark.asyncio
async def test_a_fold_that_raises_serves_todays_strip_not_a_500():
    """Gotcha #42 as a whole stage. The fold improves the strip; it is never a
    precondition for having one. A futures page with duplicates beats a 500."""
    from app.routes import futures as futures_module

    def _boom(events):
        raise RuntimeError("twin fold exploded")

    monkeypatch_target = futures_module.fold_twin_events
    futures_module.fold_twin_events = _boom
    try:
        session = _FakeSession(_market(), _the_production_pair())
        payload = await get_related_events(400, db=session)
    finally:
        futures_module.fold_twin_events = monkeypatch_target

    assert len(payload["events"]) == 2


# ── THE CLOCK, WITH NO TWIN TO FOLD ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_kalshi_row_with_no_twin_still_gets_its_real_kickoff():
    """16 of the 29 reader-visible rows have NO twin.

    Those are not duplicated — they are advertised three hours late, and no fold
    could ever reach them. The recovery is why this arm passes; a change that
    de-duplicated the strip without correcting the clock would fail here while
    the ship arm above still passed.
    """
    lone = _event(15307707, _BASE + timedelta(hours=3), kalshi=True,
                  home="Atletico", away="Real Madrid")
    session = _FakeSession(_market(), [lone])

    payload = await get_related_events(400, db=session)

    assert len(payload["events"]) == 1
    assert payload["events"][0]["commence_time"] == _BASE.isoformat(), (
        "the Madrid derby is still being advertised three hours late"
    )


@pytest.mark.asyncio
async def test_a_provider_reported_row_is_never_moved():
    """The recovery's own refusal, pinned on this surface.

    A row carrying an `external_id` was reported by a schedule provider, and its
    hour is not Kalshi's expected expiration. Widening the correction to reach
    those would move real kick-offs three hours early.
    """
    reported = _event(15312069, _BASE, kalshi=False)
    session = _FakeSession(_market(), [reported])

    payload = await get_related_events(400, db=session)

    assert payload["events"][0]["commence_time"] == _BASE.isoformat()


# ── REACH: THE LOADER IS WHAT MAKES THE SOCCER PASS ABLE TO FIRE ──────────────


@pytest.mark.asyncio
async def test_the_strip_eager_loads_the_sport():
    """CERT-2805's finding, guarded on this route before it can happen here.

    A join in the FROM clause does not populate the relationship. Without the
    loader, `loaded_sport_key` answers `None` for every hydrated row, the soccer
    pass skips all of them, and the fold above reads as having run while
    changing nothing on the page.
    """
    session = _FakeSession(_market(), _the_production_pair())

    await get_related_events(400, db=session)

    events_statement = session.statements[1]
    assert "sport" in _eager_paths(events_statement), (
        "the related-events strip does not eager-load Event.sport, so the "
        "#5918 soccer fold silently no-ops on every soccer futures page"
    )


def test_the_probe_can_tell_a_loaded_select_from_an_unloaded_one():
    """NON-VACUITY. A probe that found `sport` everywhere would pass above."""
    from sqlalchemy import select

    from app.models.models import Event as EventModel
    from app.models.models import Sport as SportModel

    unloaded = select(EventModel).join(SportModel, SportModel.id == EventModel.sport_id)
    assert _eager_paths(unloaded) == set(), (
        "a join is not a loader — if the probe reports `sport` here it is "
        "reading the FROM clause and would pass on the broken route"
    )


# ── THE CAP IS SPENT ON GAMES, NOT ON ROWS THE FOLD THEN DROPS ────────────────


@pytest.mark.asyncio
async def test_a_duplicate_does_not_cost_the_reader_a_card():
    """Folding after a DB limit of twenty would leave nineteen games.

    The query over-fetches and the cap is applied to the fold's OUTPUT. Safe
    here, and not in `list_events`, because this strip has no offset and no
    cursor: there is no page two for an over-fetch to re-serve.
    """
    rows = list(_the_production_pair())
    for n in range(RELATED_EVENTS_LIMIT):
        rows.append(
            _event(
                16000000 + n,
                _BASE + timedelta(days=1, minutes=n),
                kalshi=False,
                home=f"Home {n}",
                away=f"Away {n}",
            )
        )
    session = _FakeSession(_market(), rows)

    payload = await get_related_events(400, db=session)

    assert len(payload["events"]) == RELATED_EVENTS_LIMIT
    ids = [e["event_id"] for e in payload["events"]]
    assert 15307701 not in ids, "the dropped duplicate was served anyway"
    assert len(set(ids)) == RELATED_EVENTS_LIMIT


@pytest.mark.asyncio
async def test_the_query_asks_for_more_rows_than_the_cap():
    """The headroom is what the arm above spends. Read off the statement."""
    session = _FakeSession(_market(), _the_production_pair())

    await get_related_events(400, db=session)

    assert session.statements[1]._limit > RELATED_EVENTS_LIMIT, (
        "the strip fetches exactly its cap, so every folded duplicate is a card "
        "the reader loses"
    )


# ── THE NEIGHBOURING GUARD STILL HOLDS ────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_fold_did_not_relax_the_non_soccer_refusal():
    """#2553's clause and this one are independent.

    The fold must not become the reason a baseball market's strip starts showing
    soccer: `loaded_sport_key` still gates the soccer pass on the key, and the
    sport WHERE clause is untouched by this change.
    """
    from app.utils.kalshi_occurrence_start import kalshi_occurrence_scheduled_start

    kalshi_row = _event(15307701, _BASE + timedelta(hours=3), kalshi=True)

    assert kalshi_occurrence_scheduled_start(kalshi_row, "baseball_mlb") is None
    assert kalshi_occurrence_scheduled_start(kalshi_row, None) is None
    assert (
        kalshi_occurrence_scheduled_start(kalshi_row, "soccer_spain_la_liga")
        == _BASE
    )
