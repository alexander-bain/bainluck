"""#5661 — the fast lane must not re-date a price nobody re-read.

Production 2026-09-26 14:24Z, Slovenia v Scotland (event 15290677): the
moneyline's Polymarket rows were last written 13:28Z, Gamma traded Slovenia at
0.225, and the served `polymarket` leg read 0.405 stamped 14:24:35Z — re-stamped
every ~45s by `LiveBlendRefresher` because the event's OTHER books kept ticking.
The fixtures below are that specimen's numbers.

Two layers: the pure rule (`restamp_records_no_observation`), and the batch
proving the rule is actually CONSULTED before the stamp, the chart point and the
frame — a correct helper nothing calls is the disconnected-feature failure
`TestTheFastLaneActuallyCallsTheSnapshot` exists for one module over.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks.live_blend_refresh import (
    LiveBlendRefresher,
    restamp_records_no_observation,
)

FROZEN_ROW = datetime(2026, 9, 26, 13, 27, 51, tzinfo=timezone.utc)
FORGED_STAMP = "2026-09-26T14:24:35.290484+00:00"
REREAD_ROW = datetime(2026, 9, 26, 14, 25, 10, tzinfo=timezone.utc)


def _stored(value=0.405, updated_at=FORGED_STAMP):
    return {"polymarket": {"value": value, "updated_at": updated_at}}


class TestTheRule:
    def test_the_specimen_an_unchanged_price_from_rows_older_than_its_stamp(self):
        assert restamp_records_no_observation(0.405, FROZEN_ROW, _stored(), "polymarket")

    def test_rows_re_read_after_the_stamp_may_be_re_stamped(self):
        """A quiet-but-healthy book: the socket or the poll touched the rows."""
        assert not restamp_records_no_observation(
            0.405, REREAD_ROW, _stored(), "polymarket"
        )

    def test_a_moved_value_is_never_refused(self):
        """Every real move keeps #837's database clock."""
        assert not restamp_records_no_observation(
            0.225, FROZEN_ROW, _stored(), "polymarket"
        )

    def test_the_stored_value_is_compared_at_the_written_precision(self):
        assert restamp_records_no_observation(
            0.405, FROZEN_ROW, _stored(value=0.40500001), "polymarket"
        )

    def test_equal_instants_are_not_a_re_observation(self):
        """The 120s poll stamps the rows' own observation time, so its stamp and
        the rows it just touched are EQUAL; re-stamping that adds nothing."""
        stamp = REREAD_ROW.isoformat()
        assert restamp_records_no_observation(
            0.405, REREAD_ROW, _stored(updated_at=stamp), "polymarket"
        )

    @pytest.mark.parametrize(
        "observed, sources",
        [
            (None, _stored()),  # a contributor that cannot say when it was seen
            (FROZEN_ROW, {}),  # nothing stored for this source
            (FROZEN_ROW, {"polymarket": 0.405}),  # legacy bare float: no stamp
            (FROZEN_ROW, _stored(updated_at="not a time")),
            (FROZEN_ROW, None),  # SQL NULL column
            (FROZEN_ROW, ["polymarket"]),  # a column that is not an object
        ],
    )
    def test_it_abstains_when_it_cannot_know(self, observed, sources):
        """Unknown is not stale: abstaining is today's behaviour, unchanged."""
        assert not restamp_records_no_observation(0.405, observed, sources, "polymarket")

    def test_it_reads_only_its_own_source_key(self):
        sources = {"kalshi": {"value": 0.405, "updated_at": FORGED_STAMP}}
        assert not restamp_records_no_observation(0.405, FROZEN_ROW, sources, "polymarket")


class _Session:
    def __init__(self, market_rows):
        self._market_rows = market_rows
        self._selects = 0
        self.updates = []

    async def execute(self, statement, *args, **kwargs):
        from sqlalchemy.sql.dml import Update

        if isinstance(statement, Update):
            self.updates.append(statement)
            return SimpleNamespace(
                scalar_one_or_none=lambda: {
                    "polymarket": {"value": 0.405, "updated_at": FORGED_STAMP}
                }
            )
        if hasattr(statement, "text"):  # SET lock_timeout
            return SimpleNamespace()
        self._selects += 1
        rows = self._market_rows if self._selects == 1 else []
        return SimpleNamespace(all=lambda: rows, scalars=lambda: iter(rows))

    def add(self, row):
        pass

    def begin_nested(self):
        class _Savepoint:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *exc):
                return False

        return _Savepoint()

    async def flush(self):
        pass


def _refresher(monkeypatch, *, sources, home_probability, outcomes):
    event = SimpleNamespace(
        id=15290677, home_team_name="Slovenia", away_team_name="Scotland",
        completed_at=None, status="live", espn_win_prob_home=None,
        opening_home_probability=None, win_probability_sources=sources,
    )
    market = SimpleNamespace(id=60933571, event_id=event.id, name="Slovenia vs. Scotland")
    session = _Session([(market, event)])

    @asynccontextmanager
    async def _fake_session():
        yield session

    monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
    monkeypatch.setattr(
        "app.utils.live_blend.compute_source_home_probability",
        lambda group, home, away: SimpleNamespace(
            home_probability=home_probability, away_probability=None,
            draw_probability=None, eligibility=None, market=market,
            outcome=outcomes[0], contributing_outcomes=tuple(outcomes),
            yes_probability=home_probability,
        ),
    )

    async def _no_inversion(session, event_id, home_prob, source):
        return home_prob

    monkeypatch.setattr(
        "app.tasks.prediction_market_matching._check_and_fix_inversion", _no_inversion
    )
    snapshots = []

    async def _spy_snapshot(session, **kwargs):
        snapshots.append(kwargs)
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", _spy_snapshot
    )
    published = []

    async def _capture(frames):
        published.extend(frames)

    r = LiveBlendRefresher("polymarket")
    monkeypatch.setattr(r, "_publish", _capture)
    return r, session, snapshots, published


def _row(at):
    return SimpleNamespace(name="Slovenia", last_updated=at)


class TestTheBatchConsultsTheRule:
    @pytest.mark.asyncio
    async def test_the_specimen_writes_no_stamp_no_chart_point_and_no_frame(
        self, monkeypatch
    ):
        """A FRESH refresher: a dyno restart empties `_last_written_value`, and
        `_should_write` then says "first value, write it" — so the rule must
        read the ROW's stored entry, not this process's memory."""
        r, session, snapshots, published = _refresher(
            monkeypatch, sources=_stored(), home_probability=0.405,
            outcomes=[_row(FROZEN_ROW)],
        )

        stats = await r.refresh([15290677])

        assert session.updates == [], "re-dated a price nobody re-read"
        assert snapshots == [], "drew a fresh chart point for a frozen price"
        assert published == []
        assert stats["unobserved_skipped"] == 1 and stats["stamped"] == 0
        assert r._dispositions[15290677] == ("unobserved", 0.405)
        assert stats["errors"] == 0

    @pytest.mark.asyncio
    async def test_the_same_price_from_re_read_rows_is_stamped(self, monkeypatch):
        """The strawman's other arm: without it, a lane that stamped nothing
        at all would pass the test above."""
        r, session, snapshots, published = _refresher(
            monkeypatch, sources=_stored(), home_probability=0.405,
            outcomes=[_row(REREAD_ROW)],
        )

        stats = await r.refresh([15290677])

        assert len(session.updates) == 1
        assert stats["stamped"] == 1 and stats["unobserved_skipped"] == 0
        assert [f["event_id"] for f in published] == [15290677]

    @pytest.mark.asyncio
    async def test_a_moved_price_is_stamped_even_from_old_rows(self, monkeypatch):
        r, session, _snapshots, published = _refresher(
            monkeypatch, sources=_stored(), home_probability=0.225,
            outcomes=[_row(FROZEN_ROW)],
        )

        stats = await r.refresh([15290677])

        assert len(session.updates) == 1 and stats["stamped"] == 1
        assert published

    @pytest.mark.asyncio
    async def test_a_devig_is_as_fresh_as_its_stalest_contributor(self, monkeypatch):
        """One sub-market re-read, its sibling frozen: the composite was not
        re-observed, so it is not re-dated (`oldest_observation_time`)."""
        r, session, _snapshots, _published = _refresher(
            monkeypatch, sources=_stored(), home_probability=0.405,
            outcomes=[_row(REREAD_ROW), _row(FROZEN_ROW)],
        )

        stats = await r.refresh([15290677])

        assert session.updates == [] and stats["unobserved_skipped"] == 1

    @pytest.mark.asyncio
    async def test_a_reading_that_cannot_date_its_rows_keeps_todays_behaviour(
        self, monkeypatch
    ):
        r, session, _snapshots, _published = _refresher(
            monkeypatch, sources=_stored(), home_probability=0.405,
            outcomes=[SimpleNamespace(name="Slovenia", last_updated=None)],
        )

        stats = await r.refresh([15290677])

        assert len(session.updates) == 1 and stats["unobserved_skipped"] == 0


def test_both_socket_log_lines_report_the_counter():
    """Gotcha #53: a refusal nobody counts reads exactly like a quiet market."""
    import inspect

    from app.tasks import kalshi_ws, polymarket_ws

    for module in (kalshi_ws, polymarket_ws):
        source = inspect.getsource(module)
        assert 'blend.get("unobserved_skipped", 0)' in source, module.__name__
        assert "unobserved=%d" in source, module.__name__
