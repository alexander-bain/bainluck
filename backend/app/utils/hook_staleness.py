"""Hook staleness detection for Discover feed cards AND the futures detail page.

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

WHO ASKS, AND THE ONE THAT NEVER DID (#5906). Two serve paths publish a stored
hook to a reader: the Discover card (``routes/feed.py``, which has called
``is_hook_stale`` since this module shipped) and the futures DETAIL page
(``routes/futures.py``), which until #5906 served ``market.hook_description``
raw. Same sentence, same reader, one gate. The split was not a product
decision — nobody made it — and it was total rather than marginal: measured on
production 2026-09-13, of the **11,444 open markets carrying a hook, 0 are
policy 2 and 10,629 are also older than the 7-day age gate**, so every hook the
feed refuses is a hook the detail page publishes.

What a reader saw (#5906): ``/futures/8641774`` (*Brazil Série B: Winner*) said
*"Novorizontino has surged to the top"* under a hero crowning **Juventude** and
over a table where Novorizontino's own row read **—**, its price withheld by
#5876. Three statements, no two agreeing. That market's stored hook is policy 1,
was generated 2026-06-29 (76 days), and names a leader that has since changed —
it trips THREE of the rules below, and the feed had been suppressing it the
whole time.

The detail page's two share surfaces improve rather than empty: both
``app/futures/[id]/layout.tsx`` and ``opengraph-image.tsx`` already fall back to
a derived, true sentence (``"{leader} leads {market} at {probability}"``), and
the page body renders the paragraph conditionally, so suppression leaves no
gap to explain (notice 34).

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

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable


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


#: Shortest outcome name this module will look for inside a hook.
#:
#: Not a style rule — a false-positive bound. Real boards carry legs named
#: ``C``, ``D`` and ``Yes``, and a one- or two-character needle matches
#: somewhere in almost any English sentence, which would suppress hooks on
#: markets that have nothing wrong with them. Four is the shortest length at
#: which a name is carrying identity rather than a slot number.
MIN_MATCHABLE_OUTCOME_NAME = 4


def _is_word_char(ch: str) -> bool:
    """Whether ``\\b`` can assert a boundary against this character.

    Mirrors the regex engine's own ``\\w`` for ``str`` patterns — Unicode
    letters and digits plus underscore — so "í" and "ã" count, as they must for
    Avaí and São Bernardo.
    """
    return ch.isalnum() or ch == "_"


def hook_names_unpriced_outcome(
    *,
    hook_description: str | None,
    unpriced_outcome_names: Iterable[str],
) -> bool:
    """True if the hook talks about an outcome whose price this response withholds.

    #5906'S OWN RULE, AND IT IS NOT REDUNDANT WITH ``is_hook_stale`` ABOVE.
    Today it is inert — every stored hook is policy 1, so rule 0 suppresses the
    whole population before this is reached, and the Brazil specimen is caught
    three times over. It is here because that is a statement about a COUNT, not
    about the rule: the moment ``enrich_market_hooks`` writes policy-2 hooks,
    rule 0 stops firing and a freshly-written, correctly-versioned hook can name
    a leg the serializer withholds. The hook writer reads STORED prices; the
    serializer withholds at SERVE time (#5611/#5876), so the two can disagree
    about a leg without either being stale.

    Rule 2 above does not cover it. That rule asks whether the LEADER changed;
    this one fires on any named leg, and a hook routinely names a challenger
    ("X is closing on Y") whose price is the withheld one.

    WORD BOUNDARIES, NOT ``in``. The Brazil board carries a club named **Sport**,
    and a bare substring test would fire on the word "sports" in any hook —
    suppressing honest prose on markets with no withheld leg at all. ``\\b`` is
    Unicode-aware for ``str`` patterns, so accented names (Avaí, Ceará) bound
    correctly rather than falling back to ASCII.

    THE BOUNDARY IS APPLIED PER EDGE, WHICH IS NOT DECORATION. ``\\b`` asserts a
    word/non-word transition, so gluing it to a needle whose own first or last
    character is NOT a word character asserts a transition that can never occur:
    ``\\b\\(Over\\)\\b`` matches nothing at all, because the character before
    ``(`` in " (Over)" is a space and neither side is a word character. Outcome
    names carrying punctuation at the edge are real — ``(Over)``, ``+3.5``, a
    quoted song title — so an unconditional boundary would silently make this
    rule inert on exactly those legs. Each edge gets a boundary only when the
    needle's character there can participate in one.

    THE CALLER CHOOSES THE NAMES, deliberately, for the reason the futures
    serializer's own comment gives about withheld ids: only the caller can see
    which rows its display pipeline dropped, demoted or refused. Handing this
    module a display rule to re-derive would put a second copy of that judgement
    here, free to drift from the first.

    Pure: no DB, no clock, no LLM. Safe in a serve path.
    """
    if not hook_description:
        return False
    for name in unpriced_outcome_names:
        if not name:
            continue
        needle = str(name).strip()
        if len(needle) < MIN_MATCHABLE_OUTCOME_NAME:
            continue
        lead = r"\b" if _is_word_char(needle[0]) else ""
        trail = r"\b" if _is_word_char(needle[-1]) else ""
        pattern = f"{lead}{re.escape(needle)}{trail}"
        if re.search(pattern, hook_description, re.IGNORECASE):
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
