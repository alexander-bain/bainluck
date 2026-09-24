"""#8375 — search stops answering a game with its Polymarket container's top leg.

THE DEFECT, SEEN ON PRODUCTION (2026-09-24 07:58Z, 390px, `/search?q=falcons
packers`). The ANSWERS card's second row read

    Falcons vs. Packers · O/U 24.5 95%

The row is futures market 58980362, the Polymarket EVENT row for the game:

    external_id 848221   group_id polymarket:848221   event_id 14780546
    mutually_exclusive false   199 outcomes

Each outcome is one sub-market's lead leg, keyed on that sub-market's
`condition_id`, and every sub-market is already its own row on the same group.
#8348 removed this parent from `/game-markets` by the same by-id test. Search
had no such test.

🔴 THE CONTROLS ARE THE POINT. "The container is gone" is satisfied by a search
that withholds every Polymarket board. So: a one-winner board (Norway / Draw /
Denmark, `mutually_exclusive` true) stays; a board with no game ("What will the
announcers say…") stays; a single-market parent (`{cond}` + `{cond}_side1`)
stays; a parent with one leg that names no row stays; a leg that names a row on
ANOTHER group does not count; and a failed read serves the page unfiltered.
"""

import ast
import inspect
import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import events as events_module
from app.routes.events import (
    _search_container_parent_candidates,
    _search_container_parent_ids,
    _search_container_parents_among,
)

GROUP = "polymarket:848221"
CONTAINER_ID = 58980362
EVENT_ID = 14780546
OU_COND = "0xaaa1"
PACKERS_OU_COND = "0xaaa2"
LOVE_COND = "0xaaa3"
SUB_MARKETS = {61766324: OU_COND, 61766330: PACKERS_OU_COND, 61692240: LOVE_COND}


def _outcome(external_id, name="leg", p=0.5):
    return SimpleNamespace(external_id=external_id, name=name, current_probability=p)


def _market(
    id,
    *,
    legs,
    source="polymarket",
    group_id=GROUP,
    event_id=EVENT_ID,
    mutually_exclusive=False,
):
    return SimpleNamespace(
        id=id,
        source=source,
        group_id=group_id,
        event_id=event_id,
        mutually_exclusive=mutually_exclusive,
        outcomes=[_outcome(e) for e in legs],
    )


def _container():
    return _market(CONTAINER_ID, legs=[OU_COND, PACKERS_OU_COND, LOVE_COND])


def _sibling_rows(group=GROUP):
    return [(mid, group, cond) for mid, cond in SUB_MARKETS.items()]


# ── the pure verdict ────────────────────────────────────────────────────────


def test_the_falcons_packers_container_is_withheld():
    """🔴 THE SHIP: every leg names another row on its own group."""
    candidates = _search_container_parent_candidates([_container()])
    assert candidates == {CONTAINER_ID: (GROUP, {OU_COND, PACKERS_OU_COND, LOVE_COND})}
    assert _search_container_parents_among(candidates, _sibling_rows()) == {CONTAINER_ID}


def test_a_one_winner_board_is_never_a_candidate():
    """Norway vs. Denmark (Norway / Draw / Denmark) is a real question even
    though each leg is also a row: it is `mutually_exclusive`."""
    three_way = _market(60744994, legs=[OU_COND, PACKERS_OU_COND], mutually_exclusive=True)
    assert _search_container_parent_candidates([three_way]) == {}


def test_a_board_with_no_game_is_never_a_candidate():
    """ "What will the announcers say during the Falcons vs Packers game?" is a
    leg-copy board with `event_id` NULL. It is the legitimate shape."""
    mentions = _market(61998666, legs=[OU_COND, PACKERS_OU_COND], event_id=None)
    assert _search_container_parent_candidates([mentions]) == {}


def test_a_null_exclusivity_is_not_read_as_false():
    unknown = _market(1, legs=[OU_COND], mutually_exclusive=None)
    assert _search_container_parent_candidates([unknown]) == {}


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": "kalshi"},
        {"group_id": None},
        {"legs": []},
        {"legs": [OU_COND, None]},
        {"legs": [OU_COND, ""]},
    ],
)
def test_rows_that_cannot_be_proved_a_copy_are_not_candidates(overrides):
    kwargs = {"legs": [OU_COND, PACKERS_OU_COND]}
    kwargs.update(overrides)
    assert _search_container_parent_candidates([_market(7, **kwargs)]) == {}


def test_a_single_market_parent_is_kept():
    """Legs `{cond}` and `{cond}_side1`: the `_side1` leg names no row."""
    single = _market(9, legs=[OU_COND, f"{OU_COND}_side1"])
    candidates = _search_container_parent_candidates([single])
    assert _search_container_parents_among(candidates, _sibling_rows()) == set()


def test_a_parent_with_one_unwritten_sub_market_is_kept():
    """If one sub-market was never written as a row, the parent is the only
    place it can be found."""
    parent = _market(CONTAINER_ID, legs=[OU_COND, PACKERS_OU_COND, "0xnotarow"])
    candidates = _search_container_parent_candidates([parent])
    assert _search_container_parents_among(candidates, _sibling_rows()) == set()


def test_a_leg_on_another_group_does_not_count():
    candidates = _search_container_parent_candidates([_container()])
    assert (
        _search_container_parents_among(candidates, _sibling_rows("polymarket:999"))
        == set()
    )


def test_a_leg_that_names_the_parent_itself_does_not_count():
    candidates = _search_container_parent_candidates([_container()])
    rows = [(CONTAINER_ID, GROUP, OU_COND)] + _sibling_rows()[1:]
    assert _search_container_parents_among(candidates, rows) == set()


def test_the_verdict_is_per_parent():
    other = _market(
        CONTAINER_ID + 1, legs=[OU_COND, "0xnotarow"], group_id=GROUP
    )
    candidates = _search_container_parent_candidates([_container(), other])
    assert _search_container_parents_among(candidates, _sibling_rows()) == {CONTAINER_ID}


# ── the async read ──────────────────────────────────────────────────────────


def _db(rows=None, exc=None):
    db = AsyncMock()
    savepoint = AsyncMock()
    db.begin_nested = AsyncMock(return_value=savepoint)
    result = MagicMock()
    result.all.return_value = rows or []
    db.execute = AsyncMock(side_effect=exc) if exc else AsyncMock(return_value=result)
    return db, savepoint


@pytest.fixture
def no_timeout(monkeypatch):
    monkeypatch.setattr(
        events_module, "_apply_search_statement_timeout", AsyncMock()
    )


@pytest.mark.asyncio
async def test_the_read_names_the_container(no_timeout):
    db, savepoint = _db(rows=_sibling_rows())
    got = await _search_container_parent_ids(db, [_container()], deadline=float("inf"))
    assert got == {CONTAINER_ID}
    savepoint.commit.assert_awaited_once()
    sql = str(db.execute.await_args.args[0]).lower()
    assert "futures_markets.source" in sql and "futures_markets.external_id in" in sql


@pytest.mark.asyncio
async def test_no_candidate_issues_no_read(no_timeout):
    db, _ = _db()
    three_way = _market(1, legs=[OU_COND], mutually_exclusive=True)
    assert await _search_container_parent_ids(db, [three_way], float("inf")) == set()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_spent_deadline_serves_the_page_unfiltered(no_timeout):
    db, _ = _db(rows=_sibling_rows())
    assert await _search_container_parent_ids(db, [_container()], deadline=0.0) == set()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_timeout_fails_open_under_a_savepoint(no_timeout, monkeypatch):
    monkeypatch.setattr(events_module, "_is_query_timeout", lambda exc: True)
    db, savepoint = _db(exc=RuntimeError("canceling statement due to statement timeout"))
    assert await _search_container_parent_ids(db, [_container()], float("inf")) == set()
    savepoint.rollback.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_non_timeout_error_is_not_swallowed(no_timeout, monkeypatch):
    monkeypatch.setattr(events_module, "_is_query_timeout", lambda exc: False)
    db, savepoint = _db(exc=ValueError("bug"))
    with pytest.raises(ValueError):
        await _search_container_parent_ids(db, [_container()], float("inf"))
    savepoint.rollback.assert_awaited_once()


# ── the route wiring ────────────────────────────────────────────────────────


def _route_source():
    return textwrap.dedent(inspect.getsource(events_module.search_events))


def _route_tree():
    return ast.parse(_route_source())


def test_the_route_reads_the_whole_deduped_set():
    calls = [
        n
        for n in ast.walk(_route_tree())
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", None) == "_search_container_parent_ids"
    ]
    assert len(calls) == 1, "search_events must ask the container question exactly once"
    assert [getattr(a, "id", None) for a in calls[0].args[:2]] == ["db", "deduped_futures"]


def _comprehensions_over_deduped_futures():
    return [
        n
        for n in ast.walk(_route_tree())
        if isinstance(n, ast.ListComp)
        and getattr(n.generators[0].iter, "id", None) == "deduped_futures"
        and "_futures_card_has_no_answer" in ast.unparse(n)
    ]


def test_every_reader_list_built_from_the_deduped_set_withholds_containers():
    """The flat list AND the families. #6327's note: a family is the back door a
    half-applied withdrawal leaves open. Both exclude containers in the same
    comprehension that withdraws answerless cards, so #3412's and #5516's
    two-call-site guards still hold."""
    comps = _comprehensions_over_deduped_futures()
    assert len(comps) == 2, f"expected the flat bucket and the families input, got {len(comps)}"
    for comp in comps:
        assert "_container_parent_ids" in ast.unparse(comp), ast.unparse(comp)
    families = [
        n
        for n in ast.walk(_route_tree())
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", None) == "_compose_futures_families"
    ]
    assert families and "_container_parent_ids" in ast.unparse(families[0].args[0])


def test_the_read_has_its_own_stage_clock_after_the_refill():
    """The read is a DB lane, so it sits between the refill mark and its own
    mark, and BEFORE the lists that consume its answer."""
    src = _route_source()
    refill = src.index('_mark("futures_refill")')
    read = src.index("_search_container_parent_ids(")
    mark = src.index('_mark("futures_containers")')
    flat = src.index("_deduped_page = deduped_futures[")
    families = src.index("_compose_futures_families(")
    assert refill < read < mark < flat < families
