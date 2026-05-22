"""Hook staleness detection for Discover feed cards.

A hook description becomes stale when:
1. The market leader has changed since the hook was generated
2. The leader's probability has moved more than STALE_PROBABILITY_DELTA
   (15 percentage points) since generation
3. The hook is older than STALE_HOOK_MAX_AGE_DAYS (7 days) without
   re-enrichment

Stale hooks are suppressed at serve time (replaced by deterministic
headlines from feed_reasons.py) and prioritized for async re-enrichment
by the enrich_market_hooks Celery task.
"""

from datetime import datetime, timedelta, timezone


# Probability delta threshold (as a fraction 0-1) above which a hook
# is considered stale.  15pp = 0.15.
STALE_PROBABILITY_DELTA = 0.15

# Maximum age in days before a hook is unconditionally stale.
STALE_HOOK_MAX_AGE_DAYS = 7

# Key inside market_metadata JSONB where we store the leader probability
# at hook generation time.
HOOK_PROB_METADATA_KEY = "hook_probability_at_generation"


def is_hook_stale(
    *,
    hook_description: str | None,
    hook_generated_at: datetime | None,
    hook_leader_at_generation: str | None,
    current_leader_name: str | None,
    current_leader_probability: float | None,
    market_metadata: dict | None,
    now: datetime | None = None,
    max_age_days: int = STALE_HOOK_MAX_AGE_DAYS,
    probability_delta: float = STALE_PROBABILITY_DELTA,
) -> bool:
    """Return True if the hook should be suppressed at serve time.

    This is a pure function with no DB or LLM calls — safe for use in
    the hot path of GET /api/feed.
    """
    # No hook to suppress
    if not hook_description:
        return False

    if now is None:
        now = datetime.now(timezone.utc)

    # 1. Age check: suppress hooks older than max_age_days
    if hook_generated_at:
        # Ensure timezone-aware comparison
        gen_at = hook_generated_at
        if gen_at.tzinfo is None:
            gen_at = gen_at.replace(tzinfo=timezone.utc)
        if gen_at < now - timedelta(days=max_age_days):
            return True
    else:
        # No generation timestamp — treat as stale (legacy row)
        return True

    # 2. Leader change: the frontrunner shifted since hook was written
    if (
        hook_leader_at_generation
        and current_leader_name
        and hook_leader_at_generation != current_leader_name
    ):
        return True

    # 3. Probability delta: leader probability moved significantly
    if current_leader_probability is not None and market_metadata:
        gen_prob = market_metadata.get(HOOK_PROB_METADATA_KEY)
        if gen_prob is not None:
            try:
                delta = abs(float(current_leader_probability) - float(gen_prob))
            except (TypeError, ValueError):
                delta = 0.0
            if delta >= probability_delta:
                return True

    return False


def get_hook_probability_at_generation(
    market_metadata: dict | None,
) -> float | None:
    """Read the probability snapshot stored at hook generation time."""
    if not isinstance(market_metadata, dict):
        return None
    value = market_metadata.get(HOOK_PROB_METADATA_KEY)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
