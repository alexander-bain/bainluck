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
import os
import re
from dataclasses import dataclass, field
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
from app.utils.roundup_containers import validate_roundup_definition

logger = logging.getLogger(__name__)

#: Dedicated Anthropic key for the scout on Heroku app ``bainluck`` (#13102).
#: Read from this variable and nothing else (never ``ANTHROPIC_API_KEY``).
SCOUT_ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY_SCOUT"
#: Feature gate for the scheduled nightly task (OFF until Wed Nov 25).
SCOUT_ENABLED_ENV = "DISCOVER_FUN_SCOUT_ENABLED"

#: Decide 61-A / Ruling 276: B hard caps.
SCOUT_RUN_CAP_USD = 5.0
SCOUT_MONTHLY_CAP_USD = 30.0

#: Decide 32-C / Ruling 276: B ship cadence and minimum set size.
SCOUT_MAX_NEW_SETS_PER_DAY = 2
SCOUT_MIN_LIVE_MEMBERS = 3

#: Decide 61-A licence ramp: 7 clean days on Fable's look earn auto-ship.
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

_TAG_BATCH_SIZE = 150
_DEFAULT_TOKENS_PER_TITLE = 22
_DEFAULT_TAG_OUTPUT_TOKENS_PER_BATCH = 900
_DEFAULT_SET_INPUT_TOKENS = 18_000
_DEFAULT_SET_OUTPUT_TOKENS = 4_000


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
    """Report whether ``ANTHROPIC_API_KEY_SCOUT`` is set and its length.

    Never returns, copies, or logs any character of the key itself.
    """
    val = os.getenv(SCOUT_ANTHROPIC_API_KEY_ENV)
    cleaned = val.strip() if isinstance(val, str) else ""
    return {
        "env": SCOUT_ANTHROPIC_API_KEY_ENV,
        "is_set": bool(cleaned),
        "length": len(cleaned),
    }


def build_scout_anthropic_client() -> Any:
    """Build an Anthropic SDK client reading ONLY ``ANTHROPIC_API_KEY_SCOUT``."""
    api_key = (os.getenv(SCOUT_ANTHROPIC_API_KEY_ENV) or "").strip()
    if not api_key:
        raise FunScoutMissingKeyError(
            f"{SCOUT_ANTHROPIC_API_KEY_ENV} is not set in this environment"
        )
    import anthropic

    return anthropic.Anthropic(api_key=api_key, timeout=120.0, max_retries=0)


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
    tag_in = count * max(1, int(tokens_per_title)) + batches * 600
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
            dropped.append((mid, reason or "rejected"))

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
            "requires_fable_look": licence_state != LICENCE_AUTO,
            "created_at": created_at.astimezone(timezone.utc).isoformat(),
            "verified_member_count": len(validated_set.members),
            "fun_tag": validated_set.slug,
        },
        "rule": rule,
    }
    return validate_roundup_definition(definition)


def write_scout_rule_files(
    validated_sets: Sequence[ScoutValidatedSet],
    output_dir: Path,
    *,
    model_used: str,
    created_at: datetime,
    licence_state: ScoutLicenceState,
    max_new_per_day: int = SCOUT_MAX_NEW_SETS_PER_DAY,
) -> list[Path]:
    """Write at most ``max_new_per_day`` rule files unless the scout is suspended."""
    if licence_state.status == LICENCE_SUSPENDED:
        logger.warning(
            "Fun scout is suspended (%s); writing 0 rule files",
            licence_state.suspended_reason or "wrong card served",
        )
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for vset in validated_sets[: max(0, int(max_new_per_day))]:
        defn = build_scout_rule_file_definition(
            vset,
            model_used=model_used,
            created_at=created_at,
            licence_state=licence_state.status,
        )
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
    """Record one clean day; seven clean days promote from Fable-look to auto."""
    if state.status == LICENCE_SUSPENDED:
        return state
    if state.last_clean_day == day_iso:
        return state
    state.clean_days += 1
    state.last_clean_day = day_iso
    if state.clean_days >= SCOUT_CLEAN_DAYS_FOR_LICENCE:
        state.status = LICENCE_AUTO
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


def _approved_examples_summary(seed_entries: Sequence[FunMarketEntry]) -> list[dict[str, Any]]:
    by_group: dict[str, list[str]] = {}
    for entry in seed_entries:
        group = entry.sub_tags[0] if entry.sub_tags else entry.fun_bucket
        by_group.setdefault(group, []).append(entry.title)
    return [
        {"group": group, "sample_titles": titles[:4], "count": len(titles)}
        for group, titles in sorted(by_group.items())
    ]


def run_scout_tagging_pass(
    markets: Sequence[ScoutMarketRow],
    *,
    openai_client: Any,
    approved_examples: Sequence[FunMarketEntry],
    retired_sets: Sequence[Mapping[str, Any]] = (),
    job_budget: Optional[JobBudget] = None,
    batch_size: int = _TAG_BATCH_SIZE,
) -> tuple[list[ScoutTaggedMarket], float]:
    """Run the small-model tagging pass over open non-sports titles (~2c/night)."""
    examples_json = json.dumps(_approved_examples_summary(approved_examples)[:12])
    retired_json = json.dumps(
        [{"name": r.get("name"), "reason": r.get("reason")} for r in retired_sets[:12]]
    )
    system_prompt = (
        "You are tagging open prediction markets for Bain Luck's Discover feed. "
        "Pick genuinely fun, conversation-worthy single markets (weird, curious, "
        "water-cooler, pop culture, science, weather, internet lore, milestones) "
        "and markets that belong in a clever group. Exclude routine sports, "
        "ordinary economic prints, local elections, and anything about a named "
        "person's pregnancy, health, affair, divorce, arrest, trial, or death "
        "(engagements are allowed). Never pick violence, war, or nuclear-weapon "
        "markets. Return strict JSON: "
        '{"tagged": [{"market_id": int, "fun_group": str, "is_fun_single": bool, '
        '"set_hint": str|null, "reason": str}]}.'
    )

    tagged: list[ScoutTaggedMarket] = []
    total_cost = 0.0
    step = max(1, int(batch_size))
    for i in range(0, len(markets), step):
        chunk = markets[i : i + step]
        lines = [f"{m.market_id} | {m.source} | {m.category or ''} | {m.title}" for m in chunk]
        user_prompt = (
            f"Approved set examples: {examples_json}\n"
            f"Retired (do NOT repeat): {retired_json}\n"
            f"Markets ({len(chunk)}):\n" + "\n".join(lines)
        )
        result = complete_chat_detailed(
            "fun_scout_tag",
            openai_client,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_output_tokens=_DEFAULT_TAG_OUTPUT_TOKENS_PER_BATCH,
            temperature=0.2,
            job_budget=job_budget,
            response_format={"type": "json_object"},
        )
        if result.cost_usd is not None:
            total_cost += result.cost_usd
        payload = _parse_json_object(_extract_response_text(result.response))
        for item in payload.get("tagged") or []:
            if not isinstance(item, Mapping):
                continue
            try:
                mid = int(item["market_id"])
            except (KeyError, TypeError, ValueError):
                continue
            tagged.append(
                ScoutTaggedMarket(
                    market_id=mid,
                    fun_group=str(item.get("fun_group") or "fun").strip().lower(),
                    reason=str(item.get("reason") or "").strip()[:160],
                    is_fun_single=bool(item.get("is_fun_single")),
                    set_hint=(
                        str(item["set_hint"]).strip()[:80]
                        if item.get("set_hint")
                        else None
                    ),
                )
            )
    return tagged, round(total_cost, 6)


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
) -> tuple[list[ScoutProposedSet], str, float]:
    """Run the Claude set-writing pass to propose novel Discover sets."""
    system_prompt = (
        "You are Bain Luck's nightly Fun Scout. Your job is to invent crisp, "
        "shareable sets of prediction markets that are genuinely better together "
        'than alone — the kind a person texts to a friend (e.g. "Will it ever '
        'come out?", "White Christmas", "How 2026 gets summed up").\n'
        "Rules:\n"
        "1. Every set needs at least 3 distinct live markets from the supplied list.\n"
        "2. Never put two venues' copies of the same market in one set.\n"
        "3. Taste guard: no named person's pregnancy, health, affairs, divorce, "
        "arrest, trial, or death (engagements are allowed); no war/violence/nukes.\n"
        "4. Choose `look` from: `map` (cities/weather/geography), `faces` "
        "(people — requires credited portraits), `bars` (everything else).\n"
        "5. Never repeat a retired or graded-down set.\n"
        "Return strict JSON only:\n"
        '{"sets": [{"slug": str, "name": str, "kicker": str, "category": str, '
        '"why_better_together": str, "look": "map"|"faces"|"bars", '
        '"selector_kind": "fun_tag"|"title_ilike", "title_ilike": str|null, '
        '"template": str|null, "footer": str|null, "member_ids": [int, ...]}]}'
    )

    candidate_lines = []
    for t in tagged_markets:
        row = catalog_by_id.get(t.market_id)
        if row is None:
            continue
        candidate_lines.append(
            f"{row.market_id} | {row.source} | {row.category or ''} | "
            f"group={t.fun_group} | hint={t.set_hint or ''} | {row.title}"
        )
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
        + f"\n\nTagged fun candidates ({len(candidate_lines)}):\n"
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
