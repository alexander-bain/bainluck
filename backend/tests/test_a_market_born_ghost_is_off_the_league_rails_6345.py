"""Guard: the league list stops advertising a row its own detail route folds (#6345).

THE CARD THIS EXISTS FOR. `/sport/soccer/laliga`, under **NO RESULT REPORTED**:
*"Celta Fortuna v Eibar"* — event `15308951`, `suspended`, no score. Tapping it
lands the reader on a **different event id**, `15306978` ("Celta Fortuna v SD
Eibar", Segunda, completed 0–4), because `GET /api/events/15308951` has folded
it since Q050.

So the list advertised a card the detail endpoint already knew was not a
fixture, and after #5982's repair it was the only card that section had left.

THIS IS #6231 ON AN UNCOVERED SIBLING SURFACE, NOT A NEW CLASS.
`market_born_duplicates_on_page` is the SET form, built for list rails in
#6231, and `search_events` and the events list have both called it since
2026-09-02. `routes/league_futures.py` — which serves `unreported_games` —
neither imported nor called it.

🔴 THE SIBLING FOLD CANNOT REACH THIS, AND NO WIDENING OF ITS KEY WOULD.
`fold_twin_events` is a pure IN-PAGE fold: it needs both rows in the same result
set, and the canonical here is a *Segunda* fixture that the LaLiga rails never
select. The two rows also agree on neither name (`Eibar` / `SD Eibar`), league,
nor minute (21:30Z is Kalshi's expected expiration, 18:30Z the kick-off). The
Q050 verdict has no such limit: it is id-keyed and asks the database.

WHAT EACH TEST HERE IS DEFENDING. Not "a route returns a list":

* the ship — the ghost is off the league's unreported rail
  (`test_the_celta_fortuna_ghost_is_off_the_unreported_rail`);
* the thing a careless fix breaks — the real unreported rows beside it keep
  their cards, and the CANONICAL row keeps its result card. A suppression keyed
  on the wrong side of the pair empties the fixture instead of de-duplicating it
  (`test_the_real_unreported_rows_survive`,
  `test_the_canonical_result_card_survives`);
* the cost — a page whose rows a real schedule timed must not pay a verdict
  query none of them can pass (`test_an_ordinary_page_issues_no_verdict_query`);
* the belt — a verdict that raises serves the unsuppressed page, never a 500
  (`test_a_failing_verdict_serves_the_rail_rather_than_an_error`);
* the neighbour — #6346's invented-kick-off gate runs BEFORE the fold and this
  one AFTER it, so a request holding both kinds of bad row must lose both
  (`test_both_stages_fire_in_one_request`).

REAL ROWS IN A REAL ENGINE, and the verdict SQL itself runs. The rig is the one
`test_an_invented_kickoff_is_not_a_late_match_6346.py` uses for the same route:
a sqlite engine behind the async surface `build_league` calls. The whole point
of this ship is DELIVERY — that the league rails call the verdict, act on it and
report honestly — and a mocked verdict cannot show that the stage is wired to
the rows the route actually holds. The verdict's own seven refusals are pinned
in `test_market_born_duplicate_reads_as_canonical_q050.py`.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import (  # noqa: E402
    Base,
    Event,
    EventProviderAnchor,
    FuturesMarket,
    Sport,
)
from app.routes import league_futures as route  # noqa: E402
from app.utils.provider_anchor_keys import ANCHOR_KIND_MARKET  # noqa: E402

S_LA_LIGA = 1317
S_SEGUNDA = 1318
SPORT_KEY = "soccer_spain_la_liga"

GHOST = 15308951
CANONICAL = 15306978
#: The venue's own id for the market that minted the ghost.
TICKER = "KXLALIGAGAME-26SEP14CELEIB"


def _ago(hours: float) -> datetime:
    """Gotcha #44: offset from the clock, never a literal stamp."""
    return datetime.now(timezone.utc) - timedelta(hours=hours)


#: The kick-off, and Kalshi's expected expiration exactly three hours later.
#: Gotcha #14, and the reason these two rows never shared a fold key.
KICKOFF = _ago(20).replace(minute=30, second=0, microsecond=0)
EXPIRATION = KICKOFF + timedelta(hours=3)


def _ghost() -> Event:
    """The card the reader tapped: market-born, scoreless, and not a fixture."""
    return Event(
        id=GHOST,
        sport_id=S_LA_LIGA,
        home_team_name="Celta Fortuna",
        away_team_name="Eibar",
        commence_time=EXPIRATION,
        commence_time_source="kalshi",
        status="suspended",
        home_score=None,
        away_score=None,
        completed_at=None,
        win_probability_sources={},
        created_at=(KICKOFF - timedelta(days=2)).replace(tzinfo=None),
    )


def _canonical() -> Event:
    """The match that was played, 0–4, in the league it belongs to."""
    return Event(
        id=CANONICAL,
        sport_id=S_SEGUNDA,
        home_team_name="Celta Fortuna",
        away_team_name="SD Eibar",
        commence_time=KICKOFF,
        commence_time_source="odds_api",
        external_id="247343bc379dfe120732d07d0106e412",
        status="completed",
        home_score=0,
        away_score=4,
        completed_at=KICKOFF + timedelta(hours=1, minutes=57),
        win_probability_sources={"betting": 0.31},
        created_at=(KICKOFF - timedelta(days=6)).replace(tzinfo=None),
    )


def _anchor() -> EventProviderAnchor:
    """`kalshi` calls the GHOST `TICKER`, and that id is of kind `market`.

    A correspondence record, not a merge instruction — `id_kind` is the whole
    reason this row cannot absorb anything on its own.
    """
    return EventProviderAnchor(
        # Explicit: the column is a `BigInteger` primary key, which sqlite does
        # not autoincrement, and an omitted id fails the NOT NULL rather than
        # being filled in.
        id=880001,
        event_id=GHOST,
        source="kalshi",
        source_id=TICKER,
        id_kind=ANCHOR_KIND_MARKET,
    )


def _market_on_the_canonical() -> FuturesMarket:
    """The market the anchor names, linked to the REAL match.

    This is the whole verdict: the id the ghost was minted from now resolves to
    a different event, so the ghost is what is left over.
    """
    return FuturesMarket(
        id=990001,
        source="kalshi",
        external_id=TICKER,
        event_id=CANONICAL,
        name="Celta Fortuna vs SD Eibar Winner",
        market_type="game_winner",
        status="settled",
    )


def _real_unreported(event_id: int, home: str, away: str, *, hours: float) -> Event:
    """A LaLiga2 fixture that kicked off and whose score never arrived.

    #5982's population: real matches, and the reason this rail exists. They are
    `kalshi`-timed too, so the cheap candidate gate admits them and the VERDICT
    is what has to tell them apart — which is the discrimination worth testing.
    """
    commence = _ago(hours).replace(minute=0, second=0, microsecond=0)
    return Event(
        id=event_id,
        sport_id=S_LA_LIGA,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        commence_time_source="kalshi",
        status="suspended",
        home_score=None,
        away_score=None,
        completed_at=None,
        win_probability_sources={},
        created_at=(commence - timedelta(days=3)).replace(tzinfo=None),
    )


def _schedule_timed_fixture(event_id: int = 15399001) -> Event:
    """A row a real schedule timed — excluded by the pure gate, so it is free."""
    commence = _ago(9).replace(minute=0, second=0, microsecond=0)
    return Event(
        id=event_id,
        sport_id=S_LA_LIGA,
        home_team_name="Real Zaragoza",
        away_team_name="Albacete",
        commence_time=commence,
        commence_time_source="odds_api",
        status="suspended",
        win_probability_sources={},
        created_at=(commence - timedelta(days=3)).replace(tzinfo=None),
    )


def _poll_clock_row(event_id: int = 15302967) -> Event:
    """#6346's row: a `commence_time` that is the clock we read it at.

    Its gate runs BEFORE the fold and this file's stage runs AFTER it, so a page
    holding one of each is the only case that can show both are still wired.
    """
    commence = _ago(11.6 * 24).replace(second=0, microsecond=316804)
    return Event(
        id=event_id,
        sport_id=S_LA_LIGA,
        home_team_name="Liverpool",
        away_team_name="Manchester United",
        commence_time=commence,
        commence_time_source="kalshi",
        status="suspended",
        win_probability_sources={},
        created_at=(commence + timedelta(seconds=130)).replace(tzinfo=None),
    )


# ---------------------------------------------------------------------------
# the rig
# ---------------------------------------------------------------------------


def _engine(*rows):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(
            Sport(id=S_LA_LIGA, key=SPORT_KEY, name="La Liga", group="Soccer")
        )
        s.add(
            Sport(
                id=S_SEGUNDA,
                key="soccer_spain_segunda_division",
                name="Segunda División",
                group="Soccer",
            )
        )
        for r in rows:
            s.add(r)
        s.commit()
    return eng


class _Session:
    """A real engine behind the async surface `build_league` calls.

    Forwards bind parameters, which the verdict needs: its `IN :event_ids` is an
    expanding bindparam, so a wrapper that dropped `*args` would turn the
    statement into a syntax error and the stage would look like a clean refusal.
    """

    def __init__(self, session, seen=None):
        self._s = session
        self.seen = seen if seen is not None else []

    async def execute(self, statement, *args, **kwargs):
        self.seen.append(str(statement).lower())
        return self._s.execute(statement, *args, **kwargs)


class _RaisingOnVerdict(_Session):
    """Everything works except the one statement this ship depends on."""

    async def execute(self, statement, *args, **kwargs):
        if "event_provider_anchors" in str(statement).lower():
            raise RuntimeError("verdict query exploded")
        return await super().execute(statement, *args, **kwargs)


def _payload(*rows, session_cls=_Session, seen=None) -> dict:
    eng = _engine(*rows)
    with Session(eng) as s:
        return asyncio.run(route.build_league(SPORT_KEY, session_cls(s, seen)))


def _rail_ids(payload, key="unreported_games") -> list[int]:
    return sorted(card["id"] for card in payload[key])


def _the_pair() -> tuple:
    return (_ghost(), _canonical(), _anchor(), _market_on_the_canonical())


# =============================================================================
# the ship
# =============================================================================


def test_the_celta_fortuna_ghost_is_off_the_unreported_rail():
    """The card #6345 was filed for. 15308951 stops printing."""
    payload = _payload(*_the_pair())
    assert GHOST not in _rail_ids(payload)


def test_the_ghost_is_gone_because_of_the_verdict_and_not_by_accident():
    """Same page, no anchor and no market: the row prints.

    Without this, a rail that dropped the row for any other reason — a status
    filter, a window, a cap — would pass the test above and the stage could be
    inert.
    """
    payload = _payload(_ghost(), _canonical())
    assert GHOST in _rail_ids(payload)


# =============================================================================
# what a careless fix breaks
# =============================================================================


def test_the_real_unreported_rows_survive():
    """The rail is filtered, not emptied — #5982's population keeps its cards."""
    real = [
        _real_unreported(15308585, "Tenerife", "Leganes", hours=40),
        _real_unreported(15308732, "Valladolid", "Oviedo", hours=45),
        _real_unreported(15307859, "Cordoba", "Almeria", hours=64),
    ]
    # Read the ids BEFORE the fixture session commits and expires them — the
    # rows are detached by the time the route has run.
    expected = sorted(e.id for e in real)
    payload = _payload(*_the_pair(), *real)
    assert _rail_ids(payload) == expected


def test_the_canonical_result_card_survives():
    """Keyed on the wrong side of the pair, a suppression empties the fixture.

    The canonical is a Segunda row, so it is not on this league's rails at all —
    the assertion that matters is that nothing the stage does can reach it, and
    the LaLiga page still holds exactly the rows it should.
    """
    payload = _payload(*_the_pair(), _schedule_timed_fixture())
    assert CANONICAL not in _rail_ids(payload)
    assert CANONICAL not in _rail_ids(payload, "recent_results")
    assert _rail_ids(payload) == [15399001]


def test_a_schedule_timed_row_is_never_a_candidate():
    """Refusal 1 at the rail: `odds_api` provenance is not market-born."""
    payload = _payload(_schedule_timed_fixture())
    assert _rail_ids(payload) == [15399001]


# =============================================================================
# the cost
# =============================================================================


def test_an_ordinary_page_issues_no_verdict_query():
    """A page of schedule-timed rows pays nothing for a verdict none can pass.

    The pure gate is the reason the set form exists rather than the routes
    calling the resolver per row: no candidate, no statement.
    """
    seen: list[str] = []
    _payload(_schedule_timed_fixture(), seen=seen)
    assert not [s for s in seen if "event_provider_anchors" in s]


def test_a_page_with_a_candidate_does_ask():
    """The other direction, so the case above cannot pass by the stage being dead."""
    seen: list[str] = []
    _payload(*_the_pair(), seen=seen)
    assert [s for s in seen if "event_provider_anchors" in s]


# =============================================================================
# the belt
# =============================================================================


def test_a_failing_verdict_serves_the_rail_rather_than_an_error():
    """Gotcha #42: a stage that raises costs the suppression, never the page."""
    payload = _payload(*_the_pair(), session_cls=_RaisingOnVerdict)
    assert GHOST in _rail_ids(payload)


# =============================================================================
# the neighbour
# =============================================================================


def test_both_stages_fire_in_one_request():
    """#6346's gate runs before the fold, this one after it. Both must bite.

    One ordering serves each stage and they are not the same ordering, so a
    future edit that moves either of them to "where the other one is" has to
    redden something.
    """
    payload = _payload(*_the_pair(), _poll_clock_row(), _schedule_timed_fixture())
    assert _rail_ids(payload) == [15399001]


# =============================================================================
# the sibling rails
#
# The defect was filed on `unreported_games`, but a ghost is not a property of a
# rail — it is a property of a row, and the same row moves between rails as its
# status changes. A stage wired to one list would pin one component and leave
# its siblings holding the bug. So all three rails are handed to one verdict
# call, and the two cases below are what makes that claim falsifiable rather
# than a comment: asserting the ghost's absence from `upcoming_games` while it
# is a SUSPENDED row proves nothing, because it was never on that rail.
# =============================================================================


def test_a_ghost_on_the_upcoming_rail_is_suppressed_too():
    """The same row, `scheduled` with a future kick-off, is on the other rail."""
    commence = datetime.now(timezone.utc) + timedelta(days=2)
    ghost = _ghost()
    ghost.status = "scheduled"
    ghost.commence_time = commence
    payload = _payload(ghost, _canonical(), _anchor(), _market_on_the_canonical())
    assert GHOST not in _rail_ids(payload, "upcoming_games")


def test_a_row_carrying_its_own_result_is_never_drained():
    """Why the results rail needs no protection: a scored row is refused.

    This one survives REMOVING the stage — it is a must-survive case, and the
    mutation that reddens it is the opposite one: a widening that let a row with
    truth of its own be suppressed would delete a real result from the page.
    """
    played = _real_unreported(15307866, "Granada", "Albacete", hours=30)
    played.status = "completed"
    played.home_score = 2
    played.away_score = 1
    played.completed_at = played.commence_time + timedelta(hours=2)
    anchor = _anchor()
    anchor.id = 880002
    anchor.event_id = played.id
    played_id = played.id  # read before the fixture session expires the row
    payload = _payload(played, _canonical(), anchor, _market_on_the_canonical())
    assert played_id in _rail_ids(payload, "recent_results")
