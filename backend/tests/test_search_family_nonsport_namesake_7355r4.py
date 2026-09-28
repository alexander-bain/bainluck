"""#7355 r4 — a politics namesake stops riding on a club's ANSWERS card.

WHAT THE READER SAW. `GET /api/events/search?q=kings`, production `a0542425`,
2026-09-28 00:4xZ. TEAMS leads with Los Angeles Kings, Sacramento Kings and
Louisville Kings, and the one ANSWERS card, "Kings" (`entity:kings`), reads:

    NHL: LA Kings Total Points                          (hockey)
    Kings County, New York: Kathy Hochul vote percentage (politics)

r3 kept teamless-SPORT rows off the card and said so: "the Kings County politics
row is not a sport cousin", so it stayed. It is a namesake all the same: a
county election on the hockey club's card.

THE FIX. With the teams evidence armed and the entity card's top-ranked row
from a sport one of the matched clubs plays, a row from a house non-sport
category (`NON_SPORT_LLM_CATEGORIES`, minus `other`) leaves the card. It is
still in the flat list, at its own rank. Disarmed, a non-club leader (the
`hurricanes` weather card), a story card, or an `other` row: unchanged.

RED-FIRST. Delete the r4 block in `_compose_futures_families` and
`TestTheKingsSpecimen::test_with_the_evidence_the_card_is_the_clubs` fails on
the card's member ids.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes import events as events_module
from app.routes.events import _compose_futures_families
from app.utils.sport_keys import NON_SPORT_LLM_CATEGORIES

UTC = timezone.utc
NOW = datetime(2026, 9, 28, 0, 45, tzinfo=UTC)  # the specimen's read, fixed

# Los Angeles Kings (NHL), Sacramento Kings (NBA), Louisville Kings (USL),
# Sydney Kings (NBL) — the recalled TEAMS rows' sports.
KINGS_TEAM_SPORTS = frozenset({"hockey", "basketball", "soccer"})


def _outcome(name, prob, oid):
    """Shaped to survive `_search_surviving_legs` (distinct id, real book)."""
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"leg-{oid}",
        current_probability=prob,
        current_odds=None,
        current_american_odds=None,
        current_yes_bid=max(0.01, prob - 0.02),
        current_yes_ask=min(0.99, prob + 0.02),
        previous_probability=None,
        is_winner=None,
        rank=None,
        team_id=None,
    )


def _market(mid, name, cat, legs):
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=f"PM-{mid}",
        llm_sport_category=cat,
        category="game_prop",
        market_tier=5,
        market_type="prop",
        sport=None,
        sport_id=None,
        source="polymarket",
        volume=0.0,
        status="open",
        mutually_exclusive=False,
        resolution_date=(NOW + timedelta(days=30)).date(),
        updated_at=NOW,
        canonical_market_key=None,
        image_url=None,
        hook_description=None,
        group_id=None,
        event_id=None,
        outcomes=[_outcome(n, p, mid * 100 + i) for i, (n, p) in enumerate(legs)],
    )


LAK_POINTS = 60011001
SAC_WINS = 60011002
KINGS_COUNTY = 60011003


def _kings_candidates():
    """The served family rows, in served (reranked) order."""
    return [
        _market(LAK_POINTS, "NHL: LA Kings Total Points", "hockey",
                [("Over 92.5", 0.55)]),
        _market(KINGS_COUNTY, "Kings County, New York: Kathy Hochul vote percentage",
                "politics", [("Above 70%", 0.64), ("Above 75%", 0.41)]),
        _market(SAC_WINS, "NBA: Sacramento Kings 2026-27 Win Total", "basketball",
                [("Over 34.5", 0.48)]),
    ]


def _fmt(m):
    return {"id": m.id, "name": m.name}


def _compose(markets, term="kings", **kw):
    return _compose_futures_families(
        markets, [(term, None)], _fmt, {m.id for m in markets}, **kw
    )


def _shown_ids(fam):
    return [fam["headline"]["id"]] + [m["id"] for m in fam["members"]]


def _entity(fams, term="kings"):
    return next(f for f in fams if f["family_key"] == f"entity:{term}")


class TestTheKingsSpecimen:
    def test_without_the_evidence_the_card_holds_the_county(self):
        """The BEFORE, reproduced: proves the fixture is the specimen."""
        card = _entity(_compose(_kings_candidates()))
        assert KINGS_COUNTY in _shown_ids(card)
        assert card["member_count"] == 3

    def test_with_the_evidence_the_card_is_the_clubs(self):
        fams = _compose(_kings_candidates(), team_sport_categories=KINGS_TEAM_SPORTS)
        card = _entity(fams)
        assert _shown_ids(card) == [LAK_POINTS, SAC_WINS]
        assert card["member_count"] == 2
        assert all(KINGS_COUNTY not in _shown_ids(f) for f in fams)

    def test_the_production_pair_forms_no_card(self):
        """Production had exactly two rows: the hockey one and the county. With
        the county gone the card would be a lone answer, so there is no card,
        and both rows are still in the flat list the route ships."""
        pair = _kings_candidates()[:2]
        assert _compose(pair)  # the BEFORE forms the card
        assert _compose(pair, team_sport_categories=KINGS_TEAM_SPORTS) == []


def test_disarmed_evidence_is_byte_identical():
    assert _compose(_kings_candidates(), team_sport_categories=None) == _compose(
        _kings_candidates()
    )


def test_a_card_with_no_club_row_is_left_alone():
    """`georgia`: clubs exist, but a card of nothing but election rows is a
    politics card, not a club card with a namesake in it."""
    rows = [
        _market(70000001, "Georgia, US: Jon Ossoff vote percentage", "politics",
                [("Above 50%", 0.55)]),
        _market(70000002, "Georgia turnout above 60%?", "politics", [("Yes", 0.40)]),
    ]
    armed = _compose(rows, term="georgia", team_sport_categories=frozenset({"football"}))
    assert armed == _compose(rows, term="georgia")
    # Not a story card: these rows reach the ENTITY card, so this is the arm
    # the club-row condition protects.
    assert _shown_ids(_entity(armed, "georgia")) == [70000001, 70000002]


def test_a_card_led_by_a_non_sport_row_keeps_its_club_row_and_namesakes():
    """`hurricanes`, production 2026-09-28: the card leads with Atlantic-season
    rows. One Carolina row ranked below must not turn it into the hockey club's
    card; r4 removes rows that contradict the card's leader, never the leader's
    own kind."""
    rows = [
        _market(70000011, "How many major Atlantic hurricanes will there be in 2026?",
                "weather", [("3", 0.40)]),
        _market(70000012, "How many hurricanes will form during the Atlantic season?",
                "weather", [("7", 0.30)]),
        _market(70000013, "NHL: Carolina Hurricanes Total Points", "hockey",
                [("Over 100.5", 0.52)]),
    ]
    armed = _compose(rows, term="hurricanes", team_sport_categories=frozenset({"hockey"}))
    assert armed == _compose(rows, term="hurricanes")
    assert _shown_ids(_entity(armed, "hurricanes")) == [70000011, 70000012, 70000013]


def test_other_is_never_judged():
    """`other` is the classifier's shrug and holds sports rows (sumo, sailing
    and cycling sit outside the sport set too), so it keeps its card."""
    rows = _kings_candidates()[:1] + [
        _market(70000003, "Kings of Leon to headline a halftime show?", "other",
                [("Yes", 0.10)]),
    ]
    armed = _compose(rows, team_sport_categories=KINGS_TEAM_SPORTS)
    assert armed == _compose(rows)
    assert _shown_ids(_entity(armed)) == [LAK_POINTS, 70000003]


def test_every_house_non_sport_category_but_other_is_a_namesake():
    """The set is the house predicate, not a local list that can drift."""
    assert events_module._SEARCH_NAMESAKE_NON_SPORT_CATEGORIES == (
        NON_SPORT_LLM_CATEGORIES - {"other"}
    )
    for cat in sorted(NON_SPORT_LLM_CATEGORIES - {"other"}):
        rows = _kings_candidates()[:1] + _kings_candidates()[2:] + [
            _market(70000100, "Kings County namesake row", cat, [("Yes", 0.5)]),
        ]
        card = _entity(_compose(rows, team_sport_categories=KINGS_TEAM_SPORTS))
        assert 70000100 not in _shown_ids(card), cat
