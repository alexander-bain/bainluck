"""Shared cross-source matching utilities for category page routes.

Extracts the common pattern of finding markets that exist on both Kalshi and
Polymarket, then ranking by probability disagreement.  Used by politics.py,
entertainment.py, and economics.py.

Also provides ``group_markets_by_group_id`` for collapsing Polymarket
sub-markets that share a ``group_id`` into a single representative market
with merged outcomes — used by all four category pages.
"""

import re
from collections import defaultdict
from typing import Callable, Sequence

from app.models import FuturesMarket
from app.utils.outcome_display import drop_duplicate_binary_legs

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

GARBAGE_OUTCOME_RE = re.compile(
    r"^(?:player|person|candidate|option|party|song|movie|show|app|team|ticker|choice)\s+[A-Z0-9]{1,3}$", re.I
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "be",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "shall",
    "that",
    "the",
    "this",
    "to",
    "will",
    "would",
}
_TOKEN_ALIASES = {
    "above": "over",
    "below": "under",
    "exceed": "over",
    "exceeds": "over",
    "exceeding": "over",
    "greater": "over",
    "less": "under",
    "presidency": "president",
    "presidential": "president",
    "wins": "win",
    "winner": "win",
    "winning": "win",
}
_DIRECTION_TOKENS = {"over", "under"}


def source(market: FuturesMarket) -> str:
    """Return the lowercased source name for a market."""
    return (market.source or "").lower()


def is_resolved(market: FuturesMarket) -> bool:
    """A market is effectively resolved if any outcome is >= 99% or all near-zero."""
    probs = [float(o.current_probability or 0) for o in market.outcomes
             if o.current_probability is not None]
    if not probs:
        return False
    if any(p >= 0.99 for p in probs):
        return True
    if len(probs) >= 2 and all(p <= 0.01 for p in probs):
        return True
    return False


def clean_outcomes(outcomes: list) -> list:
    """Filter garbage placeholder outcomes, and the duplicate Yes/No legs of a
    condition the list already carries under its real name (UX-P188)."""
    kept = [o for o in outcomes if not GARBAGE_OUTCOME_RE.match(o.name or "")]
    return drop_duplicate_binary_legs(kept, lambda o: o.external_id)


def normalize_question(q: str) -> str:
    """Normalize a question string for cross-source matching.

    Strips punctuation, lowercases, and trims whitespace.
    """
    return re.sub(r"[^a-z0-9 ]+", "", q.lower()).strip()


def _near_match_tokens(q: str) -> set[str]:
    tokens = []
    for token in _TOKEN_RE.findall(q.lower()):
        canonical = _TOKEN_ALIASES.get(token, token)
        if canonical not in _STOPWORDS:
            tokens.append(canonical)
    return set(tokens)


def _numeric_tokens(tokens: set[str]) -> set[str]:
    return {token for token in tokens if token.isdigit()}


def _direction_tokens(tokens: set[str]) -> set[str]:
    return tokens & _DIRECTION_TOKENS


def _near_match_signature(q: str) -> tuple[set[str], frozenset[str], frozenset[str]]:
    """Precompute the token sets used for conservative near-matching.

    Returns ``(tokens, numeric_tokens, direction_tokens)`` so the O(n^2)
    pairing loop in :func:`find_cross_source_markets` can tokenize each row
    once instead of re-tokenizing both sides on every candidate pair.
    """
    tokens = _near_match_tokens(q)
    return tokens, frozenset(_numeric_tokens(tokens)), frozenset(_direction_tokens(tokens))


def _conservative_near_match_score(
    left_sig: tuple[set[str], frozenset[str], frozenset[str]],
    right_sig: tuple[set[str], frozenset[str], frozenset[str]],
) -> float | None:
    """Jaccard score for obvious paraphrases, or None if not a conservative match.

    Same guards as the public :func:`_is_conservative_near_match`, but operates
    on precomputed signatures and returns the Jaccard similarity so callers can
    reuse it for ranking instead of recomputing the token sets.
    """
    left_tokens, left_num, left_dir = left_sig
    right_tokens, right_num, right_dir = right_sig
    if len(left_tokens) < 3 or len(right_tokens) < 3:
        return None
    if left_num != right_num:
        return None
    if (left_dir or right_dir) and left_dir != right_dir:
        return None

    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    if union == 0:
        return None
    jaccard = overlap / union
    containment = overlap / min(len(left_tokens), len(right_tokens))
    if jaccard >= 0.72 and containment >= 0.85:
        return jaccard
    return None


def _is_conservative_near_match(left: str, right: str) -> bool:
    """Return True for obvious paraphrases, with guards against false matches."""
    return (
        _conservative_near_match_score(
            _near_match_signature(left), _near_match_signature(right)
        )
        is not None
    )


# ---------------------------------------------------------------------------
# Outcome alignment — comparing like with like
# ---------------------------------------------------------------------------


def _outcome_key(name: str | None) -> str:
    """Normalize an outcome name so the same outcome matches across sources.

    Deliberately conservative: case-fold and collapse whitespace, nothing else.
    A looser key (stripping punctuation, decomposing accents) would fold
    "Ülle Madise" and "Ulle Madise" together, which is desirable, but it also
    folds bracket labels that are NOT the same outcome — "2.4%" and "2-4%",
    "$800-900B" and "800-900B". Measured over the 122 production pairs on
    /politics (2026-08-30) the looser key bought exactly one extra pair and
    risked the whole threshold-ladder population, so it is not worth it.
    """
    return re.sub(r"\s+", " ", (name or "").strip()).casefold()


def align_on_shared_outcome(
    kalshi_row: dict, poly_row: dict
) -> tuple[str, float, float] | None:
    """Pick the one outcome both sources price, or None if there isn't one.

    A cross-source spread is only a spread when the two numbers are the price
    of the SAME thing. Both row builders rank a market's outcomes and report
    the leader's probability as ``prob``, and until this function existed the
    spotlight subtracted one market's leader from the other's — which is a
    disagreement only when the two leaders happen to be the same outcome.

    Measured on production, 2026-08-30, over every cross-source pair
    /politics finds (122 of them):

      * 98 of 122 pairs have DIFFERENT leading outcomes, so their "spread" was
        an artifact of which outcome happened to lead on each side. The served
        top four included "How many House seats will Democrats win in
        Louisiana?" as Kalshi 92.5% (exactly 1 seat) vs Polymarket 36.0%
        (9 seats) — a 56.5pt spread between two numbers that were never in
        conflict, plus a "Merged: 64.3%" that is the average of two different
        futures.
      * 95 of 122 share no outcome name at all — a cumulative Kalshi ladder
        ("Above 2.2%") against Polymarket discrete brackets ("2.4%") cannot be
        reduced to one comparable number in either direction (gotcha #17).
        Those pairs are dropped rather than shown with a number nobody can act
        on.
      * The artifact was also HIDING real disagreement, not only inventing it:
        "Rio de Janeiro Governor winner?" served a 0.7pt spread that looked
        like near-perfect agreement, while the two sources priced Eduardo Paes
        at 94.0% and 63.8% — a genuine 30.2pt gap.

    Alignment reads ``top_outcomes``, the list the row builder has already
    built and already normalized, so the number on a spotlight card is the
    same number, on the same basis, as the one the market's own section
    prints. Reading ``FuturesMarket.outcomes`` directly here would be a second
    basis: ``_normalize_outcome_probs`` fires on 102 of the 244 markets in
    those pairs, so the two would visibly disagree. Top-3 costs nothing —
    all 27 comparable pairs align inside it, because a pair whose leaders
    agree aligns on rank 1 by construction.

    When the leaders differ but some lower-ranked outcome is shared, that
    outcome is still a legitimate comparison and often the most interesting
    one on the page ("both sources price Goldman Sachs, and they are 53 points
    apart about it"), so the shared outcome with the highest price on either
    side wins. For a leader-agreeing pair that rule selects the shared leader,
    so there is one rule, not two.

    Returns ``(outcome_name, kalshi_prob, poly_prob)``.
    """
    kalshi_by_key = {
        _outcome_key(o.get("name")): o
        for o in (kalshi_row.get("top_outcomes") or [])
        if _outcome_key(o.get("name"))
    }
    poly_by_key = {
        _outcome_key(o.get("name")): o
        for o in (poly_row.get("top_outcomes") or [])
        if _outcome_key(o.get("name"))
    }
    shared = set(kalshi_by_key) & set(poly_by_key)
    if not shared:
        return None

    best_key = max(
        shared,
        key=lambda k: (
            max(
                float(kalshi_by_key[k].get("prob") or 0),
                float(poly_by_key[k].get("prob") or 0),
            ),
            k,
        ),
    )
    # Kalshi's spelling is the one shown. The two agree after normalization by
    # construction; they can still differ in case or spacing, and picking one
    # side deterministically keeps the label stable as prices move.
    name = (kalshi_by_key[best_key].get("name") or "").strip()
    return (
        name,
        float(kalshi_by_key[best_key].get("prob") or 0),
        float(poly_by_key[best_key].get("prob") or 0),
    )


def _spotlight_match(kalshi_row: dict, poly_row: dict) -> dict | None:
    """Build one spotlight row, or None when the pair is not comparable."""
    aligned = align_on_shared_outcome(kalshi_row, poly_row)
    if aligned is None:
        return None
    outcome, kalshi_prob, poly_prob = aligned
    return {
        "q": kalshi_row["q"],
        "outcome": outcome,
        "kalshi": kalshi_prob,
        "poly": poly_prob,
        "delta": round(abs(kalshi_prob - poly_prob), 1),
        "category": kalshi_row.get("theme", ""),
        "kalshi_market_id": kalshi_row["market_id"],
        "poly_market_id": poly_row["market_id"],
    }


# ---------------------------------------------------------------------------
# Core cross-source matching algorithm
# ---------------------------------------------------------------------------


def find_cross_source_markets(
    markets: Sequence[FuturesMarket],
    *,
    market_row_fn: Callable[[FuturesMarket], dict | None],
    max_results: int = 8,
) -> list[dict]:
    """Find markets that exist on both Kalshi & Polymarket, ranked by disagreement.

    A pair is only reported when both sources price the SAME outcome, and the
    reported spread is that outcome's — see :func:`align_on_shared_outcome`
    for why, and for what the numbers looked like before. Pairs with no shared
    outcome are matched and then dropped, so the section shows fewer, truer
    rows rather than more, louder ones.

    Ranking happens AFTER the drop, which matters: mis-aligned leaders produce
    the largest fake spreads, so sorting first systematically promoted exactly
    the rows that were wrong and buried the real ones below the cut.

    Parameters
    ----------
    markets:
        Sequence of FuturesMarket objects to scan.
    market_row_fn:
        Callable that receives a single FuturesMarket and returns either None
        (skip this market) or a dict containing at minimum ``q``, ``prob``,
        ``src``, ``market_id`` and ``top_outcomes`` (a ranked list of
        ``{"name", "prob"}``, which all three category routes already build).
        A row without ``top_outcomes`` can never be aligned and so is never
        reported.  May include extra keys (e.g. ``theme``) that will be
        preserved in the output.
    max_results:
        Maximum number of cross-source pairs to return (default 8).

    Returns
    -------
    list[dict]
        Each entry has: ``q``, ``outcome``, ``kalshi``, ``poly``, ``delta``,
        ``category``, ``kalshi_market_id``, ``poly_market_id``.  ``outcome``
        names the single outcome ``kalshi`` and ``poly`` both price.
    """
    by_norm: dict[str, dict[str, dict]] = defaultdict(dict)
    rows_by_source: dict[str, list[tuple[str, dict]]] = {
        "kalshi": [],
        "polymarket": [],
    }

    for m in markets:
        if is_resolved(m):
            continue
        row = market_row_fn(m)
        if not row:
            continue
        src = row.get("src", "")
        if src not in ("kalshi", "polymarket"):
            continue
        norm = normalize_question(row["q"])
        if norm and src not in by_norm[norm]:
            by_norm[norm][src] = row
            rows_by_source[src].append((norm, row))

    matches = []
    matched_market_ids = set()
    for _norm, sources in by_norm.items():
        if "kalshi" not in sources or "polymarket" not in sources:
            continue
        k = sources["kalshi"]
        p = sources["polymarket"]
        # Both ids are consumed even when the pair yields no row. An exact
        # normalized-question match is the strongest evidence two markets are
        # the same question; that it cannot be reduced to one comparable
        # number is a reason to show nothing, never a reason to release the
        # markets into the near-match pass to find a WEAKER partner.
        matched_market_ids.add(k["market_id"])
        matched_market_ids.add(p["market_id"])
        match = _spotlight_match(k, p)
        if match is not None:
            matches.append(match)

    # Precompute token signatures once per row so the conservative near-match
    # pass below is O(n) tokenization instead of re-tokenizing both sides on
    # every (kalshi, polymarket) pair. With ~900 markets the naive version did
    # millions of redundant regex tokenizations and dominated endpoint latency.
    poly_sigs = [
        (p_norm, p, _near_match_signature(p["q"]))
        for p_norm, p in rows_by_source["polymarket"]
    ]

    for k_norm, k in rows_by_source["kalshi"]:
        if k["market_id"] in matched_market_ids:
            continue
        k_sig = _near_match_signature(k["q"])
        best_poly = None
        best_score = 0.0
        for p_norm, p, p_sig in poly_sigs:
            if p["market_id"] in matched_market_ids or k_norm == p_norm:
                continue
            score = _conservative_near_match_score(k_sig, p_sig)
            if score is not None and score > best_score:
                best_poly = p
                best_score = score
        if not best_poly:
            continue
        matched_market_ids.add(k["market_id"])
        matched_market_ids.add(best_poly["market_id"])
        match = _spotlight_match(k, best_poly)
        if match is not None:
            matches.append(match)

    matches.sort(key=lambda x: -x["delta"])
    return matches[:max_results]


# ---------------------------------------------------------------------------
# Group-ID market collapsing for category pages
# ---------------------------------------------------------------------------


def group_markets_by_group_id(
    markets: Sequence[FuturesMarket],
) -> list[FuturesMarket]:
    """Collapse markets sharing a ``group_id`` into a single representative.

    Polymarket decomposes multi-outcome questions (e.g. "Who wins Best
    Picture?") into N independent binary sub-markets, each with its own
    ``FuturesMarket`` row but the same ``group_id``.  On category pages this
    causes N duplicate rows for what the user perceives as one question.

    This helper groups by ``group_id``, picks the representative market
    (most outcomes, then highest volume), and **merges** the unique outcomes
    from all sibling markets onto the representative so it carries the full
    outcome set.

    Markets with ``group_id IS NULL`` pass through unchanged.

    Returns a new list — the input is not mutated.
    """
    ungrouped: list[FuturesMarket] = []
    by_group: dict[str, list[FuturesMarket]] = defaultdict(list)

    for m in markets:
        gid = getattr(m, "group_id", None)
        if gid is None:
            ungrouped.append(m)
        else:
            by_group[gid].append(m)

    result: list[FuturesMarket] = list(ungrouped)

    for _gid, members in by_group.items():
        if len(members) == 1:
            result.append(members[0])
            continue

        # Pick representative: most outcomes first, then highest volume_24h
        members.sort(
            key=lambda m: (
                len(getattr(m, "outcomes", None) or []),
                getattr(m, "volume_24h", 0) or 0,
            ),
            reverse=True,
        )
        representative = members[0]

        rep_outcomes = getattr(representative, "outcomes", None) or []
        # Collect outcome names already on the representative
        existing_names: set[str] = {
            (o.name or "").lower().strip() for o in rep_outcomes
        }

        # Merge unique outcomes from sibling markets
        merged_outcomes = list(rep_outcomes)
        for sibling in members[1:]:
            for o in getattr(sibling, "outcomes", None) or []:
                name_key = (o.name or "").lower().strip()
                if name_key and name_key not in existing_names:
                    merged_outcomes.append(o)
                    existing_names.add(name_key)

        # Attach merged outcomes.  We mutate the relationship list in-place
        # because SQLAlchemy lazy-loaded lists support item assignment.
        # This is safe because we are in a read-only request context and the
        # session will not be flushed/committed.
        representative.outcomes = merged_outcomes  # type: ignore[assignment]

        result.append(representative)

    return result
