"""Plain-English formatting for basis-point rate-move outcome labels (#13196, Ruling 244: A).

Single source of truth shared by:
- ``series_card_labels.reader_outcome_name`` (futures pages, Discover cards,
  search/typeahead, Watch/My Stuff, iOS/Watch widgets via ``/api/futures/{id}``)
- ``container_machinery._clean_outcome_label`` (groupings)
- ``routes/economics.py`` and ``routes/market_moves.py`` (direct display sites)
- ``discover_card_archetypes._outcome_threshold_value`` (signed rate-ladder ordering
  on already-formatted labels)

The raw stored ``FuturesOutcome.name`` in the database stays untouched so cross-venue
matching, ingest, and historical lookup keys keep reading the venue's exact text.
"""

from __future__ import annotations

import math
import re
from typing import Optional

_NUM_CORE = r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?"

_BPS_TOKEN_RE = re.compile(r"\bbps\b|(?<=\d)bps\b|\bbasis\s+points?\b", re.IGNORECASE)

_COUNT_BPS_PAREN_RE = re.compile(
    r"^(\d+)(\+)?\s*\(\s*(\d+(?:\.\d+)?)(\+)?\s*(?:bps|basis\s+points?)\s*\)$",
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

_RANGE_PREFIX_MOVE_RE = re.compile(
    rf"^(cut|cuts|decrease|lower|hike|hikes|increase|raise)\s*(?:by\s*)?({_NUM_CORE})\s*[-–—]\s*({_NUM_CORE})\s*(?:bps|basis\s+points?)$",
    re.IGNORECASE,
)

_MORE_THAN_PREFIX_MOVE_RE = re.compile(
    rf"^(cut|cuts|decrease|lower|hike|hikes|increase|raise)\s*(?:by\s*)?(?:more\s+than|over|above)\s+({_NUM_CORE})\s*(?:bps|basis\s+points?)$",
    re.IGNORECASE,
)

_MORE_THAN_SUFFIX_MOVE_RE = re.compile(
    rf"^(?:more\s+than|over|above)\s+({_NUM_CORE})\s*(?:bps|basis\s+points?)\s*(cut|cuts|decrease|hike|hikes|increase)$",
    re.IGNORECASE,
)

_PLAIN_RATE_MOVE_RE = re.compile(
    r"^(quarter|half|three-quarter|full|\d+(?:\.\d+)?)-point(?:\s+(or\s+(?:larger|more|greater)))?\s+(cut|decrease|increase|hike)$",
    re.IGNORECASE,
)

_PLAIN_OF_MOVE_RE = re.compile(
    r"^(cut|increase)\s+of\s+(up\s+to|more\s+than)\s+(?:a\s+)?(quarter|half|three-quarter|full|\d+(?:\.\d+)?)\s+points?$",
    re.IGNORECASE,
)

_PLAIN_COUNT_STEP_RE = re.compile(
    r"^(\d+)(\+)?(?:\s+(?:cuts?|hikes?))?\s*\(\s*(?:quarter\s+point|half\s+point|three-quarter\s+point|full\s+point|\d+(?:\.\d+)?\s+points?)(?:\s+or\s+(?:more|larger|greater))?\s*\)$",
    re.IGNORECASE,
)

_PLAIN_MAGNITUDE_BPS: dict[str, float] = {
    "quarter": 25.0,
    "half": 50.0,
    "three-quarter": 75.0,
    "full": 100.0,
}

_MARKET_CUT_RE = re.compile(r"\brate\s+cuts?\b|\bcuts?\b", re.IGNORECASE)
_MARKET_HIKE_RE = re.compile(r"\brate\s+hikes?\b|\bhikes?\b|\bincreases?\b", re.IGNORECASE)


def _parse_float(raw: str) -> float:
    return float(raw.replace(",", ""))


def plain_bps_step_words(val_bps: float) -> str:
    """Format a basis-point step size in plain English (e.g. 25 -> 'quarter point')."""
    rounded = round(val_bps, 4)
    if abs(rounded - 25.0) < 1e-6:
        return "quarter point"
    if abs(rounded - 50.0) < 1e-6:
        return "half point"
    if abs(rounded - 75.0) < 1e-6:
        return "three-quarter point"
    if abs(rounded - 100.0) < 1e-6:
        return "full point"
    pts = val_bps / 100.0
    if abs(pts - 1.0) < 1e-6:
        return "1 point"
    return f"{pts:g} points"


def _plain_bps_step_with_article(val_bps: float) -> str:
    """Format a basis-point step for prose after 'up to' / 'more than'."""
    words = plain_bps_step_words(val_bps)
    if words in {"quarter point", "half point", "three-quarter point", "full point"}:
        return f"a {words}"
    return words


def _plain_rate_more_than_label(val_bps: float, direction: int) -> str:
    """Format a strict '>' rate move without implying 'or larger' overlap (#13196)."""
    lead = "Cut" if direction < 0 else "Increase"
    return f"{lead} of more than {_plain_bps_step_with_article(val_bps)}"


def plain_rate_move_label(val_bps: float, direction: int, is_open: bool) -> str:
    """Ruling 244: A — format Fed/central-bank rate moves in plain English, never 'bps'."""
    word = "cut" if direction < 0 else "increase"
    rounded = round(val_bps, 4)
    if abs(rounded - 25.0) < 1e-6:
        mag = "Quarter-point"
    elif abs(rounded - 50.0) < 1e-6:
        mag = "Half-point"
    elif abs(rounded - 75.0) < 1e-6:
        mag = "Three-quarter-point"
    elif abs(rounded - 100.0) < 1e-6:
        mag = "Full-point"
    else:
        pts = val_bps / 100.0
        mag = f"{pts:g}-point"
    if is_open:
        return f"{mag} or larger {word}"
    return f"{mag} {word}"


def _infer_count_noun(
    market_name: Optional[str],
    default_count_noun: Optional[str],
) -> Optional[str]:
    if market_name:
        has_cut = bool(_MARKET_CUT_RE.search(market_name))
        has_hike = bool(_MARKET_HIKE_RE.search(market_name))
        if has_cut and not has_hike:
            return "cut"
        if has_hike and not has_cut:
            return "hike"
    return default_count_noun


def plain_rate_outcome_label(
    label: Optional[str],
    *,
    market_name: Optional[str] = None,
    default_count_noun: Optional[str] = None,
) -> Optional[str]:
    """Map a venue bps outcome label to plain English, or ``None`` if not a bps move.

    Examples::
        "25 bps increase"  -> "Quarter-point increase"
        "50+ bps increase" -> "Half-point or larger increase"
        "25 bps decrease"  -> "Quarter-point cut"
        "50+ bps decrease" -> "Half-point or larger cut"
        "Hike 25bps"       -> "Quarter-point increase"
        "Hike >25bps"      -> "Half-point or larger increase"
        "Cut 25bps"        -> "Quarter-point cut"
        "Cut >25bps"       -> "Half-point or larger cut"
        "1 (25 bps)"       -> "1 cut (quarter point)"  (on a rate-cuts market)
                              "1 hike (quarter point)" (on a rate-hikes market)
                              "1 (quarter point)"      (when market direction is unspecified)
    """
    if not label:
        return None
    trimmed = re.sub(r"\s+", " ", str(label).strip())
    if not trimmed or not _BPS_TOKEN_RE.search(trimmed):
        return None

    m_cnt = _COUNT_BPS_PAREN_RE.match(trimmed)
    if m_cnt:
        cnt = int(m_cnt.group(1))
        cnt_plus = "+" if m_cnt.group(2) else ""
        bps_v = _parse_float(m_cnt.group(3))
        bps_plus = bool(m_cnt.group(4))
        if math.isfinite(bps_v):
            count_noun = _infer_count_noun(market_name, default_count_noun)
            if cnt == 0 and not cnt_plus:
                return f"0 {count_noun}s" if count_noun else "0"
            step_txt = plain_bps_step_words(bps_v)
            if bps_plus:
                step_txt = f"{step_txt} or more"
            if count_noun:
                noun = count_noun if (cnt == 1 and not cnt_plus) else f"{count_noun}s"
                return f"{cnt}{cnt_plus} {noun} ({step_txt})"
            return f"{cnt}{cnt_plus} ({step_txt})"

    m_rng = _RANGE_PREFIX_MOVE_RE.match(trimmed)
    if m_rng:
        direction = -1 if m_rng.group(1).lower() in {"cut", "cuts", "decrease", "lower"} else 1
        lo = _parse_float(m_rng.group(2))
        hi = _parse_float(m_rng.group(3))
        if math.isfinite(lo) and math.isfinite(hi) and hi >= lo:
            lead = "Cut" if direction < 0 else "Increase"
            if abs(lo - 1.0) < 1e-6 or lo == 0.0:
                return f"{lead} of up to {_plain_bps_step_with_article(hi)}"
            return f"{lead} of {_plain_bps_step_with_article(lo)} to {_plain_bps_step_with_article(hi)}"

    m_mt_pre = _MORE_THAN_PREFIX_MOVE_RE.match(trimmed)
    if m_mt_pre:
        direction = -1 if m_mt_pre.group(1).lower() in {"cut", "cuts", "decrease", "lower"} else 1
        val = _parse_float(m_mt_pre.group(2))
        if math.isfinite(val):
            return _plain_rate_more_than_label(val, direction)

    m_mt_suf = _MORE_THAN_SUFFIX_MOVE_RE.match(trimmed)
    if m_mt_suf:
        direction = -1 if m_mt_suf.group(2).lower() in {"cut", "cuts", "decrease"} else 1
        val = _parse_float(m_mt_suf.group(1))
        if math.isfinite(val):
            return _plain_rate_more_than_label(val, direction)

    m_pre = _SIGNED_PREFIX_MOVE_RE.match(trimmed)
    if m_pre:
        direction = -1 if m_pre.group(1).lower() in {"cut", "cuts", "decrease", "lower"} else 1
        op_tok = (m_pre.group(2) or "").strip()
        plus_tok = (m_pre.group(4) or "").strip()
        val = _parse_float(m_pre.group(3))
        if math.isfinite(val):
            is_strict_gt = op_tok.startswith(">") and not op_tok.startswith(">=")
            # Strict '>' on the FOMC 25-bps grid ('Hike >25bps', 'Cut >25bps') means 50+ bps (Ruling 244: A).
            # Any other strict '>' (e.g. 'Cut >50bps') must say 'more than', never 'or larger' (#13196).
            if is_strict_gt and abs(val - 25.0) < 1e-6:
                val = 50.0
                is_open = True
            elif is_strict_gt:
                return _plain_rate_more_than_label(val, direction)
            else:
                is_open = bool(op_tok or plus_tok)
            return plain_rate_move_label(val, direction, is_open)

    m_suf = _SIGNED_SUFFIX_MOVE_RE.match(trimmed)
    if m_suf:
        direction = -1 if m_suf.group(4).lower() in {"cut", "cuts", "decrease"} else 1
        op_tok = (m_suf.group(1) or "").strip()
        plus_tok = (m_suf.group(3) or "").strip()
        or_more = bool(re.search(r"\bor\s+(?:more|larger|greater)$", trimmed, re.IGNORECASE))
        val = _parse_float(m_suf.group(2))
        if math.isfinite(val):
            is_strict_gt = op_tok.startswith(">") and not op_tok.startswith(">=")
            if is_strict_gt and abs(val - 25.0) < 1e-6:
                val = 50.0
                is_open = True
            elif is_strict_gt:
                return _plain_rate_more_than_label(val, direction)
            else:
                is_open = bool(op_tok or plus_tok or or_more)
            return plain_rate_move_label(val, direction, is_open)

    return None


def parse_plain_rate_threshold(label: Optional[str]) -> Optional[tuple[float, str, str]]:
    """Parse an already-formatted plain-English rate outcome into ``(value, unit, direction)``.

    Keeps signed-ladder ordering in ``discover_card_archetypes._outcome_threshold_value``
    consistent after ``reader_outcome_name`` rewrites ``"25 bps increase"`` to
    ``"Quarter-point increase"`` and ``"50+ bps decrease"`` to ``"Half-point or larger cut"``.
    """
    if not label:
        return None
    trimmed = re.sub(r"\s+", " ", str(label).strip())
    m_rate = _PLAIN_RATE_MOVE_RE.match(trimmed)
    if m_rate:
        mag_tok = m_rate.group(1).lower()
        val = (
            _PLAIN_MAGNITUDE_BPS[mag_tok]
            if mag_tok in _PLAIN_MAGNITUDE_BPS
            else _parse_float(mag_tok) * 100.0
        )
        direction = "above" if m_rate.group(2) else "exact"
        return (val, "bps", direction)

    m_of = _PLAIN_OF_MOVE_RE.match(trimmed)
    if m_of:
        qual = m_of.group(2).lower()
        mag_tok = m_of.group(3).lower()
        val = (
            _PLAIN_MAGNITUDE_BPS[mag_tok]
            if mag_tok in _PLAIN_MAGNITUDE_BPS
            else _parse_float(mag_tok) * 100.0
        )
        direction = "above" if qual.startswith("more") else "exact"
        return (val, "bps", direction)

    m_cnt = _PLAIN_COUNT_STEP_RE.match(trimmed)
    if m_cnt:
        cnt = float(int(m_cnt.group(1)))
        direction = "above" if m_cnt.group(2) else "exact"
        return (cnt, "", direction)

    return None


__all__ = [
    "parse_plain_rate_threshold",
    "plain_bps_step_words",
    "plain_rate_move_label",
    "plain_rate_outcome_label",
]
