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

    # Extract venue terminal state from real Gamma market fields when present
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

    contract: dict[str, Any] = {
        "schema": "polymarket_cumulative_deadline_v1",
        "rule_template_hash": rule_template_hash,
        "predicate_hash": predicate_hash,
        "window_kind": "cumulative_from_creation",
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
    in hand during `_process_event_batch`. Returns a verified `deadline_rule_contract`
    dict only when `market` is a cumulative deadline sub-market with verified rule
    text and matching contractual cutoff timestamp; returns `None` for all other
    sub-markets so non-deadline markets are untouched.
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
    if not question or not description or end_date is None:
        return None

    return extract_polymarket_deadline_rule_contract(
        description,
        question=question,
        group_item_title=getattr(market, "group_item_title", None),
        end_date=end_date,
        closed=getattr(market, "closed", False),
        uma_resolution_status=getattr(market, "uma_resolution_status", None),
        outcomes=getattr(market, "outcomes", None),
        outcome_prices=getattr(market, "outcome_prices", None),
        provider_market_count=len(markets_list),
    )


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
) -> dict[str, Any]:
    """Classify terminal/settlement state using only real producer fields (Section 3C).

    Keeps five states strictly distinct:
    - `"open"`: Market is open, before `deadline_instant`, with no venue/outcome
      settlement signal.
    - `"trading_closed"`: Trading has closed (`market_metadata[VENUE_SETTLED_KEY]`
      or Gamma `venue_closed=True` without `uma_resolution_status="resolved"`, or
      `now >= deadline_instant` on an `"open"` row), result not yet known (`result=None`).
    - `"resolved"`: Result is known and settled with a specific winning outcome
      (`result` is `"Yes"` or `"No"`), supported by:
      1. `FuturesOutcome.is_winner is True` with a non-guess `resolution_source`
         permitted by `app.utils.resolution_authority.can_write_winner`, or
      2. Producer-stamped Gamma `venue_terminal_state == "resolved"` with
         `venue_winner in {"Yes", "No"}` (`closed=True`, `uma_resolution_status="resolved"`,
         and exact `[1.0, 0.0]` / `[0.0, 1.0]` outcome prices), or
      3. Explicit verified `winner` in `{"Yes", "No"}` on a settled envelope.
    - `"void"`: Void, canceled, retracted (`resolution_source` in `_VOID_RESOLUTION_SOURCES`),
      or 50/50 split resolution (`result=None`).
    - `"unknown"`: Market has terminal status (`status in {"resolved", "closed", "suspended"}`
      or `resolved is True`) but the winning outcome is not carried on the current
      projection/wire (e.g. `FuturesMarketSnapshot` where `OUTCOME_ROW_COLUMNS` omits
      `is_winner` and no venue winner was stamped). Never guesses a winner from prices.
    """
    local_status = str(status or "open").strip().lower()
    meta = market_metadata if isinstance(market_metadata, Mapping) else {}
    rule_contract = (
        meta.get(DEADLINE_RULE_CONTRACT_KEY)
        if isinstance(meta.get(DEADLINE_RULE_CONTRACT_KEY), Mapping)
        else {}
    )
    venue_settled_since = meta.get(VENUE_SETTLED_KEY)

    # 1. Inspect outcome-level resolution_source and is_winner (ORM path)
    outcome_winner_name: str | None = None
    outcome_resolution_source: str | None = None
    has_void_outcome_source = False
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
                outcome_winner_name = candidate_name
                outcome_resolution_source = res_src or "outcome_winner"
                break

    # 2. Inspect producer-stamped Gamma terminal state in `deadline_rule_contract`
    venue_state = str(rule_contract.get("venue_terminal_state") or "").strip().lower()
    venue_winner = _normalize_yes_no_result(rule_contract.get("venue_winner"))

    # 3. Inspect explicit envelope winner
    explicit_winner = _normalize_yes_no_result(winner)
    local_is_terminal = local_status in _TERMINAL_MARKET_STATUSES or resolved is True

    # Classify into one of: "void", "resolved", "trading_closed", "unknown", "open"
    if (
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
    elif venue_state == "resolved" and venue_winner in {"Yes", "No"}:
        state = "resolved"
        result = venue_winner
        auth_source = "deadline_rule_contract"
    elif outcome_winner_name in {"Yes", "No"}:
        state = "resolved"
        result = outcome_winner_name
        auth_source = outcome_resolution_source
    elif local_is_terminal and explicit_winner in {"Yes", "No"}:
        state = "resolved"
        result = explicit_winner
        auth_source = "market_status"
    elif venue_state == "trading_closed" or (
        venue_settled_since is not None and not local_is_terminal
    ):
        state = "trading_closed"
        result = None
        auth_source = (
            "deadline_rule_contract"
            if venue_state == "trading_closed"
            else VENUE_SETTLED_KEY
        )
    elif local_is_terminal or local_status == "suspended":
        state = "unknown"
        result = None
        auth_source = "market_status"
    else:
        deadline_dt = parse_timezone_aware_instant(deadline_instant)
        now_dt = parse_timezone_aware_instant(now)
        if deadline_dt is not None and now_dt is not None and now_dt >= deadline_dt:
            state = "trading_closed"
            result = None
            auth_source = "deadline_passed"
        else:
            state = "open"
            result = None
            auth_source = None

    is_settled = state != "open"
    lagging_local_status = bool(
        state in {"resolved", "trading_closed", "void"}
        and local_status == "open"
        and resolved is not True
    )

    return {
        "state": state,
        "is_settled": is_settled,
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
) -> dict[str, Any]:
    """Compute truthful movement comparison wording under Direct User Decision Q4 & Section 3D.

    - Requires BOTH `basis_observed_at` and `endpoint_observed_at` (`yes_price_observed_at`)
      to be valid timezone-aware timestamps with `endpoint_observed_at >= basis_observed_at`.
    - Uses `"since yesterday"` ONLY when `basis_observed_at` and `endpoint_observed_at`
      genuinely cross from the previous calendar day (`calendar_day_diff == 1`)
      in the target timezone.
    - When both timestamps fall on the same local calendar day (`calendar_day_diff == 0`),
      even if 12–24 hours apart, uses truthful same-day time wording
      (`"today since <time>"` / `"since <time>"`), never `"since yesterday"`.
    """
    basis_dt = parse_timezone_aware_instant(basis_observed_at)
    end_dt = parse_timezone_aware_instant(endpoint_observed_at)
    if basis_dt is None or end_dt is None or end_dt < basis_dt:
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
    local_end = end_dt.astimezone(tz)
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
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Verify rule equivalence and contractual deadline cutoff for a single member (3A / 3B).

    Returns `(rule_verification_dict, parsed_question_dict_or_None)`.
    - If a verified `deadline_rule_contract` is present in `market_metadata` or
      derivable from `description`, validates the question and `resolution_date`
      against the rule's exact `cutoff_timezone` and `cutoff_local_time`.
    - If neither `description` nor `market_metadata["deadline_rule_contract"]` is
      present on the row (e.g. un-augmented Oct 14 `FuturesMarket` rows where
      `description` was not persisted), still checks whether the question is a
      candidate under the default `America/New_York` `23:59` cutoff so the caller
      can report the exact missing upstream producer evidence
      (`missing_rule_equivalence_proof`) rather than silently pretending the
      family is ready.
    """
    stored_contract = market_metadata.get(DEADLINE_RULE_CONTRACT_KEY)
    rule_contract: dict[str, Any] | None = None
    if isinstance(stored_contract, Mapping):
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

    if rule_contract is None and description:
        rule_contract = extract_polymarket_deadline_rule_contract(
            description,
            question=name,
            end_date=resolution_date,
        )

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
                        "cutoff_timezone": cutoff_tz,
                        "cutoff_local_time": cutoff_time,
                        "missing_producer_fields": [],
                    },
                    None,
                )
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
                "cutoff_timezone": cutoff_tz,
                "cutoff_local_time": cutoff_time,
                "group_item_title": rule_contract.get("group_item_title"),
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
    `market_metadata["deadline_rule_contract"]`), returns the contract with
    `rule_verification.verified = False` and `missing_producer_fields` populated
    so `verify_and_select_deadline_family` refuses grouping with an explicit
    producer-gap reason (`missing_rule_equivalence_proof`).
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
    # non-stale, at or after `basis_observed_at`, and observed within the 24h window.
    endpoint_valid_for_basis = bool(
        yes_observed_dt is not None
        and basis_observed_at is not None
        and yes_observed_dt >= basis_observed_at
        and (
            reference_dt is None
            or 0.0
            <= (reference_dt - yes_observed_dt).total_seconds() / 3600.0
            <= DATED_BASIS_WINDOW_HOURS
        )
    )

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
        )
        if supported_move is not None
        and basis_observed_at is not None
        and yes_observed_dt is not None
        else None
    )

    # Q8 check (Section 3D): a genuinely open question at 97%+ remains eligible
    # locally ONLY when it has a verified rule contract, a non-stale `yes_observed_dt`,
    # and a qualifying recent dated move (`moderate` or `hero`, >= 2 pts) on `Yes`.
    probs_for_extreme = [p for p in (yes_probability, no_probability) if p is not None]
    max_side_prob = max(probs_for_extreme) if probs_for_extreme else None
    is_near_certain = bool(
        max_side_prob is not None
        and (
            max_side_prob >= NEAR_CERTAIN_THRESHOLD
            or (
                yes_probability is not None
                and yes_probability <= (1.0 - NEAR_CERTAIN_THRESHOLD)
            )
        )
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
        if status_code == "missing_upstream_rule_text":
            return None, "missing_rule_equivalence_proof"
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
            "rule_template_hash": rule_hash,
            "predicate_hash": rule_ver.get("predicate_hash"),
            "window_kind": "cumulative_from_creation",
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
        status="resolved" if state_in == "unknown" else status_in,
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

    # Cumulative monotonicity sanity check on resolved members: if an earlier
    # deadline resolved "Yes", a later cumulative deadline cannot resolve "No".
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
        # Filter to open, priced members that are eligible (applying Q8 for >=97% members)
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
    # `(basis_observed_at, rep.price_observed_at)` — never from `now`!
    rep_basis = rep.get("movement_basis")
    rep_timeframe = (
        format_movement_timeframe(
            rep_basis.get("observed_at") if isinstance(rep_basis, Mapping) else None,
            rep.get("price_observed_at"),
            tz_name=reader_tz or "UTC",
        )
        if rep.get("supported_move") is not None
        and isinstance(rep_basis, Mapping)
        and rep.get("price_observed_at") is not None
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
            "rule_template_hash": ascending[0]["rule_verification"]["rule_template_hash"],
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
    "extract_polymarket_deadline_rule_contract",
    "build_polymarket_submarket_deadline_contract",
    "parse_cumulative_deadline_question",
    "extract_settlement_evidence",
    "format_movement_timeframe",
    "build_deadline_member_contract",
    "qualifies_for_deadline_near_certain_exception",
    "verify_and_select_deadline_family",
]
