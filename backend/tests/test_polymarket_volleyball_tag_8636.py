"""#8636 follow-up 2 — a Polymarket volleyball match stops becoming a soccer game of ours.

Production, 390px, 2026-09-27: ``/search?q=italy`` lists **UEFA NATIONS LEAGUE ·
Italy v Slovenia · No result reported · Sep 17**. It is the Volleyball European
Championship (Gamma ``vbeuro-ita2-slo4-2026-09-17``). Read against Gamma's own
``tag_slug=volleyball`` listing, 55 of our events since July were minted from
volleyball markets — on ``soccer_other``, ``baseball_other``,
``americanfootball_other`` and ``basketball_other``, five placed into the Nations
League — and one more (Tub Bocholt v FC Schüttorf 09, ``vb2bundesliga``) on
2026-09-26, after #8636's placement fix was live.

The venue tags every one ``Volleyball`` and `_TAG_TO_CATEGORY` had no such key,
so the tag loop fell through to ``Sports`` and the sport was guessed from the
names: ``FC Schüttorf 09`` reads as soccer. Same shape as #8507 (chess), Q493
(table tennis) and #6651 (pickleball), and the same fix: honour the venue's tag
with a category that has no sport-key prefix, so it labels the card and mints
nothing.

Specimens start from RAW Gamma tag objects (CERT-2924: `_parse_event` stores the
LABEL), verbatim from Gamma 2026-09-27, trimmed to the fields the parser reads.
"""

import copy

import pytest

from app.tasks.polymarket import (
    _SPORT_CATEGORIES,
    _TAG_TO_CATEGORY,
    _tags_to_category,
    resolve_event_category,
)
from app.utils.prediction_market_matching import auto_create_sport_key_from_category
from app.utils.sport_keys import LLM_CATEGORY_TO_SPORT_PREFIX


def _gamma_tag(label, slug, tag_id):
    return {"id": tag_id, "label": label, "slug": slug, "forceShow": False}


SPORTS = _gamma_tag("Sports", "sports", "1")
GAMES = _gamma_tag("Games", "games", "100639")
VOLLEYBALL = _gamma_tag("Volleyball", "volleyball", "102412")


def _market(mid, question):
    return {
        "id": mid,
        "question": question,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.5", "0.5"]',
        "conditionId": f"0x{int(mid):064x}",
        "active": True,
    }


GAMMA_EVENTS = {
    # The /search?q=italy card: placed into the UEFA Nations League.
    "vbeuro_italy_slovenia": {
        "id": "1037992",
        "title": "Italy vs. Slovenia",
        "slug": "vbeuro-ita2-slo4-2026-09-17",
        "tags": [
            SPORTS,
            GAMES,
            VOLLEYBALL,
            _gamma_tag("Volleyball European Championship", "vbeuro", "103001"),
        ],
        "markets": [
            _market("1400001", "Italy vs. Slovenia"),
            _market("1400002", "Set Handicap: Italy (-1.5) vs Slovenia (+1.5)"),
            _market("1400003", "Italy vs. Slovenia: Total Sets O/U 3.5"),
        ],
    },
    # Minted on soccer_other on 2026-09-26 (event 15318806), after #8636 was live.
    "vb2bundesliga_bocholt_schuttorf": {
        "id": "1080303",
        "title": "Tub Bocholt vs. FC Schüttorf 09",
        "slug": "vb2bundesliga-tub-fc-2026-09-26",
        "tags": [
            SPORTS,
            GAMES,
            VOLLEYBALL,
            _gamma_tag("Volleyball 2. Bundesliga", "vb2bundesliga", "103050"),
        ],
        "markets": [_market("1400010", "Tub Bocholt vs. FC Schüttorf 09")],
    },
    # July's Volleyball Nations League, minted on baseball_other (15179607).
    "vbvnl_italy_usa": {
        "id": "739849",
        "title": "Italy vs. USA",
        "slug": "vbvnl-ita-usa-2026-07-30",
        "tags": [
            SPORTS,
            GAMES,
            VOLLEYBALL,
            _gamma_tag("Volleyball Nations League", "vbvnl", "102990"),
        ],
        "markets": [_market("1400020", "Italy vs. USA")],
    },
}

#: What the cascade answered before the tag was read. `soccer` is the defect
#: that minted 15318806; `None` leaves the sport to the null-only enrichment,
#: which is how the Nations League children came to read soccer.
BEFORE = {
    "vbeuro_italy_slovenia": None,
    "vb2bundesliga_bocholt_schuttorf": "soccer",
    "vbvnl_italy_usa": None,
}


def _parse_payload(payload):
    from app.services.polymarket_api import PolymarketAPIService

    return PolymarketAPIService()._parse_event(payload)


def _resolve_event(event):
    """Drive the cascade the way `_process_event_batch` does."""
    return resolve_event_category(
        *_tags_to_category(event.tags),
        event.title,
        [event.title] + [m.question for m in event.markets],
    )


@pytest.mark.parametrize("key", sorted(GAMMA_EVENTS))
def test_the_volleyball_tag_names_the_sport_8636(key):
    """THE SHIP: raw Gamma bytes -> parser -> cascade -> volleyball, by the tag."""
    category, sport, arm = _resolve_event(_parse_payload(GAMMA_EVENTS[key]))
    assert sport == "volleyball"
    assert category == "championship"
    assert arm == "tag"


@pytest.mark.parametrize("key", sorted(GAMMA_EVENTS))
def test_stripping_the_volleyball_tag_returns_the_production_defect(key):
    """Strawman: without the tag each specimen lands where production had it."""
    payload = copy.deepcopy(GAMMA_EVENTS[key])
    payload["tags"] = [t for t in payload["tags"] if t["slug"] != "volleyball"]
    _, sport, _ = _resolve_event(_parse_payload(payload))
    assert sport == BEFORE[key]


@pytest.mark.parametrize("key", sorted(GAMMA_EVENTS))
def test_a_volleyball_fixture_cannot_mint_an_event(key):
    """The category the tag yields opens no rail: no prefix, no `<x>_other` row."""
    _, sport, _ = _resolve_event(_parse_payload(GAMMA_EVENTS[key]))
    assert LLM_CATEGORY_TO_SPORT_PREFIX.get(sport) is None
    assert auto_create_sport_key_from_category(sport) is None


def test_the_strawman_category_did_mint():
    """Control for the arm above: the pre-fix `soccer` answer DOES open a rail."""
    assert auto_create_sport_key_from_category("soccer") == "soccer_other"


@pytest.mark.parametrize("tag", ["Volleyball", "volleyball", "VOLLEYBALL"])
def test_the_tag_matches_whatever_case_the_venue_sends(tag):
    assert _tags_to_category(["Sports", "Games", tag]) == ("championship", "volleyball")


def test_the_tag_mapping_yields_the_championship_category():
    mapped = _TAG_TO_CATEGORY["volleyball"]
    assert mapped in _SPORT_CATEGORIES
    assert _tags_to_category(["Sports", "Volleyball"]) == ("championship", mapped)


def test_a_real_soccer_event_is_untouched():
    """Control: a Nations League soccer game (Gamma tags Sports, Games, Soccer, UNL)."""
    assert _tags_to_category(["Sports", "Games", "Soccer", "UEFA Nations League"]) == (
        "championship",
        "soccer",
    )
