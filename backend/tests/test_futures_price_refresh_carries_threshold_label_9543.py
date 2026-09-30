"""#9543 — the high-value price refresher carries the threshold label forward.

**The reader-visible defect.** ``bainluck.com/futures/61461638`` "Colombia
minimum wage growth minus inflation in 2027" printed **Yes 17%** on 2026-09-30.
Kalshi's ``KXCOWAGE-2027`` is one market, ``strike_type='greater'``,
``floor_strike=4``, ``yes_sub_title='Above 4.00 pp'``: the question's number.
#9383 put that label in ``market_metadata.threshold_label``, but only the
discovery poll writes it, and the poll had not reached this row since
2026-09-26 (main-scan cursor never wrapped in 14 runs). The refresher priced
the row at 00:55Z that day from the same payload and dropped the label.

These guards pin three things:

1. ``_fetch_kalshi_prices`` fills ``labels`` from the payload it already read
   (the venue's own bytes for both #9543 specimens), only on the list return,
   and never for a plain binary or a multi-market event.
2. The write statement merges one key and never removes it (shape here; the
   JSONB rows are proved on Postgres in
   ``tests/integration/test_futures_price_refresh_writes_pg.py``).
3. The loop writes it after the price and window commits, in its own
   transaction, and counts it.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.kalshi_api import KalshiAPIService
from app.tasks import futures_price_refresh as fpr
from app.utils.kalshi_threshold_label import (
    THRESHOLD_LABEL_KEY,
    single_leg_threshold_label,
)


def _cowage():
    """``KXCOWAGE-2027`` as Kalshi served it on 2026-09-30 03:4xZ."""
    return {
        "event_ticker": "KXCOWAGE-2027",
        "title": "Colombia minimum wage growth minus inflation in 2027",
        "markets": [
            {
                "ticker": "KXCOWAGE-2027-T400",
                "status": "active",
                "result": "",
                "strike_type": "greater",
                "floor_strike": 4,
                "cap_strike": None,
                "yes_sub_title": "Above 4.00 pp",
                "no_sub_title": "Above 4.00 pp",
                "yes_bid_dollars": "0.1500",
                "yes_ask_dollars": "0.1900",
                "last_price_dollars": "0.1400",
                "close_time": "2027-02-15T15:00:00Z",
                "expiration_time": "2027-02-15T15:00:00Z",
            }
        ],
    }


def _pokemon():
    """``KXPOKEMON-26SEPCELULTPR`` as Kalshi served it on 2026-09-30 03:4xZ."""
    raw = _cowage()
    raw["event_ticker"] = "KXPOKEMON-26SEPCELULTPR"
    raw["title"] = "Celebrations Ultra Premium Collection Up or Down: "
    raw["markets"][0].update(
        ticker="KXPOKEMON-26SEPCELULTPR-1237.81",
        floor_strike=1237.81,
        yes_sub_title="Above $1237.81",
        no_sub_title="Above $1237.81",
        yes_bid_dollars="0.1600",
        yes_ask_dollars="0.2400",
        close_time="2026-10-01T03:59:00Z",
        expiration_time="2026-10-01T03:59:00Z",
    )
    return raw


class _Venue:
    """`get_event` over a fixed payload; the PARSER is the real one."""

    def __init__(self, raw):
        self._raw = raw
        self.calls = 0
        self._svc = KalshiAPIService(api_key=None)

    async def get_event(self, ticker, with_nested_markets=True):
        self.calls += 1
        return self._raw

    def _parse_event(self, raw):
        return self._svc._parse_event(raw)


def _fetch(raw, **kw):
    return asyncio.run(fpr._fetch_kalshi_prices(_Venue(raw), raw["event_ticker"], **kw))


# --- 1. the fetch fills it from the payload it already read -----------------


class TestTheFetchFillsTheLabel:
    @pytest.mark.parametrize(
        "raw, want",
        [(_cowage(), "Above 4.00 pp"), (_pokemon(), "Above $1237.81")],
        ids=["KXCOWAGE-2027", "KXPOKEMON-26SEPCELULTPR"],
    )
    def test_both_specimens_get_the_venues_label_with_no_extra_call(self, raw, want):
        venue = _Venue(raw)
        labels: dict = {}
        priced = asyncio.run(
            fpr._fetch_kalshi_prices(venue, raw["event_ticker"], labels=labels)
        )
        assert isinstance(priced, list) and priced
        assert labels == {raw["event_ticker"]: want}
        assert venue.calls == 1

    def test_it_is_the_polls_helper_not_a_second_rule(self):
        raw = _cowage()
        markets = KalshiAPIService(api_key=None)._parse_event(raw).markets
        labels: dict = {}
        _fetch(raw, labels=labels)
        assert labels[raw["event_ticker"]] == single_leg_threshold_label(markets)

    def test_a_plain_binary_is_not_entered(self):
        # KXINDUS-27JAN01-YES shape (the helper's own refusal): no strike.
        raw = _cowage()
        raw["markets"][0].update(
            strike_type=None, floor_strike=None, yes_sub_title="Yes"
        )
        labels: dict = {}
        priced = _fetch(raw, labels=labels)
        assert isinstance(priced, list) and priced  # still priced
        assert labels == {}

    def test_a_multi_market_event_is_not_entered(self):
        raw = _cowage()
        second = dict(
            raw["markets"][0],
            ticker="KXCOWAGE-2027-T500",
            floor_strike=5,
            yes_sub_title="Above 5.00 pp",
        )
        raw["markets"].append(second)
        labels: dict = {}
        _fetch(raw, labels=labels)
        assert labels == {}

    def test_a_settled_event_fills_nothing(self):
        raw = _cowage()
        raw["markets"][0].update(status="finalized", result="no")
        labels: dict = {}
        assert _fetch(raw, labels=labels) is fpr.VENUE_SETTLED
        assert labels == {}

    def test_without_labels_the_return_is_unchanged(self):
        assert _fetch(_cowage(), labels={}) == _fetch(_cowage())

    def test_a_helper_failure_costs_the_label_not_the_prices_or_the_date(
        self, monkeypatch
    ):
        def _boom(*a, **k):
            raise RuntimeError("label broke")

        monkeypatch.setattr(fpr, "single_leg_threshold_label", _boom)
        labels: dict = {}
        windows: dict = {}
        priced = _fetch(_cowage(), labels=labels, windows=windows)
        assert isinstance(priced, list) and priced
        assert labels == {}
        assert "KXCOWAGE-2027" in windows  # the date path still ran


# --- 2. the statement merges one key and removes nothing --------------------


class TestTheWriteShape:
    SQL = str(fpr._KALSHI_THRESHOLD_LABEL_WRITE_SQL)

    def test_it_writes_the_key_the_poll_writes_and_the_readers_read(self):
        assert f"'{THRESHOLD_LABEL_KEY}'" in self.SQL
        assert THRESHOLD_LABEL_KEY == "threshold_label"

    def test_it_merges_rather_than_assigns(self):
        set_clause = self.SQL.split("SET", 1)[1].split("WHERE", 1)[0]
        assert "||" in set_clause
        # SQL NULL and JSON null both become {} before the merge (the PG gate
        # showed JSON null || object is an ARRAY).
        assert "jsonb_typeof(market_metadata) = 'object'" in set_clause

    def test_it_never_writes_status_or_a_grade_or_removes_a_key(self):
        set_clause = self.SQL.split("SET", 1)[1].split("WHERE", 1)[0]
        assert "status" not in set_clause
        assert "is_winner" not in self.SQL
        assert "#-" not in self.SQL and " - '" not in self.SQL

    def test_it_is_kalshi_only_and_idempotent(self):
        where = self.SQL.split("WHERE", 1)[1]
        assert "source = 'kalshi'" in where
        assert "IS DISTINCT FROM" in where


# --- 3. the wiring: after the price and window commits, its own transaction -

from tests.test_futures_price_refresh import _RunHarness  # noqa: E402

SPECIMEN_ROW = (61461638, "kalshi", "KXCOWAGE-2027", 123_078, None, None)


class _LabelHarness(_RunHarness):
    """The real entry point with one Kalshi class row, the Colombia wage market.

    Only the venue and the price writer are faked; the loop, its transaction
    boundaries and the stats are the task's own.
    """

    def __init__(self, *, label, window=None, fail_label=False, priced=True):
        from app.utils.feed_served_markets import SERVED_EMPTY

        signal = type(
            "Sig",
            (),
            {
                "ids": [],
                "state": SERVED_EMPTY,
                "green_allowed": True,
                "shapes": 0,
                "stale_shapes": 0,
                "unreadable_shapes": 0,
            },
        )()
        super().__init__(signal=signal, class_rows=[SPECIMEN_ROW + (0, 1)])
        self.label = label
        self.window = window
        self.fail_label = fail_label
        self.priced = priced
        self.log: list[str] = []

    class _Session(_RunHarness._Session):
        async def execute(self, statement, params=None):
            if statement is fpr._KALSHI_THRESHOLD_LABEL_WRITE_SQL:
                self.outer.log.append(f"label:{params['mid']}:{params['label']}")
                if self.outer.fail_label:
                    raise RuntimeError("label write failed")
                return _RunHarness._Result(rows=[(params["mid"],)])
            if statement is fpr._KALSHI_WINDOW_WRITE_SQL:
                self.outer.log.append(f"window:{params['mid']}")
                return _RunHarness._Result(rows=[(params["mid"],)])
            return await super().execute(statement, params)

        async def commit(self):
            self.outer.log.append("commit")

        async def rollback(self):
            self.outer.log.append("rollback")

    async def run(self, monkeypatch):
        outer = self

        async def _fetch(service, external_id, *, windows=None, labels=None):
            outer.log.append(f"fetch:{external_id}")
            if windows is not None and outer.window is not None:
                windows[external_id] = outer.window
            if labels is not None and outer.label is not None:
                labels[external_id] = outer.label
            return [{"external_id": "KXCOWAGE-2027-T400", "probability": 0.17}]

        async def _write_prices(session, mid, source, priced, stats):
            outer.log.append(f"prices:{mid}")
            return 1 if outer.priced else 0

        async def _nothing(*a, **k):
            return {}

        class _KService:
            async def close(self):
                return None

        monkeypatch.setenv("KALSHI_API_KEY", "test-only")
        monkeypatch.setattr(fpr, "_fetch_kalshi_prices", _fetch)
        monkeypatch.setattr(fpr, "_write_prices", _write_prices)
        monkeypatch.setattr(fpr, "_scan_kalshi_frozen_certain", _nothing)
        monkeypatch.setattr(fpr, "_kalshi_reach_arm", _nothing)
        monkeypatch.setattr(
            "app.services.kalshi_api.KalshiAPIService", lambda *a, **k: _KService()
        )
        return await super().run(monkeypatch)


def _after_fetch(log):
    return log[log.index("fetch:KXCOWAGE-2027") + 1 :]


class TestTheLoopWritesTheLabel:
    @pytest.mark.asyncio
    async def test_written_after_the_price_commit_and_counted(self, monkeypatch):
        h = _LabelHarness(label="Above 4.00 pp")
        stats = await h.run(monkeypatch)
        tail = _after_fetch(h.log)
        assert tail[:4] == [
            "prices:61461638",
            "commit",
            "label:61461638:Above 4.00 pp",
            "commit",
        ], tail
        assert stats["threshold_labels_written"] == 1

    @pytest.mark.asyncio
    async def test_it_follows_the_window_write_not_replaces_it(self, monkeypatch):
        from datetime import datetime, timezone

        rd = datetime(2027, 2, 15, 15, tzinfo=timezone.utc)
        h = _LabelHarness(label="Above 4.00 pp", window=(rd, rd))
        await h.run(monkeypatch)
        tail = _after_fetch(h.log)
        assert tail[:6] == [
            "prices:61461638",
            "commit",
            "window:61461638",
            "commit",
            "label:61461638:Above 4.00 pp",
            "commit",
        ], tail

    @pytest.mark.asyncio
    async def test_written_even_when_no_price_survived(self, monkeypatch):
        # The label is the venue's wording, independent of whether this pass
        # could price the leg: an unpriceable threshold board still says "Yes".
        h = _LabelHarness(label="Above 4.00 pp", priced=False)
        stats = await h.run(monkeypatch)
        assert "label:61461638:Above 4.00 pp" in h.log
        assert stats["threshold_labels_written"] == 1

    @pytest.mark.asyncio
    async def test_nothing_filled_is_nothing_written_and_reads_zero(self, monkeypatch):
        h = _LabelHarness(label=None)
        stats = await h.run(monkeypatch)
        assert not [e for e in h.log if e.startswith("label:")]
        # Reported as zero, not absent: zero and "never asked" must differ.
        assert stats["threshold_labels_written"] == 0

    @pytest.mark.asyncio
    async def test_a_failed_label_write_keeps_the_prices(self, monkeypatch):
        h = _LabelHarness(label="Above 4.00 pp", fail_label=True)
        stats = await h.run(monkeypatch)
        tail = _after_fetch(h.log)
        assert tail[:4] == [
            "prices:61461638",
            "commit",
            "label:61461638:Above 4.00 pp",
            "rollback",
        ], tail
        assert stats["threshold_labels_written"] == 0
        assert stats["markets_priced"] == 1
        assert any("kalshi label KXCOWAGE-2027" in e for e in stats["errors"])
