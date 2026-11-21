"""Curated fun-market tagging, guards, and Discover admission (#13097).

Rulings 272: A & 273: B (Alex, Nov 19, 2026):

* One file keyed by market (``backend/data/discover/fun_markets.json``) holds
  the fun tag, set sub-tags (``long-shot``, ``long-awaited``, ``year-end``,
  ``space``, ``super-bowl-culture``, ``elon-musk``, ``taylor-swift``, etc.),
  and the market's true Discover subject (``odd`` or ``entertainment`` plus a
  non-misfiled category) derived from what the market is about rather than its
  stored ``llm_sport_category``.
* When ``DISCOVER_FUN_ADMISSION_ENABLED`` is on (default OFF), a tagged market
  that passes all three guards enters Discover's candidate pool regardless of
  what it traded that day (``volume_24h``). Ranking still decides the seat.
* Every tagged market must pass three code-enforced checks:
  1. **Real trading** — lifetime ``FuturesMarket.volume`` at or above the
     configured bar (default ``10,000`` contracts on Kalshi / ``$10,000`` on
     Polymarket). Missing or zero volume fails closed.
  2. **Taste guard** — no fun tag on a market about a named person's
     pregnancy, health, affairs, divorce, arrest, trial, or death. Engagements
     are explicitly allowed (Ruling 273: B).
  3. **Still ahead** — the market is open, not venue-settled or book-refused,
     not past ``resolution_date``, not title-implied stale, not past an
     entry's ``event_date``, and not matching a concluded real-world event
     whose venue markets lag settlement (e.g., Taylor Swift's wedding).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FuturesMarket
from app.utils.futures_liveness import BOOK_REFUSED_KEY, VENUE_SETTLED_KEY
from app.utils.market_staleness import is_title_implied_stale

DISCOVER_FUN_ADMISSION_ENV = "DISCOVER_FUN_ADMISSION_ENABLED"
DISCOVER_FUN_MIN_LIFETIME_VOLUME_ENV = "DISCOVER_FUN_MIN_LIFETIME_VOLUME"
FUN_TAG_DEFAULT_MIN_LIFETIME_VOLUME = 10_000

_TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
_VALID_FUN_BUCKETS = frozenset({"odd", "entertainment"})
_VALID_DISCOVER_CATEGORIES = frozenset(
    {"entertainment", "culture", "tech", "weather", "economics", "politics"}
)

FUN_MARKETS_DATA_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "discover" / "fun_markets.json"
)
CURATED_GROUPING_SETS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "groupings" / "batch3_curated_sets.json"
)
CURATED_GROUPING_SETS_PATHS: tuple[Path, ...] = (
    CURATED_GROUPING_SETS_PATH,
    Path(__file__).resolve().parents[2] / "data" / "groupings" / "batch4_curated_sets.json",
)


@lru_cache(maxsize=1)
def _load_curated_grouping_sets() -> tuple[
    dict[str, tuple[int, ...]],
    dict[tuple[str, int], str],
    dict[tuple[str, int], str],
    dict[tuple[str, int], str],
]:
    """Load curated Batch 3/4 sub-tag memberships, short labels, and headline phrases."""
    ids_by_tag: dict[str, tuple[int, ...]] = {}
    labels_by_tag_mid: dict[tuple[str, int], str] = {}
    phrases_by_tag_mid: dict[tuple[str, int], str] = {}
    with_phrases_by_tag_mid: dict[tuple[str, int], str] = {}
    for manifest_path in CURATED_GROUPING_SETS_PATHS:
        if not manifest_path.is_file():
            continue
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        for tag, spec in (raw.get("sets") or {}).items():
            tag_k = str(tag).strip().lower()
            ordered: list[int] = list(ids_by_tag.get(tag_k, ()))
            for entry in (spec or {}).get("entries") or ():
                mid = int(entry["id"])
                if mid not in ordered:
                    ordered.append(mid)
                sl = str(entry.get("short_label") or "").strip()
                if sl:
                    labels_by_tag_mid[(tag_k, mid)] = sl
                hp = str(entry.get("headline_phrase") or "").strip()
                if hp:
                    phrases_by_tag_mid[(tag_k, mid)] = hp
                hwp = str(entry.get("headline_with_phrase") or "").strip()
                if hwp:
                    with_phrases_by_tag_mid[(tag_k, mid)] = hwp
            ids_by_tag[tag_k] = tuple(ordered)
    return ids_by_tag, labels_by_tag_mid, phrases_by_tag_mid, with_phrases_by_tag_mid


@dataclass(frozen=True)
class FunMarketEntry:
    market_id: int
    title: str
    sub_tags: tuple[str, ...]
    fun_bucket: str
    discover_category: str
    set_only: bool = False
    event_date: Optional[date] = None
    unblended_twin_ids: tuple[int, ...] = ()
    short_label: Optional[str] = None
    headline_phrase: Optional[str] = None
    headline_with_phrase: Optional[str] = None


@dataclass(frozen=True)
class ConcludedEventRule:
    id: str
    event_date: date
    title_all_terms: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class FunMarketsRegistry:
    schema_version: int
    seeded_at: str
    default_min_lifetime_volume: int
    sub_tags: dict[str, str]
    concluded_events: tuple[ConcludedEventRule, ...]
    markets: dict[int, FunMarketEntry]
    ordered_market_ids: tuple[int, ...]


@dataclass(frozen=True)
class FunGuardResult:
    passed: bool
    passed_real_trading: bool
    passed_taste: bool
    passed_still_ahead: bool
    real_trading_reason: Optional[str] = None
    taste_reason: Optional[str] = None
    still_ahead_reason: Optional[str] = None

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(
            r
            for r in (
                self.real_trading_reason,
                self.taste_reason,
                self.still_ahead_reason,
            )
            if r
        )


# Taste guard patterns (Ruling 272: A & 273: B):
# No fun tag on a market about a named person's pregnancy, health, affairs,
# divorce, arrest, trial, or death. Engagements are deliberately NOT matched.
_TASTE_GUARD_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "pregnancy",
        re.compile(
            r"\b(?:pregnant|pregnancy|expecting\s+a\s+baby|have\s+a\s+baby|"
            r"give\s+birth|baby\s+bump|miscarriage)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "health",
        re.compile(
            r"\b(?:cancer|tumo(?:u)?r|hospitali[sz]ed|diagnos(?:ed|is)|"
            r"dementia|alzheimer'?s|stroke|heart\s+attack|surgery|rehab|"
            r"overdose|mental\s+breakdown|health\s+crisis|terminal\s+illness|"
            r"life\s+support|in\s+a\s+coma)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "affairs",
        re.compile(
            r"\b(?:extramarital\s+affair|have\s+an\s+affair|having\s+an\s+affair|"
            r"cheat(?:ed|ing)?\s+on|infidelity|unfaithful|mistress|sex\s+tape)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "divorce",
        re.compile(
            r"\b(?:divorce|divorced|divorcing|file\s+for\s+divorce|"
            r"split\s+up|break\s+up|breakup|annulment)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "arrest",
        re.compile(
            r"\b(?:arrest|arrested|indict(?:ed|ment)|charged\s+with|mugshot|"
            r"in\s+custody|handcuffed|jailed|sent\s+to\s+prison|imprisoned|"
            r"extradit(?:ed|ion))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "trial",
        re.compile(
            r"\b(?:murder\s+trial|criminal\s+trial|stand\s+trial|on\s+trial|"
            r"convicted|conviction|sentenced\s+to|guilty\s+verdict|"
            r"guilty\s+plea|plead\s+guilty|acquitted|granted\s+parole)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "death",
        re.compile(
            r"\b(?:die|dies|died|death|dead|pass\s+away|passed\s+away|"
            r"suicide|assassinate|assassinated|assassination|murdered|"
            r"killed|outlive|live\s+to\s+\d+)\b",
            re.IGNORECASE,
        ),
    ),
)


def is_discover_fun_admission_enabled() -> bool:
    """Return True when Discover fun-market candidate admission is switched on."""
    raw = os.getenv(DISCOVER_FUN_ADMISSION_ENV, "")
    return raw.strip().lower() in _TRUTHY_ENV_VALUES


def discover_fun_min_lifetime_volume() -> int:
    """Return the minimum lifetime trading bar for fun-tagged markets."""
    raw = os.getenv(DISCOVER_FUN_MIN_LIFETIME_VOLUME_ENV)
    if raw is not None and raw.strip():
        try:
            parsed = int(raw.strip())
            if parsed >= 0:
                return parsed
        except ValueError:
            # Ignore invalid env overrides and fall back to the registry default.
            return load_fun_markets_registry().default_min_lifetime_volume
    return load_fun_markets_registry().default_min_lifetime_volume


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    return date.fromisoformat(raw)


def _load_registry_from_path(path: Path) -> FunMarketsRegistry:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sub_tags = {
        str(k): str(v) for k, v in (payload.get("sub_tags") or {}).items()
    }
    concluded_rules: list[ConcludedEventRule] = []
    for raw_rule in payload.get("concluded_events") or []:
        terms = tuple(
            str(t).strip().lower()
            for t in (raw_rule.get("title_all_terms") or [])
            if str(t).strip()
        )
        if not terms:
            continue
        concluded_rules.append(
            ConcludedEventRule(
                id=str(raw_rule["id"]),
                event_date=date.fromisoformat(str(raw_rule["event_date"])),
                title_all_terms=terms,
                reason=str(raw_rule.get("reason") or ""),
            )
        )

    markets: dict[int, FunMarketEntry] = {}
    ordered_ids: list[int] = []
    raw_markets = payload.get("markets") or {}
    for key, item in raw_markets.items():
        market_id = int(item.get("market_id", key))
        if str(market_id) != str(key):
            raise ValueError(
                f"fun_markets.json key {key!r} disagrees with market_id {market_id}"
            )
        entry_sub_tags = tuple(str(t).strip() for t in (item.get("sub_tags") or []) if str(t).strip())
        if not entry_sub_tags:
            raise ValueError(f"fun_markets.json market {market_id} has no sub_tags")
        unknown_tags = [t for t in entry_sub_tags if sub_tags and t not in sub_tags]
        if unknown_tags:
            raise ValueError(
                f"fun_markets.json market {market_id} has unknown sub_tags {unknown_tags}"
            )
        fun_bucket = str(item.get("fun_bucket") or "").strip().lower()
        if fun_bucket not in _VALID_FUN_BUCKETS:
            raise ValueError(
                f"fun_markets.json market {market_id} has invalid fun_bucket {fun_bucket!r}"
            )
        discover_category = str(item.get("discover_category") or "").strip().lower()
        if discover_category not in _VALID_DISCOVER_CATEGORIES:
            raise ValueError(
                f"fun_markets.json market {market_id} has invalid discover_category {discover_category!r}"
            )
        twins = tuple(int(tid) for tid in (item.get("unblended_twin_ids") or []))
        raw_short_label = str(item.get("short_label") or "").strip()
        raw_headline_phrase = str(item.get("headline_phrase") or "").strip()
        raw_headline_with_phrase = str(item.get("headline_with_phrase") or "").strip()
        entry = FunMarketEntry(
            market_id=market_id,
            title=str(item.get("title") or "").strip(),
            sub_tags=entry_sub_tags,
            fun_bucket=fun_bucket,
            discover_category=discover_category,
            set_only=bool(item.get("set_only", False)),
            event_date=_parse_iso_date(item.get("event_date")),
            unblended_twin_ids=twins,
            short_label=raw_short_label or None,
            headline_phrase=raw_headline_phrase or None,
            headline_with_phrase=raw_headline_with_phrase or None,
        )
        markets[market_id] = entry
        ordered_ids.append(market_id)

    return FunMarketsRegistry(
        schema_version=int(payload.get("schema_version", 1)),
        seeded_at=str(payload.get("seeded_at") or ""),
        default_min_lifetime_volume=int(
            payload.get(
                "default_min_lifetime_volume", FUN_TAG_DEFAULT_MIN_LIFETIME_VOLUME
            )
        ),
        sub_tags=sub_tags,
        concluded_events=tuple(concluded_rules),
        markets=markets,
        ordered_market_ids=tuple(ordered_ids),
    )


@lru_cache(maxsize=1)
def _load_default_registry() -> FunMarketsRegistry:
    return _load_registry_from_path(FUN_MARKETS_DATA_PATH)


def clear_fun_markets_cache() -> None:
    """Clear the cached fun-markets registry (for tests)."""
    _load_default_registry.cache_clear()


def load_fun_markets_registry(
    path: Optional[Path] = None,
) -> FunMarketsRegistry:
    """Return the parsed fun-markets registry."""
    if path is None:
        return _load_default_registry()
    return _load_registry_from_path(path)


def get_fun_market_entry(market_id: int) -> Optional[FunMarketEntry]:
    """Return the fun-tag entry for ``market_id``, or ``None`` if untagged."""
    return load_fun_markets_registry().markets.get(int(market_id))


def all_fun_market_ids() -> tuple[int, ...]:
    """Return every tagged market ID in registry order."""
    return load_fun_markets_registry().ordered_market_ids


def fun_tags_for_market(market_id: int) -> tuple[str, ...]:
    """Return the set sub-tags for ``market_id`` (empty tuple if untagged)."""
    entry = get_fun_market_entry(market_id)
    return entry.sub_tags if entry is not None else ()


def fun_market_short_label(
    market_id: int, *, sub_tag: Optional[str] = None
) -> Optional[str]:
    """Return the sentence-ready short label for a fun-tagged market, if defined."""
    if sub_tag:
        _, labels_by_tag_mid, _, _ = _load_curated_grouping_sets()
        curated = labels_by_tag_mid.get((sub_tag.strip().lower(), int(market_id)))
        if curated:
            return curated
    entry = get_fun_market_entry(market_id)
    if entry is None:
        return None
    return entry.short_label


def fun_market_headline_phrase(
    market_id: int, *, sub_tag: Optional[str] = None
) -> Optional[str]:
    """Return an optional plain-speech headline phrase template for a curated grouping row."""
    if sub_tag:
        _, _, phrases_by_tag_mid, _ = _load_curated_grouping_sets()
        curated = phrases_by_tag_mid.get((sub_tag.strip().lower(), int(market_id)))
        if curated:
            return curated
    entry = get_fun_market_entry(market_id)
    return entry.headline_phrase if entry is not None else None


def fun_market_headline_with_phrase(
    market_id: int, *, sub_tag: Optional[str] = None
) -> Optional[str]:
    """Return an optional per-row phrase meant to follow 'with ' in a headline."""
    if sub_tag:
        _, _, _, with_phrases_by_tag_mid = _load_curated_grouping_sets()
        curated = with_phrases_by_tag_mid.get((sub_tag.strip().lower(), int(market_id)))
        if curated:
            return curated
    entry = get_fun_market_entry(market_id)
    return entry.headline_with_phrase if entry is not None else None


def fun_entry_allows_extreme_odds(entry: Optional[FunMarketEntry]) -> bool:
    """Only ``long-shot`` fun markets bypass extreme-odds suppression (#13097).

    Non-long-shot markets at 97%+ (e.g. a nearly-decided release or award)
    stay subject to the normal locked-market / near-certain filters.
    """
    return entry is not None and "long-shot" in entry.sub_tags


_FUN_PRESERVED_STORED_CATEGORIES: frozenset[str] = frozenset(
    {
        "politics",
        "geopolitics",
        "economics",
        "tech",
        "entertainment",
        "culture",
        "health",
        "weather",
    }
)


def resolve_fun_effective_category(
    stored_category: Optional[str],
    entry: Optional[FunMarketEntry],
) -> Optional[str]:
    """Keep a valid stored editorial category; use the fun tag only as fallback (#13097).

    Markets already classified into a Discover editorial category (e.g. TIME
    Person of the Year in ``entertainment`` or Nobel Peace Prize in
    ``politics``) keep their stored category so a fun tag's ``culture`` bucket
    cannot downgrade their base score while the card still competes under its
    stored category cap. Missing, ``other``, ``crypto``, ``esports``, or
    sport-tagged fun markets still receive ``entry.discover_category``.
    """
    normalized = (stored_category or "").strip().lower()
    if normalized in _FUN_PRESERVED_STORED_CATEGORIES:
        return stored_category
    if entry is not None:
        return entry.discover_category
    return stored_category


def fun_market_ids_for_sub_tag(sub_tag: str) -> tuple[int, ...]:
    """Selector helper: return tagged market IDs carrying ``sub_tag``."""
    target = (sub_tag or "").strip().lower()
    if not target:
        return ()
    curated_ids, _, _, _ = _load_curated_grouping_sets()
    if target in curated_ids:
        return curated_ids[target]
    registry = load_fun_markets_registry()
    return tuple(
        mid
        for mid in registry.ordered_market_ids
        if target in registry.markets[mid].sub_tags
    )


def check_fun_real_trading(
    volume: Optional[int | float],
    *,
    min_lifetime_volume: Optional[int] = None,
) -> tuple[bool, Optional[str]]:
    """Check 1: require real lifetime trading (not a few-dollar thin quote).

    Reads lifetime ``FuturesMarket.volume`` (contracts on Kalshi, USD on
    Polymarket), deliberately ignoring daily ``volume_24h`` so quiet
    long-running fun markets still qualify once they have real lifetime depth.
    """
    bar = (
        discover_fun_min_lifetime_volume()
        if min_lifetime_volume is None
        else int(min_lifetime_volume)
    )
    if volume is None:
        return False, "missing_volume"
    try:
        numeric = float(volume)
    except (TypeError, ValueError):
        return False, "missing_volume"
    if numeric < bar:
        return False, f"thin_trading:{int(numeric)}<{bar}"
    return True, None


def check_fun_taste_guard(
    title: Optional[str],
    description: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """Check 2: reject named-person pregnancy/health/affairs/divorce/arrest/trial/death.

    Engagements are explicitly permitted (Ruling 273: B).
    """
    text = " ".join(part for part in (title or "", description or "") if part).strip()
    if not text:
        return True, None
    for category, pattern in _TASTE_GUARD_RULES:
        if pattern.search(text):
            return False, f"taste:{category}"
    return True, None


def check_fun_still_ahead(
    *,
    title: Optional[str],
    status: Optional[str],
    resolution_date: Optional[datetime],
    sport_category: Optional[str],
    market_metadata: Optional[dict[str, Any]],
    now: datetime,
    description: Optional[str] = None,
    event_date: Optional[date] = None,
    concluded_events: Optional[Iterable[ConcludedEventRule]] = None,
) -> tuple[bool, Optional[str]]:
    """Check 3: confirm the market and the real-world event are still ahead."""
    now_utc = _utc(now) or datetime.now(timezone.utc)
    if (status or "").strip().lower() != "open":
        return False, f"not_open:{status or 'unknown'}"

    meta = market_metadata if isinstance(market_metadata, dict) else {}
    if meta.get(VENUE_SETTLED_KEY) is not None:
        return False, "venue_settled"
    if meta.get(BOOK_REFUSED_KEY) is not None:
        return False, "book_refused"

    res_utc = _utc(resolution_date)
    if res_utc is not None and res_utc < now_utc:
        return False, "past_resolution_date"

    if event_date is not None and now_utc.date() > event_date:
        return False, f"past_event_date:{event_date.isoformat()}"

    rules = (
        load_fun_markets_registry().concluded_events
        if concluded_events is None
        else tuple(concluded_events)
    )
    haystack = f"{title or ''} {description or ''}".lower()
    for rule in rules:
        if now_utc.date() > rule.event_date and all(
            term in haystack for term in rule.title_all_terms
        ):
            return False, f"concluded_event:{rule.id}"

    if title and is_title_implied_stale(title, sport_category, now_utc):
        return False, "title_implied_stale"

    if title:
        # Catch explicit past-year deadlines or editions (e.g., "2025 Oscars",
        # "before 2026") that sports-only title staleness rules do not cover.
        before_years = [
            int(y) for y in re.findall(r"\bbefore\s+(20\d{2})\b", title, re.IGNORECASE)
        ]
        if before_years and max(before_years) <= now_utc.year:
            return False, f"past_title_deadline:before_{max(before_years)}"
        all_years = [int(y) for y in re.findall(r"\b(20\d{2})\b", title)]
        if all_years and max(all_years) < now_utc.year:
            return False, f"past_title_year:{max(all_years)}"

    return True, None


def evaluate_fun_market_guards(
    *,
    title: Optional[str],
    status: Optional[str],
    volume: Optional[int | float],
    resolution_date: Optional[datetime],
    sport_category: Optional[str],
    market_metadata: Optional[dict[str, Any]],
    now: datetime,
    description: Optional[str] = None,
    entry: Optional[FunMarketEntry] = None,
    min_lifetime_volume: Optional[int] = None,
    concluded_events: Optional[Iterable[ConcludedEventRule]] = None,
) -> FunGuardResult:
    """Run all three fun-tag guards and return the per-guard verdict."""
    passed_trading, trading_reason = check_fun_real_trading(
        volume, min_lifetime_volume=min_lifetime_volume
    )
    effective_title = title or (entry.title if entry is not None else "")
    passed_taste, taste_reason = check_fun_taste_guard(
        effective_title, description=description
    )
    passed_ahead, ahead_reason = check_fun_still_ahead(
        title=effective_title,
        description=description,
        status=status,
        resolution_date=resolution_date,
        sport_category=entry.discover_category if entry is not None else sport_category,
        market_metadata=market_metadata,
        now=now,
        event_date=entry.event_date if entry is not None else None,
        concluded_events=concluded_events,
    )
    return FunGuardResult(
        passed=passed_trading and passed_taste and passed_ahead,
        passed_real_trading=passed_trading,
        passed_taste=passed_taste,
        passed_still_ahead=passed_ahead,
        real_trading_reason=trading_reason,
        taste_reason=taste_reason,
        still_ahead_reason=ahead_reason,
    )


async def discover_fun_admission_market_ids(
    db: AsyncSession,
    now: datetime,
    *,
    min_lifetime_volume: Optional[int] = None,
    force_enabled: bool = False,
) -> list[int]:
    """Return tagged fun market IDs eligible to enter Discover's candidate pool.

    Returns ``[]`` whenever ``DISCOVER_FUN_ADMISSION_ENABLED`` is off (unless
    ``force_enabled=True`` for dry-run comparisons). Deliberately omits the
    Discover ``% vs %`` title filter so curated fun comparisons such as
    ``Dune vs Avengers: higher Rotten Tomatoes score`` are admitted while
    still enforcing open status, unlinked event_id, live book, and all three
    fun-tag guards.
    """
    if not force_enabled and not is_discover_fun_admission_enabled():
        return []

    registry = load_fun_markets_registry()
    if not registry.ordered_market_ids:
        return []

    bar = (
        discover_fun_min_lifetime_volume()
        if min_lifetime_volume is None
        else int(min_lifetime_volume)
    )
    now_utc = _utc(now) or datetime.now(timezone.utc)

    query = (
        select(
            FuturesMarket.id,
            FuturesMarket.name,
            FuturesMarket.description,
            FuturesMarket.status,
            FuturesMarket.volume,
            FuturesMarket.resolution_date,
            FuturesMarket.llm_sport_category,
            FuturesMarket.market_metadata,
        )
        .where(
            FuturesMarket.id.in_(registry.ordered_market_ids),
            FuturesMarket.status == "open",
            FuturesMarket.event_id.is_(None),
            or_(
                FuturesMarket.resolution_date.is_(None),
                FuturesMarket.resolution_date >= now_utc,
            ),
            FuturesMarket.market_metadata[VENUE_SETTLED_KEY].astext.is_(None),
            FuturesMarket.market_metadata[BOOK_REFUSED_KEY].astext.is_(None),
            FuturesMarket.volume.isnot(None),
            FuturesMarket.volume >= bar,
        )
    )
    result = await db.execute(query)
    rows_by_id = {int(row.id): row for row in result.all()}

    admitted: list[int] = []
    for market_id in registry.ordered_market_ids:
        row = rows_by_id.get(market_id)
        if row is None:
            continue
        entry = registry.markets[market_id]
        verdict = evaluate_fun_market_guards(
            title=row.name,
            description=row.description,
            status=row.status,
            volume=row.volume,
            resolution_date=row.resolution_date,
            sport_category=row.llm_sport_category,
            market_metadata=row.market_metadata,
            now=now_utc,
            entry=entry,
            min_lifetime_volume=bar,
            concluded_events=registry.concluded_events,
        )
        if verdict.passed:
            admitted.append(market_id)
    return admitted
