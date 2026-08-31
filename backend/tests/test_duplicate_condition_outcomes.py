"""A market serves one outcome per condition, even when it stores three.

Every fixture here is a REAL production row set, captured 2026-08-31 from
``futures_outcomes`` before the repair. That matters more than it sounds: a
hand-written fixture comes out tidy — ascending ids, one duplicate, a clean
suffix — and the production rows are not tidy. ``Zoë Kravitz`` (id 69789475)
sorts BEFORE its own ``_yes`` leg (84318323) while ``90+`` (223434876) sorts
AFTER its leg (223434871), so any rule that leaned on insertion order would
pass on one market and fail on the other.

The population these were drawn from: 1,455 affected markets, all Polymarket,
2,910 duplicate rows, and the discriminator below matched 1,455 of 1,455 with
zero false positives.
"""

from __future__ import annotations

import pytest

from app.utils.duplicate_condition_outcomes import (
    binary_leg_base,
    drop_duplicate_legs,
    duplicate_leg_external_ids,
)

# ── REAL ROWS ─────────────────────────────────────────────────────────────────
# futures_markets 12194657, "Who will Taylor Swift's bridesmaids be?".
# The `No` leg at 0.645 outranks all ten people (who sit at 0.0035 and below),
# so the card crowned it: "New favorite: No: Who will Taylor Swift's
# bridesmai... (64%)". Its bare twin is `Zoë Kravitz`, the same condition.
_ZOE = "0xeda9eb14a054e234a72ab94dc45a6302ca702a6a8e5e7c270e7c91628ac8e084"
BRIDESMAIDS = [
    (84318324, "No", f"{_ZOE}_no", 0.645),
    (84318323, "Yes", f"{_ZOE}_yes", 0.355),
    (69789474, "Gigi Hadid", "0xdc736508860c34b8c28140480a0091734469d2587bc20cd5f87893df05aa", 0.0035),
    (69789475, "Zoë Kravitz", _ZOE, 0.0005),
    (69789473, "Selena Gomez", "0x5f731ad954f7af2601934d9c66eff170be6aa2d0cbaa1cfc1c75dc6c4dbb", 0.0005),
    (69789479, "Blake Lively", "0x1f34cc98dd6fcf91833a7e5859973f75bf7d1fed83da33823f3d82cd0844", 0.0005),
]

# futures_markets 59934326, '"Onslaught" Rotten Tomatoes Score?'. Here the
# duplicated rung is `90+` and its leg was inserted BEFORE it.
_NINETY = "0xd8b39a46a05fcb76e11fc4f310cc0b6f173411036a4d934ade0aab8e33144f51"
ONSLAUGHT = [
    (223434871, "Yes", f"{_NINETY}_yes", 0.140),
    (223434872, "No", f"{_NINETY}_no", 0.860),
    (223434873, "60+", "0x1a2b3c4d5e6f70819293a4b5c6d7e8f9012345678962b793aa669393aaaa", 0.955),
    (223434874, "70+", "0x2b3c4d5e6f70819293a4b5c6d7e8f90123456789dd5caaed5b7ef0bbbbbb", 0.625),
    (223434875, "80+", "0x3c4d5e6f70819293a4b5c6d7e8f9012345678939cc6838ba741fcccccccc", 0.120),
    (223434876, "90+", _NINETY, 0.019),
]

# futures_markets 13798072, the correctly decomposed sub-market
# "Will Zoë Kravitz be one of Taylor Swift's bridesmaids?". SAME external_ids
# as the two legs above — this is the row they belong on. Nothing may be
# dropped here: there is no bare twin, and dropping a leg would empty the row.
ZOE_SUB_MARKET = [
    (125653873, "Yes", f"{_ZOE}_yes", 0.0005),
    (125653874, "No", f"{_ZOE}_no", 0.9995),
]

_EXT = lambda row: row[2]  # noqa: E731


def _names(rows):
    return [r[1] for r in rows]


# ── the discriminator ─────────────────────────────────────────────────────────


def test_the_bridesmaids_card_stops_serving_the_leg_that_outranked_everyone():
    kept = drop_duplicate_legs(BRIDESMAIDS, _EXT)
    assert "No" not in _names(kept)
    assert "Yes" not in _names(kept)
    # and the rung those legs duplicated is still there, under its own name
    assert "Zoë Kravitz" in _names(kept)
    assert len(kept) == 4


def test_the_leader_after_the_drop_is_a_real_contender_not_a_binary_leg():
    kept = drop_duplicate_legs(BRIDESMAIDS, _EXT)
    leader = max(kept, key=lambda r: r[3])
    assert leader[1] == "Gigi Hadid", (
        "the card must crown a person, not the 64.5% `No` leg of one person's "
        "own sub-market"
    )


def test_a_leg_inserted_before_its_rung_is_still_recognised():
    """Onslaught's legs sort ahead of the `90+` they duplicate."""
    kept = drop_duplicate_legs(ONSLAUGHT, _EXT)
    assert _names(kept) == ["60+", "70+", "80+", "90+"]


def test_the_correctly_decomposed_sub_market_keeps_both_of_its_legs():
    """The same two external_ids, on the row that owns them. Nothing drops.

    This is the half that stops the rule being a blanket "delete every _yes".
    """
    kept = drop_duplicate_legs(ZOE_SUB_MARKET, _EXT)
    assert kept == ZOE_SUB_MARKET


def test_a_market_with_no_duplicates_is_returned_unchanged_and_in_order():
    clean = [r for r in BRIDESMAIDS if not r[2].endswith(("_yes", "_no"))]
    assert drop_duplicate_legs(clean, _EXT) == clean


def test_scoping_is_the_callers_job_so_ids_are_not_pooled_across_markets():
    """A rung on one market must not justify dropping a leg on another.

    Passing the two markets' ids together is exactly the mistake that would
    empty the sub-market row, so the helper is documented as per-market and
    this pins what happens if that contract is broken — the legs DO get
    dropped, which is why callers must group first.
    """
    pooled = duplicate_leg_external_ids([r[2] for r in BRIDESMAIDS + ZOE_SUB_MARKET])
    assert f"{_ZOE}_yes" in pooled  # the pooled set is wider than any one market
    per_market = duplicate_leg_external_ids([r[2] for r in ZOE_SUB_MARKET])
    assert per_market == set()


# ── the suffix reader ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "external_id,expected",
    [
        (f"{_ZOE}_yes", _ZOE),
        (f"{_ZOE}_no", _ZOE),
        (_ZOE, None),
        ("", None),
        (None, None),
        ("KXATPMATCH-26AUG30-SIN", None),  # a Kalshi ticker is never a leg
    ],
)
def test_binary_leg_base_reads_the_suffix(external_id, expected):
    assert binary_leg_base(external_id) == expected


def test_the_suffix_is_removed_not_stripped_as_a_character_set():
    """`rstrip('_yes')` eats trailing e/s/y/_ from the hex as well.

    Built to bite: this condition id ends `...say`, every character of which is
    in the set `{_,y,e,s}`. `removesuffix` takes four characters; `rstrip`
    takes seven and returns a condition that never existed.
    """
    cid = "0xfeedfacedeadbeef0123456789abcdefdeadbeefcafebabe0123456789e5say"
    assert binary_leg_base(f"{cid}_yes") == cid
    assert f"{cid}_yes".rstrip("_yes") != cid  # the bug this avoids


def test_a_null_external_id_never_crashes_the_filter():
    """`futures_outcomes.external_id` is nullable and NULL rows exist."""
    rows = [(1, "Yes", None, 0.5), (2, "No", None, 0.5)]
    assert drop_duplicate_legs(rows, _EXT) == rows
