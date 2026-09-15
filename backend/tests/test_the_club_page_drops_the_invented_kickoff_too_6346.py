"""Guard: the CLUB page drops the invented kickoff too (#6346, second reader).

#6346 took *"Liverpool — Manchester United · No result reported"* off
`/sport/soccer/epl`. MEASURED on production 2026-09-15 12:5xZ, with that fix
live (`fd5326559` an ancestor of the deployed sha):

    GET /api/leagues/soccer_epl   unreported_games: 0        <- fixed
    GET /api/teams/liverpool      15302967, 15302968 SERVED  <- same rows, same
                                                                words, still up

Two surfaces, one rail condition. `recent_or_unreported_condition` (the club
page) is `settled_rail_condition OR unreported_rail_condition` (the league
page's), so every row #6346 disqualifies is admitted here by construction — and
the gate lived in `league_futures.py` alone. That is the whole finding: not a
new defect, the un-fixed half of a shipped one, on the surface a reader reaches
by tapping the club whose fixture the card names.

WHAT EACH TEST HERE DEFENDS. The predicate itself belongs to
`test_an_invented_kickoff_is_not_a_late_match_6346.py` and is not re-asserted;
this file only pins the things that suite structurally cannot see:

* the ship — the container is off the club's recent rail (`TestTheClubPage`);
* that the rail survived the removal, and that a REAL unreported row still
  reaches the page — the #3211 population is what a careless widening costs;
* that the two readers of the condition are the two this fix covered, so a
  third surface cannot inherit the card in silence (`TestTheReaderCensus`).

Real engine, real `get_team`, the harness `test_team_page_league_family_5491.py`
established for this route and for its reason: the admission test is SQL, and a
mocked session would prove the formatter instead of the query.
"""

from __future__ import annotations

import asyncio
import pathlib
import re
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


from app.models.models import Base, Event, Sport, Team  # noqa: E402
from app.routes import teams as route  # noqa: E402

_BACKEND = pathlib.Path(__file__).resolve().parents[1]

S_EPL = 1305
LIVERPOOL_ID = 20001
LIVERPOOL = "Liverpool"
UNITED = "Manchester United"
EVERTON = "Everton"

#: The production rows, verbatim (`db-query`, 2026-09-15 12:1xZ). All five share
#: `2026-09-03 18:50:00.316804` to the microsecond — one poll pass stamped them —
#: and each `created_at` lands ~130s later.
CONTAINER_ID = 15302967
SECOND_CONTAINER_ID = 15302968
#: A real Liverpool fixture on the same rail: played, unreported, whole minute.
REAL_UNREPORTED_ID = 15298001


def _fresh(delta):
    """Clock-relative (gotcha #44): the rail is time-windowed, so a frozen
    stamp would drift out of the lookback with the calendar."""
    return datetime.now(timezone.utc) + delta


def _event(event_id, *, when, created, home, away, source, status="suspended"):
    return Event(
        id=event_id,
        sport_id=S_EPL,
        home_team_id=None,
        away_team_id=None,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        created_at=created,
        commence_time_source=source,
        status=status,
        home_score=None,
        away_score=None,
    )


def _container(event_id=CONTAINER_ID, away=UNITED):
    """`15302967` in shape: kickoff IS the write instant, to the microsecond."""
    when = _fresh(timedelta(days=-9)).replace(second=0, microsecond=316804)
    return _event(
        event_id,
        when=when,
        created=when + timedelta(seconds=130),
        home=LIVERPOOL,
        away=away,
        source="kalshi",
    )


def _a_real_unreported_match():
    """A match that WAS played and whose result never arrived.

    Whole minute, and written into the table the day before it — a fixture list
    read ahead of time, which is every real row on this rail.
    """
    when = _fresh(timedelta(days=-4)).replace(second=0, microsecond=0)
    return _event(
        REAL_UNREPORTED_ID,
        when=when,
        created=when - timedelta(days=1),
        home=LIVERPOOL,
        away="Burnley",
        source="kalshi",
    )


def _engine(*events):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_EPL, key="soccer_epl", name="EPL"))
        s.add(Team(id=LIVERPOOL_ID, sport_id=S_EPL, name=LIVERPOOL, slug="liverpool"))
        for e in events:
            s.add(e)
        s.commit()
    return eng


def _page(eng, slug="liverpool"):
    """`get_team` for real — its real `select()`s, its real predicate."""
    with Session(eng) as s:

        class _Session:
            async def execute(self, statement):
                return s.execute(statement)

        return asyncio.run(route.get_team(slug, db=_Session()))


def _ids(page):
    return [c["id"] for c in page["upcoming_events"] + page["recent_events"]]


class TestTheClubPage:
    def test_the_container_is_off_the_recent_rail(self):
        """🔴 THE SHIP. The card #6346 took off the league page leaves this one."""
        ids = _ids(_page(_engine(_container(), _a_real_unreported_match())))

        assert CONTAINER_ID not in ids, (
            "the season-matchup container still reaches the club page — this "
            f"is the production read of 2026-09-15 12:5xZ, got {ids}"
        )

    def test_the_real_unreported_match_survives(self):
        """THE NON-VACUITY HALF.

        Without it, a change that emptied every club's recent rail would pass
        the assertion above — and emptying the rail is exactly the regression
        #3211 exists to prevent, on a population (venue-minted, unanchored) that
        looks identical to the container at a glance.
        """
        ids = _ids(_page(_engine(_container(), _a_real_unreported_match())))

        assert REAL_UNREPORTED_ID in ids, (
            f"a real unreported match went with the container, got {ids}"
        )

    def test_both_containers_go_not_merely_the_first(self):
        """Production served two of them on this one page."""
        ids = _ids(
            _page(
                _engine(
                    _container(),
                    _container(SECOND_CONTAINER_ID, away=EVERTON),
                    _a_real_unreported_match(),
                )
            )
        )

        assert CONTAINER_ID not in ids and SECOND_CONTAINER_ID not in ids, (
            f"got {ids}"
        )

    def test_a_page_of_nothing_but_containers_does_not_error(self):
        """The empty rail is a legitimate outcome, not a 500."""
        page = _page(_engine(_container()))

        assert page["recent_events"] == []


class TestTheReaderCensus:
    """The two readers of the rail condition are the two this fix covered.

    A third surface spending `recent_or_unreported_condition` or
    `unreported_rail_condition` inherits the container silently, and nothing
    else in the tree would say so.
    """

    _CONDITIONS = ("recent_or_unreported_condition", "unreported_rail_condition")
    _EXPECTED_READERS = {"league_futures.py", "teams.py"}

    @staticmethod
    def _code(path):
        """The module with comment lines removed.

        🔴 NOT TIDINESS. A census that greps the raw file passes on a module
        whose gate has been deleted and whose explanatory comment — which names
        the helper — remains. Measured while writing this suite's first draft:
        removing the call outright left every assertion green.
        """
        return "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )

    def _readers(self):
        return {
            path.name
            for path in (_BACKEND / "app" / "routes").rglob("*.py")
            if any(
                re.search(rf"\b{cond}\s*\(", self._code(path))
                for cond in self._CONDITIONS
            )
        }

    def test_the_reader_set_has_not_grown(self):
        assert self._readers() == self._EXPECTED_READERS, (
            "a new surface spends the unreported rail's admission test — it "
            "inherits #6346's cards unless it calls the gate too"
        )

    def test_every_reader_calls_the_gate(self):
        for module in sorted(self._EXPECTED_READERS):
            code = self._code(_BACKEND / "app" / "routes" / module)
            assert re.search(r"\bcommence_time_was_never_a_kickoff\s*\(", code), (
                f"{module} admits the unreported population but never calls "
                "the gate — a mention in a comment is not a filter"
            )
