"""CAL-P1136 / #5401 — the three cells built on prices nobody quoted are HELD
BACK from the published score, and held back for the RIGHT STATED REASON.

klm = A (Alex, 2026-09-12): the accuracy page's launch bar is that
``kalshi/golf``, ``kalshi/entertainment`` and ``polymarket/golf`` are hidden
behind one honest line until #5401's price repair lands and they are recounted.

WHAT THIS FILE IS DEFENDING, and why each half needs its own assertion:

* **That they leave the score at all.** Trivially checkable, and the only half a
  careless change would keep.
* **That they leave BOTH halves of the needle.** ``cells_at_bar / cells_total``
  is a fraction; dropping a failing cell from the numerator alone would flatter
  the board, and dropping it from the denominator alone would punish it. The
  honest move is neither — it is absent from both.
* **That the reason is not "too small".** ``kalshi/golf`` carries 22,191
  outcomes in production. If it were filed under ``EXEMPT_BELOW_MIN_N`` the
  needle would read the same and mean something false. The two exemptions are
  asserted to be different verdicts on cells that differ only in size.
* **That the suppression is TARGETED.** A blanket "stop queueing exchange cells"
  would pass every assertion above. The control cell — over the bar, established,
  not in the set — must still be queued, and emptying the set must bring all
  three back. Without those two, this file is a guard that cannot fail.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils import calibration_scoring as scoring


# ---------------------------------------------------------------------------
# The fixture
# ---------------------------------------------------------------------------


def _bucket(source, category, n, winners, avg_prob=0.50, idx=5):
    return {
        "bucket_idx": idx,
        "source": source,
        "category": category,
        "price_moved": False,
        "n": n,
        "winners": winners,
        "avg_prob": avg_prob,
        "sum_prob": round(n * avg_prob, 4),
    }


#: One bin per cell, so a cell's ECE is just ``|winners/n - avg_prob| * 100``.
#:
#: The three held-back cells and the CONTROL are all built the same way — over
#: the bar, large enough to establish it — so the only thing that can separate
#: them in any assertion below is membership of ``HELD_BACK_CELLS``.
_BUCKETS = [
    # The three. Sized as in production: golf is large, the other two are not.
    _bucket("kalshi", "golf", 20_000, 12_000),           # 10.00 pp over
    _bucket("kalshi", "entertainment", 4_000, 2_400),    # 10.00 pp over
    _bucket("polymarket", "golf", 4_000, 2_400),         # 10.00 pp over
    # CONTROL — same shape, same class as polymarket/golf, NOT in the set.
    _bucket("polymarket", "cricket", 4_000, 2_400),      # 10.00 pp over
    # CONTROL — genuinely below the floor, so it must read EXEMPT_BELOW_MIN_N
    # and never the held-back verdict.
    _bucket("kalshi", "weather", 500, 350),              # 20.00 pp over, tiny
]


def _at() -> str:
    """A stamp always in the PAST (gotcha #44: offset first, then truncate)."""
    base = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )
    return base.isoformat()


def _payload(**over) -> dict:
    out = {
        "buckets": [dict(b) for b in _BUCKETS],
        "by_category": [],
        "by_source": [],
        "total_outcomes": 32_500,
        "total_markets": 8_125,
        "total_winners": 17_150,
        "min_category_outcomes": 1000,
        "mce_closing_line": 1.71,
        "generated_at": _at(),
        "population_version": "qtest",
    }
    out.update(over)
    return out


def _score(**over):
    """Scored on the row estimate: the ledger is not this file's subject."""
    return scoring.scorecard(_payload(**over), load_ledger=False)


def _by_cell(block_cells):
    return {c["cell"]: c for c in block_cells}


# ---------------------------------------------------------------------------


def test_the_set_is_exactly_the_three_cells_klm_named():
    """The membership is the ruling. It is not inferred from anything."""
    assert scoring.HELD_BACK_CELLS == frozenset(
        {"kalshi/golf", "kalshi/entertainment", "polymarket/golf"}
    )


def test_the_three_are_held_back_and_say_why():
    cells = _by_cell(scoring.score_cells(_payload(), None))
    for name in ("kalshi/golf", "kalshi/entertainment", "polymarket/golf"):
        cell = cells[name]
        assert cell["verdict"] == scoring.VERDICT_HELD_BACK, name
        # The reason travels on the row, so a consumer holding one cell can say
        # why it is ungraded without joining back to the set.
        assert cell["held_back_reason"] == scoring.HELD_BACK_REASON, name
        assert cell["held_back_issue"] == "#5401", name


def test_the_counterfactual_verdict_is_held_back_too():
    """``verdict_row_basis`` is what the needle's counterfactual sums.

    Leaving it graded would make ``cells_at_bar_row_basis`` count a cell the
    live needle does not, and the published delta between them would silently
    absorb the hold-back instead of reporting the sigma overlay.
    """
    cells = _by_cell(scoring.score_cells(_payload(), None))
    for name in ("kalshi/golf", "kalshi/entertainment", "polymarket/golf"):
        assert cells[name]["verdict_row_basis"] == scoring.VERDICT_HELD_BACK, name


def test_they_leave_both_halves_of_the_needle():
    """Absent from the denominator AND the numerator — not one or the other."""
    block = _score()
    graded = {c["cell"] for c in block["queued_cells"]}
    assert "kalshi/golf" not in graded
    assert "kalshi/entertainment" not in graded
    assert "polymarket/golf" not in graded

    # The denominator is the material count, and the three are not in it. Of
    # the five cells only the cricket control survives into it: three are held
    # back and weather is below the floor.
    assert block["cells_scored"] == 5
    assert block["cells_total"] == 1
    assert block["cells_held_back"] == 3
    assert block["held_back_outcomes"] == 20_000 + 4_000 + 4_000


def test_the_needle_arithmetic_still_reconciles():
    """at_bar + queued + unestablished == the denominator, with three removed."""
    block = _score()
    assert (
        block["cells_at_bar"] + block["cells_queued"] == block["cells_total"]
    ), block
    assert block["cells_at_bar"] >= 0


def test_held_back_is_not_the_same_admission_as_too_small():
    """A 20,000-row cell and a 500-row cell must not get the same verdict.

    This is the assertion that stops the tidy-looking shortcut of adding these
    cells to ``MIN_CELL_N``'s pile: the needle would read identically and the
    page would tell a reader the golf curve is thin when it is 20,000 outcomes
    of prices we should never have stored.
    """
    cells = _by_cell(scoring.score_cells(_payload(), None))
    assert cells["kalshi/golf"]["n"] == 20_000
    assert cells["kalshi/golf"]["n"] > scoring.MIN_CELL_N
    assert cells["kalshi/golf"]["verdict"] == scoring.VERDICT_HELD_BACK
    assert cells["kalshi/weather"]["verdict"] == scoring.VERDICT_EXEMPT
    assert scoring.VERDICT_HELD_BACK != scoring.VERDICT_EXEMPT


def test_the_control_cell_is_still_queued():
    """Non-vacuity, half one: the hold-back is targeted, not a blanket.

    ``polymarket/cricket`` is the same class, the same size and the same excess
    as ``polymarket/golf``. If a change suppressed cells by shape rather than by
    name, this fails.
    """
    block = _score()
    assert [c["cell"] for c in block["queued_cells"]] == ["polymarket/cricket"]


def test_emptying_the_set_returns_all_three_to_the_score(monkeypatch):
    """Non-vacuity, half two: the set is what removes them, nothing else.

    Without this, every assertion above would still pass if the cells were being
    dropped by an unrelated filter.
    """
    before = _score()
    monkeypatch.setattr(scoring, "HELD_BACK_CELLS", frozenset())
    after = _score()

    assert after["cells_total"] == before["cells_total"] + 3
    assert after["cells_held_back"] == 0
    assert after["held_back_cells"] == []
    queued = {c["cell"] for c in after["queued_cells"]}
    assert {"kalshi/golf", "kalshi/entertainment", "polymarket/golf"} <= queued


def test_the_payload_names_them_for_the_page():
    """The page's one honest line is rendered from THIS, not from a copy."""
    block = _score()
    named = {c["cell"] for c in block["held_back_cells"]}
    assert named == {"kalshi/golf", "kalshi/entertainment", "polymarket/golf"}
    # Largest first, so the line can lead with the cell that matters most.
    assert [c["n"] for c in block["held_back_cells"]] == sorted(
        (c["n"] for c in block["held_back_cells"]), reverse=True
    )
    for c in block["held_back_cells"]:
        assert c["ece"] is not None and c["n"] > 0
    assert block["held_back_reason"] == scoring.HELD_BACK_REASON
    assert block["held_back_issue"] == "#5401"


def test_the_field_is_present_when_nothing_is_held_back(monkeypatch):
    """An empty list, never a missing key (gotcha #53).

    "Nothing is held back" and "this payload predates the field" are different
    facts, and a reader keyed on absence cannot tell them apart.
    """
    monkeypatch.setattr(scoring, "HELD_BACK_CELLS", frozenset())
    block = _score()
    assert "held_back_cells" in block
    assert block["held_back_cells"] == []


def test_an_unscored_board_claims_nothing_about_what_is_held_back():
    """`None`, not `[]` — an unavailable block does not know."""
    block = scoring.unavailable("no_buckets")
    assert block["held_back_cells"] is None
    assert block["cells_held_back"] is None


def test_verdict_for_without_a_cell_name_is_unchanged():
    """Every caller that is not scoring a real cell keeps pre-#5401 behaviour."""
    assert scoring.verdict_for(5_000, 1.0, 3.0) == scoring.VERDICT_QUEUED
    assert scoring.verdict_for(10, 1.0, 3.0) == scoring.VERDICT_EXEMPT
    assert scoring.verdict_for(5_000, -1.0, 3.0) == scoring.VERDICT_PASS


def test_a_held_back_cell_is_held_back_at_any_size():
    """The name is checked BEFORE the floor, so size cannot reclassify it.

    Otherwise a held-back cell that happened to be small would report
    ``EXEMPT_BELOW_MIN_N`` and drop out of the page's honest line while still
    being ungraded — present in neither place a reader could find it.
    """
    assert (
        scoring.verdict_for(10, 1.0, 3.0, "kalshi/golf")
        == scoring.VERDICT_HELD_BACK
    )
    assert (
        scoring.verdict_for(10_000_000, -5.0, 3.0, "kalshi/golf")
        == scoring.VERDICT_HELD_BACK
    )


@pytest.mark.parametrize("name", sorted(scoring.HELD_BACK_CELLS))
def test_every_held_back_cell_is_spelled_the_way_a_cell_key_is(name):
    """``source/category`` — a typo here silently holds back nothing."""
    assert name.count("/") == 1
    source, category = name.split("/")
    assert source and category
    assert name == f"{source}/{category}"
