"""#8278: a rescheduled game's second Odds API id finds its row instead of minting a twin.

Specimen (production, 2026-09-23): Blue Jays @ Orioles, the makeup of Tuesday's
rainout. Row 15316846 carries `external_id = 7fafa79a…` (Tuesday's Odds API id).
The Odds API re-minted the rescheduled game as `cc3886…`, and
`odds_api:cc3886… -> 15316846` sits in `event_provider_anchors`, beside
`odds_api:7fafa79a… -> 15316846`. At 20:01Z a `cc3886…` claim reached Step 2.
CERT-410's rule read the anchor as stale, because the column holds the other id,
and Step 4 created 15317985. The twin took ESPN's makeup id, so game 1's own card
froze at 0–0 while the game went 4–2.

The rule under test is :data:`app.services.anchor_channel.MULTI_ID_SCALAR_SOURCES`.
An Odds API anchor that disagrees with its row's column is current ONLY when the
column's own id is anchored to that same row. Everything else keeps CERT-410's
refusal, and the ESPN class that CERT-410 was written for is pinned unchanged
below.
"""
from __future__ import annotations

import pytest

from app.services.anchor_channel import (
    MULTI_ID_SCALAR_SOURCES,
    anchor_key_for_claim,
    anchor_is_current,
    find_event_by_anchor,
)
from app.services.event_registry import find_or_create_event
from app.utils.provider_anchor_keys import ANCHOR_KIND_GAME
from tests.test_anchor_channel_consumer_2213 import (  # noqa: F401 (fixture)
    MLB_SPORT_ID,
    _AnchorSession,
    _identity,
    _row,
    _seed_sport_cache,
)

GAME_ONE_ROW = 15316846
TWIN_ROW = 15317985
TUESDAY_ODDS_ID = "7fafa79a573ac098f38c8c6c4293b93e"
MAKEUP_ODDS_ID = "cc3886440708c8649f6f878183416628"


def _session(*, rows, anchors):
    return _AnchorSession(
        anchors=anchors,
        event_sports={r.id: MLB_SPORT_ID for r in rows},
        structured_candidates=list(rows),
        sport_id=MLB_SPORT_ID,
    )


def _odds(source_id):
    return ("odds_api", source_id, ANCHOR_KIND_GAME)


class TestTheSecondOddsIdFindsItsRow:

    @pytest.mark.asyncio
    async def test_the_makeup_id_resolves_to_game_one_and_creates_nothing(self):
        game_one = _row(event_id=GAME_ONE_ROW, external_id=TUESDAY_ODDS_ID)
        session = _session(
            rows=[game_one],
            anchors={
                _odds(TUESDAY_ODDS_ID): GAME_ONE_ROW,
                _odds(MAKEUP_ODDS_ID): GAME_ONE_ROW,
            },
        )

        assert await find_event_by_anchor(
            session,
            anchor_key_for_claim("odds_api", MAKEUP_ODDS_ID),
            expected_sport_id=MLB_SPORT_ID,
        ) == GAME_ONE_ROW

        event, created = await find_or_create_event(
            session, _identity("odds_api", MAKEUP_ODDS_ID)
        )
        assert created is False, (
            "the 20:01Z twin: a second Odds id for a row that owns both ids must "
            "land on that row, not mint 15317985"
        )
        assert event.id == GAME_ONE_ROW
        assert game_one.external_id == TUESDAY_ODDS_ID, (
            "the column keeps its id; the second id lives in the anchor table"
        )


class TestEveryOtherDisagreementIsStillStale:

    @pytest.mark.asyncio
    async def test_a_column_id_anchored_to_a_different_row_refuses(self):
        game_one = _row(event_id=GAME_ONE_ROW, external_id=TUESDAY_ODDS_ID)
        other = _row(event_id=TWIN_ROW, external_id="someone-else")
        session = _session(
            rows=[game_one, other],
            anchors={
                _odds(TUESDAY_ODDS_ID): TWIN_ROW,
                _odds(MAKEUP_ODDS_ID): GAME_ONE_ROW,
            },
        )
        assert await anchor_is_current(
            session, anchor_key_for_claim("odds_api", MAKEUP_ODDS_ID), GAME_ONE_ROW
        ) is False

    @pytest.mark.asyncio
    async def test_an_unanchored_column_id_refuses(self):
        game_one = _row(event_id=GAME_ONE_ROW, external_id=TUESDAY_ODDS_ID)
        session = _session(
            rows=[game_one], anchors={_odds(MAKEUP_ODDS_ID): GAME_ONE_ROW},
        )
        assert await anchor_is_current(
            session, anchor_key_for_claim("odds_api", MAKEUP_ODDS_ID), GAME_ONE_ROW
        ) is False

        _event, created = await find_or_create_event(
            session, _identity("odds_api", MAKEUP_ODDS_ID)
        )
        assert created is True, (
            "no evidence the row owns both ids, so CERT-410's refusal stands"
        )

    @pytest.mark.asyncio
    async def test_an_empty_column_refuses(self):
        cleared = _row(event_id=GAME_ONE_ROW, external_id=None)
        session = _session(
            rows=[cleared], anchors={_odds(MAKEUP_ODDS_ID): GAME_ONE_ROW},
        )
        assert await anchor_is_current(
            session, anchor_key_for_claim("odds_api", MAKEUP_ODDS_ID), GAME_ONE_ROW
        ) is False


class TestCert410IsUnchangedForTheReKeyedColumns:
    """ESPN's column IS re-keyed (`repair_event_espn_id`). There, a disagreeing
    anchor is a disproof even when the row's current id is anchored to it too,
    which is exactly the state a re-key leaves behind."""

    @pytest.mark.asyncio
    async def test_an_old_espn_id_still_refuses_with_the_new_one_anchored(self):
        rekeyed = _row(event_id=GAME_ONE_ROW, espn_id="401923610")
        session = _session(
            rows=[rekeyed],
            anchors={
                ("espn", "401817035", ANCHOR_KIND_GAME): GAME_ONE_ROW,
                ("espn", "401923610", ANCHOR_KIND_GAME): GAME_ONE_ROW,
            },
        )
        assert await anchor_is_current(
            session, anchor_key_for_claim("espn", "401817035"), GAME_ONE_ROW
        ) is False

    def test_only_the_odds_api_is_multi_id(self):
        assert MULTI_ID_SCALAR_SOURCES == frozenset({"odds_api"})
