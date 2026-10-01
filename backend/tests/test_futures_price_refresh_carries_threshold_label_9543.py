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


# --- 4. CERT-3817: the reach — an unlabelled row the value arms never select --

POKEMON_ROW = (60481264, "kalshi", "KXPOKEMON-26SEPCELULTPR", 5_170, None, None)
COWAGE_ROW = (61461638, "kalshi", "KXCOWAGE-2027", 123_078, None, None)
PLAIN_ROW = (70000001, "kalshi", "KXINDUS-27JAN01", 900, None, None)
UNREADABLE_ROW = (70000002, "kalshi", "KXGONE-27", 50, None, None)

VENUE_LABELS = {
    "KXPOKEMON-26SEPCELULTPR": "Above $1237.81",
    "KXCOWAGE-2027": "Above 4.00 pp",
}


def _signal():
    from app.utils.feed_served_markets import SERVED_EMPTY

    return type(
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


class _ReachHarness(_RunHarness):
    """The real entry point, with the label arm's statement answered.

    The venue answers the two #9543 specimens with their real leg labels, a
    plain binary with a price and no label, and one ticker with nothing (an
    unreadable read). Everything between the selector and the write is the
    task's own: attribution, ordering, the cap, rotation, both markers.
    """

    def __init__(
        self, *, label_rows, class_rows=(), skips=(), per_run=None, read_elsewhere=()
    ):
        super().__init__(signal=_signal(), class_rows=list(class_rows))
        self.label_rows = list(label_rows)
        self.skips = set(skips)
        # Ids holding the PRICE-attempt marker: another arm read them inside
        # its own window.
        self.read_elsewhere = set(read_elsewhere)
        self.per_run = per_run
        self.fetched: list[str] = []
        self.label_writes: list[tuple[int, str]] = []
        self.marks: dict[tuple[int, ...], int] = {}
        self.label_marks: list[int] = []
        self.label_skip_asked: list[int] = []

    class _Session(_RunHarness._Session):
        async def execute(self, statement, params=None):
            if statement is fpr._THRESHOLD_LABEL_CANDIDATE_SQL:
                limit = params["threshold_label_limit"]
                return _RunHarness._Result(self.outer.label_rows[:limit])
            if statement is fpr._KALSHI_THRESHOLD_LABEL_WRITE_SQL:
                self.outer.label_writes.append((params["mid"], params["label"]))
                return _RunHarness._Result(rows=[(params["mid"],)])
            return await super().execute(statement, params)

    def _mark(self, ids, ttl_seconds):
        self.marks[tuple(ids)] = ttl_seconds

    def _attempt_skips(self, ids):
        return {i for i in ids if i in self.read_elsewhere}

    async def run(self, monkeypatch):
        outer = self

        async def _fetch(service, external_id, *, windows=None, labels=None):
            outer.fetched.append(external_id)
            if external_id == UNREADABLE_ROW[2]:
                return None
            if labels is not None and external_id in VENUE_LABELS:
                labels[external_id] = VENUE_LABELS[external_id]
            return [{"external_id": f"{external_id}-T1", "probability": 0.4}]

        async def _write_prices(session, mid, source, priced, stats):
            return 1

        async def _nothing(*a, **k):
            return {}

        class _KService:
            async def close(self):
                return None

        def _label_skips(ids):
            outer.label_skip_asked.extend(ids)
            return {i for i in ids if i in outer.skips}

        monkeypatch.setenv("KALSHI_API_KEY", "test-only")
        monkeypatch.setattr(fpr, "_fetch_kalshi_prices", _fetch)
        monkeypatch.setattr(fpr, "_write_prices", _write_prices)
        monkeypatch.setattr(fpr, "_scan_kalshi_frozen_certain", _nothing)
        monkeypatch.setattr(fpr, "_kalshi_reach_arm", _nothing)
        monkeypatch.setattr(fpr, "_load_label_attempt_skips", _label_skips)
        monkeypatch.setattr(fpr, "_mark_label_attempted", outer.label_marks.extend)
        monkeypatch.setattr(
            "app.services.kalshi_api.KalshiAPIService", lambda *a, **k: _KService()
        )
        if self.per_run is not None:
            real = fpr._refresh_stale_futures_prices

            async def _capped(**kw):
                return await real(threshold_label_per_run=self.per_run, **kw)

            monkeypatch.setattr(fpr, "_refresh_stale_futures_prices", _capped)
        return await super().run(monkeypatch)


class TestTheArmReachesWhatTheValueArmsCannot:
    @pytest.mark.asyncio
    async def test_both_specimens_are_selected_fetched_and_labelled(self, monkeypatch):
        """CERT-3817's required regression, selector to write. 60481264 is in
        no other arm (no class rows here), so before this arm it was never read.
        """
        h = _ReachHarness(label_rows=[POKEMON_ROW, COWAGE_ROW])
        stats = await h.run(monkeypatch)

        assert h.fetched == ["KXPOKEMON-26SEPCELULTPR", "KXCOWAGE-2027"]
        assert h.label_writes == [
            (60481264, "Above $1237.81"),
            (61461638, "Above 4.00 pp"),
        ]
        assert stats["threshold_label_pool"] == 2
        assert stats["threshold_label_candidates"] == 2
        assert stats["threshold_label_attempted"] == 2
        assert stats["threshold_labels_written"] == 2
        assert stats["threshold_label_pool_capped"] is False
        # Rotated on the arm's OWN marker, never the 45-minute identity one.
        assert sorted(h.label_marks) == [60481264, 61461638]
        for ids in h.marks:
            assert 60481264 not in ids and 61461638 not in ids

    @pytest.mark.asyncio
    async def test_a_plain_binary_and_an_unreadable_read_write_no_label(
        self, monkeypatch
    ):
        h = _ReachHarness(label_rows=[PLAIN_ROW, UNREADABLE_ROW, POKEMON_ROW])
        stats = await h.run(monkeypatch)

        assert h.fetched == ["KXINDUS-27JAN01", "KXGONE-27", "KXPOKEMON-26SEPCELULTPR"]
        assert h.label_writes == [(60481264, "Above $1237.81")]
        assert stats["threshold_labels_written"] == 1
        # Refusals are attempts too: they rotate out for the retry window
        # rather than taking the head of every beat.
        assert sorted(h.label_marks) == [60481264, 70000001, 70000002]

    @pytest.mark.asyncio
    async def test_a_stale_class_row_stays_on_the_class_arm_and_is_still_labelled(
        self, monkeypatch
    ):
        """The Colombia row clears the volume floor. Taken by the label arm it
        would trade its 6h price marker for a 20h rotation slot."""
        h = _ReachHarness(
            label_rows=[COWAGE_ROW, POKEMON_ROW], class_rows=[COWAGE_ROW + (0, 1)]
        )
        stats = await h.run(monkeypatch)

        assert h.fetched.count("KXCOWAGE-2027") == 1
        assert stats["candidates"] == 2
        assert stats["threshold_label_candidates"] == 1
        assert h.label_marks == [60481264]
        assert h.marks.get((61461638,)) == fpr.STALE_AFTER_HOURS * 3600
        assert (61461638, "Above 4.00 pp") in h.label_writes
        # The label arm is identity: it leads, the class row follows.
        assert h.fetched == ["KXPOKEMON-26SEPCELULTPR", "KXCOWAGE-2027"]

    @pytest.mark.asyncio
    async def test_rotation_skips_what_was_read_and_the_cap_takes_the_next(
        self, monkeypatch
    ):
        rows = [
            (80000000 + i, "kalshi", f"KXROT-{i}", 10, None, None) for i in range(5)
        ]
        h = _ReachHarness(label_rows=rows, skips={80000000, 80000002}, per_run=2)
        stats = await h.run(monkeypatch)

        assert h.fetched == ["KXROT-1", "KXROT-3"]
        assert stats["threshold_label_pool"] == 5
        assert stats["threshold_label_candidates"] == 2
        # Skips are looked up over the pool BEFORE the cap, so a skipped head
        # cannot starve the rows behind it.
        assert sorted(h.label_skip_asked) == [r[0] for r in rows]

    @pytest.mark.asyncio
    async def test_a_head_read_by_another_arm_does_not_spend_the_cap(
        self, monkeypatch
    ):
        """Production 2026-10-01: 60 candidates, 4 attempted, no budget hit.
        The head of the id order had been read by the class arm inside its 6h
        window, so `eligible` dropped it AFTER the cap — and with no label
        marker it was the head again next beat. The rotation never moved and
        60481264 (rank 729 of 932) settled still printing "Yes".
        """
        head = [
            (82000000 + i, "kalshi", f"KXHEAD-{i}", 20_000, None, None)
            for i in range(3)
        ]
        h = _ReachHarness(
            label_rows=head + [POKEMON_ROW, COWAGE_ROW],
            read_elsewhere={r[0] for r in head},
            per_run=2,
        )
        stats = await h.run(monkeypatch)

        assert h.fetched == ["KXPOKEMON-26SEPCELULTPR", "KXCOWAGE-2027"]
        assert stats["threshold_label_candidates"] == 2
        assert stats["threshold_label_attempted"] == 2
        assert stats["threshold_label_read_elsewhere"] == 3
        assert h.label_writes == [
            (60481264, "Above $1237.81"),
            (61461638, "Above 4.00 pp"),
        ]
        # The rows read elsewhere keep only their own marker: no label slot.
        assert sorted(h.label_marks) == [60481264, 61461638]

    @pytest.mark.asyncio
    async def test_read_elsewhere_counts_only_rows_not_already_label_skipped(
        self, monkeypatch
    ):
        rows = [
            (83000000 + i, "kalshi", f"KXBOTH-{i}", 10, None, None) for i in range(3)
        ]
        h = _ReachHarness(
            label_rows=rows,
            skips={83000000},
            read_elsewhere={83000000, 83000001},
        )
        stats = await h.run(monkeypatch)
        assert h.fetched == ["KXBOTH-2"]
        assert stats["threshold_label_read_elsewhere"] == 1

    @pytest.mark.asyncio
    async def test_a_pool_at_the_ceiling_says_so(self, monkeypatch):
        rows = [
            (81000000 + i, "kalshi", f"KXCAP-{i}", 10, None, None) for i in range(4)
        ]
        monkeypatch.setattr(fpr, "THRESHOLD_LABEL_SCAN_LIMIT", 3)
        h = _ReachHarness(label_rows=rows)
        stats = await h.run(monkeypatch)
        # `_scan_threshold_label_candidates` bound its default at import, so the
        # statement still ran at 3000 here; the flag reads the module constant.
        assert stats["threshold_label_pool"] == 4
        assert stats["threshold_label_pool_capped"] is True


class TestTheArmsBounds:
    def test_the_measured_population_is_read_inside_a_day(self):
        measured_pool = 963  # production 2026-09-30 03:5xZ, both specimens in it
        assert fpr.THRESHOLD_LABEL_RETRY_HOURS <= 24
        assert (
            fpr.THRESHOLD_LABEL_PER_RUN * fpr.THRESHOLD_LABEL_RETRY_HOURS
            >= measured_pool
        )
        assert fpr.THRESHOLD_LABEL_SCAN_LIMIT >= 3 * measured_pool

    def test_its_marker_cannot_veto_a_price_refresh(self):
        assert fpr._label_attempt_key(5) != fpr._attempt_key(5)
        assert not fpr._label_attempt_key(5).startswith(fpr._ATTEMPT_KEY_PREFIX)

    def test_the_statement_selects_the_stored_single_yes_shape(self):
        sql = " ".join(fpr._THRESHOLD_LABEL_CANDIDATE_SQL.text.split())
        assert "fm.source = 'kalshi'" in sql
        assert "->> 'threshold_label') IS NULL" in sql
        assert "fo_y.name = 'Yes'" in sql
        assert "fo_o.name <> 'Yes'" in sql
        assert "LIMIT :threshold_label_limit" in sql
