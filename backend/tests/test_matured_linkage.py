"""Unit tests for the matured-linkage metric (Queue #220/221 Item 2).

Alex's ruling: below-100% must MEAN something. These pin the pure summarizer's
contract: 100% when every imminent blend prediction-market source is backed by a
linked winner market, below-100 ONLY for phantom blend sources (real defects),
and a graceful insufficient_slate status when there is nothing checkable — never
a misleading 100 or 0 on an empty slate.
"""

from app.utils.matured_linkage import CHECKABLE_SOURCES, summarize_matured_linkage


def _row(eid, source, linked, sport="baseball_mlb", matchup="A @ B"):
    return {
        "event_id": eid,
        "source": source,
        "linked": linked,
        "sport": sport,
        "matchup": matchup,
        "commence_time": "2026-07-21T23:00:00+00:00",
    }


class TestSummarize:
    def test_all_backed_is_100(self):
        rows = [_row(1, "kalshi", True), _row(1, "polymarket", True), _row(2, "kalshi", True)]
        out = summarize_matured_linkage(rows)
        assert out["headline_pct"] == 100.0
        assert out["status"] == "ok"
        assert out["phantom"] == 0
        assert out["misses"] == []
        assert out["events_consistent"] == out["events_checked"] == 2

    def test_phantom_drags_below_100_and_is_filed(self):
        rows = [_row(1, "kalshi", True), _row(2, "polymarket", False), _row(3, "kalshi", True)]
        out = summarize_matured_linkage(rows)
        assert out["headline_pct"] == round(100 * 2 / 3, 1)
        assert out["phantom"] == 1
        assert len(out["misses"]) == 1
        miss = out["misses"][0]
        assert miss["event_id"] == 2 and miss["source"] == "polymarket"
        # The event with the phantom is not counted consistent.
        assert out["events_consistent"] == 2  # events 1 and 3
        assert out["events_checked"] == 3

    def test_empty_slate_is_insufficient_not_zero_or_100(self):
        out = summarize_matured_linkage([])
        assert out["status"] == "insufficient_slate"
        assert out["headline_pct"] is None
        assert out["checkable_pairs"] == 0
        assert out["misses"] == []

    def test_by_source_breakdown(self):
        rows = [_row(1, "kalshi", True), _row(2, "kalshi", False), _row(3, "polymarket", True)]
        out = summarize_matured_linkage(rows)
        assert out["by_source"]["kalshi"]["total"] == 2
        assert out["by_source"]["kalshi"]["phantom"] == 1
        assert out["by_source"]["kalshi"]["backed_pct"] == 50.0
        assert out["by_source"]["polymarket"]["backed_pct"] == 100.0

    def test_checkable_sources_are_the_linkable_pm_sources(self):
        # Only sources whose blend entry is backed by a linkable market are
        # checkable — betting/espn/mlb have no futures_market to link.
        assert set(CHECKABLE_SOURCES) == {"kalshi", "polymarket"}
