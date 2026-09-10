"""One decision site for "how old is this score, and who read it" (#4571).

Every price on an event payload carries its own observation clock; until this
module the score did not. `LiveAgeStamp` on the event page is handed
`freshestSourceStamp` — a max over `win_probability_sources[*].updated_at`,
i.e. **prices only** — so it prints a green `live · 8s ago` over a score it
knows nothing about.

Two rules, and they are the reason this is a function and not two assignments
repeated at seven call sites:

**1. Stamp on OBSERVATION, not on change.** Every score write site in this
codebase is shaped `if incoming != current: current = incoming`. A stamp placed
inside that guard would answer "when did the score last *change*", which is a
different question and is null for precisely the rows that need an answer most:
#4571's own specimen is a 0-0 NFL opener that a writer confirmed every 30
seconds and changed never. So `stamp` is called whenever a writer *read* a
score for the row, whether or not the number moved. The tennis games line
(`espn_sync`, live/073) is unconditional for exactly this reason.

**2. The clock is the OBSERVATION's, not the row write's.** Callers pass the
clock of the pass that read the upstream payload. Defaulting to `now()` inside
here would quietly convert a lagging read into a fresh-looking one — the single
failure this field exists to make visible — so `observed_at` is required.

Deliberately dependency-free: this is imported by two task modules and a
helper, and it must never be the reason one of them acquires a cycle
(same discipline as `sport_keys.py`, gotcha #3).
"""

from datetime import datetime
from typing import Any, Optional

# The writers permitted to claim a score observation. A typo'd source is worse
# than no source — it reads as a fourth writer in the attribution query that
# #4576 turns on — so the set is closed and `stamp` raises on anything else.
SCORE_OBSERVATION_SOURCES = frozenset({"espn", "statpal"})

# Mirrors `Event.score_source`'s String(20). Enforced here so an over-long
# source fails at the call site rather than as a DataError mid-commit, which in
# a per-item loop takes the whole pass down with it.
_MAX_SOURCE_LEN = 20


def stamp_score_observation(
    event: Any,
    *,
    source: str,
    observed_at: Optional[datetime],
) -> bool:
    """Record that `source` read this event's score at `observed_at`.

    Returns True when the stamp was written. Returns False — without raising —
    when `observed_at` is None, so a caller whose pass clock is unexpectedly
    absent degrades to the pre-#4571 behaviour (no stamp) rather than taking
    down a live score write. An absent stamp reads as "unknown age", which is
    honest; a wrong stamp does not.

    Raises ValueError on an unknown or over-long `source`: that is a coding
    error at a fixed call site, not a data condition, and it must not reach the
    column where it would silently corrupt the attribution query.
    """
    if source not in SCORE_OBSERVATION_SOURCES:
        raise ValueError(
            f"unknown score observation source {source!r}; "
            f"expected one of {sorted(SCORE_OBSERVATION_SOURCES)}"
        )
    if len(source) > _MAX_SOURCE_LEN:
        raise ValueError(
            f"score observation source {source!r} exceeds "
            f"{_MAX_SOURCE_LEN} characters"
        )
    if observed_at is None:
        return False

    event.score_source = source
    event.score_observed_at = observed_at
    return True


def score_observation_fields(event: Any) -> dict:
    """The stamp as payload keys — `{}` when the row has never been read.

    Present-only, so a client can distinguish "no writer has read this score"
    (keys absent) from any age we might otherwise have had to invent. Both keys
    always travel together: a source with no clock cannot be aged, and a clock
    with no source cannot be attributed, so half a stamp is served as none.

    Additive by construction — this returns a fresh dict for the caller to
    merge, and touches no existing key (#4571 scope item 2).
    """
    observed_at = getattr(event, "score_observed_at", None)
    source = getattr(event, "score_source", None)
    if observed_at is None or source is None:
        return {}
    return {
        "score_source": source,
        "score_observed_at": observed_at.isoformat(),
    }


def clear_score_observation(event: Any) -> None:
    """Drop the stamp when the score it describes is being cleared.

    A stamp outliving its score is a live-looking age over a `None`, which is
    the same class of lie the field exists to remove. Called by the
    bogus-completed and future-settled repairs in `espn_sync`, which null both
    scores.
    """
    event.score_source = None
    event.score_observed_at = None
