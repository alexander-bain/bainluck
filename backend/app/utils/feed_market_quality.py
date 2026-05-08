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
    r"hired|hire|traded|suspended|suspension|benched|cut|released"
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
    r"super bowl|world cup|champions league|masters|olympics|"
    r"nba finals?|wnba finals?|conference finals?|stanley cup|world series"
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
    r"beyonce|drake|kardashian|iceman"
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
    r"hot dog|nathan's|meme|memecoin"
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

_STOPWORDS = {
    "will", "the", "a", "an", "to", "of", "in", "on", "by", "at", "for",
    "be", "is", "are", "and", "or", "with", "between", "above", "below",
    "over", "under", "than", "next", "this", "month", "week", "day",
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

    if "russia" in lower and "ukraine" in lower:
        return "story:russia_ukraine"

    if "2028" in lower and re.search(r"\b(president|presidential|nominee|election)\b", lower):
        return "story:us_2028_election"

    if re.search(r"\b(fed|rate cuts?|interest rates?|inflation|cpi|ppi|ecb)\b", lower):
        return "story:macro_rates"

    if re.search(r"\b(wti|crude oil|brent oil|oil)\b", lower):
        return "story:oil"

    if re.search(r"\b(openai|gpt|claude|deepseek|gemini|ai model)\b", lower):
        return "story:ai"

    if category == "entertainment" and re.search(r"\b(drake|iceman)\b", lower):
        return "story:drake_iceman"

    if re.search(r"\bfederal government\b.*\btake a stake\b", lower):
        return "story:us_government_stakes"

    if "truist championship" in lower:
        return "story:golf_truist_championship"

    return None


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
    story_key = _story_key(name, category)

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
    if _OUTBREAK_RE.search(text) or re.search(r"\b(hurricane|tornado|earthquake|wildfire|flood|rain|snow)\b", text, re.I):
        return "health_weather_risk"
    if _SPORTS_PERSONNEL_RE.search(text) and (
        category in {"golf", "football", "basketball", "baseball", "hockey", "soccer", "tennis", "chess", "squash", "mma"}
        or re.search(r"\b(nba|nfl|mlb|nhl|ufc|pga|team|coach|player|next game|patriots|lakers|yankees)\b", text, re.I)
    ):
        return "sports_drama"
    if _BREAKING_NEWS_RE.search(text) and re.search(r"\b(iran|israel|russia|ukraine|china|trump|gaza|taiwan|nuclear)\b", text, re.I):
        return "breaking_news"
    if re.search(r"\b(war|invade|invasion|ceasefire|peace|regime|taiwan|ukraine|israel|iran|russia|china|cuba|venezuela)\b", text, re.I):
        return "world_event"
    if _COMPANY_DRAMA_RE.search(text) and (_PUBLIC_COMPANY_RE.search(text) or re.search(r"\b(openai|spacex|anthropic|tesla|apple|google|meta|amazon|nvidia)\b", text, re.I)):
        return "company_drama"
    if re.search(r"\b(openai|anthropic|claude|gpt|ai model|frontiermath|deepseek|gemini|nvidia|compute)\b", text, re.I):
        return "tech_frontier"
    if re.search(r"\b(fed|rate cut|recession|inflation|cpi|ppi|earnings|oil|wti|treasury|yield)\b", text, re.I):
        return "macro_signal"
    if _CULTURE_RE.search(text) or category == "entertainment":
        return "culture_moment"
    if category in {"golf", "football", "basketball", "baseball", "hockey", "soccer", "tennis", "chess", "squash"}:
        return "sports_story"
    if re.search(r"\b(pga|tour|championship|top 20|world cup|champions league|nba|nfl|mlb|nhl|ufc)\b", text, re.I):
        return "sports_story"
    if _PUBLIC_COMPANY_RE.search(text):
        return "big_public_company"
    if _BIG_NAME_RE.search(text) and category not in {"politics", "geopolitics"}:
        return "big_name"
    if category in {"politics", "geopolitics"} or re.search(r"\b(president|senate|house|governor|mayor|election|nominee|confirmed)\b", text, re.I):
        return "political_power"
    if _WEIRD_NEWS_RE.search(text):
        return "weird_news"
    return "other"


def _discover_category_group(item: dict) -> str:
    data = item.get("data") or {}
    category = (data.get("llm_sport_category") or data.get("sport_name") or data.get("sport") or "").lower()
    if item.get("type") == "event":
        return "sports_culture"
    if category in {"weather", "health"}:
        return "weather_health"
    if category in {"politics", "geopolitics", "economics", "tech", "entertainment"}:
        return category
    if category in {"golf", "football", "basketball", "baseball", "hockey", "soccer", "tennis", "chess", "squash", "mma", "cricket"}:
        return "sports_culture"
    return "other"


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
    "absurd_but_real": 2,
    "other": 3,
}


def diversify_discover_first_page(
    items: list[dict],
    *,
    first_page_size: int = 20,
) -> list[dict]:
    """Reorder the first Discover page so it feels curated, not clustered.

    This does not drop cards or change scores. It keeps the strongest item from
    each story/category near the top while preventing one category, especially
    politics, from swallowing the whole first page.
    """
    if first_page_size <= 0 or len(items) <= 1:
        return items

    target_size = min(first_page_size, len(items))
    category_counts: dict[str, int] = {}
    archetype_counts: dict[str, int] = {}
    story_counts: dict[str, int] = {}

    def can_select(item: dict, *, enforce_archetype: bool, enforce_story: bool) -> bool:
        group = _discover_category_group(item)
        if category_counts.get(group, 0) >= _DISCOVER_FIRST_PAGE_CATEGORY_CAPS.get(group, 3):
            return False

        if enforce_archetype:
            archetype = _discover_archetype_group(item)
            if archetype_counts.get(archetype, 0) >= _DISCOVER_FIRST_PAGE_ARCHETYPE_CAPS.get(archetype, 3):
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

    for enforce_archetype, enforce_story in ((True, True), (True, False), (False, False)):
        for item in items:
            if len(selected) >= target_size:
                break
            key = _feed_item_key(item)
            if key in selected_keys:
                continue
            if not can_select(item, enforce_archetype=enforce_archetype, enforce_story=enforce_story):
                continue
            selected.append(item)
            selected_keys.add(key)
            record(item)
        if len(selected) >= target_size:
            break

    if len(selected) < target_size:
        needed = target_size - len(selected)
        fallback = [
            item for item in items
            if _feed_item_key(item) not in selected_keys
        ]
        selected.extend(fallback[:needed])

    _ensure_required_archetypes(selected, items)
    _improve_strict_variety(selected, items)

    selected_keys = {_feed_item_key(item) for item in selected}
    remainder = [
        item for item in items
        if _feed_item_key(item) not in selected_keys
        and item not in selected
    ]
    return selected + remainder


def _ensure_required_archetypes(selected: list[dict], all_items: list[dict]) -> None:
    """Make room for at least one strong card from key first-page textures."""
    required: tuple[EditorialArchetype, ...] = (
        "tech_frontier",
        "culture_moment",
        "health_weather_risk",
        "sports_story",
        "sports_drama",
        "weird_news",
        "absurd_but_real",
    )
    selected_keys = {_feed_item_key(item) for item in selected}

    for target in required:
        if any(_discover_archetype_group(item) == target for item in selected):
            continue

        candidate = next(
            (
                item for item in all_items
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
            if archetype in required and archetype_counts[archetype] <= 1:
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

    # Keep at least four non-politics/geopolitics cards in the top 10 when
    # already-selected cards can satisfy that without dropping stronger stories.
    top10_size = min(10, len(selected))
    while top10_size >= 4:
        top10 = selected[:top10_size]
        non_political_count = sum(
            1 for item in top10
            if _discover_category_group(item) not in {"politics", "geopolitics"}
        )
        if non_political_count >= 4:
            break

        replacement_idx = next(
            (
                idx for idx in range(top10_size - 1, -1, -1)
                if _discover_category_group(selected[idx]) in {"politics", "geopolitics"}
            ),
            None,
        )
        candidate_idx = next(
            (
                idx for idx in range(top10_size, first_page_size)
                if _discover_category_group(selected[idx]) not in {"politics", "geopolitics"}
                and selected[idx].get("score", 0) >= 90
            ),
            None,
        )
        if replacement_idx is None or candidate_idx is None:
            break
        swap_positions(replacement_idx, candidate_idx)

    # Keep diplomatic clusters from exceeding the strict world-event cap in the
    # first 20. Prefer replacements already selected for the first page, then
    # pull a strong non-world candidate from the remainder if available.
    while True:
        first_page = selected[:first_page_size]
        world_count = sum(
            1 for item in first_page
            if _discover_archetype_group(item) == "world_event"
        )
        if world_count <= 4:
            break

        replacement_idx = next(
            (
                idx for idx in range(first_page_size - 1, -1, -1)
                if _discover_archetype_group(selected[idx]) == "world_event"
            ),
            None,
        )
        if replacement_idx is None:
            break

        selected_keys = {_feed_item_key(item) for item in selected}
        candidate_idx = next(
            (
                idx for idx in range(first_page_size, len(selected))
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
                item for item in all_items
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
        return min(100, adjusted)

    if quality.quality_class == "low_quality":
        return min(70, adjusted)

    ceiling = 94 if quality.has_named_salient_entity else 88
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
    if "health_outbreak" in quality.reasons or "sports_personnel_story" in quality.reasons:
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
        return min(100, raw_score + 5)

    if has_specific_explanation(
        hook_description=hook_description,
        headline=headline,
        quality=quality,
    ):
        return raw_score

    if quality.quality_class == "compelling":
        return min(96, raw_score)
    if quality.quality_class == "normal":
        return min(90, raw_score)
    return min(65, raw_score)


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
        key=lambda x: (x.get("score", 0), x.get("_sort_time", 0)),
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
        "story:drake_iceman": 1,
        "story:us_government_stakes": 2,
        "story:golf_truist_championship": 3,
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
