"""Nightly Fun Scout (#13102, Ruling 276: B, under Decide 60-A / 61-A / 73-A / 32-C).

Finds fun single markets and novel cross-family sets every night on the
``bainluck`` background worker — never called during a page load:

1. **Read** open non-sports titles from both venues (Kalshi + Polymarket) plus
   the grouping sentinel's uncovered families.
2. **Propose** in two model passes, both routed through
   ``app.services.llm_request.complete_chat_detailed`` and ``llm_models``:
   - ``fun_scout_tag`` on the small OpenAI model (~2 cents/night) tags fun
     singles and set hints.
   - ``fun_scout_sets`` on Claude (``claude-sonnet-5-5`` or
     ``claude-opus-5-5``; under 40 cents/night) writes sets with a name,
     members, one-line rationale, look (``map`` / ``faces`` / ``bars``), and
     selector. Reads ``ANTHROPIC_API_KEY_SCOUT`` only.
3. **Check in code, never by the model:** every member exists and is open,
   clears the real-trading volume bar, passes the taste guard (273: B), is
   still ahead, deduplicates Kalshi/Polymarket twins to one row per market,
   and every surviving set keeps at least three live members.
4. **Write** each surviving set as a Decide 60-A / 73-A rule file (with a
   ``selector`` — ``fun_tag`` for cross-family sets — never a bare typed list
   of IDs) and its declared ``look`` (``faces`` requires credited images,
   195-A).
5. **Ship** at most two new sets per day into the returning-reader novelty seat
   (32-C). First seven clean days ship only after Fable's look (61-A licence);
   one wrong card served suspends auto-shipping immediately.
6. **Learn** from Alex's approved sets, morning grades, and retired sets.

Hard spend caps (Decide 61-A / 276: B): **$5.00 per run**, **$30.00 monthly**
(December ceiling). The estimated spend line prints before any model call.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from app.services.llm_models import (
    MODELS,
    default_model_for_task,
    resolve_model,
)
from app.services.llm_request import JobBudget, complete_chat_detailed
from app.utils.discover_fun_tags import (
    FUN_TAG_DEFAULT_MIN_LIFETIME_VOLUME,
    FunMarketEntry,
    check_fun_real_trading,
    check_fun_still_ahead,
    check_fun_taste_guard,
    load_fun_markets_registry,
)
from app.utils.roundup_containers import (
    CONTAINERS_DATA_DIR,
    validate_roundup_definition,
)

logger = logging.getLogger(__name__)

#: Dedicated Anthropic key for the scout on Heroku app ``bainluck`` (#13102).
#: Read from this variable and nothing else (never ``ANTHROPIC_API_KEY``).
SCOUT_ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY_SCOUT"
#: Feature gate for the scheduled nightly task.
SCOUT_ENABLED_ENV = "DISCOVER_FUN_SCOUT_ENABLED"

#: Decide 61-A / Ruling 276: B hard caps.
SCOUT_RUN_CAP_USD = 5.0
SCOUT_MONTHLY_CAP_USD = 30.0

#: Ruling 385: A (#13102) daily staging cap and minimum set size.
SCOUT_MAX_NEW_SETS_PER_DAY = 10
SCOUT_MIN_LIVE_MEMBERS = 3

#: Ruling 385: A (#13102): staged scout sets NEVER auto-promote to public;
#: promotion happens only after Alex grades "Keep".
SCOUT_AUTO_PROMOTE_TO_PUBLIC = False
SCOUT_PUBLIC_PROMOTION_GATE = "alex_keep"

#: Clean-day counter retained for telemetry; auto-promotion is permanently off.
SCOUT_CLEAN_DAYS_FOR_LICENCE = 7
LICENCE_AWAITING_LOOK = "awaiting_fable_look"
LICENCE_AUTO = "licensed_auto"
LICENCE_SUSPENDED = "suspended"

#: Visual looks a scout rule file may declare (#13102).
SCOUT_ALLOWED_LOOKS: frozenset[str] = frozenset({"map", "faces", "bars"})

SCOUT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "discover"
SCOUT_STAGED_SETS_DIR = SCOUT_DATA_DIR / "scout_sets"
SCOUT_RETIRED_SETS_PATH = SCOUT_DATA_DIR / "scout_retired_sets.json"
SCOUT_LICENCE_STATE_PATH = SCOUT_DATA_DIR / "scout_licence_state.json"

#: Additional severe-harm guard layered on top of 273: B taste guard so violent
#: or geopolitical catastrophe markets (e.g. nuclear weapons, mass casualty)
#: are never proposed as "fun" sets even if a model suggests them.
_SCOUT_NON_FUN_HARM_RE = re.compile(
    r"\b("
    r"nuclear\s+weapon|nuke|detonat(?:e|ion)|dirty\s+bomb|"
    r"terror(?:ist|ism)|mass\s+shooting|genocide|assassination|"
    r"suicide|overdose|school\s+shooting"
    r")\b",
    re.IGNORECASE,
)

_SLUG_CLEAN_RE = re.compile(r"[^a-z0-9]+")
_NORM_TITLE_RE = re.compile(r"[^a-z0-9]+")

_TAG_BATCH_SIZE = 45
_DEFAULT_TOKENS_PER_TITLE = 22
_DEFAULT_TAG_PROMPT_OVERHEAD_PER_BATCH = 900
_DEFAULT_TAG_OUTPUT_TOKENS_PER_BATCH = 350
_TAG_MAX_OUTPUT_TOKENS_PER_BATCH = 4_000
_DEFAULT_SET_INPUT_TOKENS = 25_000
_DEFAULT_SET_OUTPUT_TOKENS = 16_000

_SCOUT_BANNED_VOICE_RE = re.compile(r"\b(?:traders?|bets?|betting)\b", re.IGNORECASE)
_SCOUT_MECHANICAL_FAMILY_RE = re.compile(
    r"(?:point[\s-]+of[\s-]+sale\s+growth|\bpos\s+growth\b|\bsales\s+growth\b|"
    r"\bapp\s+downloads?\b|\bdownload\s+counts?\b|"
    r"\bdownloads?\s+in\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b|"
    r"\bmonthly\s+(?:sales|revenue|downloads?|installs?)\b)",
    re.IGNORECASE,
)
_SCOUT_POLITICAL_CATEGORIES: frozenset[str] = frozenset(
    {"politics", "geopolitics", "elections", "government"}
)
_SCOUT_POLITICAL_GOVERNANCE_RE = re.compile(
    r"\b(?:trump\s+administration|cabinet|prime\s+minister|vice\s+president|"
    r"president\s+of|presidential|senate|congress(?:man|woman)?|"
    r"house\s+of\s+representatives|governor|mayor|parliament|election|"
    r"primary|nominee|impeach(?:ment)?|tariffs?|supreme\s+court|referendum|"
    r"coalition|legislation|government\s+shutdown|"
    r"(?:out|resign(?:s|ing)?)\s+as\s+(?:prime\s+minister|president|vice\s+president|"
    r"minister|governor|chancellor|mayor))\b",
    re.IGNORECASE,
)
_SCOUT_POP_CULTURE_CROSSOVER_RE = re.compile(
    r"\b(?:snl|saturday\s+night\s+live|pope|vatican|aliens?|ufo|"
    r"taylor\s+swift|miss\s+universe|nobel|elon\s+musk|satoshi|"
    r"world\s+happiness|time\s+person|mrbeast|spotify|nuclear\s+fusion)\b",
    re.IGNORECASE,
)


class FunScoutSpendCapExceededError(RuntimeError):
    """Raised when a fun scout run would exceed Decide 61-A / 276: B caps."""


class FunScoutMissingKeyError(RuntimeError):
    """Raised when ``ANTHROPIC_API_KEY_SCOUT`` (or ``OPENAI_API_KEY``) is unset."""


@dataclass(frozen=True)
class ScoutMarketRow:
    """One open non-sports market presented to the scout."""

    market_id: int
    source: str
    title: str
    status: str = "open"
    category: Optional[str] = None
    resolution_date: Optional[datetime] = None
    volume: Optional[float] = None
    volume_24h: Optional[float] = None
    canonical_market_key: Optional[str] = None
    group_id: Optional[str] = None
    market_metadata: Optional[dict[str, Any]] = None
    event_date: Optional[str] = None


@dataclass(frozen=True)
class ScoutUncoveredFamily:
    """One uncovered family reported by ``grouping_sentinel``."""

    family_key: str
    sample_title: str
    open_count: int
    source: Optional[str] = None


@dataclass(frozen=True)
class ScoutTaggedMarket:
    """One market selected by the small-model tagging pass."""

    market_id: int
    fun_group: str
    reason: str
    is_fun_single: bool = False
    set_hint: Optional[str] = None


@dataclass(frozen=True)
class ScoutProposedSet:
    """Raw set proposal returned by the Claude set-writing pass."""

    slug: str
    name: str
    kicker: str
    category: str
    why_better_together: str
    look: str
    member_ids: tuple[int, ...]
    selector_kind: str = "fun_tag"
    title_ilike: Optional[str] = None
    template: Optional[str] = None
    footer: Optional[str] = None


@dataclass(frozen=True)
class ScoutValidatedSet:
    """Code-verified set ready to be written as a 60-A / 73-A rule file."""

    slug: str
    name: str
    kicker: str
    category: str
    why_better_together: str
    look: str
    members: tuple[ScoutMarketRow, ...]
    selector_kind: str
    title_ilike: Optional[str]
    template: Optional[str]
    footer: str
    dropped_members: tuple[tuple[int, str], ...] = ()
    deduped_members: tuple[tuple[int, int], ...] = ()


@dataclass
class ScoutLicenceState:
    """Decide 61-A licence tracker for scout-written sets."""

    status: str = LICENCE_AWAITING_LOOK
    clean_days: int = 0
    last_clean_day: Optional[str] = None
    suspended_reason: Optional[str] = None
    suspended_at: Optional[str] = None
    suspended_slug: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "clean_days": self.clean_days,
            "last_clean_day": self.last_clean_day,
            "suspended_reason": self.suspended_reason,
            "suspended_at": self.suspended_at,
            "suspended_slug": self.suspended_slug,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScoutLicenceState":
        status = str(data.get("status") or LICENCE_AWAITING_LOOK)
        if status not in {LICENCE_AWAITING_LOOK, LICENCE_AUTO, LICENCE_SUSPENDED}:
            status = LICENCE_AWAITING_LOOK
        return cls(
            status=status,
            clean_days=max(0, int(data.get("clean_days") or 0)),
            last_clean_day=str(data["last_clean_day"]) if data.get("last_clean_day") else None,
            suspended_reason=(
                str(data["suspended_reason"]) if data.get("suspended_reason") else None
            ),
            suspended_at=str(data["suspended_at"]) if data.get("suspended_at") else None,
            suspended_slug=(
                str(data["suspended_slug"]) if data.get("suspended_slug") else None
            ),
        )


def is_fun_scout_enabled() -> bool:
    """Return True only when ``DISCOVER_FUN_SCOUT_ENABLED`` is explicitly on."""
    raw = os.getenv(SCOUT_ENABLED_ENV, "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def check_scout_anthropic_key_status() -> dict[str, Any]:
    """Report whether ``ANTHROPIC_API_KEY_SCOUT`` is set and its character count.

    Never returns, copies, or logs any character of the secret itself.
    """
    raw_value = os.environ.get(SCOUT_ANTHROPIC_API_KEY_ENV)
    cleaned = raw_value.strip() if isinstance(raw_value, str) else ""
    char_count = sum(1 for _ in cleaned)
    return {
        "env": SCOUT_ANTHROPIC_API_KEY_ENV,
        "is_set": char_count > 0,
        "length": char_count,
    }


def build_scout_anthropic_client() -> Any:
    """Build an Anthropic SDK client reading ONLY ``ANTHROPIC_API_KEY_SCOUT``."""
    api_key = (os.getenv(SCOUT_ANTHROPIC_API_KEY_ENV) or "").strip()
    if not api_key:
        raise FunScoutMissingKeyError(
            f"{SCOUT_ANTHROPIC_API_KEY_ENV} is not set in this environment"
        )
    import anthropic

    return anthropic.Anthropic(api_key=api_key, timeout=240.0, max_retries=0)


def build_scout_openai_client() -> Any:
    """Build an OpenAI SDK client with finite timeout and ``max_retries=0``."""
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise FunScoutMissingKeyError("OPENAI_API_KEY is not set in this environment")
    import openai

    return openai.OpenAI(api_key=api_key, timeout=60.0, max_retries=0)


# ---------------------------------------------------------------------------
# Decide 61-A / Ruling 276: B spend estimate & cap enforcement
# ---------------------------------------------------------------------------


def estimate_fun_scout_spend(
    title_count: int,
    *,
    tag_model: Optional[str] = None,
    set_model: Optional[str] = None,
    prior_monthly_spend_usd: float = 0.0,
    tokens_per_title: int = _DEFAULT_TOKENS_PER_TITLE,
    set_input_tokens: int = _DEFAULT_SET_INPUT_TOKENS,
    set_output_tokens: int = _DEFAULT_SET_OUTPUT_TOKENS,
    run_cap_usd: float = SCOUT_RUN_CAP_USD,
    monthly_cap_usd: float = SCOUT_MONTHLY_CAP_USD,
) -> dict[str, Any]:
    """Estimate token usage and USD cost before any model call (Decide 61-A)."""
    t_model = tag_model or resolve_model("fun_scout_tag")
    s_model = set_model or resolve_model("fun_scout_sets")
    t_spec = MODELS[t_model]
    s_spec = MODELS[s_model]

    count = max(0, int(title_count))
    batches = max(1, (count + _TAG_BATCH_SIZE - 1) // _TAG_BATCH_SIZE) if count else 0
    tag_in = count * max(1, int(tokens_per_title)) + batches * _DEFAULT_TAG_PROMPT_OVERHEAD_PER_BATCH
    tag_out = batches * _DEFAULT_TAG_OUTPUT_TOKENS_PER_BATCH
    tag_cost = (tag_in * t_spec.input_per_m + tag_out * t_spec.output_per_m) / 1_000_000.0

    set_in = max(0, int(set_input_tokens)) if count else 0
    set_out = max(0, int(set_output_tokens)) if count else 0
    set_cost = (set_in * s_spec.input_per_m + set_out * s_spec.output_per_m) / 1_000_000.0

    est_run = round(tag_cost + set_cost, 6)
    prior = round(float(prior_monthly_spend_usd), 6)
    projected = round(prior + est_run, 6)
    within_run = est_run <= float(run_cap_usd)
    within_month = projected <= float(monthly_cap_usd)

    return {
        "tag_model": t_model,
        "set_model": s_model,
        "title_count": count,
        "tag_batches": batches,
        "tag_input_tokens": tag_in,
        "tag_output_tokens": tag_out,
        "tag_cost_usd": round(tag_cost, 6),
        "set_input_tokens": set_in,
        "set_output_tokens": set_out,
        "set_cost_usd": round(set_cost, 6),
        "estimated_run_cost_usd": est_run,
        "run_cap_usd": float(run_cap_usd),
        "prior_monthly_spend_usd": prior,
        "projected_monthly_spend_usd": projected,
        "monthly_cap_usd": float(monthly_cap_usd),
        "within_caps": bool(within_run and within_month),
    }


def format_fun_scout_pre_run_spend_line(estimate: Mapping[str, Any]) -> str:
    """Format the mandatory Decide 61-A pre-run spend line."""
    return (
        f"[discover-fun-scout] tag_model={estimate.get('tag_model')} "
        f"set_model={estimate.get('set_model')} "
        f"titles={int(estimate.get('title_count') or 0)} "
        f"est_run_cost=${float(estimate.get('estimated_run_cost_usd') or 0.0):.4f} "
        f"(tag=${float(estimate.get('tag_cost_usd') or 0.0):.4f}, "
        f"sets=${float(estimate.get('set_cost_usd') or 0.0):.4f}, "
        f"cap=${float(estimate.get('run_cap_usd') or SCOUT_RUN_CAP_USD):.2f}) "
        f"projected_month=${float(estimate.get('projected_monthly_spend_usd') or 0.0):.4f} "
        f"(cap=${float(estimate.get('monthly_cap_usd') or SCOUT_MONTHLY_CAP_USD):.2f})"
    )


def assert_fun_scout_within_caps(estimate: Mapping[str, Any]) -> str:
    """Log the mandatory pre-run spend line and refuse if either cap is breached."""
    line = format_fun_scout_pre_run_spend_line(estimate)
    logger.info(line)
    if not estimate.get("within_caps"):
        raise FunScoutSpendCapExceededError(
            f"Fun scout run exceeds Decide 61-A / 276: B spend cap: {line}"
        )
    return line


# ---------------------------------------------------------------------------
# Step 3: Code-enforced member & set verification (never trusted to a model)
# ---------------------------------------------------------------------------


def _slugify(value: str) -> str:
    slug = _SLUG_CLEAN_RE.sub("-", (value or "").strip().lower()).strip("-")
    return slug[:72]


def _normalized_title_key(title: str) -> str:
    cleaned = (title or "").strip().lower()
    cleaned = re.sub(r"\b(will|the|a|an|by|in|on|of|for|to|be)\b", " ", cleaned)
    return _NORM_TITLE_RE.sub(" ", cleaned).strip()


def _parse_optional_date(raw: Optional[str | date]) -> Optional[date]:
    if raw is None:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None


def check_scout_member(
    market: Optional[ScoutMarketRow],
    *,
    min_volume: float = FUN_TAG_DEFAULT_MIN_LIFETIME_VOLUME,
    now: Optional[datetime] = None,
) -> tuple[bool, Optional[str]]:
    """Verify one candidate market purely in code."""
    if market is None:
        return False, "market_missing"
    if (market.status or "").strip().lower() != "open":
        return False, f"not_open:{market.status}"

    vol_ok, vol_reason = check_fun_real_trading(
        market.volume, min_lifetime_volume=int(min_volume)
    )
    if not vol_ok:
        return False, vol_reason

    taste_ok, taste_reason = check_fun_taste_guard(market.title)
    if not taste_ok:
        return False, taste_reason

    if _SCOUT_NON_FUN_HARM_RE.search(market.title or ""):
        return False, "taste_guard:severe_harm"

    check_now = now or datetime.now(timezone.utc)
    ahead_ok, ahead_reason = check_fun_still_ahead(
        title=market.title,
        status=market.status,
        resolution_date=market.resolution_date,
        sport_category=market.category,
        market_metadata=market.market_metadata,
        now=check_now,
        event_date=_parse_optional_date(market.event_date),
    )
    if not ahead_ok:
        return False, ahead_reason

    return True, None


def dedupe_cross_venue_members(
    members: Sequence[ScoutMarketRow],
) -> tuple[list[ScoutMarketRow], list[tuple[int, int]]]:
    """Keep at most one row when Kalshi and Polymarket list the same market.

    Returns ``(kept_rows, deduped_pairs)`` where each deduped pair is
    ``(dropped_market_id, kept_market_id)``.
    """
    ordered = sorted(
        members,
        key=lambda m: (
            -(float(m.volume) if m.volume is not None else -1.0),
            -(float(m.volume_24h) if m.volume_24h is not None else -1.0),
            m.market_id,
        ),
    )
    kept: list[ScoutMarketRow] = []
    seen_canonical: dict[str, int] = {}
    seen_title: dict[str, int] = {}
    deduped: list[tuple[int, int]] = []

    for row in ordered:
        ckey = (row.canonical_market_key or "").strip().lower()
        tkey = _normalized_title_key(row.title)
        if ckey and ckey in seen_canonical:
            deduped.append((row.market_id, seen_canonical[ckey]))
            continue
        if tkey and tkey in seen_title:
            deduped.append((row.market_id, seen_title[tkey]))
            continue
        kept.append(row)
        if ckey:
            seen_canonical[ckey] = row.market_id
        if tkey:
            seen_title[tkey] = row.market_id
    return kept, deduped


_BLURB_NUMBER_WORDS: dict[str, int] = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_BLURB_LEADING_STARTERS: frozenset[str] = frozenset(
    {
        "a",
        "across",
        "add",
        "adding",
        "after",
        "all",
        "alongside",
        "an",
        "before",
        "between",
        "both",
        "combine",
        "combining",
        "compare",
        "comparing",
        "count",
        "counting",
        "during",
        "each",
        "even",
        "every",
        "everyday",
        "everything",
        "fans",
        "few",
        "fill",
        "five",
        "follow",
        "following",
        "for",
        "four",
        "from",
        "grouped",
        "grouping",
        "guess",
        "guessing",
        "here",
        "how",
        "in",
        "many",
        "most",
        "near",
        "next",
        "no",
        "on",
        "once",
        "one",
        "over",
        "point",
        "put",
        "putting",
        "read",
        "reading",
        "rumors",
        "seeing",
        "several",
        "side",
        "six",
        "some",
        "the",
        "there",
        "these",
        "this",
        "those",
        "three",
        "together",
        "track",
        "tracking",
        "two",
        "watch",
        "watching",
        "what",
        "when",
        "where",
        "whether",
        "which",
        "who",
        "why",
        "will",
        "with",
        "your",
    }
)
_BLURB_GENERIC_PHRASES: frozenset[str] = frozenset(
    {
        "all star",
        "big game",
        "billboard hot",
        "box office",
        "cabinet departures",
        "fan forum",
        "first week",
        "golden globe",
        "golden globes",
        "hall of fame",
        "hip hop",
        "hot 100",
        "millennium prize",
        "mother nature",
        "new year",
        "nobel prize",
        "opening weekend",
        "pacific northwest",
        "point of sale",
        "pop and r&b",
        "prime minister",
        "r&b",
        "rap and r&b",
        "rock and roll",
        "rotten tomatoes",
        "super bowl",
        "united states",
        "vice president",
        "white house",
        "world cup",
        "world happiness",
        "year in search",
    }
)
_BLURB_CONNECTORS: frozenset[str] = frozenset({"of", "the", "in", "and", "vs"})
_MAP_GENERIC_NON_PLACES: frozenset[str] = frozenset(
    {
        "us",
        "usa",
        "united states",
        "america",
        "atlantic",
        "pacific",
        "earth",
        "world",
        "global",
        "planet",
        "north america",
        "south america",
        "europe",
        "asia",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "dec",
        "jan",
        "nov",
    }
)
_MAP_KNOWN_PLACES: frozenset[str] = frozenset(
    {
        "amsterdam",
        "arizona",
        "aspen",
        "atlanta",
        "austin",
        "barcelona",
        "beijing",
        "berlin",
        "big bear",
        "big sky",
        "boston",
        "brazil",
        "breckenridge",
        "brooklyn",
        "california",
        "canada",
        "charlotte",
        "chicago",
        "china",
        "colorado",
        "dallas",
        "denver",
        "detroit",
        "dubai",
        "florida",
        "france",
        "germany",
        "hong kong",
        "houston",
        "india",
        "italy",
        "jackson hole",
        "japan",
        "killington",
        "lake tahoe",
        "las vegas",
        "london",
        "los angeles",
        "madrid",
        "mammoth",
        "manhattan",
        "melbourne",
        "mexico",
        "mexico city",
        "miami",
        "minneapolis",
        "montana",
        "montreal",
        "nashville",
        "nevada",
        "new orleans",
        "new york",
        "new york city",
        "nyc",
        "orlando",
        "park city",
        "paris",
        "philadelphia",
        "phoenix",
        "portland",
        "rio de janeiro",
        "rome",
        "salt lake city",
        "san diego",
        "san francisco",
        "seattle",
        "seoul",
        "shanghai",
        "singapore",
        "south korea",
        "spain",
        "steamboat",
        "stowe",
        "sun valley",
        "sydney",
        "tahoe",
        "telluride",
        "texas",
        "tokyo",
        "toronto",
        "united kingdom",
        "utah",
        "vail",
        "vancouver",
        "vermont",
        "washington",
        "whistler",
    }
)
_MAP_FEATURE_RE = re.compile(
    r"\b(Lake\s+[A-Z][a-z]+|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+"
    r"(?:Mountain(?:\s+Resort)?|Ski\s+Resort|Resort|Peak|Lake|River|Valley|Harbor|Bay|Island))\b"
)
_MAP_WEATHER_IN_RE = re.compile(
    r"\b(?:snow|snowfall|rain|rainfall|temperatures?|weather|landfall|flood(?:ing)?|"
    r"heat\s*wave|freeze)\s+in\s+([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)"
)
_DROPPED_GENERIC_TOKENS: frozenset[str] = frozenset(
    {
        "after",
        "before",
        "best",
        "big",
        "billion",
        "day",
        "dec",
        "first",
        "game",
        "global",
        "how",
        "jan",
        "last",
        "main",
        "month",
        "more",
        "most",
        "new",
        "next",
        "nov",
        "open",
        "score",
        "season",
        "set",
        "show",
        "the",
        "top",
        "tour",
        "what",
        "when",
        "which",
        "who",
        "will",
        "winner",
        "world",
        "year",
    }
)


def _fold_text(text: str) -> str:
    cleaned = (text or "").replace("\u2019", "'").replace("\u2018", "'")
    decomposed = unicodedata.normalize("NFKD", cleaned)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _blurb_tokens_present(
    phrase_tokens: Sequence[str],
    member_text_folded: str,
    member_words: set[str],
    member_initials: set[str] | frozenset[str] = frozenset(),
    acronym_tokens: frozenset[str] = frozenset(),
) -> bool:
    for tok in phrase_tokens:
        if tok in acronym_tokens and tok in member_initials:
            continue
        if len(tok) <= 2:
            if tok not in member_words:
                return False
        elif tok not in member_text_folded and tok not in member_words:
            return False
    return True


def _extract_sig_tokens_and_acronyms(
    words: Sequence[str],
) -> tuple[list[str], frozenset[str]]:
    sig_tokens: list[str] = []
    acronyms: set[str] = set()
    for raw in words:
        stripped = raw.strip(".,\"'()")
        folded = _fold_text(stripped)
        if not folded or folded in _BLURB_CONNECTORS or len(stripped) < 2:
            continue
        sig_tokens.append(folded)
        if sum(1 for ch in stripped if ch.isupper()) >= 2:
            acronyms.add(folded)
    return sig_tokens, frozenset(acronyms)


def _extract_member_initials(members: Sequence[ScoutMarketRow]) -> set[str]:
    initials: set[str] = set()

    def _emit_run(run: list[str]) -> None:
        n = len(run)
        if 2 <= n <= 5:
            initials.add("".join(run))
        if n >= 3:
            for start in range(n):
                for end in range(start + 3, min(n, start + 5) + 1):
                    initials.add("".join(run[start:end]))

    for row in members:
        words = re.findall(r"[A-Za-z][A-Za-z.]*", row.title or "")
        cap_runs: list[str] = []
        for w in words:
            clean_w = w.replace(".", "")
            if clean_w.isupper() and 2 <= len(clean_w) <= 5:
                initials.add(clean_w.lower())
            if w[0].isupper():
                cap_runs.append(w[0].lower())
            else:
                _emit_run(cap_runs)
                cap_runs = []
        _emit_run(cap_runs)
    return initials


def check_scout_voice_words(
    name: str,
    kicker: str,
    why_better_together: str,
    footer: str,
) -> Optional[str]:
    """Rule 3.1: Reject betting/gambling voice (`traders`, `bets`, `betting`)."""
    for field in (name, kicker, why_better_together, footer):
        match = _SCOUT_BANNED_VOICE_RE.search(field or "")
        if match:
            return f"banned_voice_word:{match.group(0).lower()}"
    return None


def check_scout_blurb_matches_members(
    why_better_together: str,
    members: Sequence[ScoutMarketRow],
    dropped_rows: Sequence[tuple[ScoutMarketRow, str]] = (),
) -> Optional[str]:
    """Rule 3.2: Blurb mentions only entities/counts present in the surviving set."""
    blurb_norm = (why_better_together or "").replace("\u2019", "'").replace("\u2018", "'")
    blurb_folded = _fold_text(blurb_norm)
    blurb_words = set(re.findall(r"[a-z0-9]+", blurb_folded))

    count_match = re.search(
        r"\b(?:these|all|the)\s+(two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
        r"(?:markets?|questions?)\b",
        blurb_folded,
    )
    if count_match:
        raw_num = count_match.group(1)
        stated = _BLURB_NUMBER_WORDS.get(raw_num)
        if stated is None and raw_num.isdigit():
            stated = int(raw_num)
        if stated is not None and stated != len(members):
            return f"blurb_member_count_mismatch:{stated}!={len(members)}"

    member_text_folded = _fold_text(" ".join(m.title for m in members))
    member_words = set(re.findall(r"[a-z0-9]+", member_text_folded))
    member_initials = _extract_member_initials(members)

    # Reject any distinctive entity from a dropped/filtered candidate left in the blurb
    for dropped_row, _reason in dropped_rows:
        for cap_word in re.findall(r"\b[A-Z][a-z]{2,}\b", dropped_row.title or ""):
            folded_tok = _fold_text(cap_word)
            if (
                folded_tok in _DROPPED_GENERIC_TOKENS
                or folded_tok in member_text_folded
                or folded_tok in member_words
            ):
                continue
            if folded_tok in blurb_words:
                return f"blurb_mentions_dropped_member:{cap_word}"

    # Split on sentence punctuation and possessives ('s) so "Jordan Peele's Marvel debut"
    # isolates "Jordan Peele" cleanly instead of merging across the possessive.
    clauses = re.split(r"[.!?;:\n]+|'s\b", blurb_norm)
    phrase_re = re.compile(
        r"\b[A-Z][A-Za-z0-9+&-]+(?:\s+(?:(?:of|the|in|and|vs\.?)\s+)?[A-Z][A-Za-z0-9+&-]+){1,4}\b"
    )
    for clause in clauses:
        for match in phrase_re.finditer(clause):
            words = match.group(0).split()
            while len(words) > 1 and _fold_text(words[0]) in _BLURB_LEADING_STARTERS:
                words.pop(0)
            if len(words) < 2:
                continue
            cleaned = " ".join(words)
            folded_phrase = _fold_text(cleaned)
            if folded_phrase in _BLURB_GENERIC_PHRASES:
                continue
            sig_tokens, acronym_tokens = _extract_sig_tokens_and_acronyms(words)
            if len(sig_tokens) < 2:
                continue
            if not _blurb_tokens_present(
                sig_tokens, member_text_folded, member_words, member_initials, acronym_tokens
            ):
                return f"blurb_mentions_unlisted_member:{cleaned}"

    # Check single proper names inside 3+ proper-name comma lists (e.g. "Drake, Kendrick, Travis, Ye and Don Toliver")
    list_re = re.compile(
        r"\b([A-Z][A-Za-z0-9+&-]+(?:\s+[A-Z][A-Za-z0-9+&-]+)*"
        r"(?:\s*,\s*(?:the\s+)?[A-Z][A-Za-z0-9+&-]+(?:\s+[A-Z][A-Za-z0-9+&-]+)*)+"
        r"\s+(?:and|or)\s+(?:the\s+)?[A-Z][A-Za-z0-9+&-]+(?:\s+[A-Z][A-Za-z0-9+&-]+)*)"
    )
    for lmatch in list_re.finditer(blurb_norm):
        items = re.split(r"\s*,\s*|\s+(?:and|or)\s+", lmatch.group(1))
        if len(items) < 3:
            continue
        for item in items:
            words = item.split()
            while words and _fold_text(words[0]) in _BLURB_LEADING_STARTERS:
                words.pop(0)
            if not words:
                continue
            cleaned = " ".join(words)
            folded_item = _fold_text(cleaned)
            if folded_item in _BLURB_GENERIC_PHRASES:
                continue
            if len(words) == 1:
                tok = folded_item
                if (
                    tok in _DROPPED_GENERIC_TOKENS
                    or tok in member_words
                    or tok in member_text_folded
                    or tok in member_initials
                ):
                    continue
                return f"blurb_mentions_unlisted_member:{cleaned}"
            sig_tokens, acronym_tokens = _extract_sig_tokens_and_acronyms(words)
            if sig_tokens and not _blurb_tokens_present(
                sig_tokens, member_text_folded, member_words, member_initials, acronym_tokens
            ):
                return f"blurb_mentions_unlisted_member:{cleaned}"

    return None


def _extract_specific_places(title: str) -> set[str]:
    """Extract specific geographic pin candidates from a market title for `map` validation."""
    places: set[str] = set()
    clean_title = (title or "").replace("\u2019", "'")
    folded = _fold_text(re.sub(r"new\s+york\s+times", " ", _fold_text(clean_title)))

    for feat in _MAP_FEATURE_RE.findall(clean_title):
        key = _fold_text(feat).strip()
        if key and key not in _MAP_GENERIC_NON_PLACES:
            places.add(key)

    for weather_loc in _MAP_WEATHER_IN_RE.findall(clean_title):
        key = _fold_text(weather_loc).strip()
        if key and key not in _MAP_GENERIC_NON_PLACES:
            places.add(key)

    for place in _MAP_KNOWN_PLACES:
        if re.search(r"\b" + re.escape(place) + r"\b", folded):
            canonical = "new york" if place in {"nyc", "new york city"} else place
            places.add(canonical)

    # Collapse overlapping spans (e.g. "big bear" + "big bear mountain resort" -> 1 pin).
    collapsed: set[str] = set()
    for p in sorted(places, key=len):
        if any(existing in p for existing in collapsed):
            continue
        collapsed.add(p)
    return collapsed


def check_scout_map_look_places(
    look: str,
    members: Sequence[ScoutMarketRow],
) -> Optional[str]:
    """Rule 3.3: `look='map'` is permitted only when members are distinct specific places."""
    if (look or "").strip().lower() != "map":
        return None
    members_with_place = 0
    distinct_places: set[str] = set()
    for row in members:
        found = _extract_specific_places(row.title)
        if found:
            members_with_place += 1
            distinct_places.update(found)
    required_members = max(SCOUT_MIN_LIVE_MEMBERS, math.ceil(len(members) * 0.6))
    if members_with_place < required_members or len(distinct_places) < SCOUT_MIN_LIVE_MEMBERS:
        return f"map_look_requires_places:{members_with_place}/{len(members)}"
    return None


def check_scout_no_mechanical_sales_downloads(
    name: str,
    why_better_together: str,
    members: Sequence[ScoutMarketRow],
) -> Optional[str]:
    """Rule 3.4: Reject monthly POS/sales-growth and app-download-count families."""
    for text in [name, why_better_together, *(m.title for m in members)]:
        if _SCOUT_MECHANICAL_FAMILY_RE.search(text or ""):
            return "mechanical_sales_or_downloads_family"
    return None


def _is_political_market(row: ScoutMarketRow) -> bool:
    title = row.title or ""
    if _SCOUT_POP_CULTURE_CROSSOVER_RE.search(title):
        return False
    if _SCOUT_POLITICAL_GOVERNANCE_RE.search(title):
        return True
    cat = (row.category or "").strip().lower()
    return cat in _SCOUT_POLITICAL_CATEGORIES


def check_scout_no_politics_only_set(
    category: str,
    name: str,
    members: Sequence[ScoutMarketRow],
) -> Optional[str]:
    """Rule 3.5: Reject politics-only or routine government/election sets."""
    if (category or "").strip().lower() in _SCOUT_POLITICAL_CATEGORIES:
        return "politics_only_set:category"
    if not members:
        return None
    political_count = sum(1 for row in members if _is_political_market(row))
    if political_count >= max(1, math.ceil(len(members) * 0.6)):
        return "politics_only_set:members"
    return None


def validate_scout_proposed_set(
    proposal: ScoutProposedSet,
    catalog_by_id: Mapping[int, ScoutMarketRow],
    *,
    retired_slugs: frozenset[str] = frozenset(),
    retired_title_keys: frozenset[str] = frozenset(),
    existing_slugs: frozenset[str] = frozenset(),
    min_volume: float = FUN_TAG_DEFAULT_MIN_LIFETIME_VOLUME,
    min_members: int = SCOUT_MIN_LIVE_MEMBERS,
    now: Optional[datetime] = None,
) -> tuple[Optional[ScoutValidatedSet], Optional[str]]:
    """Run all code-enforced checks on one model-proposed set."""
    slug = _slugify(proposal.slug or proposal.name)
    if not slug:
        return None, "invalid_slug"
    if slug in retired_slugs or _normalized_title_key(proposal.name) in retired_title_keys:
        return None, f"retired_set:{slug}"
    if slug in existing_slugs:
        return None, f"already_exists:{slug}"

    name = (proposal.name or "").strip()
    why = (proposal.why_better_together or "").strip()
    if not name or not why:
        return None, "missing_name_or_rationale"

    taste_ok, taste_reason = check_fun_taste_guard(name)
    if not taste_ok:
        return None, f"set_title_{taste_reason}"
    if _SCOUT_NON_FUN_HARM_RE.search(name):
        return None, "set_title_taste_guard:severe_harm"

    look = (proposal.look or "bars").strip().lower()
    if look not in SCOUT_ALLOWED_LOOKS:
        return None, f"invalid_look:{look}"

    selector_kind = (proposal.selector_kind or "fun_tag").strip().lower()
    if selector_kind not in {"fun_tag", "title_ilike"}:
        selector_kind = "fun_tag"
    if selector_kind == "title_ilike" and not (proposal.title_ilike or "").strip():
        return None, "missing_title_ilike_selector"

    passing: list[ScoutMarketRow] = []
    dropped: list[tuple[int, str]] = []
    dropped_rows: list[tuple[ScoutMarketRow, str]] = []
    seen_ids: set[int] = set()
    for mid in proposal.member_ids:
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        row = catalog_by_id.get(mid)
        ok, reason = check_scout_member(row, min_volume=min_volume, now=now)
        if ok and row is not None:
            passing.append(row)
        else:
            reason_str = reason or "rejected"
            dropped.append((mid, reason_str))
            if row is not None:
                dropped_rows.append((row, reason_str))

    deduped_rows, deduped_pairs = dedupe_cross_venue_members(passing)
    if len(deduped_rows) < min_members:
        return (
            None,
            f"too_few_live_members:{len(deduped_rows)}<{min_members}",
        )

    kicker = (proposal.kicker or "DISCOVER SET").strip().upper()[:32]
    category = (proposal.category or "culture").strip().lower()
    footer = (
        (proposal.footer or "").strip()
        or "Separate markets grouped together. They do not add up to 100%."
    )

    for rule_err in (
        check_scout_voice_words(name, kicker, why, footer),
        check_scout_no_mechanical_sales_downloads(name, why, deduped_rows),
        check_scout_no_politics_only_set(category, name, deduped_rows),
        check_scout_map_look_places(look, deduped_rows),
        check_scout_blurb_matches_members(why, deduped_rows, dropped_rows),
    ):
        if rule_err is not None:
            return None, rule_err

    return (
        ScoutValidatedSet(
            slug=slug,
            name=name,
            kicker=kicker,
            category=category,
            why_better_together=why,
            look=look,
            members=tuple(deduped_rows),
            selector_kind=selector_kind,
            title_ilike=(proposal.title_ilike or "").strip() or None,
            template=(proposal.template or "").strip() or None,
            footer=footer,
            dropped_members=tuple(dropped),
            deduped_members=tuple(deduped_pairs),
        ),
        None,
    )


# ---------------------------------------------------------------------------
# Step 4: Decide 60-A / 73-A rule file generation
# ---------------------------------------------------------------------------


def build_scout_rule_file_definition(
    validated_set: ScoutValidatedSet,
    *,
    model_used: str,
    created_at: datetime,
    licence_state: str = LICENCE_AWAITING_LOOK,
) -> dict[str, Any]:
    """Build a Decide 60-A / 73-A validated container JSON definition.

    Cross-family sets select members by ``rule.selector = {"fun_tag": slug}``
    (never a bare hand list of market IDs). ``look == "faces"`` enforces
    ``image_credit_required: true`` per Ruling 195-A.
    """
    rule: dict[str, Any] = {
        "producer": "fun_scout_set",
        "min_numbered_members": SCOUT_MIN_LIVE_MEMBERS,
        "card_rows": min(5, len(validated_set.members)),
        "twins": "dedupe",
        "normalize": False,
        "relation": "same_subject",
        "refusal": "min-members",
        "materialize": "read-time",
        "look": validated_set.look,
        "image_credit_required": validated_set.look == "faces",
    }
    if validated_set.selector_kind == "title_ilike" and validated_set.title_ilike:
        rule["title_ilike"] = validated_set.title_ilike
        if validated_set.template:
            rule["template"] = validated_set.template
    else:
        rule["selector"] = {"fun_tag": validated_set.slug}

    definition: dict[str, Any] = {
        "slug": validated_set.slug,
        "stage": "preview",
        "membership": "computed-produced",
        "kind": "roundup",
        "relations": ["same_subject"],
        "level": "related",
        "kicker": validated_set.kicker,
        "name": validated_set.name,
        "category": validated_set.category,
        "tag": validated_set.category.upper(),
        "section_title": validated_set.name,
        "footer": validated_set.footer,
        "why_better_together": validated_set.why_better_together,
        "look": validated_set.look,
        "image_credit_required": validated_set.look == "faces",
        "novelty_seat": True,
        "scout": {
            "origin": "discover_fun_scout",
            "model": model_used,
            "licence_state": licence_state,
            "requires_fable_look": True,
            "auto_promote": SCOUT_AUTO_PROMOTE_TO_PUBLIC,
            "requires_keep_to_publish": True,
            "public_promotion_gate": SCOUT_PUBLIC_PROMOTION_GATE,
            "created_at": created_at.astimezone(timezone.utc).isoformat(),
            "verified_member_count": len(validated_set.members),
            "fun_tag": validated_set.slug,
        },
        "rule": rule,
    }
    return validate_roundup_definition(definition)


def _assert_staged_output_is_non_public(output_dir: Path) -> None:
    """Refuse writing staged scout sets into the public containers dir."""
    resolved_out = output_dir.resolve()
    containers_dir = CONTAINERS_DATA_DIR.resolve()
    if resolved_out == containers_dir or containers_dir in resolved_out.parents:
        raise ValueError(
            f"Refusing to stage scout sets inside public containers dir {containers_dir}; "
            "promotion requires explicit Alex Keep."
        )


def _assert_staged_definition(defn: Mapping[str, Any]) -> None:
    """Enforce Ruling 385: A invariant: no staged set may self-publish."""
    scout_meta = defn.get("scout") or {}
    if (
        defn.get("stage") != "preview"
        or scout_meta.get("auto_promote") is not False
        or scout_meta.get("requires_keep_to_publish") is not True
    ):
        raise ValueError(
            f"Staged scout definition {defn.get('slug')!r} must stay preview with explicit Keep gate"
        )


def write_scout_rule_files(
    validated_sets: Sequence[ScoutValidatedSet],
    output_dir: Path,
    *,
    model_used: str,
    created_at: datetime,
    licence_state: ScoutLicenceState,
    max_new_per_day: int = SCOUT_MAX_NEW_SETS_PER_DAY,
) -> list[Path]:
    """Write at most ``max_new_per_day`` staged preview rule files."""
    if licence_state.status == LICENCE_SUSPENDED:
        logger.warning(
            "Fun scout is suspended (%s); writing 0 rule files",
            licence_state.suspended_reason or "wrong card served",
        )
        return []

    _assert_staged_output_is_non_public(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for vset in validated_sets[: max(0, int(max_new_per_day))]:
        defn = build_scout_rule_file_definition(
            vset,
            model_used=model_used,
            created_at=created_at,
            licence_state=licence_state.status,
        )
        _assert_staged_definition(defn)
        target = output_dir / f"{vset.slug}.json"
        target.write_text(json.dumps(defn, indent=2) + "\n", encoding="utf-8")
        written.append(target)
    return written


# ---------------------------------------------------------------------------
# Step 5 & 6: Licence state & retired-sets learning store
# ---------------------------------------------------------------------------


def advance_scout_licence_clean_day(
    state: ScoutLicenceState, day_iso: str
) -> ScoutLicenceState:
    """Record one clean day without auto-promoting (Ruling 385: A requires Keep)."""
    if state.status == LICENCE_SUSPENDED:
        return state
    if state.last_clean_day == day_iso:
        return state
    state.clean_days += 1
    state.last_clean_day = day_iso
    return state


def suspend_scout_licence_on_wrong_card(
    state: ScoutLicenceState,
    *,
    slug: str,
    reason: str,
    at: datetime,
) -> ScoutLicenceState:
    """One wrong card served suspends the scout immediately (Decide 61-A)."""
    state.status = LICENCE_SUSPENDED
    state.suspended_slug = slug
    state.suspended_reason = reason
    state.suspended_at = at.astimezone(timezone.utc).isoformat()
    return state


def load_retired_scout_sets(path: Path = SCOUT_RETIRED_SETS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, Mapping)]
    if isinstance(raw, Mapping) and isinstance(raw.get("retired_sets"), list):
        return [dict(item) for item in raw["retired_sets"] if isinstance(item, Mapping)]
    return []


def retire_scout_set(
    retired_sets: list[dict[str, Any]],
    *,
    slug: str,
    name: str,
    reason: str,
    retired_at: datetime,
) -> list[dict[str, Any]]:
    """Record a set Alex graded down so future scout runs learn not to repeat it."""
    clean_slug = _slugify(slug or name)
    entry = {
        "slug": clean_slug,
        "name": name.strip(),
        "reason": reason.strip(),
        "retired_at": retired_at.astimezone(timezone.utc).isoformat(),
    }
    updated = [r for r in retired_sets if _slugify(str(r.get("slug") or "")) != clean_slug]
    updated.append(entry)
    return updated


# ---------------------------------------------------------------------------
# Step 2: Model prompts, response parsing, and two-stage runner
# ---------------------------------------------------------------------------


def _extract_response_text(response: Any) -> str:
    """Extract text from either an OpenAI ChatCompletion or Anthropic Message."""
    choices = getattr(response, "choices", None)
    if choices:
        msg = getattr(choices[0], "message", None)
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            return content
    content_blocks = getattr(response, "content", None)
    if isinstance(content_blocks, list):
        parts = [
            getattr(block, "text", "")
            for block in content_blocks
            if isinstance(getattr(block, "text", None), str)
        ]
        if parts:
            return "\n".join(parts)
    if isinstance(content_blocks, str):
        return content_blocks
    return ""


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _approved_examples_summary(
    seed_entries: Sequence[FunMarketEntry],
    sub_tag_descriptions: Optional[Mapping[str, str]] = None,
) -> list[dict[str, Any]]:
    by_group: dict[str, list[str]] = {}
    for entry in seed_entries:
        tags = entry.sub_tags or (entry.fun_bucket,)
        for group in tags:
            by_group.setdefault(group, []).append(entry.title)
    if sub_tag_descriptions is None:
        try:
            sub_tag_descriptions = load_fun_markets_registry().sub_tags
        except OSError:
            sub_tag_descriptions = {}
    return [
        {
            "group": group,
            "description": str(sub_tag_descriptions.get(group) or ""),
            "sample_titles": titles[:8],
            "count": len(titles),
        }
        for group, titles in sorted(by_group.items())
    ]


def _tag_chunk_recursive(
    chunk: Sequence[ScoutMarketRow],
    *,
    openai_client: Any,
    system_prompt: str,
    job_budget: Optional[JobBudget],
    depth: int = 0,
) -> tuple[list[ScoutTaggedMarket], float]:
    lines = [f"{m.market_id} | {m.source} | {m.category or ''} | {m.title}" for m in chunk]
    user_prompt = f"Markets ({len(chunk)}):\n" + "\n".join(lines)
    result = complete_chat_detailed(
        "fun_scout_tag",
        openai_client,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_output_tokens=_TAG_MAX_OUTPUT_TOKENS_PER_BATCH,
        temperature=0.2,
        job_budget=job_budget,
        response_format={"type": "json_object"},
    )
    cost = float(result.cost_usd or 0.0)
    choices = getattr(result.response, "choices", None)
    finish_reason = getattr(choices[0], "finish_reason", None) if choices else None
    if finish_reason == "length" and len(chunk) > 1 and depth < 4:
        mid = len(chunk) // 2
        left_tagged, left_cost = _tag_chunk_recursive(
            chunk[:mid],
            openai_client=openai_client,
            system_prompt=system_prompt,
            job_budget=job_budget,
            depth=depth + 1,
        )
        right_tagged, right_cost = _tag_chunk_recursive(
            chunk[mid:],
            openai_client=openai_client,
            system_prompt=system_prompt,
            job_budget=job_budget,
            depth=depth + 1,
        )
        return left_tagged + right_tagged, cost + left_cost + right_cost

    payload = _parse_json_object(_extract_response_text(result.response))
    items_out: list[ScoutTaggedMarket] = []
    for item in payload.get("tagged") or []:
        if not isinstance(item, Mapping):
            continue
        try:
            mid = int(item["market_id"])
        except (KeyError, TypeError, ValueError):
            continue
        items_out.append(
            ScoutTaggedMarket(
                market_id=mid,
                fun_group=str(item.get("fun_group") or "fun").strip().lower(),
                reason=str(item.get("reason") or "").strip()[:120],
                is_fun_single=bool(item.get("is_fun_single")),
                set_hint=(
                    str(item["set_hint"]).strip()[:80]
                    if item.get("set_hint")
                    else None
                ),
            )
        )
    return items_out, cost


def run_scout_tagging_pass(
    markets: Sequence[ScoutMarketRow],
    *,
    openai_client: Any,
    approved_examples: Sequence[FunMarketEntry],
    retired_sets: Sequence[Mapping[str, Any]] = (),
    job_budget: Optional[JobBudget] = None,
    batch_size: int = _TAG_BATCH_SIZE,
) -> tuple[list[ScoutTaggedMarket], float]:
    """Run the small-model high-recall tagging pass over open non-sports titles."""
    examples_json = json.dumps(_approved_examples_summary(approved_examples))
    retired_json = json.dumps(
        [{"name": r.get("name"), "reason": r.get("reason")} for r in retired_sets[:12]]
    )
    system_prompt = (
        "You are filtering prediction markets for Bain Luck's Discover feed. "
        "Keep EVERY market that belongs to any approved theme OR could anchor a clever, "
        "conversation-worthy set (pop culture, movies, music, awards, TV finales, games, "
        "Christmas/snow cities, Taylor Swift, Elon Musk, James Bond, Pope Leo XIV, space, "
        "science/unsolved mysteries, celebrity engagements, internet lore, everyday food/gas "
        "prices, year-end Super Bowl/Google/Spotify/TIME lists).\n"
        f"Approved themes and example titles (all must be represented): {examples_json}\n"
        f"Retired sets (do NOT pick sets matching these): {retired_json}\n"
        "High-recall rules:\n"
        "- Inspect EVERY numbered market in this batch one by one and return EVERY match — "
        "do NOT cap or cherry-pick only a few per batch (batches often contain 8–20 valid matches).\n"
        "- Pay special attention to frequently missed approved themes: `elon-musk`, `space`, "
        "`unsolved-problems`, `james-bond`, `long-awaited`, `year-end`, `who-shows-up`, "
        "`pope-leo-xiv`, `engagements`, `everyday-prices`, `christmas`, `white-christmas`, "
        "`tv-finales`, and `taylor-swift`.\n"
        "- If a market fits ANY approved theme — even a modest city weather question, movie RT score, "
        "TV winner, music album/song, Pope/Taylor Swift/Bond/Space market, or Costco/fast-food price — "
        "ALWAYS include it and set `fun_group` to that theme slug (e.g. `taylor-swift`, `white-christmas`, "
        "`christmas`, `james-bond`, `space`, `unsolved-problems`, `tv-finales`, `engagements`, `pope-leo-xiv`, "
        "`everyday-prices`, `super-bowl-culture`, `year-end`, `movies`, `long-awaited`, `long-shot`, `who-shows-up`, `elon-musk`).\n"
        "- EXCLUDE routine sports, Fed/CPI/GDP/unemployment prints, monthly point-of-sale or sales-growth "
        "series, monthly app download counts, routine elections/cabinet/head-of-state/geopolitical conflict markets "
        "(NOTE: keep non-political curiosity markets misfiled under politics like Pope Leo XIV, aliens/UFOs, "
        "Miss Universe, World Happiness, Nobel Peace Prize), and any named person's pregnancy/health/affair/"
        "divorce/arrest/trial/death or violence/war/nuclear weapons (engagements ARE allowed).\n"
        "- Keep `reason` to <= 6 words.\n"
        'Return strict JSON: {"tagged": [{"market_id": int, "fun_group": str, '
        '"is_fun_single": bool, "set_hint": str|null, "reason": str}]}.'
    )

    tagged_by_id: dict[int, ScoutTaggedMarket] = {}
    total_cost = 0.0
    step = max(1, int(batch_size))
    for i in range(0, len(markets), step):
        chunk = markets[i : i + step]
        chunk_tagged, chunk_cost = _tag_chunk_recursive(
            chunk,
            openai_client=openai_client,
            system_prompt=system_prompt,
            job_budget=job_budget,
        )
        total_cost += chunk_cost
        for item in chunk_tagged:
            if item.market_id not in tagged_by_id:
                tagged_by_id[item.market_id] = item
    return list(tagged_by_id.values()), round(total_cost, 6)


def run_scout_set_writing_pass(
    tagged_markets: Sequence[ScoutTaggedMarket],
    catalog_by_id: Mapping[int, ScoutMarketRow],
    uncovered_families: Sequence[ScoutUncoveredFamily],
    *,
    anthropic_client: Any,
    approved_examples: Sequence[FunMarketEntry],
    retired_sets: Sequence[Mapping[str, Any]] = (),
    morning_grades: Sequence[Mapping[str, Any]] = (),
    job_budget: Optional[JobBudget] = None,
    min_volume: float = FUN_TAG_DEFAULT_MIN_LIFETIME_VOLUME,
    now: Optional[datetime] = None,
) -> tuple[list[ScoutProposedSet], str, float]:
    """Run the Claude set-writing pass to propose novel Discover sets."""
    system_prompt = (
        "You are Bain Luck's nightly Fun Scout. Your job is to invent 20 to 26 crisp, "
        "shareable sets of prediction markets that are genuinely better together "
        'than alone — the kind a person texts to a friend (e.g. "Will it ever '
        'come out?", "White Christmas", "How 2026 gets summed up").\n'
        "Coverage rule: FIRST write one strong set for EVERY non-empty `group` listed in "
        "`Tagged group counts` below that has >= 3 live candidates (explicitly covering present "
        "approved themes like `taylor-swift`, `engagements`, `james-bond`, `pope-leo-xiv`, `space`, "
        "`unsolved-problems`, `tv-finales`, `movies`, `long-awaited`, `long-shot`, `who-shows-up`, "
        "`elon-musk`, `year-end`, `super-bowl-culture`, `everyday-prices`, `christmas`, "
        "`white-christmas`), BEFORE spending extra slots on duplicate topics or bonus ideas.\n"
        "Rules (enforced automatically in code — any violation drops the set):\n"
        "1. Every set needs at least 3 distinct live markets from `Live tagged fun candidates`; "
        "prefer 4 to 6 `member_ids` whenever a theme has >= 4 candidates so every set has depth.\n"
        "2. Never put two venues' copies of the same market in one set.\n"
        "3. Voice ban: NEVER use the words `trader`, `traders`, `bet`, `bets`, or `betting` "
        "in the set name, kicker, why_better_together, or footer. Write for casual readers.\n"
        "4. Blurb honesty & brevity: keep `why_better_together` to ONE crisp sentence (<= 25 words) "
        "and mention ONLY markets, people, couples, albums, books, movies, or facts whose exact "
        "`market_id` is in `member_ids` — NEVER cite an `Approved examples` sample or outside title "
        "unless its exact `market_id` is in `member_ids`.\n"
        '5. Visual look: choose `"map"` ONLY when EVERY market title in `member_ids` explicitly names '
        "a specific city, state, ski resort, mountain, or lake; choose `faces` for specific people "
        "(requires credited portraits); otherwise choose `bars` (including global storms/volcanoes).\n"
        "6. No mechanical financial metrics (never group monthly sales growth, POS growth, or app downloads).\n"
        "7. No politics-only, cabinet/government-exit, or routine election sets.\n"
        "8. Taste guard: no named person's pregnancy, health, affairs, divorce, arrest, trial, or death "
        "(engagements are allowed); no war/violence/nukes. Never repeat a retired/down-graded set.\n"
        "Return strict JSON only:\n"
        '{"sets": [{"slug": str, "name": str, "kicker": str, "category": str, '
        '"why_better_together": str, "look": "map"|"faces"|"bars", '
        '"selector_kind": "fun_tag"|"title_ilike", "title_ilike": str|null, '
        '"template": str|null, "footer": str|null, "member_ids": [int, ...]}]}'
    )

    live_rows_raw: list[tuple[ScoutTaggedMarket, ScoutMarketRow]] = []
    for t in tagged_markets:
        row = catalog_by_id.get(t.market_id)
        if row is None:
            continue
        ok, _ = check_scout_member(row, min_volume=min_volume, now=now)
        if not ok:
            continue
        live_rows_raw.append((t, row))

    deduped_rows, _ = dedupe_cross_venue_members([row for _t, row in live_rows_raw])
    kept_ids = {row.market_id for row in deduped_rows}
    live_candidates = [pair for pair in live_rows_raw if pair[1].market_id in kept_ids]

    live_candidates.sort(
        key=lambda pair: (
            pair[0].fun_group,
            -(float(pair[1].volume) if pair[1].volume is not None else -1.0),
            pair[1].market_id,
        )
    )
    group_counts: dict[str, int] = {}
    for t, _row in live_candidates:
        group_counts[t.fun_group] = group_counts.get(t.fun_group, 0) + 1
    candidate_lines = [
        f"{row.market_id} | {row.source} | {row.category or ''} | "
        f"group={t.fun_group} | hint={t.set_hint or ''} | {row.title}"
        for t, row in live_candidates
    ]
    family_lines = [
        f"{f.family_key} (open={f.open_count}, sample={f.sample_title})"
        for f in uncovered_families[:80]
    ]
    user_prompt = (
        f"Approved examples: {json.dumps(_approved_examples_summary(approved_examples))}\n"
        f"Retired sets (do NOT repeat): {json.dumps(list(retired_sets)[:20])}\n"
        f"Recent morning grades: {json.dumps(list(morning_grades)[:20])}\n"
        f"Uncovered sentinel families ({len(family_lines)}):\n"
        + "\n".join(family_lines)
        + f"\n\nTagged group counts ({len(group_counts)} themes): "
        + json.dumps(dict(sorted(group_counts.items())))
        + f"\nLive tagged fun candidates ({len(candidate_lines)}, grouped by theme):\n"
        + "\n".join(candidate_lines)
    )

    result = complete_chat_detailed(
        "fun_scout_sets",
        anthropic_client,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_output_tokens=_DEFAULT_SET_OUTPUT_TOKENS,
        temperature=0.3,
        job_budget=job_budget,
    )
    if getattr(result.response, "stop_reason", None) == "max_tokens":
        logger.warning(
            "[discover-fun-scout] set-writing pass hit max_tokens (%d) on model %s; "
            "JSON output may be truncated",
            _DEFAULT_SET_OUTPUT_TOKENS,
            result.model,
        )
    payload = _parse_json_object(_extract_response_text(result.response))
    proposals: list[ScoutProposedSet] = []
    for raw_set in payload.get("sets") or []:
        if not isinstance(raw_set, Mapping):
            continue
        raw_ids = raw_set.get("member_ids") or []
        member_ids: list[int] = []
        for mid in raw_ids:
            try:
                member_ids.append(int(mid))
            except (TypeError, ValueError):
                continue
        proposals.append(
            ScoutProposedSet(
                slug=str(raw_set.get("slug") or ""),
                name=str(raw_set.get("name") or ""),
                kicker=str(raw_set.get("kicker") or "DISCOVER SET"),
                category=str(raw_set.get("category") or "culture"),
                why_better_together=str(raw_set.get("why_better_together") or ""),
                look=str(raw_set.get("look") or "bars"),
                member_ids=tuple(member_ids),
                selector_kind=str(raw_set.get("selector_kind") or "fun_tag"),
                title_ilike=(
                    str(raw_set["title_ilike"]) if raw_set.get("title_ilike") else None
                ),
                template=str(raw_set["template"]) if raw_set.get("template") else None,
                footer=str(raw_set["footer"]) if raw_set.get("footer") else None,
            )
        )
    return proposals, result.model, round(result.cost_usd or 0.0, 6)


def run_nightly_fun_scout(
    markets: Sequence[ScoutMarketRow],
    uncovered_families: Sequence[ScoutUncoveredFamily],
    *,
    openai_client: Any,
    anthropic_client: Any,
    output_dir: Optional[Path] = None,
    approved_examples: Optional[Sequence[FunMarketEntry]] = None,
    retired_sets: Sequence[Mapping[str, Any]] = (),
    morning_grades: Sequence[Mapping[str, Any]] = (),
    existing_slugs: frozenset[str] = frozenset(),
    licence_state: Optional[ScoutLicenceState] = None,
    prior_monthly_spend_usd: float = 0.0,
    min_volume: float = FUN_TAG_DEFAULT_MIN_LIFETIME_VOLUME,
    max_new_per_day: int = SCOUT_MAX_NEW_SETS_PER_DAY,
    now: Optional[datetime] = None,
    pretagged: Optional[tuple[Sequence[ScoutTaggedMarket], float]] = None,
) -> dict[str, Any]:
    """Run the full end-to-end Nightly Fun Scout pipeline under 61-A caps."""
    run_now = now or datetime.now(timezone.utc)
    examples = (
        list(approved_examples)
        if approved_examples is not None
        else list(load_fun_markets_registry().markets.values())
    )
    lic = licence_state or ScoutLicenceState()

    estimate = estimate_fun_scout_spend(
        len(markets),
        prior_monthly_spend_usd=prior_monthly_spend_usd,
    )
    spend_line = assert_fun_scout_within_caps(estimate)

    job_budget = JobBudget(SCOUT_RUN_CAP_USD)
    catalog_by_id = {m.market_id: m for m in markets}

    if pretagged is not None:
        tagged = list(pretagged[0])
        tag_cost = round(float(pretagged[1]), 6)
    else:
        tagged, tag_cost = run_scout_tagging_pass(
            markets,
            openai_client=openai_client,
            approved_examples=examples,
            retired_sets=retired_sets,
            job_budget=job_budget,
        )
    proposals, set_model_used, set_cost = run_scout_set_writing_pass(
        tagged,
        catalog_by_id,
        uncovered_families,
        anthropic_client=anthropic_client,
        approved_examples=examples,
        retired_sets=retired_sets,
        morning_grades=morning_grades,
        job_budget=job_budget,
        min_volume=min_volume,
        now=run_now,
    )

    retired_slugs = frozenset(
        _slugify(str(r.get("slug") or r.get("name") or "")) for r in retired_sets
    )
    retired_title_keys = frozenset(
        _normalized_title_key(str(r.get("name") or "")) for r in retired_sets
    )

    validated: list[ScoutValidatedSet] = []
    rejected: list[dict[str, Any]] = []
    seen_slugs = set(existing_slugs)
    for prop in proposals:
        vset, err = validate_scout_proposed_set(
            prop,
            catalog_by_id,
            retired_slugs=retired_slugs,
            retired_title_keys=retired_title_keys,
            existing_slugs=frozenset(seen_slugs),
            min_volume=min_volume,
            now=run_now,
        )
        if vset is not None:
            validated.append(vset)
            seen_slugs.add(vset.slug)
        else:
            rejected.append({"slug": prop.slug, "name": prop.name, "reason": err})

    written_files: list[str] = []
    if output_dir is not None:
        paths = write_scout_rule_files(
            validated,
            output_dir,
            model_used=set_model_used,
            created_at=run_now,
            licence_state=lic,
            max_new_per_day=max_new_per_day,
        )
        written_files = [str(p) for p in paths]

    # Verify fun singles in code as well
    verified_singles = []
    for t in tagged:
        if not t.is_fun_single:
            continue
        row = catalog_by_id.get(t.market_id)
        ok, _ = check_scout_member(row, min_volume=min_volume, now=run_now)
        if ok and row is not None:
            verified_singles.append(
                {
                    "market_id": row.market_id,
                    "title": row.title,
                    "fun_group": t.fun_group,
                    "reason": t.reason,
                }
            )

    return {
        "spend_line": spend_line,
        "estimate": estimate,
        "actual_tag_cost_usd": tag_cost,
        "actual_set_cost_usd": set_cost,
        "actual_total_cost_usd": round(tag_cost + set_cost, 6),
        "set_model": set_model_used,
        "tagged_count": len(tagged),
        "verified_singles": verified_singles,
        "proposed_set_count": len(proposals),
        "validated_sets": validated,
        "rejected_sets": rejected,
        "written_rule_files": written_files,
        "licence_state": lic.to_dict(),
    }


# ---------------------------------------------------------------------------
# Benchmark comparison against Fable's 17 hand-made seed sets (#13102)
# ---------------------------------------------------------------------------


def evaluate_scout_against_seed_sets(
    validated_sets: Sequence[ScoutValidatedSet],
    seed_entries: Optional[Mapping[int, FunMarketEntry]] = None,
    *,
    min_overlap_members: int = 2,
) -> dict[str, Any]:
    """Measure how many of Fable's 17 hand-made sets the scout rebuilt."""
    entries = seed_entries if seed_entries is not None else load_fun_markets_registry().markets
    seed_groups: dict[str, set[int]] = {}
    for mid, entry in entries.items():
        for tag in entry.sub_tags or (entry.fun_bucket,):
            seed_groups.setdefault(tag, set()).add(mid)

    scout_sets_by_slug = {
        v.slug: {m.market_id for m in v.members} for v in validated_sets
    }
    matched_seed_groups: list[dict[str, Any]] = []
    missed_seed_groups: list[str] = []
    matched_scout_slugs: set[str] = set()

    for group_name, seed_ids in sorted(seed_groups.items()):
        best_slug = None
        best_overlap = 0
        for slug, scout_ids in scout_sets_by_slug.items():
            overlap = len(seed_ids & scout_ids)
            if overlap > best_overlap:
                best_overlap = overlap
                best_slug = slug
        threshold = min(min_overlap_members, len(seed_ids))
        if best_slug is not None and best_overlap >= threshold:
            matched_scout_slugs.add(best_slug)
            matched_seed_groups.append(
                {
                    "seed_group": group_name,
                    "scout_slug": best_slug,
                    "overlap": best_overlap,
                    "seed_size": len(seed_ids),
                    "recall": round(best_overlap / max(1, len(seed_ids)), 3),
                }
            )
        else:
            missed_seed_groups.append(group_name)

    novel_scout_sets = [
        {"slug": v.slug, "name": v.name, "member_count": len(v.members)}
        for v in validated_sets
        if v.slug not in matched_scout_slugs
    ]
    return {
        "seed_group_count": len(seed_groups),
        "matched_seed_count": len(matched_seed_groups),
        "matched_seed_groups": matched_seed_groups,
        "missed_seed_groups": missed_seed_groups,
        "novel_scout_sets": novel_scout_sets,
        "default_set_model": default_model_for_task("fun_scout_sets"),
    }


def evaluate_tagging_pass_against_seed_sets(
    tagged_markets: Sequence[ScoutTaggedMarket],
    input_markets: Sequence[ScoutMarketRow],
    seed_entries: Optional[Mapping[int, FunMarketEntry]] = None,
) -> dict[str, Any]:
    """Measure per-seed-group input presence vs first-pass tagging survival (#13102)."""
    entries = seed_entries if seed_entries is not None else load_fun_markets_registry().markets
    input_ids = {m.market_id for m in input_markets}
    tagged_ids = {t.market_id for t in tagged_markets}

    seed_groups: dict[str, set[int]] = {}
    unique_seed_ids: set[int] = set()
    for mid, entry in entries.items():
        unique_seed_ids.add(mid)
        for tag in entry.sub_tags or (entry.fun_bucket,):
            seed_groups.setdefault(tag, set()).add(mid)

    groups_report: list[dict[str, Any]] = []
    for group_name, seed_ids in sorted(seed_groups.items()):
        in_input = len(seed_ids & input_ids)
        survived = len(seed_ids & tagged_ids)
        groups_report.append(
            {
                "seed_group": group_name,
                "seed_size": len(seed_ids),
                "in_input": in_input,
                "survived_first_pass": survived,
            }
        )

    return {
        "tagged_count": len(tagged_ids),
        "input_count": len(input_ids),
        "unique_seed_total": len(unique_seed_ids),
        "unique_seed_in_input": len(unique_seed_ids & input_ids),
        "unique_seed_survived": len(unique_seed_ids & tagged_ids),
        "groups": groups_report,
    }


def build_fun_scout_set_producer(definition: Mapping[str, Any]) -> Any:
    """Build a ``RoundupProducer`` from a Nightly Fun Scout rule definition (#13102)."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import FuturesMarket
    from app.utils.container_presentation import market_destination
    from app.utils.discover_fun_tags import fun_market_ids_for_sub_tag
    from app.utils.roundup_containers import (
        RoundupMembers,
        RoundupProducer,
        RoundupRefusal,
    )

    validated = validate_roundup_definition(dict(definition))
    if isinstance(validated.get("sections"), Sequence) and not isinstance(
        validated.get("sections"), (str, bytes)
    ) and len(validated["sections"]) > 0:
        from app.utils.container_machinery import build_container_machinery_producer

        return build_container_machinery_producer(validated)

    rule = dict(validated.get("rule") or {})
    selector = rule.get("selector") if isinstance(rule.get("selector"), Mapping) else {}
    fun_tag = str(selector.get("fun_tag") or "").strip()
    title_ilike = str(rule.get("title_ilike") or selector.get("title_ilike") or "").strip()
    min_members = max(1, int(rule.get("min_numbered_members") or SCOUT_MIN_LIVE_MEMBERS))
    card_rows = max(1, int(rule.get("card_rows") or 4))
    open_status = "open"

    async def _produce(db: Any) -> RoundupMembers | RoundupRefusal:
        if title_ilike:
            stmt = (
                select(FuturesMarket)
                .options(selectinload(FuturesMarket.outcomes))
                .where(
                    FuturesMarket.status == open_status,
                    FuturesMarket.name.ilike(title_ilike),
                )
                .limit(50)
            )
            market_rows = list((await db.execute(stmt)).scalars().all())
        elif fun_tag:
            candidate_ids = [int(mid) for mid in fun_market_ids_for_sub_tag(fun_tag)]
            if not candidate_ids:
                return RoundupRefusal(("empty_fun_scout_selector",))
            stmt = (
                select(FuturesMarket)
                .options(selectinload(FuturesMarket.outcomes))
                .where(
                    FuturesMarket.status == open_status,
                    FuturesMarket.id.in_(candidate_ids),
                )
            )
            market_rows = list((await db.execute(stmt)).scalars().all())
        else:
            return RoundupRefusal(("missing_fun_scout_selector",))

        market_rows.sort(
            key=lambda m: (
                -(float(getattr(m, "volume", None) or 0.0)),
                int(getattr(m, "id", 0) or 0),
            )
        )
        if len(market_rows) < min_members:
            return RoundupRefusal(
                (f"too_few_live_members:{len(market_rows)}<{min_members}",)
            )

        member_cards: list[dict[str, Any]] = []
        rows_out: list[dict[str, Any]] = []
        default_category = str(validated.get("category") or "culture")
        for m in market_rows:
            mid = int(getattr(m, "id"))
            title = str(getattr(m, "question", None) or getattr(m, "name", None) or "").strip()
            if not title:
                continue
            outs = sorted(
                list(getattr(m, "outcomes", None) or ()),
                key=lambda o: (
                    getattr(o, "rank", None) or 9999,
                    -(float(getattr(o, "current_probability", None) or 0.0)),
                ),
            )
            lead = outs[0] if outs else None
            raw_prob = getattr(lead, "current_probability", None) if lead else None
            prob = float(raw_prob) if raw_prob is not None else 0.5
            raw_delta = getattr(lead, "probability_change_24h", None) if lead else None
            delta = float(raw_delta) if raw_delta is not None else None
            lead_name = str(getattr(lead, "name", None) or "Yes") if lead else "Yes"
            member_cards.append(
                {
                    "id": mid,
                    "name": title,
                    "question": title,
                    "category": str(getattr(m, "category", None) or default_category),
                    "top_outcomes": [
                        {
                            "name": lead_name,
                            "probability": round(prob, 4),
                            "movement": round(delta, 4) if delta is not None else None,
                        }
                    ],
                    "destination": market_destination(mid),
                }
            )
            rows_out.append(
                {
                    "label": title,
                    "probability": round(prob, 4),
                    "rendered_percent": round(prob * 100),
                    "movement": round(delta, 4) if delta is not None else None,
                    "destination_href": f"/markets/{mid}",
                }
            )

        if len(member_cards) < min_members:
            return RoundupRefusal(
                (f"too_few_live_members:{len(member_cards)}<{min_members}",)
            )

        return RoundupMembers(
            member_cards,
            rows_out[:card_rows],
            footer=str(validated.get("footer") or ""),
            title=str(validated["name"]),
            kicker=str(validated.get("kicker") or "CURIOSITIES"),
            destination_href=validated.get("destination_href"),
        )

    return RoundupProducer(
        slug=str(validated["slug"]),
        name=str(validated["name"]),
        kind=str(validated.get("kind") or "roundup"),
        category=str(validated.get("category") or "culture"),
        section_title=validated.get("section_title") or str(validated["name"]),
        footer=str(validated.get("footer") or ""),
        produce=_produce,
        membership=str(validated.get("membership") or "computed-produced"),
        relations=tuple(validated["relations"]),
        level=str(validated["level"]),
        rule=rule,
        tag=validated.get("tag"),
        kicker=str(validated.get("kicker") or "CURIOSITIES"),
        destination_href=validated.get("destination_href"),
        stage=str(validated.get("stage") or "preview"),
        look=str(validated.get("look") or "bars"),
        enabled=(lambda: bool(validated["enabled"])) if "enabled" in validated else None,
    )

