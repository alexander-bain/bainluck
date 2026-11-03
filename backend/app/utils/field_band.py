"""Reusable ``field_band`` producer kind and the ``roundup-cfp-picture`` definition (#4 in ``docs/containers/catalog-2026-11.md``).

PILLAR: DISCOVER / TRUTH · SHIP: a reusable ``field_band`` producer kind driven
by a stored container definition (``membership: "computed-produced"``,
``kind: "roundup"``), with ``roundup-cfp-picture`` ("College Football Playoff
picture") as its first definition over the Kalshi qualifiers spine
(``kalshi:227``, 54 teams, 12 winners — never normalized to 100) and the
national-title field (``kalshi:181``). One venue (no blend across differing
deadlines), named only as attribution, never in narrative copy; refuses rather
than serving a thin or unpriced field.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence

from app.utils.container_presentation import MEMBER_MARKET, market_destination
from app.utils.futures_liveness import leg_is_graded
from app.utils.tonights_games import _parse_dt


def _rc() -> Any:
    return importlib.import_module("app.utils.roundup_containers")

__all__ = [
    "CFP_PICTURE_DEFINITION",
    "CFP_PICTURE_DEFINITION_PATH",
    "CFP_PICTURE_ID",
    "CFP_PICTURE_PRODUCER",
    "CFP_PICTURE_SLUG",
    "PRODUCER_KIND_FIELD_BAND",
    "build_field_band_producer",
    "cfp_picture",
    "cfp_picture_enabled",
    "load_field_band_definition",
    "parse_market_ref",
    "produce_field_band",
    "select_field_band",
]

PRODUCER_KIND_FIELD_BAND = "field_band"

CFP_PICTURE_SLUG = "roundup-cfp-picture"
CFP_PICTURE_ID = "roundup:cfp-picture"
CFP_PICTURE_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{CFP_PICTURE_SLUG}.json"
)

_FORBIDDEN_NARRATIVE_RE = re.compile(
    r"\b(?:kalshi|polymarket|draftkings|fanduel|betmgm|caesars|question|questions)\b",
    re.IGNORECASE,
)
_PLACEHOLDER_OUTCOME_NAMES = frozenset(
    {"other", "field", "the field", "none", "no winner", "any other", "tbd"}
)


def cfp_picture_enabled() -> bool:
    """One setting turns the CFP picture card and container on or off together."""
    return os.getenv("CFP_PICTURE_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def parse_market_ref(spec: Any) -> tuple[str, Optional[int], Optional[str]]:
    """Parse a definition's market reference such as ``"kalshi:227"`` into ``(source, market_id, token)``."""
    raw = str(spec or "").strip()
    if ":" not in raw:
        raise ValueError(f"Market reference must be '<source>:<id>': {spec!r}")
    left, right = [part.strip() for part in raw.split(":", 1)]
    source = left.lower()
    if not source or not right:
        raise ValueError(f"Market reference must be '<source>:<id>': {spec!r}")
    try:
        mid = int(right)
        if mid <= 0:
            raise ValueError(f"Market id must be positive: {spec!r}")
        return source, mid, None
    except ValueError as exc:
        if right.isdigit() or right.startswith("-"):
            raise ValueError(f"Market id must be positive: {spec!r}") from exc
        return source, None, right


def _validate_narrative_copy(*strings: Any) -> None:
    """Ensure reader-facing narrative copy never names a venue or says 'question'."""
    for s in strings:
        if isinstance(s, (list, tuple)):
            _validate_narrative_copy(*s)
            continue
        text = str(s or "").strip()
        if not text:
            continue
        match = _FORBIDDEN_NARRATIVE_RE.search(text)
        if match is not None:
            raise ValueError(
                f"Forbidden token {match.group(0)!r} in narrative copy: {text!r}"
            )


@dataclass(frozen=True)
class _PricedOutcome:
    outcome_id: int
    name: str
    probability: float
    movement: Optional[float]
    observed_at: Optional[str]


def _iso_utc(value: Any) -> Optional[str]:
    dt = _parse_dt(value)
    if dt is not None:
        return dt.astimezone(timezone.utc).isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _is_placeholder_name(name: str) -> bool:
    cleaned = name.strip().lower()
    if not cleaned or cleaned in _PLACEHOLDER_OUTCOME_NAMES:
        return True
    if cleaned.startswith("placeholder") or cleaned.startswith("person "):
        return True
    return False


def _extract_market_outcomes(
    market: Mapping[str, Any],
    *,
    expected_source: str,
    withheld_ids: Optional[set[int]] = None,
) -> tuple[Optional[list[_PricedOutcome]], Optional[str]]:
    """Validate a market mapping and return its priced, non-placeholder, ungraded outcomes."""
    status = str(market.get("status") or "").strip().lower()
    if status != "open":
        return None, f"status_{status or 'missing'}"

    source = str(market.get("source") or "").strip().lower()
    if source != expected_source.lower():
        return None, f"source_{source or 'missing'}_expected_{expected_source.lower()}"

    raw_outcomes = market.get("outcomes")
    if not isinstance(raw_outcomes, Sequence) or isinstance(raw_outcomes, (str, bytes)):
        raw_outcomes = market.get("top_outcomes")
    if not isinstance(raw_outcomes, Sequence) or isinstance(raw_outcomes, (str, bytes)):
        return None, "outcomes_missing"

    blocked = withheld_ids or set()
    market_observed = _iso_utc(
        market.get("prices_updated_at") or market.get("updated_at")
    )
    priced: list[_PricedOutcome] = []
    seen_outcome_ids: set[int] = set()
    seen_names: set[str] = set()

    for idx, raw in enumerate(raw_outcomes):
        if not isinstance(raw, Mapping):
            continue
        oid_raw = raw.get("id")
        oid = (
            int(oid_raw)
            if isinstance(oid_raw, int) and not isinstance(oid_raw, bool) and oid_raw > 0
            else idx + 1
        )
        if oid in blocked:
            return None, f"withheld_price_{oid}"
        if oid in seen_outcome_ids:
            continue
        if leg_is_graded(raw.get("is_winner"), raw.get("resolution_source")):
            continue

        name = str(raw.get("name") or raw.get("label") or "").strip()
        if _is_placeholder_name(name):
            continue
        norm_name = name.lower()
        if norm_name in seen_names:
            continue

        prob_raw = (
            raw.get("probability")
            if "probability" in raw
            else raw.get("current_probability")
        )
        if prob_raw is None or isinstance(prob_raw, bool):
            continue
        try:
            prob = float(prob_raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(prob) or prob < 0.0 or prob > 1.0:
            continue

        mv_raw = (
            raw.get("movement")
            if "movement" in raw
            else raw.get("probability_change_24h")
        )
        movement: Optional[float] = None
        if mv_raw is not None and not isinstance(mv_raw, bool):
            try:
                mv_val = float(mv_raw)
                if math.isfinite(mv_val) and mv_val != 0.0:
                    movement = mv_val
            except (TypeError, ValueError):
                movement = None

        obs = _iso_utc(raw.get("observed_at") or raw.get("last_updated")) or market_observed
        seen_outcome_ids.add(oid)
        seen_names.add(norm_name)
        priced.append(
            _PricedOutcome(
                outcome_id=oid,
                name=name,
                probability=prob,
                movement=movement,
                observed_at=obs,
            )
        )

    return priced, None


def _newest_stamp(outcomes: Sequence[_PricedOutcome], fallback: Any = None) -> Optional[str]:
    parsed: list[tuple[datetime, str]] = []
    for o in outcomes:
        if o.observed_at:
            dt = _parse_dt(o.observed_at)
            if dt is not None:
                parsed.append((dt.astimezone(timezone.utc), o.observed_at))
    if parsed:
        parsed.sort(key=lambda pair: pair[0])
        return parsed[-1][1]
    return _iso_utc(fallback)


def _build_section_market_card(
    base_market: Mapping[str, Any],
    *,
    market_id: int,
    source: str,
    category: str,
    shown_outcomes: Sequence[_PricedOutcome],
    board_outcomes: Sequence[_PricedOutcome],
    remaining_count: int,
    mutually_exclusive: bool,
) -> dict[str, Any]:
    """Build the container member card for one section of a ``field_band`` container.

    Attribution is single-venue (``source``, ``sources: [source]``, ``source_count: 1``),
    never a blend across differing deadlines. When ``mutually_exclusive`` is False
    (such as the 12-winner CFP qualifiers spine), probabilities are preserved verbatim
    without ever normalizing to 100, and ``discover_card.field_is_a_race`` is ``False``.
    """
    prices_updated_at = _newest_stamp(
        shown_outcomes,
        base_market.get("prices_updated_at") or base_market.get("updated_at"),
    )
    resolution_date = _iso_utc(base_market.get("resolution_date"))
    top_outcomes = [
        {
            "id": o.outcome_id,
            "name": o.name,
            "probability": o.probability,
            "american_odds": None,
            "rank": idx + 1,
            "movement": o.movement,
            "is_winner": False,
            "resolution_source": None,
        }
        for idx, o in enumerate(shown_outcomes)
    ]
    distribution_outcomes = [
        {
            "label": o.name,
            "probability": o.probability,
            "movement": o.movement,
        }
        for o in board_outcomes
    ]
    return {
        "id": int(market_id),
        "name": str(base_market.get("name") or "").strip(),
        "sport": base_market.get("sport") or "americanfootball_ncaaf",
        "sport_name": base_market.get("sport_name") or "NCAAF",
        "category": base_market.get("category") or "sports",
        "llm_sport_category": base_market.get("llm_sport_category") or category or "football",
        "market_tier": int(base_market.get("market_tier") or 1),
        "market_type_label": base_market.get("market_type_label") or "Championship",
        "market_type": str(base_market.get("market_type") or "field"),
        "status": "open",
        "source": source,
        "sources": [source],
        "source_count": 1,
        "mutually_exclusive": bool(mutually_exclusive),
        "resolution_date": resolution_date,
        "top_outcomes": top_outcomes,
        "outcome_count": len(shown_outcomes) + int(remaining_count),
        "updated_at": _iso_utc(base_market.get("updated_at")) or prices_updated_at,
        "prices_updated_at": prices_updated_at,
        "discover_card": {
            "suggested_format": "outcome_distribution",
            "distribution_outcomes": distribution_outcomes,
            "remaining_outcome_count": int(remaining_count),
            "field_is_a_race": bool(mutually_exclusive),
        },
    }


def select_field_band(
    markets: Mapping[int, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    field_spec: str,
    band: Sequence[float],
    section_titles: Sequence[str] | str,
    category: str = "ncaaf",
    footer: str = "",
    card_rows: int = 4,
    min_field_outcomes: int = 24,
    min_band_outcomes: int = 4,
    second_section_spec: Optional[str] = None,
    min_second_section_outcomes: int = 12,
    normalize: bool = False,
    field_external_id: Optional[str] = None,
    second_section_external_id: Optional[str] = None,
    withheld_by_market: Optional[Mapping[int, set[int]]] = None,
) -> Any:
    """Pure selector for ``field_band``.

    * Validates the spine field market (must be open, match ``field_spec``'s venue,
      carry at least ``min_field_outcomes`` priced outcomes, and have
      ``mutually_exclusive == False`` when ``normalize`` is ``False``).
    * Never normalizes spine outcomes to 100 when ``normalize`` is ``False``
      (e.g. 12 winners of 54 in CFP qualifiers).
    * Selects all spine outcomes with ``band[0] <= probability <= band[1]`` for
      section 1 (``"On the bubble"``) and takes the top ``card_rows`` (highest
      probability first) for the Discover round-up card. Refuses if fewer than
      ``max(min_band_outcomes, card_rows)`` outcomes sit inside the band.
    * When ``second_section_spec`` is configured, validates the second market
      (must be open, match the venue, and carry at least
      ``min_second_section_outcomes`` priced outcomes) and builds section 2
      (``"Title contenders"``). Refuses all-or-nothing if the second section
      fails validation.
    """
    rc = _rc()
    RoundupMembers = rc.RoundupMembers
    RoundupRefusal = rc.RoundupRefusal

    if len(band) != 2:
        raise ValueError(f"band must be a [low, high] pair: {band!r}")
    band_low = float(band[0])
    band_high = float(band[1])
    if not (0.0 <= band_low < band_high <= 1.0):
        raise ValueError(f"band must satisfy 0 <= low < high <= 1: {band!r}")

    titles = (
        [str(section_titles).strip()]
        if isinstance(section_titles, str)
        else [str(t).strip() for t in section_titles if str(t).strip()]
    )
    if not titles:
        raise ValueError("section_titles must provide at least one title")
    _validate_narrative_copy(titles, footer)

    by_id: dict[int, Mapping[str, Any]] = {}
    by_ext: dict[tuple[str, str], Mapping[str, Any]] = {}
    seq = markets.values() if isinstance(markets, Mapping) else markets
    for m in seq:
        if not isinstance(m, Mapping):
            continue
        mid = m.get("id")
        if isinstance(mid, int) and not isinstance(mid, bool) and mid > 0:
            by_id[int(mid)] = m
        src = str(m.get("source") or "").strip().lower()
        ext = str(m.get("external_id") or "").strip().upper()
        if src and ext:
            by_ext[(src, ext)] = m

    spine_source, spine_id, spine_token = parse_market_ref(field_spec)
    spine_market: Optional[Mapping[str, Any]] = None
    if spine_id is not None:
        spine_market = by_id.get(spine_id)
    if spine_market is None and field_external_id:
        spine_market = by_ext.get((spine_source, field_external_id.strip().upper()))
    if spine_market is None and spine_token:
        spine_market = by_ext.get((spine_source, spine_token.strip().upper()))

    if spine_market is None:
        return RoundupRefusal((("field", "spine_missing"),))

    resolved_spine_id = int(spine_market["id"])
    if not normalize and spine_market.get("mutually_exclusive") is True:
        return RoundupRefusal((("field", "spine_mutually_exclusive"),))

    withheld_map = withheld_by_market or {}
    spine_priced, err = _extract_market_outcomes(
        spine_market,
        expected_source=spine_source,
        withheld_ids=withheld_map.get(resolved_spine_id),
    )
    if spine_priced is None:
        return RoundupRefusal((("field", f"spine_{err}"),))

    required_field = max(1, int(min_field_outcomes))
    if len(spine_priced) < required_field:
        return RoundupRefusal(
            (("field", f"thin_field_{len(spine_priced)}_below_{required_field}"),)
        )

    band_outcomes = sorted(
        [
            o
            for o in spine_priced
            if band_low - 1e-9 <= o.probability <= band_high + 1e-9
        ],
        key=lambda o: (-o.probability, o.name, o.outcome_id),
    )
    required_band = max(1, int(min_band_outcomes), int(card_rows))
    if len(band_outcomes) < required_band:
        return RoundupRefusal(
            (("band", f"thin_band_{len(band_outcomes)}_below_{required_band}"),)
        )

    top_band_rows = band_outcomes[: int(card_rows)]
    rows = [
        {
            "market_id": resolved_spine_id,
            "outcome_id": o.outcome_id,
            "label": o.name,
            "probability": o.probability,
            "observed_at": o.observed_at,
        }
        for o in top_band_rows
    ]

    bubble_card = _build_section_market_card(
        spine_market,
        market_id=resolved_spine_id,
        source=spine_source,
        category=category,
        shown_outcomes=band_outcomes,
        board_outcomes=band_outcomes[:4],
        remaining_count=max(0, len(band_outcomes) - 4),
        mutually_exclusive=bool(normalize),
    )
    bubble_member = {
        "type": MEMBER_MARKET,
        "id": resolved_spine_id,
        "destination": market_destination(resolved_spine_id),
        "card": bubble_card,
        "event_id": None,
    }

    members: list[dict[str, Any]] = [bubble_member]
    sections: list[dict[str, Any]] = [
        {
            "class": "advancement",
            "title": titles[0],
            "layout": "field",
            "count": 1,
            "members": [bubble_member],
        }
    ]
    revision_ids: list[int] = [o.outcome_id for o in band_outcomes]

    if second_section_spec:
        sec_source, sec_id, sec_token = parse_market_ref(second_section_spec)
        sec_market: Optional[Mapping[str, Any]] = None
        if sec_id is not None:
            sec_market = by_id.get(sec_id)
        if sec_market is None and second_section_external_id:
            sec_market = by_ext.get(
                (sec_source, second_section_external_id.strip().upper())
            )
        if sec_market is None and sec_token:
            sec_market = by_ext.get((sec_source, sec_token.strip().upper()))

        if sec_market is None:
            return RoundupRefusal((("second_section", "missing"),))

        resolved_sec_id = int(sec_market["id"])
        if resolved_sec_id == resolved_spine_id:
            return RoundupRefusal((("second_section", "duplicate_spine_market"),))

        sec_priced, sec_err = _extract_market_outcomes(
            sec_market,
            expected_source=sec_source,
            withheld_ids=withheld_map.get(resolved_sec_id),
        )
        if sec_priced is None:
            return RoundupRefusal((("second_section", f"invalid_{sec_err}"),))

        required_sec = max(1, int(min_second_section_outcomes))
        if len(sec_priced) < required_sec:
            return RoundupRefusal(
                (
                    (
                        "second_section",
                        f"thin_field_{len(sec_priced)}_below_{required_sec}",
                    ),
                )
            )

        sec_sorted = sorted(
            sec_priced,
            key=lambda o: (-o.probability, o.name, o.outcome_id),
        )
        sec_mutually_exclusive = bool(
            sec_market.get("mutually_exclusive", True)
        )
        sec_card = _build_section_market_card(
            sec_market,
            market_id=resolved_sec_id,
            source=sec_source,
            category=category,
            shown_outcomes=sec_sorted[:5],
            board_outcomes=sec_sorted[:4],
            remaining_count=max(0, len(sec_sorted) - 4),
            mutually_exclusive=sec_mutually_exclusive,
        )
        sec_member = {
            "type": MEMBER_MARKET,
            "id": resolved_sec_id,
            "destination": market_destination(resolved_sec_id),
            "card": sec_card,
            "event_id": None,
        }
        members.append(sec_member)
        sec_title = titles[1] if len(titles) > 1 else "Title contenders"
        sections.append(
            {
                "class": "title",
                "title": sec_title,
                "layout": "field",
                "count": 1,
                "members": [sec_member],
            }
        )
        revision_ids.extend(o.outcome_id for o in sec_sorted[:4])

    return RoundupMembers(
        members=members,
        rows=rows,
        footer=footer,
        sections=sections,
        revision_ids=revision_ids,
    )


async def _load_markets_from_db(
    db: Any,
    market_ids: Sequence[int],
    external_ids: Sequence[str],
) -> tuple[dict[int, dict[str, Any]], dict[int, set[int]]]:
    """Query ORM ``FuturesMarket`` rows (with outcomes and withheld-price sets) and convert to mappings."""
    if isinstance(db, (list, tuple)):
        mapped_seq: dict[int, dict[str, Any]] = {}
        for item in db:
            if isinstance(item, Mapping):
                raw_id = item.get("id") if "id" in item else item.get("market_id")
                if isinstance(raw_id, int) and not isinstance(raw_id, bool) and raw_id > 0:
                    entry = dict(item)
                    entry.setdefault("id", int(raw_id))
                    mapped_seq[int(raw_id)] = entry
        return mapped_seq, {}

    if not hasattr(db, "execute") or not callable(db.execute):
        return {}, {}

    from sqlalchemy import or_, select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import selectinload

    from app.models import FuturesMarket
    from app.routes.futures import withheld_price_outcome_ids_for_markets
    from app.utils.kalshi_display_names import repair_outcome_name_by_ticker

    clauses = []
    clean_ids = [int(mid) for mid in market_ids if isinstance(mid, int) and mid > 0]
    clean_exts = [str(ext).strip() for ext in external_ids if str(ext or "").strip()]
    if clean_ids:
        clauses.append(FuturesMarket.id.in_(clean_ids))
    if clean_exts:
        clauses.append(FuturesMarket.external_id.in_(clean_exts))
    if not clauses:
        return {}, {}

    res = await db.execute(
        select(FuturesMarket)
        .options(
            selectinload(FuturesMarket.sport),
            selectinload(FuturesMarket.outcomes),
        )
        .where(or_(*clauses))
        .order_by(FuturesMarket.id)
    )
    rows = res.scalars().all() if hasattr(res, "scalars") else []
    if not rows:
        return {}, {}

    withheld: dict[int, set[int]] = {}
    if isinstance(db, AsyncSession):
        withheld = await withheld_price_outcome_ids_for_markets(db, rows)
    mapped: dict[int, dict[str, Any]] = {}
    for m in rows:
        if isinstance(m, Mapping):
            raw_id = m.get("id") if "id" in m else m.get("market_id")
            if isinstance(raw_id, int) and not isinstance(raw_id, bool) and raw_id > 0:
                entry = dict(m)
                entry.setdefault("id", int(raw_id))
                mapped[int(raw_id)] = entry
            continue
        mid_val = getattr(m, "id", None)
        if not isinstance(mid_val, int) or isinstance(mid_val, bool) or mid_val <= 0:
            continue
        outcomes_list = []
        for o in getattr(m, "outcomes", None) or ():
            repaired_name = (
                repair_outcome_name_by_ticker(
                    getattr(o, "external_id", None),
                    getattr(o, "name", None),
                )
                or o.name
            )
            outcomes_list.append(
                {
                    "id": int(o.id),
                    "external_id": o.external_id,
                    "name": repaired_name,
                    "probability": o.current_probability,
                    "movement": o.probability_change_24h,
                    "last_updated": o.last_updated.isoformat() if o.last_updated else None,
                    "is_winner": getattr(o, "is_winner", None),
                    "resolution_source": getattr(o, "resolution_source", None),
                }
            )
        sport_obj = getattr(m, "sport", None)
        mapped[int(mid_val)] = {
            "id": int(mid_val),
            "name": str(m.name or "").strip(),
            "source": m.source,
            "external_id": m.external_id,
            "status": m.status,
            "mutually_exclusive": getattr(m, "mutually_exclusive", True),
            "market_tier": getattr(m, "market_tier", 1),
            "market_type": getattr(m, "market_type", "field"),
            "sport": getattr(sport_obj, "key", None) or "americanfootball_ncaaf",
            "sport_name": getattr(sport_obj, "name", None) or "NCAAF",
            "category": getattr(m, "category", None) or "sports",
            "llm_sport_category": getattr(m, "llm_sport_category", None) or "football",
            "resolution_date": getattr(m, "resolution_date", None),
            "updated_at": getattr(m, "updated_at", None),
            "prices_updated_at": getattr(m, "prices_updated_at", None),
            "outcomes": outcomes_list,
        }
    return mapped, withheld


async def produce_field_band(
    db: Any,
    *,
    definition: Mapping[str, Any],
    load_markets: Optional[
        Callable[
            [Any, Sequence[int], Sequence[str]],
            Awaitable[tuple[Mapping[int, Mapping[str, Any]], Mapping[int, set[int]]]]
            | tuple[Mapping[int, Mapping[str, Any]], Mapping[int, set[int]]],
        ]
    ] = None,
) -> Any:
    """Evaluate a stored ``field_band`` container definition against ``db``."""
    import inspect

    rule = definition.get("rule")
    if not isinstance(rule, Mapping):
        raise ValueError(f"Definition {definition.get('slug')!r} is missing 'rule'")

    field_spec = str(rule.get("field") or "").strip()
    band = rule.get("band") or (0.20, 0.80)
    section_titles = definition.get("section_title") or ("On the bubble",)
    category = str(definition.get("category") or "ncaaf")
    footer = str(definition.get("footer") or "")
    card_rows = int(rule.get("card_rows", 4) or 4)
    min_field_outcomes = int(rule.get("min_field_outcomes", 24) or 24)
    min_band_outcomes = int(rule.get("min_band_outcomes", 4) or 4)
    second_section_spec = (
        str(rule["second_section"]).strip()
        if rule.get("second_section")
        else None
    )
    min_second_section_outcomes = int(
        rule.get("min_second_section_outcomes", 12) or 12
    )
    normalize = bool(rule.get("normalize", False))
    field_external_id = (
        str(rule["field_external_id"]).strip()
        if rule.get("field_external_id")
        else None
    )
    second_section_external_id = (
        str(rule["second_section_external_id"]).strip()
        if rule.get("second_section_external_id")
        else None
    )

    market_ids: list[int] = []
    external_ids: list[str] = []
    _, spine_id, spine_token = parse_market_ref(field_spec)
    if spine_id is not None:
        market_ids.append(spine_id)
    if field_external_id:
        external_ids.append(field_external_id)
    elif spine_token:
        external_ids.append(spine_token)

    if second_section_spec:
        _, sec_id, sec_token = parse_market_ref(second_section_spec)
        if sec_id is not None:
            market_ids.append(sec_id)
        if second_section_external_id:
            external_ids.append(second_section_external_id)
        elif sec_token:
            external_ids.append(sec_token)

    loader = load_markets if load_markets is not None else _load_markets_from_db
    loaded = loader(db, market_ids, external_ids)
    if inspect.isawaitable(loaded):
        loaded = await loaded
    markets_map, withheld_map = loaded

    return select_field_band(
        markets_map,
        field_spec=field_spec,
        band=band,
        section_titles=section_titles,
        category=category,
        footer=footer,
        card_rows=card_rows,
        min_field_outcomes=min_field_outcomes,
        min_band_outcomes=min_band_outcomes,
        second_section_spec=second_section_spec,
        min_second_section_outcomes=min_second_section_outcomes,
        normalize=normalize,
        field_external_id=field_external_id,
        second_section_external_id=second_section_external_id,
        withheld_by_market=withheld_map,
    )


def load_field_band_definition(path: Path | str) -> dict[str, Any]:
    """Load and validate a stored JSON container definition for ``field_band``."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Container definition at {path} must be a JSON object")
    for required_key in ("slug", "name", "category", "section_title", "footer", "rule"):
        if not raw.get(required_key):
            raise ValueError(
                f"Container definition at {path} missing {required_key!r}"
            )
    _validate_narrative_copy(
        raw.get("name"),
        raw.get("footer"),
        raw.get("section_title"),
    )
    return raw


def build_field_band_producer(
    definition: Mapping[str, Any],
    *,
    enabled: Optional[Callable[[], bool]] = None,
    load_markets: Optional[
        Callable[
            [Any, Sequence[int], Sequence[str]],
            Awaitable[tuple[Mapping[int, Mapping[str, Any]], Mapping[int, set[int]]]]
            | tuple[Mapping[int, Mapping[str, Any]], Mapping[int, set[int]]],
        ]
    ] = None,
) -> Any:
    """Build a ``RoundupProducer`` from a stored ``field_band`` definition."""
    RoundupProducer = _rc().RoundupProducer

    rule = definition.get("rule")
    if not isinstance(rule, Mapping) or rule.get("producer") != PRODUCER_KIND_FIELD_BAND:
        raise ValueError(
            f"Expected rule.producer == {PRODUCER_KIND_FIELD_BAND!r}, got {rule!r}"
        )
    slug = str(definition["slug"])
    name = str(definition["name"])
    footer = str(definition["footer"])
    raw_titles = definition["section_title"]
    _validate_narrative_copy(name, footer, raw_titles)

    async def _produce(db: Any) -> Any:
        return await produce_field_band(
            db,
            definition=definition,
            load_markets=load_markets,
        )

    return RoundupProducer(
        slug=slug,
        name=name,
        kind=str(definition.get("kind") or "roundup"),
        category=str(definition["category"]),
        section_title=raw_titles,
        footer=footer,
        produce=_produce,
        membership=str(definition.get("membership") or "computed-produced"),
        rule=dict(rule),
        tag=str(
            definition.get("tag") or str(definition["category"]).upper()
        ),
        story_key=f"roundup:{slug.removeprefix('roundup-')}",
        enabled=enabled,
    )


CFP_PICTURE_DEFINITION: dict[str, Any] = load_field_band_definition(
    CFP_PICTURE_DEFINITION_PATH
)

CFP_PICTURE_PRODUCER: Any = build_field_band_producer(
    CFP_PICTURE_DEFINITION,
    enabled=cfp_picture_enabled,
)
_rc().register_roundup_producer(CFP_PICTURE_PRODUCER)


async def cfp_picture(
    db: Any,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Evaluate ``CFP_PICTURE_PRODUCER`` once and return ``(feed_item, container_payload)``."""
    return await _rc().evaluate_roundup_producer(CFP_PICTURE_PRODUCER, db)
