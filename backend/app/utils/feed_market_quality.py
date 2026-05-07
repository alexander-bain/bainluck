"""Market quality classification for Discover feed futures.

This module is intentionally pure: no database access and no app imports.
It identifies markets that are liquid or timely but poor feed material,
especially repetitive range/bucket ladders.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


QualityClass = Literal["compelling", "normal", "low_quality", "suppress"]


_MONTH_RE = (
    r"january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
)

_NUMBER_RE = re.compile(r"[-+]?\$?\d+(?:,\d{3})*(?:\.\d+)?%?")

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
    r"|(posts|tweets)\s+("
    + _MONTH_RE +
    r")"
    r"|white house #"
    r"|what will .+ (say|post) (during|this week|on truth)"
    r"|will .+ (say|post) \".+\""
    r"|who will .+ (talk to|speak to)"
    r"|how many people will .+ endorse"
    r"|weekly streams"
    r"|runner-up .+ on spotify"
    r"|net worth on ("
    + _MONTH_RE +
    r")"
    r")",
    re.IGNORECASE,
)

_ENTERTAINMENT_METRIC_RE = re.compile(
    r"\b("
    r"streams up this week|weekly streams|album equivalent units|"
    r"billboard hot 100|billboard 200|weekly top (songs|albums)|"
    r"top usa artist on spotify|top album on weekly|top song on weekly|"
    r"rank on the billboard|#\d+ on the billboard"
    r")\b",
    re.IGNORECASE,
)

_OBSCURE_PROCEDURAL_RE = re.compile(
    r"\b("
    r"reauthorize|committee|subcommittee|cloture|filibuster|"
    r"by-election|byelection|mayoral election|mayor election|"
    r"hackney|newham|lewisham|watford|doncaster|croydon|tower hamlets|"
    r"terrebone|chungche|andalusia|saxony|thuringia|hesse"
    r")\b",
    re.IGNORECASE,
)

_SPORTS_PERSONNEL_RE = re.compile(
    r"\b("
    r"fired|fire|resign|resignation|step down|retire|retirement|"
    r"hired|hire|traded|trade|suspended|suspension|benched|cut|released"
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
    r"president|presidential|election|nominee|fed|recession|rate cut|"
    r"hurricane|tornado|earthquake|wildfire|flood|"
    r"openai|gpt|claude|ai model|deepseek|gemini|ipo|bankrupt|earnings|"
    r"bitcoin|btc|ethereum|eth|crypto|"
    r"taylor swift|beyonce|drake|kardashian|musk|sam altman|pope|nobel|"
    r"super bowl|world cup|champions league|masters|olympics"
    r")\b",
    re.IGNORECASE,
)

_STOPWORDS = {
    "will", "the", "a", "an", "to", "of", "in", "on", "by", "at", "for",
    "be", "is", "are", "and", "or", "with", "between", "above", "below",
    "over", "under", "than", "next", "this", "month", "week", "day",
}


@dataclass(frozen=True)
class MarketQuality:
    quality_class: QualityClass
    family_key: str
    reasons: list[str] = field(default_factory=list)
    is_ladder_or_bucket: bool = False
    is_narrow_range: bool = False
    has_named_salient_entity: bool = False
    explanation_required: bool = False


def _normalized_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
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


def classify_market_quality(
    market_name: str | None,
    sport_category: str | None = None,
    outcome_names: list[str] | None = None,
) -> MarketQuality:
    """Classify whether a futures market is good generic Discover material."""
    name = market_name or ""
    category = (sport_category or "").lower()
    outcome_names = outcome_names or []
    reasons: list[str] = []

    normalized = _normalized_text(name)
    has_salient = _has_named_salient_entity(name)
    is_narrow = _is_narrow_range(name)

    price_bucket = bool(
        _PRICE_BUCKET_RE.search(name)
        or _COMMODITY_DATED_PRICE_RE.search(name)
        or _DATED_FINANCE_METRIC_RE.search(name)
    )
    weather_bucket = bool(_WEATHER_BUCKET_RE.search(name))
    social_filler = bool(_SOCIAL_FILLER_RE.search(name))
    entertainment_metric = bool(_ENTERTAINMENT_METRIC_RE.search(name))
    obscure = bool(_OBSCURE_PROCEDURAL_RE.search(name))

    ladder_or_bucket = price_bucket or weather_bucket
    if ladder_or_bucket:
        reasons.append("ladder_or_bucket")
    if is_narrow:
        reasons.append("narrow_range")
    if social_filler:
        reasons.append("social_filler")
    if entertainment_metric:
        reasons.append("entertainment_metric")
    if obscure:
        reasons.append("obscure_procedural")

    compelling = bool(_COMPELLING_RE.search(name))
    personnel = bool(_SPORTS_PERSONNEL_RE.search(name)) and has_salient
    outbreak = bool(_OUTBREAK_RE.search(name))
    if compelling:
        reasons.append("compelling_topic")
    if personnel:
        reasons.append("sports_personnel_story")
    if outbreak:
        reasons.append("health_outbreak")
    if has_salient:
        reasons.append("salient_entity")

    # Outcome-only ladders: many numeric outcomes with the same market shell.
    numeric_outcomes = sum(1 for o in outcome_names if _NUMBER_RE.search(o or ""))
    if (
        len(outcome_names) >= 4
        and numeric_outcomes / max(len(outcome_names), 1) >= 0.7
    ):
        ladder_or_bucket = True
        reasons.append("numeric_outcome_ladder")

    if social_filler or (obscure and not compelling):
        quality: QualityClass = "suppress"
    elif entertainment_metric:
        quality = "low_quality"
    elif (price_bucket or weather_bucket) and (is_narrow or not compelling):
        quality = "low_quality"
    elif personnel or outbreak or compelling:
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

    return MarketQuality(
        quality_class=quality,
        family_key=family_key,
        reasons=reasons,
        is_ladder_or_bucket=ladder_or_bucket,
        is_narrow_range=is_narrow,
        has_named_salient_entity=has_salient,
        explanation_required=quality in ("compelling", "normal"),
    )


def quality_score_adjustment(quality: MarketQuality) -> int:
    """Score adjustment applied after highlight scoring."""
    if quality.quality_class == "compelling":
        return 12
    if quality.quality_class == "low_quality":
        penalty = -35
        if quality.is_narrow_range:
            penalty -= 15
        return penalty
    if quality.quality_class == "suppress":
        return -100
    return 0


def cap_low_quality_families(items: list[dict], cap: int = 1) -> list[dict]:
    """Cap low-quality ladder/bucket families after scoring.

    Items are expected to be sorted later by the caller; this helper sorts by
    score first to keep the strongest representative per family.
    """
    sorted_items = sorted(
        items,
        key=lambda x: (x.get("score", 0), x.get("_sort_time", 0)),
        reverse=True,
    )
    counts: dict[str, int] = {}
    kept: list[dict] = []
    for item in sorted_items:
        qclass = item.get("_quality_class")
        family = item.get("_quality_family_key")
        if qclass == "low_quality" and family:
            count = counts.get(family, 0)
            if count >= cap:
                continue
            counts[family] = count + 1
        kept.append(item)
    return kept
