"""Reusable ``field_leaders`` producer kind and its stored definitions (#11949 §3).

PILLAR: DISCOVER / FORMATTING / TRUTH · SHIP: the ``field_leaders`` round-up
producer kind — each row is one member field's leading outcome carrying the
venue's own bucket label verbatim (weather daily highs, opening-weekend box
office, and this week's economic releases).

Rules enforced:
* **Exclusive bucket sets only (#11995 decision 6-A)**: every candidate member
  must be a one-winner mutually-exclusive bucket set that passes
  ``display_probability_divisor`` / ``normalize_display_probs``. Cumulative
  ``Above X`` / ``Below X`` threshold ladders are refused so brackets are never
  computed by subtracting asynchronous quotes.
* **Date & window honesty**:
  - ``weather_daily_highs``: stored ``resolution_date`` is tomorrow in the
    city's timezone, and any date stated in the market title must match the
    stored date (``title_date_mismatch``).
  - ``economic_releases_week``: requires a stored release timestamp
    (``release_at`` / ``release_time``) in the future within 7 days; refuses
    when missing (``missing_release_time``) or past (``release_time_passed``),
    and folds duplicate markets for the same release (``fold_same_release``).
  - ``box_office_opening_weekend``: opening-weekend bucket markets in the
    Thursday–Monday window, one per film.
* **Top-two range separation**: if a member's top two buckets are within 1
  percentage point, that member's row is dropped.
* **Freshness bound**: any member whose leading observation is older than the
  6-hour futures cadence is refused (``stale_observation``).
* **Minimum 3 coherent members**: fewer than 3 coherent members withholds the
  entire card and container (``too_few_coherent_members``).
"""

from __future__ import annotations

import importlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from app.utils.container_presentation import MEMBER_MARKET, market_destination
from app.utils.field_band import _iso_utc, _validate_narrative_copy
from app.utils.futures_liveness import leg_is_graded
from app.utils.ladder_monotonicity import DEC, INC, parse_threshold
from app.utils.outcome_display import (
    display_probability_divisor,
    normalize_display_probs,
)
from app.utils.tonights_games import _parse_dt


def _rc() -> Any:
    return importlib.import_module("app.utils.roundup_containers")


__all__ = [
    "OPENING_WEEKEND_DEFINITION",
    "OPENING_WEEKEND_DEFINITION_PATH",
    "OPENING_WEEKEND_ID",
    "OPENING_WEEKEND_PRODUCER",
    "OPENING_WEEKEND_SLUG",
    "PRODUCER_KIND_FIELD_LEADERS",
    "SPECIALTY_FIELD_MASS_MIN",
    "THIS_WEEKS_ECONOMIC_DATA_DEFINITION",
    "THIS_WEEKS_ECONOMIC_DATA_DEFINITION_PATH",
    "THIS_WEEKS_ECONOMIC_DATA_ID",
    "THIS_WEEKS_ECONOMIC_DATA_PRODUCER",
    "THIS_WEEKS_ECONOMIC_DATA_SLUG",
    "TOMORROWS_HIGHS_DEFINITION",
    "TOMORROWS_HIGHS_DEFINITION_PATH",
    "TOMORROWS_HIGHS_ID",
    "TOMORROWS_HIGHS_PRODUCER",
    "TOMORROWS_HIGHS_SLUG",
    "build_field_leaders_producer",
    "field_leaders_enabled",
    "load_field_leaders_definition",
    "opening_weekend",
    "produce_field_leaders",
    "select_field_leaders",
    "this_weeks_economic_data",
    "tomorrows_highs",
]

PRODUCER_KIND_FIELD_LEADERS = "field_leaders"
SPECIALTY_FIELD_MASS_MIN = 0.9

TOMORROWS_HIGHS_SLUG = "roundup-tomorrows-highs"
TOMORROWS_HIGHS_ID = "roundup:tomorrows-highs"
TOMORROWS_HIGHS_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{TOMORROWS_HIGHS_SLUG}.json"
)

OPENING_WEEKEND_SLUG = "roundup-opening-weekend"
OPENING_WEEKEND_ID = "roundup:opening-weekend"
OPENING_WEEKEND_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{OPENING_WEEKEND_SLUG}.json"
)

THIS_WEEKS_ECONOMIC_DATA_SLUG = "roundup-this-weeks-economic-data"
THIS_WEEKS_ECONOMIC_DATA_ID = "roundup:this-weeks-economic-data"
THIS_WEEKS_ECONOMIC_DATA_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{THIS_WEEKS_ECONOMIC_DATA_SLUG}.json"
)

_DEFAULT_TZ = ZoneInfo("America/New_York")

_CITY_TIMEZONES: dict[str, str] = {
    "new york": "America/New_York",
    "nyc": "America/New_York",
    "boston": "America/New_York",
    "miami": "America/New_York",
    "philadelphia": "America/New_York",
    "atlanta": "America/New_York",
    "washington": "America/New_York",
    "chicago": "America/Chicago",
    "dallas": "America/Chicago",
    "houston": "America/Chicago",
    "austin": "America/Chicago",
    "minneapolis": "America/Chicago",
    "denver": "America/Denver",
    "phoenix": "America/Phoenix",
    "los angeles": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "las vegas": "America/Los_Angeles",
}

_MONTH_NUMBERS: dict[str, int] = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_TITLE_MONTH_DAY_RE = re.compile(
    r"\b(?:on\s+|for\s+|in\s+)?(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:\s*,\s*(?P<year>20\d{2}))?\b",
    re.IGNORECASE,
)


def field_leaders_enabled() -> bool:
    """Feature flag check for ``field_leaders`` round-up containers."""
    return os.getenv("FIELD_LEADERS_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _half_up_percent(prob: float) -> int:
    return int(math.floor(prob * 100.0 + 0.5))


def _resolve_city_tz(market: Mapping[str, Any], subject: str) -> ZoneInfo:
    raw_tz = str(
        market.get("city_tz")
        or (market.get("market_metadata") or {}).get("city_tz")
        or ""
    ).strip()
    if raw_tz:
        try:
            return ZoneInfo(raw_tz)
        except Exception:
            pass
    tz_name = _CITY_TIMEZONES.get(subject.strip().casefold())
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    return _DEFAULT_TZ


def _extract_title_date(title: str, default_year: int) -> Optional[date]:
    m = _TITLE_MONTH_DAY_RE.search(str(title or ""))
    if m is None:
        return None
    month_num = _MONTH_NUMBERS.get(m.group("month").lower().rstrip("."))
    if month_num is None:
        return None
    day_num = int(m.group("day"))
    year_num = int(m.group("year")) if m.group("year") else default_year
    try:
        return date(year_num, month_num, day_num)
    except ValueError:
        return None


def _extract_subject(market: Mapping[str, Any], domain: str) -> str:
    explicit = str(
        market.get("subject")
        or market.get("city")
        or market.get("film")
        or market.get("release_label")
        or (market.get("market_metadata") or {}).get("subject")
        or ""
    ).strip()
    if explicit:
        return explicit

    name = str(market.get("name") or "").strip()
    if domain == "weather_daily_highs":
        m = re.search(
            r"(?:high(?:est)?\s+temperature\s+in|high\s+in)\s+(?P<city>[A-Za-z .'-]+?)(?:\s+on\b|\s+for\b|\?|$)",
            name,
            re.IGNORECASE,
        )
        if m:
            return m.group("city").strip()
    elif domain == "box_office_opening_weekend":
        m = re.search(
            r"^(?P<film>.+?)\s+(?:opening\s+weekend|domestic\s+opening|box\s+office)\b",
            name,
            re.IGNORECASE,
        )
        if m:
            return m.group("film").strip(" -–—:?")
    elif domain == "economic_releases_week":
        m = re.search(
            r"^(?P<rel>.+?)(?:\s+in\s+[A-Za-z]+\s+20\d{2}|\?|$)",
            name,
            re.IGNORECASE,
        )
        if m:
            return m.group("rel").strip(" -–—:?")
    return name.rstrip("?.!")


def _is_cumulative_threshold_ladder(outcomes: Sequence[Mapping[str, Any]]) -> bool:
    """Return True when outcomes are cumulative ``Above X`` / ``Below X`` threshold rungs."""
    parsed_dirs: list[str] = []
    for o in outcomes:
        label = str(o.get("name") or o.get("label") or "").strip()
        if not label:
            continue
        # Range labels with explicit dash/to between two bounds are buckets, not cumulative ladders.
        if re.search(r"\d\s*(?:–|—|-|to)\s*-?\d", label, re.IGNORECASE):
            continue
        p = parse_threshold(label)
        if p is not None and p[2] in (INC, DEC):
            parsed_dirs.append(p[2])
    return len(parsed_dirs) >= 2 and len(set(parsed_dirs)) == 1 and len(parsed_dirs) >= len(outcomes) // 2


@dataclass(frozen=True)
class _NormalizedBucket:
    outcome_id: int
    label: str
    probability: float
    rendered_percent: int
    observed_at: Optional[str]


@dataclass(frozen=True)
class _CoherentFieldMember:
    market_id: int
    source: Optional[str]
    category: str
    name: str
    subject: str
    release_key: str
    release_at: Optional[datetime]
    resolution_date: Optional[str]
    leader: _NormalizedBucket
    buckets: tuple[_NormalizedBucket, ...]
    raw_market: Mapping[str, Any]


_BOX_OFFICE_RANGE_RE = re.compile(
    r"\$?\s*(?P<lo>\d+(?:\.\d+)?)\s*(?P<lo_u>[kmb])?\s*(?:–|—|-|to)\s*\$?\s*(?P<hi>\d+(?:\.\d+)?)\s*(?P<hi_u>[kmb])?",
    re.IGNORECASE,
)
_BOX_OFFICE_LOW_TAIL_RE = re.compile(
    r"(?:^\s*[<≤]\s*|^\s*(?:under|below|less\s+than)\s+)\$?\s*(?P<val>\d+(?:\.\d+)?)\s*(?P<u1>[kmb])?"
    r"|\$?\s*(?P<val2>\d+(?:\.\d+)?)\s*(?P<u2>[kmb])?\s+or\s+(?:less|below|under|lower)",
    re.IGNORECASE,
)
_BOX_OFFICE_HIGH_TAIL_RE = re.compile(
    r"(?:^\s*[>≥]\s*|^\s*(?:over|above|more\s+than|at\s+least)\s+)\$?\s*(?P<val>\d+(?:\.\d+)?)\s*(?P<u1>[kmb])?"
    r"|\$?\s*(?P<val2>\d+(?:\.\d+)?)\s*(?P<u2>[kmb])?\s*(?:\+|or\s+(?:more|higher|above|greater))",
    re.IGNORECASE,
)


def _to_millions(raw_val: str, raw_unit: Optional[str], fallback_unit: Optional[str] = None) -> float:
    val = float(raw_val)
    u = (raw_unit or fallback_unit or "m").lower()
    if u == "k":
        return val / 1000.0
    if u == "b":
        return val * 1000.0
    return val


def _expected_box_office_millions(buckets: Sequence[_NormalizedBucket]) -> float:
    """Compute probability-weighted expected opening gross in $M (#12659).

    Wide releases with multi-bracket dispersion (e.g. Ebenezer leading at
    ``19m-22m`` · 38%) must rank above micro-budget releases whose ``<2.5m``
    bottom bracket sits at 92%.
    """
    widths: list[float] = []
    for b in buckets:
        m = _BOX_OFFICE_RANGE_RE.search(b.label)
        if m:
            hi_u = m.group("hi_u")
            lo_u = m.group("lo_u") or hi_u
            lo = _to_millions(m.group("lo"), lo_u)
            hi = _to_millions(m.group("hi"), hi_u, lo_u)
            if hi > lo:
                widths.append(hi - lo)
    interior_width = sorted(widths)[len(widths) // 2] if widths else 0.0

    expected = 0.0
    matched_prob = 0.0
    for b in buckets:
        label = b.label.strip()
        m_range = _BOX_OFFICE_RANGE_RE.search(label)
        midpoint: Optional[float] = None
        if m_range:
            hi_u = m_range.group("hi_u")
            lo_u = m_range.group("lo_u") or hi_u
            lo = _to_millions(m_range.group("lo"), lo_u)
            hi = _to_millions(m_range.group("hi"), hi_u, lo_u)
            midpoint = (lo + hi) / 2.0
        else:
            m_low = _BOX_OFFICE_LOW_TAIL_RE.search(label)
            if m_low:
                raw_v = m_low.group("val") or m_low.group("val2")
                raw_u = m_low.group("u1") or m_low.group("u2")
                if raw_v is not None:
                    cap = _to_millions(raw_v, raw_u)
                    midpoint = max(0.0, cap / 2.0)
            else:
                m_high = _BOX_OFFICE_HIGH_TAIL_RE.search(label)
                if m_high:
                    raw_v = m_high.group("val") or m_high.group("val2")
                    raw_u = m_high.group("u1") or m_high.group("u2")
                    if raw_v is not None:
                        floor = _to_millions(raw_v, raw_u)
                        tail_half = (
                            interior_width / 2.0
                            if interior_width > 0
                            else max(floor * 0.10, 1.5)
                        )
                        midpoint = floor + tail_half
        if midpoint is not None:
            expected += b.probability * midpoint
            matched_prob += b.probability
    if matched_prob <= 0.0:
        return 0.0
    return expected / matched_prob


def _build_field_leader_card(member: _CoherentFieldMember) -> dict[str, Any]:
    base = member.raw_market
    top_outcomes = [
        {
            "id": b.outcome_id,
            "name": b.label,
            "probability": b.probability,
            "rendered_percent": b.rendered_percent,
            "american_odds": None,
            "rank": idx + 1,
            "movement": None,
            "is_winner": False,
            "resolution_source": None,
        }
        for idx, b in enumerate(member.buckets)
    ]
    return {
        "id": member.market_id,
        "name": member.name,
        "sport": base.get("sport"),
        "sport_name": base.get("sport_name"),
        "category": member.category,
        "llm_sport_category": base.get("llm_sport_category") or member.category,
        "market_tier": int(base.get("market_tier") or 2),
        "market_type_label": base.get("market_type_label") or "Range distribution",
        "market_type": "field",
        "status": "open",
        "source": member.source,
        "sources": [member.source] if member.source else [],
        "source_count": 1 if member.source else 0,
        "mutually_exclusive": True,
        "resolution_date": member.resolution_date,
        "top_outcomes": top_outcomes,
        "outcome_count": len(member.buckets),
        "updated_at": _iso_utc(base.get("updated_at")) or member.leader.observed_at,
        "prices_updated_at": member.leader.observed_at,
        "price_observed_at": member.leader.observed_at,
    }


def select_field_leaders(
    markets: Mapping[int, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    domain: str = "weather_daily_highs",
    window: str = "tomorrow_in_city_zone",
    order: str = "least_likely_leader",
    min_members: int = 3,
    card_rows: int = 3,
    min_top_two_gap_points: int = 1,
    max_age_hours: float = 6.0,
    require_release_time: bool = False,
    fold_same_release: bool = False,
    require_guard_11995: bool = True,
    section_title: str = "Tomorrow's highs",
    footer: str = "Each row is the likeliest range for that city's high; a city's ranges add to 100.",
    title: Optional[str] = None,
    kicker: Optional[str] = None,
    now: Optional[datetime] = None,
    withheld_by_market: Optional[Mapping[int, set[int]]] = None,
) -> Any:
    """Pure selector for ``field_leaders`` (#11949 §3)."""
    rc = _rc()
    RoundupMembers = rc.RoundupMembers
    RoundupRefusal = rc.RoundupRefusal

    _validate_narrative_copy(footer, title or "", kicker or "", section_title)

    effective_now = (
        now.astimezone(timezone.utc)
        if isinstance(now, datetime) and now.tzinfo is not None
        else datetime.now(timezone.utc)
    )

    seq = markets.values() if isinstance(markets, Mapping) else markets
    raw_list: list[Mapping[str, Any]] = []
    seen_ids: set[int] = set()
    for m in seq:
        if not isinstance(m, Mapping):
            continue
        mid = m.get("id")
        if isinstance(mid, int) and not isinstance(mid, bool) and mid > 0:
            if int(mid) not in seen_ids:
                seen_ids.add(int(mid))
                raw_list.append(m)

    if not raw_list:
        return RoundupRefusal((("field_leaders", "empty_pool"),))

    candidates: list[_CoherentFieldMember] = []
    seen_subjects: set[str] = set()
    dropped_reasons: list[tuple[str, str]] = []

    for m in raw_list:
        mid = int(m["id"])
        status = str(m.get("status") or "open").strip().lower()
        if status != "open":
            continue

        subject = _extract_subject(m, domain)
        if not subject:
            continue

        # Check resolution_date / window filter first so out-of-window markets are skipped cleanly
        # without failing per-member checks (gotcha #42: one bad item must never wipe a scoring pass).
        res_dt = _parse_dt(m.get("resolution_date"))
        if domain == "weather_daily_highs":
            if res_dt is None:
                dropped_reasons.append(("field_leaders", f"missing_resolution_date:{mid}"))
                continue
            city_tz = _resolve_city_tz(m, subject)
            tomorrow_local = effective_now.astimezone(city_tz).date() + timedelta(days=1)
            stored_local_date = res_dt.astimezone(city_tz).date()
            title_date = _extract_title_date(str(m.get("name") or ""), tomorrow_local.year)
            if title_date is not None and title_date != stored_local_date:
                dropped_reasons.append(("field_leaders", f"title_date_mismatch:{mid}"))
                continue
            if stored_local_date != tomorrow_local:
                continue
        elif domain == "box_office_opening_weekend":
            if res_dt is None:
                dropped_reasons.append(("field_leaders", f"missing_resolution_date:{mid}"))
                continue
            res_utc = res_dt.astimezone(timezone.utc)
            if res_utc <= effective_now or res_utc > effective_now + timedelta(days=6):
                continue
        elif domain == "economic_releases_week":
            if res_dt is not None:
                res_utc = res_dt.astimezone(timezone.utc)
                if res_utc <= effective_now or res_utc > effective_now + timedelta(days=7):
                    continue

        # Check release time for economic releases.
        release_raw = (
            m.get("release_at")
            or m.get("release_time")
            or (m.get("market_metadata") or {}).get("release_at")
            or (m.get("market_metadata") or {}).get("release_time")
        )
        release_dt = _parse_dt(release_raw)
        if require_release_time or domain == "economic_releases_week":
            if release_dt is None:
                dropped_reasons.append(("field_leaders", f"missing_release_time:{mid}"))
                continue
            release_utc = release_dt.astimezone(timezone.utc)
            if release_utc <= effective_now:
                dropped_reasons.append(("field_leaders", f"release_time_passed:{mid}"))
                continue
            if release_utc > effective_now + timedelta(days=7):
                continue
        else:
            release_utc = release_dt.astimezone(timezone.utc) if release_dt is not None else None

        outcomes = m.get("outcomes")
        if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
            outcomes = m.get("top_outcomes")
        if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)) or len(outcomes) < 2:
            dropped_reasons.append(("field_leaders", f"missing_outcomes:{mid}"))
            continue

        outcome_mappings = [o for o in outcomes if isinstance(o, Mapping)]
        if _is_cumulative_threshold_ladder(outcome_mappings):
            dropped_reasons.append(("field_leaders", f"cumulative_ladder_not_allowed:{mid}"))
            continue

        if m.get("mutually_exclusive") is not True:
            dropped_reasons.append(("field_leaders", f"guard_failed:{mid}"))
            continue

        blocked = (
            set(withheld_by_market.get(mid, set()))
            if withheld_by_market is not None
            else set()
        )

        raw_buckets: list[tuple[int, str, float, Optional[str]]] = []
        market_obs = _iso_utc(
            m.get("prices_updated_at")
            or m.get("price_observed_at")
            or m.get("updated_at")
        )
        bucket_error: Optional[str] = None
        for idx, o in enumerate(outcome_mappings):
            if leg_is_graded(o.get("is_winner"), o.get("resolution_source")):
                bucket_error = f"graded_outcome:{mid}"
                break
            oid_raw = o.get("id")
            oid = (
                int(oid_raw)
                if isinstance(oid_raw, int) and not isinstance(oid_raw, bool) and oid_raw > 0
                else mid * 100 + idx + 1
            )
            if oid in blocked:
                bucket_error = f"withheld_price:{mid}"
                break
            label = str(o.get("name") or o.get("label") or "").strip()
            if not label:
                bucket_error = f"empty_bucket_label:{mid}"
                break
            p_raw = (
                o.get("probability")
                if "probability" in o
                else o.get("current_probability")
            )
            if p_raw is None or isinstance(p_raw, bool):
                bucket_error = f"unpriced_bucket:{mid}"
                break
            try:
                p_val = float(p_raw)
            except (TypeError, ValueError):
                bucket_error = f"unpriced_bucket:{mid}"
                break
            if not math.isfinite(p_val) or p_val < 0.0 or p_val > 1.0:
                bucket_error = f"invalid_probability:{mid}"
                break
            obs = _iso_utc(o.get("observed_at") or o.get("last_updated")) or market_obs
            raw_buckets.append((oid, label, p_val, obs))

        if bucket_error is not None:
            dropped_reasons.append(("field_leaders", bucket_error))
            continue

        if len(raw_buckets) < 2:
            dropped_reasons.append(("field_leaders", f"too_few_buckets:{mid}"))
            continue

        raw_mass = sum(p_val for _, _, p_val, _ in raw_buckets)
        if raw_mass + 1e-9 < SPECIALTY_FIELD_MASS_MIN:
            dropped_reasons.append(("field_leaders", f"partial_field:{mid}"))
            continue

        outcome_dicts: list[dict[str, Any]] = [
            {
                "id": oid,
                "name": label,
                "probability": p_val,
                "observed_at": obs,
            }
            for oid, label, p_val, obs in raw_buckets
        ]
        if require_guard_11995:
            divisor = display_probability_divisor(
                outcome_dicts,
                mutually_exclusive=True,
                field_complete=True,
                question=str(m.get("name") or ""),
            )
            if divisor is None:
                dropped_reasons.append(("field_leaders", f"guard_failed:{mid}"))
                continue
            normalize_display_probs(
                outcome_dicts,
                mutually_exclusive=True,
                field_complete=True,
                question=str(m.get("name") or ""),
            )

        norm_buckets = [
            _NormalizedBucket(
                outcome_id=int(od["id"]),
                label=str(od["name"]),
                probability=float(od["probability"]),
                rendered_percent=(
                    int(od["rendered_percent"])
                    if isinstance(od.get("rendered_percent"), int)
                    else _half_up_percent(float(od["probability"]))
                ),
                observed_at=od.get("observed_at"),
            )
            for od in outcome_dicts
        ]
        by_prob = sorted(
            norm_buckets,
            key=lambda b: (-b.probability, b.outcome_id),
        )
        leader = by_prob[0]
        runner_up = by_prob[1]

        # Freshness check (6h cadence) on both leader and runner-up so a stale runner-up cannot decide the 1-pt gap.
        freshness_reason: Optional[str] = None
        for top_bucket in (leader, runner_up):
            obs_dt = _parse_dt(top_bucket.observed_at)
            if obs_dt is None:
                freshness_reason = f"missing_observation_time:{mid}"
                break
            age_hours = (effective_now - obs_dt.astimezone(timezone.utc)).total_seconds() / 3600.0
            if age_hours > max_age_hours:
                freshness_reason = f"stale_observation:{mid}"
                break
        if freshness_reason is not None:
            dropped_reasons.append(("field_leaders", freshness_reason))
            continue

        # Top two ranges within 1 point -> drop that row (not a whole-card refusal unless < min_members remain).
        if (
            abs(leader.rendered_percent - runner_up.rendered_percent) <= min_top_two_gap_points
            or abs(leader.probability - runner_up.probability) <= (min_top_two_gap_points / 100.0) + 1e-9
        ):
            dropped_reasons.append(("field_leaders", f"top_two_within_gap:{mid}"))
            continue

        release_key = str(
            m.get("release_key")
            or (m.get("market_metadata") or {}).get("release_key")
            or subject
        ).strip().casefold()
        dedup_key = release_key if fold_same_release else subject.strip().casefold()
        if dedup_key in seen_subjects:
            continue
        seen_subjects.add(dedup_key)

        raw_src = str(m.get("source") or "").strip().lower()
        source_str: Optional[str] = raw_src if raw_src else None
        cat_str = str(m.get("category") or domain).strip().lower()
        candidates.append(
            _CoherentFieldMember(
                market_id=mid,
                source=source_str,
                category=cat_str,
                name=str(m.get("name") or subject).strip(),
                subject=subject,
                release_key=release_key,
                release_at=release_utc,
                resolution_date=_iso_utc(m.get("resolution_date")),
                leader=leader,
                buckets=tuple(norm_buckets),
                raw_market=m,
            )
        )

    if len(candidates) < min_members:
        return RoundupRefusal(
            tuple(dropped_reasons) + (("field_leaders", "too_few_coherent_members"),)
        )

    if order == "least_likely_leader":
        selected = sorted(
            candidates,
            key=lambda c: (c.leader.probability, c.subject.casefold(), c.market_id),
        )[:card_rows]
    elif order == "release_time_asc":
        selected = sorted(
            candidates,
            key=lambda c: (
                c.release_at or effective_now,
                -c.leader.probability,
                c.market_id,
            ),
        )[:card_rows]
    elif order == "expected_box_office_desc":
        selected = sorted(
            candidates,
            key=lambda c: (
                -round(_expected_box_office_millions(c.buckets), 6),
                -c.leader.probability,
                c.subject.casefold(),
                c.market_id,
            ),
        )[:card_rows]
    else:
        selected = sorted(
            candidates,
            key=lambda c: (-c.leader.probability, c.subject.casefold(), c.market_id),
        )[:card_rows]

    if order == "expected_box_office_desc":
        # Preserve expected-gross descending order (#12659); producer emits
        # `roundup_contract["order"] = "sequence"` so RoundupCard keeps it.
        ordered_selected = list(selected)
    else:
        # RoundupCard sorts rows highest-probability-first; order selected rows & members to match.
        ordered_selected = sorted(
            selected,
            key=lambda c: (-c.leader.probability, c.subject.casefold(), c.market_id),
        )

    rows_out: list[dict[str, Any]] = []
    member_entries: list[dict[str, Any]] = []
    revision_ids: list[int] = []

    for c in ordered_selected:
        row_label = f"{c.subject} · {c.leader.label}"
        rows_out.append(
            {
                "market_id": c.market_id,
                "outcome_id": c.leader.outcome_id,
                "label": row_label,
                "probability": c.leader.probability,
                "rendered_percent": c.leader.rendered_percent,
                "observed_at": c.leader.observed_at,
            }
        )
        card = _build_field_leader_card(c)
        member_entries.append(
            {
                "type": MEMBER_MARKET,
                "id": c.market_id,
                "destination": market_destination(c.market_id),
                "card": card,
                "event_id": None,
            }
        )
        revision_ids.append(c.market_id)

    sections_out = [
        {
            "class": "title",
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
        title=title,
        kicker=kicker,
        sections=sections_out,
        revision_ids=revision_ids,
    )


async def _load_field_leaders_from_db(
    db: Any,
    *,
    domain: str,
    now: Optional[datetime] = None,
) -> tuple[dict[int, dict[str, Any]], dict[int, set[int]]]:
    """Load candidate ``FuturesMarket`` rows for ``field_leaders`` when ``db`` is a DB session."""
    if not hasattr(db, "execute") or not callable(db.execute):
        return {}, {}

    from sqlalchemy import and_, or_, select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import selectinload

    from app.models import FuturesMarket
    from app.routes.futures import withheld_price_outcome_ids_for_markets

    effective_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    window_floor = effective_now - timedelta(days=1)
    window_ceil = effective_now + timedelta(days=8)

    if domain == "weather_daily_highs":
        cat_filter = and_(
            or_(
                FuturesMarket.category == "weather",
                FuturesMarket.llm_sport_category == "weather",
            ),
            FuturesMarket.resolution_date >= window_floor,
            FuturesMarket.resolution_date <= window_ceil,
        )
    elif domain == "box_office_opening_weekend":
        cat_filter = and_(
            or_(
                FuturesMarket.category == "entertainment",
                FuturesMarket.llm_sport_category == "entertainment",
            ),
            or_(
                FuturesMarket.name.ilike("%opening%"),
                FuturesMarket.name.ilike("%box office%"),
            ),
            FuturesMarket.resolution_date >= window_floor,
            FuturesMarket.resolution_date <= window_ceil,
        )
    else:
        cat_filter = and_(
            or_(
                FuturesMarket.category == "economics",
                FuturesMarket.llm_sport_category == "economics",
            ),
            or_(
                FuturesMarket.resolution_date.is_(None),
                and_(
                    FuturesMarket.resolution_date >= window_floor,
                    FuturesMarket.resolution_date <= window_ceil,
                ),
            ),
        )

    stmt = (
        select(FuturesMarket)
        .options(
            selectinload(FuturesMarket.sport),
            selectinload(FuturesMarket.outcomes),
        )
        .where(
            and_(
                FuturesMarket.status == "open",
                cat_filter,
            )
        )
        .order_by(FuturesMarket.id.desc())
        .limit(200)
    )
    res = await db.execute(stmt)
    if not hasattr(res, "scalars") or not callable(res.scalars):
        return {}, {}
    scalars_obj = res.scalars()
    if not hasattr(scalars_obj, "all") or not callable(scalars_obj.all):
        return {}, {}
    rows = list(scalars_obj.all())
    if not rows:
        return {}, {}

    orm_rows = [
        m
        for m in rows
        if not isinstance(m, Mapping)
        and isinstance(getattr(m, "id", None), int)
        and not isinstance(getattr(m, "id", None), bool)
    ]
    withheld: dict[int, set[int]] = {}
    if isinstance(db, AsyncSession) and orm_rows:
        withheld = await withheld_price_outcome_ids_for_markets(db, orm_rows)

    by_id: dict[int, dict[str, Any]] = {}
    for m in rows:
        if isinstance(m, Mapping):
            raw_id = m.get("id")
            if isinstance(raw_id, int) and not isinstance(raw_id, bool) and raw_id > 0:
                entry = dict(m)
                entry["id"] = int(raw_id)
                by_id[int(raw_id)] = entry
            continue
        raw_mid = getattr(m, "id", None)
        if not isinstance(raw_mid, int) or isinstance(raw_mid, bool) or raw_mid <= 0:
            continue
        mid = int(raw_mid)
        outcomes_list = [
            {
                "id": int(o.id),
                "name": o.name,
                "probability": (
                    float(o.current_probability)
                    if o.current_probability is not None
                    else None
                ),
                "is_winner": getattr(o, "is_winner", None),
                "resolution_source": getattr(o, "resolution_source", None),
                "observed_at": (
                    o.last_updated.isoformat()
                    if getattr(o, "last_updated", None) is not None
                    else None
                ),
            }
            for o in (getattr(m, "outcomes", None) or ())
        ]
        by_id[mid] = {
            "id": mid,
            "name": getattr(m, "name", None),
            "status": getattr(m, "status", None),
            "source": getattr(m, "source", None),
            "category": getattr(m, "category", None),
            "llm_sport_category": getattr(m, "llm_sport_category", None),
            "market_tier": getattr(m, "market_tier", None),
            "market_type": getattr(m, "market_type", None),
            "mutually_exclusive": getattr(m, "mutually_exclusive", None),
            "resolution_date": getattr(m, "resolution_date", None),
            "updated_at": getattr(m, "updated_at", None),
            "prices_updated_at": getattr(m, "prices_updated_at", None),
            "market_metadata": getattr(m, "market_metadata", None),
            "outcomes": outcomes_list,
        }
    return by_id, {int(k): set(v) for k, v in (withheld or {}).items()}


async def produce_field_leaders(
    db: Any,
    definition: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Any:
    """Evaluate a stored ``field_leaders`` definition against ``db`` (or an in-memory fixture)."""
    rule = definition.get("rule")
    if not isinstance(rule, Mapping):
        raise ValueError("field_leaders definition requires a 'rule' mapping")
    if rule.get("producer") != PRODUCER_KIND_FIELD_LEADERS:
        raise ValueError(
            f"Unsupported producer kind {rule.get('producer')!r}; expected {PRODUCER_KIND_FIELD_LEADERS!r}"
        )

    domain = str(rule.get("domain") or "weather_daily_highs")
    withheld_by_market: dict[int, set[int]] = {}
    if isinstance(db, Mapping):
        by_id = {int(k): v for k, v in db.items() if isinstance(v, Mapping)}
    elif isinstance(db, (list, tuple)):
        by_id = {
            int(m["id"]): m
            for m in db
            if isinstance(m, Mapping)
            and isinstance(m.get("id"), int)
            and not isinstance(m.get("id"), bool)
        }
    else:
        by_id, withheld_by_market = await _load_field_leaders_from_db(
            db, domain=domain, now=now
        )

    return select_field_leaders(
        by_id,
        domain=domain,
        window=str(rule.get("window") or "tomorrow_in_city_zone"),
        order=str(rule.get("order") or "least_likely_leader"),
        min_members=int(rule.get("min_members", 3)),
        card_rows=int(rule.get("card_rows", 3)),
        min_top_two_gap_points=int(rule.get("min_top_two_gap_points", 1)),
        max_age_hours=float(rule.get("max_age_hours", 6.0)),
        require_release_time=bool(rule.get("require_release_time", False)),
        fold_same_release=bool(rule.get("fold_same_release", False)),
        require_guard_11995=bool(rule.get("require_guard_11995", True)),
        section_title=str(definition.get("section_title") or "Tomorrow's highs"),
        footer=str(definition.get("footer") or ""),
        title=str(definition.get("name") or "") or None,
        kicker=str(definition.get("kicker") or "") or None,
        now=now,
        withheld_by_market=withheld_by_market,
    )


def load_field_leaders_definition(
    path: Path = TOMORROWS_HIGHS_DEFINITION_PATH,
) -> dict[str, Any]:
    """Load and validate a stored ``field_leaders`` JSON definition."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Container definition at {path} must be a JSON object")
    if data.get("kind") != "roundup":
        raise ValueError(f"Container definition {path} must have kind='roundup'")
    rule = data.get("rule")
    if not isinstance(rule, Mapping) or rule.get("producer") != PRODUCER_KIND_FIELD_LEADERS:
        raise ValueError(
            f"Container definition {path} must declare rule.producer={PRODUCER_KIND_FIELD_LEADERS!r}"
        )
    _validate_narrative_copy(
        str(data.get("name") or ""),
        str(data.get("footer") or ""),
        str(data.get("kicker") or ""),
        str(data.get("section_title") or ""),
    )
    return data


def build_field_leaders_producer(
    definition: Mapping[str, Any],
    *,
    enabled: Optional[Callable[[], bool]] = None,
) -> Any:
    """Instantiate a ``RoundupProducer`` from a stored ``field_leaders`` definition."""
    RoundupProducer = _rc().RoundupProducer
    slug = str(definition["slug"])
    name = str(definition["name"])
    kind = str(definition.get("kind") or "roundup")
    category = str(definition.get("category") or "weather")
    section_title = definition.get("section_title") or ""
    footer = str(definition["footer"])
    membership = str(definition.get("membership") or "computed-produced")
    rule = definition.get("rule")
    tag = (
        str(definition["tag"])
        if "tag" in definition and definition["tag"] is not None
        else ""
    )
    kicker = str(definition.get("kicker") or "ROUND-UP")
    story_key = f"roundup:{slug.removeprefix('roundup-')}"

    async def _produce(db: Any) -> Any:
        return await produce_field_leaders(db, definition)

    contract_order: Optional[str] = None
    if isinstance(rule, Mapping) and str(rule.get("order") or "") == "expected_box_office_desc":
        contract_order = "sequence"

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
        order=contract_order,
        enabled=enabled if enabled is not None else field_leaders_enabled,
    )


TOMORROWS_HIGHS_DEFINITION: dict[str, Any] = load_field_leaders_definition(
    TOMORROWS_HIGHS_DEFINITION_PATH
)
OPENING_WEEKEND_DEFINITION: dict[str, Any] = load_field_leaders_definition(
    OPENING_WEEKEND_DEFINITION_PATH
)
THIS_WEEKS_ECONOMIC_DATA_DEFINITION: dict[str, Any] = load_field_leaders_definition(
    THIS_WEEKS_ECONOMIC_DATA_DEFINITION_PATH
)


async def tomorrows_highs(db: Any, *, now: Optional[datetime] = None) -> Any:
    return await produce_field_leaders(db, TOMORROWS_HIGHS_DEFINITION, now=now)


async def opening_weekend(db: Any, *, now: Optional[datetime] = None) -> Any:
    return await produce_field_leaders(db, OPENING_WEEKEND_DEFINITION, now=now)


async def this_weeks_economic_data(db: Any, *, now: Optional[datetime] = None) -> Any:
    return await produce_field_leaders(
        db, THIS_WEEKS_ECONOMIC_DATA_DEFINITION, now=now
    )


TOMORROWS_HIGHS_PRODUCER = build_field_leaders_producer(TOMORROWS_HIGHS_DEFINITION)
OPENING_WEEKEND_PRODUCER = build_field_leaders_producer(OPENING_WEEKEND_DEFINITION)
THIS_WEEKS_ECONOMIC_DATA_PRODUCER = build_field_leaders_producer(
    THIS_WEEKS_ECONOMIC_DATA_DEFINITION
)
for _p in (
    TOMORROWS_HIGHS_PRODUCER,
    OPENING_WEEKEND_PRODUCER,
    THIS_WEEKS_ECONOMIC_DATA_PRODUCER,
):
    _rc().register_roundup_producer(_p)
