"""
Binary contract → implied spread/total/projected score utilities.

Prediction markets (Kalshi, Polymarket) offer binary "Team wins by X+"
contracts at multiple thresholds. This module:
1. Derives an implied spread by interpolating the 50% probability crossover
2. Derives an implied total from "Total exceeds X" contracts
3. Combines spread + total into a projected final score

Example:
    contracts = [
        {"threshold": 1.0, "probability": 0.87},
        {"threshold": 3.5, "probability": 0.76},
        {"threshold": 5.5, "probability": 0.66},
        {"threshold": 7.5, "probability": 0.60},
        {"threshold": 10.5, "probability": 0.48},
        {"threshold": 14.5, "probability": 0.26},
    ]
    implied = binary_to_implied_spread(contracts)
    # => {"spread": -10.0, "confidence": 0.95}
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, Sequence

logger = logging.getLogger(__name__)


# Fallback preference between venues when their readings are equally trusted.
PROJECTION_SOURCE_ORDER: tuple[str, ...] = ("kalshi", "polymarket", "sportsbook")


# Two bracketing rungs whose thresholds differ by less than this sit on the SAME
# line — they can only come from two ladders pooled onto one event, never from
# one ladder's own rungs.
_SAME_LINE_EPSILON = 1e-9

# Below this the two bracketing prices are the same price (the module's existing
# notion of a degenerate straddle, kept as one constant so the interpolation and
# the confidence rule cannot drift apart).
_DEGENERATE_PROB_RANGE = 0.001

# What a same-line DISAGREEMENT scores. The width-based formula reads a
# zero-width bracket as a perfect one, so the least informative input available
# earned the maximum score (#4035). The value is deliberately below the score
# any single-point-gap ladder can reach, so a contradiction can never outrank a
# real bracket — the arm survives to be served, it just stops being preferred.
_CONTRADICTION_CONFIDENCE = 0.3


def _threshold_order(contract: dict) -> tuple[float, float]:
    """Deterministic sort key for a ladder's rungs: threshold, then price desc.

    Sorting on threshold alone leaves rungs that share a threshold in whatever
    order the rows arrived in, and the crossover walk takes the FIRST straddling
    pair — so one pool answered two different ways depending on row order, which
    no query guarantees (#4035). The production pool at 10.5 read
    ``total=10.5 confidence=1.0`` or ``total=11.1 confidence=0.9`` from the same
    three rows. Descending price within a threshold also keeps the walk's
    "probability falls as the threshold rises" assumption true across the tie.
    """
    return (contract["threshold"], -contract["probability"])


def ladder_recrosses(sorted_contracts: Sequence[dict], crossover: float) -> bool:
    """Does this pool price ABOVE the crossover again after pricing BELOW it?

    A ladder is a statement about one quantity: ``P(total > x)`` falls as ``x``
    rises, so once the pool has priced a threshold under the crossover, no
    higher threshold can price over it. A pool that does climb back is not one
    ladder — it is two market families poured into one pot — and it does not
    name one value: it straddles the crossover in several places, and which of
    them the walk returns is decided by :func:`_threshold_order`, not by the
    market.

    🔴 The comparisons are STRICT on purpose. A rung sitting exactly ON the
    crossover is neither above nor below it, and counting it as both is how the
    obvious version of this test — "count the adjacent pairs that straddle" —
    reports two crossings for a perfectly monotone ladder. Two arms measured on
    production read that way (14780146's Polymarket total ``… 37.5@0.535
    38.5@0.500 39.5@0.485 …`` and 14780144's Polymarket spread ``… 7.5@0.525
    8.5@0.500 10.5@0.440 …``), and demoting either would have handed a
    reader's page to the worse arm.

    Takes the pool ALREADY sorted by :func:`_threshold_order` so it reads the
    same rung order the walk does; an unsorted pool would answer about a
    sequence no derivation ever sees.
    """
    prices = [contract["probability"] for contract in sorted_contracts]
    above = [i for i, price in enumerate(prices) if price > crossover]
    below = [i for i, price in enumerate(prices) if price < crossover]
    # The two index sets are disjoint by construction, so no rung can be both
    # the last above and the first below: `>` and `>=` are the same test here.
    return bool(above and below and max(above) > min(below))


def _bracket_confidence(
    bracket_width: float,
    prob_range: float,
    divisor: float,
    pool_recrosses: bool,
) -> float:
    """Score how much the bracketing pair tells us, 0-1.

    Normally that is how tightly the pair sits around the crossover: the narrower
    the bracket, the better the interpolation is pinned.

    The exception is a bracket of zero width, which cannot come from one ladder.
    Two rungs on the SAME line come from two ladders pooled onto one event, and
    then the width says nothing at all:

    * priced the same (``prob_range`` below :data:`_DEGENERATE_PROB_RANGE`) the
      ladders AGREE the line is a coin flip — genuinely the best evidence there
      is, and it keeps the maximum score;
    * priced apart they CONTRADICT each other, which the width-based formula
      scored 1.0 — the maximum — for being maximally uninformative (#4035).

    ``pool_recrosses`` (:func:`ladder_recrosses`) is the same failure one step
    out: there the two ladders collided on a single line, here they sit side by
    side and the walk brackets the crossover inside whichever one it reaches
    first. The width of that bracket is a fact about the winning family, not
    about the pool, so a narrow bracket in a contaminated pot scored 0.9 while
    the clean venue beside it scored 0.8 — which is how Sunday's Texans–Bills
    page came to project a **7 – 9** football final off an implied total of 16
    (#5413). The bracket width says nothing once the pool is not one ladder, so
    the same constant answers both.

    🔴 This is a *scoring* rule, not a refusal, and that is what lets it need no
    tolerance for market noise. #3965 made this module refuse to invent a value
    it cannot locate; here a value IS located, so the arm is still served and
    only its standing changes — a demoted arm that is the only one left is
    served exactly as before, and two demoted arms fall back to
    :data:`PROJECTION_SOURCE_ORDER`, which is today's answer. The rule can
    therefore only move a page when there is a cleaner arm to move it to, so a
    false positive costs a reader nothing.

    Which of a contaminated pool's several crossings is the real one is NOT
    decided here, and deliberately: it needs to know which market family each
    rung came from, and the fold that pooled them is a matching defect, filed
    and not patched here (D35, #2693). Measured over the 686 scheduled/live
    events in the ±48h window (2026-09-12), 618 arms carrying a ladder: 76
    re-cross, 74 of them keep the projection they serve today, and exactly two
    pages change — both NFL, both from a two-digit football score to a real one.
    """
    if pool_recrosses:
        return _CONTRADICTION_CONFIDENCE
    if bracket_width < _SAME_LINE_EPSILON and prob_range >= _DEGENERATE_PROB_RANGE:
        return _CONTRADICTION_CONFIDENCE
    return max(0.0, min(1.0, 1.0 - (bracket_width / divisor)))


def _projection_source_rank(
    implied: dict,
    source: str,
    order: Sequence[str],
) -> tuple[float, int, str]:
    """Sort key for one source's arm: best first.

    Negated confidence so ``min``/``sorted`` read as "best first"; the trailing
    name keeps two unknown sources at equal confidence deterministic.
    """
    entry = implied.get(source) or {}
    try:
        confidence = float(entry.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    try:
        tie_break = order.index(source)
    except ValueError:
        tie_break = len(order)
    return (-confidence, tie_break, source)


def rank_projection_sources(
    implied: Optional[dict],
    order: Sequence[str] = PROJECTION_SOURCE_ORDER,
) -> list[str]:
    """Every source's arm, best first, by the rule ``select_projection_source`` picks with.

    The ranked list exists so a caller that finds the best arm unusable can walk
    to the next one instead of serving the unusable answer or nothing at all
    (#3921 repair `3921-PROJECTION-SELECTION-CANNOT-EMIT-NEGATIVE-SCORES`).
    """
    if not implied:
        return []
    return sorted(implied, key=lambda s: _projection_source_rank(implied, s, order))


def select_projection_source(
    implied: Optional[dict],
    order: Sequence[str] = PROJECTION_SOURCE_ORDER,
) -> Optional[str]:
    """Pick which source's implied value feeds the projected final score.

    Highest ``confidence`` wins; ``order`` breaks ties. Until #3921 the choice
    was position in ``order`` alone, so a Kalshi spread at confidence 0.3 beat
    a sportsbook spread at confidence 1.0 sitting in the same dict — the
    confidence was computed, serialised, and never read by the one thing it
    was computed for.

    A source missing from ``order`` is still eligible: it sorts after the
    known ones rather than being dropped, so a venue added after this list
    was written can never be silently discarded by an allowlist that predates
    it. A missing or unparseable ``confidence`` sorts as 0.0 — still eligible,
    because a sole arm is better than no projection, but never preferred over
    an arm that states one.

    This is ``rank_projection_sources(...)[0]`` and is kept as the name callers
    use when they want the single best arm; the two can never disagree because
    there is one ranking rule.
    """
    ranked = rank_projection_sources(implied, order)
    return ranked[0] if ranked else None


@dataclass
class ImpliedSpread:
    """Result of binary-to-spread derivation."""
    spread: float  # Negative = favorite (e.g., -10 means favorite by 10)
    confidence: float  # 0-1, how close the bracketing contracts are to 50%
    lower_threshold: float
    upper_threshold: float
    lower_prob: float
    upper_prob: float


def home_margin_from_spread(spread: float) -> float:
    """Convert a betting-line spread into the chart's ``home - away`` axis.

    🔴 There are TWO opposite sign conventions in this payload and they are one
    negation apart, which is exactly why they were confused (#3948 repair
    `3948-KALSHI-IMPLIED-LINE-MATCHES-HOME-MARGIN-AXIS`):

    * ``spread`` is **betting-line sign** — negative means the HOME team is
      favoured. Every producer agrees: ``binary_to_implied_spread`` returns
      ``-round(spread, 1)`` and the sportsbook arm computes ``away - home``.
      ``projected_final_score`` consumes this convention and is correct.
    * ``home_margin`` is the **chart axis** — positive means the HOME team is
      leading, matching ``projected_home_score - projected_away_score``, which
      is how `ScoreDifferentialChart` builds every other series it draws.

    Plotting ``spread`` on that axis mirrors the line about zero: a Giants-home
    ladder with Dallas favoured by 3 yields ``spread=+3.0``, which the chart
    would draw as the Giants leading by 3 while the hero favours Dallas.

    Rendered consumers read ``home_margin`` and never re-derive the flip — one
    named rule, in one place, instead of a negation remembered at each call.
    """
    return -spread


@dataclass
class ImpliedTotal:
    """Result of binary-to-total derivation."""
    total: float
    confidence: float
    lower_threshold: float
    upper_threshold: float
    lower_prob: float
    upper_prob: float


@dataclass
class ProjectedScore:
    """Projected final score from spread + total."""
    home_score: float
    away_score: float
    spread: float
    total: float
    spread_source: Optional[str] = None
    total_source: Optional[str] = None


def binary_to_implied_spread(
    contracts: list[dict],
    crossover: float = 0.50,
) -> Optional[ImpliedSpread]:
    """
    Derive implied spread from binary "wins by X+" contracts.

    Args:
        contracts: List of dicts with "threshold" (float) and "probability" (float, 0-1).
                   Threshold is the margin (e.g., 7.5 means "wins by 7.5+").
                   Probability is the market's implied probability of that outcome.
        crossover: The probability to interpolate at (default 0.50).

    Returns:
        ImpliedSpread with the interpolated spread, or None when the ladder
        does not locate one — either fewer than two rungs, or no adjacent pair
        straddling ``crossover``. A ladder whose rungs all sit on one side of
        50% implies nothing and says so by returning None (#3965); it is never
        extrapolated past its own last rung.
    """
    if not contracts or len(contracts) < 2:
        return None

    # Sort by threshold ascending
    sorted_contracts = sorted(contracts, key=_threshold_order)
    pool_recrosses = ladder_recrosses(sorted_contracts, crossover)

    # Find two adjacent contracts that straddle the crossover
    for i in range(len(sorted_contracts) - 1):
        low = sorted_contracts[i]
        high = sorted_contracts[i + 1]

        low_prob = low["probability"]
        high_prob = high["probability"]

        # Probabilities should decrease as threshold increases
        # (harder to win by more points)
        if low_prob >= crossover >= high_prob:
            # Linear interpolation
            prob_range = low_prob - high_prob
            if prob_range < _DEGENERATE_PROB_RANGE:
                # Degenerate case: both ~50%
                spread = (low["threshold"] + high["threshold"]) / 2
            else:
                fraction = (low_prob - crossover) / prob_range
                spread = low["threshold"] + fraction * (high["threshold"] - low["threshold"])

            # Confidence based on how tight the bracket is
            bracket_width = high["threshold"] - low["threshold"]
            confidence = _bracket_confidence(
                bracket_width, prob_range, 20.0, pool_recrosses
            )

            return ImpliedSpread(
                spread=-round(spread, 1),  # Negative = favorite
                confidence=round(confidence, 2),
                lower_threshold=low["threshold"],
                upper_threshold=high["threshold"],
                lower_prob=low_prob,
                upper_prob=high_prob,
            )

    # No rung crosses 50%, so this ladder does not locate a spread and we
    # refuse rather than invent one (#3965).
    #
    # Until now the two one-sided cases each extrapolated past the end of the
    # ladder — `-first * 0.5` when every rung sat below the crossover,
    # `-last * 1.5` when every rung sat above it. Both multipliers are
    # arbitrary, and the second one is how `/events/15307194` came to serve an
    # implied spread of **-14.25 runs** (`-9.5 * 1.5`) off a Polymarket ladder
    # priced 1.000 at all twenty of its rungs: a dead price surface that says
    # nothing was read as the most lopsided baseball game ever played.
    #
    # 🔴 The extrapolation is not merely imprecise — on the signed home-margin
    # axis #3948 introduced, it can land on the WRONG SIDE of its own data.
    # `-last * 1.5` treats the threshold as a positive magnitude, so a negative
    # rung is pushed further negative instead of toward the crossover. Measured
    # on `/events/15307719` (Nippon-Ham at SoftBank): rungs `-2.5 @ 0.770` and
    # `-1.5 @ 0.685`. Probability falls as the threshold rises, so
    # `P(home_margin >= -1.5) = 0.685` puts the 50% crossover ABOVE -1.5 — yet
    # the branch returned `home_margin = -2.25`, below every threshold the
    # ladder priced. It is the two sign conventions colliding again; see
    # `home_margin_from_spread`.
    #
    # Measured cost of refusing, over the 318 scheduled/live events in the ±48h
    # window that actually render projections (2026-09-08): the all-below
    # branch fired **0 times**, the all-above branch **3 times**. Two were this
    # defect and both events keep their projection, because their Kalshi arm
    # already crosses cleanly and already outranks on confidence (0.85 vs 0.3);
    # the third was the wrong-signed NPB arm above. **0 correct projections
    # lost.** What goes away is the rendered line: `ScoreDifferentialChart`
    # draws every non-sportsbook arm on presence alone, so the -14.25 was a
    # chart line at +14.25 home margin beside a Kalshi line at +0.2.
    #
    # `binary_to_implied_total` has never had these branches and already
    # returns None here; the two derivations now agree.
    return None


def binary_to_implied_total(
    contracts: list[dict],
    crossover: float = 0.50,
) -> Optional[ImpliedTotal]:
    """
    Derive implied total from binary "total exceeds X" contracts.

    Same interpolation logic as spread, but for total points.

    Args:
        contracts: List of dicts with "threshold" (float) and "probability" (float, 0-1).
                   Threshold is the points total (e.g., 220.5 means "over 220.5").
        crossover: The probability to interpolate at (default 0.50).
    """
    if not contracts or len(contracts) < 2:
        return None

    sorted_contracts = sorted(contracts, key=_threshold_order)
    pool_recrosses = ladder_recrosses(sorted_contracts, crossover)

    for i in range(len(sorted_contracts) - 1):
        low = sorted_contracts[i]
        high = sorted_contracts[i + 1]

        low_prob = low["probability"]
        high_prob = high["probability"]

        if low_prob >= crossover >= high_prob:
            prob_range = low_prob - high_prob
            if prob_range < _DEGENERATE_PROB_RANGE:
                total = (low["threshold"] + high["threshold"]) / 2
            else:
                fraction = (low_prob - crossover) / prob_range
                total = low["threshold"] + fraction * (high["threshold"] - low["threshold"])

            bracket_width = high["threshold"] - low["threshold"]
            confidence = _bracket_confidence(
                bracket_width, prob_range, 10.0, pool_recrosses
            )

            return ImpliedTotal(
                total=round(total, 1),
                confidence=round(confidence, 2),
                lower_threshold=low["threshold"],
                upper_threshold=high["threshold"],
                lower_prob=low_prob,
                upper_prob=high_prob,
            )

    return None


def projected_final_score(
    spread: float,
    total: float,
    home_is_favorite: bool = True,
) -> ProjectedScore:
    """
    Calculate projected final score from spread + total.

    Formula:
        If home is favorite (spread is negative):
            home_score = (total - spread) / 2   (higher because they're favored)
            away_score = (total + spread) / 2
        If away is favorite:
            home_score = (total + spread) / 2
            away_score = (total - spread) / 2

    Note: spread should be negative for the favorite.
    """
    # spread is negative for favorite, so:
    # home_score = (total + abs(spread)) / 2 when home is favorite
    # which is (total - spread) / 2 since spread is negative
    home_score = (total - spread) / 2
    away_score = (total + spread) / 2

    return ProjectedScore(
        home_score=round(home_score, 1),
        away_score=round(away_score, 1),
        spread=spread,
        total=total,
    )


def projection_is_renderable(projection: ProjectedScore) -> bool:
    """Can this pair be shown to a reader as a final score?

    A team cannot score a negative number of points, so a pair whose margin
    exceeds its total is not a scoreline — it is proof that the spread and the
    total came from two different quantities. Production served
    ``7.9 – -6.4`` on a Detroit v Minnesota page (#3951) because a spread
    derived from 1st-5-innings rungs (−14.25) was combined with a real
    9-inning total (8.0).

    This is the arithmetic invariant, not a plausibility heuristic: it asks
    only whether ``|spread| <= total``, and so can never reject a pair that
    describes one real game.
    """
    return projection.home_score >= 0 and projection.away_score >= 0


def select_projected_final(
    implied_spreads: Optional[dict],
    implied_totals: Optional[dict],
    order: Sequence[str] = PROJECTION_SOURCE_ORDER,
) -> Optional[tuple[str, str, ProjectedScore]]:
    """Best ``(spread_source, total_source, projection)`` whose scores are renderable.

    **The pair each arm's own best choice makes is tried first and returned if
    it is renderable**, so on every page whose projection is already a scoreline
    this is ``select_projection_source`` twice over and nothing else — the
    behaviour #3921 shipped, reached through the same call rather than through
    an argument that two rankings must agree. Only when that pair is not a
    scoreline does the walk begin, which is the whole of its job: the required
    repair `3921-PROJECTION-SELECTION-CANNOT-EMIT-NEGATIVE-SCORES` asks that an
    unusable pair fall back to the next valid source rather than be served.

    ``None`` when no pair is renderable. Serving no projection is the correct
    end of the walk: a reader who sees nothing has lost a number, while a
    reader who sees ``8 – -6`` has been told something false about the game.
    """
    if not implied_spreads or not implied_totals:
        return None

    def attempt(spread_source, total_source):
        spread = (implied_spreads.get(spread_source) or {}).get("spread")
        total = (implied_totals.get(total_source) or {}).get("total")
        if spread is None or total is None:
            return None
        projection = projected_final_score(spread, total)
        if projection_is_renderable(projection):
            return (spread_source, total_source, projection)
        return None

    # The pair #3921 would have served, tried on its own terms first.
    preferred = attempt(
        select_projection_source(implied_spreads, order),
        select_projection_source(implied_totals, order),
    )
    if preferred is not None:
        return preferred

    pairs = [
        (spread_source, total_source)
        for spread_source in rank_projection_sources(implied_spreads, order)
        for total_source in rank_projection_sources(implied_totals, order)
    ]
    pairs.sort(
        key=lambda pair: (
            _projection_source_rank(implied_spreads, pair[0], order)[0]
            + _projection_source_rank(implied_totals, pair[1], order)[0],
            _projection_source_rank(implied_spreads, pair[0], order)[1:],
            _projection_source_rank(implied_totals, pair[1], order)[1:],
        )
    )

    for spread_source, total_source in pairs:
        found = attempt(spread_source, total_source)
        if found is not None:
            return found

    return None


# =========================================================================
# Market title parsing — extract threshold from outcome/market names
# =========================================================================

# Spread patterns: "Team wins by 9.5+", "BOS -9.5", "+9.5", etc.
_SPREAD_THRESHOLD_RE = re.compile(
    r"(?:wins?\s+by|margin)\s+(\d+(?:\.\d+)?)\+?"
    r"|(?:^|[a-zA-Z]\s+)([+-]\d+(?:\.\d+)?)\s*(?:points?|pts?)?\s*$"
    r"|(?:spread|by)\s+([+-]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

# Total patterns: "Over 220.5", "Total exceeds 219.5", "O/U 222", etc.
_TOTAL_THRESHOLD_RE = re.compile(
    r"(?:over|exceeds?|above)\s+(\d+(?:\.\d+)?)"
    r"|(?:total|o/u)\s+(\d+(?:\.\d+)?)"
    r"|(\d+(?:\.\d+)?)\s+(?:or\s+more|total)",
    re.IGNORECASE,
)


# Kalshi's own game-spread phrasing, which the patterns above cannot read:
# "Dallas wins by over 10.5 points" (#3948). The unit is a closed set measured
# across all 57,631 production rungs — points 28,837 / runs 20,547 / goals 8,247
# — and is required rather than optional on purpose: "wins by over 10.5 outs"
# is a player prop, and a margin parser that accepts any trailing word would
# feed it to the game's spread ladder.
_MARGIN_RUNG_RE = re.compile(
    r"^\s*(?P<team>.+?)\s+wins?\s+by\s+over\s+"
    r"(?P<threshold>\d+(?:\.\d+)?)\s*"
    r"(?:points?|runs?|goals?)\s*$",
    re.IGNORECASE,
)


def parse_margin_rung(text: str) -> Optional[tuple[str, float]]:
    """Split "Dallas wins by over 10.5 points" into ``("Dallas", 10.5)``.

    Returns ``None`` for anything that is not this phrasing, including the
    legacy forms ``extract_spread_threshold`` already reads.
    """
    match = _MARGIN_RUNG_RE.match(text or "")
    if not match:
        return None
    try:
        return match.group("team").strip(), float(match.group("threshold"))
    except (TypeError, ValueError):
        return None


def _name_tokens(name: Optional[str]) -> list[str]:
    """Lowercase word tokens with punctuation removed. ``A's`` -> ``["as"]``."""
    cleaned = re.sub(r"[^a-z0-9\s]", "", (name or "").lower())
    return [token for token in cleaned.split() if token]


# Rung short forms the token rule provably cannot reach, rewritten BEFORE it
# runs (#3981).
#
# Deliberately data rather than a branch inside `_rung_names_side`: the
# prefix/initials rule is a general contract with its own guard, and a
# hard-coded club inside it would make that contract untrue and hide the next
# miss. A short form that needs help is declared here, with the reason.
#
# `A's` is the whole population today. `_name_tokens("A's")` -> `["as"]`, and
# `events` stores the club as the single token `Athletics`, which `as` reaches
# by neither arm: the prefix arm asks whether "athletics" starts with "as" (it
# starts "at"), and the initials arm compares "a" to "as". So the resolver
# refuses, and the caller correctly drops the rung rather than guess a side —
# 470 `futures_outcomes` spread rungs across 144 markets read `A's wins by ...`
# (`name LIKE 'A''s wins by%'`, measured on production 2026-09-09 05:55Z).
#
# The ladder is NOT dropped whole, and the distinction is the point: all 144 of
# those markets are mixed (0 are all-A's), so the opponent's rungs resolve and
# the A's rungs do not — 470 of the 1,266 rungs in those markets, 37%, are
# discarded, and the spread is then inferred from ONE side. A one-sided ladder
# is a confident answer built on half the evidence, not a missing one; see
# `margin_rung_on_home_axis` below on why a confident wrong spread is worse
# than shipping nothing.
#
# Keyed on the WHOLE token sequence rather than per token, so a rewrite can
# never fire inside a longer name — `["kansas"]` and `["las","vegas"]` are
# untouched, and a rung reading "As" as part of some longer phrase never
# reaches the table at all.
_RUNG_TOKEN_ALIASES: dict[tuple[str, ...], tuple[str, ...]] = {
    ("as",): ("athletics",),
}


def _aliased_rung_tokens(rung_tokens: list[str]) -> list[str]:
    """The rung's tokens with a declared short form rewritten, else unchanged.

    This CANNOT widen a match to a second team, which is the property that
    keeps `resolve_rung_side`'s refusal intact: `athletics` reaches the club
    stored as `Athletics` and nothing else. The soccer clubs are safe by the
    shape of the prefix arm rather than by luck — it asks whether the SIDE
    token starts with the RUNG token, and "athletic" (Charlton Athletic,
    Athletic Club, Dover Athletic FC) does not start with "athletics".
    """
    return list(_RUNG_TOKEN_ALIASES.get(tuple(rung_tokens), rung_tokens))


def _rung_names_side(rung_tokens: list[str], side_tokens: list[str]) -> bool:
    """Could this rung's team text be naming the team called ``side_tokens``?

    Kalshi writes disambiguated short forms — ``New York G``, ``Chicago WS``,
    ``Los Angeles D`` — never the event's full team name, so an equality test
    against ``events.home_team_name`` matches nothing. Every rung token but the
    last must match in place; the last may be a prefix of the next word
    (``G`` -> ``Giants``) or the initials of the words that remain
    (``WS`` -> ``White Sox``).
    """
    if not rung_tokens or not side_tokens or len(rung_tokens) > len(side_tokens):
        return False
    for rung_token, side_token in zip(rung_tokens[:-1], side_tokens):
        if rung_token != side_token:
            return False
    last = rung_tokens[-1]
    remaining = side_tokens[len(rung_tokens) - 1:]
    if not remaining:
        return False
    if remaining[0].startswith(last):
        return True
    return last == "".join(token[0] for token in remaining)


def resolve_rung_side(
    team_text: str,
    home_team_name: Optional[str],
    away_team_name: Optional[str],
) -> Optional[str]:
    """``"home"``, ``"away"``, or ``None`` when the rung names neither or both.

    🔴 ``None`` is a refusal, and callers must drop the rung rather than pick a
    side. The market title cannot stand in for this: all three spread markets
    measured for #3948 name the AWAY team first (``Dallas vs New York: Spread``
    on a page whose home team is New York), so position in the title resolves
    the sign backwards. Ambiguity is real rather than theoretical — a rung
    reading only ``New York`` in Giants v Jets matches both sides, and guessing
    there inverts the scoreline instead of merely losing a rung.
    """
    # Aliases are consulted BEFORE the token rule and cannot widen a match to a
    # second team, so the refusal above still holds for genuinely ambiguous
    # rungs (#3981).
    rung_tokens = _aliased_rung_tokens(_name_tokens(team_text))
    names_home = _rung_names_side(rung_tokens, _name_tokens(home_team_name))
    names_away = _rung_names_side(rung_tokens, _name_tokens(away_team_name))
    if names_home and not names_away:
        return "home"
    if names_away and not names_home:
        return "away"
    return None


def rung_provider_code(
    outcome_external_id: Optional[str],
    market_external_id: Optional[str],
) -> Optional[str]:
    """Kalshi's own team code for one rung, or ``None`` when there isn't one.

    A rung's ticker is its market's ticker plus a per-team suffix:
    ``KXMLBSPREAD-26MAY051840ATHPHI-ATH3`` is the Athletics' 3rd rung in the
    market ``KXMLBSPREAD-26MAY051840ATHPHI``. The code is what remains after the
    market prefix and the trailing rung index — ``ATH``.

    🔴 This is an **id**, not a name. That is the whole point: ``ATH`` needs no
    spelling of "Athletics" to tell you that two rungs belong to the same team,
    which is what lets `resolve_rung_sides_by_code` place a rung whose own text
    the token rule cannot read (#4218).

    Keyed on the market's own ticker rather than a general pattern, per D55:
    the prefix must match exactly, or there is no code. A suffix that is all
    digits is a rung index with no team in it and yields ``None`` — the code is
    never inferred from digit count.
    """
    if not outcome_external_id or not market_external_id:
        return None
    prefix = f"{market_external_id}-"
    if not outcome_external_id.startswith(prefix):
        return None
    suffix = outcome_external_id[len(prefix):]
    code = re.sub(r"\d+$", "", suffix)
    return code or None


def resolve_rung_sides_by_code(
    market_external_id: Optional[str],
    rungs: Sequence[tuple[Optional[str], Optional[str]]],
    home_team_name: Optional[str],
    away_team_name: Optional[str],
) -> Optional[dict[str, Optional[str]]]:
    """Which side each of a spread market's two team codes is on.

    ``rungs`` is ``(outcome_name, outcome_external_id)`` for every outcome in
    one market. Returns:

    * ``None`` — this market is **not** code-resolvable, and the caller must
      keep resolving each rung on its own text (`margin_rung_on_home_axis`);
    * a dict keyed by **both** codes — **authoritative**, refusals included. A
      code mapped to ``None`` is refused, and the caller drops its rungs even
      though the token rule might have had an opinion.

    Two things the per-rung rule cannot do, both measured on the 5,901 linked
    Kalshi spread markets on production 2026-09-09:

    1. **A code inherits a side from its own siblings.** ``SF``'s rungs read
       both "San Francisco" and "SF"; the first resolves and the second does
       not, so today half a team's ladder is dropped while the other half is
       placed. Same code, same team, one side.
    2. **The second team is the one the first is not.** Where exactly one code
       resolves, the other names the opposite side by elimination — 260 markets
       / 1,241 rungs, including every ``A's`` market. Together these place
       **3,304** rungs that are dropped today, 71% of the 4,631 dropped.

    🔴 It also **refuses two markets that are served today**, and that is a fix,
    not a cost: where both codes resolve to the *same* side, both ladders are
    being poured onto one axis. Both live cases are mis-linked markets — a
    Texas–Texas A&M market on a Virginia Tech–Texas A&M event (11 rungs), a
    Michigan St.–Michigan market on a Michigan St.–Ohio St. event (29) — and a
    ladder built from two teams that are not playing each other is the confident
    wrong answer `margin_rung_on_home_axis` exists to avoid. The mis-link itself
    is a matching defect and is filed, not patched here (D35).

    The elimination step inherits the link: it is sound exactly when the
    market's two ladders are the event's two teams, which is what ``event_id``
    asserts. It does **not** guess from ticker order — ``BOUSUN`` is
    home-then-away and ``ATHPHI`` is away-then-home, so position resolves the
    sign backwards as often as not.
    """
    if not market_external_id:
        return None

    texts_by_code: dict[str, set[str]] = {}
    for name, external_id in rungs:
        parsed = parse_margin_rung(name or "")
        if parsed is None:
            continue  # not a margin rung; this map says nothing about it
        code = rung_provider_code(external_id, market_external_id)
        if code is None:
            # A margin rung with no code means the market's rungs are not all
            # id-anchored, so the partition this rule depends on is incomplete.
            return None
        texts_by_code.setdefault(code, set()).add(parsed[0])

    if len(texts_by_code) != 2:
        # One code is a one-sided ladder with nothing to eliminate against;
        # three or more is not the two-team shape this reasoning describes.
        return None

    sides: dict[str, Optional[str]] = {}
    for code, texts in texts_by_code.items():
        named = {
            resolve_rung_side(text, home_team_name, away_team_name) for text in texts
        } - {None}
        if len(named) > 1:
            # One code naming both sides is a contradiction about the same
            # team. Refuse the market rather than pick the majority.
            return {code: None for code in texts_by_code}
        sides[code] = named.pop() if named else None

    first, second = sorted(sides)
    anchored = [code for code in (first, second) if sides[code] is not None]
    if len(anchored) == 2:
        if sides[first] == sides[second]:
            return {first: None, second: None}
        return sides
    if len(anchored) == 1:
        known = anchored[0]
        other = second if known == first else first
        sides[other] = "away" if sides[known] == "home" else "home"
        return sides
    return {first: None, second: None}


def margin_rung_on_home_axis_for_side(
    text: str,
    probability: float,
    side: Optional[str],
) -> Optional[dict]:
    """`margin_rung_on_home_axis` for a side that is already known.

    Split out so a side resolved from the rung's provider code
    (`resolve_rung_sides_by_code`) is placed by exactly the same arithmetic as
    one resolved from its text — there is one home-axis rule, not two.

    ``side=None`` is a refusal and returns ``None``, so an authoritative refusal
    from the code map drops the rung just as an unresolvable name does.
    """
    parsed = parse_margin_rung(text)
    if parsed is None or side is None:
        return None
    threshold = parsed[1]
    if side == "home":
        return {"threshold": threshold, "probability": probability}
    return {"threshold": -threshold, "probability": 1.0 - probability}


def margin_rung_on_home_axis(
    text: str,
    probability: float,
    home_team_name: Optional[str],
    away_team_name: Optional[str],
) -> Optional[dict]:
    """One Kalshi margin rung as a contract on the HOME-MARGIN axis.

    A Kalshi spread market carries BOTH teams' ladders in one pool, so the two
    halves have to be put on one axis before `binary_to_implied_spread` — which
    requires probability to fall as the threshold rises — can read them:

    * a home rung keeps its threshold and its price;
    * an away rung is **negated and inverted**: ``P(Dallas wins by over 1.5)``
      is ``P(home margin > -1.5) = 1 - p``.

    🔴 The inversion is the half that signing alone leaves out, and leaving it
    out is worse than shipping nothing. Measured on event 14637256's real 25
    rungs, sign-only produces 13 monotonicity violations and derives a spread of
    0.5 points at confidence 0.85 — a confident wrong answer on a game the
    market prices at 3 — where sign-and-invert produces 0 violations and 3.0 at
    0.95 (`artifacts-lane1-183/validate_3948_design.py`).

    ``None`` when the text is not a margin rung, or when the side cannot be
    resolved.
    """
    parsed = parse_margin_rung(text)
    if parsed is None:
        return None
    side = resolve_rung_side(parsed[0], home_team_name, away_team_name)
    return margin_rung_on_home_axis_for_side(text, probability, side)


def extract_spread_threshold(text: str) -> Optional[float]:
    """Extract the spread threshold from a market title or outcome name."""
    m = _SPREAD_THRESHOLD_RE.search(text)
    if m:
        for g in m.groups():
            if g is not None:
                try:
                    return abs(float(g))
                except ValueError:
                    continue
    return None


def extract_total_threshold(text: str) -> Optional[float]:
    """Extract the total threshold from a market title or outcome name."""
    m = _TOTAL_THRESHOLD_RE.search(text)
    if m:
        for g in m.groups():
            if g is not None:
                try:
                    return float(g)
                except ValueError:
                    continue
    return None
