"""Current odds use the same admitted chance as the hero (#12824).

The first stored line is historical evidence, not a current quote. A missing
aggregate must stay missing: a raw snapshot can be old or below ruling 051's
three-book floor. The snapshot object still carries its spread, total, count
and capture time; those fields do not license a current win probability.
"""

from typing import Optional

from app.utils.aggregation import TIER_OPENING


def current_odds_probability(
    blend: Optional[float],
    blend_tier: Optional[str],
    snapshot_consensus: Optional[float],
    event_status: Optional[str],
) -> Optional[float]:
    """Return an admitted aggregate, preserving a real zero.

    The snapshot and status arguments remain part of the shared route contract;
    neither can supply a substitute for an absent or historical aggregate.
    """
    # #12824 / 225-A: a refused source cannot re-enter through the snapshot
    # object, whose rows may be months old or below the three-book floor.
    # Preserve the signature for both route call sites; only an admitted
    # aggregate can supply a current chance.
    return blend if blend_tier != TIER_OPENING else None
