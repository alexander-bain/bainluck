"""Reusable ``yardstick_pair`` producer kind and the ``for-scale-snow-in-dc``, ``for-scale-snow-in-buffalo``, and ``for-scale-us-recession-2026`` definitions (``docs/discover/grouping-types-2026-11.md`` §1.4).

PILLAR: DISCOVER / TRUTH · SHIP: the cross-topic grouping type "The yardstick" —
an unfamiliar binary market set beside a familiar anchor market from a different
category, with the headline sentence recomputed from the two live numbers on
every serve and never cached as static text. Under Alex's Decision C ruling,
whole numbers within 2 percentage points print ``"<target>: as likely as
<anchor>"`` (with ``"less likely than"`` at >= 10 points apart gated behind
``allow_less_likely=True``), while pairs sitting 3–9 points apart, missing a
fresh observation, within 48 hours of their deciding event, in the same
category, past the anchor's deadline, or in an excluded class refuse cleanly.
"""

from __future__ import annotations

import importlib
import inspect
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from app.utils.container_presentation import MEMBER_MARKET, market_destination
from app.utils.field_band import _iso_utc, _validate_narrative_copy, parse_market_ref
from app.utils.futures_liveness import leg_is_graded
from app.utils.same_deadline_board import (
    EXCLUDED_CLASSES,
    _QualifiedDeadlineMarket,
    _build_binary_member_card,
    _effective_category,
    _excluded_class_reason,
    _half_up_percent,
    _orm_market_to_dict,
    _parse_deadline_date,
)
from app.utils.tonights_games import _parse_dt


def _rc() -> Any:
    return importlib.import_module("app.utils.roundup_containers")


__all__ = [
    "DEFAULT_APART_BAND_MIN_DIFF",
    "DEFAULT_MAX_AGE_HOURS",
    "DEFAULT_MIN_HOURS_TO_DECISION",
    "DEFAULT_SAME_BAND_MAX_DIFF",
    "FOR_SCALE_SNOW_IN_BUFFALO_DEFINITION",
    "FOR_SCALE_SNOW_IN_BUFFALO_DEFINITION_PATH",
    "FOR_SCALE_SNOW_IN_BUFFALO_ID",
    "FOR_SCALE_SNOW_IN_BUFFALO_PRODUCER",
    "FOR_SCALE_SNOW_IN_BUFFALO_SLUG",
    "FOR_SCALE_SNOW_IN_DC_DEFINITION",
    "FOR_SCALE_SNOW_IN_DC_DEFINITION_PATH",
    "FOR_SCALE_SNOW_IN_DC_ID",
    "FOR_SCALE_SNOW_IN_DC_PRODUCER",
    "FOR_SCALE_SNOW_IN_DC_SLUG",
    "FOR_SCALE_US_RECESSION_2026_DEFINITION",
    "FOR_SCALE_US_RECESSION_2026_DEFINITION_PATH",
    "FOR_SCALE_US_RECESSION_2026_ID",
    "FOR_SCALE_US_RECESSION_2026_PRODUCER",
    "FOR_SCALE_US_RECESSION_2026_SLUG",
    "MAX_YARDSTICK_PERCENT",
    "MIN_YARDSTICK_PERCENT",
    "PRODUCER_KIND_YARDSTICK_PAIR",
    "build_yardstick_pair_producer",
    "compute_yardstick_sentence",
    "for_scale_snow_in_buffalo",
    "for_scale_snow_in_buffalo_enabled",
    "for_scale_snow_in_dc",
    "for_scale_snow_in_dc_enabled",
    "for_scale_us_recession_2026",
    "for_scale_us_recession_2026_enabled",
    "format_yardstick_labels",
    "load_yardstick_pair_definition",
    "produce_yardstick_pair",
    "select_yardstick_pair",
    "yardstick_pair_enabled",
]

PRODUCER_KIND_YARDSTICK_PAIR = "yardstick_pair"

MIN_YARDSTICK_PERCENT = 3
MAX_YARDSTICK_PERCENT = 97
DEFAULT_SAME_BAND_MAX_DIFF = 2
DEFAULT_APART_BAND_MIN_DIFF = 10
DEFAULT_MAX_AGE_HOURS = 48.0
DEFAULT_MIN_HOURS_TO_DECISION = 48.0

FOR_SCALE_SNOW_IN_DC_SLUG = "for-scale-snow-in-dc"
FOR_SCALE_SNOW_IN_DC_ID = "roundup:for-scale-snow-in-dc"
FOR_SCALE_SNOW_IN_DC_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{FOR_SCALE_SNOW_IN_DC_SLUG}.json"
)

FOR_SCALE_SNOW_IN_BUFFALO_SLUG = "for-scale-snow-in-buffalo"
FOR_SCALE_SNOW_IN_BUFFALO_ID = "roundup:for-scale-snow-in-buffalo"
FOR_SCALE_SNOW_IN_BUFFALO_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{FOR_SCALE_SNOW_IN_BUFFALO_SLUG}.json"
)

FOR_SCALE_US_RECESSION_2026_SLUG = "for-scale-us-recession-2026"
FOR_SCALE_US_RECESSION_2026_ID = "roundup:for-scale-us-recession-2026"
FOR_SCALE_US_RECESSION_2026_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{FOR_SCALE_US_RECESSION_2026_SLUG}.json"
)

_ET_ZONE = ZoneInfo("America/New_York")

_AMPERSAND_COMBO_RE = re.compile(r"\s+&\s+", re.IGNORECASE)

_MIDTERM_ELECTION_DECISION_IDS = frozenset({108619, 108620, 108621, 109685, 67804794, 67804787})
_MIDTERM_ELECTION_DECISION_RE = re.compile(
    r"\b(?:democrats?|republicans?|dem|gop)\s+sweep\b"
    r"|\bcongress\s+balance\s+of\s+power\b"
    r"|\bcore\s+four\b.*\bsenate\b",
    re.IGNORECASE,
)
_MIDTERM_2026_ELECTION_UTC = datetime(2026, 11, 4, 4, 0, tzinfo=timezone.utc)

_MONTH_LONG_TO_SHORT: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bJanuary\s+(\d{1,2})(?:,\s*20\d{2})?\b", re.IGNORECASE), r"Jan \1"),
    (re.compile(r"\bFebruary\s+(\d{1,2})(?:,\s*20\d{2})?\b", re.IGNORECASE), r"Feb \1"),
    (re.compile(r"\bMarch\s+(\d{1,2})(?:,\s*20\d{2})?\b", re.IGNORECASE), r"Mar \1"),
    (re.compile(r"\bApril\s+(\d{1,2})(?:,\s*20\d{2})?\b", re.IGNORECASE), r"Apr \1"),
    (re.compile(r"\bJune\s+(\d{1,2})(?:,\s*20\d{2})?\b", re.IGNORECASE), r"Jun \1"),
    (re.compile(r"\bJuly\s+(\d{1,2})(?:,\s*20\d{2})?\b", re.IGNORECASE), r"Jul \1"),
    (re.compile(r"\bAugust\s+(\d{1,2})(?:,\s*20\d{2})?\b", re.IGNORECASE), r"Aug \1"),
    (re.compile(r"\bSeptember\s+(\d{1,2})(?:,\s*20\d{2})?\b", re.IGNORECASE), r"Sep \1"),
    (re.compile(r"\bOctober\s+(\d{1,2})(?:,\s*20\d{2})?\b", re.IGNORECASE), r"Oct \1"),
    (re.compile(r"\bNovember\s+(\d{1,2})(?:,\s*20\d{2})?\b", re.IGNORECASE), r"Nov \1"),
    (re.compile(r"\bDecember\s+(\d{1,2})(?:,\s*20\d{2})?\b", re.IGNORECASE), r"Dec \1"),
)


def yardstick_pair_enabled() -> bool:
    """Global toggle for ``yardstick_pair`` round-ups."""
    return os.getenv("YARDSTICK_PAIR_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def for_scale_snow_in_dc_enabled() -> bool:
    """Toggle for the ``for-scale-snow-in-dc`` round-up card and container."""
    if not yardstick_pair_enabled():
        return False
    return os.getenv("FOR_SCALE_SNOW_IN_DC_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def for_scale_snow_in_buffalo_enabled() -> bool:
    """Toggle for the ``for-scale-snow-in-buffalo`` round-up card and container."""
    if not yardstick_pair_enabled():
        return False
    return os.getenv("FOR_SCALE_SNOW_IN_BUFFALO_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def for_scale_us_recession_2026_enabled() -> bool:
    """Toggle for the ``for-scale-us-recession-2026`` round-up card and container."""
    if not yardstick_pair_enabled():
        return False
    return os.getenv("FOR_SCALE_US_RECESSION_2026_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _shorten_months(text: str) -> str:
    out = text
    for pat, repl in _MONTH_LONG_TO_SHORT:
        out = pat.sub(repl, out)
    return out


def format_yardstick_labels(
    title: str,
    *,
    is_anchor: bool = False,
    short_override: Optional[str] = None,
    row_override: Optional[str] = None,
) -> tuple[str, str]:
    """Derive ``(short_label, row_label)`` from a binary market title or explicit overrides."""
    cleaned = str(title or "").strip().rstrip("?").strip()
    if not cleaned:
        return ("", "")

    m_snow = re.match(
        r"^will\s+it\s+snow\s+in\s+(?P<city>.+?)\s+by\s+(?P<date>.+)$",
        cleaned,
        re.IGNORECASE,
    )
    if m_snow is not None:
        city_raw = m_snow.group("city").strip()
        date_short = _shorten_months(m_snow.group("date").strip())
        city_no_state = re.sub(r",\s*[A-Z]{2}$", "", city_raw)
        if city_raw.lower() in {"washington, dc", "washington dc"}:
            default_row = f"Snow in Washington, DC by {date_short}"
            default_short = f"snow in DC by {date_short}" if is_anchor else f"Snow in DC by {date_short}"
        else:
            default_row = f"Snow in {city_no_state} by {date_short}"
            default_short = (
                f"snow in {city_no_state} by {date_short}"
                if is_anchor
                else f"Snow in {city_no_state} by {date_short}"
            )
    else:
        body = re.sub(r"^will\s+", "", cleaned, flags=re.IGNORECASE).strip()
        body = re.sub(r"\bcreate\s+a\s+new\b", "creates a new", body)
        body = re.sub(r"\bfall\s+before\b", "falls before", body)
        body = _shorten_months(body)
        if body:
            default_row = body[0].upper() + body[1:]
        else:
            default_row = cleaned
        short_body = re.sub(r"\s+as\s+Secretary\s+of\s+Defense\b", "", default_row, flags=re.IGNORECASE)
        short_body = re.sub(r"\s+or\s+street\s+artwork\b", "", short_body, flags=re.IGNORECASE)
        if is_anchor and short_body.lower().startswith("us recession"):
            default_short = "a " + short_body
        else:
            default_short = short_body

    short_final = str(short_override or "").strip() or default_short
    row_final = str(row_override or "").strip() or default_row
    return short_final, row_final


def compute_yardstick_sentence(
    *,
    target_short: str,
    anchor_short: str,
    target_pct: int,
    anchor_pct: int,
    same_band_max_diff: int = DEFAULT_SAME_BAND_MAX_DIFF,
    apart_band_min_diff: int = DEFAULT_APART_BAND_MIN_DIFF,
    allow_less_likely: bool = False,
    same_footer: str = "Two unrelated markets with the same chance.",
    apart_footer: str = "Two unrelated markets compared for scale.",
) -> Optional[tuple[str, str, str]]:
    """Compute ``(headline, footer, relation)`` from the live whole-number percentages, or ``None`` if outside the bands."""
    t_short = str(target_short or "").strip()
    a_short = str(anchor_short or "").strip()
    if not t_short or not a_short:
        return None

    diff = abs(int(target_pct) - int(anchor_pct))
    if diff <= int(same_band_max_diff):
        headline = f"{t_short}: as likely as {a_short}"
        return headline, same_footer, "as_likely_as"

    if allow_less_likely and (int(anchor_pct) - int(target_pct)) >= int(apart_band_min_diff):
        headline = f"{t_short} is less likely than {a_short}"
        return headline, apart_footer, "less_likely_than"

    return None


@dataclass(frozen=True)
class _QualifiedYardstickMember:
    market_id: int
    yes_outcome_id: int
    source: str
    category: str
    short_label: str
    row_label: str
    probability: float
    no_probability: Optional[float]
    rendered_percent: int
    observed_at: str
    raw_market: Mapping[str, Any]


def _deciding_within_window(
    market: Mapping[str, Any],
    *,
    market_id: int,
    title: str,
    now_dt: datetime,
    min_hours_to_decision: float,
) -> bool:
    """Return True if the market's deciding event is within ``min_hours_to_decision`` hours of ``now_dt``."""
    window_s = float(min_hours_to_decision) * 3600.0
    meta = market.get("market_metadata") if isinstance(market.get("market_metadata"), Mapping) else {}
    for raw_dt in (
        market.get("deciding_at"),
        market.get("deciding_date"),
        market.get("event_date"),
        meta.get("deciding_at") if isinstance(meta, Mapping) else None,
        meta.get("deciding_date") if isinstance(meta, Mapping) else None,
        market.get("resolution_date"),
    ):
        dt = _parse_dt(raw_dt)
        if dt is not None:
            delta_s = (dt.astimezone(timezone.utc) - now_dt.astimezone(timezone.utc)).total_seconds()
            if delta_s <= window_s:
                return True

    if (
        market_id in _MIDTERM_ELECTION_DECISION_IDS
        or _MIDTERM_ELECTION_DECISION_RE.search(title)
    ):
        if abs((now_dt.astimezone(timezone.utc) - _MIDTERM_2026_ELECTION_UTC).total_seconds()) <= window_s:
            return True

    return False


def _qualify_yardstick_member(
    market: Mapping[str, Any],
    *,
    is_anchor: bool,
    short_override: Optional[str],
    row_override: Optional[str],
    anchor_deadline: Optional[date],
    max_age_hours: float,
    min_hours_to_decision: float,
    now_dt: datetime,
    withheld_ids: Optional[set[int]] = None,
) -> tuple[Optional[_QualifiedYardstickMember], Optional[str]]:
    raw_id = market.get("id")
    if not isinstance(raw_id, int) or isinstance(raw_id, bool) or raw_id <= 0:
        return None, "invalid_market_id"
    market_id = int(raw_id)

    status = str(market.get("status") or "").strip().lower()
    if status != "open":
        return None, f"status_{status or 'missing'}"

    title = str(market.get("name") or "").strip()
    if not title:
        return None, "missing_title"

    if is_anchor and anchor_deadline is not None:
        if anchor_deadline < now_dt.astimezone(_ET_ZONE).date():
            return None, "anchor_deadline_passed"

    res_dt = _parse_dt(market.get("resolution_date"))
    if res_dt is not None and res_dt.astimezone(timezone.utc) <= now_dt.astimezone(timezone.utc):
        return None, "anchor_deadline_passed" if is_anchor else "past_deadline"

    if _AMPERSAND_COMBO_RE.search(title):
        return None, "excluded_class:combination"

    excluded = _excluded_class_reason(market, title)
    if excluded is not None:
        return None, excluded

    if _deciding_within_window(
        market,
        market_id=market_id,
        title=title,
        now_dt=now_dt,
        min_hours_to_decision=min_hours_to_decision,
    ):
        return None, "deciding_within_48h"

    mtype = str(market.get("market_type") or "yes_no").strip().lower()
    if mtype not in {"yes_no", "binary", "container_member", "unshaped", ""}:
        return None, f"non_binary_market_type:{mtype}"

    raw_outcomes = market.get("outcomes")
    if not isinstance(raw_outcomes, Sequence) or isinstance(raw_outcomes, (str, bytes)):
        raw_outcomes = market.get("top_outcomes")
    if not isinstance(raw_outcomes, Sequence) or isinstance(raw_outcomes, (str, bytes)):
        return None, "outcomes_missing"
    if len(raw_outcomes) == 0 or len(raw_outcomes) > 2:
        return None, "non_binary_outcomes"

    blocked = withheld_ids or set()
    yes_outcome: Optional[Mapping[str, Any]] = None
    no_outcome: Optional[Mapping[str, Any]] = None
    yes_oid: int = market_id * 10 + 1

    for idx, o in enumerate(raw_outcomes):
        if not isinstance(o, Mapping):
            return None, "invalid_outcome"
        oid_raw = o.get("id")
        oid = (
            int(oid_raw)
            if isinstance(oid_raw, int) and not isinstance(oid_raw, bool) and oid_raw > 0
            else market_id * 10 + idx + 1
        )
        if oid in blocked:
            return None, f"withheld_price_{oid}"
        if leg_is_graded(o.get("is_winner"), o.get("resolution_source")):
            return None, "graded_outcome"
        oname = str(o.get("name") or o.get("label") or "").strip().lower()
        if oname == "yes":
            yes_outcome = o
            yes_oid = oid
        elif oname == "no":
            no_outcome = o
        else:
            return None, f"non_binary_outcome_name:{oname or 'empty'}"

    if yes_outcome is None:
        return None, "missing_yes_outcome"

    prob_raw = (
        yes_outcome.get("probability")
        if "probability" in yes_outcome
        else yes_outcome.get("current_probability")
    )
    if prob_raw is None or isinstance(prob_raw, bool):
        return None, "missing_probability"
    try:
        prob = float(prob_raw)
    except (TypeError, ValueError):
        return None, "missing_probability"
    if not math.isfinite(prob) or prob <= 0.0 or prob >= 1.0:
        return None, "missing_probability"

    pct = _half_up_percent(prob)
    if pct < MIN_YARDSTICK_PERCENT or pct > MAX_YARDSTICK_PERCENT:
        return None, f"outside_probability_band:{pct}"

    no_prob: Optional[float] = None
    if no_outcome is not None:
        np_raw = (
            no_outcome.get("probability")
            if "probability" in no_outcome
            else no_outcome.get("current_probability")
        )
        if np_raw is not None and not isinstance(np_raw, bool):
            try:
                np_val = float(np_raw)
                if math.isfinite(np_val) and 0.0 <= np_val <= 1.0:
                    no_prob = np_val
            except (TypeError, ValueError):
                no_prob = None

    market_observed = _iso_utc(
        market.get("prices_updated_at")
        or market.get("price_observed_at")
        or market.get("updated_at")
    )
    obs = (
        _iso_utc(yes_outcome.get("observed_at") or yes_outcome.get("last_updated"))
        or market_observed
    )
    if not obs:
        return None, "missing_observed_at"

    obs_dt = _parse_dt(obs)
    if obs_dt is None:
        return None, "missing_observed_at"
    age_s = (now_dt.astimezone(timezone.utc) - obs_dt.astimezone(timezone.utc)).total_seconds()
    if age_s > float(max_age_hours) * 3600.0:
        return None, "stale_observation"

    category = _effective_category(market)
    if category == "uncategorized":
        return None, "missing_category"

    short_label, row_label = format_yardstick_labels(
        title,
        is_anchor=is_anchor,
        short_override=short_override,
        row_override=row_override,
    )
    if not short_label or not row_label:
        return None, "empty_label"

    try:
        _validate_narrative_copy(short_label, row_label)
    except ValueError:
        return None, "forbidden_narrative_token"

    source = str(market.get("source") or "polymarket").strip().lower() or "polymarket"
    return (
        _QualifiedYardstickMember(
            market_id=market_id,
            yes_outcome_id=yes_oid,
            source=source,
            category=category,
            short_label=short_label,
            row_label=row_label,
            probability=prob,
            no_probability=no_prob,
            rendered_percent=pct,
            observed_at=obs,
            raw_market=market,
        ),
        None,
    )


def _to_deadline_market_shim(member: _QualifiedYardstickMember) -> _QualifiedDeadlineMarket:
    return _QualifiedDeadlineMarket(
        market_id=member.market_id,
        yes_outcome_id=member.yes_outcome_id,
        source=member.source,
        category=member.category,
        label=member.row_label,
        probability=member.probability,
        no_probability=member.no_probability,
        movement=None,
        observed_at=member.observed_at,
        template_key="",
        claim_key="",
        story_key=None,
        subject_tokens=frozenset(),
        raw_market=member.raw_market,
    )


def select_yardstick_pair(
    markets: Mapping[int, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    anchor_spec: str | int | Mapping[str, Any],
    candidate_specs: Optional[Sequence[str]] = None,
    candidate_labels: Optional[Mapping[str, Mapping[str, str]]] = None,
    same_band_max_diff: int = DEFAULT_SAME_BAND_MAX_DIFF,
    apart_band_min_diff: int = DEFAULT_APART_BAND_MIN_DIFF,
    allow_less_likely: bool = False,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    min_hours_to_decision: float = DEFAULT_MIN_HOURS_TO_DECISION,
    section_title: str = "For scale",
    kicker: str = "FOR SCALE",
    footer: str = "Two unrelated markets with the same chance.",
    less_likely_footer: str = "Two unrelated markets compared for scale.",
    now: Optional[datetime] = None,
    withheld_by_market: Optional[Mapping[int, set[int]]] = None,
) -> Any:
    """Pure selector for ``yardstick_pair`` (§1.4).

    Recomputes the headline sentence from the two live numbers on every call,
    never caching the sentence text. Returns ``RoundupMembers`` when the anchor
    and a cross-category target pass every freshness, 48h decision-window,
    excluded-class, and whole-number band check; otherwise returns
    ``RoundupRefusal``.
    """
    rc = _rc()
    RoundupMembers = rc.RoundupMembers
    RoundupRefusal = rc.RoundupRefusal

    _validate_narrative_copy(section_title, kicker, footer, less_likely_footer)

    effective_now = (
        now.astimezone(timezone.utc)
        if isinstance(now, datetime) and now.tzinfo is not None
        else datetime.now(timezone.utc)
    )

    anchor_ref: str
    anchor_short_override: Optional[str] = None
    anchor_row_override: Optional[str] = None
    anchor_deadline: Optional[date] = None

    if isinstance(anchor_spec, Mapping):
        anchor_ref = str(anchor_spec.get("market") or anchor_spec.get("id") or "").strip()
        anchor_short_override = anchor_spec.get("short_label")
        anchor_row_override = anchor_spec.get("row_label")
        raw_dl = anchor_spec.get("deadline")
        if raw_dl:
            anchor_deadline = _parse_deadline_date(raw_dl)
    else:
        anchor_ref = str(anchor_spec).strip()

    _, anchor_id, _ = parse_market_ref(anchor_ref)
    if anchor_id is None:
        return RoundupRefusal((("anchor", anchor_ref, "invalid_anchor_spec"),))

    by_id: dict[int, Mapping[str, Any]] = {}
    ordered_inputs: list[Mapping[str, Any]] = []
    seq = markets.values() if isinstance(markets, Mapping) else markets
    for m in seq:
        if not isinstance(m, Mapping):
            continue
        mid = m.get("id")
        if isinstance(mid, int) and not isinstance(mid, bool) and mid > 0:
            if int(mid) not in by_id:
                by_id[int(mid)] = m
                ordered_inputs.append(m)

    withheld_map = withheld_by_market or {}
    anchor_raw = by_id.get(anchor_id)
    if anchor_raw is None:
        return RoundupRefusal((("anchor", anchor_id, "anchor_missing"),))

    anchor_member, anchor_err = _qualify_yardstick_member(
        anchor_raw,
        is_anchor=True,
        short_override=anchor_short_override,
        row_override=anchor_row_override,
        anchor_deadline=anchor_deadline,
        max_age_hours=max_age_hours,
        min_hours_to_decision=min_hours_to_decision,
        now_dt=effective_now,
        withheld_ids=withheld_map.get(anchor_id),
    )
    if anchor_member is None:
        return RoundupRefusal((("anchor", anchor_id, str(anchor_err)),))

    priority_ids: list[int] = []
    if candidate_specs is not None:
        for spec in candidate_specs:
            _, cid, _ = parse_market_ref(spec)
            if cid is not None and cid != anchor_id and cid in by_id and cid not in priority_ids:
                priority_ids.append(cid)
        candidate_pool: list[Mapping[str, Any]] = [by_id[cid] for cid in priority_ids]
    else:
        candidate_pool = [
            m for m in ordered_inputs if int(m["id"]) != anchor_id
        ]
    priority_set = set(priority_ids)

    labels_by_id = candidate_labels or {}
    same_matches: list[tuple[int, float, _QualifiedYardstickMember, str, str]] = []
    apart_matches: list[tuple[int, float, _QualifiedYardstickMember, str, str]] = []
    rejections: list[tuple[str, Any, str]] = []

    for order_idx, cand_raw in enumerate(candidate_pool):
        cid = int(cand_raw["id"])
        lbl_cfg = labels_by_id.get(str(cid)) or labels_by_id.get(cid) or {}  # type: ignore[arg-type]
        c_short = lbl_cfg.get("short_label") if isinstance(lbl_cfg, Mapping) else None
        c_row = lbl_cfg.get("row_label") if isinstance(lbl_cfg, Mapping) else None

        cand_member, cand_err = _qualify_yardstick_member(
            cand_raw,
            is_anchor=False,
            short_override=c_short,
            row_override=c_row,
            anchor_deadline=None,
            max_age_hours=max_age_hours,
            min_hours_to_decision=min_hours_to_decision,
            now_dt=effective_now,
            withheld_ids=withheld_map.get(cid),
        )
        if cand_member is None:
            rejections.append(("candidate", cid, str(cand_err)))
            continue

        if cand_member.category == anchor_member.category:
            rejections.append(("candidate", cid, "same_category"))
            continue

        sentence = compute_yardstick_sentence(
            target_short=cand_member.short_label,
            anchor_short=anchor_member.short_label,
            target_pct=cand_member.rendered_percent,
            anchor_pct=anchor_member.rendered_percent,
            same_band_max_diff=same_band_max_diff,
            apart_band_min_diff=apart_band_min_diff,
            allow_less_likely=allow_less_likely,
            same_footer=footer,
            apart_footer=less_likely_footer,
        )
        if sentence is None:
            diff = abs(cand_member.rendered_percent - anchor_member.rendered_percent)
            if 3 <= diff <= 9:
                rejections.append(("candidate", cid, f"band_gap_between_bands:{diff}"))
            else:
                rejections.append(("candidate", cid, f"outside_band:{diff}"))
            continue

        headline, chosen_footer, relation = sentence
        try:
            _validate_narrative_copy(headline, chosen_footer)
        except ValueError:
            rejections.append(("candidate", cid, "forbidden_narrative_token"))
            continue

        is_priority = 0 if cid in priority_set else 1
        prob_diff = abs(cand_member.probability - anchor_member.probability)
        sort_rank = (is_priority, order_idx if is_priority == 0 else 0)
        if relation == "as_likely_as":
            same_matches.append((sort_rank[0] * 1000 + order_idx, prob_diff, cand_member, headline, chosen_footer))
        else:
            apart_matches.append((sort_rank[0] * 1000 + order_idx, prob_diff, cand_member, headline, chosen_footer))

    chosen_tuple: Optional[tuple[int, float, _QualifiedYardstickMember, str, str]] = None
    if same_matches:
        same_matches.sort(key=lambda x: (x[0], x[1], x[2].market_id))
        chosen_tuple = same_matches[0]
    elif apart_matches:
        apart_matches.sort(key=lambda x: (x[0], -x[1], x[2].market_id))
        chosen_tuple = apart_matches[0]

    if chosen_tuple is None:
        return RoundupRefusal([("pair", "no_qualifying_target"), *rejections])

    _, _, target_member, computed_headline, computed_footer = chosen_tuple

    rows = [
        {
            "market_id": target_member.market_id,
            "label": target_member.row_label,
            "probability": target_member.probability,
            "rendered_percent": target_member.rendered_percent,
            "observed_at": target_member.observed_at,
        },
        {
            "market_id": anchor_member.market_id,
            "label": anchor_member.row_label,
            "probability": anchor_member.probability,
            "rendered_percent": anchor_member.rendered_percent,
            "observed_at": anchor_member.observed_at,
        },
    ]

    members = [
        {
            "type": MEMBER_MARKET,
            "id": target_member.market_id,
            "destination": market_destination(target_member.market_id),
            "card": _build_binary_member_card(_to_deadline_market_shim(target_member)),
            "event_id": None,
        },
        {
            "type": MEMBER_MARKET,
            "id": anchor_member.market_id,
            "destination": market_destination(anchor_member.market_id),
            "card": _build_binary_member_card(_to_deadline_market_shim(anchor_member)),
            "event_id": None,
        },
    ]

    sec_title = str(section_title or "For scale").strip() or "For scale"
    sections = [
        {
            "class": "title",
            "title": sec_title,
            "layout": "field",
            "count": 2,
            "members": members,
        }
    ]
    revision_ids = [target_member.market_id, anchor_member.market_id]

    return RoundupMembers(
        members=members,
        rows=rows,
        footer=computed_footer,
        title=computed_headline,
        kicker=str(kicker or "FOR SCALE").strip() or "FOR SCALE",
        sections=sections,
        revision_ids=revision_ids,
    )


async def _load_markets_from_db(
    db: Any,
    target_ids: Sequence[int],
) -> tuple[dict[int, dict[str, Any]], dict[int, set[int]]]:
    """Load the explicit anchor and curated ``target_ids`` from ``db``."""
    if isinstance(db, (list, tuple)):
        mapped_seq: dict[int, dict[str, Any]] = {}
        for item in db:
            conv = _orm_market_to_dict(item)
            if conv is not None:
                mapped_seq[int(conv["id"])] = conv
        return mapped_seq, {}

    if not hasattr(db, "execute") or not callable(db.execute):
        return {}, {}

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import joinedload

    from app.models import FuturesMarket
    from app.routes.futures import withheld_price_outcome_ids_for_markets

    clean_ids = [
        int(mid)
        for mid in target_ids
        if isinstance(mid, int) and not isinstance(mid, bool) and mid > 0
    ]
    if not clean_ids:
        return {}, {}

    res = await db.execute(
        select(FuturesMarket)
        .options(
            joinedload(FuturesMarket.sport),
            joinedload(FuturesMarket.outcomes),
        )
        .where(FuturesMarket.id.in_(clean_ids))
    )
    orm_rows: list[Any] = []
    if hasattr(res, "scalars") and callable(res.scalars):
        scalars_obj = res.scalars()
        if hasattr(scalars_obj, "unique") and callable(scalars_obj.unique):
            scalars_obj = scalars_obj.unique()
        orm_rows.extend(list(scalars_obj.all()))
    elif hasattr(res, "all") and callable(res.all):
        orm_rows.extend(list(res.all()))

    if not orm_rows:
        return {}, {}

    withheld: dict[int, set[int]] = {}
    if isinstance(db, AsyncSession):
        withheld = await withheld_price_outcome_ids_for_markets(db, orm_rows)

    mapped: dict[int, dict[str, Any]] = {}
    for m in orm_rows:
        conv = _orm_market_to_dict(m)
        if conv is not None:
            mapped[int(conv["id"])] = conv
    return mapped, withheld


async def produce_yardstick_pair(
    db: Any,
    *,
    definition: Mapping[str, Any],
    load_markets: Optional[
        Callable[
            [Any, Sequence[int]],
            Awaitable[tuple[Mapping[int, Mapping[str, Any]], Mapping[int, set[int]]]]
            | tuple[Mapping[int, Mapping[str, Any]], Mapping[int, set[int]]],
        ]
    ] = None,
    now: Optional[datetime] = None,
) -> Any:
    """Evaluate a stored ``yardstick_pair`` container definition against ``db``."""
    rule = definition.get("rule")
    if not isinstance(rule, Mapping):
        raise ValueError(f"Definition {definition.get('slug')!r} is missing 'rule'")

    anchor_cfg = rule.get("anchor")
    if not anchor_cfg:
        raise ValueError(
            f"Definition {definition.get('slug')!r} is missing 'rule.anchor'"
        )

    anchor_ref = (
        str(anchor_cfg.get("market") or anchor_cfg.get("id") or "")
        if isinstance(anchor_cfg, Mapping)
        else str(anchor_cfg)
    )
    _, anchor_id, _ = parse_market_ref(anchor_ref)
    candidate_specs = [
        str(c) for c in (rule.get("candidates") or ()) if str(c).strip()
    ]
    target_ids: list[int] = []
    if anchor_id is not None:
        target_ids.append(anchor_id)
    for spec in candidate_specs:
        _, cid, _ = parse_market_ref(spec)
        if cid is not None and cid not in target_ids:
            target_ids.append(cid)

    if load_markets is not None:
        loaded = load_markets(db, target_ids)
    else:
        loaded = _load_markets_from_db(db, target_ids)
    if inspect.isawaitable(loaded):
        loaded = await loaded
    markets_map, withheld_map = loaded

    return select_yardstick_pair(
        markets_map,
        anchor_spec=anchor_cfg,
        candidate_specs=candidate_specs,
        candidate_labels=rule.get("candidate_labels"),
        same_band_max_diff=int(rule.get("same_band_max_diff", DEFAULT_SAME_BAND_MAX_DIFF)),
        apart_band_min_diff=int(rule.get("apart_band_min_diff", DEFAULT_APART_BAND_MIN_DIFF)),
        allow_less_likely=bool(rule.get("allow_less_likely", False)),
        max_age_hours=float(rule.get("max_age_hours", DEFAULT_MAX_AGE_HOURS)),
        min_hours_to_decision=float(
            rule.get("min_hours_to_decision", DEFAULT_MIN_HOURS_TO_DECISION)
        ),
        section_title=str(definition.get("section_title") or "For scale"),
        kicker=str(definition.get("kicker") or "FOR SCALE"),
        footer=str(
            definition.get("footer")
            or "Two unrelated markets with the same chance."
        ),
        less_likely_footer=str(
            definition.get("less_likely_footer")
            or "Two unrelated markets compared for scale."
        ),
        now=now,
        withheld_by_market=withheld_map,
    )


def load_yardstick_pair_definition(path: Path | str) -> dict[str, Any]:
    """Load and validate a stored JSON container definition for ``yardstick_pair``."""
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
        raw.get("kicker"),
    )
    return raw


def build_yardstick_pair_producer(
    definition: Mapping[str, Any],
    *,
    enabled: Optional[Callable[[], bool]] = None,
    load_markets: Optional[
        Callable[
            [Any, Sequence[int]],
            Awaitable[tuple[Mapping[int, Mapping[str, Any]], Mapping[int, set[int]]]]
            | tuple[Mapping[int, Mapping[str, Any]], Mapping[int, set[int]]],
        ]
    ] = None,
    now: Optional[datetime] = None,
) -> Any:
    """Build a ``RoundupProducer`` from a stored ``yardstick_pair`` definition."""
    RoundupProducer = _rc().RoundupProducer

    rule = definition.get("rule")
    if (
        not isinstance(rule, Mapping)
        or rule.get("producer") != PRODUCER_KIND_YARDSTICK_PAIR
    ):
        raise ValueError(
            f"Expected rule.producer == {PRODUCER_KIND_YARDSTICK_PAIR!r}, got {rule!r}"
        )

    slug = str(definition["slug"])
    name = str(definition["name"])
    footer = str(definition["footer"])
    section_title = definition["section_title"]
    kicker = str(definition.get("kicker") or "FOR SCALE")
    raw_tag = definition.get("tag")
    tag = "" if raw_tag is None else str(raw_tag)
    _validate_narrative_copy(name, footer, section_title, kicker, tag)

    async def _produce(db: Any) -> Any:
        return await produce_yardstick_pair(
            db,
            definition=definition,
            load_markets=load_markets,
            now=now,
        )

    rule_dict = dict(rule)
    rule_dict["cache"] = "none"

    return RoundupProducer(
        slug=slug,
        name=name,
        kind=str(definition.get("kind") or "roundup"),
        category=str(definition["category"]),
        section_title=section_title,
        footer=footer,
        produce=_produce,
        membership=str(definition.get("membership") or "computed-produced"),
        rule=rule_dict,
        tag=tag,
        kicker=kicker,
        story_key=f"roundup:{slug.removeprefix('roundup-')}",
        enabled=enabled,
    )


FOR_SCALE_SNOW_IN_DC_DEFINITION: dict[str, Any] = load_yardstick_pair_definition(
    FOR_SCALE_SNOW_IN_DC_DEFINITION_PATH
)
FOR_SCALE_SNOW_IN_DC_PRODUCER: Any = build_yardstick_pair_producer(
    FOR_SCALE_SNOW_IN_DC_DEFINITION,
    enabled=for_scale_snow_in_dc_enabled,
)
_rc().register_roundup_producer(FOR_SCALE_SNOW_IN_DC_PRODUCER)

FOR_SCALE_SNOW_IN_BUFFALO_DEFINITION: dict[str, Any] = load_yardstick_pair_definition(
    FOR_SCALE_SNOW_IN_BUFFALO_DEFINITION_PATH
)
FOR_SCALE_SNOW_IN_BUFFALO_PRODUCER: Any = build_yardstick_pair_producer(
    FOR_SCALE_SNOW_IN_BUFFALO_DEFINITION,
    enabled=for_scale_snow_in_buffalo_enabled,
)
_rc().register_roundup_producer(FOR_SCALE_SNOW_IN_BUFFALO_PRODUCER)

FOR_SCALE_US_RECESSION_2026_DEFINITION: dict[str, Any] = load_yardstick_pair_definition(
    FOR_SCALE_US_RECESSION_2026_DEFINITION_PATH
)
FOR_SCALE_US_RECESSION_2026_PRODUCER: Any = build_yardstick_pair_producer(
    FOR_SCALE_US_RECESSION_2026_DEFINITION,
    enabled=for_scale_us_recession_2026_enabled,
)
_rc().register_roundup_producer(FOR_SCALE_US_RECESSION_2026_PRODUCER)


async def for_scale_snow_in_dc(
    db: Any,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Evaluate ``FOR_SCALE_SNOW_IN_DC_PRODUCER`` and return ``(feed_item, container_payload)``."""
    return await _rc().evaluate_roundup_producer(FOR_SCALE_SNOW_IN_DC_PRODUCER, db)


async def for_scale_snow_in_buffalo(
    db: Any,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Evaluate ``FOR_SCALE_SNOW_IN_BUFFALO_PRODUCER`` and return ``(feed_item, container_payload)``."""
    return await _rc().evaluate_roundup_producer(FOR_SCALE_SNOW_IN_BUFFALO_PRODUCER, db)


async def for_scale_us_recession_2026(
    db: Any,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Evaluate ``FOR_SCALE_US_RECESSION_2026_PRODUCER`` and return ``(feed_item, container_payload)``."""
    return await _rc().evaluate_roundup_producer(FOR_SCALE_US_RECESSION_2026_PRODUCER, db)
