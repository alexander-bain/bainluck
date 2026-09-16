"""A board stops printing one label twice with two different answers (#6508).

Every specimen below is a production row read on 2026-09-16 from
``futures_markets``/``futures_outcomes``, and every guard case is a board that
is REAL and must not move. The helper's own docstring carries the correspondence
argument and the two rival designs it refutes; this file asks only whether the
rule fires where it should and — mostly — whether it stays silent everywhere
else.

THE BALANCE OF THIS FILE IS DELIBERATE
======================================

Four tests assert the ship and nine assert a population it must NOT touch. That
ratio is the point: the danger in a dedup is never that it fails to fire, it is
that it deletes a true row. #6508's first two proposed designs both did exactly
that — dedup-by-name would have deleted one of two genuinely distinct *"Mehmet
Oz confirmed as …"* questions, and the phantom guard below is the only thing
standing between this rule and leaving a reader looking at a lone unbacked
**100%** on ``113545``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.utils.superseded_name_twins import (
    drop_superseded_name_twins,
    superseded_name_twins,
)

ACCESSORS = dict(
    name_of=lambda o: o.name,
    external_id_of=lambda o: o.external_id,
    is_winner_of=lambda o: o.is_winner,
    resolution_source_of=lambda o: o.resolution_source,
)


def _row(oid, name, external_id, prob, is_winner=None, resolution_source=None):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=external_id,
        current_probability=prob,
        is_winner=is_winner,
        resolution_source=resolution_source,
    )


def _drop(rows):
    return drop_superseded_name_twins(rows, **ACCESSORS)


def _names(rows):
    return [r.name for r in rows]


# ── The five production boards the rule is FOR ───────────────────────────────
#: ``(market id, label, live row, superseded row)``. The superseded row in every
#: case prices 0.000000 and carries `api_settlement` + `is_winner=False`; the
#: live one carries `resolution_source=None`. Venue-side, the pair is a prior
#: cycle: `end_date_iso` 2026-01-01 against 2027-01-01.
FIRING_BOARDS = [
    (113486, "December 31", "0x74778c32", 0.100, "0xb03860dd"),
    (112914, "December 31", "0xf691956d", 0.095, "0x69b00959"),
    (113039, "December 31", "0x12bd7c63", 0.155, "0xbc19cb5c"),
    (113040, "December 31", "0xa6aa5a20", 0.165, "0x377e97f2"),
    (112938, "James Bullard", "0x83a36918", 0.038, "0x582c62c3"),
    (112938, "Rick Rieder", "0xb9e50edb", 0.075, "0xbd603617"),
]


@pytest.mark.parametrize(
    "market_id,label,live_id,live_prob,dead_id",
    FIRING_BOARDS,
    ids=[f"{m}-{l}" for m, l, _, _, _ in FIRING_BOARDS],
)
def test_the_superseded_rung_is_not_served_6508(
    market_id, label, live_id, live_prob, dead_id
):
    """The ship, on each board that actually prints the contradiction."""
    rows = [
        _row(1, label, live_id, live_prob),
        _row(2, label, dead_id, 0.0, is_winner=False, resolution_source="api_settlement"),
        _row(3, "April 30", "0xaaaa", 0.02),
    ]
    kept = _drop(rows)
    assert [r.id for r in kept] == [1, 3]
    assert _names(kept).count(label) == 1


def test_the_survivor_keeps_its_own_price_and_id_6508():
    """Only the duplicate leaves. Nothing about the survivor is rewritten."""
    rows = [
        _row(1, "December 31", "0x74778c32", 0.100),
        _row(2, "December 31", "0xb03860dd", 0.0, is_winner=False, resolution_source="api_settlement"),
    ]
    (survivor,) = _drop(rows)
    assert survivor.id == 1
    assert survivor.external_id == "0x74778c32"
    assert survivor.current_probability == pytest.approx(0.100)


def test_one_board_can_have_two_superseded_labels_6508():
    """`112938` prints the contradiction twice — both must go, in one pass."""
    rows = [
        _row(1, "Kevin Warsh", "0x01", 0.41),
        _row(2, "Rick Rieder", "0xb9e50edb", 0.075),
        _row(3, "Rick Rieder", "0xbd603617", 0.0, is_winner=False, resolution_source="api_settlement"),
        _row(4, "James Bullard", "0x83a36918", 0.038),
        _row(5, "James Bullard", "0x582c62c3", 0.0, is_winner=False, resolution_source="api_settlement"),
    ]
    assert [r.id for r in _drop(rows)] == [1, 2, 4]


def test_order_is_preserved_6508():
    """Callers rank either side of this and must not be reshuffled."""
    rows = [
        _row(1, "Zulu", "0x01", 0.1),
        _row(2, "Alpha", "0x02", 0.2),
        _row(3, "Zulu", "0x03", 0.0, is_winner=False, resolution_source="api_settlement"),
        _row(4, "Mike", "0x04", 0.3),
    ]
    assert _names(_drop(rows)) == ["Zulu", "Alpha", "Mike"]


# ── Guard 1: every row settled ⇒ say nothing ─────────────────────────────────


def test_two_graded_rows_are_both_kept_6508():
    """`189` Heisman: `Josh Hoover` under two Kalshi tickers, both graded.

    Nothing here says which grade belongs to which question, so a guess would
    attach a real verdict to the wrong row. The duplicate survives on purpose.
    """
    rows = [
        _row(1, "Josh Hoover", "KXHEISMAN-27-JHOO", 0.041, is_winner=False, resolution_source="api_settlement"),
        _row(2, "Josh Hoover", "KXHEISMAN-27-JHOOV", 0.028, is_winner=False, resolution_source="api_settlement"),
    ]
    assert len(_drop(rows)) == 2


def test_a_graded_pair_with_differing_sources_is_kept_6508():
    """`109506` `Man I Need`: `ungradeable_result` beside `api_settlement`."""
    rows = [
        _row(1, "Man I Need", "KXTOPSONGSPOTIFYUSA-26-M", 0.009, is_winner=False, resolution_source="ungradeable_result"),
        _row(2, "Man I Need", "KXTOPSONGSPOTIFYUSA-26-O", 0.0, is_winner=False, resolution_source="api_settlement"),
    ]
    assert len(_drop(rows)) == 2


# ── Guard 2: the survivor must be id-anchored ────────────────────────────────


def test_a_blank_id_sibling_cannot_supersede_anything_6508():
    """`113545` / `114237`, and this is the guard that matters most.

    The unsettled row on those boards has `external_id = ''` — no venue leg
    behind it — while the GRADED row is the one that is real. Firing here would
    drop the backed row and leave the reader looking at a lone unbacked row
    reading 100%: strictly worse than the duplicate. Those two rows are #6524.
    """
    rows = [
        _row(1, "May 31", "", 1.0),
        _row(2, "May 31", "0xec843b00", 0.02, is_winner=False, resolution_source="api_settlement"),
    ]
    kept = _drop(rows)
    assert len(kept) == 2, "the graded, id-anchored row must survive a blank-id sibling"
    assert any(r.current_probability == 0.02 for r in kept)


def test_a_whitespace_id_is_not_an_anchor_either_6508():
    """`external_id` is NOT NULL in the schema, so blankness arrives as `''`."""
    rows = [
        _row(1, "May 31", "   ", 1.0),
        _row(2, "May 31", "0xec843b00", 0.02, is_winner=False, resolution_source="api_settlement"),
    ]
    assert len(_drop(rows)) == 2


def test_a_none_id_is_not_an_anchor_either_6508():
    rows = [
        _row(1, "May 31", None, 1.0),
        _row(2, "May 31", "0xec843b00", 0.02, is_winner=False, resolution_source="api_settlement"),
    ]
    assert len(_drop(rows)) == 2


# ── Guard 3: only a definite loss ────────────────────────────────────────────


def test_a_winner_is_never_dropped_6508():
    """Settled means settled. A won rung stays whatever else is true."""
    rows = [
        _row(1, "Mehmet Oz", "0xf5a3b705", 0.0),
        _row(2, "Mehmet Oz", "0x39e0367e", 1.0, is_winner=True, resolution_source="api_settlement"),
    ]
    kept = _drop(rows)
    assert len(kept) == 2
    assert any(r.is_winner for r in kept)


def test_an_ungraded_row_with_a_source_is_not_superseded_6508():
    """`is_winner is False`, never `not is_winner` — `None` means ungraded."""
    rows = [
        _row(1, "December 31", "0x01", 0.10),
        _row(2, "December 31", "0x02", 0.0, is_winner=None, resolution_source="api_settlement"),
    ]
    assert len(_drop(rows)) == 2


def test_a_zero_price_alone_is_not_a_reason_to_drop_6508():
    """A rung can be a genuine 0% long shot. Price is not the discriminator."""
    rows = [
        _row(1, "December 31", "0x01", 0.10),
        _row(2, "December 31", "0x02", 0.0),
    ]
    assert len(_drop(rows)) == 2


# ── Everything else the rule must leave alone ────────────────────────────────


def test_two_unsettled_rows_are_both_kept_6508():
    """`112900` RFK Jr., `13641466` UAE, `8414987` Person A."""
    rows = [
        _row(1, "Robert F. Kennedy Jr.", "0x0b17bd62", None),
        _row(2, "Robert F. Kennedy Jr.", "0xc510176c", 0.0035),
    ]
    assert len(_drop(rows)) == 2


def test_a_board_with_no_repeated_label_is_untouched_6508():
    """The overwhelming majority of boards. A settled loser keeps its row."""
    rows = [
        _row(1, "Kevin Warsh", "0x01", 0.41),
        _row(2, "Rick Rieder", "0x02", 0.075),
        _row(3, "Barron Trump", "0x03", 0.0, is_winner=False, resolution_source="api_settlement"),
    ]
    assert _drop(rows) is not rows
    assert [r.id for r in _drop(rows)] == [1, 2, 3]


def test_a_nameless_row_is_never_grouped_6508():
    """Two blank names are not 'the same label'."""
    rows = [
        _row(1, "", "0x01", 0.1),
        _row(2, "", "0x02", 0.0, is_winner=False, resolution_source="api_settlement"),
    ]
    assert len(_drop(rows)) == 2


def test_an_empty_board_is_fine_6508():
    assert _drop([]) == []
    assert superseded_name_twins([], **ACCESSORS) == []


def test_three_twins_lose_only_the_graded_ones_6508():
    """A group larger than two is still decided per row, not per group."""
    rows = [
        _row(1, "December 31", "0x01", 0.10),
        _row(2, "December 31", "0x02", 0.0, is_winner=False, resolution_source="api_settlement"),
        _row(3, "December 31", "0x03", 0.0, is_winner=False, resolution_source="api_settlement"),
    ]
    assert [r.id for r in _drop(rows)] == [1]


# ── The served payload, not just the helper ──────────────────────────────────


def test_the_detail_payload_serves_one_row_per_label_6508():
    """A pure function nothing calls is inert — assert the SERIALIZER.

    Built as the Zelenskyy board (`113486`), whose two `December 31` rows are
    the cleanest specimen: 10% above 0%, six rungs, nothing else repeated.
    """
    from app.routes.futures import _format_market_detail

    def outcome(oid, name, ext, prob, winner=None, source=None):
        return SimpleNamespace(
            id=oid, name=name, external_id=ext,
            current_probability=prob, current_american_odds=400,
            rank=1, rank_change_24h=None, probability_change_24h=None,
            opening_probability=None, opening_american_odds=None,
            is_winner=winner, resolution_source=source, last_updated=None,
        )

    board = SimpleNamespace(
        id=113486, external_id="113486", name="Will Zelenskyy talk to Putin by...?",
        description=None, sport=None, sport_name=None, category=None,
        llm_sport_category="geopolitics", status="open", source="polymarket",
        market_type="field", mutually_exclusive=True, commence_time=None,
        resolution_date=None, created_at=None, updated_at=None, group_id=None,
        canonical_market_key=None, hook_description=None, category_tags=None,
        image_url=None,
        outcomes=[
            outcome(1, "December 31", "0x74778c32", 0.100),
            outcome(2, "December 31", "0xb03860dd", 0.0, winner=False, source="api_settlement"),
            outcome(3, "January 31", "0x03", 0.02),
        ],
    )

    served = _format_market_detail(board)
    names = [o["name"] for o in served["outcomes"]]
    assert names.count("December 31") == 1, names
    assert "January 31" in names
    assert served["outcome_count"] == len(served["outcomes"]), (
        "the count a reader is told must match the rows a reader is shown"
    )
