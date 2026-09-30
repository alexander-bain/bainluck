"""One esports series, one row — #9696.

## What a reader saw

Production, 390px, ``/search?q=esports``, 2026-09-29 ~22:15Z: **9z Globant v
Estral Esports** listed twice, one row "No price yet" at 5:00 PM PDT and one
priced 1% / 99% at 6:00 PM PDT. Same walk: **EDward Gaming v Global Esports**
twice. Two splits in one 21-game result.

## Why, per specimen (production rows, read 2026-09-29)

Every Kalshi market on one series carries Kalshi's own segment — ``26SEP2917009ZEST``
— and ``kalshi_anchor_key`` turns that into the game anchor
``esports:26SEP2917009ZEST`` that registry Step 2 finds the first row by. Two
gaps kept the anchor from existing:

* **LoL 9z v Estral** — ``kalshi_game_id`` required the team code to START WITH
  A LETTER, and Kalshi writes 9z Globant as ``9Z``. No game id ⇒ every leg
  (GAME, MAP-1/2/3, TOTALMAPS) anchored as a lone ``market`` ⇒ the map legs,
  arriving six hours after the game leg on a clock an hour away, found nothing
  and minted ``15319219`` beside ``15319091``.
* **VALORANT EDG v Global** — the id parsed and GAME + MAP-1/2 shared a game
  anchor on ``15321208`` (the path works); ``KXVALORANTTOTALMAPS`` was simply
  missing from the esports game prefixes (LoL and CS2 both carry theirs), so
  Total Maps anchored as a ``market`` and minted ``15321334`` 8h away.
  Production, 45 days: Valorant Total Maps linked **33 of 201**, its MAP and
  GAME siblings ~59%.

## Why this is not a loosening (ruling 048 / gotcha #32)

The correspondence is a shared PROVIDER id, read verbatim out of Kalshi's ticker
(arm A). No name is compared and no time window opened — the two arms below
join rows an hour and eight hours apart precisely because they never look at
the clock. Tennis stays ``market`` (Alex 2026-08-21), untouched here.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    _sport_id_cache,
    find_or_create_event,
)
from app.utils.prediction_market_matching import kalshi_game_id, kalshi_game_teams
from app.utils.provider_anchor_keys import (
    ANCHOR_KIND_GAME,
    ANCHOR_KIND_MARKET,
    kalshi_anchor_key,
)
from app.utils.sport_keys import is_kalshi_game_level_ticker
from tests.test_anchor_channel_consumer_2213 import _AnchorSession

ESPORTS_SPORT_ID = 70707

# The two production specimens, verbatim.
LOL_GAME = "KXLOLGAME-26SEP2917009ZEST"
LOL_MAPS = (
    "KXLOLMAP-26SEP2917009ZEST-1",
    "KXLOLMAP-26SEP2917009ZEST-2",
    "KXLOLMAP-26SEP2917009ZEST-3",
    "KXLOLTOTALMAPS-26SEP2917009ZEST",
)
VAL_GAME = "KXVALORANTGAME-26OCT020500EDGGE"
VAL_TOTAL = "KXVALORANTTOTALMAPS-26OCT020500EDGGE"


@pytest.fixture(autouse=True)
def _seed_sport_cache():
    _sport_id_cache["esports"] = ESPORTS_SPORT_ID
    yield
    _sport_id_cache.pop("esports", None)


# ══════════════════════════════════════════════════════════════════════════
# The id and the prefix
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("ticker, game_id", [
    (LOL_GAME, "26SEP2917009ZEST"),
    ("KXLOLMAP-26SEP2917009ZEST-2", "26SEP2917009ZEST"),
    ("KXCS2MAP-26SEP0210001WINNEM-1", "26SEP0210001WINNEM"),
    ("KXVALORANTMAP-26SEP041300100TNRG-1", "26SEP041300100TNRG"),
    ("KXCZEFNLGAME-26SEP181SKDUK", "26SEP181SKDUK"),
])
def test_a_team_code_may_begin_with_a_digit(ticker, game_id):
    """🔴 before #9696: all five returned None."""
    assert kalshi_game_id(ticker) == game_id


@pytest.mark.parametrize("ticker, game_id", [
    ("KXNCAAMBGAME-26FEB22IOWAWIS", "26FEB22IOWAWIS"),
    ("KXCS2MAP-26FEB24OMEACE-1", "26FEB24OMEACE"),
    ("KXMLBGAME-26APR291840COLCIN", "26APR291840COLCIN"),
    (VAL_GAME, "26OCT020500EDGGE"),
    ("KXATPMATCH-26AUG30BUBWOL", "26AUG30BUBWOL"),
    # still no id: nothing after the date carries a letter
    ("KXHIGHNY-26SEP29-B75", None),
    ("KXBTC-26SEP2917-T100000", None),
    # still no id: #3198's discipline — no hyphen boundary, no real month
    ("0x26sep29a1b2c3", None),
    ("KXFOO-26XYZ2917009ZEST", None),
])
def test_every_ticker_that_parsed_before_parses_the_same(ticker, game_id):
    """The control: the widening may only ADD ids, never move one."""
    assert kalshi_game_id(ticker) == game_id


def test_the_team_code_reader_is_deliberately_not_widened():
    """Where a digit-led team code starts is ambiguous (``0435HEIF``), and
    ``filter_foreign_game_markets`` keeps a market whose code it cannot parse —
    so it stays None rather than guess."""
    assert kalshi_game_teams(LOL_GAME) is None
    assert kalshi_game_teams(VAL_GAME) == "EDGGE"


def test_valorant_total_maps_is_game_level_like_lol_and_cs2():
    """🔴 before #9696: False, so the leg anchored as a lone market."""
    assert is_kalshi_game_level_ticker(VAL_TOTAL)
    assert is_kalshi_game_level_ticker("KXLOLTOTALMAPS-26SEP2917009ZEST")
    assert is_kalshi_game_level_ticker("KXCS2TOTALMAPS-26SEP0210001WINNEM")


@pytest.mark.parametrize("ticker, segment", [
    (LOL_GAME, "26SEP2917009ZEST"),
    *[(t, "26SEP2917009ZEST") for t in LOL_MAPS],
    (VAL_GAME, "26OCT020500EDGGE"),
    (VAL_TOTAL, "26OCT020500EDGGE"),
])
def test_every_leg_of_a_series_carries_one_game_anchor(ticker, segment):
    key = kalshi_anchor_key(ticker)
    assert (key.source_id, key.id_kind) == (f"esports:{segment}", ANCHOR_KIND_GAME)


def test_tennis_still_anchors_as_a_market():
    """Alex's 2026-08-21 ruling, unchanged."""
    assert kalshi_anchor_key("KXATPMATCH-26AUG30BUBWOL").id_kind == ANCHOR_KIND_MARKET


# ══════════════════════════════════════════════════════════════════════════
# The registry — the reader-visible half
# ══════════════════════════════════════════════════════════════════════════


def _claim(ticker, *, commence, home="9z Globant", away="Estral Esports"):
    """The auto-create claim exactly as `prediction_market_matching` builds it:
    a synthetic `pm_kalshi_` source id, the real ticker as `provider_id`."""
    return EventIdentity(
        sport_key="esports", home_team_name=home, away_team_name=away,
        commence_time=commence,
        claim=EventClaim("kalshi", f"pm_kalshi_{ticker}", provider_id=ticker),
        commence_time_source="kalshi", status="scheduled",
    )


@pytest.mark.asyncio
async def test_lol_map_legs_join_the_game_row_an_hour_away():
    """🔴 before #9696: every map leg CREATED (15319219 beside 15319091)."""
    session = _AnchorSession(sport_id=ESPORTS_SPORT_ID)
    game_row, created = await find_or_create_event(
        session, _claim(LOL_GAME, commence=datetime(2026, 9, 30, 1, 0, tzinfo=timezone.utc))
    )
    assert created is True
    session.by_id[game_row.id] = game_row
    session.event_sports[game_row.id] = ESPORTS_SPORT_ID

    for ticker in LOL_MAPS:
        row, created = await find_or_create_event(
            session, _claim(ticker, commence=datetime(2026, 9, 30, 0, 0, tzinfo=timezone.utc))
        )
        assert (row.id, created) == (game_row.id, False), ticker
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_valorant_total_maps_joins_the_game_row_eight_hours_away():
    """🔴 before #9696: Total Maps CREATED 15321334 beside 15321208."""
    session = _AnchorSession(sport_id=ESPORTS_SPORT_ID)
    kickoff = datetime(2026, 10, 2, 13, 0, tzinfo=timezone.utc)
    game_row, _ = await find_or_create_event(
        session, _claim(VAL_GAME, commence=kickoff,
                        home="EDward Gaming", away="Global Esports")
    )
    session.by_id[game_row.id] = game_row
    session.event_sports[game_row.id] = ESPORTS_SPORT_ID

    row, created = await find_or_create_event(
        session, _claim(VAL_TOTAL, commence=kickoff - timedelta(hours=8),
                        home="EDward Gaming", away="Global Esports")
    )
    assert (row.id, created) == (game_row.id, False)


@pytest.mark.asyncio
async def test_another_series_between_the_same_clubs_still_creates():
    """The refusal arm (gotcha #43): a rematch the next day is a DIFFERENT
    segment, so it gets its own row — the anchor is the id, not the names."""
    session = _AnchorSession(sport_id=ESPORTS_SPORT_ID)
    first, _ = await find_or_create_event(
        session, _claim(LOL_GAME, commence=datetime(2026, 9, 30, 1, 0, tzinfo=timezone.utc))
    )
    session.by_id[first.id] = first
    session.event_sports[first.id] = ESPORTS_SPORT_ID

    rematch, created = await find_or_create_event(
        session, _claim("KXLOLGAME-26SEP3017009ZEST",
                        commence=datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc))
    )
    assert created is True
    assert rematch.id != first.id
