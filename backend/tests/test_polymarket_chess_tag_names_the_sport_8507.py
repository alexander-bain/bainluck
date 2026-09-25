"""#8507 — chess markets name chess, and the Chess Olympiad leaves /hub/esports.

Production, 390px, 2026-09-25 01:50Z: `/hub/esports` listed **46th FIDE Chess
Olympiad Open Tournament Winner** as its 14th futures card, and the five open
Titled Tuesday parents plus their children carried `llm_sport_category = NULL`.

The venue tags every chess event ``Chess`` and `_TAG_TO_CATEGORY` had no
``chess`` key, so the loop skipped it and returned on the next tag it knew —
``Esports`` for the Olympiad, nothing for Titled Tuesday. Same shape as Q493
(table tennis), #6411 (AFL) and #6651 (pickleball).

The specimens below start from RAW Gamma tag objects (CERT-2924: `_parse_event`
stores the LABEL, so a test that builds its own tag strings cannot see a
label/slug disagreement), trimmed to the fields the parser reads.
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


CHESS = _gamma_tag("Chess", "chess", "256")
SPORTS = _gamma_tag("Sports", "sports", "1")
ESPORTS = _gamma_tag("Esports", "esports", "64")

# Verbatim tag order from Gamma 2026-09-25. Order is part of the specimen: the
# Olympiad's `Esports` sits AFTER `Chess`; Titled Tuesday leads with `Sports`.
GAMMA_EVENTS = {
    "olympiad": {
        "id": "775267",
        "title": "46th FIDE Chess Olympiad Open Tournament Winner",
        "slug": "46th-fide-chess-olympiad-open-tournament-winner-20260716211453703",
        "tags": [CHESS, SPORTS, ESPORTS],
        "markets": [
            {
                "id": "3235948",
                "question": "Will United States of America win the 46th FIDE Chess Olympiad Open Tournament?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.0695", "0.9305"]',
                "conditionId": "0xb1a67b00d51ba602459c39b64f6a6798fcc03c03a634af9fa3febe584b6d0d2d",
                "active": True,
            }
        ],
    },
    "titled_tuesday": {
        "id": "1064637",
        "title": "Titled Tuesday Winner: September 29",
        "slug": "titled-tuesday-2026-09-29-winner",
        "tags": [
            SPORTS,
            CHESS,
            _gamma_tag("Titled Tuesday", "titled-tuesday", "105791"),
            _gamma_tag("Recurring", "recurring", "101757"),
        ],
        "markets": [
            {
                "id": "4844592",
                "question": "Will Magnus Carlsen win Titled Tuesday on September 29?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.115", "0.885"]',
                "conditionId": "0xc166eae5e04bca09579c6533f66a15190c0cbd22244e0a8561773764962613e8",
                "active": True,
            }
        ],
    },
}

# What production stored before the fix, per specimen.
BEFORE = {"olympiad": "esports", "titled_tuesday": None}


def _parse_payload(payload):
    from app.services.polymarket_api import PolymarketAPIService

    return PolymarketAPIService()._parse_event(payload)


def _resolve_event(event):
    """Drive the cascade the way `_process_polymarket_events` does."""
    return resolve_event_category(
        *_tags_to_category(event.tags),
        event.title,
        [event.title] + [m.question for m in event.markets],
    )


@pytest.mark.parametrize("key", sorted(GAMMA_EVENTS))
def test_the_chess_tag_names_the_sport_8507(key):
    """THE SHIP: raw Gamma bytes -> parser -> cascade -> chess, decided by the tag."""
    category, sport, arm = _resolve_event(_parse_payload(GAMMA_EVENTS[key]))
    assert sport == "chess"
    # What the 160 resolved chess `championship` rows carry — not ("chess", "chess").
    assert category == "championship"
    assert arm == "tag"


@pytest.mark.parametrize("key", sorted(GAMMA_EVENTS))
def test_the_parser_keeps_the_chess_label(key):
    assert "Chess" in _parse_payload(GAMMA_EVENTS[key]).tags


@pytest.mark.parametrize("key", sorted(GAMMA_EVENTS))
def test_stripping_the_chess_tag_returns_the_production_defect(key):
    """Strawman: without the tag, each specimen lands exactly where production had it.

    If this stops reproducing, something else started answering and the ship
    arm above no longer proves the tag did the work.
    """
    payload = copy.deepcopy(GAMMA_EVENTS[key])
    payload["tags"] = [t for t in payload["tags"] if t["slug"] != "chess"]
    _, sport, _ = _resolve_event(_parse_payload(payload))
    assert sport == BEFORE[key]


def test_the_olympiad_leaves_esports():
    """The reader-visible half: the Olympiad no longer qualifies for /hub/esports."""
    _, sport, _ = _resolve_event(_parse_payload(GAMMA_EVENTS["olympiad"]))
    assert sport != "esports"


def test_a_real_esports_event_is_untouched():
    """Control: LoL Worlds (Gamma 2026-09-25 tags lol, Sports, Esports, league of legends)."""
    assert _tags_to_category(["lol", "Sports", "Esports", "league of legends"]) == (
        "championship",
        "esports",
    )


@pytest.mark.parametrize("tag", ["Chess", "chess", "CHESS"])
def test_the_tag_matches_whatever_case_the_venue_sends(tag):
    assert _tags_to_category(["Sports", tag]) == ("championship", "chess")


def test_the_tag_mapping_yields_the_championship_category():
    mapped = _TAG_TO_CATEGORY["chess"]
    assert mapped in _SPORT_CATEGORIES
    assert _tags_to_category(["Sports", "Chess"]) == ("championship", mapped)


def test_chess_cannot_mint_an_event():
    """A label, not a matching rail: no sport-key prefix, so no phantom events."""
    category = _TAG_TO_CATEGORY["chess"]
    assert LLM_CATEGORY_TO_SPORT_PREFIX.get(category) is None
    assert auto_create_sport_key_from_category(category) is None
