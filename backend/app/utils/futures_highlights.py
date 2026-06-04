"""
Futures market highlight scoring and classification.

Parallel to highlights.py (game events), this scores futures markets
on interestingness (0-100) for the unified feed.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


# Market tier weights (lower tier number = more important)
MARKET_TIER_WEIGHTS = {
    1: 15,  # Championship
    2: 10,  # Conference
    3: 8,   # Awards (MVP, etc.)
    4: 5,   # Division
    5: 2,   # Props/other
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
    r"CFL|UFL|XFL|USFL|Arena\s*Football"
    r")\b",
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
    r"|voter turnout"
    r"|district .+ (margin|turnout)"
    r"|how many launches will spacex"
    r"|allegiance \d+ winner"
    r"|college baseball.*(tournament|champion)"
    r"|\([A-Z]{1,5}\) (up or down)"
    r"|women.s champions league"
    r"|coca.cola \d+ winner"
    r"|detroit grand prix"
    r"|opendoor .* up or down"
    r"|closing market cap"
    r"|ipo closing"
    r"|\bmarket cap\b.*(range|\$\d)"
    r"|college (baseball|softball|lacrosse|field hockey)"
    r"|college basketball.*(big west|patriot|horizon|southland|big south|meac|swac|summit|ohio valley))",
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
    re.compile(p, re.IGNORECASE) for p in [
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
FOREIGN_LOCAL_ELECTION_PENALTY = -30
COMPELLING_BOOST = 8  # per matching pattern, max 3
SPORTS_POSTSEASON_STORY_BOOST = 40

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

_MAJOR_ELECTION_RE = re.compile(
    r"\b("
    r"u\.?s\.?|united states|american|president|presidential|senate|house|congress|"
    r"republican|democratic|democrat|gop|dnc|rnc|"
    r"governor|gubernatorial|midterm|"
    r"uk|united kingdom|britain|british|prime minister|"
    r"france|french|germany|german|canada|canadian|brazil|brazilian|india|indian|"
    r"european parliament|eu parliament|eu election"
    r")\b",
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

# Scoring weights
FUTURES_WEIGHTS = {
    "major_movement_24h": 12,       # Leader moved >5% in 24h
    "moderate_movement_24h": 6,     # Leader moved 2-5% in 24h
    "leader_change": 15,            # #1 ranking changed
    "rank_shakeup": 8,              # Multiple rank changes in top 5
    "high_tier_market": 10,         # Championship/conference
    "major_league": 8,              # Major sport/league
    "secondary_league": 4,          # Secondary sport
    "resolving_soon_7d": 8,         # Resolves within 7 days
    "resolving_soon_30d": 4,        # Resolves within 30 days
    "multi_source": 8,              # Available from 2+ sources
    "source_divergence": 12,        # Sources disagree by >5%
    "high_volume": 8,               # Market has significant trade volume
    "moderate_volume": 4,           # Market has some trade volume
}

# Thresholds
MAJOR_MOVEMENT_THRESHOLD = 0.05    # 5% change in 24h
MODERATE_MOVEMENT_THRESHOLD = 0.02 # 2% change
SOURCE_DIVERGENCE_THRESHOLD = 0.05 # 5% disagreement between sources

# Volume thresholds (24h trading volume in contracts/dollars)
HIGH_VOLUME_THRESHOLD = 50_000     # $50K+ 24h volume = high interest
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
    reasons: list[str] = field(default_factory=list)
    flags: FuturesFlags = field(default_factory=FuturesFlags)
    primary_reason: Optional[str] = None
    top_mover_name: Optional[str] = None
    top_mover_change: Optional[float] = None


def is_minor_league_market(market_name: str) -> bool:
    """Check if a futures market name indicates a minor/lower-tier league."""
    return bool(_MINOR_LEAGUE_PATTERNS.search(market_name))


def is_top_tier_soccer_market(market_name: str) -> bool:
    """Check if a soccer futures market has broad/top-tier audience interest."""
    return bool(_TOP_TIER_SOCCER_RE.search(market_name or ""))


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

    # === Category base score (calibrated against Polymarket ground truth) ===
    _market_name = market_name or ""
    _name_lower = _market_name.lower()
    _sport_lower = (sport_category or "").lower()

    base = CATEGORY_BASE_SCORES.get(_sport_lower, 0)
    if base == 0 and _sport_lower:
        base = SPORTS_CATEGORY_BASE
    result.score += base
    if base > 0:
        result.reasons.append(f"category_base_{_sport_lower}")

    # === Stale market penalty (resolution date in the past) ===
    if resolution_date is not None:
        if resolution_date.tzinfo is None:
            resolution_date = resolution_date.replace(tzinfo=timezone.utc)
        if resolution_date < now:
            result.score -= 30
            result.reasons.append("stale_past_resolution")

    # === Boring market penalty (overrides compelling) ===
    if _market_name and _BORING_PATTERNS.search(_market_name):
        result.score += BORING_PENALTY
        result.reasons.append("boring_pattern")

    # === Obscure election penalty ===
    if _market_name and _OBSCURE_ELECTION_PATTERNS.search(_market_name):
        result.score += OBSCURE_ELECTION_PENALTY
        result.reasons.append("obscure_election")

    # === Minor sport event penalty ===
    if _market_name and _MINOR_SPORT_EVENT_PATTERNS.search(_market_name):
        result.score += MINOR_SPORT_EVENT_PENALTY
        result.reasons.append("minor_sport_event")

    if (
        _sport_lower in {"politics", "elections"}
        and _market_name
        and _ELECTION_MARKET_RE.search(_market_name)
        and not _MAJOR_ELECTION_RE.search(_market_name)
    ):
        result.score += FOREIGN_LOCAL_ELECTION_PENALTY
        result.reasons.append("foreign_local_election")

    # === Non-major election penalty (allowlist inversion) ===
    if (
        _sport_lower == "politics"
        and _market_name
        and re.search(r"\b(election|winner|nominee|primary|caucus)\b", _market_name, re.IGNORECASE)
        and not _MAJOR_ELECTION_RE.search(_market_name)
        and "obscure_election" not in result.reasons
    ):
        result.score += FOREIGN_LOCAL_ELECTION_PENALTY
        result.reasons.append("non_major_election")

    # === Cultural gravity boost (high-interest culture/entertainment) ===
    if "boring_pattern" not in result.reasons and _market_name:
        if _CULTURAL_GRAVITY_T1.search(_market_name):
            result.score += CULTURAL_GRAVITY_T1_BOOST
            result.reasons.append("cultural_gravity_t1")
        elif _CULTURAL_GRAVITY_T2.search(_market_name):
            result.score += CULTURAL_GRAVITY_T2_BOOST
            result.reasons.append("cultural_gravity_t2")

    # === Compelling market boost (skip if boring) ===
    if "boring_pattern" not in result.reasons and _market_name:
        compelling_hits = sum(1 for p in _COMPELLING_PATTERNS if p.search(_market_name))
        if compelling_hits > 0:
            result.score += COMPELLING_BOOST * min(compelling_hits, 3)
            result.reasons.append(f"compelling_x{min(compelling_hits, 3)}")

    if _market_name and _SPORTS_POSTSEASON_STORY_RE.search(_market_name):
        result.score += SPORTS_POSTSEASON_STORY_BOOST
        result.reasons.append("sports_postseason_story")

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

            # Track biggest mover
            if change_24h > biggest_change:
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

        # Major movement scoring
        if biggest_change >= MAJOR_MOVEMENT_THRESHOLD:
            flags.has_major_movement = True
            result.score += FUTURES_WEIGHTS["major_movement_24h"]
            result.reasons.append("major_movement_24h")
            result.top_mover_name = biggest_mover_name
            result.top_mover_change = biggest_change
        elif biggest_change >= MODERATE_MOVEMENT_THRESHOLD:
            flags.has_moderate_movement = True
            result.score += FUTURES_WEIGHTS["moderate_movement_24h"]
            result.reasons.append("moderate_movement_24h")
            result.top_mover_name = biggest_mover_name
            result.top_mover_change = biggest_change

        # No movement = stale market, less interesting
        # Only penalize when we HAVE movement data (probability_change_24h is not None)
        has_movement_data = any(o.get("probability_change_24h") is not None for o in outcomes)
        if has_movement_data and biggest_change < 0.005:
            result.score -= 15
            result.reasons.append("no_movement")

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
    if resolution_date is not None:
        if resolution_date.tzinfo is None:
            resolution_date = resolution_date.replace(tzinfo=timezone.utc)
        days_until = (resolution_date - now).days
        if days_until <= 1:
            # Micro-bets (resolves today/tomorrow) — daily temperature, oil price,
            # stock close. High volume but not Discover-worthy content.
            result.score -= 20
            result.reasons.append("micro_bet")
        elif 0 < days_until <= 7:
            flags.is_resolving_soon = True
            result.score += FUTURES_WEIGHTS["resolving_soon_7d"]
            result.reasons.append("resolving_soon_7d")
        elif 0 < days_until <= 30:
            flags.is_resolving_soon = True
            result.score += FUTURES_WEIGHTS["resolving_soon_30d"]
            result.reasons.append("resolving_soon_30d")

    # === Cross-source scoring ===
    if source_count >= 2:
        flags.has_multi_source = True
        result.score += FUTURES_WEIGHTS["multi_source"]
        result.reasons.append("multi_source")

    if max_source_divergence is not None and max_source_divergence >= SOURCE_DIVERGENCE_THRESHOLD:
        flags.has_source_divergence = True
        result.score += FUTURES_WEIGHTS["source_divergence"]
        result.reasons.append("source_divergence")

    # === Volume scoring ===
    if volume_24h is not None and volume_24h > 0:
        if volume_24h >= HIGH_VOLUME_THRESHOLD:
            flags.has_high_volume = True
            result.score += FUTURES_WEIGHTS["high_volume"]
            result.reasons.append("high_volume")
        elif volume_24h >= MODERATE_VOLUME_THRESHOLD:
            result.score += FUTURES_WEIGHTS["moderate_volume"]
            result.reasons.append("moderate_volume")

    # === Volume velocity (current vs 7-day average) ===
    if (
        volume_24h is not None
        and volume_7d_avg is not None
        and volume_7d_avg > 0
    ):
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

    # === Cap score at 100 ===
    result.score = min(98, result.score)

    # === Determine primary reason for display ===
    priority_order = [
        ("leader_change", "New favorite"),
        ("source_divergence", "Sources disagree"),
        ("major_movement_24h", "Big odds movement"),
        ("major_surprise", "Big shift from opening"),
        ("volume_spike", "Trading surge"),
        ("rank_shakeup", "Rankings shakeup"),
        ("moderate_movement_24h", "Odds moving"),
        ("moderate_surprise", "Odds shifted"),
        ("resolving_soon_7d", "Resolving soon"),
        ("resolving_soon_30d", "Resolving this month"),
        ("multi_source", "Multi-source"),
    ]

    for reason_code, display_text in priority_order:
        if reason_code in result.reasons:
            result.primary_reason = display_text
            break

    if curation_score_adj:
        result.score += curation_score_adj
        result.reasons.append(f"curation_adj:{curation_score_adj:+d}")

    return result


def should_highlight_futures(result: FuturesHighlightResult, min_score: int = 25) -> bool:
    """Determine if a futures market should appear in the feed."""
    # Always highlight leader changes and source divergence
    if result.flags.leader_changed:
        return True
    if result.flags.has_source_divergence:
        return True
    # Always highlight major movements in high-tier markets
    if result.flags.has_major_movement and result.flags.is_high_tier:
        return True
    # Otherwise, use score threshold
    return result.score >= min_score
