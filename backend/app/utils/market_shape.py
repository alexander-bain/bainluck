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

Semantics v2 (Queue #260, the C16 P1 trio):
The single six-value ``market_type`` enum overloaded *display geometry* with
*probability semantics*. v2 splits them:

  * ``classify_market_shape`` still returns the DISPLAY shape (what geometry the
    Discover card renders) — a backward-compatible ``market_type`` value.
  * ``classify_market_semantics`` returns the full probabilistic contract:
    ``outcome_relation`` / ``exhaustive`` / ``expected_winners`` /
    ``push_void_capable`` plus a ``classifier_version`` + ``input_fingerprint``
    so classification is recomputable, not frozen at first sight.

The C16 P1 fixes folded in here:
  * **Event-linked Yes/No** is a *claim*, not a *duel*. The old step-4 order
    checked ``event_id`` before the Yes/No test, so every game-linked Yes/No prop
    became a duel. Yes/No is now checked first.
  * **Field / participation conflation.** Top-N / participation contracts
    (DataGolf ``top_5``, "make cut", qualify/advance) are NOT one-winner fields —
    they have many winners and their probabilities do not sum to 1. They get a
    distinct display shape ``participation`` so they carry their own cohort
    identity and never enter the ``market_type='field'`` mex-normalization branch
    (invariant-monotone-safe for the #259 canonical calibration population).

The display shapes (census-derived), each with a canonical Discover render
"kernel":

    claim            one yes/no question           → number + delta
    quantity         a numeric threshold ladder     → ladder strip
    duel             two named competitors          → split
    field            >2 named competitors, 1 wins    → top-3
    participation    Top-N / multi-winner contract   → top-3 (own cohort identity)
    container_member a yes/no member of a decomposed field (shared group_id)
                                                     → rolls up into a container
    unshaped         0- or 1-outcome / incomplete    → (no native kernel)
"""

from __future__ import annotations

import hashlib
import json
import re

# ---------------------------------------------------------------------------
# Shape + side_kind vocabularies (keep these as the canonical string set)
# ---------------------------------------------------------------------------

SHAPE_CLAIM = "claim"
SHAPE_QUANTITY = "quantity"
SHAPE_DUEL = "duel"
SHAPE_FIELD = "field"
SHAPE_PARTICIPATION = "participation"
SHAPE_CONTAINER_MEMBER = "container_member"
SHAPE_UNSHAPED = "unshaped"

ALL_SHAPES = frozenset(
    {
        SHAPE_CLAIM,
        SHAPE_QUANTITY,
        SHAPE_DUEL,
        SHAPE_FIELD,
        SHAPE_PARTICIPATION,
        SHAPE_CONTAINER_MEMBER,
        SHAPE_UNSHAPED,
    }
)

SIDE_YES_NO = "yes_no"
SIDE_COMPETITORS = "competitors"
SIDE_THRESHOLD = "threshold"

# ---------------------------------------------------------------------------
# Semantics v2 vocabulary (Queue #260) — the probabilistic relation between a
# market's outcomes. Deliberately separate from the display shape above.
# ---------------------------------------------------------------------------

CLASSIFIER_VERSION = 2

REL_COMPLEMENTS = "complements"  # Yes/No, Over/Under — sums to 1, one winner
REL_COMPETITORS = "competitors"  # named mutually-exclusive field, one winner
REL_CUMULATIVE = "cumulative_thresholds"  # "at least N" ladder (non-exclusive)
REL_RANGES = "exclusive_ranges"  # numeric bins (0-10, 11-20, …)
REL_PARTICIPATION = "independent_participation"  # Top-N / make-cut, many winners
REL_CONDITIONAL = "conditional"  # sub-market gated on a parent condition
REL_UNKNOWN = "unknown"  # relation not provable from available inputs

ALL_RELATIONS = frozenset(
    {
        REL_COMPLEMENTS,
        REL_COMPETITORS,
        REL_CUMULATIVE,
        REL_RANGES,
        REL_PARTICIPATION,
        REL_CONDITIONAL,
        REL_UNKNOWN,
    }
)

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

# Draw/tie tokens (soccer, chess, etc.) — a competitors relation that is NOT a
# simple two-sided complement.
_DRAW_TOKENS = {"draw", "tie"}

# Source-metadata Top-N / participation contract detector (DataGolf market kind,
# Kalshi ticker suffix). ``top_5`` → group(1)="5"; make-cut/qualify/advance → no
# count but still multi-winner.
_TOP_N_RE = re.compile(r"(?:top[_\s-]?(\d+)|make[_\s-]?cut|qualif|advance)", re.I)

# A source kind that reads as a single-winner "win/champion" contract.
_WIN_RE = re.compile(r"(?:^|[_\s-])(win|winner|champion)(?:$|[_\s-])", re.I)

# Any number inside an outcome name (used to gate cumulative-threshold phrases).
_NUMBER_RE = re.compile(r"[-+]?\d+(?:[,.]\d+)?")

# An outcome name that reads as an explicit numeric RANGE (a bin): "0-10",
# "100 to 150", "$1.2M-$1.5M".
_RANGE_RE = re.compile(r"\d[^\n]*(?:-|–|—|\bto\b)[^\n]*\d", re.I)

# An outcome name that reads as a CUMULATIVE threshold (open-ended): "at least
# 20", ">= 100", "or more". These ladders are non-exclusive (a later rung
# implies the earlier ones), so they never sum to 1.
_CUMULATIVE_RE = re.compile(
    r"(?:>=|<=|≥|≤|\bat least\b|\bat most\b|\bover\b|\bunder\b|"
    r"\babove\b|\bbelow\b|\bor more\b|\bor fewer\b|\bor higher\b|\bor less\b)",
    re.I,
)

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


def _int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


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


def _is_participation(source_kind: str | None, expected_winners: int | None) -> bool:
    """True for a Top-N / multi-winner (independent participation) contract.

    Structure-driven: an explicit ``expected_winners > 1`` OR a source-metadata
    Top-N / make-cut / qualify / advance kind. A single-winner "win/champion"
    contract is NOT participation."""
    if expected_winners is not None and expected_winners > 1:
        return True
    return bool(source_kind and _TOP_N_RE.search(source_kind))


def _structured_expected_winners(
    source_kind: str | None,
    explicit: int | None,
    mutually_exclusive: bool | None,
) -> int | None:
    """Best-effort expected winner cardinality from STRUCTURED inputs only.

    Explicit metadata wins; then a Top-N count from source kind; then a
    single-winner "win" kind or a proven mutual-exclusivity flag. Returns None
    when nothing structured proves it (title inference is never used here)."""
    v = _int(explicit)
    if v is not None:
        return v
    if source_kind:
        m = _TOP_N_RE.search(source_kind)
        if m and m.group(1):
            return int(m.group(1))
        if _WIN_RE.search(source_kind):
            return 1
    if mutually_exclusive is True:
        return 1
    return None


def classify_market_shape(
    *,
    outcome_names: list[str] | None,
    external_id: str | None = None,
    event_id: int | None = None,
    group_id: str | None = None,
    group_size: int = 1,
    source_kind: str | None = None,
    expected_winners: int | None = None,
    mutually_exclusive: bool | None = None,
) -> tuple[str, str | None]:
    """Return ``(display_shape, side_kind)`` for a futures market.

    Args:
        outcome_names: the market's outcome name strings (order-insensitive).
        external_id:   source ticker / key (used for quantity-family prefixes).
        event_id:      set when the market is linked to a game.
        group_id:      cross-source grouping key.
        group_size:    number of markets sharing this ``group_id`` (>1 ⇒ the
                       market is a member of a decomposed field/container).
        source_kind:   structured source market-kind hint (DataGolf market type,
                       Kalshi ticker suffix) — drives the participation split.
        expected_winners: structured winner cardinality when known.
        mutually_exclusive: the stored MX flag (unused for display; kept for a
                       symmetric signature with ``classify_market_semantics``).

    side_kind is ``yes_no`` | ``competitors`` | ``threshold`` | ``None``
    (None only for unshaped rows).
    """
    names = [n for n in (outcome_names or []) if (n or "").strip()]
    n = len(names)
    src_kind = _norm(source_kind)

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

    # 4. 2-outcome — claim (yes/no) vs duel (named competitors).
    #    C16 fix: Yes/No is a *claim* even when event-linked — the old code
    #    forced event-linked binaries to duel before checking the names.
    if n == 2:
        if _is_yes_no(names):
            return SHAPE_CLAIM, SIDE_YES_NO
        # Named sides (incl. an event-linked Home/Away) → duel.
        return SHAPE_DUEL, SIDE_COMPETITORS

    # 5. >2 outcomes — a field of named competitors (one winner) vs a Top-N /
    #    participation contract (many winners). C16 fix: split participation off
    #    so it never masquerades as a one-winner field.
    if _is_participation(src_kind, expected_winners):
        return SHAPE_PARTICIPATION, SIDE_COMPETITORS
    return SHAPE_FIELD, SIDE_COMPETITORS


def input_fingerprint(
    *,
    outcome_names: list[str] | None,
    source: str | None = None,
    source_kind: str | None = None,
    event_id: int | None = None,
    group_id: str | None = None,
    group_type: str | None = None,
    group_size: int = 1,
    mutually_exclusive: bool | None = None,
    expected_winners: int | None = None,
    conditional: bool = False,
    parent_condition_id=None,
    push_possible=None,
) -> str:
    """Stable 20-hex fingerprint of every input that can change a market's
    semantics (Queue #260 Item 2). Recompute is triggered when this differs from
    the stored value — late siblings (group_size), late event links (event_id),
    repaired outcome sets (outcome_names), and source-metadata corrections
    (source_kind / mutually_exclusive / expected_winners) all flip it."""
    payload = {
        "outcomes": sorted(_norm(n) for n in (outcome_names or []) if _norm(n)),
        "source": _norm(source),
        "source_kind": _norm(source_kind),
        "event_id": event_id,
        "group_id": (group_id or "").strip(),
        "group_type": _norm(group_type),
        "group_size": _int(group_size) or 1,
        "mutually_exclusive": mutually_exclusive,
        "expected_winners": expected_winners,
        "conditional": bool(conditional),
        "parent_condition_id": parent_condition_id,
        "push_possible": push_possible,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def _outcome_relation(
    names: list[str],
    name_set: set[str],
    source_kind: str,
    expected_winners: int | None,
    mutually_exclusive: bool | None,
    conditional: bool,
    parent_condition_id,
    push_possible,
    event_id: int | None,
) -> dict:
    """Probabilistic-semantics core: derive the outcome relation, exhaustiveness,
    winner cardinality, push capability, confidence, and evidence.

    Structure- and source-metadata-driven. Title inference is never used to
    upgrade confidence above ``medium``."""
    evidence: list[str] = []
    confidence = "low"
    relation = REL_UNKNOWN
    exhaustive: bool | None = None
    ew = expected_winners
    push = push_possible

    if source_kind:
        evidence.append(f"source_kind:{source_kind}")
    if mutually_exclusive is not None:
        evidence.append(f"mutually_exclusive:{str(bool(mutually_exclusive)).lower()}")
    if ew is not None:
        evidence.append(f"expected_winners:{ew}")

    if conditional or parent_condition_id:
        relation = REL_CONDITIONAL
        confidence = "high" if parent_condition_id else "medium"
        evidence.append("conditional_parent")
    elif len(names) < 2:
        relation = REL_UNKNOWN
    elif name_set <= _YES_NO_TOKENS:
        relation = REL_COMPLEMENTS
        exhaustive = True
        ew = 1
        confidence = "high"
        evidence.append("yes_no_pair")
        if event_id is not None:
            # C16 risk marker: a Yes/No prop linked to a game is a claim, not a
            # duel — recorded so the census can count how many were rescued.
            evidence.append("linked_yes_no")
    elif name_set in ({"over", "under"}, {"above", "below"}):
        relation = REL_COMPLEMENTS
        exhaustive = True
        ew = 1
        confidence = "high"
        push = True if push is None else push
        evidence.append("two_sided_threshold")
    else:
        range_count = sum(bool(_RANGE_RE.search(nm)) for nm in names)
        cumulative_count = sum(
            bool(_CUMULATIVE_RE.search(nm) and _NUMBER_RE.search(nm)) for nm in names
        )
        has_draw = bool(name_set & _DRAW_TOKENS)
        top_n = bool(source_kind and _TOP_N_RE.search(source_kind))

        if top_n or (ew is not None and ew > 1):
            relation = REL_PARTICIPATION
            exhaustive = False
            confidence = "high" if (source_kind or expected_winners is not None) else "medium"
            evidence.append("multi_winner_contract")
        elif range_count >= 2 and range_count * 2 >= len(names):
            relation = REL_RANGES
            exhaustive = bool(mutually_exclusive) if mutually_exclusive is not None else None
            confidence = "medium" if mutually_exclusive is None else "high"
            evidence.append("range_outcomes")
        elif cumulative_count >= 2 and cumulative_count * 2 >= len(names):
            relation = REL_CUMULATIVE
            exhaustive = False
            confidence = "medium"
            evidence.append("cumulative_threshold_outcomes")
        elif len(names) == 2 or has_draw:
            relation = REL_COMPETITORS
            exhaustive = bool(mutually_exclusive) if mutually_exclusive is not None else None
            ew = ew or (1 if mutually_exclusive else None)
            confidence = "high" if mutually_exclusive is not None else "medium"
            evidence.append("named_competitors")
            if has_draw:
                evidence.append("draw_capable")
        elif ew == 1 and mutually_exclusive is True:
            relation = REL_COMPETITORS
            exhaustive = True
            confidence = "high"
            evidence.append("exactly_one_structured")
        else:
            relation = REL_UNKNOWN
            confidence = "low"
            evidence.append("multi_named_relation_unknown")

    # Item 3 guard: a field is only a *proven* one-winner exhaustive partition
    # when the source proves it (MX flag + one expected winner). Never inferred
    # from ">2 named outcomes" alone.
    if relation == REL_COMPETITORS and ew == 1 and mutually_exclusive is True:
        exhaustive = True

    return {
        "outcome_relation": relation,
        "exhaustive": exhaustive,
        "expected_winners": ew,
        "push_void_capable": bool(push),
        "confidence": confidence,
        "evidence": sorted(set(evidence)),
    }


def classify_market_semantics(
    *,
    outcome_names: list[str] | None,
    external_id: str | None = None,
    event_id: int | None = None,
    group_id: str | None = None,
    group_size: int = 1,
    source: str | None = None,
    source_kind: str | None = None,
    expected_winners: int | None = None,
    mutually_exclusive: bool | None = None,
    push_possible=None,
    conditional: bool = False,
    parent_condition_id=None,
    group_type: str | None = None,
) -> dict:
    """The semantics v2 contract (Queue #260) for one futures market.

    Returns a dict carrying BOTH the display geometry (``display_shape`` /
    ``side_kind``) and the probabilistic semantics (``outcome_relation`` /
    ``exhaustive`` / ``expected_winners`` / ``push_void_capable``), plus
    ``classifier_version`` / ``input_fingerprint`` / ``confidence`` / ``evidence``
    so classification is recomputable rather than frozen at first sight.
    """
    names = [n for n in (outcome_names or []) if (n or "").strip()]
    name_set = {_norm(n) for n in names}
    src_kind = _norm(source_kind)
    ew_structured = _structured_expected_winners(src_kind, expected_winners, mutually_exclusive)

    display_shape, side_kind = classify_market_shape(
        outcome_names=names,
        external_id=external_id,
        event_id=event_id,
        group_id=group_id,
        group_size=group_size,
        source_kind=src_kind,
        expected_winners=ew_structured,
        mutually_exclusive=mutually_exclusive,
    )

    semantics = _outcome_relation(
        names=names,
        name_set=name_set,
        source_kind=src_kind,
        expected_winners=ew_structured,
        mutually_exclusive=mutually_exclusive,
        conditional=conditional,
        parent_condition_id=parent_condition_id,
        push_possible=push_possible,
        event_id=event_id,
    )

    fingerprint = input_fingerprint(
        outcome_names=names,
        source=source,
        source_kind=src_kind,
        event_id=event_id,
        group_id=group_id,
        group_type=group_type,
        group_size=group_size,
        mutually_exclusive=mutually_exclusive,
        expected_winners=ew_structured,
        conditional=conditional,
        parent_condition_id=parent_condition_id,
        push_possible=push_possible,
    )

    return {
        "classifier_version": CLASSIFIER_VERSION,
        "display_shape": display_shape,
        "side_kind": side_kind,
        "input_fingerprint": fingerprint,
        "outcome_count": len(names),
        **semantics,
    }


# The canonical shape → Discover render-kernel map (used by the card-coverage
# analysis and, later, by the card system). Kept here so shape + kernel stay
# defined in one place. ``participation`` renders like a field (top-3) but is a
# distinct cohort identity (Queue #260).
SHAPE_TO_KERNEL = {
    SHAPE_CLAIM: "number+delta",
    SHAPE_QUANTITY: "ladder-strip",
    SHAPE_DUEL: "split",
    SHAPE_FIELD: "top-3",
    SHAPE_PARTICIPATION: "top-3",
    SHAPE_CONTAINER_MEMBER: "headliner+count",
    SHAPE_UNSHAPED: None,
}
