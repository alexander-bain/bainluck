"""Shared cross-source matching utilities for category page routes.

Extracts the common pattern of finding markets that exist on both Kalshi and
Polymarket, then ranking by probability disagreement.  Used by politics.py,
entertainment.py, and economics.py.
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


def source(market: FuturesMarket) -> str:
    """Return the lowercased source name for a market."""
    return (market.source or "").lower()


def is_resolved(market: FuturesMarket) -> bool:
    """A market is effectively resolved if any outcome is >= 99%."""
    for o in market.outcomes:
        if float(o.current_probability or 0) >= 0.99:
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

    matches = []
    for _norm, sources in by_norm.items():
        if "kalshi" not in sources or "polymarket" not in sources:
            continue
        k = sources["kalshi"]
        p = sources["polymarket"]
        delta = round(abs(k["prob"] - p["prob"]), 1)
        matches.append({
            "q": k["q"],
            "kalshi": k["prob"],
            "poly": p["prob"],
            "delta": delta,
            "category": k.get("theme", ""),
            "kalshi_market_id": k["market_id"],
            "poly_market_id": p["market_id"],
        })

    matches.sort(key=lambda x: -x["delta"])
    return matches[:max_results]
