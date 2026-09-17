"""The chart reads the same outcomes as the board beside it (#6641).

Alex's 2026-09-16 physical-phone pass caught a **Market Details** screen whose
chart participant table listed five rows crowned by "No 100%" directly above an
All Outcomes board of three that lists no "No" at all. One screen, two answers.

The market is `futures_markets.id = 112868` "Taylor Swift pregnant by...?".
Reading its stored `external_id`s settles what it is: `Yes`
(`0x1ba46d…372b2_yes`), `No` (`…_no`) and the rung `March 31, 2026`
(`0x1ba46d…372b2`) are ONE Polymarket condition stored three times — the field
row carries the bare rung, and the decomposition branch of `tasks/polymarket.py`
writes the same condition's two legs beside it. Not a deadline ladder rendered
poorly; the ladder is correct.

`app/utils/duplicate_condition_outcomes.py` has held the rule since Q480 and
`_format_market_detail` applies it — which is exactly why the board was right
and the chart was wrong. Four chart readers in `routes/futures.py` read
`market.outcomes` raw, and `APIClient.swift` points the phone's chart at one of
them. Measured on production 2026-09-16 (release v4650), served payloads:

    market     /probability-timeline   /{id} board   chart's #1
    112868              5                   3        No   0.999
    112904              5                   3        No   0.9275
    113446              5                   3        No   1.0
    112936              8                   6        No   1.0   (Yes AND No both 1.0)
    30635376            8                   6        No   0.999

Five for five. The full BEFORE/AFTER, rebuilt from those rows and pinned to what
production actually served, is `artifacts-407/before_after_6641.py` (exit 0;
`--strawman` exit 1).
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.futures import get_probability_timeline

#: The real condition behind 112868's `March 31, 2026` rung and its two legs.
_C = "0x1ba46d242ac8b0cd6abc243bdd76630bbb7fdbbd380c766ae569bc2cc42372b2"
_DEC26 = "0x0803b42cec5723f301f77f3ea818fcb393eb58b9694096cab2d4f8b81b4a2bdf"
_DEC25 = "0xf4f51e9e4e8439e32f64dc0e659828af7564f9cbc323d4f7442f2c590a2ea07d"


def _outcome(oid, name, external_id, prob):
    o = MagicMock()
    o.id = oid
    o.name = name
    # A REAL string, deliberately. `MagicMock().endswith(...)` returns a truthy
    # mock and the subsequent `base in present` is False by identity, so a mock
    # id makes the filter a no-op and the test vacuous.
    o.external_id = external_id
    o.current_probability = prob
    o.probability_change_24h = None
    o.opening_probability = None
    o.rank = None
    o.team = None
    o.team_id = None
    o.is_winner = False
    o.resolution_source = None
    o.current_yes_bid = None
    o.current_yes_ask = None
    return o


def _taylor_swift_112868():
    """The five rows production stores, in `futures_outcomes.id` order."""
    return [
        _outcome(1, "December 31, 2026", _DEC26, 0.145),
        _outcome(2, "March 31, 2026", _C, 0.001),
        _outcome(3, "December 31, 2025", _DEC25, 0.0),
        _outcome(4, "Yes", f"{_C}_yes", 0.001),
        _outcome(5, "No", f"{_C}_no", 0.999),
    ]


def _market(outcomes, mid=112868, name="Taylor Swift pregnant by...?"):
    m = MagicMock()
    m.id = mid
    m.name = name
    m.outcomes = outcomes
    # In-play, so the route pins the window to the event start and skips the
    # sparse auto-extend — the same harness shape the existing timeline tests
    # use, and it keeps the mocked `db.execute` sequence honest rather than
    # padding it with results the real route would not ask for.
    m.commence_time = datetime.now(timezone.utc) - timedelta(hours=2)
    m.source = "polymarket"
    m.market_metadata = {}
    return m


async def _timeline(market, top=10):
    captured = datetime.now(timezone.utc) - timedelta(hours=1)
    snaps = []
    for o in market.outcomes:
        s = MagicMock()
        s.outcome_id = o.id
        s.probability = o.current_probability
        s.captured_at = captured
        s.bookmaker = "polymarket"
        snaps.append(s)

    market_result = MagicMock()
    market_result.scalar_one_or_none.return_value = market
    snap_result = MagicMock()
    snap_result.scalars.return_value.all.return_value = snaps
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[market_result, snap_result, snap_result])
    return await get_probability_timeline(market_id=market.id, top=top, hours=168, db=db)


class TestThePhoneChartAgreesWithTheBoard:
    async def test_the_chart_does_not_serve_a_leg_the_board_drops(self):
        resp = await _timeline(_market(_taylor_swift_112868()))
        names = [o["name"] for o in resp["outcomes"]]

        assert "No" not in names and "Yes" not in names, (
            f"the chart still serves the binary legs: {names}"
        )
        assert len(names) == 3, f"expected the board's three rungs, got {names}"
        assert names[0] == "December 31, 2026", (
            f"the chart is crowned by {names[0]!r}; production crowned 'No' at 99.9%"
        )

    async def test_the_dropped_leg_is_gone_from_the_timeline_series_too(self):
        """Not just the legend — the plotted lines."""
        resp = await _timeline(_market(_taylor_swift_112868()))
        assert resp["timeline"], "expected at least one bucket"
        for entry in resp["timeline"]:
            assert "No" not in entry["outcomes"] and "Yes" not in entry["outcomes"], (
                f"a dropped leg is still plotted: {sorted(entry['outcomes'])}"
            )

    async def test_a_dropped_leg_is_not_resurrected_as_an_inflated_field(self):
        """`> top` and the Field sum must count the SAME list the participants come from.

        With `top=2` the deduped market has 3 rungs, so Field is one rung
        (`December 31, 2025`, 0.0). Counted against the raw five it would be
        three rows including `No` at 0.999 — the leg reappearing as a line.
        """
        resp = await _timeline(_market(_taylor_swift_112868()), top=2)
        field = [o for o in resp["outcomes"] if o["name"] == "Field"]
        assert field, "expected a Field entry with top=2"
        assert field[0]["current_probability"] == pytest.approx(0.0, abs=1e-9), (
            f"Field is {field[0]['current_probability']} — it is summing the legs"
        )


class TestTheFilterOnlyFiresWhereTheDefectIs:
    async def test_a_correctly_decomposed_sub_market_still_draws_its_chart(self):
        """The withholding control: the legs are only wrong BESIDE their rung.

        On the sub-market that owns them there is no bare twin, so dropping them
        would leave an empty chart. A rule that empties a surface is not a fix.
        """
        sub = _market(
            [
                _outcome(11, "Yes", f"{_C}_yes", 0.001),
                _outcome(12, "No", f"{_C}_no", 0.999),
            ],
            mid=13798072,
            name="Will Taylor Swift be pregnant by March 31, 2026?",
        )
        resp = await _timeline(sub)
        names = sorted(o["name"] for o in resp["outcomes"])
        assert names == ["No", "Yes"], f"the sub-market chart lost its legs: {names}"
        assert resp["timeline"], "the sub-market chart was emptied"

    async def test_a_market_that_never_held_a_leg_is_byte_identical(self):
        """Unchanged wherever the defect wasn't."""
        clean = [o for o in _taylor_swift_112868()
                 if not o.external_id.endswith(("_yes", "_no"))]
        contaminated = await _timeline(_market(_taylor_swift_112868()))
        control = await _timeline(_market(clean))
        assert contaminated["outcomes"] == control["outcomes"]
        assert contaminated["timeline"] == control["timeline"]


#: Every chart reader in `routes/futures.py`. Enumerating them IS the job: the
#: class was fixed on the board in Q480 and survived here for a month because
#: only the surfaces someone happened to be editing were converted.
CHART_READERS = [
    "get_probability_timeline",
    "get_futures_history",
    "get_cross_source_timeline",
    "get_multi_market_history",
]


def _tree(func_name):
    import app.routes.futures as futures

    return ast.parse(textwrap.dedent(inspect.getsource(getattr(futures, func_name))))


@pytest.mark.parametrize("func_name", CHART_READERS)
def test_every_market_outcomes_read_in_a_chart_reader_goes_through_the_filter(func_name):
    """No bare `market.outcomes` survives in these four bodies.

    Anchored on THIS function's own tree, and on the ATTRIBUTE rather than on
    the presence of a call: `charted_outcomes = market.outcomes` with a stray
    `drop_duplicate_legs(...)` left elsewhere in the body would satisfy a
    "does it call the filter" check and serve the leg anyway. Every
    `market.outcomes` must BE an argument to the filter.
    """
    tree = _tree(func_name)

    filtered = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("drop_duplicate_legs", "_drop_duplicate_legs")
            and node.args
        ):
            filtered.add(ast.dump(node.args[0]))

    assert filtered, (
        f"{func_name} never calls drop_duplicate_legs — a market holding both a "
        "rung and its _yes/_no twin will chart the twin (#6641)"
    )

    bare = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "outcomes"
        and isinstance(node.value, ast.Name)
        and node.value.id == "market"
        and ast.dump(node) not in filtered
    ]
    assert not bare, (
        f"{func_name} reads market.outcomes raw at offset line(s) {bare} — that "
        "read bypasses the duplicate-leg filter the board applies (#6641)"
    )
