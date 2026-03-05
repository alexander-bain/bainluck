"""
Market Grouping Utilities

Provides two grouping strategies for related futures markets:

1. **Canonical key grouping** — Markets sharing the same `canonical_market_key`
   (e.g., basketball:NBA:championship:2025-26) from different sources
   (Polymarket, Kalshi, Odds API) are logically the same market.

2. **Threshold variant detection** — Markets that differ only by a numeric
   threshold (e.g., "Will Bitcoin exceed $80,000?", "Will Bitcoin exceed
   $90,000?", "Will Bitcoin exceed $100,000?") are grouped into a
   threshold progression.

These utilities are used by:
- The admin backfill endpoint to discover and set group_id on existing markets
- The grouping API endpoints to assemble grouped market views
"""

import re
from typing import Optional

# ── THRESHOLD DETECTION ──

# Regex to extract numeric threshold from market names.
# Matches patterns like:
#   "exceed $80,000"     → ("80000", "$")
#   "above 33°F"         → ("33", "°F")
#   "over 100.5 points"  → ("100.5", "points")
#   "at least 250"       → ("250", "")
#   "reach 1,000,000"    → ("1000000", "")
_THRESHOLD_RE = re.compile(
    r"""
    (?:exceed|above|over|under|below|at\s+least|at\s+most|reach|hit|top|more\s+than|less\s+than|higher\s+than|lower\s+than)
    \s+
    (\$?)                          # optional dollar sign
    ([\d,]+(?:\.\d+)?)             # number (with optional commas and decimals)
    \s*
    (°[FCK]|%|points?|goals?|runs?|yards?|mph|mm|inches|feet|degrees?)?  # optional unit
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Simpler pattern for "X or more", "X or below", "X+" etc.
_THRESHOLD_SIMPLE_RE = re.compile(
    r"""
    (\$?)                          # optional dollar sign
    ([\d,]+(?:\.\d+)?)             # number
    \s*
    (°[FCK]|%|points?|goals?|runs?|yards?|mph|mm|inches|feet|degrees?)?  # optional unit
    \s*
    (?:or\s+(?:more|above|higher|greater|less|below|lower|fewer)|\+|-|\s+and\s+above|\s+and\s+below)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def extract_threshold(name: str) -> Optional[tuple[float, str, str]]:
    """
    Extract a numeric threshold from a market outcome or title name.

    Returns:
        Tuple of (threshold_value, unit, direction) or None.
        - threshold_value: numeric value (e.g., 80000.0)
        - unit: unit string (e.g., "$", "°F", "points", "")
        - direction: "above" or "below" or "exact"
    """
    if not name:
        return None

    # Try primary pattern first
    m = _THRESHOLD_RE.search(name)
    if m:
        dollar, num_str, unit = m.group(1), m.group(2), m.group(3)
        value = float(num_str.replace(",", ""))
        # Reject year-like numbers (2020-2099) without a unit or dollar sign
        if not dollar and not unit and 2020 <= value <= 2099:
            return None
        unit_str = (dollar + (unit or "")).strip()
        # Determine direction from keyword
        keyword = name[m.start():m.start() + 20].lower()
        if any(w in keyword for w in ("under", "below", "less", "lower", "at most")):
            direction = "below"
        else:
            direction = "above"
        return (value, unit_str, direction)

    # Try simpler pattern
    m = _THRESHOLD_SIMPLE_RE.search(name)
    if m:
        dollar, num_str, unit = m.group(1), m.group(2), m.group(3)
        value = float(num_str.replace(",", ""))
        # Reject year-like numbers without a unit or dollar sign
        if not dollar and not unit and 2020 <= value <= 2099:
            return None
        unit_str = (dollar + (unit or "")).strip()
        # Check the text AFTER the number for direction keywords
        after_text = name[m.end():].strip().lower() if m.end() < len(name) else ""
        # Also check the "or below/above" part which is captured in the match itself
        match_text = name[m.start():m.end()].lower()
        full_context = match_text + " " + after_text
        if any(w in full_context for w in ("below", "less", "lower", "fewer", "under")):
            direction = "below"
        else:
            direction = "above"
        return (value, unit_str, direction)

    return None


def compute_threshold_stem(name: str) -> Optional[str]:
    """
    Compute a "stem" from a market/outcome name by removing the numeric
    threshold. Markets sharing the same stem are threshold variants of
    each other.

    Example:
        "Will Bitcoin exceed $80,000?"  → "will bitcoin exceed $?"
        "Will Bitcoin exceed $90,000?"  → "will bitcoin exceed $?"
        (same stem → threshold group)
    """
    if not name:
        return None

    # Replace numeric values (with optional $ prefix and commas) with a placeholder
    # This normalizes "exceed $80,000" and "exceed $90,000" to the same stem
    stem = re.sub(
        r'\$?[\d,]+(?:\.\d+)?(?:\s*(?:°[FCK]|%|points?|goals?|runs?|yards?|mph|mm|inches|feet|degrees?))?',
        '#',
        name,
    )
    # Normalize whitespace and case
    stem = re.sub(r'\s+', ' ', stem).strip().lower()
    return stem if stem != name.lower().strip() else None


# ── CANONICAL KEY GROUPING ──


def compute_canonical_groups(
    markets: list[dict],
) -> dict[str, list[dict]]:
    """
    Group markets by their canonical_market_key.

    Each market dict should have at minimum:
        - id: int (market ID)
        - canonical_market_key: Optional[str]
        - source: str

    Returns:
        Dict mapping canonical_market_key → list of market dicts
        (only groups with 2+ markets from different sources).
    """
    by_key: dict[str, list[dict]] = {}
    for m in markets:
        key = m.get("canonical_market_key")
        if not key:
            continue
        by_key.setdefault(key, []).append(m)

    # Only return groups with 2+ markets (cross-source or same-source siblings)
    return {
        k: v for k, v in by_key.items()
        if len(v) >= 2
    }


def detect_threshold_groups(
    outcomes: list[dict],
) -> dict[str, list[dict]]:
    """
    Detect threshold variant groups among a list of outcomes.

    Each outcome dict should have at minimum:
        - id: int (outcome ID)
        - name: str (outcome name like "33°F or below")
        - market_id: int (parent market ID)

    Returns:
        Dict mapping threshold_stem → sorted list of outcome dicts
        (only groups with 2+ outcomes sharing the same stem).
        Each outcome dict gets additional keys:
        - threshold_value: float
        - threshold_unit: str
        - threshold_direction: str
    """
    by_stem: dict[str, list[dict]] = {}

    for o in outcomes:
        name = o.get("name", "")
        stem = compute_threshold_stem(name)
        if not stem:
            continue

        threshold = extract_threshold(name)
        if not threshold:
            continue

        value, unit, direction = threshold
        enriched = {
            **o,
            "threshold_value": value,
            "threshold_unit": unit,
            "threshold_direction": direction,
        }
        by_stem.setdefault(stem, []).append(enriched)

    # Only return groups with 2+ outcomes, sorted by threshold value
    result = {}
    for stem, group in by_stem.items():
        if len(group) >= 2:
            group.sort(key=lambda x: x["threshold_value"])
            result[stem] = group

    return result


def discover_group_id_for_market(
    source: str,
    external_id: str,
    canonical_market_key: Optional[str],
    name: str,
    market_id: int,
) -> Optional[tuple[str, str]]:
    """
    Compute a (group_id, group_type) for a market based on available data.

    Priority:
    1. Source-specific hierarchy (polymarket:X, kalshi:X) — set during ingestion
    2. Canonical key grouping — when canonical_market_key matches other markets
    3. Threshold stem detection — within same canonical group

    Returns:
        Tuple of (group_id, group_type) or None.
    """
    # Source-specific hierarchy (already set during ingestion)
    if source == "polymarket" and external_id:
        return (f"polymarket:{external_id}", "polymarket_event")
    if source == "kalshi" and external_id:
        return (f"kalshi:{external_id}", "kalshi_event")

    # Canonical key grouping
    if canonical_market_key:
        return (f"canonical:{canonical_market_key}", "canonical")

    return None
