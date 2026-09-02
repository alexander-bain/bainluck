"""#2637 — the resolved-status sync could only ever see 2021, and what replaced it.

`_sync_polymarket_resolved_status` paged `/events?active=false&closed=true` by
`offset` up to `max_events = 100000`. Two facts about Gamma, both measured live
2026-09-02, made that structurally incapable of reaching a recent event:

1. **`offset` caps at 2000.** `offset=2100` → HTTP 422 *"offset too large, use
   /events/keyset for deeper pagination"*. The loop's ceiling was unreachable by
   a factor of 50.
2. **With no `order`, Gamma serves oldest-first.** `offset=0&closed=true`
   returns event ids 2890/2891/2892, startDates 2021-12-04 / 2021-10-31 /
   2021-09-26.

So every run re-read the same ~2,000 closed events from 2021 and nothing newer
was ever marked resolved: **32,090 markets across 22,092 events carried `open`
while finished**, some since 2020. Downstream that is the blocker the task's own
docstring names — calibration, winner backfill, snapshot backfill.

Copying #219E's `order="startDate", ascending=False` onto the scan is the
obvious repair and drains ~nothing: on `closed=true` the newest reachable 2,000
events span ~1.5 days and are essentially all hourly crypto, which ingest skips.

The fix addresses events **by id from our own rows** instead. Two things then
have to be true that were free before, and they are what this file guards:

* **The closed test moves onto each leg.** A paged `closed=true` scan could take
  every condition id it saw, because the filter had vouched for them. A direct
  fetch has no filter. Measured on a 460-event sample of the stuck population:
  297 events were still open and **8 of them carried closed legs anyway** —
  event `92611` ("Which states will Donald Trump visit in 2026?") has 24 of 50
  legs `closed` + `umaResolutionStatus: resolved` quoting a terminal
  `["1","0"]`, while the other 26 quote live mid prices like `["0.535","0.465"]`.
  An event-level rule either misses all 24 or resolves all 26 live ones.
* **Never by staleness.** 407 of the sample's 779 stuck rows are long-horizon
  futures that are legitimately open — "Illinois Senate Election Winner" (ends
  2026-11-03), "Liga MX: 2026-27 Largest Goal Differential" (ends 2027-06-13),
  "Negative GDP growth in 2026?". Any age-keyed sweep resolves every one of
  them and manufactures the resolved-but-never-graded cohort #2637 warns about.

The task tests here EXECUTE the real function against a fake Gamma that serves
BOTH the old paging call and the new id-addressed one, so the pre-fix code takes
its own path on the same payload and fails on the defect rather than on a
missing method (ruling 050 — a control that cannot fail measures nothing).
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

import app.services.polymarket_api as poly_api_mod
import app.tasks.polymarket as poly_mod
import app.tasks.redis_state as redis_state


# ---------------------------------------------------------------------------
# The pure reader: which legs did the venue say are over
# ---------------------------------------------------------------------------


class TestSettledLegs:
    """`settled_legs` — venue truth, leg by leg."""

    def _legs(self, raw):
        # Lazy import so the task-level guards below still collect (and stay
        # discriminating) in a tree where this module does not exist yet.
        from app.utils.polymarket_settlement_scan import settled_legs

        return settled_legs(raw)

    def test_a_closed_leg_on_an_open_event_is_settled(self):
        """Event 92611's shape: the event trades on, 24 of its legs are over."""
        legs = self._legs(
            {
                "id": "92611",
                "closed": False,
                "markets": [
                    {
                        "conditionId": "0xalaska",
                        "closed": True,
                        "outcomePrices": '["1", "0"]',
                    },
                    {
                        "conditionId": "0xalabama",
                        "closed": False,
                        "outcomePrices": '["0.535", "0.465"]',
                    },
                ],
            }
        )
        assert legs.settled_condition_ids == ("0xalaska",)
        assert legs.open_condition_ids == ("0xalabama",)
        assert legs.event_closed is False

    def test_a_live_leg_is_never_settled_by_its_event(self):
        """The direction that loses money: 26 live legs on a settling event."""
        legs = self._legs(
            {
                "id": "92611",
                "closed": True,
                "markets": [
                    {
                        "conditionId": "0xlive",
                        "closed": False,
                        "outcomePrices": '["0.53", "0.47"]',
                    }
                ],
            }
        )
        assert legs.settled_condition_ids == ()
        assert "0xlive" in legs.open_condition_ids

    def test_closed_is_tested_by_identity_not_truthiness(self):
        """Resolution is a one-way write, so it fails closed.

        A missing key, a `None`, and the STRING `"false"` must all fail the
        test. `"false"` is the one that matters: it is truthy in Python, so a
        `if market.get("closed")` spelling would settle a live market on a
        payload that explicitly said it was open.
        """
        for flag in ({}, {"closed": None}, {"closed": "false"}, {"closed": 0}):
            legs = self._legs(
                {"id": "1", "markets": [{"conditionId": "0xa", **flag}]}
            )
            assert legs.settled_condition_ids == (), flag

    def test_terminal_legs_are_split_from_merely_closed_ones(self):
        """Closed is not gradable. CAL-P086A's specimen is the 0.60/0.40."""
        legs = self._legs(
            {
                "id": "1",
                "markets": [
                    {
                        "conditionId": "0xwin",
                        "closed": True,
                        "outcomePrices": '["0.99", "0.01"]',
                    },
                    {
                        "conditionId": "0xlose",
                        "closed": True,
                        "outcomePrices": '["0.01", "0.99"]',
                    },
                    {
                        "conditionId": "0xungraded",
                        "closed": True,
                        "outcomePrices": '["0.60", "0.40"]',
                    },
                ],
            }
        )
        assert set(legs.settled_condition_ids) == {"0xwin", "0xlose", "0xungraded"}
        assert set(legs.terminal_condition_ids) == {"0xwin", "0xlose"}

    def test_a_malformed_price_loses_the_grade_not_the_batch(self):
        """One bad leg must not take the other 99 events with it (gotcha #42)."""
        legs = self._legs(
            {
                "id": "1",
                "markets": [
                    {
                        "conditionId": "0xbad",
                        "closed": True,
                        "outcomePrices": "not json",
                    },
                    {
                        "conditionId": "0xgood",
                        "closed": True,
                        "outcomePrices": '["1", "0"]',
                    },
                ],
            }
        )
        assert set(legs.settled_condition_ids) == {"0xbad", "0xgood"}
        # Closed with no readable price: resolvable, but with nothing to grade.
        assert legs.terminal_condition_ids == ("0xgood",)

    def test_an_event_with_no_markets_is_an_answer_not_a_failure(self):
        """`None` means "no id to key on". An empty market list means "nothing
        of this event is settled" — collapsing the two would let a parse failure
        read as a settlement."""
        assert self._legs({"id": "1", "markets": []}).settled_condition_ids == ()
        assert self._legs({"id": "1"}) is not None
        assert self._legs({"markets": []}) is None


# ---------------------------------------------------------------------------
# The batch call: Gamma's two undocumented bounds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetEventsByIdsIsHonestAboutItsBounds:
    """Measured 2026-09-02 against live Gamma; both halves bite."""

    def _service(self, captured):
        svc = poly_api_mod.PolymarketAPIService.__new__(
            poly_api_mod.PolymarketAPIService
        )

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return []

        class _Client:
            async def get(self, path, params=None):
                captured.append((path, list(params or [])))
                return _Resp()

        svc.gamma_client = _Client()
        return svc

    async def test_it_sends_an_explicit_limit(self):
        """Gamma's default page size is 20 and it applies to an id-addressed
        request: 100 ids with no `limit` returned 20 events, 200, no warning.

        Under this method's own contract ("ids it does not recognise are simply
        absent") a truncated page is indistinguishable from 80 unknown ids —
        the caller records them as absent and moves on. Gotcha #53: an empty 200
        is a response shape, not an absence.
        """
        captured = []
        svc = self._service(captured)

        await svc.get_events_by_ids([str(i) for i in range(50)])

        _path, params = captured[0]
        assert ("limit", "50") in params, (
            "no explicit limit was sent, so Gamma's default page size of 20 "
            f"silently truncates this 50-id batch; params={params}"
        )

    async def test_it_refuses_a_batch_gamma_would_reject(self):
        """101 ids → HTTP 422 `expected array length <= 100`. Chunking is the
        call site's decision to make visibly, not this method's to paper over.
        """
        captured = []
        svc = self._service(captured)

        with pytest.raises(ValueError, match="100"):
            await svc.get_events_by_ids([str(i) for i in range(101)])

        assert captured == [], "it called Gamma with a batch it knew would 422"

    async def test_the_boundary_itself_is_allowed(self):
        captured = []
        svc = self._service(captured)

        await svc.get_events_by_ids([str(i) for i in range(100)])

        assert captured, "100 is Gamma's documented maximum and must pass"


# ---------------------------------------------------------------------------
# The task: what it reaches, and what it refuses to write
# ---------------------------------------------------------------------------


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = str(value)

    def delete(self, key):
        self.store.pop(key, None)
        return 1


class _Harness:
    """Drives the real task against a fake Gamma that serves BOTH call shapes.

    Serving `get_events` as well as `get_events_by_ids` is what makes these
    guards discriminating rather than merely broken on the pre-fix tree: the old
    offset scan finds its own method and the same payload, takes every condition
    id off it, and fails on the defect.
    """

    def __init__(self, events):
        self.events = list(events)
        self.by_id = {str(e["id"]): e for e in self.events}
        self.statements = []
        self.paged_calls = []
        self.id_calls = []

    def install(self, monkeypatch, open_count=5, stale_open=32090):
        monkeypatch.setattr(
            redis_state, "get_redis_client", lambda *a, **k: _FakeRedis()
        )

        class _Scalar:
            def __init__(self, v):
                self._v = v

            def scalar(self):
                return self._v

        class _Rows:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        harness = self

        async def _execute(stmt, params=None):
            sql = str(getattr(stmt, "text", stmt))
            if "ORDER BY eid::bigint" in sql:
                return _Rows([(str(e["id"]),) for e in harness.events])
            if "commence_time" in sql and "count(*)" in sql:
                return _Scalar(stale_open)
            if "COUNT(*)" in sql or "count(*)" in sql:
                return _Scalar(open_count)
            harness.statements.append((sql, dict(params or {})))
            return MagicMock(rowcount=1)

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=_execute)
        session.commit = AsyncMock()

        class _CM:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *a):
                return False

        monkeypatch.setattr(poly_mod, "get_task_session", lambda: _CM())

        class _Service:
            def __init__(self, *a, **k):
                pass

            async def get_events(self, **kw):
                # The pre-fix path. Serves the whole population once, then
                # empties, exactly as a real page walk would.
                harness.paged_calls.append(kw)
                if len(harness.paged_calls) == 1:
                    return harness.events
                return []

            async def get_events_by_ids(self, event_ids):
                harness.id_calls.append(list(event_ids))
                return [
                    harness.by_id[str(i)]
                    for i in event_ids
                    if str(i) in harness.by_id
                ]

            async def close(self):
                return None

        monkeypatch.setattr(poly_api_mod, "PolymarketAPIService", _Service)
        return self

    @property
    def resolve_params(self):
        return [
            p
            for s, p in self.statements
            if "UPDATE futures_markets" in s and "status = 'resolved'" in s
        ]


#: Event 92611's measured shape, reduced to two legs: the venue says one is over
#: and one is still trading, on an event that is itself still open.
MIXED_EVENT = {
    "id": "92611",
    "closed": False,
    "markets": [
        {
            "conditionId": "0xsettled",
            "closed": True,
            "outcomePrices": '["1", "0"]',
        },
        {
            "conditionId": "0xtrading",
            "closed": False,
            "outcomePrices": '["0.535", "0.465"]',
        },
    ],
}

#: A long-horizon future: commence_time long past, nothing settled. The class
#: that an age-keyed sweep destroys.
LONG_HORIZON_EVENT = {
    "id": "57646",
    "closed": False,
    "markets": [
        {
            "conditionId": "0xillinois",
            "closed": False,
            "outcomePrices": '["0.62", "0.38"]',
        }
    ],
}


@pytest.mark.asyncio
class TestTheSweepReachesTheWholePopulation:
    async def test_it_does_not_walk_gamma_by_offset(self, monkeypatch):
        """The defect itself. `offset` caps at 2000 and defaults oldest-first,
        so a page walk is bounded away from every recent event forever."""
        h = _Harness([MIXED_EVENT]).install(monkeypatch)

        await poly_mod._sync_polymarket_resolved_status()

        assert h.paged_calls == [], (
            "the sync is still paging Gamma by offset — that scan caps at "
            f"offset 2000 and serves oldest-first; calls={h.paged_calls}"
        )
        assert h.id_calls, "nothing addressed Gamma by id"

    async def test_the_ids_it_asks_for_come_from_our_own_rows(self, monkeypatch):
        """Bounded by our database, not by Gamma's ordering — which is why no
        crypto flood can crowd the population out."""
        h = _Harness([MIXED_EVENT, LONG_HORIZON_EVENT]).install(monkeypatch)

        await poly_mod._sync_polymarket_resolved_status()

        assert sorted(sum(h.id_calls, [])) == ["57646", "92611"], h.id_calls

    async def test_it_chunks_within_gammas_batch_limit(self, monkeypatch):
        """101 ids is a 422. The chunk is the call site's job."""
        events = [
            {
                "id": str(1000 + i),
                "closed": True,
                "markets": [
                    {
                        "conditionId": f"0x{i:04x}",
                        "closed": True,
                        "outcomePrices": '["1", "0"]',
                    }
                ],
            }
            for i in range(250)
        ]
        h = _Harness(events).install(monkeypatch)

        await poly_mod._sync_polymarket_resolved_status()

        assert h.id_calls, "nothing was fetched"
        assert max(len(c) for c in h.id_calls) <= 100, (
            f"a batch exceeded Gamma's 100-id limit: "
            f"{[len(c) for c in h.id_calls]}"
        )
        assert sum(len(c) for c in h.id_calls) == 250, h.id_calls


@pytest.mark.asyncio
class TestItResolvesOnlyWhatTheVenueClosed:
    async def test_a_live_leg_is_never_marked_resolved(self, monkeypatch):
        """THE guard. Direct addressing has no `closed=true` filter in front of
        it, so a payload's live legs arrive beside its settled ones. Taking the
        whole event — which is all the old scan ever had to do — writes a
        trading market as settled and poisons the calibration population."""
        h = _Harness([MIXED_EVENT]).install(monkeypatch)

        await poly_mod._sync_polymarket_resolved_status()

        assert h.resolve_params, "nothing was resolved at all"
        raw = h.resolve_params[0]["raw_cids"]
        assert "0xtrading" not in raw, (
            "a leg Gamma reports as OPEN, quoting a live 0.535/0.465, was "
            f"marked resolved; raw_cids={raw}"
        )
        assert raw == ["0xsettled"], raw

    async def test_the_settled_leg_of_an_open_event_is_still_reached(
        self, monkeypatch
    ):
        """The other direction, and the reason an event-level rule is wrong:
        24 of event 92611's 50 legs are settled and graded while the event
        itself trades on. A `closed=true` page walk cannot see them at all."""
        h = _Harness([MIXED_EVENT]).install(monkeypatch)

        await poly_mod._sync_polymarket_resolved_status()

        params = h.resolve_params[0]
        assert params["raw_cids"] == ["0xsettled"]
        assert params["terminal_raw"] == ["0xsettled"], params

    async def test_a_long_horizon_future_is_left_alone(self, monkeypatch):
        """The control #2637 asked for by name: a market whose `commence_time`
        is long past but which has NOT settled must survive the sweep. 407 of
        779 sampled stuck rows are this class."""
        h = _Harness([LONG_HORIZON_EVENT]).install(monkeypatch)

        stats = await poly_mod._sync_polymarket_resolved_status()

        assert h.resolve_params == [], (
            "an open long-horizon future was marked resolved; "
            f"params={h.resolve_params}"
        )
        assert stats["events_fully_open"] == 1, stats

    async def test_an_ungradeable_close_still_records_why(self, monkeypatch):
        """CAL-P086A's contract, carried through the rewrite unchanged: closed
        with no readable winner is resolvable, but the reason is written."""
        from app.utils.resolved_write_gate import (
            REASON_CLOSED_WITHOUT_TERMINAL_PRICE,
        )

        h = _Harness(
            [
                {
                    "id": "3",
                    "closed": True,
                    "markets": [
                        {
                            "conditionId": "0xungraded",
                            "closed": True,
                            "outcomePrices": '["0.60", "0.40"]',
                        }
                    ],
                }
            ]
        ).install(monkeypatch)

        stats = await poly_mod._sync_polymarket_resolved_status()

        params = h.resolve_params[0]
        assert params["terminal_raw"] == [], params
        assert REASON_CLOSED_WITHOUT_TERMINAL_PRICE in json.dumps(
            params["reason_stamp"]
        )
        assert stats["resolved_without_winner_proof"] == 1, stats


@pytest.mark.asyncio
class TestTheRunReportsTheClassItExistsToDrain:
    async def test_it_counts_stale_open_before_and_after(self, monkeypatch):
        """The durable instrument. A run that resolves markets outside the
        class #2637 named must not read as progress against it, and a run that
        resolves nothing must say so in the same units as the bug report
        (gotcha #53)."""
        h = _Harness([MIXED_EVENT]).install(monkeypatch, stale_open=32090)

        stats = await poly_mod._sync_polymarket_resolved_status()

        assert stats["stale_open_before"] == 32090, stats
        assert "stale_open_after" in stats, stats

    async def test_a_full_sweep_is_distinguishable_from_a_truncated_one(
        self, monkeypatch
    ):
        """"Swept everything and found nothing left" and "gave up early" are
        different runs and must not return the same shape."""
        h = _Harness([MIXED_EVENT]).install(monkeypatch)

        stats = await poly_mod._sync_polymarket_resolved_status()

        assert stats["swept_full_population"] is True, stats
        assert stats["population_events"] == 1, stats

    async def test_ids_gamma_does_not_answer_for_are_counted(self, monkeypatch):
        """Only meaningful because the batch now sends an explicit `limit`:
        before that, a short page meant "truncated" and this counter would have
        been a lie."""
        h = _Harness([MIXED_EVENT]).install(monkeypatch)
        h.by_id = {}  # Gamma knows none of them

        stats = await poly_mod._sync_polymarket_resolved_status()

        assert stats["events_requested"] == 1, stats
        assert stats["events_not_found"] == 1, stats


class TestTheNeedleDoesNotExcuseTheDefect:
    """The refinement that had to be measured before it could be refused."""

    def test_the_census_does_not_filter_on_resolution_date(self):
        """The obvious refinement, and the measurement that killed it.

        Many stale-open rows are legitimately open long-horizon futures, so the
        tempting move is to excuse the ones whose `resolution_date` is still in
        the future and call the remainder "the part with no innocent reading".
        Measured 2026-09-02 on the 460-event sample: of the 371 stuck rows
        behind events **Gamma itself reports closed** — finished, by the venue's
        own statement — **265 (71%) carry a future `resolution_date`**.

        The filter would have excused 71% of the real defect. `resolution_date`
        is a hint written at ingest, not a settlement fact. This asserts the
        negative because that is the whole claim: no such predicate, ever.
        """
        from app.utils.polymarket_settlement_scan import STALE_OPEN_CENSUS_SQL

        assert "resolution_date" not in STALE_OPEN_CENSUS_SQL, (
            "the census excuses rows by resolution_date — measured 2026-09-02, "
            "265 of 371 rows behind Gamma-confirmed-CLOSED events carry a "
            "future resolution_date, so this hides 71% of the defect"
        )

    def test_the_census_columns_match_the_dataclass_order(self):
        """Positional unpacking with no names on the wire is a silent swap."""
        from app.utils.polymarket_settlement_scan import (
            STALE_OPEN_CENSUS_SQL,
            StaleOpenCensus,
        )

        selected = [
            line.split(" AS ")[1].strip().rstrip(",")
            for line in STALE_OPEN_CENSUS_SQL.splitlines()
            if " AS " in line
        ]
        fields = list(StaleOpenCensus.__dataclass_fields__)
        assert selected == fields[: len(selected)], (
            f"census selects {selected} but the dataclass reads "
            f"{fields[: len(selected)]} positionally"
        )

    def test_the_needle_endpoint_is_mounted(self):
        """Gotcha #2: an admin endpoint that is not mounted is not an
        instrument, and this one is the whole "it cannot hide again" clause."""
        from app.main import app

        assert "/api/admin/polymarket/stale-open" in {
            getattr(r, "path", None) for r in app.routes
        }


class TestOneDefinitionOfWhichGammaEventAnswersForARow:
    def test_the_price_refresh_path_uses_the_shared_expression(self):
        """Two copies of settlement id-reconciliation is how truth drifts.

        Polymarket rows arrive under two keying conventions — negRisk field rows
        carry the event id in `external_id`, decomposed sub-market rows carry a
        `0x` condition id there and the event id in metadata/`group_id` — and
        both the price-refresh path and this sweep have to reconcile them the
        same way or they disagree about which event answers for a row.
        """
        from app.tasks.futures_price_refresh import _POLY_EVENT_ID_SQL
        from app.utils.polymarket_settlement_scan import GAMMA_EVENT_ID_EXPR

        assert GAMMA_EVENT_ID_EXPR in _POLY_EVENT_ID_SQL
