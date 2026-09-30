"""#4646 — Bigger Picture drops a container parent whose only served child the fixture fold took.

WHAT A READER SAW. `/events/15320104` (Challenger Mouilleron-Le-Captif doubles),
390px, 2026-09-29 16:00Z. The hero read **Balshaw/Martineau 95%**; Bigger
Picture drew a chip titled "Mouilleron-Le-Captif (Doubles): Balshaw/Martineau vs
Harris/" at 60%.

The group, read on production 19:40Z (`polymarket:1092595`). At 16:00Z it held
only the first two rows; the set/total children arrived at 16:27Z:

    62829653 field  "Mouilleron-Le-Captif (Doubles): Balshaw/Martineau vs Harris/Whitehouse"
                    one leg 237138198, a copy of the child below, named after its title
    62842567 duel   the same name, legs the two pairs: the match winner

WHY IT GOT THROUGH. Door two folds the fixture's winner FIRST
(`_fold_event_match_winner_futures` takes `62842567`: bare fixture name, both
legs name a side), then judges parents LAST (#8848) and finds no surviving
member, so it keeps the parent as the group's only representation
(CERT-2335/2340). Door one runs the same two passes the other way round (#4189
verdict before the #6799 fold), so there the child counts and the parent goes.
The fix hands the verdict the ids the fold took: `/game-markets` draws them.

SYNTHETIC ROWS, LABELLED — that group's shape on the #8848 harness's football
fixture so its sport net applies unchanged; every id, price and condition id is
invented. The control is the same page with the winner child producing no row
at all: nothing was folded, so the parent must still be served.
"""

from types import SimpleNamespace

import pytest

from tests.integration.test_route_related_futures_cfl_7851 import _football_event, _get, _outcome
from tests.integration.test_route_related_futures_redundant_parent_8848 import (
    _market,
    _served_ids,
    _session,
)

GROUP = "polymarket:884801"  # the imported `_market` stamps this group on every market
PARENT, WINNER = 88480001, 88480003
_EVENT_IDS = iter(range(4646001, 4646100))


def _fixture(event_id, *, winner_rows=True):
    parent = _market(PARENT, "Duke vs Stanford", event_id, "884801")
    winner = _market(WINNER, "Duke vs Stanford", event_id, "0xwin")
    candidates = [
        # The parent's one leg: the winner child's title, cut short by the venue.
        _outcome(46461001, parent, "Duke Blue Devils vs Stanf", 0.60),
    ]
    if winner_rows:
        candidates += [
            _outcome(46461002, winner, "Duke Blue Devils", 0.95),
            _outcome(46461003, winner, "Stanford Cardinal", 0.05),
        ]
    group_rows = [
        SimpleNamespace(id=PARENT, group_id=GROUP, market_type="field", external_id="884801"),
        SimpleNamespace(id=WINNER, group_id=GROUP, market_type="duel", external_id="0xwin"),
    ]
    parent_legs = [SimpleNamespace(market_id=PARENT, external_id="0xwin")]
    return candidates, group_rows, parent_legs


def _event(event_id):
    return _football_event(
        event_id, "Duke Blue Devils", "Stanford Cardinal", sport_key="americanfootball_ncaaf"
    )


@pytest.mark.asyncio
async def test_the_parent_leaves_when_its_only_child_was_folded_to_game_markets(monkeypatch):
    event_id = next(_EVENT_IDS)
    candidates, group_rows, parent_legs = _fixture(event_id)
    seen: list = []
    body = await _get(
        monkeypatch, _session(_event(event_id), candidates, group_rows, parent_legs, seen), event_id
    )
    served = _served_ids(body)
    assert seen == ["group", "parent_legs"], seen
    assert WINNER not in served, "precondition: the #4646 fold takes the winner child"
    assert PARENT not in served


@pytest.mark.asyncio
async def test_control_a_parent_whose_child_produced_no_row_stays(monkeypatch):
    """Nothing was folded, so no member reached the reader: CERT-2335/2340 holds.
    Also proves the parent's row reaches the verdict at all."""
    event_id = next(_EVENT_IDS)
    candidates, group_rows, parent_legs = _fixture(event_id, winner_rows=False)
    seen: list = []
    body = await _get(
        monkeypatch, _session(_event(event_id), candidates, group_rows, parent_legs, seen), event_id
    )
    served = _served_ids(body)
    assert seen == ["group", "parent_legs"], seen
    assert PARENT in served
