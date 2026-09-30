"""Dota 2 matches get a row from their Kalshi listing — #9823.

## What a reader saw

Production, 2026-09-30 ~12:25Z: the BLAST Slam Dota 2 matches of the day —
Team Spirit v 1win, Natus Vincere v Team Nemesis, LGD v PARIVISION, Team Liquid
v Aurora — had no match page and no search result, while Kalshi listed every one
(``KXDOTA2GAME-26SEP3009001WINTS``, ``-26SEP301200NAVINEM``,
``-26OCT011200LIQUIDAUR``) and CS2 / LoL / Valorant matches on the same day each
had their Kalshi-minted row. Every ``KXDOTA2GAME/MAP/TOTALMAPS`` market from the
previous 48 h sat at ``event_id`` NULL.

## Why

``_UNSUPPORTED_LEAGUE_PREFIXES`` carried the bare ``kxdota2`` from #1081 ("we
ingest no events for these leagues"). That was written before Kalshi esports
rows minted their own fixtures. So ``KALSHI_GAME_TICKER_PREFIXES`` never picked
up a Dota game ticker (Pass 1 never selected one), and
``is_classification_only_ticker`` refused its auto-create.

## The fix and its boundary

The explicit game prefixes ``kxdota2game`` / ``kxdota2map`` / ``kxdota2totalmaps``
are armed beside their three siblings. The bare ``kxdota2`` stays
classification-only, and longest-prefix-wins keeps the two apart: a
The-International future stays refused. The map and total-maps legs join the
match row through Kalshi's own series id (the #9696 anchor, ruling 048 arm A).
No name is compared and no clock window is opened.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    _sport_id_cache,
    find_or_create_event,
)
from app.tasks.prediction_market_matching import (
    WRONG_GAME_PREFIXES,
    _KALSHI_TICKER_LIKE_PATTERNS,
)
from app.utils.provider_anchor_keys import ANCHOR_KIND_GAME, kalshi_anchor_key
from app.utils.sport_keys import (
    KALSHI_GAME_TICKER_PREFIXES,
    KALSHI_LINK_RATE_GAME_TICKER_PREFIXES,
    get_sport_key_from_ticker,
    is_classification_only_ticker,
    is_kalshi_game_level_ticker,
)
from tests.test_anchor_channel_consumer_2213 import _AnchorSession

ESPORTS_SPORT_ID = 70707

# Production specimens, verbatim (futures_markets, read 2026-09-30).
SPIRIT_1WIN = "KXDOTA2GAME-26SEP3009001WINTS"
NAVI_NEMESIS = "KXDOTA2GAME-26SEP301200NAVINEM"
DBXE_GAME = "KXDOTA2GAME-26OCT010500DBXE"
DBXE_LEGS = (
    "KXDOTA2MAP-26OCT010500DBXE-1",
    "KXDOTA2MAP-26OCT010500DBXE-2",
    "KXDOTA2TOTALMAPS-26OCT010500DBXE",
)
DOTA_GAME_LEGS = (SPIRIT_1WIN, NAVI_NEMESIS, DBXE_GAME, *DBXE_LEGS)


@pytest.fixture(autouse=True)
def _seed_sport_cache():
    _sport_id_cache["esports"] = ESPORTS_SPORT_ID
    yield
    _sport_id_cache.pop("esports", None)


def _selected_by_pass1(ticker: str) -> bool:
    """Pass 1's SQL is `external_id ILIKE <pattern>` over these patterns."""
    t = ticker.lower()
    return any(t.startswith(p.rstrip("%")) for p in _KALSHI_TICKER_LIKE_PATTERNS)


# ══════════════════════════════════════════════════════════════════════════
# The prefix — the whole defect
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("ticker", DOTA_GAME_LEGS)
def test_a_dota_game_leg_reaches_the_matcher_and_may_mint(ticker):
    """🔴 before #9823: not selected by Pass 1, and auto-create refused."""
    assert _selected_by_pass1(ticker)
    assert not is_classification_only_ticker(ticker)
    assert is_kalshi_game_level_ticker(ticker)
    assert get_sport_key_from_ticker(ticker) == "esports"


@pytest.mark.parametrize("ticker", (
    "KXCS2GAME-26SEP300600HSINF",
    "KXLOLGAME-26SEP2917009ZEST",
    "KXVALORANTTOTALMAPS-26OCT020500EDGGE",
))
def test_dota_now_matches_its_three_siblings(ticker):
    """The reference: the sibling games that already had their rows."""
    assert _selected_by_pass1(ticker)
    assert not is_classification_only_ticker(ticker)


@pytest.mark.parametrize("ticker", ("KXDOTA2TI-26", "KXDOTA2-26TIWIN"))
def test_the_rest_of_the_dota_family_stays_classification_only(ticker):
    """The refusal arm (gotcha #43): only the game legs are armed. The bare
    `kxdota2` still out-specifies every game prefix for a non-game ticker, so a
    tournament future never mints a fixture."""
    assert not _selected_by_pass1(ticker)
    assert is_classification_only_ticker(ticker)
    assert get_sport_key_from_ticker(ticker) == "esports"


def test_dota_stays_out_of_the_link_rate_denominator_like_its_siblings():
    for ticker in DOTA_GAME_LEGS:
        t = ticker.lower()
        assert any(t.startswith(p) for p in KALSHI_GAME_TICKER_PREFIXES)
        assert not any(t.startswith(p) for p in KALSHI_LINK_RATE_GAME_TICKER_PREFIXES)


def test_dota_match_and_map_winners_get_the_wrong_game_guard():
    """A different-dated Dota leg on one row is a wrong game, like CS2's;
    total maps is a prop and is absent, like its siblings'."""
    assert {"kxdota2game", "kxdota2map"} <= WRONG_GAME_PREFIXES
    assert "kxdota2totalmaps" not in WRONG_GAME_PREFIXES
    assert "kxcs2totalmaps" not in WRONG_GAME_PREFIXES


@pytest.mark.parametrize("ticker, segment", [
    (SPIRIT_1WIN, "26SEP3009001WINTS"),
    (DBXE_GAME, "26OCT010500DBXE"),
    *[(t, "26OCT010500DBXE") for t in DBXE_LEGS],
])
def test_every_dota_leg_carries_its_series_game_anchor(ticker, segment):
    key = kalshi_anchor_key(ticker)
    assert (key.source_id, key.id_kind) == (f"esports:{segment}", ANCHOR_KIND_GAME)


# ══════════════════════════════════════════════════════════════════════════
# The registry — one series, one row
# ══════════════════════════════════════════════════════════════════════════


def _claim(ticker, *, commence, home="Direborn", away="Xipto Esports"):
    """The auto-create claim as `prediction_market_matching` builds it."""
    return EventIdentity(
        sport_key="esports", home_team_name=home, away_team_name=away,
        commence_time=commence,
        claim=EventClaim("kalshi", f"pm_kalshi_{ticker}", provider_id=ticker),
        commence_time_source="kalshi", status="scheduled",
    )


@pytest.mark.asyncio
async def test_dota_map_and_total_maps_legs_join_the_match_row():
    kickoff = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    session = _AnchorSession(sport_id=ESPORTS_SPORT_ID)
    game_row, created = await find_or_create_event(
        session, _claim(DBXE_GAME, commence=kickoff)
    )
    assert created is True
    session.by_id[game_row.id] = game_row
    session.event_sports[game_row.id] = ESPORTS_SPORT_ID

    for ticker in DBXE_LEGS:
        row, created = await find_or_create_event(
            session, _claim(ticker, commence=kickoff - timedelta(hours=6))
        )
        assert (row.id, created) == (game_row.id, False), ticker
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_a_different_dota_series_between_other_clubs_gets_its_own_row():
    session = _AnchorSession(sport_id=ESPORTS_SPORT_ID)
    first, _ = await find_or_create_event(
        session, _claim(SPIRIT_1WIN, commence=datetime(2026, 9, 30, 13, 0, tzinfo=timezone.utc),
                        home="1win", away="Team Spirit")
    )
    session.by_id[first.id] = first
    session.event_sports[first.id] = ESPORTS_SPORT_ID

    other, created = await find_or_create_event(
        session, _claim(NAVI_NEMESIS, commence=datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc),
                        home="Natus Vincere", away="Team Nemesis")
    )
    assert created is True
    assert other.id != first.id
