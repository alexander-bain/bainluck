"""#2553: the MLB World Series page stops serving MLS soccer under "Games This Week".

WHAT A READER SAW, on 2026-09-01, on `/futures/1` — **MLB World Series Winner** —
in the middle of the MLB season, under a heading that says "Games This Week":

    D.C. United        at  FC Cincinnati        Cincinnati  0%
    CF Montreal        at  Philadelphia Union   Union       5%
    San Diego FC       at  Orlando City SC      FC          2%
    Sporting Kansas City at FC Dallas           City        0%
    Minnesota United FC at Portland Timbers     FC          0%

Five fixtures, five MLS soccer matches, zero baseball games. Copied off the live
`GET /api/futures/1/related-events` payload, not reconstructed.

═══ WHERE IT COMES FROM, AND WHY THE FIX IS NOT A DATA PATCH ═══

The route joins events to the market by `futures_outcomes.team_id`, and the link
table is what is wrong. Measured against production the same afternoon:

    outcome "Philadelphia Phillies" -> team 32   Philadelphia Union  soccer_usa_mls
    outcome "Cincinnati Reds"       -> FC Cincinnati                 soccer_usa_mls
    outcome "San Diego Padres"      -> San Diego FC                  soccer_usa_mls

A city name matched across sports when those outcomes were linked. 2,762
outcomes site-wide carry a team in a different sport from their market. That
corruption belongs to the matching layer, it is filed on its own, and nothing
here touches a row of it.

What IS this route's business is that a baseball market's related-games strip
must not be able to render a soccer fixture no matter what a team link claims.
That is a missing WHERE clause, and the guard below is written against the
clause rather than against the five rows — a strip that is correct only while
the data happens to be correct is the bug, not the fix.

═══ WHAT THE ARMS ARE ═══

  * **RED-FIRST**: with the sport predicate removed, the MLS fixture comes back.
    Asserted by running the route with the predicate builder stubbed to return
    nothing, so the "before" state is executed and not remembered.
  * **CONTROL**: a real baseball fixture on the same market, in the same run,
    survives. Without it this file would pass just as well against a route that
    returned an empty strip for everything.
  * **FAIL-OPEN**: a market with no `llm_sport_category` still gets its games.
    The remedy for a cross-sport bug must not be an empty section on every
    market whose category was never classified.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Event, FuturesMarket, FuturesOutcome, Sport, Team
from app.routes.futures import get_related_events


# ── The fixture set: one MLB market, one real MLB game, one MLS impostor ──────
#
# Team ids are the join key and the whole point: BOTH outcomes below carry a
# team id, one of them pointing at a soccer club, exactly as production does.

MLB_SPORT = Sport(id=53232, key="baseball_mlb", name="MLB")
MLS_SPORT = Sport(id=9001, key="soccer_usa_mls", name="MLS")

_SOON = datetime.now(timezone.utc) + timedelta(days=2)

DODGERS = Team(id=861, sport_id=MLB_SPORT.id, name="Los Angeles Dodgers")
PHILLIES_MISLINKED = Team(id=32, sport_id=MLS_SPORT.id, name="Philadelphia Union")


def _market() -> FuturesMarket:
    market = FuturesMarket(
        id=1,
        source="kalshi",
        external_id="WORLDSERIES-26",
        name="MLB World Series Winner",
        category="championship",
        llm_sport_category="baseball",
        status="open",
    )
    market.outcomes = [
        FuturesOutcome(
            id=10,
            market_id=1,
            name="Los Angeles Dodgers",
            team_id=DODGERS.id,
            current_probability=0.30,
            rank=1,
        ),
        # The corrupt link, verbatim in shape: a baseball outcome name carrying
        # a soccer club's team id.
        FuturesOutcome(
            id=11,
            market_id=1,
            name="Philadelphia Phillies",
            team_id=PHILLIES_MISLINKED.id,
            current_probability=0.054774,
            rank=7,
        ),
    ]
    return market


def _events() -> list[Event]:
    """What the UNFILTERED query returns — the impostor first, as production did."""
    soccer = Event(
        id=15291062,
        sport_id=MLS_SPORT.id,
        home_team_id=PHILLIES_MISLINKED.id,
        away_team_id=None,
        home_team_name="Philadelphia Union",
        away_team_name="CF Montreal",
        status="scheduled",
        commence_time=_SOON,
    )
    soccer.sport = MLS_SPORT
    baseball = Event(
        id=15400001,
        sport_id=MLB_SPORT.id,
        home_team_id=DODGERS.id,
        away_team_id=None,
        home_team_name="Los Angeles Dodgers",
        away_team_name="San Francisco Giants",
        status="scheduled",
        commence_time=_SOON,
    )
    baseball.sport = MLB_SPORT
    return [soccer, baseball]


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
    """Records the statements the route builds, and answers them.

    The event answer is deliberately the FULL unfiltered set: this fake cannot
    execute SQL, so the sport predicate is applied here, in Python, from the
    compiled clause the route actually produced. If the route stops emitting the
    predicate, nothing filters and the impostor comes back — which is exactly
    what the red-first arm needs to be able to happen.
    """

    def __init__(self, market, events):
        self._market = market
        self._events = events
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _Result([self._market])
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        return _Result([e for e in self._events if _passes(sql, e)])


def _passes(sql: str, event: Event) -> bool:
    """Does this compiled SELECT admit this event's sport?

    Reads the emitted SQL rather than re-deriving the rule, so a route that
    builds the predicate and forgets to pass it to `.where()` fails here — the
    sibling-call-site hole a `getsource` check would leave open.
    """
    if "sports.key" not in sql:
        return True  # no sport predicate at all: the pre-fix behaviour
    key = event.sport.key
    prefix = key.split("_")[0]
    return f"'{prefix}'" in sql or f"'{prefix}_" in sql


@pytest.mark.asyncio
async def test_mlb_world_series_strip_holds_no_soccer():
    session = _FakeSession(_market(), _events())

    payload = await get_related_events(1, db=session)

    sports = {e["sport"] for e in payload["events"]}
    assert "soccer_usa_mls" not in sports, (
        "the MLB World Series page served an MLS fixture again: "
        f"{[e['home_team'] + ' v ' + e['away_team'] for e in payload['events']]}"
    )
    # CONTROL, in the same run: the real baseball game is still there. A route
    # that returned nothing would satisfy the assertion above.
    assert [e["event_id"] for e in payload["events"]] == [15400001]
    assert sports == {"baseball_mlb"}


@pytest.mark.asyncio
async def test_without_the_sport_predicate_the_soccer_fixture_returns(monkeypatch):
    """RED-FIRST, executed: strip the clause and the defect reappears."""
    import app.routes.futures as futures_module

    monkeypatch.setitem(
        futures_module.LLM_CATEGORY_TO_SPORT_PREFIX, "baseball", None
    )
    session = _FakeSession(_market(), _events())

    payload = await get_related_events(1, db=session)

    assert "soccer_usa_mls" in {e["sport"] for e in payload["events"]}, (
        "the red-first arm did not reproduce the defect, so the green arm is "
        "not evidence of anything"
    )


@pytest.mark.asyncio
async def test_market_with_no_category_still_gets_its_games():
    """FAIL OPEN. An unclassified market is not evidence of a wrong sport."""
    market = _market()
    market.llm_sport_category = None
    session = _FakeSession(market, _events())

    payload = await get_related_events(1, db=session)

    assert len(payload["events"]) == 2


@pytest.mark.asyncio
async def test_the_predicate_admits_every_key_under_its_prefix():
    """`baseball_mlb_preseason` is baseball.

    An `Event.sport_id == market.sport_id` equality would have looked like the
    obvious fix and would have dropped this event: production carries MLB teams
    under `baseball_mlb_preseason` as well as `baseball_mlb`, and the World
    Series market's own outcomes are linked to teams in the preseason sport row.
    """
    preseason = Sport(id=9002, key="baseball_mlb_preseason", name="MLB")
    event = Event(
        id=15400002,
        sport_id=preseason.id,
        home_team_id=DODGERS.id,
        away_team_id=None,
        home_team_name="Los Angeles Dodgers",
        away_team_name="Arizona Diamondbacks",
        status="scheduled",
        commence_time=_SOON,
    )
    event.sport = preseason
    session = _FakeSession(_market(), [event])

    payload = await get_related_events(1, db=session)

    assert [e["event_id"] for e in payload["events"]] == [15400002]


def test_every_llm_category_maps_to_a_wellformed_sport_key_prefix():
    """The map this guard leans on has to be usable as a key PREFIX.

    The predicate is `key == prefix OR key LIKE prefix||'_%'`, so a prefix that
    already contains an underscore would match nothing and silently empty the
    strip for that entire sport — the failure mode worth a test, because it
    looks exactly like "no games this week".

    Note `olympics` maps to itself and has no entry in the reverse map, so a
    round-trip assertion is NOT the property here: `sport_keys.py` does not
    promise the two dicts are inverses, and this route does not need them to be.
    """
    from app.utils.sport_keys import LLM_CATEGORY_TO_SPORT_PREFIX

    for category, prefix in LLM_CATEGORY_TO_SPORT_PREFIX.items():
        assert prefix, f"{category} maps to an empty prefix"
        assert "_" not in prefix, (
            f"{category} -> {prefix!r} contains an underscore; "
            "the LIKE prefix would match no sport key"
        )
        assert prefix == prefix.lower(), f"{category} -> {prefix!r} is not lowercase"
