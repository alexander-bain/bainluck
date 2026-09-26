"""#8972 — hub/league cards withhold what the market's own page withholds.

WHAT A READER SAW, production 2026-09-26 23:35Z. `/hub/esports` printed
"Will Team Secret be a 2027 VCT Pacific partner team? No 71% · Yes 29%",
Paper Rex "Yes 93%", and VARREL a lone "No 51%" beside "Yes –". Every leg was
last written 2026-08-04, and each board's page, `/api/futures/<id>`, served
both legs `null` with `prices_withheld: 2`.

WHY. `league_futures` asked `_withheld_price_outcome_ids` (#7016), which is five
arms. The detail route adds two terms outside that helper: `stale_observation_keys`
on an open board (#7537) and `unobserved_board_keys` on an open or resolved board
(#8011). #8102 was the same gap on `/entertainment`.

WHAT THIS FILE PINS. The two added terms are decided by the REAL rules in
`market_staleness`. The five-arm helper and the fleet stamp are the only fakes,
so anything withheld beyond the helper's set was withheld by the page's extra
terms and for no other reason.
"""

import ast
import inspect
import textwrap
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import futures as futures_route
from app.routes import league_futures as lf

pytestmark = pytest.mark.asyncio

NOW = datetime.now(timezone.utc)
# The specimen's age on the day it was filed: 2026-08-04 → 2026-09-26.
SPECIMEN_AGE = timedelta(days=53)

YES_ID, NO_ID = 215727848, 215727849


def _leg(oid, name, probability, stamp, *, is_winner=None, resolution_source=None):
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=probability,
        opening_probability=None,
        probability_change_24h=None,
        rank=None,
        team_id=None,
        last_updated=stamp,
        is_winner=is_winner,
        resolution_source=resolution_source,
    )


def _board(legs, *, status="open", updated_at=None):
    return SimpleNamespace(
        id=58112498,
        name="Will VARREL be a 2027 VCT Pacific partner team?",
        source="polymarket",
        status=status,
        outcomes=legs,
        llm_sport_category="esports",
        mutually_exclusive=True,
        updated_at=updated_at if updated_at is not None else NOW,
    )


def _specimen(status="open", **leg_kw):
    """VARREL as stored: both legs written in one August batch, never since."""
    stamp = NOW - SPECIMEN_AGE
    return _board(
        [
            _leg(YES_ID, "Yes", 0.495, stamp, **leg_kw),
            _leg(NO_ID, "No", 0.505, stamp, **leg_kw),
        ],
        status=status,
        updated_at=stamp,
    )


def _install(monkeypatch, *, five_arms=frozenset(), fleet=NOW):
    asked = []

    async def _helper(db, market):
        return set(five_arms)

    async def _fleet(db, market):
        asked.append(market.id)
        return fleet

    monkeypatch.setattr(lf, "_withheld_price_outcome_ids", _helper)
    monkeypatch.setattr(lf, "_fleet_newest_observation", _fleet)
    return asked


# ── the specimen ────────────────────────────────────────────────────────────


async def test_the_specimen_withholds_both_legs_not_just_the_one_with_a_quote(
    monkeypatch,
):
    """The five arms refuse the Yes leg (empty book, bid 0.01 / ask 0.98). The
    page also refuses the No leg because the whole board is 53 days unobserved.
    """
    asked = _install(monkeypatch, five_arms={YES_ID})
    withheld = await lf._page_withheld_outcome_ids(None, _specimen())

    assert withheld == {YES_ID, NO_ID}
    assert asked == [58112498], "the fleet stamp was never read for this board"


async def test_a_dead_board_the_five_arms_acquit_is_still_withheld(monkeypatch):
    """Team Secret (71/29) and Paper Rex (93/7): no arm refuses either leg, and
    the hub printed both. This is the term the old wiring never asked.
    """
    _install(monkeypatch)
    assert await lf._page_withheld_outcome_ids(None, _specimen()) == {YES_ID, NO_ID}


async def test_the_card_prints_the_no_price_mark_for_both_legs(monkeypatch):
    """Read through the hub's own serializer, which is the shape the card draws."""
    _install(monkeypatch, five_arms={YES_ID})
    board = _specimen()
    withheld = await lf._page_withheld_outcome_ids(None, board)
    rows = lf._serialize_outcomes(board.outcomes, board, withheld)

    assert [r["probability"] for r in rows] == [None, None]


# ── controls: the extra terms fire on what the page names and nothing else ──


async def test_a_live_board_keeps_its_prices(monkeypatch):
    _install(monkeypatch)
    board = _board([_leg(1, "Yes", 0.29, NOW), _leg(2, "No", 0.71, NOW)])
    assert await lf._page_withheld_outcome_ids(None, board) == set()


async def test_no_fleet_stamp_withholds_nothing_new(monkeypatch):
    """Fail-open is inherited: a fleet read that could not happen must degrade to
    today's card, never to a blanked board.
    """
    _install(monkeypatch, five_arms={YES_ID}, fleet=None)
    assert await lf._page_withheld_outcome_ids(None, _specimen()) == {YES_ID}


async def test_a_graded_dead_board_is_a_result_and_is_not_withheld(monkeypatch):
    """Settled means settled. A board a venue graded prints its result however
    old its stamps are, which is the exemption `_board_has_a_verdict` carries.
    """
    _install(monkeypatch)
    board = _specimen(
        status="resolved", is_winner=True, resolution_source="api_settlement"
    )
    assert await lf._page_withheld_outcome_ids(None, board) == set()


async def test_an_ungraded_dead_resolved_board_is_withheld(monkeypatch):
    """#2077's half: `resolved` with no verdict is the last quote of a dead
    market, and the page withholds it.
    """
    _install(monkeypatch)
    board = _specimen(status="resolved")
    assert await lf._page_withheld_outcome_ids(None, board) == {YES_ID, NO_ID}


async def test_a_leg_left_behind_on_an_open_board_is_withheld(monkeypatch):
    """#7537's term, open boards only: one leg is 20 days behind its siblings."""
    _install(monkeypatch)
    legs = [
        _leg(1, "A", 0.5, NOW),
        _leg(2, "B", 0.3, NOW),
        _leg(3, "C", 0.2, NOW - timedelta(days=20)),
    ]
    assert await lf._page_withheld_outcome_ids(None, _board(legs)) == {3}


async def test_the_lagging_leg_rule_is_open_only(monkeypatch):
    """Same legs on a resolved board: the page's lag term does not run there, and
    the board as a whole is fresh, so nothing is withheld.
    """
    _install(monkeypatch)
    legs = [
        _leg(1, "A", 0.5, NOW),
        _leg(2, "B", 0.3, NOW),
        _leg(3, "C", 0.2, NOW - timedelta(days=20)),
    ]
    assert (
        await lf._page_withheld_outcome_ids(None, _board(legs, status="resolved"))
        == set()
    )


# ── wiring: both serve sites ask the composition, from the page's own helpers ─


def _calls_in(func) -> set[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


@pytest.mark.parametrize("serve_site", ["build_league", "build_linked_matches"])
async def test_every_serve_site_asks_the_page_composition(serve_site):
    """A serve site that goes back to the bare five-arm helper re-opens #8972
    with every test above still green, because they call the composition directly.
    """
    calls = _calls_in(getattr(lf, serve_site))
    assert "_page_withheld_outcome_ids" in calls
    assert "_withheld_price_outcome_ids" not in calls


async def test_the_composition_uses_the_detail_routes_own_helpers():
    """Identity, not behaviour (#7016's class guard). A private copy of the fleet
    read or the verdict test would pass every case here and drift later.
    """
    assert lf._fleet_newest_observation is futures_route._fleet_newest_observation
    assert lf._board_has_a_verdict is futures_route._board_has_a_verdict
    assert lf._withheld_price_outcome_ids is futures_route._withheld_price_outcome_ids
