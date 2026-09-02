"""Collapse duplicate fixture rows out of a page of search results.

THE SHIP (#2623). A fan searching "Sabalenka" was shown **every WTA match
twice**: one rich row (tournament chip, full names, avatars, score) and one
ghost beside it (bare `WTA` chip, surname only, no score, start time off by
hours). The page said "26 results · 16 games" when there were nine matches.

The ghosts are not a ranking quirk, they are a population. Measured in
production 2026-09-01:

    sport_key       events   with_score
    tennis_atp      13,874        0
    tennis_other     7,978        0
    tennis_wta       4,790        0
    ...              (tournament-specific buckets carry the scores)

The generic per-tour buckets have **never** held a score. Every real match
also exists under a tournament-specific sport (`tennis_wta_us_open`,
`tennis_wta_cincinnati_open`, ...) with full player names and a result. The
two rows are the same fixture seen through two providers, and per ruling 048
the id-less claim correctly CREATED rather than absorbed — the missing half is
the id-keyed drain, which is `event_provider_anchors` (#1946).

This module does NOT drain anything. It is the user-visible half: a page of
search results must not render a less-specific, scoreless twin beside the row
it duplicates. When the anchor channel lands and the duplicates go away, this
helper simply stops finding pairs and costs one pass over ~25 rows.

WHY THE RULES ARE CONJUNCTIVE. The obvious rule — "same teams, same day, keep
one" — eats real fixtures: an MLB doubleheader is two genuine completed games
between the same two clubs hours apart. So a row is only ever dropped when
another row on the same page **dominates** it: same sport family, same
participants, close in time, and *strictly more specific* in naming or in
having the result the other lacks. Two equally-specific scored rows never
collapse, which is exactly the doubleheader.

WHY IT IS SCOPED TO INDIVIDUAL SPORTS, and this was found by MEASURING rather
than reasoning. The first cut of this helper ran on every sport. Replayed
against ten live `/api/events/search` payloads it collapsed the tennis ghosts
correctly and then ate **consecutive games of an MLB series**: Angels–Yankees
on Sep 1 (closed 4-1), Sep 2 (live 3-4) and Sep 3 (scheduled) are three real
games with identical team names ~24h apart, so the "has the result the other
lacks" branch fired on the un-played one. Team sport plays the same opponent
on back-to-back days as a matter of routine; two tennis players, two fighters
or two boxers do not. So the pass runs only where "same two participants
within 36h" genuinely implies "same fixture" — which is also exactly where the
measured ghost population is.

The duplicate rows that pass 5 found in MLB are real (two byte-identical live
Angels–Yankees rows, and a `St. Louis` / `St.Louis` pair at the same minute)
but they are a DIFFERENT shape: equally specific, equally scored, so no
dominance test can pick a survivor and none should try. Those belong to the
event-graph drain, not to a renderer.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Iterable

from app.utils.event_completion import commence_time_is_a_reported_start

# Observed pair-gap in the #2623 population runs to 23h (the ghost's start time
# is a provider close-time, not a start time — gotcha #14). 36h keeps every
# observed pair together while staying well inside "the next edition of this
# fixture", which for tennis is days and for league sport is at minimum a day.
FIXTURE_TIME_WINDOW_HOURS = 36

# Q048: the window above is EVIDENCE OF SEPARATENESS — "these started far apart,
# so they are different fixtures". That inference needs both sides to be times
# somebody reported, and one whole class of ghost is exactly the case where one
# is not.
#
# A `commence_time_source = 'kalshi_ticker'` row carries midnight UTC of a date
# parsed out of a Kalshi ticker, and for tennis that date is the TOURNAMENT
# SEGMENT's date, not the match's (CERT-706 measured the same thing from the
# other side: `26AUG30` in the ticker while the match was played 2026-09-01).
# So the gap against the real row is an artefact of the stand-in, and reading it
# as evidence is reading something nobody reported.
#
# Measured on production 2026-09-02 over the 22 ghost/real pairs the Kalshi
# segment key identifies across the US Open: gaps run **15.0h to 71.1h, median
# 66.7h**, and **19 of the 22 fall outside the 36h window** — so the dedup that
# #2623 shipped cannot reach the population this queue is about. `/api/events/
# 15300759` (a ghost of Monfils v Vallejo) sits **71.1h** from the real row and
# ranks FIRST for a search on "Monfils".
#
# 96h covers all 22 with headroom and stays bounded — it is deliberately NOT
# "no window at all", because an unbounded pass would let any past meeting of
# the same two players dominate a future ghost. Under-coverage is the safe
# failure direction here: a missed ghost renders, a false drop deletes a real
# match.
DERIVED_START_WINDOW_HOURS = 96

# The 1-on-1 sports, where the same two participants meeting twice inside the
# window is not a thing that happens. Mirrors `_INDIVIDUAL_SPORT_PREFIXES` in
# `app/routes/events.py`; duplicated rather than imported because a utils
# module must not import a route (and `sport_keys.py` imports nothing by law —
# gotcha #3). `tests/test_search_fixture_dedup.py` asserts the two agree, so
# the copy cannot drift silently.
INDIVIDUAL_SPORT_PREFIXES: tuple[str, ...] = (
    "tennis_",
    "mma_",
    "boxing_",
    "golf_",
)


def is_individual_sport(sport_key: Any) -> bool:
    if not sport_key:
        return False
    return str(sport_key).startswith(INDIVIDUAL_SPORT_PREFIXES)


def _normalize_name(value: Any) -> str:
    """Case-, accent- and whitespace-insensitive form of a participant name."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().split())


def _surname(value: Any) -> str:
    """The last whitespace token — the token the ghost rows carry alone."""
    normalized = _normalize_name(value)
    if not normalized:
        return ""
    return normalized.split()[-1]


def _sport_family(sport_key: Any) -> str:
    """`tennis_wta_us_open` and `tennis_wta` are both `tennis`.

    The whole point is that the twins sit in DIFFERENT sport rows, so the group
    key cannot be the sport key itself. Family is deliberately coarse; the
    participant match below is what carries the precision.
    """
    if not sport_key:
        return ""
    return str(sport_key).split("_", 1)[0].lower()


def _sport_specificity(sport_key: Any) -> int:
    """How many underscore segments the key has — a tiebreak, never a rule.

    `tennis_wta_us_open` (3) beats `tennis_wta` (2) when both rows are
    otherwise equally rich, so the survivor is the one wearing the tournament
    chip. It is NOT part of the dominance test: a sport key must never on its
    own be grounds for hiding a row.
    """
    if not sport_key:
        return 0
    return len(str(sport_key).split("_"))


class _Row:
    """A duck-typed view of whatever the caller is paginating.

    Both call sites hold ORM `Event` rows, but the helper stays free of the
    model import so its tests need no database and no app import graph.
    """

    __slots__ = (
        "obj", "id", "home", "away", "commence_time", "scored", "sport_key",
        "derived_start",
    )

    def __init__(self, obj: Any, sport_key: Any):
        self.obj = obj
        self.id = getattr(obj, "id", None)
        self.home = getattr(obj, "home_team_name", None)
        self.away = getattr(obj, "away_team_name", None)
        self.commence_time = getattr(obj, "commence_time", None)
        # Q048. `commence_time_is_a_reported_start` is the repo's ONE definition
        # of "this field holds a stand-in" (q076/CERT-690) and the two status
        # clocks already read it. Reading the same predicate here rather than
        # comparing to the literal is what keeps a future derived provenance
        # from joining the rule in `event_completion` and being missed here.
        self.derived_start = not commence_time_is_a_reported_start(
            getattr(obj, "commence_time_source", None)
        )
        self.scored = (
            getattr(obj, "home_score", None) is not None
            and getattr(obj, "away_score", None) is not None
        )
        self.sport_key = sport_key

    @property
    def name_length(self) -> int:
        return len(_normalize_name(self.home)) + len(_normalize_name(self.away))

    @property
    def richness(self) -> tuple:
        """Sort key, richest first. Ordering only — dominance decides drops."""
        return (
            1 if self.scored else 0,
            self.name_length,
            _sport_specificity(self.sport_key),
        )


def _resolve_sport_key(obj: Any) -> Any:
    """`event.sport.key`, tolerating an unloaded or absent relationship.

    Deliberately does NOT trigger a lazy load: both call sites `selectinload`
    the sport, and a helper that quietly emits IO per row inside a request is
    how a dedup pass becomes a latency incident.
    """
    explicit = getattr(obj, "sport_key", None)
    if explicit:
        return explicit
    sport = obj.__dict__.get("sport") if hasattr(obj, "__dict__") else None
    return getattr(sport, "key", None) if sport is not None else None


def _slot_at_least_as_specific(richer: Any, poorer: Any) -> tuple[bool, bool]:
    """(is-at-least-as-specific, is-strictly-more-specific) for one participant.

    "Aryna Sabalenka" is strictly more specific than "Sabalenka"; the suffix is
    matched on a whole-word boundary so "Wang" does not absorb "Huang".
    """
    a = _normalize_name(richer)
    b = _normalize_name(poorer)
    if not a or not b:
        return (False, False)
    if a == b:
        return (True, False)
    if a.endswith(" " + b):
        return (True, True)
    return (False, False)


def _dominates(richer: _Row, poorer: _Row) -> bool:
    """True when `poorer` is a strictly worse rendering of `richer`'s fixture.

    Requires, in both participant slots and in either orientation, that the
    survivor's name is at least as specific — and then at least one real reason
    to prefer it: a strictly fuller name somewhere, or the result the other row
    is missing. Equally-specific scored rows fail both branches and both stay.
    """
    if richer.id is None or poorer.id is None or richer.id == poorer.id:
        return False
    if not richer.scored and poorer.scored:
        return False

    orientations = (
        ((richer.home, poorer.home), (richer.away, poorer.away)),
        ((richer.home, poorer.away), (richer.away, poorer.home)),
    )
    for slots in orientations:
        checks = [_slot_at_least_as_specific(a, b) for a, b in slots]
        if not all(ok for ok, _ in checks):
            continue
        fuller_name = any(strict for _, strict in checks)
        has_the_result = richer.scored and not poorer.scored
        if fuller_name or has_the_result:
            return True
    return False


def _within_window(a: _Row, b: _Row) -> bool:
    if a.commence_time is None or b.commence_time is None:
        return False
    try:
        delta = abs((a.commence_time - b.commence_time).total_seconds())
    except TypeError:
        # Naive minus aware. `commence_time` is timestamptz so this cannot
        # happen in production, but a dedup pass is an accelerator and must
        # never be the thing that 500s a search. Unknown gap => not a twin.
        return False
    # Q048: a stand-in start is not evidence of separateness, so a pair holding
    # one gets the wider bound. BOTH sides derived keeps the NARROW window on
    # purpose — two stand-ins are two dates, and nothing in the gap between them
    # was reported by anybody, so widening there would be pairing rows on no
    # evidence at all. (Dominance would refuse them anyway: two ghosts are
    # equally unspecific and equally scoreless. The window is the cheaper and
    # more honest place to say so.)
    one_side_derived = a.derived_start != b.derived_start
    hours = DERIVED_START_WINDOW_HOURS if one_side_derived else FIXTURE_TIME_WINDOW_HOURS
    return delta <= hours * 3600


def duplicate_fixture_event_ids(events: Iterable[Any]) -> set:
    """Ids of rows that another row on the same page already renders, better.

    Pure and order-independent: it reads only the fields listed on `_Row` and
    returns ids, so the caller keeps its own ordering and its own formatting.
    """
    rows = [_Row(obj, _resolve_sport_key(obj)) for obj in events]
    groups: dict[tuple, list[_Row]] = {}
    for row in rows:
        if row.id is None or row.commence_time is None:
            continue
        if not is_individual_sport(row.sport_key):
            continue
        home, away = _surname(row.home), _surname(row.away)
        if not home or not away:
            continue
        family = _sport_family(row.sport_key)
        if not family:
            continue
        # Orientation-insensitive: the two providers do not agree on which
        # participant is "home" for a neutral-court tennis match.
        groups.setdefault((family, frozenset((home, away))), []).append(row)

    dropped: set = set()
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (r.richness, r.id), reverse=True)
        for index, poorer in enumerate(group):
            if poorer.id in dropped:
                continue
            for richer in group[:index]:
                if richer.id in dropped:
                    continue
                if _within_window(richer, poorer) and _dominates(richer, poorer):
                    dropped.add(poorer.id)
                    break
    return dropped


def collapse_duplicate_fixtures(events: Iterable[Any]) -> tuple[list, int]:
    """`(kept, dropped_count)`, preserving the caller's ordering exactly."""
    ordered = list(events)
    dropped = duplicate_fixture_event_ids(ordered)
    if not dropped:
        return ordered, 0
    kept = [e for e in ordered if getattr(e, "id", None) not in dropped]
    return kept, len(ordered) - len(kept)
