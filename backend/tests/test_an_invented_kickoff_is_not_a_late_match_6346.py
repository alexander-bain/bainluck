"""Guard: the EPL page stops reporting no result for a match nobody played (#6346).

THE CARD THIS EXISTS FOR. `/sport/soccer/epl` at 390px, 2026-09-15 09:5xZ, four
cards under **NO RESULT REPORTED**, club crests, no date, no score:

    NO RESULT REPORTED
      Liverpool — Manchester United      <- no such fixture has been played
      Arsenal — Tottenham
      Liverpool — Everton
      Chelsea — Tottenham

🔴 AND FOUR OF THE FIVE ARE NOT FIXTURES AT ALL. Read back at the venue, the
markets these rows were minted from are season-long head-to-head futures:

    15302967  KXEPLH2HFINISH-EPL27LFCMUN  "Liverpool vs Manchester United:
                                           Who Will Finish Higher"     duel
    15302970  KXEPLH2H-27ARSTOT           "Arsenal vs Tottenham:
                                           Season Matchup Result"      duel

"Who Will Finish Higher" is a question about final league-table position over
the whole 2026-27 season. **It has no kick-off because there is no game.** The
fabricated timestamp is the symptom, not the disease.

WHY THE ROW CAN NEVER LEAVE THE RAIL ON ITS OWN. `prediction_market_matching`
line 6801 stamps `commence_time = now` when the market carries no usable time,
so the row is **past its own kick-off forever** — it satisfies "started and
nobody reported an ending" permanently, and more strongly every day. All five
EPL rows share `18:50:00.316804` **to the microsecond**: one poll pass stamped
them all.

WHAT EACH TEST HERE IS DEFENDING. Not "a function returns a bool":

* the ship — the four cards are off the EPL rail
  (`TestTheEplRail`);
* the two populations a careless fix destroys — #3211's US Open rows (this
  rail's whole reason to exist, and themselves venue-minted) and every real
  fixture merely DISCOVERED near its own start
  (`TestWhatMustSurvive`);
* that each arm alone is too broad, which is why the predicate is a conjunction
  and not either half (`TestNeitherArmAloneWouldDo`);
* the tz trap that makes the predicate raise rather than answer wrongly
  (`TestTheTimezoneTrap`);
* the belt — a raising gate serves the rail unfiltered (`TestTheBelt`).

THE NUMBERS THESE CASES ENCODE, measured on production 2026-09-15 over the rows
satisfying this rail's admission test:

    commence_time_source = 'kalshi'                  610   <- 166 real ATP rows
    a sub-minute commence_time alone                 204
    born within ten minutes of its own created_at     13
    both of the last two (this predicate)              6   <- 0 false positives
"""

from __future__ import annotations

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


from app.models.models import Base, Event, Sport  # noqa: E402
from app.routes import league_futures as route  # noqa: E402
from app.utils.event_rails import (  # noqa: E402
    commence_time_was_never_a_kickoff,
)

S_EPL = 1305
SPORT_KEY = "soccer_epl"

#: The five production rows, verbatim (`db-query`, 2026-09-15 10:2xZ). Their
#: `commence_time` agrees to the microsecond and sits ~130s BEFORE `created_at`.
THE_FIVE = (
    (15302966, "Newcastle United", "Sunderland"),
    (15302967, "Liverpool", "Manchester United"),
    (15302968, "Liverpool", "Everton"),
    (15302969, "Chelsea", "Tottenham"),
    (15302970, "Arsenal", "Tottenham"),
)


def _ago(hours: float) -> datetime:
    """Gotcha #44: offset from the clock, never a literal stamp."""
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _poll_clock_row(event_id: int, home: str, away: str, *, days: float = 11.6) -> Event:
    """A row whose `commence_time` is the pass clock, written ~130s later.

    `created_at` is deliberately built NAIVE, as the column is
    (`DateTime`, no timezone), while `commence_time` is aware. The production
    rows are exactly this pair, and a predicate that subtracts them without
    normalising raises instead of answering.
    """
    commence = _ago(days * 24).replace(second=0, microsecond=316804)
    return Event(
        id=event_id,
        sport_id=S_EPL,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        commence_time_source="kalshi",
        status="suspended",
        home_score=None,
        away_score=None,
        completed_at=None,
        win_probability_sources={},
        event_tags=["provenance:source:kalshi", "provenance:unanchored"],
        created_at=(commence + timedelta(seconds=130)).replace(tzinfo=None),
    )


def _us_open_row(event_id: int = 15200001) -> Event:
    """#3211's population: ticker-derived midnight, and this rail exists FOR it.

    Venue-minted and `provenance:unanchored`, exactly like the ghosts — which is
    why neither of those can be the discriminator.
    """
    commence = _ago(30).replace(hour=0, minute=0, second=0, microsecond=0)
    return Event(
        id=event_id,
        sport_id=S_EPL,
        home_team_name="Sabalenka",
        away_team_name="Pegula",
        commence_time=commence,
        commence_time_source="kalshi_ticker",
        status="scheduled",
        win_probability_sources={},
        event_tags=["provenance:source:kalshi", "provenance:unanchored"],
        created_at=(commence - timedelta(days=3)).replace(tzinfo=None),
    )


def _discovered_at_kickoff(event_id: int = 15200002) -> Event:
    """A REAL game we happened to discover minutes before it started.

    The positive control for arm 2. Production holds seven of these (MiLB,
    esports, tennis) at 23:05:00, 20:08:00, 19:15:00 and 06:30:00 — clean minute
    boundaries, created within ten minutes of them. Keyed on "born at its own
    kick-off" alone they would all vanish.
    """
    commence = _ago(40).replace(second=0, microsecond=0)
    return Event(
        id=event_id,
        sport_id=S_EPL,
        home_team_name="Columbus Clippers",
        away_team_name="Iowa Cubs",
        commence_time=commence,
        commence_time_source="kalshi",
        status="suspended",
        win_probability_sources={},
        created_at=(commence - timedelta(seconds=127)).replace(tzinfo=None),
    )


def _ordinary_kalshi_fixture(event_id: int = 15200003) -> Event:
    """A real fixture Kalshi timed, scheduled days ahead. The 610-row majority."""
    commence = _ago(50).replace(minute=30, second=0, microsecond=0)
    return Event(
        id=event_id,
        sport_id=S_EPL,
        home_team_name="Cordoba",
        away_team_name="Almeria",
        commence_time=commence,
        commence_time_source="kalshi",
        status="suspended",
        win_probability_sources={},
        created_at=(commence - timedelta(days=4)).replace(tzinfo=None),
    )


# ---------------------------------------------------------------------------
# the predicate
# ---------------------------------------------------------------------------


class TestThePredicate:
    def test_the_liverpool_manchester_united_row_is_named(self):
        row = _poll_clock_row(*THE_FIVE[1])
        assert commence_time_was_never_a_kickoff(row) is True

    def test_all_five_are_named(self):
        rows = [_poll_clock_row(i, h, a) for i, h, a in THE_FIVE]
        assert all(commence_time_was_never_a_kickoff(r) for r in rows)


class TestWhatMustSurvive:
    def test_the_us_open_population_is_untouched(self):
        """#3211 built this rail for 171 of these. Emptying it is the old bug."""
        assert commence_time_was_never_a_kickoff(_us_open_row()) is False

    def test_a_real_game_discovered_at_its_own_kickoff_survives(self):
        assert commence_time_was_never_a_kickoff(_discovered_at_kickoff()) is False

    def test_an_ordinary_kalshi_timed_fixture_survives(self):
        assert commence_time_was_never_a_kickoff(_ordinary_kalshi_fixture()) is False

    def test_a_row_that_cannot_answer_is_left_alone(self):
        """Fails in the recoverable direction: serve the card, never hide a match."""
        row = _poll_clock_row(*THE_FIVE[0])
        row.created_at = None
        assert commence_time_was_never_a_kickoff(row) is False


class TestNeitherArmAloneWouldDo:
    def test_the_source_alone_is_not_the_discriminator(self):
        """610 rail rows are bare `kalshi`; 166 of them are real ATP fixtures."""
        ordinary = _ordinary_kalshi_fixture()
        assert ordinary.commence_time_source == "kalshi"
        assert commence_time_was_never_a_kickoff(ordinary) is False

    def test_sub_minute_alone_is_not_the_discriminator(self):
        """A sub-minute stamp on a row created days earlier is a real time."""
        row = _ordinary_kalshi_fixture()
        row.commence_time = row.commence_time.replace(second=44)
        assert commence_time_was_never_a_kickoff(row) is False

    def test_born_at_its_own_kickoff_alone_is_not_the_discriminator(self):
        assert commence_time_was_never_a_kickoff(_discovered_at_kickoff()) is False

    def test_unanchored_provenance_is_not_the_discriminator(self):
        """All 17 rail rows across the five soccer leagues carry this tag."""
        survivor = _us_open_row()
        assert "provenance:unanchored" in survivor.event_tags
        assert commence_time_was_never_a_kickoff(survivor) is False


class TestTheTimezoneTrap:
    def test_a_naive_created_at_does_not_raise(self):
        """`commence_time` is tz-aware, `created_at` is not. Subtracting raises."""
        row = _poll_clock_row(*THE_FIVE[1])
        assert row.created_at.tzinfo is None
        assert row.commence_time.tzinfo is not None
        assert commence_time_was_never_a_kickoff(row) is True

    def test_an_aware_created_at_answers_the_same(self):
        row = _poll_clock_row(*THE_FIVE[1])
        row.created_at = row.created_at.replace(tzinfo=timezone.utc)
        assert commence_time_was_never_a_kickoff(row) is True


# ---------------------------------------------------------------------------
# the rail
# ---------------------------------------------------------------------------


def _engine(*rows):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_EPL, key=SPORT_KEY, name="Premier League", group="Soccer"))
        for r in rows:
            s.add(r)
        s.commit()
    return eng


class _Session:
    """A real engine behind the async surface `build_league` calls.

    Forwards bind parameters — see the note in
    `test_a_market_born_ghost_is_off_the_league_rails_6345.py`.
    """

    def __init__(self, session):
        self._s = session

    async def execute(self, statement, *args, **kwargs):
        return self._s.execute(statement, *args, **kwargs)


def _unreported_rail(*rows) -> dict:
    eng = _engine(*rows)
    with Session(eng) as s:
        payload = asyncio.run(route.build_league(SPORT_KEY, _Session(s)))
    return {card["id"]: card for card in payload["unreported_games"]}


class TestTheEplRail:
    def test_the_four_marquee_cards_are_gone(self):
        rail = _unreported_rail(*[_poll_clock_row(i, h, a) for i, h, a in THE_FIVE])
        assert rail == {}

    def test_a_real_row_beside_them_keeps_its_card(self):
        """The rail is filtered, not emptied — the half a blanket fix gets wrong."""
        real = _ordinary_kalshi_fixture()
        # Read the id BEFORE the fixture session commits and expires it — the
        # row is detached by the time the route has run.
        real_id = real.id
        rail = _unreported_rail(
            *[_poll_clock_row(i, h, a) for i, h, a in THE_FIVE], real
        )
        assert sorted(rail) == [real_id]


class TestTheBelt:
    def test_a_raising_gate_serves_the_rail_unfiltered(self, monkeypatch):
        """Gotcha #42: a gate that raises costs the filter, never the page."""

        def _boom(_e):
            raise RuntimeError("gate down")

        monkeypatch.setattr(route, "commence_time_was_never_a_kickoff", _boom)
        rail = _unreported_rail(_poll_clock_row(*THE_FIVE[1]))
        assert THE_FIVE[1][0] in rail
