"""Which sports StatPal can DISCOVER a game in, not merely agree about. #2867.

**SHIP: a sport cannot become StatPal's to own until StatPal can find its games
on its own — so a perfect agreement streak stops being enough.** (Pillar:
MATCHING. Program step 7, riding the lane's ship: *every game exists on the site
before any market lists it; nothing goes blank when ESPN does.*)

AGREEMENT IS NOT COVERAGE
═════════════════════════
`authority_by_sport.flip_permitted` gates a flip on a seven-day ≥99.5%
agreement streak. That streak is measured over the games **both** sources see.
It is silent on the capability the flip actually hands over: whether StatPal
could find a game ESPN never reported.

Those come apart, and not marginally. Of ESPN's 26 sports:

    discovery-resilient   4   NFL, MLB, NBA, NHL — a StatPal *schedule* sync on
                              the beat, which CREATES events via
                              `find_or_create_event` under a `statpal` claim.
    livescore-only        8   golf_pga + 7 soccer leagues. In
                              `STATPAL_SPORT_MAPPING`, so livescores update — but
                              no scheduled schedule-sync, so StatPal can only
                              UPDATE a row something else already created.
    no fallback          14   Not in `STATPAL_SPORT_MAPPING` at all.

A livescore-only sport can post a flawless seven-day streak. It agrees about
every game it is shown, and the intersection is exactly where the two sources
agree by construction. Flipping it would make StatPal the source of record for a
sport StatPal cannot enumerate — the ship's own first clause ("every game exists
on the site") broken by the change that was supposed to serve it.

So discovery coverage is a gate input, beside the shadow stamper and the
governing number, and this module is where it is stated.

WHY A LITERAL SET AND NOT A BEAT-SCHEDULE READ
══════════════════════════════════════════════
The truth being modelled lives in the beat schedule (`sync-statpal-schedules-*`
entries in `app/tasks/__init__.py`). Deriving it here would mean importing
`app.tasks` from a module that `app.config.authority_by_sport` imports — pulling
Celery, every task module and their clients into a config import, for a
four-element answer. `sport_keys.py`'s rule (imports nothing, stays
circular-import safe) is the shape that has held; this module keeps it.

The cost of a literal is that it can rot, and that cost is paid by a test rather
than by trust: `test_espn_dark_fallback_coverage_2867` derives the same set from
`celery_app.conf.beat_schedule` and fails if the two disagree. Adding a StatPal
schedule beat, or dropping one, moves a sport between tiers and trips there
rather than silently widening or narrowing what a flip is allowed to cover.
"""

from __future__ import annotations

from typing import Optional

#: Sports with a StatPal **schedule** sync on the beat — the ones where StatPal
#: can create a game nobody else reported.
#:
#: Mirrors the `sync-statpal-schedules-{nba,nhl,mlb,nfl}` beat entries and is
#: pinned against them by test. A livescore sync is deliberately NOT enough:
#: `sync-statpal-livescores` filters `status='live'`, so it can only ever update
#: a row that some other path already created.
#:
#: Soccer's absence is not a defect to fix here. Its season-schedule endpoint
#: returns thousands of global fixtures and overwhelms a single run, which is why
#: it was left off the beat (`app/tasks/__init__.py`, above the entries). It is a
#: fact to not forget: those leagues read as "StatPal covered" from
#: `STATPAL_SPORT_MAPPING` alone, and for discovery they are not.
DISCOVERY_SYNCED_SPORTS: frozenset[str] = frozenset(
    {
        "americanfootball_nfl",
        "baseball_mlb",
        "basketball_nba",
        "icehockey_nhl",
    }
)


def can_discover(sport_key: Optional[str]) -> bool:
    """Can StatPal find a game in `sport_key` that ESPN never reported?

    Total, like `authority_for`: every input has an answer and none raise. An
    unknown or empty key answers `False` — the conservative direction, because
    this function's only consumer is a gate, and a typo must not be able to
    widen what a flip is permitted to cover.
    """
    if not sport_key:
        return False
    return sport_key in DISCOVERY_SYNCED_SPORTS
