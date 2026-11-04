"""Reusable ``same_deadline_board`` producer kind and the ``by-november-30`` and ``by-december-31`` definitions (``docs/discover/grouping-types-2026-11.md`` §1.6).

PILLAR: DISCOVER / TRUTH · SHIP: the cross-topic grouping type "Same deadline,
different worlds" — unrelated binary markets from at least three categories
whose stated deadline is the same calendar day, ranked highest probability
first, with "Will … by <date>?" dropped from each market's own words (ruling
145 item 3). The card carries up to five rows and a count line ("Showing 5 of
6") without claiming a blend or naming a venue (ruling 141); the container page
carries all six members with single-venue attribution.
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
from app.utils.tonights_games import _parse_dt


def _rc() -> Any:
    return importlib.import_module("app.utils.roundup_containers")


__all__ = [
    "BY_DECEMBER_31_DEFINITION",
    "BY_DECEMBER_31_DEFINITION_PATH",
    "BY_DECEMBER_31_ID",
    "BY_DECEMBER_31_PRODUCER",
    "BY_DECEMBER_31_SLUG",
    "BY_NOVEMBER_30_DEFINITION",
    "BY_NOVEMBER_30_DEFINITION_PATH",
    "BY_NOVEMBER_30_ID",
    "BY_NOVEMBER_30_PRODUCER",
    "BY_NOVEMBER_30_SLUG",
    "EXCLUDED_CLASSES",
    "PRODUCER_KIND_SAME_DEADLINE_BOARD",
    "build_same_deadline_board_producer",
    "by_december_31",
    "by_december_31_enabled",
    "by_november_30",
    "by_november_30_enabled",
    "load_same_deadline_board_definition",
    "produce_same_deadline_board",
    "same_deadline_board_enabled",
    "select_same_deadline_board",
    "strip_deadline_framing",
]

PRODUCER_KIND_SAME_DEADLINE_BOARD = "same_deadline_board"

BY_NOVEMBER_30_SLUG = "by-november-30"
BY_NOVEMBER_30_ID = "roundup:by-november-30"
BY_NOVEMBER_30_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{BY_NOVEMBER_30_SLUG}.json"
)

BY_DECEMBER_31_SLUG = "by-december-31"
BY_DECEMBER_31_ID = "roundup:by-december-31"
BY_DECEMBER_31_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{BY_DECEMBER_31_SLUG}.json"
)

EXCLUDED_CLASSES: tuple[str, ...] = (
    "mention",
    "statement",
    "daily",
    "financial",
    "combination",
    "path",
    "foreign_election",
    "person_harm",
)

_ET_ZONE = ZoneInfo("America/New_York")

_MONTH_NAMES = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# Forbidden alternative deadline prepositions inside the stripped stem.
_OTHER_DEADLINE_PREPOSITION_RE = re.compile(
    r"\b(?:on\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}"
    r"|in\s+20\d{2}\b|before\s+20\d{2}\b|prior\s+to\s+20\d{2}\b)",
    re.IGNORECASE,
)

# Excluded class patterns (§1.6 & §4).
_MENTION_RE = re.compile(
    r"\b(?:say|says|said|mention|mentions|mentioned|tweet|tweets|tweeted|truth\s+social|what\s+will\s+.+\s+say|words?\s+will)\b",
    re.IGNORECASE,
)
_STATEMENT_RE = re.compile(
    r"\b(?:press\s+conference|speech|address|interview|debate|briefing|hearing|remarks|publicly\s+state|official\s+statement|public\s+statement)\b",
    re.IGNORECASE,
)
_DAILY_RE = re.compile(
    r"\b(?:15-minute|15\s+minute|intraday|hourly|daily\s+close|close\s+above|close\s+below|up\s+or\s+down\s+today|end\s+the\s+day\s+above)\b",
    re.IGNORECASE,
)
_FINANCIAL_RE = re.compile(
    r"\b(?:bitcoin|btc|ethereum|eth|solana|dogecoin|xrp|crypto|s&p\s*500|nasdaq|dow\s+jones|russell\s+2000"
    r"|gold\s+price|silver\s+price|crude\s+oil\s+price|treasury\s+yield|stock\s+price|share\s+price"
    r"|trade\s+above\s+\$|close\s+above\s+\$|dip\s+to\s+\$|reach\s+\$\d)\b",
    re.IGNORECASE,
)
_COMBINATION_RE = re.compile(
    r"(?:\bboth\b.+\band\b|\bparlay\b|\bcombo\b|\ball\s+(?:two|three|four)\s+of\b)",
    re.IGNORECASE,
)
_PATH_RE = re.compile(
    r"(?:^if\s+.+\bthen\b|\bconditional\s+on\b|\bgiven\s+that\b|\bassuming\b|\bfirst\s+.+\bthen\b)",
    re.IGNORECASE,
)
_FOREIGN_ELECTION_RE = re.compile(
    r"\b(?:uk|british|french|france|german|germany|canadian|canada|brazilian|brazil|mexican|mexico"
    r"|japanese|japan|indian|india|australian|australia|south\s+korean|south\s+korea|polish|poland"
    r"|romanian|romania|argentine|argentina|chilean|chile|colombian|colombia|israeli|israel"
    r"|turkish|turkey|dutch|netherlands|spanish|spain|italian|italy|portuguese|portugal"
    r"|irish|ireland|czech|philippine|philippines|venezuelan|venezuela|bolivian|bolivia)\b"
    r".*\b(?:election|presidential\s+election|parliamentary|parliament|prime\s+minister|chancellor|runoff|general\s+election)\b"
    r"|\b(?:election|parliamentary|prime\s+minister|general\s+election)\b.*\b(?:in\s+(?:uk|britain|france|germany|canada|brazil|mexico|japan|india|australia|poland|romania|israel|turkey|spain|italy|ireland|venezuela))\b",
    re.IGNORECASE,
)
_PERSON_HARM_RE = re.compile(
    r"\b(?:die|dies|dead|death|pass\s+away|passes\s+away|assassinated|assassination|murdered|killed"
    r"|hospitalized|cancer|stroke|heart\s+attack|diagnosed\s+with|arrested|indicted|convicted"
    r"|sentenced\s+to\s+prison|jailed|imprisoned|prison\s+sentence|plead\s+guilty|found\s+guilty|felony)\b",
    re.IGNORECASE,
)

# Known multi-subject template stems (§1.6: "attend a US x Iran diplomatic meeting", "announce his retirement", etc.).
_TEMPLATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "announce_retirement",
        re.compile(r"\bannounce\s+(?:his|her|their|a)\s+retirement\b", re.IGNORECASE),
    ),
    (
        "announce_run",
        re.compile(
            r"\bannounce\s+a\s+(?:presidential\s+|senate\s+|gubernatorial\s+)?run\b",
            re.IGNORECASE,
        ),
    ),
    (
        "out_as_role",
        re.compile(r"\bout\s+as\s+[a-z\s]+\b", re.IGNORECASE),
    ),
    (
        "attend_diplomatic_meeting",
        re.compile(r"\battend\s+a\s+.+\bmeeting\b", re.IGNORECASE),
    ),
    (
        "record_snow",
        re.compile(r"\b(?:record|have|see)\s+snow\b|\bsnow\s+in\s+", re.IGNORECASE),
    ),
    (
        "visit_country",
        re.compile(r"\bvisit\s+[A-Z][a-z]+", re.IGNORECASE),
    ),
)

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "with",
        "from",
        "by",
        "as",
        "or",
        "and",
        "be",
        "is",
        "are",
        "will",
        "new",
        "next",
        "another",
        "any",
        "least",
        "more",
        "than",
        "his",
        "her",
        "their",
        "its",
        "this",
        "that",
        "into",
        "over",
        "under",
        "before",
        "after",
        "worldwide",
        "global",
        "national",
    }
)

_PREDICATE_STOPWORDS = _STOPWORDS | frozenset(
    {
        "released",
        "release",
        "launch",
        "launched",
        "occur",
        "occurs",
        "pass",
        "passes",
        "accept",
        "accepts",
        "create",
        "creates",
        "add",
        "adds",
        "meet",
        "meets",
        "hold",
        "holds",
        "reach",
        "reaches",
        "announce",
        "announces",
        "out",
        "ipo",
        "banned",
        "ban",
    }
)


def same_deadline_board_enabled() -> bool:
    """Global toggle for ``same_deadline_board`` round-ups."""
    return os.getenv("SAME_DEADLINE_BOARD_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def by_november_30_enabled() -> bool:
    """Toggle for the ``by-november-30`` round-up card and container."""
    if not same_deadline_board_enabled():
        return False
    return os.getenv("BY_NOVEMBER_30_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def by_december_31_enabled() -> bool:
    """Toggle for the ``by-december-31`` round-up card and container."""
    if not same_deadline_board_enabled():
        return False
    return os.getenv("BY_DECEMBER_31_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _parse_deadline_date(deadline: str | date) -> date:
    if isinstance(deadline, date) and not isinstance(deadline, datetime):
        return deadline
    raw = str(deadline or "").strip()
    parts = raw.split("-")
    if len(parts) != 3:
        raise ValueError(f"deadline must be YYYY-MM-DD: {deadline!r}")
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


def _default_deadline_phrase(d: date) -> str:
    return f"by {_MONTH_NAMES[d.month]} {d.day}"


def strip_deadline_framing(
    title: str,
    *,
    deadline_phrase: str,
    year: Optional[int] = None,
) -> Optional[str]:
    """Verify ``title`` ends with ``deadline_phrase`` (optionally ``, <year>``) and return the market's own words with the deadline phrase dropped.

    When ``title`` starts with ``"Will"``, preserves ``"Will …?"`` so the row
    remains grammatical without conjugating inside the market's terms (ruling
    145 item 3); titles without ``"Will"`` remain statements with the trailing
    ``"?"`` dropped. Returns ``None`` if the title does not carry the board's
    exact deadline wording (e.g. uses ``"on December 31"``, ``"in 2026"``,
    ``"before 2027"``, or a different date/year).
    """
    cleaned = str(title or "").strip()
    if not cleaned:
        return None
    phrase = str(deadline_phrase or "").strip()
    if not phrase:
        return None

    if year is not None:
        year_part = rf"(?:,\s*{int(year)})?"
    else:
        year_part = r"(?:,\s*\d{4})?"

    pattern = re.compile(
        rf"^(?P<will>will\s+)?(?P<body>.+?)\s+{re.escape(phrase)}{year_part}\s*\??\s*$",
        re.IGNORECASE,
    )
    match = pattern.match(cleaned)
    if match is None:
        return None

    body = match.group("body").strip().rstrip("?").strip()
    if not body or "__" in body:
        return None

    if _OTHER_DEADLINE_PREPOSITION_RE.search(body):
        return None

    had_will = bool(match.group("will"))
    if had_will:
        will_token = match.group("will").strip()
        return f"{will_token} {body}?"

    if re.match(r"^(?:who|which|what|where|when|how\s+many|how\s+much)\b", body, re.IGNORECASE):
        return None

    return body


def _excluded_class_reason(market: Mapping[str, Any], title: str) -> Optional[str]:
    """Return ``excluded_class:<class>`` if ``market`` belongs to an excluded class, else ``None``."""
    explicit = str(
        market.get("excluded_class")
        or (
            market.get("market_metadata", {}).get("excluded_class")
            if isinstance(market.get("market_metadata"), Mapping)
            else ""
        )
        or ""
    ).strip().lower()
    if explicit in EXCLUDED_CLASSES:
        return f"excluded_class:{explicit}"

    mtype = str(market.get("market_type") or "").strip().lower()
    cat = str(market.get("category") or "").strip().lower()
    llm_cat = str(market.get("llm_sport_category") or "").strip().lower()

    if mtype == "statement" or _STATEMENT_RE.search(title):
        return "excluded_class:statement"
    if mtype == "mention" or _MENTION_RE.search(title):
        return "excluded_class:mention"
    if mtype == "daily" or _DAILY_RE.search(title):
        return "excluded_class:daily"
    if (
        mtype in {"financial", "crypto"}
        or cat in {"crypto", "finance", "financial"}
        or llm_cat in {"crypto", "finance", "financial", "stocks", "commodities", "forex"}
        or _FINANCIAL_RE.search(title)
    ):
        return "excluded_class:financial"
    if mtype in {"combination", "combo", "parlay"} or _COMBINATION_RE.search(title):
        return "excluded_class:combination"
    if mtype == "path" or _PATH_RE.search(title):
        return "excluded_class:path"
    if mtype == "foreign_election" or _FOREIGN_ELECTION_RE.search(title):
        return "excluded_class:foreign_election"
    if mtype == "person_harm" or _PERSON_HARM_RE.search(title):
        return "excluded_class:person_harm"

    return None


def _derive_template_key(market: Mapping[str, Any], label: str) -> str:
    """Derive a template key so at most one member from any template is selected."""
    explicit = str(market.get("template_key") or "").strip().lower()
    if explicit:
        return explicit

    for name, pat in _TEMPLATE_PATTERNS:
        if pat.search(label):
            return f"tpl:{name}"

    tokens = [
        t
        for t in re.findall(r"[a-z0-9]+", label.lower())
        if t not in _STOPWORDS and not t.isdigit()
    ]
    if len(tokens) >= 4:
        return f"tail3:{' '.join(tokens[-3:])}"
    return f"label:{' '.join(tokens)}"


def _derive_claim_key(market: Mapping[str, Any], label: str) -> str:
    """Derive a normalized claim key so two markets asking the same claim cannot both appear."""
    explicit = str(market.get("claim_key") or "").strip().lower()
    if explicit:
        return explicit
    tokens = [
        t
        for t in re.findall(r"[a-z0-9]+", label.lower())
        if t not in _STOPWORDS
    ]
    return " ".join(tokens)


def _derive_story_key(market: Mapping[str, Any]) -> Optional[str]:
    """Derive a story/group key when a market belongs to a provider group or story."""
    for field in ("story_key", "group_id"):
        val = str(market.get(field) or "").strip().lower()
        if val:
            return val
    meta = market.get("market_metadata")
    if isinstance(meta, Mapping):
        pm_event = str(meta.get("polymarket_event_id") or "").strip().lower()
        if pm_event:
            return f"polymarket:{pm_event}"
    return None


def _derive_subject_tokens(market: Mapping[str, Any], label: str) -> frozenset[str]:
    """Extract subject entity tokens from ``label`` to refuse overlapping row subjects (decision D)."""
    explicit = market.get("subject_key") or market.get("subjects")
    if isinstance(explicit, str) and explicit.strip():
        return frozenset(
            t.strip().lower() for t in re.split(r"[,;/|\s]+", explicit) if t.strip()
        )
    if isinstance(explicit, (list, tuple, set, frozenset)):
        return frozenset(str(x).strip().lower() for x in explicit if str(x).strip())

    # Extract leading/proper-noun subject tokens before the predicate, plus any capitalized named entities.
    words = [
        w
        for w in re.findall(r"[A-Za-z0-9.+-]+", label)
        if w.lower() != "will"
    ]
    subjects: set[str] = set()
    for idx, w in enumerate(words):
        cleaned = w.strip(".,()+-").lower()
        if len(cleaned) < 2 or cleaned in _PREDICATE_STOPWORDS or cleaned.isdigit():
            continue
        # Proper noun / acronym or leading subject noun phrase (first 3 tokens)
        if idx < 3 or any(ch.isupper() for ch in w):
            subjects.add(cleaned)
    if not subjects:
        for w in words:
            cleaned = w.strip(".,()+-").lower()
            if len(cleaned) >= 3 and cleaned not in _STOPWORDS:
                subjects.add(cleaned)
                break
    return frozenset(subjects)


def _effective_category(market: Mapping[str, Any]) -> str:
    llm_cat = str(market.get("llm_sport_category") or "").strip().lower()
    if llm_cat and llm_cat not in {"other", "general", "unknown", "futures", "game_prop"}:
        return llm_cat
    cat = str(market.get("category") or "").strip().lower()
    if cat and cat not in {"other", "general", "unknown", "futures", "game_prop"}:
        return cat
    sport = str(market.get("sport") or "").strip().lower()
    if sport:
        return sport
    return "uncategorized"


@dataclass(frozen=True)
class _QualifiedDeadlineMarket:
    market_id: int
    yes_outcome_id: int
    source: str
    category: str
    label: str
    probability: float
    no_probability: Optional[float]
    movement: Optional[float]
    observed_at: Optional[str]
    template_key: str
    claim_key: str
    story_key: Optional[str]
    subject_tokens: frozenset[str]
    raw_market: Mapping[str, Any]


def _classify_candidate(
    market: Mapping[str, Any],
    *,
    deadline_date: date,
    deadline_phrase: str,
    band_low: float,
    band_high: float,
    now_dt: datetime,
    withheld_ids: Optional[set[int]] = None,
) -> tuple[Optional[_QualifiedDeadlineMarket], Optional[str]]:
    """Validate one candidate market against §1.6's member and refusal rules."""
    raw_id = market.get("id")
    if not isinstance(raw_id, int) or isinstance(raw_id, bool) or raw_id <= 0:
        return None, "invalid_market_id"
    market_id = int(raw_id)

    status = str(market.get("status") or "").strip().lower()
    if status != "open":
        return None, f"status_{status or 'missing'}"

    if deadline_date < now_dt.astimezone(_ET_ZONE).date():
        return None, "past_deadline"

    title = str(market.get("name") or "").strip()
    if not title:
        return None, "missing_title"

    excluded = _excluded_class_reason(market, title)
    if excluded is not None:
        return None, excluded

    label = strip_deadline_framing(
        title,
        deadline_phrase=deadline_phrase,
        year=deadline_date.year,
    )
    if label is None:
        return None, "deadline_wording_mismatch"

    try:
        _validate_narrative_copy(label)
    except ValueError:
        return None, "forbidden_narrative_token"

    res_dt = _parse_dt(market.get("resolution_date"))
    if res_dt is None:
        return None, "stored_date_missing"
    if res_dt.astimezone(timezone.utc) <= now_dt.astimezone(timezone.utc):
        return None, "past_deadline"

    utc_date = res_dt.astimezone(timezone.utc).date()
    et_date = res_dt.astimezone(_ET_ZONE).date()
    if utc_date != deadline_date and et_date != deadline_date:
        return None, "stored_date_mismatch"

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
    if not math.isfinite(prob):
        return None, "missing_probability"

    if not (band_low - 1e-9 <= prob <= band_high + 1e-9):
        return None, "out_of_band"

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

    mv_raw = (
        yes_outcome.get("movement")
        if "movement" in yes_outcome
        else yes_outcome.get("probability_change_24h")
    )
    movement: Optional[float] = None
    if mv_raw is not None and not isinstance(mv_raw, bool):
        try:
            mv_val = float(mv_raw)
            if math.isfinite(mv_val) and mv_val != 0.0:
                movement = mv_val
        except (TypeError, ValueError):
            movement = None

    market_observed = _iso_utc(
        market.get("prices_updated_at")
        or market.get("price_observed_at")
        or market.get("updated_at")
    )
    obs = (
        _iso_utc(yes_outcome.get("observed_at") or yes_outcome.get("last_updated"))
        or market_observed
    )

    source = str(market.get("source") or "polymarket").strip().lower() or "polymarket"
    category = _effective_category(market)
    if category == "uncategorized":
        return None, "missing_category"

    return (
        _QualifiedDeadlineMarket(
            market_id=market_id,
            yes_outcome_id=yes_oid,
            source=source,
            category=category,
            label=label,
            probability=prob,
            no_probability=no_prob,
            movement=movement,
            observed_at=obs,
            template_key=_derive_template_key(market, label),
            claim_key=_derive_claim_key(market, label),
            story_key=_derive_story_key(market),
            subject_tokens=_derive_subject_tokens(market, label),
            raw_market=market,
        ),
        None,
    )


def _half_up_percent(prob: float) -> int:
    """Round ``prob * 100`` half-up to match ``Math.round(prob * 100)`` on the client."""
    return int(math.floor(prob * 100.0 + 0.5))


def _build_binary_member_card(item: _QualifiedDeadlineMarket) -> dict[str, Any]:
    """Build the container member card for one binary market with single-venue attribution."""
    base = item.raw_market
    yes_pct = _half_up_percent(item.probability)
    no_prob = (
        item.no_probability
        if item.no_probability is not None
        else max(0.0, min(1.0, 1.0 - item.probability))
    )
    no_pct = 100 - yes_pct

    top_outcomes = [
        {
            "id": item.yes_outcome_id,
            "name": "Yes",
            "probability": item.probability,
            "rendered_percent": yes_pct,
            "american_odds": None,
            "rank": 1,
            "movement": None,
            "is_winner": False,
            "resolution_source": None,
        },
        {
            "id": item.yes_outcome_id + 1,
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

    resolution_date = _iso_utc(base.get("resolution_date"))
    updated_at = _iso_utc(base.get("updated_at")) or item.observed_at
    raw_cat = str(base.get("category") or "").strip()
    card_category = (
        item.category
        if not raw_cat or raw_cat.lower() in {"game_prop", "other", "general", "unknown", "futures"}
        else raw_cat
    )
    return {
        "id": item.market_id,
        "name": str(base.get("name") or "").strip(),
        "sport": base.get("sport"),
        "sport_name": base.get("sport_name"),
        "category": card_category,
        "llm_sport_category": base.get("llm_sport_category") or item.category,
        "market_tier": int(base.get("market_tier") or 2),
        "market_type_label": base.get("market_type_label") or "Yes / No",
        "market_type": "yes_no",
        "status": "open",
        "source": item.source,
        "sources": [item.source],
        "source_count": 1,
        "mutually_exclusive": True,
        "resolution_date": resolution_date,
        "top_outcomes": top_outcomes,
        "outcome_count": 2,
        "updated_at": updated_at,
        "prices_updated_at": item.observed_at,
        "price_observed_at": item.observed_at,
    }


def select_same_deadline_board(
    markets: Mapping[int, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    deadline: str | date,
    deadline_phrase: Optional[str] = None,
    min_members: int = 4,
    max_members: int = 6,
    card_rows: int = 5,
    min_categories: int = 3,
    band: Sequence[float] = (0.05, 0.95),
    candidate_specs: Optional[Sequence[str]] = None,
    section_title: str = "",
    footer: str = "Separate markets that settle by the same day.",
    now: Optional[datetime] = None,
    withheld_by_market: Optional[Mapping[int, set[int]]] = None,
) -> Any:
    """Pure selector for ``same_deadline_board`` (§1.6).

    * Filters binary markets whose stated title deadline matches ``deadline_phrase``
      (e.g. ``"by December 31"``; never ``"on"``, ``"in 2026"``, or ``"before 2027"``)
      and whose stored ``resolution_date`` agrees with ``deadline``.
    * Refuses members from excluded classes (``mention``, ``statement``, ``daily``,
      ``financial``, ``combination``, ``path``, ``foreign_election``, ``person_harm``),
      members without a finite ``Yes`` probability or outside ``band`` (``[0.05, 0.95]``),
      or past their deadline.
    * Enforces one member per template (``duplicate_template``), one per story
      (``duplicate_story``), one per claim (``duplicate_claim``), and refuses
      overlapping row subjects (``overlapping_subject``, decision D).
    * Orders selected members highest probability first; refuses the whole board
      (``RoundupRefusal``) if fewer than ``min_members`` (4) or fewer than
      ``min_categories`` (3) qualify.
    * Emits up to ``card_rows`` (5) rows on the Discover card with
      ``count_line = "Showing 5 of 6"`` when 6 members sit in the container.
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

    deadline_date = _parse_deadline_date(deadline)
    phrase = (
        str(deadline_phrase).strip()
        if deadline_phrase is not None and str(deadline_phrase).strip()
        else _default_deadline_phrase(deadline_date)
    )
    _validate_narrative_copy(section_title, footer, phrase)

    effective_now = (
        now.astimezone(timezone.utc)
        if isinstance(now, datetime) and now.tzinfo is not None
        else datetime.now(timezone.utc)
    )
    if deadline_date < effective_now.astimezone(_ET_ZONE).date():
        return RoundupRefusal((("board", "past_deadline"),))

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

    # Order priority candidates first (if configured), then any remaining markets by highest Yes probability.
    priority_ids: list[int] = []
    if candidate_specs:
        for spec in candidate_specs:
            _, cid, _ = parse_market_ref(spec)
            if cid is not None and cid in by_id and cid not in priority_ids:
                priority_ids.append(cid)

    priority_set = set(priority_ids)
    candidate_pool: list[Mapping[str, Any]] = [by_id[cid] for cid in priority_ids]
    remaining = [
        m for m in ordered_inputs if int(m["id"]) not in priority_set
    ]
    candidate_pool.extend(remaining)

    withheld_map = withheld_by_market or {}
    qualified: list[_QualifiedDeadlineMarket] = []
    member_rejections: list[tuple[str, Any, str]] = []

    for m in candidate_pool:
        mid = int(m["id"])
        q, reason = _classify_candidate(
            m,
            deadline_date=deadline_date,
            deadline_phrase=phrase,
            band_low=band_low,
            band_high=band_high,
            now_dt=effective_now,
            withheld_ids=withheld_map.get(mid),
        )
        if q is None:
            member_rejections.append(("member", mid, str(reason)))
            continue
        qualified.append(q)

    # If no priority order was given, sort candidates highest probability first before deduplication
    # so the strongest market in each template/subject wins deterministically.
    if not priority_ids:
        qualified.sort(key=lambda item: (-item.probability, item.market_id))

    selected: list[_QualifiedDeadlineMarket] = []
    seen_templates: set[str] = set()
    seen_claims: set[str] = set()
    seen_stories: set[str] = set()
    seen_subjects: set[str] = set()

    for q in qualified:
        if q.claim_key in seen_claims:
            member_rejections.append(("member", q.market_id, "duplicate_claim"))
            continue
        if q.template_key in seen_templates:
            member_rejections.append(("member", q.market_id, "duplicate_template"))
            continue
        if q.story_key is not None and q.story_key in seen_stories:
            member_rejections.append(("member", q.market_id, "duplicate_story"))
            continue
        overlap = q.subject_tokens & seen_subjects
        if overlap:
            shared = sorted(overlap)[0]
            member_rejections.append(
                ("member", q.market_id, f"overlapping_subject:{shared}")
            )
            continue

        selected.append(q)
        seen_claims.add(q.claim_key)
        seen_templates.add(q.template_key)
        if q.story_key is not None:
            seen_stories.add(q.story_key)
        seen_subjects.update(q.subject_tokens)
        if len(selected) >= int(max_members):
            break

    req_members = max(1, int(min_members))
    if len(selected) < req_members:
        reasons: list[Any] = [
            ("board", f"too_few_members_{len(selected)}_below_{req_members}"),
            *member_rejections,
        ]
        return RoundupRefusal(reasons)

    distinct_categories = {item.category for item in selected}
    req_categories = max(1, int(min_categories))
    if len(distinct_categories) < req_categories:
        reasons = [
            (
                "board",
                f"too_few_categories_{len(distinct_categories)}_below_{req_categories}",
            ),
            *member_rejections,
        ]
        return RoundupRefusal(reasons)

    # Order highest probability first (ruling: rows run highest first).
    selected.sort(key=lambda item: (-item.probability, item.market_id))

    shown_rows = selected[: max(1, int(card_rows))]
    rows = [
        {
            "market_id": item.market_id,
            "label": item.label,
            "probability": item.probability,
            "rendered_percent": _half_up_percent(item.probability),
            "observed_at": item.observed_at,
        }
        for item in shown_rows
    ]

    count_line: Optional[str] = (
        f"Showing {len(rows)} of {len(selected)}"
        if len(rows) < len(selected)
        else None
    )

    members: list[dict[str, Any]] = []
    for item in selected:
        card = _build_binary_member_card(item)
        members.append(
            {
                "type": MEMBER_MARKET,
                "id": item.market_id,
                "destination": market_destination(item.market_id),
                "card": card,
                "event_id": None,
            }
        )

    sec_title = (
        str(section_title).strip()
        or f"Markets settling {phrase}"
    )
    sections = [
        {
            "class": "title",
            "title": sec_title,
            "layout": "field",
            "count": len(members),
            "members": members,
        }
    ]
    revision_ids = [item.market_id for item in selected]

    return RoundupMembers(
        members=members,
        rows=rows,
        footer=footer,
        count_line=count_line,
        sections=sections,
        revision_ids=revision_ids,
    )


def _orm_market_to_dict(m: Any) -> Optional[dict[str, Any]]:
    from app.utils.kalshi_display_names import repair_outcome_name_by_ticker

    if isinstance(m, Mapping):
        raw_id = m.get("id") if "id" in m else m.get("market_id")
        if isinstance(raw_id, int) and not isinstance(raw_id, bool) and raw_id > 0:
            entry = dict(m)
            entry.setdefault("id", int(raw_id))
            return entry
        return None

    mid_val = getattr(m, "id", None)
    if not isinstance(mid_val, int) or isinstance(mid_val, bool) or mid_val <= 0:
        return None

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
    return {
        "id": int(mid_val),
        "name": str(m.name or "").strip(),
        "source": m.source,
        "external_id": m.external_id,
        "status": m.status,
        "mutually_exclusive": getattr(m, "mutually_exclusive", True),
        "market_tier": getattr(m, "market_tier", 2),
        "market_type": getattr(m, "market_type", "yes_no"),
        "group_id": getattr(m, "group_id", None),
        "market_metadata": getattr(m, "market_metadata", None),
        "sport": getattr(sport_obj, "key", None),
        "sport_name": getattr(sport_obj, "name", None),
        "category": getattr(m, "category", None),
        "llm_sport_category": getattr(m, "llm_sport_category", None),
        "resolution_date": getattr(m, "resolution_date", None),
        "updated_at": getattr(m, "updated_at", None),
        "prices_updated_at": getattr(m, "prices_updated_at", None),
        "outcomes": outcomes_list,
    }


async def _load_markets_from_db(
    db: Any,
    candidate_ids: Sequence[int],
    deadline_phrase: str,
    *,
    deadline_date: Optional[date] = None,
) -> tuple[dict[int, dict[str, Any]], dict[int, set[int]]]:
    """Load the open deadline pool (``resolution_date`` within ``deadline_date``, capped at 300 newest-priced first) plus priority ``candidate_ids``."""
    if isinstance(db, (list, tuple)):
        mapped_seq: dict[int, dict[str, Any]] = {}
        for item in db:
            conv = _orm_market_to_dict(item)
            if conv is not None:
                mapped_seq[int(conv["id"])] = conv
        return mapped_seq, {}

    if not hasattr(db, "execute") or not callable(db.execute):
        return {}, {}

    from sqlalchemy import or_, select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import joinedload

    from app.models import FuturesMarket
    from app.routes.futures import withheld_price_outcome_ids_for_markets

    clean_ids = [
        int(mid)
        for mid in candidate_ids
        if isinstance(mid, int) and not isinstance(mid, bool) and mid > 0
    ]

    target_ids: list[int] = list(clean_ids)
    seen_ids: set[int] = set(clean_ids)
    preloaded_rows: list[Any] = []

    if deadline_date is not None:
        utc_start = datetime.combine(deadline_date, dtime.min, tzinfo=timezone.utc)
        et_end = datetime.combine(
            deadline_date, dtime.max, tzinfo=_ET_ZONE
        ).astimezone(timezone.utc)
        res_pool = await db.execute(
            select(FuturesMarket.id, FuturesMarket.name)
            .where(
                FuturesMarket.status == "open",
                FuturesMarket.event_id.is_(None),
                FuturesMarket.resolution_date.is_not(None),
                FuturesMarket.resolution_date >= utc_start,
                FuturesMarket.resolution_date <= et_end,
                or_(
                    FuturesMarket.market_type.is_(None),
                    FuturesMarket.market_type.in_(
                        ("yes_no", "binary", "container_member", "unshaped")
                    ),
                ),
            )
            .order_by(
                FuturesMarket.updated_at.desc().nullslast(),
                FuturesMarket.id.desc(),
            )
            .limit(300)
        )
        pool_items: list[Any] = []
        if hasattr(res_pool, "all") and callable(res_pool.all):
            pool_items = list(res_pool.all())
        elif hasattr(res_pool, "scalars") and callable(res_pool.scalars):
            pool_items = list(res_pool.scalars().all())

        for item in pool_items:
            if hasattr(item, "outcomes") or isinstance(item, Mapping):
                preloaded_rows.append(item)
                continue
            try:
                mid = int(item[0])
                mname = str(item[1] or "")
            except (IndexError, TypeError, ValueError):
                continue
            if mid in seen_ids or mid <= 0:
                continue
            if (
                strip_deadline_framing(
                    mname,
                    deadline_phrase=deadline_phrase,
                    year=deadline_date.year,
                )
                is not None
            ):
                seen_ids.add(mid)
                target_ids.append(mid)

    hydrate_ids = target_ids[:40]
    orm_rows: list[Any] = list(preloaded_rows)
    if hydrate_ids:
        res = await db.execute(
            select(FuturesMarket)
            .options(
                joinedload(FuturesMarket.sport),
                joinedload(FuturesMarket.outcomes),
            )
            .where(FuturesMarket.id.in_(hydrate_ids))
        )
        if hasattr(res, "scalars") and callable(res.scalars):
            scalars_obj = res.scalars()
            if hasattr(scalars_obj, "unique") and callable(scalars_obj.unique):
                scalars_obj = scalars_obj.unique()
            orm_rows.extend(list(scalars_obj.all()))

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


async def produce_same_deadline_board(
    db: Any,
    *,
    definition: Mapping[str, Any],
    load_markets: Optional[
        Callable[
            [Any, Sequence[int], str],
            Awaitable[tuple[Mapping[int, Mapping[str, Any]], Mapping[int, set[int]]]]
            | tuple[Mapping[int, Mapping[str, Any]], Mapping[int, set[int]]],
        ]
    ] = None,
    now: Optional[datetime] = None,
) -> Any:
    """Evaluate a stored ``same_deadline_board`` container definition against ``db``."""
    rule = definition.get("rule")
    if not isinstance(rule, Mapping):
        raise ValueError(f"Definition {definition.get('slug')!r} is missing 'rule'")

    deadline = str(rule.get("deadline") or "").strip()
    if not deadline:
        raise ValueError(
            f"Definition {definition.get('slug')!r} is missing 'rule.deadline'"
        )
    deadline_date = _parse_deadline_date(deadline)
    deadline_phrase = (
        str(rule.get("deadline_phrase") or "").strip()
        or _default_deadline_phrase(deadline_date)
    )
    min_members = int(rule.get("min_members", 4) or 4)
    max_members = int(rule.get("max_members", 6) or 6)
    card_rows = int(rule.get("card_rows", 5) or 5)
    min_categories = int(rule.get("min_categories", 3) or 3)
    band = rule.get("band") or (0.05, 0.95)
    candidate_specs = [str(c) for c in (rule.get("candidates") or ()) if str(c).strip()]
    section_title = str(definition.get("section_title") or "")
    footer = str(
        definition.get("footer") or "Separate markets that settle by the same day."
    )

    candidate_ids: list[int] = []
    for spec in candidate_specs:
        _, cid, _ = parse_market_ref(spec)
        if cid is not None:
            candidate_ids.append(cid)

    if load_markets is not None:
        loaded = load_markets(db, candidate_ids, deadline_phrase)
    else:
        loaded = _load_markets_from_db(
            db,
            candidate_ids,
            deadline_phrase,
            deadline_date=deadline_date,
        )
    if inspect.isawaitable(loaded):
        loaded = await loaded
    markets_map, withheld_map = loaded

    return select_same_deadline_board(
        markets_map,
        deadline=deadline_date,
        deadline_phrase=deadline_phrase,
        min_members=min_members,
        max_members=max_members,
        card_rows=card_rows,
        min_categories=min_categories,
        band=band,
        candidate_specs=candidate_specs,
        section_title=section_title,
        footer=footer,
        now=now,
        withheld_by_market=withheld_map,
    )


def load_same_deadline_board_definition(path: Path | str) -> dict[str, Any]:
    """Load and validate a stored JSON container definition for ``same_deadline_board``."""
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


def build_same_deadline_board_producer(
    definition: Mapping[str, Any],
    *,
    enabled: Optional[Callable[[], bool]] = None,
    load_markets: Optional[
        Callable[
            [Any, Sequence[int], str],
            Awaitable[tuple[Mapping[int, Mapping[str, Any]], Mapping[int, set[int]]]]
            | tuple[Mapping[int, Mapping[str, Any]], Mapping[int, set[int]]],
        ]
    ] = None,
    now: Optional[datetime] = None,
) -> Any:
    """Build a ``RoundupProducer`` from a stored ``same_deadline_board`` definition."""
    RoundupProducer = _rc().RoundupProducer

    rule = definition.get("rule")
    if (
        not isinstance(rule, Mapping)
        or rule.get("producer") != PRODUCER_KIND_SAME_DEADLINE_BOARD
    ):
        raise ValueError(
            f"Expected rule.producer == {PRODUCER_KIND_SAME_DEADLINE_BOARD!r}, got {rule!r}"
        )

    slug = str(definition["slug"])
    name = str(definition["name"])
    footer = str(definition["footer"])
    section_title = definition["section_title"]
    kicker = str(definition.get("kicker") or "SAME DEADLINE")
    raw_tag = definition.get("tag")
    tag = "" if raw_tag is None else str(raw_tag)
    _validate_narrative_copy(name, footer, section_title, kicker, tag)

    async def _produce(db: Any) -> Any:
        return await produce_same_deadline_board(
            db,
            definition=definition,
            load_markets=load_markets,
            now=now,
        )

    return RoundupProducer(
        slug=slug,
        name=name,
        kind=str(definition.get("kind") or "roundup"),
        category=str(definition["category"]),
        section_title=section_title,
        footer=footer,
        produce=_produce,
        membership=str(definition.get("membership") or "computed-produced"),
        rule=dict(rule),
        tag=tag,
        kicker=kicker,
        story_key=f"roundup:{slug.removeprefix('roundup-')}",
        enabled=enabled,
    )


BY_NOVEMBER_30_DEFINITION: dict[str, Any] = load_same_deadline_board_definition(
    BY_NOVEMBER_30_DEFINITION_PATH
)
BY_NOVEMBER_30_PRODUCER: Any = build_same_deadline_board_producer(
    BY_NOVEMBER_30_DEFINITION,
    enabled=by_november_30_enabled,
)
_rc().register_roundup_producer(BY_NOVEMBER_30_PRODUCER)

BY_DECEMBER_31_DEFINITION: dict[str, Any] = load_same_deadline_board_definition(
    BY_DECEMBER_31_DEFINITION_PATH
)
BY_DECEMBER_31_PRODUCER: Any = build_same_deadline_board_producer(
    BY_DECEMBER_31_DEFINITION,
    enabled=by_december_31_enabled,
)
_rc().register_roundup_producer(BY_DECEMBER_31_PRODUCER)


async def by_november_30(
    db: Any,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Evaluate ``BY_NOVEMBER_30_PRODUCER`` once and return ``(feed_item, container_payload)``."""
    return await _rc().evaluate_roundup_producer(BY_NOVEMBER_30_PRODUCER, db)


async def by_december_31(
    db: Any,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Evaluate ``BY_DECEMBER_31_PRODUCER`` once and return ``(feed_item, container_payload)``."""
    return await _rc().evaluate_roundup_producer(BY_DECEMBER_31_PRODUCER, db)
