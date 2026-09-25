"""
Odds conversion and calculation utilities.

This module handles all the math for converting betting odds
to probabilities, projected scores, and excitement indices.
"""

import math
from typing import Container, Dict, List, Mapping, Optional, Sequence, Tuple

from statistics import mean, median


def american_to_probability(odds: int) -> float:
    """
    Convert American odds to implied probability.
    
    American odds format:
    - Positive (+150): Amount won on a $100 bet
    - Negative (-150): Amount needed to bet to win $100
    
    Examples:
        >>> american_to_probability(-150)
        0.6  # 60% implied probability
        >>> american_to_probability(150)
        0.4  # 40% implied probability
    """
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)


def decimal_to_probability(odds: float) -> float:
    """
    Convert decimal odds to implied probability.
    
    Examples:
        >>> decimal_to_probability(1.67)
        0.5988  # ~60%
        >>> decimal_to_probability(2.50)
        0.4  # 40%
    """
    return 1 / odds


def remove_vig_nway(probabilities: Sequence[Optional[float]]) -> Optional[List[float]]:
    """
    Remove the bookmaker's vig from an N-outcome mutually-exclusive market.

    Bookmakers price every outcome of a market so the implied probabilities sum
    to MORE than 100%. The excess is the overround (vig). On a two-way market
    that excess is typically 4-6%; on a 30-outcome futures market it is routinely
    16-33% (measured on ``MLB World Series Winner``, 2026-08-13: fanduel 16.6%,
    betrivers 32.5%). Proportional normalization divides it back out.

    This is the N-way generalization of :func:`remove_vig`, which handles only
    the home/away pair. It exists because there was NO n-way helper: every caller
    that needed one either open-coded the division or — worse — compared a RAW,
    vig-inclusive book price against a de-vigged consensus, which is #1844: the
    grid's "Biggest Movers" row rendered 29 of 30 teams falling every single day,
    because ``merged - old_p`` subtracted a 1.3178-sum column from a 0.9873-sum
    one. The bias is negative by construction and proportional to each outcome's
    probability, so it looks exactly like real market movement.

    **Standing rule this encodes (Alex, 2026-08-13): raw vig-inclusive book
    prices NEVER enter probability arithmetic, anywhere.** De-vig first, then
    compare, average, or subtract.

    Args:
        probabilities: One bookmaker's raw implied probabilities for EVERY
            outcome it quotes on a single mutually-exclusive market.

    Returns:
        A list in the same order, summing to 1.0 — or ``None`` when the input
        cannot be normalized (empty, contains ``None``, negative, non-finite, or
        sums to zero). ``None`` is deliberate: a caller must not silently treat
        an un-normalizable column as if it were a distribution. That is the
        gotcha-#53 shape — an absence and a fact must not share a return value.

    Examples:
        >>> remove_vig_nway([0.55, 0.50])  # two-way, 5% overround
        [0.5238095238095238, 0.47619047619047616]
        >>> sum(remove_vig_nway([0.39, 0.16, 0.12, 0.65]))  # 32% overround
        1.0
    """
    values: List[float] = []
    for p in probabilities:
        if p is None:
            return None
        try:
            value = float(p)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or value < 0:
            return None
        values.append(value)

    if not values:
        return None

    total = sum(values)
    if total <= 0:
        return None

    return [value / total for value in values]


def remove_vig(home_prob: float, away_prob: float) -> Tuple[float, float]:
    """
    Remove the bookmaker's vig (juice) to get true probabilities.

    Bookmakers set odds so implied probabilities sum to >100%.
    The excess is their profit margin (vig).

    This normalizes the probabilities to sum to exactly 100%.

    Thin two-way wrapper over :func:`remove_vig_nway` — ONE normalization
    implementation, so the two-way and N-way paths can never drift apart.

    Examples:
        >>> remove_vig(0.55, 0.50)  # Sum is 1.05 (5% vig)
        (0.5238, 0.4762)  # Now sums to 1.0
    """
    normalized = remove_vig_nway([home_prob, away_prob])
    if normalized is None:
        # Un-normalizable (both zero / non-finite). Pass through rather than
        # raising: callers historically got a ZeroDivisionError here, which is
        # strictly worse than returning the input unchanged.
        return home_prob, away_prob
    return normalized[0], normalized[1]


def devig_consensus(
    book_columns: Mapping[str, Mapping[str, Optional[float]]],
    method: str = "mean",
    already_normalized: Container[str] = (),
) -> Dict[str, float]:
    """
    Build a de-vigged consensus across bookmakers for one N-way market.

    Each bookmaker's column is de-vigged on its OWN outcome set first (so a book
    with a 32% overround stops out-weighting a book with a 16% one), then the
    normalized values are aggregated across books per outcome.

    This is the single implementation of "what the market thinks", and it is
    deliberately shared by both the live path (``_aggregate_futures_outcomes``
    in ``app/tasks/futures.py``) and the historical path (``_compute_movers`` in
    ``app/routes/playoffs.py``). #1844's design constraint, in one sentence: a
    second copy written to serve the historical side re-creates exactly the
    divergence this closes.

    Args:
        book_columns: ``{bookmaker: {outcome_key: raw_implied_probability}}``.
            Raw means straight from American odds — vig-inclusive, NOT
            pre-normalized.
        method: Cross-book aggregation, passed to :func:`aggregate_probabilities`
            ("mean", "median", or "trimmed_mean").
        already_normalized: Bookmaker keys whose column is ALREADY a probability
            and must be aggregated as-is. De-vigging is only meaningful for a
            column of vig-inclusive prices over a mutually exclusive, exhaustive
            outcome set; applying :func:`remove_vig_nway` to anything else
            divides by whatever that column happens to sum to (#6675). Empty by
            default, so the live path is unchanged.

    Returns:
        ``{outcome_key: consensus_probability}``. Sums to ~1.0 whenever every
        book quotes the same outcome set. Empty dict when no book column could
        be normalized.

        The sum is "~1.0" rather than exactly 1.0 because books quote different
        SUBSETS (fanduel priced 25 of 30 World Series teams on 2026-08-13 where
        the other four priced all 30). Each book is normalized over what it
        actually quotes, so averaging partially-overlapping columns lands near,
        not on, 1.0. That is pre-existing behaviour, preserved here on purpose:
        both sides of a delta must be the SAME quantity, and changing the live
        side's semantics while fixing the historical side would defeat the fix.
    """
    per_outcome: Dict[str, List[float]] = {}

    for bookmaker, column in book_columns.items():
        if not column:
            continue
        keys = list(column.keys())
        if bookmaker in already_normalized:
            # This source publishes probabilities, not prices. Contribute the
            # column unchanged — normalizing it would re-scale by its own sum.
            normalized = [column[k] for k in keys]
        else:
            normalized = remove_vig_nway([column[k] for k in keys])
        if normalized is None:
            # This book's column is unusable; skip the BOOK, not the market.
            continue
        for key, value in zip(keys, normalized):
            if value is None:
                continue
            per_outcome.setdefault(key, []).append(value)

    consensus: Dict[str, float] = {}
    for key, values in per_outcome.items():
        aggregated = aggregate_probabilities(values, method=method)
        if aggregated is not None:
            consensus[key] = aggregated
    return consensus


def moneyline_to_probability(
    home_odds: int, 
    away_odds: int, 
    remove_juice: bool = True
) -> Tuple[float, float]:
    """
    Convert moneyline odds to win probabilities.
    
    Args:
        home_odds: American odds for home team
        away_odds: American odds for away team
        remove_juice: Whether to normalize probabilities
    
    Returns:
        Tuple of (home_probability, away_probability)
    
    Examples:
        >>> moneyline_to_probability(-150, 130)
        (0.5932, 0.4068)  # Home team ~59% favorite
    """
    home_prob = american_to_probability(home_odds)
    away_prob = american_to_probability(away_odds)

    if remove_juice:
        return remove_vig(home_prob, away_prob)

    return home_prob, away_prob


#: Below this, a book's quoted outcome set is INCOMPLETE and must not be
#: normalized. A market a book actually offers always sums ABOVE 1.0 — that
#: excess IS the vig, and it is how the book makes money, so a sum under 1.0 is
#: not a thin market but missing outcomes.
#:
#: Measured on production `odds_snapshots`, 2 days, raw home+away only
#: (2026-09-16): 25 soccer leagues span **0.743 – 0.808**; all 17 non-soccer
#: sports span **1.043 – 1.110**. No overlap, and nothing lands in between. The
#: floor sits at 0.95 — above every fragment by 14pp, below every complete
#: market by 9pp, and just under the theoretical minimum of 1.0 a zero-vig book
#: would post.
MARKET_COMPLETENESS_FLOOR = 0.95


def h2h_pair_on_the_full_board(
    home_odds: Optional[int],
    away_odds: Optional[int],
    other_odds: Sequence[Optional[int]] = (),
) -> Optional[Tuple[float, float]]:
    """``(home, away)`` de-vigged over EVERY outcome the book quotes, or None.

    #1011. :func:`moneyline_to_probability` normalizes the home/away PAIR, which
    is correct only when that pair is the whole market. On a soccer game winner
    it is not — the draw holds a quarter of the mass — and dividing it out
    inflates both named sides. Measured on production: `betting` matched
    ``kalshi_home/(kalshi_home+kalshi_away)`` at abs Δ 0.0151 over 80 events
    (discover/126), while the raw three-way home was 0.1289 away. At weight 3.0
    against 0.8 that put the blended hero **~8pp** onto the home team on every
    soccer match carrying a sportsbook line.

    **THE DRAW IS NEVER NAMED, AND THAT IS THE DESIGN.** ``other_odds`` is
    whatever else the book quotes; this function does not know or care that it
    is a draw, a tie, an "Empate" or a no-result. Only home and away are
    identified — by the team names the caller already matched on — and the rest
    is residual mass. So there is no vocabulary map to maintain and no sport to
    look up, which matters because the sport is the wrong question:

    🪤 **`cricket_odi` and `cricket_international_t20` read 1.0570 / 1.0585 on
    production — genuine, complete TWO-way markets — although cricket sits in
    ``DRAW_CAPABLE_CATEGORIES`` beside soccer.** Limited-overs cricket is not
    drawn the way Test cricket is. A rule that inferred three-wayness from the
    sport would have deleted the sportsbook line from every cricket match. Shape
    is decided by the outcome set the book actually quotes, exactly as the
    read-side ``market_omits_draw_authority`` decides it by evidence.

    Two outcomes take the identical arithmetic they take today, by construction
    rather than by care: the board is ``[home, away]``, and
    :func:`remove_vig_nway` over a pair IS :func:`remove_vig`. That also means a
    GENUINELY two-way soccer market — an advancement line, a shootout-decided
    tie — is preserved automatically, because it *quotes* two outcomes summing
    above 1 and is de-vigged over two.

    Returns ``None`` — a refusal, not a zero — when the board is unusable:
    either side missing, or a raw sum under :data:`MARKET_COMPLETENESS_FLOOR`.
    The second is the missing-draw case, and returning ``None`` rather than
    renormalizing is the whole point: a fragment scaled to 1.0 is exactly the
    defect above, re-created one book at a time. A refused book contributes
    nothing to the consensus instead of contributing a confident lie, which is
    gotcha #53's shape — "we cannot say" must not render as a number. A missing
    third outcome is never inferred as zero; it makes the board unreadable.
    """
    if home_odds is None or away_odds is None:
        return None

    board = [
        american_to_probability(home_odds),
        american_to_probability(away_odds),
    ]
    # A `None` among the others is an outcome we failed to read, not an outcome
    # the book declined to price. Skipping it lets the floor below judge the
    # board on what we actually hold, rather than asserting the gap is empty.
    board.extend(
        american_to_probability(price) for price in other_odds if price is not None
    )

    if sum(board) < MARKET_COMPLETENESS_FLOOR:
        return None

    normalized = remove_vig_nway(board)
    if normalized is None:
        return None
    return normalized[0], normalized[1]


#: How far apart the two named sides must be before either is called the
#: favourite. On a board whose pair sums to 1.0 this is exactly the 0.48/0.52
#: band it replaces: ``home - away > 0.04`` ⇔ ``2*home - 1 > 0.04`` ⇔
#: ``home > 0.52``. See :func:`favorite_from_pair`.
FAVORITE_MARGIN = 0.04

#: Binary floating point does not hold 0.04, and the equivalence above is
#: claimed AT the boundary, not near it: ``0.52 - (1 - 0.52)`` evaluates to
#: 0.040000000000000036, which is greater than ``FAVORITE_MARGIN`` while
#: ``0.52 > 0.52`` is false — so the exact edge of the old band, a value a
#: ``Numeric(5, 4)`` column can hold exactly, would be the one place the two
#: forms disagreed. Nine decimal places is five below anything the column can
#: store, so this admits the representation error and nothing else.
_MARGIN_EPSILON = 1e-9


def favorite_from_pair(
    home_prob: Optional[float],
    away_prob: Optional[float],
    margin: float = FAVORITE_MARGIN,
) -> Optional[str]:
    """``'home'`` / ``'away'`` / ``'even'`` from BOTH legs, or None. (#7055)

    Which of the two named sides is the shorter price, asked by comparing them
    to EACH OTHER rather than either of them to 0.5.

    🪤 **The pair does not sum to 1, by design, and the old rule assumed it
    did.** :func:`h2h_pair_on_the_full_board` de-vigs home and away over every
    outcome the book quotes, so on a draw-priced board the two named sides
    share only about three quarters of the mass and the draw keeps the rest —
    that fragment is the honest number and #1011 exists to stop anyone scaling
    it back to 1.0. The favourite determination never got the memo. It read the
    home leg alone against a two-way band::

        if home_prob > 0.52:   "home"
        elif home_prob < 0.48: "away"
        else:                  "even"

    On a three-way board BOTH sides usually sit under 0.48, so every such row
    was recorded ``away`` whichever side was actually shorter. Measured on
    production over the 14 days to 2026-09-18: **124 of 2,724** events carrying
    an opening pair contradict their own two stored numbers, every one of them
    in that single direction, and **0** of the two-way sports do — the mirror
    case cannot exist, because the band can only write ``home`` when the home
    leg alone clears 0.52. Brentford opened 0.3725 against Chelsea's 0.3648,
    was stored ``away``, won 3-0, and was chipped "Recent upset" above the two
    numbers saying it was not one.

    **A strict generalization, not a new rule.** Where the pair sums to 1.0 the
    two forms are algebraically the same band (see :data:`FAVORITE_MARGIN`), so
    every two-way sport takes the identical answer it takes today — which is
    why the production separation is perfect rather than merely large.

    **Deliberately NOT ``home/(home+away)`` against the old band.** Re-scaling
    the pair to 1.0 and reusing 0.48/0.52 agrees with this on almost every real
    board, but it is the exact operation :func:`h2h_pair_on_the_full_board`
    refuses, and a reader who found it here would be right to ask which rule
    this module actually holds. Comparing the legs needs no such scaling. The
    two differ only on a compressed board with a hairline gap — home 0.38 /
    away 0.35 is ``even`` here and ``home`` there — and on a card whose job is
    to claim an upset, ``even`` is both the more honest answer and the one that
    cannot manufacture the claim.

    **No sport lookup, for :func:`h2h_pair_on_the_full_board`'s reason:** shape
    is decided by the numbers in hand, not by the sport, because a sport is not
    a reliable witness to its own board (that function's cricket trap). So a
    row whose stored away leg is really ``1 - home`` wearing an away name —
    :func:`~app.utils.draw_priced_winner.away_is_the_complement`'s case, which
    the #6238 census found on 2 of 13 soccer cards — is not detected here and
    does not need to be: comparing a home leg against its own complement
    reproduces the old band exactly, so such a row keeps today's answer while
    every genuinely-quoted pair gets the right one. The change is monotone; it
    cannot make a row worse than it is now.

    Returns ``None`` — unanswerable, never a guess — when either leg is
    missing. There is no home-only fallback and that is deliberate: it would be
    the defect above, rebuilt as an error path. Nothing is lost by refusing,
    measured rather than assumed: of the 2,724 events above, **0** carry one
    leg without the other, so the legs are written as a pair or not at all.
    """
    if home_prob is None or away_prob is None:
        return None
    if abs(home_prob - away_prob) <= margin + _MARGIN_EPSILON:
        return "even"
    return "home" if home_prob > away_prob else "away"


def project_scores(
    spread: float,
    over_under: float,
) -> Tuple[float, float]:
    """
    Project final scores based on spread and total.

    The spread indicates expected point differential:
    - Negative spread means home team is favored
    - Positive spread means away team is favored

    Math:
    - home_score + away_score = over_under
    - home_score - away_score = abs(spread) (if home favored)

    Args:
        spread: Point spread (negative = home favored)
        over_under: Expected total points/runs/goals

    Returns:
        Tuple of (projected_home_score, projected_away_score)

    Examples:
        >>> project_scores(-14.5, 226)  # Home favored by 14.5, total 226
        (120.2, 105.8)
        >>> project_scores(3.5, 45)  # Away favored by 3.5, total 45
        (20.8, 24.2)
    """
    # Spread is typically negative when home is favored
    # home_score - away_score = -spread (since negative spread means home wins by that margin)
    # home_score + away_score = over_under
    # Solving: home_score = (over_under - spread) / 2
    #          away_score = (over_under + spread) / 2
    home_score = (over_under - spread) / 2
    away_score = (over_under + spread) / 2

    return round(home_score, 1), round(away_score, 1)


def sportsbook_spread_is_a_margin(sport_key: Optional[str]) -> bool:
    """False when a sport's sportsbook spread is a fixed handicap, not an expected margin.

    #8617. :func:`project_scores` reads the spread point as the expected margin.
    A baseball run line is pinned at ±1.5 whatever the matchup, so on a coin
    flip it projected ``4.7 – 3.1`` and the card printed "Proj 5-3" (event
    15318355, home 0.50, 2026-09-25). Same misreading as #8613 in the stat
    model. Mirrors the web's ``sportsbookSpreadIsAMargin`` (baseball false,
    everything else true). An unknown sport keeps the old answer.
    """
    return not str(sport_key or "").startswith("baseball")


def projection_contradicts_moneyline(
    home_probability: Optional[float],
    projected_home: Optional[float],
    projected_away: Optional[float],
) -> bool:
    """True when one book's projected leader is the team its OWN moneyline makes the underdog.

    #8231. ``project_scores`` reads the spread POINT and ignores its price, which
    is only sound when the point is the book's fair line. A run line (MLB) or puck
    line (NHL) is pinned at ±1.5 whatever the game state, and late in a decided
    game a book will hang the -1.5 on the trailing side at long odds. Measured on
    production, event 15316869 (Red Sox 2 - 3 Guardians), betmgm at 01:42:14Z:
    ``home_spread = -1.5 @ +3300`` / ``away +1.5 @ -10000`` beside its own
    moneyline at ``+900 / -2000`` (home 0.095). The point says Boston by 1.5, the
    price and the moneyline both say Boston is nearly dead, and the settled page's
    Score Differential chart ended on that mirror - the same book had quoted
    ``+1.5 @ -10000`` for Boston two minutes earlier.

    A projection whose leader disagrees with the same book's moneyline leader is
    not a projection, so it is refused and the book contributes no projected
    score. Its moneyline, spread and total are untouched. A tie on either side
    (a pick'em point, a 0.5 moneyline) is not a contradiction, and a missing
    input is not evidence of one.
    """
    if home_probability is None or projected_home is None or projected_away is None:
        return False
    lean = float(home_probability) - 0.5
    margin = float(projected_home) - float(projected_away)
    return (lean > 0 and margin < 0) or (lean < 0 and margin > 0)


def refuse_incoherent_projections(rows: List[dict]) -> List[dict]:
    """Null the projected pair on every served per-book row that contradicts its own moneyline.

    #8231, the per-book half of ``aggregate_bookmaker_odds``: the sportsbook table
    prints each book's projected score and the history's per-book lines carry
    them, so the refusal has to reach the rows as well as the consensus. Reads
    the row's already-oriented ``home_probability`` so a reversed book is judged
    after its sides are swapped back. Mutates and returns ``rows``.
    """
    for row in rows:
        if projection_contradicts_moneyline(
            row.get("home_probability"),
            row.get("projected_home_score"),
            row.get("projected_away_score"),
        ):
            row["projected_home_score"] = None
            row["projected_away_score"] = None
    return rows


# Sport-specific average totals for normalization
SPORT_AVG_TOTALS = {
    "americanfootball_nfl": 45.0,
    "americanfootball_ncaaf": 52.0,
    "basketball_nba": 220.0,
    "basketball_ncaab": 145.0,
    "baseball_mlb": 8.5,
    "icehockey_nhl": 6.0,
    "soccer_epl": 2.5,
    "soccer_mls": 2.8,
}


def calculate_gei(
    home_prob: float, 
    over_under: float, 
    sport_key: str
) -> float:
    """
    Calculate Game Excitement Index (GEI).
    
    Higher scores indicate more exciting games based on:
    - Closeness (games near 50/50 are more exciting)
    - Scoring (high-scoring games relative to sport average)
    
    Based on methodology from: https://lukebenz.com/post/gei/
    
    Args:
        home_prob: Home team's win probability (0-1)
        over_under: Expected total points/runs/goals
        sport_key: Sport identifier for average lookup
    
    Returns:
        GEI score from 0-100 (higher = more exciting)
    
    Examples:
        >>> calculate_gei(0.51, 230, "basketball_nba")
        85.7  # Close game, high scoring
        >>> calculate_gei(0.85, 180, "basketball_nba")
        32.1  # Blowout expected, lower scoring
    """
    # Closeness factor: peaks at 0.5, drops toward 0 or 1
    # Score of 1.0 when perfectly even, 0.0 when certain outcome
    closeness = 1 - abs(home_prob - 0.5) * 2
    
    # Scoring factor: how does this game's total compare to average?
    avg_total = SPORT_AVG_TOTALS.get(sport_key, 100.0)
    scoring_factor = min(over_under / avg_total, 1.5)  # Cap at 150%
    
    # Weighted combination
    # Closeness matters more than raw scoring
    gei = (closeness * 0.65) + (scoring_factor * 0.35)
    
    # Scale to 0-100
    return round(gei * 100, 1)


def format_probability(prob: float, style: str = "percent") -> str:
    """
    Format probability for display.
    
    Args:
        prob: Probability from 0-1
        style: 'percent' for "60%", 'decimal' for "0.60"
    
    Examples:
        >>> format_probability(0.593)
        "59%"
        >>> format_probability(0.593, style="decimal")
        "0.59"
    """
    if style == "percent":
        return f"{round(prob * 100)}%"
    else:
        return f"{prob:.2f}"


def probability_to_american(prob: float) -> Optional[int]:
    """
    Convert probability back to American odds.

    Useful for displaying "fair odds" after removing vig.
    Returns None for extreme probabilities (0.0 or 1.0) where
    American odds are undefined.

    Examples:
        >>> probability_to_american(0.6)
        -150
        >>> probability_to_american(0.4)
        150
    """
    if prob <= 0 or prob >= 1:
        return None
    if prob >= 0.5:
        return round(-100 * prob / (1 - prob))
    else:
        return round(100 * (1 - prob) / prob)


def aggregate_probabilities(
    probabilities: List[float],
    method: str = "mean"
) -> Optional[float]:
    """
    Aggregate win probabilities from multiple bookmakers.

    Args:
        probabilities: List of probabilities from different bookmakers (0-1)
        method: Aggregation method - "mean", "median", or "trimmed_mean"

    Returns:
        Aggregated probability or None if no valid probabilities

    Examples:
        >>> aggregate_probabilities([0.55, 0.57, 0.54])
        0.5533  # Mean of the three
        >>> aggregate_probabilities([0.55, 0.57, 0.54], method="median")
        0.55  # Median value
    """
    # Filter out None and invalid values
    valid_probs = [p for p in probabilities if p is not None and 0 <= p <= 1]

    if not valid_probs:
        return None

    if len(valid_probs) == 1:
        return valid_probs[0]

    if method == "median":
        return median(valid_probs)
    elif method == "trimmed_mean" and len(valid_probs) >= 3:
        # Remove highest and lowest, then average
        sorted_probs = sorted(valid_probs)
        trimmed = sorted_probs[1:-1]
        return mean(trimmed) if trimmed else mean(valid_probs)
    else:  # Default to mean
        return mean(valid_probs)


def detect_reversed_bookmakers(snapshots) -> set:
    """
    Detect bookmakers whose home/away odds appear to be swapped.

    Some bookmakers in The Odds API occasionally return h2h outcomes
    with the moneyline prices assigned to the wrong team. This detects
    those cases by comparing each bookmaker's home probability against
    the median consensus.

    A bookmaker is flagged as reversed if:
    - Its home probability is close to (1 - median) rather than the median
    - The median is far enough from 50% to make detection reliable
    - At least 3 bookmakers have probability data

    Args:
        snapshots: List of OddsSnapshot objects or dicts with
            home_win_probability and bookmaker fields.

    Returns:
        Set of bookmaker keys whose odds appear reversed.
    """
    def get_val(item, key):
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    # Collect (bookmaker, home_prob) pairs
    entries = []
    for s in snapshots:
        prob = get_val(s, "home_win_probability")
        bk = get_val(s, "bookmaker")
        if prob is not None and bk is not None:
            entries.append((bk, float(prob)))

    if len(entries) < 3:
        return set()

    probs = [p for _, p in entries]
    med = median(probs)

    # Don't attempt detection when odds are close to 50/50
    if 0.38 <= med <= 0.62:
        return set()

    reversed_keys = set()
    for bk, prob in entries:
        mirror = 1.0 - med
        dist_to_median = abs(prob - med)
        dist_to_mirror = abs(prob - mirror)
        # Reversed if much closer to the mirror than to the median,
        # and meaningfully far from the median
        if dist_to_mirror < 0.10 and dist_to_median > 0.20:
            reversed_keys.add(bk)

    # Safety: don't "correct" if too many would be flagged —
    # requires a clear consensus (>2/3 of bookmakers agree)
    if len(reversed_keys) > len(entries) // 3:
        return set()

    return reversed_keys


def aggregate_bookmaker_odds(
    bookmaker_snapshots: List[dict],
    method: str = "mean"
) -> dict:
    """
    Aggregate odds data from multiple bookmakers into a single consensus.

    Args:
        bookmaker_snapshots: List of dicts with keys:
            - home_win_probability: float
            - away_win_probability: float
            - over_under: float (optional)
            - home_spread: float (optional)
            - projected_home_score: float (optional)
            - projected_away_score: float (optional)
        method: Aggregation method ("mean", "median", "trimmed_mean")

    Returns:
        Dict with aggregated values and metadata:
            - home_probability: aggregated home win probability
            - away_probability: aggregated away win probability
            - over_under: aggregated total (if available)
            - home_spread: aggregated spread (if available)
            - projected_home_score: aggregated projected score
            - projected_away_score: aggregated projected score
            - bookmaker_count: number of bookmakers included
            - min_home_probability: lowest home probability
            - max_home_probability: highest home probability
    """
    if not bookmaker_snapshots:
        return {
            "home_probability": None,
            "away_probability": None,
            "over_under": None,
            "home_spread": None,
            "projected_home_score": None,
            "projected_away_score": None,
            "bookmaker_count": 0,
            "min_home_probability": None,
            "max_home_probability": None,
        }

    # Extract values, handling both dict keys and attribute access
    def get_val(item, key):
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    home_probs = [get_val(s, "home_win_probability") for s in bookmaker_snapshots]
    away_probs = [get_val(s, "away_win_probability") for s in bookmaker_snapshots]
    over_unders = [get_val(s, "over_under") for s in bookmaker_snapshots]
    home_spreads = [get_val(s, "home_spread") for s in bookmaker_snapshots]
    proj_home = [get_val(s, "projected_home_score") for s in bookmaker_snapshots]
    proj_away = [get_val(s, "projected_away_score") for s in bookmaker_snapshots]

    # Convert Decimal types to float
    home_probs = [float(p) if p is not None else None for p in home_probs]
    away_probs = [float(p) if p is not None else None for p in away_probs]
    over_unders = [float(p) if p is not None else None for p in over_unders]
    home_spreads = [float(p) if p is not None else None for p in home_spreads]
    proj_home = [float(p) if p is not None else None for p in proj_home]
    proj_away = [float(p) if p is not None else None for p in proj_away]

    # #8231: a book whose projected leader contradicts its own moneyline gives
    # no projection - neither side, so the pair stays a pair.
    for i, home_prob in enumerate(home_probs):
        if projection_contradicts_moneyline(home_prob, proj_home[i], proj_away[i]):
            proj_home[i] = None
            proj_away[i] = None

    # Filter valid home probabilities for min/max calculation
    valid_home_probs = [p for p in home_probs if p is not None and 0 <= p <= 1]

    # Aggregate each metric
    agg_home = aggregate_probabilities(home_probs, method)
    agg_away = aggregate_probabilities(away_probs, method)

    # For over_under and spreads, use mean of valid values
    valid_ou = [v for v in over_unders if v is not None]
    valid_spread = [v for v in home_spreads if v is not None]
    valid_proj_home = [v for v in proj_home if v is not None]
    valid_proj_away = [v for v in proj_away if v is not None]

    return {
        "home_probability": round(agg_home, 4) if agg_home is not None else None,
        "away_probability": round(agg_away, 4) if agg_away is not None else None,
        "over_under": round(mean(valid_ou), 1) if valid_ou else None,
        "home_spread": round(mean(valid_spread), 1) if valid_spread else None,
        "projected_home_score": round(mean(valid_proj_home), 1) if valid_proj_home else None,
        "projected_away_score": round(mean(valid_proj_away), 1) if valid_proj_away else None,
        "bookmaker_count": len(valid_home_probs),
        "min_home_probability": round(min(valid_home_probs), 4) if valid_home_probs else None,
        "max_home_probability": round(max(valid_home_probs), 4) if valid_home_probs else None,
    }
