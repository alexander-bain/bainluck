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

AMENDED #7700 — THE ONE LEAGUE-SPORT PAIR THAT IS NOT SYMMETRIC. Everything
above stands, including the refusal to guess between two rows that differ in
nothing. A second, separate pass handles the one league-sport shape where the
two rows are NOT interchangeable: when one wears a season-variant sport key
(`icehockey_nhl_preseason`) and the other its parent league's
(`icehockey_nhl`), `sport_keys.league_identity` already rules those are one
league, and the asymmetry is readable off the row rather than guessed. That
pass has its own bound (30 minutes, the same-fixture separation, not 36 hours),
its own grouping (full names, not surnames) and its own survivor rule; it never
fires on two rows that share a sport key, so none of the MLB pairs above move.
See `SAME_FIXTURE_MAX_SEPARATION_MINUTES`.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Iterable

from app.utils.event_completion import (
    KALSHI_OCCURRENCE_COMMENCE_SOURCE,
    POLYMARKET_VENUE_COMMENCE_SOURCE,
    TICKER_DERIVED_COMMENCE_SOURCE,
    commence_time_is_a_reported_start,
)
from app.utils.provider_anchor_keys import SOURCE_KALSHI, SOURCE_POLYMARKET
from app.utils.sport_keys import is_season_variant, league_identity

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


# #8430 — AN EMPTY MARKET-BORN ROW NEVER HIDES THE PRICED ONE, AND GOES ITSELF.
#
# The dominance pass below prefers the FULLER NAME, which is right for the
# #2623 population (the tournament row names "Aryna Sabalenka", the ghost only
# "Sabalenka", and the ghost is the one with nothing behind it). It is exactly
# backwards when the fuller-named row is itself a ghost. Measured on production
# 2026-09-24 ~21:00Z, `/api/events/search?q=Boyer` served ONE game row:
#
#     15317846  Tristan Boyer v Sebastian Gorzny  polymarket_venue  no price, 0 markets
#
# while the match's two priced rows were both dropped by it for being
# surname-only:
#
#     15317904  Boyer v Gorzny  polymarket_venue  Polymarket 75%, 14 markets
#     15318254  Boyer v Gorzny  kalshi            Kalshi 99%
#
# 15317846 is one of twelve empty rows an hourly Polymarket poll minted for the
# match (the creator is fixed in the same ship). A reader who searched the
# player got "No price yet" for a match two venues were pricing.
#
# So two clauses, both narrow:
#
# 1. A row that is market-born AND carries nothing a card prints — no price,
#    no score, no result — may not dominate a row that carries a price. It
#    would hide the only copy with a number on it.
# 2. That same empty row is dropped when a priced row for the same two
#    participants survives on the page inside the window. Its card could only
#    ever say "No price yet" beside the card that has the price.
#
# Scoped to MARKET-BORN rows on purpose. A schedule row (odds_api, espn,
# statpal) is where the tournament chip, the avatars and eventually the score
# live; clause 2 never hides one, however empty, so the #2623 shape — a priced
# Kalshi ghost beside a not-yet-priced tournament row — collapses exactly as
# before. Nothing is written: the empty row keeps its id and its page, and when
# the event graph drains it this pass simply stops finding it.
#
# The set mirrors `anchor_channel.MARKET_BORN_COMMENCE_SOURCES` (Q050's drain
# clause), built from the same utils constants rather than imported, because a
# utils module must not import a service. `tests/test_search_empty_ghost_never_
# hides_the_priced_row_8430.py` asserts the two agree.
MARKET_BORN_COMMENCE_SOURCES: frozenset = frozenset(
    {
        SOURCE_KALSHI,
        SOURCE_POLYMARKET,
        TICKER_DERIVED_COMMENCE_SOURCE,
        KALSHI_OCCURRENCE_COMMENCE_SOURCE,
        POLYMARKET_VENUE_COMMENCE_SOURCE,
    }
)


def is_individual_sport(sport_key: Any) -> bool:
    if not sport_key:
        return False
    return str(sport_key).startswith(INDIVIDUAL_SPORT_PREFIXES)


# #7700 — the SEASON-VARIANT pair, which is the one league-sport shape where a
# survivor CAN be picked, and the reason the dominance pass above cannot do it.
#
# The rejection this sits beside is real and stands: two equally specific,
# equally scored rows in the SAME sport key (the byte-identical Angels–Yankees
# pair, the `St. Louis`/`St.Louis` pair) offer no grounds to prefer either, and
# search must not guess. What makes the variant pair different is that the two
# rows are not symmetric — one of them wears `<league>_preseason`, which
# `sport_keys.league_identity` already rules is the SAME league as its parent
# (#1798, #4945). That is an asymmetry the renderer can read off the row.
#
# Measured on production 2026-09-21, the whole NHL preseason is this shape —
# every one of the 12 `icehockey_nhl_preseason` rows in a three-day window pairs
# with an `icehockey_nhl` row for the same game, and `kraken` returns both, both
# `completed`, both 4-2, eight minutes apart, adjacent on page one. The ESPN-born
# parent row holds the anchor and ZERO markets; the Odds-API-born variant row
# holds 3 markets and 177–301 odds snapshots. So the reader is shown the game
# twice and the copy labelled plainly "NHL" is the one with nothing behind it.
#
# Per-sport-key shape, same window, same read: `americanfootball_nfl` 14/14 rows
# carry BOTH provider ids, `baseball_mlb` 40/42, `americanfootball_ncaaf` 72/74 —
# one row per game. `icehockey_nhl` reads 18 espn-only and the variant key 12
# odds-only. The split key is the whole difference.
#
# This is NOT the drain and does not pretend to be: neither row absorbs the
# other, nothing is deleted, and when the event graph finally joins them this
# pass simply stops finding pairs (#2693, ruling 048's `ANCHORED_TWIN_UNSEEN`).
SAME_FIXTURE_MAX_SEPARATION_MINUTES = 30

#: Why 30 minutes and not the 36h window above: the wide window is for a GHOST
#: whose start time is a provider stand-in, and it is safe there only because
#: the pass is scoped to sports where the same two participants do not meet
#: twice. League sport meets the same opponent on consecutive days as routine,
#: so the bound here has to be the one that separates a twin from a real second
#: fixture. `event_registry._SAME_FIXTURE_MAX_SEPARATION` is that bound, argued
#: from the schedule rather than from taste (no format starts two same-pair
#: fixtures within half an hour) and guarded there by a doubleheader test. The
#: value is duplicated rather than imported because a utils module must not
#: import a service; `tests/test_search_fixture_dedup.py` asserts the two agree,
#: so the copy cannot drift silently — the same contract the individual-sport
#: prefix list above already lives under.


def _season_variant_pair(a: "_Row", b: "_Row") -> bool:
    """True when one row wears a season-variant key and the other its parent's.

    This is the ONLY clause here: that the two rows name the same league is
    already carried by the group key, and a second copy of that test inside this
    function is unreachable — mutation-verified, 2026-09-21, by replacing the
    body with `return True` and watching every guard stay green. A redundant
    check that no test can distinguish reads as protection and is not, so it is
    gone rather than guarded.

    Both directions of the asymmetry are required: two variant rows, or two
    parent rows, are the symmetric case this pass deliberately leaves alone.
    """
    return is_season_variant(a.sport_key) != is_season_variant(b.sport_key)


#: The statuses this pass will act on. A game IN PROGRESS is excluded, and that
#: exclusion was MEASURED rather than reasoned: replaying the pass over 548
#: served search rows on 2026-09-21 found three live pairs, and in one of them
#: — Rangers at Devils, 23:00Z — the ESPN-anchored parent read 1-2 while the
#: variant row read 0-1 at the same instant. The parent is the faster score rail
#: during play. So while a game is live the asymmetry this pass CAN read (the
#: label, and which row carries the prices) is outranked by one it CANNOT (which
#: row's score is current), and hiding either copy would sometimes hide the true
#: score. A live twin therefore stays double and belongs to the event graph
#: (#2693) like every other shape this module refuses.
#:
#: Completed pairs agreed on the score in every measured case — 7 of 7 on the
#: 2026-09-20 slate — which is why the Final, the case #7700 was filed for, is
#: safe to collapse.
_COLLAPSIBLE_STATUSES: frozenset = frozenset({"scheduled", "completed", "closed"})


def _variant_survivor_rank(row: "_Row") -> tuple:
    """Higher wins, and the two members of a variant pair can never tie.

    The result comes first because a row that reports the score is strictly more
    use to a reader than one that does not — that ordering is the existing
    dominance rule's, unchanged.

    The variant breaks the remaining tie, and the direction is deliberate.
    `sport_keys.is_season_variant` tells callers choosing one row per league to
    prefer the PARENT, but its reason is about TEAM rows (`standings_data` lives
    on the parent club), which is a different question from which EVENT row to
    render. Here the variant row is the one whose label is true — a September
    exhibition is not an NHL regular-season game (#7051 is the same complaint
    from the other side) — and, measured, it is also the row carrying the prices.
    """
    return (1 if row.scored else 0, 1 if is_season_variant(row.sport_key) else 0)


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
        "derived_start", "status", "priced", "empty_ghost",
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
        self.status = getattr(obj, "status", None)
        self.sport_key = sport_key
        # #8430. `win_probability_sources` is what a card's number is read
        # from, so "priced" is exactly "the card has something to print". An
        # empty dict (`{}`) is as unpriced as NULL.
        self.priced = bool(getattr(obj, "win_probability_sources", None))
        # Any one score or a `completed_at` is truth the reader would lose, so
        # this is deliberately looser than `scored` (which wants both halves).
        carries_truth = (
            getattr(obj, "home_score", None) is not None
            or getattr(obj, "away_score", None) is not None
            or getattr(obj, "completed_at", None) is not None
        )
        self.empty_ghost = (
            getattr(obj, "commence_time_source", None) in MARKET_BORN_COMMENCE_SOURCES
            and not carries_truth
            and not self.priced
        )

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
    # #8430 clause 1: an empty market-born row never hides the priced copy.
    if richer.empty_ghost and poorer.priced:
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


def _same_participants(ghost: _Row, keeper: _Row) -> bool:
    """The ghost names the keeper's two participants, at least as fully.

    Directional on purpose: the other direction (a short-named ghost beside a
    fuller-named priced row) never reaches this — the dominance pass already
    drops that ghost for the fuller name. The whole-word suffix rule is the
    dominance test's own, so "Wang" still never pairs with "Huang".
    """
    return any(
        all(_slot_at_least_as_specific(g, k)[0] for g, k in slots)
        for slots in (
            ((ghost.home, keeper.home), (ghost.away, keeper.away)),
            ((ghost.home, keeper.away), (ghost.away, keeper.home)),
        )
    )


def _empty_ghost_ids(groups: dict, dropped: set) -> None:
    """#8430 clause 2: drop an empty market-born row beside a surviving priced one.

    Runs AFTER the dominance pass, over its survivors only, so a priced row that
    was itself dominated (by a scored row, say) cannot be the reason a ghost
    goes — the page keeps whatever the dominance pass decided it would print,
    minus cards that could only say "No price yet" beside a card with a price.
    """
    for group in groups.values():
        priced = [r for r in group if r.priced and r.id not in dropped]
        if not priced:
            continue
        for ghost in group:
            if not ghost.empty_ghost:
                continue
            if any(
                _within_window(ghost, keeper) and _same_participants(ghost, keeper)
                for keeper in priced
            ):
                dropped.add(ghost.id)


def _season_variant_duplicate_ids(rows: list["_Row"], dropped: set) -> None:
    """#7700: add the losing half of every season-variant pair to `dropped`.

    Grouped on the LEAGUE (so `icehockey_nhl_preseason` and `icehockey_nhl` land
    together) and on both participants' FULL normalized names — not the surname
    the ghost pass uses, because in league sport the surname is the city and
    "Seattle Kraken" against "Seattle Storm" must never group.
    """
    groups: dict[tuple, list[_Row]] = {}
    for row in rows:
        if row.id is None or row.commence_time is None:
            continue
        # An unknown status is not collapsible either: this pass only ever
        # HIDES, so the safe direction for anything it does not recognise is to
        # render both rows.
        if row.status not in _COLLAPSIBLE_STATUSES:
            continue
        home, away = _normalize_name(row.home), _normalize_name(row.away)
        if not home or not away:
            continue
        identity = league_identity(row.sport_key)
        if not identity:
            continue
        groups.setdefault((identity, frozenset((home, away))), []).append(row)

    for group in groups.values():
        if len(group) < 2:
            continue
        # Richest first, then by id, so the pass is order-independent for the
        # same reason the dominance pass is: the caller's page order must not
        # decide which row survives.
        group.sort(key=lambda r: (_variant_survivor_rank(r), r.id), reverse=True)
        for index, poorer in enumerate(group):
            if poorer.id in dropped:
                continue
            for richer in group[:index]:
                if richer.id in dropped:
                    continue
                if not _season_variant_pair(richer, poorer):
                    continue
                if not _within_same_fixture_separation(richer, poorer):
                    continue
                # No rank comparison here, and that is not an omission. The sort
                # above puts `richer` first, and the asymmetry gate means the two
                # members of a pair can never hold the same rank (they differ in
                # the variant component by construction), so `richer` outranks
                # `poorer` STRICTLY for every pair that reaches this line. A
                # re-check was written, and mutation testing showed no guard
                # could tell it from `pass` — unreachable protection reads as
                # protection, so it is gone rather than kept for comfort.
                dropped.add(poorer.id)
                break


def _within_same_fixture_separation(a: "_Row", b: "_Row") -> bool:
    if a.commence_time is None or b.commence_time is None:
        return False
    try:
        delta = abs((a.commence_time - b.commence_time).total_seconds())
    except TypeError:
        # Naive minus aware — see `_within_window`. Unknown gap => not a twin.
        return False
    return delta <= SAME_FIXTURE_MAX_SEPARATION_MINUTES * 60


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

    _empty_ghost_ids(groups, dropped)
    _season_variant_duplicate_ids(rows, dropped)
    return dropped


def collapse_duplicate_fixtures(events: Iterable[Any]) -> tuple[list, int]:
    """`(kept, dropped_count)`, preserving the caller's ordering exactly."""
    ordered = list(events)
    dropped = duplicate_fixture_event_ids(ordered)
    if not dropped:
        return ordered, 0
    kept = [e for e in ordered if getattr(e, "id", None) not in dropped]
    return kept, len(ordered) - len(kept)
