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


# ---------------------------------------------------------------------------
# #5121 — a trade the LIVE BOOK has priced out is not evidence.
#
# Rule 2 preferred any real trade to a wide book. That is right when the book is
# uninformative and wrong when the book MOVED PAST the trade: an ask of 0.09
# means anyone may buy at nine cents now, so a trade at 0.52 is a memory, not a
# price. A reader saw this as Miami's "60+ wins 52%" printed above its own
# "55+ wins 14.5%" — a cumulative ladder going up, which no season can make true.
# ---------------------------------------------------------------------------


def test_a_trade_above_the_live_ask_is_refuted_5121():
    # THE SPECIMEN, verbatim from production KXNBAWINS-27MIA-60 (2026-09-11):
    # venue bid 0.0000 / ask 0.0900 / last 0.5200. Rule 1 fails on the zero bid,
    # so rule 2 used to publish the stale 0.52. It must now fall through to the
    # ask-only cap and price the rung at the venue's own live offer.
    assert _kalshi_yes_probability(0.0, 0.09, 0.52) == 0.09
    # And the rung below it is untouched (tight book -> midpoint), so the ladder
    # reads 55+ 0.145 > 60+ 0.09 and stops contradicting itself.
    assert _kalshi_yes_probability(0.11, 0.18, None) == 0.145


def test_empty_book_still_falls_through_to_the_last_trade_5121():
    # 🔴 LOAD-BEARING. `kalshi_resolution_sweep.RECENT_FINAL_SELECT_SQL` screens
    # live games on `yes_bid = 0 AND yes_ask = 1` precisely BECAUSE that shape
    # falls through to the last trade here — it is how a stuck 99%/1% ladder is
    # spotted. An ask of 1.00 cannot be exceeded, so the refutation is inert on
    # the empty book by construction. If this test ever fails, that sweep's
    # screen has been silently changed too.
    assert _kalshi_yes_probability(0.0, 1.0, 0.99) == 0.99
    assert _kalshi_yes_probability(0.0, 1.0, 0.01) == 0.01


def test_a_trade_inside_the_live_book_is_still_trusted_5121():
    # The wide-book-prefers-the-trade rule (#182) is untouched whenever the book
    # has NOT moved past the trade — this is the case the refutation must not eat.
    assert _kalshi_yes_probability(0.05, 0.95, 0.18) == 0.18
    # Exactly AT the ask is not refuted: the venue quotes on a one-cent grid, so
    # a trade at the offer is a trade at a live price.
    assert _kalshi_yes_probability(0.0, 0.09, 0.09) == 0.09
    # One cent ABOVE the ask is refuted, and the ask-only cap answers instead.
    assert _kalshi_yes_probability(0.0, 0.09, 0.10) == 0.09


def test_a_refuted_trade_on_a_high_ask_book_is_skipped_not_fabricated_5121():
    # ask > ASK_ONLY_TRUSTED_MAX, so rule 3 declines and rule 4 skips. We publish
    # NOTHING rather than swap one unsupported number for another — the same
    # "don't fabricate" judgement Queue #182 made for the wide no-trade book.
    assert _kalshi_yes_probability(0.0, 0.80, 0.95) is None


def test_a_trade_below_a_live_bid_is_refuted_5121():
    # The mirror arm. Spread 0.60 keeps rule 1 out, and a standing bid of 0.40 is
    # money you could sell into right now, so a trade at 0.20 is priced out the
    # same way. Rule 3 declines (ask > 0.50) -> skip.
    assert _kalshi_yes_probability(0.40, 1.0, 0.20) is None


def test_every_measured_production_violation_is_repaired_5121():
    """The full #5121 census, checked ticker-by-ticker against Kalshi itself.

    These twelve rows are every rung of `KXNBAWINS-27*` / `KXNFLWINS-27*` whose
    stored probability exceeded its own ask on 2026-09-11 ~17:00Z. For all
    twelve the stored value equalled the venue's `last_price` EXACTLY (12/12,
    zero mismatches), which is what identifies rule 2 as the writer rather than
    a stale row. Each must now price at or below the venue's live ask.
    """
    # (ticker, venue yes_bid, venue yes_ask, venue last_price)
    measured = [
        ("KXNBAWINS-27MIA-60", 0.0, 0.09, 0.52),
        ("KXNBAWINS-27TOR-60", 0.0, 0.08, 0.11),
        ("KXNBAWINS-27MIN-65", 0.0, 0.06, 0.07),
        ("KXNBAWINS-27DAL-55", 0.0, 0.06, 0.07),
        ("KXNFLWINS-27CLE-13", 0.0, 0.05, 0.10),
        ("KXNFLWINS-27SF-16", 0.0, 0.08, 0.17),
        ("KXNFLWINS-27CAR-14", 0.0, 0.05, 0.09),
        ("KXNFLWINS-27CAR-15", 0.0, 0.05, 0.06),
        ("KXNFLWINS-27CAR-16", 0.0, 0.05, 0.06),
        ("KXNFLWINS-27KC-17", 0.0, 0.05, 0.06),
        ("KXNFLWINS-27CIN-17", 0.0, 0.05, 0.06),
        ("KXNFLWINS-27NE-16", 0.0, 0.01, 0.02),
    ]
    for ticker, bid, ask, last in measured:
        # Before the fix every one of these returned `last`, above its own ask.
        assert _kalshi_yes_probability(bid, ask, last) is not None, ticker
        assert _kalshi_yes_probability(bid, ask, last) <= ask, ticker
