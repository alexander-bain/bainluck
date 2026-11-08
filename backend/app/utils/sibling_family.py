"""Reusable ``sibling_family`` producer kind and its stored definitions (``docs/discover/grouping-types-2026-11.md`` §1.3).

PILLAR: DISCOVER / FORMATTING / TRUTH · SHIP: the fourth round-up producer kind,
``sibling_family`` ("Same market, many subjects", the Oct 7 sibling rule),
instantiated by two stored definitions in ``backend/data/containers/*.json``
(``gta-vi-album-features`` and ``snow-first-flakes-2026``) with
``membership: "sibling-family"`` (container-catalog decision A).

Rules enforced:
* **Structural template detection with case & spacing folding** (ruling 145):
  markets from one venue whose titles share one template and differ in
  **exactly one contiguous run** (the row subject), with at least
  ``MIN_SHARED_TOKENS = 2`` shared tokens and the differing run no longer than
  the shared part (``MAX_SUBJECT_RATIO = 1.0``, refusing the US Open /
  Australian Open specimen).
* **One venue only**: mixing venues (e.g. ``kalshi`` and ``polymarket``) in one
  sibling family refuses the whole card.
* **Combined-market exclusion**: a provider's multi-outcome ``field`` market
  (such as snow's 31-outcome ``60084865`` or GTA VI's 12-outcome ``61321728``)
  is excluded when binary per-subject markets exist, and refuses if both would
  supply rows.
* **Fixed dimensions proven equal**: within each deadline cohort, every member
  must carry the same stored ``resolution_date`` calendar day and agree with
  the title's stated deadline (refusing ``TIME Person of the Year 2026`` and
  ``2028 "announce a run"``).
* **Member ladder & field coherence**: refuses the family if any member's own
  threshold ladder violates monotonicity (``Denver 65536371`` where ``Above 6``
  at 64.0% > ``Above 4`` at 59.5%) or if any one-winner field sums over 100%
  (Kalshi ``Next Team`` ``67541294`` at 181.5%).
* **Overlapping row subjects refused** (catalog §5 decision D): state sets or
  combinations sharing a state/entity token (e.g. ``Senate Combo``) or
  duplicate subjects are refused.
* **Leading-deadline rule** (catalog §5 decision A): the nearest open deadline
  with at least three numbered members leads the card (Section 1), while later
  open deadlines become subsequent sections of the container (Section 2, etc.).
* **No-number rule** (ruling 146): an open member with no number is never
  hidden — it stays in its container section and is named on the card's count
  line (``"Showing 5 of 10 cities · No number yet: Detroit, Minneapolis, Pittsburgh"``).
* **Past-deadline / settled rule**: a member past its deadline shows only its
  graded result, never an open probability.
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
from app.utils.futures_liveness import leg_is_graded
from app.utils.tonights_games import _parse_dt


def _rc() -> Any:
    return importlib.import_module("app.utils.roundup_containers")


__all__ = [
    "ALCARAZ_SINNER_TWO_MAJORS_2027_DEFINITION",
    "ALCARAZ_SINNER_TWO_MAJORS_2027_DEFINITION_PATH",
    "ALCARAZ_SINNER_TWO_MAJORS_2027_ID",
    "ALCARAZ_SINNER_TWO_MAJORS_2027_PRODUCER",
    "ALCARAZ_SINNER_TWO_MAJORS_2027_SLUG",
    "CONTAINERS_DATA_DIR",
    "DEFAULT_SIBLING_LEVEL",
    "DEFAULT_SIBLING_RELATIONS",
    "GTA_VI_ALBUM_FEATURES_DEFINITION",
    "GTA_VI_ALBUM_FEATURES_DEFINITION_PATH",
    "GTA_VI_ALBUM_FEATURES_ID",
    "GTA_VI_ALBUM_FEATURES_PRODUCER",
    "GTA_VI_ALBUM_FEATURES_SLUG",
    "MEMBERSHIP_SIBLING_FAMILY",
    "MIN_SHARED_TOKENS",
    "MAX_SUBJECT_RATIO",
    "PRODUCER_KIND_SIBLING_FAMILY",
    "RT_SCORES_THIS_WEEK_DEFINITION",
    "RT_SCORES_THIS_WEEK_DEFINITION_PATH",
    "RT_SCORES_THIS_WEEK_ID",
    "RT_SCORES_THIS_WEEK_PRODUCER",
    "RT_SCORES_THIS_WEEK_SLUG",
    "SNOW_FIRST_FLAKES_2026_DEFINITION",
    "SNOW_FIRST_FLAKES_2026_DEFINITION_PATH",
    "SNOW_FIRST_FLAKES_2026_ID",
    "SNOW_FIRST_FLAKES_2026_PRODUCER",
    "SNOW_FIRST_FLAKES_2026_SLUG",
    "WHO_ANNOUNCES_BEFORE_2027_DEFINITION",
    "WHO_ANNOUNCES_BEFORE_2027_DEFINITION_PATH",
    "WHO_ANNOUNCES_BEFORE_2027_ID",
    "WHO_ANNOUNCES_BEFORE_2027_PRODUCER",
    "WHO_ANNOUNCES_BEFORE_2027_SLUG",
    "alcaraz_sinner_two_majors_2027",
    "build_sibling_family_producer",
    "detect_sibling_template_pair",
    "find_sibling_family_candidates",
    "fold_template_key",
    "gta_vi_album_features",
    "load_sibling_family_definition",
    "load_sibling_family_definitions_from_dir",
    "produce_sibling_family",
    "rt_scores_this_week",
    "select_sibling_family",
    "sibling_family_enabled",
    "snow_first_flakes_2026",
    "who_announces_before_2027",
]

PRODUCER_KIND_SIBLING_FAMILY = "sibling_family"
MEMBERSHIP_SIBLING_FAMILY = "sibling-family"
DEFAULT_SIBLING_RELATIONS: tuple[str, ...] = ("same_measure", "same_window", "sibling")
DEFAULT_SIBLING_LEVEL = "member"

MIN_SHARED_TOKENS = 2
MAX_SUBJECT_RATIO = 1.0

CONTAINERS_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "containers"

SNOW_FIRST_FLAKES_2026_SLUG = "snow-first-flakes-2026"
SNOW_FIRST_FLAKES_2026_ID = "roundup:snow-first-flakes-2026"
SNOW_FIRST_FLAKES_2026_DEFINITION_PATH = (
    CONTAINERS_DATA_DIR / f"{SNOW_FIRST_FLAKES_2026_SLUG}.json"
)

GTA_VI_ALBUM_FEATURES_SLUG = "gta-vi-album-features"
GTA_VI_ALBUM_FEATURES_ID = "roundup:gta-vi-album-features"
GTA_VI_ALBUM_FEATURES_DEFINITION_PATH = (
    CONTAINERS_DATA_DIR / f"{GTA_VI_ALBUM_FEATURES_SLUG}.json"
)

RT_SCORES_THIS_WEEK_SLUG = "rt-scores-this-week"
RT_SCORES_THIS_WEEK_ID = "roundup:rt-scores-this-week"
RT_SCORES_THIS_WEEK_DEFINITION_PATH = (
    CONTAINERS_DATA_DIR / f"{RT_SCORES_THIS_WEEK_SLUG}.json"
)

WHO_ANNOUNCES_BEFORE_2027_SLUG = "who-announces-before-2027"
WHO_ANNOUNCES_BEFORE_2027_ID = "roundup:who-announces-before-2027"
WHO_ANNOUNCES_BEFORE_2027_DEFINITION_PATH = (
    CONTAINERS_DATA_DIR / f"{WHO_ANNOUNCES_BEFORE_2027_SLUG}.json"
)

ALCARAZ_SINNER_TWO_MAJORS_2027_SLUG = "alcaraz-sinner-two-majors-2027"
ALCARAZ_SINNER_TWO_MAJORS_2027_ID = "roundup:alcaraz-sinner-two-majors-2027"
ALCARAZ_SINNER_TWO_MAJORS_2027_DEFINITION_PATH = (
    CONTAINERS_DATA_DIR / f"{ALCARAZ_SINNER_TWO_MAJORS_2027_SLUG}.json"
)

_ET_ZONE = ZoneInfo("America/New_York")

_FORBIDDEN_NARRATIVE_RE = re.compile(
    r"\b(?:kalshi|polymarket|sportsbooks?|bookmakers?|fanatics|draftkings|fanduel|betmgm|caesars|bain\s+luck\s+blend|blended|question|questions)\b",
    re.IGNORECASE,
)

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

_MONTH_FULL_NAMES: dict[int, str] = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

_MONTH_SHORT_UPPER: dict[int, str] = {
    1: "JAN",
    2: "FEB",
    3: "MAR",
    4: "APR",
    5: "MAY",
    6: "JUN",
    7: "JUL",
    8: "AUG",
    9: "SEP",
    10: "OCT",
    11: "NOV",
    12: "DEC",
}

_MONTH_END_DAY: dict[int, int] = {
    1: 31,
    2: 28,
    3: 31,
    4: 30,
    5: 31,
    6: 30,
    7: 31,
    8: 31,
    9: 30,
    10: 31,
    11: 30,
    12: 31,
}

# 50 US state 2-letter postal abbreviations (excluding DC so "Washington, DC" stays intact).
_US_STATE_CODES = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    }
)

_STATE_SUFFIX_RE = re.compile(r"^(?P<city>.+?),\s*(?P<state>[A-Z]{2})$")

# Generic words inside proper city/artist names that do not constitute overlapping subjects on their own.
_GENERIC_SUBJECT_TOKENS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "city",
        "st",
        "saint",
        "new",
        "north",
        "south",
        "east",
        "west",
        "fort",
        "ft",
        "mount",
        "mt",
        "port",
        "lake",
        "salt",
        "bay",
        "falls",
        "springs",
        "park",
        "beach",
        "island",
        "valley",
        "hills",
        "grand",
        "little",
        "los",
        "las",
        "san",
        "santa",
        "el",
        "la",
        "de",
        "del",
        "lil",
        "young",
        "big",
        "dj",
    }
)

_COMPOUND_SUBJECT_RE = re.compile(
    r"(?:\s*[+&/]\s*|\s*,\s*|\b(?:and|or|vs\.?|versus)\b)",
    re.IGNORECASE,
)

# Stated deadline patterns in market titles.
_BY_MONTH_DAY_RE = re.compile(
    r"\b(?P<prep>by|on|before)\s+(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:\s*,\s*(?P<year>20\d{2}))?(?=\s*[?.!)]*$|\s+)",
    re.IGNORECASE,
)
_IN_MONTH_YEAR_RE = re.compile(
    r"\bin\s+(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(?P<year>20\d{2})\b",
    re.IGNORECASE,
)
_BEFORE_YEAR_RE = re.compile(
    r"\bbefore\s+(?P<year>20\d{2})\b",
    re.IGNORECASE,
)
_IN_OR_FOR_YEAR_RE = re.compile(
    r"\b(?:in|for|of)\s+(?:the\s+year\s+)?(?P<year>20\d{2})\b|\b(?P<bare_year>20\d{2})\s*[?.!]*$",
    re.IGNORECASE,
)

# Threshold ladder outcome patterns (e.g. "Above 4 inches", "Above 50", "25k+", "Over 3.5").
_ABOVE_RUNG_RE = re.compile(
    r"^(?:(?:above|over|more\s+than|at\s+least|>=?)\s*(?P<num1>-?\d+(?:\.\d+)?)|(?P<num2>-?\d+(?:\.\d+)?)\s*(?:k\s*\+|\+|or\s+more|or\s+higher))(?:\b|$)",
    re.IGNORECASE,
)
_BELOW_RUNG_RE = re.compile(
    r"^(?:(?:below|under|less\s+than|fewer\s+than|<=?)\s*(?P<num1>-?\d+(?:\.\d+)?)|(?P<num2>-?\d+(?:\.\d+)?)\s*(?:or\s+less|or\s+fewer|or\s+lower))(?:\b|$)",
    re.IGNORECASE,
)

_TOKEN_CLEAN_RE = re.compile(r"^[^\w]+|[^\w]+$")


@dataclass(frozen=True)
class _StatedDeadline:
    phrase: str
    deadline_date: Optional[date]
    section_title: str
    short_kicker: str
    stem_text: str


@dataclass(frozen=True)
class _SiblingMember:
    market_id: int
    source: str
    category: str
    name: str
    subject: str
    raw_subject: str
    template_key: str
    stated_deadline: _StatedDeadline
    cohort_deadline: date
    stored_resolution_date: date
    status: str
    is_open: bool
    is_graded: bool
    settled_winner: Optional[str]
    probability: Optional[float]
    no_probability: Optional[float]
    outcome_id: int
    observed_at: Optional[str]
    raw_market: Mapping[str, Any]


def sibling_family_enabled() -> bool:
    """Feature flag check for sibling-family round-up containers."""
    return os.getenv("SIBLING_FAMILY_ENABLED", "true").lower() == "true"


def _validate_narrative_copy(*texts: str) -> None:
    """Enforce that narrative copy contains no venue name, blend claim, or 'question'."""
    for text in texts:
        if text and _FORBIDDEN_NARRATIVE_RE.search(text):
            raise ValueError(
                f"sibling_family narrative copy contains forbidden venue/blend/question wording: {text!r}"
            )


def _iso_utc(val: Any) -> Optional[str]:
    dt = _parse_dt(val)
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_market_ref_id(spec: str) -> tuple[str, int]:
    text = str(spec or "").strip()
    if ":" not in text:
        raise ValueError(f"Expected '<source>:<market_id>' market reference, got {spec!r}")
    source_raw, id_raw = text.split(":", 1)
    source = source_raw.strip().lower()
    if source not in {"kalshi", "polymarket"}:
        raise ValueError(f"Unsupported market venue {source!r} in {spec!r}")
    try:
        mid = int(id_raw.strip())
    except ValueError as err:
        raise ValueError(f"Non-integer market id in {spec!r}") from err
    if mid <= 0:
        raise ValueError(f"Market id must be positive in {spec!r}")
    return source, mid


def fold_template_key(text: str) -> str:
    """Fold case, punctuation, and whitespace into one canonical template key."""
    words: list[str] = []
    for raw in str(text or "").split():
        if raw == "*":
            words.append("*")
            continue
        cleaned = _TOKEN_CLEAN_RE.sub("", raw).casefold()
        if cleaned:
            words.append(cleaned)
    return " ".join(words)


def _tokenize_title(text: str) -> list[tuple[str, str]]:
    """Return ``[(raw_token, folded_token), ...]`` for a market title."""
    out: list[tuple[str, str]] = []
    for piece in str(text or "").strip().rstrip("?.!").split():
        if piece in {"+", "&", "/"}:
            out.append((piece, piece))
            continue
        folded = _TOKEN_CLEAN_RE.sub("", piece).casefold()
        if folded:
            out.append((piece, folded))
    return out


def detect_sibling_template_pair(
    title_a: str, title_b: str
) -> tuple[Optional[tuple[str, str, str]], Optional[str]]:
    """Compare two titles and return ``((template_key, subject_a, subject_b), refusal_reason)``.

    Enforces Ruling 145:
    * Titles must differ in **exactly one contiguous run** of tokens.
    * Shared token count must be at least ``MIN_SHARED_TOKENS`` (2).
    * Differing subject token run may be no longer than the shared token count
      (``MAX_SUBJECT_RATIO = 1.0``); returns ``(None, "differing_run_exceeds_shared")``
      when violated (the US Open / Australian Open specimen).
    """
    toks_a = _tokenize_title(title_a)
    toks_b = _tokenize_title(title_b)
    if not toks_a or not toks_b:
        return None, "empty_title"

    folded_a = [f for _, f in toks_a]
    folded_b = [f for _, f in toks_b]
    if folded_a == folded_b:
        return None, "identical_titles"

    pre = 0
    limit = min(len(folded_a), len(folded_b))
    while pre < limit and folded_a[pre] == folded_b[pre]:
        pre += 1

    suf = 0
    while (
        suf < (len(folded_a) - pre)
        and suf < (len(folded_b) - pre)
        and folded_a[len(folded_a) - 1 - suf] == folded_b[len(folded_b) - 1 - suf]
    ):
        suf += 1

    mid_a = toks_a[pre : len(toks_a) - suf]
    mid_b = toks_b[pre : len(toks_b) - suf]
    if not mid_a or not mid_b:
        return None, "empty_subject_run"

    shared = pre + suf
    if shared > 0 and (
        len(mid_a) > shared * MAX_SUBJECT_RATIO
        or len(mid_b) > shared * MAX_SUBJECT_RATIO
    ):
        return None, "differing_run_exceeds_shared"

    if shared < MIN_SHARED_TOKENS:
        return None, "too_few_shared_tokens"

    skeleton_tokens = (
        folded_a[:pre] + ["*"] + (folded_a[len(folded_a) - suf :] if suf else [])
    )
    template_key = " ".join(skeleton_tokens)
    subj_a = " ".join(raw for raw, _ in mid_a).strip()
    subj_b = " ".join(raw for raw, _ in mid_b).strip()
    return (template_key, subj_a, subj_b), None


def _extract_stated_deadline(title: str, default_year: int = 2026) -> _StatedDeadline:
    """Parse the stated deadline from ``title`` and return the stem without that deadline."""
    raw = str(title or "").strip()

    m_by = _BY_MONTH_DAY_RE.search(raw)
    if m_by is not None:
        prep = m_by.group("prep").lower()
        month_num = _MONTH_NUMBERS[m_by.group("month").lower().rstrip(".")]
        day_num = int(m_by.group("day"))
        year_num = int(m_by.group("year")) if m_by.group("year") else default_year
        d = date(year_num, month_num, day_num)
        month_full = _MONTH_FULL_NAMES[month_num]
        month_short = _MONTH_SHORT_UPPER[month_num]
        phrase = f"{prep} {month_full} {day_num}"
        sec_title = f"{prep.capitalize()} {month_full} {day_num}"
        short_kicker = f"{month_short} {day_num}"
        stem = (raw[: m_by.start()] + " " + raw[m_by.end() :]).strip()
        stem = re.sub(r"\s+([?.!])", r"\1", stem)
        return _StatedDeadline(
            phrase=phrase,
            deadline_date=d,
            section_title=sec_title,
            short_kicker=short_kicker,
            stem_text=stem,
        )

    m_in_my = _IN_MONTH_YEAR_RE.search(raw)
    if m_in_my is not None:
        month_num = _MONTH_NUMBERS[m_in_my.group("month").lower().rstrip(".")]
        year_num = int(m_in_my.group("year"))
        end_day = _MONTH_END_DAY[month_num]
        d = date(year_num, month_num, end_day)
        month_full = _MONTH_FULL_NAMES[month_num]
        month_short = _MONTH_SHORT_UPPER[month_num]
        phrase = f"in {month_full} {year_num}"
        sec_title = f"In {month_full} {year_num}"
        short_kicker = f"{month_short} {year_num}"
        stem = (raw[: m_in_my.start()] + " " + raw[m_in_my.end() :]).strip()
        stem = re.sub(r"\s+([?.!])", r"\1", stem)
        return _StatedDeadline(
            phrase=phrase,
            deadline_date=d,
            section_title=sec_title,
            short_kicker=short_kicker,
            stem_text=stem,
        )

    m_before_yr = _BEFORE_YEAR_RE.search(raw)
    if m_before_yr is not None:
        year_num = int(m_before_yr.group("year"))
        # "before 2028" means by the end of 2027 (Dec 31, year_num - 1).
        d = date(year_num - 1, 12, 31)
        phrase = f"before {year_num}"
        sec_title = f"Before {year_num}"
        short_kicker = f"BEFORE {year_num}"
        stem = (raw[: m_before_yr.start()] + " " + raw[m_before_yr.end() :]).strip()
        stem = re.sub(r"\s+([?.!])", r"\1", stem)
        return _StatedDeadline(
            phrase=phrase,
            deadline_date=d,
            section_title=sec_title,
            short_kicker=short_kicker,
            stem_text=stem,
        )

    m_yr = _IN_OR_FOR_YEAR_RE.search(raw)
    if m_yr is not None:
        year_str = m_yr.group("year") or m_yr.group("bare_year")
        year_num = int(year_str)
        d = date(year_num, 12, 31)
        phrase = f"in {year_num}"
        sec_title = f"In {year_num}"
        short_kicker = str(year_num)
        stem = (raw[: m_yr.start()] + " " + raw[m_yr.end() :]).strip()
        stem = re.sub(r"\s+([?.!])", r"\1", stem)
        return _StatedDeadline(
            phrase=phrase,
            deadline_date=d,
            section_title=sec_title,
            short_kicker=short_kicker,
            stem_text=stem,
        )

    return _StatedDeadline(
        phrase="",
        deadline_date=None,
        section_title="",
        short_kicker="",
        stem_text=raw,
    )


def _clean_subject_display(raw_subject: str, *, strip_state_suffix: bool) -> str:
    """Format the extracted row subject from the market's own words."""
    subj = str(raw_subject or "").strip().rstrip("?.!:\u00b7").strip()
    if strip_state_suffix:
        m = _STATE_SUFFIX_RE.match(subj)
        if m is not None and m.group("state") in _US_STATE_CODES:
            return m.group("city").strip()
    return subj


def _match_declared_template(
    stem_text: str,
    declared_template: str,
) -> Optional[tuple[str, str]]:
    """Match ``stem_text`` against an explicit single-wildcard ``declared_template`` (e.g. ``* rotten tomatoes score``).

    Used only when a stored definition declares an explicit ``template`` with at
    least ``MIN_SHARED_TOKENS`` literal words, allowing multi-word subject titles
    (such as film titles) to match the declared template without relaxing
    ``detect_sibling_template_pair``'s ``MAX_SUBJECT_RATIO`` when ``template=None``.
    """
    hint_stem = fold_template_key(_extract_stated_deadline(declared_template).stem_text)
    if hint_stem.count("*") != 1:
        hint_stem = fold_template_key(declared_template)
    if hint_stem.count("*") != 1:
        return None

    hint_words = hint_stem.split()
    if "*" not in hint_words:
        return None
    star_idx = hint_words.index("*")
    prefix_words = hint_words[:star_idx]
    suffix_words = hint_words[star_idx + 1 :]
    if len(prefix_words) + len(suffix_words) < MIN_SHARED_TOKENS:
        return None

    toks = _tokenize_title(stem_text)
    if len(toks) <= len(prefix_words) + len(suffix_words):
        return None
    folded_toks = [f for _, f in toks]
    if prefix_words and folded_toks[: len(prefix_words)] != prefix_words:
        return None
    if suffix_words and folded_toks[len(folded_toks) - len(suffix_words) :] != suffix_words:
        return None

    subj_end = len(toks) - len(suffix_words) if suffix_words else len(toks)
    subj_slice = toks[len(prefix_words) : subj_end]
    if not subj_slice:
        return None
    raw_subject = " ".join(raw for raw, _ in subj_slice).strip()
    if not raw_subject:
        return None
    return hint_stem, raw_subject


def _check_member_coherence(
    market: Mapping[str, Any],
    *,
    withheld: set[int],
) -> Optional[str]:
    """Verify that ``market``'s own threshold ladder or one-winner field is coherent.

    * If outcomes form a numeric threshold ladder (``Above 4 inches``, ``Above 6 inches``),
      probabilities must be monotonically non-increasing as the ``Above`` threshold
      rises (and non-decreasing as an ``Under`` threshold rises). Refuses
      ``Denver 65536371`` where ``Above 6 inches`` (64.0%) > ``Above 4 inches`` (59.5%).
    * If ``market`` is a one-winner mutually-exclusive field (more than 2 outcomes or
      ``market_type == "field"``), the sum of priced outcome probabilities must not
      exceed ``1.05`` (105%). Refuses Kalshi ``Next Team`` ``67541294`` (181.5%).
    """
    market_id = int(market.get("id") or 0)
    outcomes = market.get("outcomes")
    if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
        outcomes = market.get("top_outcomes")
    if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
        return None

    above_rungs: list[tuple[float, float]] = []
    below_rungs: list[tuple[float, float]] = []
    priced_probs: list[float] = []
    outcome_names: list[str] = []

    for idx, o in enumerate(outcomes):
        if not isinstance(o, Mapping):
            continue
        oid_raw = o.get("id")
        oid = (
            int(oid_raw)
            if isinstance(oid_raw, int) and not isinstance(oid_raw, bool) and oid_raw > 0
            else market_id * 10 + idx + 1
        )
        if oid in withheld:
            continue
        oname = str(o.get("name") or o.get("label") or "").strip()
        outcome_names.append(oname.lower())
        p_raw = (
            o.get("probability")
            if "probability" in o
            else o.get("current_probability")
        )
        if p_raw is None or isinstance(p_raw, bool):
            continue
        try:
            prob = float(p_raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(prob):
            continue
        priced_probs.append(prob)

        m_above = _ABOVE_RUNG_RE.match(oname)
        if m_above is not None:
            num_str = m_above.group("num1") or m_above.group("num2")
            try:
                above_rungs.append((float(num_str), prob))
            except ValueError:
                # Non-numeric threshold rung token; skip rung comparison.
                continue
            continue

        m_below = _BELOW_RUNG_RE.match(oname)
        if m_below is not None:
            num_str = m_below.group("num1") or m_below.group("num2")
            try:
                below_rungs.append((float(num_str), prob))
            except ValueError:
                # Non-numeric threshold rung token; skip rung comparison.
                continue

    if len(above_rungs) >= 2:
        above_rungs.sort(key=lambda pair: pair[0])
        for (t_low, p_low), (t_high, p_high) in zip(above_rungs, above_rungs[1:]):
            if t_high > t_low and p_high > p_low + 1e-6:
                return f"incoherent_ladder:{market_id}"

    if len(below_rungs) >= 2:
        below_rungs.sort(key=lambda pair: pair[0])
        for (t_low, p_low), (t_high, p_high) in zip(below_rungs, below_rungs[1:]):
            if t_high > t_low and p_low > p_high + 1e-6:
                return f"incoherent_ladder:{market_id}"

    is_binary_yes_no = set(outcome_names) <= {"yes", "no"} and len(outcomes) <= 2
    is_ladder = bool(above_rungs or below_rungs)
    mutually_exclusive = market.get("mutually_exclusive")
    mtype = str(market.get("market_type") or "").strip().lower()

    if is_binary_yes_no:
        if len(priced_probs) == 2 and sum(priced_probs) > 1.05:
            return f"incoherent_field_sum:{market_id}"
    elif not is_ladder and (mutually_exclusive is not False or mtype == "field"):
        if len(priced_probs) >= 2 and sum(priced_probs) > 1.05:
            return f"incoherent_field_sum:{market_id}"

    return None


def _is_combined_multi_subject_market(
    market: Mapping[str, Any],
    *,
    outcome_name: str,
) -> bool:
    """Return True when ``market`` is a provider's combined multi-outcome field market
    alongside per-subject binaries (e.g. ``60084865`` "First snow of the 2026 season"
    or ``61321728`` "Who will be featured on GTA VI: The Album?").
    """
    if str(outcome_name or "Yes").strip().lower() not in {"yes", "no"}:
        return False
    mtype = str(market.get("market_type") or "").strip().lower()
    if mtype == "field":
        return True
    outcomes = market.get("outcomes")
    if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
        outcomes = market.get("top_outcomes")
    if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
        return False
    if len(outcomes) <= 2:
        return False
    names = {
        str(o.get("name") or o.get("label") or "").strip().lower()
        for o in outcomes
        if isinstance(o, Mapping)
    }
    return not (names <= {"yes", "no"})


def _subjects_overlap(members: Sequence[_SiblingMember]) -> bool:
    """Return True when any two members in a cohort have duplicate or overlapping row subjects (decision D)."""
    seen_folded: set[str] = set()
    compound_token_sets: list[frozenset[str]] = []
    all_token_sets: list[tuple[bool, frozenset[str]]] = []

    for m in members:
        folded = m.subject.casefold().strip()
        if not folded or folded in seen_folded:
            return True
        seen_folded.add(folded)

        # Check if raw_subject (after stripping a single trailing ", ST" state code) is a compound set.
        cleaned_for_compound = _clean_subject_display(
            m.raw_subject, strip_state_suffix=True
        )
        tokens = frozenset(
            tok
            for _, tok in _tokenize_title(cleaned_for_compound)
            if tok not in _GENERIC_SUBJECT_TOKENS and tok not in {"+", "&", "/"}
        )
        state_tokens = frozenset(t.upper() for t in tokens if t.upper() in _US_STATE_CODES)
        is_compound = (
            bool(_COMPOUND_SUBJECT_RE.search(cleaned_for_compound))
            or len(state_tokens) >= 2
        )
        if is_compound and tokens:
            for prev in compound_token_sets:
                if tokens & prev:
                    return True
            compound_token_sets.append(tokens)
        all_token_sets.append((is_compound, tokens))

    # Also refuse if a compound subject shares any entity token with a single-entity subject
    # (e.g. "Pennsylvania" alongside "Pennsylvania & Ohio").
    if compound_token_sets:
        for i, (comp_i, toks_i) in enumerate(all_token_sets):
            if not toks_i:
                continue
            for j in range(i + 1, len(all_token_sets)):
                comp_j, toks_j = all_token_sets[j]
                if (comp_i or comp_j) and (toks_i & toks_j):
                    return True

    return False


def _half_up_percent(prob: float) -> int:
    """Round ``prob * 100`` half-up to match ``Math.round(prob * 100)`` on the client."""
    return int(math.floor(prob * 100.0 + 0.5))


def _build_member_card(member: _SiblingMember) -> dict[str, Any]:
    """Build the container member card for a numbered, unnumbered, or graded settled sibling market."""
    base = member.raw_market
    resolution_date = _iso_utc(base.get("resolution_date"))
    updated_at = _iso_utc(base.get("updated_at")) or member.observed_at
    raw_cat = str(base.get("category") or "").strip()
    card_category = (
        member.category
        if not raw_cat
        or raw_cat.lower() in {"game_prop", "other", "general", "unknown", "futures"}
        else raw_cat
    )

    if member.is_open and member.probability is not None:
        yes_pct = _half_up_percent(member.probability)
        no_prob = (
            member.no_probability
            if member.no_probability is not None
            else max(0.0, min(1.0, 1.0 - member.probability))
        )
        no_pct = 100 - yes_pct
        top_outcomes: list[dict[str, Any]] = [
            {
                "id": member.outcome_id,
                "name": "Yes",
                "probability": member.probability,
                "rendered_percent": yes_pct,
                "american_odds": None,
                "rank": 1,
                "movement": None,
                "is_winner": False,
                "resolution_source": None,
            },
            {
                "id": member.outcome_id + 1,
                "name": "No",
                "probability": no_prob,
                "rendered_percent": no_pct,
                "american_odds": None,
                "rank": 2,
                "movement": None,
                "is_winner": False,
                "resolution_source": None,
            },
        ]
        status_str = "open"
        prices_ts = member.observed_at
    elif member.is_graded and member.settled_winner:
        yes_won = member.settled_winner.lower() == "yes"
        graded_source = next(
            (
                o.get("resolution_source")
                for o in (base.get("outcomes") or ())
                if isinstance(o, Mapping) and o.get("resolution_source")
            ),
            None,
        )
        top_outcomes = [
            {
                "id": member.outcome_id,
                "name": "Yes",
                "probability": None,
                "rendered_percent": None,
                "american_odds": None,
                "rank": 1 if yes_won else 2,
                "movement": None,
                "is_winner": yes_won,
                "resolution_source": graded_source,
            },
            {
                "id": member.outcome_id + 1,
                "name": "No",
                "probability": None,
                "rendered_percent": None,
                "american_odds": None,
                "rank": 2 if yes_won else 1,
                "movement": None,
                "is_winner": not yes_won,
                "resolution_source": graded_source,
            },
        ]
        status_str = "resolved"
        prices_ts = None
    else:
        # Open unnumbered member ("No number yet") or resolved ungraded member:
        # empty top_outcomes so CollectionMemberCard prints "Probabilities aren't available right now."
        # or "Result unavailable", never a 0% or 100% open number.
        top_outcomes = []
        status_str = "open" if member.is_open else "resolved"
        prices_ts = None

    card: dict[str, Any] = {
        "id": member.market_id,
        "name": member.name,
        "sport": base.get("sport"),
        "sport_name": base.get("sport_name"),
        "category": card_category,
        "llm_sport_category": base.get("llm_sport_category") or member.category,
        "market_tier": int(base.get("market_tier") or 2),
        "market_type_label": base.get("market_type_label") or "Yes / No",
        "market_type": "yes_no",
        "status": status_str,
        "source": member.source,
        "sources": [member.source],
        "source_count": 1,
        "mutually_exclusive": True,
        "resolution_date": resolution_date,
        "top_outcomes": top_outcomes,
        "outcome_count": 2,
        "updated_at": updated_at,
        "prices_updated_at": prices_ts,
        "price_observed_at": prices_ts,
    }
    if member.is_graded and member.settled_winner:
        card["settled_winner"] = member.settled_winner
    return card


def _format_count_line(
    shown_count: int,
    total_count: int,
    subject_unit: str,
    unnumbered_subjects: Sequence[str],
) -> Optional[str]:
    """Build the two-part count line: ``Showing X of Y <unit> · No number yet: <names>``."""
    unit = str(subject_unit or "").strip()
    parts: list[str] = []
    if shown_count < total_count or unnumbered_subjects:
        if unit:
            parts.append(f"Showing {shown_count} of {total_count} {unit}")
        else:
            parts.append(f"Showing {shown_count} of {total_count}")
    if unnumbered_subjects:
        parts.append(f"No number yet: {', '.join(unnumbered_subjects)}")
    return " · ".join(parts) if parts else None


def select_sibling_family(
    markets: Mapping[int, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    expected_source: Optional[str] = None,
    template: Optional[str] = None,
    title_template: Optional[str] = None,
    kicker_prefix: Optional[str] = None,
    kicker_include_date: Optional[bool] = None,
    subject_unit: str = "",
    strip_state_suffix: bool = False,
    outcome_name: str = "Yes",
    shared_rung_band: Optional[tuple[float, float]] = None,
    strict_rungs_only: bool = False,
    lead_rule: str = "nearest_open_deadline",
    closed_world: bool = False,
    min_numbered_members: int = 3,
    max_members: Optional[int] = None,
    card_rows: int = 5,
    section_titles: Optional[Sequence[str]] = None,
    footer: str = "Each row is its own market. They don't add up to 100%.",
    exclude_combined_market: bool = True,
    release_window_days: Optional[int] = None,
    now: Optional[datetime] = None,
    withheld_by_market: Optional[Mapping[int, set[int]]] = None,
) -> Any:
    """Pure selector for ``sibling_family`` (§1.3 and §1.7 ``closed_world: true``).

    The sibling template is discovered structurally from the candidate titles
    via ``detect_sibling_template_pair`` and ``fold_template_key`` (Ruling 145:
    the template is found from the markets' own words, not supplied by hand).
    When ``template`` is passed from a stored definition, it acts as a declared
    expectation checked against the structurally detected family key.

    When ``closed_world=True`` (Ruling 143, §1.7 "Two rivals, one market"):
    * ``max_members`` defaults to ``2`` and ``min_numbered_members`` defaults to ``2``.
    * If more than ``max_members`` sibling markets exist under the template, refuses
      with ``RoundupRefusal((("family", "closed_world_exceeded"),))``.
    * If either leg has no open reading, refuses with
      ``RoundupRefusal((("family", "unpriced_legs"), ("unpriced_legs", tuple(unpriced))))``
      (CERT-430: no card while either leg has no reading).

    Returns ``RoundupMembers`` when the sibling family passes every check, or
    ``RoundupRefusal`` with structured reasons when any check fails.
    """
    rc = _rc()
    RoundupMembers = rc.RoundupMembers
    RoundupRefusal = rc.RoundupRefusal

    effective_max_members = (
        int(max_members)
        if max_members is not None
        else (2 if closed_world else None)
    )
    effective_min_numbered = (
        int(min_numbered_members)
        if not (closed_world and min_numbered_members == 3)
        else 2
    )
    effective_card_rows = (
        min(int(card_rows), effective_max_members)
        if closed_world and effective_max_members is not None
        else int(card_rows)
    )
    include_date_in_kicker = (
        bool(kicker_include_date)
        if kicker_include_date is not None
        else (not closed_world)
    )

    _validate_narrative_copy(
        footer,
        title_template or "",
        *(section_titles or ()),
    )

    effective_now = (
        now.astimezone(timezone.utc)
        if isinstance(now, datetime) and now.tzinfo is not None
        else datetime.now(timezone.utc)
    )
    today_et = effective_now.astimezone(_ET_ZONE).date()

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
        return RoundupRefusal((("family", "empty_pool"),))

    # Separate combined multi-outcome field markets (e.g. 60084865, 61321728) from per-subject markets.
    combined_markets: list[Mapping[str, Any]] = []
    candidate_markets: list[Mapping[str, Any]] = []
    for m in raw_list:
        if _is_combined_multi_subject_market(m, outcome_name=outcome_name):
            combined_markets.append(m)
        else:
            candidate_markets.append(m)

    if combined_markets and not exclude_combined_market:
        return RoundupRefusal((("family", "combined_market_conflict"),))
    if not candidate_markets:
        if combined_markets:
            return RoundupRefusal((("family", "combined_market_only"),))
        return RoundupRefusal((("family", "empty_pool"),))

    if release_window_days is not None and int(release_window_days) > 0:
        window_end_et = today_et + timedelta(days=int(release_window_days))
        windowed_candidates: list[Mapping[str, Any]] = []
        for m in candidate_markets:
            res_dt = _parse_dt(m.get("resolution_date"))
            stated_dl = _extract_stated_deadline(str(m.get("name") or ""))
            cohort_d = (
                stated_dl.deadline_date
                if stated_dl.deadline_date is not None
                else (res_dt.astimezone(timezone.utc).date() if res_dt is not None else None)
            )
            if cohort_d is not None and today_et <= cohort_d <= window_end_et:
                windowed_candidates.append(m)
        if not windowed_candidates:
            return RoundupRefusal((("family", "no_open_deadline"),))
        candidate_markets = windowed_candidates

    # One-venue-only check across candidate markets.
    venues: set[str] = set()
    for m in candidate_markets:
        src = str(m.get("source") or "").strip().lower()
        if not src:
            raw_srcs = m.get("sources")
            if (
                isinstance(raw_srcs, Sequence)
                and not isinstance(raw_srcs, (str, bytes))
                and len(raw_srcs) == 1
            ):
                src = str(raw_srcs[0] or "").strip().lower()
        if src:
            venues.add(src)
    if len(venues) > 1:
        return RoundupRefusal((("family", "mixed_venues"),))
    venue = next(iter(venues)) if venues else (expected_source or "polymarket").lower()
    if expected_source and venue != expected_source.strip().lower():
        return RoundupRefusal((("family", "mixed_venues"),))

    # Coherence check on every candidate market before grouping.
    for m in candidate_markets:
        mid = int(m["id"])
        blocked = (
            set(withheld_by_market.get(mid, set()))
            if withheld_by_market is not None
            else set()
        )
        coherence_err = _check_member_coherence(m, withheld=blocked)
        if coherence_err is not None:
            return RoundupRefusal((("family", coherence_err),))

    # Extract stated deadlines & stems and group into structural template families (case-folded).
    stems_by_id: dict[int, _StatedDeadline] = {}
    for m in candidate_markets:
        mid = int(m["id"])
        stems_by_id[mid] = _extract_stated_deadline(str(m.get("name") or ""))

    # Pairwise structural template detection across stems.
    family_groups: dict[str, dict[int, str]] = {}
    exceeded_ratio = False
    n = len(candidate_markets)
    for i in range(n):
        m_i = candidate_markets[i]
        id_i = int(m_i["id"])
        stem_i = stems_by_id[id_i].stem_text
        for j in range(i + 1, n):
            m_j = candidate_markets[j]
            id_j = int(m_j["id"])
            stem_j = stems_by_id[id_j].stem_text
            res, err = detect_sibling_template_pair(stem_i, stem_j)
            if err == "differing_run_exceeds_shared":
                exceeded_ratio = True
                continue
            if res is None:
                continue
            t_key, subj_i, subj_j = res
            bucket = family_groups.setdefault(t_key, {})
            bucket.setdefault(id_i, subj_i)
            bucket.setdefault(id_j, subj_j)

    # When a stored definition declares an explicit template (with >= MIN_SHARED_TOKENS
    # literal words), include any candidate whose stem matches the declared template
    # so multi-word titles (such as 4+ word film names) join the family cleanly.
    if template:
        declared_matches: dict[str, dict[int, str]] = {}
        for m in candidate_markets:
            mid = int(m["id"])
            matched_decl = _match_declared_template(
                stems_by_id[mid].stem_text, template
            )
            if matched_decl is not None:
                decl_key, decl_subj = matched_decl
                declared_matches.setdefault(decl_key, {})[mid] = decl_subj
        for decl_key, decl_map in declared_matches.items():
            if len(decl_map) >= 2:
                bucket = family_groups.setdefault(decl_key, {})
                for mid, decl_subj in decl_map.items():
                    bucket.setdefault(mid, decl_subj)

    if not family_groups:
        if exceeded_ratio:
            return RoundupRefusal((("family", "differing_run_exceeds_shared"),))
        return RoundupRefusal((("family", "no_template_family"),))

    # If a specific template hint was configured, match against its stem; otherwise pick the largest detected family.
    chosen_key: Optional[str] = None
    if template:
        folded_hint = fold_template_key(_extract_stated_deadline(template).stem_text)
        if folded_hint in family_groups:
            chosen_key = folded_hint
        else:
            # Also try matching without deadline stripping in case the hint already omitted the deadline.
            folded_raw_hint = fold_template_key(template)
            if folded_raw_hint in family_groups:
                chosen_key = folded_raw_hint
        if chosen_key is None and closed_world:
            return RoundupRefusal((("family", "no_template_family"),))
    if chosen_key is None:
        chosen_key = max(
            family_groups.keys(),
            key=lambda k: (len(family_groups[k]), k),
        )

    matched_subjects = family_groups[chosen_key]
    if (
        effective_max_members is not None
        and len(matched_subjects) > effective_max_members
    ):
        return RoundupRefusal((("family", "closed_world_exceeded"),))
    by_id = {int(m["id"]): m for m in candidate_markets}
    target_outcome_folded = str(outcome_name or "Yes").strip().casefold()

    if strict_rungs_only or target_outcome_folded == "auto_shared_rung":
        from app.utils.ladder_monotonicity import DEC, parse_plus_bracket, parse_threshold

        _NON_STRICT_RUNG_RE = re.compile(
            r"(?:\bat\s+least\b|\bat\s+most\b|\bor\s+more\b|\bor\s+less\b|\bor\s+fewer\b|\bor\s+higher\b|\bor\s+lower\b|>=|<=|≥|≤)",
            re.IGNORECASE,
        )

        def _is_non_strict_rung_label(label: str) -> bool:
            if parse_plus_bracket(label) is not None:
                return True
            return bool(_NON_STRICT_RUNG_RE.search(label))

        # Check strict_rungs_only across matched candidate markets.
        if strict_rungs_only:
            for mid in matched_subjects:
                m = by_id[mid]
                raw_outs = m.get("outcomes") or m.get("top_outcomes") or ()
                for o in raw_outs:
                    if not isinstance(o, Mapping):
                        continue
                    oname = str(o.get("name") or o.get("label") or "").strip()
                    if not oname:
                        continue
                    if _is_non_strict_rung_label(oname):
                        return RoundupRefusal((("family", f"non_strict_rung:{mid}"),))

        if target_outcome_folded == "auto_shared_rung":
            band_low, band_high = (
                (float(shared_rung_band[0]), float(shared_rung_band[1]))
                if shared_rung_band is not None and len(shared_rung_band) == 2
                else (0.05, 0.95)
            )
            rungs_by_mid: dict[int, dict[str, tuple[float, float]]] = {}
            cohort_mids: dict[Optional[date], list[int]] = {}
            for mid in matched_subjects:
                m = by_id[mid]
                res_dt = _parse_dt(m.get("resolution_date"))
                stated_dl = stems_by_id[mid]
                c_date = (
                    stated_dl.deadline_date
                    if stated_dl.deadline_date is not None
                    else (
                        res_dt.astimezone(timezone.utc).date()
                        if res_dt is not None
                        else None
                    )
                )
                cohort_mids.setdefault(c_date, []).append(mid)
                if str(m.get("status") or "open").strip().lower() != "open":
                    continue
                raw_outs = m.get("outcomes") or m.get("top_outcomes") or ()
                rung_map: dict[str, tuple[float, float]] = {}
                for o in raw_outs:
                    if not isinstance(o, Mapping):
                        continue
                    if leg_is_graded(o.get("is_winner"), o.get("resolution_source")):
                        continue
                    oname = str(o.get("name") or o.get("label") or "").strip()
                    pt = parse_threshold(oname)
                    if (
                        pt is None
                        or pt[2] != DEC
                        or (strict_rungs_only and _is_non_strict_rung_label(oname))
                    ):
                        continue
                    p_raw = (
                        o.get("probability")
                        if "probability" in o
                        else o.get("current_probability")
                    )
                    if p_raw is None or isinstance(p_raw, bool):
                        continue
                    try:
                        p_val = float(p_raw)
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(p_val) and 0.0 < p_val < 1.0:
                        rung_map[oname.casefold()] = (pt[1], p_val)
                if rung_map:
                    rungs_by_mid[mid] = rung_map

            if len(rungs_by_mid) < min_numbered_members:
                return RoundupRefusal((("family", "too_few_numbered_members"),))

            # Evaluate cohorts in chronological order (nearest open deadline first) so an
            # early-listed film in a later cohort with different rungs never blocks this week's cohort.
            dated_cohorts = sorted(
                (d for d in cohort_mids if d is not None and d >= today_et)
            )
            cohort_groups_to_try: list[list[dict[str, tuple[float, float]]]] = []
            for d in dated_cohorts:
                c_rungs = [
                    rungs_by_mid[mid]
                    for mid in cohort_mids[d]
                    if mid in rungs_by_mid
                ]
                if len(c_rungs) >= min_numbered_members:
                    cohort_groups_to_try.append(c_rungs)
            if not cohort_groups_to_try:
                cohort_groups_to_try.append(list(rungs_by_mid.values()))

            chosen_rung_key: Optional[str] = None
            for open_member_rungs in cohort_groups_to_try:
                shared_keys = set(open_member_rungs[0].keys())
                for rm in open_member_rungs[1:]:
                    shared_keys &= set(rm.keys())

                qualifying_rungs: list[tuple[float, str]] = []
                for r_key in shared_keys:
                    in_band = sum(
                        1
                        for rm in open_member_rungs
                        if band_low <= rm[r_key][1] <= band_high
                    )
                    if in_band >= min_numbered_members:
                        thresh_val = open_member_rungs[0][r_key][0]
                        qualifying_rungs.append((thresh_val, r_key))

                if qualifying_rungs:
                    qualifying_rungs.sort(key=lambda pair: (pair[0], pair[1]))
                    chosen_rung_key = qualifying_rungs[-1][1]
                    break

            if chosen_rung_key is None:
                return RoundupRefusal((("family", "no_shared_rung_in_band"),))

            target_outcome_folded = chosen_rung_key
            # Exclude secondary cohorts whose members do not carry the chosen shared rung.
            if len(cohort_mids) > 1:
                valid_mids: dict[int, str] = {}
                for _c_date, mids_in_cohort in cohort_mids.items():
                    if all(
                        any(
                            isinstance(o, Mapping)
                            and str(o.get("name") or o.get("label") or "").strip().casefold()
                            == target_outcome_folded
                            for o in (
                                by_id[m_id].get("outcomes")
                                or by_id[m_id].get("top_outcomes")
                                or ()
                            )
                        )
                        for m_id in mids_in_cohort
                    ):
                        for m_id in mids_in_cohort:
                            valid_mids[m_id] = matched_subjects[m_id]
                if valid_mids:
                    matched_subjects = valid_mids

    # Build _SiblingMember objects and validate outcomes & resolution dates.
    parsed_members: list[_SiblingMember] = []
    for mid, raw_subj in matched_subjects.items():
        m = by_id[mid]
        res_dt = _parse_dt(m.get("resolution_date"))
        if res_dt is None:
            return RoundupRefusal((("family", "missing_resolution_date"),))
        stored_res_date = res_dt.astimezone(timezone.utc).date()

        stated = stems_by_id[mid]
        cohort_date = (
            stated.deadline_date
            if stated.deadline_date is not None
            else stored_res_date
        )

        # Verify stored resolution_date agrees with the title's stated deadline (within 0..5 day settlement window,
        # or within the stated calendar year when the title specifies an 'in <YYYY>' season horizon).
        if stated.deadline_date is not None:
            is_in_year_season = (
                stated.phrase == f"in {stated.deadline_date.year}"
                and stored_res_date.year == stated.deadline_date.year
            )
            if not is_in_year_season and (
                stored_res_date < stated.deadline_date
                or stored_res_date > stated.deadline_date + timedelta(days=5)
            ):
                return RoundupRefusal(
                    (("family", "resolution_date_disagrees_with_title"),)
                )

        status_raw = str(m.get("status") or "open").strip().lower()
        is_open = status_raw == "open"

        outcomes = m.get("outcomes")
        if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
            outcomes = m.get("top_outcomes")
        if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
            return RoundupRefusal((("family", f"missing_outcomes:{mid}"),))

        blocked = (
            set(withheld_by_market.get(mid, set()))
            if withheld_by_market is not None
            else set()
        )

        target_outcome: Optional[Mapping[str, Any]] = None
        target_oid: int = mid * 10 + 1
        no_outcome: Optional[Mapping[str, Any]] = None
        is_graded = False
        settled_winner: Optional[str] = None

        for idx, o in enumerate(outcomes):
            if not isinstance(o, Mapping):
                continue
            oid_raw = o.get("id")
            oid = (
                int(oid_raw)
                if isinstance(oid_raw, int)
                and not isinstance(oid_raw, bool)
                and oid_raw > 0
                else mid * 10 + idx + 1
            )
            oname = str(o.get("name") or o.get("label") or "").strip()
            oname_folded = oname.casefold()
            if leg_is_graded(o.get("is_winner"), o.get("resolution_source")):
                is_graded = True
                if o.get("is_winner") is True:
                    settled_winner = oname or "Yes"
            if oname_folded == target_outcome_folded:
                target_outcome = o
                target_oid = oid
            elif oname_folded == "no":
                no_outcome = o

        if target_outcome is None:
            return RoundupRefusal((("family", f"missing_target_outcome:{mid}"),))

        if is_graded:
            is_open = False

        prob: Optional[float] = None
        if is_open and target_oid not in blocked:
            p_raw = (
                target_outcome.get("probability")
                if "probability" in target_outcome
                else target_outcome.get("current_probability")
            )
            if p_raw is not None and not isinstance(p_raw, bool):
                try:
                    p_val = float(p_raw)
                    # An open market never prints 0% or 100%; probabilities outside (0, 1) are not valid open numbers.
                    if math.isfinite(p_val) and 0.0 < p_val < 1.0:
                        prob = p_val
                except (TypeError, ValueError):
                    prob = None

        no_prob: Optional[float] = None
        if is_open and no_outcome is not None and prob is not None:
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
            m.get("prices_updated_at")
            or m.get("price_observed_at")
            or m.get("updated_at")
        )
        obs = (
            _iso_utc(
                target_outcome.get("observed_at")
                or target_outcome.get("last_updated")
            )
            or market_observed
        )

        subject_display = _clean_subject_display(
            raw_subj, strip_state_suffix=strip_state_suffix
        )
        category_str = (
            str(m.get("category") or m.get("llm_sport_category") or "other")
            .strip()
            .lower()
        )

        parsed_members.append(
            _SiblingMember(
                market_id=mid,
                source=venue,
                category=category_str,
                name=str(m.get("name") or "").strip(),
                subject=subject_display,
                raw_subject=raw_subj,
                template_key=chosen_key,
                stated_deadline=stated,
                cohort_deadline=cohort_date,
                stored_resolution_date=stored_res_date,
                status=status_raw,
                is_open=is_open,
                is_graded=is_graded,
                settled_winner=settled_winner,
                probability=prob,
                no_probability=no_prob,
                outcome_id=target_oid,
                observed_at=obs,
                raw_market=m,
            )
        )

    # Group members by cohort_deadline.
    cohorts_by_date: dict[date, list[_SiblingMember]] = {}
    for pm in parsed_members:
        cohorts_by_date.setdefault(pm.cohort_deadline, []).append(pm)

    # Validate fixed-dimension equality and non-overlapping subjects within each open cohort.
    open_cohort_dates = sorted(d for d in cohorts_by_date if d >= today_et)
    if not open_cohort_dates:
        return RoundupRefusal((("family", "no_open_deadline"),))

    for d in open_cohort_dates:
        cohort = cohorts_by_date[d]
        stored_dates = {pm.stored_resolution_date for pm in cohort}
        if len(stored_dates) > 1:
            return RoundupRefusal((("family", "inconsistent_resolution_dates"),))
        if _subjects_overlap(cohort):
            return RoundupRefusal((("family", "overlapping_subjects"),))

    if lead_rule == "single_deadline" and len(open_cohort_dates) > 1:
        return RoundupRefusal((("family", "multiple_open_deadlines"),))

    if closed_world:
        for d in open_cohort_dates:
            cohort = cohorts_by_date[d]
            if (
                effective_max_members is not None
                and len(cohort) > effective_max_members
            ):
                return RoundupRefusal((("family", "closed_world_exceeded"),))
            if len(cohort) < effective_min_numbered:
                return RoundupRefusal((("family", "too_few_numbered_members"),))
            unpriced = [
                pm.subject
                for pm in sorted(
                    cohort, key=lambda pm: (pm.subject.casefold(), pm.market_id)
                )
                if not pm.is_open or pm.probability is None
            ]
            if unpriced:
                return RoundupRefusal(
                    (
                        ("family", "unpriced_legs"),
                        ("unpriced_legs", tuple(unpriced)),
                    )
                )

    # Decision A: select the nearest open deadline with at least effective_min_numbered members that have a number.
    leading_date: Optional[date] = None
    for d in open_cohort_dates:
        numbered_at_d = [
            pm for pm in cohorts_by_date[d] if pm.is_open and pm.probability is not None
        ]
        if len(numbered_at_d) >= effective_min_numbered:
            leading_date = d
            break

    if leading_date is None:
        return RoundupRefusal((("family", "too_few_numbered_members"),))

    # Build ordered sections starting from leading_date, followed by any subsequent open cohorts.
    active_cohort_dates = [d for d in open_cohort_dates if d >= leading_date]
    sections_out: list[dict[str, Any]] = []
    all_member_entries: list[dict[str, Any]] = []
    all_revision_ids: list[int] = []

    leading_rows: list[dict[str, Any]] = []
    leading_count_line: Optional[str] = None
    leading_title: Optional[str] = None
    leading_kicker: Optional[str] = None

    for sec_idx, d in enumerate(active_cohort_dates):
        cohort = cohorts_by_date[d]
        numbered = sorted(
            [pm for pm in cohort if pm.is_open and pm.probability is not None],
            key=lambda pm: (
                -(pm.probability or 0.0),
                pm.subject.casefold(),
                pm.market_id,
            ),
        )
        unnumbered = sorted(
            [pm for pm in cohort if pm.is_open and pm.probability is None],
            key=lambda pm: (pm.subject.casefold(), pm.market_id),
        )
        settled = sorted(
            [pm for pm in cohort if not pm.is_open],
            key=lambda pm: (pm.subject.casefold(), pm.market_id),
        )
        ordered_cohort = numbered + unnumbered + settled

        sample_stated = ordered_cohort[0].stated_deadline
        month_full = _MONTH_FULL_NAMES[d.month]
        month_short = _MONTH_SHORT_UPPER[d.month]
        default_sec_title = (
            sample_stated.section_title
            if sample_stated.section_title
            else f"By {month_full} {d.day}"
        )
        configured_sec_title = (
            str(section_titles[sec_idx]).strip()
            if section_titles and sec_idx < len(section_titles) and str(section_titles[sec_idx]).strip()
            else default_sec_title
        )
        # If Leading deadline shifted (e.g. Nov 15 -> Nov 30), prefer the cohort's own stated date title
        # unless closed_world has an explicit section_title configured.
        if closed_world and section_titles and sec_idx < len(section_titles) and str(section_titles[sec_idx]).strip():
            sec_title = configured_sec_title
        elif sample_stated.section_title:
            sec_title = sample_stated.section_title
        else:
            sec_title = configured_sec_title

        sec_members: list[dict[str, Any]] = []
        for pm in ordered_cohort:
            card = _build_member_card(pm)
            entry = {
                "type": MEMBER_MARKET,
                "id": pm.market_id,
                "destination": market_destination(pm.market_id),
                "card": card,
                "event_id": None,
            }
            sec_members.append(entry)
            all_member_entries.append(entry)
            all_revision_ids.append(pm.market_id)

        sections_out.append(
            {
                "class": f"deadline_{d.strftime('%Y_%m_%d')}",
                "title": sec_title,
                "layout": "field",
                "count": len(sec_members),
                "members": sec_members,
            }
        )

        if sec_idx == 0:
            shown_numbered = numbered[:effective_card_rows]
            for pm in shown_numbered:
                assert pm.probability is not None
                leading_rows.append(
                    {
                        "market_id": pm.market_id,
                        "outcome_id": pm.outcome_id,
                        "label": pm.subject,
                        "probability": pm.probability,
                        "rendered_percent": _half_up_percent(pm.probability),
                        "observed_at": pm.observed_at,
                    }
                )
            unnumbered_names = [pm.subject for pm in unnumbered]
            leading_count_line = _format_count_line(
                len(shown_numbered),
                len(ordered_cohort),
                subject_unit,
                unnumbered_names,
            )

            deadline_phrase = (
                sample_stated.phrase
                if sample_stated.phrase
                else f"by {month_full} {d.day}"
            )
            short_date = (
                sample_stated.short_kicker
                if sample_stated.short_kicker
                else f"{month_short} {d.day}"
            )
            if title_template:
                leading_title = title_template.replace("{deadline}", deadline_phrase)
            if kicker_prefix:
                if include_date_in_kicker:
                    leading_kicker = f"{kicker_prefix.strip().upper()} · {short_date}"
                else:
                    leading_kicker = kicker_prefix.strip().upper()

    return RoundupMembers(
        all_member_entries,
        leading_rows,
        footer=footer,
        count_line=leading_count_line,
        title=leading_title,
        kicker=leading_kicker,
        sections=sections_out,
        revision_ids=all_revision_ids,
    )


async def _load_markets_from_db(
    db: Any,
    *,
    group_id: Optional[str] = None,
    candidate_ids: Sequence[int] = (),
    title_ilike: Optional[str] = None,
    expected_source: Optional[str] = None,
) -> tuple[dict[int, dict[str, Any]], dict[int, set[int]]]:
    """Load candidate ``FuturesMarket`` rows and their withheld outcome IDs in constant queries.

    ``candidates`` are queried as a union (SQL ``OR``) with ``group_id``, not a
    restriction, so any new sibling market the venue adds under ``group_id``
    joins the family automatically without listing IDs by hand.
    """
    if not hasattr(db, "execute") or not callable(db.execute):
        return {}, {}

    from sqlalchemy import and_, or_, select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import selectinload

    from app.models import FuturesMarket
    from app.routes.futures import withheld_price_outcome_ids_for_markets

    clean_group_id = str(group_id).strip() if group_id else None
    clean_title_ilike = str(title_ilike).strip() if title_ilike else None
    clean_expected_source = str(expected_source).strip().lower() if expected_source else None
    clean_candidate_ids = [
        int(x)
        for x in candidate_ids
        if isinstance(x, int) and not isinstance(x, bool) and int(x) > 0
    ]
    candidate_id_set = set(clean_candidate_ids)

    filters = []
    if clean_group_id:
        filters.append(FuturesMarket.group_id == clean_group_id)
    if clean_candidate_ids:
        filters.append(FuturesMarket.id.in_(clean_candidate_ids))
    if clean_title_ilike:
        if clean_expected_source:
            filters.append(
                and_(
                    FuturesMarket.source == clean_expected_source,
                    FuturesMarket.name.ilike(clean_title_ilike),
                )
            )
        else:
            filters.append(FuturesMarket.name.ilike(clean_title_ilike))
    if not filters:
        return {}, {}

    stmt = (
        select(FuturesMarket)
        .options(
            selectinload(FuturesMarket.sport),
            selectinload(FuturesMarket.outcomes),
        )
        .where(or_(*filters) if len(filters) > 1 else filters[0])
        .order_by(FuturesMarket.id.asc())
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
            if (
                not isinstance(raw_id, int)
                or isinstance(raw_id, bool)
                or raw_id <= 0
                or "outcomes" not in m
            ):
                continue
            mid = int(raw_id)
            row_gid = str(m.get("group_id") or "").strip() or None
            if (
                not clean_title_ilike
                and (clean_group_id or candidate_id_set)
                and row_gid != clean_group_id
                and mid not in candidate_id_set
            ):
                continue
            entry = dict(m)
            entry["id"] = mid
            by_id[mid] = entry
            continue

        raw_mid = getattr(m, "id", None)
        if not isinstance(raw_mid, int) or isinstance(raw_mid, bool) or raw_mid <= 0:
            continue
        mid = int(raw_mid)
        row_gid = str(getattr(m, "group_id", None) or "").strip() or None
        if (
            not clean_title_ilike
            and (clean_group_id or candidate_id_set)
            and row_gid != clean_group_id
            and mid not in candidate_id_set
        ):
            continue

        outcomes_list = [
            {
                "id": int(o.id),
                "name": o.name,
                "probability": (
                    float(o.current_probability)
                    if o.current_probability is not None
                    else None
                ),
                "movement": (
                    float(o.probability_change_24h)
                    if getattr(o, "probability_change_24h", None) is not None
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
        raw_name = getattr(m, "name", None)
        raw_res_date = getattr(m, "resolution_date", None)
        norm_name, norm_res_date = normalize_registered_family_market(
            raw_name, raw_res_date
        )
        by_id[mid] = {
            "id": mid,
            "name": norm_name,
            "status": getattr(m, "status", None),
            "source": getattr(m, "source", None),
            "external_id": getattr(m, "external_id", None),
            "group_id": getattr(m, "group_id", None),
            "sport": m.sport.key if getattr(m, "sport", None) is not None else None,
            "sport_name": (
                m.sport.name if getattr(m, "sport", None) is not None else None
            ),
            "category": getattr(m, "category", None),
            "llm_sport_category": getattr(m, "llm_sport_category", None),
            "market_tier": getattr(m, "market_tier", None),
            "market_type": getattr(m, "market_type", None),
            "mutually_exclusive": getattr(m, "mutually_exclusive", True),
            "resolution_date": norm_res_date,
            "updated_at": getattr(m, "updated_at", None),
            "outcomes": outcomes_list,
        }
    return by_id, {int(k): set(v) for k, v in (withheld or {}).items()}


_TIME_PERSON_OF_THE_YEAR_RE = re.compile(
    r"^\s*Will\s+(?P<subject>.+?)\s+be\s+named\s+TIME(?:'s)?\s+Person\s+of\s+the\s+Year\s+for\s+(?P<year>\d{4})\?\s*$",
    re.IGNORECASE,
)
_ANNOUNCE_PRESIDENTIAL_RUN_RE = re.compile(
    r"^\s*Will\s+(?P<subject>.+?)\s+announce\s+a\s+(?P<office>Presidential|presidential)\s+run\s+before\s+(?P<year>\d{4})\?\s*$"
)


def normalize_registered_family_market(
    name: Any,
    resolution_date: Any,
) -> tuple[Any, Any]:
    """Normalize known sibling-family date and capitalization artefacts (#11943).

    Every normalization moves a cutoff later or not at all, never earlier, so no leg
    can be clock-settled sooner than its venue states:
    * ``TIME Person of the Year <YYYY>`` binaries normalize ``resolution_date`` to
      ``<YYYY>-12-31T00:00:00Z`` (fixing the 1-of-26 ``2026-12-30T12:00:00Z`` leg).
    * ``Will <person> announce a Presidential/presidential run before <YYYY>?``
      binaries normalize ``Presidential run`` -> ``presidential run`` and
      ``resolution_date`` to ``(<YYYY>-1)-12-31T23:59:00Z`` (fixing the 26
      ``12:00Z`` vs 7 ``23:59Z`` split and ``Gavin Newsom``'s capital ``P``).
    """
    if not isinstance(name, str) or not name.strip():
        return name, resolution_date
    m_time = _TIME_PERSON_OF_THE_YEAR_RE.match(name)
    if m_time is not None:
        year = int(m_time.group("year"))
        canon_dt = datetime(year, 12, 31, 0, 0, 0, tzinfo=timezone.utc)
        return (
            name,
            canon_dt.isoformat().replace("+00:00", "Z")
            if isinstance(resolution_date, str)
            else canon_dt,
        )
    m_run = _ANNOUNCE_PRESIDENTIAL_RUN_RE.match(name)
    if m_run is not None:
        subject = m_run.group("subject").strip()
        year = int(m_run.group("year"))
        canon_name = f"Will {subject} announce a presidential run before {year}?"
        canon_dt = datetime(year - 1, 12, 31, 23, 59, 0, tzinfo=timezone.utc)
        return (
            canon_name,
            canon_dt.isoformat().replace("+00:00", "Z")
            if isinstance(resolution_date, str)
            else canon_dt,
        )
    return name, resolution_date


async def produce_sibling_family(
    db: Any,
    definition: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Any:
    """Evaluate a stored ``sibling_family`` definition against ``db`` (or an in-memory fixture)."""
    rule = definition.get("rule")
    if not isinstance(rule, Mapping):
        raise ValueError("sibling_family definition requires a 'rule' mapping")
    if rule.get("producer") != PRODUCER_KIND_SIBLING_FAMILY:
        raise ValueError(
            f"Unsupported producer kind {rule.get('producer')!r}; expected {PRODUCER_KIND_SIBLING_FAMILY!r}"
        )

    expected_source = str(rule.get("source") or "").strip().lower() or None
    group_id = str(rule.get("group_id") or "").strip() or None
    title_ilike = str(rule.get("title_ilike") or "").strip() or None
    template = str(rule.get("template") or "").strip() or None
    title_template = (
        str(rule.get("title_template") or definition.get("name") or "").strip() or None
    )
    kicker_prefix = str(rule.get("kicker_prefix") or "").strip() or None
    kicker_include_date_raw = rule.get("kicker_include_date")
    kicker_include_date: Optional[bool] = (
        bool(kicker_include_date_raw)
        if isinstance(kicker_include_date_raw, bool)
        else None
    )
    subject_unit = str(rule.get("subject_unit") or "").strip()
    strip_state_suffix = bool(rule.get("strip_state_suffix", False))
    outcome_name = str(rule.get("outcome_name") or "Yes").strip()
    raw_band = rule.get("shared_rung_band")
    shared_rung_band: Optional[tuple[float, float]] = (
        (float(raw_band[0]), float(raw_band[1]))
        if isinstance(raw_band, (list, tuple)) and len(raw_band) == 2
        else None
    )
    strict_rungs_only = bool(rule.get("strict_rungs_only", False))
    lead_rule = str(rule.get("lead_rule") or "nearest_open_deadline").strip()
    closed_world = bool(rule.get("closed_world", False))
    min_numbered_members = int(
        rule.get("min_numbered_members", 2 if closed_world else 3)
    )
    raw_max_members = rule.get("max_members")
    max_members: Optional[int] = (
        int(raw_max_members)
        if isinstance(raw_max_members, int) and not isinstance(raw_max_members, bool)
        else (2 if closed_world else None)
    )
    card_rows = int(rule.get("card_rows", 2 if closed_world else 5))
    raw_window_days = rule.get("release_window_days")
    release_window_days: Optional[int] = (
        int(raw_window_days)
        if isinstance(raw_window_days, int) and not isinstance(raw_window_days, bool)
        else None
    )
    footer = str(
        definition.get("footer")
        or "Each row is its own market. They don't add up to 100%."
    ).strip()

    raw_sec_title = definition.get("section_title")
    if isinstance(raw_sec_title, (list, tuple)):
        section_titles: tuple[str, ...] = tuple(str(t) for t in raw_sec_title if str(t))
    elif isinstance(raw_sec_title, str) and raw_sec_title.strip():
        section_titles = (raw_sec_title.strip(),)
    else:
        section_titles = ()

    candidate_specs_raw = rule.get("candidates")
    candidate_ids: list[int] = []
    if isinstance(candidate_specs_raw, Sequence) and not isinstance(
        candidate_specs_raw, (str, bytes)
    ):
        for spec in candidate_specs_raw:
            _, mid = _parse_market_ref_id(str(spec))
            candidate_ids.append(mid)

    withheld_by_market: dict[int, set[int]] = {}
    if isinstance(db, Mapping):
        by_id = {
            int(k): v for k, v in db.items() if isinstance(v, Mapping)
        }
    elif isinstance(db, (list, tuple)):
        by_id = {
            int(m["id"]): m
            for m in db
            if isinstance(m, Mapping)
            and isinstance(m.get("id"), int)
            and not isinstance(m.get("id"), bool)
        }
    else:
        by_id, withheld_by_market = await _load_markets_from_db(
            db,
            group_id=group_id,
            candidate_ids=candidate_ids,
            title_ilike=title_ilike,
            expected_source=expected_source,
        )

    return select_sibling_family(
        by_id,
        expected_source=expected_source,
        template=template,
        title_template=title_template,
        kicker_prefix=kicker_prefix,
        kicker_include_date=kicker_include_date,
        subject_unit=subject_unit,
        strip_state_suffix=strip_state_suffix,
        outcome_name=outcome_name,
        shared_rung_band=shared_rung_band,
        strict_rungs_only=strict_rungs_only,
        lead_rule=lead_rule,
        closed_world=closed_world,
        min_numbered_members=min_numbered_members,
        max_members=max_members,
        card_rows=card_rows,
        section_titles=section_titles,
        footer=footer,
        release_window_days=release_window_days,
        now=now,
        withheld_by_market=withheld_by_market,
    )


def load_sibling_family_definition(
    path: Path = SNOW_FIRST_FLAKES_2026_DEFINITION_PATH,
) -> dict[str, Any]:
    """Load and validate a stored ``sibling_family`` JSON definition."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Container definition at {path} must be a JSON object")
    if data.get("membership") != MEMBERSHIP_SIBLING_FAMILY:
        raise ValueError(
            f"Container definition {path} must have membership={MEMBERSHIP_SIBLING_FAMILY!r}"
        )
    if data.get("kind") != "roundup":
        raise ValueError(f"Container definition {path} must have kind='roundup'")
    rule = data.get("rule")
    if not isinstance(rule, Mapping) or rule.get("producer") != PRODUCER_KIND_SIBLING_FAMILY:
        raise ValueError(
            f"Container definition {path} must declare rule.producer={PRODUCER_KIND_SIBLING_FAMILY!r}"
        )
    relations_raw = (
        data.get("relations") or rule.get("relations") or DEFAULT_SIBLING_RELATIONS
    )
    data["relations"] = [str(r) for r in relations_raw]
    data["level"] = str(
        data.get("level") or rule.get("level") or DEFAULT_SIBLING_LEVEL
    )
    raw_sec = data.get("section_title") or ""
    sec_texts = (
        tuple(str(x) for x in raw_sec)
        if isinstance(raw_sec, (list, tuple))
        else (str(raw_sec),)
    )
    _validate_narrative_copy(
        str(data.get("name") or ""),
        str(data.get("footer") or ""),
        str(data.get("kicker") or ""),
        *sec_texts,
    )
    return data


def load_sibling_family_definitions_from_dir(
    directory: Path = CONTAINERS_DATA_DIR,
) -> list[dict[str, Any]]:
    """Scan ``backend/data/containers/*.json`` and load every ``sibling_family`` definition (Decide 60-A)."""
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
        if isinstance(rule, Mapping) and rule.get("producer") == PRODUCER_KIND_SIBLING_FAMILY:
            definitions.append(load_sibling_family_definition(path))
    return definitions


def find_sibling_family_candidates(
    markets: Mapping[int, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    closed_world: bool = True,
    outcome_name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Finder listing every candidate card ``sibling_family`` could make from ``markets`` with refusal reasons (#12221 §4).

    When ``closed_world=True`` (Decide 59-A: "Two rivals, one market", Ruling 143),
    evaluates every structural template family with ``closed_world=True`` and ``max_members=2``
    so the pair finder seeds Row 4 of #12221 while applying the exact same verdict and
    refusal rules (including ``CERT-430: unpriced_legs``) as live serving.
    """
    from app.utils.week_events import export_roundup_card_words_390px

    rc = _rc()
    RoundupMembers = rc.RoundupMembers
    RoundupRefusal = rc.RoundupRefusal

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

    # Group candidate markets by (source, structural_template_key).
    by_source: dict[str, list[Mapping[str, Any]]] = {}
    for m in raw_list:
        src = str(m.get("source") or "").strip().lower()
        if not src:
            raw_srcs = m.get("sources")
            if (
                isinstance(raw_srcs, Sequence)
                and not isinstance(raw_srcs, (str, bytes))
                and raw_srcs
            ):
                src = str(raw_srcs[0] or "").strip().lower()
        src = src or "polymarket"
        by_source.setdefault(src, []).append(m)

    families: list[tuple[str, str, list[Mapping[str, Any]], dict[int, str]]] = []
    for src, src_markets in sorted(by_source.items()):
        stems = {
            int(m["id"]): _extract_stated_deadline(str(m.get("name") or "")).stem_text
            for m in src_markets
        }
        by_id = {int(m["id"]): m for m in src_markets}
        groups: dict[str, dict[int, str]] = {}
        n = len(src_markets)
        for i in range(n):
            id_i = int(src_markets[i]["id"])
            for j in range(i + 1, n):
                id_j = int(src_markets[j]["id"])
                res, _err = detect_sibling_template_pair(stems[id_i], stems[id_j])
                if res is None:
                    continue
                t_key, subj_i, subj_j = res
                bucket = groups.setdefault(t_key, {})
                bucket.setdefault(id_i, subj_i)
                bucket.setdefault(id_j, subj_j)
        for t_key, subj_map in sorted(groups.items()):
            member_list = [by_id[mid] for mid in sorted(subj_map.keys())]
            families.append((src, t_key, member_list, subj_map))

    candidates_out: list[dict[str, Any]] = []
    for src, t_key, member_list, subj_map in families:
        # Determine target outcome name if not explicitly provided:
        effective_outcome = outcome_name
        if not effective_outcome:
            # Check if member markets are binary Yes/No or share a non-Yes/No rung
            first_outs = member_list[0].get("outcomes") or member_list[0].get("top_outcomes") or ()
            out_names = [
                str(o.get("name") or o.get("label") or "").strip()
                for o in first_outs
                if isinstance(o, Mapping)
            ]
            if set(n.lower() for n in out_names if n) <= {"yes", "no"} or not out_names:
                effective_outcome = "Yes"
            else:
                # Prefer "2+" rung if present (e.g. Grand Slam wins), else first outcome label
                two_plus = next((n for n in out_names if "2+" in n), None)
                effective_outcome = two_plus or out_names[0]

        kicker_pref = "HEAD TO HEAD" if closed_world else "SIBLING FAMILY"
        footer_text = (
            "Each subject is their own market; both can happen."
            if closed_world
            else "Each row is its own market. They don't add up to 100%."
        )
        slug_base = re.sub(r"[^a-z0-9]+", "-", t_key).strip("-")[:48]
        synth_def = {
            "slug": f"{src}-{slug_base}",
            "kicker": kicker_pref,
            "name": t_key,
            "category": str(member_list[0].get("category") or "other"),
            "tag": str(member_list[0].get("category") or "OTHER").upper(),
            "footer": footer_text,
        }
        verdict_obj = select_sibling_family(
            member_list,
            expected_source=src,
            template=t_key,
            title_template=t_key,
            kicker_prefix=kicker_pref,
            kicker_include_date=not closed_world,
            outcome_name=effective_outcome,
            lead_rule="single_deadline" if closed_world else "nearest_open_deadline",
            closed_world=closed_world,
            min_numbered_members=2 if closed_world else 3,
            max_members=2 if closed_world else None,
            card_rows=2 if closed_world else 5,
            footer=footer_text,
            now=now,
        )
        cleaned_subjects = [
            _clean_subject_display(s, strip_state_suffix=False)
            for _, s in sorted(subj_map.items())
        ]
        if isinstance(verdict_obj, RoundupMembers):
            candidates_out.append(
                {
                    "template_key": t_key,
                    "source": src,
                    "outcome_name": effective_outcome,
                    "member_ids": [int(m["id"]) for m in member_list],
                    "subjects": cleaned_subjects,
                    "relations": list(DEFAULT_SIBLING_RELATIONS),
                    "level": DEFAULT_SIBLING_LEVEL,
                    "closed_world": closed_world,
                    "verdict": "serve",
                    "refusal_reasons": [],
                    "unpriced_legs": [],
                    "card_words_390px": export_roundup_card_words_390px(
                        verdict_obj, synth_def
                    ),
                }
            )
        else:
            reasons_raw = (
                list(verdict_obj.reasons)
                if isinstance(verdict_obj, RoundupRefusal)
                else []
            )
            reason_dict = dict(
                r for r in reasons_raw if isinstance(r, tuple) and len(r) == 2
            )
            fam_reason = str(reason_dict.get("family") or "refused")
            unpriced_legs = list(reason_dict.get("unpriced_legs") or ())
            candidates_out.append(
                {
                    "template_key": t_key,
                    "source": src,
                    "outcome_name": effective_outcome,
                    "member_ids": [int(m["id"]) for m in member_list],
                    "subjects": cleaned_subjects,
                    "relations": list(DEFAULT_SIBLING_RELATIONS),
                    "level": DEFAULT_SIBLING_LEVEL,
                    "closed_world": closed_world,
                    "verdict": "refuse",
                    "refusal_reasons": [fam_reason],
                    "unpriced_legs": unpriced_legs,
                    "card_words_390px": None,
                }
            )
    return candidates_out


def build_sibling_family_producer(
    definition: Mapping[str, Any],
    *,
    enabled: Optional[Callable[[], bool]] = None,
) -> Any:
    """Instantiate a ``RoundupProducer`` from a stored ``sibling_family`` definition."""
    RoundupProducer = _rc().RoundupProducer
    slug = str(definition["slug"])
    name = str(definition["name"])
    kind = str(definition.get("kind") or "roundup")
    category = str(definition.get("category") or "cross-topic")
    section_title = definition.get("section_title") or ""
    footer = str(definition["footer"])
    membership = str(definition.get("membership") or MEMBERSHIP_SIBLING_FAMILY)
    rule = definition.get("rule")
    tag = (
        str(definition["tag"])
        if "tag" in definition and definition["tag"] is not None
        else ""
    )
    kicker = str(definition.get("kicker") or "SIBLING FAMILY")
    story_key = f"roundup:{slug.removeprefix('roundup-')}"

    async def _produce(db: Any) -> Any:
        return await produce_sibling_family(db, definition)

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
        enabled=enabled if enabled is not None else sibling_family_enabled,
    )


SNOW_FIRST_FLAKES_2026_DEFINITION: dict[str, Any] = load_sibling_family_definition(
    SNOW_FIRST_FLAKES_2026_DEFINITION_PATH
)

GTA_VI_ALBUM_FEATURES_DEFINITION: dict[str, Any] = load_sibling_family_definition(
    GTA_VI_ALBUM_FEATURES_DEFINITION_PATH
)

RT_SCORES_THIS_WEEK_DEFINITION: dict[str, Any] = load_sibling_family_definition(
    RT_SCORES_THIS_WEEK_DEFINITION_PATH
)

WHO_ANNOUNCES_BEFORE_2027_DEFINITION: dict[str, Any] = load_sibling_family_definition(
    WHO_ANNOUNCES_BEFORE_2027_DEFINITION_PATH
)

ALCARAZ_SINNER_TWO_MAJORS_2027_DEFINITION: dict[str, Any] = (
    load_sibling_family_definition(ALCARAZ_SINNER_TWO_MAJORS_2027_DEFINITION_PATH)
)


async def snow_first_flakes_2026(
    db: Any, *, now: Optional[datetime] = None
) -> Any:
    """Produce ``RoundupMembers`` (or ``RoundupRefusal``) for ``snow-first-flakes-2026``."""
    return await produce_sibling_family(
        db, SNOW_FIRST_FLAKES_2026_DEFINITION, now=now
    )


async def gta_vi_album_features(
    db: Any, *, now: Optional[datetime] = None
) -> Any:
    """Produce ``RoundupMembers`` (or ``RoundupRefusal``) for ``gta-vi-album-features``."""
    return await produce_sibling_family(
        db, GTA_VI_ALBUM_FEATURES_DEFINITION, now=now
    )


async def rt_scores_this_week(
    db: Any, *, now: Optional[datetime] = None
) -> Any:
    """Produce ``RoundupMembers`` (or ``RoundupRefusal``) for ``rt-scores-this-week``."""
    return await produce_sibling_family(
        db, RT_SCORES_THIS_WEEK_DEFINITION, now=now
    )


async def who_announces_before_2027(
    db: Any, *, now: Optional[datetime] = None
) -> Any:
    """Produce ``RoundupMembers`` (or ``RoundupRefusal``) for ``who-announces-before-2027``."""
    return await produce_sibling_family(
        db, WHO_ANNOUNCES_BEFORE_2027_DEFINITION, now=now
    )


async def alcaraz_sinner_two_majors_2027(
    db: Any, *, now: Optional[datetime] = None
) -> Any:
    """Produce ``RoundupMembers`` (or ``RoundupRefusal``) for ``alcaraz-sinner-two-majors-2027``."""
    return await produce_sibling_family(
        db, ALCARAZ_SINNER_TWO_MAJORS_2027_DEFINITION, now=now
    )


SNOW_FIRST_FLAKES_2026_PRODUCER = build_sibling_family_producer(
    SNOW_FIRST_FLAKES_2026_DEFINITION
)

GTA_VI_ALBUM_FEATURES_PRODUCER = build_sibling_family_producer(
    GTA_VI_ALBUM_FEATURES_DEFINITION
)

RT_SCORES_THIS_WEEK_PRODUCER = build_sibling_family_producer(
    RT_SCORES_THIS_WEEK_DEFINITION
)

WHO_ANNOUNCES_BEFORE_2027_PRODUCER = build_sibling_family_producer(
    WHO_ANNOUNCES_BEFORE_2027_DEFINITION
)

ALCARAZ_SINNER_TWO_MAJORS_2027_PRODUCER = build_sibling_family_producer(
    ALCARAZ_SINNER_TWO_MAJORS_2027_DEFINITION
)

_NAMED_SIBLING_PRODUCERS = {
    SNOW_FIRST_FLAKES_2026_SLUG: SNOW_FIRST_FLAKES_2026_PRODUCER,
    GTA_VI_ALBUM_FEATURES_SLUG: GTA_VI_ALBUM_FEATURES_PRODUCER,
    RT_SCORES_THIS_WEEK_SLUG: RT_SCORES_THIS_WEEK_PRODUCER,
    WHO_ANNOUNCES_BEFORE_2027_SLUG: WHO_ANNOUNCES_BEFORE_2027_PRODUCER,
    ALCARAZ_SINNER_TWO_MAJORS_2027_SLUG: ALCARAZ_SINNER_TWO_MAJORS_2027_PRODUCER,
}
for _sf_def in load_sibling_family_definitions_from_dir():
    _sf_slug = _sf_def["slug"]
    _rc().register_roundup_producer(
        _NAMED_SIBLING_PRODUCERS.get(_sf_slug)
        or build_sibling_family_producer(_sf_def)
    )
