"""Movement-led cumulative deadline-family story verification and bundle assembly (#9878 / #11040).

Slice 1 scope:
- Verifies a single-provider cumulative deadline family from authoritative identity,
  condition/outcome IDs, subject/predicate stem, and timezone-aware deadline instants.
- Preserves the existing stored-claim gate (`probability_change_24h`) AND requires a
  correctly outcome-bound `dated_movement_basis` entry inside the 12h–24h window.
- Binds every probability, movement, bar, and label to the exact `Yes` outcome ID,
  even when `No` is the leading outcome (`rank=1`), without complementing `No` or
  inverting a movement sign.
- Enforces authoritative settlement/currentness over lagging local `status="open"` rows,
  and applies the local Q8 97%+ open-mover exception only while its supporting dated
  movement evidence is valid and in-window.
- Selects the open deadline with the largest eligible supported dated move (`>= 2` pts),
  falling back to the open priced deadline nearest 50% with a deterministic tie-break
  (closest to 50% -> earliest `deadline_instant` -> lowest `market_id`).
- Orders sibling deadlines in ascending `deadline_instant` order for in-place expansion
  while keeping represented member counts distinct from provider inventory completeness.
"""

from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.utils.futures_market_snapshot import (
    DATED_BASIS_MIN_AGE_HOURS,
    DATED_BASIS_WINDOW_HOURS,
    dated_basis_admits_zero,
    dated_movement_basis,
    outcome_observed_at,
    outcome_prints_a_price,
    read_dated_basis_entry,
)

DEADLINE_FAMILY_STORY_PREFIX = "story:deadline_family:"

#: Q7: The new deadline-family story hero chip has a 5-percentage-point threshold
#: (0.05 fraction). Global `HERO_MIN_MOVEMENT_POINTS` (10) and `MovementBadge` (2)
#: remain unchanged.
DEADLINE_HERO_MIN_MOVEMENT_POINTS = 5.0
DEADLINE_HERO_MIN_MOVEMENT_FRACTION = 0.05

#: Minimum supported dated move (2 percentage points, 0.02 fraction) to count as
#: an eligible movement lead under Q1 or a moderate movement claim under 6E.
DEADLINE_MODERATE_MIN_MOVEMENT_POINTS = 2.0
DEADLINE_MODERATE_MIN_MOVEMENT_FRACTION = 0.02

#: Near-certainty threshold for Q8 local exception checks.
NEAR_CERTAIN_THRESHOLD = 0.97

#: Deterministic tie-break rule identifier documented in payload and contract.
DETERMINISTIC_TIE_BREAK_RULE = (
    "abs_supported_move_desc -> distance_from_50pct_asc -> deadline_instant_asc -> market_id_asc"
)

_SETTLED_STATUSES = frozenset({"resolved", "closed", "settled", "finalized", "final"})

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

_SHORT_MONTH_NAMES: dict[int, str] = {
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

_MONTH_PATTERN = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)

#: Cumulative deadline question pattern: `<stem> by <Month> <day>[, <year>]?`
_CUMULATIVE_DEADLINE_QUESTION_RE = re.compile(
    r"^\s*(?P<stem>.+?)\s+\b(?P<prep>by)\s+(?P<deadline>[^?]+?)\s*\??\s*$",
    re.IGNORECASE,
)

#: Exact calendar date inside the deadline slot: `<Month> <day>[, <year>]`
_CALENDAR_DATE_DEADLINE_RE = re.compile(
    rf"^(?P<month>{_MONTH_PATTERN})\.?\s+(?P<day>\d{{1,2}})(?:\s*,\s*(?P<year>\d{{4}})|\s+(?P<year_plain>\d{{4}}))?$",
    re.IGNORECASE,
)

#: Exclusive date-bucket phrases that must never be admitted as cumulative deadlines (6B).
_EXCLUSIVE_BUCKET_RE = re.compile(
    r"\b(?:between\s+.+\s+and|from\s+.+\s+to|in\s+(?:"
    + _MONTH_PATTERN
    + r")|during\s+|q[1-4]\b|quarter\b|only\b|or\s+later\b|or\s+earlier\b|after\s+)\b",
    re.IGNORECASE,
)

#: Negative or inverted predicate markers that violate affirmative `Yes` binding (6B / 6C).
_NEGATIVE_STEM_RE = re.compile(
    r"\b(?:not|won't|will\s+not|cannot|can't|never|fail(?:s)?\s+to|stay(?:s)?\s+in|remain(?:s)?\s+(?:in|as))\b",
    re.IGNORECASE,
)

#: Mention-only speech/word markets that must not be grouped as event deadline stories (6B).
_MENTION_ONLY_STEM_RE = re.compile(
    r"\b(?:say|says|said|mention|mentions|mentioned|tweet|tweets|post|posts|utter|use\s+the\s+word)\b",
    re.IGNORECASE,
)

_LEADING_AUXILIARY_RE = re.compile(r"^(?:will|does|do|is|are|has|have)\s+", re.IGNORECASE)


def is_deadline_family_story_key(story_key: str | None) -> bool:
    """True when `story_key` names a verified cumulative deadline-family bundle."""
    if not story_key or not isinstance(story_key, str):
        return False
    return story_key.startswith(DEADLINE_FAMILY_STORY_PREFIX)


def deadline_family_story_key(source: str, group_id: str) -> str:
    """Canonical story key for a verified single-provider deadline family."""
    clean_source = str(source or "").strip().lower()
    clean_group = str(group_id or "").strip()
    if clean_group.lower().startswith(f"{clean_source}:"):
        return f"{DEADLINE_FAMILY_STORY_PREFIX}{clean_group}"
    return f"{DEADLINE_FAMILY_STORY_PREFIX}{clean_source}:{clean_group}"


def parse_timezone_aware_instant(value: Any) -> datetime | None:
    """Parse an ISO timestamp or datetime, requiring an explicit timezone offset.

    Timezone-naive values are rejected (`None`) rather than guessed as UTC or
    local time (Section 6B / Section 8 Case 15).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            return None
        return value.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        return None
    return parsed.astimezone(timezone.utc)


def _normalize_stem(stem: str) -> tuple[str, str]:
    """Return `(normalized_stem_key, display_stem)` for a question stem."""
    collapsed = re.sub(r"\s+", " ", stem.strip()).rstrip("?.,:; ")
    without_aux = _LEADING_AUXILIARY_RE.sub("", collapsed).strip()
    if not without_aux:
        return "", ""
    display = without_aux[:1].upper() + without_aux[1:]
    norm = re.sub(r"[^\w\s]", " ", without_aux.lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm, display


def parse_cumulative_deadline_question(
    name: str | None,
    resolution_date: Any,
) -> dict[str, Any] | None:
    """Verify and parse a cumulative deadline question and its deadline instant.

    Rejects:
    - Non-deadline questions or exclusive date buckets ("in October", "between ...", etc.)
    - Negative/inverted predicates ("not out", "stays in", "will not", etc.)
    - Mention-only markets ("Will X say/mention ...")
    - Vague/ambiguous deadlines ("by end of term", "by 2026", "by next month")
    - Missing or timezone-naive `resolution_date`
    - `resolution_date` instants that do not correspond to the stated calendar deadline.
    """
    if not name or not isinstance(name, str):
        return None
    cleaned_name = name.strip()
    if not cleaned_name or _EXCLUSIVE_BUCKET_RE.search(cleaned_name):
        return None

    match = _CUMULATIVE_DEADLINE_QUESTION_RE.match(cleaned_name)
    if match is None:
        return None

    raw_stem = match.group("stem").strip()
    prep = match.group("prep").strip().lower()
    raw_deadline = match.group("deadline").strip()

    if not raw_stem or not raw_deadline:
        return None
    if _EXCLUSIVE_BUCKET_RE.search(raw_deadline) or _EXCLUSIVE_BUCKET_RE.search(raw_stem):
        return None
    if _NEGATIVE_STEM_RE.search(raw_stem) or _NEGATIVE_STEM_RE.search(raw_deadline):
        return None
    if _MENTION_ONLY_STEM_RE.search(raw_stem):
        return None

    date_match = _CALENDAR_DATE_DEADLINE_RE.match(raw_deadline)
    if date_match is None:
        return None

    month_token = date_match.group("month").rstrip(".").lower()
    month_num = _MONTH_NUMBERS.get(month_token)
    if month_num is None:
        return None
    try:
        day_num = int(date_match.group("day"))
    except (TypeError, ValueError):
        return None

    explicit_year_str = date_match.group("year") or date_match.group("year_plain")
    explicit_year = int(explicit_year_str) if explicit_year_str else None

    deadline_instant = parse_timezone_aware_instant(resolution_date)
    if deadline_instant is None:
        return None

    candidate_years = (
        [explicit_year]
        if explicit_year is not None
        else [deadline_instant.year, deadline_instant.year - 1, deadline_instant.year + 1]
    )

    matched_year: int | None = None
    for year in candidate_years:
        if year is None or year < 2000 or year > 2100:
            continue
        max_day = calendar.monthrange(year, month_num)[1]
        if not (1 <= day_num <= max_day):
            continue
        day_start_utc = datetime(year, month_num, day_num, 0, 0, 0, tzinfo=timezone.utc)
        day_end_utc = datetime(year, month_num, day_num, 23, 59, 59, tzinfo=timezone.utc)
        # Allow [-14h, +36h] around the UTC calendar day so US/Pacific end-of-day
        # (`2027-01-01T04:59:00+00:00` for Dec 31 23:59 EST, or `+07:59Z` PST)
        # and UTC+14 closes both align with the named calendar date while any
        # different date (even 2+ days away) is rejected.
        if (day_start_utc - timedelta(hours=14)) <= deadline_instant <= (
            day_end_utc + timedelta(hours=36)
        ):
            matched_year = year
            break

    if matched_year is None:
        return None

    stem_key, display_stem = _normalize_stem(raw_stem)
    if not stem_key or len(stem_key.split()) < 2:
        return None

    short_month = _SHORT_MONTH_NAMES[month_num]
    short_deadline = (
        f"{short_month} {day_num}, {explicit_year}"
        if explicit_year is not None
        else f"{short_month} {day_num}"
    )
    deadline_label = f"By {short_deadline}"
    calendar_date = f"{matched_year:04d}-{month_num:02d}-{day_num:02d}"

    return {
        "stem_key": stem_key,
        "display_stem": display_stem,
        "shared_question": f"{display_stem} by…?",
        "preposition": prep,
        "deadline_text": raw_deadline,
        "short_deadline": short_deadline,
        "deadline_label": deadline_label,
        "calendar_date": calendar_date,
        "deadline_instant": deadline_instant.isoformat(),
        "deadline_epoch": deadline_instant.timestamp(),
    }


def _normalize_yes_no_result(raw_winner: Any) -> str | None:
    if raw_winner is None:
        return None
    text = str(raw_winner).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"yes", "true", "1"}:
        return "Yes"
    if lowered in {"no", "false", "0"}:
        return "No"
    if lowered.startswith(("no:", "not ")):
        return "No"
    return text


def extract_settlement_evidence(
    *,
    status: Any,
    resolved: Any = None,
    winner: Any = None,
    market_metadata: Any = None,
    outcomes: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Determine authoritative settlement status for a deadline-family member (6D).

    Authoritative terminal evidence from the venue (`market_metadata`), outcome
    winner flags (`is_winner`), or market status/winner always wins over a
    lagging local `status="open"` with `winner=None`. Extreme prices (`0%`,
    `97%`, `100%`) never establish settlement on their own.
    """
    local_status = str(status or "open").strip().lower()
    local_settled = (
        local_status in _SETTLED_STATUSES
        or resolved is True
        or bool(str(winner or "").strip())
    )
    local_result = _normalize_yes_no_result(winner)

    outcome_winner_name: str | None = None
    for outcome in outcomes or ():
        is_win = (
            outcome.get("is_winner")
            if isinstance(outcome, Mapping)
            else getattr(outcome, "__dict__", {}).get("is_winner")
        )
        if is_win is True:
            raw_name = (
                outcome.get("name")
                if isinstance(outcome, Mapping)
                else getattr(outcome, "__dict__", {}).get("name")
            )
            outcome_winner_name = _normalize_yes_no_result(raw_name)
            break

    meta = market_metadata if isinstance(market_metadata, Mapping) else {}
    venue_closed = meta.get("closed") is True or meta.get("is_closed") is True
    venue_resolved = (
        meta.get("resolved") is True
        or meta.get("is_resolved") is True
        or str(meta.get("umaResolutionStatus") or "").strip().lower() in _SETTLED_STATUSES
        or str(meta.get("venue_status") or "").strip().lower() in _SETTLED_STATUSES
        or str(meta.get("resolution_status") or "").strip().lower() in _SETTLED_STATUSES
    )
    venue_winner = _normalize_yes_no_result(
        meta.get("winning_outcome")
        or meta.get("winner")
        or meta.get("resolved_outcome")
        or meta.get("uma_resolved_outcome")
    )

    is_settled = bool(
        local_settled
        or outcome_winner_name is not None
        or venue_resolved
        or (venue_closed and venue_winner is not None)
    )
    result = venue_winner or outcome_winner_name or local_result

    if venue_resolved or (venue_closed and venue_winner is not None) or venue_winner is not None:
        source = "venue_metadata"
    elif outcome_winner_name is not None:
        source = "outcome_winner"
    elif local_settled:
        source = "market_status"
    else:
        source = None

    lagging_local_status = bool(
        is_settled and local_status == "open" and not local_result and resolved is not True
    )

    return {
        "is_settled": is_settled,
        "status": "resolved" if is_settled else local_status,
        "winner": result,
        "result": result,
        "authoritative_source": source,
        "lagging_local_status": lagging_local_status,
    }


def format_movement_timeframe(
    basis_observed_at: Any,
    reference_at: Any,
    *,
    tz_name: str | None = None,
) -> dict[str, Any]:
    """Compute truthful movement comparison wording under Direct User Decision Q4.

    - Uses `"since yesterday"` ONLY when `basis_observed_at` and `reference_at`
      genuinely cross from the previous calendar day (`calendar_day_diff == 1`)
      in the target timezone.
    - When both timestamps fall on the same local calendar day (`calendar_day_diff == 0`),
      even if 12–24 hours apart, uses truthful same-day time wording
      (`"today since <time>"` / `"since <time>"`), never `"since yesterday"`.
    """
    basis_dt = parse_timezone_aware_instant(basis_observed_at)
    ref_dt = parse_timezone_aware_instant(reference_at)
    if basis_dt is None or ref_dt is None:
        return {
            "valid": False,
            "calendar_day_diff": None,
            "crosses_previous_calendar_day": False,
            "chip_timeframe": None,
            "sentence_timeframe": None,
            "timezone": tz_name or "UTC",
        }

    tz: Any = timezone.utc
    effective_tz_name = "UTC"
    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
            effective_tz_name = tz_name
        except ZoneInfoNotFoundError:
            tz = timezone.utc
            effective_tz_name = "UTC"

    local_basis = basis_dt.astimezone(tz)
    local_ref = ref_dt.astimezone(tz)
    day_diff = (local_ref.date() - local_basis.date()).days
    if day_diff < 0:
        return {
            "valid": False,
            "calendar_day_diff": day_diff,
            "crosses_previous_calendar_day": False,
            "chip_timeframe": None,
            "sentence_timeframe": None,
            "timezone": effective_tz_name,
        }

    if day_diff == 1:
        return {
            "valid": True,
            "calendar_day_diff": 1,
            "crosses_previous_calendar_day": True,
            "chip_timeframe": "since yesterday",
            "sentence_timeframe": "since yesterday",
            "timezone": effective_tz_name,
        }

    if day_diff == 0:
        hour_12 = local_basis.hour % 12 or 12
        am_pm = "AM" if local_basis.hour < 12 else "PM"
        time_label = f"{hour_12}:{local_basis.minute:02d} {am_pm}"
        return {
            "valid": True,
            "calendar_day_diff": 0,
            "crosses_previous_calendar_day": False,
            "chip_timeframe": f"since {time_label}",
            "sentence_timeframe": f"today since {time_label}",
            "timezone": effective_tz_name,
        }

    month_label = _SHORT_MONTH_NAMES[local_basis.month]
    date_label = f"{month_label} {local_basis.day}"
    return {
        "valid": True,
        "calendar_day_diff": day_diff,
        "crosses_previous_calendar_day": False,
        "chip_timeframe": f"since {date_label}",
        "sentence_timeframe": f"since {date_label}",
        "timezone": effective_tz_name,
    }


def _outcome_field(outcome: Any, key: str) -> Any:
    if isinstance(outcome, Mapping):
        return outcome.get(key)
    try:
        return outcome.__dict__.get(key)
    except AttributeError:
        return getattr(outcome, key, None)


def _extract_binary_yes_no_outcomes(
    outcomes: Sequence[Any] | None,
) -> tuple[Any, Any] | None:
    """Return `(yes_outcome, no_outcome)` when `outcomes` is an exact Yes/No pair."""
    if not outcomes or len(outcomes) != 2:
        return None
    by_name: dict[str, Any] = {}
    for outcome in outcomes:
        raw_name = _outcome_field(outcome, "name")
        if not raw_name or not isinstance(raw_name, str):
            return None
        lowered = raw_name.strip().lower()
        if lowered not in {"yes", "no"} or lowered in by_name:
            return None
        by_name[lowered] = outcome
    if set(by_name.keys()) != {"yes", "no"}:
        return None
    yes_outcome = by_name["yes"]
    no_outcome = by_name["no"]
    yes_id = _outcome_field(yes_outcome, "id")
    no_id = _outcome_field(no_outcome, "id")
    if yes_id is None or no_id is None or isinstance(yes_id, bool) or isinstance(no_id, bool):
        return None
    try:
        if int(yes_id) == int(no_id):
            return None
    except (TypeError, ValueError):
        return None
    yes_ext = _outcome_field(yes_outcome, "external_id")
    no_ext = _outcome_field(no_outcome, "external_id")
    if yes_ext is not None and no_ext is not None:
        if not str(yes_ext).strip() or not str(no_ext).strip():
            return None
        if str(yes_ext).strip() == str(no_ext).strip():
            return None
    return yes_outcome, no_outcome


def _readable_probability(
    outcome: Any,
    withheld_ids: frozenset[int] | set[int] | Sequence[int] | None = None,
) -> float | None:
    outcome_id = _outcome_field(outcome, "id")
    if withheld_ids and outcome_id is not None and int(outcome_id) in set(withheld_ids):
        return None
    if isinstance(outcome, Mapping):
        raw_prob = (
            outcome.get("current_probability")
            if "current_probability" in outcome
            else outcome.get("probability")
        )
        if raw_prob is None:
            return None
        try:
            val = float(raw_prob)
        except (TypeError, ValueError):
            return None
    else:
        if not outcome_prints_a_price(outcome):
            return None
        try:
            val = float(_outcome_field(outcome, "current_probability"))
        except (TypeError, ValueError):
            return None
    if not (0.0 <= val <= 1.0):
        return None
    return val


def build_deadline_member_contract(
    *,
    market_id: Any,
    name: str | None,
    source: str | None,
    external_id: str | None,
    group_id: str | None,
    group_type: str | None = None,
    market_type: str | None = None,
    status: str | None = "open",
    resolved: Any = None,
    winner: Any = None,
    resolution_date: Any = None,
    market_metadata: Any = None,
    outcomes: Sequence[Any] | None = None,
    top_outcomes_data: Sequence[Mapping[str, Any]] | None = None,
    price_observed_at: str | None = None,
    withheld_outcome_ids: Sequence[int] | set[int] | frozenset[int] | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Build the verified producer contract for a single deadline-family member.

    Returns `None` when the market is not a cumulative deadline-family candidate
    or lacks required condition/outcome/deadline identity.
    """
    if market_id is None or isinstance(market_id, bool):
        return None
    try:
        clean_market_id = int(market_id)
    except (TypeError, ValueError):
        return None

    clean_source = str(source or "").strip().lower()
    clean_group_id = str(group_id or "").strip()
    clean_external_id = str(external_id or "").strip()
    if not clean_source or not clean_group_id or not clean_external_id:
        return None

    parsed_q = parse_cumulative_deadline_question(name, resolution_date)
    if parsed_q is None:
        return None

    pair = _extract_binary_yes_no_outcomes(outcomes)
    if pair is None:
        return None
    yes_outcome, no_outcome = pair

    yes_outcome_id = int(_outcome_field(yes_outcome, "id"))
    no_outcome_id = int(_outcome_field(no_outcome, "id"))
    yes_external_id = _outcome_field(yes_outcome, "external_id")
    no_external_id = _outcome_field(no_outcome, "external_id")

    yes_probability = _readable_probability(yes_outcome, withheld_outcome_ids)
    no_probability = _readable_probability(no_outcome, withheld_outcome_ids)

    yes_rendered_percent: int | None = None
    if top_outcomes_data:
        for row in top_outcomes_data:
            if isinstance(row, Mapping) and row.get("id") == yes_outcome_id:
                rp = row.get("rendered_percent")
                if isinstance(rp, int) and not isinstance(rp, bool):
                    yes_rendered_percent = rp
                break
    if yes_rendered_percent is None and yes_probability is not None:
        yes_rendered_percent = round(yes_probability * 100)

    raw_stored_change = _outcome_field(yes_outcome, "probability_change_24h")
    stored_change: float | None = None
    if raw_stored_change is not None and not isinstance(raw_stored_change, bool):
        try:
            stored_change = float(raw_stored_change)
        except (TypeError, ValueError):
            stored_change = None

    settlement = extract_settlement_evidence(
        status=status,
        resolved=resolved,
        winner=winner,
        market_metadata=market_metadata,
        outcomes=outcomes,
    )

    meta_dict = market_metadata if isinstance(market_metadata, Mapping) else {}
    dummy_carrier = type("_Carrier", (), {})()
    dummy_carrier.__dict__["market_metadata"] = meta_dict
    dummy_carrier.__dict__["source"] = clean_source

    bank = dated_movement_basis(dummy_carrier)
    admits_zero = dated_basis_admits_zero(dummy_carrier)
    basis_price, basis_observed_at = read_dated_basis_entry(
        bank.get(str(yes_outcome_id))
    )

    reference_dt = parse_timezone_aware_instant(now) or datetime.now(timezone.utc)
    basis_age_hours: float | None = None
    basis_in_window = False
    if basis_observed_at is not None:
        basis_age_hours = (reference_dt - basis_observed_at).total_seconds() / 3600.0
        basis_in_window = (
            DATED_BASIS_MIN_AGE_HOURS <= basis_age_hours <= DATED_BASIS_WINDOW_HOURS
        )

    # Evaluate movement status strictly under 6A / 6C / 6D / 6E:
    # - Authoritative settlement suppresses live movement claims.
    # - Stored claim (`probability_change_24h` on `Yes`) is mandatory.
    # - Dated basis bound to `str(yes_outcome_id)` inside 12h..24h is mandatory.
    supported_move: float | None = None
    supported_move_points: float | None = None
    if settlement["is_settled"]:
        movement_status = "settled_suppressed"
    elif yes_probability is None:
        movement_status = "unpriced"
    elif stored_change is None:
        movement_status = "no_stored_claim"
    elif stored_change == 0.0 and not admits_zero:
        movement_status = "zero_stored_claim_refused"
    elif basis_price is None or basis_observed_at is None:
        movement_status = "missing_or_invalid_basis"
    elif not basis_in_window:
        movement_status = "basis_out_of_window"
    else:
        raw_move = yes_probability - basis_price
        supported_move = round(raw_move, 6)
        supported_move_points = round(raw_move * 100.0, 2)
        if abs(raw_move) < 1e-9:
            movement_status = "measured_zero"
        elif abs(raw_move) < DEADLINE_MODERATE_MIN_MOVEMENT_FRACTION:
            movement_status = "sub_threshold"
        elif abs(raw_move) < DEADLINE_HERO_MIN_MOVEMENT_FRACTION:
            movement_status = "moderate"
        else:
            movement_status = "hero"

    yes_observed_dt = (
        outcome_observed_at(yes_outcome) if not isinstance(yes_outcome, Mapping) else None
    )
    effective_price_observed_at = (
        yes_observed_dt.isoformat()
        if yes_observed_dt is not None
        else price_observed_at
    )

    timeframe_utc = (
        format_movement_timeframe(
            basis_observed_at.isoformat() if basis_observed_at else None,
            effective_price_observed_at or reference_dt.isoformat(),
            tz_name="UTC",
        )
        if supported_move is not None and basis_observed_at is not None
        else None
    )

    # Q8 check: a genuinely open question at 97%+ remains eligible locally in
    # this deadline family ONLY when it has a qualifying recent dated move
    # (`moderate` or `hero`, i.e. >= 2 pts with valid in-window dated basis and
    # stored claim) and is not settled or past its deadline instant.
    probs_for_extreme = [p for p in (yes_probability, no_probability) if p is not None]
    max_side_prob = max(probs_for_extreme) if probs_for_extreme else None
    is_near_certain = bool(
        max_side_prob is not None
        and (
            max_side_prob >= NEAR_CERTAIN_THRESHOLD
            or (yes_probability is not None and yes_probability <= (1.0 - NEAR_CERTAIN_THRESHOLD))
        )
    )
    deadline_dt = parse_timezone_aware_instant(parsed_q["deadline_instant"])
    deadline_in_future = bool(deadline_dt is not None and deadline_dt > reference_dt)
    near_certain_open_eligible = bool(
        not settlement["is_settled"]
        and deadline_in_future
        and is_near_certain
        and movement_status in {"moderate", "hero"}
        and supported_move is not None
        and abs(supported_move) >= DEADLINE_MODERATE_MIN_MOVEMENT_FRACTION
    )

    raw_market_count = meta_dict.get("market_count")
    provider_market_count: int | None = None
    if isinstance(raw_market_count, int) and not isinstance(raw_market_count, bool) and raw_market_count > 0:
        provider_market_count = raw_market_count

    return {
        "market_id": clean_market_id,
        "name": str(name).strip(),
        "source": clean_source,
        "external_id": clean_external_id,
        "group_id": clean_group_id,
        "group_type": group_type,
        "market_type": market_type,
        "stem_key": parsed_q["stem_key"],
        "display_stem": parsed_q["display_stem"],
        "shared_question": parsed_q["shared_question"],
        "preposition": parsed_q["preposition"],
        "deadline_text": parsed_q["deadline_text"],
        "short_deadline": parsed_q["short_deadline"],
        "deadline_label": parsed_q["deadline_label"],
        "calendar_date": parsed_q["calendar_date"],
        "deadline_instant": parsed_q["deadline_instant"],
        "deadline_epoch": parsed_q["deadline_epoch"],
        "yes_outcome_id": yes_outcome_id,
        "yes_outcome_name": "Yes",
        "yes_external_id": str(yes_external_id) if yes_external_id is not None else None,
        "no_outcome_id": no_outcome_id,
        "no_external_id": str(no_external_id) if no_external_id is not None else None,
        "yes_probability": yes_probability,
        "yes_rendered_percent": yes_rendered_percent,
        "no_probability": no_probability,
        "price_observed_at": effective_price_observed_at,
        "stored_movement_claim": stored_change,
        "movement_basis": (
            {
                "outcome_id": yes_outcome_id,
                "basis_price": basis_price,
                "observed_at": basis_observed_at.isoformat(),
                "age_hours": round(basis_age_hours, 4) if basis_age_hours is not None else None,
                "in_window": basis_in_window,
                "admits_zero": admits_zero,
            }
            if basis_price is not None and basis_observed_at is not None
            else None
        ),
        "movement_status": movement_status,
        "supported_move": supported_move,
        "supported_move_points": supported_move_points,
        "show_hero_movement_chip": movement_status == "hero",
        "show_row_movement_badge": movement_status in {"moderate", "hero"},
        "timeframe_utc": timeframe_utc,
        "settlement": settlement,
        "is_near_certain": is_near_certain,
        "near_certain_open_eligible": near_certain_open_eligible,
        "provider_market_count": provider_market_count,
        "detail_href": f"/futures/{clean_market_id}",
    }


def qualifies_for_deadline_near_certain_exception(
    *,
    name: str | None,
    source: str | None,
    external_id: str | None,
    group_id: str | None,
    status: str | None,
    resolution_date: Any,
    market_metadata: Any,
    outcomes: Sequence[Any] | None,
    prices_stopped: bool,
    now: datetime,
) -> bool:
    """Q8 helper for `_market_runtime_filter_trace` in `routes/feed.py`.

    A genuinely open cumulative deadline-family question at 97%+ remains eligible
    ONLY when it carries a qualifying recent dated move (`>= 2` pts) on its bound
    `Yes` outcome inside the 12h–24h dated-basis window and has fresh prices.
    """
    if prices_stopped:
        return False
    contract = build_deadline_member_contract(
        market_id=1,
        name=name,
        source=source,
        external_id=external_id,
        group_id=group_id,
        status=status,
        resolution_date=resolution_date,
        market_metadata=market_metadata,
        outcomes=outcomes,
        now=now,
    )
    if contract is None:
        return False
    return bool(contract.get("near_certain_open_eligible"))


def _validate_member_contract_dict(
    member_contract: Any,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Re-validate a serialized `deadline_member` contract dict on the consumer/bundler side.

    Never trusts pre-computed flags blindly: re-verifies the question grammar,
    deadline instant, outcome binding, stored-claim + dated-basis window, and
    settlement precedence from the contract fields.
    """
    if not isinstance(member_contract, Mapping):
        return None
    market_id = member_contract.get("market_id")
    name = member_contract.get("name")
    source = member_contract.get("source")
    external_id = member_contract.get("external_id")
    group_id = member_contract.get("group_id")
    deadline_instant = member_contract.get("deadline_instant")
    yes_outcome_id = member_contract.get("yes_outcome_id")
    no_outcome_id = member_contract.get("no_outcome_id")
    if (
        market_id is None
        or isinstance(market_id, bool)
        or not name
        or not source
        or not external_id
        or not group_id
        or not deadline_instant
        or yes_outcome_id is None
        or isinstance(yes_outcome_id, bool)
        or no_outcome_id is None
        or isinstance(no_outcome_id, bool)
    ):
        return None

    synthetic_outcomes = [
        {
            "id": yes_outcome_id,
            "name": "Yes",
            "external_id": member_contract.get("yes_external_id") or f"yes-{yes_outcome_id}",
            "current_probability": member_contract.get("yes_probability"),
            "probability_change_24h": member_contract.get("stored_movement_claim"),
        },
        {
            "id": no_outcome_id,
            "name": "No",
            "external_id": member_contract.get("no_external_id") or f"no-{no_outcome_id}",
            "current_probability": member_contract.get("no_probability"),
            "probability_change_24h": None,
        },
    ]
    basis_info = member_contract.get("movement_basis")
    synthetic_meta: dict[str, Any] = {}
    if isinstance(basis_info, Mapping):
        b_oid = basis_info.get("outcome_id", yes_outcome_id)
        b_price = basis_info.get("basis_price")
        b_at = basis_info.get("observed_at")
        if b_oid is not None and b_price is not None and b_at is not None:
            synthetic_meta["dated_movement_basis"] = {str(b_oid): [b_price, b_at]}
        if basis_info.get("admits_zero"):
            synthetic_meta["dated_movement_basis_eligibility"] = "priced_leg"
    if member_contract.get("provider_market_count") is not None:
        synthetic_meta["market_count"] = member_contract.get("provider_market_count")

    settlement_in = member_contract.get("settlement")
    status_in = "open"
    resolved_in = False
    winner_in = None
    if isinstance(settlement_in, Mapping):
        status_in = str(settlement_in.get("status") or "open")
        resolved_in = bool(settlement_in.get("is_settled"))
        winner_in = settlement_in.get("result") or settlement_in.get("winner")
        if settlement_in.get("authoritative_source") == "venue_metadata" and resolved_in:
            synthetic_meta["resolved"] = True
            if winner_in:
                synthetic_meta["winning_outcome"] = winner_in

    top_outcomes_in = (
        [{"id": yes_outcome_id, "rendered_percent": member_contract.get("yes_rendered_percent")}]
        if member_contract.get("yes_rendered_percent") is not None
        else None
    )

    rebuilt = build_deadline_member_contract(
        market_id=market_id,
        name=str(name),
        source=str(source),
        external_id=str(external_id),
        group_id=str(group_id),
        group_type=member_contract.get("group_type"),
        market_type=member_contract.get("market_type"),
        status=status_in,
        resolved=resolved_in,
        winner=winner_in,
        resolution_date=deadline_instant,
        market_metadata=synthetic_meta,
        outcomes=synthetic_outcomes,
        top_outcomes_data=top_outcomes_in,
        price_observed_at=member_contract.get("price_observed_at"),
        now=now,
    )
    if rebuilt is None:
        return None
    if isinstance(settlement_in, Mapping) and settlement_in.get("lagging_local_status"):
        rebuilt["settlement"]["lagging_local_status"] = True
    return rebuilt


def verify_and_select_deadline_family(
    member_contracts: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    reader_tz: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Verify a candidate set of deadline-family member contracts and select the representative.

    Returns `(family_payload, None)` on success, or `(None, rejection_reason)` when
    any identity, predicate, deadline, outcome-binding, or eligibility check fails.
    """
    if not member_contracts or len(member_contracts) < 2:
        return None, "fewer_than_two_members"

    validated: list[dict[str, Any]] = []
    for raw in member_contracts:
        checked = _validate_member_contract_dict(raw, now=now)
        if checked is None:
            return None, "invalid_or_missing_member_contract"
        validated.append(checked)

    sources = {m["source"] for m in validated}
    group_ids = {m["group_id"] for m in validated}
    if len(sources) != 1 or len(group_ids) != 1:
        return None, "mixed_provider_or_group_id"

    market_ids = [m["market_id"] for m in validated]
    external_ids = [m["external_id"] for m in validated]
    if len(set(market_ids)) != len(validated) or len(set(external_ids)) != len(validated):
        return None, "duplicate_market_or_condition_id"

    yes_outcome_ids = [m["yes_outcome_id"] for m in validated]
    if len(set(yes_outcome_ids)) != len(validated):
        return None, "duplicate_yes_outcome_id"

    stems = {m["stem_key"] for m in validated}
    preps = {m["preposition"] for m in validated}
    if len(stems) != 1 or len(preps) != 1:
        return None, "mixed_subject_or_predicate"

    calendar_dates = [m["calendar_date"] for m in validated]
    deadline_epochs = [m["deadline_epoch"] for m in validated]
    if (
        len(set(calendar_dates)) != len(validated)
        or len(set(deadline_epochs)) != len(validated)
    ):
        return None, "duplicate_or_ambiguous_deadline"

    # Sort in ascending deadline_instant order (Q2 / Section 4)
    ascending = sorted(validated, key=lambda m: (m["deadline_epoch"], m["market_id"]))
    if [m["calendar_date"] for m in ascending] != sorted(calendar_dates):
        return None, "deadline_instant_contradicts_calendar_order"

    source = ascending[0]["source"]
    group_id = ascending[0]["group_id"]
    story_key = deadline_family_story_key(source, group_id)
    display_stem = ascending[0]["display_stem"]
    shared_question = ascending[0]["shared_question"]

    # Determine family settlement state (6D)
    all_settled = all(m["settlement"]["is_settled"] for m in ascending)
    if all_settled:
        yes_winners = [
            m for m in ascending if m["settlement"].get("result") == "Yes"
        ]
        rep = yes_winners[0] if yes_winners else ascending[-1]
        selection_reason = "settled_family"
        family_state = "settled"
    else:
        family_state = "open"
        # Filter to open, priced members that are eligible (applying Q8 for >=97% members)
        eligible_open_priced = [
            m
            for m in ascending
            if not m["settlement"]["is_settled"]
            and m["yes_probability"] is not None
            and (not m["is_near_certain"] or m["near_certain_open_eligible"])
        ]
        if not eligible_open_priced:
            return None, "no_eligible_open_priced_member"

        # Q1: Select the open deadline with the largest eligible supported dated move (>= 2 pts).
        # If no eligible movement exists, select the eligible priced proposition nearest 50%.
        eligible_movers = [
            m
            for m in eligible_open_priced
            if m["movement_status"] in {"moderate", "hero"}
            and m["supported_move"] is not None
            and abs(m["supported_move"]) >= DEADLINE_MODERATE_MIN_MOVEMENT_FRACTION
        ]
        if eligible_movers:
            eligible_movers.sort(
                key=lambda m: (
                    -round(abs(float(m["supported_move"])), 6),
                    round(abs(float(m["yes_probability"]) - 0.50), 6),
                    float(m["deadline_epoch"]),
                    int(m["market_id"]),
                )
            )
            rep = eligible_movers[0]
            selection_reason = "largest_supported_dated_move"
        else:
            eligible_open_priced.sort(
                key=lambda m: (
                    round(abs(float(m["yes_probability"]) - 0.50), 6),
                    float(m["deadline_epoch"]),
                    int(m["market_id"]),
                )
            )
            rep = eligible_open_priced[0]
            selection_reason = "nearest_50_pct_fallback"

    # Compute timeframe in requested timezone (`reader_tz` or UTC) for the representative
    rep_basis = rep.get("movement_basis")
    rep_timeframe = (
        format_movement_timeframe(
            rep_basis.get("observed_at") if isinstance(rep_basis, Mapping) else None,
            rep.get("price_observed_at")
            or (now.isoformat() if isinstance(now, datetime) else None),
            tz_name=reader_tz or "UTC",
        )
        if rep.get("supported_move") is not None and isinstance(rep_basis, Mapping)
        else None
    )

    # 6F: Distinguish represented family members from complete provider inventory.
    represented_count = len(ascending)
    known_counts = {
        int(m["provider_market_count"])
        for m in ascending
        if m.get("provider_market_count") is not None
        and int(m["provider_market_count"]) >= represented_count
    }
    provider_market_count = next(iter(known_counts)) if len(known_counts) == 1 else None
    inventory_complete: bool | None = (
        (provider_market_count == represented_count)
        if provider_market_count is not None
        else None
    )

    return (
        {
            "story_key": story_key,
            "source": source,
            "group_id": group_id,
            "title": display_stem,
            "shared_question": shared_question,
            "family_state": family_state,
            "representative_market_id": rep["market_id"],
            "representative_outcome_id": rep["yes_outcome_id"],
            "representative_deadline_label": rep["deadline_label"],
            "selection_reason": selection_reason,
            "tie_break_rule": DETERMINISTIC_TIE_BREAK_RULE,
            "hero_min_movement_points": DEADLINE_HERO_MIN_MOVEMENT_POINTS,
            "moderate_min_movement_points": DEADLINE_MODERATE_MIN_MOVEMENT_POINTS,
            "represented_count": represented_count,
            "provider_market_count": provider_market_count,
            "inventory_complete": inventory_complete,
            "representative_timeframe": rep_timeframe,
            "members": ascending,
        },
        None,
    )


__all__ = [
    "DEADLINE_FAMILY_STORY_PREFIX",
    "DEADLINE_HERO_MIN_MOVEMENT_POINTS",
    "DEADLINE_HERO_MIN_MOVEMENT_FRACTION",
    "DEADLINE_MODERATE_MIN_MOVEMENT_POINTS",
    "DEADLINE_MODERATE_MIN_MOVEMENT_FRACTION",
    "DETERMINISTIC_TIE_BREAK_RULE",
    "is_deadline_family_story_key",
    "deadline_family_story_key",
    "parse_timezone_aware_instant",
    "parse_cumulative_deadline_question",
    "extract_settlement_evidence",
    "format_movement_timeframe",
    "build_deadline_member_contract",
    "qualifies_for_deadline_near_certain_exception",
    "verify_and_select_deadline_family",
]
