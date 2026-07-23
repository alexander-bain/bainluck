"""Market quality classification for Discover feed futures.

This module is intentionally pure: no database access and no app imports.
It identifies markets that are liquid or timely but poor feed material,
especially repetitive range/bucket ladders.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

# #921: a market needs a real, showable price to earn a Discover card. Below
# this floor the top outcome rounds to 0% in the UI — the "0% probability on
# active markets" junk Manus kept flagging (e.g. "Korea K League 1 Champion" with
# no meaningful line). 0.5% is the display-rounding boundary; genuine even-odds
# (50%) and real longshot-leader races sit far above it.
FEED_MIN_REAL_PROBABILITY = 0.005


def has_no_real_price(outcome_probabilities: "list[float | None]") -> bool:
    """True if a futures market has no meaningful price to surface (#921).

    No real price means EITHER every outcome is null/zero (a dead market) OR even
    the top outcome is below the display floor (rounds to 0%). Inputs are the
    per-outcome ``current_probability`` values (0.0-1.0); ``None``/``0`` mean "no
    price". False-positive-safe: 50% even-odds and real longshot-leader races
    (leader well above 0.5%) return False and stay eligible.
    """
    real = [float(p) for p in outcome_probabilities if p]
    if not real:
        return True
    return max(real) < FEED_MIN_REAL_PROBABILITY


# #1004: unresolved markets whose leader is pinned at a dead extreme render as a
# lone "100%" (or "0%") card — the locked-near-certain junk class Manus flagged
# (split from #921; cf. gotcha #23). Suppress them UNLESS there's live interest:
# a genuine near-certain MOVER (a big 24h swing — e.g. it just jumped to 99% on
# news) or a high-volume market stays eligible.
FEED_LOCKED_CERTAIN_HIGH = 0.99   # leader rounds to 100%
FEED_LOCKED_CERTAIN_LOW = 0.01    # leader rounds to 0%
FEED_LOCKED_CERTAIN_KEEP_MOVE = 0.10       # >=10pt 24h swing = genuine mover
FEED_LOCKED_CERTAIN_KEEP_VOLUME = 25000.0  # live money = keep


def is_locked_near_certain(
    leader_probability: "float | None",
    max_abs_movement_24h: "float | None" = None,
    volume_24h: "float | None" = None,
) -> bool:
    """True if an UNRESOLVED market is pinned at a dead-extreme price with no live
    interest (#1004). The caller applies this only to open/unresolved feed
    candidates. Guarded so a near-certain MOVER or a high-volume market is kept —
    only the boring locked-certain cards are suppressed.
    """
    if leader_probability is None:
        return False
    if not (
        leader_probability >= FEED_LOCKED_CERTAIN_HIGH
        or leader_probability <= FEED_LOCKED_CERTAIN_LOW
    ):
        return False
    # Genuine mover — a big recent swing is interesting even at a dead extreme.
    if (
        max_abs_movement_24h is not None
        and abs(max_abs_movement_24h) >= FEED_LOCKED_CERTAIN_KEEP_MOVE
    ):
        return False
    # Live money — high 24h volume means the market is actively traded.
    if volume_24h is not None and volume_24h >= FEED_LOCKED_CERTAIN_KEEP_VOLUME:
        return False
    return True


QualityClass = Literal["compelling", "normal", "low_quality", "suppress"]
EditorialArchetype = Literal[
    "world_event",
    "breaking_news",
    "tech_frontier",
    "macro_signal",
    "culture_moment",
    "health_weather_risk",
    "sports_story",
    "sports_drama",
    "big_public_company",
    "company_drama",
    "political_power",
    "big_name",
    "weird_news",
    "absurd_but_real",
    "other",
]


_MONTH_RE = (
    r"january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
)

_NUMBER_RE = re.compile(r"[-+]?\$?\d+(?:,\d{3})*(?:\.\d+)?%?")

# Mapping for #N ranking placeholders — word form prevents the <num> pass
# from collapsing distinct rankings (e.g., #1 vs #2) into the same token.
_RANK_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}

_PRICE_BUCKET_RE = re.compile(
    r"\b("
    r"oil|crude|brent|wti|gas|natural gas|gold|silver|copper|"
    r"cattle|livestock|corn|wheat|soybeans?|coffee|cocoa|"
    r"s&p|s\s*&\s*p|nasdaq|dow|russell|stock|shares?|"
    r"treasury|yield|usd/jpy|eur/usd|gbp/usd|currency|forex|"
    r"bitcoin|btc|ethereum|eth|solana|sol|crypto|"
    r"cpi|inflation|fed funds|interest rate|mortgage rate"
    r")\b.*\b("
    r"between|range|close price|closing price|close above|close below|"
    r"at \d|above|below"
    r")\b",
    re.IGNORECASE,
)

_COMMODITY_DATED_PRICE_RE = re.compile(
    r"\b("
    r"oil|crude|brent|wti|natural gas|gasoline|cattle|livestock|"
    r"corn|wheat|soybeans?|coffee|cocoa|treasury|yield|"
    r"usd/jpy|eur/usd|gbp/usd"
    r")\b.*\b"
    r"(price|hit|close|settle)\b.*\b(on|in|this week|next week|by)\b",
    re.IGNORECASE,
)

_DATED_FINANCE_METRIC_RE = re.compile(
    r"\b(treasury|yield|inflation|cpi|ppi|usd/jpy|eur/usd|gbp/usd)\b"
    r".*\b(on|in|this week|next week|by)\b",
    re.IGNORECASE,
)

_DAILY_EQUITY_DIRECTION_RE = re.compile(
    r"\b("
    r"s&p\s*500|spx|spy|nasdaq|qqq|dow|russell|iwm|"
    r"nvidia|nvda|tesla|tsla|apple|aapl|microsoft|msft|"
    r"google|alphabet|googl|amazon|amzn|meta|netflix|nflx|"
    r"robinhood|hood|rocket lab|rklb|ewy|gme|gamestop"
    r")\b.*\b("
    r"up or down|closes? above|closes? below|close above|close below"
    r")\b.*\b("
    r"today|tomorrow|on|"
    rf"{_MONTH_RE}|"
    r"\d{1,2}/\d{1,2}"
    r")\b",
    re.IGNORECASE,
)

_WEATHER_BUCKET_RE = re.compile(
    r"\b("
    r"temperature|degrees?|rainfall|snowfall|precipitation|weather|"
    r"high temp|low temp|daily high|daily low"
    r")\b.*\b("
    r"between|above|below|over|under|at least|less than|more than|"
    rf"{_MONTH_RE}|\d{{1,2}}/\d{{1,2}}"
    r")\b",
    re.IGNORECASE,
)

_SOCIAL_FILLER_RE = re.compile(
    r"(# ?(posts|tweets|truths|views|likes|comments)"
    r"|photographed every"
    r"|(posts|tweets)\s+(" + _MONTH_RE + r")"
    r"|white house #"
    r"|what will .+ (say|post) (during|this week|on truth)"
    r"|will .+ (say|post) \".+\""
    r"|who will .+ (talk to|speak to)"
    r"|how many people will .+ endorse"
    r"|weekly streams"
    r"|runner-up .+ on spotify"
    r"|net worth on (" + _MONTH_RE + r")"
    r")",
    re.IGNORECASE,
)

_ENTERTAINMENT_METRIC_RE = re.compile(
    r"\b("
    r"streams up this week|weekly streams|album equivalent units|"
    r"weekly top (songs|albums)|"
    r"top album on weekly|top song on weekly|"
    r"rank on the billboard|#[2-9]\d* on the billboard"
    r")\b",
    re.IGNORECASE,
)

# --- Alex interview 2026-06-15 rules (R2/R6/R8), audit-verifiable ----------
# R2: asset price-LEVEL markets are never interesting — "will <asset> close/
# trade/hit above/below $X" on stocks/crypto/commodities. Broader than the
# named-asset lists above (catches single tickers like META not listed there).
# A market must have BOTH an asset context AND a price threshold, and must NOT
# be a macro policy/EVENT market (those stay eligible per Alex).
_ASSET_CONTEXT_RE = re.compile(
    r"\b("
    r"stock|shares?|share price|etf|"
    r"bitcoin|btc|ethereum|eth|solana|sol|crypto|dogecoin|doge|xrp|cardano|ada|"
    r"oil|crude|brent|wti|gas|gold|silver|copper|cattle|livestock|corn|wheat|"
    r"soybeans?|coffee|cocoa|"
    r"s&p|s\s*&\s*p|spx|spy|nasdaq|qqq|dow|russell|iwm|"
    r"nvidia|nvda|tesla|tsla|apple|aapl|microsoft|msft|alphabet|googl|google|"
    r"amazon|amzn|meta|netflix|nflx|palantir|pltr|gamestop|gme|coinbase|coin|"
    r"microstrategy|mstr|robinhood|hood|rocket lab|rklb|strategy"
    r")\b",
    re.IGNORECASE,
)
_PRICE_THRESHOLD_RE = re.compile(
    r"(\$\s?\d[\d,]*(?:\.\d+)?\s?(?:k|m|bn|b|trillion|t)?\b"  # a $ amount
    r"|\b(above|below|over|under|past|exceeds?|reach(?:es)?|hit)\b\s+\$?\s?[\d,]+"  # 'above 6000'
    r"|\b(close|closing|trade|trading|finish|end|settle|reach|hit|be|stay|go|top)\b"
    r"[^?]{0,30}\b(above|below|over|under|past|at)\b[^?]{0,15}\d)",
    re.IGNORECASE,
)
# Macro policy/EVENT markets are a DIFFERENT category and stay eligible.
_MACRO_EVENT_RE = re.compile(
    r"\b("
    r"fed (rate|funds|decision|meeting|cut|hike|hold|chair)|"
    r"rate (cut|hike|decision|hold)|recession|soft landing|hard landing|"
    r"jobs report|unemployment rate|nonfarm|payrolls|gdp|"
    r"cpi (surprise|print|come|release|report)|inflation (surprise|print|report)|"
    r"debt ceiling|government shutdown|tariff|emergency rate"
    r")\b",
    re.IGNORECASE,
)


def _is_asset_price_level(name: str) -> bool:
    """R2 — asset price-LEVEL market (stocks/crypto/commodities ' above $X')."""
    if _MACRO_EVENT_RE.search(name):
        return False
    return bool(_ASSET_CONTEXT_RE.search(name)) and bool(_PRICE_THRESHOLD_RE.search(name))


# R8: "#1 yes, #2 no." A "will X be number one" market is eligible; runner-up /
# "#2" / non-winning-rank markets are downranked.
_NUMBER_ONE_RE = re.compile(
    r"(#\s?1\b|\bnumber one\b|\bno\.?\s?1\b|\btop of\b|\b(reach|hit|be|stay)\s+#?\s?1\b)",
    re.IGNORECASE,
)
_RUNNER_UP_RE = re.compile(
    r"(#\s?[2-9]\d*\b|\bnumber (two|three|four|five)\b|\bno\.?\s?[2-9]\b|"
    r"\brunner.?up\b|\bfinish (second|third|fourth|2nd|3rd|4th)\b|"
    r"\b(come|finish|place)\s+(in\s+)?(second|2nd)\b|\bsecond place\b)",
    re.IGNORECASE,
)


def _is_runner_up_rank(name: str) -> bool:
    """R8 — non-#1 ranking market (runner-up / #2+); not a 'number one' market."""
    return bool(_RUNNER_UP_RE.search(name)) and not bool(_NUMBER_ONE_RE.search(name))


# R6: resolved SPORTS scores never surface (Alex gets them from ESPN). Needs the
# market/event status (threaded in from the scoring path).
_SPORTS_CATEGORIES = {
    "basketball", "football", "baseball", "hockey", "soccer", "golf", "tennis",
    "mma", "boxing", "cricket", "rugby", "motorsports", "esports", "lacrosse",
    "wrestling", "olympics", "cycling", "rodeo", "pickleball",
}


def _is_resolved_sports(status: str | None, category: str) -> bool:
    """R6 — a resolved/closed market in a sports category."""
    if (status or "").lower() not in ("resolved", "completed", "closed", "settled"):
        return False
    cat = (category or "").lower()
    return cat in _SPORTS_CATEGORIES or bool(_LOW_SIGNAL_SPORT_RE.search(cat))


# R3: novel sports framings — nationality / region / aggregate angles are
# interesting even when they aren't marquee games (Alex 2026-06-15, verbatim
# examples: "Will a Canadian team win the NHL Stanley Cup?", "Will a golfer from
# Europe or from Asia finish higher?"). These are NOT vanilla stat-line player
# props ("X scores 30+"). Gated on a sports category so it never matches non-
# sports ("a Canadian company"). A BOOST (→ compelling), never a suppression.
_SPORTS_NATIONALITY = (
    r"canadian|canada|american|european|europe|asian|asia|african|africa|"
    r"australian|british|britain|english|scottish|irish|mexican|japanese|"
    r"korean|chinese|international|foreign|non-?us|non-?american"
)
_SPORTS_NOVELTY_RE = re.compile(
    r"(?:"
    # "a/any <nationality> team|player|golfer|driver|... (to|will) win|finish|reach"
    r"\b(?:a|an|any)\s+(?:" + _SPORTS_NATIONALITY + r")\s+"
    r"(?:\w+\s+){0,2}?(?:team|nation|country|player|golfer|driver|"
    r"pitcher|rider|club|side|athlete)\b"
    r"|"
    # region-vs-region / "from Europe or Asia" aggregate framings
    r"\b(?:" + _SPORTS_NATIONALITY + r")\s+(?:or|vs\.?|versus)\s+"
    r"(?:" + _SPORTS_NATIONALITY + r")\b"
    r"|"
    r"\bfrom\s+(?:europe|asia|africa|north america|south america|"
    r"another (?:country|continent))\b"
    r")",
    re.IGNORECASE,
)


def _is_novel_sports_framing(name: str, category: str) -> bool:
    """R3 — novel sports framing (nationality/region/aggregate angle).

    A boost signal: these read as genuinely interesting even outside marquee
    games. Gated on a sports category to avoid matching non-sports nationality
    phrasing.
    """
    cat = (category or "").lower()
    if cat not in _SPORTS_CATEGORIES and not _LOW_SIGNAL_SPORT_RE.search(cat):
        return False
    return bool(_SPORTS_NOVELTY_RE.search(name))


_OBSCURE_PROCEDURAL_RE = re.compile(
    r"\b("
    r"reauthorize|committee|subcommittee|cloture|filibuster|"
    r"by-election|byelection|mayoral election|mayor election|mayor winner|"
    r"hackney|newham|lewisham|watford|doncaster|croydon|tower hamlets|"
    r"terrebone|chungche|andalusia|saxony|thuringia|hesse"
    r")\b",
    re.IGNORECASE,
)

_REGIONAL_US_ELECTION_RE = re.compile(
    r"("
    r"\b[A-Z]{2}[-\s]?\d{1,2}\b|"
    r"\b(state house|state senate|city council|county executive|school board)\b|"
    r"\b(republican|democratic|gop|dem)\s+(nominee|primary)\b|"
    r"\b(governor|senate|house)\s+(nominee|primary)\b|"
    r"\b(lieutenant governor|secretary of state)\b|"
    r"\b("
    r"state|alabama|alaska|arizona|arkansas|california|colorado|connecticut|"
    r"delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|"
    r"kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|"
    r"mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|"
    r"new mexico|new york|north carolina|north dakota|ohio|oklahoma|oregon|"
    r"pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|"
    r"utah|vermont|virginia|washington|west virginia|wisconsin|wyoming"
    r")\s+attorney general\b"
    r")",
    re.IGNORECASE,
)

# Margin-of-victory + voter-turnout election markets — Alex product decision
# (2026-06-24). These two families flooded Discover: ~1,100 open variants, one
# per state/district (KXMIDTERMMOV-*, KXMIDTERMVOTETURN-*, ...), and Alex judged
# them "hard to imagine ever being interesting to any audience." They previously
# only got the weak -25 BORING_PENALTY (politics base 45 - 25 = 20 still cleared
# the 18.5 sports floor), so they survived and crowded the feed. Treatment: HARD
# EXCLUDE both families by default. The ONLY carve-out is US presidential turnout
# (see _is_us_presidential_turnout) — foreign presidential/parliamentary turnout
# (Zambia, Russia, New Zealand) stays suppressed.
#
# Margin: nearly all say "margin of victory" literally; the election-context
# branches catch variants ("LA mayoral primary: ... margin") while deliberately
# NOT matching finance margins ("Micron gross margin", "MicroStrategy margin
# called", "Sweetgreen profit margin"), which carry no election keyword.
_ELECTION_MARGIN_RE = re.compile(
    r"margin of victory"
    r"|\b(election|primary|runoff|midterm|senate|house|governor|gubernatorial"
    r"|presidential|congress(?:ional)?|district|electoral college|popular vote"
    r"|mayoral|parliament(?:ary)?|redistrict\w*)\b[^.]{0,40}\bmargin\b"
    r"|\bmargin\b[^.]{0,40}\b(election|primary|runoff|midterm|senate|house"
    r"|governor|gubernatorial|presidential|congress(?:ional)?|district)\b",
    re.IGNORECASE,
)
# "turnout" is election-specific in this catalog; plain word match is safe and
# catches the variants the old `voter turnout` literal missed ("U.S. House
# turnout?", "House Turnout", "Russia Parliamentary Election: Turnout").
_VOTER_TURNOUT_RE = re.compile(r"\bturnout\b", re.IGNORECASE)
# Belt-and-suspenders: the known margin/turnout ticker families. Name detection
# alone covers every current market, but tickers guard against future blank/odd
# names. Tokens chosen to avoid collisions (e.g. "MOVIE").
_MARGIN_TURNOUT_TICKER_RE = re.compile(
    r"(KXMOV|MIDTERMMOV|PRIMARYMOV|POPVOTEMOV|ECMOV|POPVOTEMARGIN"
    r"|VOTETURN|MIDTERMVOTETURN|PRIMARYTURNOUT|HOUSETURNOUT|TURNOUT)",
)


def _is_us_presidential_turnout(name: str) -> bool:
    """Carve-out: US presidential voter turnout may surface (Alex 2026-06-24).

    Must be US-specific so foreign presidential/parliamentary turnout
    (Zambia, Russia) stays suppressed.
    """
    low = (name or "").lower()
    if "turnout" not in low:
        return False
    if not re.search(r"\bpresident", low):
        return False
    return bool(re.search(r"\b(u\.?s\.?|united states|american)\b", low))


# Artist annual stream-count markets — Lane 2 Queue L2-2 (2026-06-24), the next
# over-represented mechanical family after margin/turnout (#968). ~60 open
# variants, one per artist (KXARTISTSTREAMS*): "Rihanna Streams in 2026", "Drake
# Streams in 2026", ... A number-guessing ladder of annual Spotify stream counts
# with no audience-facing story. The *weekly* variant was already suppressed by
# _ENTERTAINMENT_METRIC_RE; this is the same family, just the annual phrasing the
# regex missed, so entertainment base 40 survived (and big names like Drake even
# got the compelling boost). Hard-exclude, same as #968.
#
# Pattern is plural "streams in <year>" so it does NOT catch the legit carve-outs:
# awards ("Streamer of the Year", "Best ... Streamed Motion Picture"),
# competitions ("Most Watched Kick Streamer in June"), or industrial "comes on
# stream in <year>" idioms (singular "stream").
_STREAM_COUNT_RE = re.compile(r"\bstreams\s+in\s+\d{4}\b", re.IGNORECASE)
_STREAM_COUNT_TICKER_RE = re.compile(r"KXARTISTSTREAMS")

# Vote-percent ladders — Lane 2 Queue L2-3 (Alex 2026-06-24). "[Candidate] vote
# percent" per-candidate vote-share threshold markets (~54 open, ticker
# KXVOTEPRIMARY*) are the same mechanical ladder shape as margin-of-victory
# (#968): one row per candidate, no audience-facing story. Hard-exclude.
# False-positive-safe: requires the literal "vote percent / % of the vote /
# vote share" — does NOT catch approval ratings or poll shares of other things.
_VOTE_PERCENT_RE = re.compile(
    r"\bvote percent\b"
    r"|\bvote share\b"
    r"|\b(?:percent|%|\d+%)\s+of the vote\b",
    re.IGNORECASE,
)
_VOTE_PERCENT_TICKER_RE = re.compile(r"KXVOTEPRIMARY")

# Individual House-DISTRICT winner markets — Lane 2 Queue L2-3 (Alex 2026-06-24).
# "TN-09 House winner?" per-district races (~359 open, ticker KXHOUSERACE*) — one
# row per congressional district. Hard-exclude. The carve-out is by construction:
# the chamber-CONTROL market ("Which party will win the U.S. House?", ticker
# CONTROLH-*) carries no district code and no "House winner" phrasing, so it is
# NOT matched and stays eligible — likewise Senate/Governor/President major races.
_HOUSE_DISTRICT_RE = re.compile(
    r"\b[a-z]{2}-?\d{1,2}\b\s+house\s+winner",
    re.IGNORECASE,
)
_HOUSE_DISTRICT_TICKER_RE = re.compile(r"KXHOUSERACE")

# Nonfarm-payrolls jobs-number ladders — Lane 2 Queue L2-4 (Alex 2026-06-24:
# "GDP is potentially interesting. Payroll is not."). ~9 open monthly BLS jobs-
# number threshold markets (ticker KXPAYROLLS*). Hard-exclude. False-positive-
# safe: matches the unambiguous "nonfarm payroll(s)" metric (and the ticker),
# NOT "payroll tax" policy markets. GDP (KXGDPNOM*), Fed-rate, and CPI markets
# carry no "nonfarm payroll" text and a different ticker → stay eligible.
_PAYROLLS_RE = re.compile(r"\bnonfarm\s+payrolls?\b", re.IGNORECASE)
_PAYROLLS_TICKER_RE = re.compile(r"KXPAYROLLS")


_LOW_SIGNAL_SPORT_RE = re.compile(
    r"\b(table tennis|ping pong|wtt|badminton|snooker|darts|"
    r"esports|counter.?strike|cs2|csgo|valorant|league of legends|"
    r"dota|overwatch|call of duty|rocket league|blast slam)\b",
    re.IGNORECASE,
)

_EPISODE_LEVEL_RE = re.compile(
    r"("
    r"S\d{1,2}E\d{1,2}"
    r"|season \d+.*(episode|elimination|eviction|week \d)"
    r"|episode \d+.*(elimination|eviction|winner)"
    r"|week \d+.*(?:elimination|eviction)"
    r")",
    re.IGNORECASE,
)

# Ticker-prefix suppression: numeric KPI/index threshold ladders
_SUPPRESS_TICKER_PREFIXES = (
    # Stock index ranges/levels
    "KXINX-", "KXINXY-", "KXNASDAQ100Y-", "KXINXU-", "KXINXMAXY-", "KXINXMINY-",
    # Company KPI thresholds
    "KXTSLA-", "KXMTN-", "KXFDX-", "KXF-", "KXMCD-",
    # Macro indicators
    "KXISMPMI-", "KXNOTE10-", "KXUSDM-",
    # Launch/production counts
    "KXSPACEXCOUNT-",
)

# Ticker-prefix boost: narrative-driven markets
_BOOST_TICKER_PREFIXES = (
    # IPO timing
    "KXWAYMO", "KXIPOANTHROPIC", "KXIPOSTARLINK", "KXIPO-",
    # CEO/leadership changes
    "KXAAPLCEOCHANGE", "KXTESLACEOCHANGE", "KXOPENAICEOCHANGE", "KXNEWROLEX",
    # M&A / acquisitions
    "KXTAKEOVERACQ", "KXACQUANNOUNCE", "KXACQANNOUNCE", "KXUSACOMPANYSTAKE",
    "KXCOMPANYSTAKE",
    # Product launches
    "KXIPHONERELEASE", "KXAPPLEFOLD", "KXPS6",
    # Cultural / fun
    "KXCOSTCOHOTDOG", "KXBEZELP", "KXNBAFINALSPRICE", "KXNFLXINCREASE",
    # AI milestones
    "KXAISTREAMSERIES", "KXOAIANTH", "KXLLM1",
)

_TOP_TIER_SOCCER_RE = re.compile(
    r"\b("
    r"premier league|epl|la liga|bundesliga|serie a|ligue 1|"
    r"champions league|ucl|europa league|mls|major league soccer|"
    r"world cup|copa america|copa libertadores|liga mx|"
    r"euro 20\d{2}|euros 20\d{2}|european championship"
    r")\b",
    re.IGNORECASE,
)

_SPORTS_PERSONNEL_RE = re.compile(
    r"\b("
    r"fired|fire|resign|resignation|step down|retire|retirement|"
    r"hired|hire|traded|suspended|suspension|benched|cut|released"
    r")\b",
    re.IGNORECASE,
)

_SPORTS_CONTEXT_RE = re.compile(
    r"\b("
    r"nba|wnba|nfl|mlb|nhl|ufc|pga|mls|epl|team|coach|player|manager|"
    r"next game|patriots|lakers|yankees|knicks|celtics|dodgers|cowboys"
    r")\b",
    re.IGNORECASE,
)

_OUTBREAK_RE = re.compile(
    r"\b("
    r"hantavirus|outbreak|pandemic|epidemic|bird flu|avian flu|h5n1|"
    r"covid|measles|ebola|mpox|fda|drug approval|vaccine"
    r")\b",
    re.IGNORECASE,
)

_COMPELLING_RE = re.compile(
    r"\b("
    r"war|invade|invasion|strike|ceasefire|peace deal|treaty|coup|"
    r"revolution|overthrow|regime|taiwan|ukraine|israel|iran|russia|china|"
    r"president|presidential|election|nominee|fed\s+(?:decision|rate|fund|cut|hike)|recession|rate cut|"
    r"hurricane|tornado|earthquake|wildfire|flood|"
    r"openai|gpt|claude|ai model|deepseek|gemini|ipo|bankrupt|earnings|"
    r"bitcoin|btc|ethereum|eth|crypto|"
    r"taylor swift|beyonce|drake|kardashian|musk|sam altman|pope|nobel|"
    r"super bowl|world cup|champions league|masters|olympics|"
    r"wimbledon|french open|australian open|us open|grand slam|"
    r"ufc \d{3,}|ufc.*(title|champion)|"
    r"nba finals?|wnba finals?|stanley cup|world series"
    r")\b",
    re.IGNORECASE,
)

_PUBLIC_COMPANY_RE = re.compile(
    r"\b("
    r"nvidia|nvda|tesla|tsla|apple|aapl|microsoft|msft|google|alphabet|googl|"
    r"amazon|amzn|meta|netflix|nflx|openai|anthropic|spacex|rocket lab|rklb|"
    r"wendy's|wen|fidelity national|fis|gamestop|gme|freeport|d-wave"
    r")\b",
    re.IGNORECASE,
)

_CULTURE_RE = re.compile(
    r"\b("
    r"super bowl|eurovision|survivor|academy|emmy|grammy|billboard|spotify|"
    r"album|song|movie|box office|oscars?|rott?en tomatoes|kimmel|taylor swift|"
    r"beyonce|drake|kardashian|iceman|pregnan(?:t|cy)|baby|bridesmaids?|"
    r"wedding|engaged|engagement|married|divorce"
    r")\b",
    re.IGNORECASE,
)

_WEIRD_NEWS_RE = re.compile(
    r"\b("
    r"apologize|arrested|aliens?|ufo|pope|nobel|jail|prison|pardon|"
    r"resign|fired|fire|scandal|banned"
    r")\b",
    re.IGNORECASE,
)

_ABSURD_BUT_REAL_RE = re.compile(
    r"\b("
    r"aliens?|ufo|extraterrestrial|bigfoot|loch ness|simulation|"
    r"will .+ apologize|will .+ say \"|what will .+ wear|"
    r"hot dog|nathan's|meme|memecoin|pregnan(?:t|cy)|"
    r"bridesmaids?|wedding|engaged|engagement|married|divorce"
    r")\b",
    re.IGNORECASE,
)

_BREAKING_NEWS_RE = re.compile(
    r"\b("
    r"diplomatic meeting|peace deal|nuclear deal|airspace|"
    r"ceasefire talks?|hostage deal|summit|visit china|surrender"
    r")\b",
    re.IGNORECASE,
)

_COMPANY_DRAMA_RE = re.compile(
    r"\b("
    r"lawsuit|case against|sue|sues|acquire|acquisition|merger|"
    r"bankrupt|bankruptcy|ipo|take a stake|antitrust|sec investigation"
    r")\b",
    re.IGNORECASE,
)

_BIG_NAME_RE = re.compile(
    r"\b("
    r"trump|biden|obama|musk|elon|sam altman|taylor swift|beyonce|"
    r"drake|kardashian|pope|putin|zelensky|xi jinping|netanyahu"
    r")\b",
    re.IGNORECASE,
)

_RUSSIA_WAR_TERRITORY_RE = re.compile(
    r"\b(russia|russian)\b.*\b("
    r"captur\w*|seiz\w*|occup\w*|annex\w*|advanc\w*|enter\w*|offensive|"
    r"territor\w*|frontline|oblast|donbas|donetsk|luhansk|kharkiv|sumy|"
    r"zaporizhzhia|zaporizhia|kherson|crimea|odesa|odessa|dnipro|pokrovsk|chasyv yar|kupiansk"
    r")\b",
    re.IGNORECASE,
)

_STOPWORDS = {
    "will",
    "the",
    "a",
    "an",
    "to",
    "of",
    "in",
    "on",
    "by",
    "at",
    "for",
    "be",
    "is",
    "are",
    "and",
    "or",
    "with",
    "between",
    "above",
    "below",
    "over",
    "under",
    "than",
    "next",
    "this",
    "month",
    "week",
    "day",
}

_GENERIC_HEADLINES = {
    None,
    "",
    "Big odds movement",
    "Odds moving",
    "Odds shifted",
    "Big shift from opening",
    "New favorite",
    "Resolving soon",
    "Resolving this month",
    "Multi-source",
}


@dataclass(frozen=True)
class MarketQuality:
    quality_class: QualityClass
    family_key: str
    story_key: str | None = None
    reasons: list[str] = field(default_factory=list)
    is_ladder_or_bucket: bool = False
    is_narrow_range: bool = False
    has_named_salient_entity: bool = False
    explanation_required: bool = False


def _normalized_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
    # Preserve #N ranking patterns (e.g., "#1 Netflix Show" vs "#2 Netflix
    # Show") so that different rankings get distinct family keys. Without
    # this, both collapse to "<num> netflix show" and dedup kills one.
    # Use a non-numeric placeholder so the subsequent <num> pass won't eat it.
    text = re.sub(
        r"#(\d{1,2})\b",
        lambda m: (
            f"<rank{_RANK_WORDS[int(m.group(1))]}>"
            if int(m.group(1)) in _RANK_WORDS
            else "<rankother>"
        ),
        text,
    )
    text = re.sub(r"\$?\d+(?:,\d{3})*(?:\.\d+)?%?", "<num>", text)
    text = re.sub(rf"\b({_MONTH_RE})\b", "<month>", text)
    text = re.sub(r"\b\d{4}\b", "<year>", text)
    text = re.sub(r"[^a-z0-9<>]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _numbers(text: str) -> list[float]:
    vals: list[float] = []
    for match in _NUMBER_RE.findall(text):
        cleaned = match.replace("$", "").replace(",", "").replace("%", "")
        try:
            vals.append(float(cleaned))
        except ValueError:
            continue
    return vals


def _is_narrow_range(text: str) -> bool:
    vals = _numbers(text)
    if len(vals) < 2:
        return False
    for a, b in zip(vals, vals[1:]):
        lo, hi = sorted((abs(a), abs(b)))
        if hi == 0:
            continue
        width = hi - lo
        if width <= 1.0 or width / hi <= 0.02:
            return True
    return False


def _has_named_salient_entity(name: str) -> bool:
    # Proper-case words are a useful salience hint for people, teams, companies,
    # places, and diseases. Exclude title-case boilerplate by requiring either
    # multiple proper tokens or a known high-salience pattern.
    proper_tokens = re.findall(r"\b[A-Z][a-z]{2,}\b", name)
    filtered = [t for t in proper_tokens if t.lower() not in _STOPWORDS]
    return len(filtered) >= 2 or bool(
        _COMPELLING_RE.search(name) or _OUTBREAK_RE.search(name)
    )


def _story_key(name: str, category: str) -> str | None:
    lower = name.lower()

    if re.search(
        r"\b(iran|iranian|israel|hormuz|uranium|enrichment|nuclear deal|airspace|gaza)\b",
        lower,
    ):
        return "story:middle_east_conflict"

    if ("russia" in lower and "ukraine" in lower) or _RUSSIA_WAR_TERRITORY_RE.search(
        name
    ):
        return "story:russia_ukraine"

    if "russia" in lower and re.search(
        r"\b(putin|president|regime|fall|collapse)\b", lower
    ):
        return "story:russia_ukraine"

    if "2028" in lower and re.search(
        r"\b(president|presidential|nominee|election)\b", lower
    ):
        return "story:us_2028_election"

    if _REGIONAL_US_ELECTION_RE.search(name) and not re.search(
        r"\bpresidential\b", lower
    ):
        return "story:regional_us_elections"

    if re.search(r"\b((mayoral|mayor)\s+election|mayor\s+winner)\b", lower):
        return "story:regional_us_elections"

    if re.search(r"\b(fed|rate cuts?|interest rates?|inflation|cpi|ppi|ecb)\b", lower):
        return "story:macro_rates"

    if re.search(r"\b(beat|miss|report|quarterly)\b.*\bearnings\b", lower) or re.search(
        r"\bearnings\b.*\b(beat|miss|report|quarterly)\b", lower
    ):
        return "story:single_stock_earnings"

    if re.search(r"\b(wti|crude oil|brent oil|oil)\b", lower):
        return "story:oil"

    if re.search(r"\b(aliens?|ufo|extraterrestrial)\b", lower):
        return "story:aliens_disclosure"

    if "spacex" in lower and re.search(r"\b(ipo|public|bank)\b", lower):
        return "story:spacex_ipo"

    if "spacex" in lower and re.search(r"\b(starship|launch|launches)\b", lower):
        return "story:spacex_launches"

    if "ipo" in lower:
        return "story:ipo_markets"

    if re.search(r"\b(spotify|billboard)\b", lower):
        return "story:music_charts"

    if _DAILY_EQUITY_DIRECTION_RE.search(name):
        return "story:daily_equity_direction"

    if re.search(r"\b(nba finals?|wnba finals?)\b", lower):
        return "story:basketball_finals_path"

    if re.search(r"\b(fifa\s+)?world cup\b", lower):
        return "story:fifa_world_cup"

    if re.search(r"\bufc\s+\d{3,}\b", lower) or re.search(
        r"\bufc\b.*\b(title|champion|main event)\b", lower
    ):
        return "story:ufc_events"

    if re.search(
        r"\b(wimbledon|french open|australian open|roland garros|grand slam)\b", lower
    ):
        return "story:grand_slam_tennis"

    # "US Open" is tennis when the category is tennis (not golf)
    if category == "tennis" and re.search(r"\bus open\b", lower):
        return "story:grand_slam_tennis"

    if re.search(r"\b(openai|gpt|claude|deepseek|gemini|ai model|best ai)\b", lower):
        return "story:ai"

    if re.search(r"\b(met gala|oscars?|academy awards?|grammys?|emmys?)\b", lower):
        return "story:major_entertainment_events"

    if re.search(
        r"\b(attorney general|fbi director|save act|cabinet|supreme court|nomination|confirmed)\b",
        lower,
    ):
        return "story:us_federal_power"

    if category == "entertainment" and re.search(r"\b(drake|iceman)\b", lower):
        return "story:drake_iceman"

    if re.search(r"\bfederal government\b.*\btake a stake\b", lower):
        return "story:us_government_stakes"

    if "truist championship" in lower:
        return "story:golf_truist_championship"

    if _LOW_SIGNAL_SPORT_RE.search(name):
        return "story:niche_low_signal_sports"

    if category == "soccer" and not _TOP_TIER_SOCCER_RE.search(name):
        return "story:minor_soccer_leagues"

    return None


def classify_market_quality(
    market_name: str | None,
    sport_category: str | None = None,
    outcome_names: list[str] | None = None,
    external_id: str | None = None,
    persisted_story_key: str | None = None,
    status: str | None = None,
) -> MarketQuality:
    """Classify whether a futures market is good generic Discover material."""
    name = market_name or ""
    category = (sport_category or "").lower()
    outcome_names = outcome_names or []
    reasons: list[str] = []
    ticker = (external_id or "").upper()

    normalized = _normalized_text(name)
    has_salient = _has_named_salient_entity(name)
    is_narrow = _is_narrow_range(name)

    ticker_suppress = any(ticker.startswith(p) for p in _SUPPRESS_TICKER_PREFIXES) if ticker else False
    ticker_boost = any(ticker.startswith(p) for p in _BOOST_TICKER_PREFIXES) if ticker else False
    if ticker_suppress:
        reasons.append("ticker_suppress")
    if ticker_boost:
        reasons.append("ticker_boost")

    asset_price_level = _is_asset_price_level(name)  # R2
    runner_up_rank = _is_runner_up_rank(name)  # R8
    resolved_sports = _is_resolved_sports(status, category)  # R6
    novel_sports = _is_novel_sports_framing(name, category)  # R3
    price_bucket = bool(
        _PRICE_BUCKET_RE.search(name)
        or _COMMODITY_DATED_PRICE_RE.search(name)
        or _DATED_FINANCE_METRIC_RE.search(name)
        or asset_price_level
    )
    weather_bucket = bool(_WEATHER_BUCKET_RE.search(name))
    daily_equity_direction = bool(_DAILY_EQUITY_DIRECTION_RE.search(name))
    social_filler = bool(_SOCIAL_FILLER_RE.search(name))
    entertainment_metric = bool(_ENTERTAINMENT_METRIC_RE.search(name))
    obscure = bool(_OBSCURE_PROCEDURAL_RE.search(name))
    regional_election = (
        bool(_REGIONAL_US_ELECTION_RE.search(name))
        or bool(
            re.search(
                r"\b((mayoral|mayor)\s+election|mayor\s+winner)\b",
                name,
                re.IGNORECASE,
            )
        )
    ) and not re.search(
        r"\b(president|presidential|trump|biden|obama|2028)\b",
        name,
        re.IGNORECASE,
    )
    low_signal_sport = bool(_LOW_SIGNAL_SPORT_RE.search(name))
    episode_level = bool(_EPISODE_LEVEL_RE.search(name))

    # Margin-of-victory + voter-turnout: hard-exclude both families (Alex
    # 2026-06-24), carving out only US presidential turnout.
    margin_turnout = (
        bool(_ELECTION_MARGIN_RE.search(name))
        or bool(_VOTER_TURNOUT_RE.search(name))
        or bool(_MARGIN_TURNOUT_TICKER_RE.search(ticker))
    )
    margin_turnout_excluded = margin_turnout and not _is_us_presidential_turnout(name)
    if margin_turnout_excluded:
        reasons.append("margin_turnout_excluded")

    # Artist annual stream-count ladder: hard-exclude (Lane 2 L2-2, 2026-06-24).
    stream_count_excluded = bool(_STREAM_COUNT_RE.search(name)) or bool(
        _STREAM_COUNT_TICKER_RE.search(ticker)
    )
    if stream_count_excluded:
        reasons.append("stream_count_excluded")

    # Vote-percent ladders + individual House-district winners: hard-exclude
    # (Alex 2026-06-24, Lane 2 L2-3). Chamber-control / major races are NOT
    # matched (no district code / no "vote percent" / different ticker).
    vote_percent_excluded = bool(_VOTE_PERCENT_RE.search(name)) or bool(
        _VOTE_PERCENT_TICKER_RE.search(ticker)
    )
    if vote_percent_excluded:
        reasons.append("vote_percent_excluded")
    house_district_excluded = bool(_HOUSE_DISTRICT_RE.search(name)) or bool(
        _HOUSE_DISTRICT_TICKER_RE.search(ticker)
    )
    if house_district_excluded:
        reasons.append("house_district_excluded")

    # Nonfarm-payrolls jobs ladder: hard-exclude; GDP stays eligible (Alex
    # 2026-06-24, Lane 2 L2-4).
    payrolls_excluded = bool(_PAYROLLS_RE.search(name)) or bool(
        _PAYROLLS_TICKER_RE.search(ticker)
    )
    if payrolls_excluded:
        reasons.append("payrolls_excluded")

    ladder_or_bucket = price_bucket or weather_bucket
    if ladder_or_bucket:
        reasons.append("ladder_or_bucket")
    if is_narrow:
        reasons.append("narrow_range")
    if social_filler:
        reasons.append("social_filler")
    if daily_equity_direction:
        reasons.append("daily_equity_direction")
    if entertainment_metric:
        reasons.append("entertainment_metric")
    if obscure:
        reasons.append("obscure_procedural")
    if regional_election:
        reasons.append("regional_us_election")
    if low_signal_sport:
        reasons.append("low_signal_sport")
    if episode_level:
        reasons.append("episode_level")
    if asset_price_level:
        reasons.append("asset_price_level")
    if runner_up_rank:
        reasons.append("runner_up_rank")
    if resolved_sports:
        reasons.append("resolved_sports")
    if novel_sports:
        reasons.append("novel_sports_framing")

    compelling = bool(_COMPELLING_RE.search(name))
    personnel = _has_sports_personnel_context(name, category) and has_salient
    outbreak = bool(_OUTBREAK_RE.search(name))
    absurd_public_interest = bool(_ABSURD_BUT_REAL_RE.search(name))
    if compelling:
        reasons.append("compelling_topic")
    if personnel:
        reasons.append("sports_personnel_story")
    if outbreak:
        reasons.append("health_outbreak")
    if absurd_public_interest:
        reasons.append("absurd_but_real")
    if has_salient:
        reasons.append("salient_entity")

    # Outcome-only ladders: many numeric outcomes with the same market shell.
    numeric_outcomes = sum(1 for o in outcome_names if _NUMBER_RE.search(o or ""))
    if len(outcome_names) >= 4 and numeric_outcomes / max(len(outcome_names), 1) >= 0.7:
        ladder_or_bucket = True
        reasons.append("numeric_outcome_ladder")

    if social_filler or (obscure and not compelling) or resolved_sports:
        # R6: resolved sports never surface as live cards.
        quality: QualityClass = "suppress"
    elif margin_turnout_excluded:
        # Alex 2026-06-24: margin-of-victory + voter-turnout flood, hard-excluded.
        quality = "suppress"
    elif stream_count_excluded:
        # Lane 2 L2-2: artist annual stream-count ladder, hard-excluded.
        quality = "suppress"
    elif vote_percent_excluded or house_district_excluded:
        # Lane 2 L2-3 (Alex 2026-06-24): vote-percent ladders + individual
        # House-district winner markets, hard-excluded (chamber-control and
        # major races stay eligible — not matched here).
        quality = "suppress"
    elif payrolls_excluded:
        # Lane 2 L2-4 (Alex 2026-06-24): nonfarm-payrolls jobs ladder,
        # hard-excluded. GDP / Fed / CPI stay eligible (not matched here).
        quality = "suppress"
    elif ticker_suppress:
        quality = "low_quality"
    elif (
        obscure
        or daily_equity_direction
        or entertainment_metric
        or regional_election
        or low_signal_sport
        or episode_level
        or asset_price_level  # R2: asset price-levels are never interesting
        or runner_up_rank  # R8: non-#1 ranking markets
    ):
        quality = "low_quality"
    elif (price_bucket or weather_bucket) and (is_narrow or not compelling):
        quality = "low_quality"
    elif (
        ticker_boost
        or personnel
        or outbreak
        or compelling
        or absurd_public_interest
        or novel_sports  # R3: novel nationality/region/aggregate sports framing
    ):
        quality = "compelling"
    else:
        quality = "normal"

    family_key = normalized
    if entertainment_metric:
        if re.search(r"streams up this week|weekly streams", name, re.IGNORECASE):
            family_key = "entertainment:streaming_metric"
        elif re.search(r"billboard|weekly top|spotify", name, re.IGNORECASE):
            family_key = "entertainment:chart_metric"
        else:
            family_key = "entertainment:metric"
    if ladder_or_bucket:
        family_key = re.sub(r"<num>(?:\s*(?:to|and|-)\s*<num>)+", "<range>", normalized)
        family_key = re.sub(r"<num>", "<num>", family_key)
    if not family_key:
        family_key = "unknown"
    story_key = persisted_story_key or _story_key(name, category)

    return MarketQuality(
        quality_class=quality,
        family_key=family_key,
        story_key=story_key,
        reasons=reasons,
        is_ladder_or_bucket=ladder_or_bucket,
        is_narrow_range=is_narrow,
        has_named_salient_entity=has_salient,
        explanation_required=quality in ("compelling", "normal"),
    )


def quality_score_adjustment(quality: MarketQuality) -> int:
    """Score adjustment applied after highlight scoring."""
    if quality.quality_class == "compelling":
        boost = 12
        if "health_outbreak" in quality.reasons:
            boost += 12
        if "sports_personnel_story" in quality.reasons:
            boost += 10
        if "absurd_but_real" in quality.reasons:
            boost += 8
        return boost
    if quality.quality_class == "low_quality":
        penalty = -35
        if quality.is_narrow_range:
            penalty -= 15
        return penalty
    if quality.quality_class == "suppress":
        return -100
    return 0


def editorial_archetype(
    market_name: str | None,
    sport_category: str | None = None,
) -> EditorialArchetype:
    """Classify a market into the editorial role it can play in Discover."""
    name = market_name or ""
    category = (sport_category or "").lower()
    text = f"{name} {category}"

    if _ABSURD_BUT_REAL_RE.search(text):
        return "absurd_but_real"
    if _OUTBREAK_RE.search(text) or re.search(
        r"\b(hurricane|tornado|earthquake|wildfire|flood|rain|snow)\b", text, re.I
    ):
        return "health_weather_risk"
    if _has_sports_personnel_context(name, category):
        return "sports_drama"
    if _BREAKING_NEWS_RE.search(text) and re.search(
        r"\b(iran|israel|russia|ukraine|china|trump|gaza|taiwan|nuclear)\b", text, re.I
    ):
        return "breaking_news"
    if re.search(
        r"\b(war|invade|invasion|ceasefire|peace|regime|taiwan|ukraine|israel|iran|russia|china|cuba|venezuela)\b",
        text,
        re.I,
    ):
        return "world_event"
    if _COMPANY_DRAMA_RE.search(text) and (
        _PUBLIC_COMPANY_RE.search(text)
        or re.search(
            r"\b(openai|spacex|anthropic|tesla|apple|google|meta|amazon|nvidia)\b",
            text,
            re.I,
        )
    ):
        return "company_drama"
    if re.search(
        r"\b(openai|anthropic|claude|gpt|ai model|frontiermath|deepseek|gemini|nvidia|compute)\b",
        text,
        re.I,
    ):
        return "tech_frontier"
    if re.search(
        r"\b(fed|rate cut|recession|inflation|cpi|ppi|earnings|oil|wti|treasury|yield)\b",
        text,
        re.I,
    ):
        return "macro_signal"
    if _CULTURE_RE.search(text) or category == "entertainment":
        return "culture_moment"
    if category in {
        "golf",
        "football",
        "basketball",
        "baseball",
        "hockey",
        "soccer",
        "tennis",
        "chess",
        "squash",
    }:
        return "sports_story"
    if re.search(
        r"\b(pga|tour|championship|top 20|world cup|champions league|nba|nfl|mlb|nhl|ufc|wimbledon|french open|australian open|us open|grand slam)\b",
        text,
        re.I,
    ):
        return "sports_story"
    if _PUBLIC_COMPANY_RE.search(text):
        return "big_public_company"
    if _BIG_NAME_RE.search(text) and category not in {"politics", "geopolitics"}:
        return "big_name"
    if category in {"politics", "geopolitics"} or re.search(
        r"\b(president|senate|house|governor|mayor|election|nominee|confirmed)\b",
        text,
        re.I,
    ):
        return "political_power"
    if _WEIRD_NEWS_RE.search(text):
        return "weird_news"
    return "other"


def _has_sports_personnel_context(name: str, category: str) -> bool:
    """Return true for personnel verbs only in sports contexts."""
    text = f"{name} {category}"
    if not _SPORTS_PERSONNEL_RE.search(text):
        return False
    return category in {
        "golf",
        "football",
        "basketball",
        "baseball",
        "hockey",
        "soccer",
        "tennis",
        "chess",
        "squash",
        "mma",
    } or bool(_SPORTS_CONTEXT_RE.search(text))


def _discover_category_group(item: dict) -> str:
    data = item.get("data") or {}
    category = (
        data.get("llm_sport_category")
        or data.get("sport_name")
        or data.get("sport")
        or ""
    ).lower()
    if item.get("type") in ("event", "tournament", "concept"):
        # Golf tournament cards and UFC/F1 concept cards carry no
        # llm_sport_category / sport on their payload, so without this they fall
        # through to the "other" bucket and escape the sports first-page cap,
        # letting a single sport (e.g. golf during a major week) flood Discover
        # (#1087). Bucket them with sports the same way event cards are.
        return "sports_culture"
    if category in {"weather", "health"}:
        return "weather_health"
    if category in {"politics", "geopolitics", "economics", "tech", "entertainment"}:
        return category
    if category in {
        "golf",
        "football",
        "basketball",
        "baseball",
        "hockey",
        "soccer",
        "tennis",
        "chess",
        "squash",
        "mma",
        "cricket",
    }:
        return "sports_culture"
    return "other"


def _discover_event_sport_group(item: dict) -> str:
    """Return the broad sport bucket for a Discover event card."""
    data = item.get("data") or {}
    sport = (data.get("sport") or data.get("sport_name") or "").lower()
    if "soccer" in sport or sport.startswith(("epl", "mls")):
        return "soccer"
    if "baseball" in sport or sport.startswith("mlb"):
        return "baseball"
    if "basketball" in sport or sport.startswith(("nba", "wnba")):
        return "basketball"
    if "football" in sport or sport.startswith(("nfl", "ncaaf")):
        return "football"
    if "hockey" in sport or sport.startswith("nhl"):
        return "hockey"
    if "golf" in sport or sport.startswith("pga"):
        return "golf"
    if "tennis" in sport:
        return "tennis"
    if "mma" in sport or "ufc" in sport:
        return "mma"
    if "racing" in sport or "nascar" in sport or "f1" in sport:
        return "racing"
    if "cricket" in sport:
        return "cricket"
    return "other"


_DISCOVER_EVENT_SPORT_CAPS = {
    "soccer": 5,
    "baseball": 5,
    "basketball": 6,
    "football": 6,
    "hockey": 5,
    "golf": 4,
    "tennis": 3,
    "mma": 3,
    "racing": 3,
    "cricket": 2,
    "other": 3,
}


def balance_discover_event_category_mix(items: list[dict]) -> list[dict]:
    """Defer repetitive or low-scoring sports events behind futures in Discover.

    This is a pure reorder pass: scores and card data are unchanged. It keeps
    live/high-interest sports in the feed while preventing one event bucket
    from filling the long tail after first-page caps have done their work.
    """
    if not items:
        return items

    kept: list[dict] = []
    deferred_events: list[dict] = []
    event_counts: dict[str, int] = {}

    for item in items:
        if item.get("type") != "event":
            kept.append(item)
            continue

        sport_group = _discover_event_sport_group(item)
        cap = _DISCOVER_EVENT_SPORT_CAPS.get(sport_group, 3)
        score = float(item.get("score") or 0)
        if score < 50 or event_counts.get(sport_group, 0) >= cap:
            deferred_events.append(item)
            continue

        event_counts[sport_group] = event_counts.get(sport_group, 0) + 1
        kept.append(item)

    return kept + deferred_events


_DISCOVER_FIRST_PAGE_CATEGORY_CAPS = {
    "politics": 5,
    "geopolitics": 3,
    "economics": 4,
    "tech": 3,
    "entertainment": 3,
    "weather_health": 2,
    "sports_culture": 3,
    "other": 3,
}

_DISCOVER_FIRST_PAGE_ARCHETYPE_CAPS = {
    "world_event": 4,
    "breaking_news": 3,
    "political_power": 3,
    "macro_signal": 4,
    "culture_moment": 3,
    "health_weather_risk": 2,
    "sports_story": 3,
    "sports_drama": 2,
    "tech_frontier": 2,
    "big_public_company": 2,
    "company_drama": 2,
    "big_name": 2,
    "weird_news": 2,
    "absurd_but_real": 3,
    "other": 3,
}

_DISCOVER_REQUIRED_ARCHETYPES: tuple[EditorialArchetype, ...] = (
    "tech_frontier",
    "culture_moment",
    "health_weather_risk",
    "sports_story",
    "sports_drama",
    "weird_news",
    "absurd_but_real",
)


def diversify_discover_first_page(
    items: list[dict],
    *,
    first_page_size: int = 20,
    cold_start: bool = False,
) -> list[dict]:
    """Reorder the first Discover page so it feels curated, not clustered.

    When cold_start=True (empty personalization context), tighten category caps
    to 2 for the first 8 cards, ensuring >= 5 distinct category groups appear
    before any category repeats heavily. This makes the first page informative
    for new users without adding friction (#850).
    """
    if first_page_size <= 0 or len(items) <= 1:
        return items

    target_size = min(first_page_size, len(items))
    category_counts: dict[str, int] = {}
    archetype_counts: dict[str, int] = {}
    story_counts: dict[str, int] = {}

    cold_start_cap = 2 if cold_start else None

    def can_select(item: dict, *, enforce_archetype: bool, enforce_story: bool) -> bool:
        group = _discover_category_group(item)
        cap = _DISCOVER_FIRST_PAGE_CATEGORY_CAPS.get(group, 3)
        if cold_start_cap is not None and len([s for s in category_counts.values()]) < 8:
            cap = min(cap, cold_start_cap)
        if category_counts.get(group, 0) >= cap:
            return False

        if enforce_archetype:
            archetype = _discover_archetype_group(item)
            if archetype_counts.get(
                archetype, 0
            ) >= _DISCOVER_FIRST_PAGE_ARCHETYPE_CAPS.get(archetype, 3):
                return False

        if enforce_story:
            story_key = item.get("_quality_story_key")
            if story_key and story_counts.get(story_key, 0) >= 2:
                return False

        return True

    def record(item: dict) -> None:
        group = _discover_category_group(item)
        archetype = _discover_archetype_group(item)
        story_key = item.get("_quality_story_key")
        category_counts[group] = category_counts.get(group, 0) + 1
        archetype_counts[archetype] = archetype_counts.get(archetype, 0) + 1
        if story_key:
            story_counts[story_key] = story_counts.get(story_key, 0) + 1

    selected: list[dict] = []
    selected_keys: set[tuple] = set()

    for enforce_archetype, enforce_story in (
        (True, True),
        (True, False),
        (False, False),
    ):
        for item in items:
            if len(selected) >= target_size:
                break
            key = _feed_item_key(item)
            if key in selected_keys:
                continue
            if not can_select(
                item, enforce_archetype=enforce_archetype, enforce_story=enforce_story
            ):
                continue
            selected.append(item)
            selected_keys.add(key)
            record(item)
        if len(selected) >= target_size:
            break

    if len(selected) < target_size:
        # #1090: fill remaining first-page slots with PROGRESSIVE cap relaxation,
        # not a blind sorted append. On a thin/clustered slate (The Open golf week
        # + summer break) the old fallback dumped whatever sorted highest — golf,
        # re-boosted to the top for a golf-affinity user — straight into the first
        # page, wiping out category diversity. Relax the per-category cap in steps
        # (+2, +5, then unbounded) so one category can flood the page only as an
        # absolute last resort, keeping >=4 categories visible up top.
        for relaxed_extra in (2, 5, None):
            if len(selected) >= target_size:
                break
            for item in items:
                if len(selected) >= target_size:
                    break
                key = _feed_item_key(item)
                if key in selected_keys:
                    continue
                if relaxed_extra is not None:
                    group = _discover_category_group(item)
                    cap = _DISCOVER_FIRST_PAGE_CATEGORY_CAPS.get(group, 3) + relaxed_extra
                    if category_counts.get(group, 0) >= cap:
                        continue
                selected.append(item)
                selected_keys.add(key)
                record(item)

    _ensure_required_archetypes(selected, items)
    _ensure_category_hunger(selected, items)
    _improve_strict_variety(selected, items)

    selected_keys = {_feed_item_key(item) for item in selected}
    remainder = [
        item
        for item in items
        if _feed_item_key(item) not in selected_keys and item not in selected
    ]
    return selected + remainder


_DISCOVER_TAIL_RECALL_RULES: tuple[tuple[str, re.Pattern[str], float], ...] = (
    ("survivor", re.compile(r"\bsurvivor\b", re.IGNORECASE), 88),
    ("music_charts", re.compile(r"\b(spotify|billboard)\b", re.IGNORECASE), 88),
    ("film_tv_scores", re.compile(r"\brotten tomatoes\b", re.IGNORECASE), 88),
    ("macro_recession", re.compile(r"\brecession\b", re.IGNORECASE), 88),
    ("china_leadership", re.compile(r"\bxi\s+jinping\b", re.IGNORECASE), 88),
    (
        "us_2028_presidential",
        re.compile(
            r"\b2028\b.*\b(presidential|president|nominee|election)\b", re.IGNORECASE
        ),
        90,
    ),
    (
        "us_civic_power",
        re.compile(
            r"\b(2026\s+midterms|congress\s+balance|los angeles mayor|"
            r"virginia redistricting referendum)\b",
            re.IGNORECASE,
        ),
        90,
    ),
    ("major_entertainment_events", re.compile(r"\bmet gala\b", re.IGNORECASE), 88),
    ("ai_frontier", re.compile(r"\bbest ai\b", re.IGNORECASE), 88),
    (
        "spacex_launches",
        re.compile(r"\bspacex\b.*\b(starship|launch|launches)\b", re.IGNORECASE),
        88,
    ),
    (
        "federal_power",
        re.compile(
            r"\b(attorney general|fbi director|save act|cabinet|supreme court)\b",
            re.IGNORECASE,
        ),
        86,
    ),
    (
        "shareable_life_story",
        re.compile(
            r"\b("
            r"bridesmaids?|wedding|engaged|engagement|married|divorce|"
            r"pregnan(?:t|cy)|baby"
            r")\b",
            re.IGNORECASE,
        ),
        86,
    ),
    ("fifa_world_cup", re.compile(r"\b(fifa\s+)?world cup\b", re.IGNORECASE), 82),
    ("ufc_events", re.compile(r"\bufc\b", re.IGNORECASE), 82),
    (
        "grand_slam_tennis",
        re.compile(
            r"\b(wimbledon|french open|australian open|roland garros|grand slam|us open)\b",
            re.IGNORECASE,
        ),
        82,
    ),
)


def backfill_discover_editorial_tail(
    items: list[dict],
    *,
    window_size: int = 50,
    preserve_top: int = 20,
    max_insertions: int = 6,
) -> list[dict]:
    """Pull a few high-texture eligible stories into the top-50 tail.

    Discover scoring often saturates at 100, so good but slightly less timely
    culture/macro stories can sit at rank 100+ behind many same-score finance
    and politics cards. This pass leaves the first page untouched and only
    swaps a small number of strong recall candidates into positions 21-50.
    """
    if window_size <= preserve_top or max_insertions <= 0 or len(items) <= window_size:
        return items

    selected = list(items[:window_size])
    remainder = list(items[window_size:])
    insertions = 0

    def item_name(item: dict) -> str:
        return str((item.get("data") or {}).get("name") or "")

    def matches_rule(item: dict, pattern: re.Pattern[str]) -> bool:
        return bool(pattern.search(item_name(item)))

    def is_recall_item(item: dict) -> bool:
        name = item_name(item)
        return any(
            pattern.search(name) for _, pattern, _ in _DISCOVER_TAIL_RECALL_RULES
        )

    def can_replace(item: dict, candidate: dict) -> bool:
        if is_recall_item(item):
            return False
        if float(item.get("score") or 0) > float(candidate.get("score") or 0) + 15:
            return False
        return True

    for _, pattern, min_score in _DISCOVER_TAIL_RECALL_RULES:
        if insertions >= max_insertions:
            break
        if any(matches_rule(item, pattern) for item in selected):
            continue

        candidate_idx = next(
            (
                idx
                for idx, item in enumerate(remainder)
                if matches_rule(item, pattern)
                and item.get("_quality_class") not in {"low_quality", "suppress"}
                and float(item.get("score") or 0) >= min_score
            ),
            None,
        )
        if candidate_idx is None:
            continue
        candidate = remainder[candidate_idx]

        replacement_idx = next(
            (
                idx
                for idx in range(window_size - 1, preserve_top - 1, -1)
                if can_replace(selected[idx], candidate)
            ),
            None,
        )
        if replacement_idx is None:
            continue

        removed = selected[replacement_idx]
        selected[replacement_idx] = candidate
        remainder.pop(candidate_idx)
        remainder.append(removed)
        insertions += 1

    return selected + remainder


def _ensure_category_hunger(selected: list[dict], all_items: list[dict]) -> None:
    """Give a strong missing category one first-page slot when possible."""
    if not selected:
        return

    selected_keys = {_feed_item_key(item) for item in selected}
    desired_thresholds = {
        "entertainment": 80,
        "tech": 90,
        "economics": 90,
        "weather_health": 90,
        "sports_culture": 90,
    }

    for target, min_score in desired_thresholds.items():
        if any(_discover_category_group(item) == target for item in selected):
            continue

        candidate = next(
            (
                item
                for item in all_items
                if _feed_item_key(item) not in selected_keys
                and _discover_category_group(item) == target
                and item.get("score", 0) >= min_score
            ),
            None,
        )
        if candidate is None:
            continue

        category_counts = Counter(_discover_category_group(item) for item in selected)
        archetype_counts = Counter(_discover_archetype_group(item) for item in selected)
        replacement_idx = next(
            (
                idx
                for idx in range(len(selected) - 1, -1, -1)
                if category_counts[_discover_category_group(selected[idx])] > 1
                and not (
                    _discover_archetype_group(selected[idx])
                    in _DISCOVER_REQUIRED_ARCHETYPES
                    and archetype_counts[_discover_archetype_group(selected[idx])] <= 1
                )
                and selected[idx].get("score", 0) <= candidate.get("score", 0) + 15
            ),
            None,
        )
        if replacement_idx is None:
            continue

        removed = selected[replacement_idx]
        selected[replacement_idx] = candidate
        selected_keys.discard(_feed_item_key(removed))
        selected_keys.add(_feed_item_key(candidate))


def _ensure_required_archetypes(selected: list[dict], all_items: list[dict]) -> None:
    """Make room for at least one strong card from key first-page textures."""
    selected_keys = {_feed_item_key(item) for item in selected}

    for target in _DISCOVER_REQUIRED_ARCHETYPES:
        if any(_discover_archetype_group(item) == target for item in selected):
            continue

        candidate = next(
            (
                item
                for item in all_items
                if _feed_item_key(item) not in selected_keys
                and _discover_archetype_group(item) == target
                and item.get("score", 0) >= 90
            ),
            None,
        )
        if candidate is None:
            continue

        archetype_counts = Counter(_discover_archetype_group(item) for item in selected)
        category_counts = Counter(_discover_category_group(item) for item in selected)
        replacement_idx = None
        for idx in range(len(selected) - 1, -1, -1):
            item = selected[idx]
            archetype = _discover_archetype_group(item)
            category = _discover_category_group(item)
            if (
                archetype in _DISCOVER_REQUIRED_ARCHETYPES
                and archetype_counts[archetype] <= 1
            ):
                continue
            if archetype_counts[archetype] <= 1 and category_counts[category] <= 1:
                continue
            replacement_idx = idx
            break

        if replacement_idx is None:
            continue

        removed = selected[replacement_idx]
        selected[replacement_idx] = candidate
        selected_keys.discard(_feed_item_key(removed))
        selected_keys.add(_feed_item_key(candidate))


def _improve_strict_variety(selected: list[dict], all_items: list[dict]) -> None:
    """Repair strict first-page texture targets after the initial score pass."""
    if len(selected) <= 1:
        return

    first_page_size = min(20, len(selected))

    def swap_positions(a: int, b: int) -> None:
        selected[a], selected[b] = selected[b], selected[a]

    fun_archetypes = {
        "culture_moment",
        "weird_news",
        "absurd_but_real",
        "big_name",
        "sports_drama",
    }

    # Keep at least four non-politics/geopolitics cards in the top 10 when
    # already-selected cards can satisfy that without dropping stronger stories.
    top10_size = min(10, len(selected))
    while top10_size >= 4:
        top10 = selected[:top10_size]
        non_political_count = sum(
            1
            for item in top10
            if _discover_category_group(item) not in {"politics", "geopolitics"}
        )
        if non_political_count >= 4:
            break

        replacement_idx = next(
            (
                idx
                for idx in range(top10_size - 1, -1, -1)
                if _discover_category_group(selected[idx])
                in {"politics", "geopolitics"}
            ),
            None,
        )
        candidate_idx = next(
            (
                idx
                for idx in range(top10_size, first_page_size)
                if _discover_category_group(selected[idx])
                not in {"politics", "geopolitics"}
                and selected[idx].get("score", 0) >= 90
            ),
            None,
        )
        if replacement_idx is None or candidate_idx is None:
            break
        swap_positions(replacement_idx, candidate_idx)

    # Guarantee the opening screen has one genuinely social/fun card when a
    # strong candidate exists. Sports_story does not count here; this lane is
    # for culture, celebrity, weird news, or big-name drama.
    top10 = selected[:top10_size]
    if not any(_discover_archetype_group(item) in fun_archetypes for item in top10):
        candidate_idx = next(
            (
                idx
                for idx in range(top10_size, first_page_size)
                if _discover_archetype_group(selected[idx]) in fun_archetypes
                and selected[idx].get("score", 0) >= 88
            ),
            None,
        )
        if candidate_idx is not None:
            replacement_idx = next(
                (
                    idx
                    for idx in range(top10_size - 1, -1, -1)
                    if _discover_archetype_group(selected[idx])
                    not in {
                        "breaking_news",
                        "health_weather_risk",
                    }
                ),
                top10_size - 1,
            )
            swap_positions(replacement_idx, candidate_idx)
        else:
            selected_keys = {_feed_item_key(item) for item in selected}
            candidate = next(
                (
                    item
                    for item in all_items
                    if _feed_item_key(item) not in selected_keys
                    and _discover_archetype_group(item) in fun_archetypes
                    and item.get("score", 0) >= 88
                ),
                None,
            )
            if candidate is not None and top10_size > 0:
                replacement_idx = top10_size - 1
                selected[replacement_idx] = candidate

    # Keep diplomatic clusters from exceeding the strict world-event cap in the
    # first 20. Prefer replacements already selected for the first page, then
    # pull a strong non-world candidate from the remainder if available.
    while True:
        first_page = selected[:first_page_size]
        world_count = sum(
            1 for item in first_page if _discover_archetype_group(item) == "world_event"
        )
        if world_count <= 4:
            break

        replacement_idx = next(
            (
                idx
                for idx in range(first_page_size - 1, -1, -1)
                if _discover_archetype_group(selected[idx]) == "world_event"
            ),
            None,
        )
        if replacement_idx is None:
            break

        selected_keys = {_feed_item_key(item) for item in selected}
        candidate_idx = next(
            (
                idx
                for idx in range(first_page_size, len(selected))
                if _discover_archetype_group(selected[idx]) != "world_event"
                and selected[idx].get("score", 0) >= 88
            ),
            None,
        )
        if candidate_idx is not None:
            swap_positions(replacement_idx, candidate_idx)
            continue

        candidate = next(
            (
                item
                for item in all_items
                if _feed_item_key(item) not in selected_keys
                and _discover_archetype_group(item) != "world_event"
                and item.get("score", 0) >= 88
            ),
            None,
        )
        if candidate is None:
            break
        selected[replacement_idx] = candidate


def _discover_archetype_group(item: dict) -> EditorialArchetype:
    if item.get("type") == "event":
        return "sports_story"
    data = item.get("data") or {}
    return editorial_archetype(
        data.get("name"),
        data.get("llm_sport_category") or data.get("sport_name") or data.get("sport"),
    )


def _feed_item_key(item: dict) -> tuple:
    data = item.get("data") or {}
    return (
        item.get("type"),
        data.get("id")
        or data.get("canonical_market_key")
        or data.get("name")
        or item.get("reason")
        or id(item),
    )


def apply_quality_score(raw_score: float, quality: MarketQuality) -> float:
    """Apply quality adjustment plus feed-facing score ceilings.

    The upstream futures scorer intentionally finds any market with a live
    signal, but many candidates saturate at 100. Discover needs more headroom:
    compelling stories can still max out, ordinary salient stories sit below
    them, and low-quality bucket families cannot tie the best cards.
    """
    if quality.quality_class == "suppress":
        return 0

    adjusted = max(0, raw_score + quality_score_adjustment(quality))

    if quality.quality_class == "compelling":
        return min(95, adjusted)

    if quality.quality_class == "low_quality":
        return min(65, adjusted)

    ceiling = 88 if quality.has_named_salient_entity else 82
    return min(ceiling, adjusted)


def has_strong_hook(hook_description: str | None) -> bool:
    """Return whether a hook is specific enough to improve a feed card."""
    hook = (hook_description or "").strip()
    if len(hook) < 48:
        return False
    words = re.findall(r"\b[\w'-]+\b", hook)
    if len(words) < 8:
        return False
    weak_phrases = (
        "this market is interesting",
        "this is interesting",
        "prediction market",
    )
    return not any(phrase in hook.lower() for phrase in weak_phrases)


def has_specific_explanation(
    *,
    hook_description: str | None,
    headline: str | None,
    quality: MarketQuality,
) -> bool:
    """Return whether a card has enough explanation to stand on its own."""
    if has_strong_hook(hook_description):
        return True
    if (
        "health_outbreak" in quality.reasons
        or "sports_personnel_story" in quality.reasons
    ):
        return True
    return headline not in _GENERIC_HEADLINES


def apply_explanation_quality_score(
    raw_score: float,
    *,
    hook_description: str | None,
    headline: str | None,
    quality: MarketQuality,
) -> float:
    """Boost strong hooks and cap weakly explained cards.

    The market can still appear without a hook, but generic "Big movement" or
    "New favorite" labels should not tie richly contextualized cards unless the
    topic is self-explanatory enough to carry itself.
    """
    if has_strong_hook(hook_description):
        return min(98, raw_score + 3)

    if has_specific_explanation(
        hook_description=hook_description,
        headline=headline,
        quality=quality,
    ):
        return raw_score

    if quality.quality_class == "compelling":
        return min(93, raw_score)
    if quality.quality_class == "normal":
        return min(80, raw_score)
    return min(60, raw_score)


def quality_score_rank(raw_score: float, quality: MarketQuality) -> float:
    """Uncapped ORDERING counterpart to `apply_quality_score` (#141/Item 1).

    Applies the same additive quality adjustment used for display, but omits the
    per-class display ceilings (95/88/82/65). Those ceilings intentionally shape
    the 0-98 DISPLAY number, but for ORDERING they collapse distinct high-signal
    cards onto the same value, so the feed sort falls back to a recency tiebreak.
    Tier separation still holds via the additive adjustment (compelling +12,
    low_quality -35, suppress -100). Suppressed markets floor at 0 (they are
    filtered before this runs; the invariant is kept for safety).
    """
    if quality.quality_class == "suppress":
        return 0.0
    return max(0.0, raw_score + quality_score_adjustment(quality))


def explanation_score_rank(
    raw_score: float,
    *,
    hook_description: str | None,
    headline: str | None,
    quality: MarketQuality,
) -> float:
    """Uncapped ORDERING counterpart to `apply_explanation_quality_score`.

    Strong hooks add +3; specific explanations are neutral. Weakly explained
    cards keep the per-class demotion ceilings (93/80/60) because that is a
    genuine quality penalty (weak cards must not outrank contextualized ones),
    not display saturation. #141/Item 1.
    """
    if has_strong_hook(hook_description):
        return raw_score + 3
    if has_specific_explanation(
        hook_description=hook_description,
        headline=headline,
        quality=quality,
    ):
        return raw_score
    if quality.quality_class == "compelling":
        return min(93, raw_score)
    if quality.quality_class == "normal":
        return min(80, raw_score)
    return min(60, raw_score)


def cap_low_quality_families(items: list[dict], cap: int = 1) -> list[dict]:
    """Cap low-quality ladder/bucket/story families after scoring.

    Items are expected to be sorted later by the caller; this helper sorts by
    score first to keep the strongest representative per family.
    """
    sorted_items = sorted(
        items,
        # Keep the strongest representative per family under the de-saturated
        # ordering score, falling back to display score. #141/Item 1.
        key=lambda x: (
            x.get("_rank_score", x.get("score", 0)),
            x.get("_sort_time", 0),
        ),
        reverse=True,
    )
    counts: dict[str, int] = {}
    kept: list[dict] = []
    for item in sorted_items:
        qclass = item.get("_quality_class")
        family = item.get("_quality_story_key") or item.get("_quality_family_key")
        if qclass == "low_quality" and family:
            count = counts.get(family, 0)
            if count >= cap:
                continue
            counts[family] = count + 1
        kept.append(item)
    return kept


def diversify_quality_families(
    items: list[dict],
    *,
    exact_family_cap: int = 1,
    story_family_cap: int = 5,
) -> list[dict]:
    """Cap repeated market/story families after scoring.

    This is intentionally separate from low-quality suppression: a hot story
    can still have several cards, but not enough near-duplicates to consume the
    whole first screen.
    """
    sorted_items = sorted(
        items,
        # Keep the strongest representative per family under the de-saturated
        # ordering score, falling back to display score. #141/Item 1.
        key=lambda x: (
            x.get("_rank_score", x.get("score", 0)),
            x.get("_sort_time", 0),
        ),
        reverse=True,
    )
    exact_counts: dict[str, int] = {}
    story_counts: dict[str, int] = {}
    kept: list[dict] = []
    per_story_caps = {
        "story:middle_east_conflict": 4,
        "story:russia_ukraine": 2,
        "story:us_2028_election": 2,
        "story:macro_rates": 3,
        "story:ai": 2,
        "story:aliens_disclosure": 2,
        "story:ipo_markets": 4,
        "story:spacex_launches": 3,
        "story:major_entertainment_events": 2,
        "story:us_federal_power": 3,
        "story:drake_iceman": 1,
        "story:music_charts": 1,
        "story:us_government_stakes": 2,
        "story:single_stock_earnings": 1,
        "story:golf_truist_championship": 3,
        "story:basketball_finals_path": 4,
        "story:fifa_world_cup": 3,
        "story:ufc_events": 3,
        "story:grand_slam_tennis": 3,
        "story:regional_us_elections": 1,
        "story:niche_low_signal_sports": 1,
        "story:minor_soccer_leagues": 1,
    }

    for item in sorted_items:
        family = item.get("_quality_family_key")
        story = item.get("_quality_story_key")

        if family and exact_family_cap > 0:
            count = exact_counts.get(family, 0)
            if count >= exact_family_cap:
                continue

        if story and story_family_cap > 0:
            count = story_counts.get(story, 0)
            cap = min(story_family_cap, per_story_caps.get(story, story_family_cap))
            if count >= cap:
                continue

        if family:
            exact_counts[family] = exact_counts.get(family, 0) + 1
        if story:
            story_counts[story] = story_counts.get(story, 0) + 1
        kept.append(item)

    return kept


# --- #490: confidence signal (1-3 bars) -------------------------------------
# A data-driven "how much do we trust this probability" score, derived ONLY
# from signals a feed candidate already carries: how many independent sources
# priced it, whether it has recent movement (live interest), whether real money
# traded, and — when measurable — whether the sources agree. Rendered as a 1-3
# bar signal glyph (Alex ruling 2026-07-23; cell-signal metaphor). Pure, like
# the rest of this module: no DB, no app imports. The frontend maps tier -> bars
# and its tooltip names these inputs, so the glyph is never unexplained chrome.

# Tier thresholds (see #490). Kept as constants — data-driven inputs, fixed
# cut points — so a re-calibration is a one-line change with a guard test.
CONFIDENCE_TIER_HIGH = 0.70
CONFIDENCE_TIER_MODERATE = 0.40

ConfidenceTier = Literal["high", "moderate", "low"]

# Signal weights (#490). When a signal is unavailable (e.g. source-agreement is
# not computable on a single-source market) its weight is dropped and the score
# renormalizes over the signals we DO have — so a well-sourced, actively-traded
# market can still reach "high" without every input present.
_CONF_W_SOURCES = 0.45
_CONF_W_MOVEMENT = 0.25
_CONF_W_VOLUME = 0.15
_CONF_W_AGREE = 0.15

# Source count saturates at 3: one source is thin, three-plus is a full bar.
_CONF_SOURCE_SATURATION = 3

# Cross-source agreement: independent sources "agree" when their home-prob spread
# is within this band (10 points). Used to populate the calibration-ready
# ``sources_agree`` signal (L2-172) — see ``cross_source_agreement``.
_CONF_AGREE_SPREAD = 0.10


def cross_source_agreement(
    probabilities: "list[float] | None",
    *,
    spread_threshold: float = _CONF_AGREE_SPREAD,
) -> "bool | None":
    """Do independent sources agree on the probability?

    ``True``/``False`` when there are >=2 numeric readings (agree = spread within
    ``spread_threshold``); ``None`` when agreement isn't measurable (0-1 readings)
    so the confidence signal drops it rather than guessing. Pure, like the rest of
    this module — the frontend mirrors it in ``lib/confidence.ts``.
    """
    vals = [
        float(p)
        for p in (probabilities or [])
        if isinstance(p, (int, float)) and not isinstance(p, bool)
    ]
    if len(vals) < 2:
        return None
    return (max(vals) - min(vals)) <= spread_threshold


def compute_confidence_score(
    *,
    source_count: "int | None",
    has_recent_movement: bool = False,
    has_volume: bool = False,
    sources_agree: "bool | None" = None,
) -> float:
    """Confidence (0.0-1.0) in a feed probability, from signals already present.

    Inputs (all optional except source_count, which is the backbone):
      - ``source_count``      how many independent sources priced this question
      - ``has_recent_movement`` a non-trivial 24h price change (live interest)
      - ``has_volume``        real money traded in the last 24h
      - ``sources_agree``     ``True``/``False`` when a cross-source spread is
                               measurable; ``None`` when it isn't (its weight is
                               then dropped and the rest renormalize).

    Returns 0.0 when there is no signal at all (no sources, nothing else).
    """
    sc = max(0, int(source_count or 0))
    components: list[tuple[float, float]] = [
        (
            min(sc, _CONF_SOURCE_SATURATION) / float(_CONF_SOURCE_SATURATION),
            _CONF_W_SOURCES,
        ),
        (1.0 if has_recent_movement else 0.0, _CONF_W_MOVEMENT),
        (1.0 if has_volume else 0.0, _CONF_W_VOLUME),
    ]
    if sources_agree is not None:
        components.append((1.0 if sources_agree else 0.0, _CONF_W_AGREE))

    total_weight = sum(w for _, w in components)
    if total_weight <= 0:
        return 0.0
    score = sum(value * weight for value, weight in components) / total_weight
    return round(max(0.0, min(1.0, score)), 4)


def confidence_tier(score: float) -> ConfidenceTier:
    """Map a 0-1 confidence score to a tier (high/moderate/low)."""
    if score >= CONFIDENCE_TIER_HIGH:
        return "high"
    if score >= CONFIDENCE_TIER_MODERATE:
        return "moderate"
    return "low"


# tier -> number of filled signal bars (out of 3). Single source of truth on the
# backend; the frontend keeps an identical map for the client-computed event hero.
CONFIDENCE_TIER_BARS: dict[str, int] = {"high": 3, "moderate": 2, "low": 1}


def confidence_signal(
    *,
    source_count: "int | None",
    has_recent_movement: bool = False,
    has_volume: bool = False,
    sources_agree: "bool | None" = None,
    has_closing_line: "bool | None" = None,
) -> "dict | None":
    """Build the feed-card confidence payload, or ``None`` when there's no signal.

    Returns ``{"score", "tier", "bars"}`` (plus an optional ``"signals"`` sub-dict).
    ``None`` (glyph absent) when we can't even count a single source — the frontend
    renders nothing rather than a misleading empty bar (#490 "render only where
    present").

    ``sources_agree`` (cross-source spread) and ``has_closing_line`` are recorded
    raw under ``"signals"`` for later calibration against labeled outcomes (the
    interestingness posture, L2-172). They are intentionally NOT fed into the live
    weighted score yet: today's tier stays driven by the three signals #490
    shipped (source count, recent movement, real volume), so the shipped
    distribution is frozen — weights untouched, signals populated. A future
    calibration decides their weight.
    """
    if not source_count:
        return None
    score = compute_confidence_score(
        source_count=source_count,
        has_recent_movement=has_recent_movement,
        has_volume=has_volume,
    )
    tier = confidence_tier(score)
    payload: dict = {"score": score, "tier": tier, "bars": CONFIDENCE_TIER_BARS[tier]}
    signals: dict = {}
    if sources_agree is not None:
        signals["sources_agree"] = bool(sources_agree)
    if has_closing_line is not None:
        signals["has_closing_line"] = bool(has_closing_line)
    if signals:
        payload["signals"] = signals
    return payload
