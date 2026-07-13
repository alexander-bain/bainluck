"""Queue #182: Kalshi wide-spread capture guard (weather/tech calibration disease).

The poll used to compute prob = (yes_bid + yes_ask) / 2 for ANY two-sided book,
regardless of spread. On illiquid weather/tech threshold markets a wide book
(e.g. bid=0.05 / ask=0.95) has no real price discovery at the midpoint — the
average fabricates a ~0.50 quote that was captured as the closing line and
inflated calibration MCE (#181). The fix mirrors gotcha #19's Polymarket rule:
midpoint only for a TIGHT book; otherwise prefer a real trade (last_price);
never fabricate a midpoint from a wide/one-sided book with no trade.

These tests pin _kalshi_yes_probability so the guard can't silently regress.
"""

from app.tasks.kalshi import _KALSHI_TIGHT_SPREAD_MAX, _kalshi_yes_probability


def test_tight_two_sided_book_uses_midpoint():
    # spread 0.10 < 0.50 -> real price discovery, midpoint is trusted
    assert _kalshi_yes_probability(0.45, 0.55, None) == 0.50
    assert _kalshi_yes_probability(0.20, 0.30, None) == 0.25


def test_wide_book_no_trade_is_skipped_not_fabricated():
    # bid=0.05/ask=0.95 midpoint would be 0.50 — the exact weather/tech disease.
    # No trade, ask > 0.50 -> None (caller skips), NOT 0.50.
    assert _kalshi_yes_probability(0.05, 0.95, None) is None
    # bid=0.30/ask=0.90 (spread 0.60) with no trade -> skip, don't average to 0.60
    assert _kalshi_yes_probability(0.30, 0.90, None) is None


def test_wide_book_prefers_last_price_over_midpoint():
    # Wide spread but a real trade exists -> use the trade, not the 0.50 midpoint.
    assert _kalshi_yes_probability(0.05, 0.95, 0.18) == 0.18


def test_boundary_spread_is_wide():
    # A clearly wide spread (0.55) is not tight; no trade -> skip (not a 0.475 avg).
    assert _kalshi_yes_probability(0.20, 0.75, None) is None
    # A clearly tight spread (0.40) -> midpoint.
    assert _kalshi_yes_probability(0.20, 0.60, None) == (0.20 + 0.60) / 2


def test_longshot_ask_only_cap_preserved():
    # Zero (present) bid with a low ask (<= 0.50) keeps the pre-existing longshot
    # cap behavior — a low ask is not a ~0.50 fabrication. Matches the original
    # branch, which required yes_bid to be present (0 allowed).
    assert _kalshi_yes_probability(0.0, 0.40, None) == 0.40
    # yes_bid=None disqualifies the ask-only cap (original semantics) -> skip.
    assert _kalshi_yes_probability(None, 0.10, None) is None
    # A high ask-only book (> 0.50) with a zero bid and no trade -> skip.
    assert _kalshi_yes_probability(0.0, 0.80, None) is None


def test_no_pricing_at_all_is_skipped():
    assert _kalshi_yes_probability(None, None, None) is None
    assert _kalshi_yes_probability(0.0, 0.0, 0.0) is None


def test_last_price_used_when_no_bid():
    # No bid at all, but a trade happened -> last_price (illiquid-but-traded).
    assert _kalshi_yes_probability(0.0, 0.0, 0.62) == 0.62


def test_threshold_constant_matches_polymarket_rule():
    # Guard against silent drift from the gotcha #19 / has_real_trading 0.50 rule.
    assert _KALSHI_TIGHT_SPREAD_MAX == 0.50
