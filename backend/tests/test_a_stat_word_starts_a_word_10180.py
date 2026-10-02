"""#10180: the game's own winner is not a player prop because a team is from Tampa.

`_PLAYER_PROP_RE` in `app/routes/events.py` closes with `\\b` and opens with
nothing, so its short arms (`PRA|PA|PR|RA`) match the END of a word: Tam-PA.
`_classify_game_market` asks it before the moneyline arm, so on production
`/events/15322539` (Yankees at Rays, ALDS Game 1, read 2026-10-02 08:45Z) Kalshi's
Game 1 winner (`KXMLBGAME-26OCT031830NYYTB`) was served in `player_props`, and
the page drew:

    The script   New York Yankees vs Tampa Bay: 1+          55% chance
    THE SCRIPT   GAME 1: NEW YORK YANKEES VS TAMPA BAY   Tampa Bay 55% / NYY 45%

— the hero's own number, twice more, under a label naming no team.

The control was on the same night: `/events/15322462` carries the identical
Kalshi shape (`Game 1: Chicago WS vs Cleveland`, `KXMLBGAME-…CWSCLE`) and served
no props at all.

The fix is the ticker's, not the regex's: a Kalshi series token ending in GAME
skips the bare stat-word arm. Anchoring the regex is the general cure, but four
other test modules (#1588, #1735, #5088, #4189) reach their subject only through
the same Tam-PA / Mi-RRA match — that is #10180's follow-up, routed to its owners.

The fixtures are the specimen's real market names, tickers and prices.
"""

from datetime import datetime, timezone

import pytest
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


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base, FuturesMarket, FuturesOutcome  # noqa: E402
from app.routes.events import (  # noqa: E402
    _classify_game_market,
    _is_kalshi_game_winner_series,
)

EVENT_ID = 15322539
SPORT_ID = 1
COMMENCE = datetime(2026, 10, 3, 22, 30, tzinfo=timezone.utc)

#: Kalshi's Game 1 winner, as stored (`New York Y` is Kalshi's truncation).
KALSHI_WINNER = (
    "Game 1: New York Y vs Tampa Bay",
    "KXMLBGAME-26OCT031830NYYTB",
    "kalshi",
    "duel",
    (("New York Yankees", 0.445), ("Tampa Bay", 0.55)),
)
#: Polymarket's moneyline leg of the ALDS game container (market 63612403). Its
#: condition hash is used as a not-a-Kalshi-ticker arm; the leg itself still
#: reaches `player_props` through the regex and is the follow-up's.
POLY_WINNER = (
    "New York Yankees vs. Tampa Bay Rays",
    "0x2725d6ea18758162f32f88a223c2d7e220d1332a94ca51073b4e7be04bb8798f",
    "polymarket",
    "duel",
    (("New York Yankees", 0.4525), ("Tampa Bay Rays", 0.55)),
)
#: A real prop on the same game whose name ALSO contains "Tampa" — the control
#: that a word boundary does not cost a genuine stat word its match.
REAL_PROP_NAME = "Tampa Bay vs New York Y: Shane McClanahan Strikeouts"
REAL_PROP = (
    REAL_PROP_NAME,
    "KXMLBKS-26OCT031830NYYTB-SMCCLANAHAN",
    "kalshi",
    "player_prop",
    (("Shane McClanahan: 6+", 0.48),),
)


def _engine(markets):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=SPORT_ID, key="baseball_mlb", name="MLB"))
        s.add(
            Event(
                id=EVENT_ID,
                sport_id=SPORT_ID,
                home_team_name="Tampa Bay Rays",
                away_team_name="New York Yankees",
                commence_time=COMMENCE,
                status="scheduled",
            )
        )
        outcome_id = 9000
        for market_id, (name, ticker, source, mtype, legs) in enumerate(markets, start=700):
            s.add(
                FuturesMarket(
                    id=market_id,
                    event_id=EVENT_ID,
                    sport_id=SPORT_ID,
                    source=source,
                    external_id=ticker,
                    name=name,
                    category="game",
                    llm_sport_category="baseball",
                    market_type=mtype,
                    status="open",
                )
            )
            for leg, prob in legs:
                outcome_id += 1
                s.add(
                    FuturesOutcome(
                        id=outcome_id,
                        market_id=market_id,
                        external_id=f"{ticker}-{outcome_id}",
                        name=leg,
                        current_probability=prob,
                        opening_probability=prob,
                    )
                )
        s.commit()
    return eng


class _SyncAsAsync:
    def __init__(self, session):
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)


def _served(eng):
    """`GET /api/events/{id}/game-markets`'s builder, actually executed."""
    import asyncio

    from app.routes.events import _build_game_markets

    with Session(eng) as s:
        response, _status, _ids = asyncio.run(
            _build_game_markets(EVENT_ID, _SyncAsAsync(s))
        )
    return response


def _prop_markets(response):
    return {p["market_name"] for p in response.get("player_props") or []}


def _script_keys(response):
    return {row["key"] for row in response.get("props_script") or []}


class TestAKalshiGameSeriesIsTheWinner:
    @pytest.mark.parametrize(
        "ticker",
        [
            "KXMLBGAME-26OCT031830NYYTB",
            "KXNFLGAME-26OCT04TBATL",
            "KXNHLGAME-26OCT09TBFLA",
            "kxmlbgame-26oct031830nyytb",
        ],
    )
    def test_a_game_series_token_is_a_winner_series(self, ticker):
        assert _is_kalshi_game_winner_series(ticker)

    @pytest.mark.parametrize(
        "ticker",
        [
            None,
            "",
            "KXMLBKS-26OCT031830NYYTB-SMCCLANAHAN",
            "KXMLBTOTAL-26OCT031830NYYTB-8",
            "KXMLBSPREAD-26OCT031830NYYTB-TB2",
            # "GAME" inside a later segment is not the series token.
            "KXMLBHITS-26OCT03GAME-AJUDGE",
            POLY_WINNER[1],
        ],
    )
    def test_anything_else_is_not(self, ticker):
        assert not _is_kalshi_game_winner_series(ticker)

    def test_the_specimen_is_classified_like_its_control(self):
        """The control is the same night's White Sox–Guardians Game 1, the same
        Kalshi family, whose names carry no word ending in a stat abbreviation."""
        specimen = _classify_game_market(KALSHI_WINNER[0], external_id=KALSHI_WINNER[1])
        control = _classify_game_market(
            "Game 1: Chicago WS vs Cleveland",
            external_id="KXMLBGAME-26OCT031300CWSCLE",
        )
        assert control == "moneyline"
        assert specimen == control

    def test_a_tampa_prop_with_a_real_stat_word_is_still_a_prop(self):
        """Control on the same name family: the exemption is the ticker's, so a
        real Rays strikeout prop keeps its class."""
        assert _classify_game_market(REAL_PROP[0], external_id=REAL_PROP[1]) == "player_prop"


class TestTheServedPageHasNoWinnerProp:
    def test_the_kalshi_game_winner_is_not_served_as_a_prop(self):
        response = _served(_engine([KALSHI_WINNER, REAL_PROP]))

        served = _prop_markets(response)
        assert KALSHI_WINNER[0] not in served
        # #6447 completes Kalshi's truncated club on the way out, so read the
        # reader's spelling too — the prop must be gone under either name.
        assert not any("vs Tampa Bay" in m and m.startswith("Game 1") for m in served)

    def test_the_script_does_not_restate_the_hero(self):
        response = _served(_engine([KALSHI_WINNER, REAL_PROP]))

        keys = _script_keys(response)
        assert not any(k.startswith("Game 1:") for k in keys), sorted(keys)

    def test_the_real_prop_is_still_served(self):
        """Control: the fix moves winner markets out; it must not take a real
        prop on the same Tampa Bay game with it."""
        response = _served(_engine([KALSHI_WINNER, REAL_PROP]))

        assert any("McClanahan" in m for m in _prop_markets(response)), (
            sorted(_prop_markets(response))
        )
