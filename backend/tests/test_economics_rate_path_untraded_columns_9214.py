"""#9214 — the rate path stops drawing meetings nobody is trading.

`/economics`, 390px, 2026-09-27 21:35Z: the *2026–27 rate path* heatmap
scrolled right into three 2027 columns, each a confident story no market
prices — Jun **91% at 3.25%**, Jul **99% at 3.25%**, Sep **80% at 3.25%** —
beside five real meetings whose mass sits at 4.00–4.25%.

`get_economics` differenced every `Fed funds rate after …` ladder through
`_cumulative_to_discrete` without asking where its prices came from:

    column     priced  quoted  what the rungs are
    Jun 2027   17      2       1c/99c books; an unpriced `Above 3.50%` reads
                               as 0 and clamps the only real rungs above it
    Jul 2027   14      0       1c/99c books carrying a 99c last trade
    Sep 2027   14      0       one 60c/$1.00 quote copied onto every rung
                               (#8826's shape — the feed already refuses it)

The fixtures below are those stored rows, verbatim (price, bid, ask), read
from production the same minute, plus two of the five healthy columns as the
control. The gate is `_ladder_is_mostly_quoted`: a column is drawn only when
most of its priced rungs pass `_rung_is_quoted` (not `book_bounds_nothing`,
not `is_fabricated_midpoint` — both shared predicates, no new constant).

Non-vacuity: `TestTheSeedIsReal` proves every specimen reaches the card with
the gate removed, so "is not present" cannot pass on a ladder that never
qualified for another reason; `test_the_reported_screen_reproduces_without_the_gate`
is the strawman, pinning the exact cells the reader saw.
"""

from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes import economics
from app.routes.economics import (
    _ladder_is_mostly_quoted,
    _rung_is_quoted,
    get_economics,
)

# The day the defect was read. No meeting title here is stale at this instant.
FIXED_NOW = datetime(2026, 9, 27, 21, 35, 0, tzinfo=timezone.utc)


# 109947 `KXFED-26OCT`: (threshold, price, yes_bid, yes_ask)
_OCT_2026 = [
    ('2.75%', 0.995, 0.99, 1.0), ('3.00%', 0.995, 0.99, 1.0), ('3.25%', 0.995, 0.99, 1.0),
    ('3.50%', 0.99, 0.98, 1.0), ('3.75%', 0.995, 0.99, 1.0), ('4.00%', 0.635, 0.63, 0.64),
    ('4.25%', 0.015, 0.01, 0.02), ('4.50%', 0.02, 0.0, 0.02), ('4.75%', 0.01, 0.0, 0.01),
    ('5.00%', 0.01, 0.0, 0.01), ('5.25%', 0.01, 0.0, 0.01),
]

# 108574 `KXFED-27APR`: (threshold, price, yes_bid, yes_ask)
_APR_2027 = [
    ('0.00%', 0.88, 0.76, 1.0), ('0.25%', 0.89, 0.78, 1.0), ('0.50%', 0.905, 0.81, 1.0),
    ('0.75%', 0.94, 0.91, 0.97), ('1.00%', 0.935, 0.92, 0.95), ('1.25%', 0.94, 0.91, 0.97),
    ('1.50%', 0.945, 0.91, 0.98), ('1.75%', 0.95, 0.91, 0.99), ('2.00%', 0.95, 0.91, 0.99),
    ('2.25%', 0.95, 0.91, 0.99), ('2.50%', 0.935, 0.89, 0.98), ('2.75%', 0.945, 0.9, 0.99),
    ('3.00%', 0.91, 0.85, 0.97), ('3.25%', 0.855, 0.8, 0.91), ('3.50%', 0.805, 0.72, 0.89),
    ('3.75%', 0.735, 0.51, 0.96), ('4.00%', 0.74, 0.56, 0.92), ('4.25%', 0.56, 0.49, 0.63),
    ('4.50%', None, None, None), ('4.75%', None, None, None), ('5.00%', None, None, None),
    ('5.25%', None, None, None), ('5.50%', 0.83, 0.01, 0.98), ('5.75%', None, None, None),
    ('6.00%', None, None, None),
]

# 61461616 `KXFED-27JUN`: (threshold, price, yes_bid, yes_ask)
_JUN_2027 = [
    ('0.00%', 0.96, 0.93, 0.99), ('0.25%', 0.95, 0.03, 0.99), ('0.50%', 0.99, 0.01, 0.99),
    ('0.75%', 0.99, 0.01, 0.99), ('1.00%', 0.99, 0.01, 0.99), ('1.25%', 0.99, 0.01, 0.99),
    ('1.50%', 0.99, 0.01, 0.99), ('1.75%', 0.99, 0.01, 0.99), ('2.00%', 0.94, 0.01, 0.99),
    ('2.25%', 0.93, 0.01, 0.99), ('2.50%', 0.91, 0.01, 0.99), ('2.75%', 0.91, 0.01, 0.99),
    ('3.00%', 0.91, 0.01, 0.99), ('3.25%', 0.94, 0.01, 0.99), ('3.50%', None, None, None),
    ('3.75%', None, None, None), ('4.00%', 0.63, 0.02, 0.92), ('4.25%', 0.645, 0.4, 0.89),
    ('4.50%', None, None, None), ('4.75%', 0.33, 0.21, 0.8), ('5.00%', None, None, None),
    ('5.25%', None, None, None), ('5.50%', None, None, None), ('5.75%', None, None, None),
    ('6.00%', None, None, None),
]

# 61461586 `KXFED-27JUL`: (threshold, price, yes_bid, yes_ask)
_JUL_2027 = [
    ('0.00%', 0.99, 0.01, 0.99), ('0.25%', 0.99, 0.01, 0.99), ('0.50%', 0.99, 0.01, 0.99),
    ('0.75%', 0.99, 0.01, 0.99), ('1.00%', 0.99, 0.01, 0.99), ('1.25%', 0.99, 0.01, 0.99),
    ('1.50%', 0.99, 0.01, 0.99), ('1.75%', 0.99, 0.02, 0.99), ('2.00%', 0.99, 0.02, 0.99),
    ('2.25%', 0.99, 0.02, 0.99), ('2.50%', 0.99, 0.02, 0.99), ('2.75%', 0.99, 0.01, 0.99),
    ('3.00%', 0.99, 0.01, 0.99), ('3.25%', 0.99, 0.01, 0.99), ('3.50%', None, None, None),
    ('3.75%', None, None, None), ('4.00%', None, None, None), ('4.25%', None, None, None),
    ('4.50%', None, None, None), ('4.75%', None, None, None), ('5.00%', None, None, None),
    ('5.25%', None, None, None), ('5.50%', None, None, None), ('5.75%', None, None, None),
    ('6.00%', None, None, None),
]

# 61461585 `KXFED-27SEP`: (threshold, price, yes_bid, yes_ask)
_SEP_2027 = [
    ('0.00%', 0.8, 0.6, 1.0), ('0.25%', 0.8, 0.6, 1.0), ('0.50%', 0.8, 0.6, 1.0),
    ('0.75%', 0.8, 0.6, 1.0), ('1.00%', 0.8, 0.6, 1.0), ('1.25%', 0.8, 0.6, 1.0),
    ('1.50%', 0.8, 0.6, 1.0), ('1.75%', 0.8, 0.6, 1.0), ('2.00%', 0.8, 0.6, 1.0),
    ('2.25%', 0.8, 0.6, 1.0), ('2.50%', 0.8, 0.6, 1.0), ('2.75%', 0.8, 0.6, 1.0),
    ('3.00%', 0.8, 0.6, 1.0), ('3.25%', 0.8, 0.6, 1.0), ('3.50%', None, None, None),
    ('3.75%', None, None, None), ('4.00%', None, None, None), ('4.25%', None, None, None),
    ('4.50%', None, None, None), ('4.75%', None, None, None), ('5.00%', None, None, None),
    ('5.25%', None, None, None), ('5.50%', None, None, None), ('5.75%', None, None, None),
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
    # Production spelling: `KXFED-27JUN` matches no `_THEME_BY_TICKER` prefix,
    # so these theme as `fed` through the NAME regex, as they do live.
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


HEALTHY = {109947: ("Oct 2026", _OCT_2026), 108574: ("Apr 2027", _APR_2027)}
UNTRADED = {
    61461616: ("Jun 2027", _JUN_2027),
    61461586: ("Jul 2027", _JUL_2027),
    61461585: ("Sep 2027", _SEP_2027),
}


def _pool():
    return [_ladder(mid, month, rows) for mid, (month, rows) in {**HEALTHY, **UNTRADED}.items()]


_REAL_CUMULATIVE_TO_DISCRETE = economics._cumulative_to_discrete


def _cells_unfiltered(outcomes, max_buckets=8, usable=None):
    return _REAL_CUMULATIVE_TO_DISCRETE(outcomes, max_buckets=max_buckets)


async def _columns(markets, gate=True, cells=True):
    """``gate=False`` removes this file's column gate; ``cells=False`` also
    removes #9804's per-cell one, which blanks these same untraded rungs one
    cell at a time — so the seed, which proves the specimens reach the card
    with NOTHING refusing them, needs both off."""
    result_obj = MagicMock()
    result_obj.scalars.return_value.unique.return_value.all.return_value = list(markets)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result_obj)
    with patch("app.routes.economics.datetime") as dt, ExitStack() as stack:
        dt.now.return_value = FIXED_NOW
        if not gate:
            stack.enter_context(patch.object(economics, "_ladder_is_mostly_quoted", lambda _o: True))
        if not cells:
            stack.enter_context(patch.object(economics, "_cumulative_to_discrete", _cells_unfiltered))
        payload = await get_economics(db)
    return {c["market_id"]: c for c in payload["themes"]["fed"]["fomc_meetings"]}


def _cell(column, label):
    return next((p for p, lab in column["dist"] if lab == label), None)


@pytest.mark.asyncio
class TestTheSeedIsReal:
    async def test_every_specimen_reaches_the_card_without_the_gate(self):
        cols = await _columns(_pool(), gate=False, cells=False)
        assert set(cols) == set(HEALTHY) | set(UNTRADED), (
            "a seeded ladder no longer reaches the heatmap for another reason — "
            "every absence asserted below is vacuous until this passes"
        )

    async def test_the_reported_screen_reproduces_without_the_gate(self):
        """Strawman: the exact cells the reader saw."""
        cols = await _columns(_pool(), gate=False, cells=False)
        assert _cell(cols[61461616], "3.25%") == 91.0
        assert _cell(cols[61461586], "3.25%") == 99.0
        assert _cell(cols[61461585], "3.25%") == 80.0


@pytest.mark.asyncio
class TestTheShip:
    async def test_the_three_untraded_meetings_draw_no_column(self):
        cols = await _columns(_pool())
        for mid, (month, _rows) in UNTRADED.items():
            assert mid not in cols, f"{month} still draws a column out of untraded books"

    async def test_the_real_meetings_are_untouched(self):
        with_gate = await _columns(_pool())
        without = await _columns(_pool(), gate=False)
        for mid in HEALTHY:
            assert with_gate[mid] == without[mid]

    async def test_the_healthy_columns_keep_their_mass_where_the_market_put_it(self):
        cols = await _columns(_pool())
        assert _cell(cols[109947], "4.00%") == 62.0
        assert _cell(cols[108574], "4.25%") == 56.0


class TestTheRule:
    def test_rung_classes(self):
        # A real book.
        assert _rung_is_quoted(SimpleNamespace(current_probability=0.635, current_yes_bid=0.63, current_yes_ask=0.64))
        # A 1c/99c book: bounds nothing, whatever its stored trade says.
        assert not _rung_is_quoted(SimpleNamespace(current_probability=0.99, current_yes_bid=0.01, current_yes_ask=0.99))
        # #8826: a narrower book, but the price IS its midpoint.
        assert not _rung_is_quoted(SimpleNamespace(current_probability=0.80, current_yes_bid=0.60, current_yes_ask=1.00))
        # No book at all is a model price — the predicates' own fail-open.
        assert _rung_is_quoted(SimpleNamespace(current_probability=0.40))

    def test_measured_ratios(self):
        """Each specimen's quoted/priced split, so a predicate change upstream
        that moves one of them fails here, named."""
        def split(rows):
            priced = [o for o in _rungs(rows) if o.current_probability is not None]
            return sum(_rung_is_quoted(o) for o in priced), len(priced)

        assert split(_OCT_2026) == (11, 11)
        assert split(_APR_2027) == (14, 19)
        assert split(_JUN_2027) == (2, 17)
        assert split(_JUL_2027) == (0, 14)
        assert split(_SEP_2027) == (0, 14)

    def test_majority_boundary(self):
        quoted = SimpleNamespace(current_probability=0.5, current_yes_bid=0.49, current_yes_ask=0.51)
        dead = SimpleNamespace(current_probability=0.99, current_yes_bid=0.01, current_yes_ask=0.99)
        assert _ladder_is_mostly_quoted([quoted, quoted, dead])
        assert not _ladder_is_mostly_quoted([quoted, dead]), "a tie is not a majority"
        assert not _ladder_is_mostly_quoted([])
        unpriced = SimpleNamespace(current_probability=None, current_yes_bid=None, current_yes_ask=None)
        assert _ladder_is_mostly_quoted([quoted, unpriced, unpriced]), "unpriced rungs are not votes"
