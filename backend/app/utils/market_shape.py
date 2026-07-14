"""Market *shape* classification — the single source of truth (Queue #194 Item 1).

Background (the #193 shape census, 2026-07-14):
`futures_markets.market_type` and `group_type` are 100% NULL across all ~456K
rows, and `mutually_exclusive` is TRUE for both yes/no claims AND two-competitor
duels — so shape is *not stored* and *cannot be reconstructed* from existing
columns alone. It has to be assigned from outcome structure + outcome-name
strings + group membership.

This module is that one classifier. It is a **pure function** (imports only
stdlib + `re`) so it can run at ingest, in a backfill task, and inside the
card-coverage analysis without circular-import or DB coupling.

The six shapes (census-derived), each with a canonical Discover render "kernel":

    claim            one yes/no question          → number + delta
    quantity         a numeric threshold ladder    → ladder strip
    duel             two named competitors         → split
    field            >2 named competitors, 1 wins   → top-3
    container_member a yes/no member of a decomposed field (shared group_id)
                                                    → rolls up into a container
    unshaped         0- or 1-outcome / incomplete   → (no native kernel)

Census mis-bucket fixes folded in here (see #193 "Residue"):
  * 2-outcome mutually-exclusive with *named* sides is a **duel**, not a claim.
    The legacy `_classify_kind` lumped every ≤2-outcome market as "binary".
  * sub-2-outcome rows (0/1 outcome — ~29K: 0-outcome level markets +
    1-outcome long-horizon "before 20XX" contracts) are **unshaped**, not claims.
  * quantity is under-detected by question-text regex — key off the *numeric
    outcome structure*, not the market name.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Shape + side_kind vocabularies (keep these as the canonical string set)
# ---------------------------------------------------------------------------

SHAPE_CLAIM = "claim"
SHAPE_QUANTITY = "quantity"
SHAPE_DUEL = "duel"
SHAPE_FIELD = "field"
SHAPE_CONTAINER_MEMBER = "container_member"
SHAPE_UNSHAPED = "unshaped"

ALL_SHAPES = frozenset(
    {
        SHAPE_CLAIM,
        SHAPE_QUANTITY,
        SHAPE_DUEL,
        SHAPE_FIELD,
        SHAPE_CONTAINER_MEMBER,
        SHAPE_UNSHAPED,
    }
)

SIDE_YES_NO = "yes_no"
SIDE_COMPETITORS = "competitors"
SIDE_THRESHOLD = "threshold"

# Quantity ticker prefixes (Kalshi numeric-ladder families) — consolidated from
# entertainment._KIND_BY_TICKER plus weather/economics numeric ladders.
_QUANTITY_TICKER_PREFIXES = (
    "kxspotify",
    "kxbillboard",
    "kxboxoffice",
    "kxrottentomatoes",
)

# Yes/No outcome tokens (Kalshi binaries + Polymarket condition sub-markets).
_YES_NO_TOKENS = {"yes", "no"}

# A single outcome name that reads as a numeric threshold / range / bin.
# Examples that should match:
#   "≥ 75", ">=100", "at least 3", "3 or more", "above 250", "under 40",
#   "100 to 150", "100-150", "$1.2M-$1.5M", "40" (bare number), "less than 2"
_NUMERIC_OUTCOME_RE = re.compile(
    r"""
    ^\s*
    (?:
        (?:≥|≤|>=|<=|>|<)\s*[\$€£]?\d               # ≥75, >=100, < 40
      | (?:at\s+least|at\s+most|above|over|under|below|less\s+than|more\s+than|
           fewer\s+than|greater\s+than|up\s+to|or\s+more|or\s+higher|or\s+fewer|
           or\s+less)\b
      | [\$€£]?\d[\d,\.]*\s*(?:k|m|b|bn|mn)?\s*
          (?:[-–—]|to)\s*[\$€£]?\d                   # 100-150, 100 to 150
      | [\$€£]?\d[\d,\.]*\s*(?:k|m|b|bn|mn)?\s*
          (?:\+|or\s+more|or\s+higher|or\s+above)\s*$   # 3+, 100 or more
      | [\$€£]?\d[\d,\.]*\s*(?:%|percent|points?|pts?|goals?|°f?|°c?)?\s*$  # bare number/unit
      | (?:before|after|by|on\s+or\s+before)\b.*\b(?:19|20)\d{2}\b          # before 2028
      | (?:before|after|by)\b.*\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)  # before Jan …
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _is_yes_no(outcome_names: list[str]) -> bool:
    """True if the outcome set is a pure Yes/No pair (order-insensitive)."""
    toks = {_norm(n) for n in outcome_names if _norm(n)}
    return bool(toks) and toks <= _YES_NO_TOKENS


def _is_numeric_outcome(name: str) -> bool:
    return bool(_NUMERIC_OUTCOME_RE.search(_norm(name)))


def _looks_like_quantity(
    external_id: str | None,
    outcome_names: list[str],
) -> bool:
    """Numeric-ladder detection: known ticker family OR a majority of outcomes
    read as numeric thresholds/ranges/bins.

    Deliberately conservative and structure-driven (not question-text regex) per
    the census caveat "quantity is under-detected by name regex". A single
    2-outcome Yes/No threshold market is NOT quantity — it is one *claim* about a
    number; the ladder is a group-level concept."""
    ext = _norm(external_id)
    if any(ext.startswith(p) for p in _QUANTITY_TICKER_PREFIXES):
        return True
    named = [n for n in outcome_names if _norm(n) and _norm(n) not in _YES_NO_TOKENS]
    if len(named) < 2:
        return False
    numeric = sum(1 for n in named if _is_numeric_outcome(n))
    # Majority of the *named* (non-yes/no) outcomes are numeric bins.
    return numeric >= 2 and numeric * 2 >= len(named)


def classify_market_shape(
    *,
    outcome_names: list[str] | None,
    external_id: str | None = None,
    event_id: int | None = None,
    group_id: str | None = None,
    group_size: int = 1,
) -> tuple[str, str | None]:
    """Return ``(shape, side_kind)`` for a futures market.

    Args:
        outcome_names: the market's outcome name strings (order-insensitive).
        external_id:   source ticker / key (used for quantity-family prefixes).
        event_id:      set when the market is linked to a game (→ duel).
        group_id:      cross-source grouping key.
        group_size:    number of markets sharing this ``group_id`` (>1 ⇒ the
                       market is a member of a decomposed field/container).

    side_kind is ``yes_no`` | ``competitors`` | ``threshold`` | ``None``
    (None only for unshaped rows).
    """
    names = [n for n in (outcome_names or []) if (n or "").strip()]
    n = len(names)

    # 1. unshaped — 0/1-outcome rows (level markets w/ no sides; 1-sided "before
    #    20XX" long-horizon contracts). No native kernel; explicit incomplete
    #    state per census schema-implication (4).
    if n < 2:
        return SHAPE_UNSHAPED, None

    # 2. quantity — numeric ladder. Checked before duel/field because it can be
    #    either 2-outcome (Over/Under a number) or >2-outcome (bins) and must
    #    not be miscounted as claim/field.
    if _looks_like_quantity(external_id, names):
        return SHAPE_QUANTITY, SIDE_THRESHOLD

    # 3. container_member — a yes/no sub-market of a decomposed field (Polymarket
    #    nested condition_id: the 72-member "Presidential run" group). Only a
    #    yes/no binary that shares a multi-member group_id counts; a lone yes/no
    #    is a claim (step 4).
    if group_id and group_size > 1 and n == 2 and _is_yes_no(names):
        return SHAPE_CONTAINER_MEMBER, SIDE_YES_NO

    # 4. 2-outcome — claim (yes/no) vs duel (named competitors / game link).
    if n == 2:
        if event_id is not None:
            return SHAPE_DUEL, SIDE_COMPETITORS
        if _is_yes_no(names):
            return SHAPE_CLAIM, SIDE_YES_NO
        # Mis-bucket fix: 2-outcome MX with named sides is a duel, not a claim.
        return SHAPE_DUEL, SIDE_COMPETITORS

    # 5. >2 outcomes — a field of named competitors, one winner.
    return SHAPE_FIELD, SIDE_COMPETITORS


# The canonical shape → Discover render-kernel map (used by the card-coverage
# analysis and, later, by the card system). Kept here so shape + kernel stay
# defined in one place.
SHAPE_TO_KERNEL = {
    SHAPE_CLAIM: "number+delta",
    SHAPE_QUANTITY: "ladder-strip",
    SHAPE_DUEL: "split",
    SHAPE_FIELD: "top-3",
    SHAPE_CONTAINER_MEMBER: "headliner+count",
    SHAPE_UNSHAPED: None,
}
