"""
Golf category landing page endpoint.

Aggregates futures market odds across Polymarket, Kalshi, and The Odds API for golf tournaments.
Groups by tournament, merges cross-source golfer odds, and computes biggest movers.
Enriches with PGA tour schedule from DataGolf for accurate current-event detection.
"""

import logging
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
from app.services import get_db
from app.utils.golf_evolution_market import (
    NON_CONTENDER_WINNER_RE,
    SETTLED_RESOLVE_MIN,
    contender_candidates,
    eligible_candidates,
    select_by_settled_resolution,
    select_by_snapshot_richness,
)
from app.utils.odds_math import probability_to_american
from app.utils.golf_membership import (
    drop_foreign_field_markets,
    is_foreign_domain,
    is_prop_outcome,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# Market validation — filter out non-golf false positives from LLM
# ============================================================================

# Non-golf terms in market names that indicate LLM miscategorization.
# The LLM sometimes classifies esports "Masters" events, entertainment props,
# and other non-golf markets as golf.
_NON_GOLF_RE = re.compile(
    r"\b(?:"
    # Esports
    r"vct|valorant|league\s+of\s+legends|\blol\b|dota|counter[-\s]?strike|"
    r"\bcs2?\b|esports?|overwatch|call\s+of\s+duty|fortnite|apex\s+legends|"
    r"rocket\s+league|starcraft|hearthstone|"
    # Sports leagues (not golf)
    r"\bnba\b|\bnfl\b|\bnhl\b|\bmlb\b|\bwnba\b|\bmls\b|\bufc\b|\bmma\b|"
    # Racquet sports that share tournament names with golf (#225: the "British
    # Open Squash" winner leaked into The (golf) Open's winner field and crowned
    # squash champion Paul Coll as a co-winner).
    r"\bsquash\b|\bbadminton\b|table\s+tennis|"
    r"\bepl\b|la\s+liga|serie\s+a|\bbundesliga\b|"
    r"super\s+bowl|world\s+series|stanley\s+cup|"
    # English football / EFL (prevents "EFL Championship" matching golf)
    r"\befl\b|english\s+football|football\s+league|"
    r"\bleague\s+(?:one|two)\b|championship\s+(?:relegation|promotion)|"
    r"\bfa\s+cup\b|\bcarabao\b|\bpremier\s+league\b|"
    r"\bligue\s+1\b|\beredivisie\b|\bscottish\b|"
    # Entertainment / media
    r"\boscar|emmy|grammy|golden\s+globe|tony\s+award|"
    r"netflix|hulu|disney\+|streaming|tv\s+show|television|"
    r"box\s+office|academy\s+award|"
    r"most[- ]watched|most[- ]streamed|"
    r"k-?pop|anime|manga|"
    r"movie|film\b|cinema|"
    r"reality\s+tv|talk\s+show|podcast|"
    r"album\s+of|concert|"
    r"motion\s+picture|producers?\s+guild|pga\s+award|"
    # Politics
    r"election|president(?:ial)?|senate|governor|congress|democrat|republican|"
    r"cabinet|supreme\s+court|"
    # Finance/crypto
    r"bitcoin|ethereum|crypto|stock\s+market|s&p|nasdaq|"
    # Weather
    r"temperature|weather|hurricane|tornado"
    r")\b",
    re.I,
)

# Positive golf signals — market names that indicate actual golf content.
# For Kalshi/Polymarket, passing the blocklist is necessary but not sufficient.
# The market name must also contain at least one golf-related term.
#
_GOLF_SIGNAL_RE = re.compile(
    r"\b(?:"
    r"golf|golfer|pga|lpga|"
    r"masters|"
    r"open|"
    r"classic|invitational|"
    r"ryder|presidents?\s+cup|"
    r"major|hole[-\s]in[-\s]one|"
    r"wgc|"
    r"liv\s+golf|korn\s+ferry|"
    r"dp\s+world|sunshine\s+tour|"
    r"asian\s+tour|european\s+tour|"
    r"top\s+\d+\s+finish|make\s+the?\s+cut|"
    r"birdie|bogey|eagle|par\s+\d|under\s+par"
    r")\b",
    re.I,
)

# ============================================================================
# The GENERIC-WORD gate (Q446) — a tournament word is not a sport claim
# ============================================================================
#
# `_GOLF_SIGNAL_RE` above accepts a market on `masters` alone, and `masters` is
# not a golf word: it is a generic English tournament word that darts, snooker,
# chess, esports and Philippine basketball all use. Measured on production
# 2026-08-29, that is not hypothetical. `GET /api/golf` was serving, inside its
# PGA Tour section:
#
#     New Zealand Darts Masters   15 "golfers"  (Simon Whitlock, James Wade)
#     Asia Masters 2026            4 "golfers"  (Dplus Challengers, T1 Esports
#                                                 Academy, NS Challengers, KT
#                                                 Challengers — a League of
#                                                 Legends bracket)
#
# The blocklist could not save either one: neither name contains a darts or an
# esports token, so both reached the allowlist and `masters` waved them through.
# Extending the blocklist is whack-a-mole — the next one is snooker, or pool, or
# a Masters of anything. The structural rule is that a GENERIC word is not
# evidence of a SPORT, so it may not stand alone.
#
# MONOTONE BY CONSTRUCTION, and that is the whole design (the rule `_is_placeholder_price`
# already follows below): this gate runs AFTER `_GOLF_SIGNAL_RE`, never instead of
# it, so it can only ever REJECT. No market that the golf page serves today starts
# being served because of this code. Verified over the full 7,622-row golf-identity
# population: 18 rejected, 0 admitted.
#
# WEAK: the words that may not stand alone.
_GOLF_WEAK_ONLY_RE = re.compile(
    r"\b(?:masters|open|classic|invitational|major)\b",
    re.I,
)

# ...and the rest of `_GOLF_SIGNAL_RE`, which may. Kept as its own pattern rather
# than as "signal minus weak" so that neither can be edited without the other
# being looked at.
_GOLF_STRONG_SIGNAL_RE = re.compile(
    r"\b(?:"
    r"golf|golfer|pga|lpga|"
    r"ryder|presidents?\s+cup|"
    r"hole[-\s]in[-\s]one|"
    r"wgc|"
    r"liv\s+golf|korn\s+ferry|"
    r"dp\s+world|sunshine\s+tour|"
    r"asian\s+tour|european\s+tour|"
    r"top\s+\d+\s+finish|make\s+the?\s+cut|"
    r"birdie|bogey|eagle|par\s+\d|under\s+par"
    r")\b",
    re.I,
)

# CORROBORATION 1 — Kalshi writes the tour into the ticker, ahead of the event
# name, and it does so systematically. That is a claim by the VENUE rather than by
# our own classifier, which is what makes it worth reading: `KXLPGAR2LEAD-CPKWO26`
# ("CPKC Women's Open End of Round 2 Leader") is real LPGA golf whose name says
# only "Open", and the first cut of this rule dropped it along with the darts.
#
# `KXPGAAWARDS` (the Producers Guild film awards) shares the `KXPGA` prefix and is
# NOT excluded here: `_NON_GOLF_RE` already refuses it on "pga award"/"motion
# picture" several lines earlier, so it never reaches corroboration.
_KALSHI_GOLF_TICKER_RE = re.compile(
    r"^kx(?:pga|lpga|dpworldtour|kornferry|kftour|liv|champtour|golf|prescup|rydercup)",
    re.I,
)

# CORROBORATION 2 — a named golf event, not a generic word. `masters` and
# `the open` are absent because they are the two ambiguous ones and have measured
# disambiguators of their own (`_is_the_masters`, `_is_the_open`), which the caller
# consults separately.
_GOLF_MAJOR_NAME_RE = re.compile(
    r"\b(?:"
    r"u\.?s\.?\s+open|pga\s+championship|players\s+championship|"
    r"ryder\s+cup|presidents?\s+cup|tour\s+championship|fedex\s+cup|"
    # The full name is unambiguous where the bare word is not: chess writes
    # "Grand Masters", darts "Darts Masters", the PBA "Fuel Masters". Only Augusta
    # writes "Masters Tournament" — and `_is_the_masters` will not vouch for
    # "the 2022 US Masters Tournament", because "us" is not one of the two words
    # it allows in front.
    r"masters\s+tournament"
    r")\b",
    re.I,
)

# CORROBORATION 3 — a golf MARKET SHAPE. "Will <player> finish in the Top 10 at
# the 2026 <event>?" is how Polymarket writes a golf placement market, and those
# names carry no golf word at all beyond the event's own generic one. Not promoted
# into `_GOLF_STRONG_SIGNAL_RE`, because that pattern is also the outer gate and
# adding a term to it would ADMIT 2,197 markets the page does not serve today —
# measured, and out of scope for a queue whose ship is removing wrong content.
_GOLF_SHAPE_RE = re.compile(
    r"\bfinish\s+in\s+the\s+top\s+\d+\b|\balbatross\b",
    re.I,
)


# Kalshi external_id patterns that are NOT golf despite LLM classification.
# These tickers indicate tennis or cross-sport markets.
_NON_GOLF_TICKER_RE = re.compile(
    r"kxgrandslam|kxgolftennis",
    re.I,
)


def _is_golf_market(market) -> bool:
    """Validate that a market is actually golf-related, not a false positive."""
    source = market.source or ""
    external_id = (market.external_id or "").lower()
    name = market.name or ""

    # DataGolf markets: always golf
    if source == "datagolf":
        return True

    # Odds API markets: trust the sport key prefix
    if source == "odds_api":
        return external_id.startswith("golf_")

    # Reject markets with non-golf Kalshi tickers (tennis grand slams, cross-sport)
    if _NON_GOLF_TICKER_RE.search(external_id):
        return False

    # For Kalshi/Polymarket: reject markets with clear non-golf signals
    if _NON_GOLF_RE.search(name):
        return False

    # UX-P168: the same question, asked of the #1625 membership authority rather
    # than of this module's private copy. `_NON_GOLF_RE` and `FOREIGN_TERMS` had
    # drifted apart — the authority knows domains (darts, snooker, chess, rodeo)
    # this regex never listed, and every one of them runs an event called a
    # "Masters" or an "Open", which `_GOLF_SIGNAL_RE` accepts on its own.
    if is_foreign_domain(name):
        return False

    # Require at least one positive golf signal in the market name.
    # This catches entertainment markets that the LLM miscategorized as golf
    # (e.g., movie/show names) which don't trigger the blocklist but also
    # have no golf-related terms.
    if not _GOLF_SIGNAL_RE.search(name):
        logger.debug("Golf filter: rejected '%s' (source=%s) — no golf signal", name, source)
        return False

    # THE GENERIC-WORD GATE (Q446). Everything above is unchanged; this runs after
    # it and can only reject. A market whose ONLY golf signal is a word every sport
    # owns must corroborate golf somewhere our classifier did not write it: the tour
    # the market itself declares (Kalshi encodes it in the ticker — `KXDPWORLDTOUR-OMEM26`
    # is how the real Omega European Masters survives this), a named golf event, one
    # of the two ambiguous majors via its own disambiguator, or a golf market shape.
    #
    # `llm_sport_category` is deliberately NOT corroboration: it is the field that put
    # every one of these rows here, so reading it back would be the classifier
    # vouching for itself.
    if _GOLF_STRONG_SIGNAL_RE.search(name):
        return True
    if not _GOLF_WEAK_ONLY_RE.search(name):
        # Signalled by something in `_GOLF_SIGNAL_RE` that is in neither list —
        # unreachable while the two patterns partition it, and an accept rather than
        # a reject so a future edit to one pattern cannot silently empty the page.
        return True
    if (
        _KALSHI_GOLF_TICKER_RE.search(external_id)
        or _declared_tour(name, external_id) is not None
        or _GOLF_MAJOR_NAME_RE.search(name)
        or _GOLF_SHAPE_RE.search(name)
        or _is_the_masters(name)
        or _is_the_open(name)
    ):
        return True

    logger.debug(
        "Golf filter: rejected '%s' (source=%s) — generic tournament word with no "
        "golf corroboration",
        name,
        source,
    )
    return False


# ============================================================================
# The golf identity prefilter — LAT-P058 / #1866
# ============================================================================
#
# This is the SQL superset that feeds `_is_golf_market` on the completed-tournament
# path. It was, when measured on production v3817, **the single largest consumer of
# physical reads in the entire database**:
#
#     1,110 calls/day · 492.2 MB physically read per call · mean 2,742 ms
#     = 533.7 GB/day = 19% of every physical read the database performs
#
# It reads 7,169 rows out of 779,617 (0.92%) and pays a full sequential scan of a
# 977 MB heap to find them, because the `OR` defeats every index on the table.
#
# THE MEASUREMENT THAT SHAPES THIS CODE (LAT-P058, production, `EXPLAIN` only):
#
#   | shape | plan | total cost |
#   |---|---|---|
#   | `OR`    | one Seq Scan                             | 128,191.5 |
#   | `UNION` | TWO Seq Scans + Sort + Unique            | 255,180.0 |
#
# A `UNION` rewrite of this predicate was built, indexed, measured, and **REFUSED**.
# It is not here, and it is not behind a flag. `docs/rulings/076-planner-cost-cannot-
# rank-two-statements.md` and `docs/audits/latency/lat-p061-split-scan-refused.md`
# carry the numbers; the short version, from 11 `EXPLAIN ANALYZE` runs whose last 8
# alternated the two shapes so warm-cache drift could not favour either arm:
#
#   | shape                        | planner cost | warm median | shared buffers |
#   |------------------------------|--------------|-------------|----------------|
#   | `OR` (this code, post-index) |     12,243.9 |  ≈ 18.4 ms  |          1.00x |
#   | `UNION`                      |      4,361.8 |  ≈ 88.2 ms  |      **2.45x** |
#
# The `UNION` is **4.79x SLOWER** while costing 2.8x LESS on paper — 94 of its 98 ms
# is a `HashAggregate` the `OR` never pays and the planner priced at nearly nothing.
# That inversion is ruling 076's first clause: planner cost cannot rank two different
# statements, only two plans for the same one.
#
# **THE DDL ALONE WAS THE WHOLE WIN, with the rewrite never once reachable.** The two
# partial indexes below took planner cost 128,191.5 -> 12,243.92, per-call physical
# reads 516.7 -> 2.395 MB (~216x, 427.6 -> 3.2 GB/day), warm runtime ~2,900 -> ~18 ms.
# Do not reintroduce the split scan to "finish" that work; the work is finished, and
# the split scan was never the part that did it.
#
# Ruling 076's second clause is why no flag survives here: measured-worse code behind
# a permanently-off switch is not a rollback path, it is a trap. A green-tested,
# documented alternative one `heroku config:set` away reads as an unfinished migration
# rather than a closed experiment, and someone eventually finishes it (#1917).

#: The two partial indexes this `OR` depends on for its `BitmapOr`. Live and
#: load-bearing — named here so the spec, the DDL and the code cannot drift apart
#: silently. NOT optional: without them this predicate is a full seq scan of a 977 MB
#: heap, which is the 19%-of-all-physical-reads defect described above.
GOLF_IDENTITY_INDEXES = ("ix_fm_golf_identity_category", "ix_fm_golf_identity_extid")


def golf_identity_select():
    """The golf identity prefilter: one statement, the indexed `OR`.

    Selects exactly the four columns the caller reads — `_is_golf_market` uses
    source/external_id/name and the slug test uses name — and no outcomes.

    There is deliberately no alternative shape and no switch. See the module comment
    above for the measurement that refused the `UNION`, and
    `test_golf_identity_prefilter.py` for the compiled-SQL and predicate-level proofs
    that this shape selects what it claims to.
    """
    cols = (
        FuturesMarket.id,
        FuturesMarket.source,
        FuturesMarket.external_id,
        FuturesMarket.name,
    )
    by_external_id = FuturesMarket.external_id.ilike("golf_%")
    by_category = FuturesMarket.llm_sport_category == "golf"

    return select(*cols).where(or_(by_external_id, by_category))


# ============================================================================
# Tournament classification
# ============================================================================

# Patterns that look like "Open Championship" but are NOT The Open Championship.
# Must be checked before _TOURNAMENT_PATTERNS to prevent false classification.
# "senior open" catches the U.S. Senior Open Championship (KXCHAMPTOUR-USSOC*)
# and The Senior Open Championship — Champions/senior-tour majors whose names
# contain "Open Championship" and would otherwise fold into The (British) Open's
# family, contaminating its winner group with a different field (L2-90 render gap).
# "last-chance qualifier"/"final qualifying" catch The Open's DISTINCT pre-tournament
# Final Qualifying event (KXPGATOUR-THOLCQ26, "The Open: Last-Chance Qualifier
# Winner") — a separate field of hopefuls competing for entry, not the championship
# itself; it name-matches "the open" and would otherwise surface on the championship
# page (L2-93 render gap, caught on the Open debut-eve pass).
_NOT_THE_OPEN_RE = re.compile(
    r"south\s+african\s+open|joburg\s+open|kenya\s+open|senior\s+open"
    r"|last[-\s]?chance\s+qualifier|final\s+qualifying",
    re.I,
)

# Order matters: more specific patterns first
_TOURNAMENT_PATTERNS = [
    (re.compile(r"(?:the\s+)?masters(?:\s+(?:tournament|golf|winner|champion))?(?!\s+(?:tour|bangkok|shanghai|madrid|tokyo|reykjavik|copenhagen))", re.I), "masters"),
    # NOTE: "Augusta National Invitational" is a Kalshi participation/field
    # market, NOT a winner market. Do NOT map it to "masters" — its high
    # per-golfer probabilities (80-95%) corrupt winner market averages.
    # It is suppressed below via the market probability sum guard.
    (re.compile(r"pga\s+championship", re.I), "pga_championship"),
    (re.compile(r"us\s+open|u\.s\.\s+open", re.I), "us_open"),
    (re.compile(r"the\s+open\s+championship|(?:the\s+)?open\s+championship|british\s+open|the\s+open\b", re.I), "the_open"),
    (re.compile(r"players\s+championship", re.I), "players"),
    (re.compile(r"ryder\s+cup", re.I), "ryder_cup"),
    (re.compile(r"presidents?\s+cup", re.I), "presidents_cup"),
    (re.compile(r"liv\s+golf", re.I), "liv"),
    (re.compile(r"tomorrow'?s?\s+golf\s+league|tgl\s+champion", re.I), "tgl"),
]

# #950: Polymarket intermittently obfuscates major trademarks (e.g. "uptspt
# Open" for "U.S. Open"). A scrambled name shares too few words with the real
# major, so it orphans into a separate card instead of merging. Normalize known
# scrambles to the canonical name BEFORE pattern matching. Small + reusable —
# extend as new scrambles are observed. (Defensive: as of prod 2026-06-18 no
# scrambled major name is present — current Polymarket major names are clean —
# but the obfuscation recurs, so this is forward insurance.)
_SCRAMBLED_MAJOR_FIXUPS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"uptspt\s+open", re.I), "U.S. Open"),
]


def _fix_scrambled_major(market_name: str) -> str:
    """Replace a known scrambled major name with its canonical form."""
    for pattern, canonical in _SCRAMBLED_MAJOR_FIXUPS:
        if pattern.search(market_name):
            return pattern.sub(canonical, market_name)
    return market_name


TOURNAMENT_DISPLAY_NAMES = {
    "masters": "The Masters",
    "pga_championship": "PGA Championship",
    "us_open": "U.S. Open",
    "the_open": "The Open Championship",
    "players": "The Players Championship",
    "ryder_cup": "Ryder Cup",
    "presidents_cup": "Presidents Cup",
    "liv": "LIV Golf",
    "tgl": "TGL",
    "other": "Other Tournaments",
    # Women's variants — separated from men's to prevent cross-contamination
    "masters_womens": "The Masters (Women's)",
    "pga_championship_womens": "KPMG Women's PGA Championship",
    "us_open_womens": "U.S. Women's Open",
    "the_open_womens": "AIG Women's Open",
    "players_womens": "The Players Championship (Women's)",
}

MAJOR_TOURNAMENTS = {"masters", "pga_championship", "us_open", "the_open"}


# ============================================================================
# Fold discriminators — LEVEL and TOUR (UX-P126 / F4)
# ============================================================================
#
# `_normalize_tournament`'s Priority-1 patterns are SUBSTRING matches. Any market
# whose name merely CONTAINS a major's noun was claimed by that major's key, so
# unrelated events folded onto one card. Measured live 2026-08-24, key `masters`
# claimed 22 open markets spanning SEVEN distinct real-world events:
#
#   * Masters Tournament Winner            (odds_api — the actual Augusta major)
#   * Husqvarna British Masters ... x6     (DP World Tour, datagolf + kalshi)
#   * DP World Tour: British Masters x7    (the same event, polymarket)
#   * Asia Masters 2026 Winner             (not golf)
#   * Masters London 2026 x4               (Valorant)
#   * New Zealand Darts Masters: Winner    (darts)
#   * Hitpoint Masters 2026 Summer: Winner (esports)
#
# The user-visible cost is NOT a messy card — it is a MISSING one. The folded key
# inherits Augusta's DataGolf schedule (`_TOURN_TO_SCHED_KEY`), whose end_date is
# April, so `_filter_stale_tournaments` drops the whole group. On 2026-08-24 the
# Husqvarna British Masters — a real DP World Tour event teeing off in three days,
# with 13 open markets across three sources — was absent from `/api/golf` entirely,
# while the Tour Championship (identical Aug-27..30 dates) rendered fine.
#
# Two discriminators gate the claim; gender is handled separately by `_WOMENS_RE`.

# LEVEL: "Masters" alone is the major. Every other event qualifies the word with a
# sponsor, a place, or a discipline. Claim the major only when nothing qualifies it.
_MASTERS_TOKEN_RE = re.compile(r"\bmasters\b", re.I)
_MASTERS_ALLOWED_BEFORE = {"the", ""}
_MASTERS_ALLOWED_AFTER = {"tournament", "golf", "winner", "champion", "champions",
                          "odds", "field", "top", ""}


def _word_at(tokens: list[str], index: int) -> str:
    """Alphanumeric-only form of a boundary token, or '' when absent."""
    if not tokens:
        return ""
    return re.sub(r"[^a-z0-9]", "", tokens[index].lower())


# A clause separator ends the qualifier's reach. "PGA Tour: Masters Tournament" is
# Augusta with a source prefix, not an event called "Tour Masters" — without this,
# the level guard refused a legitimate Polymarket major.
_CLAUSE_END_RE = re.compile(r"[:\-–—,(|]\s*$")


def _preceding_word(text_before: str) -> str:
    """The qualifier immediately before a token, or '' across a clause boundary."""
    if not text_before.strip() or _CLAUSE_END_RE.search(text_before):
        return ""
    return _word_at(text_before.split(), -1)


def _is_the_masters(market_name: str) -> bool:
    """True only when 'Masters' in this name means the Augusta major."""
    for match in _MASTERS_TOKEN_RE.finditer(market_name):
        prev = _preceding_word(market_name[: match.start()])
        nxt = _word_at(market_name[match.end():].split(), 0)
        if prev and not (prev in _MASTERS_ALLOWED_BEFORE or prev.isdigit()):
            continue
        if nxt and not (nxt in _MASTERS_ALLOWED_AFTER or nxt.isdigit()):
            continue
        return True
    return False


# LEVEL, the same shape for `the_open`. Its specific arms ("Open Championship",
# "British Open") are unambiguous and bypass the check entirely, so the major's own
# card is never at risk. The bare `the open` arm is the loose one: it claimed
# "Will Anthropic sign the Open Weights and American AI Leadership letter?", where
# "open" is an ADJECTIVE. In golf it is a noun — terminal, or followed by a golf
# market-type word.
_THE_OPEN_BARE_RE = re.compile(r"\bthe\s+open\b", re.I)
_THE_OPEN_SPECIFIC_RE = re.compile(r"open\s+championship|british\s+open", re.I)
_THE_OPEN_ALLOWED_AFTER = {
    "championship", "champion", "winner", "golf", "tournament", "odds", "field",
    "top", "make", "cut", "round", "rounds", "leader", "finish", "finishers",
    "hole", "holes", "first", "second", "third", "fourth", "final", "playoff",
    "at", "in", "this", "next", "by", "before", "after", "",
}


def _is_the_open(market_name: str) -> bool:
    """True only when 'the Open' in this name means The Open Championship."""
    if _THE_OPEN_SPECIFIC_RE.search(market_name):
        return True
    for match in _THE_OPEN_BARE_RE.finditer(market_name):
        nxt = _word_at(market_name[match.end():].split(), 0)
        if nxt and not (nxt in _THE_OPEN_ALLOWED_AFTER or nxt.isdigit()):
            continue
        return True
    return False


# TOUR: a men's major is played on the PGA Tour; a market that explicitly declares
# one of these other tours is, by that declaration, a different event. `pga` is NOT
# here (Polymarket prefixes majors with "PGA Tour:"), and `lpga` is NOT here
# (gender is the `_womens` suffix's job, and `us_open_womens` is a real card).
_MAJOR_EXCLUSIVE_TOURS = {"dp_world", "korn_ferry", "sunshine", "asian", "tgl", "liv"}

_DECLARED_TOUR_PATTERNS = [
    (re.compile(r"\bdp\s+world\s+tour\b|\beuropean\s+tour\b", re.I), "dp_world"),
    (re.compile(r"\bkorn\s+ferry\b|\bnationwide\s+tour\b", re.I), "korn_ferry"),
    (re.compile(r"\bsunshine\s+tour\b", re.I), "sunshine"),
    (re.compile(r"\basian\s+tour\b", re.I), "asian"),
    (re.compile(r"\bliv\s+golf\b", re.I), "liv"),
    (re.compile(r"\btgl\b|tomorrow'?s?\s+golf\s+league", re.I), "tgl"),
]

# Kalshi encodes the tour in the ticker prefix, ahead of the event name.
_KALSHI_TICKER_TOUR_RE = [
    (re.compile(r"^kxdpworldtour", re.I), "dp_world"),
    (re.compile(r"^kxkornferry", re.I), "korn_ferry"),
    (re.compile(r"^kxliv", re.I), "liv"),
]


def _declared_tour(market_name: str, external_id: str | None = None) -> str | None:
    """The tour this market explicitly declares, or None when it declares nothing.

    Absence is permissive on purpose: cross-source folding is the product, and the
    odds_api major ("Masters Tournament Winner") declares no tour at all. Only an
    explicit CONTRADICTION blocks a fold.
    """
    eid = external_id or ""
    if eid.startswith("datagolf:"):
        parts = eid.split(":")
        if len(parts) >= 2:
            mapped = _datagolf_tour_to_key(parts[1])
            if mapped:
                return mapped
    for pattern, tour in _KALSHI_TICKER_TOUR_RE:
        if pattern.search(eid):
            return tour
    for pattern, tour in _DECLARED_TOUR_PATTERNS:
        if pattern.search(market_name):
            return tour
    return None


# The market-type tail that turns one tournament into one card. Separator optional.
_MARKET_TYPE_SUFFIX_RE = re.compile(
    r"\s*(?:[-–:]\s*)?(?:"
    r"Tournament\s+Winner|Winner|Champion"
    r"|Top\s+\d+(?:\s+Finish(?:ers)?)?"
    r"|(?:To\s+)?Make\s+(?:the\s+)?Cut"
    r"|(?:End\s+of\s+)?Round\s+\d+\s+Leader"
    r"|(?:First|Second|Third|Fourth|Final)\s+Round\s+Leader"
    r"|Hole[-\s]?in[-\s]?One"
    r")\s*\??\s*$",
    re.I,
)


_TOUR_PREFIX_RE = re.compile(
    r"^(?:PGA\s+Tour|DP\s+World\s+Tour|European\s+Tour|LPGA|Korn\s+Ferry\s+Tour"
    r"|Asian\s+Tour|Sunshine\s+Tour):\s*",
    re.I,
)


def _strip_market_chrome(name: str) -> str:
    """Drop the tour prefix and the market-type tail, leaving the event name."""
    clean = _MARKET_TYPE_SUFFIX_RE.sub("", name)
    clean = _TOUR_PREFIX_RE.sub("", clean)
    return re.sub(r"\s*\?\s*$", "", clean).strip()


def _slug_tournament(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _major_claim_allowed(key: str, market_name: str, external_id: str | None) -> bool:
    """Gate a Priority-1 major claim on the LEVEL and TOUR discriminators."""
    if key == "masters" and not _is_the_masters(market_name):
        return False
    if key == "the_open" and not _is_the_open(market_name):
        return False
    if key in MAJOR_TOURNAMENTS:
        declared = _declared_tour(market_name, external_id)
        if declared in _MAJOR_EXCLUSIVE_TOURS:
            return False
    return True


# Tokens every LIV market shares, so none of them can distinguish one LIV event
# from another. "liv golf" is the tour's name; it is the question, not the answer.
_LIV_GENERIC_TOKENS = {"liv", "golf", "tour", "tournament"}


def _names_a_scheduled_liv_event(market_name: str, schedule: list[dict] | None) -> bool:
    """True if this market names a SPECIFIC LIV event that the schedule knows about.

    UX-P127 residual 2. Priority-1's `liv\\s+golf` pattern is a tour claim, and it was
    swallowing the events: nine open markets sat under key `liv` on 2026-08-24 —
    LIV Golf Indianapolis (5), LIV Golf New York (2), a corporate-shutdown question
    and a Q1-2027 eligibility question — one bucket holding four different subjects.

    The discriminator is anchored on the SCHEDULE rather than a city regex, for the
    same reason F4's was anchored on the tour: a regex would have to enumerate every
    venue LIV ever visits, and the day it misses one the market silently rejoins the
    bucket. With no schedule (DataGolf down) this returns False and the tour key is
    kept — no authority, no split.

    A match requires the event's DISTINGUISHING tokens, not merely a shared one.
    "LIV Golf New York" needs both `new` and `york`, so "announce a new team" cannot
    forge the claim — one shared token is exactly how F4's original defect worked.
    """
    if not schedule:
        return False

    market_tokens = {w.lower() for w in re.findall(r"[a-z]{3,}", market_name, re.I)}

    for entry in schedule:
        name = entry.get("name", "")
        if not re.search(r"\bliv\s+golf\b", name, re.I):
            continue
        distinguishing = {
            w.lower() for w in re.findall(r"[a-z]{3,}", name, re.I)
        } - _LIV_GENERIC_TOKENS
        if not distinguishing:
            continue
        # One-word venues ("Indianapolis") need that word; multi-word venues
        # ("New York") need at least two, so no single generic word suffices.
        needed = min(2, len(distinguishing))
        if len(market_tokens & distinguishing) >= needed:
            return True

    return False


# PGA Tour Signature Events — elevated purse/field, top-tier regular season events
_SIGNATURE_EVENTS = {
    "arnold_palmer_invitational",
    "the_genesis_invitational",
    "genesis_invitational",
    "the_players_championship",
    "memorial_tournament",
    "the_sentry",
    "at_t_pebble_beach",
    "at_t_pebble_beach_pro_am",
    "rbc_heritage",
    "wells_fargo_championship",
    "travelers_championship",
    "fedex_st_jude_championship",
}

from app.utils.name_normalization import clean_slug as _clean_slug, strip_diacritics as _strip_diacritics_canonical, _SPONSOR_SUFFIX_RE

TOURNAMENT_ORDER = [
    "masters", "pga_championship", "us_open", "the_open",
    "players", "ryder_cup", "presidents_cup",
    # Women's majors after men's majors
    "masters_womens", "pga_championship_womens", "us_open_womens", "the_open_womens",
    "liv", "tgl", "other",
]

# Max golfers to return per tournament
_MAX_GOLFERS = 15

# Outcomes that are not individual golfer names — skip these.
# Catches prop market outcomes that leak through when Kalshi groups
# multiple market types (winner, tour, nationality, score, margin)
# under the same tournament name.
_PROP_OUTCOME_RE = re.compile(
    r"(?:"
    r"\d\+\s|"                   # "1+ golf major..."
    r"\bany\s+golfer\b|"         # "Any golfer"
    r"\bcombined\b|"             # "...combined"
    r"\band\b.*\bcombined\b|"    # "X, Y, and Z combined"
    r"^yes$|^no$|"               # Binary yes/no outcomes
    # Tour name outcomes (from "tour of winner" props)
    r"^pga\s+tour$|"             # "PGA Tour"
    r"^liv$|"                    # "LIV"
    r"^dp\s+world|"              # "DP World Tour"
    r"^european\s+tour|"         # "European Tour"
    r"^korn\s+ferry|"            # "Korn Ferry Tour"
    r"^asian\s+tour|"            # "Asian Tour"
    # Country/region outcomes (from "nationality of winner" props)
    r"\bunited\s+states\b|"      # "United States"
    r"\bunited\s+kingdom\b|"     # "United Kingdom & Ireland"
    r"\bcontinental\s+europe\b|" # "Continental Europe"
    r"\brest\s+of\s+(?:the\s+)?world\b|" # "Rest of World"
    r"^(?:europe|asia|africa|australia|international)$|"  # Single-word regions
    # Score/margin outcomes (from "winning score" and "margin" props)
    r"\bexactly\s+\d+|"          # "Exactly 1 stroke", "Exactly 0 strokes"
    r"\bstroke|"                  # Anything with "stroke(s)"
    r"\bwinning\s+score|"        # "Winning Score: -13 to -15"
    r"-\d+\s+to\s+-\d+|"         # Score ranges like "-13 to -15"
    r"\bunder\s+par\b|"          # "Under par" props
    r"\bover\s+par\b|"           # "Over par" props
    r"\bbogey|"                   # "Bogey-free round" etc.
    r"\bbirdie"                   # "Most birdies" etc.
    r")",
    re.I,
)

# Ordinal words a source may use where another uses a digit. UX-P070: the round-leader
# exclusion below enumerated Kalshi's digit phrasing ("Round 2 Leader") plus exactly ONE
# hand-patched word ("first round leader"), so Polymarket's "Second/Third/Final Round
# Leader" classified as an OUTRIGHT WINNER market. Enumerating a naming convention is
# only ever complete for the source it was read off; spell both spellings once, here.
_ORDINAL_WORD = r"first|second|third|fourth|fifth|sixth|seventh|final"

# Round-leader markets in EITHER phrasing and EITHER spelling — "Round 2 Leader",
# "End of Round 1 Leader", "First Round Leader", "Second Round Leader", "2nd Round
# Leader". These are placement markets about a single round, never the tournament
# winner, and must never reach the winner field.
_ROUND_LEADER_RE_SRC = (
    r"\bround\s+(?:\d+|" + _ORDINAL_WORD + r")\s+leader\b|"
    r"\b(?:\d+(?:st|nd|rd|th)|" + _ORDINAL_WORD + r")\s+round\s+leader\b"
)

# Markets that are NOT outright winner markets — exclude from headline probability.
# These include field/participation markets, placement, and prop bets.
#
# UX-P070 — this pattern was wrong in BOTH directions, and both errors came from
# reading one source's titles:
#   * UNDER-exclusion: see `_ROUND_LEADER_RE_SRC` above.
#   * OVER-exclusion: `\btour\b.*\bwinner\b` was written for the Kalshi prop "Tour of
#     Winner", but `.*` makes it swallow every tour-PREFIXED title Polymarket uses —
#     "PGA Tour: FedEx St. Jude Championship Winner", "DP World Tour: … Winner",
#     "Korn Ferry Tour: … Winner". Measured across futures_markets: 23 golf markets
#     dropped (20 resolved carrying 1,957 priced outcomes), and ZERO golf true
#     positives — there is no golf "Tour of Winner" market in the table at all.
#     The correct phrasing was already derived once, for #955, and is documented in
#     `app.utils.golf_evolution_market.NON_CONTENDER_WINNER_RE` with a comment naming
#     this exact over-breadth ("must NOT match a real field like 'PGA Tour: U.S. Open
#     Winner' … rather than a broad 'tour .* winner'"). It was applied to the CHART
#     consumer and not to this one, so the two copies disagreed and the aggregation
#     kept the broken half. Same prop phrasing is used here now.
_NON_WINNER_MARKET_RE = re.compile(
    r"(?:"
    r"\bcompete\s+(?:in|at)\b|"  # "Golfers to compete in/at The Masters"
    r"\bplay\s+(?:in|at)\b|"     # "Will Tiger Woods play in/at..."
    r"\bparticipat|"             # "participate in"
    r"\binvitational\b|"         # "Augusta National Invitational" (Kalshi participation market)
    r"\bmake\s+(?:the\s+)?cut\b|" # "Make Cut" / "Make the Cut" placement markets
    r"\bmade\s+(?:the\s+)?cut\b|" # "Made Cut" / "Made the Cut" (past tense)
    r"\bTop\s+\d+\b|"            # "Top 5/10/20 Finishers"
    + _ROUND_LEADER_RE_SRC + r"|"  # every round-leader phrasing/spelling (UX-P070)
    + r"\b(?:miss|made)\s+the\s+cut\b|"
    r"\bfield\s+size\b|"         # "Field size" props
    r"\bnumber\s+of\b|"          # "Number of birdies" etc.
    r"\bhole[- ]in[- ]one\b|"    # Hole-in-one props
    r"\bplayoff\b|"              # "Will there be a playoff"
    r"\bwill\b.*\bplay\b|"       # "Will X play in..."
    r"\bwill\b.*\bcompete\b|"    # "Will X compete in/at..."
    r"\btee\s+(?:it\s+)?up\b|"   # "Will X tee up at..."
    r"\bin\s+the\s+field\b|"     # "Will X be in the field?"
    r"\bcaptain\b|"              # "U.S. Team Captain at 2027 Ryder Cup"
    # Prop market types (Kalshi creates separate events for these)
    r"\bnationality\b|"          # "Nationality of Winner"
    # "Country/Tour/Region of (the) Winner" — the PROP phrasing, not a broad
    # `country|tour .* winner`, which swallowed real tour-prefixed winner fields
    # (UX-P070; phrasing proven by #955's NON_CONTENDER_WINNER_RE).
    r"\b(?:country|tour|region|state)\s+of\s+(?:the\s+)?winner\b|"
    r"\bwinner'?s?\s+tour\b|"    # "Winner's Tour"
    r"\bwinning\s+score\b|"      # "Winning Score"
    r"\bscore\s+range\b|"        # "Score Range"
    r"\bmargin\s+of\s+victory\b|" # "Margin of Victory"
    r"\bwinning\s+margin\b|"     # "Winning Margin"
    r"\bmargin\s+in\s+stroke|"   # "Margin in strokes"
    r"\b(?:over|under)\s+par\b|" # "Over/Under Par"
    r"\bstroke[s]?\s+(?:margin|lead|ahead)\b" # "Strokes margin/lead"
    r")",
    re.I,
)

# Positive outright-winner signal — paired with _NON_WINNER_MARKET_RE (which
# excludes props like "Nationality of Winner") to detect a true winner field.
_WINNER_MARKET_RE = re.compile(r"\b(?:winner|to\s+win)\b", re.I)

# The evolution-chart pick (which winner market draws the path-to-resolution
# line) moved to `app.utils.golf_evolution_market` as a pure module, alongside the
# LAT-P020/#1107 fix that batched its inputs — ruling 005, extract-on-touch.
# Re-exported under the original private names because `_NON_CONTENDER_WINNER_RE`
# is also read by `_golf_winner_renorm_factor` below and imported by
# `tests/test_golf_tournament_render.py`.
_SETTLED_RESOLVE_MIN = SETTLED_RESOLVE_MIN
_NON_CONTENDER_WINNER_RE = NON_CONTENDER_WINNER_RE


def _golf_winner_renorm_factor(
    market_name: str, n_outcomes: int, prob_sum: float
) -> float | None:
    """Renormalization factor for a golf winner market, or None to skip it (#926).

    Kalshi tournament-WINNER markets are independent per-golfer binaries that sum
    well over 100% (gotcha #23). They represent a real field, so we renormalize
    them to sum 1.0 (factor = 1/sum) instead of dropping them at the >1.5
    participation-market skip — but ONLY when there's a positive winner signal,
    ≥4 candidates, and it isn't a participation/threshold/prop market. Markets
    summing <=1.5 are returned with factor 1.0 (used as-is, unchanged — keeps the
    existing majors like the 1.483-sum U.S. Open winner identical).

    THE CONTRACT, STATED HONESTLY (UX-P070). A previous version of this docstring
    claimed "genuine participation markets (make-cut, top-N, round-leader, scores)
    return None". **That is only true above the 1.5 threshold.** The `prob_sum <= 1.5`
    early return fires FIRST and is name-blind, so a one-outcome "Second Round Leader"
    summing 0.5 returns 1.0 — verified by direct call. This function is a
    RENORMALIZATION rule, not an exclusion rule; excluding placement markets is the
    caller's job, via `_NON_WINNER_MARKET_RE`. The docstring mattered: it read as a
    second line of defence that does not exist, so the ordinal gap in that regex had
    nothing behind it.
    """
    if prob_sum <= 1.5:
        return 1.0
    is_winner_field = (
        n_outcomes >= 4
        and bool(_WINNER_MARKET_RE.search(market_name))
        and not _NON_WINNER_MARKET_RE.search(market_name)
    )
    if is_winner_field and prob_sum > 0:
        return 1.0 / prob_sum
    return None


# Women's / LPGA detection — THE ONE GENDER DISCRIMINATOR (UX-P126 / F4).
#
# There used to be two. The fold key at `get_golf` used this regex; the completed-
# tournament path used an inline `women|lpga|chevron|amundi`. They disagreed in both
# directions: the inline one knew the two sponsor-named LPGA majors (Chevron, Amundi
# Evian) that this one did not, and this one knew "ladies" and the possessive
# boundary that the inline one did not. A Chevron Championship market therefore
# folded onto a MEN'S key here while being labelled `is_womens: true` there — the
# same market, two answers, on two surfaces. A discriminator that two callers
# implement twice is not a discriminator.
_WOMENS_RE = re.compile(r"\b(?:lpga|women'?s?|ladies|chevron|amundi)\b", re.I)

# ============================================================================
# Tour classification — classify each tournament by tour
# ============================================================================

_TOUR_CLASSIFICATION_PATTERNS = [
    (re.compile(r"\b(?:dp\s+world|european\s+tour|rolex\s+series)\b", re.I), "dp_world"),
    (re.compile(r"\b(?:lpga|women'?s?\s+(?:open|championship|tour))\b", re.I), "lpga"),
    (re.compile(r"\bliv\s+golf\b", re.I), "liv"),
    (re.compile(r"\b(?:korn\s+ferry|nationwide)\b", re.I), "korn_ferry"),
    (re.compile(r"\b(?:sunshine\s+tour)\b", re.I), "sunshine"),
    (re.compile(r"\b(?:asian\s+tour)\b", re.I), "asian"),
    (re.compile(r"\btgl\b|tomorrow'?s?\s+golf", re.I), "tgl"),
]

# UX-P185. A last-resort NAME recognizer for the PGA Tour, applied only where every
# authoritative signal has already declined. It exists so that inverting the default
# below (unknown tour -> None, not "pga") cannot strip a badge from a market that
# says PGA Tour in its own title, e.g. the `KXGOLFMAJOR` series
# ("Golfers to win a PGA Tour Major in 2027"), which carries no tour-bearing ticker.
# It is deliberately NOT in the list above: the list runs ahead of the DataGolf and
# ticker evidence, and a bare `pga` must never outrank either.
_PGA_NAME_FALLBACK_RE = re.compile(r"\bpga\b", re.I)

# UX-P185. Kalshi names the tour in the SERIES segment of its ticker — the text before
# the first "-" — and it is the only tour signal a Kalshi-only tournament carries.
# Matched as an ANCHORED prefix on that segment alone.
#
# ⚠️ A substring test over the whole external_id is lethal here, measured against
# production 2026-08-30: `KXECULPGAME` (Ecuadorian league football, 210 markets)
# contains "LPGA", and every `...CUPGAME` series — `KXEFLCUPGAME`, `KXFACUPGAME`,
# `KXCONCACAFCCUPGAME`, 15 more — contains "PGA", as does `KXEFLCHAMPIONSHIPGAME`.
#
# ⚠️ `KXLIV` is DELIBERATELY ABSENT. It would be the obvious fourth entry and it is a
# false friend: `KXLIVENATIONUS` ("Courts consider Live Nation a monopoly?") shares the
# prefix. LIV Golf needs no ticker rule — every LIV event names itself in the market
# title and `\bliv\s+golf\b` above already claims it.
#
# Every prefix below was swept over the full production table before being added; each
# resolves only to golf: KXDPWORLDTOUR 63 markets / 5 series, KXLPGA 52 / 4,
# KXKFTOUR 15 / 1.
_KALSHI_SERIES_TOUR_PREFIXES = [
    ("KXDPWORLDTOUR", "dp_world"),
    ("KXLPGA", "lpga"),
    ("KXKFTOUR", "korn_ferry"),
    ("KXPGA", "pga"),
]


def _kalshi_series_tour(kalshi_external_ids: list[str] | None) -> str | None:
    """Read the tour out of a Kalshi series ticker, or None if none of them says.

    Callers pass ids they have already scoped to `source == "kalshi"`; the `KX`
    guard here is a second belt, not the scoping.
    """
    for external_id in kalshi_external_ids or []:
        if not external_id or not external_id.startswith("KX"):
            continue
        series = external_id.split("-", 1)[0]
        for prefix, tour in _KALSHI_SERIES_TOUR_PREFIXES:
            if series.startswith(prefix):
                return tour
    return None

TOUR_DISPLAY_NAMES = {
    "pga": "PGA Tour",
    "dp_world": "DP World Tour",
    "lpga": "LPGA Tour",
    "liv": "LIV Golf",
    "korn_ferry": "Korn Ferry Tour",
    "sunshine": "Sunshine Tour",
    "asian": "Asian Tour",
    "tgl": "TGL",
    "major": "Major",
}


# DataGolf tour codes → our tour keys
_DG_TOUR_TO_KEY = {
    "pga": "pga",
    "euro": "dp_world",
    "dp_world": "dp_world",
    "kft": "korn_ferry",
    "korn_ferry": "korn_ferry",
    "opp": "pga",         # opposite-field PGA Tour events (same week as majors)
    "alt": "dp_world",    # alternate/co-sanctioned events
    "asian": "asian",
    "asian_tour": "asian",
    "liv": "liv",
    "lpga": "lpga",
}


def _datagolf_tour_to_key(tour: str | None) -> str | None:
    """Map a DataGolf tour code or label to our public tour key."""
    if not tour:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", tour.lower()).strip("_")
    return _DG_TOUR_TO_KEY.get(normalized)


def _classify_tour(
    market_name: str,
    tournament_key: str,
    is_major: bool,
    is_womens: bool,
    market_external_ids: list[str] | None = None,
    market_metadata_tours: list[str] | None = None,
    kalshi_external_ids: list[str] | None = None,
) -> str | None:
    """Classify a tournament into a tour. Returns a tour key, or None if unknown.

    UX-P185 — this used to default to `"pga"`, which is why a DP World Tour event
    with no DataGolf coverage (the Omega European Masters, ticker
    `KXDPWORLDTOUR-OMEM26`) was badged **PGA Tour** and filed under the PGA Tour
    heading, one section away from the Husqvarna British Masters — the other DP
    World Tour event of the same week, which DataGolf did cover.

    The two additions below sit strictly INSIDE what used to be `return "pga"`, so
    no tournament that resolves to a non-PGA tour today can change: only a
    tournament that reaches the old blind default can, and it changes to its true
    tour, to `pga` on its own say-so, or to None. None degrades honestly — the card
    reads `⛳ Golf` rather than naming a tour we cannot evidence.
    """
    if is_major:
        return "major"
    if is_womens:
        return "lpga"
    for pattern, tour in _TOUR_CLASSIFICATION_PATTERNS:
        if pattern.search(market_name):
            return tour
    # Prefer DataGolf's explicit tournament tour metadata when present.
    # Some events have generic names (e.g. Hainan Open) and otherwise fall
    # through to the PGA default.
    if market_metadata_tours:
        for tour in market_metadata_tours:
            mapped = _datagolf_tour_to_key(tour)
            if mapped:
                return mapped
    # Check DataGolf external_id for authoritative tour classification
    # e.g., "datagolf:euro:123:win" → "dp_world"
    if market_external_ids:
        for eid in market_external_ids:
            if eid and eid.startswith("datagolf:"):
                parts = eid.split(":")
                if len(parts) >= 2:
                    mapped = _datagolf_tour_to_key(parts[1])
                    if mapped:
                        return mapped
    # Kalshi's own series ticker is authoritative for a Kalshi-only tournament,
    # and for most weeks of the DP World Tour it is the ONLY tour signal there is.
    ticker_tour = _kalshi_series_tour(kalshi_external_ids)
    if ticker_tour:
        return ticker_tour
    # Last resort before giving up: the title says PGA itself.
    if _PGA_NAME_FALLBACK_RE.search(market_name):
        return "pga"
    # Unknown. Say so — do not guess PGA Tour on a tournament's behalf.
    return None

# ============================================================================
# Tour event extraction — sub-group "other" into named tour events
# ============================================================================

# Known PGA Tour event name patterns to extract from market names.
# These appear in Kalshi/Polymarket market names like:
#   "Cognizant Classic in The Palm Beaches Winner?"
#   "PGA Tour: Genesis Invitational Top 5"
_TOUR_EVENT_RE = re.compile(
    r"(?:PGA\s+Tour:\s*)?"  # Optional "PGA Tour:" prefix (Polymarket)
    r"((?:"
    # Named tournaments — add new ones as they appear
    r"Cognizant\s+Classic(?:\s+in\s+The\s+Palm\s+Beaches)?"
    r"|Genesis\s+Invitational"
    r"|Arnold\s+Palmer\s+Invitational"
    r"|Honda\s+Classic"
    r"|Valspar\s+Championship"
    r"|WGC[- ].*?(?=\s+(?:Winner|Top|End|Round|Make|Playoff))"
    r"|(?:Investec\s+)?South\s+African\s+Open(?:\s+Championship)?"
    r"|Joburg\s+Open"
    r"|Kenya\s+Open"
    r"|Honda\s+LPGA\s+Thailand"
    r"|HSBC\s+Women'?s?\s+World\s+Championship"
    r"|(?:DP\s+World\s+Tour|European\s+Tour|Sunshine\s+Tour|Asian\s+Tour)[:\s]+\w[\w\s]*?(?=\s+(?:Winner|Top|End|Round))"
    r"))",
    re.I,
)

# Display names for dynamically-extracted tour events.
# Keys are the normalized form (lowered, non-alpha replaced with underscores).
_TOUR_EVENT_DISPLAY_NAMES = {
    "cognizant_classic_in_the_palm_beaches": "Cognizant Classic",
    "cognizant_classic": "Cognizant Classic",
    "investec_south_african_open_championship": "South African Open",
    "investec_south_african_open": "South African Open",
    "south_african_open_championship": "South African Open",
    "south_african_open": "South African Open",
    "honda_lpga_thailand": "Honda LPGA Thailand",
    "hsbc_women_s_world_championship": "HSBC Women's World Championship",
    "hsbc_womens_world_championship": "HSBC Women's World Championship",
}


def _extract_tour_event(market_name: str) -> str | None:
    """Extract a tour event name from a market name, or None if not a tour event."""
    m = _TOUR_EVENT_RE.search(market_name)
    if m:
        name = m.group(1).strip()
        # Clean up trailing "in The Palm Beaches" etc. for display key
        return name
    return None


# ============================================================================
# DataGolf PGA schedule cache
# ============================================================================

_golf_schedule_cache: dict = {"data": None, "ts": 0}
_GOLF_SCHEDULE_TTL = 3600  # 1 hour


# UX-P127: the schedule is the only authority `_normalize_tournament` has for folding
# two spellings of one event together (Priority 2), so an event on a tour we never
# load cannot be folded at all. Loading `pga` alone is what split the British Masters
# across two cards and what let key `liv` swallow LIV Golf Indianapolis and New York.
# Order matters: on a key collision the earlier tour wins, so PGA stays canonical.
_SCHEDULE_TOURS = ("pga", "euro", "liv")


async def _get_golf_schedule() -> list[dict]:
    """Fetch the PGA, DP World and LIV schedules from DataGolf (1-hour cache).

    Returns a list of tournament dicts with name, start/end dates, venue, status and
    the tour that supplied them. Tours are fetched independently: one tour failing
    degrades that tour's events only, and returns whatever the others gave. An empty
    list means every tour failed.
    """
    now_ts = time.time()
    if _golf_schedule_cache["data"] is not None and (now_ts - _golf_schedule_cache["ts"]) < _GOLF_SCHEDULE_TTL:
        return _golf_schedule_cache["data"]

    from app.services.datagolf_api import DataGolfAPIService

    service = DataGolfAPIService()
    result: list[dict] = []
    seen_keys: set[str] = set()
    per_tour: list[str] = []
    try:
        for tour in _SCHEDULE_TOURS:
            try:
                tournaments = await service.get_schedule(tour=tour)
            except Exception as e:
                # Isolated per tour on purpose. Before UX-P127 a single failure
                # returned [] for the whole route, so every tournament lost its dates.
                logger.warning("DataGolf %s schedule unavailable: %s", tour, e)
                continue

            added = 0
            for t in tournaments:
                if not t.event_name:
                    continue

                # Generate a stable key from the event name, stripping sponsor suffixes
                # so "Arnold Palmer Invitational Presented By Mastercard" -> "arnold_palmer_invitational"
                # This ensures keys match _SIGNATURE_EVENTS entries.
                clean_name = _SPONSOR_SUFFIX_RE.sub("", t.event_name)
                key = re.sub(r"[^a-z0-9]+", "_", clean_name.lower()).strip("_")
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)

                result.append({
                    "name": t.event_name,
                    "key": key,
                    "start_date": f"{t.start_date}T00:00:00+00:00" if t.start_date else None,
                    "end_date": f"{t.end_date}T00:00:00+00:00" if t.end_date else None,
                    "venue": t.course or "",
                    "location": t.location or "",
                    "status": t.status or "",
                    "round": str(t.current_round) if t.current_round else "",
                    "tour": tour,
                })
                added += 1
            per_tour.append(f"{tour}={added}")

        _golf_schedule_cache["data"] = result
        _golf_schedule_cache["ts"] = now_ts
        logger.info(
            "DataGolf schedule: loaded %d tournaments (%s)",
            len(result),
            ", ".join(per_tour) or "no tours available",
        )
        return result

    except Exception as e:
        logger.warning("Failed to fetch golf schedule from DataGolf: %s", e)
        return []
    finally:
        await service.close()


_strip_diacritics = _strip_diacritics_canonical


# Stopwords to strip when matching tournament names
_TOURN_STOPWORDS = {"the", "a", "at", "in", "of", "presented", "by", "pga", "tour"}


def _match_market_to_schedule(market_name: str, schedule: list[dict]) -> str | None:
    """Fuzzy-match a futures market name against DataGolf tournament names.

    Returns the DataGolf schedule key if matched, None otherwise.
    """
    if not schedule:
        return None

    # Clean market name: strip "PGA Tour:" prefix and common suffixes
    clean_market = re.sub(r"^PGA\s+Tour:\s*", "", market_name, flags=re.I)
    clean_market = re.sub(r"\s+(Winner|Top\s+\d+|End\s+of|Round\s+\d+|Make\s+Cut|Made\s+Cut)\b.*", "", clean_market, flags=re.I)
    clean_market = re.sub(r"\s*\?\s*$", "", clean_market)

    market_words = {w.lower() for w in re.findall(r"[a-z]{3,}", clean_market, re.I)} - _TOURN_STOPWORDS

    if len(market_words) < 2:
        return None

    best_match = None
    best_overlap = 0

    for entry in schedule:
        event_name = entry.get("name", "")
        # Strip "presented by X", "at X" suffixes for matching
        clean_event = re.sub(r"\s+(?:presented\s+by|at)\s+.*$", "", event_name, flags=re.I)
        event_words = {w.lower() for w in re.findall(r"[a-z]{3,}", clean_event, re.I)} - _TOURN_STOPWORDS

        if len(event_words) < 2:
            continue

        overlap = len(market_words & event_words)
        if overlap >= 2 and overlap > best_overlap:
            best_overlap = overlap
            best_match = entry.get("key")

    return best_match


def _normalize_golfer_name(name: str) -> str:
    """Normalize a golfer name for display.

    Handles DataGolf 'Last, First' format, Polymarket quoted names,
    and common prefix/suffix noise from prediction market outcomes.
    """
    name = name.strip()
    name = re.sub(r"^(Yes|No)\s*[-:]\s*", "", name, flags=re.I)
    # Strip wrapping quotes (Polymarket NegRisk format)
    name = re.sub(r'^"(.*)"$', r"\1", name)
    # Strip suffixes BEFORE comma reversal so "Love III, Davis" →
    # "Love, Davis" → "Davis Love" (not "Davis Love III, Love" order bug).
    name = re.sub(r"\s+(?:Jr|Sr|III|II|IV)\.?(?=\s*,|\s*$)", "", name, flags=re.I)
    # Convert "Last, First" to "First Last" (DataGolf format)
    # Unicode \w handles accented capitals (Højgaard, Müller, Skarsgård)
    # The first-name group uses [\w.'"-] to handle initials like "J.J." and
    # hyphenated names.
    comma_match = re.match(r"^(\w[\w'-]+),\s+([\w.]['.\w-]+.*)$", name, flags=re.UNICODE)
    if comma_match:
        name = f"{comma_match.group(2)} {comma_match.group(1)}"
    return name


# Common first-name aliases for golfer dedup across sources.
# Maps short/informal name → canonical form used in match keys.
_NAME_ALIASES: dict[str, str] = {
    "matt": "matthew",
    "mike": "michael",
    "alex": "alexander",
    "dan": "daniel",
    "bob": "robert",
    "rob": "robert",
    "will": "william",
    "bill": "william",
    "billy": "william",
    "chris": "christopher",
    "dave": "david",
    "tony": "anthony",
    "tom": "thomas",
    "tommy": "thomas",
    "rick": "richard",
    "dick": "richard",
    "nick": "nicholas",
    "ben": "benjamin",
    "sam": "samuel",
    "joe": "joseph",
    "jim": "james",
    "jimmy": "james",
    "jake": "jacob",
    "ed": "edward",
    "pat": "patrick",
    "steve": "steven",
    "charlie": "charles",
    "max": "maximilian",
    "cam": "cameron",
    # "si" omitted — conflicts with Korean names (Si Woo Kim)
    "sepp": "josef",
}


def _merge_abbreviated_golfers(golfer_data: dict[str, dict]) -> dict[str, dict]:
    """Merge abbreviated-name entries into full-name entries.

    Sportsbooks often abbreviate golfer names to "F. Lastname" while DataGolf
    and prediction markets use full names. This creates separate entries with
    different match keys (e.g., "c smith" vs "cameron smith").

    Algorithm:
    1. Group entries by last name (final token in match key)
    2. Identify abbreviated entries (1-char first part like "c") and
       initial entries (2-char first part like "ct", "jj")
    3. For each, find longer entries where the first letter matches
    4. If exactly ONE match → merge (unambiguous)
    5. If multiple matches → skip (ambiguous; DataGolf filter handles it)

    Handles three merge types:
    - "c smith" (1 char) → "cameron smith" (full name)
    - "j spaun" (1 char) → "jj spaun" (2-char initials)
    - "c pan" (1 char) → "ct pan" (2-char initials)

    Also handles _NAME_ALIASES reversals: "t finau" merges into
    "anthony finau" because "tony" (starts with 't') aliases to "anthony".
    """
    from collections import defaultdict

    # Build reverse alias map: expanded_name → set of first chars that alias to it
    # e.g., "anthony" → {"t"} (from tony→anthony), "thomas" → {"t"} (from tommy)
    _alias_first_chars: dict[str, set[str]] = {}
    for short, long in _NAME_ALIASES.items():
        _alias_first_chars.setdefault(long, set()).add(short[0])
    # Also add the canonical name's own first char
    for long_name in set(_NAME_ALIASES.values()):
        _alias_first_chars.setdefault(long_name, set()).add(long_name[0])

    def _first_chars_match(abbrev_first: str, candidate_first: str) -> bool:
        """Check if abbreviated first char(s) could match a candidate's first token."""
        # Direct first-letter match
        if candidate_first[0] == abbrev_first[0]:
            return True
        # Check alias reversals: does any alias starting with abbrev_first[0]
        # expand to candidate_first?
        possible_chars = _alias_first_chars.get(candidate_first, set())
        return abbrev_first[0] in possible_chars

    # Group by last name
    by_last: dict[str, list[str]] = defaultdict(list)
    for key in golfer_data:
        parts = key.split()
        if parts:
            by_last[parts[-1]].append(key)

    to_merge: dict[str, str] = {}  # abbreviated_key → full_key

    for last_name, keys in by_last.items():
        if len(keys) < 2:
            continue

        for key in keys:
            parts = key.split()
            first = " ".join(parts[:-1])

            # Is this an abbreviated entry? (1-char first part, all alpha)
            if not first or len(first) != 1 or not first.isalpha():
                continue

            # Find ALL longer entries where first letter could match
            candidates = [
                k for k in keys
                if k != key
                and len(k.split()[0]) > 1
                and _first_chars_match(first, k.split()[0])
            ]

            if len(candidates) == 1:
                to_merge[key] = candidates[0]

    if not to_merge:
        return golfer_data

    # Execute merges: fold abbreviated data into full-name entries
    for short_key, long_key in to_merge.items():
        if short_key not in golfer_data or long_key not in golfer_data:
            continue

        short = golfer_data[short_key]
        long = golfer_data[long_key]

        # Merge sources and probabilities
        long["sources"].update(short["sources"])
        long["probabilities"].extend(short["probabilities"])

        if short["movement_24h"] is not None and long["movement_24h"] is None:
            long["movement_24h"] = short["movement_24h"]
        if short["opening_probability"] is not None and long["opening_probability"] is None:
            long["opening_probability"] = short["opening_probability"]

        del golfer_data[short_key]
        logger.info("Golf dedup: merged '%s' into '%s'", short_key, long_key)

    return golfer_data


# Every round of a concluded tournament is over, including rounds whose own
# leader market never graded and rounds that were never played. Deliberately a
# sentinel rather than 4: the round number is parsed out of a free-text market
# name (`Round\s+(\d+)`), so it is upstream text, not a bounded enum, and a
# ceiling of 4 would quietly let a "Round 5" playoff market render live on a
# finished tournament. Terminal means terminal.
_TERMINAL_ROUND_CEILING = sys.maxsize


def _completed_round_ceiling(
    round_markets: list[tuple[str, int | None, bool]],
    tournament_settled: bool = False,
) -> int:
    """Last completed round, inferred from round-market signals (The Open 2026 p0).

    Each tuple is (kind, round_number, has_graded_winner). A round is complete
    when its LEADER market is graded (`is_winner` set on the actual leader) —
    Kalshi leaves the market status='open' (gotcha #33), so is_winner, not
    status, is the round-complete signal. Top-N projection markets never grade
    themselves, so they are settled purely by inference: every round <= this
    ceiling is over. A graded Top-N market does NOT count (only leaders mark a
    round done). Returns 0 when no round has concluded (nothing settles).

    `tournament_settled` is the TERMINAL CASE, and it is the whole of #1803.

    The inference above is **self-referential**: only round N's own leader can
    mark round N over. The Masters carries no Round 4 Leader market at all, so
    its ceiling pinned at 2 permanently and "Round 3 Leader" rendered a live
    ladder (McIlroy 80%, Young 11%) under a SETTLED banner four months after the
    tournament ended. Nothing in the inference could ever have raised it — the
    signal that would settle round 3 is precisely the signal that does not exist.

    So the terminal case does NOT come from widening the inference; widening the
    inference is how this bug got here. It comes from the tournament's
    **assigned** status, which is authoritative and was simply never consulted —
    ruling 031's assigned-beats-inferred applied to STATE rather than identity.

    UX-P069: this is the same shape as `app.utils.settledness
    .settled_under_assigned_state`, which the other five adapters now call, but over
    an `int` ceiling rather than a `bool` — so it keeps its own `max()` instead of
    being contorted into a shared boolean signature. Read that module for the
    reasoning; the monotonicity argument below is identical.

    Combined with `max()`, never a replacement, and that is load-bearing: the
    terminal case can only ever RAISE the ceiling, so consulting it makes a round
    look MORE settled and never less. A tournament genuinely in play is
    unreachable by this argument — `tournament_settled` is False there and the
    value is bit-for-bit the inference it has always been. Suppressing a round
    that is actually live is the direction that costs a reader real information,
    and monotonicity is what makes that direction structurally impossible rather
    than merely unintended.
    """
    completed = [
        rnd
        for (kind, rnd, has_winner) in round_markets
        if kind == "leader" and has_winner and isinstance(rnd, int)
    ]
    inferred = max(completed) if completed else 0
    return max(inferred, _TERMINAL_ROUND_CEILING if tournament_settled else 0)


def _round_scoped_market_complete(name: str | None, max_completed_round: int) -> bool:
    """True when a round-scoped RELATED market belongs to a round already over.

    The Open 2026 p0 follow-up. "Round 1 Scores", "Round 2 Lowest Score" and
    friends encode their round in the name; once that round is over they must not
    keep showing live odds (settled-means-settled). The round-complete signal is
    the same cross-market ceiling the round groups use (`_completed_round_ceiling`
    — highest round whose leader is graded). Tournament-wide markets with no round
    number ("Lowest Round Score") and the live/future round ("End of Round 4 …"
    while round 4 is in play) return False — only settled PAST rounds are hidden.
    """
    m = re.search(r"Round\s+(\d+)", name or "", re.I)
    if not m:
        return False
    return int(m.group(1)) <= max_completed_round


def _round_outcome_in_field(
    name: str | None, is_winner: bool, field_keys: set[str], apply_filter: bool
) -> bool:
    """Field-membership guard for a round-scoped prop outcome (The Open 2026 p0).

    Kalshi "End of Round N Leader" markets carry a ~165-name speculative candidate
    roster that includes players who are NOT in the field — past champions and
    celebrities (Tiger Woods, Phil Mickelson, John Daly, Ernie Els). Rendered
    verbatim, they appeared as live round-leader outcomes. Keep an outcome only
    when:
      * the filter is OFF (no DataGolf-authoritative field for this event — the
        golfer list IS the padded source list, so filtering would be a no-op and
        we must not risk dropping a real entrant), OR
      * it is the graded round winner (authoritative even if its name key somehow
        misses the roster — never drop a settled winner), OR
      * its name matches a field competitor (same `_match_key` the placement grid
        already uses to line Kalshi outcomes up with the DataGolf field).
    """
    if not apply_filter:
        return True
    if is_winner:
        return True
    return _match_key(name or "") in field_keys


def _match_key(name: str) -> str:
    """
    Create a matching key from a golfer name for cross-source dedup.

    Handles name variations across DataGolf, Polymarket, Kalshi, and Odds API:
    - DataGolf: "Scheffler, Scottie" → "scottie scheffler"
    - Polymarket: "Scottie Scheffler" → "scottie scheffler"
    - Kalshi: "Yes: Scottie Scheffler" → "scottie scheffler"
    - Odds API: "S. Scheffler" → "s scheffler"
    - Diacritics: "Skarsgård" → "skarsgard"
    - Aliases: "Matt Fitzpatrick" → "matthew fitzpatrick"
    - Multi-initial: "J. Spaun" (Odds API) → "jj spaun" (matches "J.J. Spaun")
    """
    clean = _normalize_golfer_name(name)
    clean = re.split(r"\s+[-\u2013]\s+|\s+for\s+", clean, maxsplit=1)[0]
    clean = _strip_diacritics(clean)
    clean = clean.lower()
    clean = re.sub(r"^the\s+", "", clean)
    clean = clean.split(":")[0].strip()
    # Remove Jr./Sr./III suffixes for matching
    clean = re.sub(r"\b(?:jr|sr|iii|ii|iv)\.?\b", "", clean)
    clean = re.sub(r"[^a-z0-9\s]", "", clean).strip()
    clean = re.sub(r"\s+", " ", clean)
    # Collapse adjacent single-letter tokens into one token.
    # "j j spaun" → "jj spaun", "c t pan" → "ct pan".
    # This handles space-separated initials from sportsbooks ("J. J. Spaun").
    parts = clean.split()
    collapsed: list[str] = []
    i = 0
    while i < len(parts):
        if len(parts[i]) == 1 and parts[i].isalpha():
            # Gather consecutive single-letter tokens
            letters = parts[i]
            while i + 1 < len(parts) and len(parts[i + 1]) == 1 and parts[i + 1].isalpha():
                i += 1
                letters += parts[i]
            collapsed.append(letters)
        else:
            collapsed.append(parts[i])
        i += 1
    parts = collapsed
    # Expand first-name aliases for cross-source dedup
    if parts and parts[0] in _NAME_ALIASES:
        parts[0] = _NAME_ALIASES[parts[0]]
    clean = " ".join(parts)
    return clean


def _normalize_tournament(
    market_name: str,
    schedule: list[dict] | None = None,
    external_id: str | None = None,
) -> str:
    """Extract tournament key from a market name. Returns 'other' if no match."""
    # #950: de-obfuscate scrambled major trademarks (e.g. Polymarket's "uptspt
    # Open") so the event merges onto the canonical major card, not an orphan.
    market_name = _fix_scrambled_major(market_name)
    # Priority 1: Hardcoded major/special patterns
    for pattern, key in _TOURNAMENT_PATTERNS:
        if pattern.search(market_name):
            if key == "the_open" and _NOT_THE_OPEN_RE.search(market_name):
                continue
            # UX-P126/F4: LEVEL + TOUR discriminators. A substring match is not a
            # claim — "British Masters" is not Augusta, and a market declaring the
            # DP World Tour is not a men's major. Falling through here sends the
            # market to Priority 2/3/4, where it earns its own key.
            if not _major_claim_allowed(key, market_name, external_id):
                continue
            # UX-P127: `liv` is a TOUR key. A market naming a scheduled LIV event
            # falls through to Priority 2, which folds every spelling of that event
            # onto one card; only tour-level questions keep the bucket.
            if key == "liv" and _names_a_scheduled_liv_event(market_name, schedule):
                continue
            return key

    # Priority 2: DataGolf schedule fuzzy match
    if schedule:
        schedule_key = _match_market_to_schedule(market_name, schedule)
        if schedule_key:
            # Guard: don't let South African/Joburg/Kenya Open
            # fuzzy-match The Open Championship schedule entry
            if "open" in schedule_key and _NOT_THE_OPEN_RE.search(market_name):
                pass  # Skip — fall through to tour event regex
            elif schedule_key == "the_open_championship":
                return "the_open"  # Canonical key for The Open
            else:
                return schedule_key

    # Priority 3: Hardcoded tour event regex
    #
    # UX-P126/F4: `_TOUR_EVENT_RE`'s generic arm stops at a lookahead on the market
    # type, so "DP World Tour: British Masters First Round Leader" came back as
    # "DP World Tour: British Masters First" — a dangling ordinal AND an unstripped
    # tour prefix, i.e. a key of its own per round. Priority 3 now gets the same
    # chrome strip Priority 4 does, so all four surfaces of one event share a key.
    tour_event = _extract_tour_event(_strip_market_chrome(market_name))
    if tour_event:
        key = _slug_tournament(_strip_market_chrome(tour_event))
        if key:
            return key

    # Priority 4: Generic tournament name extraction — strip market type
    # suffixes (" - Winner", " - Top 5 Finish", etc.) and slugify.
    # Handles DataGolf markets ("LECOM Suncoast Classic - Winner") and other
    # well-structured names that don't match hardcoded patterns.
    #
    # UX-P126/F4: the suffix list used to REQUIRE a dash for everything except a
    # bare trailing "Winner"/"Champion", so one tournament fragmented into one key
    # per market type — measured live 2026-08-24, the TOUR Championship held 13 open
    # markets across 7 keys (`tour_championship`, `..._top_5`, `..._top_10`,
    # `..._top_20`, `..._first_round_leader`, `..._second_round_leader`,
    # `..._third_round_leader`, `..._hole_in_one`) and `/api/golf` served a card
    # carrying only the 6 that happened to use dashes. The LPGA FM Championship,
    # live that same week, fragmented across all 7 of its markets and surfaced no
    # card at all. Separator-optional, and the tails Polymarket and Kalshi actually
    # write ("First Round Leader", "End of Round 1 Leader", "Top 5 Finishers",
    # "To Make the Cut", "Hole-in-One") are all named.
    key = _slug_tournament(_strip_market_chrome(market_name))
    if key and len(key) >= 3:
        return key

    return "other"


def _is_h2h_matchup(market) -> bool:
    """Check if a market is a head-to-head matchup (exactly 2 golfer outcomes summing to ~1.0)."""
    valid = [
        o for o in market.outcomes
        if o.current_probability is not None
        and o.name.strip().lower() not in (
            "yes", "no", "tie", "field", "other", "the field",
        )
    ]
    if len(valid) != 2:
        return False
    prob_sum = sum(float(o.current_probability) for o in valid)
    if prob_sum < 0.85 or prob_sum > 1.15:
        return False
    for o in valid:
        if not _match_key(o.name):
            return False
        if len(o.name.strip().split()) < 2:
            return False
    return True


async def _fetch_24h_snapshots(
    db: AsyncSession, outcome_ids: list[int], now: datetime,
) -> dict[int, float]:
    """Batch-fetch probabilities from ~24h ago for a list of outcome IDs."""
    if not outcome_ids:
        return {}

    snapshot_subq = (
        select(
            FuturesOddsSnapshot.outcome_id,
            FuturesOddsSnapshot.probability,
            sqlfunc.row_number().over(
                partition_by=FuturesOddsSnapshot.outcome_id,
                order_by=FuturesOddsSnapshot.captured_at.desc()
            ).label("rn")
        )
        .where(
            FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
            FuturesOddsSnapshot.captured_at.between(
                now - timedelta(hours=25),
                now - timedelta(hours=23),
            ),
        )
        .subquery()
    )

    snap_result = await db.execute(
        select(snapshot_subq.c.outcome_id, snapshot_subq.c.probability)
        .where(snapshot_subq.c.rn == 1)
    )
    return {row.outcome_id: float(row.probability) for row in snap_result}


# An EMPTY ORDER BOOK: nobody is quoting either side, so the best bid sits at/below
# the floor and the best ask at/above the ceiling. Its midpoint is ~0.5, and that 0.5
# is an artifact of the emptiness — not a price anyone would trade at (gotcha #19:
# "if there is no trade and no bid, skip").
EMPTY_BOOK_BID = 0.01
EMPTY_BOOK_ASK = 0.99


def _kalshi_untraded_mid(source: str | None, prob: float | None) -> bool:
    """Kalshi's untraded-midpoint sentinel — the historical rule, unchanged (#23).

    Named rather than retyped: this predicate had THREE hand-written copies in this
    module, and UX-P070 exists because two copies of a *different* golf rule drifted
    apart and the aggregation path kept the broken half (#1620, this lane's recurring
    find). One definition cannot disagree with itself.
    """
    return (source or "") == "kalshi" and prob is not None and float(prob) == 0.5


# How close a stored price has to be to its own ask to BE that ask. Matches the
# tolerance `is_fabricated_midpoint` uses for the same kind of "is this number the
# arithmetic, or a coincidence" question.
_PRICE_IS_ASK_TOLERANCE = 0.0005


def _price_is_unaccepted_offer(outcome) -> bool:
    """True when THIS outcome's printed number is a seller's offer nobody took (Q446).

    THE SPECIMEN, production 2026-08-29. `GET /api/golf` served, under PGA Tour:

        Omega European Masters   4 golfers
          Andreas Halvorsen 10%  ·  Adrian Meronk 10%
          Eddie Pepperell   10%  ·  Antoine Rozner 10%

    Four of a ~156-player field, each at an identical 10%, summing to 0.4. Behind
    every one of them: `yes_bid 0.0000 / yes_ask 0.1000`, and `last_price 0.0000`
    in every snapshot the market has ever had. Nobody has bid on any golfer in this
    tournament and nobody has ever traded one. The 10% is Kalshi's ask — the
    `_kalshi_yes_probability` ask-only arm publishing an unaccepted offer as a
    probability, which is this queue's "a number never written, something else shown
    in its place".

    PER OUTCOME, AND THAT SCOPE IS THE CERT-450 REPAIR. This rule used to be
    `_field_is_offer_sheet`, asked of the whole field and answered all-or-nothing: a
    field was refused only when NOT ONE competitor carried a bid. On the Nexo
    round-leader shape that is 137 ask-only rows laundered by the one golfer somebody
    happened to bid on — the branch even pinned the behaviour in a test called
    `test_one_real_bid_anywhere_saves_the_field`. But a bid on Rory McIlroy is not
    evidence about Adrian Meronk. Provenance belongs to the number, not to its
    neighbours, and the ship is that readers stop seeing placeholder prices — which
    137 of them plainly still were.

    The old scope was defended on the grounds that "a lone longshot at bid 0.00 /
    ask 0.02 is a normal thing for a real market to contain". It is — and its 2% is
    still a number nobody will pay a cent for. Darkening it removes a fabricated row
    from the tail; it does not remove a reading, because there was never a reading
    there. What the deep tail costs is COMPLETENESS, and the callers already present
    these fields as partial lists (`_MAX_GOLFERS`, prop top-5), so an absent tail
    reads as absent rather than as zero.

    TWO CONDITIONS, each carrying a control:

      * the printed number IS this outcome's own ask — this is what separates "no
        bid right now" from "the only number here is an offer". The CPKC Women's
        Open and FM Championship round-leader fields carry no bid on any outcome
        either, but their prices are `last_price`: real trades on a book that has
        since gone one-sided. They differ from the ask and they survive, outcome by
        outcome, exactly as they did under the field rule.
      * no bid stands behind it. NULL and 0.0000 are the same fact here and this is
        NOT the gotcha #53 hazard that makes `_is_placeholder_price` fail open on an
        absent side: the ASK is present, so this book was read. A book we read, that
        quotes an offer and reports nothing on the bid side, has no bid.

    An outcome with no ask at all cannot reach this rule, so the odds_api and
    DataGolf model fields are untouched by construction rather than by exemption.

    Renormalization is unaffected and stays conservative: `outcome_prob_sum` is taken
    over every priced outcome BEFORE any darkening, so the survivors of a thinned
    field are scaled by the full field's sum. They can only come out understated,
    never inflated — which is the direction a false number must never travel.
    """
    prob = getattr(outcome, "current_probability", None)
    if prob is None:
        return False
    ask = getattr(outcome, "current_yes_ask", None)
    if ask is None:
        return False
    if abs(float(prob) - float(ask)) >= _PRICE_IS_ASK_TOLERANCE:
        return False
    bid = getattr(outcome, "current_yes_bid", None)
    return bid is None or float(bid) <= 0


def _is_placeholder_price(outcome, source: str | None) -> bool:
    """True when this outcome's number is a placeholder rather than a quote.

    MONOTONE, and that is the whole design: the Kalshi arm is bit-for-bit the rule
    that has always run, and the empty-book arm can only ever ADD a skip. So no
    outcome that is priced today becomes unpriced unless its book is provably empty,
    and Kalshi behaviour is unchanged by construction rather than by inspection.

    FAILS OPEN on absent data. A NULL bid/ask means "we were never told", which is not
    the same fact as "nobody is quoting" (gotcha #53 — an absence is not a reading).
    DataGolf carries no book at all, so the model field is untouched.

    Why this is needed NOW: it is the safety half of the tour-prefix fix above. That
    fix ADMITS Polymarket winner markets which were being dropped wholesale, and 23 of
    the 25 open golf markets holding a 0.5 outcome hold an empty book behind it. The
    untraded skip was gated to ``source == "kalshi"``, so admitting Polymarket without
    this would have traded one wrong number for another.

    The unaccepted-offer arm (CERT-450) is the third, and it preserves the
    monotonicity above because it can only ever ADD a skip. It is where the old
    `_field_is_offer_sheet` went, and asking the question HERE rather than of the
    whole field is the entire repair: the field form could only refuse a field in
    which nobody had bid on anybody, so a single genuine quote certified every other
    competitor's ask.
    """
    prob = getattr(outcome, "current_probability", None)
    if prob is None:
        return False
    if _kalshi_untraded_mid(source, prob):
        return True
    if _price_is_unaccepted_offer(outcome):
        return True
    bid = getattr(outcome, "current_yes_bid", None)
    ask = getattr(outcome, "current_yes_ask", None)
    if bid is None or ask is None:
        return False
    return float(bid) <= EMPTY_BOOK_BID and float(ask) >= EMPTY_BOOK_ASK


def _dedup_winner_markets(tourn_key: str, tourn_markets: list) -> tuple[dict[str, int], set[int]]:
    """Per-source dedup of winner-type markets, keeping the one with most golfer outcomes.

    Returns (source_best, dedup_candidates) where source_best maps source to best market id.
    """
    source_groups: dict[str, list[tuple[int, int]]] = defaultdict(list)
    dedup_candidates: set[int] = set()

    for m in tourn_markets:
        if _NON_WINNER_MARKET_RE.search(m.name):
            continue
        src = m.source or "unknown"
        golfer_count = sum(
            1 for o in m.outcomes
            if o.current_probability is not None
            and o.name.strip().lower() not in ("tie", "field", "other", "the field")
            and not _PROP_OUTCOME_RE.search(o.name.strip())
        )
        source_groups[src].append((m.id, golfer_count))
        dedup_candidates.add(m.id)

    source_best: dict[str, int] = {}
    for src, candidates in source_groups.items():
        best_id, best_count = max(candidates, key=lambda x: x[1])
        source_best[src] = best_id
        if len(candidates) > 1:
            logger.info(
                "Golf dedup: source '%s' has %d winner markets for %s, "
                "selected market %d (%d golfer outcomes, skipping %d)",
                src, len(candidates), tourn_key, best_id, best_count,
                len(candidates) - 1,
            )

    return source_best, dedup_candidates


def _extract_prop_market(market, source_label: str) -> dict | None:
    """Extract a prop market (Top 5/10/20, Make Cut) into a response dict."""
    source = market.source or "unknown"
    # Unaccepted offers are darkened one at a time inside the loop below
    # (`_is_placeholder_price`), not refused as a field (CERT-450). A field that is
    # ALL offers loses every outcome and returns None here, exactly as the field
    # rule did; a field that is mostly offers loses only the fabricated rows.
    prop_outcomes = []
    for outcome in market.outcomes:
        if outcome.current_probability is None:
            continue
        p = float(outcome.current_probability)
        if _is_placeholder_price(outcome, source):
            continue
        raw = outcome.name.strip()
        if raw.lower() in ("tie", "field", "other", "the field"):
            continue
        prop_outcomes.append({
            "name": _normalize_golfer_name(raw),
            "probability": round(p, 3),
        })
    if not prop_outcomes:
        return None
    prop_outcomes.sort(key=lambda x: x["probability"], reverse=True)
    return {
        "name": market.name,
        "source": source_label,
        "outcomes": prop_outcomes[:5],
    }


def _extract_yes_no_prop(market, source_label: str) -> dict | None:
    """#952: surface a non-winner yes/no market as a single-probability prop.

    Markets like "U.S. Open: Playoff", "First Time Winner?", "Hole-in-One" are
    binary yes/no questions that were dropped at the <=2-outcome gate, so
    albatross/hole-in-one/playoff/first-time-winner/record-low-round never
    surfaced. Represent each as the YES probability (e.g. "Playoff: 22% Yes")
    with ``kind="binary"``; the frontend renders a single bar, not a Yes/No pair.
    """
    yes_p: float | None = None
    for o in market.outcomes:
        if o.current_probability is None:
            continue
        nm = (o.name or "").strip().lower()
        if nm == "yes":
            yes_p = float(o.current_probability)
        elif nm == "no" and yes_p is None:
            yes_p = 1.0 - float(o.current_probability)
    if yes_p is None:
        return None
    # Kalshi untraded mid (raw 0.5) is a placeholder, not a real price (#23).
    # `yes_p` may be DERIVED (1 - the "No" leg), so there is no single outcome whose
    # book could be consulted — this arm stays the magic-number rule, but shares its
    # one definition with the other two call sites.
    if _kalshi_untraded_mid(market.source, yes_p):
        return None
    return {
        "name": market.name,
        "source": source_label,
        "kind": "binary",
        "yes_probability": round(yes_p, 3),
        "outcomes": [{"name": "Yes", "probability": round(yes_p, 3)}],
    }


def _aggregate_golfer_outcome(
    outcome, source_label: str, golfer_data: dict[str, dict],
    prob_24h_ago: dict[int, float], prob_scale: float = 1.0,
) -> None:
    """Aggregate a single outcome into golfer_data, tracking sources and movement.

    `prob_scale` renormalizes independent-binary winner fields (gotcha #23, #926)
    to sum 1.0; it is applied consistently to the stored probability, the 24h
    delta, and the opening probability so movement isn't distorted.
    """
    prob = float(outcome.current_probability) * prob_scale
    raw_name = outcome.name.strip()

    if raw_name.lower() in ("tie", "field", "other", "the field"):
        return
    if _PROP_OUTCOME_RE.search(raw_name):
        return

    display_name = _normalize_golfer_name(raw_name)
    key = _match_key(raw_name)
    if not key:
        return

    if key not in golfer_data:
        golfer_data[key] = {
            "name": display_name,
            "sources": {},
            "movement_24h": None,
            "opening_probability": None,
        }

    golfer_data[key]["sources"][source_label] = round(prob, 3)

    if outcome.id in prob_24h_ago:
        delta = prob - prob_24h_ago[outcome.id] * prob_scale
        if abs(delta) >= 0.001:
            existing = golfer_data[key]["movement_24h"]
            if existing is None or abs(delta) > abs(existing):
                golfer_data[key]["movement_24h"] = round(delta, 4)

    if golfer_data[key]["movement_24h"] is None and outcome.probability_change_24h is not None:
        change = float(outcome.probability_change_24h) * prob_scale
        if abs(change) >= 0.001:
            golfer_data[key]["movement_24h"] = round(change, 4)

    if outcome.opening_probability is not None and golfer_data[key]["opening_probability"] is None:
        golfer_data[key]["opening_probability"] = round(
            float(outcome.opening_probability) * prob_scale, 3
        )


def _build_tournament_entry(
    tourn_key: str, tourn_markets: list,
    golfer_data: dict[str, dict], prop_markets_list: list[dict],
    market_ids: list[int], market_sources: list[str],
    earliest_commence, latest_resolution,
) -> dict | None:
    """Build a single tournament response dict from aggregated golfer data."""
    golfer_data = _merge_abbreviated_golfers(golfer_data)

    # Filter to invitees when DataGolf field data exists
    has_datagolf = "datagolf" in market_sources
    if has_datagolf:
        datagolf_keys = {k for k, v in golfer_data.items() if "datagolf_model" in v["sources"]}
        if datagolf_keys:
            filtered_count = len(golfer_data) - len(datagolf_keys)
            if filtered_count > 0:
                logger.info("Golf invitee filter: removed %d non-field golfers from %s", filtered_count, tourn_key)
            golfer_data = {k: v for k, v in golfer_data.items() if k in datagolf_keys}

    golfers = []
    for data in golfer_data.values():
        source_vals = list(data["sources"].values())
        avg_prob = sum(source_vals) / len(source_vals) if source_vals else 0
        golfers.append({
            "name": data["name"],
            "probability": avg_prob,
            "movement_24h": data["movement_24h"],
            "sources": data["sources"],
            "opening_probability": data["opening_probability"],
        })

    golfers.sort(key=lambda g: g["probability"], reverse=True)

    if not golfers:
        return None

    all_golfers = golfers
    for g in all_golfers:
        g["probability"] = round(g["probability"], 3)
        g["american_odds"] = probability_to_american(g["probability"])
    for i, g in enumerate(all_golfers):
        g["rank"] = i + 1

    golfers = all_golfers[:_MAX_GOLFERS]

    order_idx = TOURNAMENT_ORDER.index(tourn_key) if tourn_key in TOURNAMENT_ORDER else 50
    display_name = TOURNAMENT_DISPLAY_NAMES.get(
        tourn_key,
        _TOUR_EVENT_DISPLAY_NAMES.get(tourn_key, tourn_key.replace("_", " ").title()),
    )
    is_tour_event = tourn_key not in TOURNAMENT_ORDER and not tourn_key.startswith("other_") and tourn_key != "other"

    if tourn_key.startswith("other_"):
        display_name = tourn_markets[0].name if tourn_markets else "Other"
        display_name = re.sub(r"\s*\?\s*$", "", display_name)
        order_idx = TOURNAMENT_ORDER.index("other") if "other" in TOURNAMENT_ORDER else 99

    if is_tour_event and latest_resolution:
        order_idx = 50

    market_names = [m.name for m in tourn_markets]
    is_womens = (
        bool(_WOMENS_RE.search(display_name))
        or any(_WOMENS_RE.search(m.name) for m in tourn_markets)
    )

    tour_name_for_classify = display_name
    if tourn_markets:
        tour_name_for_classify = tourn_markets[0].name
    market_ext_ids = [m.external_id for m in tourn_markets if m.external_id]
    # Scoped to Kalshi HERE, where `source` is known — `_classify_tour` never has to
    # infer a provider from the shape of an id it was handed.
    kalshi_ext_ids = [
        m.external_id
        for m in tourn_markets
        if m.external_id and getattr(m, "source", None) == "kalshi"
    ]
    market_metadata_tours = [
        m.market_metadata.get("tour")
        for m in tourn_markets
        if m.market_metadata and m.market_metadata.get("tour")
    ]
    tour = _classify_tour(
        tour_name_for_classify, tourn_key,
        tourn_key in MAJOR_TOURNAMENTS, is_womens,
        market_external_ids=market_ext_ids,
        market_metadata_tours=market_metadata_tours,
        kalshi_external_ids=kalshi_ext_ids,
    )

    return {
        "key": tourn_key,
        "name": display_name,
        "is_major": tourn_key in MAJOR_TOURNAMENTS,
        "is_tour_event": is_tour_event,
        "is_womens": is_womens,
        "tour": tour,
        # Same shape the upcoming-schedule serializer already uses: no tour, no label.
        "tour_label": TOUR_DISPLAY_NAMES.get(tour) if tour else None,
        "order": order_idx,
        "sort_date": latest_resolution.isoformat() if is_tour_event and latest_resolution else None,
        "commence_time": earliest_commence.isoformat() if earliest_commence else None,
        "resolution_date": latest_resolution.isoformat() if latest_resolution else None,
        "market_ids": market_ids,
        "market_sources": market_sources,
        "market_names": market_names,
        "golfers": golfers,
        "prop_markets": prop_markets_list,
        "_all_golfers": all_golfers,
    }


def _route_h2h_to_tournament(
    market, golfer_to_tournaments: dict[str, set[str]],
    tourn_by_commence: list[tuple[datetime, str]], schedule: list,
) -> str | None:
    """Route a head-to-head matchup market to its tournament."""
    valid_outcomes = [
        o for o in market.outcomes
        if o.current_probability is not None
        and o.name.strip().lower() not in ("yes", "no", "tie", "field", "other", "the field")
    ]
    if len(valid_outcomes) != 2:
        return None

    a, b = valid_outcomes
    a_key = _match_key(a.name)
    b_key = _match_key(b.name)
    if not a_key or not b_key:
        return None

    a_tourns = golfer_to_tournaments.get(a_key, set())
    b_tourns = golfer_to_tournaments.get(b_key, set())
    shared = a_tourns & b_tourns

    name_key = _normalize_tournament(market.name, schedule, market.external_id)
    if name_key != "other" and _WOMENS_RE.search(market.name):
        name_key = name_key + "_womens"

    if len(shared) == 1:
        return next(iter(shared))
    if len(shared) > 1:
        return name_key if name_key in shared else next(iter(shared))

    either = a_tourns | b_tourns
    if len(either) == 1:
        return next(iter(either))
    if name_key != "other":
        return name_key

    # commence_time fallback
    if not market.commence_time:
        return None
    m_ct = market.commence_time
    best_key = None
    best_delta = timedelta(days=4)
    for ct, tk in tourn_by_commence:
        delta = abs(ct - m_ct) if ct.tzinfo else abs(ct.replace(tzinfo=timezone.utc) - m_ct)
        if delta < best_delta:
            best_delta = delta
            best_key = tk
    return best_key


def _build_h2h_entry(market, tourn_key: str) -> dict:
    """Build a single H2H matchup dict from a market."""
    valid_outcomes = [
        o for o in market.outcomes
        if o.current_probability is not None
        and o.name.strip().lower() not in ("yes", "no", "tie", "field", "other", "the field")
    ]
    a, b = valid_outcomes[0], valid_outcomes[1]
    source = market.source or "unknown"
    source_label = "datagolf_model" if source == "datagolf" else source
    a_prob = float(a.current_probability)
    b_prob = float(b.current_probability)
    if b_prob > a_prob:
        a, b = b, a
        a_prob, b_prob = b_prob, a_prob

    return {
        "market_id": market.id,
        "source": source_label,
        "golfer_a": {
            "name": _normalize_golfer_name(a.name.strip()),
            "probability": round(a_prob, 3),
        },
        "golfer_b": {
            "name": _normalize_golfer_name(b.name.strip()),
            "probability": round(b_prob, 3),
        },
    }


def _enrich_with_schedule(
    tournaments: list[dict], schedule_by_key: dict[str, dict],
) -> None:
    """Enrich tournaments with DataGolf schedule data (venue, dates, etc.)."""
    _TOURN_TO_SCHED_KEY = {
        "masters": "masters_tournament",
        "us_open": "u_s_open",
        "the_open": "the_open_championship",
        "players": "the_players_championship",
    }
    for t in tournaments:
        t["slug"] = _clean_slug(t["name"])
        sched = schedule_by_key.get(t["key"]) or schedule_by_key.get(_TOURN_TO_SCHED_KEY.get(t["key"], ""))
        if sched:
            t["venue"] = sched.get("venue") or t.get("venue") or None
            t["location"] = sched.get("location") or None
            t["schedule_status"] = sched.get("status") or None
            if sched.get("start_date"):
                t["start_date"] = sched["start_date"]
            if sched.get("end_date"):
                t["end_date"] = sched["end_date"]
                # #1077: normalize resolution_date to the DataGolf tournament
                # end_date. As shipped, resolution_date carried the Kalshi
                # close-time artifact (gotcha #14), which diverges wildly across
                # surfaces for the same tournament (The Open 2026: Kalshi Aug-2,
                # detail-header Aug-16, real dates Jul-16–19). Once a real
                # schedule end_date exists it is the ground truth, so all
                # surfaces key the same date and resolution_date stops being a
                # latent countdown/header footgun.
                t["resolution_date"] = sched["end_date"]


def _filter_stale_tournaments(tournaments: list[dict], now: datetime) -> list[dict]:
    """Remove completed or stale tournaments based on schedule/date signals."""
    now_date = now.date()
    filtered = []
    for t in tournaments:
        if t.get("schedule_status") == "completed":
            continue
        end_date_str = t.get("end_date")
        if end_date_str:
            try:
                if datetime.fromisoformat(end_date_str).date() < now_date - timedelta(days=1):
                    continue
            except (ValueError, TypeError):
                pass
        elif t.get("start_date"):
            try:
                if datetime.fromisoformat(t["start_date"]).date() < now_date - timedelta(days=7):
                    continue
            except (ValueError, TypeError):
                pass
        elif t.get("resolution_date"):
            try:
                if datetime.fromisoformat(t["resolution_date"]).date() < now_date - timedelta(days=7):
                    continue
            except (ValueError, TypeError):
                pass
        filtered.append(t)
    return filtered


# How many upcoming tournaments the golf page names. The DataGolf schedule runs to
# the end of the season, so this bounds the DISPLAY, not the data.
_MAX_UPCOMING = 10


def _upcoming_from_schedule(
    schedule: list[dict] | None,
    now: datetime,
    limit: int = _MAX_UPCOMING,
) -> list[dict]:
    """Name the tournaments that have not started yet, soonest first.

    UX-P169. This section used to be built from the `events` table filtered to
    `Sport.key ILIKE 'golf_%'`. Golf has SIX rows there in all of history, every
    one of them `closed`, and they are props and mis-ingests, not tournaments:
    "Hole-in-One vs Arnold Palmer Invitational", "U.S. Team Captain vs 2027 Ryder
    Cup", and a Philippine BASKETBALL game (Phoenix Fuel Masters vs Timplados
    Hotshots). So the section could only ever render nothing — which is what a
    reader saw — or, if one of those rows had ever been in the future, nonsense.

    The DataGolf schedule is the authority for what is coming, and it was already
    loaded here and already serialized into the same payload as `pga_schedule`.

    ⚠️ The schedule arrives GROUPED BY TOUR, not in date order. Fed through
    unsorted a reader reads Sep, Oct, Nov, Dec, then Sep again. The sort is the
    load-bearing line in this function, not a tidy-up.
    """
    if not schedule:
        return []

    dated: list[tuple[datetime, dict]] = []
    for entry in schedule:
        raw_start = entry.get("start_date")
        if not raw_start:
            continue
        try:
            start = datetime.fromisoformat(raw_start)
        except (TypeError, ValueError):
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if start <= now:
            continue
        tour_key = _datagolf_tour_to_key(entry.get("tour"))
        dated.append((
            start,
            {
                "key": entry.get("key"),
                "name": entry.get("name"),
                "start_date": entry.get("start_date"),
                "end_date": entry.get("end_date"),
                "venue": entry.get("venue") or None,
                "location": entry.get("location") or None,
                "tour": tour_key,
                "tour_label": TOUR_DISPLAY_NAMES.get(tour_key) if tour_key else None,
            },
        ))

    dated.sort(key=lambda pair: pair[0])
    return [item for _, item in dated[:limit]]


@router.get("")
async def get_golf_cached(
    db: AsyncSession = Depends(get_db),
):
    """Return golf data (Redis-cached to avoid OOM on 512MB dyno)."""
    import json as _json
    from app.tasks.redis_state import get_async_redis_client

    try:
        rc = get_async_redis_client()
        cached = await rc.get("bainluck:category:golf")
        await rc.aclose()
        if cached:
            return _json.loads(cached)
    except Exception:
        pass

    return await get_golf(db)


async def get_golf(
    db: AsyncSession = Depends(get_db),
):
    """Get golf tournament futures with aggregated odds across sources."""
    now = datetime.now(timezone.utc)

    # Query + filter golf markets
    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.status == "open",
            or_(
                FuturesMarket.external_id.ilike("golf_%"),
                FuturesMarket.llm_sport_category == "golf",
            ),
        )
    )
    result = await db.execute(query)
    markets_all = result.scalars().unique().all()
    markets_all = [m for m in markets_all if _is_golf_market(m)]
    # UX-P168. The name-side gate above cannot see a market whose title is
    # domain-neutral and whose FIELD is another sport — "Asia Masters 2026 Winner"
    # was served as a PGA Tour golf tournament over four League of Legends teams.
    # This is the only golf path that eager-loads `outcomes` (the `selectinload`
    # above), so it is the only one that can ask.
    markets_all = drop_foreign_field_markets(markets_all)

    # Split H2H matchups from winner markets
    h2h_markets_raw: list = []
    markets: list = []
    for m in markets_all:
        if _is_h2h_matchup(m):
            h2h_markets_raw.append(m)
        else:
            markets.append(m)
    logger.info(
        "Golf endpoint: %d markets after filtering (%d h2h matchups)",
        len(markets), len(h2h_markets_raw),
    )

    # 24h movement snapshots
    all_outcome_ids = []
    for market in markets:
        for outcome in market.outcomes:
            if outcome.current_probability is not None:
                all_outcome_ids.append(outcome.id)
    prob_24h_ago = await _fetch_24h_snapshots(db, all_outcome_ids, now)
    logger.info("Golf endpoint: found 24h-ago snapshots for %d/%d outcomes",
                len(prob_24h_ago), len(all_outcome_ids))

    # DataGolf schedule
    schedule = await _get_golf_schedule()
    schedule_by_key: dict[str, dict] = {}
    for s_event in schedule:
        key = s_event.get("key", "other")
        if key != "other" and key not in schedule_by_key:
            schedule_by_key[key] = s_event

    # Group markets by tournament
    tournament_markets: dict[str, list] = defaultdict(list)
    for market in markets:
        tournament_key = _normalize_tournament(market.name, schedule, market.external_id)
        if tournament_key == "other":
            tournament_markets[f"other_{market.id}"].append(market)
        else:
            if _WOMENS_RE.search(market.name):
                tournament_key = tournament_key + "_womens"
            tournament_markets[tournament_key].append(market)

    # Build tournament entries with cross-source aggregation
    tournaments = []
    for tourn_key, tourn_markets in tournament_markets.items():
        golfer_data: dict[str, dict] = {}
        prop_markets_list: list[dict] = []
        market_ids = []
        market_sources = []
        earliest_commence = None
        latest_resolution = None

        source_best, dedup_candidates = _dedup_winner_markets(tourn_key, tourn_markets)

        for market in tourn_markets:
            market_ids.append(market.id)
            market_sources.append(market.source or "unknown")
            source = market.source or "unknown"
            source_label = "datagolf_model" if source == "datagolf" else source

            if market.commence_time:
                if earliest_commence is None or market.commence_time < earliest_commence:
                    earliest_commence = market.commence_time
            if market.resolution_date:
                if latest_resolution is None or market.resolution_date > latest_resolution:
                    latest_resolution = market.resolution_date

            if market.id in dedup_candidates and market.id != source_best.get(source):
                continue

            # Per-golfer binary markets: drop the winner-field fragments, but
            # surface NON-winner yes/no questions (playoff, hole-in-one,
            # first-time winner, albatross, record-low-round) as single-prob
            # props instead of dropping them entirely (#952).
            if len(market.outcomes) <= 2:
                outcome_names = {o.name.strip().lower() for o in market.outcomes if o.name}
                if outcome_names & {"yes", "no"}:
                    if _NON_WINNER_MARKET_RE.search(market.name):
                        prop = _extract_yes_no_prop(market, source_label)
                        if prop:
                            prop_markets_list.append(prop)
                    continue

            # Skip participation/field markets (prob sum >> 1) — EXCEPT Kalshi
            # tournament-WINNER fields, which are independent per-golfer binaries
            # that also sum >100% (gotcha #23); those get renormalized to a real
            # field instead of dropped (#926). Markets summing <=1.5 are unchanged.
            outcome_prob_sum = sum(
                float(o.current_probability)
                for o in market.outcomes
                if o.current_probability is not None
            )
            renorm_factor = _golf_winner_renorm_factor(
                market.name, len(market.outcomes), outcome_prob_sum
            )
            if renorm_factor is None:
                continue

            # Non-winner markets go to props
            if _NON_WINNER_MARKET_RE.search(market.name):
                prop = _extract_prop_market(market, source_label)
                if prop:
                    prop_markets_list.append(prop)
                continue

            # Aggregate winner outcomes
            withheld = 0
            for outcome in market.outcomes:
                if outcome.current_probability is None:
                    continue
                # Skip placeholder prices before any renormalization — an untraded
                # Kalshi mid, any source's empty book (UX-P070), or a price that is
                # merely this outcome's own unaccepted ask (CERT-450). Note that
                # `renorm_factor` was computed over the FULL priced field above, so a
                # thinned field's survivors are scaled by the whole field's sum and
                # can only come out understated. That is deliberate: renormalizing to
                # the survivors instead would turn four identical 10% offers into
                # four identical 25% "forecasts" — the same non-information wearing a
                # more confident number.
                if _is_placeholder_price(outcome, source):
                    withheld += 1
                    continue
                _aggregate_golfer_outcome(
                    outcome, source_label, golfer_data, prob_24h_ago,
                    prob_scale=renorm_factor,
                )
            if withheld:
                logger.debug(
                    "Golf: withheld %d placeholder-priced outcome(s) from field '%s' "
                    "(market %s)",
                    withheld, market.name, getattr(market, "id", None),
                )

        entry = _build_tournament_entry(
            tourn_key, tourn_markets, golfer_data, prop_markets_list,
            market_ids, market_sources, earliest_commence, latest_resolution,
        )
        if entry:
            tournaments.append(entry)

    # Route H2H matchups to tournaments
    golfer_to_tournaments: dict[str, set[str]] = defaultdict(set)
    for t in tournaments:
        for g in t.get("_all_golfers", t.get("golfers", [])):
            k = _match_key(g["name"])
            if k:
                golfer_to_tournaments[k].add(t["key"])

    tourn_by_commence: list[tuple[datetime, str]] = []
    for t in tournaments:
        ct_str = t.get("commence_time")
        if ct_str:
            try:
                tourn_by_commence.append((datetime.fromisoformat(ct_str), t["key"]))
            except (ValueError, TypeError):
                pass

    h2h_by_tournament: dict[str, list[dict]] = defaultdict(list)
    h2h_unrouted = 0
    for market in h2h_markets_raw:
        tourn_key = _route_h2h_to_tournament(
            market, golfer_to_tournaments, tourn_by_commence, schedule,
        )
        if not tourn_key:
            h2h_unrouted += 1
            continue
        h2h_by_tournament[tourn_key].append(_build_h2h_entry(market, tourn_key))

    if h2h_unrouted:
        logger.info("Golf h2h: %d matchups unrouted (no matching tournament)", h2h_unrouted)

    # Attach and dedupe H2H matchups
    for t in tournaments:
        raw_matchups = h2h_by_tournament.get(t["key"], [])
        seen_pairs: set[tuple[str, str]] = set()
        deduped: list[dict] = []
        for m in raw_matchups:
            key = tuple(sorted([
                _match_key(m["golfer_a"]["name"]) or m["golfer_a"]["name"].lower(),
                _match_key(m["golfer_b"]["name"]) or m["golfer_b"]["name"].lower(),
            ]))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            deduped.append(m)
        deduped.sort(key=lambda m: abs(m["golfer_a"]["probability"] - m["golfer_b"]["probability"]))
        t["h2h_matchups"] = deduped

    # Sort and clean up
    tournaments.sort(key=lambda t: (t["order"], t.get("sort_date") or "9999"))
    for t in tournaments:
        del t["order"]
        t.pop("sort_date", None)

    # Enrich + filter
    _enrich_with_schedule(tournaments, schedule_by_key)
    tournaments = _filter_stale_tournaments(tournaments, now)

    # Biggest movers
    all_movers = []
    for tourn in tournaments:
        for g in tourn["golfers"]:
            if g["movement_24h"] is not None and abs(g["movement_24h"]) >= 0.005:
                all_movers.append({
                    "name": g["name"],
                    "tournament_key": tourn["key"],
                    "tournament_name": tourn["name"],
                    "movement_24h": g["movement_24h"],
                    "probability": g["probability"],
                })
    all_movers.sort(key=lambda m: abs(m["movement_24h"]), reverse=True)
    biggest_movers = all_movers[:5]

    # Upcoming tournaments — the DataGolf schedule, not the `events` table.
    # See `_upcoming_from_schedule` for why the old source could never work.
    upcoming_events = _upcoming_from_schedule(schedule, now)

    current_event = _find_current_event(tournaments, schedule_by_key, now)

    return {
        "tournaments": tournaments,
        "biggest_movers": biggest_movers,
        "upcoming_events": upcoming_events,
        "current_event": current_event,
        "total_tournaments": len(tournaments),
        "total_golfers": sum(len(t["golfers"]) for t in tournaments),
        "pga_schedule": schedule if schedule else None,
    }


def _tournament_importance(key: str) -> int:
    """Return importance tier for a tournament key. Higher = more important."""
    if key in MAJOR_TOURNAMENTS:
        return 3
    if key in _SIGNATURE_EVENTS:
        return 2
    # Safety net: strip sponsor suffixes that may remain in the key
    # e.g. "arnold_palmer_invitational_presented_by_mastercard" -> check without suffix
    clean_key = re.sub(r"_(?:presented|sponsored|hosted|powered)_by_.*$", "", key)
    if clean_key != key and clean_key in _SIGNATURE_EVENTS:
        return 2
    return 1


def _find_current_event(
    tournaments: list[dict],
    schedule_by_key: dict[str, dict],
    now: datetime,
) -> dict | None:
    """Find the current tour event using DataGolf dates with fallback heuristics.

    Priority order:
    1. DataGolf schedule: event whose start_date <= now <= end_date (prefer most important)
    2. DataGolf schedule: nearest upcoming event (start_date > now, within 7 days, prefer most important)
    3. Fallback: tour event closest to now, weighted by importance + activity
    """
    # Majors are NOT flagged is_tour_event (they sit in TOURNAMENT_ORDER), yet they
    # must be eligible for the marquee slot so an imminent/in-progress major wins the
    # current_event over minor qualifiers (e.g. The Open Championship over "The Open
    # Last Chance Qualifier"). Schedule-date priority (Phase 1) and the >6-days-ago
    # commence filter (Phase 2) still keep a finished major from displacing the true
    # current event, and _tournament_importance ranks a live major above any tour
    # event when both qualify. (#1075)
    tour_events = [t for t in tournaments if t.get("is_tour_event") or t.get("is_major")]
    if not tour_events:
        return None

    now_str = now.isoformat()

    # Phase 1: Use DataGolf schedule dates if available
    if schedule_by_key:
        # Find events currently in progress — collect all, pick most important
        in_progress = []
        for t in tour_events:
            sched = schedule_by_key.get(t["key"])
            if not sched:
                continue
            start = sched.get("start_date")
            end = sched.get("end_date")
            if start and end and start <= now_str <= end:
                in_progress.append(t)

        if in_progress:
            in_progress.sort(key=lambda t: -_tournament_importance(t["key"]))
            return _build_current_event(in_progress[0])

        # Find nearest upcoming events — collect all in nearest date, pick most important
        upcoming_by_start: dict[str, list[dict]] = defaultdict(list)
        for t in tour_events:
            sched = schedule_by_key.get(t["key"])
            if not sched:
                continue
            start = sched.get("start_date")
            if start and start > now_str:
                try:
                    start_dt = datetime.fromisoformat(start)
                    if (start_dt - now).days <= 7:
                        upcoming_by_start[start].append(t)
                except (ValueError, TypeError):
                    continue

        if upcoming_by_start:
            # Get the nearest start date group
            nearest_start = min(upcoming_by_start.keys())
            nearest_group = upcoming_by_start[nearest_start]
            nearest_group.sort(key=lambda t: -_tournament_importance(t["key"]))
            return _build_current_event(nearest_group[0])

    # Phase 2: Fallback — pick the tour event closest to "right now".
    # Primary signal: commence_time proximity to now (nearest current/upcoming wins).
    # Secondary: odds movement (active events have more movement).
    # Tertiary: source count as tiebreaker.
    candidates = []
    for t in tour_events:
        # Use commence_time to determine relevance
        commence_str = t.get("commence_time")
        resolution_str = t.get("resolution_date")

        # Need at least one date signal
        if not commence_str and not resolution_str:
            continue

        # Filter out events that ended >7 days ago based on commence_time
        # (resolution_date can be misleading — Kalshi markets resolve weeks after
        # tournaments end, so a finished tournament might have a far-future resolution_date)
        if commence_str:
            try:
                commence_dt = datetime.fromisoformat(commence_str)
                # Golf tournaments are ~4 days. Skip if commenced >6 days ago.
                if commence_dt < now - timedelta(days=6):
                    continue
            except (ValueError, TypeError):
                pass

        # Compute proximity to now (lower = better)
        proximity_days = 999.0
        if commence_str:
            try:
                commence_dt = datetime.fromisoformat(commence_str)
                proximity_days = abs((now - commence_dt).total_seconds()) / 86400
            except (ValueError, TypeError):
                pass

        # Movement signals: how many golfers moved + total movement magnitude
        movers = sum(
            1 for g in t["golfers"]
            if g.get("movement_24h") is not None and abs(g["movement_24h"]) >= 0.005
        )
        total_movement = sum(
            abs(g["movement_24h"]) for g in t["golfers"]
            if g.get("movement_24h") is not None
        )
        total_sources = sum(len(g.get("sources", {})) for g in t["golfers"])
        importance = _tournament_importance(t["key"])
        candidates.append((t, importance, movers, total_movement, total_sources, proximity_days))

    if candidates:
        # Sort by: importance desc, proximity asc, movers desc, total_movement desc, sources desc
        candidates.sort(key=lambda c: (-c[1], c[5], -c[2], -c[3], -c[4]))
        return _build_current_event(candidates[0][0])

    return None


def _build_current_event(t: dict) -> dict:
    """Build the current_event response dict from a tournament.

    Sorts market_ids so DataGolf Winner markets appear first, then other Winner
    markets, then remaining. DataGolf markets give best progression results
    (exact prefix-based sibling discovery via Method 1).
    """
    raw_ids = t.get("market_ids", [])
    raw_names = t.get("market_names", [])
    raw_sources = t.get("market_sources", [])

    # Build triples: (id, name, source)
    if len(raw_ids) == len(raw_names) == len(raw_sources):
        triples = list(zip(raw_ids, raw_names, raw_sources))
    elif len(raw_ids) == len(raw_names):
        triples = [(mid, nm, "") for mid, nm in zip(raw_ids, raw_names)]
    else:
        triples = [(mid, "", "") for mid in raw_ids]

    def _sort_key(triple):
        _id, name, source = triple
        name_lower = name.lower()
        is_winner = "winner" in name_lower and "round" not in name_lower
        is_datagolf = source == "datagolf"
        # DataGolf Winner = 0, Other Winner = 1, DataGolf Non-Winner = 2, Rest = 3
        if is_winner and is_datagolf:
            return (0, _id)
        elif is_winner:
            return (1, _id)
        elif is_datagolf:
            return (2, _id)
        return (3, _id)

    triples.sort(key=_sort_key)
    sorted_ids = [t[0] for t in triples]
    sorted_names = [t[1] for t in triples]

    return {
        "key": t["key"],
        "name": t["name"],
        "slug": _clean_slug(t["name"]),
        "resolution_date": t.get("resolution_date"),
        "start_date": t.get("start_date"),
        "end_date": t.get("end_date"),
        "venue": t.get("venue"),
        "golfer_count": len(t["golfers"]),
        "leader": t["golfers"][0]["name"] if t["golfers"] else None,
        "leader_probability": t["golfers"][0]["probability"] if t["golfers"] else None,
        "top_golfers": t["golfers"][:5],
        "market_ids": sorted_ids,
        "market_names": sorted_names,
    }


# ============================================================================
# Tournament detail page
# ============================================================================

# Market type detection patterns for sub-grouping.
# ORDER MATTERS — checked top-to-bottom, first match wins.
_MARKET_TYPE_PATTERNS = [
    (re.compile(r"\b(?:Winner|Champion)\b(?!.*Round)", re.I), "winner", "Winner"),
    # #951: "Round N Top M Finishers" must be caught BEFORE the bare Top-N
    # patterns — otherwise "Round 2 Top 5 Finishers" classifies as tournament
    # "top_5" and gets AVERAGED into the tournament Top-5 grid column
    # (data corruption). Round-specific Top-N is its own type, excluded from the
    # tournament placement columns (a dedicated rounds panel is a follow-up).
    (re.compile(r"\bRound\s+\d+\s+Top\s+\d+\b", re.I), "round_top", "Round Top N"),
    (re.compile(r"\bTop\s+5\b", re.I), "top_5", "Top 5"),
    (re.compile(r"\bTop\s+10\b", re.I), "top_10", "Top 10"),
    (re.compile(r"\bTop\s+20\b", re.I), "top_20", "Top 20"),
    # Alex's ruling (The Open 2026): every per-golfer placement market becomes a
    # column in the ONE golfer grid — "Top 40 Finishers" (Kalshi, 150+ outcomes)
    # was classifying "other" and rendering as a wall of numbers in Related
    # Futures instead of a fused per-golfer column.
    (re.compile(r"\bTop\s+40\b", re.I), "top_40", "Top 40"),
    (re.compile(r"\bMa[dk]e\s+(?:the\s+)?Cut\b", re.I), "make_cut", "Make Cut"),
    (re.compile(r"\bRound\s+\d+\s+Leader\b", re.I), "round_leader", "Round Leader"),
]


def _detect_market_type(market_name: str) -> tuple[str, str]:
    """Detect the market type from a market name. Returns (type_key, label)."""
    for pattern, type_key, label in _MARKET_TYPE_PATTERNS:
        if pattern.search(market_name):
            return type_key, label
    return "other", "Other"


# L2-89: "Winner"-named markets that are NOT the tournament's golfer winner field.
# "The Open: Last-Chance Qualifier Winner" is a separate qualifying field (15
# golfers who never make the main grid); nationality/continent/etc. props are
# caught by _NON_CONTENDER_WINNER_RE. Both classify as type "winner" (they contain
# "Winner") but must not pollute the winner group/evolution chart.
_QUALIFIER_WINNER_RE = re.compile(r"\bqualif(?:y|ier|ying|ication|iers)\b", re.I)


def _tournament_market_type(market_name: str) -> tuple[str, str]:
    """Market type for the tournament DETAIL grouping.

    Wraps _detect_market_type but DOWN-CLASSIFIES a "winner" market that is not the
    real golfer winner field — nationality/continent/country-of-winner props (#955)
    and last-chance *qualifier* fields (L2-89) — into "other" so they surface in
    Related Futures instead of vanishing. Previously they were filtered out of the
    golfer grid + evolution chart (#955) but never routed anywhere, so the whole
    family was invisible on the event page.
    """
    type_key, label = _detect_market_type(market_name or "")
    if type_key == "winner" and (
        _NON_CONTENDER_WINNER_RE.search(market_name or "")
        or _QUALIFIER_WINNER_RE.search(market_name or "")
    ):
        return "other", "Other"
    return type_key, label


_PLAYOFF_RE = re.compile(r"\bplayoff\b", re.I)

# Source preference when collapsing cross-source duplicate "other" markets into
# one card (#956): DataGolf model first, then the deepest liquidity.
_RELATED_SOURCE_PRIORITY = {"datagolf": 0, "polymarket": 1, "kalshi": 2, "odds_api": 3}


def _related_dedup_key(market_name: str) -> str:
    """Group key for collapsing cross-source duplicate 'other' markets (#956).

    Two source markets asking the same real-world question render as two stacked
    cards with conflicting probabilities (Polymarket "Will there be a playoff..."
    27% vs Kalshi "U.S. Open: Playoff" 22%). Their normalized question text does
    NOT match, so a tournament playoff is keyed explicitly; everything else falls
    back to the normalized question (collapses only exact cross-source dupes, not
    the distinct multi-winner family — that stays a separate work item).
    """
    from app.utils.cross_source_matching import normalize_question

    if _PLAYOFF_RE.search(market_name or ""):
        return "playoff"
    return normalize_question(market_name or "")


def _prefer_datagolf_merge(
    existing: float | None,
    existing_is_dg: bool,
    incoming: float,
    incoming_is_dg: bool,
) -> tuple[float, bool]:
    """Combine two probabilities for the same (golfer, placement type), preferring
    DataGolf over one-sided Polymarket/Kalshi placeholders (#954).

    DataGolf is the authoritative in-play model. A blind cross-source average
    blended DataGolf's well-differentiated make_cut (Scheffler 0.85, Puig 0.40)
    with the compressed ~0.5 "To Make the Cut" placeholder markets, flattening
    Bubble Watch to ~50% for everyone. Rules: DataGolf wins over non-DataGolf;
    two same-class values average (preserving prior behavior).

    Returns (value, is_datagolf).
    """
    if existing is None:
        return incoming, incoming_is_dg
    if existing_is_dg and not incoming_is_dg:
        return existing, True              # keep DataGolf, drop placeholder
    if incoming_is_dg and not existing_is_dg:
        return incoming, True              # DataGolf overrides placeholder
    return (existing + incoming) / 2, existing_is_dg  # same source class → average


def _settled_outcome_signal(outcome) -> float | None:
    """Best pre-settlement probability for ordering a settled winner field: live
    price → closing (calibration) line → opening line. Settled winner markets
    carry current_probability=None (gotcha #33), so the closing/opening line is
    the only surviving ordering signal."""
    for v in (
        outcome.current_probability,
        getattr(outcome, "calibration_probability", None),
        outcome.opening_probability,
    ):
        if v is not None:
            return float(v)
    return None


def _assemble_completed_winner_field(
    tournament_markets: list,
) -> tuple[list[dict], list[int], list[str], list[str]]:
    """Assemble the winner field for a SETTLED tournament (#225 Items 1 & 2).

    Returns (golfers, market_ids, market_names, market_sources). Pure over a list
    of market objects (each with .id/.name/.source/.outcomes; each outcome with
    .name/.current_probability/.calibration_probability/.opening_probability/
    .current_american_odds/.is_winner) so it is unit-testable without a DB.

    The prior settled builder pooled EVERY market type — winner, make-cut, top-N,
    round-leader — into one name-keyed map (first-market-wins) using raw
    current_probability. Settled placement markets resolve YES≈0.99 for the whole
    made-cut field (gotcha #33: Kalshi stays status='open' with stale prices), so
    the winner field read as a wall of 0.990000 and the champion could never be
    named (the "R2: Åberg under 69.5" hero Alex flagged). Fixes:
      * FIELD from winner-type markets only (never placement/round/props, never
        nationality/first-time/qualifier props down-classified to "other");
      * champion crowned from is_winner (settled-means-settled — authoritative even
        when the price is stale/None), ordered first;
      * restrict to the authoritative DataGolf field so speculative Kalshi-only
        names for players who never entered (the Tiger-Woods class) drop out.
    """
    market_ids: list[int] = []
    market_names: list[str] = []
    market_sources: list[str] = []
    for market in tournament_markets:
        market_ids.append(market.id)
        market_names.append(market.name or "")
        src = market.source or "sportsbook"
        if src not in market_sources:
            market_sources.append(src)

    def _collect(winner_only: bool) -> dict[str, dict]:
        gmap: dict[str, dict] = {}
        for market in tournament_markets:
            src = market.source or "sportsbook"
            # #1625: a market naming a non-golf domain never contributes a golfer,
            # however well its title overlaps the tournament name. "Norway Chess
            # Masters" and "PBA Basketball Masters" both matched `masters`.
            if is_foreign_domain(market.name):
                continue
            if winner_only and _tournament_market_type(market.name or "")[0] != "winner":
                continue
            for outcome in market.outcomes:
                if not outcome.name:
                    continue
                name = outcome.name.strip()
                # #1625: the old guard listed only yes/no/over/under/draw, so a
                # tour or a country could be crowned CHAMPION — the observed
                # "The Masters winner: PGA Tour". `is_prop_outcome` is the same
                # set the membership corpus grades against.
                if is_prop_outcome(name) or is_foreign_domain(name):
                    continue
                prob = _settled_outcome_signal(outcome)
                if not winner_only and prob is None:
                    continue  # legacy fallback keeps the old "has a price" guard
                if name not in gmap:
                    gmap[name] = {
                        "name": name,
                        "probability": prob,
                        "american_odds": outcome.current_american_odds,
                        "movement_24h": None,
                        "opening_probability": outcome.opening_probability,
                        "rank": 0,
                        "sources": {},
                        "won": False,
                    }
                elif gmap[name]["probability"] is None and prob is not None:
                    gmap[name]["probability"] = prob
                if prob is not None:
                    gmap[name]["sources"][src] = prob
                if outcome.is_winner:
                    gmap[name]["won"] = True
                    gmap[name]["is_winner"] = True
        return gmap

    golfer_map = _collect(winner_only=True)
    # Never regress to an empty field: an odd tournament with only placement
    # markets still open falls back to the legacy all-market behavior.
    if not golfer_map:
        golfer_map = _collect(winner_only=False)

    # Restrict to the authoritative DataGolf field when present (mirrors the live
    # invitee filter).
    #
    # #1625 — THE GRADE NO LONGER BYPASSES THE FIELD. This read
    # `if k in dg_field or v.get("won")`, so a graded winner was kept even when it
    # sat outside the authoritative field. That is the inversion the membership
    # corpus names `GRADE_CANNOT_OVERRIDE_MEMBERSHIP`: `is_winner` says who won a
    # market, never that the market belongs to this tournament, so it cannot clear
    # a membership failure. A champion outside the field means the field or the
    # linkage is wrong, and crowning them hides exactly that.
    dg_field = {k for k, v in golfer_map.items() if "datagolf" in v.get("sources", {})}
    if len(dg_field) >= 20:
        golfer_map = {k: v for k, v in golfer_map.items() if k in dg_field}

    # Champion(s) first, then pre-settlement probability desc, then name — a
    # longshot winner is crowned above the field's higher-priced favorites. The
    # sort runs on the PRE-settlement price so the runner-up favorites still order
    # near the top; only the displayed number is frozen below.
    golfers = sorted(
        golfer_map.values(),
        key=lambda g: (0 if g.get("won") else 1, -(g.get("probability") or 0.0), g["name"]),
    )

    # Settled-means-settled (#229): once a champion is graded, FREEZE the displayed
    # field — champion 1.0, everyone else 0.0. Kalshi settled winner markets stay
    # status='open' (gotcha #33), so the winner-market polling keeps re-polluting
    # FuturesOutcome.current_probability; without this freeze the crowned champion
    # displays a stale live longshot price BELOW the field (Ryan Fox 0.004 vs the
    # field's 0.089 — the settled-concept sentinel check-A RED, #228/#229) and the
    # evolution history re-anchors to it (_reconcile_history_to_blend). The freeze
    # only fires when a champion is known — during the settle-in-reality →
    # settle-in-DB window (is_winner not yet graded) the live pre-settlement prices
    # stand, since there is nothing better to show. Matches the soccer/WC settled
    # field (event_soccer._apply_settled_crown: champion 1.0, eliminated 0.0).
    if any(g.get("won") for g in golfers):
        for g in golfers:
            g["probability"] = 1.0 if g.get("won") else 0.0

    for i, g in enumerate(golfers):
        g["rank"] = i + 1
    return golfers, market_ids, market_names, market_sources


async def _build_completed_tournament(
    slug: str,
    db: AsyncSession,
    golf_data: dict | None = None,
) -> dict | None:
    """Build tournament data from closed/resolved markets for completed tournaments.

    Called when the main golf listing doesn't include the tournament (markets closed).
    Returns a tournament dict compatible with get_golf_tournament's expectations, or None.

    ``golf_data`` is the golf listing the CALLER already holds. It is used for one
    thing — reading ``pga_schedule`` — and passing it in is what stops this function
    from rebuilding that entire listing a second time inside the same request
    (LAT-P186). It stays optional so the function is still usable, and testable,
    on its own; when it is omitted the cached listing is fetched here instead.
    """
    # LAT-P014/#1107: match on a NARROW projection, then hydrate only the matches.
    #
    # This used to be `select(FuturesMarket).options(selectinload(outcomes))` with
    # no status, date or row bound — i.e. it loaded EVERY golf market that has ever
    # existed, with every outcome eager-loaded (`futures_outcomes` is 3.2M rows and
    # a golf winner market carries the entire field), and then matched the slug in
    # Python. It runs on every miss of the live listing and its result is never
    # cached, so each request paid the whole corpus.
    #
    # MEASURED in production 2026-08-09, paired against an `event:ufc:26aug12`
    # control on the same route 4-5s away. All four golf majors resolve through
    # this function, and all four were failing:
    #     event:golf:the-open-championship   503 @ 30,286 / 30,268 / 30,279 ms
    #     event:golf:pga-championship        503 @ 30,263 ms
    #     event:golf:u-s-open                503 @ 30,269 ms
    #     event:golf:the-masters             200 @ 17,598 ms, then 503 @ 30,279 ms
    #     control                            290-1,783 ms throughout
    # 30.3s is Heroku's H12 boundary, not a coincidence. Search offers these pages
    # (`/api/events/search?q=the open` returns the concept key) and #1063 documents
    # golf majors as "guaranteed never-dead", so this was a live broken promise.
    #
    # Isolation, via an internal control on the same route: a bad CYCLING key 404s
    # in 290ms because `CyclingEventAdapter` proves absence with an in-memory config
    # parse, while a bad GOLF key took 6,931-14,518ms. Same route, same outcome —
    # the difference is only how much work runs before giving up.
    #
    # Phase 1 selects exactly the columns the match reads (`_is_golf_market` uses
    # source/external_id/name; the slug test uses name) and NO outcomes. Phase 2
    # re-selects the matched ids WITH outcomes. Set-identical by construction: the
    # same rows are chosen by the same Python predicate, and phase 2 is a subset
    # keyed by id.
    #
    # LAT-P058/#1866: phase 1 WAS the database's #1 physical-read consumer (533.7
    # GB/day, 19% of all reads) because the `OR` had no index to use. Two partial
    # indexes fixed that — 516.7 -> 2.395 MB per call, ~2,900 -> ~18 ms warm. The
    # `UNION` rewrite that was going to fix it instead measured 4.79x SLOWER and was
    # refused and deleted (ruling 076, #1917). See `golf_identity_select`'s module
    # comment. Phase 2, not this line, is what remains of this route's cost.
    ident_rows = (await db.execute(golf_identity_select())).all()

    # Group by normalized tournament key using existing logic
    matched_ids: list[int] = []
    matched_key = None
    for m in ident_rows:
        if not _is_golf_market(m):
            continue
        market_name = m.name or ""
        key = _normalize_tournament(market_name, None, getattr(m, "external_id", None))
        # Check slug against both the display name and the raw key
        display = TOURNAMENT_DISPLAY_NAMES.get(key, key.replace("_", " ").title())
        display_slug = _clean_slug(display)
        key_slug = _clean_slug(key.replace("_", " "))
        if display_slug == slug or key_slug == slug:
            matched_ids.append(m.id)
            if not matched_key:
                matched_key = key

    if not matched_ids:
        return None

    hydrated = {
        m.id: m
        for m in (
            await db.execute(
                select(FuturesMarket)
                .options(selectinload(FuturesMarket.outcomes))
                .where(FuturesMarket.id.in_(matched_ids))
            )
        ).scalars().unique().all()
    }
    # Preserve the order phase 1 matched in, so `_assemble_completed_winner_field`
    # sees exactly the sequence the single-query version handed it. Neither query
    # carries an ORDER BY, so re-ordering by the id list is the only way the two
    # phases are guaranteed to agree.
    tournament_markets: list[FuturesMarket] = [
        hydrated[i] for i in matched_ids if i in hydrated
    ]

    if not tournament_markets:
        return None

    # Derive display name from the tournament key
    display_name = TOURNAMENT_DISPLAY_NAMES.get(matched_key or "", (matched_key or slug).replace("_", " ").title())
    key = matched_key or slug

    # Build the settled WINNER FIELD (#225 Items 1 & 2). Pure assembly extracted to
    # _assemble_completed_winner_field so the champion-crown + field-purge logic is
    # unit-tested independently of the DB.
    golfers, market_ids, market_names, market_sources = _assemble_completed_winner_field(
        tournament_markets
    )

    # Try to find schedule data from the golf listing. LAT-P186: this comment said
    # "already cached" and then called the UNCACHED `get_golf()`, so a completed
    # tournament paid the full listing rebuild TWICE per request — once in
    # `get_golf_tournament` to discover the slug was absent, and again here to read
    # a single key off the result. The caller now hands its copy down; the cached
    # read is only reached when this function is called directly.
    start_date = None
    end_date = None
    venue = None
    schedule_status = None
    try:
        if golf_data is None:
            golf_data = await get_golf_cached(db=db)
        schedule = golf_data.get("pga_schedule", [])
        for event in schedule:
            # Match by multiple strategies: display name slug, key slug, or
            # normalized tournament key matching
            event_name = event.get("name", "")
            event_key = event.get("key", "")
            event_name_slug = _clean_slug(event_name)
            event_key_slug = _clean_slug(event_key.replace("_", " "))
            norm_key = _normalize_tournament(event_name)
            norm_display = TOURNAMENT_DISPLAY_NAMES.get(norm_key, "")
            norm_slug = _clean_slug(norm_display) if norm_display else ""

            if slug in (event_name_slug, event_key_slug, norm_slug):
                start_date = event.get("start_date")
                end_date = event.get("end_date")
                venue = event.get("venue") or event.get("course")
                schedule_status = event.get("status")
                break
    except Exception:
        pass

    return {
        "name": display_name,
        "slug": slug,
        "key": key,
        # A key is a major only when it IS one — `"masters" in key` also said yes to
        # `husqvarna_british_masters_...`, the same substring bug as the fold key.
        "is_major": key.removesuffix("_womens") in MAJOR_TOURNAMENTS,
        "is_womens": bool(_WOMENS_RE.search(display_name)),
        "start_date": start_date,
        "end_date": end_date,
        "venue": venue,
        "location": None,
        "schedule_status": schedule_status,
        "commence_time": start_date,
        "resolution_date": end_date,
        "golfers": golfers,
        "market_ids": market_ids,
        "market_names": market_names,
        # #225 Item 2: carry the settled tournament's sources so the round-leader
        # field-membership filter (apply_field_filter) activates — otherwise it
        # defaults off and Kalshi's speculative round-leader roster (Tiger Woods
        # et al., who never entered) surfaces on completed rounds.
        "market_sources": market_sources,
        "_all_golfers": golfers,
    }


@router.get("/tournaments/{slug}")
async def get_golf_tournament(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed tournament data for a specific golf tournament."""
    # LAT-P186/#1107: this said "reuse get_golf() for its caching" and called the
    # UNCACHED function. The caching lives in `get_golf_cached()` — its sibling
    # thirty lines up, which is what `GET /api/golf` is wired to. So the golf
    # landing page read Redis in ~45 ms while this route rebuilt the entire golf
    # listing from scratch on every single request, and `_build_completed_tournament`
    # (whose own comment also said "already cached") rebuilt it a SECOND time in the
    # same request to read one field off it.
    #
    # MEASURED on production 2026-09-01, `x-timing-split`, median of 5:
    #     /api/golf/tournaments/us-open       2,076 ms wall   1,556 ms app   q=19
    #     /api/golf/tournaments/the-masters   1,795 ms wall   1,391 ms app   q=18
    #     /api/golf            (cached)          45 ms wall       0 ms db    q=0
    # `app` dominates every slug because the rebuild is mostly Python over every
    # open golf market's eagerly-loaded outcomes, plus up to three DataGolf schedule
    # fetches — none of which this route needs freshly built.
    #
    # Serving the cached listing is a FRESHNESS change and it was sized, not assumed:
    #   - `/api/golf` and the Discover feed's golf base ALREADY serve exactly this
    #     payload, so the detail page was the one surface that disagreed with them.
    #   - Snapshot cadence for the currently-open golf markets is ~8 distinct hours
    #     out of 26, with 4-6 hour gaps — the underlying prices move SLOWER than the
    #     hourly precompute that writes this key.
    #   - Cached vs live, compared field-by-field on both open tournaments:
    #     15/15 golfers identical, 0 differing probabilities.
    # `get_golf_cached` falls back to the live `get_golf()` on a cache miss, so a
    # cold Redis degrades to exactly today's behaviour rather than to an error.
    #
    # Everything that must be current is still read live BELOW this line: the
    # placement grid, round groups, related futures and the evolution-market pick
    # all issue their own queries against the DB.
    golf_data = await get_golf_cached(db=db)

    tournaments = golf_data.get("tournaments", [])

    # Find matching tournament by slug
    tournament = None
    for t in tournaments:
        t_slug = t.get("slug") or _clean_slug(t["name"])
        if t_slug == slug:
            tournament = t
            break

    if not tournament:
        # Fallback: tournament may have completed and its markets closed.
        # Query closed/resolved markets directly to serve completed tournament data.
        tournament = await _build_completed_tournament(slug, db, golf_data=golf_data)
        if not tournament:
            raise HTTPException(status_code=404, detail=f"Tournament '{slug}' not found")

    # Sub-group markets by type (winner, top_5, top_10, etc.)
    market_ids = tournament.get("market_ids", [])
    market_names = tournament.get("market_names", [])

    # Build market_id -> market_name mapping
    id_to_name: dict[int, str] = {}
    if len(market_ids) == len(market_names):
        id_to_name = dict(zip(market_ids, market_names))

    # Group by type
    market_groups: dict[str, dict] = {}
    for mid in market_ids:
        mname = id_to_name.get(mid, "")
        type_key, label = _tournament_market_type(mname)
        if type_key not in market_groups:
            market_groups[type_key] = {
                "type": type_key,
                "label": label,
                "market_ids": [],
                "market_names": [],
            }
        market_groups[type_key]["market_ids"].append(mid)
        market_groups[type_key]["market_names"].append(mname)

    # Order: winner first, then top_5/10/20/40, make_cut, round_leader, other
    type_order = ["winner", "top_5", "top_10", "top_20", "top_40", "make_cut", "round_leader", "other"]
    sorted_groups = sorted(
        market_groups.values(),
        key=lambda g: type_order.index(g["type"]) if g["type"] in type_order else 99
    )

    # Find the winner market for the evolution chart. The RANKING is policy and
    # lives in `app.utils.golf_evolution_market` (pure, no session — ruling 005);
    # what stays here is fetching the three facts it ranks on.
    evolution_market_id = None
    for g in sorted_groups:
        if g["type"] == "winner" and g["market_ids"]:
            # LAT-P020/#1107: this ranking used to issue THREE queries PER candidate
            # market from inside the loop — an outcome count, a snapshot count, and a
            # graded-winner lookup. Two of the three are semi-joins against
            # `futures_odds_snapshots`, so the cost scaled with the number of winner
            # markets a major carries, and majors carry the most.
            #
            # MEASURED in production 2026-08-09 by diffing `pg_stat_statements` around
            # a single cold request (`event:golf:pga-championship`, 18.77s wall, 200):
            #     count(futures_odds_snapshots) semi-join   6,951 ms / 7 calls  <- here
            #     futures_markets golf scan (phase 1)       4,839 ms / 1 call
            #     futures_markets full-column selects       3,926 ms / 2 calls
            #
            # TWO separate defects hide in that 6,951 ms, and batching alone fixes
            # only the smaller one. Timing the two shapes against each other on real
            # market ids showed the per-market cost is NOT evenly spread: five Open
            # winner markets cost 4,803 ms cold, of which 4,721 ms was ONE market
            # (datagolf, 193,981 snapshot rows). Collapsing N round trips into one
            # grouped query does not avoid that scan — both shapes read the same rows.
            #
            # What avoids it is ORDER. See the note below the outcome-count fetch:
            # the count only breaks ties among UNGRADED markets, and every completed
            # major is graded, so the expensive input was being computed and then
            # discarded. Batching is kept because it removes the per-market scaling
            # (a guard asserts it), but the laziness is the part that pays.
            #
            # Set-identical by construction: the same candidates are filtered by the
            # same predicates in the same order, and the ranking itself is untouched —
            # it moved to `app.utils.golf_evolution_market` and now reads its facts
            # from dicts. Ties still resolve as before (`>` keeps the FIRST richest,
            # `>=` lets the LAST qualifying resolve win), and an equivalence test pins
            # the split policy against a transcription of the loop it replaced.
            candidate_ids = contender_candidates(g["market_ids"], id_to_name)

            # Outcome counts filter out non-golfer markets ("League of Winner" with 3
            # outcomes, Yes/No binaries, etc.) before the snapshot work is paid for.
            outcome_counts: dict[int, int] = {}
            if candidate_ids:
                outcome_counts = {
                    mid: n
                    for mid, n in (
                        await db.execute(
                            select(
                                FuturesOutcome.market_id,
                                sqlfunc.count(FuturesOutcome.id),
                            )
                            .where(FuturesOutcome.market_id.in_(candidate_ids))
                            .group_by(FuturesOutcome.market_id)
                        )
                    ).all()
                }
            eligible_ids = eligible_candidates(candidate_ids, outcome_counts)

            # ORDER MATTERS, and it is the second half of the fix. Resolution
            # DECIDES whenever it produces an answer, and its input is one price per
            # market; richness only breaks a tie among ungraded markets, and its
            # input is a count over every snapshot of every outcome. Measured in
            # production 2026-08-09 on the same eleven golf winner markets:
            #     graded-winner last price, all 11 markets   613 ms   (one query)
            #     snapshot count, ONE fat market             4,721 ms (cold)
            # `futures_odds_snapshots` holds 193,981 rows for a single long-lived
            # golf winner market, and both majors' markets grade at 0.895-0.9995 —
            # so the old code paid the 4.7s count on every completed major and then
            # threw the answer away, because `resolved_best_id or best_id` had
            # already been decided by the cheap half.
            winner_last: dict[int, object] = {}
            if eligible_ids:
                # DISTINCT ON is the batched form of the old per-market
                # `ORDER BY captured_at DESC LIMIT 1`, and it keeps the same
                # "latest snapshot across the market's winner outcomes" semantics.
                winner_last = {
                    mid: prob
                    for mid, prob in (
                        await db.execute(
                            select(
                                FuturesOutcome.market_id,
                                FuturesOddsSnapshot.probability,
                            )
                            .select_from(FuturesOutcome)
                            .join(
                                FuturesOddsSnapshot,
                                FuturesOddsSnapshot.outcome_id == FuturesOutcome.id,
                            )
                            .where(
                                FuturesOutcome.market_id.in_(eligible_ids),
                                FuturesOutcome.is_winner.is_(True),
                            )
                            .order_by(
                                FuturesOutcome.market_id,
                                FuturesOddsSnapshot.captured_at.desc(),
                            )
                            .distinct(FuturesOutcome.market_id)
                        )
                    ).all()
                }

            evolution_market_id = select_by_settled_resolution(
                eligible_ids, winner_last
            )
            if evolution_market_id is None and eligible_ids:
                # Nothing is graded — a live or upcoming tournament. Only now is the
                # expensive count worth its cost, and only here does it change an
                # answer. A market with zero snapshots does not come back from the
                # join and defaults to 0, exactly as the per-market `scalar() or 0`
                # did.
                snap_counts = {
                    mid: n
                    for mid, n in (
                        await db.execute(
                            select(
                                FuturesOutcome.market_id,
                                sqlfunc.count(FuturesOddsSnapshot.id),
                            )
                            .select_from(FuturesOutcome)
                            .join(
                                FuturesOddsSnapshot,
                                FuturesOddsSnapshot.outcome_id == FuturesOutcome.id,
                            )
                            .where(FuturesOutcome.market_id.in_(eligible_ids))
                            .group_by(FuturesOutcome.market_id)
                        )
                    ).all()
                }
                evolution_market_id = select_by_snapshot_richness(
                    eligible_ids, snap_counts
                )
            break
    if not evolution_market_id and market_ids:
        evolution_market_id = market_ids[0]

    # Filter movers for this tournament
    all_movers = golf_data.get("biggest_movers", [])
    tournament_movers = [
        m for m in all_movers
        if m.get("tournament_key") == tournament.get("key")
    ]

    # ------------------------------------------------------------------
    # Enrich golfers with Top 5/10/20/Make Cut probabilities from
    # non-winner markets so the grid shows placement odds pre-tournament.
    # ------------------------------------------------------------------
    golfers = tournament.get("_all_golfers", tournament.get("golfers", []))

    placement_market_ids: dict[str, list[int]] = {}  # type_key -> [market_ids]
    for g in sorted_groups:
        if g["type"] in ("top_5", "top_10", "top_20", "top_40", "make_cut", "round_leader"):
            placement_market_ids[g["type"]] = g["market_ids"]

    if placement_market_ids:
        # Collect all placement market IDs
        all_placement_ids = []
        for ids in placement_market_ids.values():
            all_placement_ids.extend(ids)

        # Query outcomes for these markets in one batch
        placement_result = await db.execute(
            select(FuturesOutcome)
            .where(
                FuturesOutcome.market_id.in_(all_placement_ids),
                FuturesOutcome.current_probability.isnot(None),
            )
        )
        placement_outcomes = placement_result.scalars().all()

        # Build market_id -> type_key lookup
        mid_to_type: dict[int, str] = {}
        for type_key, mids in placement_market_ids.items():
            for mid in mids:
                mid_to_type[mid] = type_key

        # market_id -> source, so placement probs can prefer DataGolf (#954).
        src_result = await db.execute(
            select(FuturesMarket.id, FuturesMarket.source).where(
                FuturesMarket.id.in_(all_placement_ids)
            )
        )
        mid_to_source: dict[int, str] = {row[0]: row[1] for row in src_result.all()}

        # Build match_key -> {type_key: probability} from placement outcomes.
        # DataGolf is the authoritative in-play model; a blind cross-source
        # average blended its well-differentiated make_cut (Scheffler 0.85,
        # Puig 0.40) with the one-sided Polymarket/Kalshi "To Make the Cut"
        # placeholders (compressed ~0.5), flattening Bubble Watch to ~50% for
        # everyone (#954). Prefer DataGolf when present; otherwise keep the
        # prior pairwise-average behavior across non-DataGolf sources.
        placement_probs: dict[str, dict[str, float]] = defaultdict(dict)
        _from_datagolf: dict[str, dict[str, bool]] = defaultdict(dict)
        for o in placement_outcomes:
            type_key = mid_to_type.get(o.market_id)
            if not type_key:
                continue
            key = _match_key(o.name)
            if not key:
                continue
            prob = float(o.current_probability)
            is_dg = mid_to_source.get(o.market_id) == "datagolf"
            val, val_dg = _prefer_datagolf_merge(
                placement_probs[key].get(type_key),
                _from_datagolf[key].get(type_key, False),
                prob,
                is_dg,
            )
            placement_probs[key][type_key] = val
            _from_datagolf[key][type_key] = val_dg

        # Merge into golfers
        for g in golfers:
            key = _match_key(g["name"])
            if key and key in placement_probs:
                probs = placement_probs[key]
                g["top_5_prob"] = round(probs["top_5"] * 100, 1) if "top_5" in probs else None
                g["top_10_prob"] = round(probs["top_10"] * 100, 1) if "top_10" in probs else None
                g["top_20_prob"] = round(probs["top_20"] * 100, 1) if "top_20" in probs else None
                g["top_40_prob"] = round(probs["top_40"] * 100, 1) if "top_40" in probs else None
                g["make_cut_prob"] = round(probs["make_cut"] * 100, 1) if "make_cut" in probs else None
                g["round_leader_prob"] = round(probs["round_leader"] * 100, 1) if "round_leader" in probs else None
                # Enforce cross-column monotonicity: Win <= Top5 <= Top10 <= Top20 <= Top40 <= MakeCut
                win = g.get("win_prob") or 0
                for col in ["top_5_prob", "top_10_prob", "top_20_prob", "top_40_prob", "make_cut_prob"]:
                    if g.get(col) is not None and g[col] < win:
                        g[col] = win
                    if g.get(col) is not None:
                        win = g[col]

    # ------------------------------------------------------------------
    # Round-scoped groups (#951 round_top + L2-89 round_leader).
    #   * "Round N Top M Finishers" (DataGolf projections, kind="top")
    #   * "End of Round N Leader" (first/second/third-round leader fields, kind="leader")
    # Both are excluded from the tournament placement grid (round-specific numbers
    # would corrupt the whole-tournament Top-N columns). round_top previously
    # surfaced only as bare ids; round_leader was collapsed into a single averaged
    # phantom `round_leader_prob` that NO surface renders (L2-89 gap). Expose both
    # per-market (round + kind + per-golfer outcomes) so the frontend renders a
    # dedicated per-round panel. Disambiguated by (round, kind, top_n) — no
    # grid-key collision.
    # ------------------------------------------------------------------
    round_top_groups: list[dict] = []
    # Last completed round (0 = none). Computed inside the round block from the
    # graded leaders; hoisted here so the related-futures build below can settle
    # round-scoped scoring props ("Round 1 Scores", "Round 2 Lowest Score") too.
    max_completed_round = 0
    rt_group = next((g for g in sorted_groups if g["type"] == "round_top"), None)
    rl_group = next((g for g in sorted_groups if g["type"] == "round_leader"), None)
    round_market_kinds: dict[int, str] = {}
    for mid in (rt_group or {}).get("market_ids", []):
        round_market_kinds[mid] = "top"
    for mid in (rl_group or {}).get("market_ids", []):
        round_market_kinds[mid] = "leader"
    if round_market_kinds:
        # ------------------------------------------------------------------
        # Field-membership guard (The Open 2026 p0 — the "Tiger Woods" bug).
        # Kalshi "End of Round N Leader" markets carry a ~165-name speculative
        # candidate roster that includes players who are NOT in the field —
        # past champions and celebrities (Tiger Woods, Phil Mickelson, John
        # Daly, Ernie Els) — each floated at a phantom ~0.30 with no opening.
        # The WINNER grid is already protected by the DataGolf invitee filter
        # (`_build_tournament_entry`, has_datagolf branch); the round groups
        # were NOT, so out-of-field names rendered as live round-leader
        # outcomes. `golfers` (== `_all_golfers`) is that same invitee-filtered
        # field, so its `_match_key` set is the authoritative roster. Only
        # trust the filter when DataGolf actually supplied the field (otherwise
        # `golfers` IS the padded source list and filtering is a safe no-op)
        # and the set is non-trivially sized. `_match_key` is the SAME name key
        # the placement-grid merge already uses to line Kalshi outcomes up with
        # DataGolf golfers, so field members key-match reliably.
        # ------------------------------------------------------------------
        has_authoritative_field = "datagolf" in (tournament.get("market_sources") or [])
        field_keys: set[str] = set()
        if has_authoritative_field:
            field_keys = {k for k in (_match_key(g.get("name", "")) for g in golfers) if k}
        apply_field_filter = has_authoritative_field and len(field_keys) >= 20

        rt_ids = list(round_market_kinds.keys())
        rt_out_result = await db.execute(
            select(FuturesOutcome).where(
                FuturesOutcome.market_id.in_(rt_ids),
                FuturesOutcome.current_probability.isnot(None),
            )
        )
        rt_by_market: dict[int, list] = defaultdict(list)
        for o in rt_out_result.scalars().all():
            rt_by_market[o.market_id].append(o)
        rt_src_result = await db.execute(
            select(FuturesMarket.id, FuturesMarket.source).where(
                FuturesMarket.id.in_(rt_ids)
            )
        )
        rt_src = {row[0]: row[1] for row in rt_src_result.all()}

        # Which rounds are OVER — derived from the data itself, no live call.
        # The highest graded-leader round is the last completed round; every
        # round <= it is over. Top-N projection markets carry NO is_winner, so
        # they can only be settled by this cross-market inference, not their own
        # grade. Round leaders self-settle via their own is_winner below.
        def _round_of(_mid: int) -> int | None:
            _m = re.search(r"Round\s+(\d+)", id_to_name.get(_mid, ""), re.I)
            return int(_m.group(1)) if _m else None

        # #1803's terminal case. `_golf_status` is THE assigned-status authority
        # for a tournament dict and already decides the banner the reader sees, so
        # it is imported rather than re-derived here — a status rule living in two
        # places is two rules the moment one is tuned (#1620, filed twelve times by
        # this lane). Lazy import mirrors the existing golf<->event_concept idiom
        # and keeps the cycle safe: event_concept imports golf only inside
        # functions.
        from app.utils.event_concept import _golf_status

        tournament_settled = _golf_status(tournament) == "settled"

        max_completed_round = _completed_round_ceiling(
            [
                (
                    round_market_kinds.get(_mid, ""),
                    _round_of(_mid),
                    any(bool(_o.is_winner) for _o in _outs),
                )
                for _mid, _outs in rt_by_market.items()
            ],
            tournament_settled=tournament_settled,
        )

        for mid in rt_ids:
            outs = rt_by_market.get(mid)
            if not outs:
                continue  # false-positive-safe: never surface an empty group
            # Settled-means-settled. A round is done when it carries its own
            # graded winner (leader markets) OR its number is <= the last
            # completed round (Top-N projection markets, which never grade
            # themselves — inferred complete from the leaders). A done round must
            # never show live odds on an in-progress tournament: leaders render
            # WHAT HIT (the graded leader); Top-N projections have no single
            # gradeable winner, so the props body suppresses them.
            #
            # #1803: on a CONCLUDED tournament `max_completed_round` is terminal,
            # so every round-scoped market settles here regardless of whether its
            # own leader ever graded. The ungraded ones then render settled with
            # NO winner, which is the honest-empty state (ruling 025) — deliberately
            # not back-filled from probabilities, because a graded winner is a fact
            # and the 80% favourite is a guess.
            _mid_name = id_to_name.get(mid, "")
            _mid_round = _round_of(mid)
            graded_winner = next((o.name for o in outs if o.is_winner), None)
            round_is_over = _mid_round is not None and _mid_round <= max_completed_round
            settled = bool(graded_winner) or round_is_over
            # Drop out-of-field candidates (never the graded winner, which is
            # authoritative even if a name key somehow misses the roster).
            field_outs = [
                o for o in outs
                if _round_outcome_in_field(
                    o.name, bool(o.is_winner), field_keys, apply_field_filter
                )
            ]
            if not field_outs:
                continue  # whole group was out-of-field noise — surface nothing
            name = _mid_name
            kind = round_market_kinds[mid]
            rnd = _mid_round
            if kind == "top":
                tn_m = re.search(r"Top\s+(\d+)", name, re.I)
                top_n = int(tn_m.group(1)) if tn_m else None
                label = f"Top {top_n} Finishers" if top_n else "Top Finishers"
            else:
                top_n = None
                label = "Round Leader"
            outcomes = sorted(
                (
                    {
                        "name": o.name,
                        "probability": round(float(o.current_probability), 3),
                        # L2-121: opening probability = the pregame mark the concept
                        # page's PropsSection renders as THE SCRIPT (opening → current
                        # divergence). Already loaded on the ORM row (zero new query);
                        # None where the polling pipeline never captured an opening.
                        "opening_probability": (
                            round(float(o.opening_probability), 4)
                            if o.opening_probability is not None
                            else None
                        ),
                    }
                    for o in field_outs
                ),
                key=lambda x: x["probability"],
                reverse=True,
            )[:10]
            round_top_groups.append(
                {
                    "market_id": mid,
                    "market_name": name,
                    "round": rnd,
                    "top_n": top_n,
                    "kind": kind,
                    "label": label,
                    "source": "datagolf_model" if rt_src.get(mid) == "datagolf" else rt_src.get(mid, ""),
                    "outcomes": outcomes,
                    "settled": settled,
                    "graded_winner": graded_winner,
                }
            )
        # Within a round: leader field first, then Top-N ascending.
        round_top_groups.sort(
            key=lambda g: (
                g["round"] or 99,
                0 if g["kind"] == "leader" else 1,
                g["top_n"] or 99,
            )
        )

    # ------------------------------------------------------------------
    # Build "Related Futures" — tournament-specific markets NOT in the grid.
    # These are H2H matchups, nationality props, hole-in-one, bogey-free, etc.
    # ------------------------------------------------------------------
    other_group = next((g for g in sorted_groups if g["type"] == "other"), None)
    related_futures = []
    if other_group and other_group["market_ids"]:
        other_outcomes_result = await db.execute(
            select(FuturesOutcome)
            .options(selectinload(FuturesOutcome.market))
            .where(
                FuturesOutcome.market_id.in_(other_group["market_ids"]),
                FuturesOutcome.current_probability.isnot(None),
            )
            .order_by(FuturesOutcome.current_probability.desc())
        )
        other_outcomes = other_outcomes_result.scalars().all()

        # Group outcomes by market
        from collections import defaultdict as _defaultdict
        outcomes_by_market: dict[int, list] = _defaultdict(list)
        for o in other_outcomes:
            outcomes_by_market[o.market_id].append({
                "name": o.name,
                "probability": round(float(o.current_probability), 4) if o.current_probability else None,
                "american_odds": o.current_american_odds,
                "probability_change_24h": round(float(o.probability_change_24h), 4) if o.probability_change_24h else None,
                # L2-121: pregame mark for the concept page PropsSection (see round
                # groups above). Free — the ORM row is already loaded.
                "opening_probability": (
                    round(float(o.opening_probability), 4)
                    if o.opening_probability is not None
                    else None
                ),
            })

        # market_id -> source for cross-source dedup + per-card attribution (#956/#957).
        other_src_result = await db.execute(
            select(FuturesMarket.id, FuturesMarket.source).where(
                FuturesMarket.id.in_(other_group["market_ids"])
            )
        )
        other_mid_to_source: dict[int, str] = {r[0]: r[1] for r in other_src_result.all()}

        def _lead_prob(outcomes: list) -> float | None:
            """Representative probability for a card — the 'Yes' side of a binary
            question, else the top outcome (used for the cross-source comparison)."""
            for o in outcomes:
                if (o.get("name") or "").strip().lower() == "yes":
                    return o.get("probability")
            return outcomes[0]["probability"] if outcomes else None

        # #956: collapse cross-source duplicates (e.g. the two playoff cards) into
        # ONE card. Keep the highest-priority source's outcomes; expose every
        # source's probability under `sources` so the card can show "Poly 27% /
        # Kalshi 22%" instead of two stacked, disagreeing cards.
        grouped_related: dict[str, dict] = {}
        for mid in other_group["market_ids"]:
            if mid not in outcomes_by_market:
                continue
            mname = id_to_name.get(mid, "")
            # Settled-means-settled: a round-scoped scoring prop ("Round 1
            # Scores", "Round 2 Lowest Score") for a round that is already over
            # must not keep showing live odds. These are multi-winner fields /
            # ladders with no single gradeable result, so drop them entirely
            # (they'd otherwise render live in Props and Scoring & Records). The
            # live/future round ("End of Round 4 …") and tournament-wide records
            # ("Lowest Round Score") carry no completed-round match and survive.
            if _round_scoped_market_complete(mname, max_completed_round):
                continue
            src = other_mid_to_source.get(mid, "unknown")
            key = _related_dedup_key(mname)
            entry = {
                "market_id": mid,
                "market_name": mname,
                "source": src,
                "outcomes": outcomes_by_market[mid],
            }
            source_row = {
                "source": src,
                "market_id": mid,
                "probability": _lead_prob(outcomes_by_market[mid]),
            }
            existing = grouped_related.get(key)
            if existing is None:
                entry["sources"] = [source_row]
                grouped_related[key] = entry
            else:
                existing["sources"].append(source_row)
                # Keep the higher-priority source's card as the primary.
                cur_pri = _RELATED_SOURCE_PRIORITY.get(existing["source"], 99)
                new_pri = _RELATED_SOURCE_PRIORITY.get(src, 99)
                if new_pri < cur_pri:
                    sources = existing["sources"]
                    entry["sources"] = sources
                    grouped_related[key] = entry
        for entry in grouped_related.values():
            # Drop the single-source `sources` list when there's nothing to compare.
            if len(entry.get("sources", [])) <= 1:
                entry.pop("sources", None)
            related_futures.append(entry)

    return {
        "tournament": {
            "name": tournament["name"],
            "slug": slug,
            "key": tournament.get("key"),
            "is_major": tournament.get("is_major", False),
            "is_womens": tournament.get("is_womens", False),
            "start_date": tournament.get("start_date"),
            "end_date": tournament.get("end_date"),
            "venue": tournament.get("venue"),
            "location": tournament.get("location"),
            "schedule_status": tournament.get("schedule_status"),
            "commence_time": tournament.get("commence_time"),
            "resolution_date": tournament.get("resolution_date"),
        },
        "golfers": golfers,
        "markets": sorted_groups,
        "related_futures": related_futures,
        "evolution_market_id": evolution_market_id,
        "biggest_movers": tournament_movers,
        "h2h_matchups": tournament.get("h2h_matchups", []),
        "round_top_groups": round_top_groups,
    }


# ============================================================================
# Live leaderboard (ultra-low-data endpoint)
# ============================================================================

# In-process cache for leaderboard (avoid hammering DataGolf on every refresh)
_leaderboard_cache: dict[str, tuple[float, dict]] = {}
_LEADERBOARD_CACHE_TTL = 120  # 2 minutes


@router.get("/leaderboard/debug")
async def get_golf_leaderboard_debug():
    """Debug: return raw DataGolf in-play response to diagnose field names."""
    from app.services.datagolf_api import DataGolfAPIService
    service = DataGolfAPIService()
    try:
        data = await service._get("preds/in-play", {"tour": "pga"})
    except Exception as e:
        return {"error": str(e)}
    finally:
        await service.close()
    # Return raw response with first 3 player entries
    raw_players = data.get("data", [])
    return {
        "info": data.get("info", {}),
        "top_level_keys": sorted(data.keys()),
        "player_count": len(raw_players),
        "sample_players": raw_players[:3],
    }


@router.get("/leaderboard/{tour}")
@router.get("/leaderboard")
async def get_golf_leaderboard(
    tour: str = "pga",
):
    """Live leaderboard with position, score, thru, hole, and win probability.

    Designed for ultra-low-data views — returns everything needed to render
    a lightweight leaderboard table without JavaScript.
    """
    import time

    cache_key = f"leaderboard_{tour}"
    now = time.time()

    # Check cache
    if cache_key in _leaderboard_cache:
        cached_time, cached_data = _leaderboard_cache[cache_key]
        if now - cached_time < _LEADERBOARD_CACHE_TTL:
            return cached_data

    from app.services.datagolf_api import DataGolfAPIService

    service = DataGolfAPIService()
    try:
        players, info = await service.get_in_play_with_info(tour)
    finally:
        await service.close()

    if not players:
        return {
            "status": "no_event",
            "message": "No tournament currently in play",
            "event_name": None,
            "current_round": None,
            "last_updated": None,
            "players": [],
        }

    # Log score availability for debugging
    has_scores = sum(1 for p in players if p.total_score is not None)
    logger.info(
        "Leaderboard: %d players, %d with scores, event=%s, round=%s",
        len(players), has_scores, info.get("event_name"), info.get("current_round"),
    )

    # Sort by position (numeric sort, with CUT/WD at bottom)
    def _pos_sort_key(p):
        pos = (p.position or "999").lstrip("T")
        try:
            return int(pos)
        except ValueError:
            return 9999

    players.sort(key=_pos_sort_key)

    # ----------------------------------------------------------------
    # Load baseline for delta computation.
    # For Round 1, use pre-tournament odds from DataGolf FuturesOutcome
    # (more meaningful than the first in-play snapshot).
    # For subsequent rounds, use start-of-day leaderboard snapshot.
    # ----------------------------------------------------------------
    snapshot_lookup: dict[str, dict] = {}  # player_name -> {position, win_prob, ...}
    current_round = info.get("current_round")
    try:
        from app.models.models import GolfLeaderboardSnapshot
        from app.services.database import async_session_maker
        from sqlalchemy import select as sa_select
        from zoneinfo import ZoneInfo

        if current_round and current_round >= 2:
            # Rounds 2-4: use start-of-day leaderboard snapshot
            et_now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
            today_start = et_now.replace(hour=0, minute=0, second=0, microsecond=0)

            async with async_session_maker() as snap_session:
                snap_result = await snap_session.execute(
                    sa_select(GolfLeaderboardSnapshot).where(
                        GolfLeaderboardSnapshot.tour == tour,
                        GolfLeaderboardSnapshot.snapshot_date == today_start,
                        GolfLeaderboardSnapshot.snapshot_type == "start_of_day",
                    )
                )
                snapshot = snap_result.scalar_one_or_none()
                if snapshot and snapshot.data:
                    for entry in snapshot.data:
                        name = entry.get("player_name", "")
                        snapshot_lookup[name.lower()] = entry
                    logger.info("Leaderboard: loaded %d-player start-of-day snapshot", len(snapshot_lookup))
        else:
            # Round 1: use last DataGolf snapshot from before today as baseline
            # (captures pre-tournament odds from close to midnight)
            et_now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
            today_start = et_now.replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff = today_start.astimezone(timezone.utc)

            async with async_session_maker() as snap_session:
                # Find the DataGolf winner market for this tour
                dg_result = await snap_session.execute(
                    sa_select(FuturesMarket).where(
                        FuturesMarket.source == "datagolf",
                        FuturesMarket.external_id.like(f"datagolf:{tour}:%:win"),
                        FuturesMarket.status == "open",
                    )
                )
                dg_market = dg_result.scalar_one_or_none()
                if dg_market:
                    # Get outcome IDs for this market
                    out_result = await snap_session.execute(
                        sa_select(FuturesOutcome.id, FuturesOutcome.name).where(
                            FuturesOutcome.market_id == dg_market.id,
                        )
                    )
                    outcomes = out_result.all()
                    outcome_ids = [o.id for o in outcomes]
                    outcome_names = {o.id: o.name for o in outcomes}

                    if outcome_ids:
                        # Get the last snapshot per outcome before today
                        from sqlalchemy import func as sa_func
                        subq = (
                            sa_select(
                                FuturesOddsSnapshot.outcome_id,
                                sa_func.max(FuturesOddsSnapshot.captured_at).label("max_ts"),
                            )
                            .where(
                                FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
                                FuturesOddsSnapshot.captured_at < cutoff,
                            )
                            .group_by(FuturesOddsSnapshot.outcome_id)
                            .subquery()
                        )
                        snap_result = await snap_session.execute(
                            sa_select(FuturesOddsSnapshot).join(
                                subq,
                                (FuturesOddsSnapshot.outcome_id == subq.c.outcome_id)
                                & (FuturesOddsSnapshot.captured_at == subq.c.max_ts),
                            )
                        )
                        for snap in snap_result.scalars().all():
                            name = outcome_names.get(snap.outcome_id, "")
                            if name and snap.probability is not None:
                                wp = round(float(snap.probability) * 100, 1)
                                snapshot_lookup[name.lower()] = {"win_prob": wp}

                    logger.info("Leaderboard R1: loaded %d-player pre-round snapshot (cutoff=%s)",
                                len(snapshot_lookup), cutoff.isoformat())
    except Exception as e:
        logger.warning("Leaderboard: could not load baseline: %s", e)

    # Build response
    leaderboard = []
    for p in players:
        # Determine hole — thru "F" means finished round, otherwise it's the hole number
        thru = p.thru
        if thru and thru.upper() == "F":
            hole_display = "F"
        elif thru and thru.isdigit():
            hole_display = f"H{thru}"
        else:
            hole_display = thru or "—"

        # Format scores
        total = p.total_score
        if total is not None:
            score_display = "E" if total == 0 else f"{total:+d}" if total != 0 else "E"
        else:
            score_display = "—"

        today = p.today_score
        if today is not None:
            today_display = "E" if today == 0 else f"{today:+d}" if today != 0 else "E"
        else:
            today_display = "—"

        win_prob = round(p.win * 100, 1) if p.win else 0.0

        # Compute deltas from start-of-day snapshot
        position_change = None
        win_prob_change = None
        snap_entry = snapshot_lookup.get(p.player_name.lower())
        if snap_entry:
            # Position change: positive = moved up the leaderboard
            snap_pos = snap_entry.get("position", "")
            if snap_pos and p.position:
                try:
                    snap_pos_num = int(str(snap_pos).lstrip("T"))
                    cur_pos_num = int(str(p.position).lstrip("T"))
                    position_change = snap_pos_num - cur_pos_num  # positive = climbed
                except (ValueError, TypeError):
                    pass

            # Win probability change
            snap_wp = snap_entry.get("win_prob")
            if snap_wp is not None:
                win_prob_change = round(win_prob - snap_wp, 1)

        leaderboard.append({
            "position": p.position or "—",
            "name": p.player_name,
            "score": score_display,
            "total_score_raw": p.total_score,
            "today": today_display,
            "today_raw": p.today_score,
            "thru": thru or "—",
            "hole": hole_display,
            "win_prob": win_prob,
            "win_prob_change": win_prob_change,
            # ANNOTATED — queue 333, C272/B4 zero-read census (#1620).
            # The positional twin of `win_prob_change` directly above, which IS read.
            # One of a pair consumed and the other not reads as an unfinished leaderboard
            # rather than dead weight — "did he move up the board" is the more legible
            # half of the same story. Whether to render it is a PRODUCT question, so
            # plumbing does not answer it by deleting the input.
            "position_change": position_change,
            "top_5_prob": round(p.top_5 * 100, 1) if p.top_5 else None,
            "top_10_prob": round(p.top_10 * 100, 1) if p.top_10 else None,
            "top_20_prob": round(p.top_20 * 100, 1) if p.top_20 else None,
            "make_cut_prob": round(p.make_cut * 100, 1) if p.make_cut else None,
            "current_round": p.current_round,
        })

    # Detect completed tournaments: if ALL players have win prob exactly 0 or 100,
    # the event is over — report "completed" instead of "live".
    win_probs = [entry["win_prob"] for entry in leaderboard if entry["win_prob"] is not None]
    is_completed = (
        win_probs
        and all(wp in (0.0, 100.0) for wp in win_probs)
    )

    result = {
        "status": "completed" if is_completed else "live",
        "event_name": info.get("event_name", "Unknown Event"),
        "current_round": info.get("current_round"),
        "last_updated": info.get("last_updated") or datetime.now(timezone.utc).isoformat(),
        "tour": tour,
        "player_count": len(leaderboard),
        "has_snapshot": bool(snapshot_lookup),
        "players": leaderboard,
    }

    # Cache it
    _leaderboard_cache[cache_key] = (now, result)

    return result
