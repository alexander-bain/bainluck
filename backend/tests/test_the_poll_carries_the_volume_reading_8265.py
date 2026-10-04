"""#8265, second half: the 2-hourly Kalshi poll takes the venue's volume reading.

## what a reader saw

Discover page one, 2026-10-03 10:02Z: "2027 US Open Men's Singles Winner — Jakub
Mensik leads at 47%". Kalshi had no bid on any leg of that board and no leg had
traded in 24 hours. #8630's sixth arm exists to take every number off a board like
that, and it took none.

## why the arm withheld nothing

The arm only trusts a zero volume reading when it comes from our most recent write
of the row (``volume_24h_at >= last_updated``,
``futures_unsupported_price.venue_reports_no_recent_trading``). Production rows,
read 2026-10-03 15:43Z, all 25 legs of ``KXATP-27USO``:

    volume_24h 0.00   volume_24h_at 14:07:55.078Z   last_updated 15:07:37.854Z

``futures_markets.volume_updated_at`` for the board is also 15:07:37.854559Z, to the
microsecond, and only ``_poll_kalshi_markets`` writes that stamp. So the hourly price
refresh took a zero reading at 14:07, and the poll then re-touched every leg at 15:07
without taking one. Each leg then read as "never asked", which correctly fails open.
The poll runs every two hours and the refresh every hour, so on most reads the zero
was stale.

## the repair

The poll's own payload carries ``volume_24h_fp`` on every market, so the parser keeps
it un-floored (``KalshiMarket.volume_24h_reading``) and the poll writes it in the same
UPDATE that advances ``last_updated``. As in the refresh writer, a missing figure is
omitted and never written as NULL.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import datetime, timedelta, timezone

from app.services.kalshi_api import KalshiAPIService, venue_volume_24h
from app.tasks import futures_price_refresh
from app.tasks import kalshi as kalshi_mod
from app.utils.futures_unsupported_price import (
    leg_has_no_live_support,
    venue_reports_no_recent_trading,
)

#: The specimen leg as the venue listed it (``markets?event_ticker=KXATP-27USO``,
#: 2026-10-03 10:02Z): one-sided book, a seed ask, zero 24-hour volume. Only the
#: modern ``_fp`` volume form is present, which is the shape that made the legacy
#: ``volume_24h`` field useless for this question.
MENSIK_RAW = {
    "ticker": "KXATP-27USO-MEN",
    "event_ticker": "KXATP-27USO",
    "title": "Will Jakub Mensik win the 2027 US Open?",
    "status": "active",
    "yes_bid_dollars": "0.0000",
    "yes_ask_dollars": "0.4700",
    "last_price_dollars": "0.4700",
    "volume_fp": "203.00",
    "volume_24h_fp": "0.00",
}


def _parse(raw: dict):
    service = KalshiAPIService.__new__(KalshiAPIService)
    market = service._parse_market(raw)
    assert market is not None
    return market


# --------------------------------------------------------------------------
# the parser keeps the reading the poll needs
# --------------------------------------------------------------------------


def test_the_specimens_zero_survives_the_parse_as_a_zero():
    market = _parse(MENSIK_RAW)
    assert market.volume_24h_reading == 0.0
    # The legacy field turns that zero into None ("never asked"). That is why it
    # cannot answer this question, and why it is left alone for its own consumer.
    assert market.volume_24h is None


def test_a_sub_unit_trade_is_not_floored_to_untraded():
    market = _parse({**MENSIK_RAW, "volume_24h_fp": "0.04"})
    assert market.volume_24h_reading == 0.04
    # Floored to 0, then `0 or …` falls through to the absent legacy key.
    assert market.volume_24h is None


def test_an_absent_figure_is_none_not_zero():
    raw = {k: v for k, v in MENSIK_RAW.items() if k != "volume_24h_fp"}
    assert _parse(raw).volume_24h_reading is None


def test_the_legacy_integer_key_is_still_read():
    raw = {k: v for k, v in MENSIK_RAW.items() if k != "volume_24h_fp"}
    assert _parse({**raw, "volume_24h": 12}).volume_24h_reading == 12.0


def test_the_refresh_and_the_poll_read_volume_through_one_function():
    assert futures_price_refresh.venue_volume_24h is venue_volume_24h


# --------------------------------------------------------------------------
# the poll writes it beside the touch-stamp it advances
# --------------------------------------------------------------------------


def _poll_tree() -> ast.AST:
    return ast.parse(textwrap.dedent(inspect.getsource(kalshi_mod._poll_kalshi_markets)))


def _update_set_writes(tree: ast.AST) -> dict[str, list[ast.AST]]:
    """Every column the poll puts into ``update_set``, from both forms it uses."""
    writes: dict[str, list[ast.AST]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "update_set":
            if isinstance(node.value, ast.Dict):
                for key, value in zip(node.value.keys, node.value.values):
                    if isinstance(key, ast.Constant):
                        writes.setdefault(key.value, []).append(value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and getattr(target.value, "id", None) == "update_set"
                    and isinstance(target.slice, ast.Constant)
                ):
                    writes.setdefault(target.slice.value, []).append(node.value)
    return writes


def test_the_conflict_arm_stamps_the_reading_with_the_touch_stamp():
    writes = _update_set_writes(_poll_tree())
    # The bug's precondition: this arm advances the touch-stamp on every leg.
    assert "last_updated" in writes
    assert "volume_24h" in writes and "volume_24h_at" in writes
    (volume,) = writes["volume_24h"]
    assert ast.unparse(volume) == "market.volume_24h_reading"
    (stamp,) = writes["volume_24h_at"]
    assert ast.unparse(stamp) == "func.now()"
    # `last_updated` must use the SAME expression, or the consumer's `>=` stops
    # being exact.
    assert [ast.unparse(v) for v in writes["last_updated"]] == ["func.now()"]


def test_the_conflict_arm_omits_never_nulls_an_absent_reading():
    tree = _poll_tree()
    guards = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and ast.unparse(node.test) == "market.volume_24h_reading is not None"
    ]
    assert len(guards) == 1
    assigned = {
        target.slice.value
        for stmt in guards[0].body
        if isinstance(stmt, ast.Assign)
        for target in stmt.targets
        if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant)
    }
    assert assigned == {"volume_24h", "volume_24h_at"}
    assert not guards[0].orelse


def test_the_insert_arm_carries_the_reading_too():
    tree = _poll_tree()
    # The priced upsert, i.e. the insert whose conflict arm is `update_set`. The
    # unpriced placeholder insert (#3518) writes no price, so the arm never
    # reads its legs.
    upserts = [
        node.func.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "on_conflict_do_update"
        and isinstance(node.func.value, ast.Call)
        and "pg_insert(FuturesOutcome)" in ast.unparse(node.func.value.func)
    ]
    assert len(upserts) == 1
    kwargs = {kw.arg: ast.unparse(kw.value) for kw in upserts[0].keywords}
    assert kwargs["volume_24h"] == "market.volume_24h_reading"
    assert kwargs["volume_24h_at"] == (
        "func.now() if market.volume_24h_reading is not None else None"
    )


# --------------------------------------------------------------------------
# what that does to the specimen's arm
# --------------------------------------------------------------------------

POLL_AT = datetime(2026, 10, 3, 15, 7, 37, 854559, tzinfo=timezone.utc)
REFRESH_AT = datetime(2026, 10, 3, 14, 7, 55, 78206, tzinfo=timezone.utc)


def _mensik(volume_24h_at: datetime) -> bool:
    return leg_has_no_live_support(
        "kalshi",
        None,
        0.0,
        0.47,
        volume_24h=0.0,
        volume_24h_at=volume_24h_at,
        last_seen_at=POLL_AT,
    )


def test_before_the_stored_pair_reads_as_never_asked():
    """The production pair at 15:43Z: the arm treats Mensik as supported."""
    assert REFRESH_AT < POLL_AT
    assert not venue_reports_no_recent_trading(0.0, REFRESH_AT, POLL_AT)
    assert not _mensik(REFRESH_AT)


def test_after_the_poll_stamps_the_pair_and_the_arm_can_see_the_zero():
    """The poll writes both stamps from one ``func.now()``, so they are equal."""
    assert venue_reports_no_recent_trading(0.0, POLL_AT, POLL_AT)
    assert _mensik(POLL_AT)


def test_a_traded_leg_stamped_by_the_poll_is_still_supported():
    assert not venue_reports_no_recent_trading(3.24, POLL_AT, POLL_AT)
    assert not venue_reports_no_recent_trading(0.04, POLL_AT, POLL_AT)


def test_a_writer_that_skips_the_reading_still_fails_open():
    """Unchanged: a later touch without a reading leaves the leg served."""
    assert not _mensik(POLL_AT - timedelta(microseconds=1))
