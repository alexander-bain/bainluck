"""#6644 — the playoff grid stops publishing the order the draw already retired.

THE SPECIMEN, measured off production ``GET /api/tournaments/us-open`` at
2026-09-17T01:00Z, four days after both finals, on one screen:

| | TO WIN THE TITLE board | CHANCE OF REACHING grid |
|---|---|---|
| 1 | Alexander Zverev | Alexander Zverev |
| 2 | **Ben Shelton** (lost the final) | **Grigor Dimitrov** (lost in R128) |
| 3 | Frances Tiafoe (SF) | Jiri Lehecka |
| 4 | Karen Khachanov (SF) | Matteo Berrettini |

Shelton was served 2nd by the board and **21st** by the grid — ``rank: 21`` in
the payload, three inches below ``rank: 2`` — and the women's draw carried the
same shape (Sabalenka 2nd and 32nd).  So the grid's first screen was the
champion followed by four rows of em-dashes.

THE CAUSE IS THE CALL ORDER, NOT THE KEY.  ``build_grids`` runs at
``routes/tournaments.py:1936`` in the ``rest`` fragment and copies a board row's
``rank`` by value; ``apply_final_result`` reorders the board 173 lines later in
``first``.  The grid froze the PRE-SETTLE order.  Before #6628 shipped, that
order differed from the settled one only by the champion pin — and in both
draws the champion was also the price favourite — so the two surfaces agreed by
luck and nothing showed.

WHAT THESE TESTS HOLD.  Not either surface's contents: that the two AGREE, and
that they agree on a request that builds only one of them.  A grid ordered by
"whatever list I was handed" passes any assertion written about its own rows.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from itertools import permutations

import pytest

from app.routes import tournaments as route
from app.utils.tournament_board import (
    apply_final_result,
    build_boards,
    decided_board_order,
)
from app.utils.tournament_grid import build_playoff_grid
from app.utils.tournament_progress import DrawProgress, build_progress
from app.utils.tournament_register import SCHEMA_VERSION

NOW = datetime(2026, 9, 17, 1, 0, 0, tzinfo=timezone.utc)
OBSERVED = datetime(2026, 9, 16, 23, 30, 0, tzinfo=timezone.utc)
DRAW = "womens-singles"
SIZES = {DRAW: 128}

RYBAKINA = "elena-rybakina"
SABALENKA = "aryna-sabalenka"
POTAPOVA = "anastasia-potapova"

#: THE UPSET SHAPE, and it is the whole specimen: the champion is NOT the price
#: favourite and the losing finalist is NOT second on price. A board whose
#: prices already agree with the result cannot show this defect — which is
#: exactly why production hid it for as long as it did.
PRICES = {RYBAKINA: 0.10, SABALENKA: 0.20, POTAPOVA: 0.70}
OUTCOMES = {RYBAKINA: 301, SABALENKA: 302, POTAPOVA: 303}

#: The order the RESULT puts them in: champion, losing finalist, first-round
#: loser. Written out rather than derived from `_decided_order_key`, so a
#: fixture cannot agree with the code by construction.
BY_RESULT = [RYBAKINA, SABALENKA, POTAPOVA]

#: The order the dead outright PRICES put them in — what both surfaces served
#: before this ship, and what the grid alone served after #6628.
BY_PRICE = [POTAPOVA, SABALENKA, RYBAKINA]


def _player(entity_key: str, name: str) -> dict:
    return {
        "entity_key": entity_key,
        "display_name": name,
        "draw": DRAW,
        "seed": None,
        "country": None,
        "draw_slot": None,
        "section": None,
        "sources": [
            {
                "source": "kalshi",
                "market_id": 30,
                "outcome_id": OUTCOMES[entity_key],
                "status": "live",
                "terminal_result": None,
                "evidence": {"kind": "test"},
            }
        ],
    }


def _register() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 1,
        "generated_at": "2026-09-13T00:50:00+00:00",
        "draw_released": True,
        "players": [
            _player(RYBAKINA, "Elena Rybakina"),
            _player(SABALENKA, "Aryna Sabalenka"),
            _player(POTAPOVA, "Anastasia Potapova"),
        ],
        # ONE MATCHUP, AND IT IS LOAD-BEARING: the route sizes the draw from the
        # largest `R<n>` round the REGISTER carries (`first_round_size`), and
        # without a size "Round 1" is not a round at all — `build_progress`
        # returns nothing for the draw and the page under test is an undecided
        # one. A register with no matchups makes the route tests below vacuous
        # rather than failing, which is why this is stated here.
        "matchups": [
            {
                "matchup_key": f"{DRAW}:{POTAPOVA}-vs-qualifier:2026-08-25",
                "draw": DRAW,
                "round": "R128",
                "scheduled_date": "2026-08-25",
                "players": [POTAPOVA, "unresolvable-opponent"],
                "sources": [],
            }
        ],
        "reaches": [],
    }


def _prices_by_key() -> dict:
    return {
        ("kalshi", 30, OUTCOMES[key]): {
            "probability": value,
            "observed_at": OBSERVED,
        }
        for key, value in PRICES.items()
    }


def _prices_by_outcome() -> dict:
    return {
        OUTCOMES[key]: {"probability": value, "observed_at": OBSERVED}
        for key, value in PRICES.items()
    }


def _espn_draws() -> dict:
    """``parse_results``' own shape — the final, plus a first round Potapova lost.

    Two matches and not one: with the final alone the two finalists are the only
    players with a proven depth, and a three-row board orders itself correctly
    by accident. The early round is what makes "further is higher" a claim the
    order can get wrong.
    """
    return {
        "womens-singles": {
            "rybakina|sabalenka": {
                "players": ["Elena Rybakina", "Aryna Sabalenka"],
                "espn_round": "Final",
                "winner_name": "Elena Rybakina",
                "winner_normalized": "elenarybakina",
                "completion": "final",
                "score": "6-4, 5-7, 6-2",
                "espn_competition_id": None,
            },
            "potapova|qualifier": {
                "players": ["Anastasia Potapova", "Unresolvable Opponent"],
                "espn_round": "Round 1",
                "winner_name": "Unresolvable Opponent",
                "winner_normalized": "unresolvableopponent",
                "completion": "final",
                "score": "6-3, 6-3",
                "espn_competition_id": None,
            },
        }
    }


def _progress() -> DrawProgress:
    """Through the real builder, never a hand-written ``DrawProgress``.

    The depth map is the input the whole ordering rests on; writing it by hand
    would let these tests pass against a shape ``build_progress`` does not
    produce — the failure mode #5893 shipped (23 green tests, fired on nothing).
    """
    return build_progress(
        _register(), {"draws": _espn_draws()}, draw_sizes=SIZES
    )[DRAW]


def _boards() -> list[dict]:
    built = build_boards(
        _register(),
        prices=_prices_by_key(),
        series_by_outcome={},
        fine_series_by_outcome={},
        now=NOW,
    )
    return built["boards"]


def _womens(boards: list[dict]) -> dict:
    return next(b for b in boards if b["draw"] == DRAW)


def _grid(board_rows: list[dict], progress=None) -> dict:
    return build_playoff_grid(
        _register(),
        board_rows=board_rows,
        prices=_prices_by_outcome(),
        draw=DRAW,
        now=NOW,
        progress=progress,
    )


def _keys(rows: list[dict]) -> list[str]:
    return [row["entity_key"] for row in rows]


# ── THE FIXTURE IS THE DEFECT, SO PIN IT BEFORE ASSERTING THE FIX ────────────


def test_the_specimen_really_does_arrive_in_the_dead_prices_order():
    """Vacuity gate. Nothing below means anything if the input is already right."""
    assert _keys(_womens(_boards())["rows"]) == BY_PRICE


def test_the_specimen_really_is_a_decided_draw_with_a_proven_depth():
    """The other vacuity gate: an empty depth map orders nothing but the champion."""
    prog = _progress()
    assert prog.champion == RYBAKINA
    assert prog.reached[SABALENKA] > prog.reached[POTAPOVA], prog.reached


def test_an_unfixed_grid_would_serve_the_order_the_board_no_longer_holds():
    """The defect itself, reproduced: hand the grid the pre-settle rows.

    This is the production shape exactly — `build_grids` is called with
    `base["boards"]` before any overlay has touched them.
    """
    grid = _grid(_womens(_boards())["rows"], progress=None)
    assert _keys(grid["rows"]) == BY_PRICE


# ── WHAT THE SHIP IS: THE TWO SURFACES AGREE ─────────────────────────────────


def test_the_grid_and_the_board_serve_one_order_on_a_decided_draw():
    """The contract, asserted as an AGREEMENT rather than as either's contents.

    Both sides are built from the SAME pre-settle rows, the way the route does
    it: the grid from `base["boards"]`, the board from the overlay that runs
    173 lines later. A grid that orders itself by the list it was handed passes
    every assertion written about its own rows and fails this one.
    """
    pre_settle = _womens(_boards())["rows"]
    grid = _grid(copy.deepcopy(pre_settle), progress=_progress())

    boards = _boards()
    apply_final_result(boards, {DRAW: _progress()}, now=NOW)
    board = _womens(boards)

    assert _keys(grid["rows"]) == _keys(board["rows"])
    # Named too, so the agreement cannot be satisfied by both surfaces being
    # wrong in the same way — the risk of asserting only that two things match.
    assert _keys(grid["rows"]) == BY_RESULT


def test_the_two_surfaces_agree_on_each_players_rank_not_only_on_the_order():
    """`rank` is copied by VALUE into the grid, so position and number can part.

    They did on production: Ben Shelton was `rank: 2` on the board and
    `rank: 21` in the grid of the same payload, which is the headline of #6644
    and the half a reorder alone would leave live in the payload.
    """
    grid = _grid(copy.deepcopy(_womens(_boards())["rows"]), progress=_progress())

    boards = _boards()
    apply_final_result(boards, {DRAW: _progress()}, now=NOW)
    board_rank = {row["entity_key"]: row["rank"] for row in _womens(boards)["rows"]}

    assert {row["entity_key"]: row["rank"] for row in grid["rows"]} == board_rank
    assert board_rank == {RYBAKINA: 1, SABALENKA: 2, POTAPOVA: 3}


def test_the_grid_reaches_the_same_order_from_any_order_it_is_handed():
    """The ordering is the RESULT's, not a repair of one particular input.

    Every permutation, and not one shuffle: reversing THIS fixture happens to
    produce the answer (`BY_PRICE` reversed IS `BY_RESULT`), so a single
    reordered input would have passed against the unfixed grid — measured, on
    the red-first run of this file.
    """
    rows = _womens(_boards())["rows"]
    by_key = {row["entity_key"]: row for row in rows}
    for order in permutations(BY_RESULT):
        handed = [copy.deepcopy(by_key[key]) for key in order]
        assert _keys(_grid(handed, progress=_progress())["rows"]) == BY_RESULT, order


def test_the_grid_does_not_reorder_the_list_its_caller_handed_it():
    """`base["boards"]` is the object `first`'s overlays run on afterwards.

    A grid that sorted in place would reorder the board before the blend
    overlay reached it — moving a defect rather than removing one.
    """
    boards = _boards()
    rows = _womens(boards)["rows"]
    _grid(rows, progress=_progress())
    assert _keys(rows) == BY_PRICE


# ── WHERE THE BOARD REFUSES TO SETTLE, THE GRID REFUSES TO REORDER ───────────


@pytest.mark.parametrize(
    "progress,why",
    [
        (None, "no results at all"),
        (DrawProgress(), "results that prove nothing"),
        (DrawProgress(champion="espn:athlete:2345"), "a champion in ESPN's key space"),
        (DrawProgress(champion="carlos-alcaraz"), "a champion who is not on this board"),
    ],
)
def test_an_undecided_draw_keeps_the_boards_own_rank_order(progress, why):
    """Each of these is a case where `apply_final_result` publishes nothing.

    A grid that reordered itself on a draw the board left alone would re-create
    the disagreement from the other side, with the two answers merely swapped.
    """
    grid = _grid(_womens(_boards())["rows"], progress=progress)
    assert _keys(grid["rows"]) == BY_PRICE, why
    assert [row["rank"] for row in grid["rows"]] == [1, 2, 3], why


def test_a_board_already_naming_a_different_champion_is_left_alone():
    """Two authorities disagreeing about who won; ordering by either picks a side."""
    rows = _womens(_boards())["rows"]
    next(r for r in rows if r["entity_key"] == POTAPOVA)["state"] = "won"

    assert decided_board_order(rows, _progress()) is None
    assert _keys(_grid(rows, progress=_progress())["rows"]) == BY_PRICE


# ── AND IT HOLDS ON A REQUEST THAT BUILDS ONLY THE GRID ──────────────────────


@pytest.fixture
def routed(monkeypatch: pytest.MonkeyPatch):
    """The route, with every I/O edge stubbed and the finals already played."""
    monkeypatch.setattr(route, "load_register", lambda slug, season: _register())

    async def _read_links(slug):  # noqa: ANN001
        return {"links": {}, "authority_links": {}}

    async def _load_prices(db, ids, *, now):  # noqa: ANN001
        return _prices_by_outcome()

    async def _load_series(db, ids, *, now):  # noqa: ANN001
        return {}

    async def _load_fine_series(db, ids, *, now):  # noqa: ANN001
        return {}

    async def _resolve_matchup_events(db, register):  # noqa: ANN001
        return {"by_event": {}, "by_matchup": {}, "reason_counts": {}}

    async def _espn_results(slug):  # noqa: ANN001
        return {
            "scoreboard": "live",
            "order_of_play_complete": True,
            "order_of_play": {},
            "draws": _espn_draws(),
        }

    async def _resolve_espn(db, comp_ids, sport_keys):  # noqa: ANN001
        return {"by_espn": {}, "reason_counts": {}}

    monkeypatch.setattr(route, "read_links", _read_links)
    monkeypatch.setattr(route, "_load_prices", _load_prices)
    monkeypatch.setattr(route, "_load_series", _load_series)
    monkeypatch.setattr(route, "_load_fine_series", _load_fine_series)
    monkeypatch.setattr(route, "resolve_matchup_events", _resolve_matchup_events)
    monkeypatch.setattr(route, "_espn_results", _espn_results)
    monkeypatch.setattr(route, "resolve_espn_competition_events", _resolve_espn)


async def _sections(*groups: str) -> dict:
    return await route._build_sections(
        "us-open",
        route.REGISTERED_TOURNAMENTS["us-open"],
        None,  # type: ignore[arg-type]
        groups=groups,
    )


async def test_a_whole_page_serves_one_order_in_both_of_its_sections(routed):
    """Through the route, with the two builds 173 lines and one fragment apart."""
    sections = await _sections(route.SECTION_FIRST, route.SECTION_REST)

    board = next(
        b for b in sections[route.SECTION_FIRST]["boards"] if b["draw"] == DRAW
    )
    grid = sections[route.SECTION_REST]["grids"][DRAW]
    # The vacuity gate: if the route built no rows, nothing below means anything.
    assert len(board["rows"]) == 3, board["rows"]
    assert board["decided"] == {"winner_entity_key": RYBAKINA}

    assert _keys(grid["rows"]) == _keys(board["rows"]) == BY_RESULT


async def test_a_rest_only_request_orders_the_grid_the_same_way(routed):
    """The fragment trap, and the reason the grid asks `progress` and not the board.

    `rest` builds no boards and runs no overlay at all, so a fix that settled
    the boards before the split would leave this request serving the dead
    order — a grid whose answer depends on which sections a client asked for.
    """
    rest_only = (await _sections(route.SECTION_REST))[route.SECTION_REST]
    whole = (await _sections(route.SECTION_FIRST, route.SECTION_REST))[
        route.SECTION_REST
    ]

    assert "boards" not in rest_only
    assert _keys(rest_only["grids"][DRAW]["rows"]) == BY_RESULT
    assert _keys(rest_only["grids"][DRAW]["rows"]) == _keys(whole["grids"][DRAW]["rows"])
    assert [r["rank"] for r in rest_only["grids"][DRAW]["rows"]] == [1, 2, 3]
