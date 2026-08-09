"""#1589 — a stale quote must not outrank a fresh one just because it is liquid.

Alex's 2026-08-08 dogfood: the event page's "Bigger Picture" section showed the
Red Sox at **63%** to make the playoffs when the real figure was **~90%**. A
27-point error, stated with a confident number, on a page being read live.

`dedup_by_merge_group` picked the winner on `bookmaker_count` alone. Most liquid
is not most correct when one of them is stale: a season-long market carried by
many bookmakers but no longer updated outranked a fresher quote from fewer.

The fix DEMOTES stale entries rather than deleting them, so the tests below lean
hard on the both-directions guard (gotcha #43) — blanking the section would be a
worse regression than a stale number.

All timestamps are explicit and the clock is injected; nothing is seeded off
`datetime.now()` (gotcha #44).
"""

from datetime import datetime, timedelta, timezone

from app.utils.related_futures import dedup_by_merge_group

NOW = datetime(2026, 8, 8, 20, 0, 0, tzinfo=timezone.utc)


def entry(source, prob, books, age_hours=None, *, merge_group="make_playoffs",
          outcome="Boston Red Sox", last_updated="__auto__"):
    if last_updated == "__auto__":
        last_updated = (
            None if age_hours is None
            else (NOW - timedelta(hours=age_hours)).isoformat()
        )
    return {
        "merge_group": merge_group,
        "outcome_name": outcome,
        "source": source,
        "probability": prob,
        "bookmaker_count": books,
        "last_updated": last_updated,
    }


def only(entries):
    out = dedup_by_merge_group(entries, now=NOW)
    assert len(out) == 1, out
    return out[0]


class TestTheReportedCase:
    def test_fresh_quote_beats_a_staler_more_liquid_one(self):
        # The defect: 12 bookmakers, 30 days old, 63% — versus a 2-hour-old 90%.
        stale = entry("odds_api", 0.63, books=12, age_hours=24 * 30)
        fresh = entry("kalshi", 0.90, books=2, age_hours=2)
        assert only([stale, fresh])["probability"] == 0.90

    def test_order_of_input_does_not_matter(self):
        stale = entry("odds_api", 0.63, books=12, age_hours=24 * 30)
        fresh = entry("kalshi", 0.90, books=2, age_hours=2)
        assert only([fresh, stale])["probability"] == 0.90

    def test_all_sources_still_aggregated_on_the_winner(self):
        stale = entry("odds_api", 0.63, books=12, age_hours=24 * 30)
        fresh = entry("kalshi", 0.90, books=2, age_hours=2)
        assert set(only([stale, fresh])["all_sources"]) == {"odds_api", "kalshi"}


class TestBothDirections:
    """The fix must not blank the section or invert the liquidity preference."""

    def test_an_all_stale_group_still_returns_its_best_entry(self):
        # Deleting stale rows would empty "Bigger Picture" — worse than stale.
        a = entry("odds_api", 0.63, books=12, age_hours=24 * 30)
        b = entry("kalshi", 0.70, books=2, age_hours=24 * 40)
        assert only([a, b])["probability"] == 0.63  # most liquid among stale

    def test_liquidity_still_decides_between_two_fresh_entries(self):
        # The original rule is untouched WITHIN a freshness tier.
        thin = entry("kalshi", 0.90, books=2, age_hours=1)
        liquid = entry("odds_api", 0.88, books=14, age_hours=3)
        assert only([thin, liquid])["probability"] == 0.88

    def test_a_single_entry_is_returned_even_when_stale(self):
        assert only([entry("odds_api", 0.63, books=12, age_hours=24 * 90)])["probability"] == 0.63

    def test_nothing_is_dropped_from_the_result_set(self):
        rows = [
            entry("odds_api", 0.63, books=12, age_hours=24 * 30),
            entry("kalshi", 0.90, books=2, age_hours=2),
            entry("odds_api", 0.40, books=9, age_hours=2, merge_group="win_total"),
            entry("kalshi", 0.10, books=3, age_hours=2,
                  merge_group="al_east_division"),
        ]
        assert len(dedup_by_merge_group(rows, now=NOW)) == 3

    def test_ungrouped_entries_pass_through_untouched(self):
        row = entry("kalshi", 0.5, books=1, age_hours=24 * 99, merge_group=None)
        assert dedup_by_merge_group([row], now=NOW) == [row]


class TestStalenessBoundary:
    def test_just_inside_the_window_is_fresh(self):
        fresh = entry("kalshi", 0.90, books=1, age_hours=23)
        liquid_stale = entry("odds_api", 0.63, books=99, age_hours=25)
        assert only([fresh, liquid_stale])["probability"] == 0.90

    def test_just_outside_the_window_is_stale(self):
        older = entry("kalshi", 0.90, books=1, age_hours=25)
        liquid_stale = entry("odds_api", 0.63, books=99, age_hours=26)
        # Both stale -> liquidity decides, unchanged from before.
        assert only([older, liquid_stale])["probability"] == 0.63

    def test_threshold_is_configurable(self):
        a = entry("odds_api", 0.63, books=12, age_hours=10)
        b = entry("kalshi", 0.90, books=2, age_hours=2)
        out = dedup_by_merge_group([a, b], now=NOW, stale_after_hours=4)
        assert out[0]["probability"] == 0.90


class TestTimestampRobustness:
    def test_missing_timestamp_counts_as_stale(self):
        no_ts = entry("odds_api", 0.63, books=12, last_updated=None)
        fresh = entry("kalshi", 0.90, books=1, age_hours=2)
        assert only([no_ts, fresh])["probability"] == 0.90

    def test_unparseable_timestamp_counts_as_stale_and_does_not_raise(self):
        bad = entry("odds_api", 0.63, books=12, last_updated="not a date")
        fresh = entry("kalshi", 0.90, books=1, age_hours=2)
        assert only([bad, fresh])["probability"] == 0.90

    def test_zulu_suffix_parses(self):
        z = (NOW - timedelta(hours=1)).replace(tzinfo=None).isoformat() + "Z"
        fresh = entry("kalshi", 0.90, books=1, last_updated=z)
        stale = entry("odds_api", 0.63, books=99, age_hours=24 * 30)
        assert only([fresh, stale])["probability"] == 0.90

    def test_naive_timestamp_is_treated_as_utc_not_a_crash(self):
        naive = (NOW - timedelta(hours=1)).replace(tzinfo=None).isoformat()
        fresh = entry("kalshi", 0.90, books=1, last_updated=naive)
        stale = entry("odds_api", 0.63, books=99, age_hours=24 * 30)
        assert only([fresh, stale])["probability"] == 0.90
