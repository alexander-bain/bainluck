"""#6739 — a league rail stops denying a result the venue already named.

## What a reader saw, photographed on production 2026-09-18 23:4xZ

`https://bainluck.com/sports/tennis_atp` at phone width, section **"Live &
Paused"**, the first two cards::

    No result reported · Sep 18        Sanchez Izquierdo / Kolar
    No result reported · Sep 18        Cervantes / Molchanov / Jecan / Pavel

One tap away, on each of those rows' own detail payload, the same second::

    GET /api/events/15314430  ->  venue_settled: true,
                                  venue_settled_result: "Sanchez Izquierdo wins"
    GET /api/events/15314463  ->  venue_settled: true,
                                  venue_settled_result: "Cervantes / Molchanov wins"

**The list route never asked the question the detail route already answers.**
One row, one second, two answers — and the answer the reader meets first is the
one that denies having a result.

## Reach, measured through the routes rather than the table

For eight leagues: the league payload's own `unreported_games` rail, then each
of those rows' own `/api/events/{id}`. 42 rail rows, 0 errors::

    tennis_atp                  6 rail rows   6 hold a venue winner
    tennis_wta                  6             5
    boxing_boxing               6             6
    soccer_other                6             0
    mma_mixed_martial_arts      6             0
    baseball_npb                6             0
    icehockey_liiga             6             0
    soccer_epl                  0             0
    ----------------------------------------------------------
    total                      42            17

The four leagues at 0 are the honest half of that table and are a control in
`TestTheSentenceAppearsOnlyWhereTheVenueGraded`: the sentence appears where the
venue graded and nowhere else.

## What this file guards

The producer half — the KEYS on the list payload, under the names
`/api/events/{id}` has served since #6381 (ruling 047: extend the shared card's
contract, never fork the card). Rendering them on the card is ux's under notice
41 and is the linked consumer issue.

Three things are load-bearing and each has its own class below:

1. **The briefs are matched to their rows by id, never by position.**
   `_format_all` drops a row it cannot format (gotcha #42), so the two lists are
   the same length only on a page where nothing went wrong — and that is exactly
   the page where a positional zip would print Schoolkate's result on Mikrut's
   card. A card that names the loser is worse than a card that names nobody.
2. **The gate is the detail route's gate, asked of the brief.** A rail may not
   publish a sentence the event's own page would refuse to publish.
3. **A failed read is a MISSING KEY, never a present `False`.** A card that said
   "No result reported" keeps saying it rather than being handed a confident
   "the venue graded nothing" that nothing established.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


# DDL shims so `create_all` can build the real schema on SQLite — the same pair
# `test_league_page_tag_fold_5853.py` declares, for the same reason: the rails'
# own SQL has Postgres arms, so the route has to be driven against a real engine
# rather than a mock.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.models import (  # noqa: E402
    Base,
    Event,
    FuturesMarket,
    FuturesOutcome,
    Sport,
)
from app.routes import league_futures as route  # noqa: E402
from app.utils.event_completion import started_without_result  # noqa: E402
from app.utils.venue_settlement_reader import (  # noqa: E402
    askable_briefs,
    venue_settlements_for_events,
)

#: The production rows, verbatim (`/api/leagues/tennis_atp`, 2026-09-18 23:4xZ).
SPORT_KEY = "tennis_atp"
S_ATP = 1701

SCHOOLKATE = 15314383  # "Bobichon vs Schoolkate", venue graded Tristan Schoolkate
MIKRUT = 15314392  # "Gentzsch vs Mikrut", venue graded Luka Mikrut
UNGRADED = 15314430  # a rail row the venue has not graded, for the 0-leagues arm

#: Our spelling is the surname; the venue's is the full name. That gap is the
#: whole reason `choose_settled_winner` uses the fuzzy primitive, and keeping
#: the production spellings here means this file would catch a regression to an
#: exact-match test (which refused the entire ITF population when it was tried).
OUR_HOME = "Bobichon"
OUR_AWAY = "Schoolkate"
VENUE_AWAY = "Tristan Schoolkate"

MONEYLINE = "Bobichon vs Schoolkate"
SET_ONE = "Set 1 Winner: Bobichon vs Schoolkate"


def _played(hours_ago=7):
    """Offset from the clock, never a literal stamp (gotcha #44)."""
    return datetime.now(timezone.utc) - timedelta(hours=hours_ago)


def _event(event_id, *, status="suspended", scores=(None, None), when=None, **kw):
    return Event(
        id=event_id,
        sport_id=S_ATP,
        home_team_name=kw.get("home", OUR_HOME),
        away_team_name=kw.get("away", OUR_AWAY),
        commence_time=when or _played(),
        completed_at=kw.get("completed_at"),
        status=status,
        home_score=scores[0],
        away_score=scores[1],
        event_tags=["provenance:unanchored"],
    )


def _graded(market_id, event_id, market_name, outcome_name, *, source="api_settlement"):
    return (
        FuturesMarket(
            id=market_id,
            event_id=event_id,
            source="polymarket",
            # A bare `0x…` condition id, which is the shape the recognizer's
            # ticker branch reads as "no ticker to argue with the title".
            external_id=f"0x{market_id:064x}",
            sport_id=S_ATP,
            name=market_name,
            status="closed",
        ),
        FuturesOutcome(
            id=market_id,
            market_id=market_id,
            external_id=f"{market_id}-win",
            name=outcome_name,
            is_winner=True,
            resolution_source=source,
        ),
    )


def _engine(*rows):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_ATP, key=SPORT_KEY, name="ATP"))
        for r in rows:
            s.add(r)
        s.commit()
    return eng


class _Session:
    """A real engine behind the async surface `build_league` calls."""

    def __init__(self, session):
        self._s = session

    async def execute(self, statement, *args, **kwargs):
        return self._s.execute(statement)


def _rail_cards(*rows) -> dict:
    """Every game card the league page serves, by id, through the real route."""
    eng = _engine(*rows)
    with Session(eng) as s:
        payload = asyncio.run(route.build_league(SPORT_KEY, _Session(s)))
    cards = {}
    for rail in ("upcoming_games", "recent_results", "unreported_games"):
        for card in payload.get(rail) or []:
            cards[card["id"]] = card
    return cards


# ---------------------------------------------------------------------------
# the ship
# ---------------------------------------------------------------------------


class TestTheCardOnTheLeaguePage:
    """🔴 THE SHIP, through `build_league` itself rather than through a helper."""

    def test_the_rail_card_names_the_winner_the_venue_named(self):
        """The photographed card stops saying only "No result reported".

        Stated as the production sentence rather than as a truthy check: the
        value is the same string `/api/events/15314383` already serves, because
        the whole defect was two surfaces disagreeing about one row.
        """
        market, outcome = _graded(1, SCHOOLKATE, MONEYLINE, VENUE_AWAY)
        card = _rail_cards(_event(SCHOOLKATE), market, outcome)[SCHOOLKATE]

        assert card["venue_settled"] is True
        assert card["venue_settled_result"] == "Schoolkate wins"

    def test_without_a_graded_market_the_card_is_exactly_what_it_was(self):
        """The control that makes the assertion above non-vacuous.

        Same row, same rail, same route — only the venue's grade removed. The
        card must carry the pair of keys saying nothing was graded, and no
        sentence. If this ever asserts a `venue_settled_result`, the ship above
        is being proved by something other than the grade.
        """
        card = _rail_cards(_event(SCHOOLKATE))[SCHOOLKATE]

        assert card["venue_settled"] is False
        assert card["venue_settled_result"] is None


class TestTheSentenceAppearsOnlyWhereTheVenueGraded:
    """The four leagues at 0 in the reach table, as behaviour.

    17 of 42 measured rail rows hold a winner. A change that put a sentence on
    the other 25 would read as a bigger win and be a fabrication.
    """

    def test_a_row_the_venue_has_not_graded_gets_no_sentence(self):
        market, outcome = _graded(1, SCHOOLKATE, MONEYLINE, VENUE_AWAY)
        cards = _rail_cards(
            _event(SCHOOLKATE), _event(UNGRADED, home="Sanchez Izquierdo", away="Kolar"),
            market, outcome,
        )

        assert cards[SCHOOLKATE]["venue_settled_result"] == "Schoolkate wins"
        assert cards[UNGRADED]["venue_settled_result"] is None

    def test_a_grade_from_a_weaker_source_is_not_the_venues_word(self):
        """`api_settlement` only — the rung where the house that took the bets
        said so. An inferred or computed grade is not a warrant for overriding
        a page that currently says it has no result."""
        market, outcome = _graded(
            1, SCHOOLKATE, MONEYLINE, VENUE_AWAY, source="game_score"
        )
        card = _rail_cards(_event(SCHOOLKATE), market, outcome)[SCHOOLKATE]

        assert card["venue_settled"] is False
        assert card["venue_settled_result"] is None

    def test_a_set_winner_is_not_a_match_winner_on_a_rail_either(self):
        """The refusal inherited from `choose_settled_winner`, re-asked HERE.

        150 `Set 1 Winner` grades sit in the measured population. The card is
        settled and names nobody — never "the player who won set 1 won".
        """
        market, outcome = _graded(1, SCHOOLKATE, SET_ONE, VENUE_AWAY)
        card = _rail_cards(_event(SCHOOLKATE), market, outcome)[SCHOOLKATE]

        assert card["venue_settled"] is True
        assert card["venue_settled_result"] is None


class TestTheGateIsTheDetailRoutesGate:
    """A rail may not publish a sentence the event's own page would refuse."""

    def test_a_row_holding_our_own_score_is_refused(self):
        """Our result outranks the venue's grade, and publishing both invites a
        page to choose between them."""
        market, outcome = _graded(1, SCHOOLKATE, MONEYLINE, VENUE_AWAY)
        card = _rail_cards(
            _event(SCHOOLKATE, status="completed", scores=(0, 2)), market, outcome
        )[SCHOOLKATE]

        assert "venue_settled_result" not in card

    def test_a_scheduled_row_past_its_own_kickoff_is_admitted(self):
        """#3211's class — a `scheduled` row hours past its start prints the
        same "No result reported" sentence, which is why the gate consults
        `started_without_result` rather than only the status.

        🔴 NOT DRIVEN THROUGH THE SQLITE ROUTE, AND THE REASON IS THE FINDING.
        SQLite stores no timezone, so a row read back through `_rail_cards`
        carries a NAIVE `commence_time`; `started_without_result` compares it
        against a tz-aware `now`, catches the `TypeError` and FAILS CLOSED
        (#6057, by design). Every row on that harness therefore answers False
        to this arm no matter what the clock says — the arm would be green
        against an implementation that never consulted the predicate at all.
        Production reads `timestamptz`, so the specimen here is the aware one.
        """
        admitted = askable_briefs(
            [{"id": SCHOOLKATE, "status": "scheduled", "home_score": None,
              "away_score": None}],
            {SCHOOLKATE: started_without_result(
                "scheduled", _played(), datetime.now(timezone.utc)
            )},
        )

        assert [b["id"] for b in admitted] == [SCHOOLKATE]

    def test_the_scheduled_arm_is_the_predicate_and_not_a_copy_of_it(self):
        """The input the test above supplies is the house predicate's own
        answer, so a rewrite of that predicate moves this gate with it."""
        assert started_without_result(
            "scheduled", _played(), datetime.now(timezone.utc)
        ) is True
        assert started_without_result(
            "scheduled", _played(hours_ago=-6), datetime.now(timezone.utc)
        ) is False

    def test_a_fixture_still_ahead_of_its_kickoff_is_refused(self):
        market, outcome = _graded(1, SCHOOLKATE, MONEYLINE, VENUE_AWAY)
        card = _rail_cards(
            _event(SCHOOLKATE, status="scheduled", when=_played(hours_ago=-6)),
            market,
            outcome,
        )[SCHOOLKATE]

        assert "venue_settled_result" not in card

    def test_no_askable_row_issues_no_query_at_all(self):
        """The ordinary page pays nothing.

        Asserted on the DB, not on the output: a version that queried first and
        filtered afterwards would produce the same payload and a statement per
        league page view.
        """
        db = MagicMock()
        db.execute = AsyncMock()
        briefs = [{"id": SCHOOLKATE, "status": "completed", "home_score": 2,
                   "away_score": 0}]

        asyncio.run(
            route._attach_venue_settlement(
                db,
                [SimpleNamespace(id=SCHOOLKATE, home_team_name=OUR_HOME,
                                 away_team_name=OUR_AWAY, status="completed",
                                 commence_time=_played())],
                briefs,
                datetime.now(timezone.utc),
            )
        )

        db.execute.assert_not_called()

    def test_an_unbacked_live_row_is_not_admitted_from_a_list(self):
        """The narrower scope, stated as a test so it cannot widen by accident.

        The detail route's third arm reads a pinned-price flatness analysis the
        list payload does not perform. A rail row claiming `live` keeps today's
        card rather than getting that arm's answer from a weaker input.
        """
        admitted = askable_briefs(
            [{"id": SCHOOLKATE, "status": "live", "home_score": None,
              "away_score": None}],
            {SCHOOLKATE: False},
        )

        assert admitted == []


class TestTheBriefsAreMatchedByIdNeverByPosition:
    """🔴 THE ONE THAT PRINTS THE LOSER'S NAME WHEN IT IS WRONG.

    `_format_all` drops a row it cannot format (gotcha #42), so briefs and rows
    line up only on a page where nothing went wrong. A positional
    implementation passes every test written on a healthy page and mislabels
    cards on exactly the page that already had a problem.

    🔴 WHICH LOOKUP THIS ACTUALLY GUARDS, MEASURED RATHER THAN CLAIMED. Two
    lookups in `_attach_venue_settlement` are id-keyed and only ONE of them can
    be gotten wrong:

    * **brief -> its Event row** (`by_id[int(brief["id"])]`), which supplies the
      team names the winner sentence is spelled from. Replaced with positional
      indexing, `test_a_dropped_brief_does_not_shift_its_neighbours_result`
      turns red and the surviving card reads "Schoolkate wins" for Mikrut's
      match. This is the guard.
    * **brief -> its settlement** (`settlements.get(...)`). Replaced with
      `zip`, the whole suite stays GREEN — because the reader is handed exactly
      the candidate events, in candidate order, so the two sequences are
      aligned by construction and no input can separate them. The id key stays
      (it costs nothing and states the intent), but it is recorded here as an
      unkillable mutant rather than left looking like something a test proves.
    """

    def test_a_dropped_brief_does_not_shift_its_neighbours_result(self):
        schoolkate_m, schoolkate_o = _graded(1, SCHOOLKATE, MONEYLINE, VENUE_AWAY)
        mikrut_m, mikrut_o = _graded(
            2, MIKRUT, "Gentzsch vs Mikrut", "Luka Mikrut"
        )
        rows = [
            SimpleNamespace(id=SCHOOLKATE, home_team_name=OUR_HOME,
                            away_team_name=OUR_AWAY, status="suspended",
                            commence_time=_played()),
            SimpleNamespace(id=MIKRUT, home_team_name="Gentzsch",
                            away_team_name="Mikrut", status="suspended",
                            commence_time=_played()),
        ]
        # The first row's card never made it out of the formatter, so the ONLY
        # brief is the second row's. A zip would hand it the first row's result.
        briefs = [{"id": MIKRUT, "status": "suspended", "home_score": None,
                   "away_score": None}]

        eng = _engine(
            _event(SCHOOLKATE),
            _event(MIKRUT, home="Gentzsch", away="Mikrut"),
            schoolkate_m, schoolkate_o, mikrut_m, mikrut_o,
        )
        with Session(eng) as s:
            asyncio.run(
                route._attach_venue_settlement(
                    _Session(s), rows, briefs, datetime.now(timezone.utc)
                )
            )

        assert briefs[0]["venue_settled_result"] == "Mikrut wins"

    def test_two_rails_of_cards_each_keep_their_own_result(self):
        schoolkate_m, schoolkate_o = _graded(1, SCHOOLKATE, MONEYLINE, VENUE_AWAY)
        mikrut_m, mikrut_o = _graded(
            2, MIKRUT, "Gentzsch vs Mikrut", "Luka Mikrut"
        )
        cards = _rail_cards(
            _event(SCHOOLKATE),
            _event(MIKRUT, home="Gentzsch", away="Mikrut", when=_played(hours_ago=9)),
            schoolkate_m, schoolkate_o, mikrut_m, mikrut_o,
        )

        assert cards[SCHOOLKATE]["venue_settled_result"] == "Schoolkate wins"
        assert cards[MIKRUT]["venue_settled_result"] == "Mikrut wins"


class TestAFailedReadIsAMissingKey:
    """Never a present `False`: the card keeps whatever it said before."""

    def test_a_raising_read_leaves_every_brief_untouched(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("connection reset"))
        briefs = [{"id": SCHOOLKATE, "status": "suspended", "home_score": None,
                   "away_score": None}]

        asyncio.run(
            route._attach_venue_settlement(
                db,
                [SimpleNamespace(id=SCHOOLKATE, home_team_name=OUR_HOME,
                                 away_team_name=OUR_AWAY, status="suspended",
                                 commence_time=_played())],
                briefs,
                datetime.now(timezone.utc),
            )
        )

        assert "venue_settled" not in briefs[0]
        assert "venue_settled_result" not in briefs[0]

    def test_the_reader_returns_an_empty_map_rather_than_a_false_for_each_row(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("connection reset"))

        assert (
            asyncio.run(
                venue_settlements_for_events(
                    db,
                    [SimpleNamespace(id=SCHOOLKATE, home_team_name=OUR_HOME,
                                     away_team_name=OUR_AWAY)],
                )
            )
            == {}
        )


class TestTheScoreIsAskedBeforeTheWinner:
    """🔴 THE ORDER ITSELF, WHICH NOTHING IN THIS REPO ASSERTED UNTIL NOW.

    Found by mutation while building this ship: swapping the two calls in
    `settlement_from_graded_rows` left 116 tests green. Every existing specimen
    is order-BLIND — each one grades a score market or a moneyline, never both —
    so the rule the docstrings of #6381 and #6739 both spend a paragraph on was
    enforced by nobody. It was inline in `events.py` when that was true, so this
    is a pre-existing gap this extraction inherited, not one it opened.

    A row carrying BOTH is the only specimen that can see it, and it is a real
    shape: 11 of the 305 side-graded `suspended` rows measured 2026-09-17 carry
    a score-shaped market as well.
    """

    def test_a_row_graded_on_both_prints_the_richer_score_sentence(self):
        from app.utils.venue_settlement import settlement_from_graded_rows

        graded = [
            ("Exact Match Score", None, "Aryna Sabalenka wins 2-0"),
            ("Sabalenka vs Gauff", None, "Aryna Sabalenka"),
        ]

        assert settlement_from_graded_rows(graded, "Sabalenka", "Gauff") == {
            "venue_settled": True,
            "venue_settled_result": "Aryna Sabalenka wins 2-0",
        }

    def test_the_winner_sentence_is_the_same_statement_with_the_score_dropped(self):
        """Why the order is a preference for the RICHER of two true sentences
        and not a choice between two claims: with the score market removed, the
        same rows say the same thing, less."""
        from app.utils.venue_settlement import settlement_from_graded_rows

        assert settlement_from_graded_rows(
            [("Sabalenka vs Gauff", None, "Aryna Sabalenka")], "Sabalenka", "Gauff"
        )["venue_settled_result"] == "Sabalenka wins"


class TestTheOrderLivesInOnePlace:
    """#1951: the policy is score-first-then-winner, and it has two readers now."""

    def test_neither_reader_retypes_the_order(self):
        """A source scan, widened to BOTH paths rather than pointed at one.

        A ban passes for free against a file holding none of the code it bans,
        so a ban that names only the new module would silently retire itself the
        day someone re-inlines the order in the old one.
        """
        import inspect

        from app.routes import events as events_route
        from app.utils import venue_settlement, venue_settlement_reader

        for module in (events_route, venue_settlement_reader):
            source = inspect.getsource(module)
            assert "choose_settled_score(" not in source, (
                f"{module.__name__} re-types the score-then-winner order; it "
                "belongs to venue_settlement.settlement_from_graded_rows"
            )
            assert "choose_settled_winner(" not in source, (
                f"{module.__name__} re-types the score-then-winner order; it "
                "belongs to venue_settlement.settlement_from_graded_rows"
            )

        # And the positive half: the one place that DOES hold it still does.
        held = inspect.getsource(venue_settlement.settlement_from_graded_rows)
        assert "choose_settled_score(" in held
        assert "choose_settled_winner(" in held

    def test_both_readers_share_the_positive_grades_only_filter(self):
        import inspect

        from app.routes import events as events_route

        assert "venue_grade_filters()" in inspect.getsource(events_route)


class TestTheMeasurementIsOnTheRecord:
    """The reach table, so a later reader can check the claim rather than trust it."""

    def test_the_reach_table_adds_up(self):
        per_league = {
            "tennis_atp": (6, 6),
            "tennis_wta": (6, 5),
            "boxing_boxing": (6, 6),
            "soccer_other": (6, 0),
            "mma_mixed_martial_arts": (6, 0),
            "baseball_npb": (6, 0),
            "icehockey_liiga": (6, 0),
            "soccer_epl": (0, 0),
        }

        assert sum(rail for rail, _ in per_league.values()) == 42
        assert sum(held for _, held in per_league.values()) == 17
        assert all(held <= rail for rail, held in per_league.values())
