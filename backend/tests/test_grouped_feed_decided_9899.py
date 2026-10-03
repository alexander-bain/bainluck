"""#9899 — the /sports props strip stops serving questions that are already over.

THE DEFECT. Production, 2026-09-30 17:50Z, ``/sports`` at 390px, "Player Props
& Progressions (20)": four cards asked something already decided and printed it
as live — "Completed Match: Sedysheva vs Popovic" Yes >99%, "Set 1 Winner: Rozin
vs Schlagenhauf" Rozin >99% (set 1 already played), "Arsenal WFC 1st Half O/U
3.5" Under >99% (``resolution_date`` 16:45Z, already past), and "Completed
Match: Bonding vs Thomson" Yes >99%. The fourth had been marked ``resolved`` at
17:44:50Z and was still in the 600 s stale cache entry; the query's own status
filter already refuses it on a rebuild, so it needs nothing new.

THE SPECIMENS BELOW ARE THE STORED ROWS, read 2026-09-30 ~19:05Z via
``/api/admin/db-query``: prices and books verbatim, Decimals as SQLAlchemy
hands them to the route.

TWO RULES, BOTH ABOVE THE SLICE. (1) ``resolution_date IS NULL OR >= now`` on
the pool query — the clause every other open-market list route in
``routes/futures.py`` already carries. It cannot reach the tennis rows: Kalshi
stores their expiration a week out (2026-10-07), so (2) a price rule does, in
``select_ungrouped_markets`` so a refused card's slot backfills from the pool.
"""

import re
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routes.futures import _market_is_decided, select_ungrouped_markets
from tests._grouped_feed_slate import NO_SLATE, is_slate_read


def leg(prob, bid=None, ask=None, name="Yes", oid=1):
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=None if prob is None else Decimal(str(prob)),
        current_yes_bid=None if bid is None else Decimal(str(bid)),
        current_yes_ask=None if ask is None else Decimal(str(ask)),
        probability=None if prob is None else Decimal(str(prob)),
        american_odds=None,
    )


def mdict(mid, *probs):
    """A ``market_dicts`` row as the route builds it."""
    return {
        "id": mid,
        "name": f"Market {mid}",
        "outcomes": [
            {"id": mid * 10 + i, "name": f"O{i}",
             "probability": None if p is None else Decimal(str(p))}
            for i, p in enumerate(probs)
        ],
    }


#: (market id, name, legs) — the stored rows behind the four frames.
SPECIMENS = [
    (63466488, "W15 Sharm ElSheikh, Main Draw: Completed Match: Anna Sedysheva vs Andrea Popovic",
     [leg(0.995, 0.999, 1.0, "Yes", 239122725), leg(0.005, 0.0, 0.001, "No", 239122726)]),
    (63413382, "Paris FC vs. Arsenal WFC: Arsenal WFC 1st Half O/U 3.5",
     [leg(0.0005, 0.01, 0.18, "Over", 238934586), leg(0.9995, 0.82, 0.99, "Under", 238934587)]),
    (63466730, "Set 1 Winner: Alexander Rozin vs Noah Schlagenhauf",
     [leg(0.9955, 0.991, 1.0, "Alexander Rozin", 239123382),
      leg(0.0045, 0.0, 0.009, "Noah Schlagenhauf", 239123383)]),
    (63466771, "M15 Ann Arbor, MI, Main Draw: Completed Match: Oliver Bonding vs Matthew Thomson",
     [leg(0.9995, 0.99, 1.0, "Yes", 239123493), leg(0.0005, 0.0, 0.01, "No", 239123494)]),
]


class TestTheRule:
    @pytest.mark.parametrize("mid,name,legs", SPECIMENS, ids=[str(s[0]) for s in SPECIMENS])
    def test_each_stored_specimen_is_decided(self, mid, name, legs):
        m = {"id": mid, "name": name,
             "outcomes": [{"id": o.id, "name": o.name, "probability": o.probability} for o in legs]}
        assert _market_is_decided(m) is True

    def test_a_live_favourite_just_under_the_line_is_kept(self):
        """98.5% prints as "99%", not ">99%": a question a reader can still watch."""
        assert _market_is_decided(mdict(1, 0.985, 0.015)) is False

    def test_the_line_is_inclusive_at_99(self):
        assert _market_is_decided(mdict(1, 0.99, 0.01)) is True

    def test_independent_binaries_with_one_locked_leg_are_kept(self):
        """Gotcha #23: "which teams make the playoffs" — one leg at 99% beside a live 60%."""
        assert _market_is_decided(mdict(1, 0.995, 0.60, 0.40)) is False

    def test_a_lone_long_shot_is_not_decided(self):
        """A single "Yes <1%" leg is a long shot, not an answer — no leader at >99%."""
        assert _market_is_decided(mdict(1, 0.005)) is False

    def test_a_single_locked_yes_is_decided(self):
        assert _market_is_decided(mdict(1, 0.995)) is True

    def test_unpriced_legs_do_not_vote(self):
        assert _market_is_decided(mdict(1, 0.995, None)) is True
        assert _market_is_decided(mdict(1, None, None)) is False
        assert _market_is_decided({"id": 1, "outcomes": []}) is False

    def test_floats_and_bools(self):
        assert _market_is_decided({"id": 1, "outcomes": [{"probability": 0.999}, {"probability": 0.001}]}) is True
        # `True` is an int; it is not a price and must not decide a board.
        assert _market_is_decided({"id": 1, "outcomes": [{"probability": True}]}) is False


class TestAboveTheSlice:
    def test_a_decided_market_s_slot_backfills(self):
        pool = [mdict(1, 0.9995, 0.0005), mdict(2, 0.6, 0.4), mdict(3, 0.3, 0.7)]
        assert [m["id"] for m in select_ungrouped_markets(pool, set(), 2)] == [2, 3]

    def test_a_pool_with_nothing_decided_is_untouched(self):
        pool = [mdict(i, 0.55, 0.45) for i in range(1, 6)]
        assert [m["id"] for m in select_ungrouped_markets(pool, set(), 5)] == [1, 2, 3, 4, 5]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _Session:
    """One canned read; the statement is kept so its WHERE clause can be read."""

    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    async def execute(self, stmt):
        if is_slate_read(stmt):  # #10208: no slate in this pool
            return NO_SLATE
        self.statements.append(stmt)
        if len(self.statements) > 1:
            raise AssertionError("second read: this pool has nothing to fold")
        return _Result(self._rows)


class _Market:
    def __init__(self, mid, name, outcomes, sport="tennis"):
        self.id = mid
        self.name = name
        self.source = "kalshi"
        self.category = "game_prop"
        self.llm_sport_category = sport
        self.status = "open"
        self.group_id = None
        self.group_type = None
        self.market_type = None
        self.outcomes = outcomes


class _Request:
    scope: dict = {}


class _Response:
    def __init__(self):
        self.headers = {}


async def _serve(markets, limit=20):
    from app.routes.futures import grouped_feed

    session = _Session(markets)
    payload = await grouped_feed(
        request=_Request(), response=_Response(), category=None, sport=None,
        sports_only=True, limit=limit, db=session,
    )
    return payload, session


@pytest.mark.asyncio
class TestThroughTheRoute:
    async def test_no_specimen_reaches_the_payload_and_the_live_one_does(self):
        live = _Market(1, "W15 Sao Luis: Dias vs Estevez",
                       [leg(0.62, 0.60, 0.64, "Dias", 2), leg(0.38, 0.36, 0.40, "Estevez", 3)])
        pool = [_Market(mid, name, legs) for mid, name, legs in SPECIMENS] + [live]
        payload, _ = await _serve(pool)
        names = [(c.get("market") or {}).get("name") for c in payload["feed"] if c["type"] == "market"]
        assert names == ["W15 Sao Luis: Dias vs Estevez"]

    async def test_no_served_card_prints_only_extremes(self):
        """The reader's sentence: no card left on the strip is a question already answered."""
        pool = [_Market(mid, name, legs) for mid, name, legs in SPECIMENS] + [
            _Market(10 + i, f"live {i}", [leg(0.5 + i / 20, None, None, "A", 100 + i),
                                          leg(0.5 - i / 20, None, None, "B", 200 + i)])
            for i in range(5)
        ]
        payload, _ = await _serve(pool)
        for card in payload["feed"]:
            probs = [float(o["probability"]) for o in card["market"]["outcomes"]]
            assert not all(p >= 0.99 or p <= 0.01 for p in probs), card["market"]["name"]
        assert len(payload["feed"]) == 5

    async def test_the_pool_query_refuses_a_past_resolution_date(self):
        _, session = await _serve([])
        sql = str(session.statements[0].compile(compile_kwargs={"literal_binds": False}))
        where = sql.split("WHERE", 1)[1]
        assert re.search(r"futures_markets\.resolution_date IS NULL OR futures_markets\.resolution_date >=", where), where
