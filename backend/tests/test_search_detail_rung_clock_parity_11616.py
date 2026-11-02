"""#11616 F1: search and detail drop an expired ladder rung at the same instant.

lane1b's interim review of 0e5d583a (probe P1c) found search's representation
reading MIDNIGHT UTC while detail read the real instant. A rung dated ``D``
expires at ``D+1 11:59:59Z`` (deadline ``D 23:59:59Z`` + ``RUNG_GRACE_DAYS``
0.5), so for the twelve hours from 12:00Z detail had dropped yesterday's rung
and search still drew it; on an exclusive board the remaining field then
normalized differently — 44/28/20 on search against 48/30/22 on detail.

The parity suite pins ``STAMP`` at 06:40Z, the half of the day where both clocks
agree, which is why it stayed green. Here the same board is read at both halves,
at the exact grace boundary, and across a whole-day sweep of clocks (gotcha #44:
every anchor is a fixed instant, no branch on the real clock).
"""

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.routes import events, futures

EXPIRED = "October 26"
#: ``October 26`` 23:59:59Z + 0.5 d: the first instant its rung is spent.
EXPIRES_AT = datetime(2026, 10, 27, 11, 59, 59, tzinfo=timezone.utc)


def _leg(i, name, p, *, last):
    return SimpleNamespace(
        id=i, name=name, external_id=f"F1-{i}", current_probability=p,
        current_yes_bid=max(0, p - 0.01), current_yes_ask=min(1, p + 0.01),
        current_american_odds=None, rank=i, rank_change_24h=None,
        probability_change_24h=None, opening_probability=None,
        opening_american_odds=None, is_winner=None, resolution_source=None,
        last_updated=last, price_changed_at=None,
    )


def _board(now):
    """lane1b's P1c board: an exclusive date ladder, one rung dated yesterday,
    priced low and last seen before its own deadline."""
    seen = now - timedelta(hours=1)
    legs = [
        _leg(1, "October 28", 0.55, last=seen),
        _leg(2, "October 29", 0.35, last=seen),
        _leg(3, "October 30", 0.25, last=seen),
        _leg(4, EXPIRED, 0.10, last=datetime(2026, 10, 26, 20, 0, tzinfo=timezone.utc)),
    ]
    return SimpleNamespace(
        id=990011, name="Probe date board", description=None,
        category="championship", source="kalshi", external_id="F1-probe",
        status="open", sport=None, sport_id=None, event_id=None, market_type=None,
        market_tier=5, llm_sport_category="politics", mutually_exclusive=True,
        commence_time=None, resolution_date=datetime(2099, 1, 1, tzinfo=timezone.utc),
        created_at=None, updated_at=None, group_id=None, canonical_market_key=None,
        hook_description=None, image_url=None, category_tags=[],
        market_metadata=None, outcomes=legs,
    )


def _read(now):
    """Detail, search card and typeahead on one input at one fixed instant."""

    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)

    market = _board(now)
    original = deepcopy(market)
    with ExitStack() as stack:
        for module in (events, futures):
            stack.enter_context(patch.object(module, "datetime", _Fixed))
        detail = futures._format_market_detail(market)["outcomes"]
        card = list(events._build_search_top_outcomes(market, limit=5, lean=False))
        typeahead = list(events._build_search_top_outcomes(market, limit=3, lean=True))
    assert market == original
    return detail, card, typeahead


def _assert_parity(now):
    detail, card, typeahead = _read(now)
    on_detail = {row["name"]: row["rendered_percent"] for row in detail}
    for surface, rows in (("card", card), ("typeahead", typeahead)):
        names = [row["name"] for row in rows]
        assert set(names) <= set(on_detail), (surface, now, names, sorted(on_detail))
        assert {row["name"]: row["rendered_percent"] for row in rows} == {
            name: on_detail[name] for name in names
        }, (surface, now)
    return on_detail, card, typeahead


def test_afternoon_search_drops_the_rung_detail_dropped_and_prints_its_integers():
    # P1c verbatim: 15:00Z, three hours after the October 26 rung was spent.
    on_detail, card, typeahead = _assert_parity(
        datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
    )
    assert EXPIRED not in on_detail
    assert [r["name"] for r in card] == ["October 28", "October 29", "October 30"]
    assert [r["rendered_percent"] for r in card] == [48, 30, 22]
    assert [r["rendered_percent"] for r in typeahead] == [48, 30, 22]


def test_morning_control_the_live_rung_is_on_every_surface():
    # Before the grace boundary the rung is live on detail AND search: the
    # repair must not drop it early (the opposite error).
    on_detail, card, _ = _assert_parity(datetime(2026, 10, 27, 11, 0, tzinfo=timezone.utc))
    assert EXPIRED in on_detail
    assert EXPIRED in [r["name"] for r in card]


@pytest.mark.parametrize(
    ("now", "live"),
    [
        (EXPIRES_AT - timedelta(seconds=1), True),
        (EXPIRES_AT, True),
        (EXPIRES_AT + timedelta(seconds=1), False),
    ],
    ids=["one-second-before", "at-boundary", "one-second-after"],
)
def test_the_grace_boundary_is_the_same_second_on_every_surface(now, live):
    on_detail, card, _ = _assert_parity(now)
    assert (EXPIRED in on_detail) is live
    assert (EXPIRED in [r["name"] for r in card]) is live


@pytest.mark.parametrize("hour", range(0, 24, 2))
def test_clock_sweep_search_and_detail_agree_at_every_hour(hour):
    # `scripts/clock_sweep.py`-style: twelve fixed clocks across the read day.
    _assert_parity(datetime(2026, 10, 27, hour, 30, tzinfo=timezone.utc))
