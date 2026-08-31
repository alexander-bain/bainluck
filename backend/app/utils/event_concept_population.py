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
from typing import Any, Collection, NamedTuple

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


class ConceptSource(NamedTuple):
    """One concept source, and everything needed to read its markets ONCE."""

    label: str
    aliases: tuple[str, ...]  #: sport_filter values that select this source
    limit: int
    module_path: str
    func_name: str
    category: str  #: the `llm_sport_category` its open markets carry
    projection: tuple[str, ...]  #: FuturesMarket columns, in its row-loop order


#: The concept sources, in the order `_score_event_concepts` has always asked
#: them. Imports stay lazy — these modules pull in models and adapters, and
#: this module is imported by both a route and a Celery task.
#:
#: `projection` is the lister's OWN column order, declared here rather than in
#: the lister, because the prefetch has to hand back rows in exactly that shape.
#: Each lister builds its standalone read from this same tuple (LAT-P094), so
#: the two cannot disagree — the whole reason this module exists is that two
#: copies of one list always drift.
#: Each lister's own column order. Imported BY the listers rather than copied
#: into them — a projection that disagrees with the row loop it feeds silently
#: mis-assigns columns, which is a data bug wearing a latency fix's clothes.
COMBAT_PROJECTION: tuple[str, ...] = (
    "id",
    "external_id",
    "name",
    "commence_time",
    "market_metadata",
)
F1_PROJECTION: tuple[str, ...] = ("id", "name", "status", "resolution_date")
CYCLING_PROJECTION: tuple[str, ...] = ("name", "status", "resolution_date")

CONCEPT_SOURCES: tuple[ConceptSource, ...] = (
    ConceptSource(
        "ufc",
        ("mma", "all", "ufc"),
        12,
        "app.utils.event_ufc",
        "list_ufc_card_concepts",
        "mma",
        COMBAT_PROJECTION,
    ),
    ConceptSource(
        "f1",
        ("motorsports", "f1", "all"),
        8,
        "app.utils.event_f1",
        "list_f1_gp_concepts",
        "motorsports",
        F1_PROJECTION,
    ),
    ConceptSource(
        "cycling",
        ("cycling", "all"),
        6,
        "app.utils.event_cycling",
        "list_cycling_concepts",
        "cycling",
        CYCLING_PROJECTION,
    ),
)

#: `projection` lookup for the listers' own standalone reads. Keyed by category
#: so a lister asks with the one thing it already knows about itself.
PROJECTION_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    s.category: s.projection for s in CONCEPT_SOURCES
}


#: The `sport:` tag prefix the feed's static tag filter uses.
SPORT_TAG_PREFIX = "sport:"

#: Every alias that names a concept source, the `all` wildcard excluded.
#:
#: DERIVED from `CONCEPT_SOURCES`, and that is the whole point. `routes/feed.py`
#: decided whether a `sport:`-tagged feed build should run the concept tier from
#: its own hand-written `{"sport:mma", "sport:motorsports", "sport:f1"}` — a
#: second copy of the vocabulary below, and it had already lost `cycling`, so a
#: cycling surface skipped the tier that holds the grand tours. That is the
#: exact trap this module was created for, one file over.
CONCEPT_SPORT_ALIASES: frozenset[str] = frozenset(
    alias for source in CONCEPT_SOURCES for alias in source.aliases if alias != "all"
)


def concept_filter_for_tags(
    tags: Collection[str] | None,
) -> tuple[bool, tuple[str, ...] | None]:
    """Translate a feed build's static tags into a concept-tier filter.

    Returns ``(skip, sport_filter)``:

    * **no `sport:` tags** -> ``(False, None)``. The unfiltered feed; every
      source runs, exactly as before.
    * **tags naming at least one source** -> ``(False, (alias, …))``. ONLY those
      sources run. This is the half that was missing: the gate in `feed.py`
      admitted the build and then handed the builder no filter at all, so the
      tier was gated by the sport tag and never filtered by it.
    * **tags naming none of them** -> ``(True, None)``. The concept tier has
      nothing to add to a soccer page, so it is skipped rather than built and
      discarded — which is what the old gate got right and is preserved here.

    Measured on production 2026-08-29, before the fix: `?tags=["sport:mma"]`
    returned 16 concepts of which 5 were foreign (1 cycling + 4 F1), and
    `?tags=["sport:motorsports"]` returned the *same 16*, of which 12 were.
    `?tags=["sport:cycling"]` returned 0 — the missing-alias half of the same
    defect, on the one surface where the Vuelta belongs.
    """
    named = {
        t[len(SPORT_TAG_PREFIX) :]
        for t in tags or ()
        if t.startswith(SPORT_TAG_PREFIX)
    }
    if not named:
        return False, None
    applicable = tuple(sorted(named & CONCEPT_SPORT_ALIASES))
    return (False, applicable) if applicable else (True, None)


def concept_filter_for_category(
    category: str | None,
) -> tuple[bool, tuple[str, ...] | None]:
    """Translate a ``/categories/<slug>`` browse filter into a concept-tier filter.

    The `category` sibling of `concept_filter_for_tags`, and derived from the
    same `CONCEPT_SOURCES` for the same reason: `routes/feed.py` already grew
    one hand-written copy of this vocabulary, lost `cycling` out of it, and
    skipped the tier that holds the grand tours on the one surface where they
    belong (UX-P177). A second copy for a second caller is that trap again with
    a different name.

    Returns ``(skip, sport_filter)``, the same shape:

    * **no category** -> ``(False, None)``. Discover and every pre-existing
      caller, unchanged: no constraint, every source runs.
    * **a category naming a source** -> ``(False, (alias,))``. ONLY that source.
    * **any other category** -> ``(True, None)``. The concept tier has nothing
      to put on an economics page, so it is skipped rather than built and
      appended — which is precisely what CERT-542 found it doing.

    That `llm_sport_category` and the source aliases share a vocabulary is
    checked, not assumed: measured on production 2026-08-31, `mma` (240 open
    markets), `motorsports` (144) and `cycling` (17) are all live
    `llm_sport_category` values and all three name a source. `ufc` and `f1` are
    aliases with no category of their own; admitting them costs nothing and is
    what keeps this derived from `CONCEPT_SOURCES` rather than from a list.
    """
    if not category:
        return False, None
    if category in CONCEPT_SPORT_ALIASES:
        return False, (category,)
    return True, None


def _source_applies(
    aliases: tuple[str, ...], sport_filter: str | Collection[str] | None
) -> bool:
    """A source runs when there is no filter, or the filter names it.

    `sport_filter` is a single alias or a collection of them — a feed build can
    carry more than one `sport:` tag and there is no single alias that says "MMA
    or motorsports". A collection matches when ANY entry names the source, which
    is the same OR the single-string form has always run against the source's
    own alias tuple.
    """
    if not sport_filter:
        return True
    if isinstance(sport_filter, str):
        return sport_filter in aliases
    return any(f in aliases for f in sport_filter)


async def select_open_markets(
    db: Any, category: str, projection: tuple[str, ...]
) -> list:
    """One source's open markets, in its own column order.

    The standalone read every lister falls back to when it is handed no
    prefetched rows — the `/event` adapters, the warmer and four suites call
    the listers directly, so this path is not a degraded mode, it is the
    single-source mode.
    """
    from sqlalchemy import select

    from app.models import FuturesMarket

    cols = [getattr(FuturesMarket, name) for name in projection]
    return list(
        (
            await db.execute(
                select(*cols).where(
                    FuturesMarket.llm_sport_category == category,
                    FuturesMarket.status == "open",
                )
            )
        ).all()
    )


async def prefetch_open_markets(
    db: Any, categories: tuple[str, ...] | set[str]
) -> dict[str, list]:
    """ONE read of the open markets every applicable source needs (LAT-P094).

    WHY, measured on production 2026-08-26. `futures_markets` has no index on
    `llm_sport_category` for the general case, so each source's own read is an
    index scan over every open market — 50,749 rows visited to emit 168, 27,839
    buffers, ~520ms, and it ran three times per cold feed build for 315 rows in
    total. Six interleaved A/B round trips: three reads 1,109.5ms p50 vs one
    combined read 453.4ms p50.

    The rows come back re-projected per source, so each lister consumes exactly
    the tuple shape its own read would have produced.
    """
    from sqlalchemy import select

    from app.models import FuturesMarket

    wanted = {c for c in categories if c in PROJECTION_BY_CATEGORY}
    if not wanted:
        return {}

    # The union of every applicable projection, plus the category itself so the
    # rows can be split back out. Ordered, so the index map below is stable.
    columns: list[str] = ["llm_sport_category"]
    for source in CONCEPT_SOURCES:
        if source.category not in wanted:
            continue
        for name in source.projection:
            if name not in columns:
                columns.append(name)
    index_of = {name: i for i, name in enumerate(columns)}

    rows = list(
        (
            await db.execute(
                select(*[getattr(FuturesMarket, n) for n in columns]).where(
                    FuturesMarket.status == "open",
                    FuturesMarket.llm_sport_category.in_(sorted(wanted)),
                )
            )
        ).all()
    )

    out: dict[str, list] = {c: [] for c in wanted}
    picks = {c: tuple(index_of[n] for n in PROJECTION_BY_CATEGORY[c]) for c in wanted}
    for row in rows:
        bucket = out.get(row[0])
        if bucket is None:
            continue
        bucket.append(tuple(row[i] for i in picks[row[0]]))
    return out


async def list_all_concepts(
    db: Any,
    *,
    sport_filter: str | Collection[str] | None = None,
    statuses: tuple[str, ...] = LISTED_STATUSES,
) -> list[dict]:
    """Enumerate the concept tier. Best-effort per source, never raises.

    Per-source try/except is gotcha #42 — one bad lister must not empty the
    whole tier the way a throw inside `_score_events` once emptied the entire
    Sports tab (#1091). The healthy siblings survive, and the failure is logged
    rather than swallowed silently.

    LAT-P094: the sources' market reads are collapsed into ONE scan up front.
    That makes the prefetch a single point three sources depend on, so it gets
    the same best-effort treatment they have — if it fails, every lister runs
    its own read exactly as before and the tier still ships.
    """
    applicable = [
        s for s in CONCEPT_SOURCES if _source_applies(s.aliases, sport_filter)
    ]
    if not applicable:
        return []

    try:
        prefetched: dict[str, list] | None = await prefetch_open_markets(
            db, {s.category for s in applicable}
        )
    except Exception as e:
        logger.warning(
            "Concepts: shared open-market prefetch failed, falling back to "
            "per-source reads: %s",
            e,
        )
        prefetched = None

    concepts: list[dict] = []
    for source in applicable:
        try:
            module = __import__(source.module_path, fromlist=[source.func_name])
            lister = getattr(module, source.func_name)
            extra = (
                {"rows": prefetched.get(source.category, [])}
                if prefetched is not None
                else {}
            )
            concepts += await lister(db, statuses=statuses, limit=source.limit, **extra)
        except Exception as e:
            logger.warning("Concepts: failed to list %s concepts: %s", source.label, e)
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
