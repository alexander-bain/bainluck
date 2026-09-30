"""#9804 — the rate path stops drawing confident cells from rungs nobody is trading.

Not a regression of #9214. That fix refuses whole meeting COLUMNS whose rungs
are mostly untraded. This is an untraded rung INSIDE a column #9214 correctly
keeps: `_ladder_is_mostly_quoted` asks a majority question per column, then
`_cumulative_to_discrete` differences every priced rung in it, and the monotone
clamp copies an untraded rung's value into its neighbours.

`/economics`, 390px, 2026-09-30 10:48Z (ux's D48 walk), "2026–27 rate path":

    column     served cell    where it comes from
    Apr 2027   73 at 4.50%    `Above 4.50%` 0.73 on a 0.04/0.98 book, minus the
                              unpriced `Above 4.75%` read as 0
    Mar 2027   79 at 4.25%    `Above 4.25%` 0.79, the exact midpoint of 0.66/0.92
                              (and 3.75/4.00 below it are midpoints too)
    Jan 2027   5.5 at 6.00%   `Above 5.25..6.00%` are all midpoints of 1c books;
                              the clamp copies `Above 5.00%`'s 0.055 up to 6.00

The fixtures are every stored rung of the five served columns, verbatim (price,
bid, ask), read from production at 11:40Z the same morning; the unrepaired code
reproduces the served payload of that minute cell for cell, which
`TestTheSeedIsReal` pins.

The repair: a cell is served only when both rungs it differences pass
`_rung_is_quoted` (#9214's own predicate — no new constant), and a clamped rung
is usable only if the rung it copied is too. The cell is left out, never
re-linked across the gap (the rung-dropping repair #9214 measured and rejected).
A column whose surviving cells no longer carry most of the probability is left
out whole — Mar kept 4.5 of 100 points and Apr kept none, and a column of
slivers wears the heatmap's modal outline on a 1.5% cell.

NOT repaired, pinned as such: Jan's **22.5 at 4.75%**. `Above 4.75%` 0.76 on
0.02/0.78 and `Above 4.50%` 0.28 on 0.08/0.76 both pass `_rung_is_quoted`
(neither book is 90c wide, neither price is its midpoint), so a fresh trade and
a stale print are identical in the stored columns. Separating them needs a
per-rung last-trade time the table does not store.
"""

from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes import economics
from app.routes.economics import _cumulative_to_discrete, _rung_is_quoted, get_economics

# The day the defect was read. No meeting title here is stale at this instant.
FIXED_NOW = datetime(2026, 9, 30, 11, 40, 0, tzinfo=timezone.utc)


# 109947 `KXFED-26OCT`: (threshold, price, yes_bid, yes_ask)
_OCT_2026 = [
    ('2.75%', 0.995, 0.99, 1.0), ('3.00%', 0.995, 0.99, 1.0), ('3.25%', 0.995, 0.99, 1.0),
    ('3.50%', 0.99, 0.98, 1.0), ('3.75%', 0.99, 0.98, 1.0), ('4.00%', 0.455, 0.45, 0.46),
    ('4.25%', 0.01, 0.0, 0.01), ('4.50%', 0.02, 0.0, 0.02), ('4.75%', 0.01, 0.0, 0.01),
    ('5.00%', 0.01, 0.0, 0.01), ('5.25%', 0.01, 0.0, 0.01),
]

# 109658 `KXFED-26DEC`: (threshold, price, yes_bid, yes_ask)
_DEC_2026 = [
    ('2.75%', 0.985, 0.98, 0.99), ('3.00%', 0.99, 0.98, 1.0), ('3.25%', 0.98, 0.97, 0.99),
    ('3.50%', 0.975, 0.97, 0.98), ('3.75%', 0.975, 0.97, 0.98), ('4.00%', 0.875, 0.86, 0.89),
    ('4.25%', 0.395, 0.38, 0.41), ('4.50%', 0.05, 0.03, 0.07), ('4.75%', 0.02, 0.0, 0.02),
    ('5.00%', 0.02, 0.0, 0.02), ('5.25%', 0.01, 0.0, 0.01),
]

# 108626 `KXFED-27JAN`: (threshold, price, yes_bid, yes_ask)
_JAN_2027 = [
    ('0.00%', 0.98, 0.97, 0.99), ('0.25%', 0.955, 0.93, 0.98), ('0.50%', 0.975, 0.97, 0.98),
    ('0.75%', 0.975, 0.97, 0.98), ('1.00%', 0.97, 0.96, 0.98), ('1.25%', 0.96, 0.94, 0.98),
    ('1.50%', 0.95, 0.93, 0.97), ('1.75%', 0.96, 0.94, 0.98), ('2.00%', 0.955, 0.94, 0.97),
    ('2.25%', 0.96, 0.93, 0.99), ('2.50%', 0.945, 0.92, 0.97), ('2.75%', 0.94, 0.91, 0.97),
    ('3.00%', 0.945, 0.92, 0.97), ('3.25%', 0.945, 0.92, 0.97), ('3.50%', 0.935, 0.9, 0.97),
    ('3.75%', 0.95, 0.92, 0.98), ('4.00%', 0.915, 0.86, 0.97), ('4.25%', 0.735, 0.73, 0.74),
    ('4.50%', 0.28, 0.08, 0.76), ('4.75%', 0.76, 0.02, 0.78), ('5.00%', 0.055, 0.01, 0.1),
    ('5.25%', 0.255, 0.01, 0.5), ('5.50%', 0.255, 0.01, 0.5), ('5.75%', 0.255, 0.01, 0.5),
    ('6.00%', 0.155, 0.01, 0.3),
]

# 108581 `KXFED-27MAR`: (threshold, price, yes_bid, yes_ask)
_MAR_2027 = [
    ('0.00%', 0.96, 0.92, 1.0), ('0.25%', 0.965, 0.93, 1.0), ('0.50%', 0.945, 0.91, 0.98),
    ('0.75%', 0.95, 0.92, 0.98), ('1.00%', 0.975, 0.97, 0.98), ('1.25%', 0.945, 0.9, 0.99),
    ('1.50%', 0.94, 0.89, 0.99), ('1.75%', 0.935, 0.88, 0.99), ('2.00%', 0.935, 0.87, 1.0),
    ('2.25%', 0.935, 0.88, 0.99), ('2.50%', 0.935, 0.88, 0.99), ('2.75%', 0.93, 0.87, 0.99),
    ('3.00%', 0.915, 0.85, 0.98), ('3.25%', 0.93, 0.87, 0.99), ('3.50%', 0.925, 0.85, 1.0),
    ('3.75%', 0.87, 0.75, 0.99), ('4.00%', 0.855, 0.75, 0.96), ('4.25%', 0.79, 0.66, 0.92),
    ('4.50%', None, None, None), ('4.75%', 0.81, 0.02, 0.98), ('5.00%', 0.135, 0.02, 0.25),
    ('5.25%', 0.11, 0.02, 0.2), ('5.50%', 0.21, 0.01, 0.98), ('5.75%', 0.1, 0.02, 0.92),
    ('6.00%', 0.125, 0.01, 0.24),
]

# 108574 `KXFED-27APR`: (threshold, price, yes_bid, yes_ask)
_APR_2027 = [
    ('0.00%', 0.875, 0.76, 0.99), ('0.25%', 0.94, 0.89, 0.99), ('0.50%', 0.9, 0.81, 0.99),
    ('0.75%', 0.95, 0.92, 0.98), ('1.00%', 0.955, 0.94, 0.97), ('1.25%', 0.94, 0.91, 0.97),
    ('1.50%', 0.945, 0.91, 0.98), ('1.75%', 0.945, 0.91, 0.98), ('2.00%', 0.955, 0.92, 0.99),
    ('2.25%', 0.96, 0.93, 0.99), ('2.50%', 0.935, 0.89, 0.98), ('2.75%', 0.94, 0.89, 0.99),
    ('3.00%', 0.91, 0.85, 0.97), ('3.25%', 0.955, 0.94, 0.97), ('3.50%', 0.935, 0.9, 0.97),
    ('3.75%', 0.96, 0.24, 0.98), ('4.00%', 0.745, 0.52, 0.97), ('4.25%', 0.82, 0.75, 0.89),
    ('4.50%', 0.73, 0.04, 0.98), ('4.75%', None, None, None), ('5.00%', None, None, None),
    ('5.25%', None, None, None), ('5.50%', 0.83, 0.01, 0.98), ('5.75%', None, None, None),
    ('6.00%', None, None, None),
]


def _rungs(rows):
    return [
        SimpleNamespace(
            id=i,
            name=f"Above {threshold}",
            external_id=f"T{threshold}",
            current_probability=price,
            current_yes_bid=bid,
            current_yes_ask=ask,
            rank=i,
        )
        for i, (threshold, price, bid, ask) in enumerate(rows, start=1)
    ]


def _ladder(mid, month, rows):
    return SimpleNamespace(
        id=mid,
        name=f"Fed funds rate after {month} meeting?",
        source="kalshi",
        external_id=f"KXFED-{mid}",
        outcomes=_rungs(rows),
        status="open",
        llm_sport_category="economics",
        group_id=None,
        volume=50_000.0,
    )


OCT, DEC, JAN, MAR, APR = 109947, 109658, 108626, 108581, 108574
COLUMNS = {
    OCT: ("Oct 2026", _OCT_2026),
    DEC: ("Dec 2026", _DEC_2026),
    JAN: ("Jan 2027", _JAN_2027),
    MAR: ("Mar 2027", _MAR_2027),
    APR: ("Apr 2027", _APR_2027),
}

_REAL_CUMULATIVE_TO_DISCRETE = economics._cumulative_to_discrete


def _cells_unfiltered(outcomes, max_buckets=8, usable=None):
    return _REAL_CUMULATIVE_TO_DISCRETE(outcomes, max_buckets=max_buckets)


def _pool(columns=COLUMNS):
    return [_ladder(mid, month, rows) for mid, (month, rows) in columns.items()]


async def _columns(markets, cells=True):
    """``cells=False`` removes #9804's per-cell rule, leaving #9214's column gate."""
    result_obj = MagicMock()
    result_obj.scalars.return_value.unique.return_value.all.return_value = list(markets)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result_obj)
    with patch("app.routes.economics.datetime") as dt, ExitStack() as stack:
        dt.now.return_value = FIXED_NOW
        if not cells:
            stack.enter_context(patch.object(economics, "_cumulative_to_discrete", _cells_unfiltered))
        payload = await get_economics(db)
    return {c["market_id"]: c for c in payload["themes"]["fed"]["fomc_meetings"]}


def _cell(column, label):
    return next((p for p, lab in column["dist"] if lab == label), None)


@pytest.mark.asyncio
class TestTheSeedIsReal:
    async def test_every_column_reaches_the_card_without_the_cell_rule(self):
        cols = await _columns(_pool(), cells=False)
        assert set(cols) == set(COLUMNS), (
            "a seeded column no longer reaches the heatmap for another reason — "
            "every absence asserted below is vacuous until this passes"
        )

    async def test_the_served_payload_reproduces_without_the_cell_rule(self):
        """Strawman: production's /api/economics at 11:40Z, cell for cell."""
        cols = await _columns(_pool(), cells=False)
        assert cols[APR]["dist"] == [[73.0, "4.50%"], [1.5, "4.25%"], [13.0, "3.75%"]]
        assert cols[MAR]["dist"][0] == [79.0, "4.25%"]
        assert cols[JAN]["dist"][:2] == [[5.5, "6.00%"], [22.5, "4.75%"]]


@pytest.mark.asyncio
class TestTheShip:
    async def test_apr_and_mar_draw_no_column(self):
        cols = await _columns(_pool())
        assert APR not in cols, "Apr 2027 still draws 73% at 4.50% from a 4c/98c book"
        assert MAR not in cols, "Mar 2027 still draws 79% at 4.25% from a copied midpoint"

    async def test_jan_stops_drawing_the_clamped_top_cell(self):
        cols = await _columns(_pool())
        assert _cell(cols[JAN], "6.00%") is None
        # Every other Jan cell is untouched — the repair is the one cell.
        before = await _columns(_pool(), cells=False)
        assert cols[JAN]["dist"] == [c for c in before[JAN]["dist"] if c[1] != "6.00%"]

    async def test_jans_4_75_cell_is_unrepaired_and_says_so(self):
        """Both bounding rungs pass the predicate; see the module docstring."""
        jan = {o.name: o for o in _rungs(_JAN_2027)}
        assert _rung_is_quoted(jan["Above 4.75%"]) and _rung_is_quoted(jan["Above 4.50%"])
        cols = await _columns(_pool())
        assert _cell(cols[JAN], "4.75%") == 22.5

    async def test_the_fully_quoted_meetings_are_the_control(self):
        with_rule = await _columns(_pool())
        without = await _columns(_pool(), cells=False)
        for mid in (OCT, DEC):
            assert with_rule[mid] == without[mid]
        assert _cell(with_rule[OCT], "4.00%") == 44.5
        assert _cell(with_rule[DEC], "4.00%") == 48.0


def _o(name, p, bid=None, ask=None):
    return SimpleNamespace(name=name, current_probability=p, current_yes_bid=bid, current_yes_ask=ask)


DEAD = (0.01, 0.99)  # a 1c/99c book: bounds nothing


class TestTheRule:
    @pytest.mark.parametrize("mid", list(COLUMNS))
    def test_no_predicate_is_the_old_output(self, mid):
        """Every non-rate-path caller passes nothing and must not move."""
        outcomes = _rungs(COLUMNS[mid][1])
        assert _cumulative_to_discrete(outcomes, 10) == _cumulative_to_discrete(outcomes, 10, usable=None)
        assert _cumulative_to_discrete(outcomes, 10) == _cumulative_to_discrete(outcomes, 10, usable=lambda _o: True)

    def test_a_cell_bounded_above_by_an_unquoted_rung_is_left_out(self):
        ladder = [_o("Above 1%", 0.9), _o("Above 2%", 0.6, *DEAD), _o("Above 3%", 0.1)]
        assert _cumulative_to_discrete(ladder, usable=_rung_is_quoted) == [[10.0, "3%"]]

    def test_the_top_cell_is_bounded_by_its_own_rung_alone(self):
        ladder = [_o("Above 1%", 0.9), _o("Above 2%", 0.6), _o("Above 3%", 0.1, *DEAD)]
        assert _cumulative_to_discrete(ladder, usable=_rung_is_quoted) == [[30.0, "1%"]]

    def test_a_clamped_rung_is_usable_only_if_both_are(self):
        # `Above 3%` is clamped down to `Above 2%`'s 0.4.
        quoted_over_quoted = [_o("Above 1%", 0.9), _o("Above 2%", 0.4), _o("Above 3%", 0.5)]
        assert _cumulative_to_discrete(quoted_over_quoted, usable=_rung_is_quoted) == [
            [50.0, "1%"], [40.0, "3%"],
        ]
        dead_over_quoted = [_o("Above 1%", 0.9), _o("Above 2%", 0.4), _o("Above 3%", 0.5, *DEAD)]
        assert _cumulative_to_discrete(dead_over_quoted, usable=_rung_is_quoted) == [[50.0, "1%"]]
        # A quoted rung clamped to a dead one's value holds a number nobody traded.
        quoted_over_dead = [_o("Above 1%", 0.9), _o("Above 2%", 0.4, *DEAD), _o("Above 3%", 0.5)]
        assert _cumulative_to_discrete(quoted_over_dead, usable=_rung_is_quoted) == []

    def test_the_print_grid_bottom_bucket_needs_its_rung(self):
        ladder = [_o("Above 0.1%", 0.8), _o("Above 0.2%", 0.5), _o("Above 0.3%", 0.2)]
        assert _cumulative_to_discrete(ladder)[0] == [20.0, "≤0.1%"]
        refused = _cumulative_to_discrete(ladder, usable=lambda o: o.name != "Above 0.1%")
        assert all(label != "≤0.1%" for _p, label in refused)


@pytest.mark.asyncio
class TestTheMassMajority:
    @staticmethod
    def _column(second_rung_price):
        # Two quoted rungs of three, so #9214 keeps it; the dead top rung's cell
        # is blanked and only `Above 1.00%`'s cell survives.
        return {
            1: ("Apr 2027", [
                ("1.00%", 1.0, None, None),
                ("2.00%", second_rung_price, None, None),
                ("3.00%", 0.5, *DEAD),
            ]),
        }

    async def test_exactly_half_is_not_a_majority(self):
        cols = await _columns(_pool(self._column(0.5)))
        assert 1 not in cols

    async def test_just_over_half_is_drawn(self):
        cols = await _columns(_pool(self._column(0.495)))
        assert cols[1]["dist"] == [[50.5, "1.00%"]]
