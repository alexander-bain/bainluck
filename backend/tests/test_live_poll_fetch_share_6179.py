"""The venue that runs first is not cut off by the other's row count (#6179).

## the ship

During a live match the page shows a **Kalshi** price that is genuinely current.
Measured on production 2026-09-14, three consecutive beats of
`prediction_market_live` (16:16:45Z / 16:18:42Z / 16:20:43Z):

    kalshi_fetched          12 / 11 / 11        of 107 markets
    budget_stops            {"kalshi_fetch": 95 / 96 / 96}
    kalshi_outcomes_updated 28 / 28 / 28
    elapsed_seconds         62.3 / 59.6 / 59.9  of a 240 s budget
    terminal                partial, every beat

Eleven of 107, the same eleven, every two minutes — and the pass finishing in a
quarter of the time it was allowed. 20 of those markets were 30 min – 3 h behind
and 17 had never been stamped at all.

## the two defects these arms are pointed at

Both are holes in #5767's own repair, not regressions of it.

**1. the per-venue reserve counts ROWS, and the window it reserves buys CALLS.**
Polymarket's loop caches by Gamma event id — every sub-market of an event is
priced by the one fetch of its parent — so on 2026-09-14 its 569 rows resolved
to **153** distinct fetch keys, against Kalshi's 107 rows / 107 keys. Counted in
rows the reserve took `144 x 569/676 = 121.2 s` and left Kalshi
`144 - 121.2 - 20 = 2.8 s` of a 144-second fetch window. A reserve that
over-counts its own work by 3.7x is not a floor for the venue it protects; it is
a ceiling on the other one. Counted in keys the same population reserves
`144 x 153/260 = 84.7 s` and Kalshi's window is 39.3 s, which fits all 107.

**2. the stalest-first key is one a whole CLASS of rows can never advance.**
`_load_live_poll_population` orders on the event-level
`win_probability_sources.<source>.updated_at`, NULLS FIRST, tie-broken on
`FuturesMarket.id`. A derivative market has no home-team win probability to
blend, so `Torino vs Roma: Total Goals`, `... : Spread`, `... : BTTS` and single
tennis matches are NULL on that key and always will be. All 17 of them held the
head of the order, the beat reached the first 11 **by id**, and position 12
(`60949849`, a LIVE tennis match) had not been fetched in **15 h 36 m**. A work
queue whose priority key the work cannot advance starves at the head — gotcha
#41 arriving through the ordering that was added to prevent it.

The repair is a second sort term, not a replacement: rows that DO carry a
blended stamp keep #5767's ordering exactly, and the tie among those that cannot
is broken by `FuturesOutcome.last_updated` — the touch-stamp the fetch below
writes unconditionally, which is to say a quantity the work advances.
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from tests.test_live_poll_commit_boundary_5682 import (  # noqa: E402
    _Event,
    _KalshiService,
    _Market,
    _Outcome,
    _PolyService,
    _Population,
    _Session,
    _leg,
    _poly_event,
    _run,
)

# `pytest.ini` runs asyncio in AUTO mode, so the coroutines below need no mark.


# --------------------------------------------------------------------------
# 1. the reserve is counted in CALLS, because calls are what the window buys
# --------------------------------------------------------------------------


class TestTheVenueReserveIsCountedInCallsAndNotInRows:
    """The clock is charged BY THE FETCHES, so the deadline is the only thing
    that can end a stage — the rig is
    `TestNeitherVenueCanBeStarvedOfTheFetchBudget`'s, and deliberately so: this
    is the same guarantee measured against a population whose rows and whose
    requests are different numbers.
    """

    @staticmethod
    def _clock(monkeypatch):
        import time

        state = {"t": 0.0}
        monkeypatch.setattr(time, "monotonic", lambda: state["t"])
        return state

    @staticmethod
    def _beat(n_kalshi: int, *, poly_rows_per_event: int, n_poly_events: int,
              poly_keyless: int = 0) -> _Population:
        """Kalshi rows 1:1 with keys; Polymarket rows MANY:1, as in production.

        `poly_rows_per_event` is the whole point: the sub-markets of one Gamma
        event carry that event's id in `market_metadata` (the #5823 contract)
        and are priced by one fetch between them.
        """
        rows, outcomes = [], []
        for i in range(1, n_kalshi + 1):
            rows.append((_Market(i, "kalshi", f"KXNFLGAME-EVT{i}"), _Event(100 + i)))
            outcomes.append(
                _Outcome(1000 + i, i, f"KXNFLGAME-EVT{i}-LAR", "Los Angeles R")
            )
        mid = 500
        for j in range(1, n_poly_events + 1):
            for _sub in range(poly_rows_per_event):
                mid += 1
                rows.append((
                    _Market(
                        mid,
                        "polymarket",
                        f"0xcondition{mid}",
                        metadata={"polymarket_event_id": f"poly-evt-{j}"},
                    ),
                    _Event(200 + mid),
                ))
                outcomes.append(_Outcome(3000 + mid, mid, f"cond-{j}", "Los Angeles R"))
        for _k in range(poly_keyless):
            mid += 1
            # No id of ANY kind: no minted event id, no group_id, no
            # external_id. `_polymarket_gamma_event_id` returns None and the
            # loop `continue`s past it without a request, so it is not work the
            # fetch window has to buy.
            rows.append((_Market(mid, "polymarket", None), _Event(200 + mid)))
            outcomes.append(_Outcome(3000 + mid, mid, f"cond-x{mid}", "Los Angeles R"))
        return _Population(rows, outcomes)

    @classmethod
    def _venues(cls, journal, clock, *, n_kalshi, poly_event_ids,
                kalshi_cost, poly_cost):
        class _SlowKalshi(_KalshiService):
            async def get_markets(self, *a, **kw):
                clock["t"] += kalshi_cost
                return await super().get_markets(*a, **kw)

        class _SlowPoly(_PolyService):
            async def get_event_by_id(self, *a, **kw):
                clock["t"] += poly_cost
                return await super().get_event_by_id(*a, **kw)

        kalshi = _SlowKalshi(
            {f"KXNFLGAME-EVT{i}": [_leg(f"KXNFLGAME-EVT{i}-LAR", f"KXNFLGAME-EVT{i}")]
             for i in range(1, n_kalshi + 1)},
            journal,
        )
        poly = _SlowPoly(
            {eid: _poly_event(f"cond-{eid.rsplit('-', 1)[-1]}")
             for eid in poly_event_ids},
            journal,
        )
        return kalshi, poly

    @staticmethod
    def _fetches(journal):
        got = [t for kind, t in journal if kind == "fetch"]
        return (
            [t for t in got if str(t).startswith("KXNFLGAME")],
            [t for t in got if str(t).startswith("poly-evt")],
        )

    async def test_many_rows_on_few_events_do_not_shrink_the_other_venues_window(
        self, monkeypatch
    ):
        """THE DEFECT ARM — production's shape, scaled down.

        20 Polymarket rows on 2 Gamma events beside 3 Kalshi keys. Counted in
        ROWS, Polymarket reserves `max(144 x 20/23, 20) = 125.2 s`, Kalshi's
        admission window is `144 - 125.2 - 20 = -1.2` -> clamped to 0, and
        **Kalshi makes no call at all** while Polymarket spends 2 seconds of the
        144 it was handed. Counted in CALLS it reserves
        `max(144 x 2/5, 20) = 57.6 s`, Kalshi gets 66.4 s and fits two of its
        three 50-second fetches.

        This is the arm the fix exists for: revert the reserve to row counting
        and Kalshi's fetch list is empty.
        """
        clock = self._clock(monkeypatch)
        journal = []
        beat = self._beat(3, poly_rows_per_event=10, n_poly_events=2)
        session = _Session([beat, beat], journal=journal)
        kalshi, poly = self._venues(
            journal, clock, n_kalshi=3,
            poly_event_ids=["poly-evt-1", "poly-evt-2"],
            kalshi_cost=50, poly_cost=1,
        )

        stats = await _run(monkeypatch, session, kalshi=kalshi, poly=poly)

        kalshi_fetches, poly_fetches = self._fetches(journal)
        assert kalshi_fetches, (
            "Kalshi made ZERO venue calls — its admission window was spent on "
            "Polymarket ROWS that collapse onto a handful of requests. "
            f"budget_stops={stats.get('budget_stops')}"
        )
        assert len(kalshi_fetches) == 2, (
            "Kalshi should fit two 50 s fetches inside a 66.4 s window: "
            f"{kalshi_fetches}"
        )
        # The other venue is not paid for out of this: its floor still holds.
        assert len(poly_fetches) == 2, poly_fetches

    async def test_the_rows_really_do_collapse_onto_one_call_per_event(
        self, monkeypatch
    ):
        """THE CONTROL THAT STOPS THE ARM ABOVE BEING VACUOUS.

        The whole argument is that 20 rows are 2 requests. If the loop ever
        stopped caching by Gamma event id, the reserve above would be
        under-counting rather than the old one over-counting, and the arm above
        would be asserting the wrong direction for the right reason. So: count
        the requests, on a population with no time pressure at all.
        """
        clock = self._clock(monkeypatch)
        journal = []
        beat = self._beat(0, poly_rows_per_event=10, n_poly_events=2)
        session = _Session([beat, beat], journal=journal)
        kalshi, poly = self._venues(
            journal, clock, n_kalshi=0,
            poly_event_ids=["poly-evt-1", "poly-evt-2"],
            kalshi_cost=0, poly_cost=0,
        )

        await _run(monkeypatch, session, kalshi=kalshi, poly=poly)

        _kalshi_fetches, poly_fetches = self._fetches(journal)
        assert sorted(poly_fetches) == ["poly-evt-1", "poly-evt-2"], (
            "20 Polymarket rows must cost 2 requests, one per Gamma event: "
            f"{poly_fetches}"
        )

    async def test_rows_with_no_fetch_key_reserve_nothing(self, monkeypatch):
        """A row the loop never requests is not work the window has to buy.

        Four Polymarket rows with no id of any kind — no minted event id, no
        `group_id`, no `external_id` — beside three 65 s Kalshi keys. The loop
        `continue`s past every one of them without a call, so Polymarket's
        reserve is zero and Kalshi keeps the whole 144 s window and runs all
        three. Counted in rows they reserve `max(144 x 4/7, 20) = 82.3 s` and
        Kalshi is cut to 41.7 s — one fetch — to protect requests that are
        never made.

        THE COST IS 65 s AND NOT 50 s ON PURPOSE. At 50 s the third fetch is
        admitted at t=100, which clears 144 and 124 alike, so the arm could not
        see the OTHER half of the branch: the 20-second per-item wall is also
        subtracted only when the other venue has calls to make, and subtracting
        it unconditionally survived this arm at 50 s. At 65 s the third fetch is
        admitted at t=130 — inside the whole window, outside the walled one —
        so both halves of `if _polymarket_calls` are load-bearing here.

        This is also the arm that holds the divide: with no Kalshi rows and no
        resolvable Polymarket key the call total is ZERO, which the row count
        never could be on a non-empty population.
        """
        clock = self._clock(monkeypatch)
        journal = []
        beat = self._beat(3, poly_rows_per_event=0, n_poly_events=0, poly_keyless=4)
        session = _Session([beat, beat], journal=journal)
        kalshi, poly = self._venues(
            journal, clock, n_kalshi=3, poly_event_ids=[],
            kalshi_cost=65, poly_cost=1,
        )

        stats = await _run(monkeypatch, session, kalshi=kalshi, poly=poly)

        kalshi_fetches, poly_fetches = self._fetches(journal)
        assert len(kalshi_fetches) == 3, (
            "Kalshi was charged a reserve for Polymarket requests that are "
            f"never made: {kalshi_fetches}, budget_stops={stats.get('budget_stops')}"
        )
        assert poly_fetches == [], poly_fetches

    async def test_the_per_item_wall_is_subtracted_from_the_first_venue(
        self, monkeypatch
    ):
        """CERT-2774's OTHER half, which nothing was holding.

        The reserve is only a floor because the first venue's admission
        boundary is pulled back by the per-item wall as well as by the share:
        the deadline is tested BEFORE a fetch, so the last item admitted a
        millisecond inside the boundary then runs for up to
        `_LIVE_POLL_VENUE_CALL_TIMEOUT_SECONDS` and can spend the reserve it was
        supposed to leave. #5767's own arms do not see this — at their 2 s call
        cost the 20 s floor absorbs the overshoot either way — so the mutant
        that stops subtracting the wall survived the whole suite.

        Six Kalshi keys at 30 s against one Polymarket key. Reserve
        `max(144 x 1/7, 20) = 20.6 s`, so Kalshi's boundary is
        `144 - 20.6 - 20 = 103.4`: it admits at 0/30/60/90 and finishes at 120,
        inside Polymarket's 144. Without the wall term the boundary is 123.4, it
        admits a fifth at 120, finishes at **150**, and Polymarket — which is
        admitted, not pre-empted — gets nothing at all.

        I own this arm because #6179 rewrites the condition the wall term hangs
        on (`if polymarket_ids` -> `if _polymarket_calls`), and a branch nothing
        tests is one a later edit deletes for free.
        """
        clock = self._clock(monkeypatch)
        journal = []
        beat = self._beat(6, poly_rows_per_event=1, n_poly_events=1)
        session = _Session([beat, beat], journal=journal)
        kalshi, poly = self._venues(
            journal, clock, n_kalshi=6, poly_event_ids=["poly-evt-1"],
            kalshi_cost=30, poly_cost=1,
        )

        stats = await _run(monkeypatch, session, kalshi=kalshi, poly=poly)

        kalshi_fetches, poly_fetches = self._fetches(journal)
        assert len(poly_fetches) == 1, (
            "the first venue overran its boundary by a whole item and spent the "
            f"reserve: kalshi={len(kalshi_fetches)} poly={poly_fetches} "
            f"budget_stops={stats.get('budget_stops')}"
        )
        assert len(kalshi_fetches) == 4, kalshi_fetches

    async def test_a_keyless_only_population_does_not_divide_by_zero(
        self, monkeypatch
    ):
        """The call total CAN be zero where the row count cannot.

        `pop.rows` is non-empty — the beat has work to plan — and yet neither
        venue has a request to make. The old denominator was
        `len(kalshi_ids) + len(polymarket_ids)`, which is guaranteed positive
        whenever the population is non-empty; counting calls gives up that
        guarantee, so the branch has to hold it instead of the arithmetic.
        """
        clock = self._clock(monkeypatch)
        journal = []
        beat = self._beat(0, poly_rows_per_event=0, n_poly_events=0, poly_keyless=3)
        session = _Session([beat, beat], journal=journal)
        kalshi, poly = self._venues(
            journal, clock, n_kalshi=0, poly_event_ids=[],
            kalshi_cost=0, poly_cost=0,
        )

        stats = await _run(monkeypatch, session, kalshi=kalshi, poly=poly)

        assert stats["terminal"] == "complete", stats
        assert stats.get("budget_stops") in (None, {}), stats.get("budget_stops")


# --------------------------------------------------------------------------
# 2. the head of the queue is ordered by something the work advances
# --------------------------------------------------------------------------
#
# Asserted on the statement the session is handed, for the reason the #5767
# arms give: the fake cannot sort, so the SQL itself is the only honest place
# to read an ordering.


def _order_by(monkeypatch_session_sql: str) -> str:
    return " ".join(monkeypatch_session_sql.split()).split("ORDER BY", 1)[1]


async def _population_sql(monkeypatch) -> str:
    captured: dict = {}
    journal = []
    beat = _Population(
        [(_Market(1, "kalshi", "KXNFLGAME-EVT1"), _Event(101))],
        [_Outcome(1001, 1, "KXNFLGAME-EVT1-LAR", "Los Angeles R")],
    )

    def _capture(kind, n, stmt):
        if kind == "population" and "sql" not in captured:
            captured["sql"] = str(
                stmt.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            )
        return None

    session = _Session([beat, beat], journal=journal, on_execute=_capture)
    kalshi = _KalshiService(
        {"KXNFLGAME-EVT1": [_leg("KXNFLGAME-EVT1-LAR", "KXNFLGAME-EVT1")]}, journal
    )
    await _run(monkeypatch, session, kalshi=kalshi)
    return captured["sql"]


class TestTheNullStampGroupIsNotOrderedByAStaticId:
    async def test_the_tie_is_broken_by_the_touch_stamp_the_fetch_writes(
        self, monkeypatch
    ):
        """THE DEFECT ARM.

        Every derivative market's blended stamp is NULL and stays NULL, so the
        primary key cannot tell 17 of them apart and the tiebreak decides the
        whole beat. `FuturesMarket.id` is the same answer forever; the market's
        own `last_updated` is one the fetch below advances.
        """
        order_by = _order_by(await _population_sql(monkeypatch))
        lowered = order_by.lower()

        assert "max(futures_outcomes.last_updated)" in lowered, (
            "the NULL-stamp group is ordered by nothing the work advances: "
            f"{order_by}"
        )
        # CORRELATED to the row being ordered. A `max()` over the whole table
        # is one value for every market, which orders nothing at all.
        assert "futures_outcomes.market_id = futures_markets.id" in lowered, (
            "the touch-stamp term is not correlated to the market it is "
            f"ordering: {order_by}"
        )

    async def test_the_touch_stamp_and_not_the_price_change_stamp(self, monkeypatch):
        """The near-miss that would rebuild the livelock in a quieter form.

        `price_changed_at` (models.py, #2024) is the sibling column and the
        wrong one: it advances only when a price MOVES, so a market being
        fetched every beat and quoting a steady number would sit at the head of
        the queue forever — the same starvation, now invisible because the rows
        really are being read. `last_updated` is the unconditional touch-stamp
        and says "when did the poller last SEE this row", which is the question
        the ordering is asking.
        """
        order_by = _order_by(await _population_sql(monkeypatch)).lower()
        assert "price_changed_at" not in order_by, order_by

    async def test_the_blended_stamp_is_still_the_primary_key(self, monkeypatch):
        """A REFINEMENT, NOT A REPLACEMENT.

        #5767's ordering is the number the ship is about and rows that can carry
        it must keep it. The new term orders WITHIN a tie, so it comes second;
        promoting it would re-rank the whole population on a quantity that is
        advanced by any writer, not just by the stamp the reader sees.
        """
        order_by = _order_by(await _population_sql(monkeypatch)).lower()
        blended = order_by.index("jsonb_extract_path_text")
        touch = order_by.index("max(futures_outcomes.last_updated)")
        assert blended < touch, order_by

    async def test_the_static_id_is_last_and_still_there(self, monkeypatch):
        """It is the total order, and it must not be the deciding one.

        Last: a deterministic final tiebreak keeps the plan reproducible when
        two rows are genuinely indistinguishable. Not earlier: `id ASC` ahead of
        the touch-stamp is the defect this file is named for.
        """
        order_by = _order_by(await _population_sql(monkeypatch)).lower()
        touch = order_by.index("max(futures_outcomes.last_updated)")
        assert "futures_markets.id asc" in order_by, order_by
        assert order_by.index("futures_markets.id asc") > touch, order_by

    async def test_a_never_fetched_row_sorts_first_on_the_tiebreak_too(
        self, monkeypatch
    ):
        """NULLS FIRST on both terms, for the same reason.

        A market with no outcome row has never been fetched by anybody; it is
        the stalest thing in the tie, and Postgres would sort it LAST by default
        on an ASC order — exactly backwards, which is the mistake #5767 called
        out on the primary key and which the second term can make on its own.
        """
        order_by = " ".join(
            _order_by(await _population_sql(monkeypatch)).upper().split()
        )
        assert order_by.count("NULLS FIRST") == 2, order_by

    async def test_the_tiebreak_is_not_cast_to_a_timestamp(self, monkeypatch):
        """#5767's rule, which the new term must not quietly break.

        The blended stamp is compared as TEXT so one malformed row cannot raise
        the whole population read. The touch-stamp is a `timestamptz` compared
        against itself and needs no conversion at all — so there is still no
        cast anywhere in the ordering, and this arm keeps it that way.
        """
        order_by = _order_by(await _population_sql(monkeypatch)).upper()
        assert "CAST" not in order_by, order_by
