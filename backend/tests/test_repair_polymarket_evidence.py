"""Behavioural guards for the Polymarket evidence rail (#1870, CAL-P060).

Deliberately NOT source-inspection tests. The function this rail replaces,
``_backfill_polymarket_volume``, was covered by
``test_backfill_volume_fn_shape``, which asserts that the strings ``"unnest"``,
``"429"`` and ``"bainluck:poly_volume_backfill"`` appear in its source. That
suite was green for the entire time the function had **no caller at all**, and
it could not have noticed that the function's ``order="volume"`` sorts
lexicographically or that its ``offset`` pager is capped 2,000 rows into a
cohort of tens of thousands. A test that reads source text can only ever
confirm that code was written.

So these drive the real callable against a fake venue and a fake session, and
assert on what it WRITES.
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks import repair_polymarket_evidence as rail
from app.utils.polymarket_evidence import PM_SWEEP_FLOOR, PMEvidence


class FakeResult:
    def __init__(self, rows=None, rowcount=0):
        self._rows = rows or []
        self.rowcount = rowcount

    def all(self):
        return self._rows


class FakeSession:
    """Records every statement and its params, so writes can be asserted."""

    def __init__(self, targets):
        self.targets = targets
        self.executed = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.executed.append((sql, params or {}))
        if "FROM futures_markets fm" in sql and "LIMIT :cap" in sql:
            return FakeResult(rows=self.targets)
        return FakeResult(rowcount=1)

    async def commit(self):
        self.commits += 1


def _target(mid=1, rd=date(2024, 6, 1), event_id="10446", cid="0xabc", n=2):
    return SimpleNamespace(
        market_id=mid, rd=rd, event_id=event_id, condition_id=cid, n_null_outcomes=n
    )


@pytest.fixture
def venue(monkeypatch):
    """Programmable fake venue: set .clob / .trades / .event_volumes."""
    state = SimpleNamespace(clob=200, trades=[], event_volumes={}, calls=[])

    async def fake_probe(client, condition_id):
        state.calls.append(("probe", condition_id))
        return state.clob, state.trades

    async def fake_event(client, event_id):
        state.calls.append(("event", event_id))
        return state.event_volumes

    monkeypatch.setattr(rail, "_probe_market", fake_probe)
    monkeypatch.setattr(rail, "_fetch_event_volumes", fake_event)
    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)
    return state


def _writes(session, table):
    return [(s, p) for s, p in session.executed if f"UPDATE {table}" in s]


class TestConfirmedZeroIsWritten:
    async def test_addressable_with_no_trades_writes_a_real_zero(self, venue):
        """The single row type Polymarket has never once produced.

        FAILS ON REVERT of the confirmed-zero write path.
        """
        venue.clob, venue.trades, venue.event_volumes = 200, [], {}
        s = FakeSession([_target()])

        out = await rail.repair(s, apply=True)

        assert out["counts"]["confirmed_zero"] == 1
        vol_writes = _writes(s, "futures_outcomes")
        assert len(vol_writes) == 1
        assert vol_writes[0][1]["vol"] == 0

    async def test_the_zero_carries_a_fetched_at_receipt(self, venue):
        """A 0 with no receipt is a bare value; the pair is the contract."""
        venue.clob, venue.trades = 200, []
        s = FakeSession([_target()])

        await rail.repair(s, apply=True)

        import json

        receipts = _writes(s, "futures_markets")
        assert len(receipts) == 1
        r = json.loads(receipts[0][1]["receipt"])
        assert r["verdict"] == "confirmed_zero"
        assert r["fetched_at"]
        assert r["n_trades"] == 0


class TestUnaddressableIsNeverCollapsedIntoZero:
    async def test_a_404_market_gets_no_volume_write_at_all(self, venue):
        """FAILS ON REVERT of the UNADDRESSABLE guard.

        This is gotcha #53's exact prohibition. A 0 here would assert, in the
        database, that the venue confirmed nobody traded a market the venue
        will not acknowledge exists.
        """
        venue.clob, venue.trades = 404, None
        s = FakeSession([_target()])

        out = await rail.repair(s, apply=True)

        assert out["counts"]["unaddressable"] == 1
        assert _writes(s, "futures_outcomes") == []

    async def test_but_it_does_get_a_receipt_saying_why(self, venue):
        """The NULL stays; what changes is that it becomes readable.

        Without this, an unaddressable NULL and a never-asked NULL are again
        indistinguishable — the whole defect, reintroduced one layer up.
        """
        venue.clob, venue.trades = 404, None
        s = FakeSession([_target()])

        await rail.repair(s, apply=True)

        import json

        r = json.loads(_writes(s, "futures_markets")[0][1]["receipt"])
        assert r["verdict"] == "unaddressable"
        assert "not zero" in r["reason"].lower()


class TestFailedProbesWriteNothing:
    @pytest.mark.parametrize("status", [429, 500, None])
    async def test_a_failed_probe_leaves_no_trace(self, venue, status):
        """Gotcha #36. An INDETERMINATE row must stay eligible for a retry, so
        it gets neither a value nor a receipt — a receipt would exclude it from
        the next sweep's WHERE clause forever."""
        venue.clob, venue.trades = status, None
        s = FakeSession([_target()])

        out = await rail.repair(s, apply=True)

        assert out["counts"]["indeterminate"] == 1
        assert _writes(s, "futures_outcomes") == []
        assert _writes(s, "futures_markets") == []

    async def test_an_all_indeterminate_pass_reports_success_false(self, venue):
        """"It returned" is not "it worked".

        The Kalshi trade backfill recorded a SUCCESS every 6h for ten weeks
        while recovering nothing, because zero yield and nothing-to-do produced
        the same result shape. This says it out loud.
        """
        venue.clob, venue.trades = 500, None
        s = FakeSession([_target(mid=1), _target(mid=2)])

        out = await rail.repair(s, apply=True)

        assert out["success"] is False
        assert "ZERO-YIELD" in out["verdict"]

    async def test_a_productive_pass_reports_success_true(self, venue):
        venue.clob, venue.trades = 200, []
        s = FakeSession([_target()])
        out = await rail.repair(s, apply=True)
        assert out["success"] is True
        assert "verdict" not in out


class TestTradedUsesAuthoritativeVolume:
    async def test_event_volume_is_preferred_over_a_trade_count(self, venue):
        """Trade pages truncate at 500; the event figure is the real number.

        Writing len(trades) into a column documented as lifetime volume would
        store a pagination artifact as a fact.
        """
        venue.clob, venue.trades = 200, [{"size": 1}] * 500
        venue.event_volumes = {"0xabc": 27843.64}
        s = FakeSession([_target(cid="0xabc")])

        out = await rail.repair(s, apply=True)

        assert out["counts"]["traded"] == 1
        assert _writes(s, "futures_outcomes")[0][1]["vol"] == 27843


class TestDryRunWritesNothing:
    async def test_apply_false_is_read_only(self, venue):
        venue.clob, venue.trades = 200, []
        s = FakeSession([_target()])

        out = await rail.repair(s, apply=False)

        assert out["applied"] is False
        assert out["counts"]["confirmed_zero"] == 1
        assert s.executed[1:] == []  # only the SELECT ran
        assert s.commits == 0


class TestOrderingAndFloor:
    """gotcha #41 / CAL-P009: a sweep over a possibly-expiring population needs
    BOTH bounds. Each half is asserted separately, because each half alone has
    already caused a named failure in this repository."""

    async def test_ordering_is_oldest_first(self, venue):
        s = FakeSession([_target()])
        await rail.repair(s, apply=False)
        sql = s.executed[0][0]
        assert "ORDER BY fm.resolution_date ASC" in sql

    async def test_the_dead_cohort_is_excluded_by_a_floor(self, venue):
        """Oldest-first WITHOUT a floor is the CAL-P009 failure exactly: the
        ~999 permanently-unaddressable rows sort first and would consume every
        run forever, so the recoverable edge is never reached."""
        s = FakeSession([_target()])
        await rail.repair(s, apply=False)
        sql, params = s.executed[0]
        assert "fm.resolution_date > CAST(:floor AS date)" in sql
        assert params["floor"] == PM_SWEEP_FLOOR.isoformat()

    async def test_paging_is_a_keyset_never_an_offset(self, venue):
        """C-CERT-1852's finding, applied at staging rather than after a
        certification round: this repair removes rows from its own population,
        so an offset skips as many untouched rows as the last page fixed."""
        s = FakeSession([_target()])
        await rail.repair(s, apply=False, after_date="2024-06-01", after_id=7)
        sql, params = s.executed[0]
        assert "(fm.resolution_date, fm.id) > (CAST(:after_date AS date), :after_id)" in sql
        assert "OFFSET" not in sql.upper()
        assert params["after_id"] == 7

    async def test_next_cursor_is_returned_for_resumption(self, venue):
        venue.clob, venue.trades = 200, []
        s = FakeSession([_target(mid=42, rd=date(2024, 6, 1))])
        out = await rail.repair(s, apply=False)
        assert out["next_cursor"] == {"after_date": "2024-06-01", "after_id": 42}

    async def test_already_probed_markets_are_not_re_probed(self, venue):
        """The receipt is also the sweep's idempotence key."""
        s = FakeSession([_target()])
        await rail.repair(s, apply=False)
        assert "NOT (fm.market_metadata ? 'volume_evidence')" in s.executed[0][0]


class TestBoundedness:
    async def test_the_cap_cannot_be_raised_by_a_caller(self, venue):
        """APPLY_MARKET_CAP is a ceiling, not a default: the operator
        re-invokes with the cursor, the operator does not widen the pass."""
        s = FakeSession([_target()])
        out = await rail.repair(s, apply=False, limit=100_000)
        assert out["cap"] == rail.APPLY_MARKET_CAP

    async def test_the_deadline_stops_the_pass_and_says_where(self, venue, monkeypatch):
        monkeypatch.setattr(rail, "DEADLINE_SECONDS", -1)
        s = FakeSession([_target(mid=5)])
        out = await rail.repair(s, apply=False)
        assert out["stopped_before"] == "market_id=5"
        assert out["counts"]["markets_examined"] == 0
