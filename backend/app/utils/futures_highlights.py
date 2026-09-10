"""
Futures market highlight scoring and classification.

Parallel to highlights.py (game events), this scores futures markets
on interestingness (0-100) for the unified feed.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from typing import NamedTuple, Optional

from app.utils.outcome_display import drop_incoherent_ladder_outcomes

# Market tier weights (lower tier number = more important)
MARKET_TIER_WEIGHTS = {
    1: 15,  # Championship
    2: 10,  # Conference
    3: 8,  # Awards (MVP, etc.)
    4: 5,  # Division
    5: 2,  # Props/other
}

# Sport/league tier for futures (mirrors LEAGUE_TIERS in highlights.py)
FUTURES_LEAGUE_TIERS: dict[str, int] = {
    # Major sports
    "basketball": 1,
    "football": 1,
    "baseball": 1,
    "hockey": 1,
    # Secondary sports
    "soccer": 2,
    "golf": 2,
    "tennis": 2,
    "mma": 2,
    # Non-sports (high general interest)
    "politics": 1,
    "crypto": 1,
    "economics": 1,
    "entertainment": 2,
    "tech": 2,
    "weather": 2,
    "geopolitics": 2,
    "culture": 2,
}


# Minor league patterns — futures with these keywords in the market name
# get a penalty instead of a major_league bonus, even if the sport_category
# would normally qualify as tier 1. Prevents AHL/ECHL championship futures
# from outranking actual NBA/NFL games in the feed.
_MINOR_LEAGUE_PATTERNS = re.compile(
    r"\b("
    # Hockey minor leagues
    r"AHL|ECHL|KHL|SHL|DEL|Liiga|NLA|EIHL|OHL|WHL|QMJHL|USHL|"
    # Basketball minor
    r"G[\s-]?League|NBL|BSN|LNB|"
    # Baseball minor
    r"Triple[\s-]?A|Double[\s-]?A|AAA|AA\b|"
    # Soccer minor/lower divisions
    r"Ligue\s*2|Serie\s*B|2\.\s*Bundesliga|EFL\s*Championship|League\s*(One|Two)|"
    r"Eredivisie|Primeira\s*Liga|Super\s*Lig|A[\s-]?League|J[\s-]?League|K[\s-]?League|"
    r"Scottish\s*Premiership|Belgian\s*Pro|Swiss\s*Super|Austrian\s*Bundesliga|"
    # Football minor
    r"CFL|UFL|XFL|USFL|Arena\s*Football" r")\b",
    re.IGNORECASE,
)

# Penalty applied to minor league futures (offsets the major_league bonus)
MINOR_LEAGUE_PENALTY = -15
OBSCURE_SOCCER_PENALTY = -20

_TOP_TIER_SOCCER_RE = re.compile(
    r"\b("
    r"premier league|epl|la liga|bundesliga|serie a|ligue 1|"
    r"champions league|ucl|europa league|mls|major league soccer|"
    r"world cup|fifa|copa america|copa libertadores|liga mx|"
    r"euro 20\d{2}|euros 20\d{2}|european championship"
    r")\b",
    re.IGNORECASE,
)

# Category base scores — calibrated against Polymarket ground truth (April 30, 2026).
# Non-sports categories need a floor score because they lack the signals
# sports markets get (league tier, EI, live status). Without these baselines,
# politics/geopolitics/economics/tech markets score near-zero and never appear.
CATEGORY_BASE_SCORES: dict[str, float] = {
    "politics": 45.0,
    "geopolitics": 45.0,
    "economics": 42.0,
    "tech": 42.0,
    "entertainment": 40.0,
    "culture": 38.0,
    "health": 38.0,
    "weather": 32.0,
    "crypto": 28.0,
    # esports + crypto are near-zero-interest categories for Bain Luck users
    # (Alex product policy, 2026-06-12, SEQUENCE 0b1b). Without an explicit entry
    # esports falls through to SPORTS_CATEGORY_BASE (18.5) and rides the sports
    # bonus path; pinning it below the sports floor makes the bottom-of-feed
    # placement data-driven rather than relying solely on the quality-classifier
    # low_signal_sport cap. Kept below crypto/sports so esports never out-bases an
    # ordinary sports market ("no esports in top-20 absent extraordinary signals").
    "esports": 14.0,
}
SPORTS_CATEGORY_BASE = 18.5

# Boring market patterns — penalize low-quality content that floods the feed.
# These override compelling boosts (early return).
_BORING_PATTERNS = re.compile(
    r"(# ?(posts|tweets|truths)"
    r"|photographed every"
    r"|(posts|tweets)\s+(april|may|june|january|february|march)"
    r"|white house #"
    r"|what will .+ say during"
    r"|# of (views|likes|comments)"
    r"|weekly streams"
    r"|(map \d|bo3|bo5).*(winner|map)"
    r"|\bvs\b.*(map [12345]|game [12345])\b"
    r"|stage \d.+\d{4}:"
    r"|pro football.*(pick|draft|position|quarterback|lineman|linebacker|receiver|edge|running back|cornerback|safety)"
    r"|team to draft"
    r"|overall pick"
    r"|first position drafted"
    r"|1st .+ drafted"
    r"|2nd .+ drafted"
    r"|3rd .+ drafted"
    r"|4th .+ drafted"
    r"|mr\. irrelevant"
    r"|will trump (say|post) \".+\" (this week|on truth)"
    r"|trump (say|post) .+ this week"
    r"|round \d (scores|top \d|leader)"
    r"|to make the cut"
    r"|(pitcher|player) of the month"
    r"|top \d+ finishers"
    r"|net worth on (april|may|june|january|february|march)"
    r"|close price on (may|june|april|january|february|march)"
    r"|compute price (up|down)"
    r"|runner-up .+ on spotify"
    r"|what will .+ say during .+ (newsmax|fox|cnn|msnbc)"
    r"|(lowest|highest) temperature in .+ on (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"|will it rain in .+ on (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"|\b(up or down) on (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"|\b(up or down) (today|this week|on june|on may|on july)"
    r"|gasoline prices? on (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"|natural gas .* (up or down)"
    r"|jet fuel prices? for the week"
    r"|treasury yield at month.end"
    r"|inflation rate yoy.* for (jan|feb|mar|apr|may|jun)"
    r"|margin of victory"
    r"|\bturnout\b"
    r"|district .+ (margin|turnout)"
    r"|how many launches will spacex"
    r"|allegiance \d+ winner"
    r"|college baseball.*(tournament|champion)"
    r"|\([A-Z]{1,6}\) (up or down)"
    r"|daily up.down"
    r"|\bup or down on (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|june|july)"
    r"|women.s champions league"
    r"|coca.cola \d+ winner"
    r"|detroit grand prix"
    r"|opendoor .* up or down"
    r"|closing market cap"
    r"|ipo closing"
    r"|\bmarket cap\b.*(range|\$\d)"
    r"|college (baseball|softball|lacrosse|field hockey)"
    r"|college basketball.*(big west|patriot|horizon|southland|big south|meac|swac|summit|ohio valley)"
    r"|regional champion"
    r"|how many.*(posts|tweets|truths|visits)"
    r"|truth social posts this week"
    r"|series score after game"
    r"|game \d+ winner to be champion"
    r"|week \d+.*elimination"
    r"|iihf\b"
    r"|euroleague\b"
    r"|super league champion)",
    re.IGNORECASE,
)

# Obscure election patterns — local races nobody cares about
_OBSCURE_ELECTION_PATTERNS = re.compile(
    r"((mayoral|mayor).*(election|winner)"
    r"|hackney|newham|lewisham|watford|doncaster|croydon|tower hamlets"
    r"|by-election|byelection"
    r"|(wales|scotland).*(parliamentary|assembly).*(election|winner)"
    r"|(andalusia|bavaria|saxony|thuringia|hesse).*(election|winner)"
    r"|\b\w+ (senate|house|governor) (election|winner|race)"
    r"|district\b.*(general election|winner|margin)"
    r"|oregon senate"
    r"|alaska senate.*(margin|election)"
    r"|kentucky.*(house|district))",
    re.IGNORECASE,
)

# Minor motorsport/golf patterns — penalize niche events that flood the feed
_MINOR_SPORT_EVENT_PATTERNS = re.compile(
    r"("
    r"allegiance \d+|coca.cola 600|detroit grand prix|"
    r"alpine open|unc health championship|"
    r"korn ferry|web\.com|corn ferry|"
    r"women.s champions league"
    r")",
    re.IGNORECASE,
)
MINOR_SPORT_EVENT_PENALTY = -20

_MAJOR_ELECTION_RE = re.compile(
    r"("
    r"\b(u\.?s\.?|united states|american)\b.*\b(president|presidential|senate|house|congress|governor|gubernatorial)\b|"
    r"\b(president|presidential|senate|house|congress|governor|gubernatorial)\b.*\b(u\.?s\.?|united states|american|20\d{2})\b|"
    r"\b(uk|united kingdom|british|french|france|german|germany|canadian|canada|"
    r"mexican|mexico|brazilian|brazil|indian|india|japanese|japan|australian|australia|"
    r"south korea|italian|italy|spanish|spain|chilean|chile|argentin|colombian|colombia|"
    r"nigerian|nigeria|south africa|turkish|turkey|polish|poland|ukrainian|ukraine|"
    r"israeli|israel|iranian|iran|taiwan|philippine|indonesia|egyptian|egypt)\b"
    r".*\b(general election|presidential|prime minister|parliament|chancellor|bundestag|"
    r"election winner|win the election)\b|"
    r"\b(general election|presidential|prime minister|parliament)\b"
    r".*\b(uk|united kingdom|british|french|france|german|germany|canadian|canada|"
    r"mexican|mexico|brazilian|brazil|indian|india|japanese|japan|australian|australia|"
    r"south korea|italian|italy|spanish|spain|chilean|chile|argentin|colombian|colombia|"
    r"nigerian|nigeria|south africa|turkish|turkey|polish|poland|ukrainian|ukraine|"
    r"israeli|israel|iranian|iran|taiwan|philippine|indonesia|egyptian|egypt)\b|"
    r"\b(eu parliament|european parliament|un secretary|nato)\b"
    r")",
    re.IGNORECASE,
)

FOREIGN_LOCAL_ELECTION_PENALTY = -30

# Compelling market patterns — genuinely interesting content
_COMPELLING_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"(invade|invasion|war|strike|military action)",
        r"(ceasefire|peace deal|treaty)",
        r"(nba|nfl|mlb|nhl|fifa|world cup|super bowl|olympics|masters|champions league|wimbledon|french open|australian open|us open|grand slam|ufc).*(champion|winner|title)",
        r"(fed decision|interest rate|recession|rate cut)",
        r"\bipo\b(?!.*(closing|market cap|cap range))|acquire|bankrupt|fail|earnings",
        r"(taylor swift|beyonce|drake|kardashian|bieber)",
        r"(openai|gpt|claude|ai model|deepseek|gemini)",
        r"(u\.?s\.? president|presidential election).*(winner|2028|2026)",
        r"(approval rating).*(trump|biden)",
        r"(regime|coup|revolution|overthrow|fall)",
        r"(china|russia|iran|israel|ukraine|taiwan).*(invade|strike|ceasefire|war|peace)",
        r"(elon musk|jeff bezos|mark zuckerberg|sam altman|warren buffett)",
        r"(s&p 500|dow jones|nasdaq|bitcoin|ethereum).*(high|crash|hit)",
        r"(fda|drug).*(approve|psychedelic|cannabis)",
        r"(pope|vatican|papal|encyclical|conclave)",
        r"(alien|ufo|uap|extraterrestrial)",
        r"(royal family|king charles|prince|princess|meghan|harry)",
        r"(nobel prize|pulitzer|ballon d.or)",
        r"(oscars?|academy award|emmy|grammy|golden globe|tony award|bafta|cannes|sundance|eurovision)",
        r"(survivor|the boys|last of us|stranger things|squid game|house of the dragon|rings of power|bachelor|bachelorette|love island|joe rogan)(?!.*(?:S\d+E\d+|season \d+.*(?:episode|elimination|eviction)))",
        r"(box office|rotten tomatoes|netflix|disney\+|hbo|spotify|billboard|#1 song|#1 album)",
        r"(bridesmaids?|wedding|engaged|engagement|married|divorce)",
    ]
]

BORING_PENALTY = -25
OBSCURE_ELECTION_PENALTY = -20
COMPELLING_BOOST = 8  # per matching pattern, max 3
SPORTS_POSTSEASON_STORY_BOOST = 40
# How far out a "win the Stanley Cup / NBA Finals / …" market can resolve and
# still read as a story about a postseason (#4161). Covers the current season and
# the one after it; beyond that the market is a multi-season futures bet, not a
# story. A market with NO resolution date is never demoted by this — see
# `days_until` in `compute_futures_highlight`.
SPORTS_POSTSEASON_STORY_HORIZON_DAYS = 547

# Cultural gravity — high-interest culture/entertainment markets get a tier
# boost similar to how sports get league tier bonuses. These are markets a
# smart curator would want on page 1 of Discover.
_CULTURAL_GRAVITY_T1 = re.compile(
    r"("
    r"oscar|academy award|emmy|grammy|golden globe|tony award|"
    r"super bowl.*(headline|halftime|headlin)|"
    r"next (james )?bond|"
    r"taylor swift.*(wedding|married|baby|pregnant)|"
    r"time.?s? person of the year|"
    r"sexiest man alive|"
    r"world cup.*(winner|champion|halftime|headline|perform)|"
    r"game awards? 20\d{2}|"
    r"ps[56] (announce|release|launch)|"
    r"highest grossing movie|"
    r"biggest opening weekend|"
    r"nobel (peace |)prize|"
    r"(presidential|president).*(election|winner|2028)|"
    r"(republican|democratic).*(primary|nominee|nomination)|"
    r"(u\.?s\.?|which party).*(senate|house)|senate (control|majority)|"
    r"(impeach|25th amendment|removed from office)|"
    r"stanley cup (winner|champion)|"
    r"world series (winner|champion)|"
    r"french open.*(winner|champion)|"
    r"us open.*(winner|champion)|"
    r"wimbledon.*(winner|champion)|"
    r"australian open.*(winner|champion)|"
    r"roland garros.*(winner|champion)|"
    r"grand slam.*(winner|champion)|"
    r"ufc \d{3,}.*(winner|main event|title)|"
    r"ufc.*(champion|title fight|title bout)|"
    r"(nfl|nba) mvp"
    r")",
    re.IGNORECASE,
)
_CULTURAL_GRAVITY_T2 = re.compile(
    r"("
    r"#1 (song|album|artist|show|movie|app)|"
    r"number.?1.*(song|album|artist|show|movie)|"
    r"billboard.*(hot 100|200)|"
    r"top (artist|song).*(spotify|billboard)|"
    r"(elon musk|jeff bezos|kim kardashian|kanye|rogan)(?!.*(stock|net worth on))|"
    r"james beard|"
    r"(married|wedding|engaged|divorce).*(celebrity|swift|kardashian|obama|clinton)|"
    r"will .+ (buy|acquire) |"
    r"(alien|ufo|extraterrestrial).*(confirm|exist|declas)|"
    r"madden.*(cover)|nba 2k.*(cover)|"
    r"richest person|"
    r"costco.*(hotdog|hot dog)|"
    r"moon landing|"
    r"pluto.*reclassif"
    r")",
    re.IGNORECASE,
)
CULTURAL_GRAVITY_T1_BOOST = 18
CULTURAL_GRAVITY_T2_BOOST = 10

_ELECTION_MARKET_RE = re.compile(
    r"\b(election|electoral|nominee|primary|presidential|president|parliamentary|congressional)\b",
    re.IGNORECASE,
)

# The allowlist-inversion keyword set, previously an inline `re.search(...)` with
# a literal pattern inside the scoring path. Same pattern, same flags, hoisted to
# module scope so it lives beside its siblings and is asked via the shared memo.
_NON_MAJOR_ELECTION_KEYWORD_RE = re.compile(
    r"\b(election|winner|nominee|primary|caucus)\b",
    re.IGNORECASE,
)

_SPORTS_POSTSEASON_STORY_RE = re.compile(
    r"(?=.*\b(advance|reach|make|win|winner)\b)"
    r"(?=.*\b("
    r"nba finals?|wnba finals?|"
    r"stanley cup|world series|super bowl|college football playoff"
    r")\b)",
    re.IGNORECASE,
)


class _NameVerdicts(NamedTuple):
    """Every pattern question this module asks of a market NAME, answered once.

    One field per pattern above, in the order the scorer asks them.
    """

    boring: bool
    obscure_election: bool
    minor_sport_event: bool
    election_market: bool
    major_election: bool
    non_major_election_keyword: bool
    cultural_gravity_t1: bool
    cultural_gravity_t2: bool
    compelling_hits: int
    sports_postseason_story: bool
    minor_league: bool
    top_tier_soccer: bool


@lru_cache(maxsize=8192)
def _name_verdicts(market_name: str) -> _NameVerdicts:
    """Answer every name-only pattern question, memoised on the name.

    The scorer runs over the same market names on every Discover build, and each
    of these answers depends on **the name string and nothing else** — not price,
    status, time, outcomes, source count, volume, tier or category. The patterns
    themselves are module constants compiled at import and never rewritten, so a
    verdict cannot go stale inside a process, and changing a pattern means editing
    this file, which means a deploy, which means a fresh process and an empty
    cache. The key is the whole input, so a renamed market is a different key and
    can never be served an old verdict. (LAT-P225, #3030.)

    `compelling_hits` is the full count over `_COMPELLING_PATTERNS`; the caller
    still applies its own `min(..., 3)` and its own boring-market gate, so the
    scoring arithmetic is untouched.
    """
    return _NameVerdicts(
        boring=bool(_BORING_PATTERNS.search(market_name)),
        obscure_election=bool(_OBSCURE_ELECTION_PATTERNS.search(market_name)),
        minor_sport_event=bool(_MINOR_SPORT_EVENT_PATTERNS.search(market_name)),
        election_market=bool(_ELECTION_MARKET_RE.search(market_name)),
        major_election=bool(_MAJOR_ELECTION_RE.search(market_name)),
        non_major_election_keyword=bool(
            _NON_MAJOR_ELECTION_KEYWORD_RE.search(market_name)
        ),
        cultural_gravity_t1=bool(_CULTURAL_GRAVITY_T1.search(market_name)),
        cultural_gravity_t2=bool(_CULTURAL_GRAVITY_T2.search(market_name)),
        compelling_hits=sum(1 for p in _COMPELLING_PATTERNS if p.search(market_name)),
        sports_postseason_story=bool(_SPORTS_POSTSEASON_STORY_RE.search(market_name)),
        minor_league=bool(_MINOR_LEAGUE_PATTERNS.search(market_name)),
        top_tier_soccer=bool(_TOP_TIER_SOCCER_RE.search(market_name)),
    )


# Scoring weights
FUTURES_WEIGHTS = {
    "major_movement_24h": 12,  # Leader moved >5% in 24h
    "moderate_movement_24h": 6,  # Leader moved 2-5% in 24h
    "leader_change": 15,  # #1 ranking changed
    "rank_shakeup": 8,  # Multiple rank changes in top 5
    "high_tier_market": 10,  # Championship/conference
    "major_league": 8,  # Major sport/league
    "secondary_league": 4,  # Secondary sport
    "resolving_soon_7d": 8,  # Resolves within 7 days
    "resolving_soon_30d": 4,  # Resolves within 30 days
    "multi_source": 8,  # Available from 2+ sources
    "source_divergence": 12,  # Sources disagree by >5%
    "high_volume": 8,  # Market has significant trade volume
    "moderate_volume": 4,  # Market has some trade volume
}

#: The last-resort DISPLAY label for a scoring signal, highest priority first.
#: `routes/feed.py` composes the served headline as
#: `generate_futures_headline(...) or highlight_result.primary_reason`, so every
#: string here is a string a reader can end up looking at.
#:
#: Two rules govern what may be in it, and a signal that satisfies neither is
#: simply absent — the next real signal speaks, and if none does `primary_reason`
#: is None and the card says nothing rather than saying this:
#:
#: * D1 clause a (#4066): the two `*_surprise` codes measure against OPENING, an
#:   instant this list cannot name, so THEY ARE NOT IN IT. The dated sentence is
#:   composed in `feed_reasons`, where `opening_captured_at` is in hand.
#:
#:   🔴 THEY WERE, AND DEMOTING THEM TO THE BOTTOM WAS NOT ENOUGH. The first cut
#:   of this rule left them here as ("major_surprise", "Well off its opening
#:   price") / ("moderate_surprise", "Off its opening price") on the reasoning
#:   that ranking them last meant "their copy no longer claims a baseline". It
#:   does: "its opening price" IS the baseline, named and undated, and clause a
#:   says that sentence "is never the headline reason". Ordering only decides
#:   WHICH label speaks when several could — it cannot stop the last one speaking
#:   when it is the only one left, which is precisely the state a card with no
#:   live signal is in. Measured on production 2026-09-09, `GET /api/feed`
#:   limit=100: eleven occurrences over 100 served cards — 7 top-level headlines,
#:   2 bundle-member headlines, 2 context summaries — and on 6 of the 7 cards it
#:   was the ONLY prose. The reader's copy, photographed at 390px: a 42% market
#:   captioned "Well off its opening price" under "Resolves Jun 29, 2030".
#:
#:   `_biggest_move_from_opening` in `routes/feed.py` already refuses to publish
#:   the undated sentence, and says so at length. That refusal reached ONE of the
#:   two doors: `routes/feed.py` composes the served headline as
#:   `generate_futures_headline(...) or highlight_result.primary_reason`, and the
#:   `or` is the other door. A rule that lands in one component is not landed.
#: * #4133/#4160: `source_divergence`, `rank_shakeup` and `multi_source` carried
#:   "Sources disagree", "Rankings shakeup" and "Multi-source". They are scoring
#:   signals with no honest reader-facing label, and removing their branches from
#:   `feed_reasons` alone would have emptied the headline more often and handed
#:   those exact three strings to this fallback — the fix making its own defect
#:   more visible. Guarded at runtime by
#:   `tests/test_feed_reasons_serve_no_diagnostics_4160.py`.
PRIMARY_REASON_LABELS: list[tuple[str, str]] = [
    ("leader_change", "New favorite"),
    ("major_movement_24h", "Big odds movement"),
    ("volume_spike", "Trading surge"),
    ("moderate_movement_24h", "Odds moving"),
    ("resolving_soon_7d", "Resolving soon"),
    ("resolving_soon_30d", "Resolving this month"),
    # (No `major_surprise` / `moderate_surprise` rungs — see the second bullet
    # above. Both remain SCORING signals, worth 10 and 5; this is a copy fix, not
    # a ranking change, and a card still ranks on the move it no longer misnames.)
]

# Thresholds
MAJOR_MOVEMENT_THRESHOLD = 0.05  # 5% change in 24h
MODERATE_MOVEMENT_THRESHOLD = 0.02  # 2% change
SOURCE_DIVERGENCE_THRESHOLD = 0.05  # 5% disagreement between sources
# #235 Item 2: a near-0% outcome ticking a few tenths of a point (a single thin
# trade on a placeholder nominee — e.g. "Gigi Hadid 0.35% +0.3%") is NOT a story.
# An outcome must clear this absolute-probability floor before it can headline as
# the top mover. Suppresses the never-traded-placeholder 24h-move display class.
MOVER_MIN_PROBABILITY = 0.05  # 5% floor to be eligible as a "mover"

# Volume thresholds (24h trading volume in contracts/dollars)
HIGH_VOLUME_THRESHOLD = 50_000  # $50K+ 24h volume = high interest
MODERATE_VOLUME_THRESHOLD = 5_000  # $5K+ 24h volume = some interest


@dataclass
class FuturesFlags:
    """Boolean flags describing futures market characteristics."""

    has_major_movement: bool = False
    has_moderate_movement: bool = False
    leader_changed: bool = False
    has_rank_shakeup: bool = False
    is_high_tier: bool = False
    is_resolving_soon: bool = False
    has_multi_source: bool = False
    has_source_divergence: bool = False
    has_high_volume: bool = False
    league_tier: int = 3
    market_tier: int = 5


@dataclass
class FuturesHighlightResult:
    """Complete highlight analysis for a futures market."""

    score: int = 0
    # Uncapped float total (before the display cap at 98) used by the feed's
    # de-saturated ORDERING score. `score` stays an int capped at 98 for display
    # and all existing filters; `raw_score` preserves the true additive signal so
    # distinct high-signal cards do not collapse onto the ceiling and fall back to
    # a recency tiebreak. Includes curation_score_adj (applied before the cap).
    raw_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    flags: FuturesFlags = field(default_factory=FuturesFlags)
    primary_reason: Optional[str] = None
    top_mover_name: Optional[str] = None
    top_mover_change: Optional[float] = None


def is_minor_league_market(market_name: str) -> bool:
    """Check if a futures market name indicates a minor/lower-tier league."""
    return _name_verdicts(market_name).minor_league


def is_top_tier_soccer_market(market_name: str) -> bool:
    """Check if a soccer futures market has broad/top-tier audience interest."""
    return _name_verdicts(market_name or "").top_tier_soccer


def compute_futures_highlight(
    # Market metadata
    market_tier: Optional[int] = None,
    sport_category: Optional[str] = None,
    resolution_date: Optional[datetime] = None,
    # Outcome movement data
    outcomes: Optional[list[dict]] = None,
    # Cross-source data
    source_count: int = 1,
    max_source_divergence: Optional[float] = None,
    # Timing
    now: Optional[datetime] = None,
    # Market name for minor league detection
    market_name: Optional[str] = None,
    # Volume/liquidity (internal signal)
    volume_24h: Optional[int] = None,
    volume_7d_avg: Optional[float] = None,
    # Curator adjustment (from curation signals)
    curation_score_adj: int = 0,
) -> FuturesHighlightResult:
    """
    Compute highlight score and flags for a futures market.

    Args:
        market_tier: 1=championship, 2=conference, 3=awards, 4=division, 5=props
        sport_category: LLM-assigned category (basketball, football, politics, etc.)
        resolution_date: When the market resolves
        outcomes: List of dicts with keys: name, probability, probability_change_24h,
                  rank, rank_change_24h, opening_probability
        source_count: Number of sources covering this market
        max_source_divergence: Max probability difference across sources for any outcome
        now: Current time (defaults to UTC now)

    Returns:
        FuturesHighlightResult with score, reasons, flags, and primary display reason.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    result = FuturesHighlightResult()
    flags = result.flags
    outcomes = outcomes or []

    # #4610 — A PRICE THAT CANNOT BE TRUE IS NOT EVIDENCE. On a cumulative ladder
    # every rung is a strict subset of every looser rung, so a rung priced above
    # one of them is arithmetic that does not close. Such a rung is dropped here,
    # before ANY of the four things this function reads an outcome list for: the
    # biggest 24h mover, the leader change, the top-5 rank shakeup and the
    # surprise-vs-opening. Measured on production 2026-09-09, the Discover card
    # "Netflix App Downloads in September" served `P(Above 67) = 94%` over
    # `P(Above 58) = 88%`, and that ONE rung earned all four reasons
    # (`major_movement_24h` +0.48, `leader_change` rank +4, `rank_shakeup`,
    # `major_surprise` +0.49), which composed the card's headline and caption
    # ("New favorite: Above 67 (94%)") and carried its raw score to 101 — page
    # one, position 20 of 100. The reader was handed a reason to care today that
    # was manufactured by the defect.
    #
    # `routes/feed.py` filters its own outcome list upstream so the leader pick
    # and the card's copy agree with this; the guard is repeated here because
    # this function is also the digest's and the admin trace's scorer, and a rule
    # that lands in one component is not landed (#4605).
    outcomes = drop_incoherent_ladder_outcomes(
        outcomes,
        lambda o: o.get("name"),
        lambda o: o.get("probability"),
    )

    # Horizon, normalised ONCE. Two scoring terms need it and they sit on opposite
    # sides of this function (the postseason-story boost below, the resolution
    # proximity ladder near the end), so computing it here is what lets them agree
    # on the same number rather than each re-deriving it.
    #
    # `days_until is None` means WE DO NOT KNOW, and that is not the same as "far
    # away": 153 of the 160 open markets matching the postseason-story pattern
    # carry no `resolution_date` at all (measured 2026-09-09). Every rule below
    # therefore treats an unknown horizon as no evidence and leaves the score
    # alone, so a missing date can never demote a card.
    if resolution_date is not None and resolution_date.tzinfo is None:
        resolution_date = resolution_date.replace(tzinfo=timezone.utc)
    days_until = (resolution_date - now).days if resolution_date is not None else None

    # === Category base score (calibrated against Polymarket ground truth) ===
    _market_name = market_name or ""
    _name_lower = _market_name.lower()
    _sport_lower = (sport_category or "").lower()
    # Every name-only pattern question, asked once and memoised on the name
    # (LAT-P225). The guards below are unchanged, so the same branches fire on
    # the same markets — this only stops re-asking a settled question.
    _v = _name_verdicts(_market_name)

    base = CATEGORY_BASE_SCORES.get(_sport_lower, 0)
    if base == 0 and _sport_lower:
        base = SPORTS_CATEGORY_BASE
    result.score += base
    if base > 0:
        result.reasons.append(f"category_base_{_sport_lower}")

    # NOTE: the former "stale_past_resolution" penalty (resolution_date < now)
    # was dead in the feed path — markets with a past resolution date are excluded
    # by the SQL base filters and the runtime eligibility gate before scoring, so
    # the branch never fired. Removed (RANK-1 dead-code cleanup, #141/Item 3).

    # === Boring market penalty (overrides compelling) ===
    if _market_name and _v.boring:
        result.score += BORING_PENALTY
        result.reasons.append("boring_pattern")

    # === Obscure election penalty ===
    if _market_name and _v.obscure_election:
        result.score += OBSCURE_ELECTION_PENALTY
        result.reasons.append("obscure_election")

    # === Minor sport event penalty ===
    if _market_name and _v.minor_sport_event:
        result.score += MINOR_SPORT_EVENT_PENALTY
        result.reasons.append("minor_sport_event")

    # === Foreign/local + non-major election penalty (single application) ===
    # These two rules overlap heavily (both fire on non-major politics election
    # markets), and previously BOTH could add FOREIGN_LOCAL_ELECTION_PENALTY to
    # the same market for a -60 double penalty. The guards below ensure the -30
    # is applied at most once: the non-major branch is skipped when the
    # foreign/local branch (or the obscure-election penalty) already fired.
    # ("elections" was dropped from the category set — it is never a valid
    # llm_sport_category, so that arm was unreachable dead code. #141/Item 2+3.)
    if (
        _sport_lower == "politics"
        and _market_name
        and _v.election_market
        and not _v.major_election
    ):
        result.score += FOREIGN_LOCAL_ELECTION_PENALTY
        result.reasons.append("foreign_local_election")

    # === Non-major election penalty (allowlist inversion) ===
    if (
        _sport_lower == "politics"
        and _market_name
        and _v.non_major_election_keyword
        and not _v.major_election
        and "obscure_election" not in result.reasons
        and "foreign_local_election" not in result.reasons
    ):
        result.score += FOREIGN_LOCAL_ELECTION_PENALTY
        result.reasons.append("non_major_election")

    # === Cultural gravity boost (high-interest culture/entertainment) ===
    if "boring_pattern" not in result.reasons and _market_name:
        if _v.cultural_gravity_t1:
            result.score += CULTURAL_GRAVITY_T1_BOOST
            result.reasons.append("cultural_gravity_t1")
        elif _v.cultural_gravity_t2:
            result.score += CULTURAL_GRAVITY_T2_BOOST
            result.reasons.append("cultural_gravity_t2")

    # === Compelling market boost (skip if boring) ===
    if "boring_pattern" not in result.reasons and _market_name:
        compelling_hits = _v.compelling_hits
        if compelling_hits > 0:
            result.score += COMPELLING_BOOST * min(compelling_hits, 3)
            result.reasons.append(f"compelling_x{min(compelling_hits, 3)}")

    # #4161 — A POSTSEASON STORY HAS TO BE A STORY ABOUT THIS POSTSEASON.
    # This boost is +40, the single largest term in the file, and it fires on
    # "<verb> the Stanley Cup / NBA Finals / World Series / Super Bowl". Nothing
    # bounded it in time, so it also fired on `Canadian Team to Win the Stanley
    # Cup® Before the 2030-31 Season` — resolving June 2030 — and carried it to
    # 81.5 of a possible 98, which is how a four-year-out market held a page-one
    # slot on the morning edition (#4161, seen at slot 11 and again at slot 16).
    # Roughly half that card's score was this one term.
    #
    # The bound is generous ON PURPOSE: a market for the current season AND the
    # one after it still reads as a postseason story, so the boost survives to 18
    # months. Measured against every open market matching the pattern
    # (2026-09-09): 5 within 18 months keep the boost, 153 with no resolution date
    # keep it (unknown is not far — see `days_until` above), and 2 lose it, both
    # of them multi-season hockey futures resolving in 2029 and 2030.
    _postseason_is_this_era = (
        days_until is None or days_until <= SPORTS_POSTSEASON_STORY_HORIZON_DAYS
    )
    if _market_name and _v.sports_postseason_story and _postseason_is_this_era:
        result.score += SPORTS_POSTSEASON_STORY_BOOST
        result.reasons.append("sports_postseason_story")
    elif _market_name and _v.sports_postseason_story:
        # Recorded so the demotion is legible in `qa_signals` rather than looking
        # like the pattern simply failed to match.
        result.reasons.append("postseason_story_beyond_horizon")

    # === Market tier scoring ===
    tier = market_tier or 5
    flags.market_tier = tier
    tier_weight = MARKET_TIER_WEIGHTS.get(tier, 2)
    if tier <= 2:
        flags.is_high_tier = True
    result.score += tier_weight
    result.reasons.append(f"tier_{tier}")

    # === League/sport scoring ===
    _is_minor = market_name and is_minor_league_market(market_name)
    _is_obscure_soccer = (
        bool(market_name)
        and _sport_lower == "soccer"
        and not _is_minor
        and not is_top_tier_soccer_market(market_name or "")
    )
    if sport_category:
        sport_lower = sport_category.lower()
        league_tier = FUTURES_LEAGUE_TIERS.get(sport_lower, 3)
        flags.league_tier = league_tier
        if _is_minor:
            # Minor league futures get penalized regardless of sport tier.
            # An AHL championship is NOT as interesting as an NBA game.
            result.score += MINOR_LEAGUE_PENALTY
            result.reasons.append("minor_league")
        elif _is_obscure_soccer:
            result.score += OBSCURE_SOCCER_PENALTY
            result.reasons.append("obscure_soccer")
        elif league_tier == 1:
            result.score += FUTURES_WEIGHTS["major_league"]
            result.reasons.append("major_league")
        elif league_tier == 2:
            result.score += FUTURES_WEIGHTS["secondary_league"]
            result.reasons.append("secondary_league")
    elif _is_minor:
        # No sport_category but name indicates minor league
        result.score += MINOR_LEAGUE_PENALTY
        result.reasons.append("minor_league")

    # === Outcome movement analysis ===
    if outcomes:
        # Find the biggest 24h mover
        biggest_change = 0.0
        biggest_mover_name = None

        rank_changes_in_top5 = 0
        current_leader = None
        leader_was_different = False

        for o in outcomes:
            change_24h = abs(float(o.get("probability_change_24h") or 0))
            rank = o.get("rank")
            rank_change = o.get("rank_change_24h")
            opening_prob = o.get("opening_probability")
            current_prob = o.get("probability")

            # Track biggest mover — but only if the outcome itself clears the
            # probability floor. A ~0%-probability nominee is not a story no matter
            # how large its relative delta (#235 Item 2).
            if (
                change_24h > biggest_change
                and (current_prob or 0) >= MOVER_MIN_PROBABILITY
            ):
                biggest_change = change_24h
                biggest_mover_name = o.get("name")

            # Track rank changes in top 5
            if rank is not None and rank <= 5 and rank_change and rank_change != 0:
                rank_changes_in_top5 += 1

            # Track leader change
            if rank == 1:
                current_leader = o.get("name")
                if rank_change and rank_change != 0:
                    leader_was_different = True

        # Major movement scoring — SINGLE HOME: the interestingness blend.
        # 24h movement magnitude is scored once, via market_interestingness's
        # `movement` signal (blended into the feed's ordering score). The reason
        # tags + flags + top-mover are retained here for display, reason-gen, and
        # tags only — no additive score, to remove the double-count. #141/Item 2.
        if biggest_change >= MAJOR_MOVEMENT_THRESHOLD:
            flags.has_major_movement = True
            result.reasons.append("major_movement_24h")
            result.top_mover_name = biggest_mover_name
            result.top_mover_change = biggest_change
        elif biggest_change >= MODERATE_MOVEMENT_THRESHOLD:
            flags.has_moderate_movement = True
            result.reasons.append("moderate_movement_24h")
            result.top_mover_name = biggest_mover_name
            result.top_mover_change = biggest_change

        # (The former "no_movement" -15 penalty was the negative tail of the same
        # 24h-movement signal now owned by the blend, so it is removed here to
        # avoid double-counting: low movement yields a low blend contribution.)

        # Leader change scoring
        if leader_was_different:
            flags.leader_changed = True
            result.score += FUTURES_WEIGHTS["leader_change"]
            result.reasons.append("leader_change")

        # Rank shakeup (multiple top-5 rank changes)
        if rank_changes_in_top5 >= 2:
            flags.has_rank_shakeup = True
            result.score += FUTURES_WEIGHTS["rank_shakeup"]
            result.reasons.append("rank_shakeup")

    # === Resolution proximity ===
    # `days_until` is computed once at the top of this function — the postseason
    # boost above needs the same number, and two derivations of one quantity is
    # how they drift apart.
    if days_until is not None:
        if days_until <= 1:
            # Micro-bets (resolves today/tomorrow) — daily temperature, oil price,
            # stock close. High volume but not Discover-worthy content. This is a
            # low-quality DAILY-MARKET SUPPRESSION, distinct from the blend's
            # monotonic "resolving soon = timely" signal, so it stays here.
            result.score -= 20
            result.reasons.append("micro_bet")
        elif 0 < days_until <= 30:
            # SINGLE HOME: the interestingness blend owns "resolving soon = timely"
            # (resolution_proximity signal). The flag is kept for display/tags; the
            # additive +8/+4 is removed to drop the double-count. #141/Item 2.
            flags.is_resolving_soon = True
            # #4695 — THE REASON CODE IS THE DISPLAY INPUT, AND IT WAS DROPPED WITH
            # THE SCORE IT WAS SITTING NEXT TO.
            #
            # #141/Item 2 (812ca09a) set out to delete a double-counted +8/+4, and
            # the comment three lines up is its own statement of the policy: "the
            # flag is kept for display/tags; the ADDITIVE +8/+4 is removed". Its
            # sibling in the same hunk, `multi_source` fifteen lines below, executed
            # exactly that — "Flag + reason retained for display; additive score
            # removed". This branch did not: the `<= 7` arm was collapsed away
            # whole, and `result.reasons.append("resolving_soon_30d")` went out with
            # the `result.score +=` beside it.
            #
            # These two codes are not bookkeeping. They are read at TEN sites across
            # the four copy generators in `feed_reasons.py` — the reason line, the
            # headline, the binary card's three strings, the context summary — and
            # they are rungs 5 and 6 of `PRIMARY_REASON_LABELS` above, whose own
            # docstring calls every string in it "a string a reader can end up
            # looking at". Nothing in the backend has emitted either code since
            # 812ca09a, so all ten consumers are unreachable and no Discover card
            # can say "resolving this week" however close its resolution is.
            #
            # Measured on production `bbf068c2`, `GET /api/feed?limit=100`: 34 of
            # the 100 served cards resolve inside 30 days (6 inside 7). Three of
            # them are cards with no text of ANY kind — `Will Russia target Kyiv by
            # September 17, 2026?` at score 65 resolves in 7 days and says nothing.
            #
            # Restored WITHOUT the score, which is the half #141 was right about:
            # `result.score` is untouched here, so ordering is unchanged and the
            # double-count stays dead. This is a copy fix, not a ranking change.
            result.reasons.append(
                "resolving_soon_7d" if days_until <= 7 else "resolving_soon_30d"
            )

    # === Cross-source scoring ===
    if source_count >= 2:
        # SINGLE HOME: the blend's `multi_source` signal scores source count.
        # Flag + reason retained for display; additive score removed. #141/Item 2.
        flags.has_multi_source = True
        result.reasons.append("multi_source")

    # Source divergence (disagreement MAGNITUDE) is a distinct signal not carried
    # by the blend, so it remains an additive term.
    if (
        max_source_divergence is not None
        and max_source_divergence >= SOURCE_DIVERGENCE_THRESHOLD
    ):
        flags.has_source_divergence = True
        result.score += FUTURES_WEIGHTS["source_divergence"]
        result.reasons.append("source_divergence")

    # === Volume scoring ===
    # SINGLE HOME: the blend's `volume` signal scores 24h volume MAGNITUDE. Flags +
    # reasons retained for display/tags; additive high/moderate terms removed to
    # drop the double-count. Volume VELOCITY (spike/uptick) below is a distinct
    # acceleration signal not carried by the blend, so it stays additive. #141/Item 2.
    if volume_24h is not None and volume_24h > 0:
        if volume_24h >= HIGH_VOLUME_THRESHOLD:
            flags.has_high_volume = True
            result.reasons.append("high_volume")
        elif volume_24h >= MODERATE_VOLUME_THRESHOLD:
            result.reasons.append("moderate_volume")

    # === Volume velocity (current vs 7-day average) ===
    if volume_24h is not None and volume_7d_avg is not None and volume_7d_avg > 0:
        velocity = volume_24h / volume_7d_avg
        if velocity >= 3.0:
            result.score += 8
            result.reasons.append("volume_spike")
        elif velocity >= 1.5:
            result.score += 3
            result.reasons.append("volume_uptick")

    # === Surprise factor (current vs opening probability) ===
    if outcomes:
        max_surprise = 0.0
        for o in outcomes:
            opening = o.get("opening_probability")
            current = o.get("probability")
            if opening is not None and current is not None:
                max_surprise = max(max_surprise, abs(current - opening))
        if max_surprise >= 0.20:
            result.score += 10
            result.reasons.append("major_surprise")
        elif max_surprise >= 0.10:
            result.score += 5
            result.reasons.append("moderate_surprise")

    # === Curation adjustment (applied BEFORE the cap) ===
    # curation_score_adj is a deliberate human/LLM steer, so it must participate
    # in the score rather than escape the cap post-hoc. Applying it here means it
    # counts toward both the uncapped ranking score and the capped display score.
    # #141/Item 1.
    if curation_score_adj:
        result.score += curation_score_adj
        result.reasons.append(f"curation_adj:{curation_score_adj:+d}")

    # Preserve the uncapped total for the feed's de-saturated ORDERING score,
    # THEN cap the display score at 98. #141/Item 1.
    result.raw_score = float(result.score)
    result.score = min(98, result.score)

    # === Determine primary reason for display ===
    for reason_code, display_text in PRIMARY_REASON_LABELS:
        if reason_code in result.reasons:
            result.primary_reason = display_text
            break

    return result


# NOTE: `should_highlight_futures` was removed (#141/Item 3). It was imported by
# routes/feed.py but never called — the feed uses explicit personalized-score
# floors (`personalized_score < 15`) instead. Dead code.
