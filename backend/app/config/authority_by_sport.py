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
reason rather than a boolean, because "no" has five different meanings here and
only one of them is a defect.

WHAT THIS FILE DOES NOT DO
══════════════════════════
It does not resolve anything. `event_registry` and the matcher are lane1's
(D50), and nothing in this module reads or writes an event. It publishes a
per-sport setting and the question that has to be answered before that setting
may change; the consumer that acts on it is lane1's to build, and every sport
being `ESPN` means the consumer's behaviour today is byte-for-byte what it is
now.

It also does not count the seven days itself. `authority_streak.compute_streak`
does that — it shipped with authority/021, it walks the durable ledger's own
`days[]`, and it already knows the difference between a day that carries and a
day that resets. A second implementation of "consecutive" would be a second
answer to the only question D50 asks.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from app.utils.authority_agreement import (
    FLIP_BAR_PCT,
    GOVERNING_IDENTITY_NUMBERS,
    SHADOW_STAMPERS,
)

# `REQUIRED_STREAK_DAYS` and `compute_streak` both shipped with authority/021.
# Imported, never restated: the seven-day count has one owner.
from app.utils.authority_streak import REQUIRED_STREAK_DAYS, compute_streak

# lane1/132, CERT-1871: the gate's fourth input. Agreement is measured over the
# games both sources see and is therefore silent about whether StatPal could
# find a game ESPN missed — a different capability, and the one a flip actually
# hands over. Imports nothing beyond `typing`, so it costs a config import
# nothing.
from app.utils.statpal_discovery_coverage import can_discover

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
#: Empty, because nothing has flipped. Each entry, when there is one, holds the
#: `days` it flipped on — the durable ledger's own `days[]` entries, copied as
#: they stood, so the evidence is the same objects `compute_streak` walked and
#: not a retelling of them — and `your_turn`, naming the entry Alex saw.
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


def flip_permitted(
    sport_key: str, ledger_days: Iterable[dict[str, Any]]
) -> tuple[bool, str]:
    """May `sport_key` be flipped to StatPal, given its durable ledger's days?

    `ledger_days` is the `days[]` list from that sport's
    `authority-agreement-ledger:<sport_key>` snapshot — the same entries
    `authority_streak.fold_day` writes, one per UTC day, each carrying its
    `state`. The counting is `compute_streak`'s, not this module's.

    Returns `(permitted, why)`, and `why` is the point of the function. "No" has
    SIX meanings here:

      * no dark id join for this sport at all, so there is nothing to flip TO;
      * no scheduled StatPal DISCOVERY path, so StatPal could not find a game
        ESPN missed however well the two agree about the games both can see;
      * no governing number ruled, so no day could ever have advanced (D63);
      * no ledger at all — not measured, which is not a streak of zero;
      * a streak that is real and not seven days long yet;
      * a streak broken by a day under the bar, or by a day nobody recorded.

    Only the last is a problem. Returning a bare `False` for all six is how a
    sport that needs a ruling gets waited on instead, which is the failure this
    lane spent 9/4 unwinding on MLB. The last two share a wording — both are
    reported with `compute_streak`'s own `stopped_by` detail, which names the day
    and the reason rather than making the reader go and look.

    A `True` here is still not permission to flip. It is the first half of D50;
    the second half is a YOUR-TURN entry Alex has seen, and no function can
    check that.
    """
    if sport_key not in SHADOW_STAMPERS:
        return False, (
            f"{sport_key} has no shadow stamper, so there is no id join to flip "
            "onto — this is a build step, not a wait"
        )
    if not can_discover(sport_key):
        # Agreement is not coverage (lane1/132, CERT-1871). The streak is scored
        # on the INTERSECTION — the games both sources list — which is exactly
        # where the two agree by construction. A livescore-only sport can post a
        # flawless seven days and still be unable to enumerate its own fixtures,
        # and flipping it would make StatPal the source of record for a sport
        # StatPal cannot find games in. That breaks the first clause of the ship
        # this switch serves rather than serving it.
        return False, (
            f"{sport_key} has no scheduled StatPal discovery path, so StatPal "
            "cannot find a game ESPN missed — its agreement streak is measured "
            "only over the games both sources already see. This is a build "
            "step, not a wait"
        )
    if not GOVERNING_IDENTITY_NUMBERS.get(sport_key):
        return False, (
            f"{sport_key} has no governing identity number (D63), so no daily "
            "row can advance its streak however good the agreement is — this "
            "needs a ruling, not more days"
        )
    streak = compute_streak(ledger_days)
    if streak is None:
        # `None` is not zero. An empty ledger has never been measured, and
        # reporting it as "0/7 consecutive days" would describe a sport that
        # failed a bar it was never held to (gotcha #53).
        return False, (
            f"{sport_key} has no agreement ledger yet — not measured, which is "
            "not a streak of zero. The first daily pass starts it"
        )
    days = streak["days"]
    if days < REQUIRED_STREAK_DAYS:
        return False, (
            f"{sport_key} is {days}/{REQUIRED_STREAK_DAYS} consecutive days at or "
            f"above {FLIP_BAR_PCT}% — a wait, not a defect. "
            f"{(streak.get('stopped_by') or {}).get('detail', '')}".strip()
        )
    return True, (
        f"{sport_key} has {days}/{REQUIRED_STREAK_DAYS} consecutive days at or "
        f"above {FLIP_BAR_PCT}%. D50's measured half is met; the flip still "
        "needs a YOUR-TURN entry Alex has seen, which is not checkable here"
    )
