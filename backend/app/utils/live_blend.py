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
from typing import Any, Optional, Sequence

from app.utils.game_market_class import classify_game_market_class
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
    """

    market: Any
    outcomes: Sequence[Any]


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


def admissible_as_blend_speaker(market: Any, *, is_primary: bool) -> bool:
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
    """
    if getattr(market, "source", None) == "kalshi" and is_primary:
        return True
    return _class_says_game_winner(market)


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
    entries = list(group or [])
    if not entries:
        return 0
    primary = select_primary_market(entries)
    primary_id = primary.market.id if primary is not None else None
    return sum(
        1
        for entry in entries
        if admissible_as_blend_speaker(
            entry.market, is_primary=entry.market.id == primary_id
        )
    )


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
        if not admissible_as_blend_speaker(entry.market, is_primary=is_primary):
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
            elif not admissible_as_blend_speaker(sibling.market, is_primary=False):
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
