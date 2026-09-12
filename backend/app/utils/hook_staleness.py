"""Hook staleness detection for Discover feed cards.

A hook description becomes stale when:
0. It was written under a RETIRED hook policy (see below, #5461)
1. The market leader has changed since the hook was generated
2. The leader's probability has moved more than STALE_PROBABILITY_DELTA
   (15 percentage points) since generation
3. The hook is older than STALE_HOOK_MAX_AGE_DAYS (7 days) without
   re-enrichment

Stale hooks are suppressed at serve time (replaced by deterministic
headlines from feed_reasons.py) and prioritized for async re-enrichment
by the enrich_market_hooks Celery task.

WHY THERE IS A POLICY VERSION AT ALL (#5461, CERT-2697's required repair).

Rule 3 is an AGE gate, and an age gate answers "has the world moved on?". It
cannot answer "was this sentence allowed to be written?". #5461 retired the
prompt that invented content — it asked the model for "ONE specific
development" while giving it only a settlement date, so the model supplied the
development itself, and cards carried lines like *"Ella Langley's 'Choosin'
Texas' has surged to the top of the Billboard Hot 100"* that nothing in our
data supports.

Stopping the WRITER does not retire what is already WRITTEN. At the moment the
gate shipped, all 1,076 served hooks had been written by the retired prompt,
and every one of them would have stayed on a card for up to seven more days
while rule 3 counted down — the fix visible to nobody until the following week.
Worse, the same gate stops the re-enrichment that would have replaced them, so
for markets with no citable evidence the countdown was the ONLY exit.

So the version is checked FIRST and an ABSENT version is stale. Absent is the
overwhelmingly common case on the day this ships (no row has ever carried the
key), and reading it as "fine" would be reading the entire defect as fine.
Fail-closed costs a deterministic headline; fail-open ships an invented fact.
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

# Key inside market_metadata JSONB recording which hook POLICY wrote the
# stored sentence. Metadata rather than a column for the same reason
# HOOK_PROB_METADATA_KEY is: no schema migration, and the writer is already
# rewriting this dict on every hook.
HOOK_POLICY_METADATA_KEY = "hook_policy_version"

#: The policy a hook must have been written under to be served.
#:
#: 1 — implicit, never written. Every hook that existed before #5461: the
#:     prompt that listed authored examples detached from evidence and demanded
#:     "ONE specific development", so a market whose only evidence was a
#:     settlement date got an invented one.
#: 2 — #5461. Bounded cited evidence is fed to the model, the task refuses to
#:     call it at all when no dated fact is held, and the prompt states the
#:     shape instead of quoting a newsletter.
#:
#: 🔴 BUMPING THIS RETIRES EVERY STORED HOOK AT THE NEXT SERVE. That is the
#: point, and it is why it is a deliberate integer and not a hash of the prompt
#: text: a hash would roll on a typo fix and empty the feed's prose for a
#: whitespace change. Bump it when the RULES governing what a hook may say
#: change, never when the wording of the prompt does.
CURRENT_HOOK_POLICY_VERSION = 2


def hook_policy_version(market_metadata: dict | None) -> int:
    """Which hook policy wrote the stored sentence.

    ``1`` for anything that does not say — an absent key, a non-dict metadata
    blob (the #219E array-shaped rows are real and are why this does not assume
    a dict), or a value that is not an integer. All three mean "written before
    this was recorded", which is policy 1 by definition.

    Deliberately NOT ``0`` or ``None``: those would invite a caller to write
    ``if version:`` and treat the legacy case as falsy-but-fine. An unlabelled
    hook is not unknown, it is old.
    """
    if not isinstance(market_metadata, dict):
        return 1
    raw = market_metadata.get(HOOK_POLICY_METADATA_KEY)
    if isinstance(raw, bool) or not isinstance(raw, int):
        # `bool` is an `int` in Python and `True` would read as version 1 by
        # accident; excluded explicitly rather than left to coincidence.
        return 1
    return raw


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

    # 0. Policy check: the sentence was written under retired rules (#5461).
    #
    # FIRST, before the age check, and that order is the whole repair. A hook
    # written five minutes ago under the retired prompt is FRESH by every other
    # measure here — recent, same leader, same probability — so every later
    # check passes it. Age cannot see a rule change; only this can.
    if hook_policy_version(market_metadata) < CURRENT_HOOK_POLICY_VERSION:
        return True

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
