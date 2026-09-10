"""#4688 — Part A2's refill must be able to reach the rows Part A2's reset nulls.

Why this file exists
--------------------
``_compute_calibration_prices`` corrects a resolved non-event market's published
price from its opening-day stamp to its real pre-commence closing line. It does
it in two halves: a **reset** that nulls ``calibration_probability`` on rows it
can genuinely improve, and a **refill** that writes the closing line back. On
production those two halves disagreed, and the disagreement was a closed loop.

Measured on the 2026-09-10 20:10Z beat of the dedicated
``app.tasks.compute_calibration_prices`` task — ``terminal: "complete"``,
``stopped_at: None``, ``elapsed_s: 458.1`` of a 540s deadline, so **82 seconds of
budget went unspent and nothing here was starved**:

===========================  ======
``reset_a2``                  9,801
``with_market_commence``      3,126
``without_commence``         11,151
===========================  ======

The refill re-priced 3,126 of the 9,801 rows the reset had just nulled. The
other ~6,700 fell through to Part B, which prices from ``opening_captured_at``
— the opening-day price — so the row came back reading ``cal = opening``, the
next beat's reset nulled it again, and the reader was served the opening stamp
throughout. Roughly 6,700 rows a beat, indefinitely.

Two defects, and this file guards both.

**D2, the stuck head (the ship).** The refill selected the newest 20,000 NULL
rows by ``commence_time DESC`` with no cursor and broke the whole part on
``rowcount == 0``. Its UPDATE then discarded most of that window through its own
``COALESCE(...) IS NOT NULL`` guard, and the discarded rows — still NULL — were
re-selected identically on the next iteration. So one unfillable window stopped
the part permanently, and it was reached immediately: of the 1,035,350 NULL rows
in this scope, 969,290 carry no ``opening_probability`` and the large majority of
those have no pre-commence snapshot either, so they can never be filled and were
re-scanned forever while the fillable tail was never reached.

The fix is the idiom Part A-repair and Part B in the same function already use:
put the UPDATE's fillability test in the window so every selected row is a row
that gets written, break on ``scanned`` rather than on rows updated, and keyset
on ``fo.id``. The cursor is not what makes it correct — once the window and the
UPDATE agree, filled rows leave the set on their own — it is what makes it
affordable, so a run costs one pass over the id range instead of re-scanning a
million rows to find each 20,000.

**D1, the leak.** Part B is documented as the part for non-event markets
*without* a commence_time, but that half of the contract was never written into
its SQL: it tested ``e.commence_time`` — the **event's** boundary — and every
Part A2 market has ``event_id IS NULL``, so the first arm of the disjunct fired
and Part B admitted A2's whole population whatever the market's own
commence_time said. With D2 fixed A2 drains its own rows before Part B runs, so
D1 only bites if A2 is cut short by budget mid-sweep; it is the guard that stops
the loop re-forming in that case, not the ship.

Note gotcha #144 when reading a claim about either: the published curve price is
``COALESCE(calibration_probability, opening_probability)``, so a NULL and a
materialised opening are *the same number* to a reader. D1 alone moves nothing a
reader sees. D2 is what changes the published price.

SCOPE LIMIT — read before quoting a green run
---------------------------------------------
These are source-contract assertions on the two statements. They pin the shape
that makes the loop terminate correctly and the scope that keeps the two parts
disjoint; they do **not** execute SQL and they cannot prove the row-level
outcome. ``initdb`` does not run on the build host, and a new
``tests/integration/*_pg.py`` file needs both a ``COVERED`` entry and its own CI
step or it goes green unrun. The row-level proof is the production receipt:
``with_market_commence`` rising toward ``reset_a2`` and the reset-eligible
residue falling, taken on the first two beats after deploy.
"""

import re
from pathlib import Path

import pytest

SOURCE = (
    Path(__file__).resolve().parents[1] / "app" / "tasks" / "backfill_winners.py"
).read_text()


def _block(start_marker: str, end_marker: str) -> str:
    """The source between two unique markers, or fail naming which one moved.

    A slice taken with ``find`` returns -1 on a miss and silently hands back the
    tail of the file, which would make every assertion below pass against text
    it was never meant to read. Each marker is asserted unique first.
    """
    for marker in (start_marker, end_marker):
        found = SOURCE.count(marker)
        assert found == 1, (
            f"marker {marker!r} appears {found} times in backfill_winners.py, "
            "expected exactly once — this file's slices are no longer anchored"
        )
    start = SOURCE.index(start_marker)
    end = SOURCE.index(end_marker, start)
    assert end > start, f"{end_marker!r} precedes {start_marker!r}"
    return SOURCE[start:end]


def _squash(sql: str) -> str:
    """Collapse whitespace so assertions survive reindentation."""
    return re.sub(r"\s+", " ", sql)


@pytest.fixture(scope="module")
def part_a2() -> str:
    return _squash(
        _block("part_a2_total = 0", 'stats["with_market_commence"] = part_a2_total')
    )


@pytest.fixture(scope="module")
def part_b() -> str:
    return _squash(
        _block("part_b_cursor = 0", 'stats["without_commence"] = part_b_total')
    )


# --------------------------------------------------------------------------
# D2 — the stuck head
# --------------------------------------------------------------------------


def test_part_a2_window_carries_the_updates_own_fillability_test(part_a2):
    """The window may not hand the UPDATE rows the UPDATE will discard.

    This is the whole defect. `needs_cal` selected on "is NULL", the UPDATE
    wrote only where `COALESCE(closing, opening) IS NOT NULL`, and the gap
    between those two sets was 20,000 rows wide and permanent.
    """
    assert "fo.opening_probability IS NOT NULL OR EXISTS (" in part_a2, (
        "Part A2's window no longer requires the row to be fillable — the "
        "UPDATE's COALESCE guard will discard rows the window selected, they "
        "stay NULL, and the next iteration re-selects the same ones (#4688)"
    )


def test_part_a2_fillability_disjunct_is_exact_not_a_proxy(part_a2):
    """`opening IS NOT NULL` alone would silently drop ~57,000 rows.

    6.1% of the opening-less rows in this scope (measured 1-in-500, 114 of
    1,883) still have a pre-commence snapshot that can price them, and the
    refill fills those today. Narrowing the disjunct to the cheap column test
    would look like a harmless simplification and would drop every one of them.
    """
    assert "EXISTS ( SELECT 1 FROM futures_odds_snapshots fos" in part_a2, (
        "the EXISTS arm is gone: rows with no opening_probability but a valid "
        "pre-commence snapshot are now excluded from the refill (#4688)"
    )


def test_part_a2_window_and_lateral_select_the_same_snapshot_set(part_a2):
    """The EXISTS mirrors the LATERAL: if one moves the other must move with it.

    The window asks "can this row be priced?" and the UPDATE asks "what is the
    price?". They must be asking about the same snapshots — otherwise the
    window admits a row the LATERAL cannot price, the UPDATE discards it, and
    the stuck head is back in a subtler form.
    """
    bounds = "fos.captured_at < %s AND fos.probability > 0 AND fos.probability < 1"
    assert _squash(bounds % "fm.commence_time") in part_a2, (
        "the EXISTS arm's snapshot bounds no longer match the LATERAL's"
    )
    assert _squash(bounds % "nc.commence_time") in part_a2, (
        "the LATERAL's snapshot bounds no longer match the EXISTS arm's"
    )


def test_part_a2_keysets_on_outcome_id(part_a2):
    """Without the cursor each batch re-scans a 1M-row population from the top."""
    assert "AND fo.id > :cursor" in part_a2, "Part A2 lost its keyset bound"
    assert "ORDER BY fo.id LIMIT :batch" in part_a2, (
        "Part A2's window is no longer ordered by the column its cursor "
        "advances on — a cursor over an unstable order skips rows"
    )
    assert "ORDER BY fm.commence_time DESC" not in part_a2, (
        "Part A2 is back on the unstable commence_time window that could not "
        "advance past its own head (#4688)"
    )


def test_part_a2_terminates_on_scanned_not_on_rows_written(part_a2):
    """`updated == 0` is "this window was unfillable"; `scanned == 0` is "done".

    Breaking the part on rows-written is what turned one unfillable window into
    a permanent stop. The distinction only exists because the two counts can
    differ, so the guard has to be that the loop reads `scanned`.
    """
    assert "if scanned_a2 == 0: break" in part_a2, (
        "Part A2 no longer terminates on scanned — a window that writes "
        "nothing must advance the cursor, not stop the part (#4688)"
    )
    assert "result_a2.rowcount" not in part_a2, (
        "Part A2 is reading rowcount again; the CTE reports updated/scanned/"
        "max_id precisely so the loop can tell those two cases apart (#4688)"
    )


def test_part_a2_batches_are_bounded_like_its_siblings(part_a2):
    """A timed-out batch must end this part, not the parts after it."""
    assert "_run_bounded(session," in part_a2, (
        "Part A2 runs unbounded statements again — a statement timeout here "
        "propagates and takes Parts B, C and D down with it"
    )
    assert "if result_a2 is None: break" in part_a2, (
        "Part A2 does not handle _run_bounded's timeout return"
    )


# --------------------------------------------------------------------------
# D1 — Part B must not overwrite the population Part A2 owns
# --------------------------------------------------------------------------


def test_part_b_excludes_the_population_part_a2_owns(part_b):
    """Part B priced A2's rows from the opening-day stamp. That is the symptom."""
    assert (
        _squash("AND NOT ( fm.event_id IS NULL AND fm.commence_time IS NOT NULL )")
        in part_b
    ), (
        "Part B admits Part A2's population again: it tests the EVENT's "
        "commence_time, and every A2 market has event_id IS NULL, so without "
        "this exclusion Part B re-stamps the opening price on every row A2 "
        "nulled and could not refill (#4688)"
    )


def test_part_b_still_admits_event_linked_rows_with_no_event_commence_time(part_b):
    """The exclusion is scoped to A2's rows and must not shrink Part B further.

    Part B's reason to exist is the market with no usable boundary at all. An
    event-linked row whose event carries no commence_time is exactly that, and
    nothing else prices it.
    """
    assert "AND (fm.event_id IS NULL OR e.commence_time IS NULL)" in part_b, (
        "Part B's admission disjunct is gone — event-linked rows whose event "
        "has no commence_time now have no part that prices them"
    )


def test_part_b_prices_from_the_opening_stamp_which_is_why_scope_matters(part_b):
    """Pins the premise the exclusion rests on.

    If Part B ever stopped using `opening_captured_at`, the exclusion above
    would be guarding against something that no longer happens, and a reader of
    this file should find that out here rather than by re-deriving it.
    """
    assert "nc.opening_captured_at + INTERVAL '1 hour'" in part_b, (
        "Part B no longer prices from the opening stamp; re-derive whether the "
        "#4688 exclusion is still the right scope"
    )
