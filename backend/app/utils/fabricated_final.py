"""Q506 — a FINAL nobody reported is not a FINAL. The repair half of CERT-690.

CERT-690 (``commence_time_is_a_reported_start``) stopped the PRODUCER: a row whose
``commence_time`` is a ``kalshi_ticker`` stand-in — midnight UTC of a date parsed
out of a Kalshi ticker, because Kalshi's own ``commence_time`` is a close time
(gotcha #14) — no longer has a clock run from it. Its own commit said, in as many
words, what it did NOT do:

    NOT DONE, AND NOT SILENTLY: the 705 already-closed rows are unrepaired. This
    stops the producer; it does not un-settle its output.

This module is the decision layer of that un-settling. Alex ruled D26 = (a),
2026-09-01 ~12:55pm PT, verbatim *"For D26: A!"*: **history gets fixed, not left
dirty**, and it gets fixed FROM THE AUTHORITY (``EVENT-GRAPH-DOCTRINE`` rule 3:
"scheduled -> live -> final is driven by the authority's status feed, never
inferred from markets, timers, or placeholder scores").

── THE POPULATION, MEASURED ON PRODUCTION 2026-09-01 ────────────────────────────

    SELECT status, count(*), count(*) FILTER (WHERE home_score IS NULL
                                                AND away_score IS NULL)
      FROM events WHERE commence_time_source = 'kalshi_ticker' GROUP BY 1;
    --  closed  705   unscored 705      <- the ENTIRE population, not "mostly"

    ... AND count(*) FILTER (WHERE espn_id IS NOT NULL)  ->  0
    ... AND count(*) FILTER (WHERE win_probability_sources ? 'final_result') -> 0

Three facts shape every rule below.

1. **Not one of the 705 carries a score.** Every net in this codebase settles on
   ELAPSED WALL-CLOCK, never on a result, so a settled row with no score is a row
   nothing ever reported a finish for. This is the same load-bearing conjunction
   ``settlement_is_a_staleness_artifact`` stands on, reached from the other side:
   there a SCHEDULE source contradicts the settlement, here the settlement has no
   witness at all.
2. **Not one of the 705 carries an ``espn_id``.** So the existing authority
   repair, ``scripts/repair_event_final_scores.py``, cannot touch a single row of
   this population — its ``_SETTLED_PREDICATE`` requires ``espn_id IS NOT NULL``
   *and* a stored score. This is a different cohort with a different remedy, and
   the two rails must not be confused: that one CORRECTS a wrong score, this one
   adjudicates whether the game happened at all.
3. **No fabricated final has leaked into calibration.** Zero rows carry a
   ``final_result`` in ``win_probability_sources``, so nothing here has to
   re-grade a curve. (Re-measure before trusting it: gotcha #21's neighbourhood.)

── WHY MOST OF THIS POPULATION CANNOT BE SCORED, AND WHAT THAT MEANS ────────────

By sport (production, 2026-09-01), of the 705:

    esports 308 · soccer_other 194 · tennis_atp 46 · americanfootball_other 35
    tennis_wta 28 · soccer_epl 27 · bundesliga 21 · la_liga 18 · ligue_one 9
    serie_a 9 · basketball_other 6 · motorsport_other 2 · lacrosse_other 1
    rugby_other 1

**547 of them are in sports with no schedule of record at all** — the
``EVENT-GRAPH-DOCTRINE`` per-sport table says so in prose ("esports, table
tennis, MMA, ITF/challengers, minor leagues: no ESPN endpoint") and
``SPORT_LEAGUE_MAP`` says so in code, which is what this module reads. For those
rows there is no authority that will ever supply a result, and the chain is
closed:

    the start was a stand-in (the writer stamped it so)
      -> so nothing reported a start
        -> so nothing reported a finish
          -> and the row carries no score (measured, 705/705)
            -> so the only thing that settled it is a wall-clock net
               measuring elapsed time FROM the stand-in
              -> and no authority exists that could ever say otherwise.

That is a phantom finished game with no path to truth. Doctrine rule 1 — "an
unresolvable market goes to a visible quarantine, never a phantom event" — and
the directive's own words, *"where the authority has no record of the event, that
event is a fabrication ... don't invent a score"*. So it is QUARANTINED:
``status = 'voided'``, the reversible soft-void ``repair_season_series_mislinks``
already established, excluded from every surface allowlist
(``Event.status.in_(["scheduled", "live", "completed", "closed"])`` in
``event_registry`` and in ``routes/events.py``). A status flip, not a delete.

── THE FOUR DISPOSITIONS, AND WHY ONE OF THEM IS "HOLD" ─────────────────────────

Every row reaches a NAMED verdict and each is counted (ruling 054). Nothing is
ever left in an unnamed bucket, and **nothing is written on a verdict we did not
earn**:

* ``repaired_final``  — the authority reports this fixture FINAL with a score.
  Write the score, the state, the real start. This is the only path that writes
  a number, and the number is the authority's.
* ``unsettled``       — the authority reports the fixture but it is NOT final.
  The settlement is the wrong field. Clear it and take the authority's real
  start, exactly as ``event_registry`` voids a staleness artifact.
* ``quarantined``     — no authority record. Either the sport has no schedule of
  record, or the authority's slate for those days is present and does not
  contain this fixture. ``status = 'voided'``. No score is invented.
* ``held``            — we do not know, and we say so. **This is a real state,
  not a bin.** It is what stops the two ways this repair could do harm:

  - **gotcha #53, an empty 200 is a response shape.** ``get_scoreboard`` returns
    ``[]`` for an HTTP failure and for a genuinely empty slate alike. A rail that
    read ``[]`` as "the authority has no record" would VOID a real game every
    time ESPN 500'd. So the adapter must report reachability separately, and an
    unreachable or empty slate HOLDS.
  - **an adapter that cannot speak for a sport must not be allowed to guess.**
    ``ESPNAPIService._parse_event`` reads ``competitions[0]`` — exactly one
    competition, with a home/away pair. On a tournament-shaped payload (a tennis
    draw, a golf field, an MMA card) that is ONE competition out of hundreds, and
    ESPN's tennis endpoint additionally **ignores ``?dates=``** (measured
    2026-09-01: ``atp``/``wta`` x ``20260901``/``20260902`` returned the
    byte-identical 625-competition payload). Adjudicating 74 tennis rows against
    one arbitrary sibling match would quarantine real US Open matches off the
    site on the night Alex is reviewing it. So tennis is HELD, by name, with a
    follow-up filed — not silently mis-adjudicated, and not silently voided.

── WHAT THIS MODULE DELIBERATELY DOES NOT DECIDE ────────────────────────────────

**The attached markets stay attached.** 1,198 futures markets (106 of them
``open``) point at the 705. Unlinking them would turn open game markets into
loose unattached futures with nowhere to go — the ``unattached_markets``
quarantine that doctrine rules 6-9 call for does not exist yet (it is lane1/041
branch 2). A voided event is excluded from every surface, so its markets stop
rendering with it; that is the ship. The counts are reported so the quarantine
ship can consume them, and no ``futures_markets`` row is touched here.

**Nothing scored is ever reconsidered.** Gotcha #21: a real result outranks any
schedule correction. The population predicate requires both score columns NULL
and the write guards restate it, so a row that acquires a score between the
census and the write is skipped, not clobbered.
"""
from typing import Optional

from app.utils.event_completion import DERIVED_COMMENCE_SOURCES
from app.utils.sport_keys import SPORT_LEAGUE_MAP

# ── The population ───────────────────────────────────────────────────────────
#
# ONE definition, three consumers (before-census, candidate fetch, after-census),
# so the bound and the work can never drift onto different populations — the
# shape ``repair_event_final_scores._SETTLED_PREDICATE`` earned.
#
# `commence_time_source` is read, never inferred. q066b established that
# CLUSTERING IS NOT A PLACEHOLDER SIGNATURE (a Saturday 3pm card genuinely is ten
# simultaneous kickoffs; ESPN's real order of play gives 15:05Z to three US Open
# matches at once), so nothing here binds on a date, an hour, or a count.
#
# `= ANY(:derived_sources)` rather than a literal: the set lives in
# `event_completion.DERIVED_COMMENCE_SOURCES`, which is the SAME set CERT-690's
# two producer doors refuse, so the producer and the repair cannot drift on what
# "derived" means. A future derived source joins both by joining that set.
FABRICATED_FINAL_PREDICATE = """
      e.commence_time_source = ANY(:derived_sources)
      AND e.status IN ('closed', 'completed')
      AND e.home_score IS NULL
      AND e.away_score IS NULL
"""

#: Bound for :data:`FABRICATED_FINAL_PREDICATE`. A list, not the frozenset —
#: asyncpg binds a Python list to ``text[]``; a set raises.
DERIVED_SOURCE_PARAM = sorted(DERIVED_COMMENCE_SOURCES)

#: The reversible soft-void. Established by ``repair_season_series_mislinks``
#: for exactly this purpose ("the reversible soft-void already used by the
#: dup-merge path ('merged'), excluded from every surface query") and already
#: carrying 72 production rows, so this rail introduces no new status and no new
#: reader has to learn one.
VOID_STATUS = "voided"

# ── Dispositions ─────────────────────────────────────────────────────────────

REPAIRED_FINAL = "repaired_final"
UNSETTLED = "unsettled"
QUARANTINED = "quarantined"
HELD = "held"

#: Every disposition, so a ledger census can assert it accounts for all of them
#: rather than counting whichever ones happened to occur.
DISPOSITIONS = (REPAIRED_FINAL, UNSETTLED, QUARANTINED, HELD)

#: The two that write nothing.
_READ_ONLY_DISPOSITIONS = frozenset({HELD})

# Reasons. Each one is the sentence a reader needs, not a code.
NO_SCHEDULE_OF_RECORD = "no_schedule_of_record"
NOT_ON_THE_AUTHORITY_SLATE = "not_on_the_authority_slate"
AUTHORITY_UNREACHABLE = "authority_unreachable"
AUTHORITY_SLATE_EMPTY = "authority_slate_empty"
ADAPTER_CANNOT_SPEAK = "adapter_cannot_speak_for_sport"
AUTHORITY_FINAL_WITHOUT_A_SCORE = "authority_final_without_a_score"
ORIENTATION_DISAGREES = "orientation_disagrees"
PAIRING_UNRESOLVED = "pairing_unresolved"
AUTHORITY_HAS_IT_FINAL = "authority_has_it_final"
AUTHORITY_HAS_IT_UNPLAYED = "authority_has_it_unplayed"

# ── Which authority speaks for which sport ───────────────────────────────────
#
# `SPORT_LEAGUE_MAP` is the codebase's own answer to "does ESPN have an endpoint
# for this sport", and it is read here rather than restated so a league added
# there is adjudicable here in the same commit.
#
# But an ENDPOINT is not an ADAPTER. `ESPNAPIService._parse_event` reads
# `competitions[0]` and pulls a home/away pair out of it, which is right for a
# head-to-head team fixture and wrong for a tournament payload, where
# `competitions` is the whole draw/field/card. So the map is partitioned, and the
# partition is EXHAUSTIVE BY GUARD: `test_every_espn_sport_is_classified` fails
# the build if a new `SPORT_LEAGUE_MAP` key lands in neither set. That is
# deliberate — the alternative (a denylist with an "adjudicable" default) would
# silently mis-adjudicate the next tournament sport somebody adds.

#: ESPN events whose ``competitions`` list is a DRAW/FIELD/CARD, not one fixture.
#: The scoreboard adapter cannot speak for these and must never pretend to.
TOURNAMENT_SHAPED_SPORTS = frozenset({
    "tennis_atp",
    "tennis_wta",
    "golf_pga",
    "golf_lpga",
    "mma_ufc",
    "mma_mixed_martial_arts",
})

#: Head-to-head sports the ESPN scoreboard adapter CAN adjudicate: one
#: competition, a home/away pair, an honest ``?dates=``.
#:
#: 🔴 WRITTEN OUT, NOT DERIVED, AND THE MUTATION BATTERY IS WHY. The first cut
#: was ``frozenset(SPORT_LEAGUE_MAP) - TOURNAMENT_SHAPED_SPORTS``, which reads
#: better and makes ``test_every_espn_sport_is_classified`` VACUOUS: a new key
#: added to ``SPORT_LEAGUE_MAP`` lands in this set automatically, the union is
#: exhaustive by construction, and the guard that is supposed to stop the next
#: tournament sport from being mis-adjudicated passes without seeing it. The
#: battery's M14 (adding a fictional ``padel_wpt`` to the map) survived. Two
#: literals plus an equality assertion is the only shape where the guard has
#: something to fail on.
SCOREBOARD_ADJUDICABLE_SPORTS = frozenset({
    # Football
    "americanfootball_nfl", "americanfootball_ncaaf", "americanfootball_cfl",
    "americanfootball_ufl",
    # Basketball
    "basketball_nba", "basketball_wnba", "basketball_ncaab", "basketball_wncaab",
    # Baseball
    "baseball_mlb", "baseball_mlb_preseason", "baseball_ncaa",
    # Hockey
    "icehockey_nhl",
    # Soccer
    "soccer_epl", "soccer_usa_mls", "soccer_uefa_champs_league",
    "soccer_spain_la_liga", "soccer_germany_bundesliga", "soccer_italy_serie_a",
    "soccer_france_ligue_one",
    # Lacrosse
    "lacrosse_ncaa", "lacrosse_pll",
    # Aussie rules
    "aussierules_afl", "aussierules_other",
})

#: The stand-in resolves to MIDNIGHT UTC of a ticker DATE. ESPN's scoreboard day
#: boundary is not UTC midnight (US leagues bucket by Eastern, European soccer by
#: local kickoff), so the real fixture legitimately lands on either side of it.
#: A false "not on the slate" VOIDS a real game, so the window is widened by a
#: day in each direction before absence is ever asserted. It is a window on the
#: AUTHORITY's calendar, not a matching tolerance: names still have to match.
AUTHORITY_DAY_OFFSETS = (-1, 0, 1)

#: ESPN's finished states as ``_parse_event`` MAPS them, used only as a fallback
#: — see :func:`authority_says_final`. The pair is the one ``espn_helpers``
#: already tests against (``ee.status in ("post", "final")``) rather than a
#: second opinion about what "finished" means at ESPN.
AUTHORITY_FINAL_STATES = frozenset({"post", "final"})

#: ESPN's ``status.type.state`` for a finished fixture. Sport-independent, which
#: ``type.name`` is not.
AUTHORITY_FINAL_STATE = "post"


def authority_says_final(fixture: dict) -> bool:
    """Is the authority reporting this fixture FINISHED?

    🔴 THE FIRST CUT OF THIS RAIL GOT IT WRONG AND A LIVE REPLAY CAUGHT IT.

    It tested ``fixture["status"] in AUTHORITY_FINAL_STATES``, i.e. the value
    ``ESPNAPIService._parse_event`` produces. That ladder maps exactly three
    ``status.type.name`` values — ``STATUS_SCHEDULED``, ``STATUS_IN_PROGRESS``,
    ``STATUS_FINAL`` — and passes everything else through as the raw lowercased
    name. **Soccer does not use ``STATUS_FINAL``.** Measured 2026-09-01 across
    eng.1 / esp.1 / ger.1 / ita.1 / fra.1 for Aug 29-31: **42 of 42 finished
    matches carried ``STATUS_FULL_TIME``**, which maps to the string
    ``"status_full_time"`` and is not in that set. (Knockout ties add
    ``STATUS_FINAL_PEN`` and ``STATUS_FINAL_AET``; the vocabulary is open-ended.)

    So the rail read every completed EPL, La Liga, Bundesliga, Serie A and
    Ligue 1 match as NOT FINAL and would have UNSETTLED 66 real, finished
    games back to ``scheduled`` — turning "Liverpool 2-2 Nottingham Forest,
    full time" into an upcoming fixture. The unit guards all passed: they
    asserted the ladder, and the ladder was faithful to a status vocabulary
    nobody had measured.

    The fix is to read what ESPN itself keys on. ``status.type.completed`` is a
    BOOLEAN and ``status.type.state`` is ``pre``/``in``/``post``, both
    sport-independent, both present on all 42. The mapped-name test survives
    only as a fallback for a payload that carries neither.
    """
    completed = fixture.get("completed")
    if isinstance(completed, bool):
        return completed
    state = fixture.get("state")
    if state:
        return state == AUTHORITY_FINAL_STATE
    return fixture.get("status") in AUTHORITY_FINAL_STATES

#: What our ``events.status`` becomes when the authority says FINAL. The same
#: word ``espn_helpers`` writes on that signal — a repair that invented a
#: different terminal would split the settled-language rule Alex ratified
#: ("settled means settled: one system-wide settled language").
FINAL_STATUS = "completed"

#: What a settlement with no witness becomes when the authority says the fixture
#: has NOT been played. ``event_registry`` uses exactly this pair (``scheduled``
#: + ``completed_at`` cleared) when it voids a staleness artifact.
UNSETTLED_STATUS = "scheduled"


def has_schedule_of_record(sport_key: Optional[str]) -> bool:
    """Does ANY authority publish a fixture list for this sport?

    False ⇒ the ``EVENT-GRAPH-DOCTRINE`` per-sport table's bottom row: "no ESPN
    endpoint ... venue-authority-of-last-resort". A settled, unscored, derived
    row in such a sport can never be adjudicated by anybody, which is precisely
    what makes it a fabrication rather than an open question.

    Read off ``SPORT_LEAGUE_MAP`` — the same map ``ESPNAPIService`` dispatches
    on, so "we have no endpoint" is one fact with one home.
    """
    return bool(sport_key) and sport_key in SPORT_LEAGUE_MAP


def adapter_can_speak_for(sport_key: Optional[str]) -> bool:
    """Can the ESPN *scoreboard* adapter adjudicate a single fixture here?

    False for tournament-shaped sports even though ESPN has an endpoint. This is
    the difference between "no authority exists" (a fabrication, quarantine) and
    "our reader cannot ask the question yet" (a hold, with a follow-up). Merging
    the two is how a real US Open match gets voided off the site.
    """
    return bool(sport_key) and sport_key in SCOREBOARD_ADJUDICABLE_SPORTS


class AuthorityVerdict:
    """What the schedule of record said about ONE fixture.

    Deliberately dumb: the adapter fills it, :func:`disposition_for` reads it,
    and no decision lives in the fetching code. That split is what lets every
    branch below be exercised without a network.

    ``reachable`` is separate from ``slate_size`` on purpose (gotcha #53): an
    empty 200 and a failed request produce the same empty list, and only one of
    them is evidence.
    """

    __slots__ = (
        "reachable", "slate_size", "fixture", "orientation_swapped",
        "any_side_on_slate",
    )

    def __init__(
        self,
        *,
        reachable: bool,
        slate_size: int = 0,
        fixture: Optional[dict] = None,
        orientation_swapped: bool = False,
        any_side_on_slate: bool = False,
    ):
        self.reachable = reachable
        self.slate_size = slate_size
        self.fixture = fixture
        self.orientation_swapped = orientation_swapped
        #: Did EITHER of our two team names appear anywhere on the slate?
        #: The difference between "the authority has no record of this fixture"
        #: and "our name matcher could not resolve the pairing", which the first
        #: cut of this rail conflated — see :func:`disposition_for` rung 5.
        self.any_side_on_slate = any_side_on_slate


def disposition_for(sport_key: Optional[str], verdict: AuthorityVerdict) -> tuple[str, str]:
    """``(disposition, reason)`` for one fabricated final. Pure.

    The ladder is ordered so that every step that could WRITE is reached only
    after every step that could excuse us from writing has been asked.

    1. No schedule of record at all  -> QUARANTINE. Nothing will ever adjudicate
       it; the FINAL has no witness and no path to one.
    2. An endpoint exists but our adapter cannot read this shape -> HOLD. Named,
       counted, and filed. We do not void what we merely cannot read.
    3. The authority did not answer -> HOLD. gotcha #53.
    4. The authority answered with an EMPTY slate for all three days -> HOLD.
       An empty list is a response shape, not an absence, and a league in its
       off-season returns one for every date. Absence is only asserted against a
       slate that demonstrably has fixtures in it.
    5. The fixture is absent from a NON-empty slate. Split in two, and the live
       replay is why:

       - If EITHER of our team names appears somewhere on that slate, the
         authority plainly covers this competition on this day and our NAME
         MATCHER is what failed. -> HOLD. Measured 2026-09-01 over the real 705:
         our row ``'Chelsea' v 'Brighton'`` did not pair with ESPN's
         ``Chelsea`` / ``Brighton & Hove Albion`` (``names_match`` is
         deliberately suffix-only, so a prefix like "Brighton" does not match),
         and ``'Leipzig' v 'M´gladbach'`` did not pair with
         ``RB Leipzig`` / ``Borussia Mönchengladbach``. Both are real matches
         that were really played, and a rail that voided them would delete them
         off the site on a matcher limitation.
       - If NEITHER name is anywhere on the slate, the authority genuinely has
         no record. -> QUARANTINE. This is the directive's "the authority has no
         record of the event", and on the same replay it is what catches
         ``'Spurs' v 'Raptors'`` filed under Serie A.
    6. The fixture is present and FINAL, our home/away agreeing with the
       authority's -> REPAIR from its score.
    7. Present and final but scoreless, or with the sides reversed -> HOLD. A
       score written onto the wrong side is the CAL-P002 corruption, and the
       ``espn_id_drifted`` lesson on that rail is that the confident-looking
       write is the dangerous one.
    8. Present and NOT final -> UNSETTLE. The row's settlement is the wrong
       field; the authority's start replaces the stand-in.
    """
    if not has_schedule_of_record(sport_key):
        return QUARANTINED, NO_SCHEDULE_OF_RECORD
    if not adapter_can_speak_for(sport_key):
        return HELD, ADAPTER_CANNOT_SPEAK
    if not verdict.reachable:
        return HELD, AUTHORITY_UNREACHABLE
    if verdict.fixture is None:
        if verdict.slate_size <= 0:
            return HELD, AUTHORITY_SLATE_EMPTY
        if verdict.any_side_on_slate:
            return HELD, PAIRING_UNRESOLVED
        return QUARANTINED, NOT_ON_THE_AUTHORITY_SLATE

    fixture = verdict.fixture
    if authority_says_final(fixture):
        if verdict.orientation_swapped:
            return HELD, ORIENTATION_DISAGREES
        if fixture.get("home_score") is None or fixture.get("away_score") is None:
            return HELD, AUTHORITY_FINAL_WITHOUT_A_SCORE
        return REPAIRED_FINAL, AUTHORITY_HAS_IT_FINAL
    return UNSETTLED, AUTHORITY_HAS_IT_UNPLAYED


def disposition_writes(disposition: str) -> bool:
    """Does this disposition touch the row at all? Named so the apply path and
    the dry-run ledger cannot disagree about which verdicts are inert."""
    return disposition not in _READ_ONLY_DISPOSITIONS
