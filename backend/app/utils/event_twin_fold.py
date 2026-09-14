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

THE KEY IS DELIBERATELY STRICTER THAN A MATCHER'S. `(league, normalised away,
normalised home, commence MINUTE)` — the league because `sport_id` is not one
(#2866: `americanfootball_nfl` and `americanfootball_nfl_preseason` are two rows
for one competition, and every August this fold was blind to 47 duplicate NFL
cards because of it). Two distinct fixtures cannot share it: an MLB
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
`(sport_id, commence DATE)` candidate bucket, using the club-name rule the
StatPal stamper already trusts
(:func:`app.utils.soccer_team_matching.soccer_pair_matches` — token subset with a
squad-marker refusal, orientation kept) AND a bound on how far apart two
providers may put one kick-off (:data:`SOCCER_KICKOFF_DRIFT`). Both halves are
asked about the pair in hand, not about the bucket: #5964 moved the clock test
out of the bucket after La Liga served Getafe–Deportivo twice, ESPN storing the
kick-off at 16:30Z and the Odds API at 16:32Z, which put one fixture in two
minute-buckets and meant the name question was never asked at all. Four
properties make that safe to run on a reader's page, and each is a real
constraint rather than a reassurance:

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
* **The clock is a BOUND, not an equality, and it is tight** (#5964). Five
  minutes is provider rounding; it is not a schedule. Everything further apart
  belongs to somebody else and is still refused here — the 30-minute re-mints
  #5918 excluded on purpose, and the three-hour Kalshi rows #5905 corrects
  upstream of this function. The bound is enforced pairwise, so it cannot be
  walked around by chaining rows five minutes at a time.

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

RE-MEASURED FOR #5964 the same way, later the same day, over all 1,503 soccer
rows in `[now-3d, now+8d]`, folding each league page the way a reader meets it:

    master                46 rows served twice, of which 40 folded
    with the drift bound  46 folded, 0 unfolded that master folded

The six it adds are the Getafe pair on La Liga and five identical-name pairs in
`soccer_other` three to four minutes apart. Two objective false-fold tests over
all 34 surviving groups: no group holds two different `espn_id`s, and no group
holds two different scorelines — either would mean two real games merged into
one card. The naive version of this change (make the bucket a day and let the
names decide) folded 226 instead of 46, and is what the drift bound exists to
refuse.

## AND WHY A LEAGUE ELEMENT IS NOT ENOUGH EITHER (#2866, rung two)

Making element 0 the LEAGUE closed the 47 NFL preseason pairs, and it cannot
close a pair whose two rows name two leagues that are genuinely different keys —
which is what `soccer_other` is. `league_identity` falls back to an unmapped key
ITSELF, precisely so it never splits a group, so `soccer_other` and
`soccer_netherlands_eredivisie` stay apart and Ajax v Willem II drew two cards on
2026-09-14 with everything else about the two rows already identical.
:func:`_merge_catchall_leagues` is the third and last pass: a row whose league is
simply unmapped folds into the row that names one, guarded by the SPORT (65 of
the 73 candidate pairs in the table are cross-sport and every one of them must
stay two cards). Its docstring carries the census and the refusals.

**The venue union is the reason this merges rather than filters, and production
says so plainly.** Getafe's elected survivor carries NO venues of its own and
gains `betting` and `kalshi` from the twin it absorbs; two more survivors gain a
Kalshi price they would otherwise have lost. Dropping the tagged row instead —
the fix #5918 was filed to refuse — would have served those three cards with no
number on them.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from functools import lru_cache
from typing import Any, Iterable, Optional

from app.utils.kalshi_occurrence_start import (
    _is_orm_instance,
    loaded_sport_key,
    recover_kalshi_occurrence_starts,
)
from app.utils.name_normalization import strip_diacritics
from app.utils.proven_duplicates import merge_opening_line
from app.utils.soccer_team_matching import club_alias_tokens, soccer_pair_matches
from app.utils.sport_keys import league_identity

logger = logging.getLogger(__name__)

__all__ = [
    "FoldResult",
    "fold_twin_events",
    "is_kalshi_date_only",
    "twin_fold_key",
    "twin_identity_rank",
]

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

SOCCER_KICKOFF_DRIFT = timedelta(minutes=5)
"""How far apart two providers may put ONE soccer kick-off and still be folded.

#5964. This is a bound on provider disagreement, not on scheduling: two rows
this far apart are one fixture recorded twice, never two fixtures. It is the
clock half of the soccer pass's licence, and it is deliberately far below the
two populations either side of it.

MEASURED, and the reading that sets it is quoted rather than the round number.
Over the 1,503 soccer rows a reader could reach on 2026-09-13 (`[now-3d,
now+8d]`), driving this module's own predicate over every pair in a competition:

    drift on a LEAGUE page a reader opens   0 min (name variants), 2 min
    drift only in `soccer_other`            3, 5, 8, 9, 14, 15, 16, 21, 24 min
    the 30-minute re-mint class             30 and 31 min   (#5918 excluded it)
    the Kalshi expected-expiration class    180 min         (#5905 corrects it)

The only sub-30-minute disagreement reaching a reader's league page was the
2-minute Getafe pair, so 5 minutes is that reading plus margin — chosen to sit
in the empty band between the defect and the nearest population somebody else
owns, so that widening it later is a decision and not an accident. n is small
and the constant is a ceiling on a rounding artifact, so it is sized to be
obviously clear of its neighbours rather than fitted to its one specimen.

Chaining is not a way around it: the clique refusal below requires EVERY pair in
a cluster to pass, so rows at 0, 4 and 8 minutes do not become one fixture by
standing next to each other.
"""


def _squash(name: Optional[str]) -> str:
    """Alphanumeric-only, lowercase, diacritic-free form of a team name.

    "St. Louis Cardinals" and "St.Louis Cardinals" both become
    "stlouiscardinals"; "Atlético Madrid" becomes "atleticomadrid".
    """
    if not name:
        return ""
    return _NON_ALNUM.sub("", strip_diacritics(name).lower())


KALSHI_DATE_ONLY_SOURCE = "kalshi_ticker"
"""The `commence_time_source` that means "this time came out of a ticker".

A Kalshi ticker encodes a DATE and no hour (gotcha #14), so a row stamped with
this source and sitting at exactly midnight UTC never learned when its fixture
kicks off. Deliberately not `kalshi`: that source is the market's own
`close_time`, which is a real instant even when it is wrong, and three
`soccer_other` rows carried it at midnight on 2026-09-13 with no evidence either
way. This one names the ticker in its own value.
"""


def is_kalshi_date_only(event: Any) -> bool:
    """True when a row asserts a fixture's DATE and no kick-off hour.

    #6007. Both halves are required and each carries its own weight: the source
    says where the time came from, and midnight-UTC is the fingerprint that no
    hour was ever recovered on top of it. A `kalshi_ticker` row that has since
    been given a real hour — by `recover_kalshi_occurrence_starts`, by a later
    poll, by anything — stops being date-only the moment it has one, which is
    the behaviour we want: the exception below exists for rows with no clock,
    not for rows whose clock we dislike.

    THE MIDNIGHT TEST IS ALSO AN INVARIANT THE CALLER RELIES ON.
    :func:`_name_clusters` walks its bucket in time order and breaks out of the
    inner loop past the drift bound; it is safe to exempt a dateless group from
    that break *only* because a dateless group is pinned to 00:00 and therefore
    sorts first in its day. Loosen this predicate to admit some other hour and
    that reasoning silently stops holding.

    Measured on production 2026-09-13: 13 soccer rows in `[now-3d, now+8d]`, of
    which 10 sat beside a completed, ESPN-anchored row for the same fixture on
    the same day — a finished card and a phantom "upcoming" one, side by side.
    """
    if getattr(event, "commence_time_source", None) != KALSHI_DATE_ONLY_SOURCE:
        return False
    commence = getattr(event, "commence_time", None)
    if commence is None:
        return False
    try:
        return (
            commence.hour == 0
            and commence.minute == 0
            and commence.second == 0
            and commence.microsecond == 0
        )
    except AttributeError:  # gotcha #42 — a surprising type costs this row only
        return False


def _league_identities(events: Iterable[Any]) -> dict:
    """``{sport_id: league identity}`` for every row whose sport is in memory. #2866.

    Built once per fold and handed to :func:`twin_fold_key` so that element 0 of
    the key is a property of the SPORT ROW rather than of the individual event
    object. Without it the key would answer `football/nfl` for a row whose
    `Event.sport` a caller happened to eager-load and `1` for a row in the same
    league that a different query in the same request did not — two values for
    one league, and a pair that folds on master today would stop folding. With
    it, two rows sharing a `sport_id` can never disagree about element 0, so
    this change can only ever MERGE groups the old key made and never SPLIT one.

    Only rows that answer are recorded: :func:`loaded_sport_key` returns `None`
    for an unloaded relationship rather than emitting IO (gotcha #42), and a
    `sport_id` no row in the batch could name is simply absent from the map,
    which lands on the `sport_id` fallback — master's behaviour exactly.
    """
    identities: dict = {}
    for event in events:
        sport_id = getattr(event, "sport_id", None)
        if sport_id is None or sport_id in identities:
            continue
        identity = league_identity(loaded_sport_key(event))
        if identity:
            identities[sport_id] = identity
    return identities


def twin_fold_key(event: Any, identities: Optional[dict] = None) -> Optional[tuple]:
    """The key two rows must share to be the same fixture, or ``None``.

    ``None`` means "never fold this row" — a row missing a team name or a
    commence time cannot be proven to be anybody's twin, and the fold's whole
    licence is that the key admits no false positives.

    #2866 — ELEMENT 0 IS THE LEAGUE, NOT `sport_id`, AND THAT IS A REPAIR RATHER
    THAN A RELAXATION. `sport_id` is not a league: `americanfootball_nfl` and
    `americanfootball_nfl_preseason` are two `sports` rows for one competition
    (#1798), so every August the Chiefs–Seahawks preseason game exists once
    under each and this key put the two rows in different groups. Measured on
    production 2026-09-14: `bainluck.com/search?q=Chiefs` returned three such
    pairs adjacent on ONE 390px screen, same date, same `9–9` / `16–15` /
    `12–20` scores, one card labelled NFL and one NFL PRESEASON (authority/196
    on #2866; the fold was returning `dropped_ids: []` for all of them).

    :func:`app.utils.sport_keys.league_identity` is the repo's existing answer to
    "which league is this key", built for #1798/#4945, and it only ever collapses
    keys the map or a season suffix already says are one league — an unmapped key
    falls back to itself, and `sports.key` is UNIQUE, so an unknown key stays
    exactly as discriminating as `sport_id` was.

    THE WIDENING WAS MEASURED, NOT REASONED ABOUT (production, 2026-09-14).
    Of every pair of rows in the table sharing both squashed club names and the
    same minute across two different `sport_id`s — 1,085 fixtures in 90 days,
    32 key combinations — exactly ONE combination collapses under
    `league_identity`: `americanfootball_nfl | americanfootball_nfl_preseason`,
    47 fixtures, 2026-08-07 → 2026-08-29. The other 31 combinations (1,038
    fixtures, overwhelmingly `*_other` catch-all keys pairing rows from genuinely
    different sports) key exactly as they do today. Over ALL time and every
    season-variant family in the `sports` table — the only ones that can collapse
    are `*_preseason`, `*_summer_league` and `mma_mixed_martial_arts` — the total
    is 48: those 47 plus one MLB pair on 2026-05-23 (`14787332` / `9016349`,
    both `4–9`). No soccer key collapses at all, so every soccer bucket below
    holds exactly the rows it held before this change.

    TWO FALSE-FOLD CONTROLS OVER THE 47, both objective and both clean: no group
    holds two different scorelines and no group holds two different `espn_id`s —
    either would mean two real games merged onto one card. Every group is exactly
    two rows with exactly one ESPN-anchored row, so :func:`twin_identity_rank`
    elects the anchored row on all 47.

    A DOUBLEHEADER IS NOT REACHED BY THIS, and that is the key's own strictness
    rather than a promise: element 3 is still exact-minute equality, so two real
    games between one pair on one day remain two groups. Nothing about the clock
    moves here.

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
    # The batch map first (it is the one answer every row of this `sport_id`
    # gets), then this row's own sport for a standalone caller such as
    # `league_futures._twin_key_or_none`, then `sport_id` — never a constant,
    # which would equate every league whose sport a caller did not load.
    league = (identities or {}).get(sport_id) or league_identity(
        loaded_sport_key(event)
    )
    return (
        league or sport_id,
        away,
        home,
        commence.replace(second=0, microsecond=0),
    )


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
    3. Only then source count, then a row that NAMES ITS LEAGUE over a `*_other`
       catch-all, and finally the lower row id, so the election is deterministic
       across requests and the served `id` does not flicker between two polls.

    #2866 — WHY THE CATCH-ALL CRITERION SITS SECOND-TO-LAST, AND WHY IT IS
    INERT EVERYWHERE EXCEPT THE GROUPS :func:`_merge_catchall_leagues` MAKES.
    The survivor's row is the one whose `sport` labels the card and decides
    which league page it can be filtered onto, so a group that ties on
    everything above would otherwise hand the card to whichever row happened to
    have the lower id and serve a correct fixture that has forgotten its
    competition. Measured on 2026-09-14, the three `esports_other × esports`
    pairs are exactly that: `14977192`/`15170329`, `14978751`/`15169745` and
    `14986830`/`15169671` carry no score, no `espn_id`, no provider id and no
    venues on either side, and the catch-all row won all three on row id alone.
    They now elect the row that names its league.

    THE WORLD CUP PAIRS ARE THE CASE WHERE THIS CRITERION CORRECTLY DOES NOT
    FIRE, and they are worth recording so nobody promotes it later. In
    `15168069`/`14900527` (AUS v TUR) and `15168074`/`14900526` (CAN v BIH) the
    `soccer_other` row is the one holding a Polymarket price and the
    `soccer_fifa_world_cup` row has no venues at all, so source count decides
    one rung higher and the catch-all row survives. That is the ordering
    working: a reader keeps the number and loses a label, never the reverse.

    It cannot reach any OTHER group, and that is provable rather than hoped
    for: before this pass every member of a group shares element 0 of the
    strict key, which is `league_identity(sport_key)`; `sports.key` is UNIQUE
    and an unmapped key is its own identity, so two rows can share an identity
    while spelling their keys differently only through `SPORT_LEAGUE_MAP` —
    and `aussierules_other` is the ONLY catch-all that map rewrites, with no
    non-catch-all key sharing its value. So a pre-existing group is all
    catch-all or none, the criterion ties, and nothing moves.

    THE SECOND CALLER WAS CHECKED, NOT ASSUMED. This function is not private to
    the fold: `tasks/reconcile_shared_fixture_ids.py` elects a canonical row
    with it and that task COMMITS, so a new tuple element there is a write-path
    change rather than a serve-time one. Measured on production 2026-09-14 —
    of every group of rows sharing a `statpal_fixture_id`, the number holding
    both a `*_other` key and a real-league key is ZERO, so the criterion cannot
    reach a tag that task writes. Were such a group ever to appear, this points
    the same way there as here: the canonical row is the one that names its
    league.

    A row whose `sport` a caller did not load reads as naming its league, which
    is the harmless answer rather than the correct-in-principle one: the only
    way it meets a row we CAN see is inside a pre-existing group, where both
    share a `sport_id` and therefore the same league, so serving the unseen row
    instead serves a card with an identical label.

    It is placed BELOW source count deliberately. Everything above it is
    something a reader loses outright — a score, an anchor, a venue's price —
    whereas this only decides which of two equally-informative rows gets to
    keep its league label.
    """
    home_score = getattr(event, "home_score", None)
    away_score = getattr(event, "away_score", None)
    has_score = home_score is not None or away_score is not None
    names_league = _catchall_sport_prefix(loaded_sport_key(event)) is None
    return (
        1 if has_score else 0,
        1 if getattr(event, "espn_id", None) else 0,
        1 if getattr(event, "external_id", None) else 0,
        _source_count(event),
        1 if names_league else 0,
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

    dropped_ids: list = field(default_factory=list)
    """Row ids the fold removed, for the log line and the guard tests."""

    survivor_of: dict = field(default_factory=dict)
    """``{dropped_id: survivor_id}`` — which row absorbed each row that went.

    :attr:`dropped_ids` says a row lost. This says what it lost TO, and a caller
    serving more than one rail needs the difference: "this contest is still on
    the page, correctly" is a claim about the SURVIVOR, and a bare dropped id
    cannot make it.

    🔴 IT IS NOT RECONSTRUCTIBLE FROM `twin_fold_key` EQUALITY, AND THAT IS THE
    WHOLE REASON IT EXISTS. :func:`_merge_soccer_name_variants` folds rows whose
    strict keys DIFFER — on the NAMES (#5918: `Celta Vigo` / `RC Celta de Vigo`)
    and on the MINUTE (#5964: the bucket is the kick-off DATE, so 16:30Z and
    16:32Z cluster). A caller that re-derives "who absorbed this row" by matching
    keys therefore answers correctly on the exact-name pairs and silently wrongly
    on precisely the pairs that pass was written for.

    The sibling correction does NOT have this property, and the difference is
    worth stating so nobody widens the wrong one:
    :func:`recover_kalshi_occurrence_starts` (#5905) rewrites the row's served
    `commence_time` in place before the keying, so both members of a Kalshi-timed
    pair key alike downstream and equality would have been enough there.

    `_folded_past_rails` in `app/routes/league_futures.py` is the caller (#5532):
    it drops a stuck-`live` row from the upcoming rail only when the row that
    absorbed it is a Final the same response is already printing.
    """

    merged_opening: dict = field(default_factory=dict)
    """``{survivor_id: (home, away)}`` — survivors that gained a pre-match line
    from the row they absorbed, and only those. Unlike
    :attr:`merged_sources`, the fold has ALREADY applied this to the row (see
    :func:`_elect`); this is the record, for the log line and the guard tests."""

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

    # #2866 — one league answer per `sport_id`, read once. See
    # `_league_identities`: this is what makes the league element of the key
    # unable to SPLIT a group that `sport_id` alone would have made.
    try:
        identities = _league_identities(ordered)
    except Exception:  # noqa: BLE001 — gotcha #42; `sport_id` is master's key
        logger.exception("twin fold: league identities failed; keying on sport_id")
        identities = {}

    groups: dict[tuple, list] = {}
    unkeyed: list = []
    row_identities: dict = {}

    # Gotcha #42 — one bad item must never wipe a scoring pass. This runs on the
    # `/api/feed` hot path above every other stage, so a single row with a
    # surprising `commence_time` type must cost that row its fold, not the whole
    # page. A row that cannot be keyed is a row that cannot be proven a twin,
    # which is already the "leave it alone" branch.
    for event in ordered:
        try:
            key = twin_fold_key(event, identities)
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
        # Elements 1–3 — WHO and WHEN, with no league in them. Kept here so the
        # catch-all pass below can ask "same fixture?" without squashing every
        # club name on the page a second time. Keyed on the PYTHON object for
        # the reason `keep` is: two hydrated rows can share a primary key.
        row_identities[id(event)] = key[1:]

    # #5918 — the strict key has now grouped every pair that SPELLS its clubs the
    # same way. The soccer pass below is the only thing that can reach a pair
    # that NAMES them differently, and it runs on the groups rather than on the
    # rows so that it can never weaken the key for anybody else.
    try:
        grouped = _merge_soccer_name_variants(groups)
    except Exception:  # noqa: BLE001 — gotcha #42; the strict groups are today's
        logger.exception("twin fold: soccer name merge failed; serving strict groups")
        grouped = list(groups.values())

    # #2866 rung two — the strict key and the soccer pass have both had their
    # say, and a `*_other` row whose league is simply unmapped is still sitting
    # beside its twin. This unions whole clusters and never splits one, so on a
    # failure the groups above are exactly what a reader gets today.
    try:
        grouped = _merge_catchall_leagues(grouped, row_identities)
    except Exception:  # noqa: BLE001 — gotcha #42; the league-keyed groups stand
        logger.exception("twin fold: catch-all league merge failed; serving groups")

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


def _soccer_bucket_key(key: tuple) -> tuple:
    """`(league, commence DATE)` — the CANDIDATE bucket, not the licence.

    Element 0 is whatever :func:`twin_fold_key` put there — since #2866 the
    LEAGUE, with `sport_id` as the fallback — and this helper simply carries it
    through. No soccer key has a season variant or a map collision, so every
    soccer bucket holds exactly the rows it held before that change.

    #5964 — THE BUCKET STOPPED BEING THE CLOCK TEST. Until today this returned
    `(sport_id, minute)` and exact-minute equality was the whole clock rule.
    That cost a real pair: on 2026-09-13 La Liga served Getafe–Deportivo twice,
    ESPN storing the kick-off at 16:30Z and the Odds API at 16:32Z, so the two
    rows sat in different buckets and were never asked the name question at all.

    So the bucket is now only how CANDIDATES are found cheaply — a day of one
    competition — and the clock rule moved into the pair predicate, where it is
    applied to the two rows actually being compared
    (:data:`SOCCER_KICKOFF_DRIFT`). Widening a bucket cannot fold anything on its
    own: every pair inside it must still pass both the name rule and the drift
    rule, and the clique refusal still applies to the result.

    Why not simply make the bucket the day and let the names decide, which is the
    obvious version of this change: it folds two populations that are not
    #5964's and that other people deliberately own. The 30-minute re-mints
    measured on these boards were excluded by #5918 on purpose, and the
    three-hour Kalshi rows are #5905's recovery to correct — folding them here
    would make that recovery's own non-vacuity guards pass for the wrong reason
    and quietly retire a ship that is still doing work on rows with no twin.

    The day is read in UTC because that is the frame the rows are stored in. Two
    twins either side of midnight UTC are therefore never even candidates; that
    fails CLOSED — two cards, which is today's behaviour — and no observed pair
    needs it.
    """
    league, _away, _home, minute = key
    return (league, minute.date())


def _group_representative(members: list) -> Any:
    """The row whose names speak for a group — lowest id, so it never flickers.

    Members of a group share a *squashed* name, not a tokenized one:
    "St.Louis" and "St. Louis" squash alike and tokenize differently. So which
    member answers for the group is a real choice, and it is made the same way
    :func:`twin_identity_rank` breaks its final tie — deterministically, by row
    id — rather than by the order the caller happened to hand us the rows.
    """
    return min(members, key=lambda m: getattr(m, "id", 0) or 0)


def _merge_soccer_name_variants(groups: dict[tuple, list]) -> list[list]:
    """Merge same-minute soccer groups whose club names name the same fixture.

    Returns the groups to elect over, in the order the strict key made them; a
    merged cluster takes the position of its earliest member group. Nothing is
    dropped and nothing is reordered for a sport this does not touch, so a
    caller serving no soccer gets byte-identical behaviour to before #5918.

    THE CLIQUE TEST IS THE SAFETY, AND IT IS NOT BELT-AND-BRACES. Union-find
    over a non-transitive predicate is exactly the bug lane1/281 warned about
    when handing this over: `Madrid` ⊆ `Real Madrid` and `Madrid` ⊆ `Atlético
    Madrid` would chain the two Madrid clubs into one card through a third row
    that matched both. Requiring every pair inside a cluster to match collapses
    that chain back to nothing and leaves all three groups standing.
    """
    buckets: dict[tuple, list[tuple]] = {}
    for key in groups:
        buckets.setdefault(_soccer_bucket_key(key), []).append(key)

    merged_into: dict[tuple, tuple] = {}
    for bucket_keys in buckets.values():
        if len(bucket_keys) < 2:
            continue
        sport_key = loaded_sport_key(_group_representative(groups[bucket_keys[0]]))
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


_CATCHALL_SUFFIX = "_other"


def _catchall_sport_prefix(sport_key: Optional[str]) -> Optional[str]:
    """The SPORT behind a `*_other` catch-all key, or ``None`` for a real league.

    `soccer_other` → `soccer`, `americanfootball_other` → `americanfootball`.
    The suffix is stripped rather than the key split on its first `_` — the two
    agree on every key in the table today, since no sport name contains an
    underscore, but stripping is the exact inverse of how the key is formed and
    so cannot start disagreeing when one does.

    The returned value is the prefix the MATCHER already scopes candidates with
    (`event.sport.key.startswith(sport_prefix)` in `_score_candidates`), and
    `sport_keys.py` carries the reason it is the bare sport: `soccer_other` is
    itself a real key with 4,752 production events, so using it as a prefix
    rejects every competition that is not it.
    """
    if not sport_key or not sport_key.endswith(_CATCHALL_SUFFIX):
        return None
    return sport_key[: -len(_CATCHALL_SUFFIX)]


#: Squad markers that name a DIFFERENT side of the same club and that
#: :func:`soccer_pair_matches` cannot see. #2866 rung 3.
#:
#: Its `SQUAD_QUALIFIERS` already refuses a disagreement about `b` / `ii` / `w` /
#: `u21` / `reserves`, and its docstring states the residual it cannot close: **a
#: reserve side with its own NAME is not caught** — `Real Madrid` matches `Real
#: Madrid Castilla`, and `Ajax` matches `Jong Ajax Amsterdam` (measured True).
#: Within a league that residual is harmless, because a club's senior and
#: reserve sides are not in one competition; this pass is the first thing to
#: compare names ACROSS competitions, and an unmapped key is exactly where
#: reserve and amateur sides land.
#:
#: So these two tokens are not a remembered vocabulary of B-team names — the
#: thing `soccer_team_matching` refuses to invent, and rightly. Each is a word
#: carried by a `soccer_other` row on our own board today: `/api/events/search?q=Ajax`
#: served `Jong Ajax Amsterdam` (four rows) and `Ajax Amateurs` beside the senior
#: Ajax fixtures on 2026-09-14. A token earns its place here by appearing on a
#: real catch-all row that this pass would otherwise fold onto a senior card,
#: never by being recalled as a B-team word.
#:
#: It can only ever REFUSE, so the failure it risks is two cards — today's
#: behaviour — and never one card holding two games.
_DIFFERENT_SQUAD_TOKENS = frozenset({"jong", "amateurs"})


def _names_a_different_squad(left: tuple, right: tuple) -> bool:
    """Does one side carry a named-squad marker the other does not? #2866 rung 3."""
    for left_name, right_name in zip(left, right):
        disputed = set(club_alias_tokens(left_name)) ^ set(club_alias_tokens(right_name))
        if disputed & _DIFFERENT_SQUAD_TOKENS:
            return True
    return False


def _objectively_different_games(left: list, right: list) -> bool:
    """Do these two clusters hold evidence of being TWO REAL GAMES? #2866 rung 3.

    The two controls the rung-two census applied to its population, applied here
    per pair instead, so the pass refuses a bad fold on the row in front of it
    rather than on a measurement taken once:

    * two different `espn_id`s — the authority id is one game, one id (#2693),
      so two of them in a cluster is two games by construction;
    * two different SCORELINES — a fold that put these on one card would have to
      throw one away, and neither is ours to discard.

    A missing value on either side is NOT evidence and never refuses: 19 of the
    19 catch-all rows this pass acts on carry no score and no `espn_id`, so a
    refusal on absence would refuse the entire population it exists for.
    """

    def values(members: list, attr: str) -> set:
        return {
            value
            for value in (getattr(member, attr, None) for member in members)
            if value is not None
        }

    if len(values(left, "espn_id") | values(right, "espn_id")) > 1:
        return True

    def scores(members: list) -> set:
        found = set()
        for member in members:
            home = getattr(member, "home_score", None)
            away = getattr(member, "away_score", None)
            if home is not None or away is not None:
                found.add((home, away))
        return found

    return len(scores(left) | scores(right)) > 1


def _catchall_name_variant_merges(
    clusters: list[list],
    identities: dict,
    sport_keys: dict,
    league_at: dict,
) -> list[tuple[int, int]]:
    """`(catch-all cluster, league cluster)` pairs naming one fixture. #2866 rung 3.

    Only for a catch-all cluster whose exact fixture identity found NO league
    twin — everything the identity pass already folds is left to it, so this can
    add merges and can never change one.

    The licence is the rung-two licence plus one substitution, and it is worth
    naming the piece that does NOT change: the catch-all row still makes no
    claim about its competition, the league row still does, they still agree on
    the sport and on the MINUTE, and one club cannot play two fixtures in one
    minute. What changes is only how "the same clubs" is decided — from
    byte-equal squashed names to :func:`soccer_pair_matches`, the same predicate
    `_merge_soccer_name_variants` has used within a league since #5918.

    Three refusals, each of which leaves both rows standing (two cards, today's
    behaviour) rather than guessing:

    * **not soccer.** The predicate measured itself on soccer boards and is used
      on soccer rows and nowhere else, exactly as the strict pass says. The 65
      cross-sport catch-all pairs rung two found are refused by the prefix test
      before this is ever reached.
    * **more than one candidate.** A catch-all cluster matching two league
      clusters is the `Madrid` ⊆ `Real Madrid` / `Atlético Madrid` shape, and it
      is refused WHOLE — never resolved by picking one. A league cluster claimed
      by two catch-all clusters is refused the same way and for the same reason.
    * **objectively two games** — see :func:`_objectively_different_games`.
    """
    league_by_minute: dict = {}
    for identity, entries in league_at.items():
        league_by_minute.setdefault(identity[2], []).extend(entries)
    if not league_by_minute:
        return []

    def names(index: int) -> tuple:
        rep = _group_representative(clusters[index])
        return (
            getattr(rep, "home_team_name", None),
            getattr(rep, "away_team_name", None),
        )

    candidates: dict[int, set] = {}
    for index, members in enumerate(clusters):
        for member in members:
            identity = identities.get(id(member))
            if identity is None or identity in league_at:
                continue  # the identity pass has already had its say
            sport_key = sport_keys.get(getattr(member, "sport_id", None))
            prefix = _catchall_sport_prefix(sport_key) if sport_key else None
            if prefix != "soccer":
                continue
            for target, target_key in league_by_minute.get(identity[2], ()):
                if target == index or not target_key.startswith(prefix):
                    continue
                if not soccer_pair_matches(names(index), names(target)):
                    continue
                if _names_a_different_squad(names(index), names(target)):
                    logger.info(
                        "twin fold: refused a catch-all naming another squad of "
                        "the same club (%s x %s)",
                        getattr(_group_representative(clusters[index]), "id", "?"),
                        getattr(_group_representative(clusters[target]), "id", "?"),
                    )
                    continue
                if _objectively_different_games(clusters[index], clusters[target]):
                    logger.info(
                        "twin fold: refused a catch-all name variant holding a "
                        "second scoreline or authority id (%s x %s)",
                        getattr(_group_representative(clusters[index]), "id", "?"),
                        getattr(_group_representative(clusters[target]), "id", "?"),
                    )
                    continue
                candidates.setdefault(index, set()).add(target)

    merges: list[tuple[int, int]] = []
    claimed: dict[int, set] = {}
    for index, targets in candidates.items():
        if len(targets) != 1:
            logger.info(
                "twin fold: refused an ambiguous catch-all name variant claimed "
                "by %d leagues",
                len(targets),
            )
            continue
        target = next(iter(targets))
        claimed.setdefault(target, set()).add(index)
        merges.append((index, target))

    # A league cluster two DIFFERENT catch-all clusters both name is the same
    # ambiguity read from the other end, and union-find would join all three —
    # putting two catch-all fixtures on one real card. Refused whole.
    contested = {target for target, sources in claimed.items() if len(sources) > 1}
    if contested:
        logger.info(
            "twin fold: refused %d league cluster(s) claimed by more than one "
            "catch-all name variant",
            len(contested),
        )
    return [(source, target) for source, target in merges if target not in contested]


def _merge_catchall_leagues(clusters: list[list], identities: dict) -> list[list]:
    """Fold a `*_other` group into the real league naming the same fixture. #2866.

    THE SHAPE, PHOTOGRAPHED ON PRODUCTION 2026-09-14 03:44Z AT 390px. Ajax v
    Willem II on 2026-09-15 was two cards on `/api/events/search` — `15297733`
    keyed `soccer_netherlands_eredivisie`, priced 91/9, and `15307699` keyed
    `soccer_other` saying "No price yet". Toluca v Santos Laguna on 2026-09-21
    is the same shape (`15312342` × `15307702`). Both survive every other guard
    in this file: after #5905's recovery the two rows agree to the MINUTE and
    their club names are byte-identical, so elements 1–3 of the strict key
    already match and element 0 alone keeps them apart.

    `league_identity` — rung one of #2866, which closed the 47 NFL preseason
    pairs — cannot reach these and it is worth saying why, because the obvious
    reading is that it should. Its own docstring promises an unmapped key falls
    back to ITSELF so that it never splits a group, and neither `soccer_other`
    nor `soccer_netherlands_eredivisie` is in `SPORT_LEAGUE_MAP`: both map to
    themselves and stay two leagues. Measured, not assumed —
    `soccer_other → soccer_other`, `soccer_netherlands_eredivisie →
    soccer_netherlands_eredivisie` (authority/197). `league_family_identity`
    answers identically. Rung one is right and it is not sufficient.

    WHY A CATCH-ALL MAY BE FOLDED AT ALL. A `*_other` row makes no claim about
    which competition it is in — the key is where an unmapped Kalshi series
    lands. The row it is being folded into does make that claim, and the two
    agree on both clubs and on the minute. One club cannot play two fixtures in
    one minute, so same sport + same clubs + same minute is one game.

    🔴 THE SAME-SPORT GUARD IS THE WHOLE LICENCE AND IT IS LOAD-BEARING, NOT A
    RESERVATION. Pairs sharing squashed clubs and the minute across two
    `sport_id`s where exactly one side is a catch-all number 73 in a 90d/30d
    window — and 65 of them are CROSS-SPORT: 59 `baseball_other × esports`, 5
    `americanfootball_other × esports`, 1 `basketball_other × baseball_npb`.
    Those are a classification defect somebody else owns, they are emphatically
    not one fixture each, and without the prefix test this pass would fold every
    one of them onto a single card. The prefix test is the only thing standing
    between this fold and all 65.

    THE ENTIRE POPULATION IT ACTS ON, MEASURED ALL-TIME AND ROW BY ROW, IS 9
    FIXTURES — every one of them verified two rows of one game:

        soccer_other × soccer_mexico_ligamx            2   Toluca v Santos,
                                                           América v Guadalajara
        soccer_other × soccer_fifa_world_cup           2   AUS v TUR, CAN v BIH
        soccer_other × soccer_netherlands_eredivisie   1   Ajax v Willem II
        soccer_other × soccer_korea_kleague1           1   Daejeon v Pohang
        esports_other × esports                        3
        baseball / tennis / basketball / american
        football / cricket / rugby / icehockey / mma
        / motorsport / aussierules / golf, all time    0

    Both objective false-fold controls are clean over all 9: no pair holds two
    different scorelines and no pair holds two different `espn_id`s — either
    would mean two real games merged onto one card. Every pair is exactly two
    rows.

    TWO WAYS A CENSUS OF THIS SHAPE LIES, BOTH OF WHICH BIT THIS ONE BEFORE THE
    NUMBER ABOVE SETTLED. Postgres has no `unaccent` here, so a SQL squash that
    only strips `[^a-z0-9]` turns `América` into `amrica` and silently drops the
    Liga MX clásico this pass folds — the count read 8 until `translate()` was
    added, and the DRIVEN run over the real rows is what caught it. And the
    Kalshi three-hour correction is SOCCER-ONLY
    (`kalshi_occurrence_start._soccer` gates it), so applying it to every sport
    in the census manufactured 3 `tennis_other × tennis_atp` pairs that the code
    can never see; on the clock the fold actually uses, tennis is 0.

    THE MEN'S/WOMEN'S CLASS IS THE ONE THAT WOULD BREAK THIS, and it is excluded
    by construction rather than by luck. `cricket_the_hundred` and
    `cricket_the_hundred_womens` field clubs of the SAME NAME and 19 such pairs
    exist — but neither key is a catch-all, so requiring exactly one side to be
    `*_other` never admits them. Measured for the residual case (a women's
    fixture landing in `cricket_other` beside its men's counterpart): zero
    cricket pairs of this shape have ever existed.

    AMBIGUITY IS REFUSED WHOLE, the way :func:`_name_clusters` refuses a
    non-clique. If one fixture identity is claimed by two DIFFERENT real-league
    groups, the catch-all row cannot say which it belongs to and nothing merges
    — two cards, today's behaviour, rather than a guess.

    Runs AFTER :func:`_merge_soccer_name_variants` and on its output, so it can
    neither weaken nor reorder that pass: #5918, #5964 and #6007 decide first
    and this only ever unions whole clusters they have already settled.

    ``identities`` is ``{id(row): key[1:]}`` — elements 1–3 of the strict key,
    handed in rather than recomputed. Recomputing them here is the obvious way
    to write this and it costs a second `_squash` of both club names for every
    row on the page (`strip_diacritics` plus a regex, uncached): +5ms on a
    1,554-row soccer page, for an answer :func:`twin_fold_key` had already
    worked out. Every row in ``clusters`` has an entry, because a row the key
    refused never reaches a group at all.
    """
    catchall_at: dict[tuple, list[tuple[int, str]]] = {}
    league_at: dict[tuple, list[tuple[int, str]]] = {}

    # One key per `sport_id`, resolved once — the same shape as
    # `_league_identities` and for the same two reasons. Correctness: two rows
    # of one sport can never disagree about whether their key is a catch-all.
    # Cost: `loaded_sport_key` runs a SQLAlchemy `inspect()` behind a
    # try/except, and asking it per ROW rather than per SPORT put +8ms on a
    # 1,554-row page; per sport it is ~40 calls and the page pays +0.4ms.
    sport_keys: dict = {}
    for members in clusters:
        for member in members:
            sport_id = getattr(member, "sport_id", None)
            if sport_id is None or sport_id in sport_keys:
                continue
            key = loaded_sport_key(member)
            if key:
                sport_keys[sport_id] = key

    for index, members in enumerate(clusters):
        for member in members:
            identity = identities.get(id(member))
            if identity is None:
                continue
            sport_key = sport_keys.get(getattr(member, "sport_id", None))
            if not sport_key:
                # The caller did not load `Event.sport`. This pass reads the
                # raw key rather than the key's identity — `aussierules_other`
                # is the one catch-all `SPORT_LEAGUE_MAP` rewrites — so with no
                # key it has nothing it is licensed to say (gotcha #42).
                continue
            prefix = _catchall_sport_prefix(sport_key)
            if prefix is None:
                league_at.setdefault(identity, []).append((index, sport_key))
            else:
                catchall_at.setdefault(identity, []).append((index, prefix))

    merges: list[tuple[int, int]] = []
    for identity, catchall_entries in catchall_at.items():
        league_entries = league_at.get(identity, ())
        targets = {index for index, _ in league_entries}
        if len(targets) != 1:
            if targets:
                logger.info(
                    "twin fold: refused an ambiguous catch-all fixture %s "
                    "claimed by %d leagues",
                    identity,
                    len(targets),
                )
            continue
        target = next(iter(targets))
        target_keys = {sport_key for index, sport_key in league_entries}
        for index, prefix in catchall_entries:
            if index == target:
                continue  # one cluster already holds both sides
            if all(key.startswith(prefix) for key in target_keys):
                merges.append((index, target))

    # #2866 RUNG THREE — the catch-all row that SPELLS ITS CLUBS DIFFERENTLY.
    # Everything above pairs on the exact fixture identity, so it reaches a
    # `*_other` row only when its club names already squash byte-identically to
    # the league row's. Measured 2026-09-14 06:3xZ by DRIVING `fold_twin_events`
    # over the 1,559 reader-reachable soccer rows in `[now-3d, now+8d]`: master
    # folds 80, this folds 98 — 18 newly folded, 0 lost, every one read by hand
    # against its survivor and every one two rows of one fixture:
    #
    #     Sittard v Ajax           × Fortuna Sittard v Ajax    (eredivisie)
    #     Enschede v Den Haag      × FC Twente Enschede v ADO Den Haag
    #     GA Eagles v Groningen    × Go Ahead Eagles v Groningen
    #     Jeonbuk v Seoul          × Jeonbuk Hyundai Motors v FC Seoul
    #     Bucheon v Jeju SK        × Bucheon FC 1995 v Jeju United FC
    #     America FC v Sao Bernardo × América Mineiro v São Bernardo  … 18 in all
    #
    # The reader sees the league row as a FINAL with a scoreline and the
    # catch-all row directly beneath it saying "No result reported": the league
    # row is `completed` while the catch-all sits `suspended`/`closed`/`voided`,
    # and NOT ONE catch-all row in the population carries a score or an
    # `espn_id`. Both objective false-fold controls are clean across it — no
    # pair holds two different scorelines, no pair holds two different
    # `espn_id`s — and they are re-applied per pair below rather than trusted
    # from the measurement.
    #
    # A SQL census over a wider window is deliberately not the number here. It
    # narrowed candidates by substring containment, while the predicate this
    # pass uses is a TOKEN SUBSET, so it missed five of the 18 outright
    # (`GA Eagles`, `Bucheon`, `América Mineiro` twice, `Hoffenheim II`). An
    # instrument that is not the code is a lower bound, never the population —
    # the same way rung two's own census read 8 until `translate()` was added.
    #
    # 🔴 WHY THIS PASS AND NOT A WIDER BUCKET, WHICH IS THE OBVIOUS VERSION.
    # `_merge_soccer_name_variants` already owns "same fixture, different
    # spelling" and would answer this if its bucket were not `(league, date)`.
    # Dropping the league from that bucket would let the name predicate run
    # across EVERY pair of competitions, and the predicate's own docstring
    # states the residual that makes that unsafe: a reserve side with its own
    # NAME is not caught, so `Ajax` matches `Jong Ajax Amsterdam` (measured
    # True). Reserve and amateur sides are exactly what an unmapped key
    # collects — this very board carries `Jong Ajax Amsterdam` and `Ajax
    # Amateurs` in `soccer_other` — so the league separation is what stands
    # between those rows and a senior card today. This pass keeps that
    # separation everywhere except where one side is a catch-all making no
    # competition claim at all, and pays for the residual with the two
    # objective controls and the ambiguity refusals rather than with a
    # remembered list of B-team names, which is the unmeasured vocabulary
    # `soccer_team_matching` exists to avoid, plus
    # :data:`_DIFFERENT_SQUAD_TOKENS` for the two markers our own board carries.
    # Measured over the same window: not one senior-versus-reserve pair reaches
    # this pass, because a reserve fixture and the senior fixture it shadows do
    # not kick off in the same MINUTE. One reserve pair IS in the population and
    # is correct — `Hoffenheim II` × `TSG Hoffenheim II` in Liga 3, the marker on
    # BOTH sides, which is agreement and not a conflict.
    #
    # The minute is exact here, not `SOCCER_KICKOFF_DRIFT`: all 18 agree to the
    # minute once #5905's Kalshi correction has run, so the drift bound would
    # widen the licence without folding anything it does not already fold.
    try:
        merges.extend(
            _catchall_name_variant_merges(clusters, identities, sport_keys, league_at)
        )
    except Exception:  # noqa: BLE001 — gotcha #42; the exact-identity merges stand
        logger.exception("twin fold: catch-all name-variant pass failed")

    # A catch-all cluster that would land on TWO different league clusters is
    # refused whole, the same way an ambiguous identity is above. It is the only
    # path by which this pass could put two REAL leagues on one card: a cluster
    # the soccer name pass built spans more than one fixture identity (two
    # spellings, or two minutes inside the drift bound), and each identity finds
    # its own league twin in a different cluster — union-find would then join
    # all three. Measured zero in the whole 9-fixture population, where every
    # group is exactly two rows; refused anyway, because the docstring's claim
    # that two real leagues never merge should be true by construction rather
    # than by the population happening to be small.
    targets_per_source: dict[int, set] = {}
    for source, target in merges:
        targets_per_source.setdefault(source, set()).add(target)
    for source, found in targets_per_source.items():
        if len(found) > 1:
            logger.info(
                "twin fold: refused a catch-all cluster reaching %d leagues",
                len(found),
            )
    merges = [
        (source, target)
        for source, target in merges
        if len(targets_per_source[source]) == 1
    ]

    if not merges:
        return clusters

    parent = list(range(len(clusters)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for source, target in merges:
        left, right = find(source), find(target)
        if left != right:
            # The EARLIER cluster is always the root, so a merged cluster takes
            # the position of its earliest member — the same ordering rule
            # `_merge_soccer_name_variants` states.
            parent[max(left, right)] = min(left, right)

    out: list[list] = []
    position: dict[int, int] = {}
    for index, members in enumerate(clusters):
        root = find(index)
        if root in position:
            out[position[root]].extend(members)
            continue
        position[root] = len(out)
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

    #5964 RE-MEASURED, because widening the candidate bucket to a day is exactly
    the change that could have made this expensive. On the largest page in the
    system — all 697 `soccer_other` rows, the worst case by a distance — master
    against this change, two rounds after discarding an import-warmed first
    reading, cold and warm on the same rows:

        697 rows, `soccer_other`   8.76ms → 13.2ms cold   3.58ms → 4.4ms warm
        40 rows, a feed page                0.54ms cold          0.24ms warm

    So +4.4ms cold and +0.8ms warm on the one page that pays the most, and the
    day bucket asks 1,679 distinct questions where the minute bucket asked 1,062.
    The sliding window in :func:`_name_clusters` is what keeps that from being a
    cross product; without it the same page cost 16.2ms cold.
    """
    return soccer_pair_matches(left, right)


def _name_clusters(bucket_keys: list[tuple], groups: dict[tuple, list]) -> list[list]:
    """Groups of keys inside one bucket that all pair-match each other.

    Only clusters of two or more are returned, and only cliques: a candidate
    cluster that is merely connected is discarded whole rather than split, so a
    chain never decides which of its links survives.
    """
    pairs: dict[tuple, tuple] = {}
    dateless: dict[tuple, bool] = {}
    for key in bucket_keys:
        rep = _group_representative(groups[key])
        pairs[key] = (
            getattr(rep, "home_team_name", None),
            getattr(rep, "away_team_name", None),
        )
        dateless[key] = all(is_kalshi_date_only(member) for member in groups[key])

    def same_fixture(left: tuple, right: tuple) -> bool:
        """Both halves of the licence, asked about the two groups in hand.

        #5964 — the clock half lives here rather than in the bucket so that it is
        asked about the PAIR. A bucket can only sort rows into piles; it cannot
        say that these two rows are four minutes apart and those two are forty.
        Names are asked second because :func:`_pair_matches` is the memoized,
        expensive half and the drift test is a subtraction.

        #6007 — A GROUP THAT NEVER CLAIMED AN HOUR CANNOT DISAGREE ABOUT ONE.
        The drift bound measures how far two providers put the same kick-off.
        A :func:`is_kalshi_date_only` group put it nowhere: its time is a
        ticker's date with midnight stapled on. Holding it to a five-minute
        bound asks it to agree with a clock it does not have, and the answer is
        always no — which is why ten fixtures on 2026-09-13 served a finished
        card and a phantom "upcoming" one beside it. So for those groups the
        clock half is satisfied by the bucket itself (`sport_id`, UTC date) and
        the club names carry the whole decision. The names are not weakened:
        both clubs, orientation kept, squad-marker refusal, clique refusal.
        """
        if not (dateless[left] or dateless[right]):
            if abs(left[3] - right[3]) > SOCCER_KICKOFF_DRIFT:
                return False
        return _pair_matches(pairs[left], pairs[right])

    parent = {key: key for key in bucket_keys}

    def find(key: tuple) -> tuple:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    # #5964 — a day-wide bucket asked in time order is a sliding window, not a
    # cross product. Beyond the drift bound `same_fixture` can only answer False,
    # so the inner loop stops at the first key out of range instead of asking the
    # expensive name half about every other fixture in the competition that day.
    # Semantics are identical — this skips only pairs already refused — and it is
    # what keeps the wider bucket cheaper than the minute one it replaced.
    #
    # #6007 — AND THE WINDOW HAS TO KNOW THE SAME EXCEPTION THE PREDICATE DOES,
    # or the fix is inert. A date-only group sits at 00:00Z, so it sorts first in
    # its day and every real kick-off is hours past the break: the loop would
    # stop before `same_fixture` was ever asked, and the change above would read
    # as a no-op with green tests. A dateless `left` therefore scans its whole
    # day-bucket. That is 13 rows' worth of full scan across the fleet today, and
    # only a dateless group pays it — every other row keeps the sliding window.
    in_time_order = sorted(bucket_keys, key=lambda key: key[3])
    for i, left in enumerate(in_time_order):
        for right in in_time_order[i + 1 :]:
            if not dateless[left] and right[3] - left[3] > SOCCER_KICKOFF_DRIFT:
                break
            if same_fixture(left, right):
                parent[find(left)] = find(right)

    clusters: dict[tuple, list] = {}
    for key in bucket_keys:
        clusters.setdefault(find(key), []).append(key)

    out: list[list] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        if all(
            same_fixture(left, right)
            for i, left in enumerate(members)
            for right in members[i + 1 :]
        ):
            out.append(members)
        else:
            logger.info(
                "twin fold: refused a non-clique soccer cluster %s",
                [pairs[key] for key in members],
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
    # #5532 — recorded HERE, the one place the pair is still in hand. The fold
    # returns its survivors flattened into one list, so a caller downstream can
    # see THAT a row went and can never see which of the rows it is holding
    # took its place.
    for loser in losers:
        result.survivor_of[loser.id] = survivor.id

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
