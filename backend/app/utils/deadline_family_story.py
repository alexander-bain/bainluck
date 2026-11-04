"""Movement-led cumulative deadline-family story verification and bundle assembly (#9878 / #11040).

Slice 1 (v2) scope:
- Verifies a single-provider cumulative deadline family from supported producer evidence:
  - Provider/group identity (`source`, `group_id`, distinct `external_id` condition IDs,
    and distinct `yes_outcome_id` / `no_outcome_id` pairs).
  - Deterministic rule-equivalence verification extracted from the producer rule text
    (`FuturesMarket.description` / Gamma `market.description` stamped into
    `market_metadata["deadline_rule_contract"]` at ingest by `tasks/polymarket.py`),
    proving an affirmative `"Yes"` resolution clause, a cumulative window from market
    creation (`"between market creation and <deadline>"`), a shared normalized rule
    template digest (`rule_template_hash`), and an explicit contractual cutoff time and
    timezone (e.g. `11:59 PM ET` -> `America/New_York` `23:59`).
  - Timezone-exact contractual deadline verification in the rule's `ZoneInfo` timezone
    (converting `resolution_date` to the rule's timezone and requiring an exact match on
    the local calendar date and cutoff hour:minute, plus `groupItemTitle` date agreement
    when present — with no multi-hour tolerance window that could admit adjacent dates).
  - Fail-closed refusal (`missing_rule_equivalence_proof`) when upstream rule/cutoff
    evidence is absent on already-stored rows, preserving ordinary standalone card
    behavior.
- Keeps terminal/settlement states strictly distinct using real producer fields
  (`FuturesMarket.status`, `FuturesOutcome.is_winner` + `FuturesOutcome.resolution_source`
  governed by `app.utils.resolution_authority`, `market_metadata["price_refresh_venue_settled_since"]`,
  and Gamma's `closed` / `uma_resolution_status` / terminal `outcome_prices`):
  - `"open"`: open and before `deadline_instant`, no terminal signal.
  - `"trading_closed"`: trading closed or past `deadline_instant`, result not yet known.
  - `"resolved"`: result known/settled with a specific verified winning outcome (`"Yes"` or `"No"`).
  - `"void"`: void, canceled, retracted (`ungradeable_result`, `did_not_play`, etc.), or 50/50 split.
  - `"unknown"`: terminal market status (`resolved`/`closed`/`suspended`) where the winning
    outcome is not carried on the current projection/wire.
- Traces current price and movement observation lineage strictly from the selected `Yes`
  outcome (`outcome_observed_at(yes_outcome)` -> `price_observed_epoch` / `last_updated`):
  - Never substitutes `datetime.now`, `now`, or feed-read/render time as the observation
    endpoint of a movement comparison.
  - Missing observation timestamps remain `None` and refuse dated movement claims and
    the Q8 `>=97%` exception.
  - Enforces existing freshness policy (`prices_have_stopped` and `stale_observation_keys`
    from `app.utils.market_staleness`) and requires `yes_price_observed_at >= basis_observed_at`
    within the 24h window.
"""

from __future__ import annotations

import calendar
import hashlib
import re
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.utils.futures_liveness import VENUE_SETTLED_KEY
from app.utils.futures_market_snapshot import (
    DATED_BASIS_MIN_AGE_HOURS,
    DATED_BASIS_WINDOW_HOURS,
    dated_basis_admits_zero,
    dated_movement_basis,
    outcome_observed_at,
    outcome_prints_a_price,
    read_dated_basis_entry,
)
from app.utils.market_staleness import (
    prices_have_stopped,
    stale_observation_keys,
)
from app.utils.resolution_authority import (
    GUESS_FAMILY_SOURCES,
    can_write_winner,
    is_authoritative,
)

DEADLINE_FAMILY_STORY_PREFIX = "story:deadline_family:"

#: Metadata key stamped at Polymarket sub-market ingest when a sub-market's
#: question, rule text (`description`), `groupItemTitle`, and `endDate` satisfy
#: the cumulative deadline-family contract.
DEADLINE_RULE_CONTRACT_KEY = "deadline_rule_contract"

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

#: Minimum probability (> 5%) required to surface a movement claim on a Yes leg
#: (`MovementBadge` and `MOVER_MIN_PROBABILITY` suppress placeholder-floor moves at `<= 5%`).
DEADLINE_MOVER_MIN_PROBABILITY = 0.05

#: Deterministic tie-break rule identifier documented in payload and contract.
DETERMINISTIC_TIE_BREAK_RULE = (
    "abs_supported_move_desc -> distance_from_50pct_asc -> deadline_instant_asc -> market_id_asc"
)

_TERMINAL_MARKET_STATUSES = frozenset({"resolved", "closed", "settled", "finalized", "final"})
_VOID_MARKET_STATUSES = frozenset({"void", "canceled", "cancelled", "invalid", "retracted", "50_50"})
_VOID_RESOLUTION_SOURCES = frozenset({
    "ungradeable_result",
    "did_not_play",
    "withdrew",
    "no_pregame_trading",
    "all_losers",
})

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
    r"\b(?:not|won't|will\s+not|cannot|can't|never|fail(?:s)?\s+to|stay(?:s)?\s+in|remain(?:s)?\s+(?:in|as)|continues?\s+through)\b",
    re.IGNORECASE,
)

#: Mention-only speech/word markets that must not be grouped as event deadline stories (6B).
_MENTION_ONLY_STEM_RE = re.compile(
    r"\b(?:say|says|said|mention|mentions|mentioned|tweet|tweets|post|posts|utter|use\s+the\s+word)\b",
    re.IGNORECASE,
)

_LEADING_AUXILIARY_RE = re.compile(r"^(?:will|does|do|is|are|has|have)\s+", re.IGNORECASE)

#: Map rule-text timezone abbreviations to IANA ZoneInfo identifiers.
_RULE_TZ_TO_IANA: dict[str, str] = {
    "ET": "America/New_York",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CT": "America/Chicago",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "MT": "America/Denver",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "PT": "America/Los_Angeles",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "UTC": "UTC",
    "GMT": "UTC",
}

#: Affirmative cumulative deadline resolution clause in Polymarket rule text:
#: "This market will resolve to "Yes" if <predicate> between market creation and
#:  (the specified date|<Month> <day>[, <year>]), <HH:MM AM/PM> <TZ>.
#:  Otherwise, this market will resolve to "No"."
_AFFIRMATIVE_CUMULATIVE_RULE_RE = re.compile(
    rf"This market will resolve to [\x22\u201c]Yes[\x22\u201d] if (?P<predicate>.+?)\s+"
    rf"(?P<window_phrase>between market creation and)\s+"
    rf"(?P<date_slot>the specified date|(?:{_MONTH_PATTERN})\.?\s+\d{{1,2}}(?:\s*,\s*\d{{4}}|\s+\d{{4}})?)\s*,?\s*"
    rf"(?P<cutoff_hour>\d{{1,2}}):(?P<cutoff_minute>\d{{2}})\s*(?P<cutoff_ampm>AM|PM)\s+"
    rf"(?P<cutoff_tz>ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|UTC|GMT)\s*\.\s*"
    rf"Otherwise,?\s+this market will resolve to [\x22\u201c]No[\x22\u201d]\.",
    re.IGNORECASE | re.DOTALL,
)

#: Any secondary date slot inside the rule body (`by <Month> <day>[, <year>], 11:59 PM ET`)
#: so that normalizing the rule text produces a date-independent template digest.
_SECONDARY_RULE_DATE_SLOT_RE = re.compile(
    rf"\b(?P<prep>by|between market creation and)\s+(?P<slot>the specified date|(?:{_MONTH_PATTERN})\.?\s+\d{{1,2}}(?:\s*,\s*\d{{4}}|\s+\d{{4}})?)(?=\s*,\s*\d{{1,2}}:\d{{2}}\s*(?:AM|PM)\b)",
    re.IGNORECASE,
)


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
    local time (Section 3B / Section 6B / Case 15).
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


def _parse_calendar_date_slot(raw_text: str | None) -> tuple[int, int, int | None] | None:
    """Parse `<Month> <day>[, <year>]` into `(month_num, day_num, explicit_year)`."""
    if not raw_text or not isinstance(raw_text, str):
        return None
    date_match = _CALENDAR_DATE_DEADLINE_RE.match(raw_text.strip())
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
    if not (1 <= day_num <= 31):
        return None
    explicit_year_str = date_match.group("year") or date_match.group("year_plain")
    explicit_year = int(explicit_year_str) if explicit_year_str else None
    if explicit_year is not None and not (2000 <= explicit_year <= 2100):
        return None
    return month_num, day_num, explicit_year


def _convert_12h_to_24h(hour_12: int, minute: int, ampm: str) -> tuple[int, int] | None:
    if not (1 <= hour_12 <= 12) or not (0 <= minute <= 59):
        return None
    upper = ampm.strip().upper()
    if upper == "AM":
        hour_24 = 0 if hour_12 == 12 else hour_12
    elif upper == "PM":
        hour_24 = 12 if hour_12 == 12 else hour_12 + 12
    else:
        return None
    return hour_24, minute


def _normalize_rule_text_for_hash(description: str) -> str:
    """Normalize quotes, whitespace, and deadline-date slots in rule text for template hashing."""
    text = (
        description.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )
    text = _SECONDARY_RULE_DATE_SLOT_RE.sub(r"\g<prep> <DEADLINE_DATE>", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _sha256_hex(text: str | None) -> str | None:
    if not text or not isinstance(text, str):
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def is_verified_deadline_rule_contract(contract: Any) -> bool:
    """True only when `contract` is a verified cumulative deadline rule contract."""
    return isinstance(contract, Mapping) and contract.get("verified") is True


def merge_submarket_metadata_for_upsert(
    existing_metadata: Mapping[str, Any] | None,
    new_sub_meta: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Apply the top-level JSONB `||` merge semantics used by `_process_event_batch`.

    In `tasks/polymarket.py`, `FuturesMarket.market_metadata` is updated on conflict via:
        `COALESCE(futures_markets.market_metadata, '{}'::jsonb) || jsonb_build_object(...)`
    Top-level keys present in `new_sub_meta` (including `deadline_rule_contract`)
    atomically replace the corresponding top-level key in `existing_metadata` while
    every unrelated top-level key (`dated_movement_basis`, `clob_token_ids`,
    `content_understanding`, `volume_evidence`, etc.) is preserved untouched.
    """
    merged: dict[str, Any] = dict(existing_metadata) if isinstance(existing_metadata, Mapping) else {}
    if isinstance(new_sub_meta, Mapping):
        if DEADLINE_RULE_CONTRACT_KEY not in new_sub_meta:
            merged.pop(DEADLINE_RULE_CONTRACT_KEY, None)
        for key, value in new_sub_meta.items():
            merged[key] = value
    return merged


def diagnose_polymarket_deadline_rule_refusal(
    description: str | None,
    *,
    question: str | None = None,
    group_item_title: str | None = None,
    end_date: Any = None,
) -> str:
    """Return a specific deterministic refusal reason when a sub-market fails deadline rule validation."""
    if not description or not isinstance(description, str) or not description.strip():
        return "missing_or_empty_description"
    cleaned_desc = description.strip()
    rule_match = _AFFIRMATIVE_CUMULATIVE_RULE_RE.search(cleaned_desc)
    if rule_match is None:
        return "non_cumulative_or_non_affirmative_rule_clause"
    raw_predicate = rule_match.group("predicate").strip()
    main_clause_predicate = re.sub(r"\([^)]*\)", " ", raw_predicate).strip()
    if not main_clause_predicate or _NEGATIVE_STEM_RE.search(main_clause_predicate):
        return "negative_or_inverted_rule_predicate"
    raw_tz = rule_match.group("cutoff_tz").strip().upper()
    iana_tz = _RULE_TZ_TO_IANA.get(raw_tz)
    if not iana_tz:
        return "unsupported_rule_cutoff_timezone"
    try:
        hour_12 = int(rule_match.group("cutoff_hour"))
        minute = int(rule_match.group("cutoff_minute"))
    except (TypeError, ValueError):
        return "invalid_rule_cutoff_time"
    converted = _convert_12h_to_24h(hour_12, minute, rule_match.group("cutoff_ampm"))
    if converted is None:
        return "invalid_rule_cutoff_time"
    cutoff_local_time = f"{converted[0]:02d}:{converted[1]:02d}"
    raw_date_slot = rule_match.group("date_slot").strip()
    rule_slot_date = None
    if raw_date_slot.lower() != "the specified date":
        rule_slot_date = _parse_calendar_date_slot(raw_date_slot)
        if rule_slot_date is None:
            return "invalid_rule_date_slot"
    if group_item_title is not None and str(group_item_title).strip():
        gi_date = _parse_calendar_date_slot(str(group_item_title).strip())
        if gi_date is None:
            return "non_calendar_group_item_title"
        if rule_slot_date is not None and (
            (gi_date[0], gi_date[1]) != (rule_slot_date[0], rule_slot_date[1])
            or (gi_date[2] is not None and rule_slot_date[2] is not None and gi_date[2] != rule_slot_date[2])
        ):
            return "group_item_title_conflicts_with_rule_date"
    if question is not None or end_date is not None:
        parsed_q = parse_cumulative_deadline_question(
            question,
            end_date,
            cutoff_timezone=iana_tz,
            cutoff_local_time=cutoff_local_time,
        )
        if parsed_q is None:
            return "question_or_end_date_cutoff_mismatch"
    return "rule_contract_validation_failed"


def _extract_venue_terminal_fields(
    *,
    closed: Any = None,
    uma_resolution_status: str | None = None,
    outcomes: Sequence[Any] | None = None,
    outcome_prices: Sequence[Any] | None = None,
) -> tuple[bool, str | None, str, str | None]:
    venue_terminal_state = "open"
    venue_winner: str | None = None
    uma_status_clean = (
        str(uma_resolution_status).strip().lower()
        if isinstance(uma_resolution_status, str) and uma_resolution_status.strip()
        else None
    )
    is_closed = closed is True
    if is_closed and uma_status_clean == "resolved":
        parsed_prices: list[float] = []
        if isinstance(outcome_prices, Sequence) and not isinstance(outcome_prices, (str, bytes)):
            try:
                parsed_prices = [float(p) for p in outcome_prices]
            except (TypeError, ValueError):
                parsed_prices = []
        norm_outcomes = [
            str(o).strip().lower()
            for o in (outcomes or ["Yes", "No"])
            if str(o).strip()
        ]
        if norm_outcomes == ["yes", "no"] and len(parsed_prices) == 2:
            if parsed_prices == [1.0, 0.0]:
                venue_terminal_state = "resolved"
                venue_winner = "Yes"
            elif parsed_prices == [0.0, 1.0]:
                venue_terminal_state = "resolved"
                venue_winner = "No"
            elif parsed_prices == [0.5, 0.5]:
                venue_terminal_state = "void"
            else:
                venue_terminal_state = "unknown"
        else:
            venue_terminal_state = "unknown"
    elif is_closed:
        venue_terminal_state = "trading_closed"
    return is_closed, uma_status_clean, venue_terminal_state, venue_winner


def extract_polymarket_deadline_rule_contract(
    description: str | None,
    *,
    question: str | None = None,
    group_item_title: str | None = None,
    end_date: Any = None,
    closed: Any = None,
    uma_resolution_status: str | None = None,
    outcomes: Sequence[Any] | None = None,
    outcome_prices: Sequence[Any] | None = None,
    provider_market_count: int | None = None,
    condition_id: str | None = None,
    market_created_at: Any = None,
) -> dict[str, Any] | None:
    """Extract and verify a cumulative deadline rule contract from producer fields.

    Requires:
    1. Non-empty rule text (`description`) matching the affirmative cumulative
       deadline resolution grammar:
       `"This market will resolve to 'Yes' if <predicate> between market creation and
        <date_slot>, <HH:MM AM/PM> <TZ>. Otherwise, this market will resolve to 'No'."`
    2. Valid IANA timezone mapping for `<TZ>` (e.g. `ET` -> `America/New_York`) and
       valid 24-hour cutoff time (e.g. `11:59 PM` -> `23:59`).
    3. If `question` and `end_date` are supplied, verifies that `question` is an
       affirmative `"<stem> by <Month> <day>"` question whose calendar date matches:
       - the rule's `<date_slot>` when `<date_slot>` names a specific date,
       - `group_item_title` when `group_item_title` is provided, and
       - `end_date` converted to `ZoneInfo(cutoff_timezone)` at the exact local
         `cutoff_hour:cutoff_minute` (handling EDT/EST DST transitions and UTC year
         rollovers with zero adjacent-day tolerance).
    4. Records lower-bound window semantics honestly: `"between market creation and ..."`
       binds each market's resolution window to that market's creation (`window_start_kind:
       "market_creation"`). It does NOT claim nested cumulative windows across siblings
       unless their `window_start_instant` timestamps are present and proven equal
       (`nested_window_proven`).
    """
    if not description or not isinstance(description, str):
        return None
    cleaned_desc = description.strip()
    if not cleaned_desc:
        return None

    rule_match = _AFFIRMATIVE_CUMULATIVE_RULE_RE.search(cleaned_desc)
    if rule_match is None:
        return None

    raw_predicate = rule_match.group("predicate").strip()
    main_clause_predicate = re.sub(r"\([^)]*\)", " ", raw_predicate).strip()
    if not main_clause_predicate or _NEGATIVE_STEM_RE.search(main_clause_predicate):
        return None

    raw_date_slot = rule_match.group("date_slot").strip()
    try:
        hour_12 = int(rule_match.group("cutoff_hour"))
        minute = int(rule_match.group("cutoff_minute"))
    except (TypeError, ValueError):
        return None
    ampm = rule_match.group("cutoff_ampm")
    converted = _convert_12h_to_24h(hour_12, minute, ampm)
    if converted is None:
        return None
    cutoff_hour, cutoff_minute = converted

    raw_tz = rule_match.group("cutoff_tz").strip().upper()
    iana_tz = _RULE_TZ_TO_IANA.get(raw_tz)
    if not iana_tz:
        return None

    rule_slot_date: tuple[int, int, int | None] | None = None
    if raw_date_slot.lower() != "the specified date":
        rule_slot_date = _parse_calendar_date_slot(raw_date_slot)
        if rule_slot_date is None:
            return None

    group_item_date: tuple[int, int, int | None] | None = None
    if group_item_title is not None and str(group_item_title).strip():
        group_item_date = _parse_calendar_date_slot(str(group_item_title).strip())
        if group_item_date is None:
            return None
        if rule_slot_date is not None:
            if (group_item_date[0], group_item_date[1]) != (rule_slot_date[0], rule_slot_date[1]):
                return None
            if (
                group_item_date[2] is not None
                and rule_slot_date[2] is not None
                and group_item_date[2] != rule_slot_date[2]
            ):
                return None

    normalized_template = _normalize_rule_text_for_hash(cleaned_desc)
    rule_template_hash = hashlib.sha256(normalized_template.encode("utf-8")).hexdigest()[:16]
    normalized_predicate = re.sub(r"\s+", " ", raw_predicate.lower()).strip()
    predicate_hash = hashlib.sha256(normalized_predicate.encode("utf-8")).hexdigest()[:16]
    cutoff_local_time = f"{cutoff_hour:02d}:{cutoff_minute:02d}"

    # Verify question + end_date against the rule contract when supplied
    verified_calendar_date: str | None = None
    if question is not None or end_date is not None:
        parsed_q = parse_cumulative_deadline_question(
            question,
            end_date,
            cutoff_timezone=iana_tz,
            cutoff_local_time=cutoff_local_time,
        )
        if parsed_q is None:
            return None
        verified_calendar_date = parsed_q["calendar_date"]
        q_year, q_month, q_day = (int(part) for part in verified_calendar_date.split("-"))
        if rule_slot_date is not None:
            if (rule_slot_date[0], rule_slot_date[1]) != (q_month, q_day):
                return None
            if rule_slot_date[2] is not None and rule_slot_date[2] != q_year:
                return None
        if group_item_date is not None:
            if (group_item_date[0], group_item_date[1]) != (q_month, q_day):
                return None
            if group_item_date[2] is not None and group_item_date[2] != q_year:
                return None

    is_closed, uma_status_clean, venue_terminal_state, venue_winner = (
        _extract_venue_terminal_fields(
            closed=closed,
            uma_resolution_status=uma_resolution_status,
            outcomes=outcomes,
            outcome_prices=outcome_prices,
        )
    )

    clean_condition_id = (
        str(condition_id).strip()
        if condition_id is not None and str(condition_id).strip()
        else None
    )
    end_dt = parse_timezone_aware_instant(end_date)
    created_dt = parse_timezone_aware_instant(market_created_at)

    contract: dict[str, Any] = {
        "schema": "polymarket_cumulative_deadline_v1",
        "verified": True,
        "status": "verified",
        "condition_id": clean_condition_id,
        "question_sha256": _sha256_hex(question),
        "description_sha256": _sha256_hex(cleaned_desc),
        "end_date_iso": end_dt.isoformat() if end_dt is not None else None,
        "rule_template_hash": rule_template_hash,
        "predicate_hash": predicate_hash,
        "window_kind": "cumulative_from_creation",
        "window_start_kind": "market_creation",
        "window_start_instant": created_dt.isoformat() if created_dt is not None else None,
        "nested_window_proven": False,
        "resolves_yes_on_affirmative": True,
        "cutoff_timezone": iana_tz,
        "cutoff_tz_abbr": raw_tz,
        "cutoff_local_time": cutoff_local_time,
        "date_slot_kind": (
            "shared_specified_date" if rule_slot_date is None else "explicit_calendar_date"
        ),
        "group_item_title": (
            str(group_item_title).strip()
            if group_item_title is not None and str(group_item_title).strip()
            else None
        ),
        "verified_calendar_date": verified_calendar_date,
        "venue_closed": is_closed,
        "uma_resolution_status": uma_status_clean,
        "venue_terminal_state": venue_terminal_state,
        "venue_winner": venue_winner,
    }
    if (
        isinstance(provider_market_count, int)
        and not isinstance(provider_market_count, bool)
        and provider_market_count > 0
    ):
        contract["provider_market_count"] = provider_market_count
    return contract


def build_polymarket_submarket_deadline_contract(event: Any, market: Any) -> dict[str, Any] | None:
    """Ingest helper for `tasks/polymarket.py` (`sub_market_metadata`).

    Inspects `market` (`PolymarketMarket`) and `event` (`PolymarketEvent`) already
    in hand during `_process_event_batch`.
    - For single-market or `neg_risk` events, returns `None`.
    - For multi-market non-`neg_risk` events (`len(event.markets) >= 2`):
      Always returns a `deadline_rule_contract` dict so that re-ingestion via the
      PostgreSQL `COALESCE(market_metadata, '{}') || jsonb_build_object(...)` merge
      in `_process_event_batch` atomically replaces any prior `deadline_rule_contract`
      while preserving all unrelated `market_metadata` keys:
      1. When the sub-market satisfies cumulative deadline rule & cutoff validation:
         returns `"verified": True, "status": "verified"`, bound to `condition_id`,
         `question_sha256`, `description_sha256`, and `end_date_iso`.
      2. When `description` is missing (`None` or empty):
         returns `"verified": False, "status": "missing_rule_description"`.
      3. When `description`, `question`, `group_item_title`, or `end_date` fails
         validation (including when a previously valid rule is edited to an
         incompatible rule):
         returns `"verified": False, "status": "invalidated_incompatible_rule"`
         with the specific refusal `reason`, invalidating any previously stored proof.
    """
    if event is None or market is None:
        return None
    if getattr(event, "neg_risk", False):
        return None
    markets_list = getattr(event, "markets", None) or []
    if len(markets_list) < 2:
        return None

    question = getattr(market, "question", None) or getattr(event, "title", None)
    description = getattr(market, "description", None)
    end_date = getattr(market, "end_date", None)
    raw_cid = getattr(market, "condition_id", None)
    clean_condition_id = str(raw_cid).strip() if raw_cid is not None and str(raw_cid).strip() else None
    market_created_at = getattr(market, "created_at", None) or getattr(market, "start_date", None)
    group_item_title = getattr(market, "group_item_title", None)
    provider_market_count = len(markets_list)

    if question and isinstance(description, str) and description.strip() and end_date is not None:
        verified_contract = extract_polymarket_deadline_rule_contract(
            description,
            question=question,
            group_item_title=group_item_title,
            end_date=end_date,
            closed=getattr(market, "closed", False),
            uma_resolution_status=getattr(market, "uma_resolution_status", None),
            outcomes=getattr(market, "outcomes", None),
            outcome_prices=getattr(market, "outcome_prices", None),
            provider_market_count=provider_market_count,
            condition_id=clean_condition_id,
            market_created_at=market_created_at,
        )
        if verified_contract is not None:
            return verified_contract

    is_closed, uma_status_clean, venue_terminal_state, venue_winner = (
        _extract_venue_terminal_fields(
            closed=getattr(market, "closed", False),
            uma_resolution_status=getattr(market, "uma_resolution_status", None),
            outcomes=getattr(market, "outcomes", None),
            outcome_prices=getattr(market, "outcome_prices", None),
        )
    )
    end_dt = parse_timezone_aware_instant(end_date)
    missing_desc = not description or not isinstance(description, str) or not description.strip()
    status_code = "missing_rule_description" if missing_desc else "invalidated_incompatible_rule"
    reason = (
        "missing_or_empty_description"
        if missing_desc
        else diagnose_polymarket_deadline_rule_refusal(
            description,
            question=question,
            group_item_title=group_item_title,
            end_date=end_date,
        )
    )

    invalidation_contract: dict[str, Any] = {
        "schema": "polymarket_cumulative_deadline_v1",
        "verified": False,
        "status": status_code,
        "reason": reason,
        "condition_id": clean_condition_id,
        "question_sha256": _sha256_hex(question),
        "description_sha256": None if missing_desc else _sha256_hex(description),
        "end_date_iso": end_dt.isoformat() if end_dt is not None else None,
        "rule_template_hash": None,
        "predicate_hash": None,
        "window_kind": None,
        "window_start_kind": None,
        "window_start_instant": None,
        "nested_window_proven": False,
        "resolves_yes_on_affirmative": False,
        "cutoff_timezone": None,
        "cutoff_tz_abbr": None,
        "cutoff_local_time": None,
        "date_slot_kind": None,
        "group_item_title": (
            str(group_item_title).strip()
            if group_item_title is not None and str(group_item_title).strip()
            else None
        ),
        "verified_calendar_date": None,
        "venue_closed": is_closed,
        "uma_resolution_status": uma_status_clean,
        "venue_terminal_state": venue_terminal_state,
        "venue_winner": venue_winner,
        "provider_market_count": provider_market_count,
    }
    return invalidation_contract


def parse_cumulative_deadline_question(
    name: str | None,
    resolution_date: Any,
    *,
    cutoff_timezone: str | None = "America/New_York",
    cutoff_local_time: str | None = "23:59",
) -> dict[str, Any] | None:
    """Verify and parse a cumulative deadline question and its contractual cutoff instant.

    Section 3B requirements:
    - Does NOT use a broad `[-14h, +36h]` UTC tolerance window that could accept
      timestamps belonging to an adjacent calendar date.
    - Requires a supported contractual `cutoff_timezone` (e.g. `"America/New_York"`)
      and `cutoff_local_time` (e.g. `"23:59"`). When `cutoff_timezone` or
      `cutoff_local_time` is `None` or invalid, refuses (`None`).
    - Converts `resolution_date` into `ZoneInfo(cutoff_timezone)` and verifies that:
      1. The local calendar date `(local_dt.year, local_dt.month, local_dt.day)`
         matches the question's `<Month> <day>[, <year>]` exactly.
      2. The local time `(local_dt.hour, local_dt.minute)` matches `cutoff_local_time`
         exactly (`23:59`, allowing only `0..59` seconds within that exact minute).
    - Automatically and accurately handles US EDT (`UTC-4`) vs EST (`UTC-5`)
      daylight-saving transitions and Dec 31 -> Jan 1 UTC year rollovers.
    """
    if not name or not isinstance(name, str):
        return None
    if not cutoff_timezone or not cutoff_local_time:
        return None
    try:
        tz = ZoneInfo(cutoff_timezone)
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        return None

    time_parts = str(cutoff_local_time).strip().split(":")
    if len(time_parts) != 2:
        return None
    try:
        expected_hour = int(time_parts[0])
        expected_minute = int(time_parts[1])
    except (TypeError, ValueError):
        return None
    if not (0 <= expected_hour <= 23 and 0 <= expected_minute <= 59):
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

    parsed_slot = _parse_calendar_date_slot(raw_deadline)
    if parsed_slot is None:
        return None
    month_num, day_num, explicit_year = parsed_slot

    deadline_instant = parse_timezone_aware_instant(resolution_date)
    if deadline_instant is None:
        return None

    # Convert the UTC instant into the contractual cutoff timezone (`America/New_York`, etc.)
    local_cutoff = deadline_instant.astimezone(tz)
    local_year = local_cutoff.year
    if not (2000 <= local_year <= 2100):
        return None
    if explicit_year is not None and local_year != explicit_year:
        return None

    max_day = calendar.monthrange(local_year, month_num)[1]
    if not (1 <= day_num <= max_day):
        return None

    # Exact local calendar date and exact contractual cutoff minute required
    if local_cutoff.date() != date(local_year, month_num, day_num):
        return None
    if (local_cutoff.hour, local_cutoff.minute) != (expected_hour, expected_minute):
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
    calendar_date = f"{local_year:04d}-{month_num:02d}-{day_num:02d}"

    return {
        "stem_key": stem_key,
        "display_stem": display_stem,
        "shared_question": f"{display_stem} by…?",
        "preposition": prep,
        "deadline_text": raw_deadline,
        "short_deadline": short_deadline,
        "deadline_label": deadline_label,
        "calendar_date": calendar_date,
        "cutoff_timezone": cutoff_timezone,
        "cutoff_local_time": f"{expected_hour:02d}:{expected_minute:02d}",
        "deadline_instant": deadline_instant.isoformat(),
        "deadline_epoch": deadline_instant.timestamp(),
    }


def _normalize_yes_no_result(raw_winner: Any) -> str | None:
    if raw_winner is None or isinstance(raw_winner, bool):
        return None
    text = str(raw_winner).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered == "yes":
        return "Yes"
    if lowered == "no":
        return "No"
    return None


def extract_settlement_evidence(
    *,
    status: Any,
    resolved: Any = None,
    winner: Any = None,
    market_metadata: Any = None,
    outcomes: Sequence[Any] | None = None,
    deadline_instant: Any = None,
    now: Any = None,
    external_id: str | None = None,
    question: str | None = None,
) -> dict[str, Any]:
    """Classify terminal/settlement state using only real producer fields (Section 3C / Gap 2).

    Keeps six states strictly distinct:
    1. `"open"`: Market is open, before `deadline_instant`, with no venue/outcome
       settlement signal (`is_settled=False, is_trading_closed=False, is_deadline_passed=False`).
    2. `"deadline_passed"`: Condition cutoff (`deadline_instant`) has passed (`now >= deadline_instant`)
       while the market row remains `"open"` without venue trading-closure or result evidence.
       Excluded from live-movement representative selection and movement chips/badges,
       while rendering truthful `"Deadline passed"` wording rather than `"Trading closed"`
       (`is_settled=False, is_trading_closed=False, is_deadline_passed=True`).
    3. `"trading_closed"`: Venue trading has closed (`market_metadata[VENUE_SETTLED_KEY]`,
       Gamma `venue_closed=True` without `uma_resolution_status="resolved"`, or
       `status in {"closed", "trading_closed"}` without an authoritative winner),
       result not yet known (`is_settled=False, is_trading_closed=True, result=None`).
    4. `"resolved"`: Result is known and settled with a specific winning outcome
       (`result` is `"Yes"` or `"No"`, `is_settled=True`), supported by:
       - `FuturesOutcome.is_winner is True` with a non-guess `resolution_source`
         permitted by `app.utils.resolution_authority.can_write_winner`, or
       - Producer-stamped Gamma `venue_terminal_state == "resolved"` with
         `venue_winner in {"Yes", "No"}` (`closed=True`, `uma_resolution_status="resolved"`,
         and exact `[1.0, 0.0]` / `[0.0, 1.0]` outcome prices), or
       - Explicit verified `winner` in `{"Yes", "No"}` on a settled envelope.
    5. `"void"`: Void, canceled, retracted (`resolution_source` in `_VOID_RESOLUTION_SOURCES`),
       or 50/50 split resolution (`is_settled=False, result=None`).
    6. `"unknown"`: Market has terminal resolved/settled/suspended status
       (`status in {"resolved", "settled", "finalized", "final", "suspended"}` or
       `resolved is True` or `venue_terminal_state == "unknown"`) without an
       authoritative winning outcome, OR stale stored proof conflicts with newer
       state (`conflicting_settlement_evidence`). Never guesses a winner from prices.
    """
    local_status = str(status or "open").strip().lower()
    meta = market_metadata if isinstance(market_metadata, Mapping) else {}
    rule_contract = (
        meta.get(DEADLINE_RULE_CONTRACT_KEY)
        if isinstance(meta.get(DEADLINE_RULE_CONTRACT_KEY), Mapping)
        else {}
    )
    venue_settled_since = meta.get(VENUE_SETTLED_KEY)

    deadline_dt = parse_timezone_aware_instant(deadline_instant)
    now_dt = parse_timezone_aware_instant(now)
    cutoff_has_passed = bool(
        deadline_dt is not None and now_dt is not None and now_dt >= deadline_dt
    )

    # Check whether stored `deadline_rule_contract` identity/cutoff conflicts with current row
    stored_contract_stale_conflict = False
    if rule_contract:
        rc_cid = rule_contract.get("condition_id")
        if (
            rc_cid is not None
            and external_id is not None
            and str(rc_cid).strip()
            and str(external_id).strip()
            and str(rc_cid).strip() != str(external_id).strip()
        ):
            stored_contract_stale_conflict = True
        rc_q_sha = rule_contract.get("question_sha256")
        if (
            rc_q_sha is not None
            and question is not None
            and _sha256_hex(question) is not None
            and str(rc_q_sha) != _sha256_hex(question)
        ):
            stored_contract_stale_conflict = True
        rc_end_iso = rule_contract.get("end_date_iso")
        if rc_end_iso is not None and deadline_dt is not None:
            rc_end_dt = parse_timezone_aware_instant(rc_end_iso)
            if rc_end_dt is None or rc_end_dt != deadline_dt:
                stored_contract_stale_conflict = True

    # 1. Inspect outcome-level resolution_source and is_winner (ORM path)
    outcome_winner_name: str | None = None
    outcome_resolution_source: str | None = None
    has_void_outcome_source = False
    multiple_outcome_winners = False
    for outcome in outcomes or ():
        raw_res_src = _outcome_field(outcome, "resolution_source")
        res_src = str(raw_res_src).strip() if isinstance(raw_res_src, str) and raw_res_src.strip() else None
        if res_src in _VOID_RESOLUTION_SOURCES:
            has_void_outcome_source = True
        is_win = _outcome_field(outcome, "is_winner")
        if is_win is True:
            # Never trust heuristic guess-family sources (#754)
            if res_src in GUESS_FAMILY_SOURCES:
                continue
            # On an open market, only Tier-3 authoritative external settlement can
            # stand on its own (`can_write_winner` in `resolution_authority.py`).
            if res_src is not None:
                if not can_write_winner(local_status, res_src):
                    continue
            elif local_status not in _TERMINAL_MARKET_STATUSES and resolved is not True:
                continue
            candidate_name = _normalize_yes_no_result(_outcome_field(outcome, "name"))
            if candidate_name in {"Yes", "No"}:
                if outcome_winner_name is not None and outcome_winner_name != candidate_name:
                    multiple_outcome_winners = True
                outcome_winner_name = candidate_name
                outcome_resolution_source = res_src or "outcome_winner"

    # 2. Inspect producer-stamped Gamma terminal state in `deadline_rule_contract`
    venue_state = (
        ""
        if stored_contract_stale_conflict
        else str(rule_contract.get("venue_terminal_state") or "").strip().lower()
    )
    venue_winner = (
        None
        if stored_contract_stale_conflict
        else _normalize_yes_no_result(rule_contract.get("venue_winner"))
    )

    # 3. Inspect explicit envelope winner
    explicit_winner = _normalize_yes_no_result(winner)
    local_is_resolved_status = (
        local_status in {"resolved", "settled", "finalized", "final"}
        or resolved is True
    )
    local_is_closed_only = (
        local_status in {"closed", "trading_closed"} and not local_is_resolved_status
    )

    # Detect conflicting settlement evidence (e.g. stored proof says Yes while outcome/envelope says No,
    # or stored contract is bound to a different condition/question/cutoff while claiming terminal state).
    distinct_winners = {
        w
        for w in (outcome_winner_name, venue_winner, explicit_winner)
        if w in {"Yes", "No"}
    }
    has_conflicting_evidence = (
        multiple_outcome_winners
        or len(distinct_winners) > 1
        or (
            stored_contract_stale_conflict
            and str(rule_contract.get("venue_terminal_state") or "").strip().lower()
            in {"resolved", "trading_closed", "void"}
        )
        or (
            venue_state == "resolved"
            and venue_winner in {"Yes", "No"}
            and has_void_outcome_source
        )
    )

    if has_conflicting_evidence:
        state = "unknown"
        result = None
        auth_source = "conflicting_settlement_evidence"
    elif (
        local_status in _VOID_MARKET_STATUSES
        or has_void_outcome_source
        or venue_state == "void"
    ):
        state = "void"
        result = None
        auth_source = (
            "outcome_resolution_source"
            if has_void_outcome_source
            else "deadline_rule_contract"
            if venue_state == "void"
            else "market_status"
        )
    elif venue_state == "unknown":
        state = "unknown"
        result = None
        auth_source = "deadline_rule_contract"
    elif venue_state == "resolved" and venue_winner in {"Yes", "No"}:
        state = "resolved"
        result = venue_winner
        auth_source = "deadline_rule_contract"
    elif outcome_winner_name in {"Yes", "No"}:
        state = "resolved"
        result = outcome_winner_name
        auth_source = outcome_resolution_source
    elif (local_is_resolved_status or local_is_closed_only) and explicit_winner in {"Yes", "No"}:
        state = "resolved"
        result = explicit_winner
        auth_source = "market_status"
    elif local_is_resolved_status or local_status == "suspended":
        state = "unknown"
        result = None
        auth_source = "market_status"
    elif (
        venue_state == "trading_closed"
        or venue_settled_since is not None
        or local_is_closed_only
    ):
        state = "trading_closed"
        result = None
        auth_source = (
            "deadline_rule_contract"
            if venue_state == "trading_closed"
            else VENUE_SETTLED_KEY
            if venue_settled_since is not None
            else "market_status"
        )
    elif cutoff_has_passed:
        state = "deadline_passed"
        result = None
        auth_source = "deadline_passed"
    else:
        state = "open"
        result = None
        auth_source = None

    is_settled = state == "resolved"
    is_trading_closed = state == "trading_closed"
    is_deadline_passed = state == "deadline_passed"
    venue_closure_evidence = bool(
        venue_state in {"resolved", "trading_closed", "void"}
        or venue_settled_since is not None
        or local_is_closed_only
        or local_is_resolved_status
        or outcome_winner_name in {"Yes", "No"}
    )
    lagging_local_status = bool(
        state in {"resolved", "trading_closed", "void"}
        and local_status == "open"
        and resolved is not True
    )

    return {
        "state": state,
        "is_settled": is_settled,
        "is_trading_closed": is_trading_closed,
        "is_deadline_passed": is_deadline_passed,
        "venue_closure_evidence": venue_closure_evidence,
        "conflicting_settlement_evidence": has_conflicting_evidence,
        "status": "resolved" if state == "resolved" else local_status,
        "result": result,
        "authoritative_source": auth_source,
        "lagging_local_status": lagging_local_status,
    }


def format_movement_timeframe(
    basis_observed_at: Any,
    endpoint_observed_at: Any,
    *,
    tz_name: str | None = None,
    timezone_name: str | None = None,
    now: Any = None,
) -> dict[str, Any]:
    """Compute truthful movement comparison wording under Direct User Decision Q4 & Section 3D.

    - Requires BOTH `basis_observed_at` and `endpoint_observed_at` (`yes_price_observed_at`)
      to be valid timezone-aware timestamps with `endpoint_observed_at >= basis_observed_at`.
    - When `now` is provided, also checks the reader's current local calendar date:
      - Uses `"since yesterday"` ONLY when `basis_observed_at` is the local calendar day
        before `endpoint_observed_at` (`calendar_day_diff == 1`) AND `endpoint_observed_at`
        is on the reader's current local calendar date (`local_end.date() == local_now.date()`).
      - Uses `"today since <time>"` / `"since <time>"` ONLY when `basis_observed_at` and
        `endpoint_observed_at` fall on the same local calendar day (`calendar_day_diff == 0`)
        AND `endpoint_observed_at` is on the reader's current local calendar date.
      - Otherwise uses explicit calendar-date wording (`"since <Mon D>"`, e.g. `"since Oct 13"`).
    - Never manufactures an observation timestamp from `now`.
    """
    effective_tz_arg = tz_name or timezone_name
    basis_dt = parse_timezone_aware_instant(basis_observed_at)
    end_dt = parse_timezone_aware_instant(endpoint_observed_at)
    if basis_dt is None or end_dt is None or end_dt < basis_dt:
        return {
            "valid": False,
            "calendar_day_diff": None,
            "crosses_previous_calendar_day": False,
            "chip_timeframe": None,
            "sentence_timeframe": None,
            "timezone": effective_tz_arg or "UTC",
        }

    tz: Any = timezone.utc
    effective_tz_name = "UTC"
    if effective_tz_arg:
        try:
            tz = ZoneInfo(effective_tz_arg)
            effective_tz_name = effective_tz_arg
        except ZoneInfoNotFoundError:
            tz = timezone.utc
            effective_tz_name = "UTC"

    local_basis = basis_dt.astimezone(tz)
    local_end = end_dt.astimezone(tz)
    now_dt = parse_timezone_aware_instant(now)
    local_now_date = now_dt.astimezone(tz).date() if now_dt is not None else None
    end_is_reader_today = (
        local_now_date is None or local_end.date() == local_now_date
    )

    day_diff = (local_end.date() - local_basis.date()).days
    if day_diff < 0:
        return {
            "valid": False,
            "calendar_day_diff": day_diff,
            "crosses_previous_calendar_day": False,
            "chip_timeframe": None,
            "sentence_timeframe": None,
            "timezone": effective_tz_name,
        }

    if day_diff == 1 and end_is_reader_today:
        return {
            "valid": True,
            "calendar_day_diff": 1,
            "crosses_previous_calendar_day": True,
            "chip_timeframe": "since yesterday",
            "sentence_timeframe": "since yesterday",
            "timezone": effective_tz_name,
        }

    if day_diff == 0 and end_is_reader_today:
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


def _outcome_observation_dt(outcome: Any) -> datetime | None:
    """Resolve an outcome's observation timestamp strictly from its own lineage (Section 3D).

    - On ORM `FuturesOutcome` or `FuturesOutcomeSnapshot`: delegates to
      `outcome_observed_at(outcome)` (`price_observed_epoch` -> `last_updated`).
    - On a `Mapping` carrier: reads `price_observed_at` or `last_updated` (requiring
      timezone awareness) or integer `price_observed_epoch`.
    - Never falls back to market-level `price_observed_at`, `now`, or `datetime.now`.
    """
    if outcome is None:
        return None
    if not isinstance(outcome, Mapping):
        obs = outcome_observed_at(outcome)
        return parse_timezone_aware_instant(obs)
    for key in ("price_observed_at", "last_updated"):
        raw = outcome.get(key)
        if raw is not None:
            parsed = parse_timezone_aware_instant(raw)
            if parsed is not None:
                return parsed
    epoch = outcome.get("price_observed_epoch")
    if isinstance(epoch, int) and not isinstance(epoch, bool):
        return datetime.fromtimestamp(epoch, tz=timezone.utc)
    return None


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


def _verify_member_rule_equivalence(
    *,
    name: str,
    resolution_date: Any,
    description: str | None,
    market_metadata: Mapping[str, Any],
    external_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Verify rule equivalence and contractual deadline cutoff for a single member (3A / 3B / Gap 1).

    Returns `(rule_verification_dict, parsed_question_dict_or_None)`.
    - If `description` is explicitly supplied, validates `description` directly against
      `name` and `resolution_date`; if `description` fails validation, returns
      `verified=False, status="invalidated_incompatible_rule"` and NEVER falls back
      to stale stored proof in `market_metadata["deadline_rule_contract"]`.
    - If `market_metadata["deadline_rule_contract"]` carries an explicit invalidation or
      missing-rule marker (`verified is False`), honours that status
      (`"invalidated_incompatible_rule"` vs `"missing_rule_description"`).
    - If `market_metadata["deadline_rule_contract"]` carries verified proof, verifies
      its bound `condition_id`, `question_sha256`, `end_date_iso`, and
      `verified_calendar_date` against the current row so stale proof cannot be
      reused after a question, condition, or cutoff change.
    """
    stored_contract = market_metadata.get(DEADLINE_RULE_CONTRACT_KEY)
    rule_contract: dict[str, Any] | None = None

    # 1. If a live `description` is explicitly provided, it is authoritative over any stored contract.
    if isinstance(description, str) and description.strip():
        extracted = extract_polymarket_deadline_rule_contract(
            description,
            question=name,
            end_date=resolution_date,
            condition_id=external_id,
        )
        if extracted is None:
            candidate_q = parse_cumulative_deadline_question(
                name,
                resolution_date,
                cutoff_timezone="America/New_York",
                cutoff_local_time="23:59",
            )
            if candidate_q is None:
                return (
                    {
                        "verified": False,
                        "status": "not_a_deadline_candidate",
                        "reason": "question_or_end_date_cutoff_mismatch",
                        "rule_template_hash": None,
                        "predicate_hash": None,
                        "window_kind": None,
                        "window_start_kind": None,
                        "window_start_instant": None,
                        "nested_window_proven": False,
                        "cutoff_timezone": None,
                        "cutoff_local_time": None,
                        "missing_producer_fields": [],
                    },
                    None,
                )
            return (
                {
                    "verified": False,
                    "status": "invalidated_incompatible_rule",
                    "reason": diagnose_polymarket_deadline_rule_refusal(
                        description,
                        question=name,
                        end_date=resolution_date,
                    ),
                    "rule_template_hash": None,
                    "predicate_hash": None,
                    "window_kind": None,
                    "window_start_kind": None,
                    "window_start_instant": None,
                    "nested_window_proven": False,
                    "cutoff_timezone": None,
                    "cutoff_local_time": None,
                    "missing_producer_fields": [],
                },
                candidate_q,
            )
        rule_contract = extracted

    # 2. Otherwise inspect `market_metadata["deadline_rule_contract"]`
    elif isinstance(stored_contract, Mapping):
        if stored_contract.get("verified") is False:
            status_code = str(
                stored_contract.get("status") or "invalidated_incompatible_rule"
            )
            reason = stored_contract.get("reason")
            candidate_q = parse_cumulative_deadline_question(
                name,
                resolution_date,
                cutoff_timezone="America/New_York",
                cutoff_local_time="23:59",
            )
            if candidate_q is None:
                return (
                    {
                        "verified": False,
                        "status": "not_a_deadline_candidate",
                        "reason": reason,
                        "rule_template_hash": None,
                        "predicate_hash": None,
                        "window_kind": None,
                        "window_start_kind": None,
                        "window_start_instant": None,
                        "nested_window_proven": False,
                        "cutoff_timezone": None,
                        "cutoff_local_time": None,
                        "missing_producer_fields": [],
                    },
                    None,
                )
            return (
                {
                    "verified": False,
                    "status": status_code,
                    "reason": reason,
                    "rule_template_hash": None,
                    "predicate_hash": None,
                    "window_kind": None,
                    "window_start_kind": None,
                    "window_start_instant": None,
                    "nested_window_proven": False,
                    "cutoff_timezone": None,
                    "cutoff_local_time": None,
                    "missing_producer_fields": (
                        [
                            "FuturesMarket.description",
                            f"market_metadata.{DEADLINE_RULE_CONTRACT_KEY}",
                        ]
                        if status_code == "missing_rule_description"
                        else []
                    ),
                },
                candidate_q,
            )

        # Verify identity and content bindings on stored proof before trusting it
        bound_cid = stored_contract.get("condition_id")
        if (
            bound_cid is not None
            and external_id is not None
            and str(bound_cid).strip()
            and str(external_id).strip()
            and str(bound_cid).strip() != str(external_id).strip()
        ):
            candidate_q = parse_cumulative_deadline_question(
                name,
                resolution_date,
                cutoff_timezone="America/New_York",
                cutoff_local_time="23:59",
            )
            return (
                {
                    "verified": False,
                    "status": "stale_bound_condition_id",
                    "reason": "stored_contract_condition_id_mismatch",
                    "rule_template_hash": None,
                    "predicate_hash": None,
                    "window_kind": None,
                    "window_start_kind": None,
                    "window_start_instant": None,
                    "nested_window_proven": False,
                    "cutoff_timezone": None,
                    "cutoff_local_time": None,
                    "missing_producer_fields": [],
                },
                candidate_q,
            )

        bound_q_sha = stored_contract.get("question_sha256")
        if (
            bound_q_sha is not None
            and _sha256_hex(name) is not None
            and str(bound_q_sha) != _sha256_hex(name)
        ):
            candidate_q = parse_cumulative_deadline_question(
                name,
                resolution_date,
                cutoff_timezone="America/New_York",
                cutoff_local_time="23:59",
            )
            return (
                {
                    "verified": False,
                    "status": "stale_bound_question",
                    "reason": "stored_contract_question_sha256_mismatch",
                    "rule_template_hash": None,
                    "predicate_hash": None,
                    "window_kind": None,
                    "window_start_kind": None,
                    "window_start_instant": None,
                    "nested_window_proven": False,
                    "cutoff_timezone": None,
                    "cutoff_local_time": None,
                    "missing_producer_fields": [],
                },
                candidate_q,
            )

        bound_end_iso = stored_contract.get("end_date_iso")
        if bound_end_iso is not None:
            bound_end_dt = parse_timezone_aware_instant(bound_end_iso)
            current_end_dt = parse_timezone_aware_instant(resolution_date)
            if bound_end_dt is None or current_end_dt is None or bound_end_dt != current_end_dt:
                candidate_q = parse_cumulative_deadline_question(
                    name,
                    resolution_date,
                    cutoff_timezone="America/New_York",
                    cutoff_local_time="23:59",
                )
                return (
                    {
                        "verified": False,
                        "status": "stale_bound_cutoff",
                        "reason": "stored_contract_end_date_mismatch",
                        "rule_template_hash": None,
                        "predicate_hash": None,
                        "window_kind": None,
                        "window_start_kind": None,
                        "window_start_instant": None,
                        "nested_window_proven": False,
                        "cutoff_timezone": None,
                        "cutoff_local_time": None,
                        "missing_producer_fields": [],
                    },
                    candidate_q,
                )

        rule_template_hash = stored_contract.get("rule_template_hash")
        cutoff_tz = stored_contract.get("cutoff_timezone")
        cutoff_time = stored_contract.get("cutoff_local_time")
        window_kind = stored_contract.get("window_kind")
        resolves_yes = stored_contract.get("resolves_yes_on_affirmative")
        if (
            isinstance(rule_template_hash, str)
            and len(rule_template_hash.strip()) >= 8
            and isinstance(cutoff_tz, str)
            and isinstance(cutoff_time, str)
            and window_kind == "cumulative_from_creation"
            and resolves_yes is True
        ):
            rule_contract = dict(stored_contract)

    if rule_contract is not None:
        cutoff_tz = str(rule_contract["cutoff_timezone"])
        cutoff_time = str(rule_contract["cutoff_local_time"])
        parsed_q = parse_cumulative_deadline_question(
            name,
            resolution_date,
            cutoff_timezone=cutoff_tz,
            cutoff_local_time=cutoff_time,
        )
        if parsed_q is None:
            return (
                {
                    "verified": False,
                    "status": "contractual_cutoff_mismatch",
                    "rule_template_hash": None,
                    "predicate_hash": None,
                    "window_kind": None,
                    "window_start_kind": None,
                    "window_start_instant": None,
                    "nested_window_proven": False,
                    "cutoff_timezone": cutoff_tz,
                    "cutoff_local_time": cutoff_time,
                    "missing_producer_fields": [],
                },
                None,
            )
        verified_cal = rule_contract.get("verified_calendar_date")
        if verified_cal and verified_cal != parsed_q["calendar_date"]:
            return (
                {
                    "verified": False,
                    "status": "rule_calendar_date_mismatch",
                    "rule_template_hash": None,
                    "predicate_hash": None,
                    "window_kind": None,
                    "window_start_kind": None,
                    "window_start_instant": None,
                    "nested_window_proven": False,
                    "cutoff_timezone": cutoff_tz,
                    "cutoff_local_time": cutoff_time,
                    "missing_producer_fields": [],
                },
                None,
            )
        group_item_title = rule_contract.get("group_item_title")
        if isinstance(group_item_title, str) and group_item_title.strip():
            gi_slot = _parse_calendar_date_slot(group_item_title)
            q_year, q_month, q_day = (
                int(part) for part in parsed_q["calendar_date"].split("-")
            )
            if gi_slot is None or (gi_slot[0], gi_slot[1]) != (q_month, q_day):
                return (
                    {
                        "verified": False,
                        "status": "group_item_title_mismatch",
                        "rule_template_hash": None,
                        "predicate_hash": None,
                        "window_kind": None,
                        "window_start_kind": None,
                        "window_start_instant": None,
                        "nested_window_proven": False,
                        "cutoff_timezone": cutoff_tz,
                        "cutoff_local_time": cutoff_time,
                        "missing_producer_fields": [],
                    },
                    None,
                )
            if gi_slot[2] is not None and gi_slot[2] != q_year:
                return (
                    {
                        "verified": False,
                        "status": "group_item_title_year_mismatch",
                        "rule_template_hash": None,
                        "predicate_hash": None,
                        "window_kind": None,
                        "window_start_kind": None,
                        "window_start_instant": None,
                        "nested_window_proven": False,
                        "cutoff_timezone": cutoff_tz,
                        "cutoff_local_time": cutoff_time,
                        "missing_producer_fields": [],
                    },
                    None,
                )
        raw_w_start = rule_contract.get("window_start_instant")
        parsed_w_start = parse_timezone_aware_instant(raw_w_start)
        return (
            {
                "verified": True,
                "status": "verified",
                "rule_template_hash": str(rule_contract["rule_template_hash"]),
                "predicate_hash": (
                    str(rule_contract["predicate_hash"])
                    if rule_contract.get("predicate_hash")
                    else None
                ),
                "window_kind": "cumulative_from_creation",
                "window_start_kind": str(
                    rule_contract.get("window_start_kind") or "market_creation"
                ),
                "window_start_instant": (
                    parsed_w_start.isoformat() if parsed_w_start is not None else None
                ),
                "nested_window_proven": False,
                "cutoff_timezone": cutoff_tz,
                "cutoff_local_time": cutoff_time,
                "group_item_title": rule_contract.get("group_item_title"),
                "condition_id": rule_contract.get("condition_id") or external_id,
                "question_sha256": rule_contract.get("question_sha256") or _sha256_hex(name),
                "description_sha256": rule_contract.get("description_sha256"),
                "end_date_iso": (
                    rule_contract.get("end_date_iso")
                    or parsed_q["deadline_instant"]
                ),
                "missing_producer_fields": [],
            },
            parsed_q,
        )

    # No verified rule contract or description on this row: check whether it is even
    # a structural candidate so we can distinguish "not a deadline question at all"
    # from "candidate blocked on missing upstream rule-equivalence evidence".
    candidate_q = parse_cumulative_deadline_question(
        name,
        resolution_date,
        cutoff_timezone="America/New_York",
        cutoff_local_time="23:59",
    )
    if candidate_q is None:
        return (
            {
                "verified": False,
                "status": "not_a_deadline_candidate",
                "rule_template_hash": None,
                "predicate_hash": None,
                "window_kind": None,
                "window_start_kind": None,
                "window_start_instant": None,
                "nested_window_proven": False,
                "cutoff_timezone": None,
                "cutoff_local_time": None,
                "missing_producer_fields": [],
            },
            None,
        )
    return (
        {
            "verified": False,
            "status": "missing_upstream_rule_text",
            "rule_template_hash": None,
            "predicate_hash": None,
            "window_kind": None,
            "window_start_kind": None,
            "window_start_instant": None,
            "nested_window_proven": False,
            "cutoff_timezone": None,
            "cutoff_local_time": None,
            "missing_producer_fields": [
                "FuturesMarket.description",
                f"market_metadata.{DEADLINE_RULE_CONTRACT_KEY}",
            ],
        },
        candidate_q,
    )


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
    description: str | None = None,
    market_metadata: Any = None,
    outcomes: Sequence[Any] | None = None,
    top_outcomes_data: Sequence[Mapping[str, Any]] | None = None,
    withheld_outcome_ids: Sequence[int] | set[int] | frozenset[int] | None = None,
    stale_outcome_ids: Sequence[int] | set[int] | frozenset[int] | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any] | None:
    """Build the producer contract for a single cumulative deadline-family member.

    Returns `None` when the market is not a cumulative deadline-family candidate
    or lacks required condition/outcome/deadline identity. When the market is a
    structural candidate but lacks upstream rule-equivalence proof (`description` /
    `market_metadata["deadline_rule_contract"]`) or has invalidated rule proof,
    returns the contract with `rule_verification.verified = False` so
    `verify_and_select_deadline_family` refuses grouping with the exact reason.
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
    if not clean_source or not clean_group_id or not clean_external_id or not name:
        return None

    meta_dict = market_metadata if isinstance(market_metadata, Mapping) else {}
    rule_verification, parsed_q = _verify_member_rule_equivalence(
        name=str(name),
        resolution_date=resolution_date,
        description=description,
        market_metadata=meta_dict,
        external_id=clean_external_id,
    )
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

    reference_dt = parse_timezone_aware_instant(now)

    settlement = extract_settlement_evidence(
        status=status,
        resolved=resolved,
        winner=winner,
        market_metadata=meta_dict,
        outcomes=outcomes,
        deadline_instant=parsed_q["deadline_instant"],
        now=reference_dt,
        external_id=clean_external_id,
        question=str(name),
    )

    # Section 3D: Observation timestamp comes strictly from the selected Yes outcome.
    # Missing observation timestamps remain None; never substitute `now` or `price_observed_at`.
    yes_observed_dt = _outcome_observation_dt(yes_outcome)
    no_observed_dt = _outcome_observation_dt(no_outcome)
    yes_price_observed_at = (
        yes_observed_dt.isoformat() if yes_observed_dt is not None else None
    )

    # Existing supported freshness policies (`prices_have_stopped` and `stale_observation_keys`)
    newest_board_dt = max(
        (dt for dt in (yes_observed_dt, no_observed_dt) if dt is not None),
        default=None,
    )
    board_prices_stopped = bool(
        reference_dt is not None
        and newest_board_dt is not None
        and prices_have_stopped(newest_board_dt, reference_dt)
    )
    stale_leg_ids = set(
        stale_observation_keys(
            [(yes_outcome_id, yes_observed_dt), (no_outcome_id, no_observed_dt)]
        )
    )
    if stale_outcome_ids:
        stale_leg_ids |= {int(x) for x in stale_outcome_ids}
    yes_observation_stale = (
        board_prices_stopped
        or (yes_outcome_id in stale_leg_ids)
        or (
            reference_dt is not None
            and yes_observed_dt is not None
            and (reference_dt - yes_observed_dt).total_seconds() < 0
        )
    )

    dummy_carrier = type("_Carrier", (), {})()
    dummy_carrier.__dict__["market_metadata"] = meta_dict
    dummy_carrier.__dict__["source"] = clean_source

    bank = dated_movement_basis(dummy_carrier)
    admits_zero = dated_basis_admits_zero(dummy_carrier)
    basis_price, basis_observed_at = read_dated_basis_entry(
        bank.get(str(yes_outcome_id))
    )

    basis_age_hours: float | None = None
    basis_in_window = False
    if basis_observed_at is not None and reference_dt is not None:
        basis_age_hours = (reference_dt - basis_observed_at).total_seconds() / 3600.0
        basis_in_window = (
            DATED_BASIS_MIN_AGE_HOURS <= basis_age_hours <= DATED_BASIS_WINDOW_HOURS
        )

    # For a movement comparison to be valid, `yes_observed_dt` MUST be present,
    # non-stale, separated from `basis_observed_at` by the 12-24h dated window,
    # and observed within the 24h window relative to `reference_dt`.
    endpoint_valid_for_basis = bool(
        yes_observed_dt is not None
        and basis_observed_at is not None
        and (
            DATED_BASIS_MIN_AGE_HOURS
            <= (yes_observed_dt - basis_observed_at).total_seconds() / 3600.0
            <= DATED_BASIS_WINDOW_HOURS
        )
        and (
            reference_dt is None
            or 0.0
            <= (reference_dt - yes_observed_dt).total_seconds() / 3600.0
            <= DATED_BASIS_WINDOW_HOURS
        )
    )

    supported_move: float | None = None
    supported_move_points: float | None = None
    settlement_state = settlement["state"]
    if settlement_state == "resolved":
        movement_status = "settled_suppressed"
    elif settlement_state == "trading_closed":
        movement_status = "trading_closed_suppressed"
    elif settlement_state == "deadline_passed":
        movement_status = "deadline_passed_suppressed"
    elif settlement_state in {"void", "unknown"}:
        movement_status = "settled_suppressed"
    elif yes_probability is None:
        movement_status = "unpriced"
    elif yes_probability <= DEADLINE_MOVER_MIN_PROBABILITY:
        movement_status = "placeholder_floor_suppressed"
    elif stored_change is None:
        movement_status = "no_stored_claim"
    elif stored_change == 0.0 and not admits_zero:
        movement_status = "zero_stored_claim_refused"
    elif basis_price is None or basis_observed_at is None:
        movement_status = "missing_or_invalid_basis"
    elif reference_dt is None or not basis_in_window:
        movement_status = "basis_out_of_window"
    elif yes_observed_dt is None:
        movement_status = "missing_observation_timestamp"
    elif yes_observation_stale or not endpoint_valid_for_basis:
        movement_status = "stale_price_observation"
    else:
        raw_move = yes_probability - basis_price
        supported_move = round(raw_move, 6)
        supported_move_points = round(raw_move * 100.0, 2)
        if abs(supported_move) < 1e-9:
            movement_status = "measured_zero"
        elif abs(supported_move) < DEADLINE_MODERATE_MIN_MOVEMENT_FRACTION:
            movement_status = "sub_threshold"
        elif abs(supported_move) < DEADLINE_HERO_MIN_MOVEMENT_FRACTION:
            movement_status = "moderate"
        else:
            movement_status = "hero"

    timeframe = (
        format_movement_timeframe(
            basis_observed_at,
            yes_observed_dt,
            tz_name="UTC",
            now=reference_dt,
        )
        if supported_move is not None
        and basis_observed_at is not None
        and yes_observed_dt is not None
        else None
    )

    # Q8 check (Section 3D): a genuinely open question at 97%+ on `Yes` remains eligible
    # locally ONLY when it has a verified rule contract, a non-stale `yes_observed_dt`,
    # and a qualifying recent dated move (`moderate` or `hero`, >= 2 pts) on `Yes`.
    # Near-zero (`<= 3%` `Yes`) questions remain suppressed (`Q8d`).
    is_near_certain = bool(
        yes_probability is not None and yes_probability >= NEAR_CERTAIN_THRESHOLD
    )
    deadline_dt = parse_timezone_aware_instant(parsed_q["deadline_instant"])
    deadline_in_future = bool(
        deadline_dt is not None
        and reference_dt is not None
        and deadline_dt > reference_dt
    )
    near_certain_open_eligible = bool(
        rule_verification["verified"]
        and settlement["state"] == "open"
        and deadline_in_future
        and yes_observed_dt is not None
        and not yes_observation_stale
        and is_near_certain
        and movement_status in {"moderate", "hero"}
        and supported_move is not None
        and abs(supported_move) >= DEADLINE_MODERATE_MIN_MOVEMENT_FRACTION
    )

    rule_contract_meta = (
        meta_dict.get(DEADLINE_RULE_CONTRACT_KEY)
        if isinstance(meta_dict.get(DEADLINE_RULE_CONTRACT_KEY), Mapping)
        else {}
    )
    raw_market_count = (
        meta_dict.get("market_count")
        or meta_dict.get("provider_market_count")
        or rule_contract_meta.get("provider_market_count")
    )
    provider_market_count: int | None = None
    if (
        isinstance(raw_market_count, int)
        and not isinstance(raw_market_count, bool)
        and raw_market_count > 0
    ):
        provider_market_count = raw_market_count

    raw_verified_family_count = meta_dict.get("verified_family_count")
    verified_family_count: int | None = None
    if (
        isinstance(raw_verified_family_count, int)
        and not isinstance(raw_verified_family_count, bool)
        and raw_verified_family_count > 0
    ):
        verified_family_count = raw_verified_family_count

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
        "cutoff_timezone": rule_verification.get("cutoff_timezone"),
        "cutoff_local_time": rule_verification.get("cutoff_local_time"),
        "rule_template_hash": rule_verification.get("rule_template_hash"),
        "rule_verification": rule_verification,
        "yes_outcome_id": yes_outcome_id,
        "yes_outcome_name": "Yes",
        "yes_external_id": str(yes_external_id) if yes_external_id is not None else None,
        "no_outcome_id": no_outcome_id,
        "no_external_id": str(no_external_id) if no_external_id is not None else None,
        "yes_probability": yes_probability,
        "yes_rendered_percent": yes_rendered_percent,
        "no_probability": no_probability,
        "price_observed_at": yes_price_observed_at,
        "yes_price_observed_at": yes_price_observed_at,
        "yes_observation_fresh": (yes_observed_dt is not None and not yes_observation_stale),
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
        "timeframe": timeframe,
        "settlement": settlement,
        "is_near_certain": is_near_certain,
        "near_certain_open_eligible": near_certain_open_eligible,
        "provider_market_count": provider_market_count,
        "verified_family_count": verified_family_count,
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
    description: str | None = None,
) -> bool:
    """Q8 helper for `_market_runtime_filter_trace` in `routes/feed.py`.

    A genuinely open cumulative deadline-family question at 97%+ remains eligible
    ONLY when it carries a verified rule contract, a fresh `Yes` price observation,
    and a qualifying recent dated move (`>= 2` pts) on its bound `Yes` outcome
    inside the 12h–24h dated-basis window.
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
        description=description,
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
    now: datetime | str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Re-validate a serialized `deadline_member` contract dict on the bundler side."""
    if not isinstance(member_contract, Mapping):
        return None, "invalid_or_missing_member_contract"

    rule_ver = member_contract.get("rule_verification")
    if isinstance(rule_ver, Mapping) and rule_ver.get("verified") is not True:
        status_code = str(rule_ver.get("status") or "")
        if status_code in {"missing_upstream_rule_text", "missing_rule_description"}:
            return None, "missing_rule_equivalence_proof"
        if status_code == "invalidated_incompatible_rule":
            return None, "invalidated_incompatible_rule"
        if status_code.startswith("stale_bound_"):
            return None, f"stale_rule_proof:{status_code}"
        return None, f"unverified_rule_contract:{status_code or 'unknown'}"

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
        return None, "invalid_or_missing_member_contract"

    if not isinstance(rule_ver, Mapping):
        return None, "missing_rule_equivalence_proof"

    rule_hash = rule_ver.get("rule_template_hash")
    cutoff_tz = rule_ver.get("cutoff_timezone")
    cutoff_time = rule_ver.get("cutoff_local_time")
    window_kind = rule_ver.get("window_kind")
    if (
        not isinstance(rule_hash, str)
        or len(rule_hash.strip()) < 8
        or not isinstance(cutoff_tz, str)
        or not isinstance(cutoff_time, str)
        or window_kind != "cumulative_from_creation"
    ):
        return None, "missing_rule_equivalence_proof"

    settlement_in = member_contract.get("settlement")
    state_in = (
        str(settlement_in.get("state") or "open")
        if isinstance(settlement_in, Mapping)
        else "open"
    )
    status_in = (
        str(settlement_in.get("status") or "open")
        if isinstance(settlement_in, Mapping)
        else "open"
    )
    result_in = (
        settlement_in.get("result")
        if isinstance(settlement_in, Mapping)
        else None
    )
    auth_src_in = (
        settlement_in.get("authoritative_source")
        if isinstance(settlement_in, Mapping)
        else None
    )

    yes_obs_iso = member_contract.get("price_observed_at")
    synthetic_outcomes = [
        {
            "id": yes_outcome_id,
            "name": "Yes",
            "external_id": member_contract.get("yes_external_id") or f"yes-{yes_outcome_id}",
            "current_probability": member_contract.get("yes_probability"),
            "probability_change_24h": member_contract.get("stored_movement_claim"),
            "price_observed_at": yes_obs_iso,
            "is_winner": True if state_in == "resolved" and result_in == "Yes" else False,
            "resolution_source": (
                "api_settlement"
                if state_in == "resolved" and result_in == "Yes"
                else "ungradeable_result"
                if state_in == "void"
                else None
            ),
        },
        {
            "id": no_outcome_id,
            "name": "No",
            "external_id": member_contract.get("no_external_id") or f"no-{no_outcome_id}",
            "current_probability": member_contract.get("no_probability"),
            "probability_change_24h": None,
            "price_observed_at": yes_obs_iso,
            "is_winner": True if state_in == "resolved" and result_in == "No" else False,
            "resolution_source": (
                "api_settlement"
                if state_in == "resolved" and result_in == "No"
                else None
            ),
        },
    ]

    basis_info = member_contract.get("movement_basis")
    synthetic_meta: dict[str, Any] = {
        DEADLINE_RULE_CONTRACT_KEY: {
            "schema": "polymarket_cumulative_deadline_v1",
            "verified": True,
            "status": "verified",
            "condition_id": str(external_id),
            "question_sha256": _sha256_hex(str(name)),
            "end_date_iso": str(deadline_instant),
            "rule_template_hash": rule_hash,
            "predicate_hash": rule_ver.get("predicate_hash"),
            "window_kind": "cumulative_from_creation",
            "window_start_kind": rule_ver.get("window_start_kind") or "market_creation",
            "window_start_instant": rule_ver.get("window_start_instant"),
            "nested_window_proven": False,
            "resolves_yes_on_affirmative": True,
            "cutoff_timezone": cutoff_tz,
            "cutoff_local_time": cutoff_time,
            "group_item_title": rule_ver.get("group_item_title"),
            "verified_calendar_date": member_contract.get("calendar_date"),
            "venue_closed": state_in in {"trading_closed", "resolved", "void"},
            "uma_resolution_status": (
                "resolved" if state_in in {"resolved", "void"} else None
            ),
            "venue_terminal_state": (
                state_in
                if state_in in {"resolved", "trading_closed", "void"}
                and auth_src_in == "deadline_rule_contract"
                else "open"
            ),
            "venue_winner": result_in if state_in == "resolved" else None,
        }
    }
    if state_in == "trading_closed" and auth_src_in == VENUE_SETTLED_KEY:
        synthetic_meta[VENUE_SETTLED_KEY] = "2026-10-14T00:00:00+00:00"

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
    if member_contract.get("verified_family_count") is not None:
        synthetic_meta["verified_family_count"] = member_contract.get("verified_family_count")

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
        status=(
            "resolved"
            if state_in == "unknown"
            else "closed"
            if state_in == "trading_closed"
            and auth_src_in not in {"deadline_rule_contract", VENUE_SETTLED_KEY}
            else status_in
        ),
        resolved=True if state_in in {"resolved", "unknown"} else False,
        winner=result_in if state_in == "resolved" else None,
        resolution_date=deadline_instant,
        market_metadata=synthetic_meta,
        outcomes=synthetic_outcomes,
        top_outcomes_data=top_outcomes_in,
        now=now,
    )
    if rebuilt is None:
        return None, "invalid_or_missing_member_contract"
    if state_in == "deadline_passed" and rebuilt["settlement"]["state"] == "open":
        rebuilt["settlement"] = {
            "state": "deadline_passed",
            "is_settled": False,
            "is_trading_closed": False,
            "is_deadline_passed": True,
            "status": status_in,
            "result": None,
            "authoritative_source": "deadline_passed",
            "lagging_local_status": False,
        }
        rebuilt["movement_status"] = "deadline_passed_suppressed"
        rebuilt["supported_move"] = None
        rebuilt["supported_move_points"] = None
        rebuilt["show_hero_movement_chip"] = False
        rebuilt["show_row_movement_badge"] = False
    if isinstance(settlement_in, Mapping) and settlement_in.get("lagging_local_status"):
        rebuilt["settlement"]["lagging_local_status"] = True
    return rebuilt, None


def verify_and_select_deadline_family(
    member_contracts: Sequence[Mapping[str, Any]],
    *,
    now: datetime | str | None = None,
    reader_tz: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Verify a candidate set of deadline-family member contracts and select the representative.

    Returns `(family_payload, None)` on success, or `(None, rejection_reason)` when
    any rule-equivalence, identity, predicate, deadline, outcome-binding, terminal-state,
    or eligibility check fails.
    """
    if not member_contracts or len(member_contracts) < 2:
        return None, "fewer_than_two_members"

    validated: list[dict[str, Any]] = []
    for raw in member_contracts:
        checked, err = _validate_member_contract_dict(raw, now=now)
        if checked is None:
            return None, err or "invalid_or_missing_member_contract"
        validated.append(checked)

    sources = {m["source"] for m in validated}
    group_ids = {m["group_id"] for m in validated}
    if len(sources) != 1 or len(group_ids) != 1:
        return None, "mixed_provider_or_group_id"

    # Section 3A: Verify rule-template and cutoff equivalence across all members
    rule_hashes = {m["rule_verification"]["rule_template_hash"] for m in validated}
    cutoff_tzs = {m["rule_verification"]["cutoff_timezone"] for m in validated}
    cutoff_times = {m["rule_verification"]["cutoff_local_time"] for m in validated}
    window_kinds = {m["rule_verification"]["window_kind"] for m in validated}
    if (
        len(rule_hashes) != 1
        or None in rule_hashes
        or len(cutoff_tzs) != 1
        or len(cutoff_times) != 1
        or window_kinds != {"cumulative_from_creation"}
    ):
        return None, "mismatched_rule_template_or_cutoff"

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

    # Section 3C: Refuse families containing void or unknown terminal members
    states = [m["settlement"]["state"] for m in ascending]
    if "void" in states:
        return None, "member_void_or_retracted"
    if "unknown" in states:
        return None, "member_settlement_result_unknown"

    # Lower-bound window provenance ("between market creation and ..."):
    # Identical template text does not automatically mean identical start instants.
    # Nested cumulative windows across members are proven ONLY when every member
    # carries an explicit `window_start_instant` and all start instants are identical.
    start_instants = [
        m["rule_verification"].get("window_start_instant") for m in ascending
    ]
    nested_window_proven = bool(
        all(s is not None for s in start_instants) and len(set(start_instants)) == 1
    )
    for m in ascending:
        m["rule_verification"]["nested_window_proven"] = nested_window_proven

    if nested_window_proven:
        saw_resolved_yes = False
        for m in ascending:
            if m["settlement"]["state"] == "resolved":
                if m["settlement"]["result"] == "Yes":
                    saw_resolved_yes = True
                elif saw_resolved_yes and m["settlement"]["result"] == "No":
                    return None, "contradictory_cumulative_settlement_results"

    source = ascending[0]["source"]
    group_id = ascending[0]["group_id"]
    story_key = deadline_family_story_key(source, group_id)
    display_stem = ascending[0]["display_stem"]
    shared_question = ascending[0]["shared_question"]

    all_resolved = all(
        m["settlement"]["state"] == "resolved"
        and m["settlement"].get("result") in {"Yes", "No"}
        for m in ascending
    )
    if all_resolved:
        yes_winners = [
            m for m in ascending if m["settlement"].get("result") == "Yes"
        ]
        rep = yes_winners[0] if yes_winners else ascending[-1]
        selection_reason = "settled_family"
        family_state = "settled"
    else:
        family_state = "open"
        running_pct: int | None = None
        for m in ascending:
            if m["settlement"]["state"] != "open":
                continue
            pct = m.get("yes_rendered_percent")
            if pct is None:
                continue
            pct_int = int(pct)
            if running_pct is not None and pct_int < running_pct:
                return None, "ladder_refused"
            running_pct = pct_int if running_pct is None else max(running_pct, pct_int)

        # Filter to open, priced members that are eligible (excluding `deadline_passed`,
        # `trading_closed`, and `resolved`, and applying Q8 for >=97% members)
        eligible_open_priced = [
            m
            for m in ascending
            if m["settlement"]["state"] == "open"
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

    # Compute timeframe in requested timezone (`reader_tz` or UTC) strictly from
    # `(basis_observed_at, rep.price_observed_at)`, checking reader-local today against `now`.
    rep_basis = rep.get("movement_basis")
    rep_timeframe = (
        format_movement_timeframe(
            rep_basis.get("observed_at") if isinstance(rep_basis, Mapping) else None,
            rep.get("price_observed_at"),
            tz_name=reader_tz or "UTC",
            now=now,
        )
        if rep.get("supported_move") is not None
        and isinstance(rep_basis, Mapping)
        and rep.get("price_observed_at") is not None
        else None
    )

    # 6F & Gap 4: Distinguish represented family members from verified family total
    # and raw provider event market count.
    represented_count = len(ascending)
    known_provider_counts = {
        int(m["provider_market_count"])
        for m in ascending
        if m.get("provider_market_count") is not None
        and int(m["provider_market_count"]) >= represented_count
    }
    provider_market_count = (
        next(iter(known_provider_counts)) if len(known_provider_counts) == 1 else None
    )

    known_verified_counts = {
        int(m["verified_family_count"])
        for m in ascending
        if m.get("verified_family_count") is not None
        and int(m["verified_family_count"]) >= represented_count
    }
    verified_family_count = (
        next(iter(known_verified_counts))
        if len(known_verified_counts) == 1
        else represented_count
    )

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
            "rule_template_hash": ascending[0]["rule_verification"]["rule_template_hash"],
            "window_start_kind": ascending[0]["rule_verification"].get("window_start_kind")
            or "market_creation",
            "nested_window_proven": nested_window_proven,
            "cutoff_timezone": ascending[0]["rule_verification"]["cutoff_timezone"],
            "cutoff_local_time": ascending[0]["rule_verification"]["cutoff_local_time"],
            "representative_market_id": rep["market_id"],
            "representative_outcome_id": rep["yes_outcome_id"],
            "representative_deadline_label": rep["deadline_label"],
            "selection_reason": selection_reason,
            "tie_break_rule": DETERMINISTIC_TIE_BREAK_RULE,
            "hero_min_movement_points": DEADLINE_HERO_MIN_MOVEMENT_POINTS,
            "moderate_min_movement_points": DEADLINE_MODERATE_MIN_MOVEMENT_POINTS,
            "represented_count": represented_count,
            "verified_family_count": verified_family_count,
            "provider_market_count": provider_market_count,
            "inventory_complete": inventory_complete,
            "representative_timeframe": rep_timeframe,
            "members": ascending,
        },
        None,
    )


__all__ = [
    "DEADLINE_FAMILY_STORY_PREFIX",
    "DEADLINE_RULE_CONTRACT_KEY",
    "DEADLINE_HERO_MIN_MOVEMENT_POINTS",
    "DEADLINE_HERO_MIN_MOVEMENT_FRACTION",
    "DEADLINE_MODERATE_MIN_MOVEMENT_POINTS",
    "DEADLINE_MODERATE_MIN_MOVEMENT_FRACTION",
    "DETERMINISTIC_TIE_BREAK_RULE",
    "is_deadline_family_story_key",
    "deadline_family_story_key",
    "parse_timezone_aware_instant",
    "is_verified_deadline_rule_contract",
    "merge_submarket_metadata_for_upsert",
    "diagnose_polymarket_deadline_rule_refusal",
    "extract_polymarket_deadline_rule_contract",
    "build_polymarket_submarket_deadline_contract",
    "parse_cumulative_deadline_question",
    "extract_settlement_evidence",
    "format_movement_timeframe",
    "build_deadline_member_contract",
    "qualifies_for_deadline_near_certain_exception",
    "verify_and_select_deadline_family",
]
