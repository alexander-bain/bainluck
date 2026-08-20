"""Provenance drift validator — shipping label/training join boundary.

The card Alex grades is derived from LIVE state (feed.py:6638
rank_score = base*(1-w) + i*w). At train time the sampler must see the
same features serve will see; otherwise training/serving skew is built in.
This validator is the production gate that the label/training join calls —
a test that lives only inside its own file guards nothing, so this
function must be imported by both the shipping join and its test.
"""

from __future__ import annotations


def is_within_drift(frozen: float, live: float, bound: float = 0.01) -> bool:
    """Return True if frozen and live feature values agree within bound.

    Used by the label/training join to prove training/serving parity.
    A drift >0.01 means the gold label was graded on a different
    objective than the one it will tune (audit finding 4, #1873).
    """
    return abs(frozen - live) <= bound


def validate_label_join_drift(
    frozen_rank: float,
    live_rank: float,
    frozen_i: float,
    live_i: float,
    bound: float = 0.01,
) -> bool:
    """Validate both rank_score and interestingness drift.

    Returns True only if both the blended rank and the per-component
    interestingness agree within bound — a pass on rank must not hide
    a component drift.
    """
    return is_within_drift(frozen_rank, live_rank, bound) and is_within_drift(
        frozen_i, live_i, bound
    )
