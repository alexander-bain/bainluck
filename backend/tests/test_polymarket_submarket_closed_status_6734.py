"""#6734 — a decomposed sub-market's status is the MARKET's, not its parent event's.

The rows written at the two sub-market sites in `_process_event_batch` are keyed
on `external_id=market.condition_id`: each one IS an individual Polymarket
market. Their `status` was nevertheless read off `event.active`, the parent's
flag, so a market the venue had closed under a still-trading event kept
`status='open'` and its last quote was served as live. The filed specimen is a
LIVE tennis page printing `Over 21.5 / 22.5 / 23.5` all at 51%, off three
different condition ids whose books Gamma answers "No orderbook exists".

The fixtures here are hand-built dicts rather than vendored venue bytes, and
they are driven through the REAL parsers (`_parse_event` / `_parse_market`) on
purpose: the load-bearing claim is that `closed` reaches the DTO from a
venue-shaped payload at all. A test that constructed `PolymarketMarket(...)`
directly, or duck-typed a stub, would pass just as happily if the parser dropped
the field — which is the only way this fix can silently do nothing.
"""

import re

import pytest

from app.services.polymarket_api import PolymarketAPIService
from app.tasks import polymarket as poly


def _market(*, closed: bool) -> dict:
    """Venue-shaped market payload. `closed` is the only field under test."""
    return {
        "id": "552111",
        "conditionId": "0x147f2e8b",
        "question": "Will the match go over 21.5 games?",
        "slug": "collins-cross-over-21-5",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.505", "0.495"]',
        "clobTokenIds": '["111", "222"]',
        "closed": closed,
        "bestBid": 0.50,
        "bestAsk": 0.51,
    }


def _event(*, active: bool, closed: bool, market_closed: bool) -> dict:
    return {
        "id": "27114",
        "title": "Collins vs Cross",
        "slug": "collins-cross",
        "active": active,
        "closed": closed,
        "markets": [_market(closed=market_closed)],
    }


def _parsed(*, active: bool, closed: bool, market_closed: bool):
    svc = PolymarketAPIService()
    event = svc._parse_event(
        _event(active=active, closed=closed, market_closed=market_closed)
    )
    assert event is not None, "the parser refused a venue-shaped payload"
    assert event.markets, "the parser dropped the nested market"
    return event, event.markets[0]


class TestTheFieldSurvivesTheRealParser:
    """If `closed` does not arrive, every other test here is vacuous."""

    def test_the_market_carries_the_venues_closed_flag(self):
        _, market = _parsed(active=True, closed=False, market_closed=True)
        assert market.closed is True

    def test_and_it_is_not_simply_always_true(self):
        _, market = _parsed(active=True, closed=False, market_closed=False)
        assert market.closed is False

    def test_the_event_carries_its_own_separately(self):
        event, _ = _parsed(active=True, closed=True, market_closed=False)
        assert event.active is True and event.closed is True


class TestSubmarketIsOpen:
    def test_a_market_closed_under_an_open_event_is_not_open(self):
        """The filed specimen: Over 21.5 settles mid-match, the match trades on."""
        event, market = _parsed(active=True, closed=False, market_closed=True)
        assert poly.submarket_is_open(event, market) is False

    def test_gammas_active_true_on_a_closed_event_does_not_keep_it_open(self):
        """`_process_event_batch` is fed by a `closed=True` sweep too.

        Gamma keeps `active=true` on a closed event — the reason
        `sunk_event_is_open` exists — so that whole population reached this
        writer and was stamped `open` on the parent's flag.
        """
        event, market = _parsed(active=True, closed=True, market_closed=False)
        assert poly.submarket_is_open(event, market) is False

    def test_an_open_market_under_an_open_event_is_open(self):
        """Non-vacuity: a predicate that always refused would pass every test above."""
        event, market = _parsed(active=True, closed=False, market_closed=False)
        assert poly.submarket_is_open(event, market) is True

    def test_it_never_un_resolves_a_row(self):
        """STRICTLY TIGHTENING, and the bound is deliberate.

        `status` gates `/api/futures/{categories,faceted,grouped-feed,movers}`,
        so a predicate that turned `resolved` back into `open` would push
        markets onto the feed and into Biggest Movers. The inverse defect —
        rows stamped `resolved` while the venue still trades them — is real,
        measured and filed separately; it is not smuggled in here. This test
        pins that non-coverage so widening it is a conscious act.
        """
        event, market = _parsed(active=False, closed=False, market_closed=False)
        assert poly.submarket_is_open(event, market) is False

    def test_a_caller_carrying_no_closed_field_keeps_the_old_behaviour(self):
        """The `getattr` default, same contract as `_is_reserved_slot`'s."""

        class _Bare:
            active = True

        assert poly.submarket_is_open(_Bare(), _Bare()) is True

    def test_it_is_pure(self):
        event, market = _parsed(active=True, closed=False, market_closed=True)
        before = (event.active, event.closed, market.closed)
        poly.submarket_is_open(event, market)
        assert (event.active, event.closed, market.closed) == before


class TestTheWriterActuallyAsksIt:
    """Source-level, because the alternative is standing up the whole writer.

    Comments are stripped first: a blunt substring test over source text cannot
    tell code from prose, and an explanatory comment naming `event.active` would
    otherwise satisfy — or break — these assertions for the wrong reason.
    """

    @staticmethod
    def _code() -> str:
        import inspect

        src = inspect.getsource(poly._process_event_batch)
        return "\n".join(line.split("#")[0] for line in src.splitlines())

    def test_the_submarket_sites_read_the_markets_own_flag(self):
        code = self._code()
        assert "sub_open = submarket_is_open(event, market)" in code
        assert len(re.findall(r'"open" if sub_open else "resolved"', code)) == 2, (
            "both the update set and the insert values must agree, or an upsert "
            "disagrees with itself about whether the leg still trades"
        )

    def test_settled_at_stays_coupled_to_the_same_value(self):
        """LINKLOSS-02: the stamp moves in the same statement as the status."""
        code = self._code()
        assert "None if sub_open" in code

    def test_no_status_site_anywhere_reads_the_events_raw_flag(self):
        """RE-AIMED, deliberately — this test used to assert the opposite.

        It previously pinned the parent's two sites at `event.active` on the
        reasoning "the parent row IS the event, so they are correct as they
        are". That premise was wrong, and this file's own
        `test_gammas_active_true_on_a_closed_event_does_not_keep_it_open`
        already said why: Gamma keeps `active=true` on a CLOSED event, so
        `event.active` alone is not "is this event open at the venue" on ANY
        row. Measured on production 2026-09-18: 842 parents sitting `open` with
        every outcome already graded, and 19 of a random 20 confirmed
        `closed=true, active=true` at Gamma itself.

        The parent half is `sunk_event_is_open`; the child half is
        `submarket_is_open`. Neither reads the raw flag now, and this pins that
        no site can drift back.
        """
        code = self._code()
        assert len(re.findall(r'"open" if event\.active else "resolved"', code)) == 0
        assert len(re.findall(r"None if event\.active", code)) == 0


@pytest.mark.parametrize(
    "active,ev_closed,mkt_closed,expected",
    [
        (True, False, False, "open"),
        (True, False, True, "resolved"),
        (True, True, False, "resolved"),
        (True, True, True, "resolved"),
        (False, False, False, "resolved"),
        (False, False, True, "resolved"),
        (False, True, False, "resolved"),
        (False, True, True, "resolved"),
    ],
)
def test_the_whole_truth_table(active, ev_closed, mkt_closed, expected):
    """All eight combinations, so the predicate's shape is pinned, not sampled."""
    event, market = _parsed(active=active, closed=ev_closed, market_closed=mkt_closed)
    status = "open" if poly.submarket_is_open(event, market) else "resolved"
    assert status == expected
