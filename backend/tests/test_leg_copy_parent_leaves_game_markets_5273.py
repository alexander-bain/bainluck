"""#5273 — a Polymarket parent whose legs are its children's lead legs leaves the page.

THE DEFECT, SEEN ON PRODUCTION (2026-09-24 04:36Z, 390px, /events/15318167,
White Sox v Royals). One "Additional Markets" card read

    Chicago White Sox 54% / NRFI 50% / Kansas City Royals 46%

`GET /api/events/15318167/game-markets` served three Polymarket markets on
`group_id = polymarket:1042973`, all verbatim from `futures_markets`:

    61385201  parent  market_type=duel   Chicago White Sox=0.540 [0x185a60d0…]
                                         NRFI=0.495              [0x27c202a3…]
    62155955  child   market_type=NULL   Chicago White Sox=0.540 [0x185a60d0…_yes]
                                         Kansas City Royals=0.460 [0x185a60d0…_no]
    62155956  child   market_type=NULL   Yes=0.495 / No=0.505    (first-inning run)

The parent and the moneyline child share the market name, so the page merged
them. The parent's legs are, BY ID, its two children's lead legs
(`_parent_outcome_data`'s non-negRisk branch). #4189 already drops a redundant
container parent, but only when the parent is shaped `field` and its children
`container_member`/`quantity` — here neither holds, so nothing fired.

🔴 THE CONTROLS ARE THE POINT. "NRFI is gone" is satisfied by a serializer that
returns nothing. So: the children still arrive with their own prices; a parent
with no served children stays; a parent whose children render nothing stays; a
single-market parent (`{cond}` + `{cond}_side1`) is never a candidate; and a
parent with one leg that names no sibling is never a candidate.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.events import (
    _game_markets_cache,
    _leg_copy_parent_members,
    get_game_markets,
)

GROUP = "polymarket:1042973"
PARENT_ID = 61385201
MONEYLINE_ID = 62155955
FIRST_INNING_ID = 62155956
MONEYLINE_COND = "0x185a60d0897ce533cc31020f8bacc0e2c44d8ed4863ef97e200aa51ba2b7d4b1"
FIRST_INNING_COND = "0x27c202a338bf4edb0d250a11639d9817e280ff0400959da9f8b72f797af0764b"
MATCHUP = "Chicago White Sox vs. Kansas City Royals"


def _make_result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _make_event():
    event = MagicMock()
    event.id = 15318167
    event.home_team_name = "Kansas City Royals"
    event.away_team_name = "Chicago White Sox"
    event.status = "scheduled"
    event.sport_id = None
    event.sport = MagicMock()
    event.sport.key = "baseball_mlb"
    event.commence_time = datetime(2026, 9, 24, 18, 10, tzinfo=timezone.utc)
    event.home_score = None
    event.away_score = None
    event.period = None
    event.game_clock = None
    event.box_score_data = None
    return event


def _make_market(*, id, name, external_id, market_type=None, group_id=GROUP):
    market = MagicMock()
    market.id = id
    market.name = name
    market.external_id = external_id
    market.event_id = 15318167
    market.category = "game_prop"
    market.status = "open"
    market.source = "polymarket"
    market.sport_id = None
    market.llm_sport_category = "baseball"
    market.commence_time = datetime(2026, 9, 24, 18, 10, tzinfo=timezone.utc)
    market.market_type = market_type
    market.group_id = group_id
    market.group_type = None
    return market


def _make_outcome(*, id, market_id, name, probability, external_id):
    outcome = MagicMock()
    outcome.id = id
    outcome.market_id = market_id
    outcome.name = name
    outcome.external_id = external_id
    outcome.current_probability = probability
    outcome.opening_probability = None
    outcome.resolution_source = None
    outcome.is_winner = None
    return outcome


def _db_for(event, markets, outcomes):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar=event),
            _make_result(rows=[]),        # #2693 folded_event_ids
            _make_result(rows=markets),
            _make_result(all_rows=[]),    # polymarket parent groups
            _make_result(rows=[]),        # unlinked fallback
            _make_result(rows=outcomes),
            _make_result(all_rows=[]),    # #4970 load_latest_observed_at
        ]
    )
    return db


def _parent():
    market = _make_market(
        id=PARENT_ID, name=MATCHUP, external_id="1042973", market_type="duel"
    )
    legs = [
        _make_outcome(id=1, market_id=PARENT_ID, name="Chicago White Sox",
                      probability=0.540, external_id=MONEYLINE_COND),
        _make_outcome(id=2, market_id=PARENT_ID, name="NRFI",
                      probability=0.495, external_id=FIRST_INNING_COND),
    ]
    return market, legs


def _children(state="renderable"):
    markets = [
        _make_market(id=MONEYLINE_ID, name=MATCHUP, external_id=MONEYLINE_COND),
        _make_market(
            id=FIRST_INNING_ID,
            name=f"Will there be a run scored in the first inning?: {MATCHUP}",
            external_id=FIRST_INNING_COND,
        ),
    ]
    if state == "no_outcomes":
        return markets, []
    legs = [
        _make_outcome(id=11, market_id=MONEYLINE_ID, name="Chicago White Sox",
                      probability=0.540, external_id=f"{MONEYLINE_COND}_yes"),
        _make_outcome(id=12, market_id=MONEYLINE_ID, name="Kansas City Royals",
                      probability=0.460, external_id=f"{MONEYLINE_COND}_no"),
        _make_outcome(id=13, market_id=FIRST_INNING_ID, name="Yes",
                      probability=0.495, external_id=f"{FIRST_INNING_COND}_yes"),
        _make_outcome(id=14, market_id=FIRST_INNING_ID, name="No",
                      probability=0.505, external_id=f"{FIRST_INNING_COND}_no"),
    ]
    return markets, legs


async def _payload(*, children="renderable"):
    event = _make_event()
    parent, parent_legs = _parent()
    markets, outcomes = [parent], list(parent_legs)
    if children != "absent":
        child_markets, child_legs = _children(children)
        markets += child_markets
        outcomes += child_legs
    return await get_game_markets(event.id, _db_for(event, markets, outcomes))


def _rows(payload):
    rows = []
    for section in ("player_props", "totals", "spreads", "matchups", "other",
                    "period_markets", "team_totals"):
        for row in payload.get(section) or []:
            if isinstance(row, dict):
                rows.append(row)
    return rows


@pytest.fixture(autouse=True)
def clear_game_markets_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


class TestTheLegCopyParentLeaves:
    @pytest.mark.asyncio
    async def test_the_nrfi_leg_is_not_served(self):
        payload = await _payload()
        nrfi = [r for r in _rows(payload) if r.get("outcome_name") == "NRFI"]
        assert nrfi == [], f"the parent's copied 'NRFI' leg is still served: {nrfi}"

    @pytest.mark.asyncio
    async def test_the_matchup_card_carries_exactly_the_two_teams(self):
        """The card the reader saw: one name, and after the fix two legs, not three."""
        payload = await _payload()
        legs = sorted(
            (r.get("outcome_name"), r.get("probability"))
            for r in _rows(payload)
            if r.get("market_name") == MATCHUP
        )
        assert legs == [("Chicago White Sox", 0.54), ("Kansas City Royals", 0.46)], legs

    def test_the_helper_names_the_parent_and_both_children(self):
        parent, parent_legs = _parent()
        child_markets, child_legs = _children()
        by_market: dict = {}
        for o in parent_legs + child_legs:
            by_market.setdefault(o.market_id, []).append(o)
        assert _leg_copy_parent_members([parent] + child_markets, by_market) == {
            PARENT_ID: {MONEYLINE_ID, FIRST_INNING_ID}
        }


class TestWithTheKalshiMoneylineOnThePage:
    """The production page also carried Kalshi's moneyline (61827719). With the
    parent gone, #6799's fold leaves ONE match-winner card; with it, the parent's
    "White Sox / NRFI" pair stood beside Kalshi's card."""

    @pytest.mark.asyncio
    async def test_one_winner_card_and_no_nrfi(self):
        event = _make_event()
        parent, parent_legs = _parent()
        child_markets, child_legs = _children()
        kalshi = _make_market(
            id=61827719, name="Chicago White Sox vs Kansas City",
            external_id="KXMLBGAME-26SEP241310CWSKC", group_id=None,
        )
        kalshi.source = "kalshi"
        kalshi_legs = [
            _make_outcome(id=21, market_id=61827719, name="Chicago White Sox",
                          probability=0.535, external_id="KXMLBGAME-26SEP241310CWSKC-CWS"),
            _make_outcome(id=22, market_id=61827719, name="Kansas City",
                          probability=0.465, external_id="KXMLBGAME-26SEP241310CWSKC-KC"),
        ]
        payload = await get_game_markets(
            event.id,
            _db_for(event, [parent] + child_markets + [kalshi],
                    parent_legs + child_legs + kalshi_legs),
        )
        rows = _rows(payload)
        assert not [r for r in rows if r.get("outcome_name") == "NRFI"], rows
        winner_cards = {
            (r.get("source"), r.get("market_name"))
            for r in rows
            if r.get("outcome_name") in ("Chicago White Sox", "Kansas City",
                                         "Kansas City Royals")
        }
        assert len(winner_cards) == 1, f"more than one match-winner card: {winner_cards}"
        assert any("first inning" in (r.get("market_name") or "").lower() for r in rows)


class TestTheChildrenStillArrive:
    @pytest.mark.asyncio
    async def test_both_children_keep_their_own_prices(self):
        payload = await _payload()
        served = {(r.get("outcome_name"), r.get("probability")) for r in _rows(payload)}
        for leg in (("Chicago White Sox", 0.54), ("Kansas City Royals", 0.46)):
            assert leg in served, f"moneyline leg {leg} lost: {sorted(served)}"
        first_inning = [
            r for r in _rows(payload)
            if "first inning" in (r.get("market_name") or "").lower()
        ]
        assert first_inning, "the first-inning child left the page with its parent"


class TestTheParentStaysWhenItIsTheOnlyRepresentation:
    @pytest.mark.asyncio
    async def test_no_served_children(self):
        payload = await _payload(children="absent")
        names = {r.get("outcome_name") for r in _rows(payload)}
        assert "Chicago White Sox" in names, (
            f"a parent with no served children was dropped: {sorted(names)}"
        )

    @pytest.mark.asyncio
    async def test_children_served_but_rendering_nothing(self):
        """Candidate by id, but no child row survives → the payload verdict keeps it."""
        payload = await _payload(children="no_outcomes")
        names = {r.get("outcome_name") for r in _rows(payload)}
        assert "Chicago White Sox" in names, (
            f"the parent left with children that rendered nothing: {sorted(names)}"
        )


class TestWhatIsNeverACandidate:
    def test_a_single_market_parent_with_its_side1_leg(self):
        """#7505's two-leg sole-moneyline parent has no sibling rows at all."""
        parent = _make_market(id=1, name="Draxl vs Halys", external_id="1045485")
        legs = [
            _make_outcome(id=1, market_id=1, name="Liam Draxl", probability=0.5,
                          external_id="0xabc"),
            _make_outcome(id=2, market_id=1, name="Quentin Halys", probability=0.5,
                          external_id="0xabc_side1"),
        ]
        assert _leg_copy_parent_members([parent], {1: legs}) == {}

    def test_a_parent_with_one_leg_naming_no_sibling(self):
        parent, parent_legs = _parent()
        moneyline = _make_market(id=MONEYLINE_ID, name=MATCHUP, external_id=MONEYLINE_COND)
        assert _leg_copy_parent_members(
            [parent, moneyline], {PARENT_ID: parent_legs}
        ) == {}

    def test_a_sibling_in_another_group_does_not_count(self):
        parent, parent_legs = _parent()
        stranger = _make_market(
            id=MONEYLINE_ID, name=MATCHUP, external_id=MONEYLINE_COND,
            group_id="polymarket:999",
        )
        other = _make_market(
            id=FIRST_INNING_ID, name="x", external_id=FIRST_INNING_COND,
        )
        assert _leg_copy_parent_members(
            [parent, stranger, other], {PARENT_ID: parent_legs}
        ) == {}
