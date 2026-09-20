"""Economics markets API endpoint.

Serves prediction-market economic data from Kalshi and Polymarket,
organized into sub-themes: Fed rates, inflation, jobs, GDP/recession,
markets/indices, energy, housing, trade/tariffs, government/fiscal.

Single endpoint returns the full EconData shape consumed by the frontend.
"""

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket, FuturesOutcome
from app.services import get_db
from app.utils.cross_source_matching import (
    GARBAGE_OUTCOME_RE,
    clean_outcomes as _clean_outcomes,
    find_cross_source_markets,
    group_markets_by_group_id,
    is_resolved as _is_resolved,
    source as _source,
)
from app.utils.economics_headline import (
    LadderCandidate,
    RecessionCandidate,
    select_mortgage_ladder,
    select_recession_headline,
)
from app.utils.market_staleness import should_exclude_from_featured

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Sub-theme classification — ticker prefix + name pattern matching
# ---------------------------------------------------------------------------

_THEME_BY_TICKER: list[tuple[str, str]] = [
    # Fed / interest rates
    ("kxfedfunds", "fed"),
    ("kxfedcuts", "fed"),
    ("kxfedhikes", "fed"),
    # Inflation / CPI
    ("kxcpi", "inflation"),
    ("kxpce", "inflation"),
    ("kxinflation", "inflation"),
    # Jobs / employment
    ("kxunemployment", "jobs"),
    ("kxjobless", "jobs"),
    ("kxnonfarm", "jobs"),
    ("kxjobs", "jobs"),
    # GDP / recession
    ("kxgdp", "recession"),
    ("kxrecession", "recession"),
    # Markets / indices
    ("kxnasdaq", "markets"),
    ("kxsp500", "markets"),
    ("kxvix", "markets"),
    ("kxdow", "markets"),
    ("kxstocks", "markets"),
    # Energy / commodities
    ("kxgasprice", "energy"),
    ("kxwti", "energy"),
    ("kxbrent", "energy"),
    ("kxoil", "energy"),
    # Housing
    ("kxmortgage", "housing"),
    ("kxhousing", "housing"),
    ("kxhomeprice", "housing"),
    # Trade / tariffs
    ("kxtariff", "trade"),
    ("kxtrade", "trade"),
    # Government / fiscal
    ("kxshutdown", "government"),
    ("kxdebt", "government"),
    ("kxdoge", "government"),
]

_THEME_BY_NAME: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:fed\s*funds|fomc|rate\s*(?:cut|hike|decision)|federal\s*reserve)\b", re.I), "fed"),
    (re.compile(r"\b(?:cpi|inflation|consumer\s*price|pce|breakeven)\b", re.I), "inflation"),
    (re.compile(r"\b(?:unemployment|jobless|nonfarm|payroll|jobs?\s*report)\b", re.I), "jobs"),
    (re.compile(r"\b(?:gdp|recession|economic\s*growth)\b", re.I), "recession"),
    (re.compile(r"\b(?:nasdaq|s&p|dow\s*jones|vix|stock\s*market|nyse)\b", re.I), "markets"),
    (re.compile(r"\b(?:gas\s*price|oil\s*price|crude|wti|brent|petrol|gasoline)\b", re.I), "energy"),
    (re.compile(r"\b(?:mortgage|home\s*price|housing|case.shiller)\b", re.I), "housing"),
    (re.compile(r"\b(?:tariff|trade\s*war|trade\s*deal|import\s*duty)\b", re.I), "trade"),
    (re.compile(r"\b(?:shutdown|debt\s*ceiling|government\s*spending|doge|deficit)\b", re.I), "government"),
    (re.compile(r"\b(?:ecb|bank\s*of\s*(?:japan|england)|boj|boe)\b", re.I), "fed"),
    (re.compile(r"\b(?:consumer\s*sentiment|confidence)\b", re.I), "inflation"),
    (re.compile(r"\b(?:productivity)\b", re.I), "jobs"),
]


def _classify_theme(market: FuturesMarket) -> str:
    ext = (market.external_id or "").lower()
    for prefix, theme in _THEME_BY_TICKER:
        if ext.startswith(prefix):
            return theme
    name = market.name or ""
    for pat, theme in _THEME_BY_NAME:
        if pat.search(name):
            return theme
    return "other"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _outcomes_sorted(market: FuturesMarket) -> list:
    return sorted(market.outcomes, key=lambda o: o.rank or 0)


# A leader name that would tell the reader nothing they don't already have.
# "Yes"/"No" only restate the binary framing the question itself carries, so
# naming them adds a word and no information.
_UNINFORMATIVE_LEADER_RE = re.compile(r"^(?:yes|no)$", re.I)

# A question that pits named alternatives against each other. Whole tokens, so
# the "vs" inside "Vsevolod" or a ticker cannot trip it.
_VERSUS_RE = re.compile(r"(?<!\w)(?:vs\.?|versus)(?!\w)", re.I)


def _prices_the_negation(outcome) -> bool:
    """Is ``outcome``'s price the price of the question NOT happening?

    True for a bare ``No`` leg, and for a garbage placeholder, whose name is not
    a name and whose price is therefore about nothing the reader can see.

    The weather twin (`weather._prices_the_negation`, #2563) carries the long
    reasoning for why negation is kept apart from redundancy. In short:
    redundancy suppresses the NAME, negation moves the NUMBER, and merging them
    hands a card to a 10% also-ran whose only fault was repeating the question.
    """
    name = (outcome.name or "").strip()
    if not name:
        return True
    if GARBAGE_OUTCOME_RE.match(name):
        return True
    return bool(re.match(r"^no$", name, re.I))


def _appears_in(name: str | None, question: str | None) -> bool:
    """Is ``name`` spelled out in ``question``, as whole tokens?

    Lookarounds rather than ``\\b``: a name may begin or end with punctuation
    ("<4m sq km", "41°C or higher"), where ``\\b`` asserts the opposite thing.
    The match is on WHOLE TOKENS and not a bare substring, because outcome names
    on these markets get very short — a market priced across "0", "1" and "2"
    would otherwise find its leader "0" inside "2026" and suppress the only word
    that makes the number mean anything.
    """
    normalized = re.sub(r"\s+", " ", name or "").strip().lower()
    if not normalized:
        return False
    haystack = re.sub(r"\s+", " ", question or "").lower()
    return re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", haystack) is not None


def _leader_name(market: FuturesMarket, outcome, outcomes: list) -> str | None:
    """Name of the outcome whose probability the row prints, or None.

    A bare percentage is a complete answer only when the question already says
    what the number is about. Measured on the served `/api/economics` payload of
    2026-09-17 04:45Z, 18 of 53 rendered rows print a number whose referent the
    question does not carry: "What will the tariff rate on Canadian imports be
    on Jan 1, 2027?" printed **85%**, which is the price of "10% or above" and
    not a confidence in anything; "Which sectors will Trump tariff in 2026?"
    printed **97%**, the price of Pharmaceuticals alone.

    An outcome name earns its place by ADDING to the question, whatever the
    market's shape: a "Yes"/"No" restates it, a placeholder is not a name, and a
    name already spelled out in the question renders the same words twice in two
    type sizes.

    THE EXCEPTION IS A QUESTION THAT ENUMERATES ITS OWN ALTERNATIVES, and it is
    what a straight lift of the weather rule gets wrong here. "Bitcoin vs. Gold
    vs. S&P 500 in 2026" names all three contenders, so "S&P 500" appearing in
    the question does not make it redundant — selecting it is the entire answer.
    The discriminator is the market's OWN population rather than a word list: a
    name is redundant when it is the only outcome the question spells out, and
    informative when the question spells out two or more and the leader picks
    between them. #6696 named one such row.

    A versus question is the second arm because it enumerates BY CONSTRUCTION
    even when the counting arm cannot see it. "Annual Return: S&P 500 vs. S&P
    500 Equal Weight Index" is priced across "S&P 500 Equal Weight Index" and
    "S&P 500 Index", and only the first is spelled out exactly — the rival is
    written "S&P 500" in the question and "S&P 500 Index" in the outcome, so the
    count reaches 1 and the leader is suppressed on a question whose whole point
    is which of two things won. Measured over the served payload this arm names
    exactly one further row, that one; it cannot reach a question with no versus
    token, which is every row the counting arm already decided.
    """
    if outcome is None:
        return None
    name = (outcome.name or "").strip()
    if not name or GARBAGE_OUTCOME_RE.match(name):
        return None
    if _UNINFORMATIVE_LEADER_RE.match(name):
        return None
    if _appears_in(name, market.name):
        enumerated = sum(1 for o in outcomes if _appears_in(o.name, market.name))
        if enumerated < 2 and not _VERSUS_RE.search(market.name or ""):
            return None
    return name


def _market_row(market: FuturesMarket) -> dict | None:
    """Convert a binary market to a Market row.

    Returns None for a multi-outcome market, and for a market this page holds
    no probability for at all.

    #2950 — the old body opened `prob = 0.0` and gave that one name two jobs:
    the running maximum, and the value returned when the loop never ran. Its
    only refusal was `len(outcomes) > 5` — too MANY outcomes; it never refused
    zero. So a market with no outcomes fell through and the page printed a
    confident `0%` under a real question, including `"WTI Crude Oil (WTI) Up or
    Down on September 4?"` on September 3rd. 175 of 2,269 open economics
    markets carry no outcomes at all.

    Both sibling dashboards already refuse on their third line
    (`politics.py`, `entertainment.py`), and so does this file's own
    `_cross_source_row_fn` below. This was the one row-builder of the four that
    did neither — measured the same minute: `/api/politics` 68 rows / 0 zeros,
    `/api/entertainment` 105 / 0, `/api/economics` 58 / **5**.

    The sentinel is removed rather than guarded: `prob` is a `max()` over a
    list already proven non-empty, so no initialiser survives that could be
    mistaken for a measurement.

    #6696 — THE ``No`` LEG NEVER WINS THIS SCAN, and the row NAMES the leg it
    prints. The old body took the dearest leg whatever it was called and printed
    the bare number, which fails in two different directions at once. Measured
    on the served payload, 2026-09-17 04:45Z:

        prints  honest  question
         85.5%   14.5%  Tariff increase on Canada in effect by December 31, 2026?
           81%     19%  Will S&P 500 (SPY) hit (HIGH) $780 in September?
           50%   49.5%  Will WTI Crude Oil (WTI) hit (LOW) $90 Week of Sept 14?

    Each of those is the price of the question's own negation, printed in green
    behind a near-full bar; the first sits in TRADE & TARIFFS telling a reader a
    Canadian tariff increase is near-certain when the market says it is not.
    A further 18 rows printed a real leg's price with no way to tell which leg.

    The outcome is chosen ONCE and the number, the name and the `market_id` all
    read that single object, so they cannot come to disagree about what the row
    is about — the same seam discipline as `weather._card_outcome`.

    The fallback keeps today's number when every priced leg is a negation: that
    case has no specimen in the served population, and preserving a number beats
    shipping an unexercised withholding path across nine theme lists.
    """
    outcomes = _clean_outcomes(list(market.outcomes))
    if len(outcomes) > 5:
        return None
    # `is not None`, not `or 0`. `current_probability` is Numeric(7, 6), so it
    # arrives as a Decimal — and `Decimal("0.000000")` is FALSY, so the old
    # `or 0` read a genuine priced zero as no reading at all. A priced zero is
    # data (the market says no); a NULL is the absence of data. Only the second
    # is grounds for refusing the row.
    priced = [o for o in outcomes if o.current_probability is not None]
    if not priced:
        return None
    answerable = [o for o in priced if not _prices_the_negation(o)]
    leg = max(answerable or priced, key=lambda o: float(o.current_probability))
    return {
        "q": market.name,
        "prob": round(float(leg.current_probability) * 100, 1),
        # Which outcome `prob` belongs to. Always present, explicitly null when
        # there is nothing worth naming — an absent key would be
        # indistinguishable from a payload served out of a Redis cache built
        # before the field existed, which the page must also survive.
        "leader": _leader_name(market, leg, outcomes),
        "src": _source(market),
        "delta": None,
        "market_id": market.id,
    }


def _up_leg(market: FuturesMarket):
    """The leg a daily up/down card prints, or None if the market has none.

    The FIRST matching leg wins and the scan stops there, exactly as the two
    inline loops this replaces did. It deliberately does not fall through to a
    second `Yes` when the first has no price: these markets carry one such leg,
    and substituting another would quietly change which question the row is
    answering — a worse fault than the missing number.
    """
    for outcome in _outcomes_sorted(market):
        if (outcome.name or "").lower() in ("up", "yes", ""):
            return outcome
    return None


# A rung label that names ONE price rather than a span: "$755", "7,350",
# "$6.50". The span forms — "$7,000-$7,500", "7,400 to 7,599.99", "<$6,000" —
# are deliberately excluded, and that exclusion is the discriminator this whole
# arm rests on. Measured over the 66 markets that reach the index branch on
# 2026-09-19, the five with an unpriced up leg and priced non-binary rungs are
# one threshold ladder (`61381310`) and four PARTITIONS of a closing price
# (`109484`, `109487`, `114285`, `114287`), and every rung of all four is a
# span. Printing a partition's rung as "above X" would be a new false claim, so
# the shape test has to keep them out on its own, before any probability is read.
_STRIKE_RE = re.compile(r"^\$?\d[\d,]*(?:\.\d+)?$")

# The threshold words this page already recognises (`_CUMULATIVE_PREFIXES`),
# here in the position they take when the venue puts the threshold in the market
# NAME and leaves the rungs bare: "S&P 500 (SPY) closes above ___".
_NAME_THRESHOLD_WORDS = ("above", "over", "at least")


def _named_threshold_rungs(market: FuturesMarket) -> tuple[str, list] | None:
    """The rungs of a ladder whose threshold word lives in the market's NAME.

    ``_is_cumulative_ladder`` cannot see this shape: it asks whether every
    OUTCOME name starts with a cumulative prefix, and these rungs are bare
    strikes (``$735`` … ``$785``) with the word "above" sitting up in the
    question. Both helpers stay, because they answer for different venues'
    conventions and neither subsumes the other.

    Three conditions, each load-bearing, and the market must fail none:

    1. the question carries a threshold word;
    2. at least three priced rungs whose labels name a single price
       (``_STRIKE_RE``) — a span label means a partition, not a ladder;
    3. the prices are monotone non-increasing as the strike rises, which is
       what MAKES a set of rungs cumulative. A partition sorted by strike is
       hump-shaped and fails this on its first rise.

    Strict, with no tolerance for venue tick noise, because the cost of the two
    errors is not symmetric: refusing a real ladder withholds a row that is
    already withheld today, while admitting a partition prints a number under a
    label that misstates what it measures.

    Returns ``(threshold word, rungs ordered by strike)`` or None.
    """
    name = (market.name or "").lower()
    word = next((w for w in _NAME_THRESHOLD_WORDS if f" {w} " in name), None)
    if word is None:
        return None

    rungs = [
        o
        for o in market.outcomes
        if o.current_probability is not None
        and _STRIKE_RE.match((o.name or "").strip())
    ]
    if len(rungs) < 3:
        return None

    def _strike(outcome) -> float:
        return float((outcome.name or "").strip().lstrip("$").replace(",", ""))

    ordered = sorted(rungs, key=_strike)
    probs = [float(o.current_probability) for o in ordered]
    if any(later > earlier for earlier, later in zip(probs, probs[1:])):
        return None
    return word, ordered


def _index_symbol(market: FuturesMarket, cut: str) -> str:
    """The index a threshold-ladder row is about, without the question around it.

    ``"S&P 500 (SPY) closes above ___ on September 21?"`` is the whole question;
    the row's left column wants ``"S&P 500 (SPY)"``. Cut at the threshold word
    the ladder was detected on, then drop the verb that introduced it, so the
    symbol does not read ``"S&P 500 (SPY) closes"`` beside a label that already
    says what it closes above.
    """
    head = re.split(rf"\b{re.escape(cut)}\b", market.name or "", maxsplit=1, flags=re.I)[0]
    head = re.sub(r"\b(?:closes?|finishes|ends?|settles?)\s*$", "", head.strip(), flags=re.I)
    return head.strip(" ,-—")[:20]


def _index_row(market: FuturesMarket) -> dict | None:
    """A TODAY'S CLOSE row, or None when the venue has not priced its leg.

    #7085 — the old inline body read the price as
    `float(o.current_probability or 0)` and printed the result unconditionally,
    so a leg the venue has not priced became a confident `0%`. Measured on the
    served payload of 2026-09-18 (market `61381310`, *"S&P 500 (SPY) closes
    above ___ on September 21?"*, `current_probability` NULL behind a live
    0.55/0.78 book), the card printed:

        S&P 500 (SPY) closes     0%  up
        S&P 500 (SPX)           53%  up

    — two rows for one index, the first asserting there is no chance the S&P
    closes up. `0%` is worse than a blank because it is a claim.

    Withheld by DROPPING THE ROW rather than serving a null `prob`. This is a
    list surface and the web card renders `{prob}% {dir}` with no null arm, so
    a null would print `% up`; the same reasoning took a card out of the boxing
    hub under #7016. A list keeps its shape by losing an item, not by keeping a
    row that says nothing. If every index leg is unpriced the card is absent
    entirely, which is the honest-empty end state (ruling 027), not a regression.

    `is None`, not `or 0`, for the reason `_market_row` gives above: the column
    is `Numeric(7, 6)`, so a genuine priced zero arrives as a FALSY
    `Decimal("0.000000")` and an `or 0` refusal would throw away real data —
    the market saying "no" — alongside the absence.

    #7115 — WITHHOLDING WAS RIGHT AND STILL LEFT A PRICED LADDER OFF THE PAGE.
    The leg `_up_leg` reads on `61381310` is the Polymarket EVENT stub (its
    `external_id` is the bare numeric `1042750`, an event id, which is also why
    the question carries a literal blank: *"S&P 500 (SPY) closes above ___"*).
    That stub is unpriced — but eleven rungs of the same market are not, and
    `group_markets_by_group_id` had already merged them onto this very row
    before it reached this function:

        Yes  NULL  <- the only leg the up-leg scan will look at
        $735 90.6%   $745 89.5%   $755 83.0%   $765 19.0%   $775 10.5%
        $740 89.5%   $750 89.5%   $760 47.5%   $770 10.5%   $780 10.5%
                                                            $785  9.5%

    So the card served ONE row (the SPX sibling at 53%) while a complete,
    monotone, fully-priced S&P ladder sat one field away. The threshold arm
    prints its own question instead of the up/down one it does not answer:

        S&P 500 (SPY)            83% above $755

    THE RUNG IS CHOSEN ON THE PRICE, NEVER ON THE LABEL, by this file's own
    `_pick_rung` — the tightest bound the market still calls more likely than
    not. The dearest rung is never the answer: "above $735, 91%" is the loosest
    bound on the ladder and tells a reader nothing.

    IT NAMES THE THRESHOLD IN `dir`, which the card renders verbatim after the
    percentage, so no layout changes and no field is invented: `sym` and `dir`
    are the two text slots the row already had. A number this specific may not
    travel under the word "up" — "83% up" would be a second false claim where
    #7085 removed the first.

    This DOES put a second S&P row back on a card #7085 reduced to one, and the
    difference is the whole point: #7085's two rows contradicted each other (0%
    against 53% for the same index), while these two answer different questions
    and now say which. The `stocks` card gets no such arm — it renders a bare
    `{prob}%` with no second slot, so a rung there would print 83% beside real
    up-probabilities with nothing to mark it apart, which is worse than absence.
    """
    outcome = _up_leg(market)
    if outcome is None or outcome.current_probability is None:
        ladder = _named_threshold_rungs(market)
        if ladder is None:
            return None
        word, rungs = ladder
        rung = _pick_rung(rungs)
        if rung is None:  # pragma: no cover - _named_threshold_rungs pre-filters
            return None
        return {
            "sym": _index_symbol(market, word),
            "prob": round(float(rung.current_probability) * 100, 1),
            "dir": f"{word} {(rung.name or '').strip()}",
            "range": "",
            "src": _source(market),
        }
    return {
        "sym": (market.name or "").split(" Up ")[0].split(" up ")[0].split("?")[0].strip()[:20],
        "prob": round(float(outcome.current_probability) * 100, 1),
        "dir": "up",
        "range": "",
        "src": _source(market),
    }


def _stock_row(market: FuturesMarket) -> dict | None:
    """A single-stock row, or None when the venue has not priced its leg.

    The same #7085 coercion, one branch down, on a card that renders a bare
    `{prob}%` with no direction word at all — so an unpriced leg there reads as
    a flat `0%` beside real prices with nothing to mark it apart. No specimen on
    the served payload the day this shipped (`stocks` was empty), but it is the
    same builder, the same leg scan and the same `or 0`; leaving one of the two
    would be arbitrary.
    """
    outcome = _up_leg(market)
    if outcome is None or outcome.current_probability is None:
        return None
    name = market.name or ""
    sym = name.split("(")[1].split(")")[0] if "(" in name else name.split(" ")[0]
    return {
        "sym": sym[:6],
        "prob": round(float(outcome.current_probability) * 100, 1),
        "delta": None,
        "src": _source(market),
    }


# Outcome-name prefixes that mark a CUMULATIVE threshold ladder rather than a
# partition into mutually exclusive brackets. Each row of such a ladder is an
# independent "at or above X" probability (gotcha #17), so the rows are NOT a
# distribution: they legitimately sum well over 100% and must never be
# normalized or rescaled against each other.
#
# The temporal forms belong here for the same reason: "Before Jan 1, 2028" is
# a deadline the market either clears or doesn't, and the rungs nest. Every
# prefix below is attested in the open economics pool — a first-word census on
# 2026-08-29 counted 798 markets on "above", 44 on "before" and 16 on "below".
_CUMULATIVE_PREFIXES = (
    "above ",
    "at least ",
    "more than ",
    "over ",
    "greater than ",
    "below ",
    "before ",
)


def _is_cumulative_ladder(market: FuturesMarket) -> bool:
    """True when a multi-outcome market's rows are cumulative thresholds."""
    outcomes = list(market.outcomes)
    if len(outcomes) < 2:
        return False
    marked = sum(
        1
        for o in outcomes
        if (o.name or "").strip().lower().startswith(_CUMULATIVE_PREFIXES)
    )
    return marked >= 2 and marked == len(outcomes)


def _ladder_rung(market: FuturesMarket):
    """The rung a one-line summary of a cumulative ladder should print.

    THE DEAREST RUNG IS NEVER THE ANSWER. A ladder's probabilities are monotone
    in its threshold, so the highest one is always the loosest bound — "at least
    370 rigs, 97%" tells a reader nothing they could not have guessed. The
    informative rung is the TIGHTEST bound the market still calls more likely
    than not, which is the distribution's own median: "at least 450, 57%".

    Chosen on the probability, never on a number parsed out of the label. The
    ladder is monotone in both directions the prefixes allow — ``above``/``at
    least`` rise as the threshold falls, ``below``/``before`` rise as it rises —
    and "the tightest bound still favoured" is the same sentence either way,
    while a threshold parsed from "Before Jan 1, 2028" would sort on 1.

    First of a tie wins, the same discipline as ``weather._leader_outcome``: two
    rungs at one price must not be able to give two callers two answers.

    Falls back to the dearest rung when the market favours none of them, which
    is the best available statement about a ladder that is long odds all the way
    up. Returns None only when nothing is priced.
    """
    return _pick_rung(
        [o for o in _outcomes_sorted(market) if o.current_probability is not None]
    )


def _pick_rung(priced: list):
    """The tightest bound a ladder still calls more likely than not.

    Lifted out of ``_ladder_rung`` unchanged so the two callers — the oil card
    and the TODAY'S CLOSE threshold arm — cannot drift into two answers for one
    question. The rule and the reasoning are ``_ladder_rung``'s docstring above;
    this holds only the arithmetic, over an already-priced list.
    """
    if not priced:
        return None
    favoured = [o for o in priced if float(o.current_probability) >= 0.5]
    if favoured:
        return min(favoured, key=lambda o: float(o.current_probability))
    return max(priced, key=lambda o: float(o.current_probability))


def _oil_row(market: FuturesMarket) -> dict | None:
    """A Crude-oil row that names its question and prints a price the venue quotes.

    #3004 — THE OIL CARD'S COMPOSITE LABEL IS ONLY HALF THE DEFECT; THE OTHER
    HALF IS THAT THE NUMBER UNDER IT IS NOT A PRICE ANYBODY QUOTED. Both rows on
    production tonight (390px, 2026-09-16 22:28 PDT) were built by treating a
    market that is not a distribution as one, and then normalizing it:

        rendered            prints  the venue says
        WTI No                 32%  50.0  — P(No) on a Yes/No market whose
                                           outcome set also carries two rungs
                                           of a sibling ladder, so the four
                                           "brackets" sum to 154.5% and the
                                           rescale invents 32.4
        Oil At least 370       13%  97.0  — twelve cumulative "At least X"
                                           rungs summing to 777.5%, rescaled
                                           into 12.5

    The second is this file's own rule, one call site short: the
    ``_CUMULATIVE_PREFIXES`` block above says in as many words that a cumulative
    ladder's rows "legitimately sum well over 100% and must never be normalized
    or rescaled against each other", and ``_is_cumulative_ladder`` has been here
    since #2563 to detect exactly that. The energy branch asks a weaker question
    (`any("above" in name)`), which "At least 370" fails, so the ladder falls
    through to the partition path and is rescaled.

    Repairing only the label would have been worse than leaving it: a reader who
    cannot parse ``Oil At least 370`` distrusts the row, where "Number of US oil
    rigs at end of 2026 · At least 370 — 13%" is a confident sentence that is
    wrong by 84 points.

    Returns None for a genuine partition of a price — ``WTI 85 or above`` is a
    fair reading of one, has no specimen on today's card, and keeps the
    composite path it has always had rather than taking an unmeasured change.

    IT ALSO REFUSES GAS, and that refusal lives here rather than at the call
    site so it is reachable by a test. The gas card is a HISTOGRAM of the whole
    distribution: it is handed `brackets` and draws every one of them, so a
    market summarised down to a single rung would render a one-bar chart. Gas
    markets are cumulative ladders as often as oil ones are — the refusal is
    load-bearing, not defensive.
    """
    if "gas" in (market.name or "").lower():
        return None
    outcomes = _clean_outcomes(list(market.outcomes))
    if _is_cumulative_ladder(market):
        rung = _ladder_rung(market)
        if rung is None:
            return None
        return {
            "q": market.name,
            "prob": round(float(rung.current_probability) * 100, 1),
            "leader": _leader_name(market, rung, outcomes),
            "src": _source(market),
            "delta": None,
            "market_id": market.id,
        }
    # A bare Yes or No rung is proof the market is a BINARY whose extra outcomes
    # are contamination rather than a distribution: no partition of a price
    # prices "No" beside its brackets. `_market_row` is the page's binary
    # renderer and already refuses the negation's price (#6696), so it returns
    # the question with a price the venue actually quotes. It returns None above
    # five outcomes, and that is a fall-through, not a refusal — a market that
    # wide is handed back to the bracket path unchanged.
    if any(_UNINFORMATIVE_LEADER_RE.match((o.name or "").strip()) for o in outcomes):
        return _market_row(market)
    return None


def _distribution_row(
    market: FuturesMarket, *, min_outcomes: int = 6
) -> dict | None:
    """Render a multi-outcome market that ``_market_row`` refuses.

    ``_market_row`` returns None above five outcomes, which silently drops
    priced markets out of the sections that only render Market rows. This
    keeps them by serving their shape instead: a cumulative threshold ladder
    stays raw (see ``_CUMULATIVE_PREFIXES``), a partition is normalized into
    brackets. Returns None when nothing is priced.

    ``min_outcomes`` defaults to 6 because that is where ``_market_row`` gives
    up, which is the whole reason this function exists. The housing card (#6702)
    passes 3: its branch has its own, lower floor and a market of four rungs
    there is a card, not a row that fell through a gap.
    """
    outcomes = list(market.outcomes)
    if len(outcomes) < min_outcomes:
        return None
    if not any(float(o.current_probability or 0) > 0 for o in outcomes):
        return None

    if _is_cumulative_ladder(market):
        kind = "ladder"
        rows = [
            [round(float(o.current_probability or 0) * 100, 1), o.name or ""]
            for o in _outcomes_sorted(market)
        ]
    else:
        kind = "brackets"
        rows = _brackets_from_outcomes(market)

    return {
        "q": market.name,
        "kind": kind,
        "rows": rows,
        "src": _source(market),
        "market_id": market.id,
    }


def _brackets_from_outcomes(market: FuturesMarket, normalize: bool = True) -> list[list]:
    """Convert multi-outcome market to [[prob, label], ...] brackets.

    When normalize=True, scale so probabilities sum to 100% (removes
    overround from independent binary markets displayed as distributions).
    """
    result = []
    for o in _outcomes_sorted(market):
        p = float(o.current_probability or 0)
        result.append([round(p * 100, 1), o.name or ""])
    if normalize and result:
        total = sum(b[0] for b in result)
        if total > 105:
            for b in result:
                b[0] = round(b[0] * 100 / total, 1)
    return result


def _modal_bracket(brackets: list[list]) -> tuple[int, float, str]:
    """Return (index, prob, label) of highest-probability bracket."""
    best_idx, best_prob, best_label = 0, 0.0, ""
    for i, (prob, label) in enumerate(brackets):
        if prob > best_prob:
            best_idx, best_prob, best_label = i, prob, label
    return best_idx, best_prob, best_label


# A month, and only a month. The expression this replaces was
# `\b(Jan|...|Dec)\w*\b`, which also matches "Maybe", "Marginal" and "August"
# inside "Augusta" — `\w*` after a three-letter stem accepts any word that
# merely starts like one. Strictly narrower, so no name newly matches; a name
# that stops matching was never naming a month.
_CPI_MONTH_RE = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
    r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?"
    r"|Dec(?:ember)?)\b",
    re.IGNORECASE,
)
_CPI_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _cpi_release_label(name: str) -> str:
    """The short period label a CPI block prints, and it keeps the YEAR.

    #2564 — THE DROPPED YEAR IS THE DIFFERENCE BETWEEN THREE BLOCKS AND ONE.
    This label was ``re.search(<month>, name).group(0).title()[:3]``, so every
    market naming a December collapsed onto the same four characters. On
    production 2026-09-17 09:25:34Z that put three blocks titled ``Dec`` on the
    card, and they were US headline CPI for December **2030**, **2034** and
    **2036** — a decade apart, carrying different distributions, printed under
    one heading. The issue reads this as "December repeated three times"; it is
    three different questions wearing one name.

    It is not only a web defect. ``CPIRelease`` in the iOS models declares
    ``var id: String { mo }``, so the label IS the ``Identifiable`` id: three
    ``Dec`` blocks are three duplicate ids in a ``ForEach``, which is why
    native's iPad walk photographed "December repeated three times with
    byte-identical values and an identical bar chart". Unique labels settle the
    symptom; ``id = marketId`` is the durable fix and belongs to native.

    The no-month fallback truncated at a fixed 20 characters, mid-word, so
    "South Korea Annual Inflation 2026" reached the card as ``South Korea
    Annual I``. It now stops at a word boundary. That is the best a SHORT label
    can do for a market whose period is not a month, and it is why the block
    also carries ``q``: the label is a hint, the question is the truth.

    Returns "" when the name yields no period at all, which the caller reads as
    "this block has no short label" rather than substituting one.
    """
    name = (name or "").strip()
    if not name:
        return ""
    month = _CPI_MONTH_RE.search(name)
    year = _CPI_YEAR_RE.search(name)
    if month:
        mon = month.group(0).title()[:3]
        return f"{mon} {year.group(1)}" if year else mon
    if len(name) <= 20:
        return name
    return name[:20].rsplit(" ", 1)[0].rstrip(" -–,:")


def _cpi_release_sort_key(market: FuturesMarket) -> tuple[int, float]:
    """Order CPI blocks by when the release they price actually lands.

    #2564 — THE SIX BLOCKS WERE AN ARBITRARY SLICE OF 56. The query feeding this
    page carries no ``ORDER BY`` and the list is cut ``[:6]``, so which six
    releases a reader sees was decided by row order — the same undefined pairing
    this file already documents for the recession headline. Measured on
    production 2026-09-17: three of the six resolved in 2031, 2035 and 2037,
    while the next actual print (September CPI, 2026-10-14) and all of October
    and November lost to them. That is the issue's "a reader cannot reach Oct or
    Nov at all", and it is an ordering defect, not a missing-data one.

    Undated markets sort last rather than first: a null is not "imminent".

    ``resolution_date`` is compared as a timestamp because the column yields
    naive and aware datetimes from different writers, and sorting those against
    each other raises rather than mis-orders.
    """
    resolves = getattr(market, "resolution_date", None)
    if resolves is None:
        return (1, 0.0)
    if resolves.tzinfo is None:
        resolves = resolves.replace(tzinfo=timezone.utc)
    return (0, resolves.timestamp())


def _cumulative_to_discrete(outcomes: list, max_buckets: int = 8) -> list[list]:
    """Convert cumulative 'Above X' outcomes to discrete bracket probabilities.

    Kalshi economics markets use cumulative outcomes (P(above 3%), P(above 3.5%)).
    We need P(exactly in bracket) = P(above lower) - P(above upper).
    Returns [[prob, label], ...] sorted by threshold, at most max_buckets entries.

    The threshold is parsed WITH its sign (#7081). An unsigned `[\\d.]+` reads
    "Above -0.4%" as 0.4, which interleaves a mixed-sign ladder — 0.0, -0.1,
    0.1, -0.2, ... — and reverses an all-negative one. Neither failure is
    visible in the output shape: the monotonicity clamp below then overwrites
    the real cumulatives with a neighbour's, and the differences that follow
    subtract non-adjacent thresholds, so the bars keep plausible values and
    wear the wrong labels. On the September CPI card that put 42 points of
    probability on deflation labels belonging to +0.2% and +0.3%; an
    all-negative ladder collapses to a single bar, because the clamp flattens
    every leg to the first one's value and every difference rounds to zero.

    The `(?<!\\w)` guard keeps a hyphen inside a word from reading as a sign,
    so "COVID-19 above 5%" still parses 19 rather than -19.
    """
    import re as _re

    raw = []
    for o in outcomes:
        p = float(o.current_probability or 0) * 100
        label = (o.name or "").strip()
        nums = _re.findall(r'(?<!\w)-?\d[\d.]*', label)
        try:
            sort_val = float(nums[0]) if nums else 0
        except ValueError:
            # A malformed token ("1.2.3") must not 500 the whole page.
            sort_val = 0
        # Clean label: remove "Above " prefix
        clean = label.replace("Above ", "").strip()
        raw.append((p, clean, sort_val))

    if not raw:
        return []

    # Sort by threshold ascending (lowest first)
    raw.sort(key=lambda x: x[2])

    # Enforce monotonicity: P(above lower threshold) >= P(above higher threshold)
    for i in range(1, len(raw)):
        if raw[i][0] > raw[i - 1][0]:
            raw[i] = (raw[i - 1][0], raw[i][1], raw[i][2])

    # Convert cumulative to discrete:
    # P(in bracket i) = P(above threshold_i) - P(above threshold_{i+1})
    # P(above highest) stays as-is (the top bracket)
    # Rows carry their threshold as a third element so the re-sort below can
    # order by it; it is projected away before returning, because callers
    # (`_modal_bracket`) unpack exactly [prob, label].
    discrete = []
    for i in range(len(raw)):
        cum_p = raw[i][0]
        next_p = raw[i + 1][0] if i + 1 < len(raw) else 0
        bracket_p = round(cum_p - next_p, 1)
        if bracket_p >= 0.1:
            discrete.append([bracket_p, raw[i][1], raw[i][2]])

    # If too many, keep top by probability, then restore threshold order.
    # Sorting the survivors by their LABEL instead would reverse an
    # all-negative ladder ("-3%" < "-4%" as strings) and mis-place any label
    # whose digits are not zero-padded (#7081).
    if len(discrete) > max_buckets:
        discrete.sort(key=lambda x: x[0], reverse=True)
        discrete = discrete[:max_buckets]
        discrete.sort(key=lambda x: x[2])

    # Normalize: independent binary markets can sum well over 100%.
    # Same threshold as _brackets_from_outcomes / politics _normalize_outcome_probs.
    if discrete:
        total = sum(b[0] for b in discrete)
        if total > 105:
            for b in discrete:
                b[0] = round(b[0] * 100 / total, 1)

    return [[b[0], b[1]] for b in discrete]


# ---------------------------------------------------------------------------
# Cross-source matching — find markets on both Kalshi & Polymarket
# ---------------------------------------------------------------------------


def _cross_source_row_fn(market: FuturesMarket) -> dict | None:
    """Build a row for cross-source matching (economics-specific)."""
    outcomes = _clean_outcomes(list(market.outcomes))
    outcomes = sorted(
        outcomes, key=lambda o: float(o.current_probability or 0), reverse=True
    )
    if not outcomes:
        return None
    top = outcomes[:3]
    row = {
        "q": market.name,
        "prob": round(float(outcomes[0].current_probability or 0) * 100, 1),
        "src": _source(market),
        "market_id": market.id,
        "top_outcomes": [
            {
                "name": o.name,
                "prob": round(float(o.current_probability or 0) * 100, 1),
            }
            for o in top
        ],
        "outcome_count": len(outcomes),
        "theme": _classify_theme(market),
    }
    if row["outcome_count"] <= 2 and row["prob"] > 95:
        return None
    return row


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

@router.get("")
async def get_economics_cached(db: AsyncSession = Depends(get_db)):
    """Return all economics market data (Redis-cached, precomputed hourly).

    Falls back to a stale cache (24h TTL) when the primary cache is cold,
    and wraps the live DB query with a 25s timeout so Heroku never kills
    the connection.
    """
    import asyncio
    from app.tasks.redis_state import get_async_redis_client

    try:
        rc = get_async_redis_client()
        cached = await rc.get("bainluck:category:economics")
        if cached:
            await rc.aclose()
            return json.loads(cached)
        # Primary cache miss — try stale fallback
        stale = await rc.get("bainluck:category:economics:stale")
        await rc.aclose()
        if stale:
            logger.info("Economics: serving stale cache (primary miss)")
            return json.loads(stale)
    except Exception:
        pass  # Fall through to live query

    # Live DB fallback with timeout guard
    try:
        response = await asyncio.wait_for(get_economics(db), timeout=25)
    except asyncio.TimeoutError:
        logger.warning("Economics live query timed out after 25s")
        return {"error": "timeout", "themes": {}}

    # Populate stale cache for future cold-cache resilience
    try:
        rc = get_async_redis_client()
        await rc.set(
            "bainluck:category:economics:stale",
            json.dumps(response, default=str),
            ex=86400,
        )
        await rc.aclose()
    except Exception:
        logger.warning("Economics: failed to write stale cache", exc_info=True)

    return response


async def get_economics(db: AsyncSession):
    """Build economics response from database (called by precompute task + fallback)."""
    now = datetime.now(timezone.utc)

    # Query all open economics markets with outcomes
    econ_categories = ["economics", "finance", "crypto"]
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            or_(
                FuturesMarket.llm_sport_category.in_(econ_categories),
                # Also grab Kalshi markets with economics ticker prefixes
                # regardless of llm_sport_category (often misclassified)
                *[FuturesMarket.external_id.ilike(f"{prefix}%")
                  for prefix, _ in _THEME_BY_TICKER],
            ),
            FuturesMarket.status == "open",
        )
    )
    all_markets = list(result.scalars().unique().all())

    # Collapse Polymarket sub-markets sharing a group_id into a single
    # representative market with merged outcomes (BR62 / #487).
    all_markets = group_markets_by_group_id(all_markets)

    def _leader_prob(m):
        outcomes = sorted(
            (m.outcomes or []),
            key=lambda o: float(o.current_probability or 0),
            reverse=True,
        )
        return float(outcomes[0].current_probability) if outcomes and outcomes[0].current_probability else None

    # Classify into themes — exclude resolved, extreme, and title-stale markets.
    # ``spotlight_eligible`` is the set this page is willing to RENDER, kept so
    # the cross-source spotlight below is fed those markets rather than the raw
    # query result. UX-P194-1 / CERT-540.
    #
    # On THIS page the two coincide: `_classify_theme` always returns a theme
    # (worst case `"other"`), so there is no second rejection gate here the way
    # `/politics` and `/entertainment` have one. The name and the append
    # position still match its siblings on purpose — the sibling routes were
    # blocked for appending ABOVE their later gates, and the cheapest way to
    # keep this one from acquiring the same defect is for a new gate to have an
    # obvious place to go: ABOVE the append.
    themed: dict[str, list] = defaultdict(list)
    spotlight_eligible: list = []
    for m in all_markets:
        if should_exclude_from_featured(
            m.name, m.llm_sport_category, m.status, _leader_prob(m), now,
        ):
            continue
        spotlight_eligible.append(m)
        theme = _classify_theme(m)
        themed[theme].append(m)

    # Build response sections
    fed_markets = themed.get("fed", [])
    inflation_markets = themed.get("inflation", [])
    jobs_markets = themed.get("jobs", [])
    recession_markets = themed.get("recession", [])
    markets_markets = themed.get("markets", [])
    energy_markets = themed.get("energy", [])
    housing_markets = themed.get("housing", [])
    trade_markets = themed.get("trade", [])
    gov_markets = themed.get("government", [])

    # --- Fed rates section ---
    _MONTH_ORDER = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    fomc_meetings = []
    rate_cuts = []
    rate_side = []

    # ─── The rate-path heatmap picks its own columns (#2870) ────────────────
    #
    # This one card renders a market as a DISTRIBUTION, and that makes the
    # shared leader-probability arm of `should_exclude_from_featured` read the
    # wrong thing about it. These are cumulative `Above X%` ladders, so the
    # leader is the probability of the ladder's LOWEST rung — a near-certain
    # statement by construction, not a measure of how much the market has to
    # say. Kalshi trims the rungs already decided for a near-term meeting, so
    # the floor rung sits higher and the leader sits closer to 1.0:
    #
    #     Jan 2027   floor `Above 0.00%`   leader 0.975   18 rungs   shown
    #     Sep 2026   floor `Above 2.75%`   leader 0.995   11 rungs   HIDDEN
    #
    # Measured on production 2026-09-14, that was a perfect split over all six
    # open ladders — the three above the 0.98 bar were exactly the three 2026
    # meetings. The nearer the meeting, the shorter the ladder, the more
    # certain the exclusion, so the card was structurally guaranteed to omit
    # the imminent meeting and show only ones far enough out to still be
    # uncertain. On 2026-09-14 it was headed "2026 rate path" over three 2027
    # columns while the Sep 2026 meeting resolving in two days was absent, and
    # its distribution was perfectly drawable (~86.5% of the mass in the
    # 3.75–4.00% bracket).
    #
    # ⚠️ Why the ONE arm and not the predicate. The obvious fix — stop applying
    # a leader-probability test to markets rendered as a distribution — was
    # measured and is not narrow: 1,645 open markets site-wide are cumulative
    # ladders and 230 of them are currently held off featured surfaces by this
    # bar, across /economics, /politics, /entertainment AND the cross-source
    # spotlight (`2Pac Streams in 2026`, `Burger King Foot Traffic in
    # September`, `Brent crude oil price on September 30`). That is a
    # browse-surface content change, not a bug fix. So the exception is scoped
    # to the one card that has the distribution property, by asking the shared
    # predicate the question WITHOUT the confidence arm — `leader_probability`
    # is passed as None, which `is_probability_extreme` answers False for.
    # `PROBABILITY_EXTREME_HIGH` itself is untouched, so ux/1022's `Canada
    # recession before 2027? 99.6%` finding stays fixed and `spotlight_eligible`
    # above is unchanged.
    #
    # ⚠️ The other two arms stay LIVE, and they are what retires a meeting once
    # it has happened. `status` cannot be trusted to do it alone — settled
    # Kalshi markets sit at `status='open'` in our DB until the settled-events
    # backfill reaches them (gotcha #33), and four past meetings in this very
    # family are `resolved` only because that backfill has run. The load-bearing
    # one is the title arm: `stale_explicit_title_month` retires
    # "…after Sep 2026 meeting?" from month-end + 1 day, verified over five
    # faked clocks in the guard test. Between a meeting resolving and that
    # month ending the column can show a decided meeting, whose distribution
    # has collapsed onto the realised bracket; that is the page's existing
    # grace behaviour for every economics market, it reads as the rate path's
    # most recent anchor, and `resolution_date` is the sharper instrument if
    # anyone ever wants to close that window.
    def _is_fomc_ladder(m) -> bool:
        """Does this market belong in the rate-path heatmap at all?"""
        return (
            "fed funds rate after" in (m.name or "").lower()
            and len(_outcomes_sorted(m)) >= 3
        )

    # `_classify_theme` is re-asked rather than assumed so this set is provably
    # the old one plus ONLY what the confidence arm was rejecting — nothing
    # here can reach the card through a theme the old code never put it in.
    # (It is not free: these tickers are `KXFED-26SEP`, which matches no entry
    # in `_THEME_BY_TICKER` — `kxfedfunds`/`kxfedcuts`/`kxfedhikes` all miss the
    # hyphen — so they classify as "fed" via the NAME regex, and a ticker-prefix
    # change upstream could silently move them.)
    fomc_source = [
        m for m in all_markets
        if _is_fomc_ladder(m)
        and _classify_theme(m) == "fed"
        and should_exclude_from_featured(
            m.name, m.llm_sport_category, m.status, None, now,
        ) is None
    ]

    for m in fomc_source:
        outcomes = _outcomes_sorted(m)
        has_cumulative = any("above" in (o.name or "").lower() for o in outcomes)
        if has_cumulative:
            discrete = _cumulative_to_discrete(outcomes, max_buckets=10)
            # Reverse so highest rate is first (top of heatmap)
            discrete.reverse()
        else:
            discrete = _brackets_from_outcomes(m)

        date_str = m.name.split("after ")[-1].split("?")[0].strip() if "after" in (m.name or "") else ""
        mo = date_str.split(" ")[0] if date_str else ""
        # Extract year for sorting (e.g., "Jun 2026" → 202606)
        parts = date_str.split()
        sort_key = 0
        if len(parts) >= 2:
            year = int(parts[1]) if parts[1].isdigit() else 2026
            month_num = _MONTH_ORDER.get(mo[:3].lower(), 0)
            sort_key = year * 100 + month_num

        fomc_meetings.append({
            "date": date_str,
            "mo": mo,
            "dist": discrete,
            "resolved": m.status in ("resolved", "closed"),
            "market_id": m.id,
            "sort_key": sort_key,
        })

    for m in fed_markets:
        # Drawn as a heatmap column above, so it is not also a Side markets row.
        #
        # Measured, not assumed: this `continue` changes NOTHING today. Deleting
        # it leaves the guard suite green, because a ladder reaching the `else`
        # below hits `_market_row`, which refuses any market with more than five
        # outcomes — and these carry 11 to 18 rungs. It is kept as the explicit
        # statement of intent, and `test_a_ladder_can_never_become_a_side_row`
        # pins the refusal that makes it redundant, so whoever widens
        # `_market_row` finds out that this line just became load-bearing.
        if _is_fomc_ladder(m):
            continue
        name_lower = (m.name or "").lower()
        if "how many" in name_lower and ("cut" in name_lower or "hike" in name_lower):
            rate_cuts = _brackets_from_outcomes(m)
        else:
            _row = _market_row(m)
            if _row:
                rate_side.append(_row)

    # Sort FOMC meetings chronologically
    fomc_meetings.sort(key=lambda x: x.get("sort_key", 0))

    # --- Shared date filter: skip markets with past month+year in name ---
    _current_month = now.month
    _current_year = now.year
    _MONTH_NUMS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                   "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    _DATE_RE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{4})\b", re.I)

    def _is_past_date(name: str) -> bool:
        m = _DATE_RE.search(name.lower())
        if not m:
            return False
        m_num = _MONTH_NUMS.get(m.group(1)[:3], 0)
        m_year = int(m.group(2))
        return (m_year < _current_year) or (m_year == _current_year and m_num < _current_month)

    # Filter past-date markets from ALL themed sections
    for theme_key, theme_markets in list(themed.items()):
        themed[theme_key] = [m for m in theme_markets if not _is_past_date(m.name or "")]

    # Re-read filtered lists
    fed_markets = themed.get("fed", [])

    # The section's count must describe what the section RENDERS (#2870
    # follow-up, found by CERT-2899's grader).
    #
    # `fed_markets` is the post-exclusion theme list, so a restored ladder was
    # drawn as a heatmap column and then not counted. Two consequences, and the
    # second is the one that matters: the payload could report `count: 3`
    # beside six rendered meetings, and — because the page gates the whole
    # Federal Reserve section on `t.fed.count > 0` — a fed theme whose only
    # members were confidence-excluded ladders would yield 0 and hide a section
    # that had columns to draw.
    #
    # Latent rather than live when this was written: production `count` was 49,
    # held clear of zero by the three non-extreme 2027 controls. Fixed anyway,
    # because it is the same class as the bug this card was just repaired for —
    # a surface keyed on a set that is not the set it renders.
    #
    # A union by id, not a sum: a ladder that passes the full predicate is in
    # both lists and must not be counted twice.
    _fed_section_count = len(
        {m.id for m in fed_markets} | {m.id for m in fomc_source}
    )
    inflation_markets = themed.get("inflation", [])
    jobs_markets = themed.get("jobs", [])
    recession_markets = themed.get("recession", [])
    markets_markets = themed.get("markets", [])
    energy_markets = themed.get("energy", [])

    # --- Inflation section ---
    cpi_releases = []
    inflation_side = []
    for m in inflation_markets:
        name_lower = (m.name or "").lower()
        outcomes = _outcomes_sorted(m)
        has_cumulative = any("above" in (o.name or "").lower() for o in outcomes)
        if ("cpi" in name_lower or "inflation" in name_lower) and len(outcomes) >= 3:
            if has_cumulative:
                brackets = _cumulative_to_discrete(outcomes, max_buckets=6)
            else:
                brackets = _brackets_from_outcomes(m)
            if not brackets:
                _row = _market_row(m)
                if _row:
                    inflation_side.append(_row)
                continue
            modal_idx, _, _ = _modal_bracket(brackets)
            cpi_releases.append({
                "mo": _cpi_release_label(m.name or ""),
                # The question the market asks, in the venue's own words — the
                # same `q` every other row on this page carries (#3004, #6702).
                # A period label cannot separate Argentina's September inflation
                # from the US September CPI print, and on a card headed "CPI
                # releases" the reader has no way to tell which one the number
                # belongs to. The label is the hint; this is the truth.
                "q": m.name,
                "brackets": brackets,
                # Left true on every block ON PURPOSE. iOS gates the whole CPI
                # section on this field — `releases.filter { $0.upcoming ==
                # true }`, then `if !upcoming.isEmpty` — and draws its section
                # count from it, so narrowing it to the single next release
                # would cut native's card row from six to one. It reads "this
                # release has not happened yet", which is true of all of them.
                # The superlative the badge claims is `is_next`, below.
                "upcoming": True,
                "peakIs": modal_idx,
                "market_id": m.id,
                "_sort_key": _cpi_release_sort_key(m),
            })
        else:
            _row = _market_row(m)
            if _row:
                inflation_side.append(_row)

    # Soonest release first, then the badge. Sorting BEFORE the `[:6]` below is
    # the whole point — it decides which six of the 56 candidates a reader ever
    # sees, not merely what order they sit in (#2564, `_cpi_release_sort_key`).
    # Market id breaks the ties, and there are many: eight Kalshi markets price
    # the same September print to the same minute. A stable sort would leave
    # those in DB order, which is the undefined order this is replacing.
    cpi_releases.sort(key=lambda r: (r["_sort_key"], r["market_id"]))
    for _i, _release in enumerate(cpi_releases):
        # Exactly one block may claim to be next, and it is the first one only
        # because the list is now genuinely ordered. Stated by the payload
        # rather than inferred from array position by each client: a superlative
        # read off an index is true only for as long as nobody re-orders.
        _release["is_next"] = _i == 0
        del _release["_sort_key"]

    # --- Jobs section ---
    jobs_side = [r for m in jobs_markets if (r := _market_row(m))]

    # --- Recession/GDP section ---
    # The headline market is CHOSEN, and it ships its own question with it
    # (UX-P273 / #2674). It used to be "whichever binary recession market this
    # loop happened to see last", printed under a hardcoded "Recession by end
    # of 2026" label — on a query that carries no ORDER BY, so the pairing was
    # undefined rather than merely wrong. Measured on production 2026-09-02 it
    # was resolving to "Will the IMF declare a global recession before 2027?".
    rec_candidates: list[RecessionCandidate] = []
    rec_rows: list[tuple[int, dict]] = []
    gdp_quarters = []
    for m in recession_markets:
        name_lower = (m.name or "").lower()
        outcomes = _outcomes_sorted(m)
        if "recession" in name_lower and len(outcomes) <= 2:
            # Per-market, NOT accumulated. The old code tested the running
            # `rec_main_prob` here, so the `outcomes[0]` fallback could only
            # ever fire for the first candidate in the pool.
            prob_pct = None
            for o in outcomes:
                if (o.name or "").lower() in ("yes", ""):
                    prob_pct = round(float(o.current_probability or 0) * 100, 1)
                    break
            if prob_pct is None and outcomes:
                prob_pct = round(float(outcomes[0].current_probability or 0) * 100, 1)
            if prob_pct is not None:
                rec_candidates.append(
                    RecessionCandidate(
                        market_id=m.id, name=m.name or "", prob_pct=prob_pct,
                    )
                )
            _row = _market_row(m)
            if _row:
                rec_rows.append((m.id, _row))
        elif "gdp" in name_lower and len(outcomes) >= 3:
            has_cumulative = any("above" in (o.name or "").lower() for o in outcomes)
            if has_cumulative:
                brackets = _cumulative_to_discrete(outcomes, max_buckets=6)
            else:
                brackets = _brackets_from_outcomes(m)
            if brackets:
                gdp_quarters.append({
                    "q": m.name,
                    "dist": brackets,
                    "market_id": m.id,
                })
        else:
            _row = _market_row(m)
            if _row:
                rec_rows.append((m.id, _row))

    rec_headline = select_recession_headline(rec_candidates, current_year=now.year)
    rec_main_prob = rec_headline.prob_pct if rec_headline else None
    rec_main_q = rec_headline.name if rec_headline else None
    rec_main_market_id = rec_headline.market_id if rec_headline else None
    # The headline market is not ALSO printed as a row beneath itself. That
    # duplication is what let #2674's card show 13% above a contradicting 7%:
    # the headline was one arbitrary member of the list underneath it.
    rec_side = [row for mid, row in rec_rows if mid != rec_main_market_id]

    # --- Markets/indices section ---
    today_indices = []
    stocks = []
    markets_side = []
    for m in markets_markets:
        name_lower = (m.name or "").lower()
        if any(idx in name_lower for idx in ("nasdaq", "s&p", "dow", "vix")) and ("up or down" in name_lower or "close" in name_lower):
            _row = _index_row(m)
            if _row:
                today_indices.append(_row)
        elif any(stock in name_lower for stock in ("meta ", "aapl", "tsla", "nvda", "msft", "googl", "apple", "tesla", "nvidia", "microsoft", "google")):
            _row = _stock_row(m)
            if _row:
                stocks.append(_row)
        else:
            _row = _market_row(m)
            if _row:
                markets_side.append(_row)

    # --- Energy section ---
    gas_markets_list = []
    oil_rows = []
    for m in energy_markets:
        name_lower = (m.name or "").lower()
        outcomes = _outcomes_sorted(m)
        has_cumulative = any("above" in (o.name or "").lower() for o in outcomes)
        if ("gas" in name_lower or "oil" in name_lower or "wti" in name_lower or "brent" in name_lower or "natural gas" in name_lower) and len(outcomes) >= 3:
            # #3004. Only the OIL half is re-routed — `_oil_row` refuses a gas
            # market itself, so the histogram card's path stays byte-identical —
            # and it returns None for a genuine partition, which falls through
            # to the bracket path below unchanged.
            _oil = _oil_row(m)
            if _oil is not None:
                oil_rows.append(_oil)
                continue
            if has_cumulative:
                brackets = _cumulative_to_discrete(outcomes, max_buckets=6)
            else:
                brackets = _brackets_from_outcomes(m)
            if not brackets:
                _row = _market_row(m)
                if _row:
                    oil_rows.append(_row)
                continue
            _, modal_prob, modal_label = _modal_bracket(brackets)
            # Shorten the label
            short_label = m.name
            if len(short_label) > 40:
                for trim in [" on ", " at ", " for ", " in "]:
                    if trim in short_label.lower():
                        short_label = short_label[:short_label.lower().index(trim)]
                        break
            if "gas" in name_lower:
                gas_markets_list.append({
                    "label": short_label,
                    "val": modal_label,
                    "prob": modal_prob,
                    "brackets": brackets,
                    "src": _source(m),
                })
            else:
                oil_rows.append({
                    "sym": "WTI" if "wti" in name_lower else "Brent" if "brent" in name_lower else "Oil",
                    "prob": modal_prob,
                    "range": modal_label,
                    "src": _source(m),
                    "q": short_label,
                })
            continue
        else:
            _row = _market_row(m)
            if _row:
                oil_rows.append(_row)

    # --- Housing section ---
    # The mortgage card is CHOSEN and it ships its own question, the same repair
    # #2674 made to the recession headline one section up (#6702). It used to be
    # `mortgage_brackets = _brackets_from_outcomes(m)` inside this loop — last
    # match wins, on a query with no ORDER BY — under the hardcoded page label
    # "30-year mortgage rate by end of 2026". On production 2026-09-16 that drew
    # a market resolving the next morning.
    #
    # The numbers were the larger half. Every open mortgage market with rungs is
    # a CUMULATIVE ladder, and `_brackets_from_outcomes` rescales anything
    # summing past 105% back to 100: a thirteen-rung ladder summing to 1111%
    # printed its 94.5% rung as 8.5%. That is this file's own rule — see
    # `_CUMULATIVE_PREFIXES`, which says such rows "must never be normalized or
    # rescaled against each other" — and the branch simply never asked.
    #
    # A non-ladder mortgage market is therefore NOT a candidate: it would take
    # the rescaling path and reintroduce the defect. Tonight's example is
    # Polymarket's 115646 (`↑ 6.20%`, `↓ 6.00%`, plus a stray Yes/No pair),
    # which falls through to `_market_row` below exactly as it does today.
    mortgage_ladders: list[LadderCandidate] = []
    mortgage_by_id: dict[int, FuturesMarket] = {}
    housing_side = []
    for m in housing_markets:
        name_lower = (m.name or "").lower()
        if (
            "mortgage" in name_lower
            and len(_outcomes_sorted(m)) >= 3
            and _is_cumulative_ladder(m)
        ):
            mortgage_ladders.append(
                LadderCandidate(
                    market_id=m.id,
                    name=m.name or "",
                    probs=[
                        round(float(o.current_probability or 0) * 100, 1)
                        for o in m.outcomes
                    ],
                )
            )
            mortgage_by_id[m.id] = m
            continue
        _row = _market_row(m)
        if _row:
            housing_side.append(_row)

    _mortgage_pick = select_mortgage_ladder(mortgage_ladders)
    mortgage_dist = (
        _distribution_row(mortgage_by_id[_mortgage_pick.market_id], min_outcomes=3)
        if _mortgage_pick
        else None
    )

    # --- Trade & Government ---
    trade_rows = [r for m in trade_markets if (r := _market_row(m))]
    gov_rows = [r for m in gov_markets if (r := _market_row(m))]
    # Government markets are overwhelmingly multi-outcome (spending ladders,
    # deficit brackets), which _market_row refuses — leaving the section
    # rendering an empty card under a header that claimed `count` markets.
    gov_distributions = [d for m in gov_markets if (d := _distribution_row(m))]

    # Cross-source spotlight — fed the set this page ACCEPTED, not `all_markets`.
    # A market this page already refused to put in a theme section must not
    # reappear as its headline source disagreement. UX-P194-1 / CERT-540.
    cross_source = find_cross_source_markets(
        spotlight_eligible, market_row_fn=_cross_source_row_fn
    )

    themes = {
        "fed": {
            "count": _fed_section_count,
            "fomc_meetings": fomc_meetings[:8],
            "rate_cuts": rate_cuts,
            "side_markets": rate_side[:6],
        },
        "inflation": {
            "count": len(inflation_markets),
            "cpi_releases": cpi_releases[:6],
            "side_markets": inflation_side[:6],
        },
        "jobs": {
            "count": len(jobs_markets),
            "markets": jobs_side[:8],
        },
        "recession": {
            "count": len(recession_markets),
            "main_prob": rec_main_prob,
            # The question the headline number actually answers. The page
            # renders THIS, not a literal (UX-P273 / #2674).
            "main_q": rec_main_q,
            "main_market_id": rec_main_market_id,
            "gdp_quarters": gdp_quarters[:4],
            "side_markets": rec_side[:6],
        },
        "markets": {
            "count": len(markets_markets),
            "today": today_indices[:4],
            "stocks": stocks[:6],
            "side_markets": markets_side[:8],
        },
        "energy": {
            "count": len(energy_markets),
            "gas": gas_markets_list[:2],
            "oil": oil_rows[:4],
            "side_markets": [r for m in energy_markets if (r := _market_row(m))][:8],
        },
        "housing": {
            "count": len(housing_markets),
            # The card's own question travels with its rows. `kind` tells
            # the page whether they are a ladder (drawn raw) or a partition
            # (drawn as a histogram); `mortgage_brackets`, the bare
            # always-rescaled array this replaces, could say neither.
            "mortgage_dist": mortgage_dist,
            "markets": housing_side[:6],
        },
        "trade": {
            "count": len(trade_markets),
            "markets": trade_rows[:8],
        },
        "government": {
            "count": len(gov_markets),
            "markets": gov_rows[:8],
            "distributions": gov_distributions[:6],
        },
    }

    # #6978: THE HERO COUNTS WHAT THE PAGE CAN REACH, and the sections below
    # are the only thing that knows what that is.
    #
    # It used to be `len(all_markets)` — the PRE-GATE pool, taken before the
    # loop above drops a market through `should_exclude_from_featured` and
    # before `_classify_theme` files the remainder. Measured on the served
    # bank 2026-09-20 the hero said **1,732** while these nine sections summed
    # to **352**: 1,380 of the markets it advertised — 80% of them — were
    # reachable from nowhere on the page, and it called them "active".
    #
    # ⚠️ NOT `sum(len(v) for v in themed.values())`, which is the obvious fix
    # and is wrong HERE. `_classify_theme` on this route always returns a
    # theme, worst case the catch-all `"other"` (see its note above the loop),
    # and `other` is accepted by the loop and served by NO section — there is
    # no `/economics` equivalent of `/politics`'s Other chip. Summing `themed`
    # would move the hero 1,732 -> ~1,700 and leave the defect intact. The
    # served sections are the page's own answer to "what can I reach".
    #
    # ⚠️ Indexed, not `.get(..., 0)`. A future section with no `count` must
    # fail loudly in the guard rather than quietly shrink the hero.
    total = sum(t["count"] for t in themes.values())

    return {
        "total_markets": total,
        "updated_at": now.isoformat(),
        "cross_source": cross_source,
        "themes": themes,
        "by_source": {
            "kalshi": sum(1 for m in all_markets if _source(m) == "kalshi"),
            "polymarket": sum(1 for m in all_markets if _source(m) == "polymarket"),
        },
    }
