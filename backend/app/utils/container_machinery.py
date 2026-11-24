"""Topic-free grouping & container machinery (`#12288`, Direction 223, Decision 224, Ruling 227-A, Direction 228).

PILLAR: DISCOVER · FORMATTING · MATCHING · TRUTH
SHIP: One declarative definition produces BOTH the Discover card and the multi-section
container page, with zero hand-placed market or event IDs, choosing each section's
visual form automatically from the shape of its numbers, ordering numerical-scale
outcomes ascending (Direction 228), building live titles from the set, capping
initial visual runs at 3 with Show-all expansion, and attaching verified subject
imagery or real probability-history charts (never stock photos).

Publication gate: candidate definitions live in ``backend/data/groupings/candidates/``
and ``container_machinery_enabled()`` defaults to ``False`` until turned on by Fable/Alex.
"""

from __future__ import annotations

import copy
import inspect
import json
import logging
import math
import os
import re
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from app.utils.container_presentation import (
    MEMBER_EVENT,
    MEMBER_MARKET,
    event_destination,
    market_destination,
)
from app.utils.draw_priced_winner import printable_away
from app.utils.event_taxonomy import compute_event_tags
from app.utils.graded_card import rendered_card_percents, rendered_duel_percents, rendered_percent
from app.utils.team_short_name import is_college_sport, school_label


def _computed_event_tags(ev: Any, sport_key: str) -> list[str]:
    """Return merged stored + deterministic ``event_tags`` for server-side ranking."""
    stored = getattr(ev, "event_tags", None) or ()
    tags: set[str] = {str(t) for t in stored if t} if isinstance(stored, (list, tuple, set)) else set()
    commence = getattr(ev, "commence_time", None)
    if commence is not None and sport_key:
        raw_ei = getattr(ev, "raw_ei", None)
        tags.update(
            compute_event_tags(
                sport_key=sport_key,
                status=getattr(ev, "status", None) or "scheduled",
                commence_time=commence,
                llm_importance=getattr(ev, "llm_importance", None),
                llm_gender=getattr(ev, "llm_gender", None),
                llm_level=getattr(ev, "llm_level", None),
                llm_league=getattr(ev, "llm_league", None),
                raw_ei=float(raw_ei) if raw_ei else None,
                broadcast_info=getattr(ev, "broadcast_info", None),
            )
        )
    return sorted(tags)

# Ruling 253: A (#12288): "toss-up" means neither side above 55% (45%–55%).
TOSS_UP_MAX_SIDE_PROB = 0.55
TOSS_UP_MIN_SECTION_COUNT = 2

__all__ = [
    "CANDIDATE_2028_PRESIDENTIAL_PATH",
    "CANDIDATE_FED_AND_MACRO_PATH",
    "CANDIDATE_NFL_WEEK_PATH",
    "CANDIDATE_OSCARS_BEST_PICTURE_PATH",
    "MACHINERY_CANDIDATE_PATHS",
    "MACHINERY_FORM_IDS",
    "PRODUCER_KIND_CONTAINER_MACHINERY",
    "SubjectArtResolver",
    "build_container_machinery_producer",
    "choose_section_form",
    "compute_visual_diversity_report",
    "container_machinery_enabled",
    "discover_machinery_candidate_paths",
    "evaluate_machinery_candidates_preview",
    "is_machinery_candidate_slug",
    "load_machinery_definition",
    "numerical_scale_order_indices",
    "parse_numerical_scale_key",
    "produce_container_machinery",
    "register_machinery_slice1_candidates",
    "serve_machinery_candidate_preview",
]

PRODUCER_KIND_CONTAINER_MACHINERY = "container_machinery"

logger = logging.getLogger(__name__)

MACHINERY_FORM_IDS: frozenset[str] = frozenset(
    {
        "paired_stage_bars",
        "coin_flip_matchups",
        "matchup_slate",
        "duel_bar",
        "contender_spotlight",
        "sibling_fields_grid",
        "benchmark_strip",
        "probability_history_chart",
    }
)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_CANDIDATES_DIR = _DATA_DIR / "groupings" / "candidates"
_VERIFIED_ART_PATH = _DATA_DIR / "discover" / "verified_discover_art.json"
_PAIRED_REGISTER_PATH = _DATA_DIR / "groupings" / "paired_metric_register.json"
_SUBJECT_ART_PATH = _DATA_DIR / "groupings" / "machinery_subject_art.json"

CANDIDATE_NFL_WEEK_PATH = _CANDIDATES_DIR / "machinery-nfl-week.json"
CANDIDATE_OSCARS_BEST_PICTURE_PATH = _CANDIDATES_DIR / "machinery-oscars-best-picture.json"
CANDIDATE_2028_PRESIDENTIAL_PATH = _CANDIDATES_DIR / "machinery-2028-presidential.json"
CANDIDATE_FED_AND_MACRO_PATH = _CANDIDATES_DIR / "machinery-fed-and-macro.json"

MACHINERY_CANDIDATE_PATHS: tuple[Path, ...] = (
    CANDIDATE_NFL_WEEK_PATH,
    CANDIDATE_OSCARS_BEST_PICTURE_PATH,
    CANDIDATE_2028_PRESIDENTIAL_PATH,
)

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_PLACEHOLDER_OUTCOME_RE = re.compile(
    r"^(?:other|any\s+other|field|none(?:\s+of\s+the\s+above)?|someone\s+else|tbd)$",
    re.IGNORECASE,
)
_LOWER_PROPER_NAME_RE = re.compile(r"^[A-Z][a-z'’-]+(?:\s+[A-Za-z'’-]+)+$")
_NON_NAME_TAIL_WORDS: frozenset[str] = frozenset(
    {
        "party",
        "maintains",
        "rate",
        "rates",
        "cuts",
        "cut",
        "hikes",
        "hike",
        "holds",
        "hold",
        "wins",
        "win",
        "increase",
        "decrease",
        "change",
        "bps",
        "of",
        "the",
        "in",
        "on",
        "and",
        "to",
        "for",
        "at",
        "by",
        "or",
    }
)
_FORBIDDEN_COPY_QUESTION_RE = re.compile(r"\bquestions?\b", re.IGNORECASE)
_SETTLEMENT_FILLER_RE = re.compile(
    r"\bsettles?\s+from\s+official\b|\bseveral\s+films\s+are\s+nominated\b|\bone\s+party\s+and\s+one\s+candidate\b",
    re.IGNORECASE,
)
_PROP_MARKET_TITLE_RE = re.compile(
    r"\b(?:touchdowns?|passing\s+yards?|rushing\s+yards?|receiving\s+yards?|receptions?|sacks?|interceptions?|completions?|points?\s+leader|rebounds?\s+leader|assists?\s+leader|strikeouts?|home\s+runs?)\b",
    re.IGNORECASE,
)
_OUTCOME_PROP_SUFFIX_RE = re.compile(r"\s*:\s*\d+(?:\.\d+)?\+?\s*$")

# ── Direction 228 (#12885): Numerical-scale detection & ordering ────────────

_UNIT_MULT: dict[str, float] = {
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "mn": 1e6,
    "million": 1e6,
    "b": 1e9,
    "bn": 1e9,
    "billion": 1e9,
    "t": 1e12,
    "trillion": 1e12,
}
_NUM_CORE = r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?"
_MULT_UNIT = (
    r"(?:%|°[fc]?|\s*(?:thousand|million|billion|trillion|bps|pts?|points?|goals?|wins?|"
    r"cuts?|hikes?|days?|weeks?|months?|years?|seats?|[kmbtKMBT]|mn|bn|st|nd|rd|th)\b)?"
)
_TRAILING_PAREN_RE = re.compile(r"\s*\([^()]*\)\s*$")
_DATE_TOKEN_RE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
    re.IGNORECASE,
)
_YEAR_LEAD_RE = re.compile(r"^(?:before|after|by|in|prior\s+to|on\s+or\s+before)\s+\d{4}\b", re.IGNORECASE)
_HOLD_MOVE_RE = re.compile(
    r"^(?:no\s+change|unchanged|hold|steady|(?:fed\s+)?maintains?\s+rates?)$",
    re.IGNORECASE,
)
_SIGNED_PREFIX_MOVE_RE = re.compile(
    rf"^(cut|cuts|decrease|lower|hike|hikes|increase|raise)\s*(?:by\s*)?(>\s*|≥\s*|>=\s*|at\s+least\s+)?({_NUM_CORE})(\+)?\s*(?:bps|basis\s+points?|%|pts?)?$",
    re.IGNORECASE,
)
_SIGNED_SUFFIX_MOVE_RE = re.compile(
    rf"^(>\s*|≥\s*|>=\s*|at\s+least\s+)?({_NUM_CORE})(\+)?\s*(?:bps|basis\s+points?|%|pts?)?\s*(cut|cuts|decrease|hike|hikes|increase)(?:\s+or\s+(?:more|larger|greater))?$",
    re.IGNORECASE,
)
_RANGE_BETWEEN_RE = re.compile(
    rf"^between\s+[$€£]?({_NUM_CORE})({_MULT_UNIT})\s+and\s+[$€£]?({_NUM_CORE})({_MULT_UNIT})$",
    re.IGNORECASE,
)
_RANGE_DASH_RE = re.compile(
    rf"^(?:rank\s+)?[$€£]?({_NUM_CORE})({_MULT_UNIT})\s*(?:to|[–—-])\s*[$€£]?({_NUM_CORE})({_MULT_UNIT})$",
    re.IGNORECASE,
)
_LOWER_PREFIX_RE = re.compile(
    rf"^(?:<\s*|≤\s*|<=\s*|below\s+|under\s+|less\s+than\s+|fewer\s+than\s+|at\s+most\s+|up\s+to\s+|no\s+more\s+than\s+)[$€£]?({_NUM_CORE})({_MULT_UNIT})$",
    re.IGNORECASE,
)
_LOWER_SUFFIX_RE = re.compile(
    rf"^[$€£]?({_NUM_CORE})({_MULT_UNIT})\s+(?:or\s+(?:below|less|lower|under|fewer)|and\s+(?:below|under))$",
    re.IGNORECASE,
)
_UPPER_PREFIX_RE = re.compile(
    rf"^(?:>\s*|≥\s*|>=\s*|above\s+|at\s+least\s+|over\s+|more\s+than\s+|greater\s+than\s+|exceeds?\s+|reaches?\s+|hits?\s+)[$€£]?({_NUM_CORE})({_MULT_UNIT})$",
    re.IGNORECASE,
)
_UPPER_SUFFIX_RE = re.compile(
    rf"^(?P<prefix>(?:category|cat|tier|level|stage|grade|top)\s+)?[$€£]?(?P<num>{_NUM_CORE})(?P<unit>{_MULT_UNIT})(?:\+|\s+or\s+(?:above|more|higher|greater)|\s+and\s+(?:above|more|higher))(?P<tail>\s+[a-z][a-z\s-]*)?$",
    re.IGNORECASE,
)
_EXACT_NUM_RE = re.compile(
    rf"^(?:exactly\s+)?(?P<prefix>(?:category|cat|tier|level|stage|grade)\s+)?[$€£]?(?P<num>{_NUM_CORE})(?P<unit>{_MULT_UNIT})$",
    re.IGNORECASE,
)
_ZERO_COUNT_WORD_RE = re.compile(
    r"^(?:none|zero|no\s+(?:cuts?|hikes?|wins?|goals?|points?|medals?|titles?|changes?|rate\s+(?:cuts?|hikes?)))$",
    re.IGNORECASE,
)


def _unit_mult(raw: Optional[str]) -> float:
    if not raw:
        return 1.0
    clean = raw.replace("%", "").strip().lower()
    return _UNIT_MULT.get(clean, 1.0)


def _parse_float(raw: str) -> float:
    return float(raw.replace(",", ""))


def _scale_skeleton(raw: str) -> str:
    s = _TRAILING_PAREN_RE.sub("", raw).lower()
    s = re.sub(
        r"\b(?:exactly|at\s+least|at\s+most|more\s+than|less\s+than|fewer\s+than|greater\s+than|"
        r"no\s+more\s+than|up\s+to|or\s+(?:above|more|higher|greater|below|less|lower|under|fewer)|"
        r"and\s+(?:above|more|higher|below|under)|above|below|over|under|between|and|to)\b",
        " ",
        s,
    )
    s = re.sub(r"[<>≤≥=+–—-]", " ", s)
    s = re.sub(r"\d[\d,.]*", "#", s)
    s = re.sub(r"\b(cut|hike|win|goal|point|pt|day|week|month|year|seat)s\b", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


_PLAIN_RATE_MOVE_RE = re.compile(
    r"^(quarter|half|three-quarter|full|\d+(?:\.\d+)?)-point(?:\s+(or\s+(?:larger|more|greater)))?\s+(cut|decrease|increase|hike)$",
    re.IGNORECASE,
)

_COUNT_BPS_PAREN_RE = re.compile(
    r"^(\d+)(\+)?\s*\(\s*(\d+(?:\.\d+)?)(\+)?\s*(?:bps|basis\s+points?)\s*\)$",
    re.IGNORECASE,
)

_PLAIN_MAGNITUDE_BPS: dict[str, float] = {
    "quarter": 25.0,
    "half": 50.0,
    "three-quarter": 75.0,
    "full": 100.0,
}


from app.utils.plain_rate_outcome import (
    plain_rate_outcome_label as _plain_rate_outcome_label,
)


def _prose_rate_outcome(label: str, *, capitalize_first: bool = False) -> str:
    """Format a cleaned outcome label naturally inside a sentence (Ruling 244: A)."""
    s = str(label or "").strip()
    if not s:
        return s
    low = s.lower()
    if _PLAIN_RATE_MOVE_RE.match(s):
        phrase = f"a {low}"
    else:
        phrase = _prose_outcome_name(s)
    if capitalize_first and phrase:
        return phrase[0].upper() + phrase[1:]
    return phrase


def parse_numerical_scale_key(raw_label: Optional[str]) -> Optional[dict[str, Any]]:
    """Parse one outcome label into a numerical-scale sort key, or ``None`` if not a numeric scale."""
    full = (raw_label or "").strip()
    if not full:
        return None
    if "," in full and ":" in full:
        return None
    if full.lower() in {"yes", "no"}:
        return None
    if _DATE_TOKEN_RE.search(full) or _YEAR_LEAD_RE.match(full):
        return None
    stripped = _TRAILING_PAREN_RE.sub("", full).strip()
    if not stripped:
        return None

    if _HOLD_MOVE_RE.match(stripped):
        return {"kind": "signed_move", "primary": 0.0, "bound_rank": 0, "secondary": 0.0, "skeleton": "signed_move"}

    m_plain = _PLAIN_RATE_MOVE_RE.match(stripped)
    if m_plain:
        mag_tok = m_plain.group(1).lower()
        val = (
            _PLAIN_MAGNITUDE_BPS[mag_tok]
            if mag_tok in _PLAIN_MAGNITUDE_BPS
            else _parse_float(mag_tok) * 100.0
        )
        is_open = bool(m_plain.group(2))
        direction = -1.0 if m_plain.group(3).lower() in {"cut", "decrease"} else 1.0
        return {
            "kind": "signed_move",
            "primary": direction * val,
            "bound_rank": (-1 if direction < 0 else 1) if is_open else 0,
            "secondary": direction * val,
            "skeleton": "signed_move",
        }

    m = _SIGNED_PREFIX_MOVE_RE.match(stripped)
    if m:
        direction = -1.0 if m.group(1).lower() in {"cut", "cuts", "decrease", "lower"} else 1.0
        is_open = bool(m.group(2) or m.group(4))
        val = _parse_float(m.group(3))
        if not math.isfinite(val):
            return None
        return {
            "kind": "signed_move",
            "primary": direction * val,
            "bound_rank": (-1 if direction < 0 else 1) if is_open else 0,
            "secondary": direction * val,
            "skeleton": "signed_move",
        }

    m = _SIGNED_SUFFIX_MOVE_RE.match(stripped)
    if m:
        direction = -1.0 if m.group(4).lower() in {"cut", "cuts", "decrease"} else 1.0
        is_open = bool(m.group(1) or m.group(3) or re.search(r"\bor\s+(?:more|larger|greater)$", stripped, re.I))
        val = _parse_float(m.group(2))
        if not math.isfinite(val):
            return None
        return {
            "kind": "signed_move",
            "primary": direction * val,
            "bound_rank": (-1 if direction < 0 else 1) if is_open else 0,
            "secondary": direction * val,
            "skeleton": "signed_move",
        }

    for rx in (_RANGE_BETWEEN_RE, _RANGE_DASH_RE):
        m = rx.match(stripped)
        if m:
            u1 = (m.group(2) or "").strip() or (m.group(4) or "").strip()
            u2 = (m.group(4) or "").strip() or u1
            v1 = _parse_float(m.group(1)) * _unit_mult(u1)
            v2 = _parse_float(m.group(3)) * _unit_mult(u2)
            if not (math.isfinite(v1) and math.isfinite(v2)):
                return None
            return {"kind": "numeric", "primary": v1, "bound_rank": 0, "secondary": v2, "skeleton": _scale_skeleton(stripped)}

    for rx in (_LOWER_PREFIX_RE, _LOWER_SUFFIX_RE):
        m = rx.match(stripped)
        if m:
            v = _parse_float(m.group(1)) * _unit_mult(m.group(2))
            if not math.isfinite(v):
                return None
            return {"kind": "numeric", "primary": v, "bound_rank": -1, "secondary": v, "skeleton": _scale_skeleton(stripped)}

    m = _UPPER_PREFIX_RE.match(stripped)
    if m:
        v = _parse_float(m.group(1)) * _unit_mult(m.group(2))
        if not math.isfinite(v):
            return None
        return {"kind": "numeric", "primary": v, "bound_rank": 1, "secondary": v, "skeleton": _scale_skeleton(stripped)}

    m = _UPPER_SUFFIX_RE.match(stripped)
    if m:
        v = _parse_float(m.group("num")) * _unit_mult(m.group("unit"))
        if not math.isfinite(v):
            return None
        return {"kind": "numeric", "primary": v, "bound_rank": 1, "secondary": v, "skeleton": _scale_skeleton(stripped)}

    m = _EXACT_NUM_RE.match(stripped)
    if m:
        v = _parse_float(m.group("num")) * _unit_mult(m.group("unit"))
        if not math.isfinite(v):
            return None
        return {"kind": "numeric", "primary": v, "bound_rank": 0, "secondary": v, "skeleton": _scale_skeleton(stripped)}

    if _ZERO_COUNT_WORD_RE.match(stripped):
        return {"kind": "numeric", "primary": 0.0, "bound_rank": 0, "secondary": 0.0, "skeleton": "zero_word"}

    return None


def numerical_scale_order_indices(rows: Sequence[Mapping[str, Any]]) -> Optional[list[int]]:
    """Return ascending numerical-scale index permutation for ``rows``, or ``None`` if not a scale."""
    if len(rows) < 2:
        return None
    parsed: list[tuple[int, dict[str, Any]]] = []
    for idx, row in enumerate(rows):
        raw = str(row.get("name") or row.get("label") or "")
        key = parse_numerical_scale_key(raw)
        if key is None:
            return None
        parsed.append((idx, key))

    all_signed = all(k["kind"] == "signed_move" for _, k in parsed)
    if not all_signed:
        lower_bounds = sum(1 for _, k in parsed if k["bound_rank"] == -1)
        upper_bounds = sum(1 for _, k in parsed if k["bound_rank"] == 1)
        if lower_bounds >= 2 or upper_bounds >= 2:
            return None

    has_nonzero_signed = all_signed and any(k["primary"] != 0.0 for _, k in parsed)
    if not has_nonzero_signed:
        if any(k["kind"] == "signed_move" for _, k in parsed):
            return None
        skeletons = [k["skeleton"] for _, k in parsed if k["skeleton"] != "zero_word"]
        if not skeletons:
            return None
        counts: dict[str, int] = {}
        shared = False
        for sk in skeletons:
            canon = re.sub(r"#\s+#", "#", sk)
            nxt = counts.get(canon, 0) + 1
            if nxt >= 2:
                shared = True
            counts[canon] = nxt
        if not shared and not (len(skeletons) == 1 and len(parsed) == 2):
            return None

    ordered = sorted(
        parsed,
        key=lambda pair: (pair[1]["primary"], pair[1]["bound_rank"], pair[1]["secondary"], pair[0]),
    )
    return [idx for idx, _ in ordered]


def _proper_case_outcome_label(label: str) -> str:
    """Capitalize miscased proper names (e.g. ``'Anne hathaway'`` -> ``'Anne Hathaway'``)
    without altering numeric brackets, units, or plain sentence outcomes."""
    trimmed = label.strip()
    if not _LOWER_PROPER_NAME_RE.match(trimmed):
        return trimmed
    parts = trimmed.split(" ")
    if any(p.lower() in _NON_NAME_TAIL_WORDS for p in parts[1:]):
        return trimmed
    fixed: list[str] = [parts[0]]
    for tok in parts[1:]:
        if len(tok) >= 2 and tok.islower():
            fixed.append(tok[0].upper() + tok[1:])
        else:
            fixed.append(tok)
    return " ".join(fixed)


def _format_bps_number(val: float) -> str:
    if abs(val - round(val)) < 1e-6:
        return str(int(round(val)))
    return f"{val:g}"


def _clean_outcome_label(label: str) -> str:
    """Canonicalize venue outcome labels into one Bain Luck house style (Slice 5 Note 5)."""
    trimmed = re.sub(r"\s+", " ", label.strip())
    if not trimmed:
        return trimmed
    low = trimmed.lower()
    if low == "democratic party":
        return "Democratic Party"
    if low == "republican party":
        return "Republican Party"

    # Strip redundant leading 'Exactly ' on numerical-scale brackets ('Exactly 4.1%' -> '4.1%').
    if re.match(r"^exactly\s+[-+$€£\d]", trimmed, re.IGNORECASE):
        trimmed = re.sub(r"^exactly\s+", "", trimmed, flags=re.IGNORECASE).strip()

    # Ruling 244: A / #13196 — plain-English Fed/rate-move labels (never 'bps'),
    # shared with series_card_labels.reader_outcome_name via plain_rate_outcome.py.
    if _HOLD_MOVE_RE.match(trimmed):
        return "No change"

    plain_rate = _plain_rate_outcome_label(trimmed, default_count_noun="hike")
    if plain_rate is not None:
        return plain_rate

    return _proper_case_outcome_label(trimmed)


_PALETTE_FALLBACK: tuple[str, ...] = (
    "#059669",
    "#2563EB",
    "#D97706",
    "#7C3AED",
    "#DC2626",
    "#0891B2",
)


def container_machinery_enabled() -> bool:
    """Strictly switched OFF unless explicitly enabled via env flag."""
    return os.environ.get("CONTAINER_MACHINERY_SLICE1_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _half_up_pct(prob: float) -> int:
    clamped = max(0.0, min(1.0, float(prob)))
    pct = int(
        (Decimal(str(clamped)) * Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    if pct <= 0 and clamped > 0:
        return 1
    if pct >= 100 and clamped < 1:
        return 99
    return pct


def _norm_key(text: str | None) -> str:
    if not text:
        return ""
    return _NON_ALNUM_RE.sub(" ", text.lower()).strip()


_DOTTED_INITIALS_RE = re.compile(r"\b(?:[A-Za-z]\.\s*){2,}(?=\s|$)")


def _ascii_fold_key(text: str | None) -> str:
    """NFKD ASCII-folded + dotted-initial key so equivalent spellings
    ('Luka Dončić' / 'Luka Doncic', 'JD Vance' / 'J.D. Vance') share one identity key.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    collapsed = _DOTTED_INITIALS_RE.sub(lambda m: re.sub(r"[\.\s]+", "", m.group(0)), ascii_only)
    return _NON_ALNUM_RE.sub(" ", collapsed.lower()).strip()


def _diacritic_letter_count(text: str) -> int:
    return sum(1 for ch in text if ord(ch) > 127 and ch.isalpha())


def _pick_preferred_subject_spelling(
    variants: Sequence[str],
    *,
    primary_display: Optional[str] = None,
) -> Optional[str]:
    """When variants share the exact same ``_ascii_fold_key``:
    1. Prefer properly accented orthography ('Luka Dončić' over 'Luka Doncic').
    2. Otherwise prefer the registered primary display alias ('JD Vance') or cleaner undotted form
       ('JD Vance' over 'J.D. Vance') so one person never prints two ways in one grouping.
    """
    cleaned = [re.sub(r"\s+", " ", str(v).strip()) for v in variants if str(v).strip()]
    if not cleaned:
        return None
    best_diacritic = max(cleaned, key=lambda s: (_diacritic_letter_count(s), -len(s)))
    if _diacritic_letter_count(best_diacritic) > 0:
        return best_diacritic
    if primary_display:
        prim = re.sub(r"\s+", " ", str(primary_display).strip())
        if prim and any(c.isupper() for c in prim):
            return prim
    titled = [s for s in cleaned if any(c.isupper() for c in s)]
    if len(set(titled)) > 1:
        return min(titled, key=lambda s: (s.count("."), len(s), s))
    return None


def _initials(label: str) -> str:
    clean = str(label or "").strip()
    if not clean:
        return "?"
    from app.utils.discover_image_policy import compute_initials

    subj = clean
    for sep in (": ", " · "):
        if sep in subj:
            subj = subj.rsplit(sep, 1)[-1].strip() or subj
    return compute_initials(subj, ticker_ok=False)


def _fallback_color(label: str) -> str:
    key = _norm_key(label)
    if "democrat" in key:
        return "#2563EB"
    if "republican" in key or key == "gop":
        return "#DC2626"
    h = sum(ord(ch) for ch in key)
    return _PALETTE_FALLBACK[h % len(_PALETTE_FALLBACK)]


_PLACEHOLDER_CREST_SUFFIX = "/default.png"
_TEAM_CLUB_PREFIX_RE = re.compile(r"^(?:fc|cf|sc|ac|afc|sv|fk)\s+", re.IGNORECASE)
_TEAM_CLUB_SUFFIX_RE = re.compile(r"\s+(?:fc|cf|sc|ac|afc)$", re.IGNORECASE)
_TEAM_STATIC_LOGO_KINDS: frozenset[str] = frozenset({"team_logo", "espn_team_logo"})
_PERSON_ART_KINDS: frozenset[str] = frozenset(
    {"person", "headshot", "portrait", "tmdb_headshot", "tmdb_person"}
)
_CAST_AS_SPLIT_RE = re.compile(r"\s+as\s+", re.IGNORECASE)
_PORTRAIT_DETAIL_SUFFIX_RE = re.compile(
    r"\s+(?:tmdb\s+portrait|espn\s+headshot|wikimedia\s+commons\s+portrait|portrait|headshot)$",
    re.IGNORECASE,
)
_NUMERIC_RANGE_OUTCOME_RE = re.compile(r"\d+(?:\s*(?:[-–]|to)\s*\d+)?%?")
_NON_ENTITY_EXACT_LABELS: frozenset[str] = frozenset(
    {
        "yes",
        "no",
        "rock",
        "pop",
        "country",
        "rap",
        "hip-hop",
        "hip hop",
        "r&b",
        "jazz",
        "metal",
        "electronic",
        "indie",
        "folk",
        "latin",
        "classical",
        "alternative",
    }
)
_NON_ENTITY_PREFIXES: tuple[str, ...] = ("before ", "after ", "by ", "in ", "rank ", "top ", "<", ">")
# Intentional artist-work and stage-name pairs validated against public sets (#13587).
_ARTIST_WORK_AND_STAGE_ALLOWLIST: tuple[tuple[str, str], ...] = (
    ("all i want for christmas is you", "mariah carey"),
    ("tame impala", "kevin parker"),
    ("djo", "joe keery"),
)


def _split_cast_actor_prefix(text: str) -> Optional[str]:
    """Return the actor name before ' as <Role>' when structured as a cast credit."""
    parts = _CAST_AS_SPLIT_RE.split(str(text or "").strip(), maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip()
    return None


def _portrait_name_from_detail(detail: str) -> Optional[str]:
    """Extract the person name preceding a portrait/headshot suffix in ``art.detail``."""
    cleaned = str(detail or "").strip()
    m = _PORTRAIT_DETAIL_SUFFIX_RE.search(cleaned)
    if not m:
        return None
    prefix = cleaned[: m.start()].strip()
    return prefix or None


def is_non_entity_outcome_label(label: str) -> bool:
    """True when an outcome label is structural (Yes/No, date, rank, genre) rather than a named entity."""
    cleaned = str(label or "").strip().lower()
    if not cleaned or cleaned in _NON_ENTITY_EXACT_LABELS:
        return True
    if cleaned.startswith(_NON_ENTITY_PREFIXES):
        return True
    return bool(_NUMERIC_RANGE_OUTCOME_RE.fullmatch(cleaned))


def _monogram_art(subject: str) -> dict[str, Any]:
    """Return a clean no-picture monogram art dict for ``subject``."""
    return {
        "url": None,
        "kind": "monogram",
        "detail": "",
        "accent_color": _fallback_color(subject),
        "initials": _initials(subject),
    }
_ESPN_TEAMLOGO_LEAGUE_RE = re.compile(r"/teamlogos/([a-z0-9_-]+)/", re.IGNORECASE)
_ESPN_LEAGUE_SPORT_PREFIXES: dict[str, tuple[str, ...]] = {
    "nfl": ("americanfootball_nfl",),
    "nba": ("basketball_nba",),
    "wnba": ("basketball_wnba",),
    "nhl": ("icehockey_nhl",),
    "mlb": ("baseball_mlb",),
    "soccer": ("soccer_",),
    "ncaa": ("americanfootball_ncaaf", "basketball_ncaab", "basketball_wncaab", "baseball_ncaa", "lacrosse_ncaa"),
}


def _static_team_logo_matches_sport(
    url: Optional[str],
    sport_key: Optional[str],
) -> bool:
    if not url or not sport_key:
        return True
    m = _ESPN_TEAMLOGO_LEAGUE_RE.search(url)
    if not m:
        return True
    espn_league = m.group(1).lower()
    allowed = _ESPN_LEAGUE_SPORT_PREFIXES.get(espn_league)
    if allowed is None:
        return True
    sk = sport_key.strip().lower()
    return any(
        sk.startswith(prefix) if prefix.endswith("_") else (sk == prefix or sk.startswith(f"{prefix}_"))
        for prefix in allowed
    )


_TEAM_LOOKUP_INDEX_CACHE: Optional[
    tuple[Any, dict[str, list[str]], dict[str, str]]
] = None
_SPORTS_CATEGORIES: frozenset[str] = frozenset(
    {
        "sports",
        "basketball",
        "football",
        "hockey",
        "baseball",
        "soccer",
        "tennis",
        "golf",
        "mma",
        "boxing",
    }
)
_SPORTS_TITLE_SPORT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:uefa\s+)?champions\s+league\b|\bucl\b", re.IGNORECASE), "soccer_uefa_champs_league"),
    (re.compile(r"\beuropa\s+league\b", re.IGNORECASE), "soccer_uefa_europa_league"),
    (re.compile(r"\b(?:english\s+)?premier\s+league\b|\bepl\b", re.IGNORECASE), "soccer_epl"),
    (re.compile(r"\blaliga\b|\bla\s+liga\b", re.IGNORECASE), "soccer_spain_la_liga"),
    (re.compile(r"\bbundesliga\b", re.IGNORECASE), "soccer_germany_bundesliga"),
    (re.compile(r"\bserie\s+a\b", re.IGNORECASE), "soccer_italy_serie_a"),
    (re.compile(r"\bligue\s+1\b", re.IGNORECASE), "soccer_france_ligue_one"),
    (re.compile(r"\bliga\s+mx\b", re.IGNORECASE), "soccer_mexico_ligamx"),
    (re.compile(r"\bmls\b", re.IGNORECASE), "soccer_usa_mls"),
    (re.compile(r"\bfifa\s+world\s+cup\b|\bworld\s+cup\b", re.IGNORECASE), "soccer_fifa_world_cup"),
    (
        re.compile(r"\bwomen'?s\s+(?:march\s+madness|ncaa\b.*\bbasketball|college\s+basketball)\b|\bwncaab\b", re.IGNORECASE),
        "basketball_wncaab",
    ),
    (
        re.compile(r"\bmarch\s+madness\b|\b(?:men'?s\s+)?(?:ncaa\b.*\bbasketball|college\s+basketball)\b|\bfinal\s+four\b", re.IGNORECASE),
        "basketball_ncaab",
    ),
    (re.compile(r"\bwnba\b", re.IGNORECASE), "basketball_wnba"),
    (re.compile(r"\bnba\b", re.IGNORECASE), "basketball_nba"),
    (re.compile(r"\bstanley\s+cup\b|\bnhl\b", re.IGNORECASE), "icehockey_nhl"),
    (
        re.compile(
            r"\bsuper\s+bowl\b(?!\s+(?:halftime|half-time|commercial|ads?|anthem|broadcast|viewership))|\bnfl\b|\bpro\s+football\b|\b(?:afc|nfc)\s+(?:north|south|east|west|champion|championship|#1\s+seed)\b",
            re.IGNORECASE,
        ),
        "americanfootball_nfl",
    ),
    (re.compile(r"\bcollege\s+football\b|\bcfp\b|\bncaaf\b|\bheisman\b", re.IGNORECASE), "americanfootball_ncaaf"),
    (re.compile(r"\bworld\s+series\b|\bmlb\b", re.IGNORECASE), "baseball_mlb"),
)

_LLM_LEAGUE_TO_SPORT_KEY: dict[str, str] = {
    "nfl": "americanfootball_nfl",
    "nba": "basketball_nba",
    "nhl": "icehockey_nhl",
    "mlb": "baseball_mlb",
    "wnba": "basketball_wnba",
    "epl": "soccer_epl",
    "mls": "soccer_usa_mls",
    "liga_mx": "soccer_mexico_ligamx",
    "la_liga": "soccer_spain_la_liga",
    "laliga": "soccer_spain_la_liga",
    "europa": "soccer_uefa_europa_league",
    "ucl": "soccer_uefa_champs_league",
    "fifa_wc": "soccer_fifa_world_cup",
    "ncaaf": "americanfootball_ncaaf",
    "ncaab": "basketball_ncaab",
    "wncaab": "basketball_wncaab",
}


def _strip_club_affixes(name: str) -> str:
    cleaned = _TEAM_CLUB_PREFIX_RE.sub("", name.strip()).strip()
    return _TEAM_CLUB_SUFFIX_RE.sub("", cleaned).strip()


def _is_sports_definition(definition: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(definition, Mapping):
        return False
    if str(definition.get("category") or "").strip().lower() in _SPORTS_CATEGORIES:
        return True
    rule = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
    for sec in rule.get("sections") or ():
        if isinstance(sec, Mapping) and isinstance(sec.get("atom_query"), Mapping):
            aq = sec["atom_query"]
            if aq.get("kind") == "events" or aq.get("sport_key"):
                return True
    return False


def _infer_sports_key_for_market(
    market: Mapping[str, Any],
    definition: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    for key_field in ("sport", "sport_key"):
        raw = str(market.get(key_field) or "").strip().lower()
        if raw and "_" in raw:
            return raw
    raw_league = str(market.get("llm_league") or "").strip().lower()
    if raw_league in _LLM_LEAGUE_TO_SPORT_KEY:
        return _LLM_LEAGUE_TO_SPORT_KEY[raw_league]
    title = str(market.get("name") or market.get("raw_title") or "").strip()
    if title:
        for pat, sk in _SPORTS_TITLE_SPORT_PATTERNS:
            if pat.search(title):
                return sk
    if isinstance(definition, Mapping):
        rule = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
        sec_sports = {
            str(sec["atom_query"].get("sport_key") or "").strip().lower()
            for sec in (rule.get("sections") or ())
            if isinstance(sec, Mapping)
            and isinstance(sec.get("atom_query"), Mapping)
            and sec["atom_query"].get("sport_key")
        }
        if len(sec_sports) == 1:
            return next(iter(sec_sports))
        def_tag = str(definition.get("tag") or "").strip().lower()
        def_cat = str(definition.get("category") or "").strip().lower()
        if def_tag == "nfl" or (def_cat == "football" and "college" not in str(definition.get("name") or "").lower()):
            return "americanfootball_nfl"
    return None


def _is_sports_context(
    market: Mapping[str, Any],
    definition: Optional[Mapping[str, Any]] = None,
) -> bool:
    llm_cat = str(
        market.get("llm_sport_category") or market.get("category") or ""
    ).strip().lower()
    if llm_cat and llm_cat not in _SPORTS_CATEGORIES and not _is_sports_definition(definition):
        return False
    return (
        llm_cat in _SPORTS_CATEGORIES
        or _infer_sports_key_for_market(market, definition) is not None
        or _is_sports_definition(definition)
    )


def _extract_team_crest_record(team_obj: Any) -> Optional[dict[str, Any]]:
    """Build a verified ``team_logo`` art record from a TeamSnapshot/Team/dict, or None."""
    if team_obj is None:
        return None
    if isinstance(team_obj, Mapping):
        url_sm = str(team_obj.get("logo_url_small") or "").strip()
        url_lg = str(team_obj.get("logo_url_large") or "").strip()
        url_alt = str(team_obj.get("logo_url") or "").strip()
        abbr = str(team_obj.get("abbreviation") or "").strip()
        color = str(team_obj.get("primary_color") or "").strip()
    else:
        url_sm = str(getattr(team_obj, "logo_url_small", None) or "").strip()
        url_lg = str(getattr(team_obj, "logo_url_large", None) or "").strip()
        url_alt = str(getattr(team_obj, "logo_url", None) or "").strip()
        abbr = str(getattr(team_obj, "abbreviation", None) or "").strip()
        color = str(getattr(team_obj, "primary_color", None) or "").strip()
    chosen_url = ""
    for candidate in (url_sm, url_lg, url_alt):
        if candidate and not candidate.endswith(_PLACEHOLDER_CREST_SUFFIX):
            chosen_url = candidate
            break
    if not chosen_url:
        return None
    return {
        "url": chosen_url,
        "kind": "team_logo",
        "detail": abbr.upper(),
        "accent_color": color or "#1E293B",
    }


def _build_team_lookup_from_entries(raw_teams: Sequence[Any]) -> Any:
    """Convert snapshot team dicts or objects into a ``TeamNameLookup``."""
    from app.routes.events import TeamSnapshot, _dedupe_team_name_lookup

    snaps: list[TeamSnapshot] = []
    for item in raw_teams:
        if isinstance(item, TeamSnapshot):
            snaps.append(item)
        elif isinstance(item, Mapping):
            snaps.append(
                TeamSnapshot(
                    id=item.get("id"),
                    sport_id=item.get("sport_id"),
                    sport_key=item.get("sport_key") or item.get("sport"),
                    name=item.get("name"),
                    slug=item.get("slug"),
                    abbreviation=item.get("abbreviation"),
                    primary_color=item.get("primary_color"),
                    secondary_color=item.get("secondary_color"),
                    logo_url_small=item.get("logo_url_small") or item.get("logo_url"),
                    logo_url_large=item.get("logo_url_large") or item.get("logo_url"),
                    alternate_names=tuple(item.get("alternate_names") or ()),
                    espn_id=item.get("espn_id"),
                )
            )
        elif hasattr(item, "name"):
            snaps.append(
                TeamSnapshot(
                    id=getattr(item, "id", None),
                    sport_id=getattr(item, "sport_id", None),
                    sport_key=getattr(item, "sport_key", None),
                    name=getattr(item, "name", None),
                    slug=getattr(item, "slug", None),
                    abbreviation=getattr(item, "abbreviation", None),
                    primary_color=getattr(item, "primary_color", None),
                    secondary_color=getattr(item, "secondary_color", None),
                    logo_url_small=getattr(item, "logo_url_small", None) or getattr(item, "logo_url", None),
                    logo_url_large=getattr(item, "logo_url_large", None) or getattr(item, "logo_url", None),
                    alternate_names=tuple(getattr(item, "alternate_names", None) or ()),
                    espn_id=getattr(item, "espn_id", None),
                )
            )
    return _dedupe_team_name_lookup(snaps)


class SubjectArtResolver:
    """Unified verified-art resolver across teams, people, and films/series (#12659, #12850)."""

    def __init__(
        self,
        *,
        team_lookup: Any = None,
        _static_by_norm: Optional[dict[str, dict[str, Any]]] = None,
    ) -> None:
        self._team_lookup = team_lookup
        self._team_keys_by_norm: dict[str, list[str]] = {}
        self._team_prefix_unique: dict[str, str] = {}
        self._person_names_by_url: dict[str, set[str]] = {}
        if _static_by_norm is not None:
            self._by_norm = _static_by_norm
        else:
            self._by_norm: dict[str, dict[str, Any]] = {}
            self._load_catalogs()
        if self._team_lookup is not None:
            self._index_team_lookup()

    def _index_team_lookup(self) -> None:
        global _TEAM_LOOKUP_INDEX_CACHE
        cached = _TEAM_LOOKUP_INDEX_CACHE
        is_immutable_lookup = type(self._team_lookup).__name__ == "TeamNameLookup"
        if is_immutable_lookup and cached is not None and cached[0] is self._team_lookup:
            self._team_keys_by_norm = cached[1]
            self._team_prefix_unique = cached[2]
            return

        seen_raw: set[str] = set()
        raw_keys: list[str] = []
        if isinstance(self._team_lookup, Mapping):
            for k in self._team_lookup.keys():
                if isinstance(k, str) and k and k not in seen_raw:
                    seen_raw.add(k)
                    raw_keys.append(k)
        by_league = getattr(self._team_lookup, "by_league", None)
        if isinstance(by_league, Mapping):
            for k in by_league.keys():
                if isinstance(k, str) and k and k not in seen_raw:
                    seen_raw.add(k)
                    raw_keys.append(k)

        prefix_candidates: dict[str, set[str]] = {}
        for k in raw_keys:
            for nk in (_norm_key(k), _ascii_fold_key(k)):
                if nk:
                    bucket = self._team_keys_by_norm.setdefault(nk, [])
                    if k not in bucket:
                        bucket.append(k)
            stripped = _strip_club_affixes(k)
            if stripped and stripped != k:
                for nk in (_norm_key(stripped), _ascii_fold_key(stripped)):
                    if nk:
                        prefix_candidates.setdefault(nk, set()).add(k)
        for nk, matches in prefix_candidates.items():
            if len(matches) == 1:
                self._team_prefix_unique[nk] = next(iter(matches))

        if is_immutable_lookup:
            _TEAM_LOOKUP_INDEX_CACHE = (
                self._team_lookup,
                self._team_keys_by_norm,
                self._team_prefix_unique,
            )

    _NFL_CITY_TO_CANONICAL_TEAM: dict[str, str] = {
        "arizona": "Arizona Cardinals",
        "atlanta": "Atlanta Falcons",
        "baltimore": "Baltimore Ravens",
        "buffalo": "Buffalo Bills",
        "carolina": "Carolina Panthers",
        "chicago": "Chicago Bears",
        "cincinnati": "Cincinnati Bengals",
        "cleveland": "Cleveland Browns",
        "dallas": "Dallas Cowboys",
        "denver": "Denver Broncos",
        "detroit": "Detroit Lions",
        "green bay": "Green Bay Packers",
        "houston": "Houston Texans",
        "indianapolis": "Indianapolis Colts",
        "jacksonville": "Jacksonville Jaguars",
        "kansas city": "Kansas City Chiefs",
        "las vegas": "Las Vegas Raiders",
        "los angeles c": "Los Angeles Chargers",
        "la chargers": "Los Angeles Chargers",
        "los angeles r": "Los Angeles Rams",
        "la rams": "Los Angeles Rams",
        "miami": "Miami Dolphins",
        "minnesota": "Minnesota Vikings",
        "new england": "New England Patriots",
        "new orleans": "New Orleans Saints",
        "new york g": "New York Giants",
        "ny giants": "New York Giants",
        "new york j": "New York Jets",
        "ny jets": "New York Jets",
        "philadelphia": "Philadelphia Eagles",
        "pittsburgh": "Pittsburgh Steelers",
        "san francisco": "San Francisco 49ers",
        "seattle": "Seattle Seahawks",
        "tampa bay": "Tampa Bay Buccaneers",
        "tennessee": "Tennessee Titans",
        "washington": "Washington Commanders",
    }

    def _resolve_from_team_lookup(
        self,
        subject: str,
        *,
        sport_key: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        if self._team_lookup is None or not subject:
            return None
        from app.routes.events import (
            _lookup_mens_college_basketball,
            _team_for_event_by_name,
        )

        candidates: list[str] = []
        subj_key = " ".join(subject.strip().lower().split())
        if sport_key == "americanfootball_nfl" and subj_key in self._NFL_CITY_TO_CANONICAL_TEAM:
            candidates.append(self._NFL_CITY_TO_CANONICAL_TEAM[subj_key])
        if subject not in candidates:
            candidates.append(subject)
        stripped_subject = _strip_club_affixes(subject)
        subject_forms = [subject]
        if stripped_subject and stripped_subject != subject:
            subject_forms.append(stripped_subject)
        for form in subject_forms:
            if form not in candidates:
                candidates.append(form)
            for nk in (_norm_key(form), _ascii_fold_key(form)):
                if not nk:
                    continue
                for alias_key in self._team_keys_by_norm.get(nk, ()):
                    if alias_key not in candidates:
                        candidates.append(alias_key)
                pref_key = self._team_prefix_unique.get(nk)
                if pref_key and pref_key not in candidates:
                    candidates.append(pref_key)

        for cand in candidates:
            team_row = _team_for_event_by_name(self._team_lookup, cand, sport_key)
            rec = _extract_team_crest_record(team_row)
            if rec is not None and (
                not sport_key or _static_team_logo_matches_sport(rec.get("url"), sport_key)
            ):
                return rec

        if sport_key and sport_key.startswith("soccer_"):
            by_league = getattr(self._team_lookup, "by_league", None)
            if isinstance(by_league, Mapping):
                want_women = "women" in sport_key
                for prefer_same_gender in (True, False):
                    for cand in candidates:
                        rows = by_league.get(cand)
                        if not isinstance(rows, Mapping):
                            continue
                        for row in rows.values():
                            rsk = str(getattr(row, "sport_key", None) or "").lower()
                            if not rsk.startswith("soccer"):
                                continue
                            if prefer_same_gender and (("women" in rsk) != want_women):
                                continue
                            rec = _extract_team_crest_record(row)
                            if rec is not None and _static_team_logo_matches_sport(
                                rec.get("url"), sport_key
                            ):
                                return rec

        if sport_key == "basketball_wncaab":
            for cand in candidates:
                mens_row = _lookup_mens_college_basketball(self._team_lookup, cand)
                rec = _extract_team_crest_record(mens_row)
                if rec is not None:
                    return rec

        return None

    def _record_person_url_aliases(
        self,
        url: Optional[str],
        names: Sequence[str],
        *,
        kind: Optional[str],
        detail: Optional[str],
    ) -> None:
        if not url:
            return
        k_low = str(kind or "").strip().lower()
        d_str = str(detail or "").strip()
        det_name = _portrait_name_from_detail(d_str)
        if not (k_low in _PERSON_ART_KINDS or det_name is not None or "/headshots/" in url.lower()):
            return
        bucket = self._person_names_by_url.setdefault(url, set())
        candidates = list(names)
        if det_name:
            candidates.append(det_name)
        elif "," in d_str and k_low in _PERSON_ART_KINDS:
            candidates.append(d_str.split(",", 1)[0].strip())
        for raw in candidates:
            s = str(raw or "").strip()
            if not s:
                continue
            actor_prefix = _split_cast_actor_prefix(s)
            if actor_prefix:
                s = actor_prefix
            if s:
                bucket.add(s)

    def _register(
        self,
        aliases: Sequence[str],
        record: dict[str, Any],
        *,
        display_aliases: Optional[Sequence[str]] = None,
    ) -> None:
        disp_list = [str(a) for a in (display_aliases if display_aliases is not None else aliases) if str(a).strip()]
        self._record_person_url_aliases(
            record.get("url"),
            disp_list,
            kind=record.get("kind"),
            detail=record.get("detail"),
        )
        primary_disp = disp_list[0] if disp_list else None
        by_fold: dict[str, list[str]] = {}
        for raw in disp_list:
            fk = _ascii_fold_key(raw)
            if fk:
                by_fold.setdefault(fk, []).append(str(raw))
        for raw in aliases:
            fk = _ascii_fold_key(raw)
            rec_for_alias = record
            if fk and len(by_fold.get(fk, ())) > 1 and "canonical_name" not in record:
                prim_for_fold = (
                    primary_disp
                    if primary_disp and _ascii_fold_key(primary_disp) == fk
                    else None
                )
                pref = _pick_preferred_subject_spelling(by_fold[fk], primary_display=prim_for_fold)
                if pref:
                    rec_for_alias = {**record, "canonical_name": pref}
            for nk in (_norm_key(raw), fk):
                if nk and nk not in self._by_norm:
                    self._by_norm[nk] = rec_for_alias

    def _load_catalogs(self) -> None:
        # 1. Dedicated machinery subject art (ESPN headshots, NFL crests, verified Commons portraits)
        if _SUBJECT_ART_PATH.exists():
            raw = json.loads(_SUBJECT_ART_PATH.read_text(encoding="utf-8"))
            for item in raw.get("subjects") or ():
                if not isinstance(item, Mapping) or not item.get("url"):
                    continue
                rec = {
                    "url": str(item["url"]),
                    "kind": str(item.get("kind") or "person"),
                    "detail": str(item.get("detail") or ""),
                    "accent_color": str(item.get("accent_color") or ""),
                    "author": item.get("author"),
                    "license": item.get("license"),
                    "source_page": item.get("source_page"),
                }
                disp_aliases = [str(a) for a in (item.get("aliases") or ()) if a]
                self._register(
                    disp_aliases + [str(item.get("key") or "")],
                    rec,
                    display_aliases=disp_aliases,
                )
            for team_name, meta in (raw.get("nfl_teams") or {}).items():
                if not isinstance(meta, Mapping):
                    continue
                abbr = str(meta.get("abbr") or "").lower()
                color = str(meta.get("color") or "#1E293B")
                if not abbr:
                    continue
                short_name = team_name.split()[-1]
                city_only = " ".join(team_name.split()[:-1])
                aliases = [team_name, short_name]
                if city_only and city_only not in {"New York", "Los Angeles"}:
                    aliases.append(city_only)
                self._register(
                    aliases,
                    {
                        "url": f"https://a.espncdn.com/i/teamlogos/nfl/500/{abbr}.png",
                        "kind": "team_logo",
                        "detail": abbr.upper(),
                        "accent_color": color,
                    },
                )

        # 2. Paired metric register (vetted TMDB posters/headshots & NHL/NBA/NFL logos; horror/doc-crime excluded)
        if _PAIRED_REGISTER_PATH.exists():
            pm = json.loads(_PAIRED_REGISTER_PATH.read_text(encoding="utf-8"))
            for pset in (pm.get("sets") or {}).values():
                if not isinstance(pset, Mapping):
                    continue
                for entry in pset.get("entries") or ():
                    if not isinstance(entry, Mapping):
                        continue
                    art = entry.get("art")
                    if not isinstance(art, Mapping) or not art.get("url"):
                        continue
                    if art.get("adult") is True:
                        continue
                    genres = set(art.get("genre_ids") or ())
                    if 27 in genres or {99, 80}.issubset(genres):
                        continue
                    subj = str(entry.get("subject") or "").strip()
                    if not subj:
                        continue
                    self._register(
                        [subj],
                        {
                            "url": str(art["url"]),
                            "kind": str(art.get("kind") or "tmdb_poster"),
                            "detail": str(entry.get("detail") or ""),
                            "accent_color": "#0F172A",
                        },
                    )

        # 3. Verified Discover art register (Wikimedia Commons & TVMaze vetted entries)
        if _VERIFIED_ART_PATH.exists():
            va = json.loads(_VERIFIED_ART_PATH.read_text(encoding="utf-8"))
            for entry in va.get("entries") or ():
                if not isinstance(entry, Mapping) or not entry.get("url"):
                    continue
                aliases = [str(a) for a in (entry.get("aliases") or ()) if a]
                all_aliases = list(aliases)
                if entry.get("entity_key"):
                    all_aliases.append(str(entry["entity_key"]))
                self._register(
                    all_aliases,
                    {
                        "url": str(entry["url"]),
                        "kind": str(entry.get("kind") or "person"),
                        "detail": str(entry.get("verified_subject") or "")[:44],
                        "accent_color": "",
                        "author": entry.get("author"),
                        "license": entry.get("license"),
                        "source_page": entry.get("source_page"),
                    },
                    display_aliases=aliases,
                )

    def resolve(
        self,
        subject: str,
        *,
        explicit_url: Optional[str] = None,
        explicit_color: Optional[str] = None,
        sport_key: Optional[str] = None,
        allow_team_lookup: Optional[bool] = None,
    ) -> dict[str, Any]:
        clean_subj = _OUTCOME_PROP_SUFFIX_RE.sub("", subject.strip())
        if allow_team_lookup is True and self._team_lookup is not None and not explicit_url:
            team_hit = self._resolve_from_team_lookup(
                clean_subj or subject, sport_key=sport_key
            )
            if team_hit is not None:
                color = explicit_color or team_hit.get("accent_color") or _fallback_color(clean_subj or subject)
                return {
                    "url": team_hit["url"],
                    "kind": team_hit["kind"],
                    "detail": team_hit.get("detail") or "",
                    "accent_color": color,
                    "initials": _initials(clean_subj or subject),
                }
        nk = _norm_key(clean_subj) or _norm_key(subject)
        fk = _ascii_fold_key(clean_subj) or _ascii_fold_key(subject)
        hit = self._by_norm.get(nk) or (self._by_norm.get(fk) if fk else None)
        if hit is None:
            actor_name = _split_cast_actor_prefix(clean_subj or subject)
            if actor_name:
                a_nk = _norm_key(actor_name)
                a_fk = _ascii_fold_key(actor_name)
                actor_hit = self._by_norm.get(a_nk) or (self._by_norm.get(a_fk) if a_fk else None)
                if actor_hit and str(actor_hit.get("kind") or "").lower() in _PERSON_ART_KINDS:
                    hit = actor_hit
        if hit and hit.get("kind") in _TEAM_STATIC_LOGO_KINDS:
            if allow_team_lookup is False or not _static_team_logo_matches_sport(
                hit.get("url"), sport_key
            ):
                hit = None
        url = explicit_url or (hit["url"] if hit else None)
        kind = hit.get("kind") if hit else ("explicit" if url else "monogram")
        if not url:
            from app.utils.nation_flags import flag_url as _nation_flag_url

            country_flag = _nation_flag_url(clean_subj or subject) or _nation_flag_url(subject)
            if country_flag:
                url = country_flag
                kind = "flag"
        color = explicit_color or (hit.get("accent_color") if hit else None) or _fallback_color(clean_subj or subject)
        out: dict[str, Any] = {
            "url": url,
            "kind": kind,
            "detail": (hit.get("detail") if hit else "") or "",
            "accent_color": color,
            "initials": _initials(clean_subj or subject),
        }
        if hit and hit.get("canonical_name"):
            out["canonical_name"] = str(hit["canonical_name"])
        return out


def _extract_portrait_person_names(
    art: Mapping[str, Any],
    resolver: Optional[SubjectArtResolver] = None,
) -> tuple[list[str], set[str]]:
    """Return ``(display_names, folded_names)`` when ``art`` depicts a named person portrait."""
    url = str(art.get("url") or "").strip()
    if not url:
        return [], set()
    kind = str(art.get("kind") or "").strip().lower()
    detail = str(art.get("detail") or "").strip()
    det_name = _portrait_name_from_detail(detail)
    is_portrait = (
        kind in _PERSON_ART_KINDS
        or det_name is not None
        or "/headshots/" in url.lower()
    )
    if not is_portrait:
        return [], set()

    raw_names: list[str] = []
    if det_name:
        raw_names.append(det_name)
        if "," in det_name:
            raw_names.append(det_name.split(",", 1)[0].strip())
    elif "," in detail and kind in _PERSON_ART_KINDS:
        raw_names.append(detail.split(",", 1)[0].strip())
    if resolver is not None:
        for reg_name in sorted(resolver._person_names_by_url.get(url, ())):
            raw_names.append(reg_name)

    display_names: list[str] = []
    folded_names: set[str] = set()
    for nm in raw_names:
        cleaned = str(nm or "").strip()
        fk = _ascii_fold_key(cleaned)
        if cleaned and fk and fk not in folded_names:
            folded_names.add(fk)
            display_names.append(cleaned)
    return display_names, folded_names


def art_subject_mismatch_reason(
    subject_texts: Sequence[str],
    art: Mapping[str, Any],
    *,
    resolver: Optional[SubjectArtResolver] = None,
) -> Optional[str]:
    """Return a mismatch reason when a person portrait depicts someone other than the subject."""
    if not isinstance(art, Mapping) or not art.get("url"):
        return None
    display_names, portrait_folds = _extract_portrait_person_names(art, resolver=resolver)
    if not portrait_folds:
        return None
    hay_parts = [_ascii_fold_key(t) for t in subject_texts if t]
    hay = " ".join(part for part in hay_parts if part)
    if not hay:
        return None
    padded_hay = f" {hay} "
    hay_tokens = set(hay.split())

    for work_or_stage, artist_fold in _ARTIST_WORK_AND_STAGE_ALLOWLIST:
        if f" {work_or_stage} " in padded_hay and artist_fold in portrait_folds:
            return None

    for p_fold in portrait_folds:
        if f" {p_fold} " in padded_hay:
            return None
        tokens = [t for t in p_fold.split() if len(t) >= 3]
        if tokens and all(t in hay_tokens for t in tokens):
            return None

    primary_subj = next((str(t).strip() for t in subject_texts if str(t or "").strip()), "")
    return f"Portrait depicts {', '.join(display_names)} rather than {primary_subj!r}"


def _gate_outcome_art(
    outcome_name: str,
    context_texts: Sequence[str],
    art: Mapping[str, Any],
    *,
    resolver: Optional[SubjectArtResolver] = None,
    fallback_subject: Optional[str] = None,
) -> dict[str, Any]:
    """Strip any mismatched person portrait so a row serves no picture rather than a wrong face."""
    clean_out = str(outcome_name or "").strip()
    if not isinstance(art, Mapping):
        return _monogram_art(str(fallback_subject or clean_out or "Subject"))
    if not art.get("url"):
        return dict(art)
    check_texts: Sequence[str] = (
        [clean_out, *context_texts] if is_non_entity_outcome_label(clean_out) else [clean_out]
    )
    if art_subject_mismatch_reason(check_texts, art, resolver=resolver) is None:
        return dict(art)
    return _monogram_art(str(fallback_subject or clean_out or "Subject"))


@lru_cache(maxsize=1)
def _default_art_resolver() -> SubjectArtResolver:
    return SubjectArtResolver()


def _is_event_toss_up(item: Mapping[str, Any]) -> bool:
    """Ruling 253: A — a game is a toss-up iff neither side is above 55%."""
    if isinstance(item.get("is_toss_up"), bool):
        return bool(item["is_toss_up"])
    ap_pct = item.get("away_pct")
    hp_pct = item.get("home_pct")
    if isinstance(ap_pct, int) and isinstance(hp_pct, int):
        return max(ap_pct, hp_pct) <= int(round(TOSS_UP_MAX_SIDE_PROB * 100))
    fav = item.get("fav_prob")
    if isinstance(fav, (int, float)):
        return float(fav) <= (TOSS_UP_MAX_SIDE_PROB + 1e-9)
    ap = float(item.get("away_prob") or 0.5)
    hp = float(item.get("home_prob") or 0.5)
    return max(ap, hp) <= (TOSS_UP_MAX_SIDE_PROB + 1e-9)


def choose_section_form(
    atoms_kind: str,
    selected_items: Sequence[Mapping[str, Any]],
) -> str:
    """Choose a section's visual form strictly from the shape of its atoms (zero topic checks)."""
    if atoms_kind == "paired_stage":
        return "paired_stage_bars"

    if atoms_kind == "market_history":
        return "probability_history_chart"

    if atoms_kind == "events":
        any_started = any(
            str(it.get("status") or "").strip().lower()
            in {"live", "in_progress", "halftime"}
            for it in selected_items
        )
        if any_started:
            return "matchup_slate"
        in_band = sum(1 for it in selected_items if _is_event_toss_up(it))
        if in_band >= TOSS_UP_MIN_SECTION_COUNT and in_band == len(selected_items):
            return "coin_flip_matchups"
        return "matchup_slate"

    if atoms_kind == "markets":
        if len(selected_items) == 1:
            outcomes = selected_items[0].get("outcomes") or ()
            if len(outcomes) == 2:
                return "duel_bar"
            if len(outcomes) >= 3:
                return "contender_spotlight"
            return "benchmark_strip"
        if len(selected_items) >= 2 and all(
            len(it.get("outcomes") or ()) >= 2 for it in selected_items
        ):
            return "sibling_fields_grid"
        return "benchmark_strip"

    return "sibling_fields_grid"


_MONTH_FULL_MAP: dict[str, str] = {
    "jan": "January",
    "january": "January",
    "feb": "February",
    "february": "February",
    "mar": "March",
    "march": "March",
    "apr": "April",
    "april": "April",
    "may": "May",
    "jun": "June",
    "june": "June",
    "jul": "July",
    "july": "July",
    "aug": "August",
    "august": "August",
    "sep": "September",
    "sept": "September",
    "september": "September",
    "oct": "October",
    "october": "October",
    "nov": "November",
    "november": "November",
    "dec": "December",
    "december": "December",
}


def _expand_month_token(tok: str) -> str:
    return _MONTH_FULL_MAP.get(tok.strip().lower(), tok.strip().capitalize())


def _clean_section_market_label(name: str) -> str:
    """Rewrite raw venue strings into clean Bain Luck market titles (Slice 5 Note 5)."""
    cleaned = re.sub(r"\s+", " ", name.strip())
    if not cleaned:
        return ""

    # ── Federal Reserve & U.S. Macro house titles ────────────────────────
    m = re.match(
        r"^what\s+will\s+(?:the\s+)?fed\s+rate\s+be\s+at\s+the\s+end\s+of\s+(\d{4})\??$",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        return f"End-of-{m.group(1)} Fed Rate"

    m = re.match(
        r"^what\s+will\s+(?:the\s+)?fed\s+rate\s+hit\s+before\s+(\d{4})\??$",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        return f"Fed Rate Highs & Lows Before {m.group(1)}"

    m = re.match(
        r"^how\s+many\s+fed\s+rate\s+(hikes|cuts)\s+in\s+(\d{4})\??$",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        return f"{m.group(2)} Fed Rate {m.group(1).capitalize()}"

    m = re.match(
        r"^fed\s+decision\s+in\s+([a-z]+)(?:\s+(\d{4}))?\??$",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        mon = _expand_month_token(m.group(1))
        yr = (m.group(2) or "").strip()
        return f"{mon} {yr + ' ' if yr else ''}Fed Decision"

    m = re.match(r"^fed\s+decisions\s*\(([^)]+)\)\??$", cleaned, re.IGNORECASE)
    if m:
        span = m.group(1).strip().replace("-", "–")
        return f"{span} FOMC Rate Path"

    if re.match(r"^fed\s+rate\s+cut\s+by(?:\.\.\.|…)?\??$", cleaned, re.IGNORECASE):
        return "First Fed Rate Cut Timing"

    if re.match(r"^next\s+fed\s+rate\s+cut\??$", cleaned, re.IGNORECASE):
        return "Next Fed Rate Cut"

    if re.match(r"^predicted\s+fed\s+rate\s+under\s+each\s+fed\s+chair\??$", cleaned, re.IGNORECASE):
        return "Implied Rate by Fed Chair"

    m = re.match(
        r"^(?:us|u\.s\.)\s+(?:real\s+)?gdp\s+growth\s+in\s+(q[1-4]\s+\d{4}|\d{4})\??$",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        return f"{m.group(1).upper()} U.S. GDP Growth"

    m = re.match(r"^gdp\s+growth\s+in\s+(\d{4})\??$", cleaned, re.IGNORECASE)
    if m:
        return f"{m.group(1)} U.S. GDP Growth"

    m = re.match(
        r"^unemployment\s+rate\s+in\s+([a-z]+)(?:\s+(\d{4}))?\??$",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        mon = _expand_month_token(m.group(1))
        yr = (m.group(2) or "").strip()
        short_mon = mon[:3] if yr and len(mon) > 5 else mon
        return f"{short_mon} {yr + ' ' if yr else ''}U.S. Unemployment"

    m = re.match(r"^([a-z]+)\s+unemployment\s+rate\??$", cleaned, re.IGNORECASE)
    if m and m.group(1).lower() in _MONTH_FULL_MAP:
        return f"{_expand_month_token(m.group(1))} U.S. Unemployment"

    m = re.match(r"^recession\s+in\s+(\d{4})\??$", cleaned, re.IGNORECASE)
    if m:
        return f"{m.group(1)} U.S. Recession"

    m = re.match(r"^(?:us|u\.s\.)\s+recession\s+by\s+end\s+of\s+(\d{4})\??$", cleaned, re.IGNORECASE)
    if m:
        return f"U.S. Recession by End of {m.group(1)}"

    # ── Politics / Elections house titles ────────────────────────────────
    if re.match(r"^2028\s+presidential\s+election\s+winner\??\s*\(party\)$", cleaned, re.IGNORECASE):
        return "White House Party Control"

    m = re.match(
        r"^(?:2028\s+)?presidential\s+election:\s*(.+?)\s+winner\??(?:\s*\(\d{4}\))?$",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        return f"{m.group(1).strip()} Presidential Race"

    m = re.match(
        r"^(.+?)\s+(republican|democratic)\s+presidential\s+(primary|caucus)\s+winner(?:\s+\d{4})?\??$",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        return f"{m.group(1).strip()} {m.group(2).capitalize()} {m.group(3).capitalize()}"

    if re.match(r"^(?:2028\s+)?(?:u\.s\.\s+)?vice-presidential\s+election\s+winner\??$", cleaned, re.IGNORECASE):
        return "Vice-Presidential Race"

    m = re.match(r"^(?:2028\s+)?(democratic|republican)\s+vp\s+nominee\??$", cleaned, re.IGNORECASE)
    if m:
        return f"{m.group(1).capitalize()} VP Nominee"

    m = re.match(r"^(?:2028\s+)?(democratic|republican)\s+presidential\s+ticket\??$", cleaned, re.IGNORECASE)
    if m:
        return f"{m.group(1).capitalize()} Presidential Ticket"

    m = re.match(
        r"^(democratic|republican)\s+presidential\s+nominee(?:\s+\d{4})?\??(?:\s*\(\d{4}\))?$",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        return f"{m.group(1).capitalize()} Presidential Nominee"

    if re.match(r"^(?:2028\s+)?house\s+winner\??(?:\s*\(\d{4}\))?$", cleaned, re.IGNORECASE):
        return "U.S. House Control"

    m = re.match(
        r"^(.+?)\s+(senate|house|gubernatorial|governor)\s+winner\??(?:\s*\(\d{4}\))?$",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        return f"{m.group(1).strip()} {m.group(2).capitalize()} Race"

    # ── Seasonal / Entertainment / General binary & casting titles ───────
    m = re.match(
        r"^will\s+it\s+snow\s+in\s+(.+?)\s+on\s+christmas\??$",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    m = re.match(r"^next\s+james\s+bond\s+film:\s*(.+)$", cleaned, re.IGNORECASE)
    if m:
        role = m.group(1).strip()
        role = re.sub(r"^artist\s+performing\s+the\s+", "", role, flags=re.IGNORECASE)
        role = re.sub(r"^(?:actor|actress)\s+cast\s+as\s+(?:the\s+)?", "", role, flags=re.IGNORECASE)
        role = role.strip()
        if role:
            return role[0].upper() + role[1:]

    m = re.match(
        r"^(?:will\s+)?(.+?)(?:\s*:\s*|\s+(?:get\s+|be\s+)?)engaged(?:\s+(?:in\s+\d{4}|this\s+year|before\s+\d{4}|by\s+end\s+of\s+\d{4}))?\??$",
        cleaned,
        re.IGNORECASE,
    )
    if m and "hours" not in cleaned.lower():
        couple = re.sub(r"\s+and\s+", " & ", m.group(1).strip(), flags=re.IGNORECASE)
        if couple:
            return couple

    # ── Sports / Awards / General cleanup ────────────────────────────────
    is_oscar_nom = bool(re.match(r"^oscar\s+nominees?:", cleaned, re.IGNORECASE))
    cleaned = re.sub(
        r"^(?:(?:NFL|NBA|MLB|NHL|WNBA|MLS|PGA|NCAA|CFB):\s*|Pro\s+(?:Football|Basketball|Baseball|Hockey|Soccer|Golf|Tennis|MMA|Boxing):?\s*|(?:NFL|NBA|MLB|NHL|WNBA|MLS|PGA)\s+(?=(?:Passing|Rushing|Receiving|Points|Rebounds|Assists|Steals|Blocks|Three-Pointers|Home\s+Runs|Strikeouts|Batting|Hits|Runs|RBIs?|Goals|Saves|MVP|Most\s+Valuable|Defensive\s+Player|Offensive\s+Player|Rookie|Sixth\s+Man|Most\s+Improved|Clutch\s+Player|Coach|Comeback\s+Player|Cy\s+Young|Hart|Norris|Vezina|Selke|Calder|Heisman)\b)|Oscar\s+Winners?:\s*|Oscar\s+nominees?:\s*|Oscars?\s+\d{4}:\s*|2028\s+U\.S\.\s*|2028\s+)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Strip redundant parenthetical stat abbreviations after spelled-out stat names ('Points Per Game (PPG) Leader' -> 'Points Per Game Leader')
    cleaned = re.sub(
        r"\s*\((?:PPG|RPG|APG|SPG|BPG|TDs?|YPG|ERA|HR|RBIs?|3PM)\)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    if is_oscar_nom and not re.search(r"\bnominations?\b", cleaned, re.IGNORECASE):
        cleaned = f"{cleaned.strip()} Nominations"
    if re.match(r"^best\s+music\s*\(\s*original\s+score\s*\)", cleaned, re.IGNORECASE):
        cleaned = re.sub(
            r"^best\s+music\s*\(\s*original\s+score\s*\)",
            "Best Original Score",
            cleaned,
            flags=re.IGNORECASE,
        )
    if re.match(r"^best\s+", cleaned, re.IGNORECASE):
        cleaned = re.sub(r"\s+film\s+winner$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+film(?=\s+nominations$|$)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+winner$", "", cleaned, flags=re.IGNORECASE)
    # Strip redundant trailing 'Winner' on individual awards ('Defensive Player of the Year Winner' -> 'Defensive Player of the Year')
    cleaned = re.sub(
        r"((?:MVP|Most\s+Valuable\s+Player|Player\s+of\s+the\s+Year|Rookie\s+of\s+the\s+Year|Sixth\s+Man\s+of\s+the\s+Year|Coach\s+of\s+the\s+Year|Most\s+Improved\s+Player|Comeback\s+Player\s+of\s+the\s+Year|Clutch\s+Player\s+of\s+the\s+Year|Cy\s+Young(?:\s+Award)?|Heisman(?:\s+Trophy)?))\s+winner\??$",
        r"\1",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Strip venue trailing '? (2028)', '(2028)', '?', and conversational prefixes
    cleaned = re.sub(r"\?\s*\(\d{4}\)\s*$", "", cleaned)
    cleaned = re.sub(r"\s*\(\d{4}\)\s*$", "", cleaned)
    cleaned = re.sub(r"\s*\?\s*$", "", cleaned)
    cleaned = re.sub(r"\s+2028$", "", cleaned)
    cleaned = re.sub(r"^(?:what\s+will\s+(?:the\s+)?|who\s+will\s+(?:be\s+|win\s+)?)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+winner$", " Winner", cleaned)
    cleaned = cleaned.strip()
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned or name.strip()


_CUMULATIVE_OUTCOME_RE = re.compile(
    r"^(?:above|below|over|under|at\s+least|more\s+than|fewer\s+than)\b",
    re.IGNORECASE,
)

#: Maximum age (days) for a market's newest live outcome observation before it is
#: refused from computed groupings (#12288: prevents past-ceremony markets like #109566,
#: last updated Mar 12 with all 16 prices withheld, from entering a grouping).
_MAX_LIVE_OUTCOME_AGE_DAYS = 30
_TITLE_FOUR_DIGIT_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _parse_iso_dt_utc(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
    text = str(raw).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _finite_volume_number(raw: Any) -> Optional[float]:
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return None
    val = float(raw)
    return val if math.isfinite(val) else None


def _effective_market_volume(
    volume: Any,
    *,
    volume_24h: Any = None,
    market_metadata: Any = None,
) -> Optional[float]:
    """Resolve effective market volume when lifetime ``volume`` is missing (#336-A, Item 4).

    Uses lifetime ``volume`` when present (preserving an explicit ``0`` so a
    measured zero-volume market still fails). When lifetime ``volume`` is missing,
    tries the recorded lifetime figure (``market_metadata.volume_evidence.gamma_volume``
    when ``verdict == "traded"``) BEFORE falling back to ``volume_24h``. A market
    with neither returns ``None`` so ``missing_volume`` still fails it.
    """
    primary = _finite_volume_number(volume)
    if primary is not None:
        return primary
    if isinstance(market_metadata, Mapping):
        ve = market_metadata.get("volume_evidence")
        if isinstance(ve, Mapping) and str(ve.get("verdict") or "").strip().lower() == "traded":
            gv = _finite_volume_number(ve.get("gamma_volume"))
            if gv is not None:
                return gv
    v24 = _finite_volume_number(volume_24h)
    if v24 is not None:
        return v24
    return None


def _market_matches_query(
    market: Mapping[str, Any],
    query: Mapping[str, Any],
    *,
    now_dt: Optional[datetime] = None,
) -> bool:
    status = str(market.get("status") or "open").lower()
    if status not in {"open", "active"}:
        return False
    if market.get("is_settled") or market.get("settled_winner"):
        return False
    title_low = str(market.get("name") or "").lower()
    if not title_low:
        return False

    if now_dt is not None:
        for date_key in ("resolution_date", "event_date"):
            dt_val = _parse_iso_dt_utc(market.get(date_key))
            if dt_val is not None and dt_val < now_dt:
                return False
        max_horizon = query.get("max_horizon_years")
        if isinstance(max_horizon, (int, float)) and not isinstance(max_horizon, bool):
            max_year = now_dt.year + int(max_horizon)
            res_dt = _parse_iso_dt_utc(market.get("resolution_date"))
            if res_dt is not None and res_dt.year > max_year:
                return False
            title_years = [int(y) for y in _TITLE_FOUR_DIGIT_YEAR_RE.findall(title_low)]
            if title_years and max(title_years) > max_year:
                return False

    fun_sub_tag = str(query.get("fun_sub_tag") or "").strip()
    if fun_sub_tag:
        from app.utils.discover_fun_tags import (
            check_fun_real_trading,
            check_fun_taste_guard,
            fun_market_ids_for_sub_tag,
        )

        allowed_fun_ids = fun_market_ids_for_sub_tag(fun_sub_tag)
        mid_val = market.get("id")
        if not isinstance(mid_val, int) or mid_val not in allowed_fun_ids:
            return False
        taste_ok, _ = check_fun_taste_guard(
            str(market.get("name") or market.get("title") or ""),
            market.get("description"),
        )
        if not taste_ok:
            return False
        eff_vol = _effective_market_volume(
            market.get("volume"),
            volume_24h=market.get("volume_24h"),
            market_metadata=market.get("market_metadata"),
        )
        raw_min_vol = query.get("min_lifetime_volume")
        min_vol_override = (
            int(raw_min_vol)
            if isinstance(raw_min_vol, (int, float)) and not isinstance(raw_min_vol, bool)
            else None
        )
        trading_ok, _ = check_fun_real_trading(
            eff_vol, min_lifetime_volume=min_vol_override
        )
        if not trading_ok:
            return False
    else:
        raw_min_vol = query.get("min_lifetime_volume")
        if isinstance(raw_min_vol, (int, float)) and not isinstance(raw_min_vol, bool):
            eff_vol = _effective_market_volume(
                market.get("volume"),
                volume_24h=market.get("volume_24h"),
                market_metadata=market.get("market_metadata"),
            )
            if eff_vol is None or eff_vol < float(raw_min_vol):
                return False

    req_tokens = [str(t).lower() for t in (query.get("title_all_tokens") or ()) if str(t).strip()]
    if any(tok not in title_low for tok in req_tokens):
        return False

    any_tokens = [str(t).lower() for t in (query.get("any_tokens") or ()) if str(t).strip()]
    if any_tokens and not any(tok in title_low for tok in any_tokens):
        return False

    excl_tokens = [str(t).lower() for t in (query.get("exclude_tokens") or ()) if str(t).strip()]
    explicitly_womens = any("women" in tok for tok in req_tokens + any_tokens)
    if not explicitly_womens:
        if "wnba" in excl_tokens:
            excl_tokens.extend(["women's pro basketball", "womens pro basketball", "women\u2019s pro basketball"])
        if "lpga" in excl_tokens:
            excl_tokens.extend(["women's pro golf", "womens pro golf", "women\u2019s pro golf"])
        if "nwsl" in excl_tokens:
            excl_tokens.extend(["women's pro soccer", "womens pro soccer", "women\u2019s pro soccer"])
    if any(tok in title_low for tok in excl_tokens):
        return False

    # Never fall back from an explicitly empty screened `top_outcomes` list to raw DB `outcomes`.
    if "top_outcomes" in market and isinstance(market["top_outcomes"], (list, tuple)):
        raw_outcomes = market["top_outcomes"]
    else:
        raw_outcomes = market.get("outcomes") or ()
    priced = [
        o
        for o in raw_outcomes
        if isinstance(o, Mapping)
        and not o.get("price_withheld")
        and not o.get("withheld_reason")
        and isinstance(o.get("probability"), (int, float))
        and not isinstance(o.get("probability"), bool)
        and 0.0 < float(o["probability"]) < 1.0
        and not _PLACEHOLDER_OUTCOME_RE.match(str(o.get("name") or "").strip())
    ]
    if not priced:
        return False

    if now_dt is not None:
        obs_stamps = [
            dt
            for dt in (
                _parse_iso_dt_utc(o.get("last_updated") or o.get("observed_at"))
                for o in priced
            )
            if dt is not None
        ]
        if not obs_stamps:
            mkt_obs = _parse_iso_dt_utc(market.get("newest_outcome_updated_at"))
            if mkt_obs is not None:
                obs_stamps.append(mkt_obs)
        if obs_stamps and (now_dt - max(obs_stamps)) > timedelta(days=_MAX_LIVE_OUTCOME_AGE_DAYS):
            return False

    shape = str(query.get("shape") or "any").lower()
    if shape == "two_way" and len(priced) != 2:
        return False
    if shape == "field" and len(priced) < 3:
        return False
    if shape == "field" and not query.get("allow_cumulative"):
        cum_hits = sum(
            1
            for o in priced
            if _CUMULATIVE_OUTCOME_RE.match(str(o.get("name") or "").strip())
        )
        if cum_hits >= 2:
            return False
    if shape == "binary" and len(priced) > 2:
        names = {str(o.get("name") or "").strip().lower() for o in priced}
        if not ("yes" in names or len(priced) == 1):
            return False
    if shape == "binary":
        names = {str(o.get("name") or "").strip().lower() for o in priced}
        if "yes" not in names and len(priced) != 1:
            return False

    max_lead_prob = query.get("max_lead_probability")
    if isinstance(max_lead_prob, (int, float)) and not isinstance(max_lead_prob, bool):
        max_lp = float(max_lead_prob)
        max_pct = int(round(max_lp * 100))
        canonical_rows, _, _ = _canonical_market_outcome_map(
            raw_outcomes,
            mutually_exclusive=bool(market.get("mutually_exclusive", True)),
            question=str(market.get("name") or ""),
        )
        non_floor = [o for o in canonical_rows if 0.005 <= float(o["probability"]) <= 0.995]
        min_needed = 2 if len(canonical_rows) == 2 else 1
        valid_rows = non_floor if len(non_floor) >= min_needed else list(canonical_rows)
        if not valid_rows:
            return False
        is_yes_shape = len(valid_rows) <= 2 and any(
            str(o.get("name") or "").strip().lower() == "yes" for o in valid_rows
        )
        if is_yes_shape:
            lead_row = next(
                (o for o in valid_rows if str(o.get("name") or "").strip().lower() == "yes"),
                valid_rows[0],
            )
        else:
            lead_row = max(valid_rows, key=lambda o: float(o["probability"]))
        lead_p = float(lead_row["probability"])
        lead_pct = int(lead_row.get("rendered_percent") or _half_up_pct(lead_p))
        if lead_p > max_lp or lead_pct > max_pct:
            return False

    return True


def _legacy_grouped_percent(probability: float, allocated: int) -> int:
    """Keep the integer printed directly by existing iPhone builds."""
    return max(1, min(99, allocated)) if 0.0 < probability < 1.0 else allocated


def _canonical_market_outcome_map(
    raw_outcomes: Sequence[Mapping[str, Any]],
    *,
    mutually_exclusive: bool = True,
    question: str | None = None,
) -> tuple[list[dict[str, Any]], dict[int, int], dict[str, int]]:
    """Compute canonical member-page probabilities and whole percents for a market's outcomes
    using the same ``normalize_display_probs`` + ``rendered_card_percents`` rules as ``/futures/{id}``.
    """
    from app.utils.outcome_display import is_placeholder_outcome_name, normalize_display_probs

    rows: list[dict[str, Any]] = []
    already_has_rendered = False
    for idx, o in enumerate(raw_outcomes):
        if not isinstance(o, Mapping):
            continue
        name = str(o.get("name") or o.get("outcome_name") or "").strip()
        if not name or is_placeholder_outcome_name(name) or _PLACEHOLDER_OUTCOME_RE.match(name):
            continue
        prob = o.get("probability")
        if not isinstance(prob, (int, float)) or not math.isfinite(float(prob)):
            continue
        p = float(prob)
        if p <= 0.0 or p >= 1.0:
            continue
        oid = int(o.get("id") or o.get("outcome_id") or (idx + 1))
        rp = o.get("rendered_percent")
        if isinstance(rp, int) and not isinstance(rp, bool):
            already_has_rendered = True
        rows.append(
            {
                **dict(o),
                "id": oid,
                "name": name,
                "probability": p,
                "rendered_percent": int(rp) if isinstance(rp, int) and not isinstance(rp, bool) else None,
            }
        )

    raw_sum = sum(float(r["probability"]) for r in rows)
    if rows and not already_has_rendered and mutually_exclusive and raw_sum > 1.005:
        normalize_display_probs(
            rows,
            key="probability",
            mutually_exclusive=True,
            field_complete=True,
            question=question,
        )

    card_pcts = rendered_card_percents([r.get("probability") for r in rows])
    by_oid: dict[int, int] = {}
    by_key: dict[str, int] = {}
    for idx, r in enumerate(rows):
        rp = r.get("rendered_percent")
        if rp is None and idx < len(card_pcts) and card_pcts[idx] is not None:
            rp = int(card_pcts[idx])
        if rp is None:
            rp = _half_up_pct(float(r["probability"]))
        unfloored = r.get("unfloored_percent")
        if not isinstance(unfloored, int) or isinstance(unfloored, bool):
            unfloored = int(rp)
        pct_int = _legacy_grouped_percent(float(r["probability"]), int(rp))
        r["unfloored_percent"] = unfloored
        r["rendered_percent"] = pct_int
        by_oid[int(r["id"])] = pct_int
        nk = _norm_key(_clean_outcome_label(str(r["name"])))
        if nk and nk not in by_key:
            by_key[nk] = pct_int
        raw_nk = _norm_key(str(r["name"]))
        if raw_nk and raw_nk not in by_key:
            by_key[raw_nk] = pct_int
    return rows, by_oid, by_key


_MONTH_ABBREV_MAP: dict[str, str] = {
    "january": "Jan",
    "february": "Feb",
    "march": "Mar",
    "april": "Apr",
    "may": "May",
    "june": "June",
    "july": "July",
    "august": "Aug",
    "september": "Sep",
    "october": "Oct",
    "november": "Nov",
    "december": "Dec",
}
_FULL_MONTH_RE = re.compile(
    r"\b(January|February|March|April|August|September|October|November|December)\b",
    re.IGNORECASE,
)
_MONTH_TOKEN_PATTERN = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_PREP_DATE_OUTCOME_RE = re.compile(r"^(before|by|after)\s+(.+)$", re.IGNORECASE)
_AFTER_DATE_OUTCOME_RE = re.compile(r"^after\s+", re.IGNORECASE)
_BARE_MONTH_DAY_RE = re.compile(
    rf"^{_MONTH_TOKEN_PATTERN}\s+\d{{1,2}}(?:,\s*\d{{4}})?$",
    re.IGNORECASE,
)
_BARE_MONTH_YEAR_OR_YEAR_RE = re.compile(
    rf"^(?:{_MONTH_TOKEN_PATTERN}\s+20\d{{2}}|20\d{{2}})$",
    re.IGNORECASE,
)
_RANK_RANGE_OUTCOME_RE = re.compile(r"^Rank\s+(\d+)\s+to\s+(\d+)$", re.IGNORECASE)


def _format_rank_range_phrase(lead_ans: str) -> tuple[Optional[str], Optional[str]]:
    """Turn a bucketed chart-rank answer like ``Rank 1 to 2`` into readable copy.

    Returns ``(bare_phrase, with_article_phrase)`` — e.g. ``("top 2", "the top 2")``
    when the range begins at 1, or ``("spots 3 to 4", "spots 3 to 4")`` otherwise.
    Non-range answers (such as ``Rank 11 or lower`` or ``Not on chart``) return
    ``(None, None)`` so callers fall back to the plain row and plain headline form.
    """
    ans = lead_ans.strip().rstrip("?").strip()
    m = _RANK_RANGE_OUTCOME_RE.match(ans)
    if m:
        start = int(m.group(1))
        end = int(m.group(2))
        if start == 1:
            return f"top {end}", f"the top {end}"
        return f"spots {start} to {end}", f"spots {start} to {end}"
    return None, None


def _abbreviate_month_names(text: str) -> str:
    return _FULL_MONTH_RE.sub(
        lambda m: _MONTH_ABBREV_MAP.get(m.group(1).lower(), m.group(1)),
        text,
    )


def _format_fun_lead_answer_label(
    base_title: str,
    lead_ans: str,
    *,
    fallback_base_title: Optional[str] = None,
) -> tuple[str, bool]:
    """Format a non-Yes/No fun market's leading answer onto its short label.

    Returns ``(display_title, is_date_timing_row)``.
    - Templates containing ``{rank_slot}`` / ``{the_rank_slot}`` render e.g.
      ``top 2`` / ``the top 2`` (or ``spots 3 to 4``) inline without appending ``: ...``.
      When ``lead_ans`` is not a ``Rank N to M`` range, they fall back to
      ``fallback_base_title`` (plain ``<base>: <answer>`` formatting).
    - Bare month+day answers (e.g. ``December 31``, ``March 31, 2027``) read
      ``"<base> by Dec 31"`` / ``"<base> by Mar 31, 2027"`` (Fable Nov 20 look).
    - Bare month+year or year answers (e.g. ``March 2027``, ``2027``) read
      ``"<base> in Mar 2027"`` / ``"<base> in 2027"``.
    - ``Before ...`` / ``By ...`` / ``After ...`` read ``"<base> before ..."``
      with abbreviated month names and no awkward colon.
    - Non-date answers (e.g. ``United States``) keep ``"<base>: United States"``
      with ``is_date_timing_row = False``.
    """
    ans = lead_ans.strip().rstrip("?").strip()
    if "{rank_slot}" in base_title or "{the_rank_slot}" in base_title:
        rank_slot, the_rank_slot = _format_rank_range_phrase(ans)
        if rank_slot and the_rank_slot:
            return (
                base_title.replace("{rank_slot}", rank_slot)
                .replace("{the_rank_slot}", the_rank_slot)
                .strip(),
                False,
            )
        plain = (fallback_base_title or "").strip()
        if plain and "{rank_slot}" not in plain and "{the_rank_slot}" not in plain:
            base_title = plain
        else:
            base_title = (
                base_title.replace("{rank_slot}", "").replace("{the_rank_slot}", "").strip()
            )
    if not ans or ans.lower() in {"yes", "no"}:
        return base_title, False
    m_prep = _PREP_DATE_OUTCOME_RE.match(ans)
    if m_prep:
        prep = m_prep.group(1).lower()
        rest = _abbreviate_month_names(m_prep.group(2).strip())
        if rest.lower() in base_title.lower():
            return base_title, True
        return f"{base_title} {prep} {rest}", True
    if _BARE_MONTH_DAY_RE.match(ans):
        short_date = _abbreviate_month_names(ans)
        return f"{base_title} by {short_date}", True
    if _BARE_MONTH_YEAR_OR_YEAR_RE.match(ans):
        short_date = _abbreviate_month_names(ans)
        return f"{base_title} in {short_date}", True
    if ans.lower() in base_title.lower():
        return base_title, False
    return f"{base_title}: {ans}", False


def _parse_outcome_deadline_date(name: str) -> Optional[date]:
    """Parse cumulative date-ladder outcome labels (``Before Jan 1, 2027``, ``Dec 31, 2026``, ``Before 2028``)."""
    raw = name.strip().rstrip("?").strip()
    m_prep = _PREP_DATE_OUTCOME_RE.match(raw)
    if m_prep:
        if m_prep.group(1).lower() == "after":
            return None
        raw = m_prep.group(2).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %Y", "%b %Y", "%Y"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return date(parsed.year, parsed.month if "%b" in fmt or "%B" in fmt else 1, parsed.day if "%d" in fmt else 1)
        except ValueError:
            continue
    return None


def _pick_nearest_open_date_ladder_outcome(
    outcomes: Sequence[Mapping[str, Any]],
    *,
    ref_date: date,
) -> Optional[Mapping[str, Any]]:
    """Select the earliest future tradeable deadline rung from a cumulative date ladder."""
    dated: list[tuple[date, float, Mapping[str, Any]]] = []
    for o in outcomes:
        deadline = _parse_outcome_deadline_date(str(o.get("name") or ""))
        if deadline is not None:
            dated.append((deadline, float(o.get("probability") or 0.0), o))
    if len(dated) < 2:
        return None
    future = [item for item in dated if item[0] >= ref_date]
    if not future:
        return None
    future.sort(key=lambda item: (item[0], -item[1]))
    return future[0][2]


def _hydrate_market_visual_item(
    market: Mapping[str, Any],
    *,
    max_outcomes: int,
    resolver: SubjectArtResolver,
    content_kind: Optional[str] = None,
    use_fun_short_label: bool = False,
    fun_sub_tag: Optional[str] = None,
    sport_key: Optional[str] = None,
    allow_team_lookup: Optional[bool] = None,
    now_dt: Optional[datetime] = None,
    date_ladder_pick: Optional[str] = None,
) -> dict[str, Any]:
    mid = int(market["id"])
    if "top_outcomes" in market and isinstance(market["top_outcomes"], (list, tuple)):
        raw_outcomes = market["top_outcomes"]
    else:
        raw_outcomes = market.get("outcomes") or ()
    mut_excl = bool(market.get("mutually_exclusive", True))
    canonical_rows, canon_by_oid, canon_by_key = _canonical_market_outcome_map(
        raw_outcomes,
        mutually_exclusive=mut_excl,
        question=str(market.get("name") or ""),
    )
    # Drop sub-0.5% / >99.5% floor-tick noise when tradeable rows exist so web/iPhone
    # integer % never disagrees with '<1%' / '>99%' boundary formatting on /futures/{id}.
    non_floor = [
        o for o in canonical_rows if 0.005 <= float(o["probability"]) <= 0.995
    ]
    min_needed = 2 if len(canonical_rows) == 2 else 1
    valid = non_floor if len(non_floor) >= min_needed else list(canonical_rows)
    valid.sort(key=lambda o: (-float(o["probability"]), str(o.get("name") or "").casefold()))

    shape_is_yes = (
        len(valid) <= 2
        and any(str(o.get("name") or "").strip().lower() == "yes" for o in valid)
    )
    scale_ordered = False
    leader_outcome_id: Optional[int] = None
    lead_prob = 0.0

    if shape_is_yes:
        yes_row = next(
            (o for o in valid if str(o.get("name") or "").strip().lower() == "yes"),
            valid[0],
        )
        p = float(yes_row["probability"])
        oid = int(yes_row.get("id") or (mid * 10 + 1))
        yes_pct = int(yes_row.get("rendered_percent") or _half_up_pct(p))
        leader_outcome_id = oid
        lead_prob = p
        outcomes_out = [
            {
                "outcome_id": oid,
                "name": "Yes",
                "probability": p,
                "rendered_percent": yes_pct,
                "unfloored_percent": yes_row.get("unfloored_percent"),
                "art": {"url": None, "kind": "monogram", "detail": ""},
            }
        ]
    else:
        ordered_valid = list(valid)
        # Fable Nov 20 preview look (Item 5i): on single-number fun strips, an
        # "After <Date>" delay bucket (e.g. "GTA VI on PC: After March 2027 at 67%")
        # reads as likely to arrive when it means the opposite. Prefer the leading
        # non-"After" release-window outcome so the row ranks by actual arrival odds
        # while keeping 100% member-page parity on its real outcome_id.
        if (
            use_fun_short_label
            and max_outcomes == 1
            and date_ladder_pick == "nearest_open"
            and ordered_valid
        ):
            ref_d = (now_dt or datetime.now(timezone.utc)).date()
            nearest = _pick_nearest_open_date_ladder_outcome(ordered_valid, ref_date=ref_d)
            if nearest is not None:
                ordered_valid = [nearest] + [o for o in ordered_valid if o is not nearest]
        elif (
            use_fun_short_label
            and max_outcomes == 1
            and ordered_valid
            and _AFTER_DATE_OUTCOME_RE.match(str(ordered_valid[0].get("name") or "").strip())
        ):
            non_after = [
                o
                for o in ordered_valid
                if not _AFTER_DATE_OUTCOME_RE.match(str(o.get("name") or "").strip())
            ]
            if non_after:
                ordered_valid = non_after
        kept = ordered_valid[:max_outcomes]
        from app.utils.field_opening_coherence import field_openings_publishable

        openings_ok = field_openings_publishable(
            [o.get("opening_probability") for o in valid],
            mutually_exclusive=bool(market.get("mutually_exclusive", True)),
        )
        outcomes_out = []
        eff_sport_key = (
            sport_key
            if sport_key is not None
            else _infer_sports_key_for_market(market)
        )
        eff_allow_team_lookup = (
            bool(allow_team_lookup)
            if allow_team_lookup is not None
            else _is_sports_context(market)
        )
        for idx, o in enumerate(kept):
            o_name = _clean_outcome_label(str(o.get("name") or "").strip())
            p = float(o["probability"])
            oid = int(o.get("id") or (mid * 100 + idx + 1))
            if idx == 0:
                leader_outcome_id = oid
                lead_prob = p
            art = resolver.resolve(
                o_name,
                explicit_url=(str(o["image_url"]) if o.get("image_url") else None),
                sport_key=eff_sport_key,
                allow_team_lookup=eff_allow_team_lookup,
            )
            if not art.get("url") and max_outcomes == 1 and fun_sub_tag:
                from app.utils.discover_fun_tags import fun_market_art_subject

                art_subj = fun_market_art_subject(mid, sub_tag=fun_sub_tag)
                if art_subj:
                    resolved_tag_art = resolver.resolve(
                        art_subj,
                        sport_key=eff_sport_key,
                        allow_team_lookup=eff_allow_team_lookup,
                    )
                    if resolved_tag_art.get("url"):
                        art = resolved_tag_art
            canon_subj = art.get("canonical_name")
            if canon_subj and _ascii_fold_key(canon_subj) == _ascii_fold_key(o_name):
                o_name = str(canon_subj)
            rendered = o.get("rendered_percent")
            pct_val = int(rendered) if rendered is not None else _half_up_pct(p)
            for fk_alias in (_norm_key(o_name), _ascii_fold_key(o_name)):
                if fk_alias and fk_alias not in canon_by_key:
                    canon_by_key[fk_alias] = pct_val
            outcomes_out.append(
                {
                    "outcome_id": oid,
                    "name": o_name,
                    "probability": p,
                    "rendered_percent": pct_val,
                    "unfloored_percent": o.get("unfloored_percent"),
                    "opening_probability": (
                        o.get("opening_probability") if openings_ok else None
                    ),
                    "art": art,
                }
            )
        # Direction 228 (#12885): numerical-scale markets run ascending by value, never by probability.
        scale_idx = numerical_scale_order_indices(outcomes_out)
        if scale_idx is not None:
            outcomes_out = [outcomes_out[i] for i in scale_idx]
            scale_ordered = True

    effective_kind = content_kind or (
        "props" if _PROP_MARKET_TITLE_RE.search(str(market.get("name") or "")) else "futures"
    )
    explicit_mpn = market.get("member_page_numbers")
    if isinstance(explicit_mpn, Mapping):
        mpn = {
            "by_outcome_id": {int(k): int(v) for k, v in (explicit_mpn.get("by_outcome_id") or {}).items()},
            "by_outcome_key": {str(k): int(v) for k, v in (explicit_mpn.get("by_outcome_key") or {}).items()},
        }
    else:
        mpn = {
            "by_outcome_id": canon_by_oid,
            "by_outcome_key": canon_by_key,
        }
    from app.services.paired_metric_register import clean_card_face_title
    from app.utils.market_display_name import fill_market_display_name_blank

    lead_out_name = str(outcomes_out[0].get("name") or "") if outcomes_out else None
    clean_raw_name = (
        fill_market_display_name_blank(
            clean_card_face_title(str(market.get("name") or "")),
            lead_outcome_name=lead_out_name,
            outcome_count=len(outcomes_out),
        )
        or ""
    )
    card_copy = {k: v for k, v in market.items() if k != "market_metadata"}
    card_copy["name"] = clean_raw_name
    card_copy["content_kind"] = effective_kind
    card_copy["member_page_numbers"] = mpn

    base_title: Optional[str] = None
    plain_base_title: Optional[str] = None
    if use_fun_short_label:
        from app.utils.discover_fun_tags import (
            fun_market_plain_short_label,
            fun_market_short_label,
        )

        base_title = fun_market_short_label(mid, sub_tag=fun_sub_tag)
        plain_base_title = fun_market_plain_short_label(mid, sub_tag=fun_sub_tag)
    fallback_clean_title = clean_card_face_title(_clean_section_market_label(clean_raw_name))
    if not base_title:
        base_title = fallback_clean_title
    if not plain_base_title:
        plain_base_title = fallback_clean_title

    display_title = base_title
    is_date_timing_row = False
    # On single-number fun strips (`fun_sub_tag` + `max_outcomes == 1`), a
    # non-Yes/No ("when"/"which") market's row and headline must name its
    # leading answer cleanly alongside the number (Item 5 / #13224).
    if use_fun_short_label and max_outcomes == 1 and not shape_is_yes and outcomes_out:
        lead_ans = str(outcomes_out[0].get("name") or "").strip()
        display_title, is_date_timing_row = _format_fun_lead_answer_label(
            display_title, lead_ans, fallback_base_title=plain_base_title
        )
        if is_date_timing_row:
            out0_art = outcomes_out[0].get("art")
            if isinstance(out0_art, dict) and not out0_art.get("url"):
                date_subj = str(plain_base_title or display_title or clean_raw_name or f"Market {mid}")
                out0_art["initials"] = _initials(date_subj)
                out0_art["accent_color"] = _fallback_color(date_subj)

    if shape_is_yes and outcomes_out:
        subj_for_fallback = str(display_title or clean_raw_name or f"Market {mid}")
        yes_art: dict[str, Any] = {
            "url": None,
            "kind": "monogram",
            "detail": "",
            "accent_color": _fallback_color(subj_for_fallback),
            "initials": _initials(subj_for_fallback),
        }
        allow_tl = bool(allow_team_lookup) if allow_team_lookup is not None else None
        if fun_sub_tag:
            from app.utils.discover_fun_tags import fun_market_art_subject

            art_subj = fun_market_art_subject(mid, sub_tag=fun_sub_tag)
            if art_subj:
                resolved_tag_art = resolver.resolve(
                    art_subj,
                    sport_key=sport_key,
                    allow_team_lookup=allow_tl,
                )
                if resolved_tag_art.get("url"):
                    yes_art = resolved_tag_art
        if not yes_art.get("url"):
            probe_candidates: list[str] = []
            for cand_raw in (
                display_title,
                display_title.split(" & ", 1)[0] if " & " in display_title else None,
                display_title.split(" & ", 1)[1] if " & " in display_title else None,
                display_title.split(" and ", 1)[0] if " and " in display_title else None,
                display_title.split(" and ", 1)[1] if " and " in display_title else None,
            ):
                cand = str(cand_raw or "").strip()
                if cand and cand not in probe_candidates:
                    probe_candidates.append(cand)
            for cand in probe_candidates:
                probed = resolver.resolve(
                    cand,
                    sport_key=sport_key,
                    allow_team_lookup=allow_tl,
                )
                if probed.get("url"):
                    yes_art = probed
                    break
        outcomes_out[0]["art"] = yes_art

    # Portrait/subject gate (#13587): never serve a person's face on another subject's row.
    if outcomes_out:
        art_context_texts = (display_title, clean_raw_name)
        for oc in outcomes_out:
            oc["art"] = _gate_outcome_art(
                str(oc.get("name") or ""),
                art_context_texts,
                oc.get("art") or {},
                resolver=resolver,
                fallback_subject=(
                    str(display_title or clean_raw_name or f"Market {mid}")
                    if shape_is_yes
                    else str(oc.get("name") or display_title or clean_raw_name or f"Market {mid}")
                ),
            )

    headline_phrase: Optional[str] = None
    headline_with_phrase: Optional[str] = None
    if fun_sub_tag:
        from app.utils.discover_fun_tags import (
            fun_market_headline_phrase,
            fun_market_headline_with_phrase,
        )

        lead_ans_clean = (
            str(outcomes_out[0].get("name") or "").strip().rstrip("?").strip()
            if outcomes_out
            else ""
        )
        m_prep_ans = _PREP_DATE_OUTCOME_RE.match(lead_ans_clean)
        if m_prep_ans:
            lead_ans_for_phrase = f"{m_prep_ans.group(1).lower()} {_abbreviate_month_names(m_prep_ans.group(2).strip())}"
        elif _BARE_MONTH_DAY_RE.match(lead_ans_clean):
            lead_ans_for_phrase = f"by {_abbreviate_month_names(lead_ans_clean)}"
        elif _BARE_MONTH_YEAR_OR_YEAR_RE.match(lead_ans_clean):
            lead_ans_for_phrase = f"in {_abbreviate_month_names(lead_ans_clean)}"
        elif lead_ans_clean.startswith("<$"):
            lead_ans_for_phrase = f"below {lead_ans_clean[1:].strip()}"
        elif lead_ans_clean.startswith(">$"):
            lead_ans_for_phrase = f"above {lead_ans_clean[1:].strip()}"
        else:
            if lead_ans_clean.strip().lower() in _MONTH_FULL_MAP:
                lead_ans_for_phrase = _expand_month_token(lead_ans_clean)
            else:
                lead_ans_for_phrase = _abbreviate_month_names(lead_ans_clean)
        _THE_COUNTRIES = frozenset(
            {
                "united states",
                "u.s.",
                "us",
                "united kingdom",
                "uk",
                "netherlands",
                "philippines",
                "uae",
                "united arab emirates",
            }
        )
        ans_with_the = (
            f"the {lead_ans_for_phrase}"
            if lead_ans_for_phrase.lower() in _THE_COUNTRIES
            else lead_ans_for_phrase
        )
        ans_cap_the = (
            f"The {lead_ans_for_phrase}"
            if lead_ans_for_phrase.lower() in _THE_COUNTRIES
            else lead_ans_for_phrase
        )

        def _render_tpl(tpl: str) -> Optional[str]:
            if any(tok in tpl for tok in ("{answer}", "{lower_answer}", "{the_answer}", "{cap_the_answer}", "{rank_slot}", "{the_rank_slot}")):
                if not lead_ans_clean or lead_ans_clean.lower() in {"yes", "no"}:
                    return None
                needs_rank_slot = "{rank_slot}" in tpl or "{the_rank_slot}" in tpl
                rank_slot, the_rank_slot = _format_rank_range_phrase(lead_ans_clean)
                if needs_rank_slot and (not rank_slot or not the_rank_slot):
                    return None
                return (
                    tpl.replace("{answer}", lead_ans_for_phrase)
                    .replace("{lower_answer}", lead_ans_for_phrase.lower())
                    .replace("{the_answer}", ans_with_the)
                    .replace("{cap_the_answer}", ans_cap_the)
                    .replace("{rank_slot}", rank_slot or "")
                    .replace("{the_rank_slot}", the_rank_slot or "")
                    .rstrip("?")
                    .strip()
                )
            return tpl.rstrip("?").strip()

        raw_phrase = str(fun_market_headline_phrase(mid, sub_tag=fun_sub_tag) or "").strip()
        if raw_phrase:
            headline_phrase = _render_tpl(raw_phrase)
        raw_with_phrase = str(
            fun_market_headline_with_phrase(mid, sub_tag=fun_sub_tag) or ""
        ).strip()
        if raw_with_phrase:
            headline_with_phrase = _render_tpl(raw_with_phrase)

    return {
        "market_id": mid,
        "title": display_title,
        "headline_phrase": headline_phrase,
        "headline_with_phrase": headline_with_phrase,
        "raw_title": clean_raw_name,
        "is_date_timing_row": is_date_timing_row,
        "href": f"/futures/{mid}",
        "source": str(market.get("source") or ""),
        "lead_prob": lead_prob,
        "leader_outcome_id": leader_outcome_id,
        "scale_ordered": scale_ordered,
        "content_kind": effective_kind,
        "closeness_to_50": abs(lead_prob - 0.5),
        "_volume": float(
            _effective_market_volume(
                market.get("volume"),
                volume_24h=market.get("volume_24h"),
                market_metadata=market.get("market_metadata"),
            )
            or 0.0
        ),
        "outcomes": outcomes_out,
        "member_page_numbers": mpn,
        "card": card_copy,
    }


def _event_has_sportsbook(event: Any, *, hero_source: Optional[str] = None) -> bool:
    """True when sportsbooks actually stand behind the event's hero chance (#9081, #12288).

    Uses ``hero_sportsbook_count(event) > 0`` so games with 1–2 books below
    ``BETTING_BOOK_FLOOR`` (whose ``betting`` reading is omitted from the blend)
    are NOT counted as sportsbook-backed and cannot outrank true multi-book
    games on sports slates (e.g. NBA).
    """
    from types import SimpleNamespace

    from app.utils.hero_probability import hero_sportsbook_count

    if isinstance(event, Mapping):
        if event.get("has_sportsbook") is True:
            return True
        if event.get("has_sportsbook") is False:
            return False
        wps = event.get("win_probability_sources")
        h_src = hero_source or event.get("hero_source")
        if str(h_src or "").strip().lower() == "betting":
            return True
        if isinstance(wps, Mapping):
            ev_ns = SimpleNamespace(
                win_probability_sources=dict(wps),
                status=event.get("status"),
                sport=event.get("sport"),
                commence_time=event.get("commence_time"),
            )
            sb_cnt = hero_sportsbook_count(ev_ns)
            if sb_cnt is not None:
                return sb_cnt > 0
            # `hero_sportsbook_count` returns None only when `"betting"` IS in
            # `effective_source_weights` without an explicit integer count.
            betting_entry = wps.get("betting")
            if isinstance(betting_entry, Mapping):
                return any(
                    isinstance(betting_entry.get(k), (int, float))
                    for k in ("home", "away", "home_probability", "away_probability", "probability")
                )
            return isinstance(betting_entry, (int, float)) and not isinstance(betting_entry, bool)
        bk = event.get("bookmaker_count")
        if isinstance(bk, (int, float)) and not isinstance(bk, bool) and bk >= 3:
            return True
        odds = event.get("current_odds")
        if isinstance(odds, Mapping):
            obk = odds.get("bookmaker_count")
            if isinstance(obk, (int, float)) and not isinstance(obk, bool) and obk >= 3:
                return True
        return False

    sb_cnt = hero_sportsbook_count(event)
    return bool(sb_cnt is not None and sb_cnt > 0)


def _hydrate_event_visual_item(
    event: Mapping[str, Any],
    *,
    resolver: SubjectArtResolver,
) -> Optional[dict[str, Any]]:
    eid = int(event["id"])
    status = str(event.get("status") or "scheduled").lower()
    if status in {"cancelled", "postponed"}:
        return None
    odds = event.get("current_odds") if isinstance(event.get("current_odds"), Mapping) else {}
    hero_source = str(event.get("hero_probability_source") or event.get("hero_source") or "").strip().lower()
    if status in {"completed", "final", "closed"} and hero_source == "final_unresolved":
        # #13172 Option B: finished with no verified result never serves the last live price.
        return None
    home_p = event.get("hero_probability")
    away_p = event.get("hero_probability_away")
    draw_p = event.get("hero_probability_draw")
    if home_p is None:
        home_p = odds.get("home_probability")
    if away_p is None:
        away_p = odds.get("away_probability")
    if draw_p is None:
        draw_p = odds.get("draw_probability")

    pre = event.get("prematch_odds") if isinstance(event.get("prematch_odds"), Mapping) else {}
    if (
        status in {"completed", "final", "closed"}
        and hero_source == "settled"
        and (home_p is None or away_p is None)
    ):
        home_p = pre.get("home_probability")
        away_p = pre.get("away_probability")

    if not isinstance(home_p, (int, float)) or not isinstance(away_p, (int, float)):
        return None
    hp = float(home_p)
    ap = float(away_p)
    dp = float(draw_p) if isinstance(draw_p, (int, float)) else None
    if hp <= 0.0 and ap <= 0.0 and not (dp is not None and dp > 0.0):
        return None

    home_team = str(event.get("home_team") or "").strip()
    away_team = str(event.get("away_team") or "").strip()
    home_td = event.get("home_team_data") if isinstance(event.get("home_team_data"), Mapping) else {}
    away_td = event.get("away_team_data") if isinstance(event.get("away_team_data"), Mapping) else {}

    home_art = resolver.resolve(
        home_team,
        explicit_url=home_td.get("logo_small") or home_td.get("logo_large") or event.get("home_image_url"),
        explicit_color=home_td.get("primary_color"),
        sport_key=str(event.get("sport") or "").strip().lower() or None,
        allow_team_lookup=True,
    )
    away_art = resolver.resolve(
        away_team,
        explicit_url=away_td.get("logo_small") or away_td.get("logo_large") or event.get("away_image_url"),
        explicit_color=away_td.get("primary_color"),
        sport_key=str(event.get("sport") or "").strip().lower() or None,
        allow_team_lookup=True,
    )

    # Ruling 253: A & Fable 8:35 PM Rule 1: print the exact pair the game's own
    # page serves (`current_odds.away_rendered_percent`, `home_rendered_percent`),
    # never a second independent rounding.
    sport_key_str = str(event.get("sport") or "").strip().lower()
    served_away_pct = odds.get("away_rendered_percent")
    served_home_pct = odds.get("home_rendered_percent")
    if isinstance(served_away_pct, int) and isinstance(served_home_pct, int):
        away_pct = int(served_away_pct)
        home_pct = int(served_home_pct)
    else:
        canonical_away_p = printable_away(ap, hp, sport_key_str)
        away_pct_raw, home_pct_raw = rendered_duel_percents(canonical_away_p, hp)
        away_pct = int(away_pct_raw) if away_pct_raw is not None else _half_up_pct(ap)
        home_pct = int(home_pct_raw) if home_pct_raw is not None else _half_up_pct(hp)

    explicit_mpn = event.get("member_page_numbers")
    if isinstance(explicit_mpn, Mapping):
        ev_mpn = {
            "away_pct": int(explicit_mpn.get("away_pct", away_pct)),
            "home_pct": int(explicit_mpn.get("home_pct", home_pct)),
        }
    else:
        ev_mpn = {"away_pct": away_pct, "home_pct": home_pct}

    card_ev = dict(event)
    card_ev["hero_probability"] = hp
    card_ev["hero_probability_away"] = ap
    if dp is not None:
        card_ev["hero_probability_draw"] = dp
    card_odds = dict(odds) if isinstance(odds, Mapping) else {}
    card_odds["home_probability"] = hp
    card_odds["away_probability"] = ap
    card_odds["away_rendered_percent"] = away_pct
    card_odds["home_rendered_percent"] = home_pct
    if dp is not None:
        card_odds["draw_probability"] = dp
        served_draw_pct = odds.get("draw_rendered_percent")
        card_odds["draw_rendered_percent"] = (
            int(served_draw_pct)
            if isinstance(served_draw_pct, int)
            else int(round(dp * 100))
        )
    card_ev["current_odds"] = card_odds
    if not isinstance(card_ev.get("home_team_data"), Mapping) and (home_art.get("url") or home_art.get("accent_color")):
        card_ev["home_team_data"] = {
            "logo_small": home_art.get("url"),
            "primary_color": home_art.get("accent_color") or None,
        }
    if not isinstance(card_ev.get("away_team_data"), Mapping) and (away_art.get("url") or away_art.get("accent_color")):
        card_ev["away_team_data"] = {
            "logo_small": away_art.get("url"),
            "primary_color": away_art.get("accent_color") or None,
        }
    card_ev["rendered_away_percent"] = away_pct
    card_ev["rendered_home_percent"] = home_pct
    card_ev["member_page_numbers"] = ev_mpn

    fav_prob = max(hp, ap)
    is_toss_up = max(away_pct, home_pct) <= int(round(TOSS_UP_MAX_SIDE_PROB * 100))
    has_sportsbook = _event_has_sportsbook(event)
    sport_str = str(event.get("sport") or "")
    if is_college_sport(sport_str):
        home_loc = home_td.get("location") if isinstance(home_td.get("location"), str) else None
        away_loc = away_td.get("location") if isinstance(away_td.get("location"), str) else None
        home_short = (school_label(home_team, home_loc) or home_team) if home_team else ""
        away_short = (school_label(away_team, away_loc) or away_team) if away_team else ""
    else:
        home_short = home_team.split()[-1] if home_team else ""
        away_short = away_team.split()[-1] if away_team else ""

    return {
        "event_id": eid,
        "href": f"/events/{eid}",
        "status": status,
        "commence_time": str(event.get("commence_time") or ""),
        "sport": sport_str,
        "home_team": home_team,
        "away_team": away_team,
        "home_short": home_short,
        "away_short": away_short,
        "home_prob": hp,
        "away_prob": ap,
        "home_pct": home_pct,
        "away_pct": away_pct,
        "home_score": event.get("home_score"),
        "away_score": event.get("away_score"),
        "home_art": home_art,
        "away_art": away_art,
        "fav_prob": fav_prob,
        "is_toss_up": is_toss_up,
        "show_toss_up_tag": is_toss_up,
        "has_sportsbook": has_sportsbook,
        "closeness_to_50": abs(hp - 0.5),
        "member_page_numbers": ev_mpn,
        "card": card_ev,
    }


def _downsample_points(points: Sequence[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    pts = list(points)
    if len(pts) <= limit:
        return pts
    step = (len(pts) - 1) / float(limit - 1)
    idxs = sorted({min(len(pts) - 1, int(round(i * step))) for i in range(limit)})
    return [pts[i] for i in idxs]


def _history_chart_moved(chart_item: Mapping[str, Any], *, min_swing_pp: int = 3) -> bool:
    """True when observed history genuinely moved by >= ``min_swing_pp`` percentage points
    and is not a ceiling-pinned 95%+ lock whose leading line sat flat (Slice 4 & Slice 5 Note 2).
    """
    if chart_item.get("moved") is False:
        return False
    series = [s for s in (chart_item.get("series") or ()) if isinstance(s, Mapping)]
    if not series:
        return False
    max_swing = 0
    lead_cur = -1
    lead_swing = 0
    for s in series:
        pcts = [
            int(pt["pct"])
            for pt in (s.get("points") or ())
            if isinstance(pt, Mapping) and isinstance(pt.get("pct"), (int, float))
        ]
        swing = (max(pcts) - min(pcts)) if len(pcts) >= 2 else 0
        max_swing = max(max_swing, swing)
        cur = int(s.get("current_pct")) if isinstance(s.get("current_pct"), (int, float)) else (pcts[-1] if pcts else 0)
        if cur > lead_cur:
            lead_cur = cur
            lead_swing = swing
    if max_swing < min_swing_pp:
        return False
    # Never treat a ceiling-pinned >=95% lock ('Hawaii Senate 95%', 'Kevin Warsh & Rate > 2.5% 99%')
    # as a moving chart unless the leading line itself moved >= min_swing_pp.
    if lead_cur >= 95 and lead_swing < min_swing_pp:
        return False
    return True


def _build_history_visual_item(
    hydrated_market: Mapping[str, Any],
    outcome_histories: Mapping[int, Sequence[Mapping[str, Any]]],
    *,
    now_dt: datetime,
    hours: int,
) -> dict[str, Any]:
    mid = int(hydrated_market["market_id"])
    outcomes = list(hydrated_market.get("outcomes") or ())
    start_default = (now_dt - timedelta(hours=max(24, hours))).isoformat()
    end_default = now_dt.isoformat()
    series_out: list[dict[str, Any]] = []
    used_colors: set[str] = set()
    earliest_iso: Optional[str] = None
    latest_iso: Optional[str] = None
    max_swing_pp = 0

    for idx, o in enumerate(outcomes[:4]):
        oid = int(o["outcome_id"])
        cur_pct = int(o["rendered_percent"])
        raw_pts = list(outcome_histories.get(oid) or ())
        pts_clean: list[dict[str, Any]] = []
        for rp in raw_pts:
            ts = str(rp.get("timestamp") or rp.get("t") or "")
            prob = rp.get("probability")
            if not ts or not isinstance(prob, (int, float)):
                continue
            pct = _half_up_pct(float(prob))
            pts_clean.append({"t": ts, "pct": pct})
        pts_clean = _downsample_points(pts_clean, limit=20)
        if len(pts_clean) < 2:
            # Slice 5 Note 2: never synthesize a fake 2-point slope from months-old opening_probability.
            pts_clean = [
                {"t": start_default, "pct": cur_pct},
                {"t": end_default, "pct": cur_pct},
            ]
        else:
            s_pcts = [p["pct"] for p in pts_clean]
            max_swing_pp = max(max_swing_pp, max(s_pcts) - min(s_pcts))
        if pts_clean:
            if earliest_iso is None or pts_clean[0]["t"] < earliest_iso:
                earliest_iso = pts_clean[0]["t"]
            if latest_iso is None or pts_clean[-1]["t"] > latest_iso:
                latest_iso = pts_clean[-1]["t"]
        art = o.get("art") if isinstance(o.get("art"), Mapping) else {}
        cand_color = str(art.get("accent_color") or "").strip()
        if not cand_color or cand_color.lower() in used_colors:
            cand_color = next(
                (c for c in _PALETTE_FALLBACK if c.lower() not in used_colors),
                _PALETTE_FALLBACK[idx % len(_PALETTE_FALLBACK)],
            )
        used_colors.add(cand_color.lower())
        net_val = (pts_clean[-1]["pct"] - pts_clean[0]["pct"]) if len(pts_clean) >= 2 else 0
        series_out.append(
            {
                "outcome_id": oid,
                "name": str(o["name"]),
                "current_pct": cur_pct,
                "net_move_pp": net_val,
                "color": cand_color,
                "art": dict(art),
                "points": pts_clean,
            }
        )

    all_pcts = [pt["pct"] for s in series_out for pt in s["points"]] or [0, 100]
    lo = min(all_pcts)
    hi = max(all_pcts)
    pad = max(4, int(round((hi - lo) * 0.25)))
    y_min = max(0, ((lo - pad) // 5) * 5)
    y_max = min(100, int(math.ceil((hi + pad) / 5.0) * 5))
    if y_max - y_min < 15:
        y_max = min(100, y_min + 15)
        if y_max - y_min < 15:
            y_min = max(0, y_max - 15)

    moved = _history_chart_moved({"series": series_out})
    card_copy = dict(hydrated_market.get("card") or {})
    card_copy["content_kind"] = "history" if moved else str(hydrated_market.get("content_kind") or "futures")

    return {
        "market_id": mid,
        "title": str(hydrated_market["title"]),
        "href": str(hydrated_market["href"]),
        "scale_ordered": bool(hydrated_market.get("scale_ordered")),
        "start_iso": earliest_iso or start_default,
        "end_iso": latest_iso or end_default,
        "y_min": y_min,
        "y_max": y_max,
        "max_swing_pp": max_swing_pp,
        "moved": moved,
        "series": series_out,
        "card": card_copy,
    }


_CATEGORY_LLM_POOL: dict[str, tuple[str, ...]] = {
    "economics": ("economics", "finance", "business", "macro", "politics", "other"),
    "politics": ("politics", "geopolitics", "us_politics", "elections", "other"),
    "entertainment": (
        "entertainment",
        "culture",
        "social_media",
        "awards",
        "film",
        "movies",
        "pop_culture",
        "other",
    ),
    "weather": ("weather", "climate", "science", "other"),
    "football": ("football", "nfl", "americanfootball_nfl", "other"),
    "basketball": ("basketball", "nba", "basketball_nba", "basketball_ncaab", "other"),
    "hockey": ("hockey", "nhl", "icehockey_nhl", "other"),
    "soccer": ("soccer", "sports", "other"),
    "tech": ("tech", "technology", "ai", "science", "other"),
}


def _category_llm_pool_for_definition(
    definition: Mapping[str, Any],
) -> Optional[tuple[str, ...]]:
    """Return the scoped ``llm_sport_category`` pool for ``ix_fm_feed_open_sports``."""
    cat = str(definition.get("category") or "").strip().lower()
    rule = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
    extras = tuple(
        str(c).strip().lower()
        for c in (rule.get("extra_llm_categories") or ())
        if str(c).strip()
    )
    if cat in _CATEGORY_LLM_POOL:
        base = _CATEGORY_LLM_POOL[cat]
        return tuple(dict.fromkeys([*base, *extras])) if extras else base
    sections_cfg = rule.get("sections") or ()
    sport_keys = {
        str(sec["atom_query"].get("sport_key") or "").strip().lower()
        for sec in sections_cfg
        if isinstance(sec, Mapping)
        and isinstance(sec.get("atom_query"), Mapping)
        and sec["atom_query"].get("kind") == "events"
    }
    if any(sk.startswith("americanfootball_") for sk in sport_keys):
        return tuple(dict.fromkeys([*_CATEGORY_LLM_POOL["football"], *extras]))
    if any(sk.startswith("basketball_") for sk in sport_keys):
        return tuple(dict.fromkeys([*_CATEGORY_LLM_POOL["basketball"], *extras]))
    return extras or None


def _market_title_matches_query(title: str, query: Mapping[str, Any]) -> bool:
    """Fast pure-Python title token filter matching ``_market_matches_query``."""
    title_low = str(title or "").lower()
    if not title_low:
        return False
    req_tokens = [
        str(t).lower() for t in (query.get("title_all_tokens") or ()) if str(t).strip()
    ]
    if any(tok not in title_low for tok in req_tokens):
        return False
    any_tokens = [
        str(t).lower() for t in (query.get("any_tokens") or ()) if str(t).strip()
    ]
    if any_tokens and not any(tok in title_low for tok in any_tokens):
        return False
    excl_tokens = [
        str(t).lower() for t in (query.get("exclude_tokens") or ()) if str(t).strip()
    ]
    explicitly_womens = any("women" in tok for tok in req_tokens + any_tokens)
    if not explicitly_womens:
        if "wnba" in excl_tokens:
            excl_tokens.extend(
                [
                    "women's pro basketball",
                    "womens pro basketball",
                    "women\u2019s pro basketball",
                ]
            )
        if "lpga" in excl_tokens:
            excl_tokens.extend(
                ["women's pro golf", "womens pro golf", "women\u2019s pro golf"]
            )
        if "nwsl" in excl_tokens:
            excl_tokens.extend(
                ["women's pro soccer", "womens pro soccer", "women\u2019s pro soccer"]
            )
    if any(tok in title_low for tok in excl_tokens):
        return False
    return True


def _build_scoped_open_market_scan_stmt(cat_pool: tuple[str, ...]):
    """Lightweight (id, name, volume) scan backed by ``ix_fm_feed_open_sports``.

    Uses ``UNION ALL`` over ``llm_sport_category IN cat_pool`` and
    ``llm_sport_category IS NULL`` (both under ``status = 'open' AND event_id IS NULL``)
    so PostgreSQL walks the partial B-tree index instead of running multi-clause
    ``ILIKE`` / ``NOT ILIKE`` text scans across hundreds of thousands of resolved
    or game-linked rows.
    """
    from sqlalchemy import select, union_all

    from app.models.models import FuturesMarket

    arm_cat = select(
        FuturesMarket.id,
        FuturesMarket.name,
        FuturesMarket.volume,
    ).where(
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        FuturesMarket.llm_sport_category.in_(cat_pool),
    )
    arm_null = select(
        FuturesMarket.id,
        FuturesMarket.name,
        FuturesMarket.volume,
    ).where(
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        FuturesMarket.llm_sport_category.is_(None),
    )
    return union_all(arm_cat, arm_null)


def _build_machinery_history_lateral_stmt(
    wanted_oids: Sequence[int],
    cutoff: datetime,
    *,
    per_outcome_limit: int = 96,
):
    """Per-outcome newest-``per_outcome_limit`` snapshot query via ``LATERAL`` (#13475).

    Lets PostgreSQL run one backward index scan per ``outcome_id`` on
    ``idx_fos_outcome_captured(outcome_id, captured_at)`` stopping at
    ``LIMIT per_outcome_limit``, instead of materializing and sorting a full
    168-hour ``ROW_NUMBER()`` window across every outcome before discarding ``rn > 96``.
    """
    from sqlalchemy import Integer, column, select, true, values

    from app.models.models import FuturesOddsSnapshot

    unique_oids = sorted({int(oid) for oid in wanted_oids})
    if not unique_oids:
        return (
            select(
                FuturesOddsSnapshot.outcome_id,
                FuturesOddsSnapshot.captured_at,
                FuturesOddsSnapshot.probability,
            )
            .where(FuturesOddsSnapshot.id == -1)
        )
    want = values(
        column("outcome_id", Integer),
        name="want_outcomes",
    ).data([(oid,) for oid in unique_oids])
    per_outcome = (
        select(
            FuturesOddsSnapshot.outcome_id.label("outcome_id"),
            FuturesOddsSnapshot.captured_at.label("captured_at"),
            FuturesOddsSnapshot.probability.label("probability"),
        )
        .where(
            FuturesOddsSnapshot.outcome_id == want.c.outcome_id,
            FuturesOddsSnapshot.captured_at >= cutoff,
            FuturesOddsSnapshot.captured_at.isnot(None),
        )
        .order_by(FuturesOddsSnapshot.captured_at.desc())
        .limit(int(per_outcome_limit))
        .lateral("recent_history")
    )
    return (
        select(
            per_outcome.c.outcome_id,
            per_outcome.c.captured_at,
            per_outcome.c.probability,
        )
        .select_from(want)
        .join(per_outcome, true())
        .order_by(
            per_outcome.c.outcome_id.asc(),
            per_outcome.c.captured_at.asc(),
        )
    )


async def _load_snapshot_from_db(
    db: Any,
    definition: Mapping[str, Any],
    now_dt: datetime,
) -> dict[str, Any]:
    """Load candidate events, open futures markets, paired sets, and outcome histories."""
    if isinstance(db, Mapping) and (
        "events" in db
        or "markets" in db
        or "paired_sets" in db
        or "market_histories" in db
        or "team_lookup" in db
        or "teams" in db
    ):
        raw_mh = db.get("market_histories") or {}
        norm_mh: dict[int, list[dict[str, Any]]] = {}
        if isinstance(raw_mh, Mapping):
            for k, v in raw_mh.items():
                try:
                    norm_mh[int(k)] = [dict(x) for x in (v or ()) if isinstance(x, Mapping)]
                except (TypeError, ValueError):
                    continue
        snap_team_lookup = db.get("team_lookup")
        if snap_team_lookup is None and isinstance(db.get("teams"), Sequence):
            snap_team_lookup = _build_team_lookup_from_entries(db["teams"])
        return {
            "events": list(db.get("events") or ()),
            "markets": list(db.get("markets") or ()),
            "paired_sets": dict(db.get("paired_sets") or {}),
            "market_histories": norm_mh,
            "team_lookup": snap_team_lookup,
        }

    from sqlalchemy import and_, or_, select
    from sqlalchemy.orm import joinedload

    from app.models.models import Event, FuturesMarket, Sport
    from app.routes.futures import (
        _apply_verified_title_to_detail,
        _fleet_newest_observation,
        _format_market_detail,
        _game_container_lead_leg,
        _game_container_leg_sides,
        _resolve_verified_title,
        _verified_title_market_stmt,
        out_legs_by_market,
        withheld_price_outcome_ids_for_markets,
    )
    from app.services.paired_metric_register import fold_outcome_key, load_live_paired_metric_sets
    from app.utils.hero_probability import resolve_hero

    sections_cfg = (definition.get("rule") or {}).get("sections") or ()
    events_out: list[dict[str, Any]] = []
    markets_out: list[dict[str, Any]] = []
    paired_out: dict[str, dict[str, Any]] = {}
    histories_out: dict[int, list[dict[str, Any]]] = {}

    sport_keys = {
        str(sec["atom_query"]["sport_key"])
        for sec in sections_cfg
        if isinstance(sec, Mapping)
        and isinstance(sec.get("atom_query"), Mapping)
        and sec["atom_query"].get("kind") == "events"
        and sec["atom_query"].get("sport_key")
    }
    if sport_keys:
        horizon = now_dt + timedelta(days=9)
        recent_floor = now_dt - timedelta(hours=6)
        stmt = (
            select(Event)
            .join(Sport, Event.sport_id == Sport.id)
            .options(
                joinedload(Event.sport),
                joinedload(Event.home_team),
                joinedload(Event.away_team),
            )
            .where(
                Sport.key.in_(sorted(sport_keys)),
                Event.commence_time >= recent_floor,
                Event.commence_time <= horizon,
            )
            .order_by(Event.commence_time.asc())
            .limit(40)
        )
        from app.utils.draw_priced_winner import sport_prices_a_draw
        from app.utils.settled_hero import is_finished_status, settled_current_chance

        rows = (await db.execute(stmt)).scalars().all()
        for ev in rows:
            # Slice 6 Item 2b: use resolve_hero (same authority as GET /api/events/{id})
            hero = resolve_hero(ev)
            if hero is None:
                continue
            sport_obj = getattr(ev, "sport", None)
            if isinstance(sport_obj, str):
                sport_key_val = sport_obj
                sport_name_val = sport_obj.upper()
            elif sport_obj is not None:
                sport_key_val = str(getattr(sport_obj, "key", "") or "")
                sport_name_val = str(getattr(sport_obj, "name", "") or sport_key_val.upper())
            else:
                sport_key_val = ""
                sport_name_val = ""
            dp: Optional[float] = None
            draw_pct: Optional[int] = None
            if is_finished_status(ev.status):
                _sc = settled_current_chance(hero, sport_key=sport_key_val)
                if not _sc.resolved:
                    # #13172 Option B: final_unresolved never serves a live price.
                    continue
                hp = float(_sc.home_probability)
                ap = float(_sc.away_probability)
                home_pct = int(_sc.home_rendered_percent)
                away_pct = int(_sc.away_rendered_percent)
                if sport_prices_a_draw(sport_key_val):
                    dp = _sc.draw_probability
                    draw_pct = _sc.draw_rendered_percent
            else:
                hp = float(hero.home_probability)
                ap = float(hero.away_probability)
                # Exact same two lines as GET /api/events/{id} (`routes/events.py:20829-20837`).
                canonical_ap = printable_away(ap, hp, sport_key_val)
                away_pct_raw, home_pct_raw = rendered_duel_percents(canonical_ap, hp)
                away_pct = int(away_pct_raw) if away_pct_raw is not None else _half_up_pct(ap)
                home_pct = int(home_pct_raw) if home_pct_raw is not None else _half_up_pct(hp)
            home_team_obj = getattr(ev, "home_team", None)
            away_team_obj = getattr(ev, "away_team", None)
            home_team_str = str(
                getattr(ev, "home_team_name", None)
                or (
                    home_team_obj
                    if isinstance(home_team_obj, str)
                    else getattr(home_team_obj, "name", "")
                )
                or ""
            )
            away_team_str = str(
                getattr(ev, "away_team_name", None)
                or (
                    away_team_obj
                    if isinstance(away_team_obj, str)
                    else getattr(away_team_obj, "name", "")
                )
                or ""
            )
            ev_current_odds: dict[str, Any] = {
                "home_probability": hp,
                "away_probability": ap,
                "away_rendered_percent": away_pct,
                "home_rendered_percent": home_pct,
            }
            if dp is not None:
                ev_current_odds["draw_probability"] = dp
                ev_current_odds["draw_rendered_percent"] = draw_pct
            computed_tags = _computed_event_tags(ev, sport_key_val)
            ev_dict: dict[str, Any] = {
                "id": ev.id,
                "sport": sport_key_val,
                "sport_name": sport_name_val,
                "home_team": home_team_str,
                "away_team": away_team_str,
                "commence_time": ev.commence_time.isoformat() if ev.commence_time else "",
                "status": ev.status or "scheduled",
                "home_score": ev.home_score,
                "away_score": ev.away_score,
                "hero_probability": hp,
                "hero_probability_away": ap,
                **({"hero_probability_draw": dp} if dp is not None else {}),
                "hero_source": hero.source,
                "has_sportsbook": _event_has_sportsbook(ev, hero_source=hero.source),
                "current_odds": ev_current_odds,
                "member_page_numbers": {
                    "away_pct": away_pct,
                    "home_pct": home_pct,
                },
                **({"_event_tags": computed_tags} if computed_tags else {}),
            }
            for td_key, team_obj in (("home_team_data", home_team_obj), ("away_team_data", away_team_obj)):
                if team_obj is not None and not isinstance(team_obj, str):
                    logo_sm = getattr(team_obj, "logo_url_small", None) or getattr(team_obj, "logo_url", None)
                    logo_lg = getattr(team_obj, "logo_url_large", None) or getattr(team_obj, "logo_url", None)
                    p_col = getattr(team_obj, "primary_color", None)
                    s_col = getattr(team_obj, "secondary_color", None)
                    loc_val = getattr(team_obj, "location", None)
                    if any((logo_sm, logo_lg, p_col, s_col, loc_val)):
                        ev_dict[td_key] = {
                            "logo_small": logo_sm,
                            "logo_large": logo_lg,
                            "primary_color": p_col,
                            "secondary_color": s_col,
                            **({"location": loc_val} if loc_val else {}),
                        }
            events_out.append(ev_dict)

    ceremonies = {
        str(sec["atom_query"].get("ceremony") or "").lower()
        for sec in sections_cfg
        if isinstance(sec, Mapping)
        and isinstance(sec.get("atom_query"), Mapping)
        and sec["atom_query"].get("kind") == "paired_stage"
        and sec["atom_query"].get("ceremony")
    }
    paired_stage_mids: set[int] = set()
    if ceremonies:
        paired_prefix = f"{next(iter(ceremonies))}-" if len(ceremonies) == 1 else None
        all_paired = await load_live_paired_metric_sets(db, prefix=paired_prefix)
        paired_out.update(all_paired)
        for sec in sections_cfg:
            if not isinstance(sec, Mapping) or not isinstance(sec.get("atom_query"), Mapping):
                continue
            aq = sec["atom_query"]
            if aq.get("kind") == "paired_stage":
                matched_ps = _match_paired_set(paired_out, aq)
                if matched_ps is not None:
                    for skey in ("stage_1_market", "stage_2_market"):
                        sm = matched_ps.get(skey)
                        if isinstance(sm, Mapping) and isinstance(sm.get("id"), int) and sm["id"] > 0:
                            paired_stage_mids.add(int(sm["id"]))

    needs_markets = any(
        isinstance(sec, Mapping)
        and isinstance(sec.get("atom_query"), Mapping)
        and sec["atom_query"].get("kind") in {"markets", "market_history"}
        for sec in sections_cfg
    )
    history_queries = [
        sec["atom_query"]
        for sec in sections_cfg
        if isinstance(sec, Mapping)
        and isinstance(sec.get("atom_query"), Mapping)
        and sec["atom_query"].get("kind") == "market_history"
    ]
    if needs_markets or paired_stage_mids:
        market_sections: list[Mapping[str, Any]] = [
            sec["atom_query"]
            for sec in sections_cfg
            if isinstance(sec, Mapping)
            and isinstance(sec.get("atom_query"), Mapping)
            and sec["atom_query"].get("kind") in {"markets", "market_history"}
        ]
        # Step 1: Lightweight index-backed candidate ID discovery via
        # `ix_fm_feed_open_sports` (status='open' AND event_id IS NULL), fetching
        # ONLY (id, name, volume) and filtering section title tokens in Python.
        # Avoids multi-clause ILIKE/NOT ILIKE scans over hundreds of thousands of
        # resolved or game-linked rows and eliminates the double FuturesMarket fetch.
        title_matched_mids: set[int] = set()
        title_volume_by_mid: dict[int, float] = {}
        if needs_markets and market_sections:
            fun_tag_sections: list[Mapping[str, Any]] = []
            non_fun_sections: list[Mapping[str, Any]] = []
            for aq in market_sections:
                if str(aq.get("fun_sub_tag") or "").strip():
                    fun_tag_sections.append(aq)
                else:
                    non_fun_sections.append(aq)
            if fun_tag_sections:
                from app.utils.discover_fun_tags import fun_market_ids_for_sub_tag

                for aq in fun_tag_sections:
                    tag_ids = fun_market_ids_for_sub_tag(str(aq["fun_sub_tag"]).strip())
                    title_matched_mids.update(int(mid_i) for mid_i in tag_ids)

            cat_pool = (
                _category_llm_pool_for_definition(definition)
                if non_fun_sections
                else None
            )
            lightweight_rows: list[tuple[int, str, float]] = []
            if cat_pool is not None:
                scan_rows = (
                    await db.execute(_build_scoped_open_market_scan_stmt(cat_pool))
                ).all()
                seen_scan: set[int] = set()
                for mid_val, name_val, vol_val in scan_rows:
                    mid_i = int(mid_val)
                    if mid_i in seen_scan:
                        continue
                    seen_scan.add(mid_i)
                    lightweight_rows.append(
                        (mid_i, str(name_val or ""), float(vol_val or 0.0))
                    )

            unmatched_sections: list[Mapping[str, Any]] = []
            for aq in non_fun_sections:
                has_tokens = bool(
                    (aq.get("title_all_tokens") or ())
                    or (aq.get("any_tokens") or ())
                    or (aq.get("exclude_tokens") or ())
                )
                cap_n = (
                    max(int(aq.get("max_items", 4)) + 3, 6)
                    if aq.get("kind") == "market_history"
                    else max(int(aq.get("max_items", 4)) + 2, 4)
                )
                fetch_cap = max(cap_n * 3, 12) if has_tokens else 40
                sec_hits = [
                    row
                    for row in lightweight_rows
                    if (not has_tokens or _market_title_matches_query(row[1], aq))
                ]
                if not sec_hits:
                    unmatched_sections.append(aq)
                else:
                    sec_hits.sort(key=lambda r: (-r[2], r[0]))
                    for mid_i, _nm, vol_f in sec_hits[:fetch_cap]:
                        title_matched_mids.add(mid_i)
                        title_volume_by_mid[mid_i] = vol_f

            # Safety fallback only for an uncategorized grouping or a required section
            # whose target market carried an unexpected llm_sport_category (0 extra
            # queries in steady state on all registered groupings). Still enforces
            # `event_id IS NULL` and evaluates exclude_tokens in Python (never NOT ILIKE).
            if unmatched_sections:
                pos_clauses = []
                for aq in unmatched_sections:
                    all_toks = [
                        str(t).strip()
                        for t in (aq.get("title_all_tokens") or ())
                        if str(t).strip()
                    ]
                    any_toks = [
                        str(t).strip()
                        for t in (aq.get("any_tokens") or ())
                        if str(t).strip()
                    ]
                    parts = [FuturesMarket.name.ilike(f"%{t}%") for t in all_toks]
                    if any_toks:
                        parts.append(
                            or_(*(FuturesMarket.name.ilike(f"%{t}%") for t in any_toks))
                        )
                    if parts:
                        pos_clauses.append(and_(*parts))
                fb_stmt = select(
                    FuturesMarket.id, FuturesMarket.name, FuturesMarket.volume
                ).where(FuturesMarket.event_id.is_(None), FuturesMarket.status == "open")
                if pos_clauses:
                    fb_stmt = fb_stmt.where(or_(*pos_clauses)).limit(80)
                else:
                    fb_stmt = fb_stmt.order_by(
                        FuturesMarket.volume_24h.desc().nullslast()
                    ).limit(120)
                fb_rows = [
                    (int(r[0]), str(r[1] or ""), float(r[2] or 0.0))
                    for r in (await db.execute(fb_stmt)).all()
                ]
                for aq in unmatched_sections:
                    cap_n = (
                        max(int(aq.get("max_items", 4)) + 3, 6)
                        if aq.get("kind") == "market_history"
                        else max(int(aq.get("max_items", 4)) + 2, 4)
                    )
                    hits = [
                        row for row in fb_rows if _market_title_matches_query(row[1], aq)
                    ]
                    hits.sort(key=lambda r: (-r[2], r[0]))
                    for mid_i, _nm, vol_f in hits[: max(cap_n * 3, 12)]:
                        title_matched_mids.add(mid_i)
                        title_volume_by_mid[mid_i] = vol_f

        # Step 2: Single PK fetch via `_verified_title_market_stmt()` for all matched
        # market IDs + paired-stage market IDs (eliminates the second FuturesMarket fetch).
        all_fetch_mids = title_matched_mids | paired_stage_mids
        vt_rows_by_id: dict[int, Any] = {}
        if all_fetch_mids:
            fetched_vt_rows = (
                await db.execute(
                    _verified_title_market_stmt().where(
                        FuturesMarket.id.in_(sorted(all_fetch_mids))
                    )
                )
            ).unique().scalars().all()
            vt_rows_by_id = {int(fm.id): fm for fm in fetched_vt_rows}

        ordered_title_mids = sorted(
            (mid for mid in title_matched_mids if mid in vt_rows_by_id),
            key=lambda mid: (-title_volume_by_mid.get(mid, 0.0), mid),
        )
        prelim_markets: list[dict[str, Any]] = []
        for mid in ordered_title_mids:
            fm = vt_rows_by_id[mid]
            top_outs: list[dict[str, Any]] = []
            for o in fm.outcomes or ():
                prob_val = getattr(o, "current_probability", None)
                if prob_val is None:
                    prob_val = getattr(o, "implied_probability", None)
                if prob_val is None:
                    continue
                o_name = getattr(o, "name", None) or getattr(o, "outcome_name", "")
                open_prob = getattr(o, "opening_probability", None)
                top_outs.append(
                    {
                        "id": o.id,
                        "name": str(o_name),
                        "probability": float(prob_val),
                        "opening_probability": float(open_prob) if open_prob is not None else None,
                        "image_url": getattr(o, "image_url", None),
                    }
                )
            prelim_markets.append(
                {
                    "id": fm.id,
                    "name": fm.name,
                    "status": fm.status,
                    "source": fm.source,
                    "mutually_exclusive": bool(getattr(fm, "mutually_exclusive", True)),
                    "market_type": getattr(fm, "market_type", None),
                    "volume": _effective_market_volume(
                        fm.volume,
                        volume_24h=getattr(fm, "volume_24h", None),
                        market_metadata=getattr(fm, "market_metadata", None),
                    ),
                    "image_url": fm.image_url,
                    "llm_sport_category": fm.llm_sport_category,
                    "resolution_date": (
                        res_dt_raw.isoformat()
                        if isinstance((res_dt_raw := getattr(fm, "resolution_date", None)), (datetime, date))
                        else res_dt_raw
                    ),
                    "event_date": (
                        ev_dt_raw.isoformat()
                        if isinstance((ev_dt_raw := getattr(fm, "event_date", None)), (datetime, date))
                        else ev_dt_raw
                    ),
                    "top_outcomes": top_outs,
                }
            )

        # Slice 6 Item 2b + #12288 pre-flip guard: format EVERY candidate member market
        # through the exact same verified_title detail + withhold pipeline as
        # GET /api/futures/{id}?representation=verified_title so no unscreened raw DB
        # market (like past-ceremony #109566 with all 16 prices withheld) can slip through.
        candidate_mids: set[int] = set(paired_stage_mids) | set(ordered_title_mids)

        detail_by_mid: dict[int, dict[str, Any]] = {}
        mpn_by_mid: dict[int, dict[str, Any]] = {}
        selected_vt_rows = [
            vt_rows_by_id[mid] for mid in sorted(candidate_mids) if mid in vt_rows_by_id
        ]
        if selected_vt_rows:
            out_map = await out_legs_by_market(selected_vt_rows)
            # Constant-query-count batched withhold screen (<= 4 queries total vs N*2-3).
            withheld_by_mid = await withheld_price_outcome_ids_for_markets(
                db, selected_vt_rows
            )
            fleet_newest_by_source: dict[str, Any] = {}
            for fm in selected_vt_rows:
                unsupported_ids = withheld_by_mid.get(fm.id, set())
                if getattr(fm, "source", None) == "polymarket" and not getattr(fm, "mutually_exclusive", True):
                    leg_sides = await _game_container_leg_sides(db, fm)
                    lead_leg = await _game_container_lead_leg(db, fm, leg_sides)
                else:
                    leg_sides = {}
                    lead_leg = None
                src_key = str(getattr(fm, "source", None) or "").strip().lower()
                if src_key not in fleet_newest_by_source:
                    fleet_newest_by_source[src_key] = await _fleet_newest_observation(db, fm)
                fm_fleet = fleet_newest_by_source[src_key]
                detail = _format_market_detail(
                    fm,
                    None,
                    unsupported_ids,
                    fleet_newest_observation=fm_fleet,
                    leg_sides=leg_sides,
                    lead_leg=lead_leg,
                    out_division_labels=out_map.get(fm.id),
                    normalize_numbers=False,
                )
                _apply_verified_title_to_detail(
                    detail, await _resolve_verified_title(db, fm), fm
                )
                d_outs = list(detail.get("outcomes") or ())
                card_pcts = rendered_card_percents([row.get("probability") for row in d_outs])
                by_oid: dict[int, int] = {}
                by_key: dict[str, int] = {}
                by_fold: dict[str, tuple[float, int, int]] = {}
                formatted_outs: list[dict[str, Any]] = []
                img_by_oid = {o.id: getattr(o, "image_url", None) for o in (fm.outcomes or ())}
                upd_by_oid = {o.id: getattr(o, "last_updated", None) for o in (fm.outcomes or ())}
                newest_live_upd: Optional[datetime] = None
                for idx, row in enumerate(d_outs):
                    prob = row.get("probability")
                    if prob is None or not isinstance(prob, (int, float)) or not math.isfinite(float(prob)):
                        continue
                    p_f = float(prob)
                    oid = int(row["id"])
                    rp = row.get("rendered_percent")
                    if rp is not None:
                        unfloored = pct_int = int(rp)
                    else:
                        card_pct = card_pcts[idx] if idx < len(card_pcts) else None
                        unfloored = card_pct if card_pct is not None else _half_up_pct(p_f)
                        pct_int = _legacy_grouped_percent(p_f, unfloored)
                    by_oid[oid] = pct_int
                    r_name = str(row.get("name") or "")
                    for nk in (
                        _norm_key(_clean_outcome_label(r_name)),
                        _norm_key(r_name),
                        _ascii_fold_key(_clean_outcome_label(r_name)),
                        _ascii_fold_key(r_name),
                    ):
                        if nk and nk not in by_key:
                            by_key[nk] = pct_int
                    fk = fold_outcome_key(r_name)
                    if fk and fk not in by_fold:
                        by_fold[fk] = (p_f, pct_int, unfloored)
                    o_upd_dt = _parse_iso_dt_utc(upd_by_oid.get(oid))
                    if o_upd_dt is not None and (newest_live_upd is None or o_upd_dt > newest_live_upd):
                        newest_live_upd = o_upd_dt
                    formatted_outs.append(
                        {
                            "id": oid,
                            "name": r_name,
                            "probability": p_f,
                            "rendered_percent": pct_int,
                            "unfloored_percent": unfloored,
                            "opening_probability": row.get("opening_probability"),
                            "image_url": img_by_oid.get(oid),
                            "last_updated": o_upd_dt.isoformat() if o_upd_dt is not None else None,
                        }
                    )
                mpn = {
                    "by_outcome_id": by_oid,
                    "by_outcome_key": by_key,
                    "by_fold_key": {k: v[1] for k, v in by_fold.items()},
                }
                mpn_by_mid[fm.id] = mpn
                detail_by_mid[fm.id] = {
                    "top_outcomes": formatted_outs,
                    "newest_outcome_updated_at": newest_live_upd.isoformat() if newest_live_upd is not None else None,
                    "by_oid_prob_pct": {
                        int(o["id"]): (
                            o["probability"], o["rendered_percent"], o["unfloored_percent"],
                        )
                        for o in formatted_outs
                    },
                    "by_fold_prob_pct": by_fold,
                }

        for pm in prelim_markets:
            mid = int(pm["id"])
            if mid not in detail_by_mid:
                continue
            screened_outs = detail_by_mid[mid]["top_outcomes"]
            if not screened_outs:
                continue
            pm["top_outcomes"] = screened_outs
            pm["newest_outcome_updated_at"] = detail_by_mid[mid]["newest_outcome_updated_at"]
            pm["member_page_numbers"] = mpn_by_mid[mid]
            markets_out.append(pm)

        # The paired loader already supplied the winner field's served values.
        # Keep the separate nomination/qualification page matching here.
        for set_id, pset in paired_out.items():
            if not isinstance(pset, dict):
                continue
            s1_mid = int((pset.get("stage_1_market") or {}).get("id") or 0)
            s2_mid = int((pset.get("stage_2_market") or {}).get("id") or 0)
            s1_det = detail_by_mid.get(s1_mid)
            s2_det = detail_by_mid.get(s2_mid)
            if not s1_det and not s2_det:
                continue
            pset["member_page_numbers_by_market"] = {
                k: mpn_by_mid[k] for k in (s1_mid, s2_mid) if k in mpn_by_mid
            }
            for entry in pset.get("entries") or ():
                if not isinstance(entry, dict):
                    continue
                fk = fold_outcome_key(str(entry.get("subject") or ""))
                if s1_det and not entry.get("stage_1_settled_state"):
                    s1_oid = entry.get("stage_1_outcome_id")
                    match_s1 = (
                        s1_det["by_oid_prob_pct"].get(int(s1_oid))
                        if isinstance(s1_oid, int) and s1_oid in s1_det["by_oid_prob_pct"]
                        else s1_det["by_fold_prob_pct"].get(fk)
                    )
                    if match_s1 is not None:
                        p_s1, pct_s1, unfloored_s1 = match_s1
                        # Ensure client renderedPercent(stage_1_probability) equals pct_s1 exactly
                        entry["stage_1_probability"] = (
                            p_s1 if _half_up_pct(p_s1) == pct_s1 else round(pct_s1 / 100.0, 4)
                        )
                        entry["stage_1_rendered_percent"] = pct_s1
                        entry["stage_1_unfloored_percent"] = unfloored_s1
            # Re-sort entries by stage_2_probability desc, stage_1_probability desc, subject asc
            pset["entries"] = sorted(
                [e for e in (pset.get("entries") or ()) if isinstance(e, dict)],
                key=lambda e: (
                    0 if isinstance(e.get("stage_2_probability"), (int, float)) else 1,
                    -float(e.get("stage_2_probability") or -1.0),
                    -float(e.get("stage_1_probability") or -1.0),
                    str(e.get("subject") or "").casefold(),
                ),
            )

        card_sec_key = str((definition.get("rule") or {}).get("card_section_key") or "").strip()
        card_market_queries = [
            sec["atom_query"]
            for idx, sec in enumerate(sections_cfg)
            if isinstance(sec, Mapping)
            and isinstance(sec.get("atom_query"), Mapping)
            and sec["atom_query"].get("kind") == "markets"
            and ((card_sec_key and str(sec.get("key") or "") == card_sec_key) or (not card_sec_key and idx == 0))
        ]
        all_hist_queries = [
            (hq, max(int(hq.get("max_items", 4)) + 1, 3)) for hq in history_queries
        ] + [
            (hq, max(int(hq.get("max_items", 1)), 1)) for hq in card_market_queries
        ]
        if all_hist_queries and markets_out:
            wanted_oids: set[int] = set()
            max_hours = max([int(hq.get("hours") or 168) for hq, _ in all_hist_queries] or [168])
            for hq, hist_cap in all_hist_queries:
                matched_for_hq = [m_dict for m_dict in markets_out if _market_matches_query(m_dict, hq)]
                for m_dict in matched_for_hq[:hist_cap]:
                    outs_sorted = sorted(
                        m_dict["top_outcomes"],
                        key=lambda x: -float(x.get("probability") or 0.0),
                    )
                    for o_d in outs_sorted[:3]:
                        wanted_oids.add(int(o_d["id"]))
            if wanted_oids:
                cutoff = now_dt - timedelta(hours=max_hours)
                h_stmt = _build_machinery_history_lateral_stmt(
                    sorted(wanted_oids), cutoff
                )
                for oid_val, cap_at, prob_val in (await db.execute(h_stmt)).all():
                    oid = int(oid_val)
                    histories_out.setdefault(oid, []).append(
                        {
                            "timestamp": cap_at.isoformat() if cap_at else "",
                            "probability": float(prob_val),
                        }
                    )

    team_lookup_out: Any = None
    sports_markets_for_lookup = [
        m for m in markets_out if _is_sports_context(m, definition)
    ]
    if events_out or sports_markets_for_lookup or _is_sports_definition(definition):
        candidate_team_names: list[str] = []
        for ev_d in events_out:
            for tk in ("home_team", "away_team"):
                tv = str(ev_d.get(tk) or "").strip()
                if tv:
                    candidate_team_names.append(tv)
        for m_d in sports_markets_for_lookup:
            for o_d in m_d.get("top_outcomes") or m_d.get("outcomes") or ():
                if not isinstance(o_d, Mapping):
                    continue
                raw_on = str(o_d.get("name") or o_d.get("outcome_name") or "").strip()
                cleaned_on = _clean_outcome_label(raw_on)
                for cand_on in (raw_on, cleaned_on, _OUTCOME_PROP_SUFFIX_RE.sub("", cleaned_on).strip()):
                    if cand_on and cand_on.lower() not in {"yes", "no"}:
                        candidate_team_names.append(cand_on)
        dedup_names = list(dict.fromkeys(candidate_team_names))
        if dedup_names or _is_sports_definition(definition):
            try:
                import app.routes.events as _events_mod

                subset_lookup = await _events_mod._build_team_lookup(
                    db, dedup_names or ["__all__"]
                )
                cached_full = getattr(_events_mod, "_team_cache", None)
                if (
                    getattr(_events_mod._build_team_lookup, "__module__", "")
                    == "app.routes.events"
                    and isinstance(cached_full, Mapping)
                    and (cached_full or getattr(cached_full, "by_league", None))
                ):
                    team_lookup_out = _events_mod._as_lookup(cached_full)
                else:
                    team_lookup_out = subset_lookup
            except Exception:
                logger.debug(
                    "container_machinery: team lookup load failed; falling back to static art",
                    exc_info=True,
                )

    return {
        "events": events_out,
        "markets": markets_out,
        "paired_sets": paired_out,
        "market_histories": histories_out,
        "team_lookup": team_lookup_out,
    }


def _match_paired_set(
    paired_sets: Mapping[str, Mapping[str, Any]],
    query: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    ceremony = str(query.get("ceremony") or "").strip().lower()
    cat_name = str(query.get("category_name") or "").strip().lower()
    slug_token = _norm_key(cat_name).replace(" ", "-")
    for set_id, pset in paired_sets.items():
        sid = str(set_id).lower()
        title = str(pset.get("title") or "").lower()
        kicker = str(pset.get("kicker") or "").lower()
        if ceremony and ceremony not in sid and ceremony not in kicker:
            continue
        if slug_token and slug_token not in sid and cat_name not in title and cat_name not in kicker:
            continue
        return copy.deepcopy(dict(pset))
    return None


def _twin_market_key(title: str, *, raw_title: str = "") -> str:
    """Canonicalize cross-venue twin titles (e.g. 'Fed Decision in December?' vs 'Fed decision in Dec 2026?',
    or reversed couple names on engagement markets across Kalshi and Polymarket)."""
    low = re.sub(r"[?!.,]+$", "", title.strip().lower()).strip()
    m_fomc = re.match(r"^([a-z]+)(?:\s+\d{4})?\s+fed\s+decision$", low)
    if m_fomc:
        return f"fomc:{_expand_month_token(m_fomc.group(1)).lower()}"
    m_fomc_in = re.match(r"^fed\s+decision\s+in\s+([a-z]+)(?:\s+\d{4})?$", low)
    if m_fomc_in:
        return f"fomc:{_expand_month_token(m_fomc_in.group(1)).lower()}"
    m_unemp = re.match(r"^([a-z]+)(?:\s+\d{4})?\s+u\.s\.\s+unemployment(?:\s+rate)?$", low)
    if m_unemp:
        return f"us_unemp:{_expand_month_token(m_unemp.group(1)).lower()}"
    raw_low = (raw_title or title).strip().lower()
    if "engaged" in raw_low and "hours" not in raw_low:
        parts = [
            _ascii_fold_key(p)
            for p in re.split(r"\s+(?:&|and)\s+", title.strip(), flags=re.IGNORECASE)
            if _ascii_fold_key(p)
        ]
        if parts:
            return "engaged:" + "&".join(sorted(parts))
    m_gdp = re.match(r"^u\.?s\.?\s+(?:real\s+)?gdp\s+growth\s+in\s+(.+)$", low)
    if m_gdp:
        return f"us_gdp:{_norm_key(m_gdp.group(1))}"
    if re.search(r"\boscars?\b", low) and not re.search(r"\bnomin", low):
        m_oscar_cat = re.search(
            r"\b(best\s+(?:picture|director|supporting\s+actor|supporting\s+actress|actor|actress|"
            r"animated\s+feature|international\s+feature|documentary\s+feature|original\s+score|"
            r"adapted\s+screenplay|original\s+screenplay))\b",
            low,
        )
        if m_oscar_cat:
            oscar_cat = " ".join(m_oscar_cat.group(1).split())
            return f"oscars:{oscar_cat}"
    return _norm_key(title)


def _dedupe_twin_markets(markets: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the highest-liquidity canonical market when two venues list the same cleaned title.

    Every deduplicated twin's ``market_id`` is recorded on the kept item under
    ``_twin_market_ids`` so Discover pruning treats unlinked cross-venue twins as
    covered members of the grouping instead of showing the same race twice (#12288).
    """
    by_key: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for m in markets:
        norm_t = _twin_market_key(str(m["title"]), raw_title=str(m.get("raw_title") or ""))
        existing = by_key.get(norm_t)
        if existing is not None:
            twins = existing.setdefault("_twin_market_ids", [])
            mid = m.get("market_id")
            if isinstance(mid, int) and not isinstance(mid, bool) and mid not in twins:
                twins.append(mid)
            continue
        by_key[norm_t] = m
        out.append(m)
    return out


def _join_human_list(items: Sequence[str]) -> str:
    parts = [s.strip() for s in items if s and s.strip()]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def _resolve_section_heading(
    sec_cfg: Mapping[str, Any],
    *,
    aq_kind: str,
    form_id: str,
    rendered_items: Sequence[Mapping[str, Any]],
    visible_limit: int = 3,
    default_title: str = "Markets",
) -> tuple[str, Optional[str]]:
    """Ensure a section's title and description match BOTH its chosen form AND its actual items (Slice 5 Note 4)."""
    raw_title = str(sec_cfg.get("title") or default_title).strip()
    raw_note = str(sec_cfg.get("note") or "").strip() or None
    shown_titles = [
        str(it.get("title") or "").strip()
        for it in rendered_items[: max(1, visible_limit)]
        if isinstance(it, Mapping) and str(it.get("title") or "").strip()
    ]

    if aq_kind == "market_history":
        if form_id == "probability_history_chart":
            if raw_note and sec_cfg.get("preserve_note"):
                return raw_title, raw_note
            if len(shown_titles) >= 2:
                note = f"7-day odds movement across {_join_human_list(shown_titles)}."
            elif len(shown_titles) == 1:
                note = f"7-day odds movement in {shown_titles[0]}."
            else:
                note = raw_note
            return raw_title, note

        # Form switched away from probability_history_chart because no matched market moved:
        # switch BOTH title and description to current-odds wording naming the rendered items.
        fb_title = str(sec_cfg.get("fallback_title") or "").strip()
        if not fb_title:
            fb_title = raw_title
            fb_title = re.sub(r"\s+odds\s+over\s+the\s+past\s+week$", " Odds", fb_title, flags=re.IGNORECASE)
            fb_title = re.sub(r"\s+over\s+the\s+past\s+week$", "", fb_title, flags=re.IGNORECASE)
            fb_title = re.sub(r"\s+moves\s+this\s+week$", " Odds", fb_title, flags=re.IGNORECASE)
            fb_title = re.sub(r"\s+over\s+time$", "", fb_title, flags=re.IGNORECASE)
            fb_title = re.sub(r"\b(?:trends|moves|trajectories)\b", "Odds", fb_title, flags=re.IGNORECASE)
            fb_title = re.sub(r"\s+", " ", fb_title).strip() or default_title
        if len(shown_titles) >= 2:
            fb_note = f"Current leaders across {_join_human_list(shown_titles)}."
        elif len(shown_titles) == 1:
            fb_note = f"Current odds in {shown_titles[0]}."
        else:
            fb_note = "Current market odds."
        return fb_title, fb_note

    if sec_cfg.get("dynamic_item_note") and shown_titles:
        dyn_note = (
            f"Current leaders across {_join_human_list(shown_titles)}."
            if len(shown_titles) >= 2
            else f"Current odds in {shown_titles[0]}."
        )
        return raw_title, dyn_note

    return raw_title, raw_note


_US_SPORT_TZ = ZoneInfo("America/New_York")
_EUROPE_SPORT_TZ = ZoneInfo("Europe/London")
_AUSTRALIA_SPORT_TZ = ZoneInfo("Australia/Sydney")

_EUROPEAN_SPORT_PREFIXES = (
    "soccer_epl",
    "soccer_england_",
    "soccer_efl",
    "soccer_fa_cup",
    "soccer_uefa_",
    "soccer_spain_",
    "soccer_italy_",
    "soccer_germany_",
    "soccer_france_",
    "soccer_netherlands_",
    "soccer_portugal_",
    "soccer_scotland_",
    "rugby",
    "cricket",
)
_AUSTRALIAN_SPORT_PREFIXES = ("aussierules_", "rugbyleague_nrl")


def _sport_play_timezone(sport_key: str) -> ZoneInfo:
    """Resolve the local game-day timezone for a sport/league so slate date ranges reflect
    the calendar days games are played locally rather than UTC rollovers.
    """
    low = (sport_key or "").strip().lower()
    if low.startswith(_AUSTRALIAN_SPORT_PREFIXES):
        return _AUSTRALIA_SPORT_TZ
    if low.startswith(_EUROPEAN_SPORT_PREFIXES):
        return _EUROPE_SPORT_TZ
    return _US_SPORT_TZ


def _format_event_date_span(events: Sequence[Mapping[str, Any]]) -> str:
    local_dates: list[date] = []
    for ev in events:
        raw = str(ev.get("commence_time") or "").strip()
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        tz = _sport_play_timezone(str(ev.get("sport") or ""))
        local_dates.append(dt.astimezone(tz).date())
    if not local_dates:
        return ""
    lo = min(local_dates)
    hi = max(local_dates)
    if lo == hi:
        return f"{lo.strftime('%b')} {lo.day}"
    if lo.year == hi.year and lo.month == hi.month:
        return f"{lo.strftime('%b')} {lo.day}–{hi.day}"
    return f"{lo.strftime('%b')} {lo.day}–{hi.strftime('%b')} {hi.day}"


_PROPER_WORDS_KEEP = frozenset(
    {
        "u.s.",
        "us",
        "fed",
        "fomc",
        "gdp",
        "cpi",
        "ipo",
        "nfl",
        "nba",
        "mlb",
        "nhl",
        "wnba",
        "afc",
        "nfc",
        "west",
        "east",
        "north",
        "south",
        "oscar",
        "oscars",
        "senate",
        "house",
        "ap",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "sept",
        "oct",
        "nov",
        "dec",
    }
)

_EXACT_CASE_TOKENS: dict[str, str] = {
    "openai": "OpenAI",
    "openai's": "OpenAI's",
    "openai’s": "OpenAI’s",
    "spacex": "SpaceX",
    "spacex's": "SpaceX's",
    "millennium": "Millennium",
    "sec": "SEC",
    "pac-12": "Pac-12",
}


def _prose_outcome_name(name: str) -> str:
    raw = name.strip()
    low = raw.lower()
    if low == "democratic party":
        return "Democrats"
    if low == "republican party":
        return "Republicans"
    return raw


def _prose_market_phrase(title: str, *, capitalize_first: bool = False) -> str:
    """Turn a Title-Case market label into natural prose instead of dropping capitals mid-sentence."""
    raw = title.strip().rstrip("?")
    if not raw:
        return "this market"
    low = raw.lower()

    # Academy Award category names ("Best Picture", "Best Director") are established proper category titles.
    if re.match(r"^best\s+[a-z]", low):
        out = raw
    elif "presidential election winner" in low or low == "presidential winner":
        out = "the presidential race"
    elif re.match(r"^end-of-(\d{4})\s+fed\s+rate$", low):
        yr = re.match(r"^end-of-(\d{4})\s+fed\s+rate$", low).group(1)  # type: ignore[union-attr]
        out = f"the end-of-{yr} Fed rate"
    elif re.match(r"^(\d{4})\s+fed\s+rate\s+(hikes|cuts)$", low):
        m = re.match(r"^(\d{4})\s+fed\s+rate\s+(hikes|cuts)$", low)
        assert m is not None
        out = f"{m.group(1)} Fed rate {m.group(2)}"
    elif re.match(r"^([a-z]+(?:\s+\d{4})?)\s+fed\s+decision$", low):
        m = re.match(r"^([a-z]+(?:\s+\d{4})?)\s+fed\s+decision$", raw, re.IGNORECASE)
        assert m is not None
        parts = m.group(1).strip().split()
        parts[0] = _expand_month_token(parts[0])
        out = f"the {' '.join(parts)} Fed decision"
    elif re.match(r"^fed\s+decision\s+in\s+([a-z]+(?:\s+\d{4})?)$", low):
        m = re.match(r"^fed\s+decision\s+in\s+([a-z]+(?:\s+\d{4})?)$", raw, re.IGNORECASE)
        assert m is not None
        when_tok = m.group(1).strip()
        month_map = {
            "jan": "January",
            "feb": "February",
            "mar": "March",
            "apr": "April",
            "jun": "June",
            "jul": "July",
            "aug": "August",
            "sep": "September",
            "oct": "October",
            "nov": "November",
            "dec": "December",
        }
        parts = when_tok.split()
        parts[0] = month_map.get(parts[0].lower(), parts[0].capitalize())
        out = f"the {' '.join(parts)} Fed decision"
    else:
        cleaned = re.sub(r"\s+winner$", " race", raw, flags=re.IGNORECASE)
        words = []
        for w in cleaned.split():
            core = w.strip("(),.:;")
            exact_cased = _EXACT_CASE_TOKENS.get(core.lower())
            if exact_cased is not None:
                words.append(exact_cased + w[len(w.rstrip("(),.:;")) :])
            elif core.lower() in _PROPER_WORDS_KEEP or any(ch.isdigit() for ch in core):
                if core.upper() in {"NFL", "NBA", "MLB", "NHL", "WNBA", "AFC", "NFC", "GDP", "CPI", "FOMC", "IPO", "US", "AP"}:
                    words.append(w.upper())
                elif core.lower() == "u.s.":
                    words.append("U.S.")
                elif any(ch.isdigit() for ch in core) and not core[0].isalpha():
                    words.append(w)
                else:
                    words.append(core.capitalize())
            else:
                words.append(w.lower())
        joined = " ".join(words)
        joined = re.sub(r"\bbig\s+ten\b", "Big Ten", joined, flags=re.IGNORECASE)
        has_leading_possessive = bool(words and ("'" in words[0] or "’" in words[0]))
        out = (
            joined
            if joined.lower().startswith(("the ", "a ", "an ")) or has_leading_possessive
            else f"the {joined}"
        )

    if capitalize_first and out:
        return out[0].upper() + out[1:]
    return out


def _filter_card_benchmark_items(
    items: Sequence[Mapping[str, Any]],
    rule: Optional[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Filter out markets configured as set-page-only on the Discover card."""
    raw_omit = rule.get("card_omit_ids") if isinstance(rule, Mapping) else None
    if not isinstance(raw_omit, Sequence) or isinstance(raw_omit, (str, bytes)):
        return list(items)
    omit_ids: set[int] = set()
    for val in raw_omit:
        try:
            omit_ids.add(int(val))
        except (TypeError, ValueError):
            continue
    if not omit_ids:
        return list(items)
    filtered = [it for it in items if int(it.get("market_id") or 0) not in omit_ids]
    return filtered if len(filtered) >= 2 else list(items)


_ABBR_MONTHS: tuple[tuple[str, str], ...] = (
    ("January", "Jan"),
    ("February", "Feb"),
    ("August", "Aug"),
    ("September", "Sep"),
    ("October", "Oct"),
    ("November", "Nov"),
    ("December", "Dec"),
)


def _format_history_start_date(ts_iso: str) -> str:
    raw = str(ts_iso or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return f"{dt.strftime('%b')} {dt.day}"
    except ValueError:
        return ""


def _format_valuation_range_phrase(raw_out: str) -> str:
    """Turn bucket strings like `<$1T` or `$1.70-$2.00T` into readable prose."""
    text = str(raw_out or "").strip()
    if text.startswith("<"):
        return f"below {text[1:].strip()}"
    if text.startswith(">"):
        return f"above {text[1:].strip()}"
    if text.endswith("+"):
        return f"at {text[:-1].strip()} or more"
    if "–" in text or "-" in text:
        parts = [p.strip() for p in re.split(r"[–-]", text, maxsplit=1)]
        if len(parts) == 2:
            lo_p, hi_p = parts
            suffix_m = re.search(r"([TBM])\Z", hi_p)
            if suffix_m and lo_p.startswith("$") and not re.search(r"[TBM]\Z", lo_p):
                lo_p = f"{lo_p}{suffix_m.group(1)}"
            return f"between {lo_p} and {hi_p}"
    return f"at {text}"


def _format_benchmark_row_title(
    title: str,
    lead_outcome_name: str,
    *,
    headline_phrase: Optional[str] = None,
) -> str:
    """Ensure multi-outcome benchmark rows name their leading outcome cleanly."""
    clean_title = str(title or "").strip()
    ans = str(lead_outcome_name or "").strip().rstrip("?").strip()
    if not ans or ans.lower() in {"yes", "no"}:
        return clean_title
    if ans.lower() in clean_title.lower():
        return clean_title
    hp = str(headline_phrase or "").strip().rstrip("?").strip()
    for suffix in (" at {pct}%", " ({pct}%)"):
        if hp.endswith(suffix):
            candidate = hp[: -len(suffix)].strip()
            if candidate and "{pct}" not in candidate and "{" not in candidate:
                return candidate
    if ans.startswith("<"):
        ans_for_row = f"below {ans[1:].strip()}"
    elif ans.startswith(">"):
        ans_for_row = f"above {ans[1:].strip()}"
    else:
        ans_for_row = ans
    formatted, _ = _format_fun_lead_answer_label(clean_title, ans_for_row)
    return formatted


def _format_history_chance_clause(market_title: str, outcome_name: str) -> str:
    raw_title = str(market_title or "").strip().rstrip("?")
    low_title = raw_title.lower()
    raw_out = str(outcome_name or "").strip()
    for full_m, abbr_m in _ABBR_MONTHS:
        raw_out = re.sub(rf"\b{full_m}\b", abbr_m, raw_out)

    if "ipo valuation" in low_title or "openai's ipo" in low_title:
        subject = "OpenAI" if "openai" in low_title else raw_title.split("'", 1)[0].strip()
        val_phrase = _format_valuation_range_phrase(raw_out)
        return f"The chance {subject} lists {val_phrase}"

    if "market cap" in low_title and ("<" in raw_out or ">" in raw_out or "-" in raw_out or "–" in raw_out or "$" in raw_out):
        val_phrase = _format_valuation_range_phrase(raw_out)
        subject = "SpaceX" if "spacex" in low_title else _prose_market_phrase(raw_title, capitalize_first=True)
        if "end of 2026" in low_title or "ends 2026" in low_title:
            return f"The chance {subject} ends 2026 valued {val_phrase}"
        return f"The chance {subject} closes valued {val_phrase}"

    if "spacex" in low_title and "openai" in low_title and "ipo" in low_title:
        out_low = raw_out.lower()
        if "spacex" in out_low:
            return "The chance SpaceX finishes with a higher IPO cap than OpenAI"
        if "openai" in out_low:
            return "The chance OpenAI finishes with a higher IPO cap than SpaceX"

    if "millennium prize" in low_title:
        if "openai" in low_title:
            return f"The chance OpenAI solves a Millennium Prize problem by {raw_out}"
        return f"The chance a Millennium Prize problem is solved by {raw_out}"

    if _PREP_DATE_OUTCOME_RE.match(raw_out):
        m_prep = _PREP_DATE_OUTCOME_RE.match(raw_out)
        assert m_prep is not None
        prep = m_prep.group(1).lower()
        rest = m_prep.group(2).strip()
        return f"The chance {raw_title} {prep} {rest}"
    if _BARE_MONTH_DAY_RE.match(raw_out) or _BARE_MONTH_YEAR_OR_YEAR_RE.match(raw_out):
        prep = "in" if _BARE_MONTH_YEAR_OR_YEAR_RE.match(raw_out) else "by"
        return f"The chance {raw_title} {prep} {raw_out}"

    phrase = _prose_market_phrase(raw_title, capitalize_first=False)
    if raw_out.lower() in {"yes", "no", ""}:
        trimmed = phrase[4:] if phrase.startswith("the ") else phrase
        return f"The chance of {trimmed}"
    return f"The chance {raw_out} leads {phrase}"


def _build_dynamic_title_from_set(
    definition: Mapping[str, Any],
    built_sections: Sequence[Mapping[str, Any]],
) -> str:
    """Build a reader-facing title dynamically from the live set (Slice 3 Item 4).

    Every number and name comes directly from ``built_sections``:
    - Paired-stage ceremony: ``"<Leader> leads <Category> at <W>%, with <N> contenders at 75% or better to be nominated"``
    - Event-led slate: ``"<Away> at <Home> headlines <Dates>, with <N> toss-up games"`` (never a week number)
    - Duel + contender field: ``"<Leader> leads at <P>%, with <DuelLeader> at <D>%"``
    - Scale / market set: ``"<LeadOutcome> leads <LeadTitle> at <P>%, with <SecondTitle> at <Lead2> (<P2>%)"``
    """
    if not built_sections:
        return str(definition.get("name") or definition.get("slug") or "Round-Up")

    # 1. Paired-stage lead (e.g. Oscars Best Picture)
    for sec in built_sections:
        vb = sec.get("visual_block") or {}
        if vb.get("form_id") == "paired_stage_bars" and isinstance(vb.get("paired_metric_set"), Mapping):
            pset = vb["paired_metric_set"]
            entries = list(pset.get("entries") or ())
            if entries:
                top = entries[0]
                leader_name = str(top.get("subject") or "").strip()
                allocated = top.get("stage_2_rendered_percent")
                win_pct = int(allocated) if allocated is not None else _half_up_pct(
                    float(top.get("stage_2_probability") or 0.0)
                )
                strong_nom = sum(
                    1
                    for e in entries
                    if isinstance(e.get("stage_1_probability"), (int, float))
                    and float(e["stage_1_probability"]) >= 0.75
                )
                raw_sec_title = str(sec.get("title") or "Best Picture")
                if leader_name and raw_sec_title.lower().startswith(leader_name.lower()):
                    cat_label = str(
                        (pset.get("stage_2_market") or {}).get("category_name")
                        or "Best Picture"
                    )
                else:
                    cat_label = re.sub(r":.*$", "", raw_sec_title).strip()
                if strong_nom >= 2:
                    return f"{leader_name} leads {cat_label} at {win_pct}%, with {strong_nom} contenders at 75% or better to be nominated"
                return f"{leader_name} leads {cat_label} at {win_pct}%"

    # 2. Event-led slate (e.g. NFL/NBA slate — named by biggest/closest game & dates, never week number)
    # Ruling 253: A: count ONLY games inside the <=55% toss-up band shown on the card,
    # and lead with the closest visible game; with fewer than 2 toss-ups, drop the clause.
    rule_dict_ev = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
    card_sec_key_ev = str(rule_dict_ev.get("card_section_key") or "").strip()
    card_rows_limit_ev = max(1, int(rule_dict_ev.get("card_rows") or 3))
    event_items: list[Mapping[str, Any]] = []
    seen_event_ids: set[int] = set()
    card_event_items: list[Mapping[str, Any]] = []
    for sec in built_sections:
        vb = sec.get("visual_block") or {}
        if vb.get("form_id") in {"coin_flip_matchups", "matchup_slate"}:
            its = [it for it in (vb.get("items") or ()) if isinstance(it, Mapping)]
            sec_cls = str(sec.get("class") or "").strip()
            if not card_event_items and (not card_sec_key_ev or sec_cls == card_sec_key_ev):
                card_event_items = its[:card_rows_limit_ev]
            for it in its:
                eid = int(it.get("event_id") or 0)
                if eid > 0 and eid in seen_event_ids:
                    continue
                if eid > 0:
                    seen_event_ids.add(eid)
                event_items.append(it)
    if event_items:
        visible_events = card_event_items or event_items[:card_rows_limit_ev]
        tossup_count = sum(1 for it in visible_events if _is_event_toss_up(it))
        lead_ev = min(
            visible_events,
            key=lambda it: (
                float(it.get("closeness_to_50", abs(float(it.get("home_prob", 0.5)) - 0.5))),
                str(it.get("commence_time") or ""),
            ),
        )
        matchup = f"{lead_ev.get('away_short') or lead_ev.get('away_team')} at {lead_ev.get('home_short') or lead_ev.get('home_team')}"
        span = _format_event_date_span(event_items)
        span_clause = f" the {span} slate" if span else " this slate"
        if tossup_count >= TOSS_UP_MIN_SECTION_COUNT:
            return f"{matchup} headlines{span_clause}, with {tossup_count} toss-up games"
        return f"{matchup} headlines{span_clause}"

    # 3. Market-led sets (duel + contender field, numerical-scale rate set,
    # benchmark strip, or sibling field grid)
    duel_item: Optional[Mapping[str, Any]] = None
    spotlight_item: Optional[Mapping[str, Any]] = None
    sibling_items: list[Mapping[str, Any]] = []
    benchmark_items: list[Mapping[str, Any]] = []
    history_items: list[Mapping[str, Any]] = []
    lead_sec_form = str((built_sections[0].get("visual_block") or {}).get("form_id") or "")
    for sec in built_sections:
        vb = sec.get("visual_block") or {}
        fid = vb.get("form_id")
        its = [it for it in (vb.get("items") or ()) if isinstance(it, Mapping)]
        if fid == "duel_bar" and its and duel_item is None:
            duel_item = its[0]
        elif fid == "contender_spotlight" and its and spotlight_item is None:
            spotlight_item = its[0]
        elif fid == "sibling_fields_grid" and its:
            sibling_items.extend(its)
        elif fid == "benchmark_strip" and its:
            benchmark_items.extend(its)
        elif fid == "probability_history_chart" and its:
            history_items.extend(its)

    def _fav_outcome(m_item: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        outs = [o for o in (m_item.get("outcomes") or ()) if isinstance(o, Mapping)]
        if not outs:
            return None
        return max(outs, key=lambda o: float(o.get("probability") or 0.0))

    if spotlight_item is None and duel_item is not None and lead_sec_form == "duel_bar":
        d_outs = sorted(
            [o for o in (duel_item.get("outcomes") or ()) if isinstance(o, Mapping)],
            key=lambda o: -float(o.get("probability") or 0.0),
        )
        if len(d_outs) >= 2:
            lead_name = _prose_outcome_name(str(d_outs[0]["name"]))
            trail_name = _prose_outcome_name(str(d_outs[1]["name"]))
            lead_p = int(d_outs[0]["rendered_percent"])
            trail_p = int(d_outs[1]["rendered_percent"])
            du_phrase = _prose_market_phrase(str(duel_item["title"]))
            return f"{lead_name} leads {trail_name} {lead_p}%–{trail_p}% in {du_phrase}"

    if history_items and (
        lead_sec_form == "probability_history_chart"
        or (spotlight_item is None and not sibling_items and not benchmark_items)
    ):
        lead_h = history_items[0]
        best_net = 0
        best_series: Optional[Mapping[str, Any]] = None
        best_start_iso = str(lead_h.get("start_iso") or "")
        best_range_span = 0
        best_range_lo = 0
        best_range_hi = 0
        best_range_series: Optional[Mapping[str, Any]] = None
        best_range_start_iso = str(lead_h.get("start_iso") or "")
        for hs in lead_h.get("series") or ():
            if not isinstance(hs, Mapping):
                continue
            pts_raw = [
                pt
                for pt in (hs.get("points") or ())
                if isinstance(pt, Mapping) and isinstance(pt.get("pct"), (int, float))
            ]
            if len(pts_raw) >= 2:
                pcts_vals = [int(pt["pct"]) for pt in pts_raw]
                net = pcts_vals[-1] - pcts_vals[0]
                if abs(net) > abs(best_net):
                    best_net = net
                    best_series = hs
                    best_start_iso = str(pts_raw[0].get("t") or best_start_iso)
                lo_v = min(pcts_vals)
                hi_v = max(pcts_vals)
                span_v = hi_v - lo_v
                if span_v > best_range_span:
                    best_range_span = span_v
                    best_range_lo = lo_v
                    best_range_hi = hi_v
                    best_range_series = hs
                    best_range_start_iso = str(pts_raw[0].get("t") or best_range_start_iso)
        if best_series is not None and abs(best_net) >= 10:
            start_label = _format_history_start_date(best_start_iso)
            clause = _format_history_chance_clause(
                str(lead_h.get("title") or ""),
                str(best_series.get("name") or ""),
            )
            direction = "rose" if best_net > 0 else "fell"
            since_suffix = f" since {start_label}" if start_label else ""
            return f"{clause} {direction} {abs(best_net)} points{since_suffix}"
        if best_range_series is not None and best_range_span >= 1:
            start_label = _format_history_start_date(best_range_start_iso)
            clause = _format_history_chance_clause(
                str(lead_h.get("title") or ""),
                str(best_range_series.get("name") or ""),
            )
            since_suffix = f" since {start_label}" if start_label else ""
            return f"{clause} has ranged from {best_range_lo}% to {best_range_hi}%{since_suffix}"
        start_label = _format_history_start_date(best_start_iso)
        h_phrase = _prose_market_phrase(str(lead_h.get("title") or ""), capitalize_first=True)
        since_suffix = f" since {start_label}" if start_label else ""
        return f"The chance on {h_phrase} shifted{since_suffix}"

    if spotlight_item is not None and duel_item is not None:
        sp_fav = _fav_outcome(spotlight_item)
        du_fav = _fav_outcome(duel_item)
        if sp_fav and du_fav:
            sp_phrase = _prose_market_phrase(str(spotlight_item["title"]))
            du_name = _prose_outcome_name(str(du_fav["name"]))
            return (
                f"{_prose_outcome_name(str(sp_fav['name']))} leads {sp_phrase} at {sp_fav['rendered_percent']}%, "
                f"with {du_name} at {du_fav['rendered_percent']}%"
            )

    if spotlight_item is not None:
        sp_fav = _fav_outcome(spotlight_item)
        if sp_fav and sibling_items:
            sib_fav = _fav_outcome(sibling_items[0])
            if sib_fav:
                sp_phrase = _prose_market_phrase(str(spotlight_item["title"]))
                sib_phrase = _prose_market_phrase(str(sibling_items[0]["title"]))
                lead_outcome = _prose_rate_outcome(str(sp_fav["name"]), capitalize_first=True)
                sib_outcome = _prose_rate_outcome(str(sib_fav["name"]), capitalize_first=False)
                return (
                    f"{lead_outcome} leads {sp_phrase} at {sp_fav['rendered_percent']}%, "
                    f"with {sib_outcome} leading {sib_phrase} at {sib_fav['rendered_percent']}%"
                )
        if sp_fav:
            sp_phrase = _prose_market_phrase(str(spotlight_item["title"]))
            return f"{_prose_rate_outcome(str(sp_fav['name']), capitalize_first=True)} leads {sp_phrase} at {sp_fav['rendered_percent']}%"

    if benchmark_items:
        rule_dict = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
        headline_pool = _filter_card_benchmark_items(benchmark_items, rule_dict)
        if rule_dict.get("headline_exclude_date_rows"):
            non_date = [it for it in headline_pool if not it.get("is_date_timing_row")]
            if non_date:
                headline_pool = non_date
        lead_bm = headline_pool[0]
        lead_o = _fav_outcome(lead_bm)
        group_name = str(definition.get("name") or "").strip().rstrip("?")
        rule_pred = str(rule_dict.get("headline_predicate") or "").strip()
        rule_secs = rule_dict.get("sections")
        first_sec = rule_secs[0] if isinstance(rule_secs, Sequence) and rule_secs else {}
        item_noun = str((first_sec.get("item_noun") if isinstance(first_sec, Mapping) else None) or "categories").strip()
        if lead_o is not None:
            lead_phrase = str(lead_bm.get("headline_phrase") or "").strip().rstrip("?").strip()
            lead_t = (lead_phrase or str(lead_bm.get("title") or "").strip()).rstrip("?").strip()
            lead_p = int(lead_o["rendered_percent"])
            verb = "lead" if " & " in lead_t else "leads"
            if lead_phrase and "{pct}" in lead_phrase:
                lead_clause = lead_phrase.replace("{pct}", str(lead_p))
            elif lead_phrase:
                lead_clause = f"{lead_phrase} is at {lead_p}%"
            elif rule_pred:
                lead_clause = f"{lead_t} {rule_pred} at {lead_p}%"
            elif group_name:
                lead_clause = f"{lead_t} {verb} {group_name} at {lead_p}%"
            else:
                lead_clause = f"{lead_t} {verb} at {lead_p}%"
            if len(headline_pool) >= 2:
                lead_ans_raw = str(lead_o.get("name") or "").strip()
                lead_ans_key = _norm_key(lead_ans_raw)
                lead_is_date_or_bool = lead_ans_key in {"yes", "no"} or bool(
                    _PREP_DATE_OUTCOME_RE.match(lead_ans_raw)
                    or _BARE_MONTH_DAY_RE.match(lead_ans_raw)
                    or _BARE_MONTH_YEAR_OR_YEAR_RE.match(lead_ans_raw)
                )
                sec_bm = headline_pool[1]
                sec_o = _fav_outcome(sec_bm)

                def _sec_text_for(item_bm: Mapping[str, Any]) -> str:
                    return (
                        str(item_bm.get("headline_with_phrase") or "").strip()
                        or str(item_bm.get("headline_phrase") or "").strip()
                        or str(item_bm.get("title") or "").strip()
                    ).rstrip("?").strip()

                sec_t_initial = _sec_text_for(sec_bm)
                repeats_lead_answer = bool(
                    lead_ans_key
                    and not lead_is_date_or_bool
                    and len(lead_ans_raw) >= 3
                    and lead_ans_raw.lower() in lead_clause.lower()
                    and lead_ans_raw.lower() in sec_t_initial.lower()
                )
                if repeats_lead_answer:
                    for cand_bm in headline_pool[1:]:
                        cand_o = _fav_outcome(cand_bm)
                        if cand_o is None:
                            continue
                        cand_sec_t = _sec_text_for(cand_bm)
                        if (
                            _norm_key(str(cand_o.get("name") or "")) != lead_ans_key
                            and lead_ans_raw.lower() not in cand_sec_t.lower()
                        ):
                            sec_bm = cand_bm
                            sec_o = cand_o
                            break
                    else:
                        same_count = sum(
                            1
                            for it in headline_pool
                            if (_fav_outcome(it) or {}).get("name")
                            and _norm_key(str((_fav_outcome(it) or {})["name"])) == lead_ans_key
                        )
                        if same_count >= 2:
                            if lead_phrase or not rule_pred:
                                return f"{lead_phrase or lead_t} is at {lead_p}%, leading {same_count} of {len(headline_pool)} {item_noun}"
                            return f"{lead_t} {rule_pred} at {lead_p}%, with {lead_ans_raw} leading {same_count} of {len(headline_pool)} {item_noun}"
                if sec_o is not None:
                    sec_t = _sec_text_for(sec_bm)
                    sec_p = int(sec_o["rendered_percent"])
                    if "{pct}" in sec_t:
                        return f"{lead_clause}, and {sec_t.replace('{pct}', str(sec_p))}"
                    return f"{lead_clause}, with {sec_t} at {sec_p}%"
            return lead_clause

    if sibling_items:
        lead_sib = sibling_items[0]
        lead_o = _fav_outcome(lead_sib)
        if lead_o is not None:
            lead_name = _prose_outcome_name(str(lead_o["name"]))
            lead_title = str(lead_sib.get("title") or "").strip()
            lead_p = int(lead_o["rendered_percent"])
            _CASTING_ROLES = {
                "james bond",
                "m",
                "q",
                "moneypenny",
                "bond girl",
                "villain",
                "main villain",
            }
            if len(sibling_items) >= 2:
                sec_sib = sibling_items[1]
                sec_o = _fav_outcome(sec_sib)
                if sec_o is not None:
                    sec_name = _prose_outcome_name(str(sec_o["name"]))
                    sec_title = str(sec_sib.get("title") or "").strip()
                    sec_p = int(sec_o["rendered_percent"])
                    sec_verb = (
                        "to play"
                        if sec_title.lower() in _CASTING_ROLES
                        else "leading"
                    )
                    return f"{lead_name} leads {lead_title} at {lead_p}%, with {sec_name} {sec_verb} {sec_title} at {sec_p}%"
            return f"{lead_name} leads {lead_title} at {lead_p}%"

    return str(definition.get("name") or definition.get("slug") or "Round-Up")


def _unify_grouping_diacritic_names(sections: Sequence[Mapping[str, Any]]) -> None:
    """Ensure a subject never appears under two diacritic/ASCII spellings within one grouping
    (e.g. 'Luka Dončić' in stat leaders vs 'Luka Doncic' in MVP tiles).
    """
    variants_by_fold: dict[str, list[str]] = {}
    for sec in sections:
        vb = sec.get("visual_block") if isinstance(sec, Mapping) else None
        if not isinstance(vb, Mapping):
            continue
        for item in vb.get("items") or ():
            if not isinstance(item, Mapping):
                continue
            if "subject" in item and isinstance(item.get("subject"), str):
                fk = _ascii_fold_key(item["subject"])
                if fk:
                    variants_by_fold.setdefault(fk, []).append(item["subject"])
            for o in item.get("outcomes") or ():
                if isinstance(o, Mapping) and isinstance(o.get("name"), str):
                    fk = _ascii_fold_key(o["name"])
                    if fk:
                        variants_by_fold.setdefault(fk, []).append(o["name"])
            for s in item.get("series") or ():
                if isinstance(s, Mapping) and isinstance(s.get("name"), str):
                    fk = _ascii_fold_key(s["name"])
                    if fk:
                        variants_by_fold.setdefault(fk, []).append(s["name"])

    preferred_by_fold: dict[str, str] = {}
    for fk, names in variants_by_fold.items():
        if len(set(names)) > 1:
            pref = _pick_preferred_subject_spelling(names)
            if pref:
                preferred_by_fold[fk] = pref
    if not preferred_by_fold:
        return

    for sec in sections:
        vb = sec.get("visual_block") if isinstance(sec, Mapping) else None
        if not isinstance(vb, Mapping):
            continue
        for item in vb.get("items") or ():
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("subject"), str):
                fk = _ascii_fold_key(item["subject"])
                if fk in preferred_by_fold:
                    item["subject"] = preferred_by_fold[fk]
            for o in item.get("outcomes") or ():
                if isinstance(o, dict) and isinstance(o.get("name"), str):
                    fk = _ascii_fold_key(o["name"])
                    if fk in preferred_by_fold:
                        o["name"] = preferred_by_fold[fk]
            for s in item.get("series") or ():
                if isinstance(s, dict) and isinstance(s.get("name"), str):
                    fk = _ascii_fold_key(s["name"])
                    if fk in preferred_by_fold:
                        s["name"] = preferred_by_fold[fk]


async def produce_container_machinery(
    db: Any,
    definition: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Any:
    """Evaluate a declarative ``container_machinery`` definition into card + multi-section container."""
    from app.utils.roundup_containers import RoundupMembers, RoundupRefusal

    now_dt = now or datetime.now(timezone.utc)
    base_resolver = _default_art_resolver()
    rule = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
    sections_cfg = rule.get("sections") or ()
    if not isinstance(sections_cfg, Sequence) or not sections_cfg:
        return RoundupRefusal((("container_machinery", "empty_sections"),))

    snapshot = await _load_snapshot_from_db(db, definition, now_dt)
    snap_team_lookup = snapshot.get("team_lookup")
    resolver = (
        SubjectArtResolver(
            team_lookup=snap_team_lookup,
            _static_by_norm=base_resolver._by_norm,
        )
        if snap_team_lookup is not None
        else base_resolver
    )
    all_events = snapshot["events"]
    all_markets = snapshot["markets"]
    paired_sets = snapshot["paired_sets"]
    market_histories = snapshot["market_histories"]

    built_by_idx: dict[int, dict[str, Any]] = {}
    all_member_envelopes: list[dict[str, Any]] = []
    seen_member_keys: set[tuple[str, int]] = set()
    seen_twin_keys: set[str] = set()
    covered_twin_market_ids: list[int] = []
    lead_paired_set: Optional[dict[str, Any]] = None

    def _record_covered_twins(item: Mapping[str, Any]) -> None:
        t_key = _twin_market_key(str(item.get("title") or ""))
        if t_key:
            seen_twin_keys.add(t_key)
        for twin_mid in item.get("_twin_market_ids") or ():
            if (
                isinstance(twin_mid, int)
                and not isinstance(twin_mid, bool)
                and twin_mid not in covered_twin_market_ids
            ):
                covered_twin_market_ids.append(twin_mid)
                seen_member_keys.add((MEMBER_MARKET, twin_mid))

    def _filter_unseen_twins(items_in: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        kept: list[dict[str, Any]] = []
        for it in items_in:
            t_key = _twin_market_key(str(it.get("title") or ""))
            if t_key and t_key in seen_twin_keys:
                mid = it.get("market_id")
                if isinstance(mid, int) and not isinstance(mid, bool) and mid not in covered_twin_market_ids:
                    covered_twin_market_ids.append(mid)
                _record_covered_twins(it)
                continue
            kept.append(it)
        return kept

    indexed_cfg = [
        (idx, sec_cfg)
        for idx, sec_cfg in enumerate(sections_cfg)
        if isinstance(sec_cfg, Mapping)
    ]
    # Primary sections (paired_stage, events, markets) claim their canonical IDs first;
    # market_history sections claim disjoint companion markets while keeping their configured visual slot.
    eval_order = sorted(
        indexed_cfg,
        key=lambda pair: (
            1
            if str(((pair[1].get("atom_query") or {}) if isinstance(pair[1].get("atom_query"), Mapping) else {}).get("kind") or "")
            == "market_history"
            else 0,
            pair[0],
        ),
    )

    for sec_idx, sec_cfg in eval_order:
        sec_key = str(sec_cfg.get("key") or "section")
        sec_title = str(sec_cfg.get("title") or definition.get("section_title") or "Markets")
        sec_note = str(sec_cfg.get("note") or "").strip() or None
        aq = sec_cfg.get("atom_query") if isinstance(sec_cfg.get("atom_query"), Mapping) else {}
        aq_kind = str(aq.get("kind") or "markets")
        min_items = int(aq.get("min_items", 1))
        max_items = int(aq.get("max_items", 6))
        max_outcomes = int(aq.get("max_outcomes", 6))
        initial_visible = min(3, int(aq.get("initial_visible_limit", 3)))

        if aq_kind == "paired_stage":
            from app.services.paired_metric_register import (
                clean_card_face_title,
                fold_outcome_key,
            )

            pset = _match_paired_set(paired_sets, aq)
            if pset is None:
                return RoundupRefusal((("container_machinery", f"missing_paired_stage:{sec_key}"),))
            entries = [
                dict(e)
                for e in (pset.get("entries") or ())
                if isinstance(e, Mapping)
                and isinstance(e.get("stage_2_probability"), (int, float))
                and math.isfinite(float(e["stage_2_probability"]))
            ]
            if len(entries) < min_items:
                return RoundupRefusal((("container_machinery", f"too_few_paired_entries:{sec_key}"),))
            pset["entries"] = entries[:max_items]
            form_id = choose_section_form("paired_stage", pset["entries"])
            s2_meta = pset.get("stage_2_market") if isinstance(pset.get("stage_2_market"), Mapping) else {}
            s1_meta = pset.get("stage_1_market") if isinstance(pset.get("stage_1_market"), Mapping) else {}
            explicit_mpn_map = (
                pset.get("member_page_numbers_by_market")
                if isinstance(pset.get("member_page_numbers_by_market"), Mapping)
                else {}
            )
            sec_members: list[dict[str, Any]] = []
            for stage_idx, m_meta in ((2, s2_meta), (1, s1_meta)):
                mid = int(m_meta.get("id") or 0)
                if mid <= 0:
                    continue
                prob_field = f"stage_{stage_idx}_probability"
                oid_field = f"stage_{stage_idx}_outcome_id"
                rp_field = f"stage_{stage_idx}_rendered_percent"
                if mid in explicit_mpn_map:
                    stage_mpn = copy.deepcopy(dict(explicit_mpn_map[mid]))
                else:
                    by_oid: dict[int, int] = {}
                    by_key: dict[str, int] = {}
                    by_fold: dict[str, int] = {}
                    for e in pset["entries"]:
                        p_val = e.get(prob_field)
                        if not isinstance(p_val, (int, float)) or not math.isfinite(float(p_val)):
                            continue
                        allocated = e.get(rp_field)
                        pct_val = int(allocated) if allocated is not None else _half_up_pct(float(p_val))
                        oid_val = e.get(oid_field)
                        if isinstance(oid_val, int):
                            by_oid[int(oid_val)] = pct_val
                        subj = str(e.get("subject") or "")
                        nk = _norm_key(subj)
                        if nk and nk not in by_key:
                            by_key[nk] = pct_val
                        fk = fold_outcome_key(subj)
                        if fk and fk not in by_fold:
                            by_fold[fk] = pct_val
                    stage_mpn = {
                        "by_outcome_id": by_oid,
                        "by_outcome_key": by_key,
                        "by_fold_key": by_fold,
                    }
                synthetic_card = {
                    "id": mid,
                    "name": clean_card_face_title(str(m_meta.get("name") or sec_title)),
                    "status": "open",
                    "source": str(m_meta.get("source") or "kalshi"),
                    "content_kind": "futures",
                    "member_page_numbers": stage_mpn,
                    "top_outcomes": [
                        {
                            "name": str(e.get("subject") or ""),
                            "probability": float(e.get(prob_field) or 0.0),
                        }
                        for e in pset["entries"][:5]
                        if isinstance(e.get(prob_field), (int, float))
                    ],
                }
                env = {
                    "type": MEMBER_MARKET,
                    "id": mid,
                    "destination": market_destination(mid),
                    "card": synthetic_card,
                }
                sec_members.append(env)
                if (MEMBER_MARKET, mid) not in seen_member_keys:
                    seen_member_keys.add((MEMBER_MARKET, mid))
                    all_member_envelopes.append(env)
            if lead_paired_set is None:
                lead_paired_set = copy.deepcopy(pset)
                lead_paired_set["suppress_card_header_in_section"] = False
            section_pset = copy.deepcopy(pset)
            # Slice 6 Item 2a: embedded paired card inside a container section never repeats the headline.
            section_pset["suppress_card_header_in_section"] = True
            built_by_idx[sec_idx] = {
                "class": sec_key,
                "title": sec_title,
                "note": sec_note,
                "layout": form_id,
                "members": sec_members,
                "visual_block": {
                    "form_id": form_id,
                    "initial_visible_limit": initial_visible,
                    "paired_metric_set": section_pset,
                    "items": [],
                },
            }
            continue

        if aq_kind == "events":
            sport_req = str(aq.get("sport_key") or "").lower()
            include_completed = bool(aq.get("include_completed", False))
            exclude_decided = bool(aq.get("exclude_decided", False))
            band = aq.get("probability_band")
            band_lo = float(band[0]) if isinstance(band, Sequence) and len(band) == 2 else 0.0
            band_hi = float(band[1]) if isinstance(band, Sequence) and len(band) == 2 else 1.0
            ev_items: list[dict[str, Any]] = []
            for raw_ev in all_events:
                if sport_req and str(raw_ev.get("sport") or "").lower() != sport_req:
                    continue
                ev_status = str(raw_ev.get("status") or "").strip().lower()
                if not include_completed and ev_status in {
                    "completed",
                    "final",
                    "closed",
                    "finished",
                    "cancelled",
                    "postponed",
                }:
                    continue
                if (MEMBER_EVENT, int(raw_ev["id"])) in seen_member_keys:
                    continue
                hyd = _hydrate_event_visual_item(raw_ev, resolver=resolver)
                if hyd is None:
                    continue
                if (
                    not include_completed
                    and exclude_decided
                    and max(int(hyd["away_pct"]), int(hyd["home_pct"])) >= 100
                ):
                    continue
                if not (band_lo <= hyd["home_prob"] <= band_hi):
                    continue
                ev_items.append(hyd)
            order_by = str(aq.get("order_by") or "kickoff_asc")
            if order_by == "closeness_to_50":
                # Fable 2026-11-18 Rule 3: no row may show a started game with only
                # its scheduled time. Hold only unstarted games in closest-games /
                # Coin-Flip Matchups whenever >= min_items unstarted games exist
                # (live games render with full LIVE + score cards in Live & Upcoming
                # Matchups). If fewer than min_items unstarted games remain on the
                # slate, keep the live games and `choose_section_form` forces
                # `matchup_slate` so both web and iOS 1.0.7 draw full LIVE score cards.
                unstarted_items = [
                    it
                    for it in ev_items
                    if str(it.get("status") or "").strip().lower()
                    not in {"live", "in_progress", "halftime"}
                ]
                if len(unstarted_items) >= min_items:
                    ev_items = unstarted_items
                # Goal Step 7 (#12288): do not lead with thin venue/ESPN-only games
                # when games priced by sportsbooks exist on the slate.
                sb_items = [it for it in ev_items if it.get("has_sportsbook")]
                if len(sb_items) >= min_items:
                    ev_items = sb_items
                ev_items.sort(
                    key=lambda x: (
                        not bool(x.get("has_sportsbook")),
                        x["closeness_to_50"],
                        x["commence_time"],
                    )
                )
                # Ruling 253: A — "Toss-up" means neither side above 55%.
                # When >= 2 games are inside the band, feature ONLY those true toss-ups.
                # With fewer than 2, rename the section to "Closest games", strip all
                # TOSS-UP tags, and choose the non-toss-up slate form (so iOS 1.0.7 and
                # web both show clean matchup rows with zero TOSS-UP badges).
                in_band_items = [it for it in ev_items if _is_event_toss_up(it)]
                if len(in_band_items) >= TOSS_UP_MIN_SECTION_COUNT:
                    ev_items = in_band_items[:max_items]
                    for it in ev_items:
                        it["show_toss_up_tag"] = True
                else:
                    ev_items = ev_items[:max_items]
                    sec_title = "Closest games"
                    sec_note = "Closest matchups on this slate."
                    for it in ev_items:
                        it["show_toss_up_tag"] = False
            else:
                ev_items.sort(key=lambda x: x["commence_time"])
                ev_items = ev_items[:max_items]
            if len(ev_items) < min_items:
                return RoundupRefusal((("container_machinery", f"too_few_events:{sec_key}"),))
            # Games-in-play dynamic heading rule (Fable 2026-11-18):
            # Never show live games under "Upcoming Matchups".
            if sec_title.strip().lower().startswith("upcoming"):
                live_count = sum(
                    1
                    for it in ev_items
                    if str(it.get("status") or "").strip().lower() == "live"
                )
                if live_count > 0 and live_count == len(ev_items):
                    sec_title = "Live Now"
                    sec_note = "Live scores and win chances."
                elif live_count > 0:
                    sec_title = "Live & Upcoming Matchups"
                    sec_note = "Live scores and upcoming games in start-time order."
            form_id = choose_section_form("events", ev_items)
            sec_members = []
            for it in ev_items:
                eid = it["event_id"]
                public_card = {
                    k: v for k, v in it["card"].items() if not str(k).startswith("_")
                }
                dest = event_destination(eid)
                sec_members.append(
                    {
                        "type": MEMBER_EVENT,
                        "id": eid,
                        "destination": dest,
                        "card": public_card,
                        "event_id": eid,
                    }
                )
                if (MEMBER_EVENT, eid) not in seen_member_keys:
                    seen_member_keys.add((MEMBER_EVENT, eid))
                    all_member_envelopes.append(
                        {
                            "type": MEMBER_EVENT,
                            "id": eid,
                            "destination": dest,
                            "card": it["card"],
                            "event_id": eid,
                        }
                    )
            built_by_idx[sec_idx] = {
                "class": sec_key,
                "title": sec_title,
                "note": sec_note,
                "layout": form_id,
                "members": sec_members,
                "visual_block": {
                    "form_id": form_id,
                    "initial_visible_limit": initial_visible,
                    "items": [
                        {k: v for k, v in it.items() if k != "card"}
                        for it in ev_items
                    ],
                },
            }
            continue

        if aq_kind == "market_history":
            hours = int(aq.get("hours") or 168)
            fun_sub_tag_val = str(aq.get("fun_sub_tag") or "").strip() or None
            date_ladder_pick_val = str(aq.get("date_ladder_pick") or "").strip() or None
            matched_h = [
                _hydrate_market_visual_item(
                    m,
                    max_outcomes=max_outcomes,
                    resolver=resolver,
                    content_kind="history",
                    use_fun_short_label=bool(fun_sub_tag_val),
                    fun_sub_tag=fun_sub_tag_val,
                    sport_key=_infer_sports_key_for_market(m, definition),
                    allow_team_lookup=_is_sports_context(m, definition),
                    now_dt=now_dt,
                    date_ladder_pick=date_ladder_pick_val,
                )
                for m in all_markets
                if (MEMBER_MARKET, int(m["id"])) not in seen_member_keys
                and _market_matches_query(m, aq, now_dt=now_dt)
            ]
            matched_h = _filter_unseen_twins(_dedupe_twin_markets(matched_h))
            order_by = str(aq.get("order_by") or "movement_desc")
            if order_by == "closeness_to_50":
                matched_h.sort(key=lambda x: (x["closeness_to_50"], -x["lead_prob"]))
            else:
                matched_h.sort(key=lambda x: (-x["lead_prob"], x["title"].casefold()))
            if len(matched_h) < min_items:
                return RoundupRefusal((("container_machinery", f"too_few_history_markets:{sec_key}"),))
            all_chart_items = []
            for hm in matched_h:
                ci = _build_history_visual_item(hm, market_histories, now_dt=now_dt, hours=hours)
                if hm.get("_twin_market_ids"):
                    ci["_twin_market_ids"] = list(hm["_twin_market_ids"])
                all_chart_items.append(ci)
            rule_card_sec = str((definition.get("rule") or {}).get("card_section_key") or "").strip()
            is_card_hist_sec = (sec_key == rule_card_sec) if rule_card_sec else (sec_idx == 0)
            hist_min_swing = int(aq.get("min_swing_pp") or (10 if is_card_hist_sec else 3))
            moving_charts = [
                ci for ci in all_chart_items if _history_chart_moved(ci, min_swing_pp=hist_min_swing)
            ]
            if order_by == "movement_desc":
                moving_charts.sort(
                    key=lambda ci: (-int(ci.get("max_swing_pp") or 0), ci["title"].casefold())
                )
            if len(moving_charts) >= min_items:
                chart_items = moving_charts[:max_items]
                form_id = choose_section_form("market_history", chart_items)
                eff_title, eff_note = _resolve_section_heading(
                    sec_cfg,
                    aq_kind="market_history",
                    form_id=form_id,
                    rendered_items=chart_items,
                    visible_limit=initial_visible,
                    default_title=sec_title,
                )
                sec_members = []
                for ci in chart_items:
                    mid = int(ci["market_id"])
                    _record_covered_twins(ci)
                    env = {
                        "type": MEMBER_MARKET,
                        "id": mid,
                        "destination": market_destination(mid),
                        "card": ci["card"],
                    }
                    sec_members.append(env)
                    if (MEMBER_MARKET, mid) not in seen_member_keys:
                        seen_member_keys.add((MEMBER_MARKET, mid))
                        all_member_envelopes.append(env)
                built_by_idx[sec_idx] = {
                    "class": sec_key,
                    "title": eff_title,
                    "note": eff_note,
                    "layout": form_id,
                    "members": sec_members,
                    "visual_block": {
                        "form_id": form_id,
                        "initial_visible_limit": initial_visible,
                        "items": [
                            {k: v for k, v in ci.items() if k not in ("card", "_twin_market_ids")}
                            for ci in chart_items
                        ],
                    },
                }
            else:
                # Slice 4 & Slice 5 Note 4: when no matched market moved, switch BOTH form AND section copy.
                if order_by == "movement_desc":
                    matched_h.sort(key=lambda x: (x["closeness_to_50"], -x["lead_prob"]))
                fallback_matched = matched_h[:max_items]
                for fm_it in fallback_matched:
                    fm_it["content_kind"] = "futures"
                    if isinstance(fm_it.get("card"), dict):
                        fm_it["card"]["content_kind"] = "futures"
                form_id = choose_section_form("markets", fallback_matched)
                if form_id in {"sibling_fields_grid", "contender_spotlight"}:
                    tile_cap = 3 if form_id == "contender_spotlight" else 1
                    all_tiles_pictured = all(
                        _has_verified_art(o)
                        for fm_it in fallback_matched
                        for o in (fm_it.get("outcomes") or ())[:tile_cap]
                    )
                    if not all_tiles_pictured:
                        form_id = "benchmark_strip"
                if form_id == "benchmark_strip" and max_outcomes > 1:
                    for fm_it in fallback_matched:
                        outs = list(fm_it.get("outcomes") or ())[:1]
                        fm_it["outcomes"] = outs
                        if outs:
                            lead_name = str(outs[0].get("name") or "").strip()
                            fm_it["title"] = _format_benchmark_row_title(
                                str(fm_it.get("title") or ""),
                                lead_name,
                                headline_phrase=fm_it.get("headline_phrase"),
                            )
                        if isinstance(fm_it.get("card"), dict):
                            fm_it["card"]["outcomes"] = [dict(o) for o in outs]
                            fm_it["card"]["name"] = str(
                                fm_it.get("title") or fm_it["card"].get("name") or ""
                            )
                eff_title, eff_note = _resolve_section_heading(
                    sec_cfg,
                    aq_kind="market_history",
                    form_id=form_id,
                    rendered_items=fallback_matched,
                    visible_limit=initial_visible,
                    default_title=sec_title,
                )
                sec_members = []
                for fm_it in fallback_matched:
                    mid = int(fm_it["market_id"])
                    _record_covered_twins(fm_it)
                    env = {
                        "type": MEMBER_MARKET,
                        "id": mid,
                        "destination": market_destination(mid),
                        "card": fm_it["card"],
                    }
                    sec_members.append(env)
                    if (MEMBER_MARKET, mid) not in seen_member_keys:
                        seen_member_keys.add((MEMBER_MARKET, mid))
                        all_member_envelopes.append(env)
                built_by_idx[sec_idx] = {
                    "class": sec_key,
                    "title": eff_title,
                    "note": eff_note,
                    "layout": form_id,
                    "members": sec_members,
                    "visual_block": {
                        "form_id": form_id,
                        "initial_visible_limit": initial_visible,
                        "items": [
                            {
                                k: v
                                for k, v in fm_it.items()
                                if k not in ("card", "_twin_market_ids", "_volume")
                            }
                            for fm_it in fallback_matched
                        ],
                    },
                }
            continue

        # aq_kind == "markets"
        explicit_ck = str(aq.get("content_kind") or "").strip().lower() or None
        fun_sub_tag_val = str(aq.get("fun_sub_tag") or "").strip() or None
        use_fun_short = bool(fun_sub_tag_val)
        date_ladder_pick_val = str(aq.get("date_ladder_pick") or "").strip() or None
        matched = [
            _hydrate_market_visual_item(
                m,
                max_outcomes=max_outcomes,
                resolver=resolver,
                content_kind=explicit_ck,
                use_fun_short_label=use_fun_short,
                fun_sub_tag=fun_sub_tag_val,
                sport_key=_infer_sports_key_for_market(m, definition),
                allow_team_lookup=_is_sports_context(m, definition),
                now_dt=now_dt,
                date_ladder_pick=date_ladder_pick_val,
            )
            for m in all_markets
            if (MEMBER_MARKET, int(m["id"])) not in seen_member_keys
            and _market_matches_query(m, aq, now_dt=now_dt)
        ]
        matched = _filter_unseen_twins(_dedupe_twin_markets(matched))
        order_by = str(aq.get("order_by") or "lead_prob_desc")
        if order_by == "closeness_to_50":
            matched.sort(key=lambda x: (x["closeness_to_50"], -x["lead_prob"]))
        elif order_by == "lead_prob_asc":
            matched.sort(
                key=lambda x: (
                    x["lead_prob"],
                    -float(x.get("_volume") or 0.0),
                    x["title"].casefold(),
                )
            )
        else:
            matched.sort(
                key=lambda x: (
                    -x["lead_prob"],
                    -float(x.get("_volume") or 0.0),
                    x["title"].casefold(),
                )
            )
        matched = matched[:max_items]
        if len(matched) < min_items:
            return RoundupRefusal((("container_machinery", f"too_few_markets:{sec_key}"),))

        form_id = choose_section_form("markets", matched)
        eff_title, eff_note = _resolve_section_heading(
            sec_cfg,
            aq_kind="markets",
            form_id=form_id,
            rendered_items=matched,
            visible_limit=initial_visible,
            default_title=sec_title,
        )
        sec_members = []
        for it in matched:
            mid = it["market_id"]
            _record_covered_twins(it)
            env = {
                "type": MEMBER_MARKET,
                "id": mid,
                "destination": market_destination(mid),
                "card": it["card"],
            }
            sec_members.append(env)
            if (MEMBER_MARKET, mid) not in seen_member_keys:
                seen_member_keys.add((MEMBER_MARKET, mid))
                all_member_envelopes.append(env)

        vb_payload: dict[str, Any] = {
            "form_id": form_id,
            "initial_visible_limit": initial_visible,
            "items": [
                {
                    k: v
                    for k, v in it.items()
                    if k not in ("card", "_twin_market_ids", "_volume")
                }
                for it in matched
            ],
        }
        sec_item_noun = str(sec_cfg.get("item_noun") or "").strip()
        if sec_item_noun:
            vb_payload["item_noun"] = sec_item_noun

        built_by_idx[sec_idx] = {
            "class": sec_key,
            "title": eff_title,
            "note": eff_note,
            "layout": form_id,
            "members": sec_members,
            "visual_block": vb_payload,
        }

    built_sections = [built_by_idx[idx] for idx in sorted(built_by_idx)]
    _unify_grouping_diacritic_names(built_sections)

    # Slice 6 Item 2c: all-or-nothing across configured sections — never emit an empty or shorter grouping.
    if (
        not built_sections
        or len(built_sections) != len(indexed_cfg)
        or not all_member_envelopes
    ):
        return RoundupRefusal((("container_machinery", "incomplete_sections_built"),))

    # Build the compact Discover card from the designated card section (or section 0), capped at <=3 rows
    card_rows_limit = min(3, max(1, int(rule.get("card_rows", 3))))
    preferred_card_key = str(rule.get("card_section_key") or "").strip()
    card_sec = next(
        (s for s in built_sections if s["class"] == preferred_card_key),
        built_sections[0],
    )
    vb = card_sec["visual_block"]
    vb_form = vb["form_id"]
    card_scale_ordered = False

    rows_out: list[dict[str, Any]] = []
    card_visual_rows: list[dict[str, Any]] = []

    if vb_form == "paired_stage_bars" and isinstance(vb.get("paired_metric_set"), Mapping):
        pset = vb["paired_metric_set"]
        w_mid = int((pset.get("stage_2_market") or {}).get("id") or 1)
        for idx, e in enumerate((pset.get("entries") or ())[:card_rows_limit]):
            win_p = float(e.get("stage_2_probability") or 0.0)
            allocated = e.get("stage_2_rendered_percent")
            win_pct = int(allocated) if allocated is not None else _half_up_pct(win_p)
            nom_p = e.get("stage_1_probability")
            row_d: dict[str, Any] = {
                "market_id": w_mid,
                "outcome_id": int(e.get("stage_2_outcome_id") or (w_mid * 100 + idx + 1)),
                "label": str(e.get("subject") or ""),
                "probability": win_p,
                "rendered_percent": win_pct,
                "unfloored_percent": int(allocated) if allocated is not None else rendered_percent(win_p),
            }
            if isinstance(nom_p, (int, float)):
                row_d["secondary_probability"] = float(nom_p)
                nomination_percent = e.get("stage_1_rendered_percent")
                row_d["secondary_rendered_percent"] = int(nomination_percent or _half_up_pct(float(nom_p)))
                unfloored = e.get("stage_1_unfloored_percent")
                if unfloored is None:
                    unfloored = nomination_percent
                row_d["secondary_unfloored_percent"] = (
                    int(unfloored) if unfloored is not None else rendered_percent(nom_p)
                )
            rows_out.append(row_d)
    elif vb_form in {"coin_flip_matchups", "matchup_slate"}:
        for it in (vb.get("items") or ())[:card_rows_limit]:
            eid = int(it["event_id"])
            fav_is_home = it["home_prob"] >= it["away_prob"]
            fav_pct = it["home_pct"] if fav_is_home else it["away_pct"]
            fav_p = it["home_prob"] if fav_is_home else it["away_prob"]
            rows_out.append(
                {
                    "event_id": eid,
                    "label": f"{it['away_short']} at {it['home_short']}",
                    "probability": fav_p,
                    "rendered_percent": fav_pct,
                }
            )
            card_visual_rows.append(it)
    elif vb_form == "benchmark_strip" and len(vb.get("items") or ()) >= 2:
        card_bm_items = _filter_card_benchmark_items(vb.get("items") or (), rule)
        for bm in card_bm_items[:card_rows_limit]:
            mid = int(bm.get("market_id") or 1)
            outs = list(bm.get("outcomes") or ())
            if not outs:
                continue
            yes = outs[0]
            bm_title = str(bm.get("title") or yes.get("name") or "")
            rows_out.append(
                {
                    "market_id": mid,
                    "outcome_id": int(yes["outcome_id"]),
                    "label": bm_title,
                    "probability": float(yes["probability"]),
                    "rendered_percent": int(yes["rendered_percent"]),
                    "unfloored_percent": yes.get("unfloored_percent"),
                }
            )
            card_visual_rows.append(
                {
                    "market_id": mid,
                    "href": bm.get("href") or f"/futures/{mid}",
                    **yes,
                    "name": bm_title,
                }
            )
    elif vb_form == "sibling_fields_grid" and len(vb.get("items") or ()) >= 2:
        for sib in (vb.get("items") or ())[:card_rows_limit]:
            mid = int(sib.get("market_id") or 1)
            outs = list(sib.get("outcomes") or ())
            if not outs:
                continue
            lead = max(outs, key=lambda o: float(o.get("probability") or 0.0))
            sib_label = f"{sib.get('title') or ''} · {lead.get('name') or ''}".strip(" ·")
            rows_out.append(
                {
                    "market_id": mid,
                    "outcome_id": int(lead["outcome_id"]),
                    "label": sib_label,
                    "probability": float(lead["probability"]),
                    "rendered_percent": int(lead["rendered_percent"]),
                    "unfloored_percent": lead.get("unfloored_percent"),
                }
            )
            card_visual_rows.append(
                {
                    "market_id": mid,
                    "href": sib.get("href") or f"/futures/{mid}",
                    **lead,
                    "name": sib_label,
                }
            )
    elif vb_form == "probability_history_chart":
        chart_items = [
            ch
            for ch in (vb.get("items") or ())
            if isinstance(ch, Mapping) and (ch.get("series") or ())
        ]
        card_scale_ordered = False
        if len(chart_items) >= 2:
            for ch in chart_items[:card_rows_limit]:
                c_mid = int(ch.get("market_id") or 1)
                series_list = [s for s in (ch.get("series") or ()) if isinstance(s, Mapping)]
                lead_s = max(
                    series_list,
                    key=lambda s: (
                        int(s.get("current_pct") or 0),
                        abs(int(s.get("net_move_pp") or 0)),
                        str(s.get("name") or ""),
                    ),
                )
                cur_pct = int(lead_s.get("current_pct") or 0)
                prob = round(cur_pct / 100.0, 4)
                oid = int(lead_s.get("outcome_id") or 0)
                ch_title = str(ch.get("title") or "").strip()
                ans_name = str(lead_s.get("name") or "").strip()
                label, _ = _format_fun_lead_answer_label(ch_title, ans_name)
                art = lead_s.get("art") if isinstance(lead_s.get("art"), Mapping) else {}
                rows_out.append(
                    {
                        "market_id": c_mid,
                        "outcome_id": oid,
                        "label": label,
                        "probability": prob,
                        "rendered_percent": cur_pct,
                    }
                )
                card_visual_rows.append(
                    {
                        "market_id": c_mid,
                        "outcome_id": oid,
                        "href": ch.get("href") or f"/futures/{c_mid}",
                        "name": label,
                        "probability": prob,
                        "rendered_percent": cur_pct,
                        "art": dict(art),
                    }
                )
    else:
        lead_market = (vb.get("items") or [{}])[0]
        mid = int(lead_market.get("market_id") or 1)
        all_lead_outs = list(lead_market.get("outcomes") or ())
        if lead_market.get("scale_ordered") and len(all_lead_outs) > card_rows_limit:
            by_prob = sorted(all_lead_outs, key=lambda o: -float(o.get("probability") or 0.0))
            sliced = by_prob[:card_rows_limit]
            s_idx = numerical_scale_order_indices(sliced)
            chosen_outs = [sliced[i] for i in s_idx] if s_idx is not None else sliced
            card_scale_ordered = s_idx is not None
        else:
            chosen_outs = all_lead_outs[:card_rows_limit]
            card_scale_ordered = bool(lead_market.get("scale_ordered"))
        for o in chosen_outs:
            rows_out.append(
                {
                    "market_id": mid,
                    "outcome_id": int(o["outcome_id"]),
                    "label": str(o["name"]),
                    "probability": float(o["probability"]),
                    "rendered_percent": int(o["rendered_percent"]),
                    "unfloored_percent": o.get("unfloored_percent"),
                }
            )
            card_visual_rows.append(
                {
                    "market_id": mid,
                    "href": lead_market.get("href") or f"/futures/{mid}",
                    **o,
                }
            )

    slug = str(definition["slug"])
    dest_href = f"/collections/{slug}"
    dynamic_title = _build_dynamic_title_from_set(definition, built_sections)

    # Slice 6 Item 2a: a page's first section never repeats the page headline.
    first_sec = built_sections[0]
    if _norm_key(str(first_sec.get("title") or "")) == _norm_key(dynamic_title):
        alt_title = str(
            indexed_cfg[0][1].get("fallback_title")
            or definition.get("section_title")
            or "Lead Markets"
        ).strip()
        if _norm_key(alt_title) != _norm_key(dynamic_title):
            first_sec["title"] = alt_title
        else:
            first_sec["suppress_heading"] = True

    # Slice 3 Item 5: drop settlement boilerplate from card faces and page subtitles.
    raw_footer = str(definition.get("footer") or "").strip()
    clean_footer = "" if _SETTLEMENT_FILLER_RE.search(raw_footer) else raw_footer

    hide_row_art = bool(rule.get("hide_row_art"))
    if hide_row_art and card_visual_rows:
        card_visual_rows = _strip_visual_row_art(card_visual_rows)

    # All-or-nothing row art parity with iOS (`GroupingMachineryViews12288`):
    # a Discover card or set-page section gets row pictures only when every row
    # it renders has a real verified picture (never letters beside photos).
    if (
        not hide_row_art
        and card_visual_rows
        and vb_form in {"benchmark_strip", "sibling_fields_grid", "leader_bars", "contender_spotlight", "probability_history_chart"}
        and not card_scale_ordered
    ):
        row_has_url = [
            isinstance(r, Mapping) and _has_verified_art(r) for r in card_visual_rows
        ]
        is_public_stage = (
            str(definition.get("stage") or "").strip().lower() == "public"
            or definition.get("stage") is None
        )
        if not all(row_has_url) and is_public_stage and _is_sports_definition(definition):
            missing_subjects = [
                _missing_art_subject_label(r, vb)
                for r, has_art in zip(card_visual_rows, row_has_url)
                if isinstance(r, Mapping) and not has_art
            ]
            logger.warning(
                "Public sports card %s dropped row pictures; missing art for subjects=%s",
                slug,
                missing_subjects,
            )
        if any(row_has_url) and not all(row_has_url):
            card_visual_rows = _strip_visual_row_art(card_visual_rows)

    has_card_art = any(_has_verified_art(r) for r in card_visual_rows if isinstance(r, Mapping))
    if vb_form == "paired_stage_bars" and lead_paired_set:
        has_card_art = any(
            _has_verified_art(r)
            for r in (lead_paired_set.get("entries") or ())[:card_rows_limit]
            if isinstance(r, Mapping)
        )
    # Slice 4 (Fable #12897 notes 1 & 2): a card's picture charts the card's OWN headline market
    # (never a different market from another section), and only when that market's number moved.
    mini_chart: Optional[dict[str, Any]] = None
    if (
        (vb_form == "probability_history_chart" or not has_card_art)
        and vb_form not in {"paired_stage_bars", "coin_flip_matchups", "matchup_slate"}
        and (vb.get("items") or ())
    ):
        if vb_form == "probability_history_chart":
            own_chart = vb["items"][0]
            card_min_swing = int(((card_sec.get("atom_query") or {}).get("min_swing_pp")) or 10)
            if isinstance(own_chart, Mapping) and _history_chart_moved(
                own_chart, min_swing_pp=card_min_swing
            ):
                mini_chart = {k: v for k, v in own_chart.items() if k != "card"}
        else:
            own_lead_market = vb["items"][0]
            if isinstance(own_lead_market, Mapping) and own_lead_market.get("outcomes"):
                own_chart = _build_history_visual_item(
                    own_lead_market, market_histories, now_dt=now_dt, hours=168
                )
                if _history_chart_moved(own_chart):
                    mini_chart = {k: v for k, v in own_chart.items() if k != "card"}

    suppress_card_photo = bool(rule.get("suppress_card_photo"))
    if suppress_card_photo:
        for env in all_member_envelopes:
            if isinstance(env, dict) and isinstance(env.get("card"), dict):
                env["card"]["image_url"] = None
        for sec in built_sections:
            for env in sec.get("members") or ():
                if isinstance(env, dict) and isinstance(env.get("card"), dict):
                    env["card"]["image_url"] = None

    card_image_url = str(rule.get("card_image_url") or "").strip() or None
    card_image_alt = str(rule.get("card_image_alt") or "").strip() or None
    card_image_credit = str(rule.get("card_image_credit") or "").strip() or None
    card_image_author = str(rule.get("card_image_author") or "").strip() or None
    card_image_license = str(rule.get("card_image_license") or "").strip() or None
    card_image_source_page = str(rule.get("card_image_source_page") or "").strip() or None
    allow_card_header_image = bool(card_image_url) and not (
        mini_chart is not None and vb_form == "probability_history_chart"
    )
    if allow_card_header_image and isinstance(vb, dict):
        vb["hero_image_url"] = card_image_url
        if card_image_alt:
            vb["hero_image_alt"] = card_image_alt
        if card_image_credit:
            vb["hero_image_credit"] = card_image_credit
        if card_image_author:
            vb["hero_image_author"] = card_image_author
        if card_image_license:
            vb["hero_image_license"] = card_image_license
        if card_image_source_page:
            vb["hero_image_source_page"] = card_image_source_page

    card_item_count, card_item_noun = _machinery_card_item_count_and_noun(vb)
    machinery_card: dict[str, Any] = {
        "slug": slug,
        "form_id": vb_form,
        "stage": str(definition.get("stage") or "public"),
        "look": str(definition.get("look") or "bars"),
        "kicker": str(definition.get("kicker") or "ROUND-UP"),
        "title": dynamic_title,
        "subtitle": str(card_sec.get("note") or ""),
        "footer": clean_footer,
        "scale_ordered": card_scale_ordered,
        "section_count": len(built_sections),
        "item_count": card_item_count,
        "item_noun": card_item_noun,
        "destination_href": dest_href,
        "rows": card_visual_rows,
    }
    if suppress_card_photo:
        machinery_card["suppress_card_photo"] = True
    if allow_card_header_image:
        machinery_card["image_url"] = card_image_url
        if card_image_alt:
            machinery_card["image_alt"] = card_image_alt
        if card_image_credit:
            machinery_card["image_credit"] = card_image_credit
        if card_image_author:
            machinery_card["image_author"] = card_image_author
        if card_image_license:
            machinery_card["image_license"] = card_image_license
        if card_image_source_page:
            machinery_card["image_source_page"] = card_image_source_page
    if mini_chart is not None:
        machinery_card["mini_chart"] = mini_chart

    _enforce_section_all_or_nothing_art(built_sections, hide_row_art=hide_row_art)

    card_paired_set: Optional[dict[str, Any]] = None
    if vb_form == "paired_stage_bars" and lead_paired_set is not None:
        card_paired_set = copy.deepcopy(lead_paired_set)
        card_paired_set["title"] = dynamic_title
        card_paired_set["entries"] = list(card_paired_set.get("entries") or ())[:card_rows_limit]

    return RoundupMembers(
        all_member_envelopes,
        rows_out,
        footer=clean_footer,
        title=dynamic_title,
        kicker=str(definition.get("kicker") or "ROUND-UP"),
        destination_href=dest_href,
        sections=built_sections,
        parent_slug=definition.get("parent_slug"),
        parent_name=definition.get("parent_name"),
        paired_metric_set=card_paired_set,
        machinery_card=machinery_card,
        covered_market_ids=covered_twin_market_ids,
    )


def _machinery_card_item_count_and_noun(vb: Mapping[str, Any]) -> tuple[int, str]:
    """Return ``(item_count, item_noun)`` for a grouping Discover card CTA (#13234).

    Matches the set page's ``ShowAllButton`` counts and item nouns so a single-section
    grouping card can read ``See all 7 markets ›``, ``See all 11 cities ›``,
    ``See all 16 couples ›``, etc.
    """
    form_id = str(vb.get("form_id") or "").strip()
    explicit_noun = str(vb.get("item_noun") or "").strip()
    if form_id == "paired_stage_bars":
        paired = vb.get("paired_metric_set")
        entries = paired.get("entries") if isinstance(paired, Mapping) else None
        count = (
            len(entries)
            if isinstance(entries, Sequence) and not isinstance(entries, (str, bytes))
            else 0
        )
        return count, explicit_noun or "contenders"
    raw_items = vb.get("items")
    item_list = (
        list(raw_items)
        if isinstance(raw_items, Sequence) and not isinstance(raw_items, (str, bytes))
        else []
    )
    if form_id in {"coin_flip_matchups", "matchup_slate"}:
        return len(item_list), explicit_noun or "games"
    if form_id == "sibling_fields_grid":
        return len(item_list), explicit_noun or "markets"
    if form_id == "benchmark_strip":
        return len(item_list), explicit_noun or "benchmarks"
    if form_id == "probability_history_chart":
        return len(item_list), explicit_noun or "charts"
    if form_id == "stacked_bar_list" and len(item_list) == 1 and isinstance(item_list[0], Mapping):
        outcomes = item_list[0].get("outcomes")
        if isinstance(outcomes, Sequence) and not isinstance(outcomes, (str, bytes)):
            return len(outcomes), explicit_noun or "outcomes"
    return len(item_list), explicit_noun or "markets"


def discover_machinery_candidate_paths() -> tuple[Path, ...]:
    """Discover all ``machinery-*.json`` definitions in ``data/groupings/candidates/``."""
    return tuple(sorted(_CANDIDATES_DIR.glob("machinery-*.json")))


def load_machinery_definition(path: Path | str) -> dict[str, Any]:
    from app.utils.roundup_containers import validate_roundup_definition

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    validated = validate_roundup_definition(raw, path=path)
    if validated["rule"].get("producer") != PRODUCER_KIND_CONTAINER_MACHINERY:
        raise ValueError(f"Expected producer='container_machinery' at {path}")
    copy_fields: list[str] = [
        str(validated.get("name") or ""),
        str(validated.get("kicker") or ""),
        str(validated.get("section_title") or ""),
        str(validated.get("footer") or ""),
    ]
    for sec in validated["rule"].get("sections") or ():
        if isinstance(sec, Mapping):
            copy_fields.append(str(sec.get("title") or ""))
            copy_fields.append(str(sec.get("fallback_title") or ""))
            copy_fields.append(str(sec.get("note") or ""))
    for text_val in copy_fields:
        if _FORBIDDEN_COPY_QUESTION_RE.search(text_val):
            raise ValueError(
                f"Definition {path} calls a market a 'question' ({text_val!r}); say 'market(s)'."
            )
    return validated


def build_container_machinery_producer(
    definition: Mapping[str, Any],
    *,
    enabled: Optional[Any] = None,
) -> Any:
    from app.utils.roundup_containers import RoundupProducer, validate_roundup_definition

    validated = validate_roundup_definition(definition)

    async def _produce(db: Any, *, now: Optional[datetime] = None) -> Any:
        return await produce_container_machinery(db, validated, now=now)

    return RoundupProducer(
        slug=validated["slug"],
        name=str(validated.get("name") or validated["slug"]),
        kind="roundup",
        category=str(validated.get("category") or "other"),
        section_title=str(validated.get("section_title") or "Markets"),
        footer=str(validated.get("footer") or ""),
        produce=_produce,
        membership=str(validated.get("membership") or "computed-produced"),
        relations=validated["relations"],
        level=validated["level"],
        rule=validated["rule"],
        tag=validated.get("tag"),
        kicker=str(validated.get("kicker") or "ROUND-UP"),
        parent_slug=validated.get("parent_slug"),
        parent_name=validated.get("parent_name"),
        enabled=enabled if enabled is not None else container_machinery_enabled,
        stage=validated.get("stage", "public"),
        look=validated.get("look", "bars"),
    )


def register_machinery_slice1_candidates(*, enabled: Optional[Any] = None) -> list[str]:
    """Register all ``machinery-*.json`` candidate definitions into ``ROUNDUP_PRODUCERS``."""
    from app.utils.roundup_containers import register_roundup_producer

    slugs: list[str] = []
    for path in discover_machinery_candidate_paths():
        defn = load_machinery_definition(path)
        prod = build_container_machinery_producer(defn, enabled=enabled)
        register_roundup_producer(prod)
        slugs.append(prod.slug)
    return slugs


_SLICE1_ORDER: tuple[str, ...] = (
    "machinery-nfl-week",
    "machinery-oscars-best-picture",
    "machinery-2028-presidential",
    "machinery-fed-and-macro",
)


def _ordered_machinery_candidate_paths() -> tuple[Path, ...]:
    by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    ordered: list[Path] = []
    for s in _SLICE1_ORDER:
        if s in by_slug:
            ordered.append(by_slug.pop(s))
    for s in sorted(by_slug):
        ordered.append(by_slug[s])
    return tuple(ordered)


def is_machinery_candidate_slug(slug: str) -> bool:
    """True when ``slug`` corresponds to a ``machinery-*.json`` candidate definition."""
    if not slug or "/" in slug or "\\" in slug or ".." in slug:
        return False
    return any(p.stem == slug for p in discover_machinery_candidate_paths())


def _missing_art_subject_label(row: Mapping[str, Any], vb: Mapping[str, Any]) -> str:
    """Resolve the true outcome subject name for missing-art warnings."""
    row_mid = row.get("market_id")
    row_oid = row.get("outcome_id")
    for item in vb.get("items") or ():
        if not isinstance(item, Mapping):
            continue
        if row_mid is not None and item.get("market_id") != row_mid:
            continue
        outs = item.get("outcomes") or ()
        matched = next(
            (o for o in outs if isinstance(o, Mapping) and o.get("outcome_id") == row_oid),
            outs[0] if outs else None,
        )
        if isinstance(matched, Mapping):
            cand = str(matched.get("name") or "").strip()
            if cand and cand.lower() not in {"yes", "no"}:
                return cand
    return str(row.get("name") or "")


def _strip_visual_row_art(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Strip row picture URLs cleanly (all-or-nothing or ``rule.hide_row_art``)."""
    stripped: list[dict[str, Any]] = []
    for row in rows:
        row_copy = dict(row)
        art = row_copy.get("art")
        if isinstance(art, Mapping):
            art_copy = dict(art)
            art_copy["url"] = None
            art_copy["kind"] = "monogram"
            row_copy["art"] = art_copy
        stripped.append(row_copy)
    return stripped


def _enforce_section_all_or_nothing_art(
    built_sections: Sequence[dict[str, Any]],
    *,
    hide_row_art: bool,
) -> None:
    """Enforce per-section all-or-nothing row art on set-page sections (#12288 Item 4).

    Called AFTER ``card_visual_rows`` is built so a set-page section with some
    unpictured rows strips its section row art cleanly without disturbing a
    3/3 pictured Discover card from the same section.
    """
    for sec in built_sections:
        sec_vb = sec.get("visual_block")
        if not isinstance(sec_vb, dict):
            continue
        s_form = str(sec_vb.get("form_id") or "")
        items = sec_vb.get("items")
        if not isinstance(items, list) or not items:
            continue

        should_strip = False
        if hide_row_art and s_form in {
            "benchmark_strip",
            "sibling_fields_grid",
            "leader_bars",
            "contender_spotlight",
            "duel_bar",
        }:
            should_strip = True
        elif s_form == "benchmark_strip":
            has_urls = [
                bool((it.get("outcomes") or ()) and _has_verified_art(it["outcomes"][0]))
                for it in items
                if isinstance(it, Mapping)
            ]
            should_strip = any(has_urls) and not all(has_urls)
        elif s_form in {"sibling_fields_grid", "leader_bars", "contender_spotlight", "duel_bar"}:
            has_urls = [
                _has_verified_art(o)
                for it in items
                if isinstance(it, Mapping) and not it.get("scale_ordered")
                for o in (it.get("outcomes") or ())
                if isinstance(o, Mapping)
            ]
            should_strip = any(has_urls) and not all(has_urls)

        if not should_strip:
            continue

        stripped_items: list[dict[str, Any]] = []
        for it in items:
            if not isinstance(it, Mapping):
                continue
            it_copy = dict(it)
            if hide_row_art or not it_copy.get("scale_ordered"):
                outs = it_copy.get("outcomes")
                if isinstance(outs, Sequence) and not isinstance(outs, (str, bytes)):
                    it_copy["outcomes"] = _strip_visual_row_art(
                        [o for o in outs if isinstance(o, Mapping)]
                    )
            stripped_items.append(it_copy)
        sec_vb["items"] = stripped_items


def _has_verified_art(obj: Mapping[str, Any]) -> bool:
    art = obj.get("art")
    if isinstance(art, Mapping) and str(art.get("url") or "").strip():
        return True
    if str(obj.get("poster_url") or "").strip():
        return True
    away_art = obj.get("away_art")
    home_art = obj.get("home_art")
    if isinstance(away_art, Mapping) and str(away_art.get("url") or "").strip():
        return True
    if isinstance(home_art, Mapping) and str(home_art.get("url") or "").strip():
        return True
    return False


def _visual_block_units(vb: Mapping[str, Any]) -> tuple[str, list[tuple[float, int]]]:
    """Return ``(form_id, [(unit_height_px_at_390, verified_picture_or_chart_count), ...])``
    for the initial visible units rendered inside ``vb`` at 390 px width (capped at ``initial_visible_limit``)."""
    form = str(vb.get("form_id") or vb.get("form") or "")
    vis_limit = int(vb.get("initial_visible_limit") or 0)
    units: list[tuple[float, int]] = []
    if form == "paired_stage_bars":
        pms = vb.get("paired_metric_set") or {}
        rows = list(pms.get("entries") or pms.get("rows") or ())
        if vis_limit > 0:
            rows = rows[:vis_limit]
        for row in rows:
            if isinstance(row, Mapping):
                pics = 1 if _has_verified_art(row) else 0
                units.append((76.0, pics))
    elif form == "probability_history_chart":
        items = list(vb.get("items") or ())
        if vis_limit > 0:
            items = items[:vis_limit]
        for it in items:
            if isinstance(it, Mapping):
                moved = bool(it.get("series")) and _history_chart_moved(it)
                units.append((196.0, 1 if moved else 0))
    elif form in {"coin_flip_matchups", "matchup_slate"}:
        items = list(vb.get("items") or ())
        if vis_limit > 0:
            items = items[:vis_limit]
        for it in items:
            if isinstance(it, Mapping):
                pics = 0
                if isinstance(it.get("away_art"), Mapping) and str(it["away_art"].get("url") or "").strip():
                    pics += 1
                if isinstance(it.get("home_art"), Mapping) and str(it["home_art"].get("url") or "").strip():
                    pics += 1
                units.append((114.0, pics))
    elif form == "duel_bar":
        for it in vb.get("items") or ():
            if isinstance(it, Mapping):
                pics = sum(
                    1
                    for s in (it.get("sides") or it.get("outcomes") or ())
                    if isinstance(s, Mapping) and _has_verified_art(s)
                )
                units.append((108.0, pics))
    elif form == "contender_spotlight":
        for it in vb.get("items") or ():
            if not isinstance(it, Mapping):
                continue
            outs = [o for o in (it.get("outcomes") or ()) if isinstance(o, Mapping)]
            if it.get("scale_ordered"):
                shown = outs[:vis_limit] if vis_limit > 0 else outs
                for o in shown:
                    units.append((54.0, 1 if _has_verified_art(o) else 0))
            else:
                # 3-up horizontal podium row; chasers beyond top 3 fold behind "Show all"
                top3 = outs[:3]
                pics = sum(1 for o in top3 if _has_verified_art(o))
                units.append((168.0, pics))
                if vis_limit == 0:
                    for o in outs[3:]:
                        units.append((64.0, 1 if _has_verified_art(o) else 0))
    elif form == "sibling_fields_grid":
        items = list(vb.get("items") or ())
        if vis_limit > 0:
            items = items[:vis_limit]
        for it in items:
            if isinstance(it, Mapping):
                pics = sum(
                    1
                    for o in (it.get("outcomes") or ())
                    if isinstance(o, Mapping) and _has_verified_art(o)
                )
                units.append((148.0, pics))
    elif form == "benchmark_strip":
        items = list(vb.get("items") or ())
        if vis_limit > 0:
            items = items[:vis_limit]
        for it in items:
            if isinstance(it, Mapping):
                units.append((64.0, 1 if _has_verified_art(it) else 0))
    return form, units


def _estimate_screen_picture_counts_390px(sections: Sequence[Mapping[str, Any]]) -> list[int]:
    """Estimate verified picture/chart counts per 390x844 phone screen from rendered unit heights."""
    screen_h = 844.0
    y = 136.0  # container title + count header at 390 px
    unit_boxes: list[tuple[float, float, int]] = []
    for sec in sections:
        vb = sec.get("visual_block")
        if not isinstance(vb, Mapping):
            continue
        y += 60.0  # section title + subtitle + vertical gap
        _form, units = _visual_block_units(vb)
        for h, pics in units:
            unit_boxes.append((y, y + h, pics))
            y += h + 8.0
        y += 14.0
    total_h = max(y, screen_h)
    num_screens = max(1, int(math.ceil(total_h / screen_h)))
    counts: list[int] = []
    for idx in range(num_screens):
        top = idx * screen_h
        bot = (idx + 1) * screen_h
        pics_on_screen = sum(
            pics for (u0, u1, pics) in unit_boxes if pics > 0 and u1 > top + 12.0 and u0 < bot - 12.0
        )
        counts.append(pics_on_screen)
    return counts


def _classify_member_content_kind(
    member: Mapping[str, Any],
    *,
    section_layout: Optional[str] = None,
) -> str:
    mtype = str(member.get("type") or "")
    if mtype == "event":
        return "games"
    if mtype == "history" or section_layout == "probability_history_chart":
        return "history"
    card = member.get("card") if isinstance(member.get("card"), Mapping) else {}
    item = member.get("item") if isinstance(member.get("item"), Mapping) else {}
    futures_obj = item.get("futures") if isinstance(item.get("futures"), Mapping) else (card or item)
    explicit_ck = str(card.get("content_kind") or futures_obj.get("content_kind") or "").lower()
    if explicit_ck in {"games", "futures", "props", "history"}:
        return explicit_ck
    m_kind = str(futures_obj.get("market_type") or "").lower()
    m_name = str(futures_obj.get("name") or "")
    if "prop" in m_kind or _PROP_MARKET_TITLE_RE.search(m_name):
        return "props"
    return "futures"


def _check_scale_order_violations(rows: Sequence[Mapping[str, Any]], label: str) -> tuple[int, list[str]]:
    """Return ``(1 if rows is a numerical scale else 0, [violation] if out of ascending order else [])``."""
    idx = numerical_scale_order_indices(rows)
    if idx is None:
        return 0, []
    if idx != list(range(len(rows))):
        return 1, [label]
    return 1, []


def _lookup_market_member_pct(
    mpn: Optional[Mapping[str, Any]],
    outcome_id: Optional[int],
    label: str,
) -> Optional[int]:
    """Look up a member market's own-page integer percent by outcome_id or normalized outcome name."""
    if not isinstance(mpn, Mapping):
        return None
    by_oid = mpn.get("by_outcome_id") or {}
    if outcome_id is not None:
        if outcome_id in by_oid:
            return int(by_oid[outcome_id])
        if str(outcome_id) in by_oid:
            return int(by_oid[str(outcome_id)])
    by_key = mpn.get("by_outcome_key") or {}
    for nk in (_norm_key(_clean_outcome_label(label)), _norm_key(label), _ascii_fold_key(label)):
        if nk and nk in by_key:
            return int(by_key[nk])
    by_fold = mpn.get("by_fold_key") or {}
    if by_fold:
        from app.services.paired_metric_register import fold_outcome_key

        fk = fold_outcome_key(label)
        if fk and fk in by_fold:
            return int(by_fold[fk])
    return None


def _compute_member_number_parity(
    feed_item: Optional[Mapping[str, Any]],
    container_payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compare every percentage on a grouping's Discover card and container page
    against the number served on that member's own page at the same moment (Slice 6 Item 2b).
    """
    sections = [
        s for s in (container_payload.get("sections") or ()) if isinstance(s, Mapping)
    ]
    event_truth: dict[int, dict[str, int]] = {}
    market_truth: dict[int, dict[str, Any]] = {}

    card_checked = 0
    card_mismatches: list[dict[str, Any]] = []
    page_checked = 0
    page_mismatches: list[dict[str, Any]] = []

    for sec in sections:
        sec_cls = str(sec.get("class") or "")
        for m in sec.get("members") or ():
            if not isinstance(m, Mapping):
                continue
            m_type = str(m.get("type") or "")
            mid = int(m.get("id") or 0)
            card_obj = m.get("card") if isinstance(m.get("card"), Mapping) else {}
            mpn = card_obj.get("member_page_numbers")
            if m_type == "event":
                # Fable 2026-11-18 strict game-page parity rule:
                # Never self-compare against a copied member_page_numbers dict.
                # Verify that card.current_odds carries the exact canonical game-page
                # rendered pair (`away_rendered_percent`, `home_rendered_percent`)
                # produced by `printable_away` + `rendered_duel_percents` — the same
                # function `/api/events/{id}` serves — and fail parity immediately if
                # `current_odds` omits those integers or disagrees with the game page.
                co = (
                    card_obj.get("current_odds")
                    if isinstance(card_obj.get("current_odds"), Mapping)
                    else {}
                )
                ap_raw = co.get("away_probability")
                if ap_raw is None:
                    ap_raw = card_obj.get("hero_probability_away")
                hp_raw = co.get("home_probability")
                if hp_raw is None:
                    hp_raw = card_obj.get("hero_probability")
                sport_s = str(card_obj.get("sport") or "").strip().lower()
                canonical_away: Optional[int] = None
                canonical_home: Optional[int] = None
                if isinstance(ap_raw, (int, float)) and isinstance(hp_raw, (int, float)):
                    c_ap = printable_away(float(ap_raw), float(hp_raw), sport_s)
                    c_a_pct, c_h_pct = rendered_duel_percents(c_ap, float(hp_raw))
                    if c_a_pct is not None and c_h_pct is not None:
                        canonical_away = int(c_a_pct)
                        canonical_home = int(c_h_pct)
                served_away = co.get("away_rendered_percent")
                served_home = co.get("home_rendered_percent")
                if canonical_away is not None and canonical_home is not None:
                    event_truth[mid] = {
                        "away_pct": canonical_away,
                        "home_pct": canonical_home,
                    }
                    page_checked += 2
                    if not isinstance(served_away, int) or int(served_away) != canonical_away:
                        page_mismatches.append(
                            {
                                "location": f"{sec_cls}:member_card_current_odds:{mid}:away_rendered_percent",
                                "event_id": mid,
                                "shown": served_away,
                                "member_page": canonical_away,
                            }
                        )
                    if not isinstance(served_home, int) or int(served_home) != canonical_home:
                        page_mismatches.append(
                            {
                                "location": f"{sec_cls}:member_card_current_odds:{mid}:home_rendered_percent",
                                "event_id": mid,
                                "shown": served_home,
                                "member_page": canonical_home,
                            }
                        )
                elif isinstance(served_away, int) and isinstance(served_home, int):
                    event_truth[mid] = {
                        "away_pct": int(served_away),
                        "home_pct": int(served_home),
                    }
            elif m_type == "market":
                if isinstance(mpn, Mapping):
                    market_truth[mid] = dict(mpn)
                else:
                    _, by_oid, by_key = _canonical_market_outcome_map(
                        card_obj.get("top_outcomes") or card_obj.get("outcomes") or (),
                        mutually_exclusive=bool(card_obj.get("mutually_exclusive", True)),
                        question=str(card_obj.get("name") or ""),
                    )
                    market_truth[mid] = {"by_outcome_id": by_oid, "by_outcome_key": by_key}

    # 1. Discover card numbers
    fi_data = (feed_item or {}).get("data") if isinstance((feed_item or {}).get("data"), Mapping) else {}
    rc = fi_data.get("roundup") or (feed_item or {}).get("roundup_contract") or {}
    if not isinstance(rc, Mapping):
        rc = {}
    mc = rc.get("machinery_card") if isinstance(rc.get("machinery_card"), Mapping) else {}
    card_form = str(mc.get("form_id") or "roundup")
    pms = rc.get("paired_metric_set") if isinstance(rc.get("paired_metric_set"), Mapping) else None

    if card_form == "paired_stage_bars" and pms:
        s1_mid = int((pms.get("stage_1_market") or {}).get("id") or 0)
        s2_mid = int((pms.get("stage_2_market") or {}).get("id") or 0)
        for e in list(pms.get("entries") or ())[:3]:
            if not isinstance(e, Mapping):
                continue
            subj = str(e.get("subject") or "")
            if isinstance(e.get("stage_1_probability"), (int, float)) and not e.get("stage_1_settled_state") and s1_mid in market_truth:
                shown_s1 = int(e.get("stage_1_rendered_percent") or _half_up_pct(float(e["stage_1_probability"])))
                exp_s1 = _lookup_market_member_pct(
                    market_truth.get(s1_mid),
                    int(e["stage_1_outcome_id"]) if isinstance(e.get("stage_1_outcome_id"), int) else None,
                    subj,
                )
                card_checked += 1
                if exp_s1 is None or shown_s1 != exp_s1:
                    card_mismatches.append(
                        {"location": f"card:paired_stage_1:{subj}", "market_id": s1_mid, "shown": shown_s1, "member_page": exp_s1}
                    )
            if isinstance(e.get("stage_2_probability"), (int, float)) and s2_mid in market_truth:
                allocated = e.get("stage_2_rendered_percent")
                shown_s2 = int(allocated) if allocated is not None else _half_up_pct(float(e["stage_2_probability"]))
                exp_s2 = _lookup_market_member_pct(
                    market_truth.get(s2_mid),
                    int(e["stage_2_outcome_id"]) if isinstance(e.get("stage_2_outcome_id"), int) else None,
                    subj,
                )
                card_checked += 1
                if exp_s2 is None or shown_s2 != exp_s2:
                    card_mismatches.append(
                        {"location": f"card:paired_stage_2:{subj}", "market_id": s2_mid, "shown": shown_s2, "member_page": exp_s2}
                    )
    elif card_form in {"coin_flip_matchups", "matchup_slate"}:
        for r in mc.get("rows") or ():
            if not isinstance(r, Mapping):
                continue
            eid = int(r.get("event_id") or 0)
            ev_t = event_truth.get(eid)
            for side_key in ("away_pct", "home_pct"):
                shown_v = int(r.get(side_key) or 0)
                exp_v = ev_t.get(side_key) if ev_t else None
                card_checked += 1
                if exp_v is None or shown_v != exp_v:
                    card_mismatches.append(
                        {"location": f"card:event:{eid}:{side_key}", "event_id": eid, "shown": shown_v, "member_page": exp_v}
                    )
    else:
        for r in mc.get("rows") or ():
            if not isinstance(r, Mapping):
                continue
            mid = int(r.get("market_id") or 0)
            oid = int(r["outcome_id"]) if isinstance(r.get("outcome_id"), int) else None
            lbl = str(r.get("name") or r.get("label") or "")
            shown_v = int(r.get("rendered_percent") or 0)
            exp_v = _lookup_market_member_pct(market_truth.get(mid), oid, lbl)
            card_checked += 1
            if exp_v is None or shown_v != exp_v:
                card_mismatches.append(
                    {"location": f"card:market:{mid}:{lbl}", "market_id": mid, "shown": shown_v, "member_page": exp_v}
                )
        mini = mc.get("mini_chart")
        if isinstance(mini, Mapping):
            c_mid = int(mini.get("market_id") or 0)
            for s in list(mini.get("series") or ())[:3]:
                if not isinstance(s, Mapping):
                    continue
                oid = int(s["outcome_id"]) if isinstance(s.get("outcome_id"), int) else None
                lbl = str(s.get("name") or "")
                shown_v = int(s.get("current_pct") or 0)
                exp_v = _lookup_market_member_pct(market_truth.get(c_mid), oid, lbl)
                card_checked += 1
                if exp_v is None or shown_v != exp_v:
                    card_mismatches.append(
                        {"location": f"card:mini_chart:{c_mid}:{lbl}", "market_id": c_mid, "shown": shown_v, "member_page": exp_v}
                    )

    # 2. Container page section numbers
    for sec in sections:
        sec_cls = str(sec.get("class") or "")
        vb = sec.get("visual_block")
        if not isinstance(vb, Mapping):
            continue
        form = str(vb.get("form_id") or "")
        if form == "paired_stage_bars":
            pset = vb.get("paired_metric_set") if isinstance(vb.get("paired_metric_set"), Mapping) else {}
            s1_mid = int((pset.get("stage_1_market") or {}).get("id") or 0)
            s2_mid = int((pset.get("stage_2_market") or {}).get("id") or 0)
            for e in pset.get("entries") or ():
                if not isinstance(e, Mapping):
                    continue
                subj = str(e.get("subject") or "")
                if isinstance(e.get("stage_1_probability"), (int, float)) and not e.get("stage_1_settled_state") and s1_mid in market_truth:
                    shown_s1 = int(e.get("stage_1_rendered_percent") or _half_up_pct(float(e["stage_1_probability"])))
                    exp_s1 = _lookup_market_member_pct(
                        market_truth.get(s1_mid),
                        int(e["stage_1_outcome_id"]) if isinstance(e.get("stage_1_outcome_id"), int) else None,
                        subj,
                    )
                    page_checked += 1
                    if exp_s1 is None or shown_s1 != exp_s1:
                        page_mismatches.append(
                            {"location": f"{sec_cls}:paired_stage_1:{subj}", "market_id": s1_mid, "shown": shown_s1, "member_page": exp_s1}
                        )
                if isinstance(e.get("stage_2_probability"), (int, float)) and s2_mid in market_truth:
                    allocated = e.get("stage_2_rendered_percent")
                    shown_s2 = int(allocated) if allocated is not None else _half_up_pct(float(e["stage_2_probability"]))
                    exp_s2 = _lookup_market_member_pct(
                        market_truth.get(s2_mid),
                        int(e["stage_2_outcome_id"]) if isinstance(e.get("stage_2_outcome_id"), int) else None,
                        subj,
                    )
                    page_checked += 1
                    if exp_s2 is None or shown_s2 != exp_s2:
                        page_mismatches.append(
                            {"location": f"{sec_cls}:paired_stage_2:{subj}", "market_id": s2_mid, "shown": shown_s2, "member_page": exp_s2}
                        )
        elif form in {"coin_flip_matchups", "matchup_slate"}:
            for it in vb.get("items") or ():
                if not isinstance(it, Mapping):
                    continue
                eid = int(it.get("event_id") or 0)
                ev_t = event_truth.get(eid)
                for side_key in ("away_pct", "home_pct"):
                    shown_v = int(it.get(side_key) or 0)
                    exp_v = ev_t.get(side_key) if ev_t else None
                    page_checked += 1
                    if exp_v is None or shown_v != exp_v:
                        page_mismatches.append(
                            {"location": f"{sec_cls}:event:{eid}:{side_key}", "event_id": eid, "shown": shown_v, "member_page": exp_v}
                        )
        elif form == "probability_history_chart":
            for it in vb.get("items") or ():
                if not isinstance(it, Mapping):
                    continue
                mid = int(it.get("market_id") or 0)
                for s in it.get("series") or ():
                    if not isinstance(s, Mapping):
                        continue
                    oid = int(s["outcome_id"]) if isinstance(s.get("outcome_id"), int) else None
                    lbl = str(s.get("name") or "")
                    shown_v = int(s.get("current_pct") or 0)
                    exp_v = _lookup_market_member_pct(market_truth.get(mid), oid, lbl)
                    page_checked += 1
                    if exp_v is None or shown_v != exp_v:
                        page_mismatches.append(
                            {"location": f"{sec_cls}:chart:{mid}:{lbl}", "market_id": mid, "shown": shown_v, "member_page": exp_v}
                        )
        else:
            for it in vb.get("items") or ():
                if not isinstance(it, Mapping):
                    continue
                mid = int(it.get("market_id") or 0)
                for o in it.get("outcomes") or ():
                    if not isinstance(o, Mapping):
                        continue
                    oid = int(o["outcome_id"]) if isinstance(o.get("outcome_id"), int) else None
                    lbl = str(o.get("name") or "")
                    shown_v = int(o.get("rendered_percent") or 0)
                    exp_v = _lookup_market_member_pct(market_truth.get(mid), oid, lbl)
                    page_checked += 1
                    if exp_v is None or shown_v != exp_v:
                        page_mismatches.append(
                            {"location": f"{sec_cls}:market:{mid}:{lbl}", "market_id": mid, "shown": shown_v, "member_page": exp_v}
                        )

    card_parity = {
        "checked_numbers": card_checked,
        "mismatch_count": len(card_mismatches),
        "mismatches": card_mismatches,
        "passes": card_checked > 0 and len(card_mismatches) == 0,
    }
    page_parity = {
        "checked_numbers": page_checked,
        "mismatch_count": len(page_mismatches),
        "mismatches": page_mismatches,
        "passes": page_checked > 0 and len(page_mismatches) == 0,
    }
    return card_parity, page_parity


def compute_visual_diversity_report(
    definition: Mapping[str, Any],
    feed_item: Optional[Mapping[str, Any]],
    container_payload: Mapping[str, Any],
    *,
    screen_picture_counts_390px: Optional[Sequence[int]] = None,
) -> dict[str, Any]:
    """Compute Ruling 227-A + Direction 228 + Slice 6 member-page number parity report
    metrics for both the Discover card and the multi-section container page."""
    card_parity, page_parity = _compute_member_number_parity(feed_item, container_payload)
    fi_data = (feed_item or {}).get("data") if isinstance((feed_item or {}).get("data"), Mapping) else {}
    rc = (
        fi_data.get("roundup")
        or (feed_item or {}).get("roundup_contract")
        or {}
    )
    if not isinstance(rc, Mapping):
        rc = {}
    mc = rc.get("machinery_card") if isinstance(rc.get("machinery_card"), Mapping) else {}
    card_form = str(mc.get("form_id") or "roundup")
    card_rows = [r for r in (mc.get("rows") or ()) if isinstance(r, Mapping)]
    pms = rc.get("paired_metric_set") if isinstance(rc.get("paired_metric_set"), Mapping) else None
    if card_form == "paired_stage_bars" and pms:
        all_pms_entries = [r for r in (pms.get("entries") or pms.get("rows") or ()) if isinstance(r, Mapping)]
        pms_rows = all_pms_entries[:3]
        card_row_count = len(pms_rows)
        card_pics = sum(1 for r in pms_rows if _has_verified_art(r))
        card_scale_checked, card_scale_violations = _check_scale_order_violations(pms_rows, "card:paired_stage")
    else:
        card_row_count = len(card_rows)
        card_pics = 0
        for r in card_rows:
            if card_form in {"coin_flip_matchups", "matchup_slate"}:
                if isinstance(r.get("away_art"), Mapping) and str(r["away_art"].get("url") or "").strip():
                    card_pics += 1
                if isinstance(r.get("home_art"), Mapping) and str(r["home_art"].get("url") or "").strip():
                    card_pics += 1
            elif _has_verified_art(r):
                card_pics += 1
        if (
            isinstance(mc.get("mini_chart"), Mapping)
            and mc["mini_chart"].get("series")
            and _history_chart_moved(mc["mini_chart"])
        ):
            card_pics += 1
        if card_form in {"coin_flip_matchups", "matchup_slate"}:
            card_scale_checked, card_scale_violations = 0, []
        else:
            card_scale_checked, card_scale_violations = _check_scale_order_violations(card_rows, "card:rows")

    card_kind = "games" if card_form in {"coin_flip_matchups", "matchup_slate"} else "futures"
    card_failing: list[str] = []
    if card_pics < 1:
        card_failing.append("point_1_picture_on_screen")
    if card_row_count > 3:
        card_failing.append("point_2_no_long_runs")
    if card_scale_violations:
        card_failing.append("direction_228_numerical_scale_order")
    if not card_parity["passes"]:
        card_failing.append("member_number_parity")

    card_report = {
        "surface": "discover_card",
        "form_id": card_form,
        "point_1_pictures_per_screen_390px": {
            "screens": [card_pics],
            "min_pictures_per_screen": card_pics,
            "passes": card_pics >= 1,
        },
        "point_2_longest_form_run": {
            "longest_row_run": card_row_count,
            "max_allowed": 3,
            "passes": card_row_count <= 3,
        },
        "point_3_forms": {
            "distinct_forms": [card_form],
            "form_count": 1,
            "note": "Single Discover card contributes 1 form toward Discover's first-10 >=4 requirement.",
            "passes": True,
        },
        "point_4_content_mix": {
            "content_kinds": {card_kind: card_row_count},
            "kind_count": 1 if card_row_count else 0,
            "largest_kind": card_kind if card_row_count else None,
            "largest_kind_share": 1.0 if card_row_count else 0.0,
            "note": "Card summarizes lead section; content-mix threshold applies at page/feed level.",
            "passes": True,
        },
        "direction_228_numerical_scale_order": {
            "checked_scale_markets": card_scale_checked,
            "violations": card_scale_violations,
            "passes": len(card_scale_violations) == 0,
        },
        "member_number_parity": card_parity,
        "overall_passes": len(card_failing) == 0,
        "failing_points": card_failing,
    }

    sections = [
        s for s in (container_payload.get("sections") or ()) if isinstance(s, Mapping)
    ]
    screens = (
        [int(x) for x in screen_picture_counts_390px]
        if screen_picture_counts_390px is not None
        else _estimate_screen_picture_counts_390px(sections)
    )
    if not screens:
        screens = [0]
    min_pics = min(screens)
    p1_pass = min_pics >= 1

    longest_row_run = 0
    current_row_run = 0
    longest_sec_run = 0
    current_sec_run = 0
    prev_form: Optional[str] = None
    distinct_forms: list[str] = []
    page_scale_checked = 0
    page_scale_violations: list[str] = []

    for sec in sections:
        vb = sec.get("visual_block")
        if not isinstance(vb, Mapping):
            continue
        form, units = _visual_block_units(vb)
        unit_count = len(units)
        if form and form not in distinct_forms:
            distinct_forms.append(form)
        if form == prev_form:
            current_row_run += unit_count
            current_sec_run += 1
        else:
            current_row_run = unit_count
            current_sec_run = 1
            prev_form = form
        longest_row_run = max(longest_row_run, current_row_run)
        longest_sec_run = max(longest_sec_run, current_sec_run)

        if form in {"contender_spotlight", "sibling_fields_grid", "duel_bar"}:
            for it in vb.get("items") or ():
                if isinstance(it, Mapping):
                    outs = [o for o in (it.get("outcomes") or ()) if isinstance(o, Mapping)]
                    chk, viol = _check_scale_order_violations(
                        outs, f"{sec.get('class')}:{it.get('title') or it.get('market_id')}"
                    )
                    page_scale_checked += chk
                    page_scale_violations.extend(viol)

    p2_pass = longest_row_run <= 3
    member_count = int(container_payload.get("member_count") or 0)
    form_count = len(distinct_forms)
    p3_pass = True if member_count < 6 else form_count >= 3

    kind_counts: dict[str, int] = {}
    for sec in sections:
        sec_layout = str(sec.get("layout") or "")
        for m in sec.get("members") or ():
            if isinstance(m, Mapping):
                k = _classify_member_content_kind(m, section_layout=sec_layout)
                kind_counts[k] = kind_counts.get(k, 0) + 1
    total_members_typed = sum(kind_counts.values())
    if total_members_typed > 0:
        largest_kind = max(sorted(kind_counts), key=lambda k: kind_counts[k])
        largest_share = round(kind_counts[largest_kind] / total_members_typed, 4)
    else:
        largest_kind = None
        largest_share = 0.0

    category = str(definition.get("category") or "").lower()
    is_sports_topic = (
        "games" in kind_counts
        or category in {"sports", "football", "basketball", "baseball", "hockey", "soccer", "tennis", "golf", "mma"}
    )
    available_topic_kinds = (
        ["games", "futures", "props", "history"]
        if is_sports_topic
        else ["futures", "history"]
    )
    multi_kind_topic = len(available_topic_kinds) > 1
    p4_pass = (
        (len(kind_counts) >= 2 and largest_share <= 0.60)
        if multi_kind_topic
        else True
    )
    d228_pass = len(page_scale_violations) == 0

    page_failing: list[str] = []
    if not p1_pass:
        page_failing.append("point_1_picture_on_every_screen")
    if not p2_pass:
        page_failing.append("point_2_no_long_runs")
    if not p3_pass:
        page_failing.append("point_3_several_forms")
    if not p4_pass:
        page_failing.append("point_4_content_mix")
    if not d228_pass:
        page_failing.append("direction_228_numerical_scale_order")
    if not page_parity["passes"]:
        page_failing.append("member_number_parity")

    page_report = {
        "surface": "container_page",
        "member_count": member_count,
        "section_count": len(sections),
        "point_1_pictures_per_screen_390px": {
            "screens": screens,
            "screen_count": len(screens),
            "min_pictures_per_screen": min_pics,
            "passes": p1_pass,
        },
        "point_2_longest_form_run": {
            "longest_row_run": longest_row_run,
            "longest_section_form_run": longest_sec_run,
            "max_allowed": 3,
            "passes": p2_pass,
        },
        "point_3_forms": {
            "member_count": member_count,
            "distinct_forms": distinct_forms,
            "form_count": form_count,
            "min_required": 3 if member_count >= 6 else 1,
            "passes": p3_pass,
        },
        "point_4_content_mix": {
            "content_kinds": kind_counts,
            "available_topic_kinds": available_topic_kinds,
            "kind_count": len(kind_counts),
            "largest_kind": largest_kind,
            "largest_kind_share": largest_share,
            "max_allowed_share": 0.60,
            "passes": p4_pass,
        },
        "direction_228_numerical_scale_order": {
            "checked_scale_markets": page_scale_checked,
            "violations": page_scale_violations,
            "passes": d228_pass,
        },
        "member_number_parity": page_parity,
        "overall_passes": len(page_failing) == 0,
        "failing_points": page_failing,
    }

    combined_mismatches = list(card_parity["mismatches"]) + list(page_parity["mismatches"])
    combined_checked = int(card_parity["checked_numbers"]) + int(page_parity["checked_numbers"])
    return {
        "standard": "227-A",
        "report_only": True,
        "slug": str(definition.get("slug") or ""),
        "name": str((container_payload.get("container") or {}).get("name") or definition.get("name") or ""),
        "category": str(definition.get("category") or ""),
        "card": card_report,
        "page": page_report,
        "member_number_parity": {
            "checked_numbers": combined_checked,
            "mismatch_count": len(combined_mismatches),
            "mismatches": combined_mismatches,
            "passes": bool(card_parity["passes"] and page_parity["passes"]),
        },
        "overall_passes": bool(card_report["overall_passes"] and page_report["overall_passes"]),
    }


def _machinery_preview_error_response(
    defn: Mapping[str, Any],
    *,
    error_code: str,
    exc_class: str,
    allow_error_envelope: bool,
) -> dict[str, Any]:
    """Slice 6 Item 2c + #12288 Ask 3: a failed read surfaces an explicit error state
    (never an empty or shorter grouping) and logs one line naming the slug and exception class.
    """
    from fastapi import HTTPException

    canonical_slug = str(defn.get("slug") or "unknown").replace("\r", "").replace("\n", "")
    safe_exc = str(exc_class or "Exception").replace("\r", "").replace("\n", "")
    safe_code = str(error_code or "read_failed").replace("\r", "").replace("\n", "")
    logger.warning(
        "machinery_preview_error slug=%s exception_class=%s error_code=%s",
        canonical_slug,
        safe_exc,
        safe_code,
    )
    msg = "Couldn't load this grouping right now. Please try again."
    if not allow_error_envelope:
        raise HTTPException(
            status_code=503,
            detail={
                "state": "unavailable",
                "slug": canonical_slug,
                "error_code": safe_code,
                "message": msg,
            },
        )
    return {
        "slug": canonical_slug,
        "status": "error",
        "error": msg,
        "error_code": safe_code,
        "definition": {
            "slug": canonical_slug,
            "name": str(defn.get("name") or canonical_slug),
            "category": str(defn.get("category") or ""),
            "kicker": str(defn.get("kicker") or ""),
            "footer": str(defn.get("footer") or ""),
        },
        "feed_item": None,
        "container": None,
        "diversity_report": None,
    }


_MACHINERY_PREVIEW_CACHE_TTL_S = 60.0
_machinery_preview_local_cache: dict[tuple[str, bool], tuple[float, dict[str, Any]]] = {}


def reset_machinery_preview_cache_for_tests() -> None:
    _machinery_preview_local_cache.clear()


def _preview_redis_key(slug: str, include_children: bool) -> str:
    suffix = "children" if include_children else "nochildren"
    return f"machinery:preview:v1:{slug}:{suffix}"


async def serve_machinery_candidate_preview(
    slug: str,
    db: Any,
    *,
    include_children: bool = True,
    now: Optional[datetime] = None,
    allow_error_envelope: bool = False,
) -> Optional[dict[str, Any]]:
    """Evaluate a single ``machinery-*.json`` candidate definition for an authenticated
    admin preview without enabling the global ``CONTAINER_MACHINERY_SLICE1_ENABLED`` flag.

    Slice 6 Item 2c: when ``slug`` is a known candidate and its read fails or refuses,
    never return ``None`` (which would fall through to an empty unpublished page or silently
    drop the grouping from the preview list). Instead raise HTTP 503 for direct container
    reads or return an explicit ``status='error'`` envelope for preview-list reads.

    Preview cache (60s per slug, ok responses only): avoids repeated full snapshot rebuilds
    when opening or refreshing ``/admin/groupings-preview`` while never caching errors.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils.container_read_cache import container_read_cache_enabled
    from app.utils.roundup_containers import (
        RoundupRefusal,
        compose_roundup_container,
        compose_roundup_feed_item,
        evaluate_roundup_producer,
    )

    target_path = next(
        (p for p in _ordered_machinery_candidate_paths() if p.stem == slug),
        None,
    )
    if target_path is None:
        return None
    defn = load_machinery_definition(target_path)
    canon_slug = str(defn.get("slug") or target_path.stem).replace("\r", "").replace("\n", "")
    use_preview_cache = (
        isinstance(db, AsyncSession)
        and now is None
        and container_read_cache_enabled()
    )
    t_start = time.monotonic()
    cache_key = (canon_slug, bool(include_children))
    if use_preview_cache:
        now_ts = time.time()
        local_hit = _machinery_preview_local_cache.get(cache_key)
        if local_hit is not None and (now_ts - local_hit[0]) < _MACHINERY_PREVIEW_CACHE_TTL_S:
            elapsed_ms = int((time.monotonic() - t_start) * 1000)
            logger.info(
                "machinery_preview_built slug=%s elapsed_ms=%d cache_hit=local",
                canon_slug,
                elapsed_ms,
            )
            return copy.deepcopy(local_hit[1])
        try:
            from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

            redis_client = await get_shared_async_redis()
            r_res = await bounded_redis_call(
                lambda: redis_client.get(_preview_redis_key(canon_slug, bool(include_children)))
            )
            if r_res.is_ok and r_res.value:
                raw_env = json.loads(
                    r_res.value.decode("utf-8")
                    if isinstance(r_res.value, (bytes, bytearray))
                    else r_res.value
                )
                if (
                    isinstance(raw_env, dict)
                    and raw_env.get("status") == "ok"
                    and isinstance(raw_env.get("cached_at"), (int, float))
                    and (now_ts - float(raw_env["cached_at"])) < _MACHINERY_PREVIEW_CACHE_TTL_S
                    and isinstance(raw_env.get("payload"), dict)
                ):
                    payload_hit = raw_env["payload"]
                    _machinery_preview_local_cache[cache_key] = (
                        float(raw_env["cached_at"]),
                        payload_hit,
                    )
                    elapsed_ms = int((time.monotonic() - t_start) * 1000)
                    logger.info(
                        "machinery_preview_built slug=%s elapsed_ms=%d cache_hit=redis",
                        canon_slug,
                        elapsed_ms,
                    )
                    return copy.deepcopy(payload_hit)
        except Exception:  # noqa: BLE001 — preview cache fails open
            logger.debug("machinery preview redis read failed for %s", canon_slug, exc_info=True)

    expected_sections = len(
        [
            s
            for s in ((defn.get("rule") or {}).get("sections") or ())
            if isinstance(s, Mapping)
        ]
    )
    producer = build_container_machinery_producer(defn, enabled=lambda: True)
    try:
        if isinstance(db, Mapping):
            outcome = await produce_container_machinery(db, defn, now=now)
            if outcome is None or isinstance(outcome, RoundupRefusal):
                code = (
                    outcome.reasons[0][1]
                    if isinstance(outcome, RoundupRefusal) and outcome.reasons
                    else "read_refused"
                )
                return _machinery_preview_error_response(
                    defn,
                    error_code=str(code),
                    exc_class=type(outcome).__name__ if outcome is not None else "RoundupRefusal",
                    allow_error_envelope=allow_error_envelope,
                )
            payload = compose_roundup_container(producer, outcome)
            feed_item = compose_roundup_feed_item(producer, outcome)
        else:
            feed_item, payload = await evaluate_roundup_producer(producer, db, now=now)
    except Exception as exc:
        exc_name = type(exc).__name__
        rollback_fn = getattr(db, "rollback", None)
        if callable(rollback_fn):
            try:
                rb = rollback_fn()
                if inspect.isawaitable(rb):
                    await rb
            except Exception:
                # Best-effort rollback on an aborted DB session; return the primary read error below.
                logger.debug("machinery preview session rollback failed", exc_info=True)
        return _machinery_preview_error_response(
            defn,
            error_code="read_failed",
            exc_class=exc_name,
            allow_error_envelope=allow_error_envelope,
        )

    if (
        payload is None
        or payload.get("state") != "published"
        or len(payload.get("sections") or ()) < max(1, expected_sections)
        or int(payload.get("member_count") or 0) <= 0
    ):
        return _machinery_preview_error_response(
            defn,
            error_code="incomplete_read",
            exc_class="RoundupRefusal",
            allow_error_envelope=allow_error_envelope,
        )

    out = copy.deepcopy(payload)
    if not include_children:
        out["children"] = []
    report = compute_visual_diversity_report(defn, feed_item, out)
    envelope = {
        "slug": canon_slug,
        "status": "ok",
        "definition": {
            "slug": defn["slug"],
            "name": out.get("container", {}).get("name") or defn.get("name"),
            "category": defn.get("category"),
            "kicker": defn.get("kicker"),
            "footer": defn.get("footer"),
        },
        "feed_item": feed_item,
        "container": out,
        "diversity_report": report,
    }
    if use_preview_cache:
        stored_at = time.time()
        _machinery_preview_local_cache[cache_key] = (stored_at, copy.deepcopy(envelope))
        try:
            from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

            redis_client = await get_shared_async_redis()
            blob = json.dumps({"status": "ok", "cached_at": stored_at, "payload": envelope})
            await bounded_redis_call(
                lambda: redis_client.set(
                    _preview_redis_key(canon_slug, bool(include_children)),
                    blob,
                    ex=int(_MACHINERY_PREVIEW_CACHE_TTL_S),
                )
            )
        except Exception:  # noqa: BLE001 — preview cache write fails open
            logger.debug("machinery preview redis write failed for %s", canon_slug, exc_info=True)
    elapsed_ms = int((time.monotonic() - t_start) * 1000)
    logger.info(
        "machinery_preview_built slug=%s elapsed_ms=%d cache_hit=miss",
        canon_slug,
        elapsed_ms,
    )
    return envelope


async def evaluate_machinery_candidates_preview(
    db: Any,
    *,
    slugs: Optional[Sequence[str]] = None,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Evaluate all (or selected) ``machinery-*.json`` candidates for Alex's private preview.

    Slice 6 Item 2c: every requested candidate produces either ``status='ok'`` or an explicit
    ``status='error'`` item — never silently dropping a failed candidate to return a shorter list.
    """
    wanted = set(slugs) if slugs is not None else None
    items: list[dict[str, Any]] = []
    for path in _ordered_machinery_candidate_paths():
        if wanted is not None and path.stem not in wanted:
            continue
        res = await serve_machinery_candidate_preview(
            path.stem, db, now=now, allow_error_envelope=True
        )
        if res is not None:
            items.append(res)
    return items
