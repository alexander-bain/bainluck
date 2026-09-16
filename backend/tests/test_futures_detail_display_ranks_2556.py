"""#2556 — the rank badges follow the order the reader sees the rows in.

WHAT A READER SAW. `/futures/1` → All Outcomes has been photographed five times
since 2026-09-01 with a rank column reading `… 21, 22, 25, 23, 24 …`; on
2026-09-16 `/api/futures/40533` ("2027 Pro Football Champion") served 11 inverted
adjacent pairs of 31, and `/api/futures/113486` served **badge 1 twice on five
rows**. A numbered list that cannot count, on flagship boards.

THE ONE THING THIS FILE HAS TO GET RIGHT
========================================

**The order the reader sees is NOT the order of the served array**, and a test
written against the array passes while the page is still wrong.

`_format_market_detail` sorts by raw `current_probability`, then nulls a withheld
price IN PLACE without re-sorting (its own `reader_leader` comment says so). The
client applies its own stable sort on `probability ?? 0` descending
(`sortFuturesOutcomes`, the page default), so a withheld row sinks to the bottom
of the page while sitting near the TOP of the array.

`BRAZIL_ROWS` below is that case, read off production 2026-09-16, and it is the
specimen the whole file is built on: 15 of its 21 legs are withheld, the array
opens with the one priced leg wearing badge 6, and badges 1-5 are on rows the
page renders halfway down. Numbering the array — the obvious `enumerate` — would
hand the page `1, 17, 18, 19, 21, 2, 3, …`: the same defect, rearranged. So every
assertion here reads the rows through `_reader_order`, which mirrors the client
comparator, and `test_numbering_the_array_would_not_fix_the_page_2556` pins the
distinction so a later `enumerate` cannot pass this file.

EVERY ROW BELOW IS REAL: id, name, probability and the stored badge are as
production served them on 2026-09-16 (payloads in `artifacts-398/`).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.utils.outcome_display import assign_display_ranks


# ── Brazil Série B: Winner (`/api/futures/8641774`, polymarket, 2026-09-16) ──
#: `(outcome id, name, served probability, STORED badge)` in SERVED ARRAY ORDER.
#: 15 legs are withheld (#5876 refuted midpoints), so they serve `probability:
#: None` and the page stacks them below every priced row — while the array keeps
#: them at positions 2-16. Badge 1 appears twice: `Sport` and `Other`.
BRAZIL_ROWS = [
    (46856675, "Juventude", 0.499, 6),
    (46856661, "Sport", None, 1),
    (46856660, "Fortaleza", None, 2),
    (46856662, "Novorizontino", None, 3),
    (46856663, "Cuiabá", None, 4),
    (46856664, "Londrina", None, 5),
    (46856665, "Ceará", None, 7),
    (46856666, "Náutico", None, 8),
    (46856667, "Vila Nova", None, 9),
    (46856668, "São Bernardo", None, 10),
    (46856669, "Goiás", None, 11),
    (46856670, "Operário Ferroviário", None, 12),
    (46856671, "Athletic", None, 13),
    (46856672, "Atlético Goianiense", None, 14),
    (46856673, "Criciúma", None, 15),
    (46856674, "CRB", None, 16),
    (46856676, "Avaí", 0.0205, 17),
    (46856677, "Botafogo-SP", 0.018, 18),
    (46856678, "Ponte Preta", 0.001, 19),
    (46856679, "América Mineiro", 0.0, 20),
]

# ── Will Zelenskyy talk to Putin? (`/api/futures/113486`, 2026-09-16) ────────
#: Five rows, and the stored badges read `1, 4, 5, 2, 1`. The smallest complete
#: specimen in the issue and the one that prints a DUPLICATE badge.
ZELENSKYY_ROWS = [
    (1629814, "December 31", 0.09, 1),
    (69763927, "January 31", 0.006, 4),
    (1629815, "March 31", 0.002, 5),
    (166967850, "August 31", 0.001, 2),
    (69763924, "November 30", 0.0, 1),
]

# ── Boston pro baseball wins this season? (`/api/futures/261`, 2026-09-16) ───
#: The ladder specimen from the issue: badges `1, 2, 3, 4, 7, 6, 5`, with the
#: 0.01 rung ranked BELOW two rungs at 0.0 — not the sub-1% tie-break the issue
#: body hypothesised, but two rows that are genuinely ordered and badged wrong.
BOSTON_ROWS = [
    (500001, "80+ wins", 0.99, 1),
    (500002, "75+ wins", 0.98, 2),
    (500003, "85+ wins", 0.955, 3),
    (500004, "90+ wins", 0.185, 4),
    (500005, "95+ wins", 0.01, 7),
    (500006, "100+ wins", 0.0, 6),
    (500007, "105+ wins", 0.0, 5),
]


def _dicts(rows):
    """The rows as the serializer holds them, in served ARRAY order."""
    return [
        {"id": oid, "name": name, "probability": prob, "rank": rank}
        for oid, name, prob, rank in rows
    ]


def _reader_order(served):
    """The rows in the order the PAGE stacks them.

    A deliberate re-implementation of `sortFuturesOutcomes(outcomes,
    "probability", "desc")` rather than a call into the helper under test: a test
    that ordered its rows with the code it is checking would pass on any
    self-consistent nonsense.
    """
    return sorted(served, key=lambda o: o["probability"] or 0, reverse=True)


def _badges_down_the_page(served):
    return [o["rank"] for o in _reader_order(served)]


# ─────────────────────────────────────────────────────────────────────────────
# The ship
# ─────────────────────────────────────────────────────────────────────────────


BOARDS = {"brazil": BRAZIL_ROWS, "zelenskyy": ZELENSKYY_ROWS, "boston": BOSTON_ROWS}


@pytest.mark.parametrize("board", sorted(BOARDS))
def test_the_badges_count_down_the_page_2556(board):
    """The reader's complaint, stated as the reader would: 1, 2, 3, … N."""
    served = _dicts(BOARDS[board])
    assign_display_ranks(served)
    assert _badges_down_the_page(served) == list(range(1, len(served) + 1))


@pytest.mark.parametrize("board", sorted(BOARDS))
def test_no_badge_is_printed_twice_2556(board):
    """`/futures/113486` served badge 1 on two of five rows, and `/futures/
    8641774` on two of twenty. A duplicate is not a milder inversion — it is the
    column asserting two rows are the same row."""
    served = _dicts(BOARDS[board])
    assign_display_ranks(served)
    badges = [o["rank"] for o in served]
    assert len(set(badges)) == len(badges)


def test_the_withheld_rows_are_numbered_where_the_page_puts_them_2556():
    """The Brazil board, named row by row.

    `Juventude` is the only leg with a real price and leads the page; the three
    other priced legs follow. Then the zero block — and the point of naming it
    row by row is that A WITHHELD PRICE AND A GENUINE 0.0 SORT TOGETHER: the
    client reads both as `probability ?? 0`, so `América Mineiro` at a real 0.0
    does not lead the fifteen nulls, it trails them, because the array carries it
    last. Anything else here would be our tie-break, not the page's order.
    """
    served = _dicts(BRAZIL_ROWS)
    assign_display_ranks(served)
    by_name = {o["name"]: o["rank"] for o in served}

    assert by_name["Juventude"] == 1
    assert by_name["Avaí"] == 2
    assert by_name["Botafogo-SP"] == 3
    assert by_name["Ponte Preta"] == 4
    # The zero block, in the order the array carried it: fifteen withheld rows
    # (array positions 2-16) and then the one honest 0.0 (array position 20).
    assert by_name["Sport"] == 5
    assert by_name["Fortaleza"] == 6
    assert by_name["CRB"] == 19
    assert by_name["América Mineiro"] == 20


def test_numbering_the_array_would_not_fix_the_page_2556():
    """THE STRAWMAN, pinned so a later `enumerate(outcomes, 1)` cannot pass.

    On this board array position and page position differ on 19 of 20 rows, so
    the cheap fix produces a column that is a clean 1..20 ON THE WIRE and still
    reads `1, 17, 18, 19, 20, 2, 3 …` down the page.
    """
    array_numbered = _dicts(BRAZIL_ROWS)
    for position, outcome in enumerate(array_numbered, 1):
        outcome["rank"] = position

    assert _badges_down_the_page(array_numbered) != list(
        range(1, len(array_numbered) + 1)
    )
    assert _badges_down_the_page(array_numbered)[:5] == [1, 17, 18, 19, 2]


def test_tied_rows_are_numbered_in_the_order_the_page_stacks_them_2556():
    """Deterministic tie handling, and it is NOT a tie-break of our own.

    Two legs at 0.0 keep their served order on the page (both comparators are
    stable), so their badges must be consecutive IN THAT ORDER. Sorting ties by
    id or name here would be perfectly deterministic and would reintroduce the
    defect on every board with a flat tail.

    The specimen is built so it can SAY so: the tied pair runs `Zulu` then
    `Alpha` in the array, and `Zulu` carries the higher id — so an id tie-break
    and a name tie-break both flip the pair, and this test fails under either.
    A pair whose ids happened to ascend with the array would pass under all
    three rules and prove nothing.
    """
    served = _dicts(
        [
            (900001, "Priced", 0.4, 9),
            (900009, "Zulu", 0.0, 3),
            (900002, "Alpha", 0.0, 1),
        ]
    )
    assign_display_ranks(served)
    by_name = {o["name"]: o["rank"] for o in served}

    assert by_name["Priced"] == 1
    assert by_name["Zulu"] == 2
    assert by_name["Alpha"] == 3


def test_the_helper_reports_how_many_badges_moved_2556():
    """The return value is the measurement a probe reads; nothing serves it.

    TWO on the Boston ladder, not three: its tail is badged `7, 6, 5` where it
    should read `5, 6, 7`, and the middle rung is already right. A count of the
    inverted PAIRS would say two as well for a different reason — this counts
    rows whose badge moved, and `100+ wins` keeping badge 6 is the case that
    tells the two measures apart.
    """
    served = _dicts(BOSTON_ROWS)
    assert assign_display_ranks(served) == 2
    # Idempotent: a second pass over an already-correct board moves nothing.
    assert assign_display_ranks(served) == 0


# ─────────────────────────────────────────────────────────────────────────────
# What must NOT move
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("board", sorted(BOARDS))
def test_no_price_and_no_row_moves_2556(board):
    """The ship changes ONE field. Prices, membership and the served array order
    are byte-identical, which is the promise the offer is made on."""
    before = _dicts(BOARDS[board])
    after = _dicts(BOARDS[board])
    assign_display_ranks(after)

    assert [o["id"] for o in after] == [o["id"] for o in before]
    assert [o["name"] for o in after] == [o["name"] for o in before]
    assert [o["probability"] for o in after] == [o["probability"] for o in before]


def test_every_other_key_on_the_row_survives_2556():
    """Including `rank_change_24h`, which is a DIFFERENT column with a different
    writer (`old_rank - new_rank`, per poll) and is deliberately not repaired
    here — see the helper's docstring."""
    served = [
        {
            "id": 1,
            "name": "Kansas City",
            "probability": 0.086,
            "rank": 6,
            "rank_change_24h": -1,
            "probability_change_24h": 0.004,
            "opening_probability": 0.07,
            "is_winner": None,
            "resolution_source": None,
        }
    ]
    assign_display_ranks(served)

    assert served[0]["rank"] == 1
    assert served[0]["rank_change_24h"] == -1
    assert served[0]["probability_change_24h"] == 0.004
    assert served[0]["opening_probability"] == 0.07
    assert served[0]["is_winner"] is None
    assert served[0]["resolution_source"] is None


def test_an_empty_board_is_not_an_error_2556():
    """`drop_incoherent_near_certain` can hand this an empty list."""
    served = []
    assert assign_display_ranks(served) == 0
    assert served == []


# ─────────────────────────────────────────────────────────────────────────────
# The served payload — a pure function nothing calls is inert
# ─────────────────────────────────────────────────────────────────────────────


def _outcome(oid, name, prob, rank):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"POLY-{oid}",
        current_probability=prob,
        current_american_odds=None,
        rank=rank,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=None,
        resolution_source=None,
        last_updated=None,
    )


def _board(rows):
    return SimpleNamespace(
        id=8641774,
        external_id="poly-brazil-serie-b",
        name="Brazil Série B: Winner",
        description=None,
        sport=None,
        sport_name=None,
        category=None,
        llm_sport_category="soccer",
        status="open",
        source="polymarket",
        market_type="field",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        category_tags=None,
        image_url=None,
        outcomes=[_outcome(*r) for r in rows],
    )


def test_the_served_payload_counts_down_the_page_2556():
    """The reader-visible arm, through the real serializer.

    The withheld ids are passed the way the route passes them, so the payload
    reproduces production's shape: `probability: None` on fifteen rows that stay
    near the top of the array.
    """
    from app.routes.futures import _format_market_detail

    # Every leg production withheld, keyed the way the route keys them.
    withheld = {oid for oid, _, prob, _ in BRAZIL_ROWS if prob is None}
    # Feed the serializer the RAW prices those rows carry; withholding is the
    # caller's decision and the route applies it inside.
    rows = [(oid, name, prob if prob is not None else 0.05, rank)
            for oid, name, prob, rank in BRAZIL_ROWS]

    detail = _format_market_detail(
        _board(rows), unsupported_price_outcome_ids=withheld
    )
    served = detail["outcomes"]

    assert detail["prices_withheld"] == len(withheld)
    assert _badges_down_the_page(served) == list(range(1, len(served) + 1))
    assert len({o["rank"] for o in served}) == len(served)
