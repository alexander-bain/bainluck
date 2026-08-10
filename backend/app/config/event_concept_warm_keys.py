"""Which event-concept keys are kept warm (#1107, LAT-P021).

A named list, deliberately. The warmer is NOT "warm every concept": the concept
tier spans golf, tennis, cycling and the awards adapters, and a warmer that
walks all of them turns a targeted 4-key job into an unbounded sweep that will
find the global 300s hard SIGKILL. Adding a key here is a deliberate act with a
cost attached — four majors at 11-35s each is already most of a warm cycle.

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
