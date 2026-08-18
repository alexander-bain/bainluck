"""Which event-concept keys are kept warm BY NAME (#1107, LAT-P021).

A named list, deliberately, and it is now only HALF of what the warmer warms.

**Read this before adding a key here.** #1948: this file being the warmer's only
population is what deleted the concept tier from Discover. UX-P089 made
`_resolve_concept_leader` cache-only, so the warm set became the leader's only
source — and the warm set was these four golf slugs, so every non-golf concept
shipped with no probability and was suppressed on both surfaces. The fix was NOT
to paste more slugs in here; it was to make the warmer consume the feed's own
enumeration of unsettled concepts
(`app/utils/event_concept_population.py`). If you are here because a concept is
not warm, that is where it belongs — a slug added by hand is a slug that will
drift from the feed again.

What is still legitimately named here: keys that are expensive, permanent, and
NOT covered by the unsettled-concept population — the majors, which are warmed
for LATENCY (#1107's p0), not for content. The warmer is not "warm every
concept": the tier also spans tennis and the awards adapters, and an unbounded
sweep of all of them finds the global 300s hard SIGKILL. Adding a key here is a
deliberate act with a cost attached — four majors at 11-35s each is already most
of that tier's budget.

These four are here because #1107 is a p0 about them: they are the year's
biggest golf pages, and LAT-P021 measured every one of them missing the 2s bar
cold, with `event:golf:the-open-championship` crossing Heroku's 30s H12 boundary
into a 503.
"""

#: Golf majors, in the order the warmer builds them. Slowest first, so the key
#: most likely to be cut short by the task budget is the one that gets the whole
#: run's headroom rather than what three other builds left behind.
GOLF_MAJOR_CONCEPT_KEYS: tuple[str, ...] = (
    "event:golf:the-open-championship",
    "event:golf:the-masters",
    "event:golf:u-s-open",
    "event:golf:pga-championship",
)

#: Everything the warmer touches. Kept separate from the golf tuple so a future
#: domain can be added without re-pointing the task at a golf-shaped name.
WARM_CONCEPT_KEYS: tuple[str, ...] = GOLF_MAJOR_CONCEPT_KEYS
