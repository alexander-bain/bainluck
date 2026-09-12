"""The one decision that turns a venue's outcome prices into a blend reading.

Queue 460. `Event.win_probability_sources` is the number every card and every
hero renders, and until this module existed exactly one writer could move it:
the 120-second `poll_live_prediction_markets` pass. The Kalshi WebSocket dyno
has been streaming sub-second prices into `futures_outcomes.current_probability`
the whole time — measured 2026-08-30, 4 of 10 live outcomes moved inside a 25s
window — and not one of those moves reached the blend. The fast lane stopped one
table short of the number.

The fix is to let the WS dyno stamp the blend too. That immediately raises the
question this module answers: **the poll and the fast lane must compute the same
number from the same rows, or the hero flickers between two writers' opinions
every two minutes.** So the decision is extracted here, once, and both callers
use it. A second copy of this arithmetic is the #1951 failure mode — a drifted
predicate does not throw, it just quietly disagrees with itself.

WHAT IS AND IS NOT IN HERE. This is the *pure* half: given the markets and
outcomes already loaded for one (event, source) pair, what home probability does
that source assert? It does no I/O, so it is testable without a database and it
cannot be the thing that makes a 2-second flush loop slow. The impure half — the
inversion cross-check against sportsbook consensus, and the JSONB stamp itself —
stays with its callers, because the two callers legitimately differ there (the
poll can afford a per-event consensus query every 120s; the fast lane caches
that verdict, see `app/tasks/live_blend_refresh.py`).

DUCK-TYPED ON PURPOSE. `market` and `outcome` are whatever the caller loaded —
ORM rows in both live callers. The attributes read are named in
`MarketOutcomes`, and nothing here writes to them. That keeps the extraction
faithful: the poll's behaviour is unchanged because it is literally the same
expression, moved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from app.utils.game_market_class import (
    classify_game_market_class,
    outcomes_refute_game_winner,
)
from app.utils.prediction_market_matching import (
    _strip_category_prefix,
    extract_matchup_with_ticker_fallback,
    feeds_win_prob_blend,
    find_moneyline_outcome,
)
from app.utils.probability_eligibility import (
    EligibilityRecord,
    MarketRef,
    verified_record,
)


# The rule name every record minted here carries, qualified by the issue that
# defines the gate's behaviour. A stored record has to stay legible after the
# function is edited, and "admissible_as_blend_speaker" alone would not say
# WHICH admissible_as_blend_speaker — the per-source asymmetry it grew in #5031
# is the difference between a record that means something and one that does not.
BLEND_ADMISSION_RULE = "live_blend.admissible_as_blend_speaker@5031"


def _market_ref(market: Any) -> MarketRef:
    """One contributing market as the record's evidence pointer.

    `getattr` for the same reason the speaker's own ids use it: this function is
    called on whatever the caller's ORM row or test double exposes, and a missing
    attribute must degrade to "no id" rather than raise on the write path.
    """
    return MarketRef(
        market_id=getattr(market, "id", None),
        source_market_id=getattr(market, "external_id", None),
    )


@dataclass(frozen=True)
class MarketOutcomes:
    """One linked market plus the outcomes already loaded for it.

    ``market`` must expose ``id``, ``source``, ``external_id`` and ``name``.
    ``outcomes`` items must expose ``rank``, ``name`` and ``current_probability``
    (``find_moneyline_outcome`` reads the latter two).

    ``event_commence_time`` is the EVENT's kickoff, and it is a field here rather
    than an attribute read off ``market`` because the market row does not carry
    it. Measured on production 2026-09-12 17:0xZ over every linked market on a
    `status='live'` event: `futures_markets.commence_time` agrees with
    `events.commence_time` to within five minutes on **21 of 337** Polymarket
    rows and **52 of 477** Kalshi rows, and is off by more than an hour on 315
    and 375 of them respectively. It is the market's own clock — for Kalshi
    routinely the CLOSE time (gotcha #14) — so it cannot stand in for kickoff.

    It defaults to None, which is "no evidence", and the observation gate that
    reads it abstains on None. A construction site that does not supply it keeps
    exactly the behaviour it has today rather than silently acquiring a gate.
    """

    market: Any
    outcomes: Sequence[Any]
    event_commence_time: Optional[datetime] = None


def is_game_winner_market(market: Any) -> bool:
    """Whether this market's YES side is a game winner that feeds the blend.

    Only Kalshi is gated: its tickers distinguish game winners from spreads,
    totals and props, and `feeds_win_prob_blend` is the measured admission rule.
    Polymarket game markets arrive already decomposed, so the source itself
    carries no equivalent signal and the caller's linkage is trusted — which is
    exactly how the poll has always treated it.
    """
    if market.source != "kalshi" or not market.external_id:
        return False
    return feeds_win_prob_blend(market.external_id)


def select_primary_market(group: Sequence[MarketOutcomes]) -> Optional[MarketOutcomes]:
    """Pick the one market in a (event, source) group that speaks for the source.

    Kalshi mints a separate binary market per team ("Celtics win?" and
    "76ers win?"), both linked to the same event. A game-winner market always
    beats a non-game-winner; among equals the lowest market id wins, so the
    choice is stable across passes rather than dependent on row order.
    """
    if not group:
        return None
    primary = group[0]
    for candidate in group[1:]:
        primary_is_gw = is_game_winner_market(primary.market)
        candidate_is_gw = is_game_winner_market(candidate.market)
        if candidate_is_gw and not primary_is_gw:
            primary = candidate
        elif primary_is_gw == candidate_is_gw and candidate.market.id < primary.market.id:
            primary = candidate
    return primary


@dataclass(frozen=True)
class BlendReading:
    """What one source asserts about one event, plus the row it came from.

    Callers need more than the number: the poll stamps the originating outcome's
    name and raw YES price into the snapshot's ``game_state``, which is the audit
    trail for "why did the blend say that". Returning the number alone would have
    forced the caller to re-find the outcome and risk finding a different one.

    ``eligibility`` (CU-4, #5311) is that same audit trail in the form a READER
    can use. `game_state` lives on a different table, is written only when the
    caller asks for a snapshot, and no serve-time path joins it — so the evidence
    sits beside the published number and not on it. This field is minted here,
    by the gate that admitted the speaker, so it cannot disagree with the gate;
    a caller stamping the JSONB passes it straight to `stamp_source_reading`.
    """

    home_probability: float
    market: Any
    outcome: Any
    yes_probability: float
    devigged: bool
    eligibility: Optional[EligibilityRecord] = None


def _home_probability_for_market(
    entry: MarketOutcomes, matchup: Any, home_team_name: str, away_team_name: str
) -> Optional[tuple[float, Any, float]]:
    """This single market's implied home probability, or None if it can't say.

    ``matchup`` is the SPEAKING market's parse, deliberately, and it is passed
    in rather than re-derived per market. Kalshi's per-team pair carries two
    different market names for one game, so re-deriving would let the two halves
    of a devig disagree about which side is home — averaging a home reading with
    an away one, silently, only on the two-market path.
    """
    ordered = sorted(entry.outcomes, key=lambda o: o.rank or 999)
    if not ordered:
        return None

    ml_result = find_moneyline_outcome(
        ordered, matchup, home_team_name, away_team_name,
    )
    if not ml_result:
        return None

    outcome, yes_is_home = ml_result
    if outcome.current_probability is None:
        return None
    yes_prob = float(outcome.current_probability)
    home_prob = yes_prob if yes_is_home else 1.0 - yes_prob
    return home_prob, outcome, yes_prob


def _class_says_game_winner(market: Any) -> bool:
    """Whether the ONE shared class recognizer calls this market a game winner.

    Polymarket decomposes a game into a dozen rows that share the
    match-winner's exact two-outcome shape and its "A vs. B" title, then append
    a qualifier: `A vs. B - Halftime Result`, `- Exact Score`,
    `: Both Teams to Score`. The matchup parser strips container suffixes to
    recover the participants, so those names PARSE, and their outcomes are the
    two team names, so they RESOLVE. Measured over a 3-day 2,197-group replay:
    an ungated fallback newly stamped 95 such derivatives as the match
    moneyline — a halftime price on the hero, confidently, with nothing on
    screen to say so.

    So a fallback must be a game winner by the ONE shared recognizer
    (`game_market_class`), which is source-agnostic and keys on the bare-matchup
    shape rather than on English words. Its league-tag stripper knows the Kalshi
    spellings, not Polymarket's tournament prefixes (`US Open ATP: A vs B`), so
    the shared parser's own prefix knowledge runs first — re-implementing that
    list here is the #1951 drift failure, where the second copy does not throw
    when it disagrees, it just quietly answers differently.

    Fail-closed: a prefix neither module recognizes leaves the colon in place,
    the name is not a bare matchup, and the market stays silent. That is the
    behaviour it already has today.
    """
    name = market.name or ""
    return classify_game_market_class(
        _strip_category_prefix(name), market.external_id
    ) == "moneyline"


# ── The kickoff grace, DERIVED from the observer's enforced clock (#4854) ────
#
# The obvious predicate — "every price predates kickoff" — is TRUE for a couple
# of minutes at EVERY kickoff, because the last healthy poll landed just before
# the whistle. Retiring on it bare would drop and re-add the leg at the start of
# every game, which is precisely the twitch `count_admissible_speakers`'
# docstring exists to forbid. So the predicate needs a grace, and the grace is
# derived rather than picked.
#
# The live poll is the fastest observer of one of these books, so how long a leg
# the poller is actually reaching can sit unobserved is a property of that task's
# clock. It is sized off the bound that is ENFORCED, never off the cadence or a
# p95: the beat is 120s (`poll-live-prediction-markets`, `schedule: 120.0`) and
# the global `task_time_limit` is 300s — a HARD limit, Celery SIGKILLs the child,
# and `poll_live_prediction_markets` declares no override — so a pass cannot
# outrun it before the next beat starts clean. One beat plus one maximal pass is
# therefore the longest a healthy leg can go unobserved.
#
# The 15-minute matcher is deliberately NOT the basis: it re-derives from rows it
# already holds instead of re-observing, so its cadence says nothing about when
# we last heard from the venue.
_LIVE_POLL_BEAT_SECONDS = 120
_LIVE_POLL_ENFORCED_HARD_KILL_SECONDS = 300
UNOBSERVED_SINCE_KICKOFF_GRACE = timedelta(
    seconds=_LIVE_POLL_BEAT_SECONDS + _LIVE_POLL_ENFORCED_HARD_KILL_SECONDS
)

# ── And the window CLOSES, because a stale leg stops being this defect ───────
#
# The window is two-sided for a reason that is this issue's own scope boundary
# rather than a convenience. latency/346 sized the class on live pages and split
# it explicitly: of the marked rows, the ones **over 24h old all carry a
# settlement flag** and are #4024's wrong-fixture attachment, a different defect
# with a different fix; the band that belongs here is the two-to-six-hour one on
# a game actually in progress. An event still marked `live` half a day after its
# kickoff is not a long match, it is a status or attachment defect, and silently
# retiring its leg would hide that rather than fix it.
#
# It costs this ship nothing, which is the test of an honest bound: measured on
# production 2026-09-12 17:3xZ, every frozen Polymarket leg on a `status='live'`
# event is under **3.4 hours** past kickoff — the whole population sits in the
# first quarter of the window.
#
# It also keeps the gate off rows whose clock cannot be trusted at all. This is
# the only clause here that reads the wall clock, and gotcha #44's lesson is that
# a fixed-date fixture replayed months later drifts arbitrarily far from its own
# anchor; outside this window the gate abstains rather than acting on a date it
# has no business trusting.
UNOBSERVED_SINCE_KICKOFF_WINDOW_CLOSES = timedelta(hours=12)


def _as_utc(value: Any) -> Optional[datetime]:
    """A timezone-aware UTC datetime, or None if it is not one at all.

    Naive stamps are read as UTC because that is what every writer on this path
    stores. Anything that is not a datetime — a test double's string, a None —
    is "no evidence" and the caller abstains rather than guessing.
    """
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _last_observation(outcomes: Optional[Sequence[Any]]) -> Optional[datetime]:
    """When we last OBSERVED this book, or None if we cannot tell.

    `futures_outcomes.last_updated` is the right stamp and the price itself is
    the wrong one. The pollers write `last_updated` unconditionally on every
    successful read, so it records that we HEARD from the venue, not that the
    number moved — which is exactly the question here. A price that has not
    changed in an hour on a quiet book is fine; a price nobody has looked at
    since before kickoff is not.

    The NEWEST stamp in the book wins: one outcome lagging is not evidence the
    book is unobserved, and taking the oldest would fire on a half-written one.
    """
    newest: Optional[datetime] = None
    for outcome in outcomes or ():
        stamp = _as_utc(getattr(outcome, "last_updated", None))
        if stamp is not None and (newest is None or stamp > newest):
            newest = stamp
    return newest


def speaker_unobserved_since_kickoff(
    market: Any,
    outcomes: Optional[Sequence[Any]],
    event_commence_time: Optional[datetime],
    now: Optional[datetime] = None,
) -> bool:
    """Whether this market's book has not been observed since the game started.

    THE THIRD WAY A SOURCE FALLS SILENT (#4854), and the one the other two
    cannot see. `count_admissible_speakers` catches a group holding nothing but
    Player Props; `admissible_speakers_are_all_settled` catches a winner market
    that has stopped being able to answer. Neither catches the case where the
    winner market is right there, admissible, and PRICED — with a price from
    before the whistle. That book resolves a side perfectly well, so the reading
    is not None, the retirement path is never reached, and a pre-kickoff number
    goes on deciding a live match's published probability.

    Measured on production 2026-09-12 17:0xZ, `status='live'` events: of 323
    Polymarket legs, **134 carry no observation since their event's kickoff**,
    and all 134 are past the grace below. A further 8 legs sat 6 minutes past
    kickoff — inside the grace, protected, and the reason the grace exists.

    DECAY IS NOT ENOUGH, which is why this retires rather than demotes. Making
    the stamp honest lets `_relative_staleness_multiplier` demote the leg, and a
    demoted leg is still a leg: a weighted median is decided by POSITION, not by
    weight, so a 10%-weight source still chooses the published number when it
    sits in the middle. Only removing it removes it.

    Three abstentions, all "no evidence" rather than "fresh":

      * no ``event_commence_time`` — the caller does not know when the game
        started, so it cannot know whether we have heard since;
      * no readable ``last_updated`` on any outcome — an unfetched book, which
        is the transient case this must not touch;
      * the game has not been underway longer than the grace — see
        ``UNOBSERVED_SINCE_KICKOFF_GRACE`` for why that window is 7 minutes and
        why it is derived from the poll's enforced hard kill rather than chosen;
      * the game has been "underway" for longer than
        ``UNOBSERVED_SINCE_KICKOFF_WINDOW_CLOSES``, which is not a long match but
        a status or attachment defect — #4024's class, which latency/346
        measured and excluded from this one.
    """
    kickoff = _as_utc(event_commence_time)
    if kickoff is None:
        return False
    moment = _as_utc(now) or datetime.now(timezone.utc)
    underway_for = moment - kickoff
    if not (
        UNOBSERVED_SINCE_KICKOFF_GRACE
        < underway_for
        < UNOBSERVED_SINCE_KICKOFF_WINDOW_CLOSES
    ):
        return False
    observed = _last_observation(outcomes)
    if observed is None:
        return False
    return observed < kickoff


def admissible_as_blend_speaker(
    market: Any,
    *,
    is_primary: bool,
    outcomes: Optional[Sequence[Any]] = None,
    event_commence_time: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Whether this market may speak for its source — primary or not (#5031).

    THE PRIMARY USED TO BE EXEMPT, and that exemption was the bug. The reasoning
    for it was that the primary is "the row the live writers have always
    trusted", so gating it would retire readings that ship today. True for
    Kalshi. False for Polymarket, because for Polymarket the primary is not a
    trusted row at all: `is_game_winner_market` is hard-False for every
    non-Kalshi source, so `select_primary_market`'s tie-break degrades to
    "lowest market id" — the OLDEST row — and Polymarket mints Exact Score,
    Total Corners and Player Props before the match-winner child. The row that
    inherited the primary's exemption was therefore, routinely, a derivative.

    It did not merely fail to speak. Those derivatives' outcomes are named after
    the teams (`St. Louis City SC 2 - 2 Minnesota United FC`,
    `Columbus Crew`, `Venezia FC (-1.5)`), so `find_moneyline_outcome` resolves
    them by containment and the price of an exact scoreline is written as the
    match winner. Measured over every OPEN Polymarket market linked to an event
    commencing in (-6h, +48h) — 1,096 markets / 231 groups, 2026-09-11 04:20Z:
    89 groups have a non-winner primary, and in **10 of them the derivative is
    resolving and its number is the one stored on the event right now** (event
    15301219 holds **0.070** from an Exact Score `2 - 2` leg against Kalshi's
    0.705; event 15297961 holds 0.13 off a `(-1.5)` spread outcome).

    THE GATE IS PER SOURCE, AND MEASURING THAT WAS THE WHOLE JOB. Applying the
    class recognizer to the primary of EVERY source reads as the simpler rule
    and is a regression: over the same window's 468 Kalshi groups it refuses 13
    live UFC primaries — `Fight Night: Silva vs Delgado`, ticker
    `KXUFCFIGHT-26SEP12SILDEL` — because the colon makes the title not a bare
    matchup, no winner word appears, and the ticker carries neither "game" nor
    "winner". Every one is the real fight winner, every one holds a stored leg,
    and none has another winner market to fall back to, so the whole card would
    have gone blank. So:

      * **Kalshi** already has a venue-side admission rule that is measured and
        enforced on primary and fallback alike — `feeds_win_prob_blend` on the
        ticker, applied in `_reading_for_entry`. Nothing here changes for it;
        the class recognizer is simply the wrong instrument on a Kalshi row.
      * **Every other source** has no such signal — that absence *is* the defect
        — so the class recognizer decides, for the primary exactly as for a
        fallback.

    The fallback keeps its existing burden unchanged, including on Kalshi, where
    it is stricter than the primary's. That asymmetry is the pre-existing #759
    design ("new admission proves itself") and this is not the queue that moves
    it.

    ── ``outcomes``: the row's own refutation (#5273) ───────────────────────

    The name recognizer above reads a TITLE, and Polymarket's event-level
    container wears the match's title while carrying the derivative books as
    its outcomes (`Duquesne | Spread -16.5`). So the class gate admits it and
    `find_moneyline_outcome` resolves the lone competitor-shaped outcome,
    publishing a handicap's price as the winner. Passing the outcomes lets the
    market refute itself — see `outcomes_refute_game_winner` for the measured
    population and for why one derivative outcome is the whole signal.

    IT IS ASKED EXACTLY WHERE THE CLASS RECOGNIZER IS ASKED, never of a Kalshi
    primary. Not because the outcome test would misfire there — Kalshi's pair
    is `Yes | No` and would pass — but because the Kalshi primary's exemption
    is a MEASURED one (the 13 UFC fights above) and widening a second
    instrument onto it would change a population this queue did not measure.
    The Kalshi delta is therefore provably zero.

    ``outcomes`` defaults to None, which is "no evidence" and refuses nothing,
    so a caller that has not loaded them — `event_chart_backfill` — keeps the
    behaviour it has today rather than silently acquiring a new gate.

    ── ``event_commence_time``: has anyone looked since kickoff? (#4854) ─────

    A market can be the right KIND of question, carry outcomes that refute
    nothing, and still be quoting a price from before the whistle. That is
    `speaker_unobserved_since_kickoff`, and it is asked here — rather than in
    the retirement path beside the other two silences — because the retirement
    path is only reached when the reading is None, and this book's whole problem
    is that it resolves perfectly well. Gating admission is what makes the
    reading None, and the existing `count_admissible_speakers == 0` retirement
    then clears the stored leg with no new wiring at all.

    NOT ASKED OF KALSHI, and the delta there is provably zero. The class is
    Polymarket's: on `status='live'` events 134 of 323 Polymarket legs carry no
    post-kickoff observation, and latency/346 measured 55.7% of Polymarket legs
    over 30 minutes old against Kalshi's 4.6%. Kalshi's primary returns True
    above before any clause runs, so a Kalshi group always keeps a speaker and
    could never be retired by this anyway — asking it of Kalshi's FALLBACKS
    would only change which Kalshi row speaks, in a population this queue did
    not measure, for no ship. Same reasoning the outcomes test is held off the
    Kalshi primary above.
    """
    if getattr(market, "source", None) == "kalshi" and is_primary:
        return True
    if not _class_says_game_winner(market):
        return False
    if outcomes_refute_game_winner(
        [getattr(o, "name", None) for o in outcomes] if outcomes else None
    ):
        return False
    if getattr(market, "source", None) != "kalshi" and speaker_unobserved_since_kickoff(
        market, outcomes, event_commence_time, now
    ):
        return False
    return True


def count_admissible_speakers(group: Sequence[MarketOutcomes]) -> int:
    """How many markets in this group are ALLOWED to speak for the source.

    The discriminator behind a stored reading's retirement (#5031), and it has
    to be a different question from "did the group speak", because those two
    fail for opposite reasons and only one of them may retire a number:

      * **zero admissible markets** is STRUCTURAL. The source has linked this
        event nothing but Player Props and Total Corners; it holds no opinion
        about who wins and it will not grow one on the next pass. A stored leg
        here is the #1163 phantom in a second costume — a blend input with no
        backing market — and it must go.
      * **admissible markets that cannot resolve right now** is TRANSIENT: an
        untraded winner market with a null price, an outcome list not yet
        fetched. Retiring on that would drop and re-add the leg as prices come
        and go, and the hero would twitch by a source's whole weight every
        fifteen minutes.

    So a caller retires on this returning 0, never on a `None` reading alone.
    Asked with the same per-source rule the reading itself uses, so a Kalshi
    group can never be retired by it (its primary is always admissible here,
    and its props are refused far upstream by `feeds_win_prob_blend`).
    """
    return len(admissible_speakers(group))


def admissible_speakers(
    group: Sequence[MarketOutcomes],
    *,
    now: Optional[datetime] = None,
    apply_observation_gate: bool = True,
) -> list[MarketOutcomes]:
    """The entries in this group ALLOWED to speak for the source.

    ``apply_observation_gate=False`` withholds the kickoff from the admission
    call, which makes #4854's observation clause abstain by construction. It is
    how `admissible_speakers_are_unobserved_since_kickoff` asks "would anything
    have spoken but for that clause" without writing a second admission rule —
    see that function. Nothing on the writing path passes it.

    Factored out so `count_admissible_speakers` and
    `admissible_speakers_are_all_settled` cannot drift into two opinions of
    which rows are admissible: they are the same question asked twice, and a
    second copy of an admission rule is the #1951 failure ("the second copy
    does not throw when it disagrees, it just quietly answers differently").
    The primary is selected here, once, because admissibility is per-source AND
    per-role — `admissible_as_blend_speaker` exempts a Kalshi PRIMARY only.
    """
    entries = list(group or [])
    if not entries:
        return []
    primary = select_primary_market(entries)
    primary_id = primary.market.id if primary is not None else None
    return [
        entry
        for entry in entries
        if admissible_as_blend_speaker(
            entry.market,
            is_primary=entry.market.id == primary_id,
            outcomes=entry.outcomes,
            event_commence_time=(
                getattr(entry, "event_commence_time", None)
                if apply_observation_gate
                else None
            ),
            now=now,
        )
    ]


def admissible_speakers_are_unobserved_since_kickoff(
    group: Sequence[MarketOutcomes], now: Optional[datetime] = None
) -> bool:
    """Whether the observation gate is what silenced this whole group (#4854).

    Purely a question about WHICH CAUSE, asked so the funnel can say it. Once
    `speaker_unobserved_since_kickoff` is part of admission, a group frozen since
    before kickoff arrives at the retirement with zero admissible speakers and is
    indistinguishable there from #5031's group-of-Player-Props. Folding a new
    cause into an old counter makes it look like a spike in the old one, and the
    two need separate reach measurements.

    Asked by running the SAME admission function twice — once with the kickoff
    and once without — rather than by re-deriving which rows are stale beside it.
    Withholding ``event_commence_time`` makes the observation clause abstain by
    construction, so the second call is this module's own rule minus exactly one
    clause, never a second copy of it (the #1951 drift failure).

    Returns False when the group has no speaker even with the gate off: that is
    the structural-silence case and `count_admissible_speakers` already owns it.
    """
    without_gate = admissible_speakers(group, apply_observation_gate=False)
    if not without_gate:
        return False
    return not admissible_speakers(group, now=now)


def _is_settled_book(entry: MarketOutcomes) -> bool:
    """Whether this market's book is SETTLED — every outcome at a terminal price.

    The mechanism, not a proxy for it. All three resolution paths in
    `find_moneyline_outcome` — the team-match loop, the full-matchup fallback
    and the generic Yes/No last resort — skip any outcome that is not strictly
    between 0 and 1. So a book whose every priced outcome sits AT a boundary
    cannot produce a reading by any route, and never will again: a settled price
    does not come back off 0.00/1.00. That is what makes this permanent rather
    than transient, which is the whole distinction `count_admissible_speakers`
    exists to protect (see its docstring).

    Deliberately conservative in both of the ways it can abstain, because the
    cost of a false positive is retiring a live source leg:

      * an EMPTY outcome list is not settled — it is a book we have not fetched
        yet, which is the transient case;
      * an outcome with NO price is not settled — same reason. Every outcome
        must be priced and terminal, so a half-written book abstains.

    Mirrors `find_moneyline_outcome`'s own `prob <= 0 or prob >= 1` test rather
    than re-deriving a threshold beside it.
    """
    outcomes = list(entry.outcomes or [])
    if not outcomes:
        return False
    for outcome in outcomes:
        raw = getattr(outcome, "current_probability", None)
        if raw is None:
            return False
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return False
        if 0.0 < value < 1.0:
            return False
    return True


def admissible_speakers_are_all_settled(group: Sequence[MarketOutcomes]) -> bool:
    """Whether every market admitted to speak here is a SETTLED book (#5548).

    The second way a source can fall permanently silent, and it is invisible to
    `count_admissible_speakers`. A settled Polymarket container collapses to its
    winning outcome alone — `[('San Diego Padres', 1.0)]` — which is a bare
    matchup by title carrying no derivative vocabulary, so it stays ADMISSIBLE
    while being unable to resolve a side. Retirement asks "can anything speak?"
    and gets yes; the writer asks "did anything speak?" and gets no; the stored
    pre-settlement price is then frozen on the page forever. Event 15309667
    published 0.069 for the Giants hours after Polymarket settled the game to
    the Padres.

    Returns False when the group has NO admissible speaker, deliberately: that
    is the zero-speaker case and `count_admissible_speakers` already owns it.
    This predicate only ever speaks about a group that HAS speakers, so the two
    retirement causes stay separable in the funnel.
    """
    admissible = admissible_speakers(group)
    if not admissible:
        return False
    return all(_is_settled_book(entry) for entry in admissible)


def _reading_for_entry(
    entry: MarketOutcomes, home_team_name: str, away_team_name: str
) -> Optional[tuple[Any, float, Any, float]]:
    """``(matchup, home prob, outcome, yes prob)`` from ONE market, or None.

    The whole admission rule for a single market lives here — the Kalshi
    props/spreads gate, the name parse, and the moneyline resolution — so that
    trying a second market widens the SEARCH without widening what is allowed
    to speak. A market that cannot clear every one of these still says nothing.
    """
    # Kalshi props/spreads never write the blend, whatever they are linked to.
    if entry.market.source == "kalshi" and entry.market.external_id:
        if not feeds_win_prob_blend(entry.market.external_id):
            return None

    # Uses the ticker fallback for generically-named Kalshi markets.
    matchup = extract_matchup_with_ticker_fallback(
        entry.market.name, external_id=entry.market.external_id,
    )
    if not matchup:
        return None

    reading = _home_probability_for_market(
        entry, matchup, home_team_name, away_team_name,
    )
    if reading is None:
        return None

    home_prob, outcome, yes_prob = reading
    return matchup, home_prob, outcome, yes_prob


def compute_source_home_probability(
    group: Sequence[MarketOutcomes],
    home_team_name: str,
    away_team_name: str,
) -> Optional[BlendReading]:
    """The home win probability this source asserts, or None if it asserts none.

    ``group`` is every linked market of ONE source for ONE event, each with its
    outcomes. Returns None — never a guess — whenever the market is not a game
    winner, the matchup cannot be parsed, or no moneyline outcome is found.

    THE PRIMARY IS A PREFERENCE, NOT A VERDICT, AND NOT A LICENCE (#5031). It is
    still asked FIRST, so a group whose primary can legitimately speak keeps
    saying exactly what it said. What it no longer gets is an exemption from
    admission: outside Kalshi the primary must clear the same game-winner
    recognizer a fallback clears, because outside Kalshi "primary" means nothing
    more than "oldest row" (see ``admissible_as_blend_speaker`` for the per-source
    split and the 13 UFC fights that prove it cannot be source-agnostic). Its
    tie-break among equals is "lowest market id", and
    ``is_game_winner_market`` gates only KALSHI — for Polymarket every row of a
    group scores the same, so "lowest id" means OLDEST. Polymarket mints an
    event-level parent and the derivative books (Exact Score, Match O/U) before
    the match-winner child that actually carries the moneyline, so the oldest
    row is routinely one that cannot resolve a side, and the whole source went
    silently blank on the very events this blend exists for. Measured by
    CERT-759: an empty parent at id 1 beside a match-winner child at id 9
    selects primary 1 and reads None.

    So the rest of the group is tried, in the same deterministic id order, and
    the first ADMISSIBLE market that can speak wins.

    Admission is `admissible_as_blend_speaker`, asked of every candidate now,
    the primary included. The Kalshi gate, the name parse and the moneyline
    resolution live in the per-market attempt (`_reading_for_entry`), so a
    Kalshi prop is still refused rather than fallen back onto.

    A GROUP CAN NOW GO SILENT THAT USED TO SPEAK, and that is the point rather
    than a cost: measured over the (-6h,+48h) production window, 10 Polymarket
    groups were resolving an exact scoreline or a corners line as the match
    winner, 6 of them re-point to a real winner market in the same group and 4
    have no winner market at all and correctly say nothing. A caller that stored
    a number from the silenced row must therefore RETIRE it — a gate that only
    refuses to write freezes the old value on the page forever. That duty is the
    caller's because this half is pure; `_phase2_persist_group_reading` carries
    it, under the #1163 source-implies-a-backing-market invariant.

    ``select_primary_market`` itself is deliberately NOT changed: it is also the
    row-picker in the poll's grouping pass, and moving the tie-break under it
    would move a second caller this queue did not measure.

    DEVIG. When the source published exactly two markets for the game (Kalshi's
    per-team pair), both sides are resolved and averaged, which cancels the vig
    the two YES prices carry in opposite directions. With one market, or when
    the sibling cannot be resolved, the single reading stands as-is: an average
    of one usable number and one absent one is not a devig, it is a coin flip
    wearing the word.
    """
    entries = list(group or [])
    if not entries:
        return None

    primary = select_primary_market(entries)
    if primary is None:
        return None

    ordered_entries = [primary] + [
        entry
        for entry in sorted(entries, key=lambda e: e.market.id)
        if entry.market.id != primary.market.id
    ]

    speaker = None
    for entry in ordered_entries:
        is_primary = entry.market.id == primary.market.id
        if not admissible_as_blend_speaker(
            entry.market,
            is_primary=is_primary,
            outcomes=entry.outcomes,
            # #4854: a book nobody has looked at since kickoff may not speak.
            # Passed here as well as in `admissible_speakers` because these are
            # the two places admission is asked, and they must not disagree —
            # the writer would publish a number the retirement then clears.
            event_commence_time=getattr(entry, "event_commence_time", None),
        ):
            continue
        found = _reading_for_entry(entry, home_team_name, away_team_name)
        if found is not None:
            speaker = entry
            matchup, home_prob, outcome, yes_prob = found
            break
    if speaker is None:
        return None

    devigged = False
    # EVERY MARKET THAT MOVES THE NUMBER, in the order it moved it. The speaker
    # is always the first; a devig sibling that is admitted joins it. This is
    # what the record names (CERT-2646) — see `_market_ref`.
    contributors = [speaker.market]

    if len(entries) == 2:
        for sibling in entries:
            if sibling.market.id == speaker.market.id:
                continue
            # ── A CONTRIBUTOR IS GATED LIKE A SPEAKER (CERT-2646) ────────────
            #
            # This half of the average was gated for Kalshi and NOT AT ALL for
            # anything else, while the record named only the speaker. So an
            # admitted 60% winner averaged with a gate-refused 20% Polymarket
            # First-Team-to-Score derivative served 40%, `devigged=True`,
            # stamped `verified` / `full_event_winner` and naming only the
            # winner: a composite substantiated by one of its two halves, which
            # is precisely the class #5311 exists to end. A market that moves
            # the number is a speaker for it, whatever we call the variable.
            #
            # THE INSTRUMENT IS PER SOURCE, and that is not tidiness — the two
            # recognizers disagree and each is right about its own source:
            #
            #   * Kalshi keeps `is_game_winner_market`, the TICKER rule
            #     (`feeds_win_prob_blend`), exactly as before. The class
            #     recognizer would be a regression here: measured, it reads
            #     False on `Fight Night: Silva vs Delgado`
            #     (`KXUFCFIGHT-26SEP12SILDEL`) because the colon stops the title
            #     being a bare matchup and no winner word appears — a real fight
            #     winner, refused. This is `admissible_as_blend_speaker`'s own
            #     documented asymmetry and this queue does not move it.
            #   * Every other source has no ticker signal — that absence IS the
            #     defect — so the class recognizer decides, via
            #     `admissible_as_blend_speaker(..., is_primary=False)`. A
            #     contributor is never "the primary" for admission purposes:
            #     the exemption exists for the row the live writers have always
            #     trusted to SPEAK, not for a second row averaged into it.
            #     Measured on the same names: `Zverev vs. Khachanov` and
            #     `Chicago Cubs vs Pittsburgh Pirates` admitted, `First Team to
            #     Score`, `Total Corners` and `St. Louis City SC 2 - 2 Minnesota
            #     United FC` refused.
            #
            # The earlier comment here warned that applying the predicate
            # unconditionally would retire the Polymarket devig. That is true of
            # `live_blend.is_game_winner_market`, which is hard-False off
            # Kalshi, and NOT of the class recognizer — two different functions
            # that share a name. Which one you reach for is the whole question.
            #
            # The Kalshi tennis case the original check was built for still
            # holds: `kxatpsetwinner` carries the same two player names as
            # `kxatpmatch`, so the mean of "wins the match" and "wins set 2"
            # would be stamped as the moneyline — a number belonging to neither
            # question. For a genuine per-team pair both markets share one
            # prefix, so the gate is a no-op there.
            if sibling.market.source == "kalshi":
                if not is_game_winner_market(sibling.market):
                    continue
            elif not admissible_as_blend_speaker(
                sibling.market,
                is_primary=False,
                outcomes=sibling.outcomes,
                # A CONTRIBUTOR IS GATED LIKE A SPEAKER (CERT-2646), and #4854
                # is part of the gate now. Without this the devig could average
                # a live price with a pre-kickoff one and publish the mean.
                event_commence_time=getattr(sibling, "event_commence_time", None),
            ):
                continue
            sibling_reading = _home_probability_for_market(
                sibling, matchup, home_team_name, away_team_name,
            )
            if sibling_reading is not None:
                home_prob = (home_prob + sibling_reading[0]) / 2.0
                devigged = True
                contributors.append(sibling.market)

    return BlendReading(
        home_probability=home_prob,
        market=speaker.market,
        outcome=outcome,
        yes_probability=yes_prob,
        devigged=devigged,
        # `speaker.market`, never `primary.market`: the loop above falls through
        # the group until a market can speak, so those are not always the same
        # row. Naming the primary here would be worse than naming nothing — it
        # would substantiate a reading with a market that did not produce it.
        #
        # `contributors` names the OTHER half of a devig for the same reason one
        # step out: a composite is not the price of the market that happened to
        # speak first. `verified_record` drops the list when it holds only the
        # speaker, so a single-market reading is unchanged on the wire.
        eligibility=verified_record(
            rule=BLEND_ADMISSION_RULE,
            market_id=getattr(speaker.market, "id", None),
            source_market_id=getattr(speaker.market, "external_id", None),
            contributors=[_market_ref(m) for m in contributors],
        ),
    )
