"""Rank ties break score-DESC then id-ASC — never by the label (Queue 308 / Codex C216).

The defect these lock out: ranking bare ``(score, label)`` tuples makes Python
compare element two on a tie, placing label 1 ahead of label 0. Precision@k is
then inflated whenever tied scores straddle the cutoff, so a ranking "improvement"
can be manufactured with no fitting at all — the evaluator is reading the answer
key it is supposed to be scored against.

This matters more, not less, on a thin corpus: with a single positive in the set,
a label tiebreak hoists that one row to rank 1 and reports a confident number
about nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts.evals.calibrate_interestingness import precision_at, stable_item_id
from scripts.evaluate_discover_label_gold_set import rank_rows


# --------------------------------------------------------------------------
# The fitter's precision@k (backend/scripts/evals/calibrate_interestingness.py)
# --------------------------------------------------------------------------


def _tied_slate(n_rows: int = 40, n_positive: int = 10):
    """Every score identical; positives interleaved so a label tiebreak shows."""
    labels = [1 if i % (n_rows // n_positive) == 0 else 0 for i in range(n_rows)]
    values = [50.0] * n_rows
    item_ids = [f"m{i:03d}" for i in range(n_rows)]
    return labels, values, item_ids


def test_tied_slate_cannot_inflate_precision_at_20():
    """A fully tied slate must report exactly the base rate.

    Measured pre-fix on this fixture: **0.5 against a true base rate of 0.25** —
    double, because the label tiebreak swept all 10 positives into the top 20.
    Nothing about the scorer changed; the evaluator simply read the answer key.
    """
    labels, values, item_ids = _tied_slate(n_rows=40, n_positive=10)
    base_rate = sum(labels) / len(labels)
    assert base_rate == 0.25

    result = precision_at(labels, values, 20, item_ids)

    assert result == base_rate, (
        f"expected the base rate {base_rate} on a fully tied slate, got {result} — "
        "a value above base rate means the label is leaking into the sort"
    )


def test_precision_is_invariant_to_input_order():
    """Shuffling the rows must not move the metric or the top-20 membership."""
    labels, values, item_ids = _tied_slate(n_rows=40, n_positive=10)

    orders = [
        list(range(40)),
        list(reversed(range(40))),
        # labels-first: the adversarial order — every positive at the front
        sorted(range(40), key=lambda i: -labels[i]),
    ]

    results = set()
    for order in orders:
        results.add(
            precision_at(
                [labels[i] for i in order],
                [values[i] for i in order],
                20,
                [item_ids[i] for i in order],
            )
        )

    assert len(results) == 1, f"precision@20 moved with input order: {results}"


def test_tiebreak_is_id_ascending_and_label_blind():
    """On an exact score tie the lower id wins, whatever the labels say."""
    values = [50.0, 50.0]

    # id "a" is the negative, id "b" the positive. A label tiebreak puts b first;
    # an id tiebreak puts a first. Top-1 precision tells us which happened.
    assert precision_at([0, 1], values, 1, ["a", "b"]) == 0.0

    # Invert only the labels — ordering must not budge, so top-1 flips to 1.0.
    assert precision_at([1, 0], values, 1, ["a", "b"]) == 1.0


def test_untied_scores_still_rank_by_score():
    """The fix must not break the ordinary case: real score order still wins."""
    # Highest score is the single positive, but it sorts LAST by id.
    labels = [0, 0, 1]
    values = [1.0, 2.0, 99.0]
    item_ids = ["a", "b", "z"]

    assert precision_at(labels, values, 1, item_ids) == 1.0


def test_stable_item_id_prefers_real_identity_over_index():
    assert stable_item_id({"id": "futures:7"}, 3) == "futures:7"
    assert stable_item_id({"market_id": 42}, 3) == "42"
    assert stable_item_id({"judgment_id": 9}, 3) == "9"
    assert stable_item_id({}, 3) == "idx:3"


# --------------------------------------------------------------------------
# The gold-set ranker (backend/scripts/evaluate_discover_label_gold_set.py)
#
# P4 of Queue 308: this one was ALREADY clean — rank_rows keys on
# (rank, -score, str(id)) and no label participates. No logic changed; these
# lock the existing behaviour so it cannot regress into the same defect.
# --------------------------------------------------------------------------


def _gold_rows(labels: list[str]) -> list[dict[str, object]]:
    """Tied score, absent rank_seen — ordering must fall through to id."""
    return [
        {"id": f"futures:{i}", "score_at_review": 50.0, "label": label}
        for i, label in enumerate(labels)
    ]


def test_gold_set_rank_rows_tiebreaks_on_id_not_label():
    ranked = rank_rows(_gold_rows(["bad", "love", "bad"]))
    assert [row["id"] for row in ranked] == ["futures:0", "futures:1", "futures:2"]


def test_gold_set_rank_rows_is_label_blind():
    """Inverting every label must leave the order untouched."""
    order_a = [r["id"] for r in rank_rows(_gold_rows(["love", "bad", "love", "bad"]))]
    order_b = [r["id"] for r in rank_rows(_gold_rows(["bad", "love", "bad", "love"]))]
    assert order_a == order_b


def test_gold_set_rank_rows_still_honours_score_then_rank():
    rows = [
        {"id": "futures:a", "score_at_review": 10.0, "label": "love"},
        {"id": "futures:b", "score_at_review": 90.0, "label": "bad"},
    ]
    assert [r["id"] for r in rank_rows(rows)] == ["futures:b", "futures:a"]

    ranked = rank_rows(
        [
            {"id": "futures:a", "rank_seen": 2, "score_at_review": 90.0, "label": "bad"},
            {"id": "futures:b", "rank_seen": 1, "score_at_review": 10.0, "label": "love"},
        ]
    )
    assert [r["id"] for r in ranked] == ["futures:b", "futures:a"]
