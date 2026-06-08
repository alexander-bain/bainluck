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

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

GARBAGE_OUTCOME_RE = re.compile(
    r"^(?:player|person|candidate|option|party)\s+[A-Z]{1,3}$", re.I
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
    """Filter garbage placeholder outcomes."""
    return [o for o in outcomes if not GARBAGE_OUTCOME_RE.match(o.name or "")]


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


def _is_conservative_near_match(left: str, right: str) -> bool:
    """Return True for obvious paraphrases, with guards against false matches."""
    left_tokens = _near_match_tokens(left)
    right_tokens = _near_match_tokens(right)
    if len(left_tokens) < 3 or len(right_tokens) < 3:
        return False
    if _numeric_tokens(left_tokens) != _numeric_tokens(right_tokens):
        return False
    left_directions = _direction_tokens(left_tokens)
    right_directions = _direction_tokens(right_tokens)
    if left_directions or right_directions:
        if left_directions != right_directions:
            return False

    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    if union == 0:
        return False
    jaccard = overlap / union
    containment = overlap / min(len(left_tokens), len(right_tokens))
    return jaccard >= 0.72 and containment >= 0.85


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

    Parameters
    ----------
    markets:
        Sequence of FuturesMarket objects to scan.
    market_row_fn:
        Callable that receives a single FuturesMarket and returns either None
        (skip this market) or a dict containing at minimum ``q``, ``prob``,
        ``src``, and ``market_id``.  May include extra keys (e.g. ``theme``)
        that will be preserved in the output.
    max_results:
        Maximum number of cross-source pairs to return (default 8).

    Returns
    -------
    list[dict]
        Each entry has: ``q``, ``kalshi``, ``poly``, ``delta``, ``category``,
        ``kalshi_market_id``, ``poly_market_id``.
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
        delta = round(abs(k["prob"] - p["prob"]), 1)
        matches.append(
            {
                "q": k["q"],
                "kalshi": k["prob"],
                "poly": p["prob"],
                "delta": delta,
                "category": k.get("theme", ""),
                "kalshi_market_id": k["market_id"],
                "poly_market_id": p["market_id"],
            }
        )
        matched_market_ids.add(k["market_id"])
        matched_market_ids.add(p["market_id"])

    for k_norm, k in rows_by_source["kalshi"]:
        if k["market_id"] in matched_market_ids:
            continue
        best_poly = None
        best_score = 0.0
        for p_norm, p in rows_by_source["polymarket"]:
            if p["market_id"] in matched_market_ids or k_norm == p_norm:
                continue
            if not _is_conservative_near_match(k["q"], p["q"]):
                continue
            k_tokens = _near_match_tokens(k["q"])
            p_tokens = _near_match_tokens(p["q"])
            score = len(k_tokens & p_tokens) / len(k_tokens | p_tokens)
            if score > best_score:
                best_poly = p
                best_score = score
        if not best_poly:
            continue
        delta = round(abs(k["prob"] - best_poly["prob"]), 1)
        matches.append(
            {
                "q": k["q"],
                "kalshi": k["prob"],
                "poly": best_poly["prob"],
                "delta": delta,
                "category": k.get("theme", ""),
                "kalshi_market_id": k["market_id"],
                "poly_market_id": best_poly["market_id"],
            }
        )
        matched_market_ids.add(k["market_id"])
        matched_market_ids.add(best_poly["market_id"])

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
