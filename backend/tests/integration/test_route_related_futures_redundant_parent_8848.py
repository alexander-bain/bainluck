"""#8848 — the ROUTE drops a decomposed container's parent beside its children.

`tests/test_bigger_picture_drops_redundant_container_parent_8848.py` proves the
verdict on hand-built inputs. It cannot prove `_build_related_futures` feeds it
the right ones: the two reads (the parent's whole group, the parent's whole leg
set) are new SQL, and the leg-copy test refuses unless EVERY parent leg names a
sibling — including a sibling that names no team and so never produces a row at
this door. This file drives the real route over a mock session.

SYNTHETIC ROWS, LABELLED. The shape is production's `/events/15318843` group
(`polymarket:1080694`, read 2026-09-26 18:30Z): a `field` parent whose legs are
its children's condition ids, one served child, and one child (the match
winner here) that reaches no row. Names are a football fixture so the harness's
sport net applies unchanged; every id, price and condition id is invented.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.integration.test_route_related_futures import _make_market, _MockResult
from tests.integration.test_route_related_futures_cfl_7851 import (
    _football_event,
    _get,
    _outcome,
)

GROUP = "polymarket:884801"
PARENT, HALF, WINNER = 88480001, 88480002, 88480003
_EVENT_IDS = iter(range(8848001, 8848100))


def _market(id, name, event_id, external_id):
    m = _make_market(id=id, name=name, source="polymarket")
    m.event_id = event_id
    m.group_id = GROUP
    m.external_id = external_id
    m.market_metadata = {}
    m.mutually_exclusive = False
    return m


def _fixture(event_id):
    parent = _market(PARENT, "Duke vs Stanford", event_id, "884801")
    half = _market(HALF, "1st Half Winner: Duke vs Stanford", event_id, "0xhalf")
    candidates = [
        _outcome(88481001, parent, "Duke vs Stanford 1st Half Winner", 0.61),
        _outcome(88481002, parent, "Duke Blue Devils", 0.44),
        _outcome(88481003, half, "Duke Blue Devils", 0.61),
        _outcome(88481004, half, "Stanford Cardinal", 0.39),
    ]
    group_rows = [
        SimpleNamespace(id=PARENT, group_id=GROUP, market_type="field", external_id="884801"),
        SimpleNamespace(id=HALF, group_id=GROUP, market_type="duel", external_id="0xhalf"),
        SimpleNamespace(id=WINNER, group_id=GROUP, market_type="duel", external_id="0xwin"),
    ]
    parent_legs = [
        SimpleNamespace(market_id=PARENT, external_id="0xhalf"),
        SimpleNamespace(market_id=PARENT, external_id="0xwin"),
    ]
    return candidates, group_rows, parent_legs


def _session(event, outcomes, group_rows, parent_legs, seen):
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    market_ids = sorted({o.market.id for o in outcomes})

    async def mock_execute(stmt, *args, **kwargs):
        s = str(stmt).lower()
        if "from events" in s:
            return _MockResult(scalar=event)
        if "select sports.id" in s:
            return _MockResult(rows=[SimpleNamespace(id=11)])
        if "from teams" in s:
            return _MockResult(rows=[], first=None)
        if "select futures_outcomes.market_id, futures_outcomes.external_id" in s:
            seen.append("parent_legs")
            return _MockResult(rows=list(parent_legs))
        if "from futures_outcomes" in s:
            return _MockResult(scalar_rows=list(outcomes))
        if "from futures_odds_snapshots" in s:
            return _MockResult(rows=[])
        if "from line_movement_analyses" in s:
            return _MockResult(scalar=None)
        if "futures_markets.group_id in" in s:
            seen.append("group")
            return _MockResult(rows=list(group_rows))
        if "select futures_markets.id" in s:
            if "order by futures_markets.market_tier" in s:
                return _MockResult(rows=[SimpleNamespace(id=m, market_tier=1) for m in market_ids])
            return _MockResult(rows=[])
        return _MockResult()

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


def _served_ids(body):
    return [r["market_id"] for r in body["home_team_futures"] + body["away_team_futures"]]


@pytest.mark.asyncio
async def test_the_parent_leaves_and_the_served_child_stays(monkeypatch):
    event_id = next(_EVENT_IDS)
    event = _football_event(
        event_id, "Duke Blue Devils", "Stanford Cardinal", sport_key="americanfootball_ncaaf"
    )
    candidates, group_rows, parent_legs = _fixture(event_id)
    seen: list = []
    body = await _get(
        monkeypatch, _session(event, candidates, group_rows, parent_legs, seen), event_id
    )
    served = _served_ids(body)
    assert seen == ["group", "parent_legs"], seen
    assert HALF in served
    assert PARENT not in served


@pytest.mark.asyncio
async def test_control_a_parent_whose_group_cannot_be_read_whole_stays(monkeypatch):
    """Same page, but the group read lacks the no-row sibling: the leg-copy test
    must refuse and the parent is served exactly as before the fix — which also
    proves the parent's rows reach this point at all."""
    event_id = next(_EVENT_IDS)
    event = _football_event(
        event_id, "Duke Blue Devils", "Stanford Cardinal", sport_key="americanfootball_ncaaf"
    )
    candidates, group_rows, parent_legs = _fixture(event_id)
    group_rows = [g for g in group_rows if g.id != WINNER]
    seen: list = []
    body = await _get(
        monkeypatch, _session(event, candidates, group_rows, parent_legs, seen), event_id
    )
    served = _served_ids(body)
    assert HALF in served
    assert PARENT in served
