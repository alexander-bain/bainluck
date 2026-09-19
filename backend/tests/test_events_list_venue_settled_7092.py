"""#7092 — the events LIST stops denying a result the venue already named.

## What a reader saw, photographed on production 2026-09-19 01:26Z

`https://bainluck.com/sports/tennis_atp` at phone width, section **"Live &
Paused 6"**, the first two cards::

    No result reported · Sep 18        Cervantes / Molchanov   Jecan / Pavel
    No result reported · Sep 18        Maestrelli              Gueymard Wayenburg

Those two rows are `15314463` and `15314462`, and each held a positive
`api_settlement` grade at that minute.

## Why this is a separate issue from #6739 and not a regression of it

#6739 put the venue's verdict on the league rails — `/api/leagues/{sport_key}`
— and closed. **`/sports/[key]` does not read that route.**
`frontend/app/sports/[key]/page.tsx:49` fetches `/api/events?sport=…`, so the
fix landed one route away from the page in its own screenshot. Nobody erred:
both halves were aimed at the door a backend reading of the route file leads
you to. The lesson is in `venue_settlement_reader`'s own docstring now — grep
the client for the path before building, not after.

## The sizing that decided the shape, measured before a line was written

The open question was whether a rail helper (the rails resolve ~16 cards)
survives a route serving up to 500 rows. **The gate sizes the read, not the
page** — production 2026-09-19 01:0x–01:2xZ:

    /api/events?limit=500 (unfiltered, worst case)   457 rows   31 askable (7%)
    /api/events?sport=soccer_other&limit=500         305 rows    3 askable (1%)

and those 31 ids returned **5 rows in 9.7 ms**, max graded legs per event 1,
against the reader's documented bound of max 84 / p99 20 / mean 3.2. Reach was
5 of 31; the other 26 carry no venue grade and correctly gain nothing.
`TestTheOrdinaryPagePaysNothing` is that property as behaviour.

## What this file guards

The producer half — the KEYS on both list payloads, under the names
`/api/events/{id}` has served since #6381 (ruling 047: extend the shared card's
contract, never fork the card). Rendering them is ux's under notice 41.

1. **Both doors, because they are the same card.**
   `_format_event_with_aggregated_odds` has exactly two callers, `list_events`
   and `search_events`, and search served the identical denying row
   (`?q=Fonseca` → `15314179`, `status: suspended`, keys ABSENT) in the same
   minute. Fixing one leaves the other denying the same result.
2. **The gate is still the detail route's gate.** A list may not publish a
   sentence the event's own page would refuse to publish.
3. **A failed read is a MISSING KEY, never a present `False`.**
4. **Both derivations of the gate input agree** — see
   `TestBothDerivationsOfTheGateInputAgree`, which is the one thing #7092 adds
   that #6739 had no reason to ask.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


# DDL shims so `create_all` can build the real schema on SQLite — the same pair
# `test_events_list_tag_fold_5918.py` declares, for the same reason: this route
# has Postgres arms in its WHERE clause, so it has to be driven against a real
# engine rather than a mock that answers every statement with the same rows.
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
    OddsSnapshot,
    Sport,
)
from app.routes.events import list_events, search_events  # noqa: E402
from app.utils.event_completion import started_without_result  # noqa: E402
from app.utils.lifecycle import served_event_status  # noqa: E402
from app.utils.venue_settlement_reader import (  # noqa: E402
    attach_venue_settlement,
)

#: The production rows, verbatim (`/api/events?sport=tennis_atp`, 01:26Z).
SPORT_KEY = "tennis_atp"
S_ATP = 1701

CERVANTES = 15314463  # card 1: "No result reported · Sep 18", venue graded
MAESTRELLI = 15314462  # card 2: the same sentence, the same minute
UNGRADED = 15314430  # a served row the venue has not graded — the control

#: Our spelling is the surname, the venue's is the full name. Keeping the
#: production spellings means this file would catch a regression to an
#: exact-match comparison.
OUR_HOME = "Cervantes / Molchanov"
OUR_AWAY = "Jecan / Pavel"
VENUE_HOME = "Tomas Barrios Vera Cervantes / Molchanov"
MONEYLINE = "Cervantes / Molchanov vs Jecan / Pavel"

#: A non-empty bag. Every specimen carries one, and NOT as decoration:
#: `not_a_blank_card(now)` deletes a row that is terminal, scoreless, past
#: `FINISHED_MARGIN` and has no probability sources — which is every specimen
#: in this file. Without this the route would serve nothing and every
#: assertion below would pass or fail for a reason that has nothing to do with
#: the venue's grade.
SOURCES = {"kalshi": {"value": 0.62, "updated_at": "2026-09-18T23:00:00+00:00"}}


def _played(hours_ago=5):
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
        win_probability_sources=kw.get("sources", SOURCES),
        event_tags=["provenance:unanchored"],
    )


def _graded(market_id, event_id, market_name, outcome_name, *, source="api_settlement"):
    return (
        FuturesMarket(
            id=market_id,
            event_id=event_id,
            source="polymarket",
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
        s.add(Sport(id=S_ATP, key=SPORT_KEY, name="ATP", group="Tennis"))
        for r in rows:
            s.add(r)
        s.commit()
    return eng


class _Session:
    """A real engine behind the async surface `list_events` calls."""

    def __init__(self, session):
        self._s = session

    async def execute(self, statement, *args, **kwargs):
        return self._s.execute(statement, *args)


def _portable_odds_query(event_ids):
    """The odds enrichment read, in a form SQLite can parse.

    `latest_odds_per_bookmaker_query` is a recursive CTE joined `LATERAL`, a
    deliberate Postgres shape no other dialect executes. Every test here stores
    NO snapshots, so the truthful answer is the empty one either way; this swap
    changes which SQL is parsed, not what the page is told. The same
    substitution `test_events_list_tag_fold_5918.py` makes, for its reason.
    """
    return select(OddsSnapshot).where(OddsSnapshot.event_id.in_(event_ids))


def _list_cards(*rows, **params) -> dict:
    """Every card `GET /api/events` serves, by id, through the real route."""
    eng = _engine(*rows)
    call = {"sport": SPORT_KEY, "status": None, "days": 7, "limit": 200, "offset": 0}
    call.update(params)
    with (
        patch(
            "app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})
        ),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch(
            "app.routes.events.latest_odds_per_bookmaker_query",
            new=_portable_odds_query,
        ),
        Session(eng) as s,
    ):
        payload = asyncio.run(list_events(db=_Session(s), **call))
    return {card["id"]: card for card in payload["events"]}


# ---------------------------------------------------------------------------
# the ship
# ---------------------------------------------------------------------------


class TestTheCardOnTheListPage:
    """🔴 THE SHIP, through `list_events` itself rather than through a helper.

    Driven end-to-end deliberately: the whole finding is that a correct helper
    was wired to a route nobody reads, and a test of the helper cannot see
    that.
    """

    def test_the_list_card_names_the_winner_the_venue_named(self):
        """The photographed card stops saying only "No result reported".

        Asserted as the production sentence rather than as a truthy check: the
        value must be the string `/api/events/15314463` already serves, because
        the defect is two surfaces disagreeing about one row.
        """
        market, outcome = _graded(1, CERVANTES, MONEYLINE, VENUE_HOME)
        card = _list_cards(_event(CERVANTES), market, outcome)[CERVANTES]

        assert card["venue_settled"] is True
        assert card["venue_settled_result"] == "Cervantes / Molchanov wins"

    def test_without_a_graded_market_the_card_is_exactly_what_it_was(self):
        """The control that makes the assertion above non-vacuous.

        Same row, same route, only the venue's grade removed. If this ever
        asserts a `venue_settled_result`, the ship above is being proved by
        something other than the grade.
        """
        card = _list_cards(_event(CERVANTES))[CERVANTES]

        assert card["venue_settled"] is False
        assert card["venue_settled_result"] is None

    def test_a_row_the_venue_has_not_graded_gets_no_sentence(self):
        """Reach was 5 of 31 askable rows. A change that put a sentence on the
        other 26 would read as a bigger win and be a fabrication."""
        market, outcome = _graded(1, CERVANTES, MONEYLINE, VENUE_HOME)
        cards = _list_cards(
            _event(CERVANTES),
            _event(UNGRADED, home="Sanchez Izquierdo", away="Kolar"),
            market,
            outcome,
        )

        assert cards[CERVANTES]["venue_settled_result"] == "Cervantes / Molchanov wins"
        assert cards[UNGRADED]["venue_settled_result"] is None


class TestTheCardsAreMatchedToTheirRowsById:
    """🔴 NEVER BY POSITION.

    A formatter drops a row it cannot format (gotcha #42), so the two lists are
    the same length only on a page where nothing went wrong — and that is
    exactly the page where a positional zip would print one player's result on
    the other's card. A card that names the loser is worse than a card that
    names nobody.
    """

    def test_two_graded_rows_each_keep_their_own_result(self):
        c_market, c_outcome = _graded(1, CERVANTES, MONEYLINE, VENUE_HOME)
        m_market, m_outcome = _graded(
            2, MAESTRELLI, "Maestrelli vs Gueymard Wayenburg", "Francesco Maestrelli"
        )
        cards = _list_cards(
            _event(CERVANTES),
            _event(
                MAESTRELLI,
                home="Maestrelli",
                away="Gueymard Wayenburg",
                when=_played(hours_ago=9),
            ),
            c_market,
            c_outcome,
            m_market,
            m_outcome,
        )

        assert cards[CERVANTES]["venue_settled_result"] == "Cervantes / Molchanov wins"
        assert cards[MAESTRELLI]["venue_settled_result"] == "Maestrelli wins"

    def test_only_the_graded_row_gains_the_sentence_when_its_neighbour_is_not(self):
        """The asymmetric case, which a positional zip passes by accident when
        both rows are graded and fails here."""
        m_market, m_outcome = _graded(
            2, MAESTRELLI, "Maestrelli vs Gueymard Wayenburg", "Francesco Maestrelli"
        )
        cards = _list_cards(
            _event(CERVANTES),
            _event(
                MAESTRELLI,
                home="Maestrelli",
                away="Gueymard Wayenburg",
                when=_played(hours_ago=9),
            ),
            m_market,
            m_outcome,
        )

        assert cards[CERVANTES]["venue_settled_result"] is None
        assert cards[MAESTRELLI]["venue_settled_result"] == "Maestrelli wins"


class TestTheGateIsTheDetailRoutesGate:
    """A list may not publish a sentence the event's own page would refuse."""

    def test_a_row_holding_our_own_score_is_refused(self):
        """Our result outranks the venue's grade, and publishing both invites a
        page to choose between them."""
        market, outcome = _graded(1, CERVANTES, MONEYLINE, VENUE_HOME)
        card = _list_cards(
            _event(CERVANTES, status="completed", scores=(0, 2)), market, outcome
        )[CERVANTES]

        assert "venue_settled_result" not in card

    def test_a_grade_from_a_weaker_source_is_not_the_venues_word(self):
        """`api_settlement` only — the rung where the house that took the bets
        said so. An inferred grade is not a warrant for overriding a page that
        currently says it has no result."""
        market, outcome = _graded(
            1, CERVANTES, MONEYLINE, VENUE_HOME, source="game_score"
        )
        card = _list_cards(_event(CERVANTES), market, outcome)[CERVANTES]

        assert card["venue_settled"] is False
        assert card["venue_settled_result"] is None


class TestTheOrdinaryPagePaysNothing:
    """The sizing property, as behaviour rather than as a paragraph.

    31 of 457 rows were askable on the worst-case production page. The other
    426 must cost nothing — a version that queried first and filtered afterwards
    would serve an identical payload and issue a statement per page view.

    🪤 DELETING `attach_venue_settlement`'s EARLY RETURN IS AN EQUIVALENT
    MUTANT, AND KNOWING WHY MATTERS MORE THAN THE SCORE. The sweep expected
    this test to kill it and it did not: with the `if not candidates: return`
    removed, the call still reaches `venue_settlements_for_events`, which
    answers `{}` on an empty id set BEFORE its try block — so no statement is
    issued either way. The property this test asserts is real and is genuinely
    guarded; what provides it is the reader's own empty-set guard, not the
    early return, which saves a function call. Do not "fix" the mutant by
    weakening this assertion to a call count.
    """

    def test_no_askable_row_issues_no_query_at_all(self):
        db = MagicMock()
        db.execute = AsyncMock()
        cards = [{"id": CERVANTES, "status": "completed", "home_score": 2,
                  "away_score": 0}]

        asyncio.run(
            attach_venue_settlement(
                db,
                [SimpleNamespace(id=CERVANTES, home_team_name=OUR_HOME,
                                 away_team_name=OUR_AWAY, status="completed",
                                 commence_time=_played())],
                cards,
                datetime.now(timezone.utc),
            )
        )

        db.execute.assert_not_awaited()
        assert "venue_settled" not in cards[0]


class TestAFailedReadIsAMissingKey:
    """Never a present `False`: the card keeps whatever it said before."""

    def test_a_raising_read_leaves_every_card_untouched(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("connection reset"))
        cards = [{"id": CERVANTES, "status": "suspended", "home_score": None,
                  "away_score": None}]

        asyncio.run(
            attach_venue_settlement(
                db,
                [SimpleNamespace(id=CERVANTES, home_team_name=OUR_HOME,
                                 away_team_name=OUR_AWAY, status="suspended",
                                 commence_time=_played())],
                cards,
                datetime.now(timezone.utc),
            )
        )

        assert "venue_settled" not in cards[0]
        assert "venue_settled_result" not in cards[0]


class TestBothDerivationsOfTheGateInputAgree:
    """🔴 THE ONE THING #7092 ADDS THAT #6739 HAD NO REASON TO ASK.

    `/api/events` publishes `started_without_result` on every card; the league
    rails' briefs do not carry it. `attach_venue_settlement` therefore
    recomputes it for both callers rather than reading the published key — but
    the two derivations are not the same expression, and if they can disagree
    then one row gets two answers on two surfaces, which is the defect #6739
    exists to remove.

    `_format_event` derives the flag from the RAW `event.status` while
    publishing the SERVED one. The gap can only open on a premature `live` row,
    and `served_event_status` downgrades one only when `live_start_satisfied`
    is False — `start > now`, `start is None`, or the comparison raising. Each
    case is asserted below; `started_without_result` answers False for all
    three, so the divergence is unreachable rather than rare.

    🪤 THE COROLLARY, STATED SO NOBODY RE-DERIVES IT: substituting the RAW
    status for the SERVED one inside `attach_venue_settlement` is an EQUIVALENT
    MUTANT, and this class is the proof of why rather than a failure to catch
    it. If these four tests ever disagree, that mutant becomes killable and the
    two surfaces become capable of answering one row two ways — which is the
    whole defect #6739 exists to remove. That is what this class is for.
    """

    @staticmethod
    def _both(status, commence, now):
        published = started_without_result(status, commence, now)
        recomputed = started_without_result(
            served_event_status(status, commence, now), commence, now
        )
        return published, recomputed

    def test_a_live_row_whose_start_is_in_the_future(self):
        now = datetime.now(timezone.utc)
        published, recomputed = self._both("live", now + timedelta(hours=40), now)

        assert published is False and recomputed is False

    def test_a_live_row_with_no_commence_time_at_all(self):
        now = datetime.now(timezone.utc)
        published, recomputed = self._both("live", None, now)

        assert published is False and recomputed is False

    def test_a_live_row_whose_time_cannot_be_compared(self):
        """A tz-naive `commence_time` against a tz-aware `now` raises rather
        than compares. Both halves fail closed — #6057's rule, and the reason
        neither may be replaced by a bare `<`."""
        now = datetime.now(timezone.utc)
        published, recomputed = self._both("live", datetime.now(), now)

        assert published is False and recomputed is False

    def test_the_admitted_case_is_admitted_by_both(self):
        """The control. Without this the three assertions above are satisfied
        by a predicate that answers False to everything."""
        now = datetime.now(timezone.utc)
        published, recomputed = self._both("scheduled", now - timedelta(hours=5), now)

        assert published is True and recomputed is True


# ---------------------------------------------------------------------------
# the second door
# ---------------------------------------------------------------------------
#
# `search_events` cannot be driven on the engine above: its recall arms are
# Postgres full-text (`websearch_to_tsquery`, `numnode`), which SQLite refuses
# to parse. So this half uses the statement-dispatch session
# `test_a_fought_fight_is_not_upcoming_on_the_list_rails_6568.py` built for the
# same pair of routes, with one arm added for the venue read. Weaker evidence
# than a real engine and said so plainly — what it can still prove is the thing
# in question here, that the route CALLS the attach and that the keys reach the
# rows it serves.


def _venue_read(sql: str) -> bool:
    """The venue settlement read's own statement, and nothing else.

    Both routes touch `futures_markets` for other reasons, so the table name
    alone would count an enrichment stage as this read. The join to
    `futures_outcomes` beside a projection of `futures_markets.event_id` is the
    discriminator — the same reasoning `_is_correction_query` gives one file
    over.
    """
    return "futures_outcomes" in sql and "futures_markets.event_id" in sql


def _search_db(events, *, graded=()):
    """A session answering the search page query AND the venue read."""
    db = AsyncMock()

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
        if _venue_read(s):
            return make_result([], fetched=list(graded))
        if "count(" in s:
            return make_result([])
        if "futures_markets" in s or "odds_snapshots" in s or "teams" in s:
            return make_result([])
        if "win_prob_snapshots" in s or "event_provider_anchors" in s:
            return make_result([])
        if "from events" in s:
            return make_result(events)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


def _search_cards(events, *, graded=(), q="Cervantes") -> dict:
    """Every row `GET /api/events/search` serves, by id, through the route."""
    # A real `Sport`, not a `SimpleNamespace`: assigning to an ORM relationship
    # fires the backref event, which wants `_sa_instance_state`.
    sport = Sport(id=S_ATP, key=SPORT_KEY, name="ATP", group="Tennis")
    for e in events:
        e.sport = sport
    rc = MagicMock()
    rc.get.return_value = None  # always a cache MISS, so the route does the work
    with (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch(
            "app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})
        ),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch("app.routes.events._record_trending", new=MagicMock()),
    ):
        payload = asyncio.run(
            search_events(
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
                db=_search_db(events, graded=graded),
            )
        )
    return {row["id"]: row for row in (payload.get("results") or [])}


class TestTheSecondDoorServesTheSameCard:
    """🔴 SEARCH IS THE OTHER CALLER OF THE SAME SERIALIZER.

    `_format_event_with_aggregated_odds` has exactly two callers. Measured on
    production 2026-09-19 01:1xZ, `GET /api/events/search?q=Fonseca` served
    `15314179` with `status: suspended`, no score, and both keys ABSENT — the
    same row, in the same state, that `/sports/tennis_other` was denying in the
    same minute. Fixing one door and not the other leaves the identical
    sentence on screen one tap away.
    """

    def test_a_search_result_names_the_winner_the_venue_named(self):
        cards = _search_cards(
            [_event(CERVANTES)],
            graded=[(CERVANTES, MONEYLINE, f"0x{1:064x}", VENUE_HOME)],
        )

        assert cards[CERVANTES]["venue_settled"] is True
        assert cards[CERVANTES]["venue_settled_result"] == "Cervantes / Molchanov wins"

    def test_without_a_grade_the_search_result_is_exactly_what_it_was(self):
        """The control. Same row, same route, only the grade removed."""
        cards = _search_cards([_event(CERVANTES)])

        assert cards[CERVANTES]["venue_settled"] is False
        assert cards[CERVANTES]["venue_settled_result"] is None


class TestThePositionalPairingIsActuallyReachable:
    """🔴 #6739 RECORDED THIS MUTANT AS "UNKILLABLE BY CONSTRUCTION". IT IS NOT.

    Replacing the id lookup with `zip(candidates, settlements.values())`
    survives every guard in that file and every route-level guard in this one,
    because `venue_settlements_for_events` builds its dict from the very list
    the caller derived from `candidates`, so the two iterate in the same order
    — for as long as they are the same LENGTH.

    They are not, on one input. The events list is filtered
    (`if int(brief["id"]) in by_id`), so a candidate brief whose row is absent
    from the sequence is dropped from the read while remaining in
    `candidates` — and from that point the zip is off by one and every
    subsequent card carries its neighbour's result. The id lookup answers
    `None` for that brief and leaves it alone.

    Production cannot currently produce the input (the briefs are formatted
    FROM the rows, so every brief id has a row), which is exactly why it is
    worth a guard rather than a shrug: the property "these are paired by id" is
    load-bearing precisely when something upstream has already gone wrong, and
    a card naming the loser is worse than a card naming nobody.
    """

    def test_a_brief_with_no_row_does_not_shift_its_neighbours_result(self):
        db = MagicMock()

        async def execute(stmt, *a, **k):
            r = MagicMock()
            r.all.return_value = [
                (MAESTRELLI, "Maestrelli vs Gueymard Wayenburg", "0xabc",
                 "Francesco Maestrelli"),
            ]
            return r

        db.execute = AsyncMock(side_effect=execute)

        orphan = {"id": CERVANTES, "status": "suspended", "home_score": None,
                  "away_score": None}
        real = {"id": MAESTRELLI, "status": "suspended", "home_score": None,
                "away_score": None}

        asyncio.run(
            attach_venue_settlement(
                db,
                # CERVANTES is deliberately absent from the rows.
                [SimpleNamespace(id=MAESTRELLI, home_team_name="Maestrelli",
                                 away_team_name="Gueymard Wayenburg",
                                 status="suspended", commence_time=_played())],
                [orphan, real],
                datetime.now(timezone.utc),
            )
        )

        # The zip would hand Maestrelli's win to the orphan card.
        assert "venue_settled_result" not in orphan
        assert real["venue_settled_result"] == "Maestrelli wins"
