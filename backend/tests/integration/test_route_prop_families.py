"""Contract tests for Prop Families API: GET /api/teams/{identifier}/prop-families.

Verifies the endpoint returns the expected response shape, groups seeded
prop markets into families, and 404s for unknown teams. Uses the shared
mock_db / client fixtures from integration/conftest.py.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _scalars_result(items):
    """Mock result with .scalars().first()/all() and .all() for row tuples."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.first.return_value = items[0] if items else None
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars
    result.all.return_value = items
    result.first.return_value = items[0] if items else None
    return result


def _routed(team, branches, markets=()):
    """An `execute` side effect that answers by STATEMENT, not by call order.

    The route issues one `SET LOCAL statement_timeout` per branch and then runs
    the #8478 price screen, which reloads the family markets by id. A fixed
    side-effect list modelled none of that, so the list ran out mid-build and the
    screen raised — and it passed only while a failed screen kept every price.
    Since #11534 a failed screen withholds what it could not judge, so the
    screen's reload is answered here with the seeded markets (tight books, which
    the screen prices) and the test asserts what a real build serves.
    """
    pending = list(branches)

    def _execute(stmt, *args, **kwargs):
        sql = str(stmt)
        if "statement_timeout" in sql:
            return MagicMock()
        if "futures_outcomes" in sql and "futures_markets" in sql:
            return _scalars_result(pending.pop(0) if pending else [])
        if "FROM futures_markets" in sql:
            return _scalars_result(list(markets))
        if "FROM teams" in sql:
            return _scalars_result([team])
        return _scalars_result([])

    return _execute


def _screened(market, legs):
    """`market` as the price screen reloads it: every leg, with a tight book."""
    outcomes = [
        SimpleNamespace(
            id=o.id, name=o.name, current_probability=o.current_probability,
            current_yes_bid=o.current_probability - 0.01,
            current_yes_ask=o.current_probability + 0.01,
            resolution_source=None, is_winner=False, volume_24h=None,
            volume_24h_at=None, last_updated=None, price_changed_at=None,
            volume=None, team_id=None,
        )
        for o in legs
    ]
    return SimpleNamespace(**{**vars(market), "outcomes": outcomes,
                              "market_type": "field", "event_id": None})


def _mock_team(*, team_id=42, slug="lakers", name="Los Angeles Lakers"):
    return SimpleNamespace(
        id=team_id, slug=slug, name=name, roster_players=[],
    )


def _outcome(oid, name, prob, is_winner=False):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob, is_winner=is_winner,
    )


def _market(mid, name, *, source="kalshi", group_id=None, status="open"):
    return SimpleNamespace(
        id=mid, name=name, source=source, group_id=group_id, status=status,
        resolution_date=None, market_metadata=None,
    )


class TestPropFamiliesNotFound:
    async def test_returns_404_for_unknown_team(self, client):
        resp = await client.get("/api/teams/nonexistent/prop-families")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Team not found"


class TestPropFamiliesSeeded:
    async def test_returns_grouped_family(self, client, mock_db):
        team = _mock_team()
        m1 = _market(1, "LeBron James Next Team")
        m2 = _market(2, "Kevin Durant Next Team")
        rows = [
            (_outcome(11, "Lakers", 0.4), m1),
            (_outcome(12, "Warriors", 0.2), m1),
            (_outcome(21, "Suns", 0.5), m2),
            (_outcome(22, "Rockets", 0.1), m2),
        ]
        # #1249: the single or_() query was split into separately-indexed
        # branches (FK, outcome-name trigram, market-name trigram). The seeded
        # team has a name (→ both name branches fire) and no roster, so three
        # branch queries run after the team lookup + statement_timeout. The FK
        # branch returns all rows; the name branches return nothing new (dedup
        # by outcome id keeps the result identical to the pre-split behaviour).
        mock_db.execute.side_effect = _routed(
            team,
            [rows, [], []],  # FK branch, outcome-name trigram, market-name trigram
            markets=[
                _screened(m1, [o for o, m in rows if m is m1]),
                _screened(m2, [o for o, m in rows if m is m2]),
            ],
        )

        resp = await client.get("/api/teams/lakers/prop-families")
        assert resp.status_code == 200
        body = resp.json()
        # LAT-P138: `cache` is the envelope contract, stamped on every payload
        # this route STORES. It is additive and asserted here rather than
        # loosened to a subset check, because the point of pinning the key set
        # is that a field arrives by an edit somebody can see.
        assert set(body.keys()) == {"team", "families", "total_families", "cache"}
        assert body["team"]["id"] == 42
        assert body["total_families"] == 1
        fam = body["families"][0]
        assert fam["family_key"] == "next team"
        assert fam["entity_count"] == 2
        assert isinstance(fam["rows"], list)
        assert {r["entity"] for r in fam["rows"]} == {"LeBron James", "Kevin Durant"}

    async def test_empty_when_no_markets(self, client, mock_db):
        team = _mock_team()
        mock_db.execute.side_effect = _routed(team, [[], [], []])
        resp = await client.get("/api/teams/42/prop-families")
        assert resp.status_code == 200
        body = resp.json()
        assert body["families"] == []
        assert body["total_families"] == 0


class TestPropFamiliesBranchSplit:
    """#1249: the team→props match runs as separate per-index branches (FK +
    outcome-name trigram + market-name trigram) that are merged and deduped by
    outcome id, rather than one or_() join that seq-scanned to a 12s timeout."""

    async def test_dedups_outcomes_across_branches(self, client, mock_db):
        team = _mock_team()
        m1 = _market(1, "LeBron James Next Team")
        m2 = _market(2, "Kevin Durant Next Team")
        # Outcome 11 appears in BOTH the FK branch and the outcome-name branch;
        # it must be counted once. Outcome 21 is unique to the name branch.
        fk_rows = [(_outcome(11, "Lakers", 0.4), m1), (_outcome(12, "Warriors", 0.2), m1)]
        fo_name_rows = [(_outcome(11, "Lakers", 0.4), m1), (_outcome(21, "Suns", 0.5), m2)]
        fm_name_rows = [(_outcome(22, "Rockets", 0.1), m2)]
        all_rows = fk_rows + fo_name_rows + fm_name_rows
        legs = {m.id: {o.id: o for o, mm in all_rows if mm is m} for m in (m1, m2)}
        mock_db.execute.side_effect = _routed(
            team,
            [fk_rows, fo_name_rows, fm_name_rows],
            markets=[_screened(m, list(legs[m.id].values())) for m in (m1, m2)],
        )
        resp = await client.get("/api/teams/lakers/prop-families")
        assert resp.status_code == 200
        body = resp.json()
        # Both markets surface (two Next Team entities); outcome 11 not double-counted.
        assert body["total_families"] == 1
        fam = body["families"][0]
        assert fam["family_key"] == "next team"
        assert {r["entity"] for r in fam["rows"]} == {"LeBron James", "Kevin Durant"}


class TestPropFamiliesHTTP:
    async def test_rejects_post(self, client):
        resp = await client.post("/api/teams/lakers/prop-families")
        assert resp.status_code == 405


@pytest.mark.parametrize("hint", [None, "cy young", "mvp"])
async def test_dodgers_joint_award_stays_out_of_single_award_http_payload(client, mock_db, hint):
    """#9858: exercise the actual route and its screen before grouping.

    Synthetic IDs/prices, reported joint title; DB and Redis are test doubles.
    This does not establish live cache adoption or standalone page acceptance.
    """
    team = _mock_team(team_id=9858, slug="dodgers", name="Los Angeles Dodgers")
    cy = _market(1, "Cy Young Winner", group_id="kalshi:synthetic-cy")
    mvp = _market(2, "MVP Winner", group_id="kalshi:synthetic-mvp")
    joint = _market(3, "Shohei Ohtani: Cy Young and MVP Winner", source="polymarket",
                    group_id="polymarket:synthetic-joint")
    if hint:
        joint.market_metadata = {"prop_family": {"family_key": hint}}
    rows = [
        (_outcome(11, "Yoshinobu Yamamoto", 0.4), cy),
        (_outcome(12, "Shohei Ohtani", 0.2), cy),
        (_outcome(21, "Shohei Ohtani", 0.5), mvp),
        (_outcome(22, "Freddie Freeman", 0.1), mvp),
        (_outcome(31, "Yes", 0.01), joint),
    ]
    mock_db.execute.side_effect = _routed(
        team, [rows, [], []],
        markets=[_screened(m, [o for o, parent in rows if parent is m]) for m in (cy, mvp, joint)],
    )
    response = await client.get("/api/teams/dodgers/prop-families")
    assert response.status_code == 200
    families = {f["family_key"]: f for f in response.json()["families"]}
    assert set(families) == {"cy young", "mvp"}
    for key, market, expected in (
        ("cy young", cy, {"Yoshinobu Yamamoto": 0.4, "Shohei Ohtani": 0.2}),
        ("mvp", mvp, {"Shohei Ohtani": 0.5, "Freddie Freeman": 0.1}),
    ):
        family = families[key]
        assert {r["entity"]: r["probability"] for r in family["rows"]} == expected
        assert family["sources"] == ["kalshi"]
        for row in family["rows"]:
            assert row["market_id"] == market.id
            assert row["group_id"] == market.group_id
            assert row["settled"] is False
