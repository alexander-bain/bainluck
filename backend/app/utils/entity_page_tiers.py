"""entity_page_tiers — the tier resolver for auto-generated entity pages.

Spec: `docs/entity-page-templates.md` §2. Ruling: `docs/rulings/027-entity-pages-
render-a-declared-tier.md`. Epic #1741, step 0 (#1742).

── WHY THIS MODULE EXISTS AT ALL ──

Auto-generated entity pages die one specific death: the template is designed for
the rich case, and the thin case renders the rich case's chrome with nothing in
it. A section header over one card. A two-card carousel. "+1 more."

The fix is to make density a DECLARED, TYPED decision rather than something each
client re-derives. Ruling 021 is why that is non-negotiable: the moment web and
SwiftUI each count arrays to pick a layout, the same team renders as a map on one
and an answer on the other, and the parity bug is unfindable because both clients
are "correct".

── PURE ──

No I/O, no DB, no clock, no imports from `app.routes`. It is handed already-built
section data and returns counts plus a tier. That is what lets every later step
(leagues, competitions, teams, players) share ONE resolver instead of four, and
what lets the tier histogram run the real decision over every known entity.

The one clock-adjacent input, `now`, is an explicit PARAMETER with no default —
gotcha #44's lesson. A resolver that reads the wall clock cannot be swept.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# THE THRESHOLDS — every one of them named exactly ONCE, with its WHY.
# ---------------------------------------------------------------------------
#
# The C23 lesson is constant scatter: a number that appears in three files is
# three numbers, and the day someone tunes one of them the other two become a
# silent second policy. Spec §2 says these are "starting values ... calibratable
# mechanics" — the STRUCTURE (four tiers, count-gated, server-decided) is what was
# ruled. So they must be tunable in one edit, which means they must live in one
# place, which means nothing downstream may hardcode them.
#
# They are deliberately NOT yet tuned. Spec §11's one open decision is Alex's
# threshold taste-check, and it is explicitly gated on the tier histogram this
# step produces — an evidenced choice rather than a vibe. Do not "improve" these
# numbers before that histogram exists.

#: T3 needs enough distinct questions that navigation chrome has real work to do.
#: Below this a section shelf organizes nothing and becomes the broken shelf.
T3_MIN_ANSWERS = 12

#: ...AND enough *themed groups* to navigate between. 12 answers in one section is
#: a long list, not a map: an anchor nav with one anchor is chrome over nothing.
T3_MIN_SECTIONS_POPULATED = 3

#: What makes a section "populated". A section header earns its place by
#: organizing a group a reader could otherwise lose track of; two rows under a
#: heading is a heading over a pair.
SECTION_POPULATED_MIN_ANSWERS = 3

#: T2 needs enough answers that a flat list reads as a list. At 1-3 the page IS
#: the answer (T1) and each one renders full-width at full depth instead.
T2_MIN_ANSWERS = 4

#: The Journey Line never interpolates (chart spec P1-P4, doctrine A3). Fewer
#: real points than this is a shape, not a season, so the slot collapses entirely
#: rather than drawing a two-point "line".
TIMELINE_MIN_SNAPSHOTS = 5

#: ...and they must span real time. Five snapshots inside one hour is one moment
#: sampled five times; it says nothing about a journey.
TIMELINE_MIN_SPAN_HOURS = 24

#: "The record" prints its count-based summary line only above this n. Below it,
#: counts are still shown per row but the aggregate sentence is withheld — the
#: /calibration small-n honesty, ported (spec §5.3). Never a percentage below
#: calibration-grade n.
RECORD_SUMMARY_MIN_N = 5


# ---------------------------------------------------------------------------
# THE TIERS
# ---------------------------------------------------------------------------

TIER_FULL = "full"          # the page is a MAP
TIER_STANDARD = "standard"  # the page is a LIST
TIER_ANSWER = "answer"      # the page IS the answer
TIER_PRESENT = "present"    # the page is a STATEMENT (honest-empty, §6)

#: Not a tier — the generation gate. An entity with no identity and nothing true
#: to say does not get a page at all; it resolves to search / 404. "Never generate
#: a page whose only content is its own URL."
TIER_NONE = None

#: Ordered richest-first. Exported so the histogram and any UI that buckets by
#: tier share one ordering rather than each inventing one.
TIERS = (TIER_FULL, TIER_STANDARD, TIER_ANSWER, TIER_PRESENT)


# ---------------------------------------------------------------------------
# AVAILABILITY — ruling 025's conforming vocabulary, and ONLY this vocabulary
# ---------------------------------------------------------------------------
#
# Re-exported here because the entity envelope adopts the ruled four states from
# day one (spec §7). Doctrine C17 / register E10 record that
# `event_concept_cache` declares availability as `live/stale_ok/unavailable`,
# which is a THIRD vocabulary for the same fact. Entity pages must not inherit it.

AVAILABILITY_FRESH = "fresh"
AVAILABILITY_STALE = "stale"
AVAILABILITY_DEGRADED = "degraded"
AVAILABILITY_EMPTY = "empty"

AVAILABILITY_STATES = (
    AVAILABILITY_FRESH,
    AVAILABILITY_STALE,
    AVAILABILITY_DEGRADED,
    AVAILABILITY_EMPTY,
)

#: Translation from the legacy cache vocabulary. Kept as an explicit, total map so
#: an unrecognised legacy value is a KeyError at the seam rather than a silent
#: pass-through of a non-conforming string into the envelope.
_LEGACY_AVAILABILITY = {
    "live": AVAILABILITY_FRESH,
    "stale_ok": AVAILABILITY_STALE,
    "unavailable": AVAILABILITY_DEGRADED,
}


def conforming_availability(legacy: str | None, *, degraded: bool = False) -> str:
    """Map a legacy `live/stale_ok/unavailable` value onto ruling 025's vocabulary.

    `degraded=True` (a build recorded a typed loss) OVERRIDES a fresh read: a page
    served promptly but missing a section is not fresh, and conflating the two is
    exactly the concealment ruling 025 clause 4 names. A stale read stays stale —
    it is already declaring a substitution.
    """
    base = _LEGACY_AVAILABILITY.get(legacy or "", AVAILABILITY_FRESH)
    if degraded and base == AVAILABILITY_FRESH:
        return AVAILABILITY_DEGRADED
    return base


# ---------------------------------------------------------------------------
# COUNTING ANSWERS
# ---------------------------------------------------------------------------


def _dedup_key(market: Mapping[str, Any]) -> Any:
    """The identity of a QUESTION, not of a row.

    Spec §2: markets deduped by `group_id` + `canonical_market_key`. Ten Polymarket
    sub-markets about one question are one answer; 112 per-map matchup rows are not
    112 questions.

    Falls back to the row id so that a market carrying NEITHER key counts as its
    own answer. Falling back to the NAME would silently merge two genuinely
    different questions that happen to share a title, and under-counting is the
    direction that costs a page its tier.
    """
    group_id = market.get("group_id")
    canonical = market.get("canonical_market_key")
    if group_id or canonical:
        return ("q", group_id or None, canonical or None)
    return ("row", market.get("id"))


def _has_standable_number(market: Mapping[str, Any]) -> bool:
    """Doctrine Step 1: is there a blend number here we can stand behind?

    An answer must ANSWER something. A market whose every outcome is priceless is a
    question we are carrying, not one we can state — counting it would let a page
    claim a tier it cannot fill, which is the broken shelf arriving through the
    resolver instead of through the template.

    Deliberately NOT filtering the illiquid ~5% placeholder floor here. That
    exclusion is real (spec §2 names phantom placeholders) but it is a doctrine
    Step-1 judgement that lives with the blend, not a threshold this module may
    invent; a wrong floor silently deletes real answers. Recorded as owed rather
    than guessed — see the module note in the queue.
    """
    outcomes = market.get("top_outcomes") or []
    for o in outcomes:
        if not isinstance(o, Mapping):
            continue
        if o.get("probability") is not None:
            return True
    return False


def _is_settled(market: Mapping[str, Any], *, now: datetime) -> bool:
    """Settled items feed the record, never the answer count (doctrine A4).

    Determined from the fields the section payload actually carries. `status` is
    authoritative when present; otherwise a resolution date strictly in the past is
    taken as settled.

    A market with NEITHER signal is treated as LIVE. That is the safe direction: a
    stray settled row inflating a count by one is a smaller harm than silently
    deleting a live answer, and the resolution-date fallback already catches the
    ordinary case.
    """
    status = market.get("status")
    if isinstance(status, str) and status.lower() in {"resolved", "settled", "closed"}:
        return True

    raw = market.get("resolution_date")
    if isinstance(raw, str) and raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=now.tzinfo)
        return dt < now
    return False


def count_answers(
    sections: Mapping[str, Sequence[Mapping[str, Any]]] | None,
    *,
    now: datetime,
) -> dict[str, Any]:
    """Count ANSWERS per section and in total, plus what was excluded and why.

    Returns::

        {
          "answers": int,                    # distinct live standable questions
          "sections_populated": int,         # sections holding >= SECTION_POPULATED_MIN_ANSWERS
          "per_section": {name: {"answers": n, "total": rows, "settled": n, "unpriced": n}},
          "settled": int,
          "unpriced": int,
          "duplicates": int,
        }

    Every exclusion is COUNTED, never merely skipped — ruling 025 clause 3: a
    swallow that counts is detection, a swallow that doesn't is concealment. These
    counters are what let the histogram distinguish "this entity is thin" from
    "this entity's markets are unpriced", which are different problems with
    different owners.

    Per-item guarded (gotcha #42): one malformed market row must never zero a
    page's tier. A row that throws is counted as a duplicate-class exclusion rather
    than crashing the resolver, because a resolver that raises takes down the page
    it was meant to size.
    """
    per_section: dict[str, dict[str, int]] = {}
    seen: set[Any] = set()
    totals = {"settled": 0, "unpriced": 0, "duplicates": 0}
    answers = 0

    for name, rows in (sections or {}).items():
        sec = {"answers": 0, "total": 0, "settled": 0, "unpriced": 0}
        for market in rows or []:
            sec["total"] += 1
            try:
                if not isinstance(market, Mapping):
                    totals["duplicates"] += 1
                    continue
                if _is_settled(market, now=now):
                    sec["settled"] += 1
                    totals["settled"] += 1
                    continue
                if not _has_standable_number(market):
                    sec["unpriced"] += 1
                    totals["unpriced"] += 1
                    continue
                key = _dedup_key(market)
                if key in seen:
                    totals["duplicates"] += 1
                    continue
                seen.add(key)
                sec["answers"] += 1
                answers += 1
            except Exception:  # noqa: BLE001 — gotcha #42, and it is counted
                totals["duplicates"] += 1
        per_section[name] = sec

    sections_populated = sum(
        1 for s in per_section.values() if s["answers"] >= SECTION_POPULATED_MIN_ANSWERS
    )

    return {
        "answers": answers,
        "sections_populated": sections_populated,
        "per_section": per_section,
        **totals,
    }


def timeline_ok(snapshot_count: int, span_hours: float) -> bool:
    """Is there enough REAL series to draw the Journey Line? (spec §5.2)

    Both conditions, because either alone lies: five points inside an hour is one
    moment sampled five times, and two points a week apart is a line drawn between
    two dots. Below the floor the slot collapses ENTIRELY — no two-point lines, no
    interpolated theater, and nothing announces the absence (doctrine A6:
    unmeasured is not doubted).
    """
    return snapshot_count >= TIMELINE_MIN_SNAPSHOTS and span_hours >= TIMELINE_MIN_SPAN_HOURS


def resolve_tier(
    *,
    answers: int,
    sections_populated: int,
    entity_is_real: bool,
    record_n: int = 0,
    next_event_count: int = 0,
    season_known: bool = False,
) -> str | None:
    """The §2 gate. Returns a tier, or `TIER_NONE` for the generation gate.

    The ordering is richest-first and the gates are exclusive, so exactly one tier
    can match — a resolver with overlapping gates is two policies.

    `entity_is_real` is the caller's identity assertion (the entity exists in the
    registry with a name we can render). It is separate from the count inputs on
    purpose: a real entity with zero answers is a legitimate PAGE (T0, a statement
    with the record on it), while an unidentifiable key with zero answers is not a
    page at all.
    """
    if answers >= T3_MIN_ANSWERS and sections_populated >= T3_MIN_SECTIONS_POPULATED:
        return TIER_FULL
    if answers >= T2_MIN_ANSWERS:
        return TIER_STANDARD
    if answers >= 1:
        return TIER_ANSWER
    if entity_is_real and (record_n >= 1 or next_event_count >= 1 or season_known):
        return TIER_PRESENT
    return TIER_NONE


def resolve_entity_tier(
    sections: Mapping[str, Sequence[Mapping[str, Any]]] | None,
    *,
    now: datetime,
    entity_is_real: bool = True,
    record_n: int = 0,
    next_event_count: int = 0,
    season_known: bool = False,
) -> dict[str, Any]:
    """Count and resolve in one call — the entry point every entity class uses.

    Returns the counts from `count_answers` plus `tier` and a `pool_counts` block
    shaped for the envelope (spec §7), so a route stamps the payload rather than
    assembling the contract itself. Every count the page renders arrives IN the
    payload; clients never derive `shown/total` by measuring arrays.
    """
    counted = count_answers(sections, now=now)
    tier = resolve_tier(
        answers=counted["answers"],
        sections_populated=counted["sections_populated"],
        entity_is_real=entity_is_real,
        record_n=record_n,
        next_event_count=next_event_count,
        season_known=season_known,
    )
    return {
        **counted,
        "tier": tier,
        "pool_counts": {
            "answers": counted["answers"],
            # The clause-3 counter. Everything the resolver declined to count as an
            # answer, in one number the page can surface and the histogram can
            # separate from genuine thinness.
            "dropped": counted["unpriced"] + counted["duplicates"],
            "settled": counted["settled"],
        },
    }


# ---------------------------------------------------------------------------
# THE CHROME-EARNING GRAMMAR (§4) — the count checks, in one place
# ---------------------------------------------------------------------------
#
# The layout component enforces these client-side, but they are STATED here so the
# backend, the histogram and any future native client answer the same question the
# same way. A rule duplicated in TypeScript and Python is two rules.

#: A section header organizes; below two items it labels a pair.
CHROME_SECTION_HEADER_MIN_ITEMS = 2
#: ...and a header is only meaningful when there is something to distinguish it
#: FROM. One section on a page needs no header; the content is the page.
CHROME_SECTION_HEADER_MIN_SECTIONS = 2
#: A rail that does not scroll is a broken carousel.
CHROME_RAIL_MIN_ITEMS = 4
#: A grid that renders one orphaned row is a stack with extra steps.
CHROME_GRID_MIN_ITEMS = 3
#: "+1 more" is an apology; render the one extra item instead.
CHROME_MORE_LINK_MIN_HIDDEN = 2
#: A tab row needs somewhere to go, and something in each destination.
CHROME_TAB_MIN_TABS = 2
CHROME_TAB_MIN_ITEMS_PER_TAB = 3
#: An anchor nav with two anchors is two links pretending to be navigation.
CHROME_ANCHOR_NAV_MIN_SECTIONS = 3
#: A movers strip below this is a list of one thing that moved.
CHROME_MOVERS_MIN = 3


def earns_section_header(item_count: int, section_count: int) -> bool:
    return (
        item_count >= CHROME_SECTION_HEADER_MIN_ITEMS
        and section_count >= CHROME_SECTION_HEADER_MIN_SECTIONS
    )


def earns_rail(item_count: int) -> bool:
    return item_count >= CHROME_RAIL_MIN_ITEMS


def earns_grid(item_count: int) -> bool:
    return item_count >= CHROME_GRID_MIN_ITEMS


def earns_more_link(hidden_count: int) -> bool:
    return hidden_count >= CHROME_MORE_LINK_MIN_HIDDEN


def earns_anchor_nav(rendering_section_count: int) -> bool:
    return rendering_section_count >= CHROME_ANCHOR_NAV_MIN_SECTIONS


def earns_count_chip(tier: str | None) -> bool:
    """A count chip is a stat; at 1-3 answers the count is already visible and
    printing it is the page apologizing for its size (spec §3, banned at T1)."""
    return tier in (TIER_FULL, TIER_STANDARD)


def earns_movers_strip(mover_count: int) -> bool:
    return mover_count >= CHROME_MOVERS_MIN


def earns_record_summary(record_n: int) -> bool:
    return record_n >= RECORD_SUMMARY_MIN_N


def iter_tiers() -> Iterable[str]:
    """Stable richest-first ordering for histogram buckets and UI grouping."""
    return TIERS
