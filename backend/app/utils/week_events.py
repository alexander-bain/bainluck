"""Reusable ``week_events`` producer kind and its stored definitions (``docs/discover/grouping-types-2026-11.md`` §1.10, #11936).

PILLAR: DISCOVER / FORMATTING / TRUTH · SHIP: "This week's tournaments"
(``week_events``), grouping 2–4 concurrent tournaments in the same sport taking
place during the current play week, each row showing the tournament name, its
published play dates (from ``start_date`` and ``end_date``, never ``commence_time``,
ruling 042), and its current field leader's probability.

Built to ``docs/design/grouping-primitives.md`` (#12221):
1. **Atoms**: tournament outright/winner fields with published ``start_date`` and ``end_date``.
2. **Relations**: ``("same_measure", "same_window")`` at permission level ``"member"`` (Decide 71-A).
3. **Sets**: pure selector ``select_week_events`` returning ``RoundupMembers`` or ``RoundupRefusal``
   with per-tournament refusal reasons so a trial run and live serving apply the exact same rules.
4. **Presentations**: 390 px Discover grouping card (``GOLF · THIS WEEK``) + container page via
   ``RoundupProducer``, plus ``export_roundup_card_words_390px`` for the grading page.
5. **Triggers / Folder Loading**: definitions in ``backend/data/containers/*.json`` with
   ``rule.producer == "week_events"`` are loaded automatically by kind (Decide 60-A), and
   ``find_week_events_candidates`` enumerates every card the kind could make from today's data
   with its refusal reasons.
"""

from __future__ import annotations

import importlib
import json
import logging
import math
import os
import re
import zlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from app.utils.container_presentation import MEMBER_MARKET, market_destination
from app.utils.feed_market_quality import is_placeholder_flat_field

logger = logging.getLogger(__name__)

__all__ = [
    "CONTAINERS_DATA_DIR",
    "DEFAULT_LEVEL",
    "DEFAULT_RELATIONS",
    "GOLF_THIS_WEEK_DEFINITION",
    "GOLF_THIS_WEEK_DEFINITION_PATH",
    "GOLF_THIS_WEEK_ID",
    "GOLF_THIS_WEEK_PRODUCER",
    "GOLF_THIS_WEEK_SLUG",
    "MEMBERSHIP_WEEK_EVENTS",
    "PLACEHOLDER_HALF_PROBABILITY_THRESHOLD",
    "PLACEHOLDER_MAX_HALF_CONTENDERS",
    "PLACEHOLDER_TOP_THREE_MAX_SUM",
    "PRODUCER_KIND_WEEK_EVENTS",
    "SUPPORTED_LIVE_WEEK_EVENTS_SPORTS",
    "TOURNAMENT_MIN_FIELD_MASS",
    "WEEK_EVENTS_CANDIDATE_SPECS",
    "build_week_events_producer",
    "export_roundup_card_words_390px",
    "find_week_events_candidates",
    "golf_this_week",
    "load_week_events_definition",
    "load_week_events_definitions_from_dir",
    "produce_week_events",
    "select_week_events",
    "week_events_enabled",
]


def _rc() -> Any:
    return importlib.import_module("app.utils.roundup_containers")


PRODUCER_KIND_WEEK_EVENTS = "week_events"
MEMBERSHIP_WEEK_EVENTS = "event-derived"
DEFAULT_RELATIONS: tuple[str, ...] = ("same_measure", "same_window")
DEFAULT_LEVEL = "member"
TOURNAMENT_MIN_FIELD_MASS = 0.50
PLACEHOLDER_HALF_PROBABILITY_THRESHOLD: float = 0.499
PLACEHOLDER_MAX_HALF_CONTENDERS: int = 2
PLACEHOLDER_TOP_THREE_MAX_SUM: float = 1.25
SUPPORTED_LIVE_WEEK_EVENTS_SPORTS: frozenset[str] = frozenset({"golf"})

CONTAINERS_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "containers"

GOLF_THIS_WEEK_SLUG = "golf-this-week"
GOLF_THIS_WEEK_ID = "roundup:golf-this-week"
GOLF_THIS_WEEK_DEFINITION_PATH = CONTAINERS_DATA_DIR / f"{GOLF_THIS_WEEK_SLUG}.json"

_ET_ZONE = ZoneInfo("America/New_York")

_FORBIDDEN_NARRATIVE_RE = re.compile(
    r"\b(?:kalshi|polymarket|sportsbooks?|bookmakers?|fanatics|draftkings|fanduel|betmgm|caesars|bain\s+luck\s+blend|blended|question|questions)\b",
    re.IGNORECASE,
)

_MONTH_SHORT_NAMES: dict[int, str] = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

_COUNT_WORDS: dict[int, str] = {
    2: "Two",
    3: "Three",
    4: "Four",
}

# Canonical §1.10 sport specifications evaluated by the finder.
WEEK_EVENTS_CANDIDATE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "slug": "golf-this-week",
        "sport": "golf",
        "kicker": "GOLF · THIS WEEK",
        "name": "This week's tournaments",
        "category": "golf",
        "tag": "GOLF",
        "section_title": "This week's tournaments",
        "footer": "Each row is the leader in its own tournament.",
    },
    {
        "slug": "tennis-this-week",
        "sport": "tennis",
        "kicker": "TENNIS · THIS WEEK",
        "name": "This week's tournaments",
        "category": "tennis",
        "tag": "TENNIS",
        "section_title": "This week's tournaments",
        "footer": "Each row is the leader in its own tournament.",
    },
    {
        "slug": "ufc-this-weekend",
        "sport": "ufc",
        "kicker": "UFC · THIS WEEKEND",
        "name": "This weekend's cards",
        "category": "mma",
        "tag": "UFC",
        "section_title": "This weekend's cards",
        "footer": "Each row is the main-event favorite on its card.",
    },
    {
        "slug": "motorsport-this-weekend",
        "sport": "motorsport",
        "kicker": "MOTORSPORT · THIS WEEKEND",
        "name": "This weekend's races",
        "category": "motorsport",
        "tag": "MOTORSPORT",
        "section_title": "This weekend's races",
        "footer": "Each row is the race favorite in its series.",
    },
    {
        "slug": "esports-this-week",
        "sport": "esports",
        "kicker": "ESPORTS · THIS WEEK",
        "name": "This week's tournaments",
        "category": "esports",
        "tag": "ESPORTS",
        "section_title": "This week's tournaments",
        "footer": "Each row is the leader in its own tournament.",
    },
)


@dataclass(frozen=True)
class _SelectedTournament:
    key: str
    name: str
    tour_label: str
    start_date: date
    end_date: date
    date_label: str
    leader_name: str
    leader_probability: float
    rendered_percent: int
    market_id: int
    outcome_id: int
    observed_at: Optional[str]
    source_count: int
    sources: tuple[str, ...]
    top_golfers: tuple[dict[str, Any], ...]
    raw_tournament: Mapping[str, Any]


def week_events_enabled() -> bool:
    """Feature flag check (one on/off switch per kind, #12221 §4)."""
    return os.getenv("WEEK_EVENTS_ENABLED", "true").lower() == "true"


def _validate_narrative_copy(*texts: str) -> None:
    """Enforce that narrative copy contains no venue name, blend claim, or 'question'."""
    for text in texts:
        if text and _FORBIDDEN_NARRATIVE_RE.search(text):
            raise ValueError(
                f"week_events narrative copy contains forbidden venue/blend/question wording: {text!r}"
            )


def _half_up_percent(prob: float) -> int:
    """Round ``prob * 100`` half-up to match ``Math.round(prob * 100)`` on the client."""
    return int(math.floor(prob * 100.0 + 0.5))


def _parse_iso_date(val: Any) -> Optional[date]:
    """Parse an explicit YYYY-MM-DD (or ISO datetime) published date."""
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    text = str(val or "").strip()
    if not text:
        return None
    try:
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            return date.fromisoformat(text[:10])
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _format_date_range(start: date, end: date) -> str:
    """Format a tournament's play dates in plain words (e.g. ``Nov 5–8`` or ``Oct 30–Nov 2``)."""
    m_start = _MONTH_SHORT_NAMES[start.month]
    m_end = _MONTH_SHORT_NAMES[end.month]
    if start == end:
        return f"{m_start} {start.day}"
    if start.month == end.month:
        return f"{m_start} {start.day}\u2013{end.day}"
    return f"{m_start} {start.day}\u2013{m_end} {end.day}"


def _play_week_bounds(now: datetime) -> tuple[date, date]:
    """Return ``(monday, sunday)`` in ET for the play week containing ``now``."""
    today_et = now.astimezone(_ET_ZONE).date()
    monday = today_et - timedelta(days=today_et.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _synthetic_id(key: str) -> int:
    val = zlib.crc32(key.encode("utf-8")) & 0x7FFFFFFF
    return val if val > 0 else 1


def _extract_tournament_entries(
    raw_items: Any,
    *,
    expected_sport: str,
) -> Optional[list[Mapping[str, Any]]]:
    """Normalize a fixture sequence/mapping into tournament mappings, or return None if unrelated."""
    if isinstance(raw_items, Mapping):
        if "tournaments" in raw_items and isinstance(raw_items["tournaments"], Sequence):
            seq = raw_items["tournaments"]
        else:
            seq = list(raw_items.values())
    elif isinstance(raw_items, (list, tuple)):
        seq = raw_items
    else:
        return None

    out: list[Mapping[str, Any]] = []
    for item in seq:
        if not isinstance(item, Mapping):
            continue
        # Support feed items wrapped as {"type": "tournament", "data": {...}}
        if item.get("type") == "tournament" and isinstance(item.get("data"), Mapping):
            entry = item["data"]
        else:
            entry = item

        # Distinguish tournament objects from unrelated FuturesMarket / Event fixtures
        has_tournament_shape = (
            "golfers" in entry
            or "tour" in entry
            or "tour_label" in entry
            or "start_date" in entry
            or "end_date" in entry
            or str(entry.get("kind") or "").lower() == "tournament"
        )
        if not has_tournament_shape:
            continue

        item_sport = str(
            entry.get("sport")
            or entry.get("category")
            or ("golf" if "golfers" in entry else "")
        ).strip().lower()
        if expected_sport and item_sport and item_sport != expected_sport.lower():
            continue
        out.append(entry)
    return out


def _evaluate_single_tournament(
    t: Mapping[str, Any],
    *,
    week_start: date,
    week_end: date,
) -> tuple[Optional[_SelectedTournament], Optional[tuple[str, str]]]:
    """Validate one tournament against §1.10 rules.

    Returns ``(selected_tournament, None)`` when coherent and in-window, or
    ``(None, (tournament_name, refusal_reason))`` when refused.
    """
    name = str(t.get("name") or t.get("title") or t.get("key") or "").strip()
    if not name:
        return None, ("<unnamed>", "missing_name")

    key = (
        str(t.get("key") or t.get("slug") or "")
        .strip()
        .lower()
        .replace("-", "_")
        or re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    )

    # Rule 1 (Ruling 042 & §1.10): published dates must come from start_date and end_date,
    # NEVER from commence_time or resolution_date.
    start_d = _parse_iso_date(t.get("start_date"))
    end_d = _parse_iso_date(t.get("end_date"))
    if start_d is None or end_d is None or end_d < start_d:
        return None, (name, "missing_published_dates")

    # Rule 2: tournament play window [start_d, end_d] must overlap [week_start, week_end].
    if end_d < week_start or start_d > week_end:
        return None, (name, "outside_play_week")

    # Rule 3: decided/settled tournaments do not render as open leader rows.
    champion = str(t.get("champion") or "").strip()
    status = str(t.get("status") or t.get("schedule_status") or "open").strip().lower()
    if champion or status in {"resolved", "settled", "final", "completed", "closed"}:
        return None, (name, "already_decided")

    # Rule 4: extract field outcomes/golfers and verify coherence.
    raw_golfers = t.get("golfers")
    if not isinstance(raw_golfers, Sequence) or isinstance(raw_golfers, (str, bytes)):
        raw_golfers = t.get("outcomes") or t.get("top_outcomes") or ()
    golfers: list[dict[str, Any]] = [
        dict(g) for g in raw_golfers if isinstance(g, Mapping)
    ]
    if not golfers:
        return None, (name, "empty_field")

    # Check full-field mass when _all_golfers is present (#8334).
    all_golfers = t.get("_all_golfers")
    if isinstance(all_golfers, Sequence) and not isinstance(all_golfers, (str, bytes)):
        field_mass = 0.0
        for g in all_golfers:
            if isinstance(g, Mapping):
                try:
                    p = float(g.get("probability") or 0.0)
                    if math.isfinite(p) and p > 0.0:
                        field_mass += p
                except (TypeError, ValueError):
                    continue
        if field_mass < TOURNAMENT_MIN_FIELD_MASS:
            return None, (name, "insufficient_field_mass")

    # Check placeholder flat field (e.g. TOTO Japan Classic when 3 players sit at 50.0%).
    priced_probs: list[float] = []
    for g in golfers:
        p_raw = (
            g.get("probability")
            if "probability" in g
            else g.get("current_probability")
        )
        if p_raw is None or isinstance(p_raw, bool):
            continue
        try:
            p_val = float(p_raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(p_val) and 0.0 < p_val < 1.0:
            priced_probs.append(p_val)

    if not priced_probs:
        return None, (name, "missing_leader_probability")

    if is_placeholder_flat_field([(p, None, None) for p in priced_probs], True):
        return None, (name, "placeholder_field")

    # Also refuse when 2+ contenders in a one-winner tournament field each sit at >= 0.50
    # or the top 3 outcomes alone exceed 1.25 (e.g. 3 x 50.0% = 150.0%).
    at_or_above_half = sum(
        1 for p in priced_probs if p >= PLACEHOLDER_HALF_PROBABILITY_THRESHOLD
    )
    top_three_sum = sum(sorted(priced_probs, reverse=True)[:3])
    if (
        at_or_above_half >= PLACEHOLDER_MAX_HALF_CONTENDERS
        or top_three_sum > PLACEHOLDER_TOP_THREE_MAX_SUM
    ):
        return None, (name, "placeholder_field")

    # Sort golfers by probability descending to identify the leader deterministically.
    valid_golfers: list[tuple[float, str, dict[str, Any]]] = []
    for g in golfers:
        g_name = str(g.get("name") or g.get("label") or "").strip()
        p_raw = (
            g.get("probability")
            if "probability" in g
            else g.get("current_probability")
        )
        if not g_name or p_raw is None or isinstance(p_raw, bool):
            continue
        try:
            p_val = float(p_raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(p_val) and 0.0 < p_val < 1.0:
            valid_golfers.append((p_val, g_name, g))

    if not valid_golfers:
        return None, (name, "missing_leader_probability")

    valid_golfers.sort(key=lambda item: (-item[0], item[1].casefold()))
    leader_prob, leader_name, leader_dict = valid_golfers[0]

    raw_market_ids = t.get("market_ids")
    market_id: int = 0
    if isinstance(raw_market_ids, Sequence) and not isinstance(raw_market_ids, (str, bytes)):
        for mid_candidate in raw_market_ids:
            if (
                isinstance(mid_candidate, int)
                and not isinstance(mid_candidate, bool)
                and mid_candidate > 0
            ):
                market_id = int(mid_candidate)
                break
    if market_id <= 0:
        raw_id = t.get("id")
        if isinstance(raw_id, int) and not isinstance(raw_id, bool) and raw_id > 0:
            market_id = int(raw_id)
        else:
            market_id = _synthetic_id(f"tournament:{key}")

    raw_oid = leader_dict.get("id")
    outcome_id = (
        int(raw_oid)
        if isinstance(raw_oid, int) and not isinstance(raw_oid, bool) and raw_oid > 0
        else market_id * 10 + 1
    )

    raw_sources = t.get("market_sources") or t.get("sources") or ()
    sources_tuple = tuple(
        sorted(
            {
                str(s).strip().lower()
                for s in raw_sources
                if isinstance(s, str) and str(s).strip()
            }
        )
    )
    source_count = int(t.get("source_count") or len(sources_tuple) or 1)
    tour_label = str(t.get("tour_label") or "Golf").strip()
    observed_at = (
        str(t.get("updated_at") or leader_dict.get("observed_at") or "").strip()
        or None
    )

    top_golfers_out: list[dict[str, Any]] = []
    for rank_idx, (g_prob, g_name, g_raw) in enumerate(valid_golfers[:5], start=1):
        g_oid_raw = g_raw.get("id")
        g_oid = (
            int(g_oid_raw)
            if isinstance(g_oid_raw, int)
            and not isinstance(g_oid_raw, bool)
            and g_oid_raw > 0
            else market_id * 10 + rank_idx
        )
        top_golfers_out.append(
            {
                "id": g_oid,
                "name": g_name,
                "probability": g_prob,
                "rendered_percent": _half_up_percent(g_prob),
                "american_odds": None,
                "rank": rank_idx,
                "movement": g_raw.get("movement_24h"),
                "is_winner": False,
                "resolution_source": None,
            }
        )

    return (
        _SelectedTournament(
            key=key,
            name=name,
            tour_label=tour_label,
            start_date=start_d,
            end_date=end_d,
            date_label=_format_date_range(start_d, end_d),
            leader_name=leader_name,
            leader_probability=leader_prob,
            rendered_percent=_half_up_percent(leader_prob),
            market_id=market_id,
            outcome_id=outcome_id,
            observed_at=observed_at,
            source_count=source_count,
            sources=sources_tuple,
            top_golfers=tuple(top_golfers_out),
            raw_tournament=t,
        ),
        None,
    )


def _build_tournament_member_card(sel: _SelectedTournament, sport: str) -> dict[str, Any]:
    """Build the container section member card for a selected tournament."""
    res_iso = f"{sel.end_date.isoformat()}T23:59:00Z"
    primary_source = sel.sources[0] if len(sel.sources) == 1 else None
    return {
        "id": sel.market_id,
        "name": f"{sel.name} Winner",
        "sport": sport,
        "sport_name": sel.tour_label,
        "category": sport,
        "llm_sport_category": sport,
        "market_tier": 1,
        "market_type_label": "Tournament Winner",
        "market_type": "outright",
        "status": "open",
        "source": primary_source,
        "sources": list(sel.sources),
        "source_count": sel.source_count,
        "mutually_exclusive": True,
        "resolution_date": res_iso,
        "start_date": sel.start_date.isoformat(),
        "end_date": sel.end_date.isoformat(),
        "top_outcomes": list(sel.top_golfers),
        "outcome_count": len(sel.top_golfers),
        "updated_at": sel.observed_at,
        "prices_updated_at": sel.observed_at,
        "price_observed_at": sel.observed_at,
    }


def select_week_events(
    tournaments: Sequence[Mapping[str, Any]],
    *,
    sport: str = "golf",
    kicker: str = "GOLF · THIS WEEK",
    title: Optional[str] = None,
    section_title: str = "This week's tournaments",
    footer: str = "Each row is the leader in its own tournament.",
    min_events: int = 2,
    max_rows: int = 4,
    now: Optional[datetime] = None,
) -> Any:
    """Pure selector for ``week_events`` (§1.10).

    Applies the exact same rules for a trial run and for live serving:
    * Requires published ``start_date`` and ``end_date`` overlapping the current play week.
    * Refuses any tournament whose field is flat/placeholder or lacks a valid leader price.
    * Deduplicates by canonical tournament key.
    * Refuses the card when fewer than ``min_events`` (2) valid tournaments remain.
    """
    rc = _rc()
    RoundupMembers = rc.RoundupMembers
    RoundupRefusal = rc.RoundupRefusal

    _validate_narrative_copy(kicker, title or "", section_title, footer)

    effective_now = (
        now.astimezone(timezone.utc)
        if isinstance(now, datetime) and now.tzinfo is not None
        else datetime.now(timezone.utc)
    )
    week_start, week_end = _play_week_bounds(effective_now)

    if not tournaments:
        return RoundupRefusal((("sport", "empty_pool"),))

    valid: list[_SelectedTournament] = []
    refusals: list[tuple[str, str]] = []
    seen_keys: set[str] = set()

    for raw_t in tournaments:
        if not isinstance(raw_t, Mapping):
            continue
        sel, err = _evaluate_single_tournament(
            raw_t,
            week_start=week_start,
            week_end=week_end,
        )
        if err is not None:
            refusals.append(err)
            continue
        assert sel is not None
        if sel.key in seen_keys:
            refusals.append((sel.name, "duplicate_event"))
            continue
        seen_keys.add(sel.key)
        valid.append(sel)

    if len(valid) < min_events:
        return RoundupRefusal(
            (
                ("sport", "too_few_tournaments"),
                ("valid_count", len(valid)),
                ("tournament_refusals", tuple(refusals)),
            )
        )

    # Deterministic ordering: start_date asc, end_date asc, leader_probability desc, name asc, key asc.
    valid.sort(
        key=lambda s: (
            s.start_date,
            s.end_date,
            -s.leader_probability,
            s.name.casefold(),
            s.key,
        )
    )

    shown = valid[:max_rows]
    rows_out: list[dict[str, Any]] = []
    for sel in shown:
        row_label = f"{sel.name} \u00b7 {sel.date_label} \u00b7 {sel.leader_name}"
        rows_out.append(
            {
                "market_id": sel.market_id,
                "outcome_id": sel.outcome_id,
                "label": row_label,
                "probability": sel.leader_probability,
                "rendered_percent": sel.rendered_percent,
                "observed_at": sel.observed_at,
            }
        )

    member_entries: list[dict[str, Any]] = []
    revision_ids: list[int] = []
    for sel in valid:
        card = _build_tournament_member_card(sel, sport)
        entry = {
            "type": MEMBER_MARKET,
            "id": sel.market_id,
            "destination": market_destination(sel.market_id),
            "card": card,
            "event_id": None,
        }
        member_entries.append(entry)
        revision_ids.append(sel.market_id)

    count_word = _COUNT_WORDS.get(len(shown))
    effective_title = (
        f"{count_word} tournaments"
        if count_word and (not title or title.lower() == "this week's tournaments")
        else (title or "This week's tournaments")
    )
    count_line = (
        f"Showing {len(shown)} of {len(valid)} tournaments"
        if len(shown) < len(valid)
        else None
    )

    sections_out = [
        {
            "class": f"week_{week_start.strftime('%Y_%m_%d')}",
            "title": section_title,
            "layout": "field",
            "count": len(member_entries),
            "members": member_entries,
        }
    ]

    return RoundupMembers(
        member_entries,
        rows_out,
        footer=footer,
        count_line=count_line,
        title=effective_title,
        kicker=kicker,
        sections=sections_out,
        revision_ids=revision_ids,
    )


async def _load_tournaments_from_db(
    db: Any,
    *,
    sport: str,
    now: datetime,
) -> tuple[list[Mapping[str, Any]], Optional[str]]:
    """Load current tournaments for ``sport`` from the shared base when ``db`` is an AsyncSession.

    Returns ``(tournaments, error_reason)`` where ``error_reason`` is ``None`` when the
    live loader succeeded, or a distinct refusal reason (``"unsupported_sport"``,
    ``"missing_db_session"``, or ``"source_unavailable"``) so database/loader failures
    and unsupported sports never masquerade as an empty pool.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    if sport.lower() not in SUPPORTED_LIVE_WEEK_EVENTS_SPORTS:
        return [], "unsupported_sport"
    if not isinstance(db, AsyncSession):
        return [], "missing_db_session"
    try:
        from app.utils.golf_base import get_golf_base

        tournaments, _prov = await get_golf_base(db, now)
        if isinstance(tournaments, Sequence):
            return [t for t in tournaments if isinstance(t, Mapping)], None
    except Exception:
        logger.warning(
            "week_events: failed to load tournaments from shared base for sport=%s",
            sport,
            exc_info=True,
        )
        return [], "source_unavailable"
    return [], None


async def produce_week_events(
    db: Any,
    definition: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Any:
    """Evaluate a stored ``week_events`` definition against ``db`` or an in-memory fixture."""
    rc = _rc()
    RoundupRefusal = rc.RoundupRefusal

    rule = definition.get("rule")
    if not isinstance(rule, Mapping):
        raise ValueError("week_events definition requires a 'rule' mapping")
    if rule.get("producer") != PRODUCER_KIND_WEEK_EVENTS:
        raise ValueError(
            f"Unsupported producer kind {rule.get('producer')!r}; expected {PRODUCER_KIND_WEEK_EVENTS!r}"
        )

    sport = str(rule.get("sport") or definition.get("category") or "golf").strip().lower()
    kicker = str(definition.get("kicker") or f"{sport.upper()} · THIS WEEK").strip()
    title = str(definition.get("name") or "This week's tournaments").strip()
    section_title = str(definition.get("section_title") or "This week's tournaments").strip()
    footer = str(
        definition.get("footer") or "Each row is the leader in its own tournament."
    ).strip()
    min_events = int(rule.get("min_events", 2))
    max_rows = int(rule.get("max_rows", 4))

    effective_now = (
        now.astimezone(timezone.utc)
        if isinstance(now, datetime) and now.tzinfo is not None
        else datetime.now(timezone.utc)
    )

    extracted = _extract_tournament_entries(db, expected_sport=sport)
    if extracted is not None:
        if not extracted:
            return RoundupRefusal((("sport", "empty_pool"),))
        tournament_list = extracted
    else:
        tournament_list, load_error = await _load_tournaments_from_db(
            db, sport=sport, now=effective_now
        )
        if load_error is not None:
            return RoundupRefusal((("sport", load_error),))

    return select_week_events(
        tournament_list,
        sport=sport,
        kicker=kicker,
        title=title,
        section_title=section_title,
        footer=footer,
        min_events=min_events,
        max_rows=max_rows,
        now=effective_now,
    )


def load_week_events_definition(
    path: Path = GOLF_THIS_WEEK_DEFINITION_PATH,
) -> dict[str, Any]:
    """Load and validate a stored ``week_events`` JSON definition."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Container definition at {path} must be a JSON object")
    if data.get("membership") != MEMBERSHIP_WEEK_EVENTS:
        raise ValueError(
            f"Container definition {path} must have membership={MEMBERSHIP_WEEK_EVENTS!r}"
        )
    if data.get("kind") != "roundup":
        raise ValueError(f"Container definition {path} must have kind='roundup'")
    rule = data.get("rule")
    if not isinstance(rule, Mapping) or rule.get("producer") != PRODUCER_KIND_WEEK_EVENTS:
        raise ValueError(
            f"Container definition {path} must declare rule.producer={PRODUCER_KIND_WEEK_EVENTS!r}"
        )
    # Ensure Decide 71-A relation permission fields are normalized on the loaded definition.
    relations_raw = data.get("relations") or rule.get("relations") or DEFAULT_RELATIONS
    data["relations"] = [str(r) for r in relations_raw]
    data["level"] = str(data.get("level") or rule.get("level") or DEFAULT_LEVEL)
    _validate_narrative_copy(
        str(data.get("name") or ""),
        str(data.get("footer") or ""),
        str(data.get("kicker") or ""),
        str(data.get("section_title") or ""),
    )
    return data


def load_week_events_definitions_from_dir(
    directory: Path = CONTAINERS_DATA_DIR,
) -> list[dict[str, Any]]:
    """Scan ``backend/data/containers/*.json`` and load every ``week_events`` definition (Decide 60-A)."""
    if not directory.exists():
        return []
    definitions: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, Mapping):
            continue
        rule = raw.get("rule")
        if isinstance(rule, Mapping) and rule.get("producer") == PRODUCER_KIND_WEEK_EVENTS:
            definitions.append(load_week_events_definition(path))
    return definitions


def build_week_events_producer(
    definition: Mapping[str, Any],
    *,
    enabled: Optional[Callable[[], bool]] = None,
) -> Any:
    """Instantiate a ``RoundupProducer`` from a stored ``week_events`` definition."""
    RoundupProducer = _rc().RoundupProducer
    slug = str(definition["slug"])
    name = str(definition["name"])
    kind = str(definition.get("kind") or "roundup")
    category = str(definition.get("category") or "golf")
    section_title = definition.get("section_title") or "This week's tournaments"
    footer = str(definition["footer"])
    membership = str(definition.get("membership") or MEMBERSHIP_WEEK_EVENTS)
    rule = definition.get("rule")
    tag = (
        str(definition["tag"])
        if "tag" in definition and definition["tag"] is not None
        else category.upper()
    )
    kicker = str(definition.get("kicker") or f"{category.upper()} · THIS WEEK")
    story_key = f"roundup:{slug.removeprefix('roundup-')}"

    async def _produce(db: Any) -> Any:
        return await produce_week_events(db, definition)

    return RoundupProducer(
        slug=slug,
        name=name,
        kind=kind,
        category=category,
        section_title=section_title,
        footer=footer,
        produce=_produce,
        membership=membership,
        relations=definition.get("relations"),
        level=definition.get("level"),
        rule=rule if isinstance(rule, Mapping) else None,
        tag=tag,
        kicker=kicker,
        story_key=story_key,
        enabled=enabled if enabled is not None else week_events_enabled,
    )


def export_roundup_card_words_390px(
    members: Any,
    definition: Mapping[str, Any],
) -> dict[str, Any]:
    """Export a would-be grouping card's 390 px words for the grading page (#12221 §4 item 6)."""
    slug = str(definition.get("slug") or "")
    kicker = str(getattr(members, "kicker", None) or definition.get("kicker") or "")
    tag = str(definition.get("tag") or str(definition.get("category") or "").upper())
    title = str(getattr(members, "title", None) or definition.get("name") or "")
    footer = str(getattr(members, "footer", None) or definition.get("footer") or "")
    count_line = getattr(members, "count_line", None)
    rows_raw = getattr(members, "rows", ()) or ()
    rows_words = [
        {
            "label": str(r.get("label") or ""),
            "value": f"{int(r.get('rendered_percent', 0))}%",
            "market_id": int(r.get("market_id") or 0),
        }
        for r in rows_raw
        if isinstance(r, Mapping)
    ]
    lines: list[str] = [f"{kicker} · {tag}" if tag else kicker, title]
    for rw in rows_words:
        lines.append(f"{rw['label']} — {rw['value']}")
    if count_line:
        lines.append(str(count_line))
    if footer:
        lines.append(footer)
    return {
        "viewport_width_px": 390,
        "slug": slug,
        "href": f"/collections/{slug}",
        "kicker": kicker,
        "tag": tag,
        "title": title,
        "rows": rows_words,
        "count_line": count_line,
        "footer": footer,
        "text_390px": "\n".join(lines),
    }


def find_week_events_candidates(
    pools_by_sport: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Finder listing every card ``week_events`` could make from today's markets with refusal reasons (#12221 §4 item 3)."""
    rc = _rc()
    RoundupMembers = rc.RoundupMembers
    RoundupRefusal = rc.RoundupRefusal

    results: list[dict[str, Any]] = []
    for spec in WEEK_EVENTS_CANDIDATE_SPECS:
        sport = spec["sport"]
        pool = pools_by_sport.get(sport, ())
        outcome = select_week_events(
            pool,
            sport=sport,
            kicker=spec["kicker"],
            title=spec["name"],
            section_title=spec["section_title"],
            footer=spec["footer"],
            now=now,
        )
        if isinstance(outcome, RoundupMembers):
            results.append(
                {
                    "slug": spec["slug"],
                    "sport": sport,
                    "relations": list(DEFAULT_RELATIONS),
                    "level": DEFAULT_LEVEL,
                    "verdict": "serve",
                    "refusal_reasons": [],
                    "tournament_refusals": [],
                    "served_row_count": len(outcome.rows),
                    "card_words_390px": export_roundup_card_words_390px(outcome, spec),
                }
            )
        else:
            reasons_list = (
                list(outcome.reasons) if isinstance(outcome, RoundupRefusal) else []
            )
            reason_dict = dict(
                r for r in reasons_list if isinstance(r, tuple) and len(r) == 2
            )
            t_refusals = [
                {"tournament": t_name, "reason": t_reason}
                for t_name, t_reason in (reason_dict.get("tournament_refusals") or ())
            ]
            top_reason = str(reason_dict.get("sport") or "refused")
            results.append(
                {
                    "slug": spec["slug"],
                    "sport": sport,
                    "relations": list(DEFAULT_RELATIONS),
                    "level": DEFAULT_LEVEL,
                    "verdict": "refuse",
                    "refusal_reasons": [top_reason],
                    "tournament_refusals": t_refusals,
                    "served_row_count": 0,
                    "card_words_390px": None,
                }
            )
    return results


GOLF_THIS_WEEK_DEFINITION: dict[str, Any] = load_week_events_definition(
    GOLF_THIS_WEEK_DEFINITION_PATH
)

GOLF_THIS_WEEK_PRODUCER = build_week_events_producer(GOLF_THIS_WEEK_DEFINITION)


async def golf_this_week(db: Any, *, now: Optional[datetime] = None) -> Any:
    """Produce ``RoundupMembers`` (or ``RoundupRefusal``) for ``golf-this-week``."""
    return await produce_week_events(db, GOLF_THIS_WEEK_DEFINITION, now=now)


for _we_def in load_week_events_definitions_from_dir():
    if _we_def["slug"] == GOLF_THIS_WEEK_SLUG:
        _rc().register_roundup_producer(GOLF_THIS_WEEK_PRODUCER)
    else:
        _rc().register_roundup_producer(build_week_events_producer(_we_def))
