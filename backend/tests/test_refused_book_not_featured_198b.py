"""Ruling 198-B (Alex, Nov 15 2026): a thinly traded market keeps its number on its
own page, with "As of", and is never featured on Discover. No blanking.

"Thinly traded" here is the price writer's own judgement: the venue is quoting
the market (a real bid or a trade on an open leg) and we refused every leg's book
as too wide. Two such reads in a row stamp the market; the first accepted price,
from the 15-minute refresh or the hourly poll, clears it. Discover's candidate
pool skips a stamped market; category pages and the market's own page do not.

Every "refused" specimen asserts the resolver really refuses it first, so a test
cannot pass on a branch it never entered.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.routes.feed import _discover_candidate_pool_specs
from app.tasks import futures_price_refresh as fpr
from app.utils.futures_liveness import (
    BOOK_REFUSED_FIRST_KEY,
    BOOK_REFUSED_KEY,
    CARRIED_METADATA_KEYS,
    CLEAR_BOOK_REFUSED_SQL,
    STAMP_BOOK_REFUSED_SQL,
)
from tests.test_futures_price_refresh_retires_unpriced_4000 import (
    _FakePolyService,
    _Result,
    _RetirementHarness,
    _dead_leg,
    _field,
    _leg,
    _priced_leg,
    _resolves_to_nothing,
)

NOW = datetime(2026, 11, 15, 17, 0, tzinfo=timezone.utc)


def _quoted_but_refused(cid="0xwide"):
    """A live two-sided book the resolver refuses (bid 0.11 / ask 1.0, no trade)."""
    return _leg(cid, yes=None, bid=0.11, ask=1.0, last=None)


def _traded_but_refused(cid="0xtraded"):
    return _leg(cid, yes=0.5, bid=0.0, ask=1.0, last=0.53)


async def _refused_set(*events):
    out: set = set()
    priced, _ = await fpr._fetch_polymarket_prices(
        _FakePolyService(*events), [e.id for e in events], {}, book_refused_out=out
    )
    return out, priced


@pytest.mark.asyncio
class TestWhichReadsCountAsARefusedBook:
    async def test_a_single_market_with_a_bid_we_refuse_counts(self):
        leg = _quoted_but_refused()
        assert _resolves_to_nothing(leg)
        out, priced = await _refused_set(_field("e1", [leg], neg_risk=False))
        assert out == {"e1"} and "e1" not in priced

    async def test_a_single_market_that_has_traded_counts(self):
        leg = _traded_but_refused()
        assert _resolves_to_nothing(leg)
        out, _ = await _refused_set(_field("e1", [leg], neg_risk=False))
        assert out == {"e1"}

    async def test_a_market_nobody_quotes_is_not_this_rule(self):
        # No bid and no trade: "nobody is trading" is #12765's rule, not 198-B's.
        leg = _dead_leg("0xdead")
        assert _resolves_to_nothing(leg)
        out, _ = await _refused_set(_field("e1", [leg], neg_risk=False))
        assert out == set()

    async def test_a_market_we_price_is_not_refused(self):
        out, priced = await _refused_set(
            _field("e1", [_priced_leg("0xok", 0.42)], neg_risk=False)
        )
        assert out == set() and priced.get("e1")

    async def test_a_field_with_one_priced_leg_is_not_refused(self):
        # The leaders priced; a refused tail leg is a page matter, not featuring.
        out, _ = await _refused_set(
            _field("e1", [_priced_leg("0xlead", 0.6), _quoted_but_refused("0xtail")])
        )
        assert out == set()

    async def test_a_field_where_every_quoted_leg_is_refused_counts(self):
        out, _ = await _refused_set(
            _field("e1", [_quoted_but_refused("0xa"), _traded_but_refused("0xb")])
        )
        assert out == {"e1"}

    async def test_a_venue_closed_market_is_the_settled_rule_not_this_one(self):
        out, priced = await _refused_set(
            _field("e1", [_quoted_but_refused()], neg_risk=False, closed=True)
        )
        assert out == set() and priced["e1"] is fpr.VENUE_SETTLED

    async def test_the_out_parameter_is_optional(self):
        # Every existing caller keeps its two-tuple and passes nothing.
        priced, _ = await fpr._fetch_polymarket_prices(
            _FakePolyService(_field("e1", [_quoted_but_refused()], neg_risk=False)),
            ["e1"],
            {},
        )
        assert "e1" not in priced


class _StampHarness(_RetirementHarness):
    """The real refresh entry point; records the 198-B statements it issues."""

    def __init__(self, event, *, stamped_ids=(), confirm=False):
        super().__init__(event)
        self.stamped_ids = list(stamped_ids)
        self.confirm = confirm
        self.stamps: list[dict] = []
        self.clears: list[dict] = []
        outer = self
        base = self._Session

        class _Session(base):
            async def execute(self, statement, params=None):
                sql = str(statement)
                if "WHERE id = ANY(:ids)" in sql and BOOK_REFUSED_KEY in sql:
                    return _Result([(i,) for i in outer.stamped_ids if i in params["ids"]])
                if sql == STAMP_BOOK_REFUSED_SQL:
                    outer.stamps.append(dict(params))
                    return _Result([(outer.confirm,)])
                if sql == CLEAR_BOOK_REFUSED_SQL:
                    outer.clears.append(dict(params))
                    return _Result(rowcount=1)
                return await super().execute(statement, params)

        self._Session = _Session


MID = _RetirementHarness.CLASS_ROWS[0][0]


@pytest.mark.asyncio
class TestTheRefreshStampsAndClears:
    async def test_a_refused_read_stamps_the_market(self, monkeypatch):
        h = _StampHarness(_field("31552", [_quoted_but_refused()], neg_risk=False))
        summary = await h.run(monkeypatch)
        assert [s["mid"] for s in h.stamps] == [MID]
        assert summary["book_refused_first"] == 1
        assert "book_refused_confirmed" not in summary
        # one run's own first stamp cannot confirm: the guard is the run start
        assert isinstance(h.stamps[0]["run_started"], datetime)
        assert h.stamps[0]["run_started"].tzinfo is None
        assert h.clears == []

    async def test_a_second_refused_read_reports_confirmed(self, monkeypatch):
        h = _StampHarness(
            _field("31552", [_quoted_but_refused()], neg_risk=False), confirm=True
        )
        summary = await h.run(monkeypatch)
        assert summary["book_refused_confirmed"] == 1

    async def test_an_accepted_price_clears_a_stamped_market(self, monkeypatch):
        h = _StampHarness(
            _field("31552", [_priced_leg("0xvance", 0.24), _priced_leg("0xaoc", 0.08)]),
            stamped_ids=[MID],
        )
        summary = await h.run(monkeypatch)
        assert [c["mid"] for c in h.clears] == [MID]
        assert summary["book_refused_cleared"] == 1
        assert h.stamps == []

    async def test_an_unstamped_priced_market_issues_no_clear(self, monkeypatch):
        h = _StampHarness(
            _field("31552", [_priced_leg("0xvance", 0.24), _priced_leg("0xaoc", 0.08)])
        )
        await h.run(monkeypatch)
        assert h.clears == []

    async def test_a_market_nobody_quotes_is_not_stamped(self, monkeypatch):
        h = _StampHarness(_field("31552", [_dead_leg("0xdead")], neg_risk=False))
        await h.run(monkeypatch)
        assert h.stamps == []


def _sql(clauses):
    return " AND ".join(
        str(c.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        for c in clauses
    )


def test_discover_skips_a_confirmed_refused_book_market():
    id_filters, _ = _discover_candidate_pool_specs(now=NOW)
    sql = _sql(id_filters)
    assert BOOK_REFUSED_KEY in sql
    # only the CONFIRMED stamp; one refused read does not take a market off
    assert BOOK_REFUSED_FIRST_KEY not in sql


def test_category_pages_keep_the_market():
    id_filters, _ = _discover_candidate_pool_specs(now=NOW, category_filter="politics")
    assert BOOK_REFUSED_KEY not in _sql(id_filters)


def test_the_hourly_poll_carries_both_stamps_across_its_metadata_replace():
    assert BOOK_REFUSED_FIRST_KEY in CARRIED_METADATA_KEYS
    assert BOOK_REFUSED_KEY in CARRIED_METADATA_KEYS


def test_the_poll_clears_with_the_same_statement_as_the_refresh():
    import inspect

    from app.tasks import polymarket

    src = inspect.getsource(polymarket._process_event_batch)
    assert "text(CLEAR_BOOK_REFUSED_SQL).bindparams(mid=futures_market_id)" in src
    assert polymarket.CLEAR_BOOK_REFUSED_SQL is CLEAR_BOOK_REFUSED_SQL


def test_the_stamp_is_scoped_to_open_polymarket_markets():
    assert "source = 'polymarket'" in STAMP_BOOK_REFUSED_SQL
    assert "status = 'open'" in STAMP_BOOK_REFUSED_SQL
    assert ":run_started" in STAMP_BOOK_REFUSED_SQL
