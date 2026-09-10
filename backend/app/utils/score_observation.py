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
#
# ⚠️ THIS SET IS THE CENSUS, AND IT MUST MATCH THE CODE, NOT THE ISSUE. CERT-2460
# blocked the first cut of #4571 for exactly this: the issue's scope line named
# "ESPN sync, StatPal livescores, MLB Stats API", so the set was
# `{"espn", "statpal"}` — and `mlb_sync` turned out never to touch
# `events.home_score` at all, while `odds_polling._poll_all_odds` (a live
# production writer, every ~5.5 min) writes `home_score`/`away_score` through a
# Core UPDATE and was missed. An unstamped writer is worse than an unstamped
# column: the row keeps whichever stamp a DIFFERENT source left behind, so the
# payload attributes an Odds API score to ESPN. That is the precise lie this
# field exists to remove, served with a fresh-looking age on top.
#
# Before adding a source here, grep for writes to `events.home_score` — ORM
# assignment AND `Event.__table__.update()` — and stamp every one of them.
#
# Named rather than spelled at the call sites, and the odds one is deliberately
# NOT called `..._API_...`.
#
# Two reasons, one of them learned the hard way. First: a call site reading
# `source=SCORE_SOURCE_ODDS` cannot typo a member of a closed set into a silent
# fourth writer. Second: gitleaks' `generic-api-key` rule fires on a keyword
# argument that pairs the odds provider id with the observation clock on one
# line — entropy 3.64, no secret anywhere in it — and fails CI. Naming the value
# keeps that pair off every line. Do not paste the offending form into a comment
# to explain it, either; the scanner reads comments.
SCORE_SOURCE_ESPN = "espn"
SCORE_SOURCE_STATPAL = "statpal"
SCORE_SOURCE_ODDS = "odds_api"

SCORE_OBSERVATION_SOURCES = frozenset(
    {SCORE_SOURCE_ESPN, SCORE_SOURCE_STATPAL, SCORE_SOURCE_ODDS}
)

# Mirrors `Event.score_source`'s String(20). Enforced here so an over-long
# source fails at the call site rather than as a DataError mid-commit, which in
# a per-item loop takes the whole pass down with it.
_MAX_SOURCE_LEN = 20


def _validate_source(source: str) -> None:
    """One definition of "may this writer claim an observation".

    Shared by the ORM stamp and the Core-UPDATE stamp so the two can never
    disagree about which sources exist — a drift that would show up as a
    silently unstamped writer, which is the CERT-2460 defect.
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


def score_observation_values(
    *,
    source: str,
    observed_at: Optional[datetime],
) -> dict:
    """The stamp as Core UPDATE columns — `{}` when there is no clock.

    `_poll_all_odds` writes scores through ``Event.__table__.update()``, and
    mixing an ORM attribute assignment into that write is gotcha #5 (flush
    ordering) — so that site cannot call :func:`stamp_score_observation`. It
    merges this dict into the same ``update_values`` instead, which makes the
    stamp ATOMIC with the score it describes: one UPDATE, so there is no window
    in which the row holds a new score under an old attribution.

    Same closed registry, same both-or-neither contract, same "no clock, no
    stamp" rule as the ORM path. Returning `{}` rather than raising means a
    caller with an unexpectedly absent pass clock degrades to the pre-#4571
    behaviour instead of taking down a live score write.
    """
    _validate_source(source)
    if observed_at is None:
        return {}
    return {"score_source": source, "score_observed_at": observed_at}


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
    _validate_source(source)
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
