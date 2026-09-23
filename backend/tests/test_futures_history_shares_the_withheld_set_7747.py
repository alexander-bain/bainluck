"""#7747 (with #7537 / #7586) — `/history` is gated on the DETAIL's WHOLE
withheld set, not on one arm of it.

`02bc1545` gated the chart's squeeze on `_unsupported_price_outcome_ids` — ONE
of the five arms `_withheld_price_outcome_ids` (#6993) unions for the page.
The Polymarket refuted-midpoint arm (#5876), the book-refuted arm (#6532), the
source-agnostic empty-book arm (#6757) and the unlocated-in-broken-field arm
(#7059) were not consulted. So on a board one of THOSE withholds, the page
prints RAW (`field_complete=False`) while the chart still squeezes: the #7747
two-scale defect, re-entering through four doors the fix's own comment said
were closed ("the same set from the same two calls the serializer makes" —
the serializer makes five).

The specimen is constructed rather than read off production, because the
class is defined by a composition: a leg one of the four other arms withholds
AND a field sum inside the squeeze band. A Polymarket one-winner board with
three honest legs and one EMPTY-BOOK leg (`0.02 / 0.97` around a stored 0.495,
the #6757 "Steph Curry Next Team" shape) sums to 1.295; the page withholds the
empty-book leg and prints leg A at 0.40, the base chart squeezes by 1.295 and
draws it at 0.309.

Base/candidate: `test_the_chart_prints_the_page_scale_when_another_arm_withheld`
fails on master `83a20bc7` and passes with the route change; every other test
here passes on both (a control that failed on base would not be a control).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.models import FuturesMarket, FuturesOddsSnapshot
from app.routes import futures as futures_route

T0 = datetime(2026, 9, 22, 3, 50, 54, 864277, tzinfo=timezone.utc)

MENSIK, SINNER, ALCARAZ, RUUD = 230781795, 230781778, 230781780, 230781797

_FIELD = {
    MENSIK: 0.740, SINNER: 0.315, ALCARAZ: 0.270, RUUD: 0.030,
    230781779: 0.010, 230781785: 0.010, 230781796: 0.010, 230781798: 0.010,
    230781802: 0.010, 230781782: 0.010, 230781783: 0.010, 230781784: 0.010,
    230781786: 0.010, 230781787: 0.010, 230781788: 0.010, 230781789: 0.010,
    230781790: 0.010, 230781791: 0.010, 230781792: 0.010, 230781793: 0.010,
    230781799: 0.010, 230781801: 0.010, 230781781: 0.010, 230781794: 0.010,
}

#: What the page prints for the priced legs once Mensik is withheld (raw: the
#: survivors sum to 0.815, under the squeeze's own floor).
_HERO = {SINNER: 0.315, ALCARAZ: 0.270, RUUD: 0.030}


class _Result:
    def __init__(self, value=None, rows=()):
        self._value = value
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def unique(self):
        return self


class _Session:
    """Answers each ``execute`` BY STATEMENT SHAPE rather than by call order.

    The route under test makes a variable number of reads before the snapshot
    query — zero, one or two trade reads depending on which arms find a
    candidate — and the candidate makes one more than the base on a Polymarket
    board. A queue-ordered stub would hand the snapshot rows to the wrong read
    on one side of the comparison and prove nothing. Shape is unambiguous:

      select(FuturesMarket)            -> the market
      select(FuturesOddsSnapshot)      -> the snapshot rows (the chart's read)
      select(<columns>)                -> the trade read: `trade_rows`
    """

    def __init__(self, market, snapshot_rows, trade_rows=()):
        self._market = market
        self._snapshots = list(snapshot_rows)
        self._trades = list(trade_rows)
        self.trade_reads = 0

    async def execute(self, statement):
        desc = statement.column_descriptions[0]
        if desc["expr"] is FuturesMarket:
            return _Result(value=self._market)
        if desc["expr"] is FuturesOddsSnapshot:
            return _Result(rows=self._snapshots)
        self.trade_reads += 1
        return _Result(rows=self._trades)


def _outcome(oid, prob, *, bid=None, ask=None, last_updated, source_prefix="KX",
             volume_24h=None, volume_24h_at=None):
    return SimpleNamespace(
        id=oid,
        name=f"Leg {oid}",
        team_id=None,
        probability_change_24h=None,
        current_probability=prob,
        current_yes_bid=prob if bid is None else bid,
        current_yes_ask=prob if ask is None else ask,
        resolution_source=None,
        is_winner=None,
        last_updated=last_updated,
        external_id=f"{source_prefix}-{oid}",
        volume_24h=volume_24h,
        volume_24h_at=volume_24h_at,
    )


def _market(outcomes, *, source, market_id=61308736, status="open"):
    return SimpleNamespace(
        id=market_id,
        name="2027 US Open Men's Singles Winner",
        source=source,
        market_type="field",
        external_id="KXATP-27USO-MEN",
        status=status,
        mutually_exclusive=True,
        outcomes=outcomes,
        resolution_date=None,
        group_type="negrisk" if source == "polymarket" else "kalshi_event",
        market_metadata={
            "shape": {
                "shape": "field",
                "exhaustive": True,
                "expected_winners": 1,
                "outcome_relation": "competitors",
                "confidence": "high",
            },
            "kalshi_event_ticker": "KXATP-27USO-MEN",
        },
    )


def _snaps(field, bookmaker, stamps):
    return [
        SimpleNamespace(
            outcome_id=oid,
            bookmaker=bookmaker,
            probability=field[oid],
            yes_bid=field[oid],
            yes_ask=field[oid],
            last_price=field[oid],
            captured_at=stamp,
        )
        for stamp in stamps
        for oid in field
    ]


async def _history(market, snapshot_rows, trade_rows=()):
    """Serve `/history` over the shape-keyed stub; return the payload + session."""
    db = _Session(market, snapshot_rows, trade_rows)
    payload = await futures_route.get_futures_history(
        market.id,
        outcome_id=None,
        hours=168,
        top_n=50,
        champion=None,
        db=db,
    )
    return payload, db


def _last_values(payload):
    return {
        entry["outcome_id"]: entry["history"][-1]["probability"]
        for entry in payload["outcomes"]
        if entry["history"]
    }


def _stamps():
    return [datetime.now(timezone.utc) - timedelta(hours=h) for h in (3, 2, 1)]


# ─────────────────────────────────────────────────────────────────────────────
# 1. THE SET — the chart is gated on the page's whole union, not one arm of it.
# ─────────────────────────────────────────────────────────────────────────────

#: A Polymarket one-winner board: three honest legs plus one EMPTY-BOOK leg —
#: `0.02 / 0.97` around a stored 0.495, the #6757 shape ("Steph Curry Next Team"
#: sixteen clubs at 48%). Sum 1.295, inside the squeeze band; without the
#: refused leg the survivors sum to 0.80, under it.
_PM_A, _PM_B, _PM_C, _PM_EMPTY = 910001, 910002, 910003, 910004
_PM_FIELD = {_PM_A: 0.40, _PM_B: 0.30, _PM_C: 0.10, _PM_EMPTY: 0.495}


def _polymarket_board(*, empty_book: bool):
    fresh = datetime.now(timezone.utc) - timedelta(minutes=5)
    if empty_book:
        book = {"bid": 0.02, "ask": 0.97}
    else:
        book = {"bid": 0.49, "ask": 0.50}  # a genuine, tightly-bounded 49.5%
    outcomes = [
        _outcome(_PM_A, 0.40, bid=0.39, ask=0.41, last_updated=fresh, source_prefix="PM"),
        _outcome(_PM_B, 0.30, bid=0.29, ask=0.31, last_updated=fresh, source_prefix="PM"),
        _outcome(_PM_C, 0.10, bid=0.09, ask=0.11, last_updated=fresh, source_prefix="PM"),
        _outcome(_PM_EMPTY, 0.495, last_updated=fresh, source_prefix="PM", **book),
    ]
    return _market(outcomes, source="polymarket", market_id=910000)


class TestTheWholeWithheldSetGatesTheChart:
    @pytest.mark.asyncio
    async def test_the_page_withholds_the_empty_book_leg(self):
        """The premise, stated as a fact about the page's own helper: this leg
        IS in the set `/api/futures/{id}` hands `_format_market_detail`, and it
        got there through an arm that is not the Kalshi trade screen."""
        market = _polymarket_board(empty_book=True)
        db = _Session(market, [])
        page_set = await futures_route._withheld_price_outcome_ids(db, market)
        one_arm = await futures_route._unsupported_price_outcome_ids(db, market)
        assert _PM_EMPTY in page_set
        assert one_arm == set(), "the single arm the chart used to consult sees nothing here"

    @pytest.mark.asyncio
    async def test_the_chart_prints_the_page_scale_when_another_arm_withheld(self):
        """Base: the chart consults one arm, finds nothing, squeezes by 1.295 and
        draws leg A at 0.309 under a page printing 0.40. Candidate: 0.40."""
        market = _polymarket_board(empty_book=True)
        payload, _ = await _history(market, _snaps(_PM_FIELD, "polymarket", _stamps()))
        last = _last_values(payload)
        assert last[_PM_A] == pytest.approx(0.40, abs=5e-4), (
            f"chart draws leg A at {last[_PM_A]:.4f} while the page prints 0.40 — "
            "the chart is gated on one arm of the withheld set, not the union (#7747)"
        )
        assert last[_PM_B] == pytest.approx(0.30, abs=5e-4)
        assert last[_PM_C] == pytest.approx(0.10, abs=5e-4)


class TestTheWholeWithheldSetControl:
    @pytest.mark.asyncio
    async def test_a_board_nothing_withholds_is_still_squeezed(self):
        """Same board, the fourth leg on a real tight book: no arm withholds,
        the field is complete, and the squeeze fires on both surfaces."""
        market = _polymarket_board(empty_book=False)
        page_set = await futures_route._withheld_price_outcome_ids(_Session(market, []), market)
        assert page_set == set()
        payload, _ = await _history(market, _snaps(_PM_FIELD, "polymarket", _stamps()))
        last = _last_values(payload)
        assert sum(last.values()) == pytest.approx(1.0, abs=0.01)
        assert last[_PM_A] == pytest.approx(0.40 / 1.295, abs=1e-3)
