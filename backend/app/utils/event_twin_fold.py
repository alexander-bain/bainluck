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
from app.utils.sport_keys import is_season_variant, league_identity

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


team_name_fold_key = _squash
"""The fold's own notion of "the same team name", exported for SELECTORS.

This fold decides which event rows are one FIXTURE. A page's query decides
which rows reach the fold at all — and those two answers have to share one
notion of a team name or a surface admits a pair the fold would have collapsed,
or (worse, #7929) never admits the row that carries the number.

`routes/teams.py` is the reader of record: a club with several team rows
(`Montreal Canadiens` 568, `Montréal Canadiens` 3706, `Montréal Canadiens`
19692) had its schedule split across them, and the page's exact-string arm
could reach only the spelling its URL resolved to.

Exported as an ALIAS rather than reimplemented, so the selector and the fold
cannot drift: there is one function, under two names, and changing the key
changes both callers in the same edit.
"""

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
    3. **The authority's word** — `status == 'completed'` over anything else.
       Two rows that both carry a score can carry DIFFERENT scores, and rung 1
       cannot see that: it asks whether a score is present, not whether it is
       final. See #5841 below.
    4. Only then source count, then a row that NAMES ITS LEAGUE over a `*_other`
       catch-all, and finally the lower row id, so the election is deterministic
       across requests and the served `id` does not flicker between two polls.

    #5841 — WHY THE AUTHORITY RUNG EXISTS AND WHY IT SITS BELOW BOTH ANCHORS.
    `/api/events/search?q=Yankees` served `14877917` — a fabricated `0 - 0`,
    `closed` — over `15295242`, the `0 - 6` the game actually finished, because
    both satisfy rung 1 (a `0` is not `None`), both anchors tie, and
    `_source_count` 6 vs 5 ended it. The reader lost the RESULT and gained one
    extra probability source on a three-week-old game.

    THE POSITION IS NOT A PREFERENCE — one measured group decides it. Of the 79
    `completed`-vs-`closed` twin groups on production (2026-09-16), the existing
    ordering ALREADY elects the `completed` row in 72; this rung agrees with the
    incumbent in 72 of 72 and only speaks where the tuple previously fell
    through to venue richness. Of the 7 it could change, six are improvements
    and ONE is a loss: `15228847`/`15290802` (D'backs–Reds 08-23) hold the
    IDENTICAL scoreline `5–11`, and the `completed` row has no `espn_id`. Placed
    above rung 2 this rung would trade an anchor for nothing. Placed here it
    cannot: `espn_id` still decides that pair and it does not move.

    SO THE REACH IS SIX GROUPS, all `baseball_mlb`, each replacing a score
    frozen mid-game with the final one — `3-1`→`5-4`, `3-2`→`5-2`, `1-3`→`1-5`,
    `6-4`→`7-4`, `0-3`→`1-6`, and `0-0`→`0-6`. Two controls, both measured
    rather than argued: no group changes `espn_id` presence, and in 6 of 6
    NEITHER of the losing row's numbers exceeds the winner's — the signature of
    a partial score, which is the class this beats. A flip count alone would not
    have shown that; the DIRECTION of the disagreement is the test, and had one
    `closed` row carried the higher score this rung would be wrong.

    THE COMMITTING CALLER CHANGES NOTHING, AND UNLIKE `names_league` THAT IS NOT
    BECAUSE IT CANNOT REACH IT. `tasks/reconcile_shared_fixture_ids.py` elects a
    canonical row with this function and COMMITS, so this is a write-path change
    too. Of its 35 `statpal_fixture_id` groups, 13 hold a `completed` row beside
    a non-`completed` one — but 11 of those have no score on the other side at
    all, so rung 1 decides them and this rung is inert. The remaining two
    (`1027790` Hornets–Heat, `637968` Avalanche–Wild) are BOTH refused by
    `_refuse`'s `KICKOFF_DIFFERS` before any tag is written: their members are a
    day and two days apart respectively — they are different games wearing one
    fixture id, not twins. Zero committed tags change. Re-measure this if
    `_refuse` ever loosens its kickoff test; that guard, not this ordering, is
    what keeps the write path still.

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
    authority_called_it = getattr(event, "status", None) == "completed"
    return (
        1 if has_score else 0,
        1 if getattr(event, "espn_id", None) else 0,
        1 if getattr(event, "external_id", None) else 0,
        1 if authority_called_it else 0,
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

    # #7915 — BEFORE the soccer pass, and on the dict rather than the clusters,
    # because it is the same SHAPE of step: the strict key's groups, merged where
    # a licence this module can state covers them. It runs first only so the
    # soccer pass keeps receiving a dict keyed exactly the way it expects; the
    # two cannot interact, because a league with a season variant is never a
    # soccer league and this pass fires on nothing else.
    try:
        groups = _merge_season_variant_kickoffs(groups)
    except Exception:  # noqa: BLE001 — gotcha #42; the strict groups are today's
        logger.exception(
            "twin fold: season-variant merge failed; serving strict groups"
        )

    # #8100 — same shape of step again, and after the season-variant pass rather
    # than before it: that pass can only make a group MORE anchored, which is the
    # input this one reads. Its licence is a PROVENANCE asymmetry (one id-less
    # claim, one anchored row) and not a league or a sport, so it is the only
    # thing here that can reach two `basketball_nbl` rows six minutes apart.
    try:
        groups = _merge_anchored_claim_kickoffs(groups)
    except Exception:  # noqa: BLE001 — gotcha #42; the groups above are today's
        logger.exception(
            "twin fold: anchored-claim merge failed; serving strict groups"
        )

    # #8100 second half — the same licence, asked about the NAMES instead of the
    # clock. It sits after the clock pass only because a merge can make a group
    # more anchored and never less; the two populations do not overlap (that pass
    # needs the names identical, this one needs the minute identical), so the
    # order is a reading order and not a dependency.
    try:
        groups = _merge_anchored_claim_name_variants(groups)
    except Exception:  # noqa: BLE001 — gotcha #42; the groups above are today's
        logger.exception(
            "twin fold: anchored-claim name merge failed; serving strict groups"
        )

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


SEASON_VARIANT_KICKOFF_DRIFT = timedelta(minutes=15)
"""How far apart two providers may put ONE kick-off across a season-variant pair.

#7915. Sized the way :data:`SOCCER_KICKOFF_DRIFT` is sized — from the measured
band, placed in the empty space below the nearest population somebody else owns
— and NOT inherited from the sibling pass in `search_fixture_dedup` (#7700),
which bounds the same class at 30 minutes for a different reason. That module
takes its bound from `event_registry._SAME_FIXTURE_MAX_SEPARATION`, the
schedule-argued "no format starts two same-pair fixtures this close" constant.
Here the nearest neighbour is closer: the docstring above records a 30-minute
re-mint class that #5918 excluded on purpose, so 30 would sit ON a population
this module already refuses rather than clear of it.

MEASURED ON PRODUCTION 2026-09-21 23:5xZ over every season-variant row we hold —
`icehockey_nhl_preseason` is the only such key with any event in 21 days, 15
rows — joined to its `icehockey_nhl` parent on both club names within ±12h:

    pairs found                    13
    kick-off disagreement          5.00 min min, 9.45 min max, 8.5 min typical
    parent carries `espn_id`       13 of 13
    variant carries `espn_id`       0 of 13
    scores agree                   12 of 13 (the 13th is LIVE — see below)

Every observed pair is under ten minutes and the class has one shape: the
ESPN-born row lands on the parent key on the hour, the Odds-API-born row lands
on the variant key eight minutes later. Fifteen minutes is that reading plus
margin for a slower ingest, chosen to sit in the empty band between 9.45 and the
30-minute class rather than fitted to its own maximum.
"""

#: The statuses this pass will act on. A game IN PROGRESS is excluded, and the
#: exclusion is MEASURED rather than cautious: of the 13 pairs above, 6 were live
#: at the time of reading and the ONLY pair whose two rows disagreed about the
#: score was one of them (`15316896`/`15312807`, Wild at Blackhawks). While a
#: game is live the asymmetry this pass can read — which row wears the variant
#: key — is outranked by one it cannot: which row's score is current. Folding
#: then risks electing the stale copy and showing a wrong score as the only
#: score, which is worse than showing the game twice. So a live twin stays
#: double and belongs to the event graph (#2693), exactly as the sibling pass in
#: `search_fixture_dedup` decided for the same population on the same day.
_VARIANT_COLLAPSIBLE_STATUSES: frozenset = frozenset(
    {"scheduled", "completed", "closed"}
)


def _variant_group_is_collapsible(members: list) -> bool:
    """True when no row in the group is in a state this pass refuses to fold."""
    return all(
        str(getattr(member, "status", "") or "").strip().lower()
        in _VARIANT_COLLAPSIBLE_STATUSES
        for member in members
    )


def _group_has_season_variant(members: list) -> Optional[bool]:
    """``True``/``False`` when every row in the group agrees, ``None`` when not.

    A group is one strict key, so its rows already share a league and a minute —
    but not necessarily a sport key, because :func:`league_identity` put the
    parent and its variant in the SAME group whenever they also share a minute
    (#2866, which is why the 47 NFL preseason pairs never reach this pass). Such
    a group is already folded and has nothing to ask of a neighbour, so it
    answers ``None`` and is skipped rather than being forced to one side of an
    asymmetry it does not have. A THIRD row for that fixture, on the variant key
    a few minutes off, therefore stays a second card — an unmeasured shape (no
    production fixture holds three rows across these two keys today) left to the
    event graph rather than folded on a guess.
    ``test_a_group_that_already_holds_both_sides_is_left_alone`` pins it, so
    changing it has to be a decision.

    ``None`` is also the answer when the caller did not eager-load
    ``Event.sport``. That branch is UNREACHABLE from :func:`fold_twin_events`
    today, and it is kept as a precondition rather than sold as a guard: a row
    whose sport is not in memory is absent from the identity map, so element 0
    of its key falls back to the raw ``sport_id`` and can never equal the string
    identity a loaded row carries — the two land in different buckets and are
    never compared. Mutation-verified 2026-09-22: reading the missing key as the
    PARENT instead changes no test, and the arm below that looks like it covers
    this is really pinning the bucket.
    """
    seen = set()
    for member in members:
        sport_key = loaded_sport_key(member)
        if not sport_key:
            return None
        seen.add(is_season_variant(sport_key))
    if len(seen) != 1:
        return None
    return seen.pop()


def _merge_season_variant_kickoffs(
    groups: dict[tuple, list],
) -> dict[tuple, list]:
    """Merge a parent-league group with its season-variant twin a few minutes off.

    #7915 — THE GAP BETWEEN PASS ONE AND PASS TWO, AND WHY NEITHER REACHES IT.
    The strict key has been league-aware since #2866, so `icehockey_nhl` and
    `icehockey_nhl_preseason` land in one group WHENEVER THEY SHARE A MINUTE —
    that is what closed the 47 NFL preseason pairs, whose two providers both
    store the hour exactly. NHL's two providers do not: measured 2026-09-21, all
    13 live preseason pairs sit 5 to 9 minutes apart, so element 3 of the key
    differs and the strict pass leaves them as two groups. The soccer pass below
    is the only thing that widens the clock, and it is soccer-gated on purpose.
    So a season-variant twin whose providers disagree by minutes falls between
    the two, and `/api/teams/calgary-flames` served RECENT RESULTS as
    "vs Seattle Kraken · L 2–4" twice, above a 0-0-0 record — the same fixture
    as two cards, which is the bug this whole module exists to stop.

    WHY THIS IS A SEPARATE PASS AND NOT A WIDER `SOCCER_KICKOFF_DRIFT`. Widening
    that bound would reach the two populations its own docstring says it stays
    clear of (the 30-minute re-mints #5918 refuses, the three-hour Kalshi rows
    #5905 corrects) and would apply a token-subset name rule — the one that
    cannot tell `Miami` from `Miami (OH)` — to leagues it was never measured on.
    This pass instead keeps the strict key's EXACT squashed names and adds one
    clause the soccer pass has no use for: the two groups must be asymmetric,
    one wearing a season-variant key and the other its parent's.

    THAT ASYMMETRY IS THE WHOLE LICENCE, AND IT IS ALSO THE BLAST RADIUS. Only a
    league with a `*_preseason` / `*_summer_league` key can satisfy it, so this
    pass is structurally unable to fire on any soccer row — no soccer key has a
    season variant (:func:`_soccer_bucket_key` says so, and a guard asserts it) —
    and therefore cannot disturb the populations measured above. Two rows sharing
    a sport key are the symmetric case this module already refuses to guess
    between, and they stay refused: nothing here looks at them.

    Returns a dict so the soccer pass downstream still receives groups keyed the
    way it expects. A merged group is filed under the key of its EARLIEST
    KICK-OFF and takes the position of whichever of its members the strict key
    made first, so a caller serving no season-variant row gets a dict that is
    byte-identical to the one it gets today — the early return below makes that
    the same object, not a copy of it.
    """
    buckets: dict[tuple, list[tuple]] = {}
    for key in groups:
        buckets.setdefault(_soccer_bucket_key(key), []).append(key)

    merged_into: dict[tuple, tuple] = {}
    for bucket_keys in buckets.values():
        if len(bucket_keys) < 2:
            continue
        for cluster in _season_variant_clusters(bucket_keys, groups):
            target = cluster[0]
            for other in cluster[1:]:
                merged_into[other] = target

    if not merged_into:
        return groups

    out: dict[tuple, list] = {}
    for key, members in groups.items():
        target = merged_into.get(key, key)
        if target in out:
            out[target].extend(members)
            continue
        out[target] = list(members)
    return out


def _season_variant_clusters(
    bucket_keys: list[tuple], groups: dict[tuple, list]
) -> list[list]:
    """Cliques of keys inside one bucket that are one fixture under this licence.

    The clique refusal is the same safety :func:`_name_clusters` carries and it
    is load-bearing for the same reason: the drift bound is NOT transitive, so
    three groups at 0, 12 and 24 minutes must not become one card by standing
    next to each other.

    WHAT ACTUALLY REFUSES THAT CHAIN HERE IS THE ASYMMETRY, NOT THE CLOCK, and
    saying so is the difference between a guard and a decoration. Parent and
    variant are the only two sides there are, so any cluster of three or more
    holds two groups on the SAME side; `same_fixture` refuses that pair, and the
    whole cluster is discarded. A cluster that survives is therefore always
    exactly two groups, and the sliding window below has already proved those
    two are inside the bound. That is why the clock is expressed once, in the
    window, and not a second time in the predicate.
    """
    collapsible = {}
    variant = {}
    for key in bucket_keys:
        members = groups[key]
        collapsible[key] = _variant_group_is_collapsible(members)
        variant[key] = _group_has_season_variant(members)

    eligible = [
        key for key in bucket_keys if collapsible[key] and variant[key] is not None
    ]
    if len(eligible) < 2:
        return []

    def same_fixture(left: tuple, right: tuple) -> bool:
        """The name and asymmetry halves. THE CLOCK IS NOT HERE, ON PURPOSE.

        A copy of the drift bound in this predicate is unreachable, and it was
        kept for one mutation round before being removed rather than guarded.
        Two things make it dead: the window below never offers this function a
        pair wider than the bound, and a cluster that SURVIVES is always exactly
        two groups — any cluster of three or more must contain two groups on the
        same side of the parent/variant asymmetry, which the first clause
        refuses, so the clique test discards it whole before a clock question
        could decide anything. Mutation-verified 2026-09-22: with the bound in
        both places, deleting either copy alone changed no test, which is the
        signature of a rule with two implementations rather than a rule with a
        backstop. The window is now the single expression of it.
        """
        # The asymmetry first: it is a dict lookup, it is the clause that makes
        # this pass legal at all, and it refuses most candidate pairs outright.
        if variant[left] == variant[right]:
            return False
        # Elements 1 and 2 are the squashed away/home names the strict key
        # already built, orientation kept. Equality, not a subset rule.
        return left[1] == right[1] and left[2] == right[2]

    ordered = sorted(eligible, key=lambda k: k[3])
    parent = {key: key for key in ordered}

    def find(key: tuple) -> tuple:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    # THE CLOCK RULE, EXPRESSED ONCE. `ordered` is ascending, so this break is
    # not merely an optimisation that skips pairs already refused (which is what
    # the soccer loop's identical shape is): it IS the drift bound for this pass.
    # A second copy inside `same_fixture` was unreachable and was deleted rather
    # than kept as a decoration — that function's docstring carries the proof.
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if right[3] - left[3] > SEASON_VARIANT_KICKOFF_DRIFT:
                break
            if same_fixture(left, right):
                parent[find(right)] = find(left)

    clusters: dict[tuple, list] = {}
    for key in ordered:
        clusters.setdefault(find(key), []).append(key)

    out: list[list] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        # Clique or nothing — a merely connected chain is discarded whole.
        if all(
            same_fixture(left, right)
            for i, left in enumerate(members)
            for right in members[i + 1 :]
        ):
            out.append(members)
    return out


ANCHORED_CLAIM_KICKOFF_DRIFT = timedelta(minutes=12)
"""How far apart an id-less CLAIM and the anchored row it names may sit. #8100.

Sized the way :data:`SOCCER_KICKOFF_DRIFT` and
:data:`SEASON_VARIANT_KICKOFF_DRIFT` are sized — from the measured band, placed
in the empty space below the nearest population — and it is NOT 15 minutes,
which is what the issue proposed before the reading was taken.

MEASURED ON PRODUCTION 2026-09-22 23:4xZ over the WHOLE `events` table (241,300
rows, `2001-01-02` → `2028-07-30`), by a window pass rather than a self-join:
partition by `sport_id` and both squashed club names, order by `commence_time`,
and take every adjacent pair more than 0 and at most 15 minutes apart. Then
split that population by whether the two sides agree about carrying a provider
id (:func:`_group_is_id_anchored`'s pair of columns):

    both id-less        954 pairs   5 sports   0 two-espn_id   0 two-scoreline
    both anchored        16 pairs   5 sports   0 two-espn_id   5 two-scoreline
    ASYMMETRIC           15 pairs   3 sports   0 two-espn_id   1 two-scoreline

Only the third row is this pass's population, and the first two are why the
asymmetry is the licence rather than the clock: 954 of the 985 pairs are the
`esports` / `esports_other` bulk the issue could not bound, and the asymmetry
refuses every one of them without naming a sport. The `both anchored` row is the
same refusal earning its keep from the other side — five of those sixteen hold
two DIFFERENT scorelines, which is two real games, and two anchored rows are the
symmetric case this module has always refused to guess between.

THE BOUND ITSELF, from the asymmetric pairs' gap distribution out to four hours:

    0.4 – 9.7 min    14 pairs   basketball_nbl · baseball_mlb · mma
    15.0, 19.8 min    2 pairs
    24.9 … 55 min     6 pairs
    180.0 min         5 pairs   (the Kalshi expected-expiration class, #5905)

So the observed class ends at 9.7 minutes and the nearest neighbour above it is
at 15.0. Twelve sits in that empty band: clear above the population it is for,
clear below the first pair it is not. Fifteen — the number #8100 proposed — would
sit exactly ON a pair rather than clear of it, which is the "fitted to its own
maximum" mistake :data:`SEASON_VARIANT_KICKOFF_DRIFT` records avoiding.

The reader-reachable defect that named this ship sits at 6.0 minutes:
`/search?q=Perth+Wildcats` served `15314490` (Polymarket-born, no provider id,
holding the only price — `{"polymarket": 0.41}`) at 11:30Z above `15316489`
(Odds-API-born, `external_id` set, no sources, no odds, nothing at all) at
11:36Z, as `NBL Sep 24 4:30 AM Perth 41%` above `NBL Sep 24 4:36 AM Perth
(No price yet)`.

Chaining is not a way around it, and here the clock is not even what refuses the
chain — see :func:`_anchored_claim_clusters`.
"""


def _merge_anchored_claim_kickoffs(groups: dict[tuple, list]) -> dict[tuple, list]:
    """Merge an id-less claim group onto the anchored group it names, minutes off.

    #8100 — THE GAP BETWEEN EVERY EXISTING PASS, AND WHY NONE OF THEM REACHES IT.
    The strict key is exact-minute, so a pair that disagrees by six minutes is two
    groups. :func:`_merge_soccer_name_variants` is the only pass that widens the
    clock for two rows sharing a sport key, and it is soccer-gated on purpose.
    :func:`_merge_season_variant_kickoffs` widens the clock without a name rule,
    but its licence is a LEAGUE asymmetry — one row on a `*_preseason` key, one on
    its parent's — which two `basketball_nbl` rows cannot satisfy. So an NBL game
    whose two providers disagree by six minutes falls between all three and
    `/search?q=Perth+Wildcats` served it twice, once with the price and once with
    "No price yet".

    THE LICENCE IS A PROVENANCE ASYMMETRY, AND IT IS RULING 048 READ FORWARD.
    A row carrying neither `espn_id` nor `external_id` is an id-less CLAIM: gotcha
    #32 says such a row could only ever have CREATED, never absorbed, which is
    exactly why both rows exist and why `event_provider_anchors` has nothing to
    drain here. It is not independent evidence of a second game. A row carrying a
    provider's id was reported by somebody who knows the fixture BY id. So one of
    each, on the same clubs, minutes apart, is one game recorded twice — while two
    ANCHORED rows are two games (five of the sixteen measured pairs prove it with
    two scorelines) and two ID-LESS rows are a question nobody here can answer.
    :func:`_star_on_one_anchor` reached the same conclusion for a soccer cluster
    from the other direction; this is that reasoning as a pass's whole admission
    test rather than as a rescue for one cluster shape.

    NOTHING HERE ASKS FOR AN ABSORPTION, A REGISTRY OR A MATCHER CHANGE. Both rows
    stay in the table and stay correct. This is the serve-time fold, the only
    repair #8100 asks for, and loosening absorption was put to Alex on 2026-08-20
    and REJECTED.

    WHY THIS IS NOT A WIDER `SOCCER_KICKOFF_DRIFT` AND NOT A WIDER SEASON-VARIANT
    PASS. The soccer bound carries a token-subset name rule — the one that cannot
    tell `Miami` from `Miami (OH)` — and widening it would apply that rule to
    leagues it was never measured on, and would reach the 30-minute re-mints #5918
    refuses. The season-variant pass cannot be widened here at all: its asymmetry
    is a property of the SPORT KEY, and relaxing it to "any two groups" is the
    symmetric case, which is the 954 id-less esports pairs. This pass keeps the
    strict key's EXACT squashed names — equality, never a subset — and adds one
    clause neither sibling has.

    It runs AFTER :func:`_merge_season_variant_kickoffs` and on the same dict for
    the same reason that pass runs on one: it is the same SHAPE of step. The two
    cannot fight over a group, because a season-variant merge only ever makes a
    group MORE anchored, and this pass reads that merged group's anchoring as it
    finds it. It runs BEFORE the soccer pass so that pass still receives a dict
    keyed the way it expects. A merged group is filed under the key of its
    EARLIEST kick-off, and the early return below hands back the same object
    rather than a copy, so a caller with nothing to merge gets byte-identical
    behaviour to before #8100.
    """
    buckets: dict[tuple, list[tuple]] = {}
    for key in groups:
        buckets.setdefault(_soccer_bucket_key(key), []).append(key)

    merged_into: dict[tuple, tuple] = {}
    for bucket_keys in buckets.values():
        if len(bucket_keys) < 2:
            continue
        for cluster in _anchored_claim_clusters(bucket_keys, groups):
            target = cluster[0]
            for other in cluster[1:]:
                merged_into[other] = target

    if not merged_into:
        return groups

    out: dict[tuple, list] = {}
    for key, members in groups.items():
        target = merged_into.get(key, key)
        if target in out:
            out[target].extend(members)
            continue
        out[target] = list(members)
    return out


def _anchored_claim_clusters(
    bucket_keys: list[tuple], groups: dict[tuple, list]
) -> list[list]:
    """Cliques of keys inside one bucket that are one fixture under this licence.

    WHAT REFUSES A CHAIN HERE IS THE ASYMMETRY, NOT THE CLOCK — the same thing
    :func:`_season_variant_clusters` records, and it holds for the same reason.
    Anchored and id-less are the only two sides there are, so any cluster of three
    or more holds two groups on the SAME side, `same_fixture` refuses that pair,
    and the clique test below discards the whole cluster. A cluster that survives
    is therefore always exactly two groups, and the sliding window has already
    proved those two are inside the bound. That is why the drift is expressed
    once, in the window, and is not restated in the predicate: a second copy would
    be unreachable, and an unreachable copy of a rule is what
    :func:`_season_variant_clusters` deleted rather than kept as a decoration.

    Three refusals, and each leaves both rows standing — two cards, today's
    behaviour — rather than risking one card holding two games:

    * :func:`_variant_group_is_collapsible` — a LIVE row is not folded. Measured
      inert on this pass's population today (all 15 asymmetric pairs are
      `scheduled`, `completed` or `closed`), and kept because the reason the
      sibling pass gives is about this pass's own hazard: while a game is live the
      asymmetry this can read is outranked by one it cannot, which row's score is
      current, and electing the stale copy shows a wrong score as the only score.
    * the asymmetry itself, which is the licence.
    * :func:`_objectively_different_games` — and this one is ARMED rather than
      decorative, which is the control #8100 said it could not find. One of the 15
      asymmetric pairs holds two different scorelines and is refused by it. Its
      `espn_id` arm is a different matter and is not sold as a guard: an id-less
      group has no `espn_id` by construction, so that arm can only ever fire on a
      group that already holds two of them, which the strict key would have had to
      build. It is called for the scoreline half and inherited whole rather than
      reimplemented.
    """
    collapsible = {}
    anchored = {}
    for key in bucket_keys:
        members = groups[key]
        collapsible[key] = _variant_group_is_collapsible(members)
        anchored[key] = _group_is_id_anchored(members)

    eligible = [key for key in bucket_keys if collapsible[key]]
    if len(eligible) < 2:
        return []

    def same_fixture(left: tuple, right: tuple) -> bool:
        """The asymmetry, the names and the evidence. THE CLOCK IS NOT HERE."""
        # The asymmetry first: it is a dict lookup, it is the clause that makes
        # this pass legal at all, and it refuses 970 of the 985 measured pairs.
        if anchored[left] == anchored[right]:
            return False
        # Elements 1 and 2 are the squashed away/home names the strict key
        # already built, orientation kept. Equality, not a subset rule.
        if left[1] != right[1] or left[2] != right[2]:
            return False
        return not _objectively_different_games(groups[left], groups[right])

    ordered = sorted(eligible, key=lambda k: k[3])
    parent = {key: key for key in ordered}

    def find(key: tuple) -> tuple:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    # THE CLOCK RULE, EXPRESSED ONCE. `ordered` is ascending, so this break IS the
    # drift bound for this pass rather than an optimisation over pairs already
    # refused.
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if right[3] - left[3] > ANCHORED_CLAIM_KICKOFF_DRIFT:
                break
            if same_fixture(left, right):
                parent[find(right)] = find(left)

    clusters: dict[tuple, list] = {}
    for key in ordered:
        clusters.setdefault(find(key), []).append(key)

    out: list[list] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        # Clique or nothing — a merely connected chain is discarded whole.
        if all(
            same_fixture(left, right)
            for i, left in enumerate(members)
            for right in members[i + 1 :]
        ):
            out.append(members)
    return out


def _name_tokens(name: Optional[str]) -> frozenset:
    """The WORDS of a team name, diacritic-free and lowercased.

    The same normalisation :func:`_squash` applies, stopped one step earlier: it
    keeps the word boundaries instead of deleting them, so `Hiroshima Toyo Carp`
    is `{hiroshima, toyo, carp}` rather than `hiroshimatoyocarp`.

    NOT :func:`app.utils.soccer_team_matching.club_alias_tokens`, which is the
    tokenizer the soccer pass uses. That one also applies two soccer alias tables
    and strips club-form words, and both of those are statements about football
    clubs that nobody has measured on `baseball_npb` or `basketball_wncaab`. This
    pass runs on every sport, so it uses the plainest rule there is — and the
    plain rule is the one the #8100 census below was taken with, which is the
    whole reason to prefer it. :func:`_names_a_different_squad` still gets the
    alias tokenizer, because the marker it looks for is a soccer marker.
    """
    return frozenset(_NON_ALNUM.sub(" ", strip_diacritics(name or "").lower()).split())


def _one_club_named_twice(left: Optional[str], right: Optional[str]) -> bool:
    """Is one of these two names the other's, with extra words? #8100.

    `Hiroshima Carp` ⊆ `Hiroshima Toyo Carp`; `Tottenham` ⊆ `Tottenham Hotspur`;
    `Atletico` ⊆ `Atlético Madrid`. A SET containment in either direction, so
    which provider wrote the longer form does not matter, and equality of the
    token sets counts — `Long Beach State Beach` and `Long Beach State Dirtbags`
    reach each other only because the repeated word collapses, and two spellings
    that differ only in word ORDER are one club by the same reading.

    The empty-token branch is a PRECONDITION, not a control, and is stated that
    way because mutation says so: deleting it changes no test.
    :func:`twin_fold_key` returns ``None`` for a row whose squashed name is
    empty, so such a row is never keyed, never grouped and never reaches this
    function — the branch is unreachable from :func:`fold_twin_events`. It is
    kept for a direct caller, since an empty set is a subset of everything and
    the answer would otherwise be ``True``.

    THIS PREDICATE IS NOT SAFE ON ITS OWN AND IS NEVER ASKED ON ITS OWN.
    `Georgia` ⊆ `West Georgia` and `Florida` ⊆ `North Florida` are both true, and
    production holds the pair that proves it: `14706238` *Georgia v Florida* and
    `14707767` *West Georgia v North Florida*, same league, same minute
    (2026-05-14 22:05Z), asymmetric provenance, no score on either row and no
    `espn_id` conflict — so neither of this module's objective controls refuses
    it. It is two real games. :func:`_anchored_claim_name_clusters` is what keeps
    that pair apart, by refusing to ask this question about BOTH sides of a
    fixture at once; see its docstring, which is where the licence lives.
    """
    left_tokens = _name_tokens(left)
    right_tokens = _name_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    return left_tokens <= right_tokens or right_tokens <= left_tokens


def _merge_anchored_claim_name_variants(groups: dict[tuple, list]) -> dict[tuple, list]:
    """Merge an id-less claim onto the anchored row it names, spelled longer. #8100.

    THE SHIP. `bainluck.com/sports/baseball_npb` at 390px, 2026-09-23 00:5xZ,
    served tomorrow's Carp game as two adjacent cards with two different answers
    — `Hiroshima Toyo Carp 54% / Yomiuri Giants 46%` directly above `Hiroshima
    Carp 56% / Yomiuri Giants 44%` — and the BayStars game the same way
    (`Yokohama BayStars 61%` above `Yokohama DeNA BayStars 60%`). Same league,
    the SAME MINUTE, one club named two ways. `/api/leagues/baseball_npb` →
    `upcoming_games` carries all four rows; frame in
    `artifacts-lane1-606/BEFORE-npb-league-8100.png`.

    THIS IS #8100's SECOND PROPOSAL AND THE OTHER HALF OF ITS FIRST.
    :func:`_merge_anchored_claim_kickoffs` widened the CLOCK and kept the names
    exact; this widens the NAMES and keeps the clock exact — element 3 of the
    strict key, untouched, which is why the two passes cannot reach each other's
    population and why neither inherits the other's bound. Both take the same
    licence, and that is the finding this pass exists on rather than a
    convenience: the PROVENANCE ASYMMETRY carries the name question too.

    THE MEASUREMENT #8100 ASKED FOR, AND IT ANSWERS THE OBJECTION IN THE ISSUE.
    The issue's reason for not building this was that "a token-subset rule
    applied fleet-wide meets the `tennis_other` cluster first" — ~25 rows for one
    match at one instant, `Abe v Lu` beside `Hiromi Abe v Jia-Jing Lu`. Taken on
    production 2026-09-23 00:5x–01:2xZ over the WHOLE `events` table, all time,
    every sport, counting adjacent pairs inside one `(sport_id, minute)` bucket
    whose names are token-subset related, split by whether the two sides agree
    about carrying a provider id:

        BOTH sides differ        3,810 pairs      135 asymmetric
          of which tennis_other  3,111 pairs        0 asymmetric
          of which tennis_atp      687 pairs      127 asymmetric
          of which esports           0 pairs        0 asymmetric
        ONE side IDENTICAL         251 pairs       22 asymmetric

    The asymmetry refuses the entire `tennis_other` cluster — 3,111 pairs, not
    one of them asymmetric — so the thing the issue could not bound is bounded by
    the licence and not by a sport name, exactly as the 954 id-less `esports`
    pairs were on the clock half.

    AND THEN THE NARROWER SHAPE IS TAKEN ANYWAY, BECAUSE THE ASYMMETRY IS NOT
    ENOUGH BY ITSELF. Of the 135 asymmetric both-sides pairs, 134 are one fixture
    named two ways (127 are `tennis_atp` surname-versus-full-name, `Zhang v
    Pinnington Jones` beside `Zhizhen Zhang v Jack Pinnington Jones`) and ONE is
    two real games: the `West Georgia v North Florida` / `Georgia v Florida` pair
    quoted in :func:`_one_club_named_twice`. One measured false fold is one too
    many when the alternative costs nothing the ship needs, so this pass requires
    ONE SIDE TO BE SQUASH-IDENTICAL and lets the token rule adjudicate only the
    other. All 22 asymmetric pairs in that population were read by hand and all
    22 are one fixture; both NPB pairs are in it and the `West Georgia` pair is
    structurally out of reach rather than merely absent.

    AND IT IS OFF IN SOCCER, WHICH IS A COLLISION RULE AND NOT A HAZARD RULE.
    `_merge_soccer_name_variants` is already a token-subset rule with its own
    measured bound and its own non-clique rescue, and it reaches every one of
    the twelve soccer pairs in the census above. Two owners on one question cost
    #6047's page; the skip and the measurement behind it are in the loop below.

    WHY "ONE SIDE EXACT" IS A LICENCE AND NOT A THRESHOLD. Exact agreement on one
    club is independent corroboration that survives the name rule being wrong.
    Two genuinely different games that agree on a league, on the exact minute and
    on one team EXACTLY would be that team playing two fixtures at one instant,
    which is not a thing; two games that agree on a league and a minute and
    nothing else — the both-sides case — is `West Georgia v North Florida`. So
    the pass does not weigh how alike the names are; it asks for a fact the names
    cannot fake, and only then reads the names.

    NOTHING HERE WRITES, ABSORBS, OR TOUCHES THE REGISTRY. Both rows stay in the
    table and stay correct — they exist because ruling 048 / gotcha #32 make an
    id-less Polymarket-minted row unable to absorb the later `odds_api` claim,
    which is the same story #8100's first half records. Loosening absorption was
    put to Alex on 2026-08-20 and REJECTED.

    It runs immediately after :func:`_merge_anchored_claim_kickoffs`, on the same
    dict, for the same reason that pass runs on one: same shape of step. Order
    between the two does not change any outcome — the clock pass only ever makes
    a group hold MORE rows and this pass reads anchoring and names, both of which
    a merge can only strengthen — and it is written this way round so the soccer
    pass downstream still receives a dict keyed the way it expects. With nothing
    to merge the same object is handed back, so a caller whose page holds no such
    pair gets byte-identical behaviour to before #8100.
    """
    buckets: dict[tuple, list[tuple]] = {}
    for key in groups:
        # THE BUCKET IS THE STRICT KEY'S OWN CLOCK — league and exact minute.
        # This pass widens names only; the drift question is the sibling's.
        buckets.setdefault((key[0], key[3]), []).append(key)

    merged_into: dict[tuple, tuple] = {}
    for bucket_keys in buckets.values():
        if len(bucket_keys) < 2:
            continue
        sport_key = loaded_sport_key(_group_representative(groups[bucket_keys[0]]))
        if not sport_key or sport_key.startswith("soccer"):
            # SOCCER ALREADY HAS A NAME PASS, AND A SECOND ONE MAKES THAT PAGE
            # WORSE RATHER THAN BETTER. Measured: all twelve soccer pairs in the
            # census above are reached by `soccer_pair_matches` today, so this
            # pass has nothing to add there — and it has something to BREAK.
            # #6047's La Liga triple is `Athletic Bilbao v Alavés` (anchored),
            # `Athletic Club v Alaves` and `Bilbao v Alaves` (both id-less); the
            # rule here folds the anchored row with `Bilbao` (a token subset,
            # asymmetric, home side exact) and leaves `Athletic Club` outside,
            # whereupon the soccer pass reads the merged group by its lowest-id
            # member — `Bilbao` — and `Bilbao` ≡ `Athletic Club` is the one pair
            # its name rule cannot make. The star rescue never fires and the
            # reader gets two cards instead of one. Running this pass after the
            # soccer one instead would be the other repair; it is not taken
            # because there is no measured pair it would win.
            #
            # An unloaded `Event.sport` is skipped for the same reason, fail
            # closed: this pass cannot prove the bucket is not soccer. That
            # branch is unreachable from `fold_twin_events`, which eager-loads.
            continue
        for cluster in _anchored_claim_name_clusters(bucket_keys, groups):
            target = cluster[0]
            for other in cluster[1:]:
                merged_into[other] = target

    if not merged_into:
        return groups

    out: dict[tuple, list] = {}
    for key, members in groups.items():
        target = merged_into.get(key, key)
        if target in out:
            out[target].extend(members)
            continue
        out[target] = list(members)
    return out


def _anchored_claim_name_clusters(
    bucket_keys: list[tuple], groups: dict[tuple, list]
) -> list[list]:
    """Cliques of same-minute keys that are one fixture under the name licence.

    FOUR REFUSALS, and each leaves both rows standing — two cards, today's
    behaviour — rather than risking one card holding two games:

    * :func:`_variant_group_is_collapsible` — a LIVE row is not folded. Measured
      inert on this pass's population (every one of the 22 asymmetric pairs is
      `scheduled`, `completed` or `closed`) and kept for the reason its two
      sibling passes keep it: while a game is live, the asymmetry this can read
      is outranked by one it cannot — which row's score is current — and electing
      the stale copy shows a wrong score as the only score.
    * THE PROVENANCE ASYMMETRY, which is the licence, and which refuses 3,675 of
      the 3,810 measured pairs including all 3,111 of `tennis_other`.
    * THE EXACT SIDE, which is the other half of the licence. `same_away ==
      same_home` is the whole clause: both False is the both-sides case and is
      where the one measured false fold lives, and both True is unreachable —
      two keys agreeing on league, minute and BOTH squashed names are one key,
      so the strict key never made them two groups.
    * :func:`_objectively_different_games`, whose scoreline half is what refuses
      a pair the names cannot tell apart.

    THERE IS NO SQUAD REFUSAL HERE, AND ITS ABSENCE IS A FINDING RATHER THAN AN
    OVERSIGHT. A reserve side's name is a strict token SUPERSET of its first
    team's — `Ajax` ⊆ `Jong Ajax` — so :func:`_names_a_different_squad` looks
    like exactly the guard this pass's name rule needs, and it was written in
    before the soccer skip was. It is UNREACHABLE from here: `jong` and
    `amateurs` are Dutch football markers, every football key begins `soccer`,
    and this pass skips every one of them. An unreachable copy of a rule reads
    as protection and is not protection — the same thing
    :func:`_season_variant_clusters` deleted rather than kept as a decoration —
    so it is gone, and the soccer skip is what actually answers the case.
    (`soccer_pair_matches(('Feyenoord','Ajax'), ('Feyenoord','Jong Ajax'))` is
    `True` on master, so the soccer pass has its own answer and this is not it.)

    CHAINING IS REFUSED BY THE CLIQUE TEST, AND UNLIKE THE SIBLING PASS THAT IS
    LOAD-BEARING HERE. :func:`_anchored_claim_clusters` could prove a surviving
    cluster is always exactly two groups, because anchored and id-less are the
    only two sides there are. That argument does NOT hold once the bucket is a
    minute: production has one id-less esports row at 2026-04-21 21:30Z beside
    THREE anchored Kalshi rows spelled `Outfit 49 (900FPSvsECO)`, so three pairs
    are asymmetric, the three anchored-to-anchored pairs are not, and the clique
    test discards the cluster whole. That is the right answer — a fold would have
    had to choose which of three anchored rows the claim belongs to — and it is
    the reason the test is here rather than an argument for removing it.
    """
    collapsible: dict[tuple, bool] = {}
    anchored: dict[tuple, bool] = {}
    names: dict[tuple, tuple] = {}
    for key in bucket_keys:
        members = groups[key]
        collapsible[key] = _variant_group_is_collapsible(members)
        anchored[key] = _group_is_id_anchored(members)
        rep = _group_representative(members)
        names[key] = (
            getattr(rep, "away_team_name", None),
            getattr(rep, "home_team_name", None),
        )

    eligible = [key for key in bucket_keys if collapsible[key]]
    if len(eligible) < 2:
        return []

    def same_fixture(left: tuple, right: tuple) -> bool:
        """The asymmetry, the exact side, the names and the evidence."""
        # The asymmetry first: a dict lookup, and the clause that makes this pass
        # legal at all. It alone refuses 96.5% of the measured population.
        if anchored[left] == anchored[right]:
            return False
        # Elements 1 and 2 are the squashed away and home names the strict key
        # already built, orientation kept. EXACTLY one of them must be equal.
        same_away = left[1] == right[1]
        same_home = left[2] == right[2]
        if same_away == same_home:
            return False
        disputed = 1 if same_away else 0
        if not _one_club_named_twice(names[left][disputed], names[right][disputed]):
            return False
        return not _objectively_different_games(groups[left], groups[right])

    # Every key in a bucket shares element 3, so there is no time order to walk
    # and no sliding window to have: the bucket IS the clock rule. Sorted on the
    # two name elements purely so the surviving cluster's target does not depend
    # on dict order — `_elect` picks the survivor, this only picks the label.
    ordered = sorted(eligible, key=lambda key: (key[1], key[2]))
    parent = {key: key for key in ordered}

    def find(key: tuple) -> tuple:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if same_fixture(left, right):
                parent[find(right)] = find(left)

    clusters: dict[tuple, list] = {}
    for key in ordered:
        clusters.setdefault(find(key), []).append(key)

    out: list[list] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        # Clique or nothing — a merely connected chain is discarded whole.
        if all(
            same_fixture(left, right)
            for i, left in enumerate(members)
            for right in members[i + 1 :]
        ):
            out.append(members)
        else:
            logger.info(
                "twin fold: refused a non-clique anchored-claim name cluster %s",
                [names[key] for key in members],
            )
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
        disputed = set(club_alias_tokens(left_name)) ^ set(
            club_alias_tokens(right_name)
        )
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
                if not _pair_matches_after_transliteration(names(index), names(target)):
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


#: The ASCII digraphs that spell the letters :func:`strip_diacritics` already
#: folds to a SINGLE letter, mapped back to that letter.
#:
#: `ø`, `ö`, `å` have two conventional ASCII spellings and the providers do not
#: agree on which to use: `strip_diacritics` writes the single letter
#: (`Lillestrøm` → `Lillestrom`, the Odds API's own spelling), while Kalshi
#: writes the digraph (`Lillestroem`). Both are the same club and neither is
#: wrong, so the squash has to be asked the question a second way.
#:
#: MEASURED, NOT REASONED ABOUT — and it is why `ss` is absent. Over every
#: distinct soccer club name in the table, all 9,471 of them, collapsing each
#: digraph and counting the squashed forms that newly collide:
#:
#:     oe -> o   5 groups   bodo(e)glimt · br(o|oe)ndby · lillestr(o|oe)m
#:                          s(o|oe)nderjyske · troms(o|oe)   — all one club
#:     aa -> a   1 group    vaster(a|aa)ssk (Västerås SK)    — one club
#:     ae -> a   0 groups   inert on this population
#:     ue -> u   0 groups   inert on this population
#:     ss -> s   2 groups   alnasr/alnassr · progreso/progresso
#:
#: `ae`/`ue` are left out because they buy nothing here; `ss` is left out
#: because it is WRONG — Al Nasr and Al Nassr are different clubs, and the
#: guard file pins that pair so nobody adds the rule back by symmetry.
_TRANSLITERATION_DIGRAPHS = re.compile(r"oe|aa", re.IGNORECASE)


def _collapse_transliteration(name: Optional[str]) -> Optional[str]:
    """`Lillestroem` → `Lillestrom`. Case is preserved, not folded.

    The replacement keeps the case of the digraph's first letter so the string
    handed back has the same shape as the one that came in — `soccer_team_matches`
    reads capitals when it falls back to initials, and a blanket `.lower()` here
    would quietly change what that half of the predicate sees.

    It collapses inside any word, not only Nordic ones — `Phoenix` becomes
    `Phonix` — and that is deliberate rather than tolerated. This form is only
    ever compared against another string put through the same function, so a
    mangling both sides share cannot separate them; and the census above is what
    says it cannot JOIN two clubs either, `Phoenix` included.
    """
    if not name:
        return name
    return _TRANSLITERATION_DIGRAPHS.sub(lambda m: m.group(0)[0], name)


def _pair_matches_after_transliteration(left: tuple, right: tuple) -> bool:
    """:func:`soccer_pair_matches`, retried once on the collapsed spellings.

    STRICTLY ADDITIVE BY CONSTRUCTION, which is the whole reason it is a retry
    rather than a new normaliser inside the squash. The strict call is asked
    first and its `True` is returned untouched, so no pair that folds today can
    stop folding — the failure mode that killed the club-suffix fold proposed on
    #6221, where `Sevilla v Valencia` was decidable before the widening and
    ambiguous after it, is unreachable from this shape.

    It is also why this lives here and not in
    :func:`app.utils.soccer_team_matching.soccer_pair_matches`. That predicate is
    also the match rule for `stamp_v1_statpal_fixtures`, which WRITES anchors;
    widening a writer is a different class of change with a different bar, and
    this ship does not need it. The fold is a serve-time pass over rows that are
    already on the page.
    """
    if soccer_pair_matches(left, right):
        return True
    folded_left = tuple(_collapse_transliteration(name) for name in left)
    folded_right = tuple(_collapse_transliteration(name) for name in right)
    if folded_left == tuple(left) and folded_right == tuple(right):
        # Nothing collapsed, so the retry is the same question. Most pairs.
        return False
    return soccer_pair_matches(folded_left, folded_right)


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
    return _pair_matches_after_transliteration(left, right)


def _group_is_id_anchored(members: list) -> bool:
    """Does any row in this group carry a provider's id for the fixture? #6047.

    `espn_id` or `external_id`, which is the same pair of columns
    :func:`twin_identity_rank` ranks an anchor by and the same test
    `kalshi_occurrence_scheduled_start` calls "a schedule provider reported this
    start". A row with either was reported by somebody who knows the fixture by
    id; a row with neither is a claim (ruling 048 / gotcha #32) that could only
    ever CREATE.
    """
    for member in members:
        if getattr(member, "espn_id", None) is not None:
            return True
        if getattr(member, "external_id", None) is not None:
            return True
    return False


def _star_on_one_anchor(
    members: list, groups: dict[tuple, list], same_fixture: Any
) -> bool:
    """May this non-clique cluster fold anyway, because one anchor centres it? #6047.

    THE DEFECT THIS EXISTS FOR: A THIRD ROW MADE THE PAGE WORSE, NOT BETTER.
    On production 2026-09-17, `/sports/soccer_spain_la_liga` served Athletic
    Bilbao v Alavés THREE times — `15312047` (ESPN, `espn_id` 401882866,
    58%), `15312903` (Kalshi, no id, 83%) and `15307698` (Kalshi, no id) — and
    the fold dropped none of them. Driving :func:`fold_twin_events` over doubles
    of those exact rows shows why, and the shape is the whole finding:

        rows handed to the fold        dropped
        15312047 + 15312903            15312903
        15312047 + 15307698            15307698
        all three                      nothing

    Both pairs fold on master today. The predicate reaches `Athletic Bilbao` ≡
    `Athletic Club` and `Athletic Bilbao` ≡ `Bilbao`, and it does NOT reach
    `Athletic Club` ≡ `Bilbao` — two providers' short names for one club that
    share no token. So the cluster is connected but not a clique, and the
    refusal above discards it whole: a reader who would have met the fixture
    twice meets it three times BECAUSE a third row arrived.

    WHY A GENERAL DECOMPOSITION IS REFUSED AND THIS ONE IS NOT. `Madrid` ⊆
    `Real Madrid` and `Madrid` ⊆ `Atlético Madrid` is the chain
    :func:`_merge_soccer_name_variants` names, and splitting a non-clique into
    "some clique" would let a coin-flip decide which Madrid club the vague row
    joins. This function does not split anything. It asks one question about the
    cluster's SHAPE:

    * exactly one member group is id-anchored (:func:`_group_is_id_anchored`), and
    * every other member pair-matches THAT group under the caller's own
      `same_fixture` — the same names, the same drift bound, the same
      squad-marker refusal — so the cluster is a star centred on the anchor, and
    * no two member groups are :func:`_objectively_different_games`.

    Then every id-less member is a claim that it is the anchored fixture, and the
    anchored fixture is ONE real game: if X is that game and Y is that game, X
    and Y are each other's twin whatever the two short names say about one
    another. The Madrid chain fails the first clause in the direction that
    matters — its centre is the id-less row and its leaves are two anchored games
    — so it is refused exactly as it is today, and so is a chain of three id-less
    rows, which has no anchor to be a claim ABOUT.

    THE REACH IS BOUNDED BY SOMETHING ALREADY TRUE RATHER THAN BY A PROMISE:
    every pair this folds is a pair master folds when the third row is absent.
    No name rule is loosened, no bucket is widened, no clock bound moves; the
    only behaviour that changes is that a third row can no longer veto them.

    MEASURED BY DRIVING :func:`fold_twin_events` — not a re-implementation — over
    two production populations, 2026-09-17, with this rescue off and on. Each is
    folded twice: once per league page, the way a reader meets it, and once as a
    single fold over every soccer row, which is the only way the cross-league
    catch-all path (:func:`_merge_catchall_leagues`) is exercised at all:

        population / how folded              refused   rescued   rows folded
        914 `[now-3d, now+8d]`, per league     1          1        94 ->  96
        914, one fold                          1          1       154 -> 156
        6,501 `[now-30d, now+8d]`, per league  1          1       362 -> 364
        6,501, one fold                        1          1       444 -> 446

    THE HONEST READING OF THAT TABLE: over 38 days of soccer there is exactly ONE
    non-clique cluster, and it is the specimen above. This is not a class with a
    population — it is a shape the fold gets wrong whenever it appears, and it
    appeared on a top-five league page three days before the fixture. The same
    two rows are the only ones that move in all four folds; NO fold master makes
    today is lost in any of them, which is the control that matters more than the
    count.

    KNOWN RESIDUAL, STATED RATHER THAN HIDDEN. The one star this cannot tell from
    the Madrid chain is the chain wearing the anchor: an id-anchored row carrying
    the VAGUE name (`Madrid v Getafe`, with an `espn_id`) beside two id-less rows
    for two different clubs, each matching it. Counting anchors does not separate
    those, and no name rule can — the repo refuses to invent an unmeasured club
    vocabulary (:mod:`app.utils.soccer_team_matching`, "THE MISSES"). What bounds
    it is the schedule: all three rows must share one competition, one opponent
    and one minute to within :data:`SOCCER_KICKOFF_DRIFT`, so the two clubs would
    have to be playing the same opponent at the same moment. Zero clusters of any
    shape other than the specimen exist in the 6,501 rows measured above. If one
    ever does, the refusal to widen is here: the answer is a second anchor on the
    id-less rows, not a looser star.

    TWO ANCHORS ARE REFUSED EVEN WHEN EVERY MEMBER AGREES WITH ONE OF THEM, and
    that is about determinism, not caution. With two anchored groups the centre
    would be whichever the caller's query happened to return first, and the same
    three rows in the other order would fold differently — a card that changes
    with row arrival order is a worse thing than the duplicate it removes.
    """
    anchored = [key for key in members if _group_is_id_anchored(groups[key])]
    if len(anchored) != 1:
        return False
    centre = anchored[0]
    if not all(same_fixture(centre, other) for other in members if other != centre):
        return False
    return not any(
        _objectively_different_games(groups[left], groups[right])
        for i, left in enumerate(members)
        for right in members[i + 1 :]
    )


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
        elif _star_on_one_anchor(members, groups, same_fixture):
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
