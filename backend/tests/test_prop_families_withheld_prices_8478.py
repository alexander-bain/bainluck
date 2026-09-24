"""#8478 — the team page's Prop Races withholds the legs the market page withholds.

WHAT A READER SAW (Eagles team page, 390px, 2026-09-24 ~22:40Z): the Next Team
card read "Josh Allen — Philadelphia 47%" (and 47% on three other teams' pages),
and a Championship Game MVP card printed four Eagles at 50% each. Every one of
those legs is an empty book, and ``/api/futures/{id}`` serves each of them as
``probability: null``. The team page never asked the shared screen.

These tests drive ``build_prop_families`` through the REAL
``withheld_price_outcome_ids_for_markets`` — not a patched verdict — with the
book shapes read off production, so a change to the shared arms reaches this
surface's guard as well. One test patches the helper, and only to prove the
failure direction.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.routes import prop_families as route

pytestmark = pytest.mark.asyncio

EAGLES = 549


def _outcome(oid, name, prob, bid, ask, *, team_id=None):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        current_yes_bid=bid, current_yes_ask=ask,
        resolution_source=None, is_winner=False,
        volume_24h=None, volume_24h_at=None, last_updated=None,
        price_changed_at=None, volume=None, team_id=team_id,
    )


def _market(mid, name, outcomes, *, source="kalshi"):
    return SimpleNamespace(
        id=mid, name=name, source=source, group_id=f"{source}:{mid}",
        status="open", llm_sport_category="football", resolution_date=None,
        market_metadata=None, market_type="field", event_id=None,
        outcomes=outcomes,
    )


# Production shapes (db-query 2026-09-24): a Next Team leg the market page
# withholds (bid 0.01 / ask 0.95, printed 0.48), and one it prices.
ALLEN_PHI = _outcome(1, "Philadelphia", 0.48, 0.01, 0.95, team_id=EAGLES)
ALLEN = _market(15475, "Josh Allen's Next Team", [
    _outcome(2, "Stays with Buffalo or Retires", 0.925, 0.87, 0.98), ALLEN_PHI,
])
EVANS_PHI = _outcome(3, "Philadelphia", 0.055, 0.04, 0.07, team_id=EAGLES)
EVANS = _market(3452982, "Mike Evans's next team?", [EVANS_PHI])
WALKER_PHI = _outcome(4, "Philadelphia", 0.095, 0.08, 0.11, team_id=EAGLES)
WALKER = _market(3452984, "Kenneth Walker III's next team?", [WALKER_PHI])

# KXNFLSBMVP-26: last season's game, every leg an empty book at 50%.
SB_LEGS = [
    _outcome(10 + i, n, 0.5, 0.0, 1.0, team_id=EAGLES)
    for i, n in enumerate(["A.J. Brown", "Saquon Barkley", "Jalen Hurts", "DeVonta Smith"])
]
SB_MVP = _market(479, "Pro Football Championship Game MVP", SB_LEGS)

# A priced award race — the control family that must survive untouched.
DPOY_LEGS = [
    _outcome(20, "Jalen Carter", 0.048, 0.04, 0.056, team_id=EAGLES),
    _outcome(21, "Zack Baun", 0.0155, 0.01, 0.021, team_id=EAGLES),
]
DPOY = _market(900, "NFL Defensive Player of the Year", DPOY_LEGS)

MARKETS = {m.id: m for m in (ALLEN, EVANS, WALKER, SB_MVP, DPOY)}


def _fk_rows():
    """What the team_id branch returns: only the legs carrying the Eagles FK."""
    return [
        (o, m) for m in MARKETS.values() for o in m.outcomes if o.team_id == EAGLES
    ]


def _result(rows):
    res = MagicMock()
    res.all.return_value = list(rows)
    sc = MagicMock()
    sc.all.return_value = list(rows)
    res.scalars.return_value = sc
    return res


class _DB:
    """Dispatches on the statement: branch fetch, market reload, anything else."""

    def __init__(self, fk_rows):
        self.fk_rows = fk_rows
        self.branch_calls = 0
        self.market_loads: list[str] = []

    async def execute(self, stmt, *a, **k):
        sql = str(stmt)
        if "statement_timeout" in sql:
            return _result([])
        if "futures_outcomes" in sql and "futures_markets" in sql:
            self.branch_calls += 1
            return _result(self.fk_rows if self.branch_calls == 1 else [])
        if "FROM futures_markets" in sql:
            self.market_loads.append(sql)
            return _result(list(MARKETS.values()))
        return _result([])  # the Kalshi trade read: no snapshots on record

    async def rollback(self):
        pass


def _team():
    return SimpleNamespace(id=EAGLES, name="Philadelphia Eagles",
                           slug="philadelphia-eagles", roster_players=[])


def _families(payload):
    return {f["family_key"]: f for f in payload["families"]}


def _entities(family):
    return {r["entity"]: r["probability"] for r in family["rows"]}


async def _build(fk_rows=None):
    db = _DB(_fk_rows() if fk_rows is None else fk_rows)
    payload, unusable = await route.build_prop_families(_team(), db, 400)
    return payload, unusable, db


async def test_the_next_team_row_the_market_page_refuses_leaves_the_card():
    payload, unusable, _db = await _build()
    assert unusable is False
    fam = _families(payload)["next team"]
    ents = _entities(fam)
    assert "Josh Allen" not in ents, ents
    # The priced legs stay, at their stored numbers — withheld, never rewritten.
    assert ents == {"Kenneth Walker III": 0.095, "Mike Evans": 0.055}


async def test_a_family_of_nothing_but_empty_books_is_not_drawn():
    payload, _u, _db = await _build()
    for fam in payload["families"]:
        assert not any(
            r["probability"] == 0.5 and r["entity"] in {o.name for o in SB_LEGS}
            for r in fam["rows"]
        ), fam


async def test_the_priced_control_family_is_untouched():
    payload, _u, _db = await _build()
    dpoy = [f for f in payload["families"] if "defensive" in f["family_key"]]
    assert len(dpoy) == 1, [f["family_key"] for f in payload["families"]]
    assert _entities(dpoy[0]) == {"Jalen Carter": 0.048, "Zack Baun": 0.0155}


async def test_without_the_screen_the_specimens_would_print():
    """STRAWMAN — the fixture really carries the defect. With the screen
    answering "nothing refused", Josh Allen and the 50% coin flips come back, so
    the tests above fail for the right reason if the wiring is removed."""
    async def _nothing(_db, markets):
        return {m.id: set() for m in markets}

    with patch.object(route, "withheld_price_outcome_ids_for_markets", _nothing):
        payload, _u, _db = await _build()
    fams = _families(payload)
    assert _entities(fams["next team"])["Josh Allen"] == 0.48
    assert any(
        r["probability"] == 0.5 for f in payload["families"] for r in f["rows"]
    )


async def test_the_screen_judges_the_whole_market_not_the_team_legs():
    """The branches fetch only the Eagles leg of each Next Team market; the
    field arms need every leg. So the screen reloads the markets themselves."""
    _p, _u, db = await _build()
    assert len(db.market_loads) == 1
    assert "futures_markets.id IN" in db.market_loads[0]


async def test_a_failed_screen_fails_open_and_says_so():
    async def _boom(_db, _markets):
        raise RuntimeError("screen down")

    with patch.object(route, "withheld_price_outcome_ids_for_markets", _boom):
        payload, unusable, _db = await _build()
    assert unusable is False
    # Today's numbers, and a partial stamp so the build is never taken for full.
    assert "Josh Allen" in _entities(_families(payload)["next team"])
    assert f"{route._REASON_TIMEOUT}{route._BRANCH_PRICE_SCREEN}" in str(payload)


async def test_an_exhausted_reader_budget_defers_the_screen_as_an_iou():
    db = _DB(_fk_rows())
    # t0 and the three branch checks read 0 s; by the screen, 10 s have gone.
    ticks = iter([0.0] * 4 + [10.0] * 50)
    with patch.object(route.time, "monotonic", lambda: next(ticks)):
        payload, _u = await route.build_prop_families(_team(), db, 400, budget_ms=2500)
    assert db.market_loads == []
    assert f"{route._REASON_DEFERRED}{route._BRANCH_PRICE_SCREEN}" in str(payload)
    assert route._deferral_reasons([f"{route._REASON_DEFERRED}{route._BRANCH_PRICE_SCREEN}"])


async def test_no_family_markets_means_no_reload():
    _p, _u, db = await _build(fk_rows=[])
    assert db.market_loads == []
