"""Pure helpers for Content Understanding dual-rater fact labeling (#13900).

Design invariants:
1. Blindness: neither primary nor second rater ever sees the other's answers on
   a market while labeling. A tiebreak rater sees both fact answers only after
   both raters have submitted and disagree on >= 1 fact field.
2. Taste isolation: stakes and breadth are rated last (1-5), agreement counts
   within 1 step, and taste disagreements are NEVER tie-broken — they go to Alex.
3. No real labeler identities appear anywhere in code or defaults. Labelers type
   their own name in the UI.
4. No LLM `discover_llm` metadata is exposed in labeling candidates.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.utils.cu_frame import (
    _CURRENCY_SIGNS,
    _TITLE_DATES,
    _normalize_window_date,
    COMPARATORS,
    FRAME_SLOTS,
    HORIZON_KINDS,
    MEASURES,
    normalize_comparator,
    normalize_horizon_kind,
    normalize_measure,
    normalize_value,
)

VALID_SPLITS: tuple[str, ...] = ("sealed", "dev")
VALID_ROLES: tuple[str, ...] = ("primary", "second", "tiebreak")
VALID_SCOPES: tuple[str, ...] = ("shared_100", "all")
VALID_STRUCTURES: tuple[str, ...] = ("ladder", "dated_bucket", "neither")
VALID_SUBJECT_MODES: tuple[str, ...] = ("candidate", "custom", "none_of_these", "not_sure")
FACT_FIELDS: tuple[str, ...] = ("subjects", "event_date", "geography", "structure", "claim_frame")
TASTE_FIELDS: tuple[str, ...] = ("stakes", "breadth")
CLAIM_SLOTS: tuple[str, ...] = FRAME_SLOTS
NONE_OF_THESE = "none_of_these"

SHARED_100_SEED_PREFIX = "cu-shared-100-v1:"
SHARED_100_TARGET = 100
SHARED_100_READER_WEIGHTED_TARGET = 67

_BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATHS: dict[str, Path] = {
    "sealed": _BACKEND_DIR / "data" / "evals" / "cu_sealed_300_v1.json",
    "dev": _BACKEND_DIR / "data" / "evals" / "cu_dev_200_v1.json",
}
DEFAULT_REPEATABILITY_PATH = _BACKEND_DIR / "data" / "evals" / "cu_dev_shared_100_ids_v1.json"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CANONICAL_WINDOW_DATE_RE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}|\d{4}-\d{2}|\d{4}|--\d{2}-\d{2})$")
_THOUSANDS_COMMA_RE = re.compile(r"(?<=\d),(?=\d{3}\b)")
_COUNTRY_CODE_RE = re.compile(r"^country:([A-Za-z]{2})$")
_BARE_ALPHA2_RE = re.compile(r"^[A-Za-z]{2}$")
_CURRENCY_SIGNS_CLASS = "".join(re.escape(c) for c in _CURRENCY_SIGNS)
_LEADING_CURRENCY_VALUE_RE = re.compile(
    rf"^\s*([+\-−]?)\s*([{_CURRENCY_SIGNS_CLASS}])\s*(.+?)\s*$"
)

# Canonical ISO 3166-1 alpha-2 codes + English names (excluding custom alias helpers below).
ISO_COUNTRY_NAMES: dict[str, str] = {
    "AF": "Afghanistan", "AL": "Albania", "DZ": "Algeria", "AD": "Andorra", "AO": "Angola",
    "AG": "Antigua and Barbuda", "AR": "Argentina", "AM": "Armenia", "AU": "Australia",
    "AT": "Austria", "AZ": "Azerbaijan", "BS": "Bahamas", "BH": "Bahrain", "BD": "Bangladesh",
    "BB": "Barbados", "BY": "Belarus", "BE": "Belgium", "BZ": "Belize", "BJ": "Benin",
    "BT": "Bhutan", "BO": "Bolivia", "BA": "Bosnia and Herzegovina", "BW": "Botswana",
    "BR": "Brazil", "BN": "Brunei", "BG": "Bulgaria", "BF": "Burkina Faso", "BI": "Burundi",
    "CV": "Cabo Verde", "KH": "Cambodia", "CM": "Cameroon", "CA": "Canada",
    "CF": "Central African Republic", "TD": "Chad", "CL": "Chile", "CN": "China",
    "CO": "Colombia", "KM": "Comoros", "CG": "Congo", "CD": "DR Congo", "CR": "Costa Rica",
    "CI": "Cote d'Ivoire", "HR": "Croatia", "CU": "Cuba", "CY": "Cyprus",
    "CZ": "Czech Republic", "DK": "Denmark", "DJ": "Djibouti", "DM": "Dominica",
    "DO": "Dominican Republic", "EC": "Ecuador", "EG": "Egypt", "SV": "El Salvador",
    "GQ": "Equatorial Guinea", "ER": "Eritrea", "EE": "Estonia", "SZ": "Eswatini",
    "ET": "Ethiopia", "FJ": "Fiji", "FI": "Finland", "FR": "France", "GA": "Gabon",
    "GM": "Gambia", "GE": "Georgia", "DE": "Germany", "GH": "Ghana", "GR": "Greece",
    "GD": "Grenada", "GT": "Guatemala", "GN": "Guinea", "GW": "Guinea-Bissau",
    "GY": "Guyana", "HT": "Haiti", "HN": "Honduras", "HK": "Hong Kong", "HU": "Hungary",
    "IS": "Iceland", "IN": "India", "ID": "Indonesia", "IR": "Iran", "IQ": "Iraq",
    "IE": "Ireland", "IL": "Israel", "IT": "Italy", "JM": "Jamaica", "JP": "Japan",
    "JO": "Jordan", "KZ": "Kazakhstan", "KE": "Kenya", "KI": "Kiribati",
    "KP": "North Korea", "KR": "South Korea", "XK": "Kosovo", "KW": "Kuwait",
    "KG": "Kyrgyzstan", "LA": "Laos", "LV": "Latvia", "LB": "Lebanon", "LS": "Lesotho",
    "LR": "Liberia", "LY": "Libya", "LI": "Liechtenstein", "LT": "Lithuania",
    "LU": "Luxembourg", "MO": "Macao", "MG": "Madagascar", "MW": "Malawi",
    "MY": "Malaysia", "MV": "Maldives", "ML": "Mali", "MT": "Malta",
    "MH": "Marshall Islands", "MR": "Mauritania", "MU": "Mauritius", "MX": "Mexico",
    "FM": "Micronesia", "MD": "Moldova", "MC": "Monaco", "MN": "Mongolia",
    "ME": "Montenegro", "MA": "Morocco", "MZ": "Mozambique", "MM": "Myanmar",
    "NA": "Namibia", "NR": "Nauru", "NP": "Nepal", "NL": "Netherlands",
    "NZ": "New Zealand", "NI": "Nicaragua", "NE": "Niger", "NG": "Nigeria",
    "MK": "North Macedonia", "NO": "Norway", "OM": "Oman", "PK": "Pakistan", "PW": "Palau",
    "PS": "Palestine", "PA": "Panama", "PG": "Papua New Guinea", "PY": "Paraguay",
    "PE": "Peru", "PH": "Philippines", "PL": "Poland", "PT": "Portugal", "PR": "Puerto Rico",
    "QA": "Qatar", "RO": "Romania", "RU": "Russia", "RW": "Rwanda",
    "KN": "Saint Kitts and Nevis", "LC": "Saint Lucia",
    "VC": "Saint Vincent and the Grenadines", "WS": "Samoa", "SM": "San Marino",
    "ST": "Sao Tome and Principe", "SA": "Saudi Arabia", "SN": "Senegal", "RS": "Serbia",
    "SC": "Seychelles", "SL": "Sierra Leone", "SG": "Singapore", "SK": "Slovakia",
    "SI": "Slovenia", "SB": "Solomon Islands", "SO": "Somalia", "ZA": "South Africa",
    "SS": "South Sudan", "ES": "Spain", "LK": "Sri Lanka", "SD": "Sudan",
    "SR": "Suriname", "SE": "Sweden", "CH": "Switzerland", "SY": "Syria",
    "TW": "Taiwan", "TJ": "Tajikistan", "TZ": "Tanzania", "TH": "Thailand",
    "TL": "Timor-Leste", "TG": "Togo", "TO": "Tonga", "TT": "Trinidad and Tobago",
    "TN": "Tunisia", "TR": "Turkey", "TM": "Turkmenistan", "TV": "Tuvalu",
    "UG": "Uganda", "UA": "Ukraine", "AE": "United Arab Emirates", "GB": "United Kingdom",
    "US": "United States", "UY": "Uruguay", "UZ": "Uzbekistan", "VU": "Vanuatu",
    "VA": "Vatican City", "VE": "Venezuela", "VN": "Vietnam", "YE": "Yemen",
    "ZM": "Zambia", "ZW": "Zimbabwe",
}
_COUNTRY_NAME_ALIASES: dict[str, str] = {
    **{name.lower(): code for code, name in ISO_COUNTRY_NAMES.items()},
    "uk": "GB",
    "u.k.": "GB",
    "britain": "GB",
    "great britain": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "northern ireland": "GB",
    "usa": "US",
    "u.s.": "US",
    "u.s.a.": "US",
    "america": "US",
    "united states of america": "US",
    "uae": "AE",
    "czechia": "CZ",
    "ivory coast": "CI",
    "côte d'ivoire": "CI",
    "türkiye": "TR",
    "turkiye": "TR",
    "cape verde": "CV",
    "burma": "MM",
    "republic of korea": "KR",
    "democratic republic of the congo": "CD",
    "republic of the congo": "CG",
    "russian federation": "RU",
    "swaziland": "SZ",
    "holy see": "VA",
    "palestinian territories": "PS",
    "macau": "MO",
}

_QUESTION_WORDS = frozenset({
    "will", "who", "what", "when", "where", "which", "how",
    "is", "are", "was", "were", "does", "do", "did",
    "can", "could", "would", "should", "has", "have", "had",
})
_LEADING_CHIP_STRIP = _QUESTION_WORDS | frozenset({
    "the", "a", "an", "any", "another", "next", "before", "after", "by",
    "in", "on", "at", "for", "of", "to", "from", "with", "during",
    "rain", "snow", "snowfall", "highest", "lowest", "temperature", "total",
    "average", "most", "least",
})
_TRAILING_CHIP_STRIP = frozenset({
    "the", "a", "an", "of", "and", "or", "for", "in", "on", "at", "by", "to",
    "vs", "v", "y", "de",
})
_GENERIC_CHIP_WORDS = _QUESTION_WORDS | _LEADING_CHIP_STRIP | _TRAILING_CHIP_STRIP | frozenset({
    "yes", "no", "over", "under", "above", "below", "more", "less",
    "winner", "champion", "first", "last", "new", "all", "other", "none",
    "best", "worst", "top", "artist", "ai", "model", "country", "state",
    "city", "game", "match", "team", "player", "person", "market", "score",
    "price", "rate", "number", "count", "season", "year", "month", "week",
    "day", "time", "military", "action", "open", "close", "high", "low",
    "home", "away", "tie", "draw", "neither", "both", "two", "three",
    "four", "five", "percent", "points", "goals", "wins", "runs", "votes",
    "inc", "corp", "ltd", "llc", "plc",
})
_DATE_ONLY_CHIP_RE = re.compile(
    r"^(?:(?:before|after|by|on|in|until|through|end of|week of)\s+)?"
    r"(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
    r"(?:\s+\d{1,2}(?:st|nd|rd|th)?)?(?:,?\s+\d{4})?"
    r"(?:\s*[-–]\s*(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+)?"
    r"\d{1,2}(?:,?\s+\d{4})?)?"
    r"|q[1-4]\s+\d{4}|\d{4}(?:[-–]\d{2,4})?|(?:mon|tues|wednes|thurs|fri|satur|sun)day)$",
    re.IGNORECASE,
)
_TITLE_CANDIDATE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Z][A-Za-z0-9&'.-]*"
    r"(?:\s+(?:of|the|and|for|in|on|at|vs\.?|v\.|y|de|del|la|el|van|von|al|"
    r"[A-Z][A-Za-z0-9&'.-]*|\d{1,3}(?![\d%$.,])))*)"
)
_OUTCOME_SKIP_PREFIXES = (
    "above ", "below ", "over ", "under ", "before ", "after ", "by ",
    "more than ", "less than ", "at least ", "at most ", "between ",
)
_ABBREV_END_RE = re.compile(r"(?:^|[.\s])[A-Za-z]\.$")


def frozen_split_exists(
    split: str,
    *,
    dataset_paths: dict[str, Path] | None = None,
) -> bool:
    if split not in VALID_SPLITS:
        raise ValueError(f"Unsupported dataset split: {split!r}")
    paths = dataset_paths or DEFAULT_DATASET_PATHS
    path = paths.get(split)
    return bool(path and path.exists())


def get_claim_vocabulary() -> dict[str, list[str]]:
    """Return writer claim choices (with 'none_of_these') for the labeling UI."""
    return {
        "measures": sorted(MEASURES),
        "comparators": sorted(COMPARATORS),
        "horizon_kinds": sorted(HORIZON_KINDS),
        "special_options": [NONE_OF_THESE],
    }


def load_frozen_split(
    split: str,
    *,
    dataset_paths: dict[str, Path] | None = None,
) -> list[dict[str, Any]]:
    if split not in VALID_SPLITS:
        raise ValueError(f"Unsupported dataset split: {split!r}")
    paths = dataset_paths or DEFAULT_DATASET_PATHS
    path = paths.get(split)
    if not path or not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    markets = payload.get("markets")
    return list(markets) if isinstance(markets, list) else []


def load_repeatability_priority_ids(repeatability_path: Path | None = None) -> list[int]:
    path = repeatability_path or DEFAULT_REPEATABILITY_PATH
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        raw_ids = payload
    elif isinstance(payload, dict) and isinstance(payload.get("market_ids"), list):
        raw_ids = payload["market_ids"]
    elif isinstance(payload, dict):
        raw_ids = [
            row.get("market_id")
            for row in (payload.get("comparison", {}).get("changed_markets") or [])
            if isinstance(row, dict)
        ]
    else:
        return []
    out: list[int] = []
    for item in raw_ids:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _shared_sort_key(market_id: int) -> str:
    return hashlib.sha256(f"{SHARED_100_SEED_PREFIX}{market_id}".encode("utf-8")).hexdigest()


def select_shared_100_ids(markets: list[dict[str, Any]]) -> list[int]:
    """Deterministically pick the shared 100 markets (67 reader-weighted + 33 spread)."""
    if len(markets) <= SHARED_100_TARGET:
        return [int(m["market_id"]) for m in markets]

    reader = sorted(
        (m for m in markets if m.get("draw_bucket") == "reader_weighted"),
        key=lambda m: _shared_sort_key(int(m["market_id"])),
    )
    other = sorted(
        (m for m in markets if m.get("draw_bucket") != "reader_weighted"),
        key=lambda m: _shared_sort_key(int(m["market_id"])),
    )
    rw_take = reader[:SHARED_100_READER_WEIGHTED_TARGET]
    rem = SHARED_100_TARGET - len(rw_take)
    other_take = other[:rem]
    selected = rw_take + other_take
    if len(selected) < SHARED_100_TARGET:
        used = {int(m["market_id"]) for m in selected}
        leftover = [
            m
            for m in sorted(markets, key=lambda m: _shared_sort_key(int(m["market_id"])))
            if int(m["market_id"]) not in used
        ]
        selected.extend(leftover[: SHARED_100_TARGET - len(selected)])
    selected.sort(key=lambda m: _shared_sort_key(int(m["market_id"])))
    return [int(m["market_id"]) for m in selected]


def order_queue_markets(
    markets: list[dict[str, Any]],
    *,
    split: str,
    scope: str = "shared_100",
    repeatability_priority_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Order labeling queue: dev leads with #13899 changed markets; sealed supports shared_100."""
    by_id = {int(m["market_id"]): m for m in markets}
    if split == "dev":
        ordered_ids: list[int] = []
        seen: set[int] = set()
        for mid in repeatability_priority_ids or []:
            if mid in by_id and mid not in seen:
                ordered_ids.append(mid)
                seen.add(mid)
        for m in markets:
            mid = int(m["market_id"])
            if mid not in seen:
                ordered_ids.append(mid)
                seen.add(mid)
        ordered = [by_id[mid] for mid in ordered_ids]
        return ordered[:SHARED_100_TARGET] if scope == "shared_100" else ordered

    shared_ids = select_shared_100_ids(markets)
    if scope == "shared_100":
        return [by_id[mid] for mid in shared_ids if mid in by_id]
    shared_set = set(shared_ids)
    rest = [m for m in markets if int(m["market_id"]) not in shared_set]
    return [by_id[mid] for mid in shared_ids if mid in by_id] + rest


def _clean_subject_chip(raw: str) -> str | None:
    """Strip leading question/filler words, dates, and generic phrases from one candidate."""
    s = " ".join(raw.split()).strip(" ,:;?\"'()")
    if s.endswith(".") and not _ABBREV_END_RE.search(s):
        s = s.rstrip(".")
    tokens = s.split()
    while tokens and tokens[0].lower().rstrip(".") in _LEADING_CHIP_STRIP:
        tokens.pop(0)
    while tokens and tokens[-1].lower().rstrip(".") in _TRAILING_CHIP_STRIP:
        tokens.pop()
    s = " ".join(tokens).strip(" ,:;?\"'()")
    if s.endswith(".") and not _ABBREV_END_RE.search(s):
        s = s.rstrip(".")
    if not s or len(s) < 2 or len(s) > 80:
        return None
    if s[0].isdigit():
        return None
    if _DATE_ONLY_CHIP_RE.match(s):
        return None
    norm_tokens = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in s.split()]
    norm_tokens = [t for t in norm_tokens if t]
    if not norm_tokens or all(t in _GENERIC_CHIP_WORDS for t in norm_tokens):
        return None
    return s


def extract_subject_candidates(market: dict[str, Any]) -> list[str]:
    """Blind candidate extraction strictly from title + outcomes (never from LLM output)."""
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        cleaned = _clean_subject_chip(raw)
        if not cleaned:
            return
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            candidates.append(cleaned)

    title = str(market.get("title") or "")
    # Remove explicit dates before scanning capitalized runs so trailing prepositions/months
    # like "Rain in Chicago in Nov 2026?" yield "Chicago" rather than "... in Nov".
    dateless_title = _TITLE_DATES.sub(" ", title)
    for match in _TITLE_CANDIDATE_RE.findall(dateless_title):
        _add(match)

    outcomes = market.get("outcome_names") or [
        o.get("name") for o in (market.get("outcomes") or []) if isinstance(o, dict)
    ]
    for outcome_name in outcomes[:12]:
        if isinstance(outcome_name, str):
            text = outcome_name.strip()
            if (
                text
                and not text.lower().startswith(_OUTCOME_SKIP_PREFIXES)
                and not re.match(r"^[$£€¥₹₩+\-<>0-9]", text)
            ):
                _add(text)
    return candidates[:12]


def normalize_subjects_answer(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("subjects_answer must be an object")
    mode = str(raw.get("selection_kind") or "").strip().lower()
    if mode not in VALID_SUBJECT_MODES:
        raise ValueError(f"subjects_answer.selection_kind must be one of {VALID_SUBJECT_MODES}")
    selected_raw = raw.get("selected") or []
    if not isinstance(selected_raw, list):
        raise ValueError("subjects_answer.selected must be a list")
    selected = sorted({" ".join(str(x).split()).strip() for x in selected_raw if str(x).strip()})
    if mode in {"candidate", "custom"} and not selected:
        raise ValueError(f"subjects_answer.selected is required when selection_kind={mode!r}")
    if mode in {"none_of_these", "not_sure"}:
        selected = []
    return {"selection_kind": mode, "selected": selected}


def normalize_geography_answer(raw: Any) -> str | None:
    if raw is None:
        return None
    text = " ".join(str(raw).split()).strip()
    if not text:
        return None
    low = text.lower()
    if low in {"us", "global", "local"}:
        return low
    m = _COUNTRY_CODE_RE.match(text)
    if m:
        code = m.group(1).upper()
        if code == "US":
            return "us"
        if code not in ISO_COUNTRY_NAMES:
            raise ValueError(f"Unsupported ISO country code: country:{code}")
        return f"country:{code}"
    if _BARE_ALPHA2_RE.match(text):
        code = text.upper()
        if code == "US":
            return "us"
        if code in ISO_COUNTRY_NAMES:
            return f"country:{code}"
    if low in _COUNTRY_NAME_ALIASES:
        code = _COUNTRY_NAME_ALIASES[low]
        return "us" if code == "US" else f"country:{code}"
    raise ValueError(
        "geography_answer must be 'us', 'global', 'local', or a valid country code/name"
    )


def _normalize_vocab_slot(raw: Any, slot: str) -> str | None:
    if raw is None:
        return None
    text = " ".join(str(raw).split()).strip()
    if not text:
        return None
    if text.lower().replace(" ", "_") == NONE_OF_THESE:
        return NONE_OF_THESE
    if slot == "measure":
        norm = normalize_measure(text)
        if not norm:
            raise ValueError(f"claim_frame.measure {text!r} must be a known measure or 'none_of_these'")
        return norm
    if slot == "comparator":
        norm = normalize_comparator(text)
        if not norm:
            raise ValueError(f"claim_frame.comparator {text!r} must be a known comparator or 'none_of_these'")
        return norm
    if slot == "horizon_kind":
        norm = normalize_horizon_kind(text)
        if not norm:
            raise ValueError(f"claim_frame.horizon_kind {text!r} must be a known deadline kind or 'none_of_these'")
        return norm
    return text


def _split_value_and_unit(raw_val: str | None, raw_unit: str | None) -> tuple[str | None, str | None]:
    """Extract currency/percent sign from value when typed inline (e.g. '$100,000' -> '100,000', '$')."""
    if raw_val is None:
        return None, raw_unit
    val_text = raw_val
    unit_text = raw_unit

    m_cur = _LEADING_CURRENCY_VALUE_RE.match(val_text)
    if m_cur:
        sign, cur, rest = m_cur.group(1), m_cur.group(2), m_cur.group(3)
        candidate = f"{sign}{rest}".strip()
        cleaned_num = normalize_value(candidate)
        if cleaned_num is not None:
            val_text = cleaned_num
            if not unit_text:
                unit_text = cur
            return val_text, unit_text

    if val_text.endswith("%"):
        cleaned_num = normalize_value(val_text[:-1].strip())
        if cleaned_num is not None:
            val_text = cleaned_num
            if not unit_text:
                unit_text = "%"
            return val_text, unit_text

    cleaned_num = normalize_value(val_text)
    return (cleaned_num if cleaned_num is not None else val_text), unit_text


def _infer_currency_unit_from_title(value: str | None, title: str | None) -> str | None:
    """When unit was left blank, recover leading currency symbol directly before `value` in title."""
    if not value or not title:
        return None
    escaped = re.escape(value)
    pattern = re.compile(
        r"(?<![0-9A-Za-z.])(?<!\d-)(?<![+\-−])(?<!\d,)"
        + escaped
        + r"(?![0-9A-Za-z])(?!\.\d)(?!,\d{3}(?:\D|$))",
        re.IGNORECASE,
    )
    candidates = [title]
    stripped = _THOUSANDS_COMMA_RE.sub("", title)
    if stripped != title:
        candidates.append(stripped)
    found: set[str] = set()
    for text in candidates:
        for match in pattern.finditer(text):
            before = text[: match.start()].rstrip()
            if before and before[-1] in _CURRENCY_SIGNS:
                found.add(before[-1])
    return next(iter(found)) if len(found) == 1 else None


def _clean_window_date(raw_wd: str | None, title: str | None) -> str | None:
    if not raw_wd:
        return None
    if _CANONICAL_WINDOW_DATE_RE.match(raw_wd):
        return raw_wd
    if title:
        cleaned = _normalize_window_date(raw_wd, title)
        if cleaned:
            return cleaned
    cleaned_self = _normalize_window_date(raw_wd, raw_wd)
    return cleaned_self or raw_wd


def normalize_claim_frame(raw: Any, *, title: str | None = None) -> dict[str, Any] | None:
    """Validate and normalize one claim frame, keeping raw typed text alongside cleaned slots."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("claim_frame must be an object or null")

    existing_raw = raw.get("raw") if isinstance(raw.get("raw"), dict) else None
    raw_slots: dict[str, str | None] = {}
    any_set = False
    for slot in CLAIM_SLOTS:
        src_val = existing_raw.get(slot) if existing_raw and slot in existing_raw else raw.get(slot)
        if src_val is None:
            s = None
        else:
            trimmed = " ".join(str(src_val).split()).strip()
            s = trimmed or None
        raw_slots[slot] = s
        if s is not None:
            any_set = True

    if not any_set:
        return None

    measure = _normalize_vocab_slot(raw_slots["measure"], "measure")
    comparator = _normalize_vocab_slot(raw_slots["comparator"], "comparator")
    horizon_kind = _normalize_vocab_slot(raw_slots["horizon_kind"], "horizon_kind")

    clean_value, clean_unit = _split_value_and_unit(raw_slots["value"], raw_slots["unit"])
    if clean_value and not clean_unit and title:
        inferred = _infer_currency_unit_from_title(clean_value, title)
        if inferred:
            clean_unit = inferred
    clean_window_date = _clean_window_date(raw_slots["window_date"], title)

    return {
        "measure": measure,
        "comparator": comparator,
        "value": clean_value,
        "unit": clean_unit,
        "horizon_kind": horizon_kind,
        "window_date": clean_window_date,
        "raw": raw_slots,
    }


def validate_label_submission(
    payload: dict[str, Any],
    *,
    existing_market_rows: list[dict[str, Any]] | None = None,
    market_title: str | None = None,
) -> dict[str, Any]:
    """Validate and normalize one CU fact-labeling or tiebreak submission."""
    split = str(payload.get("dataset_split") or "").strip().lower()
    if split not in VALID_SPLITS:
        raise ValueError(f"Invalid dataset_split {split!r}")

    role = str(payload.get("role") or "").strip().lower()
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role {role!r}")

    rater = " ".join(str(payload.get("rater") or "").split()).strip()
    if not rater or len(rater) > 64:
        raise ValueError("rater must be a non-empty typed name (<= 64 chars)")

    try:
        market_id = int(payload.get("market_id"))
    except (TypeError, ValueError) as exc:
        raise ValueError("market_id must be an integer") from exc

    no_single_day = bool(payload.get("no_single_day", False))
    event_date_raw = payload.get("event_date_answer")
    event_date: str | None
    if no_single_day or event_date_raw is None or not str(event_date_raw).strip():
        event_date = None
    else:
        event_date = str(event_date_raw).strip()
        if not _DATE_RE.match(event_date):
            raise ValueError("event_date_answer must be YYYY-MM-DD when provided")

    structure_raw = payload.get("structure_answer")
    if structure_raw is None:
        raise ValueError("structure_answer is required")
    structure = str(structure_raw).strip().lower()
    if structure not in VALID_STRUCTURES:
        raise ValueError(f"structure_answer must be one of {VALID_STRUCTURES}")

    subjects = normalize_subjects_answer(payload.get("subjects_answer"))
    geography = normalize_geography_answer(payload.get("geography_answer"))
    if not geography:
        raise ValueError("geography_answer is required (us, global, local, or a country)")
    claim_frame = normalize_claim_frame(payload.get("claim_frame"), title=market_title)

    evidence_note_raw = payload.get("evidence_note")
    evidence_note = str(evidence_note_raw).strip() if evidence_note_raw is not None else None
    if evidence_note == "":
        evidence_note = None

    stakes = payload.get("stakes")
    breadth = payload.get("breadth")

    if role == "tiebreak":
        # Standing #13900 rule: taste is NEVER tie-broken (goes to Alex).
        if stakes is not None or breadth is not None:
            raise ValueError("stakes and breadth cannot be submitted in tiebreak mode")
        if not evidence_note:
            raise ValueError("evidence_note explaining written evidence is required for tiebreak")
        if existing_market_rows is not None:
            pair = _extract_distinct_rater_pair(existing_market_rows)
            if pair is None:
                raise ValueError("Tiebreak requires both primary and second raters to finish first")
            if not fact_disagreements(pair[0], pair[1], market_title=market_title):
                raise ValueError("Tiebreak only applies when primary and second disagree on a fact field")
    else:
        for name, val in (("stakes", stakes), ("breadth", breadth)):
            if not isinstance(val, int) or isinstance(val, bool) or val < 1 or val > 5:
                raise ValueError(f"{name} must be an integer from 1 to 5")

    return {
        "dataset_split": split,
        "market_id": market_id,
        "rater": rater,
        "role": role,
        "subjects_answer": subjects,
        "event_date_answer": event_date,
        "no_single_day": no_single_day if event_date is None else False,
        "geography_answer": geography,
        "structure_answer": structure,
        "claim_frame": claim_frame,
        "stakes": None if role == "tiebreak" else int(stakes),
        "breadth": None if role == "tiebreak" else int(breadth),
        "evidence_note": evidence_note,
    }


def _subject_tokens(name: str) -> tuple[str, ...]:
    cleaned = re.sub(r"['’]", "", name.strip().lower())
    cleaned = re.sub(r"[^\w]+", " ", cleaned).replace("_", " ")
    return tuple(tok for tok in cleaned.split() if tok)


def _contains_token_subsequence(seq: tuple[str, ...], sub: tuple[str, ...]) -> bool:
    if not sub or len(sub) > len(seq):
        return False
    return any(seq[idx : idx + len(sub)] == sub for idx in range(len(seq) - len(sub) + 1))


def _subjects_match(name_a: str, name_b: str) -> bool:
    """Exact same whole-word containment rule used by cu_eval_scorecard."""
    ta = _subject_tokens(name_a)
    tb = _subject_tokens(name_b)
    if not ta or not tb:
        return False
    return _contains_token_subsequence(ta, tb) or _contains_token_subsequence(tb, ta)


def _cleaned_claim_for_compare(
    frame: Any,
    *,
    market_title: str | None = None,
) -> dict[str, str | None] | None:
    if not isinstance(frame, dict):
        return None
    norm = normalize_claim_frame(frame, title=market_title)
    if not norm:
        return None
    return {slot: norm.get(slot) for slot in CLAIM_SLOTS}


def _canonical_fact_value(
    row: dict[str, Any],
    field: str,
    *,
    market_title: str | None = None,
) -> Any:
    if field == "subjects":
        subj = row.get("subjects_answer") or {}
        mode = str(subj.get("selection_kind") or "").strip().lower()
        if mode in {"none_of_these", "not_sure"}:
            return (mode, ())
        names = tuple(sorted(_subject_tokens(str(x)) for x in (subj.get("selected") or []) if str(x).strip()))
        return ("named", names)
    if field == "event_date":
        if row.get("no_single_day"):
            return ("no_single_day", None)
        val = row.get("event_date_answer")
        return ("date", str(val).strip() if val else None)
    if field == "geography":
        val = row.get("geography_answer")
        if not val:
            return None
        try:
            norm = normalize_geography_answer(val)
            return norm.lower() if norm else None
        except ValueError:
            return str(val).strip().lower()
    if field == "structure":
        val = row.get("structure_answer")
        return str(val).strip().lower() if val else None
    if field == "claim_frame":
        cleaned = _cleaned_claim_for_compare(row.get("claim_frame"), market_title=market_title) or {}
        pairs = []
        for slot in CLAIM_SLOTS:
            v = cleaned.get(slot)
            if v is None:
                pairs.append((slot, None))
            else:
                low = str(v).strip().lower()
                if slot == "value":
                    low = _THOUSANDS_COMMA_RE.sub("", low)
                pairs.append((slot, low))
        return tuple(pairs)
    raise ValueError(f"Unknown fact field: {field!r}")


def _fact_fields_agree(
    row_a: dict[str, Any],
    row_b: dict[str, Any],
    field: str,
    *,
    market_title: str | None = None,
) -> bool:
    if field == "subjects":
        subj_a = row_a.get("subjects_answer") or {}
        subj_b = row_b.get("subjects_answer") or {}
        mode_a = str(subj_a.get("selection_kind") or "").strip().lower()
        mode_b = str(subj_b.get("selection_kind") or "").strip().lower()
        if mode_a in {"none_of_these", "not_sure"} or mode_b in {"none_of_these", "not_sure"}:
            return mode_a == mode_b
        names_a = [str(x).strip() for x in (subj_a.get("selected") or []) if str(x).strip()]
        names_b = [str(x).strip() for x in (subj_b.get("selected") or []) if str(x).strip()]
        if not names_a or not names_b:
            return names_a == names_b
        return all(any(_subjects_match(na, nb) for nb in names_b) for na in names_a) and all(
            any(_subjects_match(na, nb) for na in names_a) for nb in names_b
        )
    return _canonical_fact_value(row_a, field, market_title=market_title) == _canonical_fact_value(
        row_b, field, market_title=market_title
    )


def fact_disagreements(
    row_a: dict[str, Any],
    row_b: dict[str, Any],
    *,
    market_title: str | None = None,
) -> list[str]:
    """Return list of fact fields where two submissions differ."""
    return [
        field
        for field in FACT_FIELDS
        if not _fact_fields_agree(row_a, row_b, field, market_title=market_title)
    ]


def _extract_distinct_rater_pair(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Pick the (primary, second) pair for one market when two distinct raters finished."""
    primary = [r for r in rows if r.get("role") == "primary"]
    second = [r for r in rows if r.get("role") == "second"]
    if primary and second:
        for a in primary:
            for b in second:
                if str(a.get("rater") or "").strip().lower() != str(b.get("rater") or "").strip().lower():
                    return (a, b)
    non_tb = [r for r in rows if r.get("role") in {"primary", "second"}]
    by_rater: dict[str, dict[str, Any]] = {}
    for r in non_tb:
        key = str(r.get("rater") or "").strip().lower()
        if key and key not in by_rater:
            by_rater[key] = r
    if len(by_rater) >= 2:
        vals = list(by_rater.values())
        return (vals[0], vals[1])
    return None


def _strip_taste(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rater": row.get("rater"),
        "role": row.get("role"),
        "subjects_answer": row.get("subjects_answer"),
        "event_date_answer": row.get("event_date_answer"),
        "no_single_day": bool(row.get("no_single_day")),
        "geography_answer": row.get("geography_answer"),
        "structure_answer": row.get("structure_answer"),
        "claim_frame": row.get("claim_frame"),
        "evidence_note": row.get("evidence_note"),
    }


def visible_labels_for_rater(
    market_rows: list[dict[str, Any]],
    *,
    role: str,
    rater: str,
) -> dict[str, Any]:
    """Enforce blind visibility on queue items.

    - Primary / second labelers only ever see their OWN submission (if any) plus a
      boolean indicating whether both raters have finished this market. Another rater's
      answers are NEVER returned while labeling.
    - Tiebreak raters see both primary and second FACT answers (never stakes/breadth)
      only when two distinct raters finished AND disagree on >= 1 fact field.
    """
    norm_rater = " ".join(rater.split()).strip().lower()
    own_row = next(
        (
            r
            for r in market_rows
            if str(r.get("rater") or "").strip().lower() == norm_rater and r.get("role") == role
        ),
        None,
    )
    pair = _extract_distinct_rater_pair(market_rows)
    if role in {"primary", "second"}:
        return {
            "own_label": own_row,
            "pair_complete": pair is not None,
            "peer_labels": [],
            "disagreeing_fact_fields": [],
        }

    if pair is None:
        return {
            "own_label": own_row,
            "pair_complete": False,
            "peer_labels": [],
            "disagreeing_fact_fields": [],
        }

    diffs = fact_disagreements(pair[0], pair[1])
    if not diffs:
        return {
            "own_label": own_row,
            "pair_complete": True,
            "peer_labels": [],
            "disagreeing_fact_fields": [],
        }

    return {
        "own_label": own_row,
        "pair_complete": True,
        "peer_labels": [_strip_taste(pair[0]), _strip_taste(pair[1])],
        "disagreeing_fact_fields": diffs,
    }


def _summarize_field_for_example(row: dict[str, Any], field: str, *, market_title: str | None = None) -> Any:
    if field == "subjects":
        return row.get("subjects_answer")
    if field == "event_date":
        return "no_single_day" if row.get("no_single_day") else row.get("event_date_answer")
    if field == "geography":
        return row.get("geography_answer")
    if field == "structure":
        return row.get("structure_answer")
    if field == "claim_frame":
        return _cleaned_claim_for_compare(row.get("claim_frame"), market_title=market_title)
    return row.get(field)


def compute_cu_fact_agreement(
    rows: list[dict[str, Any]],
    *,
    split: str,
    markets_by_id: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute per-field dual-rater agreement: exact/normalized on facts, within-1 on taste."""
    by_market: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("dataset_split") != split:
            continue
        by_market.setdefault(int(row["market_id"]), []).append(row)

    paired_markets = 0
    needs_tiebreak = 0
    resolved_tiebreaks = 0
    counts: dict[str, dict[str, int]] = {
        f: {"agreed": 0, "total": 0}
        for f in (*FACT_FIELDS, *TASTE_FIELDS)
    }
    disagreement_examples: dict[str, list[dict[str, Any]]] = {
        f: [] for f in (*FACT_FIELDS, *TASTE_FIELDS)
    }

    for market_id, mrows in sorted(by_market.items()):
        pair = _extract_distinct_rater_pair(mrows)
        if pair is None:
            continue
        paired_markets += 1
        a, b = pair
        meta = (markets_by_id or {}).get(market_id) or {}
        title = meta.get("title") or meta.get("name")
        has_fact_diff = False
        for field in FACT_FIELDS:
            counts[field]["total"] += 1
            if _fact_fields_agree(a, b, field, market_title=title):
                counts[field]["agreed"] += 1
            else:
                has_fact_diff = True
                if len(disagreement_examples[field]) < 5:
                    disagreement_examples[field].append(
                        {
                            "market_id": market_id,
                            "primary": _summarize_field_for_example(a, field, market_title=title),
                            "second": _summarize_field_for_example(b, field, market_title=title),
                        }
                    )

        for taste_field in TASTE_FIELDS:
            va = a.get(taste_field)
            vb = b.get(taste_field)
            if isinstance(va, int) and isinstance(vb, int):
                counts[taste_field]["total"] += 1
                if abs(va - vb) <= 1:
                    counts[taste_field]["agreed"] += 1
                elif len(disagreement_examples[taste_field]) < 5:
                    disagreement_examples[taste_field].append(
                        {
                            "market_id": market_id,
                            "primary": va,
                            "second": vb,
                        }
                    )

        if has_fact_diff:
            tb = next((r for r in mrows if r.get("role") == "tiebreak"), None)
            if tb is not None:
                resolved_tiebreaks += 1
            else:
                needs_tiebreak += 1

    field_summary: list[dict[str, Any]] = []
    below_80_fields: list[str] = []
    for field in (*FACT_FIELDS, *TASTE_FIELDS):
        c = counts[field]
        total = c["total"]
        rate = round(c["agreed"] / total, 4) if total else None
        below_80 = rate is not None and rate < 0.80
        if below_80:
            below_80_fields.append(field)
        field_summary.append(
            {
                "field": field,
                "metric": "within_1" if field in TASTE_FIELDS else "exact",
                "agreed": c["agreed"],
                "total": total,
                "agreement_rate": rate,
                "below_80_pct": below_80,
                "tiebreak_allowed": field not in TASTE_FIELDS,
            }
        )

    return {
        "split": split,
        "paired_markets": paired_markets,
        "needs_tiebreak": needs_tiebreak,
        "resolved_tiebreaks": resolved_tiebreaks,
        "below_80_fields": below_80_fields,
        "disagreement_examples": {k: v for k, v in disagreement_examples.items() if v},
        "fields": field_summary,
    }


_FIELD_TO_SCORECARD_KEY: dict[str, str] = {
    "subjects": "entities",
    "event_date": "event_date",
    "geography": "geography",
    "structure": "junk_flags",
    "claim_frame": "frame",
    "stakes": "stakes",
    "breadth": "breadth",
}


def _row_to_scorecard_answers(
    row: dict[str, Any],
    *,
    taste_pair: tuple[dict[str, Any], dict[str, Any]] | None = None,
    taste_single: dict[str, Any] | None = None,
    withheld_fields: set[str] | frozenset[str] = frozenset(),
    market_title: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Convert a DB label row into scorecard answers plus `unlisted_measure` flag."""
    subj = row.get("subjects_answer") or {}
    mode = subj.get("selection_kind")
    selected = subj.get("selected") or []

    structure = row.get("structure_answer")
    junk_flags = [structure] if structure in {"ladder", "dated_bucket"} else []

    raw_claim = row.get("claim_frame")
    claim = _cleaned_claim_for_compare(raw_claim, market_title=market_title) or {}
    unlisted_measure = claim.get("measure") == NONE_OF_THESE

    answers: dict[str, Any] = {
        "geography": row.get("geography_answer"),
        "event_date": None if row.get("no_single_day") else row.get("event_date_answer"),
        "junk_flags": junk_flags,
    }
    if not unlisted_measure:
        frame_candidate = {
            "measure": claim.get("measure"),
            "comparator": None if claim.get("comparator") == NONE_OF_THESE else claim.get("comparator"),
            "value": claim.get("value"),
            "unit": claim.get("unit"),
            "horizon_kind": None if claim.get("horizon_kind") == NONE_OF_THESE else claim.get("horizon_kind"),
            "window_date": claim.get("window_date"),
        }
        frame: dict[str, Any] | None = (
            frame_candidate if any(v is not None for v in frame_candidate.values()) else None
        )
        answers["frame"] = frame
    # When measure == "none_of_these", leave "frame" out of answers so it is excluded from
    # the frame score and counted separately in `unlisted_measure_count`.

    if mode in {"candidate", "custom"}:
        answers["entities"] = list(selected)
    elif mode == "none_of_these":
        answers["entities"] = []
    # When selection_kind == "not_sure", omit "entities" so it is not scored as a false mismatch.

    for taste_field in TASTE_FIELDS:
        if taste_field in withheld_fields:
            continue
        if taste_pair is not None:
            va = taste_pair[0].get(taste_field)
            vb = taste_pair[1].get(taste_field)
            vals = sorted({v for v in (va, vb) if isinstance(v, int) and not isinstance(v, bool)})
            if vals:
                answers[taste_field] = vals[0] if len(vals) == 1 else vals
        elif taste_single is not None:
            val = taste_single.get(taste_field)
            if isinstance(val, int) and not isinstance(val, bool):
                answers[taste_field] = val

    for withheld_field in withheld_fields:
        scorecard_key = _FIELD_TO_SCORECARD_KEY.get(withheld_field)
        if scorecard_key:
            answers.pop(scorecard_key, None)

    return answers, unlisted_measure


def build_answer_key_bundle(
    markets_by_id: dict[int, dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    split: str,
) -> dict[str, Any]:
    """Build answer-key rows alongside agreement, withheld (<80%) fields, and unlisted counts."""
    agreement = compute_cu_fact_agreement(rows, split=split, markets_by_id=markets_by_id)
    withheld_fields = list(agreement["below_80_fields"])
    withheld_taste_fields = [f for f in TASTE_FIELDS if f in withheld_fields]
    withheld_set = set(withheld_fields)
    withheld_examples = {
        f: agreement["disagreement_examples"].get(f, [])
        for f in withheld_fields
    }

    by_market: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("dataset_split") != split:
            continue
        by_market.setdefault(int(row["market_id"]), []).append(row)

    exported: list[dict[str, Any]] = []
    unlisted_measure_count = 0
    for mid, mrows in sorted(by_market.items()):
        tiebreak = next((r for r in mrows if r.get("role") == "tiebreak"), None)
        pair = _extract_distinct_rater_pair(mrows)
        single = next((r for r in mrows if r.get("role") == "primary"), None) or mrows[0]
        source_row = tiebreak or (pair[0] if pair else single)

        meta = markets_by_id.get(mid) or {}
        title = meta.get("title") or meta.get("name")
        answers, unlisted_measure = _row_to_scorecard_answers(
            source_row,
            taste_pair=pair,
            taste_single=single if pair is None and tiebreak is None else None,
            withheld_fields=withheld_set,
            market_title=title,
        )
        # If pair differed on facts and no tiebreak yet, drop un-broken fields so scorecard
        # only scores resolved facts.
        unresolved = []
        if pair and tiebreak is None:
            unresolved = fact_disagreements(pair[0], pair[1], market_title=title)
            for uf in unresolved:
                answers.pop(_FIELD_TO_SCORECARD_KEY[uf], None)

        if unlisted_measure and "claim_frame" not in unresolved:
            unlisted_measure_count += 1

        exported.append(
            {
                "market_id": mid,
                "dataset_split": split,
                "resolution_source": (
                    "tiebreak"
                    if tiebreak
                    else ("dual_agreed" if pair and not unresolved else "partial_or_single")
                ),
                "unresolved_fact_fields": unresolved,
                "unlisted_measure": bool(unlisted_measure and "claim_frame" not in unresolved),
                "market_meta": {
                    "market_id": mid,
                    "title": title,
                    "source": meta.get("source"),
                    "category": meta.get("llm_sport_category") or meta.get("category"),
                    "outcome_names": meta.get("outcome_names") or [],
                    "outcome_relation": meta.get("outcome_relation"),
                    "draw_bucket": meta.get("draw_bucket"),
                    "event_id": meta.get("event_id"),
                    "linked_game_id": meta.get("linked_game_id"),
                    "linked_start": meta.get("linked_start"),
                    "start_source": meta.get("start_source"),
                    "linked_league": meta.get("linked_league"),
                    "home_team_league": meta.get("home_team_league"),
                    "away_team_league": meta.get("away_team_league"),
                },
                "answers": answers,
            }
        )
    return {
        "rows": exported,
        "agreement": agreement,
        "withheld_fields": withheld_fields,
        "withheld_taste_fields": withheld_taste_fields,
        "withheld_examples": withheld_examples,
        "unlisted_measure_count": unlisted_measure_count,
    }


def build_answer_key_rows(
    markets_by_id: dict[int, dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    split: str,
) -> list[dict[str, Any]]:
    """Build scorecard-compatible answer rows from primary/second/tiebreak labels."""
    return build_answer_key_bundle(markets_by_id, rows, split=split)["rows"]
