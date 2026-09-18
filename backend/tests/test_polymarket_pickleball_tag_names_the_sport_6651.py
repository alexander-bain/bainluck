"""#6651 — the PPA Tour card names its sport instead of saying "Markets".

From Alex's 2026-09-16 phone test (#6444): *"Attractive 2027 PPA Tour finals for
women card never explains its sport/league."*

The card could not explain it, because the row had nothing to say. Measured on
the served payload 2026-09-17, `llm_sport_category`, `sport` and `sport_name`
are all NULL, and `frontend/components/discover/FuturesCard.tsx:130` reads::

    const category = data.sport_name || data.llm_sport_category || "Markets";

so the chip on a first-page card rendered the literal word **Markets**.

🔴 THE VENUE KNEW. Read off Gamma 2026-09-17, all three live PPA events carry
the sport as their own tag — labels ``['PPA', 'Sports', 'Pickleball']``. The
key was simply absent from ``_TAG_TO_CATEGORY``, so the specific-tag loop
missed, the ``sports`` arm returned ``(championship, None)``, and arm 2's
``categorize_by_rules`` / ``detect_league`` found nothing in "2027 PPA Tour
Finals…". Measured before the fix, on all four production titles:
``('championship', None, 'fallback')``.

This is the Q493 (`table tennis`) and #6411 (`afl`/`aflw`) shape a third time —
the venue named the sport and we inferred instead — with one difference worth
stating, because it changes what the strawman guard can assert: the AFL
fallback GUESSED WRONG (club nicknames read as basketball), whereas this one
DECLINES. That is why the defect is a NULL rather than a mislabel, and why the
untagged arm below asserts ``None`` rather than a wrong sport.

POPULATION 2026-09-17, and the split is by status rather than by row — which is
what makes this worth a fix at the source rather than a backfill::

    polymarket  open      (NULL)       178      <- every row a reader can meet
    polymarket  resolved  pickleball   141
    polymarket  resolved  tennis        18
    polymarket  open      pickleball     5

So ``pickleball`` is not a new value being minted here. It is the one this
family already settles on once anything classifies it; the live cohort is
simply the half that never got classified. And ``polymarket.py`` writes
``llm_sport_category`` unconditionally on update (no coalesce guard, unlike the
Kalshi poller), so the next poll repairs those 178 rows itself — this ship
needs no backfill and no attended production write.

GUARD DESIGN. Two lessons are inherited deliberately:

* CERT-2924 (`6411-READ-AFL-WOMEN-VENUE-LABEL`): *a test that builds its own
  input cannot discover that the field it read is not the field the code
  reads.* ``_parse_event`` stores ``tag.get("label", "")``, so the arms below
  start from RAW GAMMA TAG OBJECTS and run the shipped parser. Here label and
  slug happen to agree (``Pickleball`` / ``pickleball``), but that is a fact to
  assert, not to assume — the AFL women's code is the counter-example.
* Q493: delete the fix's ambient recovery, so a partial revert cannot pass.
  ``test_without_the_tag_the_sport_is_still_unknown`` fails the moment anything
  else starts answering, at which point the arms above stop proving the tag did
  the work.
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
    """A Gamma tag object, shaped as the API actually sends it."""
    return {"id": tag_id, "label": label, "slug": slug, "forceShow": None}


# Verbatim from Gamma 2026-09-17. All three of the venue's live PPA events, so
# the men's/women's split Alex's report named is carried in the specimen rather
# than tidied into one case. Tag ORDER is part of the specimen: `PPA` (an
# unmapped tour) leads, and `Sports` — the catch-all that produced the NULL —
# sits ahead of the sport tag on every one.
GAMMA_EVENTS = {
    "semis_mens": {
        "id": "1024935",
        "title": "2027 PPA Tour Finals: To Reach Semifinals (Men's)",
        "slug": "2027-ppa-tour-finals-to-reach-semifinals-mens",
        "tags": [
            _gamma_tag("PPA", "ppa", "103086"),
            _gamma_tag("Sports", "sports", "1"),
            _gamma_tag("Pickleball", "pickleball", "102471"),
        ],
        "markets": [
            {
                "id": "4567064",
                "question": "Will Ben Johns reach the Semifinals of the 2027 PPA Tour Finals?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.62", "0.38"]',
                "conditionId": "0x736e02a8f648dbc74f65acb861c4a6694ef9b0455b61a62ff8a991ef124a94a0",
                "active": True,
            }
        ],
    },
    "qualify_mens": {
        "id": "1024933",
        "title": "2027 PPA Tour Finals: Player to Qualify (Men's)",
        "slug": "2027-ppa-tour-finals-player-to-qualify-mens",
        "tags": [
            _gamma_tag("PPA", "ppa", "103086"),
            _gamma_tag("Sports", "sports", "1"),
            _gamma_tag("Pickleball", "pickleball", "102471"),
        ],
        "markets": [
            {
                "id": "4567032",
                "question": "Will Ben Johns qualify for the 2027 PPA Tour Finals?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.84", "0.16"]',
                "conditionId": "0x90848db81ecba177113c6dfdc7e5bad4e547a52978da3a15972fe024221f112e",
                "active": True,
            }
        ],
    },
    # The card in Alex's report — the women's field.
    "qualify_womens": {
        "id": "1024934",
        "title": "2027 PPA Tour Finals: Player to Qualify (Women's)",
        "slug": "2027-ppa-tour-finals-player-to-qualify-womens",
        "tags": [
            _gamma_tag("PPA", "ppa", "103086"),
            _gamma_tag("Sports", "sports", "1"),
            _gamma_tag("Pickleball", "pickleball", "102471"),
        ],
        "markets": [
            {
                "id": "4567045",
                "question": "Will Anna Leigh Waters qualify for the 2027 PPA Tour Finals?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.945", "0.055"]',
                "conditionId": "0x215c358d7c0e379a95eaeb940ae19caa034ee820137522584ce662bf9b1557f1",
                "active": True,
            }
        ],
    },
}

ALL_EVENTS = tuple(GAMMA_EVENTS)

# The four production titles the cascade was measured against before the fix,
# every one of them landing ('championship', None, 'fallback'). The fourth is a
# 2026 tournament row, included so the strawman arm covers the naming shape the
# RESOLVED cohort uses as well as the 2027 Finals shape.
MEASURED_NULL_TITLES = (
    "2027 PPA Tour Finals: To Reach Semifinals (Men's)",
    "2027 PPA Tour Finals: Player to Qualify (Men's)",
    "2027 PPA Tour Finals: Player to Qualify (Women's)",
    "2026 PPA: Carvana Mesa Cup (Mixed Doubles) Winner",
)


def _parse(key):
    """Run the SHIPPED parser over a verbatim Gamma event."""
    from app.services.polymarket_api import PolymarketAPIService

    return PolymarketAPIService()._parse_event(GAMMA_EVENTS[key])


def _resolve_event(event):
    """Drive the cascade the way `_process_polymarket_events` does."""
    return resolve_event_category(
        *_tags_to_category(event.tags),
        event.title,
        [event.title] + [m.question for m in event.markets],
    )


# --------------------------------------------------------------------------
# The ship — the card has a sport to name
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", ALL_EVENTS)
def test_the_venue_tag_gives_the_ppa_card_its_sport_6651(key):
    """THE SHIP: raw Gamma bytes -> parser -> cascade -> a named sport.

    `llm_sport_category` is what `FuturesCard` falls back to before the literal
    "Markets", so this assertion is the difference between a card that says
    what it is and one that does not.
    """
    category, sport, arm = _resolve_event(_parse(key))

    assert sport == "pickleball"
    # NOT ("pickleball", "pickleball"). The internal category must stay
    # `championship` — what the 141 already-classified rows of this family
    # carry. This is the arm that catches dropping `pickleball` from
    # `_SPORT_CATEGORIES`.
    assert category == "championship"
    # And the ops counter stays honest: the TAG decided, not a guess.
    assert arm == "tag"


@pytest.mark.parametrize("key", ALL_EVENTS)
def test_the_parser_keeps_the_label_not_the_slug(key):
    """CERT-2924's premise, asserted so it can never be assumed again.

    Label and slug agree for this tag today. The AFL women's code is why that
    is checked rather than trusted: there, `label='AFL Women'` and
    `slug='aflw'`, and a test written against the slug went green while
    production matched nothing.
    """
    assert _parse(key).tags == ["PPA", "Sports", "Pickleball"]


# --------------------------------------------------------------------------
# The tag is the ONLY thing that can produce the answer
# --------------------------------------------------------------------------


@pytest.mark.parametrize("title", MEASURED_NULL_TITLES)
def test_without_the_tag_the_sport_is_still_unknown(title):
    """The strawman guard — removes the fix's ambient recovery.

    Unlike the AFL case, the fallback here does not guess wrong; it declines.
    That decline is the defect, and it must stay reproducible: if this ever
    starts answering `pickleball`, the arms above no longer prove the tag did
    anything and this file needs rewriting rather than trusting.
    """
    category, sport, arm = resolve_event_category(
        *_tags_to_category(["PPA", "Sports"]), title, [title]
    )
    assert (sport, arm) == (None, "fallback")
    assert category == "championship"


def test_stripping_the_pickleball_tag_from_the_real_payload_returns_the_defect():
    """The same guard, driven from the venue payload rather than a title.

    Fails the moment the `pickleball` entry is dropped, and cannot be rescued
    by the `PPA` or `Sports` tags that remain.
    """
    payload = copy.deepcopy(GAMMA_EVENTS["qualify_womens"])
    payload["tags"] = [t for t in payload["tags"] if t["slug"] != "pickleball"]

    from app.services.polymarket_api import PolymarketAPIService

    event = PolymarketAPIService()._parse_event(payload)
    assert "Pickleball" not in event.tags

    _, sport, arm = _resolve_event(event)
    assert (sport, arm) == (None, "fallback")


@pytest.mark.parametrize("tag", ["Pickleball", "pickleball", "PICKLEBALL"])
def test_the_tag_matches_whatever_case_the_venue_sends(tag):
    """`_tags_to_category` lowercases before the lookup; the key must survive it."""
    assert _tags_to_category(["PPA", "Sports", tag]) == ("championship", "pickleball")


# --------------------------------------------------------------------------
# The relation arms — assert the wiring, never restate the constants
# --------------------------------------------------------------------------


def test_the_tag_mapping_yields_the_championship_category():
    """The `_TAG_TO_CATEGORY` -> `_SPORT_CATEGORIES` relation for the new key.

    Stated as the relation the two maps must satisfy rather than as a literal,
    so it cannot pass by being edited to agree with the source.
    """
    mapped = _TAG_TO_CATEGORY["pickleball"]
    assert mapped in _SPORT_CATEGORIES
    assert _tags_to_category(["Sports", "Pickleball"]) == ("championship", mapped)


def test_pickleball_cannot_mint_an_event_for_a_sport_we_run_no_fixtures_for():
    """The safety property that makes this a LABEL and not a matching rail.

    `auto_create_sport_key_from_category` returns None for a category with no
    `LLM_CATEGORY_TO_SPORT_PREFIX` key, so honouring the tag cannot create a
    `pickleball_other` phantom event. Asserted as the chain rather than as
    "None", so that adding a prefix later cannot silently open event creation
    without this test having an opinion about it.
    """
    category = _TAG_TO_CATEGORY["pickleball"]
    assert LLM_CATEGORY_TO_SPORT_PREFIX.get(category) is None
    assert auto_create_sport_key_from_category(category) is None


def test_pickleball_is_not_filed_as_tennis():
    """notice 40's wrong-sport attachment, at the one place it could happen.

    Kalshi files its pickleball series under `tags: ["Tennis"]`
    (`sport_keys.py`, KXPICKLEBALLMATCH), and 18 resolved rows of this very
    family carry `tennis`. Polymarket names the sport properly, so our value
    must be the sport itself — a pickleball market must never land on the
    tennis shelf through this map.
    """
    assert _TAG_TO_CATEGORY["pickleball"] != _TAG_TO_CATEGORY["tennis"]
    assert _tags_to_category(["Sports", "Pickleball"])[1] != "tennis"


def test_a_real_tennis_market_is_untouched():
    """The control: the neighbouring racquet sport keeps its own answer."""
    assert _resolve_event(
        type(
            "E",
            (),
            {
                "tags": ["Sports", "Tennis"],
                "title": "Carlos Alcaraz vs. Jannik Sinner",
                "markets": [],
            },
        )()
    ) == ("championship", "tennis", "tag")


def test_the_tour_tag_is_not_mapped_to_a_sport():
    """`PPA` is the tour, not the sport, and the sport tag is on every event.

    Pinned so a later widening has to argue for itself: mapping a tour name
    would reach any event the venue happens to tag with it, including ones
    whose sport tag disagrees.
    """
    assert "ppa" not in _TAG_TO_CATEGORY
