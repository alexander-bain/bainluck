"""#9746: a match page's "By Stage" tab listed another competition's teams.

Production, 2026-09-30: `/futures/60770199`, "Atlético Nacional vs. Millonarios FC -
Halftime Result", offered a By Stage table of England, Czechia, Greece, Spain... —
the UEFA Nations League 'Group A2 Qualifiers' (62383644) and 'Group A3 Winner'
(62383647). All three rows carry `canonical_market_key = 'soccer::championship:2026'`:
the league segment is EMPTY, so the progression route's canonical-key sibling scan
asked for `soccer::%:2026` — every league-less soccer market of the season.

The fake session answers by reading the SQL it is handed, not by call order, so a
guard can only pass if the route stops ASKING the pooled question (or asks the
right one), and every assertion reads the served body.
"""

from datetime import datetime, timezone
from itertools import count
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.anyio

EMPTY_LEAGUE_KEY = "soccer::championship:2026"
REAL_LEAGUE_KEY = "soccer:uefa_nations_league:championship:2026"


_OUTCOME_IDS = count(1)


def _outcome(name, probability):
    # A real outcome row always has an id; the 24h reader keys on it (#10248).
    return SimpleNamespace(
        id=next(_OUTCOME_IDS),
        name=name, team_id=None, current_probability=probability,
        probability_change_24h=None,
    )


def _market(market_id, name, external_id, *, key, event_id=None, tier=5,
            source="kalshi", status="open"):
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id,
        source=source,
        market_tier=tier,
        status=status,
        llm_sport_category="soccer",
        canonical_market_key=key,
        resolution_date=datetime(2026, 11, 18, tzinfo=timezone.utc),
        event_id=event_id,
        outcomes=[],
    )


def _halftime(*, key=EMPTY_LEAGUE_KEY, event_id=15310432):
    # The real specimen: Polymarket, game-level (event_id set), resolved.
    return _market(
        60770199, "Atlético Nacional vs. Millonarios FC - Halftime Result", "1005992",
        key=key, event_id=event_id, source="polymarket", status="resolved",
    )


def _uefa_pool(key):
    group_qual = _market(
        62383644, "UEFA Nations League: Group A2 Qualifiers",
        "KXUEFANLGROUPQUAL-26A2", key=key, tier=5,
    )
    group_qual.outcomes = [_outcome("Croatia", 0.72), _outcome("Serbia", 0.2)]
    group_win = _market(
        62383647, "UEFA Nations League: Group A3 Winner",
        "KXUEFANLGROUPWIN-26A3", key=key, tier=1,
    )
    group_win.outcomes = [_outcome("England", 0.98), _outcome("Spain", 0.79)]
    return [group_qual, group_win]


def _wire(mock_db, primary, pool):
    """Answer each statement by its SQL: the primary load, the canonical-key scan
    (returns `pool` only for the exact pattern the primary's key produces), and
    empty for every other sibling method."""
    issued: list[str] = []
    key_pattern = None
    parts = (primary.canonical_market_key or "").split(":")
    if len(parts) >= 4:
        key_pattern = f"{parts[0]}:{parts[1]}:%:{parts[-1]}"

    async def _execute(stmt, *args, **kwargs):
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        issued.append(sql)
        result = MagicMock()
        if len(issued) == 1:
            result.scalar_one_or_none.return_value = primary
            return result
        hit = (
            key_pattern is not None
            and "canonical_market_key) LIKE" in sql
            and key_pattern in sql
        )
        result.scalars.return_value.unique.return_value.all.return_value = (
            pool if hit else []
        )
        return result

    mock_db.execute.side_effect = _execute
    return issued


async def _get(client, market_id):
    resp = await client.get(f"/api/futures/{market_id}/progression?top_n=40")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _asked_canonical_key(issued):
    # Every SELECT lists the column; only Method 2 FILTERS on it (ILIKE compiles
    # to `lower(futures_markets.canonical_market_key) LIKE lower(...)`).
    return [s for s in issued if "canonical_market_key) LIKE" in s]


class TestTheShip:
    async def test_halftime_page_has_no_foreign_stages(self, client, mock_db):
        """The specimen: empty league + game-level ⇒ no UEFA table."""
        issued = _wire(mock_db, _halftime(), _uefa_pool(EMPTY_LEAGUE_KEY))
        body = await _get(client, 60770199)
        names = {p["name"] for p in body["participants"]}
        assert not names & {"England", "Spain", "Croatia", "Serbia"}, body
        # The futures page shows the tab only at >= 2 stages.
        assert len(body["stages"]) < 2, body["stages"]
        assert _asked_canonical_key(issued) == []

    async def test_empty_league_season_market_does_not_pool_the_sport(
        self, client, mock_db
    ):
        """Not only game rows: a league-less SEASON market (event_id NULL) must not
        read every league-less soccer market of the season as its tournament."""
        primary = _market(
            70000001, "Copa Colombia Winner", "KXCOPACOL-26",
            key=EMPTY_LEAGUE_KEY, tier=1,
        )
        issued = _wire(mock_db, primary, _uefa_pool(EMPTY_LEAGUE_KEY))
        body = await _get(client, 70000001)
        names = {p["name"] for p in body["participants"]}
        assert not names & {"England", "Spain", "Croatia", "Serbia"}, body
        assert _asked_canonical_key(issued) == []

    async def test_game_market_with_a_real_league_does_not_take_season_futures(
        self, client, mock_db
    ):
        """The second clause: a named league is still not a match's progression."""
        issued = _wire(
            mock_db, _halftime(key=REAL_LEAGUE_KEY), _uefa_pool(REAL_LEAGUE_KEY)
        )
        body = await _get(client, 60770199)
        assert len(body["stages"]) < 2, body["stages"]
        assert _asked_canonical_key(issued) == []


class TestControl:
    async def test_named_league_season_market_keeps_its_stages(self, client, mock_db):
        """A season market whose key names its league still finds its siblings
        through the canonical key and renders a two-stage table."""
        primary = _market(
            62383699, "UEFA Nations League Winner", None, key=REAL_LEAGUE_KEY, tier=1,
        )
        primary.outcomes = [_outcome("Spain", 0.3), _outcome("England", 0.2)]
        issued = _wire(mock_db, primary, _uefa_pool(REAL_LEAGUE_KEY))
        body = await _get(client, 62383699)
        assert len(_asked_canonical_key(issued)) == 1
        assert len(body["stages"]) >= 2, body
        assert "Croatia" in {p["name"] for p in body["participants"]}
