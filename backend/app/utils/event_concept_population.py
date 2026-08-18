"""The ONE enumeration of the event-concept tier (#1948).

WHY THIS MODULE EXISTS, and it is not tidiness.

`_score_event_concepts` in `routes/feed.py` enumerated the concept tier inline —
three listers, three try/excepts, three limits. `app/config/event_concept_warm_keys.py`
enumerated it again, by hand, as four golf majors. For as long as the leader
resolver could build on a cold cache those two lists were allowed to disagree,
because the feed's own build covered whatever the warmer missed.

UX-P089 (#1934) made `_resolve_concept_leader` **cache-only** — correctly: the
cold build was 10.08s of a 11.71s feed against a 6s client budget. But that
turned the warm list from an optimisation into the leader's ONLY source, and the
warm list was four golf majors. Every non-golf concept therefore resolved to
nothing. `event:cycling:vuelta-2026` went from Tadej Pogačar 0.751 of a 30-rider
field to no `leader` key at all, and `leader is None` is the suppress state on
BOTH surfaces — so all nine concept cards on the first page were dropped by iOS
and by web, in the same integration that shipped web's renderer for them
(#1939). The two fixes cancelled.

So the fix is not "add more keys to the hand-written list" — that just re-arms
the same trap for the next domain. The two populations become ONE function, and
the warmer consumes the feed's own enumeration. A concept the feed can show is
by construction a concept the warmer warms; they cannot drift apart again
because there is no second list to drift.

WHAT IS DELIBERATELY *NOT* HERE. This is not "warm every concept".
`event_concept_warm_keys.py` is right that an unbounded sweep finds the 300s
hard SIGKILL, and its four majors cost 11-35s each. The population below is the
UNSETTLED concepts only — exactly the set `_resolve_concept_leader` runs on, and
nothing else. Measured on production 2026-08-17, cold `GET /api/event/{key}`:

    event:cycling:vuelta-2026   0.32s   30 competitors, Pogačar 0.751
    event:ufc:26aug23           1.37s
    event:ufc:26aug22           0.24s
    event:ufc:26aug20           0.24s
    event:ufc:26aug19           1.00s

Sub-second to ~1.4s, against golf's 11-35s. The leader population is roughly an
order of magnitude cheaper per key than a single major, which is what makes
warming all of it affordable at all — and the warmer bounds it anyway, per tier,
rather than trusting that measurement to hold (`event_concept_warmer.py`).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Every status the feed asks its listers for. `settled` is admitted so a
#: just-finished marquee card can hold its WHAT-HIT pin (Queue #235 Item 4).
LISTED_STATUSES: tuple[str, ...] = ("upcoming", "live", "settled")

#: The statuses a LEADER is resolved for.
#:
#: This is derived, not chosen. In the feed's build loop a settled concept is
#: dropped unless it is in its WHAT-HIT window, and `_leader` is resolved only
#: when `_is_whathit` is False — and `_is_whathit` implies settled. So
#: "admitted AND not whathit" reduces exactly to "not settled". Stated as that
#: reduction rather than re-deriving the pin state here, which would be a second
#: copy of the very thing this module exists to stop copying.
UNSETTLED_STATUSES: tuple[str, ...] = ("upcoming", "live")

#: The concept sources, in the order `_score_event_concepts` has always asked
#: them. Each row: (label, sport_filter aliases, per-source limit, module,
#: function). Imports stay lazy — these modules pull in models and adapters, and
#: this module is imported by both a route and a Celery task.
CONCEPT_SOURCES: tuple[tuple[str, tuple[str, ...], int, str, str], ...] = (
    ("ufc", ("mma", "all", "ufc"), 12, "app.utils.event_ufc", "list_ufc_card_concepts"),
    ("f1", ("motorsports", "f1", "all"), 8, "app.utils.event_f1", "list_f1_gp_concepts"),
    ("cycling", ("cycling", "all"), 6, "app.utils.event_cycling", "list_cycling_concepts"),
)


def _source_applies(aliases: tuple[str, ...], sport_filter: str | None) -> bool:
    """A source runs when there is no filter, or the filter names it."""
    return not sport_filter or sport_filter in aliases


async def list_all_concepts(
    db: Any,
    *,
    sport_filter: str | None = None,
    statuses: tuple[str, ...] = LISTED_STATUSES,
) -> list[dict]:
    """Enumerate the concept tier. Best-effort per source, never raises.

    Per-source try/except is gotcha #42 — one bad lister must not empty the
    whole tier the way a throw inside `_score_events` once emptied the entire
    Sports tab (#1091). The healthy siblings survive, and the failure is logged
    rather than swallowed silently.
    """
    concepts: list[dict] = []
    for label, aliases, limit, module_path, func_name in CONCEPT_SOURCES:
        if not _source_applies(aliases, sport_filter):
            continue
        try:
            module = __import__(module_path, fromlist=[func_name])
            lister = getattr(module, func_name)
            concepts += await lister(db, statuses=statuses, limit=limit)
        except Exception as e:
            logger.warning("Concepts: failed to list %s concepts: %s", label, e)
    return concepts


async def list_unsettled_concept_keys(db: Any) -> tuple[str, ...]:
    """The leader resolver's OWN population, as cache keys.

    This is the set `_resolve_concept_leader` is called for on a feed build, and
    therefore the set whose envelopes have to be warm for it to return anything.
    Order-preserving dedupe: a key listed by two sources is warmed once, and the
    order the feed asks in is the order the warmer builds in, so the two agree
    about which key gets the budget first.
    """
    concepts = await list_all_concepts(db, statuses=UNSETTLED_STATUSES)
    seen: set[str] = set()
    keys: list[str] = []
    for c in concepts:
        key = (c or {}).get("key")
        if not isinstance(key, str) or not key.strip() or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return tuple(keys)
