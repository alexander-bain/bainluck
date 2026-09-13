"""#5893 — the hub stops answering "who wins the final" twice on one screen.

Measured on production ``GET /api/tournaments/us-open`` at 2026-09-13T11:14:15Z,
men's final day, seven hours before the match:

| section | Zverev | Shelton | observed |
|---|---|---|---|
| ``slate.matches[0]`` (NEXT UP) | ``0.575`` | ``0.425`` | 10:52:52Z, 3 sources, ``price_basis: blend`` |
| ``boards["Men's Singles"]`` | ``0.57225`` | ``0.4255`` | kalshi 0.565 @10:50:34Z + polymarket 0.5795 @05:45:21Z |

Alex's own screenshot (`artifacts-native-020/n143-hub-usopen-3.png`, iPhone 17)
catches 58% and 57% in one viewport with no scrolling.

**Renormalising the board does not fix it** — that is the finding these tests
exist to keep fixed.  The board's 36 rows sum to 1.00825, and dividing it out
gives 0.57225 / 1.00825 = 0.5676, which still prints 57.  The two numbers are
two different markets (the draw's outright vs the linked event's blend), so the
only reconciliation is the one Alex's standing ruling already names: one number
per question, and the blend is the product.  The board defers.

The values below are that production payload's.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.tournament_board import (
    FINAL_ROUND,
    PROBABILITY_BASIS_FINAL,
    PROBABILITY_BASIS_OUTRIGHT,
    apply_final_match_blend,
    build_boards,
)
from app.utils.tournament_register import ROUNDS, STALE_PRICE_HOURS

NOW = datetime(2026, 9, 13, 11, 14, 15, tzinfo=timezone.utc)

# ── THE TWO KEY SPACES, AS PRODUCTION SERVES THEM ────────────────────────────
#
# Read off the same payload: the board's rows are keyed by the REGISTER's slug
# and the card's sides by ESPN's athlete id. A fixture that used one space for
# both would pass against a join that fires on nothing in production, which is
# exactly the bug this file caught while it was being written.
#
#   boards["Men's Singles"].rows[0].entity_key == "alexander-zverev"
#   slate.matches[0].sides[0].entity_key       == "espn:athlete:2375"
ZVEREV = "alexander-zverev"
SHELTON = "ben-shelton"
DIMITROV = "grigor-dimitrov"

ZVEREV_ESPN = "espn:athlete:2375"
SHELTON_ESPN = "espn:athlete:9250"
DIMITROV_ESPN = "espn:athlete:1000003"

# The two outright legs behind the men's board, verbatim from the payload.
KALSHI_AT = datetime(2026, 9, 13, 10, 50, 34, 208617, tzinfo=timezone.utc)
POLY_AT = datetime(2026, 9, 13, 5, 45, 21, 308651, tzinfo=timezone.utc)
# And the linked event's blend, which the slate publishes.
MATCH_AT = datetime(2026, 9, 13, 10, 52, 52, 27302, tzinfo=timezone.utc)

BOARD_ZVEREV = 0.57225
BOARD_SHELTON = 0.4255
MATCH_ZVEREV = 0.575
MATCH_SHELTON = 0.425


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


def _player(entity_key: str, name: str, draw: str, sources: list[dict]):
    return {
        "entity_key": entity_key,
        "display_name": name,
        "draw": draw,
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


def _mens_register():
    """The men's board as production built it: two finalists and one eliminated
    player still carried at the polymarket dust price of 0.001."""
    return _register(
        [
            _player(
                ZVEREV,
                "Alexander Zverev",
                "mens-singles",
                [_source("kalshi", 10, 101), _source("polymarket", 20, 201)],
            ),
            _player(
                SHELTON,
                "Ben Shelton",
                "mens-singles",
                [_source("kalshi", 10, 102), _source("polymarket", 20, 202)],
            ),
            _player(
                DIMITROV,
                "Grigor Dimitrov",
                "mens-singles",
                [_source("polymarket", 20, 203)],
            ),
        ]
    )


def _mens_prices():
    return {
        ("kalshi", 10, 101): {"probability": 0.565, "observed_at": KALSHI_AT},
        ("polymarket", 20, 201): {"probability": 0.5795, "observed_at": POLY_AT},
        ("kalshi", 10, 102): {"probability": 0.425, "observed_at": KALSHI_AT},
        ("polymarket", 20, 202): {"probability": 0.426, "observed_at": POLY_AT},
        ("polymarket", 20, 203): {"probability": 0.001, "observed_at": POLY_AT},
    }


def _boards(register=None, prices=None):
    """Real boards, through the real builder — never a hand-written row dict.

    A fixture board would let this whole file pass against a `build_boards` that
    had stopped producing the fields the overlay reads.
    """
    built = build_boards(
        register if register is not None else _mens_register(),
        prices=prices if prices is not None else _mens_prices(),
        now=NOW,
    )
    return built["boards"]


def _side(entity_key: str, name: str, probability, observed=MATCH_AT):
    return {
        "entity_key": entity_key,
        "display_name": name,
        "seed": None,
        "country": None,
        "image": {"url": None, "flag_url": None},
        "role": "contender",
        "probability": probability,
        "opening_probability": None,
        "move": None,
        "raw_probability": probability,
        "raw_opening_probability": probability,
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "age_hours": 0.36,
        "price_state": "live",
        "liquidity": "traded",
        "liquidity_reasons": [],
    }


def _final_row(**over):
    """The served shape of the men's final, as `build_slate` published it."""
    row = {
        "priced": True,
        "matchup_key": "espn:182677",
        "event_id": 15310688,
        "draw": "mens-singles",
        "round": "F",
        "scheduled_date": "2026-09-13T18:00:00+00:00",
        "live_state": "upcoming",
        "sides": [
            _side(ZVEREV_ESPN, "Alexander Zverev", MATCH_ZVEREV),
            _side(SHELTON_ESPN, "Ben Shelton", MATCH_SHELTON),
        ],
        "coherent": True,
        "raw_sum": 1.0,
        "opening_raw_sum": 1.01,
        "probability_is_live": True,
        "price_state": "live",
        "observed_at": MATCH_AT.isoformat(),
        "age_hours": 0.36,
        "freshest_observed_at": MATCH_AT.isoformat(),
        "freshest_age_hours": 0.36,
        "stale_sides": [],
        "mixed_freshness": False,
        "favourite": ZVEREV,
        "has_moved": False,
        "price_basis": "blend",
        "blend_refusal": "BLEND_HAS_NO_OPEN",
        "source_count": 3,
        "liquidity": "traded",
        "liquidity_reasons": [],
        "pairing_source": "scoreboard",
    }
    row.update(over)
    return row


def _slate(*matches):
    return {"matches": list(matches), "count": len(matches)}


def _row(boards, entity_key, draw="mens-singles"):
    board = next(b for b in boards if b["draw"] == draw)
    return next(r for r in board["rows"] if r["entity_key"] == entity_key)


# ── THE DEFECT ───────────────────────────────────────────────────────────────


def test_the_board_publishes_the_finals_blend_not_its_own_outright():
    boards = _boards()
    # The defect, reproduced first: without the overlay the board disagrees.
    assert _row(boards, ZVEREV)["probability"] == pytest.approx(BOARD_ZVEREV)

    changed = apply_final_match_blend(boards, _slate(_final_row()), now=NOW)

    assert changed == 2
    assert _row(boards, ZVEREV)["probability"] == pytest.approx(MATCH_ZVEREV)
    assert _row(boards, SHELTON)["probability"] == pytest.approx(MATCH_SHELTON)


def test_next_up_and_the_board_serve_one_number_per_side():
    """The acceptance, asserted on the payload rather than on a rounding model.

    "Agree to the displayed digit" is how a reader states it, but the web board
    prints one decimal (`formatBoardProbability`) and the app prints a whole
    percent through its own helper — so equality of the SERVED values is both
    the stronger claim and the only one that does not depend on a client we are
    not running here.
    """
    boards = _boards()
    final = _final_row()
    apply_final_match_blend(boards, _slate(final), now=NOW)

    for side, board_key in zip(final["sides"], (ZVEREV, SHELTON)):
        board_row = _row(boards, board_key)
        assert board_row["display_name"] == side["display_name"]
        assert board_row["probability"] == side["probability"], (
            f"{side['display_name']}: card {side['probability']}, "
            f"board {board_row['probability']}"
        )


def test_renormalising_the_board_would_not_have_fixed_it():
    """Pins the finding, so nobody re-derives the cheaper wrong repair.

    Arithmetic on the MEASURED production board, not on the three-row fixture
    above: the overround lives in all 36 rows, of which this file carries the
    three that matter, so the sum has to be the one that was read off the wire
    at 11:14:15Z rather than one this fixture could produce.
    """
    measured_board_sum = 1.00825  # all 36 rows of `boards["Men's Singles"]`
    over_all_rows = BOARD_ZVEREV / measured_board_sum
    # And normalising the PAIR on its own — what a reader would assume "the
    # slate normalizes the head-to-head" means — lands somewhere else again.
    over_the_pair = BOARD_ZVEREV / (BOARD_ZVEREV + BOARD_SHELTON)

    for candidate, name in ((over_all_rows, "board"), (over_the_pair, "pair")):
        # Both land below 57.5%, so both still print 57 wherever the card prints
        # 58 — whatever rounding the client uses.
        assert candidate < 0.575, f"{name}: {candidate}"
        assert abs(candidate - MATCH_ZVEREV) > 0.001, f"{name}: {candidate}"


def test_the_untouched_rows_keep_their_own_outright_number():
    boards = _boards()
    apply_final_match_blend(boards, _slate(_final_row()), now=NOW)

    dust = _row(boards, DIMITROV)
    assert dust["probability"] == pytest.approx(0.001)
    assert dust["probability_basis"] == PROBABILITY_BASIS_OUTRIGHT
    assert dust["sources"], "a row the overlay did not touch keeps its provenance"


# ── THE TWO KEY SPACES ───────────────────────────────────────────────────────


def test_the_card_and_the_board_do_not_share_a_key_space():
    """The premise of the join, pinned so a fixture cannot quietly lose it.

    If these two ever became the same string, the tests below would pass
    against an id-only join and stop saying anything about production.
    """
    boards = _boards()
    final = _final_row()
    board_keys = {r["entity_key"] for r in boards[0]["rows"]}
    card_keys = {s["entity_key"] for s in final["sides"]}
    assert board_keys & card_keys == set()
    assert all(k.startswith("espn:athlete:") for k in card_keys)


def test_a_scoreboard_paired_final_still_reaches_the_board():
    """The men's final on 2026-09-13 was `pairing_source: "scoreboard"`, so its
    sides carry ESPN ids the register's board has never heard of. The name
    fallback is the only thing that makes this ship fire at all."""
    boards = _boards()
    changed = apply_final_match_blend(boards, _slate(_final_row()), now=NOW)
    assert changed == 2
    assert _row(boards, ZVEREV)["probability"] == pytest.approx(MATCH_ZVEREV)


def test_a_register_paired_final_resolves_on_the_id_without_the_name():
    """The other population: a register-matchup row carries the board's own key.

    The display names are deliberately wrong here, so this passes only through
    the id arm.
    """
    boards = _boards()
    changed = apply_final_match_blend(
        boards,
        _slate(
            _final_row(
                pairing_source="register",
                sides=[
                    _side(ZVEREV, "Not A Real Name", MATCH_ZVEREV),
                    _side(SHELTON, "Also Not Real", MATCH_SHELTON),
                ],
            )
        ),
        now=NOW,
    )
    assert changed == 2
    assert _row(boards, ZVEREV)["probability"] == pytest.approx(MATCH_ZVEREV)


def test_the_name_arm_folds_the_way_the_register_folds():
    """`normalize_name` drops case, punctuation, spaces and accents — ESPN
    writes "Felix Auger-Aliassime" where another source writes it without the
    hyphen, and the board must still be reachable."""
    boards = _boards()
    changed = apply_final_match_blend(
        boards,
        _slate(
            _final_row(
                sides=[
                    _side(ZVEREV_ESPN, "  alexander  zverev ", MATCH_ZVEREV),
                    _side(SHELTON_ESPN, "Ben-Shelton", MATCH_SHELTON),
                ]
            )
        ),
        now=NOW,
    )
    assert changed == 2


def test_a_name_carried_by_two_board_rows_promotes_nothing():
    """An ambiguous name resolves to neither row rather than to the first."""
    register = _mens_register()
    register["players"].append(
        _player(
            "alexander-zverev-2",
            "Alexander Zverev",
            "mens-singles",
            [_source("polymarket", 20, 204)],
        )
    )
    prices = _mens_prices()
    prices[("polymarket", 20, 204)] = {"probability": 0.002, "observed_at": POLY_AT}
    boards = _boards(register=register, prices=prices)
    control = copy.deepcopy(boards)

    assert apply_final_match_blend(boards, _slate(_final_row()), now=NOW) == 0
    assert boards == control


def test_two_sides_resolving_to_one_row_promotes_nothing():
    """Two different ids, one board row: a join that has proved itself wrong."""
    _unchanged(
        _slate(
            _final_row(
                sides=[
                    _side(ZVEREV_ESPN, "Alexander Zverev", MATCH_ZVEREV),
                    _side(SHELTON_ESPN, "Alexander Zverev", MATCH_SHELTON),
                ]
            )
        )
    )


# ── THE STAMP THE PROMOTED NUMBER TRAVELS WITH ───────────────────────────────


def test_a_promoted_row_carries_the_matchs_stamp_not_the_outrights():
    """The row's own second finding: 0.575 must not be dated 05:45Z."""
    boards = _boards()
    apply_final_match_blend(boards, _slate(_final_row()), now=NOW)

    row = _row(boards, ZVEREV)
    assert datetime.fromisoformat(row["observed_at"]) == MATCH_AT
    assert datetime.fromisoformat(row["freshest_observed_at"]) == MATCH_AT
    assert row["age_hours"] == pytest.approx(0.36, abs=0.01)
    assert row["price_state"] == "live"
    assert row["probability_is_live"] is True
    assert row["stale_sources"] == []
    assert row["mixed_freshness"] is False
    assert row["source_count"] == 3
    assert row["sources"] == []
    assert row["probability_basis"] == PROBABILITY_BASIS_FINAL


def test_the_board_banner_is_never_fresher_than_the_rows_under_it():
    """#5893's second finding, as a property rather than as one payload.

    The banner is a max over the rows' freshest readings, so promoting a row
    has to re-derive it — a banner still describing the numbers it replaced is
    the same class of lie one level up.
    """
    boards = _boards()
    apply_final_match_blend(boards, _slate(_final_row()), now=NOW)

    board = next(b for b in boards if b["draw"] == "mens-singles")
    freshest = max(
        datetime.fromisoformat(r["freshest_observed_at"])
        for r in board["rows"]
        if r.get("freshest_observed_at")
    )
    assert datetime.fromisoformat(board["newest_observed_at"]) == freshest
    assert datetime.fromisoformat(board["newest_observed_at"]) == MATCH_AT


def test_the_board_counts_are_re_derived_after_the_promotion():
    """A stale finalist becomes live, and `rows_not_live` has to notice."""
    prices = _mens_prices()
    # Push BOTH of Zverev's legs past the stale line so his row is not live.
    old = NOW - timedelta(hours=STALE_PRICE_HOURS + 5)
    prices[("kalshi", 10, 101)] = {"probability": 0.565, "observed_at": old}
    prices[("polymarket", 20, 201)] = {"probability": 0.5795, "observed_at": old}
    boards = _boards(prices=prices)
    before = next(b for b in boards if b["draw"] == "mens-singles")
    assert before["rows_not_live"] == 1

    apply_final_match_blend(boards, _slate(_final_row()), now=NOW)

    after = next(b for b in boards if b["draw"] == "mens-singles")
    assert after["rows_not_live"] == 0
    assert after["final_deferred_rows"] == 2


def test_the_zero_case_is_a_number_on_the_payload_not_an_absence():
    boards = _boards()
    assert all(b["final_deferred_rows"] == 0 for b in boards)
    apply_final_match_blend(boards, _slate(), now=NOW)
    assert all(b["final_deferred_rows"] == 0 for b in boards)


def test_the_ranking_follows_the_promoted_numbers():
    """A promotion that flips the order has to flip the ranks with it."""
    boards = _boards()
    assert _row(boards, ZVEREV)["rank"] == 1

    flipped = _final_row(
        sides=[
            _side(ZVEREV_ESPN, "Alexander Zverev", 0.40),
            _side(SHELTON_ESPN, "Ben Shelton", 0.60),
        ]
    )
    apply_final_match_blend(boards, _slate(flipped), now=NOW)

    assert _row(boards, SHELTON)["rank"] == 1
    assert _row(boards, ZVEREV)["rank"] == 2


# ── THE REFUSALS ─────────────────────────────────────────────────────────────
#
# Each one names a state in which promoting would be worse than disagreeing.
# They are asserted as "the boards are byte-identical to the un-overlaid build"
# rather than as "the probability did not change", so a refusal that silently
# rewrote a stamp or a rank would still fail.


def _unchanged(slate):
    boards = _boards()
    control = copy.deepcopy(boards)
    changed = apply_final_match_blend(boards, slate, now=NOW)
    assert changed == 0
    assert boards == control


def test_no_final_on_the_card_changes_nothing():
    _unchanged(_slate(_final_row(round="SF")))


def test_an_empty_or_absent_slate_changes_nothing():
    _unchanged(_slate())
    _unchanged({})
    _unchanged(None)


def test_an_unpriced_final_changes_nothing():
    _unchanged(_slate(_final_row(priced=False, price_state="unpriced")))


def test_a_row_that_says_live_but_not_priced_changes_nothing():
    """`priced` and `price_state` travel together on every row `build_slate`
    publishes, so the two clauses hide each other on a realistic fixture. This
    is the incoherent payload that separates them: a row claiming a live price
    while reporting it has none does not get to move a board."""
    _unchanged(_slate(_final_row(priced=False)))


def test_a_final_naming_one_player_twice_changes_nothing():
    """Two sides, one entity key: not a final, and not a pair to promote."""
    _unchanged(
        _slate(
            _final_row(
                sides=[
                    _side(ZVEREV_ESPN, "Alexander Zverev", 0.575),
                    _side(ZVEREV_ESPN, "Alexander Zverev", 0.425),
                ]
            )
        )
    )


def test_a_three_sided_final_changes_nothing():
    _unchanged(
        _slate(
            _final_row(
                sides=[
                    _side(ZVEREV_ESPN, "Alexander Zverev", 0.5),
                    _side(SHELTON_ESPN, "Ben Shelton", 0.3),
                    _side(DIMITROV_ESPN, "Grigor Dimitrov", 0.2),
                ]
            )
        )
    )


def test_a_stale_final_changes_nothing():
    """A stale match blend is not better than the outright it would replace."""
    _unchanged(_slate(_final_row(price_state="stale", probability_is_live=False)))


def test_a_final_the_board_would_itself_call_stale_changes_nothing():
    """The slate says live; the board's own threshold says otherwise.

    The two modules grade freshness against their own constants, so the match's
    verdict is necessary and the board's is sufficient. Without this the row
    would publish `price_state: "live"` at an age this module calls stale.
    """
    old = NOW - timedelta(hours=STALE_PRICE_HOURS + 1)
    _unchanged(
        _slate(
            _final_row(
                observed_at=old.isoformat(),
                freshest_observed_at=old.isoformat(),
            )
        )
    )


def test_a_final_with_no_timestamp_changes_nothing():
    _unchanged(_slate(_final_row(observed_at=None)))


def test_a_naive_timestamp_changes_nothing_and_does_not_raise():
    """A naive stamp among aware ones makes the banner's `max()` raise — a 500
    on the hub for a payload that merely mislabelled a timestamp."""
    _unchanged(
        _slate(_final_row(observed_at=MATCH_AT.replace(tzinfo=None).isoformat()))
    )


def test_a_one_sided_final_changes_nothing():
    _unchanged(_slate(_final_row(sides=[_side(ZVEREV_ESPN, "Alexander Zverev", 0.575)])))


def test_a_side_with_no_price_changes_nothing():
    _unchanged(
        _slate(
            _final_row(
                sides=[
                    _side(ZVEREV_ESPN, "Alexander Zverev", 0.575),
                    _side(SHELTON_ESPN, "Ben Shelton", None),
                ]
            )
        )
    )


def test_a_finalist_missing_from_the_board_moves_neither_row():
    """Half a final's blend beside an outright is the same disagreement, one row
    deeper — so if either side is absent, neither side moves."""
    _unchanged(
        _slate(
            _final_row(
                sides=[
                    _side(ZVEREV_ESPN, "Alexander Zverev", 0.575),
                    _side("espn:athlete:99999", "Nobody", 0.425),
                ]
            )
        )
    )


def test_two_finals_in_one_draw_are_refused_rather_than_tie_broken():
    other = _final_row(
        matchup_key="espn:999999",
        sides=[
            _side(ZVEREV_ESPN, "Alexander Zverev", 0.10),
            _side(SHELTON_ESPN, "Ben Shelton", 0.90),
        ],
    )
    _unchanged(_slate(_final_row(), other))


def test_a_settled_row_is_never_given_a_probability_back():
    """Settled means settled: a result may not be overwritten with a price."""
    register = _mens_register()
    for player in register["players"]:
        if player["entity_key"] == SHELTON:
            for block in player["sources"]:
                block["status"] = "settled"
                block["terminal_result"] = "eliminated"
    boards = _boards(register=register, prices=_mens_prices())
    assert _row(boards, SHELTON)["probability"] is None

    changed = apply_final_match_blend(boards, _slate(_final_row()), now=NOW)

    assert changed == 0
    assert _row(boards, SHELTON)["probability"] is None
    assert _row(boards, ZVEREV)["probability"] == pytest.approx(BOARD_ZVEREV)


def test_another_draws_final_does_not_touch_this_board():
    womens = _final_row(
        draw="womens-singles",
        sides=[
            _side(ZVEREV_ESPN, "Alexander Zverev", 0.10),
            _side(SHELTON_ESPN, "Ben Shelton", 0.90),
        ],
    )
    _unchanged(_slate(womens))


# ── THE TWO RECORDS OF "WHICH ROUND IS THE FINAL" ────────────────────────────


def test_the_final_round_key_is_the_registers_own_last_round():
    """Two constants answering one question, so the gap is asserted.

    `FINAL_ROUND` is matched against a slate row whose `round` comes from the
    register's vocabulary (`authority_round` maps ESPN's "Final" into it). If
    the register ever renamed or appended a round, a silent string compare here
    would stop matching and the hub would quietly go back to two numbers.
    """
    assert FINAL_ROUND in ROUNDS
    assert FINAL_ROUND == ROUNDS[-1]
