"""Guard: the league page stops printing a ghost search and the event page fold (#6345).

THE CARD THIS EXISTS FOR. `/sport/soccer/laliga` at 390px, 2026-09-15 09:4xZ,
walked two taps:

    NO RESULT REPORTED
      Celta Fortuna — Eibar        <- first card, href="/events/15308951"

    tap it ->  Final · Eibar WON · 0–4, with a complete win-probability curve

**The list says we have no result for a match whose result is one tap away on
our own page.** The destination is not even the same row: `GET /api/events/
15308951` has resolved to `15306978` since Q050 (2026-09-02).

    id        teams                     sport_key                      status     score
    15308951  Celta Fortuna v Eibar     soccer_spain_la_liga           suspended  null
    15306978  Celta Fortuna v SD Eibar  soccer_spain_segunda_division  completed  0-4

🔴 WHY THE PAGE'S OWN FOLD CANNOT REACH IT, AND WHY NO WIDENING OF ITS KEY WOULD.
`_folded_past_rails` is a PAGE-LOCAL fold: `fold_twin_events` needs both rows of
a pair in the same result set. **The canonical is in a different league**, so it
is never on the La Liga page at all — the fold is not declining, it is blind.
The two rows also agree on neither name (`Eibar` / `SD Eibar`), league, nor
minute (21:30Z is Kalshi's expected expiration, 18:30Z the kick-off), so even
co-located it would correctly decline. The Q050 verdict has no such limit: it is
id-keyed and asks the database, so the canonical need not be on the page.

WHAT THIS SHIP ACTUALLY IS. #6231 shipped `market_born_duplicates_on_page` for
`search_events` and `list_events` **on this exact pair** — its guard file is
`test_a_market_born_ghost_is_off_the_list_rails_6231.py` and its docstring names
15308951/15306978. The league page simply never called it. So this is a sibling
surface adopting a shipped fix, not a new rule, and the memory it pays is
`r_a_shipped_fixs_guard_pins_one_component_so_sibling_surfaces_keep_the_bug`.

WHAT EACH TEST HERE IS DEFENDING. Not "a route returns a rail":

* the ship — the dead card is off the unreported rail
  (`test_the_ghost_is_off_the_unreported_rail`);
* that the guard is not vacuous — the page-local fold alone leaves it, so the
  new stage is doing the work and a revert is visible
  (`test_the_page_local_fold_alone_leaves_the_ghost`);
* the thing a careless fix breaks — the REAL unreported rows must survive. A
  suppression keyed on "market-born" or on "unanchored" rather than on the
  verdict would empty the rail, and on soccer it would take all of it: every
  row this rail currently holds is `provenance:unanchored`
  (`test_the_other_five_real_rows_survive`);
* that the verdict, not the provenance, is what suppresses — the same ghost with
  no id-keyed contradiction keeps its card
  (`test_without_the_contradiction_the_row_is_not_suppressed`);
* the belt — a verdict that raises serves the unsuppressed page, never a 500
  (`test_a_failing_verdict_serves_the_page_rather_than_an_error`).

The verdict's own seven refusals are pinned in
`test_market_born_duplicate_reads_as_canonical_q050.py`; this file is about
DELIVERY on the third surface — that the league page calls it and acts on it.

REAL rows behind a real engine, not MagicMock, for the reason
`test_league_page_tag_fold_5853.py` records: `build_league` runs a dozen
enrichment stages after the rails, and a mock that answers every statement with
the same rows makes them explode on an `Event` — a harness story, not a result.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


# DDL shims so `create_all` can build the real schema on SQLite — the same pair
# `test_league_page_tag_fold_5853.py` declares, for the same reason.
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

#: The production pair, verbatim (`db-query`, 2026-09-15 10:2xZ).
GHOST = 15308951
CANONICAL = 15306978

S_LA_LIGA = 1317
S_SEGUNDA = 1318
SPORT_KEY = "soccer_spain_la_liga"

#: The anchor's `source_id` — Kalshi's own ticker, read back verbatim.
TICKER = "KXLALIGAGAME-26SEP14CELEIB"


def _hours_ago(hours: float) -> datetime:
    """Gotcha #44: offset from the clock, never a literal stamp."""
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _ghost(event_id: int = GHOST, *, home: str = "Celta Fortuna") -> Event:
    """The row the reader met: suspended, scoreless, market-born, wrong league.

    `commence_time` is Kalshi's expected expiration, three hours after the real
    kick-off (gotcha #14) — which is half of why the two rows never shared a
    fold key.
    """
    e = Event(
        id=event_id,
        sport_id=S_LA_LIGA,
        home_team_name=home,
        away_team_name="Eibar",
        commence_time=_hours_ago(13),
        commence_time_source="kalshi",
        status="suspended",
        home_score=None,
        away_score=None,
        completed_at=None,
        win_probability_sources={},
        event_tags=["provenance:source:kalshi", "provenance:unanchored"],
    )
    return e


def _canonical() -> Event:
    """The match that was actually played, 0-4, in the league it belongs to."""
    return Event(
        id=CANONICAL,
        sport_id=S_SEGUNDA,
        home_team_name="Celta Fortuna",
        away_team_name="SD Eibar",
        commence_time=_hours_ago(16),
        commence_time_source="odds_api",
        external_id="247343bc379dfe120732d07d0106e412",
        status="completed",
        home_score=0,
        away_score=4,
        completed_at=_hours_ago(14),
        win_probability_sources={},
        event_tags=["provenance:source:odds_api"],
    )


def _real_unreported(event_id: int, home: str, away: str, *, hours: float) -> Event:
    """One of the five rows that MUST keep its card.

    These are real Segunda fixtures mis-shelved on the La Liga page (#5982's
    `sport_id` repair owns that). Measured 2026-09-15: their kick-offs are on
    clean minute boundaries and they were created four days ahead — so they are
    ordinary scheduled matches whose result we never captured, and nothing about
    them is market-born fiction. They carry the SAME provenance tags as the
    ghost, which is exactly why a tag-keyed suppression would be wrong.
    """
    return Event(
        id=event_id,
        sport_id=S_LA_LIGA,
        home_team_name=home,
        away_team_name=away,
        commence_time=_hours_ago(hours),
        commence_time_source="kalshi",
        status="suspended",
        home_score=None,
        away_score=None,
        completed_at=None,
        win_probability_sources={},
        event_tags=["provenance:source:kalshi", "provenance:unanchored"],
    )


#: The other five rows the La Liga rail served on 2026-09-15, verbatim.
THE_OTHER_FIVE = (
    (15308585, "Tenerife", "Leganes", 39),
    (15308732, "Valladolid", "Oviedo", 44),
    (15308739, "Gijon", "Eldense", 46),
    (15307859, "Cordoba", "Almeria", 63),
    (15307866, "Granada", "Albacete", 66),
)


def _engine(*rows):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_LA_LIGA, key=SPORT_KEY, name="La Liga", group="Soccer"))
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


def _the_contradiction(event_id: int = GHOST, *, target: int = CANONICAL):
    """The id-keyed contradiction Q050 reads, as two rows.

    The anchor says Kalshi calls `event_id` by `TICKER`; the market carrying
    that very ticker is linked to `target` instead. The ghost holds no markets
    of its own, which is refusal 5 — the reason suppressing it loses nothing.
    """
    return (
        EventProviderAnchor(
            # Explicit ids: `event_provider_anchors.id` is BigInteger, and
            # SQLite only autoincrements a plain INTEGER PRIMARY KEY.
            id=84170,
            event_id=event_id,
            source="kalshi",
            source_id=TICKER,
            id_kind="market",
            first_seen_at=_hours_ago(70),
        ),
        FuturesMarket(
            id=990001,
            source="kalshi",
            external_id=TICKER,
            event_id=target,
            name="Will Celta Fortuna beat Eibar?",
            category="sports",
        ),
    )


class _Session:
    """A real engine behind the async surface `build_league` calls.

    ⚠️ It FORWARDS the bind parameters, unlike the otherwise-identical shim in
    `test_league_page_tag_fold_5853.py`, whose statements carry their values
    inline. The drain verdict is `text()` with an expanding `:event_ids`, so a
    shim that drops `*args` raises `InvalidRequestError` inside the stage — the
    belt then serves the undrained page and every ship assertion here fails
    while the belt test passes. A harness story that reads exactly like a
    missing fix.
    """

    def __init__(self, session):
        self._s = session

    async def execute(self, statement, *args, **kwargs):
        return self._s.execute(statement, *args, **kwargs)


def _unreported_rail(*rows) -> dict:
    """The served `unreported_games` rail, through the real route."""
    eng = _engine(*rows)
    with Session(eng) as s:
        payload = asyncio.run(route.build_league(SPORT_KEY, _Session(s)))
    return {card["id"]: card for card in payload["unreported_games"]}


# ---------------------------------------------------------------------------
# the ship
# ---------------------------------------------------------------------------


class TestTheLaLigaCard:
    def test_the_ghost_is_off_the_unreported_rail(self):
        rail = _unreported_rail(_ghost(), _canonical(), *_the_contradiction())
        assert GHOST not in rail

    def test_the_page_local_fold_alone_leaves_the_ghost(self):
        """The strawman: without the new stage the card is still there.

        `_folded_past_rails` is handed the page exactly as the route builds it —
        the canonical is not on it, because it is in another league — so the
        fold keeps the ghost and the assertion above can only be passing
        because of the stage this file is about.
        """
        kept_r, kept_u, kept_g = route._folded_past_rails([], [_ghost()], [], [])
        assert [e.id for e in kept_u] == [GHOST]

    def test_the_canonical_is_not_on_this_page_to_be_folded_against(self):
        """Names the blindness, so a later reader does not 'fix' the fold key."""
        rail = _unreported_rail(_ghost(), _canonical(), *_the_contradiction())
        assert CANONICAL not in rail


# ---------------------------------------------------------------------------
# the thing a careless fix breaks
# ---------------------------------------------------------------------------


class TestWhatMustSurvive:
    def test_the_other_five_real_rows_survive(self):
        """A rail of five real matches, one ghost — five cards out.

        Every one of these carries `provenance:unanchored` and
        `commence_time_source='kalshi'`, identical to the ghost. Measured
        2026-09-15: ALL 17 rows this rail holds across the five soccer leagues
        are `provenance:unanchored`, so a suppression keyed on the tag would
        empty the rail on every soccer page we serve.
        """
        others = [
            _real_unreported(i, h, a, hours=hrs) for i, h, a, hrs in THE_OTHER_FIVE
        ]
        rail = _unreported_rail(
            _ghost(), _canonical(), *others, *_the_contradiction()
        )
        assert GHOST not in rail
        assert sorted(rail) == sorted(i for i, _h, _a, _hrs in THE_OTHER_FIVE)

    def test_without_the_contradiction_the_row_is_not_suppressed(self):
        """The verdict suppresses, not the provenance.

        Same market-born row, same tags, no anchor and no market pointing
        elsewhere — so there is no id-keyed contradiction and Q050 refuses. The
        card stays. This is what stops the stage becoming "hide anything
        Kalshi minted".
        """
        rail = _unreported_rail(_ghost(), _canonical())
        assert GHOST in rail


# ---------------------------------------------------------------------------
# the belt (gotcha #42)
# ---------------------------------------------------------------------------


class TestTheBelt:
    def test_a_failing_verdict_serves_the_page_rather_than_an_error(self, monkeypatch):
        """A raising drain costs the suppression and never the page."""

        async def _boom(*_a, **_k):
            raise RuntimeError("verdict down")

        monkeypatch.setattr(route, "market_born_duplicates_on_page", _boom)
        rail = _unreported_rail(_ghost(), _canonical(), *_the_contradiction())
        assert GHOST in rail
