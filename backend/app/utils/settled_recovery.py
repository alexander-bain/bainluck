"""Category-agnostic settled-recovery enumeration (#174 Item 2).

The main polls paginate the source UNFILTERED (all markets minus crypto), so the
create path is already category-blind. But the SUPPLEMENTARY / settled recovery
passes historically iterated HAND-BUILT category lists (Kalshi `_SPORTS_SERIES_TICKERS`,
Polymarket `_SPORTS_TAG_SLUGS`, the DB-seeded settled/gap-creation backfills). A
fast-settling category not on a hand list — or never once ingested, so absent from
the DB-derived set — fell through the seam: the "golf-class" gap (#163/#171) and
then the "combat-class" gap (#173/#1024) were the same bug rediscovered.

These helpers let a recovery pass enumerate from the SOURCE's own full listing
(Kalshi `get_series`, Polymarket `get_tags`) instead of a hand-picked subset, while:

  * keeping a PRIORITY head so the proven sports coverage never regresses, and
  * bounding per-run work via a resumable ROTATION window (cursor-persisted), so
    adding hundreds of series/tags can never starve later ones or blow the task's
    time budget (gotcha #34 — never share/skew a limit across a category loop).

Everything here is pure + I/O-free so the ingestion tasks stay thin and this logic
unit-tests without a network. The tasks own the API calls + Redis cursor; they pass
the raw listings in and get back the bounded, priority-ordered selection.
"""

from __future__ import annotations

# Crypto is excluded everywhere (the polls skip it — it consumes DB space with no
# probability-first value). Matches kalshi.py:190 (category contains "crypto") and
# polymarket.py's _TAG_TO_CATEGORY crypto slugs.
_CRYPTO_TOKENS: tuple[str, ...] = (
    "crypto", "bitcoin", "btc", "ethereum", "eth", "solana", "defi", "nft",
)


def is_crypto_text(text: str | None) -> bool:
    """True if a category name / tag slug / series category is crypto-ish."""
    low = (text or "").lower()
    return any(tok in low for tok in _CRYPTO_TOKENS)


def extract_series_tickers(
    series_dicts: list[dict], exclude_crypto: bool = True
) -> list[str]:
    """Series tickers from Kalshi `get_series` rows, crypto filtered, deduped,
    order-preserving. A row is `{"ticker": "KXNBA", "category": "Sports", ...}`."""
    seen: set[str] = set()
    out: list[str] = []
    for row in series_dicts or []:
        ticker = (row.get("ticker") or row.get("series_ticker") or "").strip()
        if not ticker or ticker in seen:
            continue
        if exclude_crypto and (
            is_crypto_text(row.get("category")) or is_crypto_text(ticker)
        ):
            continue
        seen.add(ticker)
        out.append(ticker)
    return out


def extract_tag_slugs(
    tag_dicts: list[dict], exclude_crypto: bool = True
) -> list[str]:
    """Tag slugs from Polymarket `get_tags` rows, crypto filtered, deduped,
    order-preserving. A row is `{"slug": "mma", "label": "MMA", ...}`."""
    seen: set[str] = set()
    out: list[str] = []
    for row in tag_dicts or []:
        slug = (row.get("slug") or row.get("label") or "").strip().lower()
        if not slug or slug in seen:
            continue
        if exclude_crypto and is_crypto_text(slug):
            continue
        seen.add(slug)
        out.append(slug)
    return out


def select_rotation(
    all_items: list[str],
    priority: list[str],
    cursor_pos: int,
    per_run: int,
) -> tuple[list[str], int]:
    """Bounded, resumable selection for a category-agnostic recovery pass.

    Returns ``(selection, next_cursor_pos)`` where ``selection`` is the PRIORITY
    head (those present in ``all_items``, in priority order) followed by a window of
    up to ``per_run`` of the REMAINING items rotated from ``cursor_pos``. Every
    non-priority item is reached within ``ceil(len(remaining)/per_run)`` runs, so
    nothing is starved (gotcha #34) and per-run work is capped regardless of how
    many categories the source lists.

    Mirrors the proven Kalshi settled-backfill cursor (kalshi.py `_series_cursor`):
    priority-first + rotated window + modulo advance. Pure — the caller persists
    ``next_cursor_pos`` to Redis.
    """
    present = set(all_items)
    # Priority head: keep only priorities that actually exist in the listing,
    # preserving the caller's priority order (deduped).
    seen: set[str] = set()
    head: list[str] = []
    for p in priority:
        if p in present and p not in seen:
            seen.add(p)
            head.append(p)
    remaining = [i for i in all_items if i not in seen]
    if not remaining:
        return head, 0
    per_run = max(1, per_run)
    pos = cursor_pos % len(remaining) if len(remaining) else 0
    window = (remaining[pos:] + remaining[:pos])[:per_run]
    next_pos = (pos + per_run) % len(remaining)
    # Dedupe head∪window while preserving order (a priority could also be a
    # remaining item only if it wasn't `present` — impossible here — so this is
    # belt-and-braces).
    out_seen: set[str] = set()
    selection: list[str] = []
    for item in head + window:
        if item not in out_seen:
            out_seen.add(item)
            selection.append(item)
    return selection, next_pos
