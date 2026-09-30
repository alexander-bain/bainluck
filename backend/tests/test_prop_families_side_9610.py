"""#9610 — a women's team page stops listing the men's props as its own.

Arsenal Women's ``teams.name`` is "Arsenal", so the prop-families name branches
matched every "Arsenal" market. Its page carried a "To Score" prop race made of
the men's fixtures ("Arsenal FC vs Coventry City: First Team to Score", Kalshi
``KXEPLFTTS-26AUG21ARSCOV``, ``sport_id`` NULL), the same card the men's page
shows. ``build_prop_families`` now asks ``link_crosses_gender`` (#9593) about
every market before the price screen.

The fixtures carry the production shapes: the men's legs have no ``sport_id``
and an unmarked name. One women's leg says "Women" in its name; the other is
unmarked and only its ``sport_id`` says women's.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Select

from app.routes import prop_families as route
from app.utils import event_concept_cache as cache_mod

EPL_ID, UWCL_W_ID = 1, 2
SPORT_KEYS = {EPL_ID: "soccer_epl", UWCL_W_ID: "soccer_uefa_champs_league_women"}

MENS_ENTITIES = {"Arsenal FC vs Coventry City: First Team", "Arsenal FC vs Manchester City: First Team"}
WOMENS_ENTITIES = {
    "Arsenal Women vs Chelsea Women: First Team",
    "Arsenal FC vs OL Lyonnes: First Team",
}


def _market(mid, name, external_id, *, sport_id=None):
    return SimpleNamespace(
        id=mid, name=name, source="kalshi", external_id=external_id,
        sport_id=sport_id, group_id=f"kalshi:{external_id}", status="open",
        resolution_date=None, market_metadata={}, llm_sport_category="soccer",
    )


def _pair(oid, market):
    outcome = SimpleNamespace(
        id=oid, name="Arsenal", current_probability=0.55,
        market_id=market.id, is_winner=False,
    )
    return (outcome, market)


MENS_ROWS = [
    _pair(1, _market(59586278, "Arsenal FC vs Coventry City: First Team to Score",
                     "KXEPLFTTS-26AUG21ARSCOV")),
    _pair(2, _market(59201939, "Arsenal FC vs Manchester City: First Team to Score",
                     "KXENGCSFTTS-26AUG16ARSMCI")),
]
WOMENS_ROWS = [
    _pair(3, _market(70000001, "Arsenal Women vs Chelsea Women: First Team to Score",
                     "KXWSLFTTS-26OCT04ARSCHE")),
    # Unmarked name, no league in the ticker: only its sport_id says women's.
    _pair(4, _market(70000002, "Arsenal FC vs OL Lyonnes: First Team to Score",
                     "KXFTTS-26OCT08ARSOLL", sport_id=UWCL_W_ID)),
]


def _rows_result(items):
    result = MagicMock()
    result.all.return_value = list(items)
    scalars = MagicMock()
    scalars.all.return_value = []
    result.scalars.return_value = scalars
    return result


class _DB:
    """Every fetch branch returns the same rows (deduped by outcome id in the
    route); the ``sports`` lookup answers from SPORT_KEYS or raises."""

    def __init__(self, rows, *, sports_raise=False):
        self.rows = rows
        self.sports_raise = sports_raise
        self.sport_lookups = 0

    async def execute(self, stmt, *args, **kwargs):
        rendered = str(stmt)
        if "statement_timeout" in rendered:
            return _rows_result([])
        if isinstance(stmt, Select) and "futures_outcomes" in rendered:
            return _rows_result(self.rows)
        if isinstance(stmt, Select) and "FROM sports" in rendered:
            self.sport_lookups += 1
            if self.sports_raise:
                raise RuntimeError("sports lookup failed")
            return _rows_result(list(SPORT_KEYS.items()))
        return _rows_result([])  # the price screen's market reload

    async def rollback(self):
        pass


def _team(*, sport_id, tid=11857, slug="arsenal-women"):
    # No roster, so only the team_id and team-name branches run.
    return SimpleNamespace(id=tid, name="Arsenal", slug=slug, sport_id=sport_id,
                           roster_players=[])


async def _build(team, db):
    with patch.object(route, "withheld_price_outcome_ids_for_markets",
                      AsyncMock(return_value={})):
        payload, unusable = await route.build_prop_families(team, db, 50)
    assert unusable is False
    return payload


def _entities(payload):
    return {row["entity"] for fam in payload["families"] for row in fam["rows"]}


def _reasons(payload):
    # The build's own loss notes; the caller stamps them into the envelope.
    return [loss["reason"] for loss in payload.get(cache_mod.BUILD_LOSS_FIELD) or []]


class TestTheSideScreen:
    async def test_the_womens_page_keeps_only_the_womens_props(self):
        payload = await _build(_team(sport_id=UWCL_W_ID), _DB(MENS_ROWS + WOMENS_ROWS))
        assert _entities(payload) == WOMENS_ENTITIES

    async def test_the_mens_page_keeps_only_the_mens_props(self):
        payload = await _build(
            _team(sport_id=EPL_ID, tid=1826, slug="arsenal"), _DB(MENS_ROWS + WOMENS_ROWS)
        )
        assert _entities(payload) == MENS_ENTITIES

    async def test_the_womens_page_drops_the_mens_card_entirely(self):
        # The reader-visible specimen: only men's legs matched, so no card at all.
        payload = await _build(_team(sport_id=UWCL_W_ID), _DB(MENS_ROWS))
        assert payload["families"] == []
        assert _reasons(payload) == []

    async def test_strawman_without_the_screen_the_womens_page_shows_the_mens_card(self):
        # A team with no sport_id is not screened. The same fixture then prints
        # the men's card, so the tests above are not passing on an empty build.
        payload = await _build(_team(sport_id=None), _DB(MENS_ROWS + WOMENS_ROWS))
        assert _entities(payload) == MENS_ENTITIES | WOMENS_ENTITIES

    async def test_a_failed_lookup_fails_open_and_says_so(self):
        db = _DB(MENS_ROWS + WOMENS_ROWS, sports_raise=True)
        payload = await _build(_team(sport_id=UWCL_W_ID), db)
        assert db.sport_lookups == 1
        assert _entities(payload) == MENS_ENTITIES | WOMENS_ENTITIES
        assert f"{route._REASON_TIMEOUT}{route._BRANCH_SIDE_SCREEN}" in _reasons(payload)

    async def test_the_screen_inputs_never_reach_the_payload(self):
        payload = await _build(_team(sport_id=UWCL_W_ID), _DB(WOMENS_ROWS))
        rows = [row for fam in payload["families"] for row in fam["rows"]]
        assert rows
        assert not any({"external_id", "sport_id"} & set(row) for row in rows)


@pytest.mark.parametrize("sport_id", [UWCL_W_ID, EPL_ID])
async def test_one_sports_lookup_per_build(sport_id):
    db = _DB(MENS_ROWS + WOMENS_ROWS)
    await _build(_team(sport_id=sport_id), db)
    assert db.sport_lookups == 1
