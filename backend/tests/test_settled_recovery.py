"""Unit tests for category-agnostic settled-recovery enumeration (#174 Item 2).

Guards the durable "hand-built net has holes" class fix: source-enumerated
series/tags are crypto-filtered, and the rotation window is bounded + starvation-
free (every non-priority item is reached, none starved — gotcha #34)."""

from app.utils.settled_recovery import (
    extract_series_tickers,
    extract_tag_slugs,
    is_crypto_text,
    select_rotation,
)


class TestCryptoFilter:
    def test_detects_crypto_variants(self):
        for t in ["Crypto", "bitcoin price", "ETHEREUM", "defi", "NFT floor", "btc"]:
            assert is_crypto_text(t) is True

    def test_non_crypto_passes(self):
        for t in ["Sports", "mma", "politics", "The Open", None, ""]:
            assert is_crypto_text(t) is False


class TestExtractSeriesTickers:
    def test_dedupes_and_preserves_order(self):
        rows = [
            {"ticker": "KXNBA", "category": "Sports"},
            {"ticker": "KXUFCFIGHT", "category": "Sports"},
            {"ticker": "KXNBA", "category": "Sports"},  # dup
        ]
        assert extract_series_tickers(rows) == ["KXNBA", "KXUFCFIGHT"]

    def test_excludes_crypto_by_category_or_ticker(self):
        rows = [
            {"ticker": "KXBTCPRICE", "category": "Crypto"},
            {"ticker": "KXETH", "category": "Financials"},
            {"ticker": "KXUFCFIGHT", "category": "Sports"},
        ]
        assert extract_series_tickers(rows) == ["KXUFCFIGHT"]

    def test_crypto_kept_when_disabled(self):
        rows = [{"ticker": "KXBTC", "category": "Crypto"}]
        assert extract_series_tickers(rows, exclude_crypto=False) == ["KXBTC"]

    def test_handles_empty_and_missing_ticker(self):
        assert extract_series_tickers([]) == []
        assert extract_series_tickers([{"category": "Sports"}]) == []


class TestExtractTagSlugs:
    def test_lowercases_dedupes_filters_crypto(self):
        rows = [
            {"slug": "MMA"},
            {"slug": "boxing"},
            {"slug": "crypto"},
            {"slug": "mma"},  # dup after lowercase
        ]
        assert extract_tag_slugs(rows) == ["mma", "boxing"]

    def test_falls_back_to_label(self):
        assert extract_tag_slugs([{"label": "Politics"}]) == ["politics"]


class TestSelectRotation:
    def test_priority_head_then_window(self):
        items = ["a", "b", "c", "d", "e"]
        priority = ["c"]
        sel, nxt = select_rotation(items, priority, cursor_pos=0, per_run=2)
        # priority 'c' first, then window of 2 from remaining [a,b,d,e]
        assert sel[0] == "c"
        assert sel[1:] == ["a", "b"]
        assert nxt == 2

    def test_priority_absent_from_listing_is_dropped(self):
        # a hand-priority not present at source must not appear (no dead entry)
        sel, _ = select_rotation(["a", "b"], ["zzz"], cursor_pos=0, per_run=5)
        assert "zzz" not in sel
        assert set(sel) == {"a", "b"}

    def test_rotation_covers_all_without_starvation(self):
        items = [f"s{i}" for i in range(10)]
        priority: list[str] = []
        seen: set[str] = set()
        pos = 0
        # ceil(10/3) = 4 runs must cover every item
        for _ in range(4):
            sel, pos = select_rotation(items, priority, cursor_pos=pos, per_run=3)
            seen.update(sel)
        assert seen == set(items)

    def test_per_run_bounds_window(self):
        items = [f"s{i}" for i in range(100)]
        sel, _ = select_rotation(items, [], cursor_pos=0, per_run=12)
        assert len(sel) == 12

    def test_empty_remaining_returns_priority_only(self):
        sel, nxt = select_rotation(["a"], ["a"], cursor_pos=0, per_run=5)
        assert sel == ["a"]
        assert nxt == 0
