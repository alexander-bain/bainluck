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
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from app.utils.container_presentation import (
    MEMBER_EVENT,
    MEMBER_MARKET,
    event_destination,
    market_destination,
)
from app.utils.graded_card import rendered_card_percents, rendered_duel_percents

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

    # Unify FOMC / rate-move outcomes onto house style ('25 bps decrease', 'No change', '25 bps increase', '50+ bps increase').
    if _HOLD_MOVE_RE.match(trimmed):
        return "No change"

    m_pre = _SIGNED_PREFIX_MOVE_RE.match(trimmed)
    if m_pre and re.search(r"bps|basis\s+points?", trimmed, re.IGNORECASE):
        direction = -1 if m_pre.group(1).lower() in {"cut", "cuts", "decrease", "lower"} else 1
        op_tok = (m_pre.group(2) or "").strip()
        plus_tok = (m_pre.group(4) or "").strip()
        val = _parse_float(m_pre.group(3))
        if math.isfinite(val):
            # Strict '>' on the FOMC 25-bps grid ('Hike >25bps', 'Cut >25bps') means 50+ bps.
            if op_tok.startswith(">") and not op_tok.startswith(">=") and abs(val - 25.0) < 1e-6:
                val = 50.0
                is_open = True
            else:
                is_open = bool(op_tok or plus_tok)
            word = "decrease" if direction < 0 else "increase"
            return f"{_format_bps_number(val)}{'+' if is_open else ''} bps {word}"

    m_suf = _SIGNED_SUFFIX_MOVE_RE.match(trimmed)
    if m_suf and re.search(r"bps|basis\s+points?", trimmed, re.IGNORECASE):
        direction = -1 if m_suf.group(4).lower() in {"cut", "cuts", "decrease"} else 1
        op_tok = (m_suf.group(1) or "").strip()
        plus_tok = (m_suf.group(3) or "").strip()
        or_more = bool(re.search(r"\bor\s+(?:more|larger|greater)$", trimmed, re.IGNORECASE))
        val = _parse_float(m_suf.group(2))
        if math.isfinite(val):
            if op_tok.startswith(">") and not op_tok.startswith(">=") and abs(val - 25.0) < 1e-6:
                val = 50.0
                is_open = True
            else:
                is_open = bool(op_tok or plus_tok or or_more)
            word = "decrease" if direction < 0 else "increase"
            return f"{_format_bps_number(val)}{'+' if is_open else ''} bps {word}"

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


def _initials(label: str) -> str:
    words = [w for w in re.split(r"\s+", label.strip()) if w]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[-1][0]).upper()


def _fallback_color(label: str) -> str:
    key = _norm_key(label)
    if "democrat" in key:
        return "#2563EB"
    if "republican" in key or key == "gop":
        return "#DC2626"
    h = sum(ord(ch) for ch in key)
    return _PALETTE_FALLBACK[h % len(_PALETTE_FALLBACK)]


class SubjectArtResolver:
    """Unified verified-art resolver across teams, people, and films/series (#12659, #12850)."""

    def __init__(self) -> None:
        self._by_norm: dict[str, dict[str, Any]] = {}
        self._load_catalogs()

    def _register(self, aliases: Sequence[str], record: dict[str, Any]) -> None:
        for raw in aliases:
            nk = _norm_key(raw)
            if nk and nk not in self._by_norm:
                self._by_norm[nk] = record

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
                self._register(list(item.get("aliases") or ()) + [str(item.get("key") or "")], rec)
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
                if entry.get("entity_key"):
                    aliases.append(str(entry["entity_key"]))
                self._register(
                    aliases,
                    {
                        "url": str(entry["url"]),
                        "kind": str(entry.get("kind") or "person"),
                        "detail": str(entry.get("verified_subject") or "")[:44],
                        "accent_color": "",
                        "author": entry.get("author"),
                        "license": entry.get("license"),
                        "source_page": entry.get("source_page"),
                    },
                )

    def resolve(
        self,
        subject: str,
        *,
        explicit_url: Optional[str] = None,
        explicit_color: Optional[str] = None,
    ) -> dict[str, Any]:
        clean_subj = _OUTCOME_PROP_SUFFIX_RE.sub("", subject.strip())
        nk = _norm_key(clean_subj) or _norm_key(subject)
        hit = self._by_norm.get(nk)
        url = explicit_url or (hit["url"] if hit else None)
        color = explicit_color or (hit.get("accent_color") if hit else None) or _fallback_color(clean_subj or subject)
        return {
            "url": url,
            "kind": (hit.get("kind") if hit else ("explicit" if url else "monogram")),
            "detail": (hit.get("detail") if hit else "") or "",
            "accent_color": color,
            "initials": _initials(clean_subj or subject),
        }


@lru_cache(maxsize=1)
def _default_art_resolver() -> SubjectArtResolver:
    return SubjectArtResolver()


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
        if len(selected_items) >= 2 and all(
            0.34 <= float(it.get("fav_prob") or 0.5) <= 0.66 for it in selected_items
        ):
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

    # ── Sports / Awards / General cleanup ────────────────────────────────
    is_oscar_nom = bool(re.match(r"^oscar\s+nominees?:", cleaned, re.IGNORECASE))
    cleaned = re.sub(
        r"^(?:NFL:\s*|Pro\s+Football:?\s*|NFL\s+(?=(?:Passing|Rushing|Receiving)\b)|Oscar\s+Winners?:\s*|Oscar\s+nominees?:\s*|Oscars?\s+\d{4}:\s*|2028\s+U\.S\.\s*|2028\s+)",
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


def _market_matches_query(market: Mapping[str, Any], query: Mapping[str, Any]) -> bool:
    status = str(market.get("status") or "open").lower()
    if status not in {"open", "active"}:
        return False
    title_low = str(market.get("name") or "").lower()
    if not title_low:
        return False

    req_tokens = [str(t).lower() for t in (query.get("title_all_tokens") or ()) if str(t).strip()]
    if any(tok not in title_low for tok in req_tokens):
        return False

    any_tokens = [str(t).lower() for t in (query.get("any_tokens") or ()) if str(t).strip()]
    if any_tokens and not any(tok in title_low for tok in any_tokens):
        return False

    excl_tokens = [str(t).lower() for t in (query.get("exclude_tokens") or ()) if str(t).strip()]
    if any(tok in title_low for tok in excl_tokens):
        return False

    raw_outcomes = market.get("top_outcomes") or market.get("outcomes") or ()
    priced = [
        o
        for o in raw_outcomes
        if isinstance(o, Mapping)
        and isinstance(o.get("probability"), (int, float))
        and 0.0 < float(o["probability"]) < 1.0
        and not _PLACEHOLDER_OUTCOME_RE.match(str(o.get("name") or "").strip())
    ]
    if not priced:
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

    return True


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
        pct_int = max(1, min(99, int(rp))) if 0.0 < float(r["probability"]) < 1.0 else int(rp)
        r["rendered_percent"] = pct_int
        by_oid[int(r["id"])] = pct_int
        nk = _norm_key(_clean_outcome_label(str(r["name"])))
        if nk and nk not in by_key:
            by_key[nk] = pct_int
        raw_nk = _norm_key(str(r["name"]))
        if raw_nk and raw_nk not in by_key:
            by_key[raw_nk] = pct_int
    return rows, by_oid, by_key


def _hydrate_market_visual_item(
    market: Mapping[str, Any],
    *,
    max_outcomes: int,
    resolver: SubjectArtResolver,
    content_kind: Optional[str] = None,
) -> dict[str, Any]:
    mid = int(market["id"])
    raw_outcomes = market.get("top_outcomes") or market.get("outcomes") or ()
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
                "art": {
                    "url": None,
                    "kind": "none",
                    "detail": "",
                    "accent_color": "",
                    "initials": "",
                },
            }
        ]
    else:
        kept = valid[:max_outcomes]
        outcomes_out = []
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
            )
            pct_val = int(o.get("rendered_percent") or _half_up_pct(p))
            outcomes_out.append(
                {
                    "outcome_id": oid,
                    "name": o_name,
                    "probability": p,
                    "rendered_percent": pct_val,
                    "opening_probability": o.get("opening_probability"),
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
    card_copy = dict(market)
    card_copy["content_kind"] = effective_kind
    card_copy["member_page_numbers"] = mpn

    return {
        "market_id": mid,
        "title": _clean_section_market_label(str(market.get("name") or "")),
        "raw_title": str(market.get("name") or ""),
        "href": f"/futures/{mid}",
        "source": str(market.get("source") or ""),
        "lead_prob": lead_prob,
        "leader_outcome_id": leader_outcome_id,
        "scale_ordered": scale_ordered,
        "content_kind": effective_kind,
        "closeness_to_50": abs(lead_prob - 0.5),
        "outcomes": outcomes_out,
        "member_page_numbers": mpn,
        "card": card_copy,
    }


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
    home_p = event.get("hero_probability")
    away_p = event.get("hero_probability_away")
    if home_p is None:
        home_p = odds.get("home_probability")
    if away_p is None:
        away_p = odds.get("away_probability")

    pre = event.get("prematch_odds") if isinstance(event.get("prematch_odds"), Mapping) else {}
    if status in {"completed", "final", "closed"} and (home_p is None or away_p is None):
        home_p = pre.get("home_probability")
        away_p = pre.get("away_probability")

    if not isinstance(home_p, (int, float)) or not isinstance(away_p, (int, float)):
        return None
    hp = float(home_p)
    ap = float(away_p)
    if hp <= 0.0 and ap <= 0.0:
        return None

    home_team = str(event.get("home_team") or "").strip()
    away_team = str(event.get("away_team") or "").strip()
    home_td = event.get("home_team_data") if isinstance(event.get("home_team_data"), Mapping) else {}
    away_td = event.get("away_team_data") if isinstance(event.get("away_team_data"), Mapping) else {}

    home_art = resolver.resolve(
        home_team,
        explicit_url=home_td.get("logo_small") or home_td.get("logo_large") or event.get("home_image_url"),
        explicit_color=home_td.get("primary_color"),
    )
    away_art = resolver.resolve(
        away_team,
        explicit_url=away_td.get("logo_small") or away_td.get("logo_large") or event.get("away_image_url"),
        explicit_color=away_td.get("primary_color"),
    )

    # Slice 5 Note 1: send two-way game pairs through rendered_duel_percents so away_pct + home_pct == 100.
    away_pct_raw, home_pct_raw = rendered_duel_percents(ap, hp)
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
    return {
        "event_id": eid,
        "href": f"/events/{eid}",
        "status": status,
        "commence_time": str(event.get("commence_time") or ""),
        "sport": str(event.get("sport") or ""),
        "home_team": home_team,
        "away_team": away_team,
        "home_short": home_team.split()[-1] if home_team else "",
        "away_short": away_team.split()[-1] if away_team else "",
        "home_prob": hp,
        "away_prob": ap,
        "home_pct": home_pct,
        "away_pct": away_pct,
        "home_score": event.get("home_score"),
        "away_score": event.get("away_score"),
        "home_art": home_art,
        "away_art": away_art,
        "fav_prob": fav_prob,
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
        series_out.append(
            {
                "outcome_id": oid,
                "name": str(o["name"]),
                "current_pct": cur_pct,
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


async def _load_snapshot_from_db(
    db: Any,
    definition: Mapping[str, Any],
    now_dt: datetime,
) -> dict[str, Any]:
    """Load candidate events, open futures markets, paired sets, and outcome histories."""
    if isinstance(db, Mapping) and (
        "events" in db or "markets" in db or "paired_sets" in db or "market_histories" in db
    ):
        raw_mh = db.get("market_histories") or {}
        norm_mh: dict[int, list[dict[str, Any]]] = {}
        if isinstance(raw_mh, Mapping):
            for k, v in raw_mh.items():
                try:
                    norm_mh[int(k)] = [dict(x) for x in (v or ()) if isinstance(x, Mapping)]
                except (TypeError, ValueError):
                    continue
        return {
            "events": list(db.get("events") or ()),
            "markets": list(db.get("markets") or ()),
            "paired_sets": dict(db.get("paired_sets") or {}),
            "market_histories": norm_mh,
        }

    from sqlalchemy import and_, func, or_, select
    from sqlalchemy.orm import selectinload

    from app.models.models import Event, FuturesMarket, FuturesOddsSnapshot
    from app.routes.futures import (
        _apply_verified_title_to_detail,
        _fleet_newest_observation,
        _format_market_detail,
        _game_container_lead_leg,
        _game_container_leg_sides,
        _resolve_verified_title,
        _verified_title_market_stmt,
        _withheld_price_outcome_ids,
        out_legs_by_market,
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
            .where(
                Event.sport.in_(sorted(sport_keys)),
                Event.commence_time >= recent_floor,
                Event.commence_time <= horizon,
            )
            .order_by(Event.commence_time.asc())
            .limit(40)
        )
        rows = (await db.execute(stmt)).scalars().all()
        for ev in rows:
            # Slice 6 Item 2b: use resolve_hero (same authority as GET /api/events/{id})
            hero = resolve_hero(ev)
            if hero is None:
                continue
            hp = float(hero.home_probability)
            ap = float(hero.away_probability)
            away_pct_raw, home_pct_raw = rendered_duel_percents(ap, hp)
            away_pct = int(away_pct_raw) if away_pct_raw is not None else _half_up_pct(ap)
            home_pct = int(home_pct_raw) if home_pct_raw is not None else _half_up_pct(hp)
            events_out.append(
                {
                    "id": ev.id,
                    "sport": ev.sport,
                    "sport_name": ev.sport.upper(),
                    "home_team": ev.home_team,
                    "away_team": ev.away_team,
                    "commence_time": ev.commence_time.isoformat() if ev.commence_time else "",
                    "status": ev.status or "scheduled",
                    "home_score": ev.home_score,
                    "away_score": ev.away_score,
                    "hero_probability": hp,
                    "hero_probability_away": ap,
                    "hero_source": hero.source,
                    "current_odds": {
                        "home_probability": hp,
                        "away_probability": ap,
                    },
                    "member_page_numbers": {
                        "away_pct": away_pct,
                        "home_pct": home_pct,
                    },
                }
            )

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
        all_paired = await load_live_paired_metric_sets(db)
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
        m_rows: list[Any] = []
        seen_mids: set[int] = set()
        if needs_markets:
            m_stmt = (
                select(FuturesMarket)
                .options(selectinload(FuturesMarket.outcomes))
                .where(FuturesMarket.status == "open")
                .order_by(FuturesMarket.volume.desc().nullslast())
                .limit(800)
            )
            m_rows = list((await db.execute(m_stmt)).scalars().all())
            seen_mids = {fm.id for fm in m_rows}
            extra_clauses = []
            for sec in sections_cfg:
                if not isinstance(sec, Mapping) or not isinstance(sec.get("atom_query"), Mapping):
                    continue
                aq = sec["atom_query"]
                if aq.get("kind") not in {"markets", "market_history"}:
                    continue
                all_toks = [str(t).strip() for t in (aq.get("title_all_tokens") or ()) if str(t).strip()]
                any_toks = [str(t).strip() for t in (aq.get("any_tokens") or ()) if str(t).strip()]
                excl_toks = [str(t).strip() for t in (aq.get("exclude_tokens") or ()) if str(t).strip()]
                parts = [FuturesMarket.name.ilike(f"%{t}%") for t in all_toks]
                if any_toks:
                    parts.append(or_(*(FuturesMarket.name.ilike(f"%{t}%") for t in any_toks)))
                for ex in excl_toks:
                    parts.append(~FuturesMarket.name.ilike(f"%{ex}%"))
                if parts:
                    extra_clauses.append(and_(*parts))
            if extra_clauses:
                targeted_stmt = (
                    select(FuturesMarket)
                    .options(selectinload(FuturesMarket.outcomes))
                    .where(FuturesMarket.status == "open", or_(*extra_clauses))
                    .order_by(FuturesMarket.volume.desc().nullslast(), FuturesMarket.id.asc())
                    .limit(200)
                )
                for fm in (await db.execute(targeted_stmt)).scalars().all():
                    if fm.id not in seen_mids:
                        seen_mids.add(fm.id)
                        m_rows.append(fm)

        prelim_markets: list[dict[str, Any]] = []
        for fm in m_rows:
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
                    "volume": float(fm.volume or 0.0),
                    "image_url": fm.image_url,
                    "llm_sport_category": fm.llm_sport_category,
                    "top_outcomes": top_outs,
                }
            )

        # Slice 6 Item 2b: format every candidate member market through the exact same
        # verified_title detail pipeline as GET /api/futures/{id}?representation=verified_title
        # so every number on a card or page equals the member's own page at the same moment.
        candidate_mids: set[int] = set(paired_stage_mids)
        for sec in sections_cfg:
            if not isinstance(sec, Mapping) or not isinstance(sec.get("atom_query"), Mapping):
                continue
            aq = sec["atom_query"]
            if aq.get("kind") in {"markets", "market_history"}:
                cap_n = max(int(aq.get("max_items", 6)) + 4, 8)
                matched_sec = [pm for pm in prelim_markets if _market_matches_query(pm, aq)]
                for pm in matched_sec[:cap_n]:
                    candidate_mids.add(int(pm["id"]))

        detail_by_mid: dict[int, dict[str, Any]] = {}
        mpn_by_mid: dict[int, dict[str, Any]] = {}
        if candidate_mids:
            vt_rows = (
                await db.execute(
                    _verified_title_market_stmt().where(
                        FuturesMarket.id.in_(sorted(candidate_mids))
                    )
                )
            ).unique().scalars().all()
            out_map = await out_legs_by_market(list(vt_rows))
            for fm in vt_rows:
                unsupported_ids = await _withheld_price_outcome_ids(db, fm)
                leg_sides = await _game_container_leg_sides(db, fm)
                lead_leg = await _game_container_lead_leg(db, fm, leg_sides)
                detail = _format_market_detail(
                    fm,
                    None,
                    unsupported_ids,
                    fleet_newest_observation=await _fleet_newest_observation(db, fm),
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
                by_fold: dict[str, tuple[float, int]] = {}
                formatted_outs: list[dict[str, Any]] = []
                img_by_oid = {o.id: getattr(o, "image_url", None) for o in (fm.outcomes or ())}
                for idx, row in enumerate(d_outs):
                    prob = row.get("probability")
                    if prob is None or not isinstance(prob, (int, float)) or not math.isfinite(float(prob)):
                        continue
                    p_f = float(prob)
                    oid = int(row["id"])
                    rp = row.get("rendered_percent")
                    if rp is None and idx < len(card_pcts) and card_pcts[idx] is not None:
                        rp = int(card_pcts[idx])
                    if rp is None:
                        rp = _half_up_pct(p_f)
                    pct_int = max(1, min(99, int(rp))) if 0.0 < p_f < 1.0 else int(rp)
                    by_oid[oid] = pct_int
                    r_name = str(row.get("name") or "")
                    for nk in (_norm_key(_clean_outcome_label(r_name)), _norm_key(r_name)):
                        if nk and nk not in by_key:
                            by_key[nk] = pct_int
                    fk = fold_outcome_key(r_name)
                    if fk and fk not in by_fold:
                        by_fold[fk] = (p_f, pct_int)
                    formatted_outs.append(
                        {
                            "id": oid,
                            "name": r_name,
                            "probability": p_f,
                            "rendered_percent": pct_int,
                            "opening_probability": row.get("opening_probability"),
                            "image_url": img_by_oid.get(oid),
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
                    "by_oid_prob_pct": {int(o["id"]): (float(o["probability"]), int(o["rendered_percent"])) for o in formatted_outs},
                    "by_fold_prob_pct": by_fold,
                }

        for pm in prelim_markets:
            mid = int(pm["id"])
            if mid in detail_by_mid:
                pm["top_outcomes"] = detail_by_mid[mid]["top_outcomes"]
                pm["member_page_numbers"] = mpn_by_mid[mid]
            markets_out.append(pm)

        # Sync paired_stage entries to their linked stage_1_market.id & stage_2_market.id member pages
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
                        p_s1, pct_s1 = match_s1
                        # Ensure client renderedPercent(stage_1_probability) equals pct_s1 exactly
                        entry["stage_1_probability"] = (
                            p_s1 if _half_up_pct(p_s1) == pct_s1 else round(pct_s1 / 100.0, 4)
                        )
                        entry["stage_1_rendered_percent"] = pct_s1
                if s2_det:
                    s2_oid = entry.get("stage_2_outcome_id")
                    match_s2 = (
                        s2_det["by_oid_prob_pct"].get(int(s2_oid))
                        if isinstance(s2_oid, int) and s2_oid in s2_det["by_oid_prob_pct"]
                        else s2_det["by_fold_prob_pct"].get(fk)
                    )
                    if match_s2 is not None:
                        p_s2, pct_s2 = match_s2
                        entry["stage_2_probability"] = (
                            p_s2 if _half_up_pct(p_s2) == pct_s2 else round(pct_s2 / 100.0, 4)
                        )
                        entry["stage_2_rendered_percent"] = pct_s2
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
        all_hist_queries = list(history_queries) + card_market_queries
        if all_hist_queries and markets_out:
            wanted_oids: set[int] = set()
            max_hours = max([int(hq.get("hours") or 168) for hq in all_hist_queries] or [168])
            for hq in all_hist_queries:
                matched_for_hq = [m_dict for m_dict in markets_out if _market_matches_query(m_dict, hq)]
                for m_dict in matched_for_hq[:12]:
                    outs_sorted = sorted(
                        m_dict["top_outcomes"],
                        key=lambda x: -float(x.get("probability") or 0.0),
                    )
                    for o_d in outs_sorted[:4]:
                        wanted_oids.add(int(o_d["id"]))
            if wanted_oids:
                cutoff = now_dt - timedelta(hours=max_hours)
                # Partition by outcome_id so large outcome IDs are never starved behind a global row cap.
                ranked_subq = (
                    select(
                        FuturesOddsSnapshot.outcome_id.label("outcome_id"),
                        FuturesOddsSnapshot.captured_at.label("captured_at"),
                        FuturesOddsSnapshot.probability.label("probability"),
                        func.row_number()
                        .over(
                            partition_by=FuturesOddsSnapshot.outcome_id,
                            order_by=FuturesOddsSnapshot.captured_at.desc(),
                        )
                        .label("rn"),
                    )
                    .where(
                        FuturesOddsSnapshot.outcome_id.in_(sorted(wanted_oids)),
                        FuturesOddsSnapshot.captured_at >= cutoff,
                    )
                    .subquery()
                )
                h_stmt = (
                    select(
                        ranked_subq.c.outcome_id,
                        ranked_subq.c.captured_at,
                        ranked_subq.c.probability,
                    )
                    .where(ranked_subq.c.rn <= 96)
                    .order_by(ranked_subq.c.outcome_id.asc(), ranked_subq.c.captured_at.asc())
                )
                for oid_val, cap_at, prob_val in (await db.execute(h_stmt)).all():
                    oid = int(oid_val)
                    histories_out.setdefault(oid, []).append(
                        {
                            "timestamp": cap_at.isoformat() if cap_at else "",
                            "probability": float(prob_val),
                        }
                    )

    return {
        "events": events_out,
        "markets": markets_out,
        "paired_sets": paired_out,
        "market_histories": histories_out,
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


def _twin_market_key(title: str) -> str:
    """Canonicalize cross-venue twin titles (e.g. 'April 2027 Fed Decision' vs 'April Fed Decision')."""
    low = title.strip().lower()
    m_fomc = re.match(r"^([a-z]+)(?:\s+\d{4})?\s+fed\s+decision$", low)
    if m_fomc:
        return f"fomc:{m_fomc.group(1)}"
    m_unemp = re.match(r"^([a-z]+)(?:\s+\d{4})?\s+u\.s\.\s+unemployment(?:\s+rate)?$", low)
    if m_unemp:
        return f"us_unemp:{_expand_month_token(m_unemp.group(1)).lower()}"
    return _norm_key(title)


def _dedupe_twin_markets(markets: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the highest-liquidity canonical market when two venues list the same cleaned title."""
    seen_titles: set[str] = set()
    out: list[dict[str, Any]] = []
    for m in markets:
        norm_t = _twin_market_key(str(m["title"]))
        if norm_t in seen_titles:
            continue
        seen_titles.add(norm_t)
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


def _format_event_date_span(events: Sequence[Mapping[str, Any]]) -> str:
    dts: list[datetime] = []
    for ev in events:
        raw = str(ev.get("commence_time") or "").strip()
        if not raw:
            continue
        try:
            dts.append(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except ValueError:
            continue
    if not dts:
        return ""
    lo = min(dts)
    hi = max(dts)
    if lo.month == hi.month and lo.day == hi.day:
        return f"{lo.strftime('%b')} {lo.day}"
    if lo.month == hi.month:
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
        "nfl",
        "nba",
        "mlb",
        "nhl",
        "wnba",
        "afc",
        "nfc",
        "oscar",
        "oscars",
        "senate",
        "house",
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
            if core.lower() in _PROPER_WORDS_KEEP or any(ch.isdigit() for ch in core):
                if core.upper() in {"NFL", "NBA", "MLB", "NHL", "WNBA", "AFC", "NFC", "GDP", "CPI", "FOMC", "US"}:
                    words.append(w.upper())
                elif core.lower() == "u.s.":
                    words.append("U.S.")
                else:
                    words.append(core.capitalize())
            else:
                words.append(w.lower())
        joined = " ".join(words)
        out = joined if joined.lower().startswith(("the ", "a ", "an ")) else f"the {joined}"

    if capitalize_first and out:
        return out[0].upper() + out[1:]
    return out


def _build_dynamic_title_from_set(
    definition: Mapping[str, Any],
    built_sections: Sequence[Mapping[str, Any]],
) -> str:
    """Build a reader-facing title dynamically from the live set (Slice 3 Item 4).

    Every number and name comes directly from ``built_sections``:
    - Paired-stage ceremony: ``"<Leader> leads <Category> at <W>%, with <N> contenders at 75%+ to be nominated"``
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
                win_pct = int(
                    top.get("stage_2_rendered_percent")
                    or _half_up_pct(float(top.get("stage_2_probability") or 0.0))
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
                    return f"{leader_name} leads {cat_label} at {win_pct}%, with {strong_nom} contenders at 75%+ to be nominated"
                return f"{leader_name} leads {cat_label} at {win_pct}%"

    # 2. Event-led slate (e.g. NFL slate — named by biggest/closest game & dates, never week number)
    event_items: list[Mapping[str, Any]] = []
    tossup_count = 0
    for sec in built_sections:
        vb = sec.get("visual_block") or {}
        if vb.get("form_id") in {"coin_flip_matchups", "matchup_slate"}:
            its = [it for it in (vb.get("items") or ()) if isinstance(it, Mapping)]
            if vb.get("form_id") == "coin_flip_matchups":
                tossup_count = max(tossup_count, len(its))
            event_items.extend(its)
    if event_items:
        lead_ev = event_items[0]
        matchup = f"{lead_ev.get('away_short') or lead_ev.get('away_team')} at {lead_ev.get('home_short') or lead_ev.get('home_team')}"
        span = _format_event_date_span(event_items)
        span_clause = f" the {span} slate" if span else " this slate"
        if tossup_count >= 2:
            return f"{matchup} headlines{span_clause}, with {tossup_count} toss-up games"
        return f"{matchup} headlines{span_clause}"

    # 3. Market-led sets (duel + contender field, or numerical-scale rate set)
    duel_item: Optional[Mapping[str, Any]] = None
    spotlight_item: Optional[Mapping[str, Any]] = None
    sibling_items: list[Mapping[str, Any]] = []
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

    def _fav_outcome(m_item: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        outs = [o for o in (m_item.get("outcomes") or ()) if isinstance(o, Mapping)]
        if not outs:
            return None
        return max(outs, key=lambda o: float(o.get("probability") or 0.0))

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
                lead_subj = _prose_market_phrase(str(spotlight_item["title"]), capitalize_first=True)
                sib_phrase = _prose_market_phrase(str(sibling_items[0]["title"]))
                return (
                    f"{lead_subj} prices {sp_fav['name']} at {sp_fav['rendered_percent']}%, "
                    f"with {sib_fav['name']} leading {sib_phrase} at {sib_fav['rendered_percent']}%"
                )
        if sp_fav:
            sp_phrase = _prose_market_phrase(str(spotlight_item["title"]))
            return f"{_prose_outcome_name(str(sp_fav['name']))} leads {sp_phrase} at {sp_fav['rendered_percent']}%"

    return str(definition.get("name") or definition.get("slug") or "Round-Up")


async def produce_container_machinery(
    db: Any,
    definition: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Any:
    """Evaluate a declarative ``container_machinery`` definition into card + multi-section container."""
    from app.utils.roundup_containers import RoundupMembers, RoundupRefusal

    now_dt = now or datetime.now(timezone.utc)
    resolver = _default_art_resolver()
    rule = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
    sections_cfg = rule.get("sections") or ()
    if not isinstance(sections_cfg, Sequence) or not sections_cfg:
        return RoundupRefusal((("container_machinery", "empty_sections"),))

    snapshot = await _load_snapshot_from_db(db, definition, now_dt)
    all_events = snapshot["events"]
    all_markets = snapshot["markets"]
    paired_sets = snapshot["paired_sets"]
    market_histories = snapshot["market_histories"]

    built_by_idx: dict[int, dict[str, Any]] = {}
    all_member_envelopes: list[dict[str, Any]] = []
    seen_member_keys: set[tuple[str, int]] = set()
    lead_paired_set: Optional[dict[str, Any]] = None

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
            from app.services.paired_metric_register import fold_outcome_key

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
                        pct_val = int(e.get(rp_field) or _half_up_pct(float(p_val)))
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
                    "name": str(m_meta.get("name") or sec_title),
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
            band = aq.get("probability_band")
            band_lo = float(band[0]) if isinstance(band, Sequence) and len(band) == 2 else 0.0
            band_hi = float(band[1]) if isinstance(band, Sequence) and len(band) == 2 else 1.0
            ev_items: list[dict[str, Any]] = []
            for raw_ev in all_events:
                if sport_req and str(raw_ev.get("sport") or "").lower() != sport_req:
                    continue
                ev_status = str(raw_ev.get("status") or "").strip().lower()
                if not include_completed and ev_status in {"completed", "final", "closed"}:
                    continue
                if (MEMBER_EVENT, int(raw_ev["id"])) in seen_member_keys:
                    continue
                hyd = _hydrate_event_visual_item(raw_ev, resolver=resolver)
                if hyd is None:
                    continue
                if not (band_lo <= hyd["home_prob"] <= band_hi):
                    continue
                ev_items.append(hyd)
            order_by = str(aq.get("order_by") or "kickoff_asc")
            if order_by == "closeness_to_50":
                ev_items.sort(key=lambda x: (x["closeness_to_50"], x["commence_time"]))
            else:
                ev_items.sort(key=lambda x: x["commence_time"])
            ev_items = ev_items[:max_items]
            if len(ev_items) < min_items:
                return RoundupRefusal((("container_machinery", f"too_few_events:{sec_key}"),))
            form_id = choose_section_form("events", ev_items)
            sec_members = []
            for it in ev_items:
                eid = it["event_id"]
                env = {
                    "type": MEMBER_EVENT,
                    "id": eid,
                    "destination": event_destination(eid),
                    "card": it["card"],
                    "event_id": eid,
                }
                sec_members.append(env)
                if (MEMBER_EVENT, eid) not in seen_member_keys:
                    seen_member_keys.add((MEMBER_EVENT, eid))
                    all_member_envelopes.append(env)
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
            matched_h = [
                _hydrate_market_visual_item(m, max_outcomes=max_outcomes, resolver=resolver, content_kind="history")
                for m in all_markets
                if (MEMBER_MARKET, int(m["id"])) not in seen_member_keys
                and _market_matches_query(m, aq)
            ]
            matched_h = _dedupe_twin_markets(matched_h)
            order_by = str(aq.get("order_by") or "movement_desc")
            if order_by == "closeness_to_50":
                matched_h.sort(key=lambda x: (x["closeness_to_50"], -x["lead_prob"]))
            else:
                matched_h.sort(key=lambda x: (-x["lead_prob"], x["title"].casefold()))
            if len(matched_h) < min_items:
                return RoundupRefusal((("container_machinery", f"too_few_history_markets:{sec_key}"),))
            all_chart_items = [
                _build_history_visual_item(hm, market_histories, now_dt=now_dt, hours=hours)
                for hm in matched_h
            ]
            moving_charts = [ci for ci in all_chart_items if _history_chart_moved(ci)]
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
                            {k: v for k, v in ci.items() if k != "card"}
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
                            {k: v for k, v in fm_it.items() if k != "card"}
                            for fm_it in fallback_matched
                        ],
                    },
                }
            continue

        # aq_kind == "markets"
        explicit_ck = str(aq.get("content_kind") or "").strip().lower() or None
        matched = [
            _hydrate_market_visual_item(
                m,
                max_outcomes=max_outcomes,
                resolver=resolver,
                content_kind=explicit_ck,
            )
            for m in all_markets
            if (MEMBER_MARKET, int(m["id"])) not in seen_member_keys
            and _market_matches_query(m, aq)
        ]
        matched = _dedupe_twin_markets(matched)
        order_by = str(aq.get("order_by") or "lead_prob_desc")
        if order_by == "closeness_to_50":
            matched.sort(key=lambda x: (x["closeness_to_50"], -x["lead_prob"]))
        else:
            matched.sort(key=lambda x: (-x["lead_prob"], x["title"].casefold()))
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
                    {k: v for k, v in it.items() if k != "card"}
                    for it in matched
                ],
            },
        }

    built_sections = [built_by_idx[idx] for idx in sorted(built_by_idx)]

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
            win_pct = int(e.get("stage_2_rendered_percent") or _half_up_pct(win_p))
            nom_p = e.get("stage_1_probability")
            row_d: dict[str, Any] = {
                "market_id": w_mid,
                "outcome_id": int(e.get("stage_2_outcome_id") or (w_mid * 100 + idx + 1)),
                "label": str(e.get("subject") or ""),
                "probability": win_p,
                "rendered_percent": win_pct,
            }
            if isinstance(nom_p, (int, float)):
                row_d["secondary_probability"] = float(nom_p)
                row_d["secondary_rendered_percent"] = int(
                    e.get("stage_1_rendered_percent") or _half_up_pct(float(nom_p))
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
        not has_card_art
        and vb_form not in {"paired_stage_bars", "coin_flip_matchups", "matchup_slate"}
        and (vb.get("items") or ())
    ):
        own_lead_market = vb["items"][0]
        if isinstance(own_lead_market, Mapping) and own_lead_market.get("outcomes"):
            own_chart = _build_history_visual_item(
                own_lead_market, market_histories, now_dt=now_dt, hours=168
            )
            if _history_chart_moved(own_chart):
                mini_chart = {k: v for k, v in own_chart.items() if k != "card"}

    machinery_card: dict[str, Any] = {
        "slug": slug,
        "form_id": vb_form,
        "kicker": str(definition.get("kicker") or "ROUND-UP"),
        "title": dynamic_title,
        "subtitle": str(card_sec.get("note") or ""),
        "footer": clean_footer,
        "scale_ordered": card_scale_ordered,
        "section_count": len(built_sections),
        "destination_href": dest_href,
        "rows": card_visual_rows,
    }
    if mini_chart is not None:
        machinery_card["mini_chart"] = mini_chart

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
    )


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
    for nk in (_norm_key(_clean_outcome_label(label)), _norm_key(label)):
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

    for sec in sections:
        for m in sec.get("members") or ():
            if not isinstance(m, Mapping):
                continue
            m_type = str(m.get("type") or "")
            mid = int(m.get("id") or 0)
            card_obj = m.get("card") if isinstance(m.get("card"), Mapping) else {}
            mpn = card_obj.get("member_page_numbers")
            if m_type == "event":
                if isinstance(mpn, Mapping):
                    event_truth[mid] = {
                        "away_pct": int(mpn["away_pct"]),
                        "home_pct": int(mpn["home_pct"]),
                    }
                elif (
                    isinstance(card_obj.get("rendered_away_percent"), int)
                    and isinstance(card_obj.get("rendered_home_percent"), int)
                ):
                    event_truth[mid] = {
                        "away_pct": int(card_obj["rendered_away_percent"]),
                        "home_pct": int(card_obj["rendered_home_percent"]),
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
    card_checked = 0
    card_mismatches: list[dict[str, Any]] = []
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
                shown_s2 = int(e.get("stage_2_rendered_percent") or _half_up_pct(float(e["stage_2_probability"])))
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
    page_checked = 0
    page_mismatches: list[dict[str, Any]] = []
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
                    shown_s2 = int(e.get("stage_2_rendered_percent") or _half_up_pct(float(e["stage_2_probability"])))
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
    slug: str,
    defn: Mapping[str, Any],
    *,
    error_code: str,
    allow_error_envelope: bool,
) -> dict[str, Any]:
    """Slice 6 Item 2c: a failed read surfaces an explicit error state, never an empty or shorter grouping."""
    from fastapi import HTTPException

    msg = "Couldn't load this grouping right now. Please try again."
    if not allow_error_envelope:
        raise HTTPException(
            status_code=503,
            detail={
                "state": "unavailable",
                "slug": slug,
                "error_code": error_code,
                "message": msg,
            },
        )
    return {
        "slug": slug,
        "status": "error",
        "error": msg,
        "error_code": error_code,
        "definition": {
            "slug": str(defn.get("slug") or slug),
            "name": str(defn.get("name") or slug),
            "category": str(defn.get("category") or ""),
            "kicker": str(defn.get("kicker") or ""),
            "footer": str(defn.get("footer") or ""),
        },
        "feed_item": None,
        "container": None,
        "diversity_report": None,
    }


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
    """
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
                    slug, defn, error_code=str(code), allow_error_envelope=allow_error_envelope
                )
            payload = compose_roundup_container(producer, outcome)
            feed_item = compose_roundup_feed_item(producer, outcome)
        else:
            feed_item, payload = await evaluate_roundup_producer(producer, db, now=now)
    except Exception:
        return _machinery_preview_error_response(
            slug, defn, error_code="read_failed", allow_error_envelope=allow_error_envelope
        )

    if (
        payload is None
        or payload.get("state") != "published"
        or len(payload.get("sections") or ()) < max(1, expected_sections)
        or int(payload.get("member_count") or 0) <= 0
    ):
        return _machinery_preview_error_response(
            slug, defn, error_code="incomplete_read", allow_error_envelope=allow_error_envelope
        )

    out = copy.deepcopy(payload)
    if not include_children:
        out["children"] = []
    report = compute_visual_diversity_report(defn, feed_item, out)
    return {
        "slug": slug,
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
