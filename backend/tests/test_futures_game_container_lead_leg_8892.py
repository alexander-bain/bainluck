"""#8892 — a game container's page names the leg that answers "who wins".

WHAT A READER SAW. ``/futures/61778284`` at 390px, 2026-09-26 18:49Z — "LoL:
Cloud9 vs Team Liquid (BO5) - LCS Playoffs" heroed **"71% Over — O/U 3.5
Games"**. The match winner ("Cloud9 — Match Winner 36%") was row 6. Clients hero
the highest-priced outcome, and on a container that compares unrelated questions.

The payload now names the match-winner leg as ``lead_outcome_id``. The leg is
typed by its sibling row's stored #5273 understanding, and it leads only when our
classifier and the venue BOTH say full-contest winner. The production sibling
rows below are copied from the specimen (db-query, 18:5xZ 9/26).
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes import futures as futures_routes
from app.routes.futures import (
    _format_market_detail,
    _game_container_lead_leg,
    get_futures_market,
)

GROUP = "polymarket:1076304"
CONTAINER_ID = 61778284
STAMP = datetime(2026, 9, 26, 18, 49, tzinfo=timezone.utc)

MATCH, GAME1, OU, HCP = "0xmatch", "0xgame1", "0xou35", "0xhcp15"


def _cu(semantic_type, agreement, venue_type=None):
    cu = {
        "v": 1,
        "rule": "content_understanding@5273",
        "semantic_type": semantic_type,
        "agreement": agreement,
    }
    if venue_type:
        cu["venue_type"] = venue_type
    return {"content_understanding_v1": cu}


#: As production stores the specimen's siblings (61800648, 62236495, 62236499, 62236501).
MATCH_ROW = (MATCH, _cu("moneyline", "corroborated", "moneyline"))
GAME1_ROW = (GAME1, _cu("moneyline", "contradicted", "child_moneyline"))
OU_ROW = (OU, _cu("total", "corroborated", "totals"))
HCP_ROW = (HCP, _cu("spread", "corroborated", "map_handicap"))
SPECIMEN_ROWS = [OU_ROW, HCP_ROW, GAME1_ROW, MATCH_ROW]

SIDES = {MATCH: "Cloud9", GAME1: "Cloud9", OU: "Over", HCP: "Team Liquid"}


class _Db:
    """Answers each ``execute`` from a script and counts the calls."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        result = self.results.pop(0)
        return SimpleNamespace(all=lambda: result, scalar_one_or_none=lambda: result)


def _outcome(oid, external_id, name, prob):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=external_id,
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=None,
        resolution_source=None,
        last_updated=STAMP,
        price_changed_at=STAMP,
        team_id=None,
    )


def _board():
    legs = [
        (OU, "O/U 3.5 Games", 0.71),
        (HCP, "Game Handicap: TL (-1.5) vs Cloud9 (+1.5)", 0.44),
        (GAME1, "Game 1 Winner", 0.405),
        (MATCH, "Match Winner", 0.355),
    ]
    return SimpleNamespace(
        id=CONTAINER_ID,
        name="LoL: Cloud9 vs Team Liquid (BO5) - LCS Playoffs",
        description=None,
        category="esports",
        source="polymarket",
        external_id="1076304",
        status="open",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=3,
        llm_sport_category="esports",
        mutually_exclusive=False,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=GROUP,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=[_outcome(i + 1, ext, name, p) for i, (ext, name, p) in enumerate(legs)],
    )


def _id_of(board, external_id):
    return next(o.id for o in board.outcomes if o.external_id == external_id)


# ── which leg leads ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_specimen_leads_with_its_match_winner_not_its_over():
    """🔴 THE SHIP: of four legs, the one corroborated full-contest winner leads."""
    assert await _game_container_lead_leg(_Db(SPECIMEN_ROWS), _board(), SIDES) == MATCH


@pytest.mark.asyncio
async def test_a_per_game_winner_the_venue_disputes_never_leads():
    """"Game 1 Winner" classifies as moneyline; the venue says child_moneyline."""
    assert await _game_container_lead_leg(_Db([GAME1_ROW, OU_ROW]), _board(), SIDES) is None


@pytest.mark.asyncio
async def test_an_unconfirmed_winner_never_leads():
    """The venue said nothing, so our reading of the title alone is not enough."""
    unconfirmed = (MATCH, _cu("moneyline", "unconfirmed"))
    assert await _game_container_lead_leg(_Db([unconfirmed, OU_ROW]), _board(), SIDES) is None


@pytest.mark.asyncio
async def test_two_corroborated_winners_mean_no_lead():
    """A tie is not an answer; the client keeps its own rule."""
    twin = (GAME1, _cu("moneyline", "corroborated", "moneyline"))
    assert await _game_container_lead_leg(_Db([MATCH_ROW, twin]), _board(), SIDES) is None


@pytest.mark.asyncio
async def test_a_sibling_with_no_understanding_is_not_a_winner():
    rows = [(MATCH, None), (GAME1, {"content_understanding_v1": "garbage"}), OU_ROW]
    assert await _game_container_lead_leg(_Db(rows), _board(), SIDES) is None


@pytest.mark.asyncio
async def test_a_board_that_is_not_a_container_is_never_read():
    """No side map means #8669's container test failed: no query at all."""
    db = _Db()
    assert await _game_container_lead_leg(db, _board(), {}) is None
    assert db.calls == 0


# ── what the payload serves ─────────────────────────────────────────────────


def test_the_formatter_serves_the_lead_outcome_by_id():
    board = _board()
    payload = _format_market_detail(board, [], set(), leg_sides=SIDES, lead_leg=MATCH)
    assert payload["lead_outcome_id"] == _id_of(board, MATCH)
    lead = next(o for o in payload["outcomes"] if o["id"] == payload["lead_outcome_id"])
    assert lead["name"] == "Cloud9 — Match Winner"


def test_a_withheld_lead_is_never_offered_as_a_hero():
    """A leg whose price this response refused prints '-', so it cannot lead."""
    board = _board()
    payload = _format_market_detail(
        board, [], {_id_of(board, MATCH)}, leg_sides=SIDES, lead_leg=MATCH
    )
    assert payload["lead_outcome_id"] is None


def test_every_other_board_serves_the_key_as_null():
    """Present and null, so a probe can tell 'no lead' from an old build."""
    payload = _format_market_detail(_board(), [], set())
    assert "lead_outcome_id" in payload
    assert payload["lead_outcome_id"] is None


@pytest.mark.asyncio
async def test_the_route_serves_the_specimens_lead(monkeypatch):
    """End to end: market read, #8664's sibling-sides read, then this read."""

    async def _no_sources(*_a, **_k):
        return [], []

    async def _nothing_withheld(*_a, **_k):
        return set()

    async def _no_fleet(*_a, **_k):
        return None

    async def _sides(_db, _market):
        return dict(SIDES)

    monkeypatch.setattr(futures_routes, "_load_market_sources", _no_sources)
    monkeypatch.setattr(futures_routes, "_withheld_price_outcome_ids", _nothing_withheld)
    monkeypatch.setattr(futures_routes, "_fleet_newest_observation", _no_fleet)
    monkeypatch.setattr(futures_routes, "_game_container_leg_sides", _sides)
    board = _board()
    db = _Db(board, SPECIMEN_ROWS)
    payload = await get_futures_market(CONTAINER_ID, db=db)
    assert payload["lead_outcome_id"] == _id_of(board, MATCH)
    # The highest-priced leg is still the Over; the lead is NOT that.
    top = max(payload["outcomes"], key=lambda o: o["probability"] or 0)
    assert top["id"] != payload["lead_outcome_id"]
