"""Serve-time fold for twin event rows — one game, one card (#4100).

WHAT THIS IS FOR. Alex, on `/sports` at phone width 2026-09-08: page one carried
two adjacent MLB cards for the SAME game — "St. Louis Cardinals 24% / San
Francisco Giants 76%, 0-2, Top 6th" and, five cards later, "St.Louis Cardinals
38% / San Francisco Giants 62%" with no score at all. Two cards, one game, two
different numbers, and the team's own name spelled two ways.

WHY THE ROWS EXIST, AND WHY THIS IS NOT THE MATCHER'S REPAIR. They are two
`events` rows, each minted by a different authority and each anchored to that
authority's own game id — measured on production 2026-09-09 01:xxZ:

    15307210  odds_api:c8513bd1…   espn_id set   betting, espn, mlb, stat_model
    15300848  statpal:baseball_mlb:364…          kalshi, mlb

Ruling 048 (gotcha #32) is why they never merged and why they MUST not be merged
by name and time in the registry: an id-less claim never absorbs, and absorption
needs a SHARED provider id. Neither row shares one — each carries a `game` anchor
from a provider the other has never heard of — so `event_provider_anchors` has
nothing to join on and both rows are, structurally, correct. Loosening absorption
was put to Alex on 2026-08-20 and REJECTED.

So this module does not touch the registry, the matcher, or a single row. It is a
SERVE-TIME fold: the reader's page shows the fixture once, and the surviving card
carries the union of both rows' venues so the number on it is the blend Alex's
standing ruling asks for. The duplicate rows stay in the database exactly as they
are — visible to the Grid and Flow sentinels, to `audit_event_matching.py`, and
to whatever eventually lands #2693 / #4100. Hiding a card is not fixing a bug and
this file does not claim to; it stops the bug reaching a reader while the durable
repair is built.

THE KEY IS DELIBERATELY STRICTER THAN A MATCHER'S. `(sport_id, normalised away,
normalised home, commence MINUTE)`. Two distinct fixtures cannot share it: an MLB
doubleheader is the same teams on the same DAY but never the same minute, and two
different matches between one pair of players at one instant do not exist. A
matcher's helper is permissive on purpose — wrong here — so the key is built from
`strip_diacritics` and an alphanumeric squash rather than from
`normalize_team_name_for_matching`.

WHY NEITHER EXISTING NORMALISER WOULD HAVE FOLDED THE CARD ALEX SAW.
`normalize_team_name` strips a period only when a space follows it
(`re.sub(r"\\.(?=\\s)", …)`), so "St.Louis Cardinals" keeps its period and does
not equal "st louis cardinals". `match_key` keeps spaces, so it yields
"stlouis cardinals" against "st louis cardinals". Both leave the twin unfolded.
The squash below removes every non-alphanumeric character, spaces included, and
both spellings land on `stlouiscardinals`.

## AND WHY A SQUASH IS NOT ENOUGH FOR SOCCER (#5918)

The squash bridges two SPELLINGS of one name. Soccer's duplicates are not
spelled differently — they are NAMED differently, by two providers with two
vocabularies: `PSG` and `Paris Saint-Germain`, `Celta Vigo` and `RC Celta de
Vigo`, `Deportivo` and `Deportivo La Coruña`, `Plzen` and `Viktoria Plzeň`. No
character-level rule reaches those, and `/api/events` was serving both rows of
each pair to a reader on 2026-09-13: La Liga showed Celta–Málaga twice, once
finished 1–1 and once with a green LIVE badge and no price at all.

So one extra pass runs AFTER the strict key has grouped what it can, inside a
`(sport_id)` bucket and within :data:`SOCCER_NAME_FOLD_WINDOW_MINUTES` of stored
kick-off, using the club-name rule the StatPal stamper already trusts
(:func:`app.utils.soccer_team_matching.soccer_pair_matches` — token subset with a
squad-marker refusal, orientation kept). Three properties make that safe to run
on a reader's page, and each is a real constraint rather than a reassurance:

* **It is a PREDICATE, never a key.** Token subset is not transitive: `Madrid` ⊆
  `Real Madrid` and `Madrid` ⊆ `Atlético Madrid` say nothing about the other
  two. A dict key would have silently merged that triple. So the pass unions
  candidate groups and then REFUSES any cluster that is not a clique under the
  predicate — every pair in it must match, not just a chain of them.
* **Soccer only, and the gate is load-bearing.** The subset rule is written for
  a vocabulary where the short name is the same club. College sport is the
  counterexample that would break it — `Texas` ⊆ `Texas State` and `Miami` ⊆
  `Miami (OH)` are *different schools*, and soccer's squad-qualifier guard has
  nothing to say about them. `soccer_team_matching` measured itself on soccer
  boards, so it is used on soccer rows and nowhere else.
* **The survivor is elected exactly as before.** On these pairs the priced row
  and the id-bearing row are DIFFERENT rows — Getafe's ESPN twin carries the
  espn_id and no price, its Odds API twin carries a Kalshi price and no id — so
  the pass hands the merged group to the same :func:`_elect` and the same
  additive source union. Filtering one row out instead (the obvious fix, and
  the one #5918 was filed to refuse) would have deleted the only priced card.

MEASURED ON PRODUCTION 2026-09-13 by driving this function — not a
re-implementation of it — over all 756 soccer rows a reader can reach in
`[now-12h, now+8d]`, with each half switched off in turn:

    #5905 recovery   #5918 name pass   duplicate rows folded
    off              off                2      (master today)
    off              on                 4
    on               off                2
    on               on                 9

**Neither half closes this alone, and the interaction is most of the ship.** Six
of the seven rows this pass newly folds hold a Kalshi *expected expiration*
three hours after the whistle, so they are not in the same minute-bucket as
their twin until #5905 puts the kick-off back — PSG/Brest, PSG/Marseille,
Palmeiras/LDU Quito, Corinthians/Estudiantes, Union Saint-Gilloise/Plzeň. All
nine are on league pages a reader opens; none is in `soccer_other`. No cluster
was refused as a non-clique, and no group the strict key already made changed in
any way.

**The venue union is the reason this merges rather than filters, and production
says so plainly.** Getafe's elected survivor carries NO venues of its own and
gains `betting` and `kalshi` from the twin it absorbs; two more survivors gain a
Kalshi price they would otherwise have lost. Dropping the tagged row instead —
the fix #5918 was filed to refuse — would have served those three cards with no
number on them.

## WHAT THE FIRST SHIP GOT WRONG, FOUND BY CHECKING IT ON PRODUCTION (#5918)

Two things, measured at 19:0xZ–19:3xZ the same day, both by driving this
function over all 800 soccer rows a reader could then reach.

**The minute was too strict, and its own specimen proved it inside forty
minutes.** At 18:30Z Getafe–Deportivo was two rows both stamped `16:30:00Z`; at
19:06Z the Odds API row read `16:32:00Z` and the La Liga page served the
finished match twice — `54% / 46%` on one card, no percentage at all on the one
below it. Two providers, two clocks, and an exact-minute bucket cannot hold
them. Hence :data:`SOCCER_NAME_FOLD_WINDOW_MINUTES`, applied per PAIR inside the
clique rather than as a bucket boundary.

**And this fold was deleting a number.** Of the eighteen rows it folded away,
`15297786` (Brest v Paris Saint-Germain) held
`opening_home_probability = 0.0953` while its elected survivor `15311919` held
none — so that reader got one card instead of two and lost the "Pre-match ·
sportsbooks" percentage in the trade. The sources union cannot reach it: that
percentage is served from the `Event.opening_*` COLUMNS and has never been in
the JSONB bag. :func:`_carry_opening_line` closes it by calling
`merge_opening_line`, the same rule the tag fold uses, rather than restating it.

    window   duplicate rows folded   openings carried
    0m         18                      1   (Brest, the live defect)
    5m         19                      1
    10m        20                      2   (adds Getafe, 0.5439 travels)
    15m        20                      2   (the population plateaus)

No pair inside fifteen minutes was a different fixture, and each window is a
strict superset of the one before it — nothing the exact-minute key already
folded stopped being folded.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable, Optional

from app.utils.kalshi_occurrence_start import (
    _is_orm_instance,
    _loaded_sport_key,
    recover_kalshi_occurrence_starts,
)
from app.utils.name_normalization import strip_diacritics
from app.utils.proven_duplicates import merge_opening_line
from app.utils.soccer_team_matching import soccer_pair_matches

logger = logging.getLogger(__name__)

__all__ = [
    "FoldResult",
    "fold_twin_events",
    "twin_fold_key",
    "twin_identity_rank",
]

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _squash(name: Optional[str]) -> str:
    """Alphanumeric-only, lowercase, diacritic-free form of a team name.

    "St. Louis Cardinals" and "St.Louis Cardinals" both become
    "stlouiscardinals"; "Atlético Madrid" becomes "atleticomadrid".
    """
    if not name:
        return ""
    return _NON_ALNUM.sub("", strip_diacritics(name).lower())


def twin_fold_key(event: Any) -> Optional[tuple]:
    """The key two rows must share to be the same fixture, or ``None``.

    ``None`` means "never fold this row" — a row missing a team name or a
    commence time cannot be proven to be anybody's twin, and the fold's whole
    licence is that the key admits no false positives.

    #5905 — THE MINUTE THIS READS MAY HAVE BEEN RECOVERED BEFORE IT GOT HERE.
    `recover_kalshi_occurrence_starts` runs at the top of :func:`fold_twin_events`
    and corrects the one class of row that holds Kalshi's *expected expiration*
    where a kick-off belongs. This key is unchanged by that — same shape, same
    strictness, still exact minute equality — it simply now sees the instant the
    row's twin already holds instead of one three hours later.
    """
    home = _squash(getattr(event, "home_team_name", None))
    away = _squash(getattr(event, "away_team_name", None))
    commence = getattr(event, "commence_time", None)
    sport_id = getattr(event, "sport_id", None)
    if not home or not away or commence is None or sport_id is None:
        return None
    return (sport_id, away, home, commence.replace(second=0, microsecond=0))


def _source_count(event: Any) -> int:
    sources = getattr(event, "win_probability_sources", None)
    return len(sources) if sources else 0


def twin_identity_rank(event: Any) -> tuple:
    """Sort key for electing the survivor among twins — biggest wins.

    Ordered by what a reader loses if the other row is the one served, NOT by
    row richness. lane1/197 measured that richness points the wrong way in 2 of
    5 pairs, and gotcha "the emptier row heuristic is backwards for Kalshi
    ghosts" is the same lesson from the other side. What does not flip:

    1. **A visible score.** The card Alex saw twice differed in exactly this —
       one said "0-2, Top 6th", the other showed a live game with no score at
       all. Serving the scoreless row would be a worse page than serving two.
    2. **An ESPN id**, then **any provider id**. An anchored row is the one the
       event page, the chart and the settlement path can all reach.
    3. Only then source count, and finally the lower row id, so the election is
       deterministic across requests and the served `id` does not flicker
       between two polls.
    """
    home_score = getattr(event, "home_score", None)
    away_score = getattr(event, "away_score", None)
    has_score = home_score is not None or away_score is not None
    return (
        1 if has_score else 0,
        1 if getattr(event, "espn_id", None) else 0,
        1 if getattr(event, "external_id", None) else 0,
        _source_count(event),
        -(getattr(event, "id", 0) or 0),
    )


@dataclass
class FoldResult:
    """What the fold decided, in a shape a caller can act on and log."""

    events: list = field(default_factory=list)
    """The surviving rows, in the order they arrived."""

    merged_sources: dict = field(default_factory=dict)
    """``{survivor_id: unioned win_probability_sources}`` — survivors only, and
    only where a fold actually added a venue."""

    merged_opening: dict = field(default_factory=dict)
    """``{survivor_id: (home, away)}`` — survivors that gained a pre-match line
    from the row they absorbed, and only those. Unlike
    :attr:`merged_sources`, the fold has ALREADY applied this to the row (see
    :func:`_elect`); this is the record, for the log line and the guard tests."""

    dropped_ids: list = field(default_factory=list)
    """Row ids the fold removed, for the log line and the guard tests."""

    @property
    def folded_count(self) -> int:
        return len(self.dropped_ids)


def fold_twin_events(events: Iterable[Any]) -> FoldResult:
    """Collapse same-fixture rows to one, unioning their venues.

    The union is ADDITIVE ONLY: a source the survivor already reports is never
    overwritten by a twin's reading of it. The survivor's own numbers are the
    ones the rest of the pipeline already trusts; the fold adds the venues that
    were stranded on the other row and nothing else. Draining the other
    direction — electing a winner and discarding the loser's sources — deletes a
    whole venue's price for that game, which is what the "blend is the product"
    ruling forbids.

    #5905 — IT RECOVERS KICK-OFFS FIRST, AND THAT IS NOT ONLY IN SERVICE OF THE
    FOLD. A soccer row whose hour came from Kalshi holds that market's *expected
    expiration*, exactly three hours after the whistle
    (`app/utils/kalshi_occurrence_start.py` carries the venue reads). Correcting
    it here gives every caller of this function — `/api/feed`, `GET /api/events`,
    search, `/api/teams/{identifier}`, `/api/leagues/{sport_key}` — one honest
    hour from one place, which matters most for the 16 of 29 such rows that have
    NO twin and so can never be folded: they are not duplicated, they are simply
    advertised three hours late, and next weekend's Madrid derby is one of them.
    """
    ordered = list(events)

    # Before keying: a corrected row and its twin share a minute, so the strict
    # key below needs no widening to see them as one fixture.
    try:
        recover_kalshi_occurrence_starts(ordered)
    except Exception:  # noqa: BLE001 — gotcha #42; an uncorrected page is today's
        logger.exception("twin fold: kick-off recovery failed; serving stored times")
    groups: dict[tuple, list] = {}
    unkeyed: list = []

    # Gotcha #42 — one bad item must never wipe a scoring pass. This runs on the
    # `/api/feed` hot path above every other stage, so a single row with a
    # surprising `commence_time` type must cost that row its fold, not the whole
    # page. A row that cannot be keyed is a row that cannot be proven a twin,
    # which is already the "leave it alone" branch.
    for event in ordered:
        try:
            key = twin_fold_key(event)
        except Exception:  # noqa: BLE001 — see above; the fallback is inaction
            logger.warning(
                "twin fold: could not key event %s; left unfolded",
                getattr(event, "id", "?"),
                exc_info=True,
            )
            key = None
        if key is None:
            unkeyed.append(event)
            continue
        groups.setdefault(key, []).append(event)

    # #5918 — the strict key has now grouped every pair that SPELLS its clubs the
    # same way. The soccer pass below is the only thing that can reach a pair
    # that NAMES them differently, and it runs on the groups rather than on the
    # rows so that it can never weaken the key for anybody else.
    try:
        grouped = _merge_soccer_name_variants(groups)
    except Exception:  # noqa: BLE001 — gotcha #42; the strict groups are today's
        logger.exception("twin fold: soccer name merge failed; serving strict groups")
        grouped = list(groups.values())

    # Keyed on the PYTHON object, not on `.id`: the fold must survive a caller
    # that hands it two hydrated rows carrying the same primary key, and must
    # never keep a row merely because a sibling elected the same id.
    keep: set[int] = {id(e) for e in unkeyed}
    result = FoldResult()

    for members in grouped:
        if len(members) == 1:
            keep.add(id(members[0]))
            continue

        try:
            _elect(members, keep, result)
        except Exception:  # noqa: BLE001 — one group's failure keeps its rows
            logger.warning(
                "twin fold: election failed for %s; all rows kept",
                [getattr(m, "id", "?") for m in members],
                exc_info=True,
            )
            for member in members:
                keep.add(id(member))

    result.events = [e for e in ordered if id(e) in keep]
    return result


#: How far apart two soccer rows' stored kick-offs may be and still be one
#: fixture. **Measured, and the measurement is why this is not zero.** #5918
#: shipped with an exact-minute bucket and its own specimen walked out of it
#: inside forty minutes: at 18:30Z production held Getafe–Deportivo as
#: `15311881` (ESPN) and `15298080` (Odds API) both at 16:30Z; by 19:06Z the
#: Odds API row read 16:32Z, and the La Liga page served the finished match
#: twice — once with `54% / 46%`, once with no percentage at all.
#:
#: Ten minutes rather than the three observed (2.0 and 5.9) because a constant
#: fitted to the largest reading in one population is the extreme, not the
#: bound. What sizes it is what it must EXCLUDE, and the answer is nothing:
#: the same two clubs do not play a second fixture in the same competition ten
#: minutes after the first, so inside this window the club-name predicate and
#: the clique test are doing all of the work and the clock is doing none. Ten
#: keeps it obviously sub-fixture-scale.
#:
#: Over all 800 production soccer rows a reader could reach on 2026-09-13
#: 19:1xZ, driving :func:`soccer_pair_matches` over every same-sport pair:
#: four pairs at zero minutes apart (what the exact-minute key already saw),
#: one at 2.0 (the La Liga defect above) and two at 5.9 (`Lexington SC` v
#: `Orange County SC`, three rows for one match in `soccer_other`). **No pair
#: inside fifteen minutes was a different fixture** — there was nothing for a
#: tighter window to protect.
SOCCER_NAME_FOLD_WINDOW_MINUTES = 10


def _soccer_bucket_key(key: tuple) -> tuple:
    """`(sport_id,)` — the only thing two twins must share before the pairing.

    The sport is not negotiable and never was. The MINUTE used to be here too,
    and it was doing a job the club-name predicate and the clique test were
    already doing better: see :data:`SOCCER_NAME_FOLD_WINDOW_MINUTES` for the
    live specimen that two providers' clocks pushed out of an exact-minute
    bucket. Time is still a guard — it is just applied per PAIR, where a window
    can be stated, rather than per bucket, where a boundary decides.
    """
    sport_id, _away, _home, _minute = key
    return (sport_id,)


def _within_fold_window(left: tuple, right: tuple) -> bool:
    """Are these two strict keys' kick-offs inside the window, inclusive?

    Applied to every PAIR in a cluster rather than to the cluster's span, for
    the same reason the name predicate is: neither relation is transitive. Rows
    at 0, 8 and 16 minutes chain through the middle one, and a fold that
    followed the chain would serve one card for a pair sixteen minutes apart
    that nothing ever compared. The clique test below asks both questions of
    every pair, so such a cluster is refused whole and all three rows stand.
    """
    delta = abs((left[3] - right[3]).total_seconds())
    return delta <= SOCCER_NAME_FOLD_WINDOW_MINUTES * 60


def _group_representative(members: list) -> Any:
    """The row whose names speak for a group — lowest id, so it never flickers.

    Members of a group share a *squashed* name, not a tokenized one:
    "St.Louis" and "St. Louis" squash alike and tokenize differently. So which
    member answers for the group is a real choice, and it is made the same way
    :func:`twin_identity_rank` breaks its final tie — deterministically, by row
    id — rather than by the order the caller happened to hand us the rows.
    """
    return min(members, key=lambda m: getattr(m, "id", 0) or 0)


def _bucket_sport_key(
    bucket_keys: list[tuple], groups: dict[tuple, list]
) -> Optional[str]:
    """The sport key of a bucket, from the first group that can answer.

    `_loaded_sport_key` answers `None` for a row whose `Event.sport` the caller
    did not load, and that is the safe answer for that ROW. Asking only the
    first group would now let one unloaded row veto a whole sport — the bucket
    is the sport since the window replaced the minute — so the question is put
    to each group in turn until one can answer. Every row in a bucket shares a
    `sport_id`, so any answer is the bucket's answer.
    """
    for key in bucket_keys:
        sport_key = _loaded_sport_key(_group_representative(groups[key]))
        if sport_key:
            return sport_key
    return None


def _merge_soccer_name_variants(groups: dict[tuple, list]) -> list[list]:
    """Merge nearby soccer groups whose club names name the same fixture.

    Returns the groups to elect over, in the order the strict key made them; a
    merged cluster takes the position of its earliest member group. Nothing is
    dropped and nothing is reordered for a sport this does not touch, so a
    caller serving no soccer gets byte-identical behaviour to before #5918.

    THE CLIQUE TEST IS THE SAFETY, AND IT IS NOT BELT-AND-BRACES. Union-find
    over a non-transitive predicate is exactly the bug lane1/281 warned about
    when handing this over: `Madrid` ⊆ `Real Madrid` and `Madrid` ⊆ `Atlético
    Madrid` would chain the two Madrid clubs into one card through a third row
    that matched both. Requiring every pair inside a cluster to match collapses
    that chain back to nothing and leaves all three groups standing. Since the
    bucket became the sport rather than the minute, the clique carries the
    :func:`_within_fold_window` question too — non-transitive for exactly the
    same reason, and refused the same way.
    """
    buckets: dict[tuple, list[tuple]] = {}
    for key in groups:
        buckets.setdefault(_soccer_bucket_key(key), []).append(key)

    merged_into: dict[tuple, tuple] = {}
    for bucket_keys in buckets.values():
        if len(bucket_keys) < 2:
            continue
        sport_key = _bucket_sport_key(bucket_keys, groups)
        if not sport_key or not sport_key.startswith("soccer"):
            # Not soccer, or the caller did not load `Event.sport` — either way
            # this pass has nothing it is licensed to say about these rows.
            continue
        for cluster in _name_clusters(bucket_keys, groups):
            target = cluster[0]
            for other in cluster[1:]:
                merged_into[other] = target

    if not merged_into:
        return list(groups.values())

    out: list[list] = []
    position: dict[tuple, int] = {}
    for key, members in groups.items():
        target = merged_into.get(key, key)
        if target in position:
            out[position[target]].extend(members)
            continue
        position[target] = len(out)
        out.append(list(members))
    return out


@lru_cache(maxsize=4096)
def _pair_matches(left: tuple, right: tuple) -> bool:
    """:func:`soccer_pair_matches`, memoized on the two name pairs.

    Pure in its arguments — it reads two module-level alias tables and nothing
    else — so a cache is a cache and not a stale answer. It is worth having for
    one specific reason: the clique test below re-asks about every pair the
    union-find above has already decided, and the fixtures a dyno serves repeat
    from request to request. Measured, and BOTH regimes are quoted because the
    cold one is what a dyno pays on its first request after a release:

        40 rows, a feed page   +0.47ms cold   +0.03ms warm
        756 rows, all soccer   +5.24ms cold   +0.69ms warm

    4096 entries is comfortable rather than tuned: those 756 rows asked 809
    distinct questions.
    """
    return soccer_pair_matches(left, right)


def _name_clusters(bucket_keys: list[tuple], groups: dict[tuple, list]) -> list[list]:
    """Groups of keys inside one bucket that all pair-match each other.

    Only clusters of two or more are returned, and only cliques: a candidate
    cluster that is merely connected is discarded whole rather than split, so a
    chain never decides which of its links survives. "Pair-match" is BOTH
    questions — the club names name one fixture, and the two kick-offs are
    inside :data:`SOCCER_NAME_FOLD_WINDOW_MINUTES` of each other.
    """
    pairs: dict[tuple, tuple] = {}
    for key in bucket_keys:
        rep = _group_representative(groups[key])
        pairs[key] = (
            getattr(rep, "home_team_name", None),
            getattr(rep, "away_team_name", None),
        )

    parent = {key: key for key in bucket_keys}

    def find(key: tuple) -> tuple:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def joined(left: tuple, right: tuple) -> bool:
        return _within_fold_window(left, right) and _pair_matches(
            pairs[left], pairs[right]
        )

    for i, left in enumerate(bucket_keys):
        for right in bucket_keys[i + 1 :]:
            if joined(left, right):
                parent[find(left)] = find(right)

    clusters: dict[tuple, list] = {}
    for key in bucket_keys:
        clusters.setdefault(find(key), []).append(key)

    out: list[list] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        if all(
            joined(left, right)
            for i, left in enumerate(members)
            for right in members[i + 1 :]
        ):
            out.append(members)
        else:
            logger.info(
                "twin fold: refused a non-clique soccer cluster %s",
                [(pairs[key], key[3].isoformat()) for key in members],
            )
    return out


def _set_served_value(event: Any, column: str, value: Any) -> None:
    """Place a served reading on a row without making it a pending write.

    The same two arms, for the same reason, as
    `kalshi_occurrence_start._set_served_commence_time`, whose docstring carries
    the full argument: an ORM row takes `set_committed_value` so it is never
    marked dirty and no later flush can persist a serve-time reading into
    `events`; anything else — a test double, a detached object — takes a plain
    assignment, because `set_committed_value` needs instance state it has not
    got. Getting the arms backwards is what turns "we read this differently"
    into "we wrote this down".
    """
    if _is_orm_instance(event):
        from sqlalchemy.orm.attributes import set_committed_value

        set_committed_value(event, column, value)
        return
    setattr(event, column, value)


def _elect(members: list, keep: set, result: "FoldResult") -> None:
    """Pick the survivor for one group and union the losers' venues onto it."""
    ranked = sorted(members, key=twin_identity_rank, reverse=True)
    survivor, losers = ranked[0], ranked[1:]
    keep.add(id(survivor))
    result.dropped_ids.extend(loser.id for loser in losers)

    merged = dict(getattr(survivor, "win_probability_sources", None) or {})
    added = False
    for loser in losers:
        for name, reading in (
            getattr(loser, "win_probability_sources", None) or {}
        ).items():
            if name not in merged:
                merged[name] = reading
                added = True
    if added:
        result.merged_sources[survivor.id] = merged

    _carry_opening_line(survivor, losers, result)


def _carry_opening_line(survivor: Any, losers: list, result: "FoldResult") -> None:
    """Give the survivor the pre-match line only an absorbed row held. #5853.

    🔴 WITHOUT THIS, THIS FOLD DELETES A NUMBER, AND IT WAS DOING SO ON
    PRODUCTION. Measured 2026-09-13 19:3xZ by driving :func:`fold_twin_events`
    over all 800 soccer rows a reader could reach: of the eighteen rows it
    folded away, Brest v Paris Saint-Germain's `15297786` held
    `opening_home_probability = 0.0953` and the survivor it was folded into,
    `15311919`, holds none. The reader got one card instead of two and lost the
    "Pre-match · sportsbooks" percentage in the trade. That is precisely the
    regression #5918 was filed to refuse, arriving by way of its own fix.

    The sources union above cannot reach it: on a SETTLED or pre-match card the
    printed percentage comes from the `Event.opening_*` COLUMNS, which have
    never been in the JSONB bag (`merge_opening_line`'s own docstring carries
    the Bundesliga measurement that established this).

    ONE RULE, NOT A SECOND COPY OF IT. The tag fold answered this question
    first, in :func:`app.utils.proven_duplicates.merge_opening_line`, and its
    three clauses are load-bearing — both halves absent before anything is
    filled, a pair travels as a pair, twins consumed in ascending id order so a
    card cannot flicker between two readings. Restating them here is how the
    two rules drift apart, so the function is called rather than imitated.
    Orientation, which that rule requires of its caller, holds by construction
    here: the strict key is built from `(away, home)`, and the soccer name pass
    uses :func:`soccer_pair_matches`, which matches home to home and refuses the
    swap on purpose.

    APPLIED TO THE ROW, unlike :attr:`FoldResult.merged_sources`, which every
    caller applies itself. Both shapes exist in this pipeline already —
    `recover_kalshi_occurrence_starts` writes the corrected kick-off onto the
    row from inside this same function — and the row is the right place for
    this one: six call sites in four route files consume this fold, and a
    number that only arrives when a caller remembers to ask for it is a number
    that will be missing from the fifth surface somebody adds. The write goes
    through :func:`_set_served_value`, whose two arms are the safety argument
    (gotcha #4): `set_committed_value` on an ORM row, so no later flush can
    persist a served reading back into `events`.
    """
    if not losers:
        return
    own_home = getattr(survivor, "opening_home_probability", None)
    home, away = merge_opening_line(
        own_home,
        getattr(survivor, "opening_away_probability", None),
        [
            (
                loser.id,
                getattr(loser, "opening_home_probability", None),
                getattr(loser, "opening_away_probability", None),
            )
            for loser in losers
        ],
    )
    if home is own_home:
        return

    result.merged_opening[survivor.id] = (home, away)
    _set_served_value(survivor, "opening_home_probability", home)
    _set_served_value(survivor, "opening_away_probability", away)
