"""D12 (#1978, CAL-P150) — the ruled (source, category) exclusion tuple.

WHAT WAS RULED. Alex, 2026-08-30 (RULINGS-BATCH, D12): *"'CRYPTO' CELL: delete
via the approved exclusion list; the two OUR-bugs it was hiding stay filed."*
The design is ``artifacts/cal-p121/RULE-DESIGN-kalshi-crypto.md`` §4 (RULE C):
the ruled non-exclusive-bundle exclusion gains one ``(kalshi, crypto)`` tuple.

WHAT IT DOES. ``kalshi/crypto`` is 4,566 published rows at ECE 7.61 pp against a
3.0 bar — rank 6, 20,999 excess-outcomes — and 99.9% of it is the non-exclusive
bundle shape (>=3 outcomes resolving with >=2 winners) the predicate already
names. 625 markets produce 4,566 rows, so one gold print is counted 7.31 times,
and a ladder's rungs are near-deterministically related. Both arms of the ruled
gate condemn the same 4,563 rows. So this does not fix rank 6 — it deletes it,
leaving 3 rows, and that is the ruled outcome rather than a side effect.

🔴 WHAT IT DOES NOT DO, AND WHAT THIS FILE REFUSES TO LET ANYONE FORGET. The
cell is 99.5% METALS — gold, silver, palladium, copper, lithium, nickel — and
exactly one row of it is cryptocurrency. The page says we made 4,565 forecasts
about crypto; we made ~625 about the price of metal and one about Hyperliquid.
Deleting the cell fixes the first half of that sentence. The label is a WRITER
defect and it stays filed (RULE-DESIGN §5).

🔴 AND THE ADMIN BUTTON IS NOT THE FIX. ``_cleanup_crypto_impl`` deletes markets,
outcomes and snapshots ``WHERE llm_sport_category = 'crypto'``. Its predicate is
exactly the label that is wrong; pressing it would permanently destroy 3,922
legitimate commodities markets and their price history.
``test_the_exclusion_is_read_side_and_names_the_deletion_hazard`` is here so
that fact is carried by the suite and not only by a document.
"""

from __future__ import annotations

import inspect

import pytest

from app.tasks import precompute_calibration as pc


# ---------------------------------------------------------------------------
# 1. The tuple, and its scope.
# ---------------------------------------------------------------------------

def test_the_ruled_cell_is_present_and_is_the_only_one():
    """Pinned as an exact set, not a membership check.

    A membership assertion would stay green while a later queue quietly added a
    third cell. Every entry here deletes a cell from the published board, so the
    list is a ledger of rulings and its length is part of the claim.
    """
    assert pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS == (("kalshi", "crypto"),)


def test_the_tuple_is_scoped_by_source_as_well_as_category():
    """The scoping that keeps this out of an UNMEASURED cell.

    A bare category entry would also act on `polymarket/crypto`, and CAL-P112
    item 3 is the standing warning: RULE T's category-only widening moved
    `polymarket/tech` 8.04 -> 12.62 — WORSE — and that cell is still unmeasured.
    A rule may not reach a cell nobody has folded.
    """
    for entry in pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS:
        assert isinstance(entry, tuple) and len(entry) == 2, (
            f"{entry!r} is not a (source, category) pair — a bare category "
            "string here silently widens the rule across every source"
        )
        assert all(isinstance(part, str) and part for part in entry)


def test_esports_is_not_in_the_tuple_list_and_still_applies_to_every_source():
    """The pre-existing rule is untouched, and it is a DIFFERENT shape of rule.

    Esports is excluded by category on any source (its +9.2 pp defect was
    measured that way, OPS-557). Folding it into the pair list would silently
    narrow it to whichever sources someone remembered.
    """
    assert pc.ESPORTS_MULTI_BUNDLE_CATEGORY == "esports"
    assert not any(
        cat == "esports" for _src, cat in pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS
    )
    for source in ("polymarket", "kalshi", "odds_api_bookmaker"):
        assert pc.market_is_esports_multi_bundle("esports", 3, 2, source=source)


# ---------------------------------------------------------------------------
# 2. The SQL and the Python mirror must say the same thing.
# ---------------------------------------------------------------------------

def test_the_emitted_sql_carries_the_pair_predicate():
    sql = pc._calibration_population_ctes()
    body = sql.split("esports_multi_bundles AS (", 1)[1].split("\n            ),", 1)[0]

    assert "(mi.source, mrs.category)" in body, (
        "the exclusion is no longer scoped by source — it can now reach cells "
        "that were never folded"
    )
    assert "('kalshi', 'crypto')" in body
    assert f"mrs.category = '{pc.ESPORTS_MULTI_BUNDLE_CATEGORY}'" in body, (
        "the esports arm is gone; that rule is measured and separate"
    )
    # The structural test itself must still be the gate. Without these two the
    # tuple would delete the whole cell rather than the bundle-shaped part of
    # it, which is a different (and unruled) rule that happens to produce a
    # similar number today.
    assert "mrs.n_outcomes >= 3" in body and "mrs.win_count >= 2" in body


def test_the_pair_renderer_cannot_collapse_into_an_or():
    """`(a, b) IN ((x, y))`, not `a = x OR b = y`.

    This is the bug the row-value form exists to make unwriteable: one missing
    bracket pair turns "kalshi AND crypto" into "kalshi OR crypto" and the
    predicate swallows every Kalshi cell on the board. Tested on a two-element
    input so the separator between pairs is exercised too — a renderer that is
    correct for one pair and wrong for two would pass a single-entry check.
    """
    rendered = pc._sql_pair_tuple((("b", "two"), ("a", "one")))
    assert rendered == "(('a', 'one'), ('b', 'two'))"


def test_the_pair_renderer_is_sorted_and_quote_safe():
    """Sorted for a stable plan cache key; quotes doubled so a value cannot
    break out of its literal. These are module constants, never user input, so
    the quote handling is defence in depth rather than a live injection path —
    which is exactly why it needs a test: nothing else would ever exercise it.
    """
    assert pc._sql_pair_tuple((("z", "z"), ("a", "a"))).startswith("(('a', 'a')")
    # A single quote in a value renders as two, inside the surrounding pair of
    # quotes: 'x' -> ''''  is  quote, quote, quote, quote.
    assert pc._sql_pair_tuple((("'", "x"),)) == "(('''', 'x'))"


def test_the_mirror_and_the_cte_agree_on_the_ruled_cells():
    """The Python predicate is documented as "mirroring the CTE". Hold it to it.

    Read out of the constant rather than restated: a test that hard-coded
    ("kalshi", "crypto") would keep passing after someone changed the constant
    and forgot the mirror, which is the exact failure mode D5's misdescribing
    comment demonstrated for months.
    """
    for source, category in pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS:
        assert pc.market_is_esports_multi_bundle(
            category, 3, 2, source=source
        ) is True
        # The structural test still gates it: a ruled cell's single-winner
        # partitions are NOT bundles and must survive.
        assert pc.market_is_esports_multi_bundle(
            category, 3, 1, source=source
        ) is False
        assert pc.market_is_esports_multi_bundle(
            category, 2, 2, source=source
        ) is False
        # And another source's same-named cell is untouched.
        assert pc.market_is_esports_multi_bundle(
            category, 3, 2, source="polymarket"
        ) is False


def test_an_unspecified_source_cannot_trip_a_pair_rule():
    """`source=None` means "the caller did not say", and must not match.

    Four call sites predate this parameter. A default that guessed a source
    would make one of them start deleting rows on a rule it was never updated
    for — silently, because the counts would still look self-consistent.
    """
    for _source, category in pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS:
        assert pc.market_is_esports_multi_bundle(category, 3, 2) is False


# ---------------------------------------------------------------------------
# 3. What the page says, and the hazard the page must never invite.
# ---------------------------------------------------------------------------

def test_the_payload_discloses_which_cells_and_derives_it_from_the_constant():
    """`applies_to` was the literal "esports" and would have gone stale silently.

    Derived rather than hand-listed for the reason D5 exists: two hand-maintained
    copies of one fact is how a comment comes to describe a join it stopped
    describing.
    """
    src = inspect.getsource(pc.compute_calibration_payload)
    block = src.split('"esports_multi_bundle_filter"', 1)[1].split("},", 1)[0]

    assert '"excluded_cells"' in block
    assert "NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS" in block
    assert '"applies_to": "esports"' not in block, (
        "applies_to is hard-coded to esports again while the filter deletes "
        "other cells — the page is describing a rule that is not in force"
    )


def test_the_published_rule_text_admits_it_is_no_longer_esports_only():
    text = pc.ESPORTS_MULTI_BUNDLE_RULE_TEXT
    assert "excluded_cells" in text
    assert "esports" in text
    # It must NOT name the cell: the list is derived, the prose is not, and a
    # prose copy of a derived list is a second source of truth waiting to drift.
    assert "crypto" not in text.lower()


def test_the_exclusion_is_read_side_and_names_the_deletion_hazard():
    """Two things at once, because they are the same mistake.

    (a) gotcha #21: the exclusion drops rows from the curve, it never re-grades
        or deletes anything. The ladder grading is CORRECT.
    (b) the live admin button `_cleanup_crypto_impl` deletes by
        `llm_sport_category = 'crypto'` — the very label that is wrong here —
        and would destroy 3,922 legitimate commodities markets. Nobody may reach
        for it as a way to "clean up rank 6". That warning lives beside the
        constant, and this test is what stops it being tidied away.
    """
    source = inspect.getsource(pc)
    decl = source.split("NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS = (", 1)[0]
    preamble = decl.rsplit("ESPORTS_MULTI_BUNDLE_CATEGORY", 1)[-1]

    assert "_cleanup_crypto_impl" in preamble, (
        "the deletion hazard is no longer documented beside the tuple. It is "
        "the one place a reader of this rule will be standing when they think "
        "of pressing that button."
    )
    assert "metals" in preamble.lower() or "metal" in preamble.lower()


@pytest.mark.parametrize("n_outcomes,n_winners", [(3, 2), (40, 39), (5, 5)])
def test_the_bundle_shape_is_what_is_excluded_not_the_category(
    n_outcomes, n_winners
):
    assert pc.market_is_esports_multi_bundle(
        "crypto", n_outcomes, n_winners, source="kalshi"
    ) is True


@pytest.mark.parametrize("n_outcomes,n_winners", [(3, 1), (2, 2), (1, 1), (10, 0)])
def test_a_ruled_cells_non_bundle_markets_still_publish(n_outcomes, n_winners):
    """The 3 rows that survive are the point of the structural gate.

    RULE C removes 4,563 of 4,566 rows. It must remove them for their SHAPE, not
    for their label — otherwise the rule is "delete this category", which is a
    different ruling with different evidence.
    """
    assert pc.market_is_esports_multi_bundle(
        "crypto", n_outcomes, n_winners, source="kalshi"
    ) is False
