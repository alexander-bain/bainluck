"""CAL-P1021 — two rails both call a dimension ``fallback`` and they answer
DIFFERENT questions. This pins the difference so an operator cannot read one
rail's artifact as the other's.

THE TRAP, CONCRETELY. There are two independent ``DIMENSIONS`` registries:

* ``calibration_cell_exact.DIMENSIONS['fallback']`` (CAL-P995) keys price ORIGIN
  crossed with the producer's ``price_moved`` flag — FOUR labels,
  ``{has_closing,fallback_opening} x {moved,flat}``.
* ``fold_cell_ladder.DIMENSIONS['fallback']`` keys price origin alone — TWO
  labels, ``calib`` / ``opening_fallback``.

They are separate dicts, so nothing makes them agree, and their label
vocabularies are near-anagrams of each other: ``fallback_opening`` against
``opening_fallback``. An operator handed the runbook line ``--by fallback`` and
pointing it at the wrong script gets a plausible two-key answer to a question
that needs four.

🔴 AND THE WRONG ANSWER IS THE ONE WE ALREADY MADE ONCE. The four-key cross
exists precisely because a coarser split cannot separate what ``price_moved``
pools: its FALSE arm holds both "no closing price at all" and "closing price
equalled opening". CAL-P994 read ``--by price_moved`` on ``kalshi/entertainment``
(True 6,570 / False 2,352), concluded "does not split it", and could not have
concluded otherwise — the split it needed was INSIDE the FALSE arm. A two-key
``fallback`` run reproduces that dead end while looking like progress. As of
today production still lists ``kalshi/entertainment`` in
``/api/calibration``'s ``scorecard.sigma_overlay.remeasure_backlog``, so this is
a live footgun, not a hypothetical one.

WHY A TEST AND NOT A COMMENT. A comment cannot notice when someone edits one
registry toward the other. The invariant below can: the two label vocabularies
must stay DISJOINT, which is what makes any artifact self-identifying — read its
keys and you know which rail produced it.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import calibration_cell_exact as cce  # noqa: E402
import fold_cell_ladder as fcl  # noqa: E402

#: (outcome_id, market_id, calibration_probability, opening_probability).
#: Covers all three reachable states: a moved closing price, a closing price
#: equal to the opening, and no closing price at all. The middle one is the
#: population the coarse split cannot see.
SEED = [
    (1, 100, 0.80, 0.60),  # has closing, moved
    (2, 100, 0.55, 0.55),  # has closing, flat  <- hides in price_moved=False
    (3, 101, None, 0.95),  # no closing, flat   <- also price_moved=False
    (4, 101, None, 0.90),  # no closing, flat
    (5, 102, 0.40, 0.10),  # has closing, moved
]


def _price_moved(calib, opening):
    """The producer's own projection, restated so the seed cannot drift."""
    return int(calib is not None and calib != opening)


@pytest.fixture()
def db():
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE futures_outcomes ("
        "  id INTEGER PRIMARY KEY, market_id INTEGER,"
        "  calibration_probability REAL, opening_probability REAL)"
    )
    con.execute(
        "CREATE TABLE deduped ("
        "  outcome_id INTEGER, market_id INTEGER, price_moved INTEGER)"
    )
    for oid, mid, calib, opening in SEED:
        con.execute(
            "INSERT INTO futures_outcomes VALUES (?, ?, ?, ?)", (oid, mid, calib, opening)
        )
        con.execute(
            "INSERT INTO deduped VALUES (?, ?, ?)",
            (oid, mid, _price_moved(calib, opening)),
        )
    con.commit()
    yield con
    con.close()


def _labels(con, expr: str, join: str) -> set:
    rows = con.execute(
        f"SELECT DISTINCT {expr} AS k FROM deduped d {join}"
    ).fetchall()
    return {r[0] for r in rows}


#: The ladder rail's expression is written against an ``fo`` alias it joins for
#: itself in its own SQL; here we supply the equivalent join so the SAME seeded
#: rows go through both expressions and the comparison is like-for-like.
_LADDER_JOIN = "JOIN futures_outcomes fo ON fo.id = d.outcome_id"


def test_both_registries_really_do_define_fallback():
    """The premise. If either side ever drops the name the collision is gone and
    this file should be deleted rather than left asserting nothing."""
    assert "fallback" in cce.DIMENSIONS
    assert "fallback" in fcl.DIMENSIONS
    assert fcl.DIMENSIONS is not cce.DIMENSIONS, (
        "the registries have been merged — if that is deliberate, the two "
        "'fallback' entries now collide for real and one must be renamed"
    )


def test_the_cell_exact_rail_yields_the_four_key_cross(db):
    expr, join, _pre = cce.DIMENSIONS["fallback"]
    labels = _labels(db, expr, join)
    assert labels == {
        "has_closing|moved",
        "has_closing|flat",
        "fallback_opening|flat",
    }, labels
    # The fourth key is structurally impossible, which is the rail's own
    # self-check: price_moved requires calibration_probability IS NOT NULL.
    assert "fallback_opening|moved" not in labels


def test_the_ladder_rail_yields_only_two_keys(db):
    labels = _labels(db, fcl.DIMENSIONS["fallback"], _LADDER_JOIN)
    assert labels == {"calib", "opening_fallback"}, labels


def test_the_ladder_rail_cannot_answer_the_question_the_cross_exists_for(db):
    """🔴 THE POINT OF THIS FILE.

    Rows 2, 3 and 4 are all ``price_moved = False``. Row 2 has a real closing
    price that happened to equal its opening; rows 3 and 4 have no closing price
    at all. The cross separates them. The ladder's two-key split puts row 2 with
    the MOVED rows under ``calib`` and so never exposes the flat-but-priced
    population — the exact blind spot that made CAL-P994's ``--by price_moved``
    read come back empty.
    """
    expr, join, _pre = cce.DIMENSIONS["fallback"]
    cross = dict(
        db.execute(
            f"SELECT {expr} AS k, COUNT(*) FROM deduped d {join} GROUP BY 1"
        ).fetchall()
    )
    ladder = dict(
        db.execute(
            f"SELECT {fcl.DIMENSIONS['fallback']} AS k, COUNT(*)"
            f" FROM deduped d {_LADDER_JOIN} GROUP BY 1"
        ).fetchall()
    )

    # The cross isolates "priced but flat" as its own cell...
    assert cross["has_closing|flat"] == 1
    # ...while the ladder folds that row in with the moved ones.
    assert ladder["calib"] == 3
    assert "has_closing|flat" not in ladder


def test_the_two_label_vocabularies_stay_disjoint(db):
    """The durable invariant: an artifact's keys identify the rail that made it.

    If this ever goes red, someone has edited one registry toward the other and
    a saved fold can no longer be attributed by reading it. Rename, do not
    relax."""
    cross_expr, cross_join, _ = cce.DIMENSIONS["fallback"]
    cross = _labels(db, cross_expr, cross_join)
    ladder = _labels(db, fcl.DIMENSIONS["fallback"], _LADDER_JOIN)
    assert cross.isdisjoint(ladder), (
        f"label collision between the two 'fallback' rails: {cross & ladder}"
    )


def test_the_near_anagram_pair_is_pinned_apart():
    """``fallback_opening`` (cross) and ``opening_fallback`` (ladder) mean the
    same thing and differ only in word order. Pin both spellings so a well-meant
    tidy-up that unifies them turns this red instead of silently making two
    artifacts indistinguishable."""
    cross_expr = cce.DIMENSIONS["fallback"][0]
    ladder_expr = fcl.DIMENSIONS["fallback"]
    assert "fallback_opening" in cross_expr
    assert "opening_fallback" in ladder_expr
    assert "opening_fallback" not in cross_expr
    assert "fallback_opening" not in ladder_expr
