"""#5917 — a board whose draw is over stops pricing the title it already awarded.

Measured on production ``GET /api/tournaments/us-open`` at 2026-09-13T13:07Z,
seventeen hours after the women's final:

| section | says |
|---|---|
| ``boards["Women's Singles"]`` | Rybakina ``0.99475`` / Sabalenka ``0.00525``, every row ``state: "live"``, ``price_state: "stale"``, ``age_hours: 7.34`` |
| ``results.matches[]`` womens-singles Final | ``winner_entity_key: "elena-rybakina"``, ``6-4, 5-7, 6-2``, ``completion: "final"`` |
| ``grids["womens-singles"]`` Rybakina ``title`` cell | ``note: "won"`` |

So the payload already knew.  The GRID says she won the title and the BOARD,
rendered three inches above it on the same screen, still asks who will — under a
staleness apology ("Updates paused. Last confirmed reading 7 hours ago"), two
inches from a settled prop correctly reading "Yes · Settled".

The grid cell is also this file's proof that the key space is right.
``title_verdict`` returns its ``"won"`` note ONLY when
``progress[draw].champion == entity_key``, so production's own payload
establishes that ``champion`` is populated, and that it is the register slug
``elena-rybakina`` — the space the board's rows are keyed in.  That is not a
detail: #5893's first implementation joined two sections of this payload on
``entity_key``, passed 23 tests, and fired on nothing.

The men's board carries the identical gap and reaches it when the final ends.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

from app.utils.grid_register import TERMINAL_RESULTS
from app.utils.tournament_board import (
    TERMINAL_ELIMINATED,
    TERMINAL_WON,
    apply_final_result,
    build_boards,
)
from app.utils.tournament_progress import DrawProgress

NOW = datetime(2026, 9, 13, 13, 7, 0, tzinfo=timezone.utc)

# The register's slugs — the board's key space, and (proved by the grid cell
# above) `champion`'s too.
RYBAKINA = "elena-rybakina"
SABALENKA = "aryna-sabalenka"
POTAPOVA = "anastasia-potapova"

# ESPN's space, which `champion` is NOT in. Present so the key-space guard has
# something real to be wrong with.
RYBAKINA_ESPN = "espn:athlete:2345"

POLY_AT = datetime(2026, 9, 13, 5, 45, 21, 308651, tzinfo=timezone.utc)

BOARD_RYBAKINA = 0.99475
BOARD_SABALENKA = 0.00525
BOARD_POTAPOVA = 0.001


def _source(source: str, market_id: int, outcome_id: int, **kw):
    block = {
        "source": source,
        "market_id": market_id,
        "outcome_id": outcome_id,
        "status": kw.pop("status", "live"),
        "terminal_result": kw.pop("terminal_result", None),
        "evidence": {"kind": "test"},
    }
    block.update(kw)
    return block


def _player(entity_key: str, name: str, sources: list[dict]):
    return {
        "entity_key": entity_key,
        "display_name": name,
        "draw": "womens-singles",
        "seed": None,
        "country": None,
        "draw_slot": None,
        "section": None,
        "sources": sources,
    }


def _register(players: list[dict]):
    return {
        "schema_version": "tournament-register/v1",
        "tournament": "us-open",
        "season": "2026",
        "version": 1,
        "generated_at": "2026-09-13T00:50:00+00:00",
        "draw_released": True,
        "players": players,
        "matchups": [],
    }


def _womens_register():
    return _register(
        [
            _player(RYBAKINA, "Elena Rybakina", [_source("kalshi", 30, 301)]),
            _player(SABALENKA, "Aryna Sabalenka", [_source("kalshi", 30, 302)]),
            _player(POTAPOVA, "Anastasia Potapova", [_source("polymarket", 40, 403)]),
        ]
    )


def _womens_prices():
    return {
        ("kalshi", 30, 301): {"probability": BOARD_RYBAKINA, "observed_at": POLY_AT},
        ("kalshi", 30, 302): {"probability": BOARD_SABALENKA, "observed_at": POLY_AT},
        ("polymarket", 40, 403): {"probability": BOARD_POTAPOVA, "observed_at": POLY_AT},
    }


# A real trend on every priced outcome. Not decoration: without it the rows
# `build_boards` produces carry `trend: []` already, and "the settle empties the
# trend" asserts nothing — the mutation sweep caught exactly that, and this is
# what makes that assertion bite.
_SERIES = {
    outcome: [("2026-09-11", 0.4), ("2026-09-12", 0.6)] for outcome in (301, 302, 403)
}

#: An outcome id that is only ever reached through a `missing` leg, carrying a
#: series far enough from the real one to move any point that wrongly blends it.
_MISSING_LEG = 599
_SERIES[_MISSING_LEG] = [("2026-09-11", 0.9), ("2026-09-12", 0.9)]

#: What `_SERIES` looks like once the builder has blended and rounded it. Written
#: out rather than derived from `_SERIES` by the same expression the code uses:
#: a fixture that recomputes the answer asserts only that the code is consistent
#: with itself (#5934).
_SERIES_AS_POINTS = [
    {"date": "2026-09-11", "probability": 0.4},
    {"date": "2026-09-12", "probability": 0.6},
]


def _boards(register=None, prices=None):
    """Real boards, through the real builder — never a hand-written row dict.

    A hand-built row would let every assertion below pass against a settled
    shape `build_boards` does not actually produce, which is the vacuity this
    file is most exposed to: the whole ship is "make these rows look like the
    settled rows the builder already makes".
    """
    built = build_boards(
        register if register is not None else _womens_register(),
        prices=prices if prices is not None else _womens_prices(),
        series_by_outcome=_SERIES,
        fine_series_by_outcome=_SERIES,
        now=NOW,
    )
    return built["boards"]


def _womens(boards):
    return next(b for b in boards if b["draw"] == "womens-singles")


def _row(board, entity_key):
    return next(r for r in board["rows"] if r["entity_key"] == entity_key)


def _decided(champion=RYBAKINA, draw="womens-singles"):
    return {draw: DrawProgress(champion=champion)}


# ── THE FIXTURE ITSELF IS THE DEFECT, SO ASSERT IT BEFORE FIXING IT ──────────


def test_the_board_starts_out_pricing_a_title_that_has_been_won():
    """The strawman guard: if this ever fails the rest of the file is vacuous."""
    board = _womens(_boards())
    assert board["price_state"] == "stale"
    assert board["newest_observed_at"] is not None
    # The trend has to be non-empty BEFORE, or "the settle empties it" is a
    # sentence about a list that was already empty.
    assert all(r["trend"] for r in board["rows"])
    for key, probability in (
        (RYBAKINA, BOARD_RYBAKINA),
        (SABALENKA, BOARD_SABALENKA),
        (POTAPOVA, BOARD_POTAPOVA),
    ):
        row = _row(board, key)
        assert row["state"] == "live"
        assert row["probability"] == pytest.approx(probability)


# ── THE SHIP ─────────────────────────────────────────────────────────────────


def test_every_row_settles_when_the_draw_has_a_champion():
    boards = _boards()
    changed = apply_final_result(boards, _decided(), now=NOW)
    board = _womens(boards)

    assert changed == 3
    assert _row(board, RYBAKINA)["state"] == TERMINAL_WON
    assert _row(board, SABALENKA)["state"] == TERMINAL_ELIMINATED
    # The 42 players the finalists beat are the point: settling only the final
    # pair would leave the board answering "who wins the title" a second time.
    assert _row(board, POTAPOVA)["state"] == TERMINAL_ELIMINATED
    for row in board["rows"]:
        assert row["probability"] is None
        assert row["probability_basis"] is None
        assert row["probability_is_live"] is False
        assert row["price_state"] == "dark"


# ── #5934: THE CHART SURVIVES THE SETTLE ─────────────────────────────────────
#
# The defect this covers was live on production: the Women's contender chart
# vanished from the US Open hub the moment the draw was decided, because every
# row reached `_settle_row` and `_settle_row` emptied the three fields the
# chart is drawn from. No frontend change could draw it — the points did not
# travel. Measured on the 15:05Z payload of 2026-09-13: 44 of 44 women's rows
# carried `trend: []`, against 36 of 36 men's rows carrying 19 points each.


def test_the_journey_survives_the_result_so_a_decided_draw_still_has_a_chart():
    """The ship. Settled kills the PRICE, not the history behind it."""
    boards = _boards()
    apply_final_result(boards, _decided(), now=NOW)
    board = _womens(boards)

    for row in board["rows"]:
        assert row["trend"] == _SERIES_AS_POINTS, row["display_name"]
        assert row["trend_hourly"], row["display_name"]
        assert row["trend_delta"] == pytest.approx(0.2), row["display_name"]
        # And the half that "settled means settled" governs is unchanged: the
        # journey travels, a live-reading percent does not.
        assert row["probability"] is None
        assert row["price_state"] == "dark"


def test_a_venue_settled_row_draws_its_journey_from_its_own_settled_legs():
    """The other path, which never had a trend at all — and is the one the
    Women's board lands on next.

    `futures_markets.status` for the Women's Singles Winner already read
    `resolved` on 2026-09-13 while the committed register still read `live`, so
    the next register rebuild moves those rows off `_settle_row` and onto this
    branch. Fixing only the other path would have been a fix with a fuse on it:
    the chart would come back tonight and vanish again on the rebuild.
    """
    register = _womens_register()
    register["players"][0]["sources"] = [
        _source("kalshi", 30, 301, status="settled", terminal_result=TERMINAL_WON)
    ]
    row = _row(_womens(_boards(register=register)), RYBAKINA)

    assert row["state"] == TERMINAL_WON
    assert row["probability"] is None
    assert row["trend"] == _SERIES_AS_POINTS
    assert row["trend_hourly"]
    assert row["trend_delta"] == pytest.approx(0.2)


def test_a_registered_leg_with_nothing_behind_it_contributes_no_journey():
    """`missing` is not a settled leg, and the row must not read its series.

    A missing leg has an id and no observations, so a series keyed on that id
    is somebody else's reading or a leftover. The two legs here carry
    DELIBERATELY DIFFERENT series, so including the missing one would move the
    blended point off `0.4/0.6` and this assertion would catch it — with equal
    fixtures it could not.
    """
    register = _womens_register()
    register["players"][0]["sources"] = [
        _source("kalshi", 30, 301, status="settled", terminal_result=TERMINAL_WON),
        _source("polymarket", 40, _MISSING_LEG, status="missing"),
    ]
    row = _row(_womens(_boards(register=register)), RYBAKINA)

    assert row["state"] == TERMINAL_WON
    assert row["trend"] == _SERIES_AS_POINTS, row["trend"]


def test_an_unpriced_settled_row_has_no_journey_to_show():
    """A settled leg whose outcome has no history publishes nothing — the empty
    list is a measurement, not a default. Without this the ship reads as "always
    emit points" and a series lookup that silently missed would look correct.
    """
    register = _womens_register()
    register["players"][0]["sources"] = [
        _source("kalshi", 30, 999, status="settled", terminal_result=TERMINAL_WON)
    ]
    row = _row(_womens(_boards(register=register)), RYBAKINA)

    assert row["state"] == TERMINAL_WON
    assert row["trend"] == []
    assert row["trend_hourly"] == []
    assert row["trend_delta"] is None


def test_a_settled_row_matches_the_shape_the_builder_already_publishes():
    """The two ways a board can settle must be one shape, field for field.

    Driven off `build_boards`' OWN market-settled row rather than a list of
    field names written out here: a literal list would go stale the day the
    settled shape gains a field, and silently stop checking it.
    """
    venue_settled = _womens_register()
    venue_settled["players"][0]["sources"] = [
        _source("kalshi", 30, 301, status="settled", terminal_result=TERMINAL_WON)
    ]
    reference = _row(_womens(_boards(register=venue_settled)), RYBAKINA)

    boards = _boards()
    apply_final_result(boards, _decided(), now=NOW)
    ours = _row(_womens(boards), RYBAKINA)

    # `rank` alone: the two boards are ranked over different rows. The three
    # trend fields USED to be exempt here, and #5934 is what that exemption was
    # hiding — the two paths disagreed about the journey and the mirror could
    # not see it. They are now compared like every other field.
    volatile = {"rank"}
    for field, value in reference.items():
        if field in volatile:
            continue
        assert ours[field] == value, field
    # Named, so the mirror cannot be satisfied by both paths publishing nothing
    # (which is what it asserted before this ship, on both sides).
    assert ours["trend"] == _SERIES_AS_POINTS, ours["trend"]
    assert reference["trend"] == _SERIES_AS_POINTS, reference["trend"]


def test_the_champion_is_ranked_first_even_when_they_were_ranked_last():
    """The upset, which is the only case where this is observable.

    With every probability `None`, `_rank_rows`' sort key is equal for every
    row, so a stable sort leaves the winner exactly where the outright market's
    last prices put them. A favourite is already first and proves nothing.
    """
    boards = _boards()
    before = [r["entity_key"] for r in _womens(boards)["rows"]]
    assert before.index(POTAPOVA) == len(before) - 1, before

    apply_final_result(boards, _decided(champion=POTAPOVA), now=NOW)
    board = _womens(boards)

    assert board["rows"][0]["entity_key"] == POTAPOVA
    assert board["rows"][0]["rank"] == 1
    assert board["rows"][0]["state"] == TERMINAL_WON
    # The rest keep their order relative to each other.
    assert [r["entity_key"] for r in board["rows"][1:]] == [RYBAKINA, SABALENKA]


def test_the_board_names_the_champion_and_is_silent_otherwise():
    boards = _boards()
    apply_final_result(boards, _decided(), now=NOW)
    assert _womens(boards)["decided"] == {"winner_entity_key": RYBAKINA}


def test_an_undecided_board_has_no_decided_key_at_all():
    """Absent, never `None` — one falsy shape for a reader to test, not two."""
    boards = _boards()
    apply_final_result(boards, {}, now=NOW)
    assert "decided" not in _womens(boards)


# ── THE BANNER, WHICH IS THE PART THAT PROTECTS THE RENDER HALF ──────────────


def test_the_freshness_banner_is_left_exactly_as_it_was():
    """Recomputing it would print "No numbers yet" on a finished draw.

    `_board_summary` reads the rows' `freshest_observed_at`, and a settled row
    has none — so a recompute takes `newest_observed_at` to `None` and
    `price_state` to `dark`, which is the exact pair the renderer words as "No
    market has put a probability on this draw yet". On a draw that finished
    yesterday that is worse than the sentence being fixed, and it would be live
    for however long this ship and its render half are apart.
    """
    before = _womens(_boards())
    banner_before = {
        k: before[k] for k in ("price_state", "newest_observed_at", "age_hours")
    }

    boards = _boards()
    apply_final_result(boards, _decided(), now=NOW)
    board = _womens(boards)

    assert {
        k: board[k] for k in ("price_state", "newest_observed_at", "age_hours")
    } == banner_before
    # Named separately because it is the specific branch that would fire.
    assert board["newest_observed_at"] is not None
    assert board["price_state"] != "dark"


def test_the_counts_beside_the_banner_are_re_derived_not_preserved():
    """"0 rows are not live" is true of a board with no probabilities on it."""
    assert _womens(_boards())["rows_not_live"] == 3

    boards = _boards()
    apply_final_result(boards, _decided(), now=NOW)
    board = _womens(boards)
    assert board["rows_not_live"] == 0
    assert board["mixed_freshness_rows"] == 0


# ── REFUSALS ─────────────────────────────────────────────────────────────────


def test_a_draw_with_no_champion_is_left_alone():
    boards = _boards()
    untouched = copy.deepcopy(boards)
    assert apply_final_result(boards, {"womens-singles": DrawProgress()}, now=NOW) == 0
    assert boards == untouched


@pytest.mark.parametrize("progress", [None, {}, {"womens-singles": None}])
def test_no_usable_progress_is_left_alone(progress):
    boards = _boards()
    untouched = copy.deepcopy(boards)
    assert apply_final_result(boards, progress, now=NOW) == 0
    assert boards == untouched


def test_a_champion_in_the_wrong_key_space_settles_nothing():
    """The #5893 failure mode, aimed at this overlay.

    `build_progress` resolves ESPN's name into the register's `entity_key`
    space, so the champion arrives as `elena-rybakina`. If that ever changed to
    ESPN's own id the join would stop matching, and this asserts the overlay
    then publishes NOTHING rather than settling a board around a winner it
    cannot place.
    """
    boards = _boards()
    untouched = copy.deepcopy(boards)
    assert apply_final_result(boards, _decided(champion=RYBAKINA_ESPN), now=NOW) == 0
    assert boards == untouched


def test_a_champion_who_is_not_on_this_board_settles_nothing():
    boards = _boards()
    untouched = copy.deepcopy(boards)
    assert apply_final_result(boards, _decided(champion="iga-swiatek"), now=NOW) == 0
    assert boards == untouched


def test_a_board_already_naming_a_different_champion_is_left_alone():
    """Two authorities disagreeing about who won.

    The venue has settled Sabalenka as the winner and the scoreboard says
    Rybakina. Publishing either is picking a side of a contradiction.
    """
    contradicted = _womens_register()
    contradicted["players"][1]["sources"] = [
        _source("kalshi", 30, 302, status="settled", terminal_result=TERMINAL_WON)
    ]
    boards = _boards(register=contradicted)
    untouched = copy.deepcopy(boards)

    assert apply_final_result(boards, _decided(), now=NOW) == 0
    assert boards == untouched


def test_a_board_already_naming_the_SAME_champion_still_settles_the_rest():
    """The agreeing case must not be swept up by the contradiction refusal.

    Without this the guard above passes just as well with `row is not
    winner_row` deleted, and the overlay would refuse every board the venue had
    already settled correctly — the common case as a tournament ages.
    """
    agreeing = _womens_register()
    agreeing["players"][0]["sources"] = [
        _source("kalshi", 30, 301, status="settled", terminal_result=TERMINAL_WON)
    ]
    boards = _boards(register=agreeing)

    # 3, not 2: the already-settled winner is written again rather than skipped.
    # Re-stating a row that already agreed is idempotent, and counting it keeps
    # `changed` meaning "rows this overlay wrote" rather than "rows whose value
    # differed", which would be a second, unasserted rule.
    assert apply_final_result(boards, _decided(), now=NOW) == 3
    board = _womens(boards)
    assert _row(board, RYBAKINA)["state"] == TERMINAL_WON
    assert _row(board, SABALENKA)["state"] == TERMINAL_ELIMINATED


def test_a_board_with_no_rows_is_left_alone():
    boards = [{"draw": "womens-singles", "rows": []}]
    assert apply_final_result(boards, _decided(), now=NOW) == 0
    assert boards == [{"draw": "womens-singles", "rows": []}]


def test_a_non_dict_board_is_skipped_rather_than_raising():
    boards = _boards()
    mixed = [None, "not a board", *boards]
    assert apply_final_result(mixed, _decided(), now=NOW) == 3


def test_only_the_decided_draw_moves():
    """A second board in the same payload must not be settled by proxy."""
    boards = _boards()
    boards.append(
        {
            "draw": "mens-singles",
            "rows": [
                {"entity_key": RYBAKINA, "state": "live", "probability": 0.5},
            ],
        }
    )
    apply_final_result(boards, _decided(), now=NOW)
    mens = next(b for b in boards if b["draw"] == "mens-singles")
    assert mens["rows"][0]["state"] == "live"
    assert mens["rows"][0]["probability"] == 0.5
    assert "decided" not in mens


# ── THE VOCABULARY ───────────────────────────────────────────────────────────


def test_the_row_states_are_the_registers_own_terminal_results():
    """Pinned in BOTH directions.

    `_row_state` publishes the register's `terminal_result` verbatim for a
    venue-settled row. If that tuple ever gains, loses or reorders a member,
    this overlay would start writing a state no other settled row uses and the
    two ways a board can settle would drift into two vocabularies.
    """
    assert (TERMINAL_WON, TERMINAL_ELIMINATED) == TERMINAL_RESULTS
    assert TERMINAL_WON == "won"
    assert TERMINAL_ELIMINATED == "eliminated"


# ═══ THE WIRING, THROUGH THE REAL ROUTE ══════════════════════════════════════
#
# Every test above drives `apply_final_result` directly, and all of them passed
# against a first draft that read `first.get("results")` — a key that only
# exists in the OTHER fragment (`REST_SECTION_KEYS`), so the overlay would have
# fired on nothing in production while this file stayed green. That is #5893's
# failure mode exactly, one ship later, and the unit tests structurally cannot
# see it. So the guard below builds the FIRST SCREEN ONLY through the real
# `_build_sections` and asserts the board comes back decided.
#
# `espn_round` is the register's own `"F"` rather than ESPN's `"Final"`:
# `_round_key` accepts a register key directly and only consults
# `espn_round_key` when a draw SIZE is known, which needs register matchups this
# fixture has no reason to carry. The name-to-key mapping is
# `tournament_progress`' own guarded concern; what is unguarded, and what this
# asserts, is that the route hands this overlay a populated `progress` at all.

from app.routes import tournaments as route  # noqa: E402
from app.utils.tournament_register import SCHEMA_VERSION  # noqa: E402

RYBAKINA_OUTCOME, SABALENKA_OUTCOME = 910101, 910102


def _route_register():
    return {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 14,
        "generated_at": "2026-09-13T00:50:00+00:00",
        "draw_released": True,
        "players": [
            {
                "entity_key": RYBAKINA,
                "display_name": "Elena Rybakina",
                "draw": "womens-singles",
                "seed": None,
                "country": None,
                "draw_slot": None,
                "section": None,
                "sources": [_source("kalshi", 30, RYBAKINA_OUTCOME)],
            },
            {
                "entity_key": SABALENKA,
                "display_name": "Aryna Sabalenka",
                "draw": "womens-singles",
                "seed": None,
                "country": None,
                "draw_slot": None,
                "section": None,
                "sources": [_source("kalshi", 30, SABALENKA_OUTCOME)],
            },
        ],
        "matchups": [],
    }


@pytest.fixture
def routed(monkeypatch: pytest.MonkeyPatch):
    observed = datetime.now(timezone.utc)

    monkeypatch.setattr(route, "load_register", lambda slug, season: _route_register())

    async def _read_links(slug):  # noqa: ANN001
        return {"links": {}, "authority_links": {}}

    async def _load_prices(db, ids, *, now):  # noqa: ANN001
        return {
            RYBAKINA_OUTCOME: {
                "probability": BOARD_RYBAKINA,
                "observed_at": observed,
            },
            SABALENKA_OUTCOME: {
                "probability": BOARD_SABALENKA,
                "observed_at": observed,
            },
        }

    async def _load_series(db, ids, *, now):  # noqa: ANN001
        return {}

    async def _load_fine_series(db, ids, *, now):  # noqa: ANN001
        return {}

    async def _resolve_matchup_events(db, register):  # noqa: ANN001
        return {"by_event": {}, "by_matchup": {}, "reason_counts": {}}

    async def _espn_results(slug):  # noqa: ANN001
        """One decided final, in `parse_results`' own shape."""
        return {
            "scoreboard": "live",
            "order_of_play_complete": True,
            "order_of_play": {},
            "draws": {
                "womens-singles": {
                    "rybakina|sabalenka": {
                        "espn_round": "F",
                        "completion": "final",
                        # ALREADY normalized, and `normalize_name` strips the
                        # space: `build_progress` compares this against
                        # `normalize_name(player)` directly, so "elena rybakina"
                        # matches nobody and BOTH finalists come back
                        # eliminated with `champion: None`.
                        "winner_normalized": "elenarybakina",
                        "players": ["Elena Rybakina", "Aryna Sabalenka"],
                        "score": "6-4, 5-7, 6-2",
                    }
                }
            },
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


async def _first_screen(monkeypatch=None):
    sections = await route._build_sections(
        "us-open",
        route.REGISTERED_TOURNAMENTS["us-open"],
        None,  # type: ignore[arg-type]
        groups=(route.SECTION_FIRST,),
    )
    return sections[route.SECTION_FIRST]


async def test_a_first_only_request_serves_the_board_already_decided(routed):
    """The guard that a `rest`-fragment input would fail.

    `results` is a `rest` key and `boards` is a `first` key, so a
    first-screen-only request is the one where an overlay fed from the wrong
    fragment settles nothing.
    """
    first = await _first_screen()

    boards = first["boards"]
    board = next(b for b in boards if b["draw"] == "womens-singles")
    # The vacuity gate: if the route built no priced rows, nothing below means
    # anything.
    assert len(board["rows"]) == 2, board["rows"]

    assert board["decided"] == {"winner_entity_key": RYBAKINA}
    assert _row(board, RYBAKINA)["state"] == TERMINAL_WON
    assert _row(board, SABALENKA)["state"] == TERMINAL_ELIMINATED
    assert all(r["probability"] is None for r in board["rows"])
    # And `results` is genuinely absent from this fragment — the fact that makes
    # this test the one that catches it.
    assert "results" not in first
