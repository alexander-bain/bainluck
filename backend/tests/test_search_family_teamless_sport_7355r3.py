"""#7355 r3 — a nickname cousin stops riding back onto the ANSWERS card.

WHAT THE READER SAW. `https://bainluck.com/search?q=thunder`, production
`73b384a8`, 2026-09-27 06:3xZ. TEAMS leads with Oklahoma City Thunder, and
ANSWERS card "THUNDER" reads:

    Will Oklahoma City Thunder advance to the Western Conference Finals…
    Will Oklahoma City Thunder advance to the Western Conference Semifinals…
    Will THUNDER TALK GAMING make a roster change by December?
    Will THUNDER TALK GAMING Qualify for Worlds 2026?
    FlyQuest vs. THUNDER dOWNUNDER: Map 2

— then a second card, "Other Sports" (`story:niche_low_signal_sports`), holding
nothing but two Counter-Strike maps. Same shape on `warriors` (two Rogue
Warriors Honor of Kings rows) and `wolves` (one).

THE MECHANISM. r1's `_demote_teamless_sport` works: in the flat `futures` list
every esports row sits below every club row. But `_compose_futures_families`
groups by name match and story key and never asked the teams evidence, so the
rows the demotion sank came straight back as card members.

THE FIX. With the evidence armed, a teamless-sport market joins no family. It
stays in the flat list, sunk. Disarmed (None), the composer is unchanged.

RED-FIRST. Delete the `_is_teamless_sport` line in `_family_key` and
`TestTheThunderSpecimen::test_with_the_evidence_no_card_holds_an_esports_row`
fails on the entity card's member ids.
"""

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes import events as events_module
from app.routes.events import _compose_futures_families


UTC = timezone.utc
NOW = datetime(2026, 9, 27, 6, 30, tzinfo=UTC)  # the specimen's read, fixed

# Oklahoma City Thunder (NBA), Marshall Thundering Herd (NCAAF), Southern Utah
# Thunderbirds, Springfield Thunderbirds — the served TEAMS rows' sports.
THUNDER_TEAM_SPORTS = frozenset({"basketball", "football", "hockey"})


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


OKC_FINALS = 61380727
OKC_SEMIS = 61380759
TTG_ROSTER = 58512486
TTG_WORLDS = 57441836
FLYQUEST_MAP2 = 62400653
CS_MAP2 = 62522586
CS_MAP1 = 62555786
ESPORTS_IDS = {TTG_ROSTER, TTG_WORLDS, FLYQUEST_MAP2, CS_MAP2, CS_MAP1}


def _thunder_candidates():
    """The served family rows, in served (reranked) order."""
    return [
        _market(OKC_FINALS,
                "Will Oklahoma City Thunder advance to the Western Conference "
                "Finals in the 2027 NBA Playoffs?", "basketball", [("No", 0.62)]),
        _market(OKC_SEMIS,
                "Will Oklahoma City Thunder advance to the Western Conference "
                "Semifinals in the 2027 NBA Playoffs?", "basketball", [("No", 0.30)]),
        _market(CS_MAP2, "Counter-Strike: FlyQuest vs THUNDER dOWNUNDER - Map 2 Winner",
                "esports", [("FlyQuest", 0.55), ("THUNDER dOWNUNDER", 0.45)]),
        _market(CS_MAP1, "Counter-Strike: FlyQuest vs THUNDER dOWNUNDER - Map 1 Winner",
                "esports", [("FlyQuest", 0.52), ("THUNDER dOWNUNDER", 0.48)]),
        _market(TTG_ROSTER, "Will THUNDER TALK GAMING make a roster change by December?",
                "esports", [("Yes", 0.20)]),
        _market(TTG_WORLDS, "Will THUNDER TALK GAMING Qualify for Worlds 2026?",
                "esports", [("Yes", 0.10)]),
        _market(FLYQUEST_MAP2, "FlyQuest vs. THUNDER dOWNUNDER: Map 2",
                "esports", [("FlyQuest", 0.50), ("THUNDER dOWNUNDER", 0.50)]),
    ]


def _fmt(m):
    return {"id": m.id, "name": m.name}


def _compose(markets, **kw):
    return _compose_futures_families(
        markets, [("thunder", None)], _fmt, {m.id for m in markets}, **kw
    )


def _shown_ids(fam):
    return [fam["headline"]["id"]] + [m["id"] for m in fam["members"]]


def _all_card_ids(fams):
    return {i for f in fams for i in _shown_ids(f)}


class TestTheThunderSpecimen:
    def test_without_the_evidence_the_cards_hold_esports(self):
        """The BEFORE, reproduced: proves the fixture is the specimen."""
        fams = _compose(_thunder_candidates())
        assert _all_card_ids(fams) & ESPORTS_IDS
        entity = next(f for f in fams if f["family_key"] == "entity:thunder")
        assert _shown_ids(entity)[:2] == [OKC_FINALS, OKC_SEMIS]
        assert set(_shown_ids(entity)[2:]) & ESPORTS_IDS

    def test_with_the_evidence_no_card_holds_an_esports_row(self):
        fams = _compose(_thunder_candidates(), team_sport_categories=THUNDER_TEAM_SPORTS)
        assert not (_all_card_ids(fams) & ESPORTS_IDS)
        (entity,) = fams  # the all-esports "Other Sports" card is gone too
        assert entity["family_key"] == "entity:thunder"
        assert _shown_ids(entity) == [OKC_FINALS, OKC_SEMIS]
        assert entity["member_count"] == 2

    def test_disarmed_evidence_is_byte_identical(self):
        """None is what `_team_evidence_sport_categories` returns on no teams,
        a full window, or an untranslatable sport."""
        assert _compose(_thunder_candidates(), team_sport_categories=None) == _compose(
            _thunder_candidates()
        )


def test_a_sport_a_matched_team_plays_keeps_its_card():
    """`giants`: NFL and MLB clubs both exist — neither sport is a cousin. With
    esports in the evidence, the same esports rows keep their card."""
    with_esports = THUNDER_TEAM_SPORTS | {"esports"}
    assert _compose(_thunder_candidates(), team_sport_categories=with_esports) == _compose(
        _thunder_candidates()
    )


def test_a_non_sport_row_is_not_judged():
    """Politics on a club-name query (`Thunder Bay, ON Mayoral Election`) is not
    a sport cousin; this signal leaves it where it was."""
    rows = _thunder_candidates()[:2] + [
        _market(59520510, "Thunder Bay, ON Mayoral Election Winner", "politics",
                [("A", 0.6), ("B", 0.4)]),
    ]
    assert _compose(rows, team_sport_categories=THUNDER_TEAM_SPORTS) == _compose(rows)


def test_a_family_left_with_one_member_is_not_formed():
    """One club row plus cousins: the card would be a lone answer, so no card —
    and every row is still in the flat list the route ships."""
    rows = _thunder_candidates()[:1] + _thunder_candidates()[4:]
    assert _compose(rows)  # the BEFORE forms a card
    assert _compose(rows, team_sport_categories=THUNDER_TEAM_SPORTS) == []


def test_the_route_passes_the_team_evidence_to_the_composer():
    """The composer defaults to None (disarmed), so the route must pass it."""
    src = inspect.getsource(events_module.search_events)
    call = src[src.index("futures_families = _compose_futures_families("):]
    call = call[: call.index("\n    )\n")]
    assert "team_sport_categories=_team_sport_categories" in call
    assert src.index("_team_sport_categories = _team_evidence_sport_categories(") < src.index(
        "futures_families = _compose_futures_families("
    )
