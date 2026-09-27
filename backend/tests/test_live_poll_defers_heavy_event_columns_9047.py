"""#9047 — the live poll's population read leaves the event's box score behind.

`_load_live_poll_population` joins every linked market to its event, so the
event comes back once PER MARKET: 8,081 rows on 129 events at 2026-09-27
19:05Z. The asyncpg dialect json-decodes every JSONB value on every row at
fetch time, before the ORM identity map collapses the duplicates, so the read
decoded 35 MB of `box_score_data` into ~114 MB of dicts held at once — on
`worker-realtime`, a 1 GB dyno that ran over quota under the NFL slate with
this task in flight at 17 of 18 R14s.

These arms pin the statement the session is handed: the box score is out of
the SELECT list, and every event attribute the beat's path reads is still in
it — including `win_probability_sources`, which `_check_and_fix_inversion`
reads off the identity-mapped row `session.get` hands it. The sibling suites'
doubles never reach that read (the session double has no `get`, and the blend
stage is stubbed to pick no primary), so the SQL is the only place it can be
pinned.
"""

from __future__ import annotations

from tests.test_live_poll_fetch_share_6179 import _order_by, _population_sql


def _select_list(sql: str) -> set[str]:
    """The selected column names, one per item — `win_probability_sources_rev`
    is a different column and must not satisfy a substring test."""
    flat = " ".join(sql.split())
    head = flat.split(" FROM ", 1)[0].lower().removeprefix("select ")
    return {item.strip().split(" as ")[0] for item in head.split(",")}


class TestTheHeavyEventColumnsAreNotFetched:
    async def test_box_score_data_is_not_in_the_select_list(self, monkeypatch):
        """THE DEFECT ARM: one decoded box score per market row."""
        cols = _select_list(await _population_sql(monkeypatch))
        assert "events.box_score_data" not in cols, cols

    async def test_the_blend_key_still_orders_the_population(self, monkeypatch):
        """#5767's stalest-first key is read in SQL and must survive."""
        order_by = _order_by(await _population_sql(monkeypatch)).lower()
        assert "events.win_probability_sources" in order_by, order_by

    async def test_every_event_attribute_the_beat_reads_is_still_selected(
        self, monkeypatch
    ):
        cols = _select_list(await _population_sql(monkeypatch))
        for name in (
            "id",
            # `_check_and_fix_inversion`: `session.get(Event, id)` returns the
            # row this read loaded, then `.win_probability_sources` and
            # `.opening_home_probability` are read off it. Deferring either
            # raises there.
            "win_probability_sources",
            "opening_home_probability",
            "status",
            "commence_time",
            "completed_at",
            "home_team_name",
            "away_team_name",
        ):
            assert f"events.{name}" in cols, (name, cols)

    async def test_the_market_row_is_still_whole(self, monkeypatch):
        """`market_metadata` is read by the beat (Polymarket event id, pregame pin)."""
        cols = _select_list(await _population_sql(monkeypatch))
        assert "futures_markets.market_metadata" in cols, cols
