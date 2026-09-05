"""Which provider is the source of record for a sport's event graph. #2867, D50.

**SHIP: when a sport's seven days finally land, the flip that makes StatPal its
source of record is one line in this file — and until then, this file is the
thing that says out loud, per sport, that it has not happened.** (Pillar:
MATCHING. Program step 6, riding the lane's ship: *every game exists on the site
before any market lists it; nothing goes blank when ESPN does.*)

**Every sport here is `ESPN`. Nothing has flipped. Nothing flips by importing
this module.**

WHY A FILE FOR A DICTIONARY THAT IS ALL ONE VALUE
═════════════════════════════════════════════════
D50: *nothing user-visible flips without a measured 7-day ≥99.5% agreement row
from the bus AND a YOUR-TURN entry Alex has seen.* Two halves. The measurement
half has been built and is publishing (`utils/authority_agreement`,
`/api/admin/statpal/authority-agreement`). The other half — the act of flipping —
had no home at all. A flip with no home is a flip that happens as a scattered
diff across the registry on the day somebody decides the number looks good
enough, with the seven days recalled rather than checked.

So the switch exists before the number does, and it exists with its gate
attached: `flip_permitted` is the D50 sentence in code, and it answers with a
reason rather than a boolean, because "no" has four different meanings here and
three of them are fixed by waiting.

WHAT THIS FILE DOES NOT DO
══════════════════════════
It does not resolve anything. `event_registry` and the matcher are lane1's
(D50), and nothing in this module reads or writes an event. It publishes a
per-sport setting and the question that has to be answered before that setting
may change; the consumer that acts on it is lane1's to build, and every sport
being `ESPN` means the consumer's behaviour today is byte-for-byte what it is
now.

It also does not count the seven days itself. `streak_from_gates` does that, in
the module that owns what a gate state means — a second implementation of
"consecutive" is a second answer to the only question D50 asks.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from app.utils.authority_agreement import (
    FLIP_BAR_PCT,
    FLIP_STREAK_DAYS,
    GOVERNING_IDENTITY_NUMBERS,
    SHADOW_STAMPERS,
    streak_from_gates,
)

#: The two answers a sport's authority setting can hold.
ESPN = "espn"
STATPAL = "statpal"

#: What a sport falls back to when it is not named below, and what every named
#: sport holds today.
#:
#: ESPN, and not "unset". An unknown sport key must resolve to the behaviour the
#: site has always had, not to a state the caller has to interpret — a typo in a
#: sport key is a bug to find, never a reason for a surface to change provider.
DEFAULT_AUTHORITY = ESPN

#: **The switch. One line per sport, and a flip is a change to one of them.**
#:
#: Dark: every value is `ESPN`. A sport is listed here — rather than left to
#: `DEFAULT_AUTHORITY` — because the authority lane has built a dark id join for
#: it and is measuring it daily. Being listed says "this one is being watched",
#: never "this one is close".
#:
#: Changing a value is not sufficient on its own and is not meant to be:
#: `flip_permitted` has to say yes first, and D50's second half (a YOUR-TURN
#: entry Alex has seen) is not a thing code can check. `test_authority_flip_switch`
#: fails if a value here is `STATPAL` without the evidence recorded in
#: `FLIP_EVIDENCE`, so the one-line change carries its receipts or CI stops it.
AUTHORITY_BY_SPORT: dict[str, str] = {
    "americanfootball_nfl": ESPN,
    "basketball_nba": ESPN,
    "icehockey_nhl": ESPN,
    "baseball_mlb": ESPN,
}

#: For each sport that has flipped: the seven-day evidence it flipped on.
#:
#: Empty, because nothing has flipped. Each entry, when there is one, is the
#: ledger days that were read and the streak they produced — `days` is the
#: oldest-first list of gate states from `ARTIFACT-M-R-AUTHORITY-LEDGER.md`, and
#: `your_turn` names the entry Alex saw.
#:
#: The reason this is a separate map rather than a field on the switch: a flip
#: back to ESPN must be one line and must not require deleting the evidence that
#: the flip forward was earned. Rolling back is the move that has to be cheapest.
FLIP_EVIDENCE: dict[str, dict[str, Any]] = {}


def authority_for(sport_key: Optional[str]) -> str:
    """Which provider is the source of record for `sport_key` right now.

    Total: every input has an answer and none of them raise. A `KeyError` out of
    a config lookup in a Celery task is an outage in a sport we were not even
    changing, and `None`/unknown must mean "the site's existing behaviour", which
    is ESPN.
    """
    if not sport_key:
        return DEFAULT_AUTHORITY
    return AUTHORITY_BY_SPORT.get(sport_key, DEFAULT_AUTHORITY)


def flip_permitted(sport_key: str, gates: Sequence[str]) -> tuple[bool, str]:
    """May `sport_key` be flipped to StatPal, given its daily gate states?

    `gates` is oldest-first, one per day, as `identity.governing.gate` published
    them. Returns `(permitted, why)` — and `why` is the point of the function.
    "No" has four meanings here:

      * no dark id join for this sport at all, so there is nothing to flip TO;
      * no governing number ruled, so no day could ever have advanced (D63);
      * a streak that is real and not seven days long yet;
      * a streak broken by a day under the bar.

    Only the last is a problem. Returning a bare `False` for all four is how a
    sport that needs a ruling gets waited on instead, which is the failure this
    lane spent 9/4 unwinding on MLB.

    A `True` here is still not permission to flip. It is the first half of D50;
    the second half is a YOUR-TURN entry Alex has seen, and no function can
    check that.
    """
    if sport_key not in SHADOW_STAMPERS:
        return False, (
            f"{sport_key} has no shadow stamper, so there is no id join to flip "
            "onto — this is a build step, not a wait"
        )
    if not GOVERNING_IDENTITY_NUMBERS.get(sport_key):
        return False, (
            f"{sport_key} has no governing identity number (D63), so no daily "
            "row can advance its streak however good the agreement is — this "
            "needs a ruling, not more days"
        )
    streak = streak_from_gates(gates)
    if streak < FLIP_STREAK_DAYS:
        return False, (
            f"{sport_key} is {streak}/{FLIP_STREAK_DAYS} consecutive days at or "
            f"above {FLIP_BAR_PCT}% — a wait, not a defect"
        )
    return True, (
        f"{sport_key} has {streak}/{FLIP_STREAK_DAYS} consecutive days at or "
        f"above {FLIP_BAR_PCT}%. D50's measured half is met; the flip still "
        "needs a YOUR-TURN entry Alex has seen, which is not checkable here"
    )
