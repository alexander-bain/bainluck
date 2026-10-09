"""#9462 review — a genuinely live game keeps receiving prices as eligibility changes.

Two gaps the independent review of #9462 (`67a4052b8c`) found, each driven
through the REAL consumer over the REAL service (only the socket, the session,
the Gamma top-up and the blend's database batch are faked):

1. ADMISSION COUNTED SELECTED EVENTS, NOT MAPPED LEGS. An event on the slate
   whose token lookup failed was "subscribed" with nothing on the wire, so when
   it turned live the reread found nothing missing and it waited out the 600 s
   timer. A streaming prop hid a missing moneyline the same way.
2. A RECYCLE DROPPED OWED BLEND STAMPS. The final drain stops once the price
   buffer is empty, so a price committed inside the 2 s throttle kept its raw
   value but never reached the card until another tick or the 120 s poll — the
   next run's refresher started empty.
"""

import asyncio

import pytest
import websockets

import app.services.kalshi_ws as kalshi_svc
import app.tasks.kalshi_ws as kalshi_task
import app.tasks.live_blend_refresh as lbr
import app.tasks.polymarket_token_topup as topup
import app.tasks.polymarket_ws as poly_task
import app.tasks.ws_admission as admission


# ---------------------------------------------------------------- fakes ----


class _QuietSocket:
    async def send(self, _payload):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(3600)
        raise StopAsyncIteration  # pragma: no cover


class _QuietConnect:
    async def __aenter__(self):
        return _QuietSocket()

    async def __aexit__(self, *_exc):
        return False


def _install_quiet_socket(monkeypatch):
    monkeypatch.setattr(websockets, "connect", lambda *a, **kw: _QuietConnect())
    monkeypatch.setattr(kalshi_svc, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(kalshi_svc, "_sign_ws_request", lambda _k, _i: {})


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


def _is_poly_open_contract_read(stmt) -> bool:
    """#9484: the Polymarket open-contract admission read. It runs beside the
    watcher, so it is routed by statement rather than by position, and
    answered as "no open contracts" so this file's slate and reread keep
    their own sequence."""
    from app.tasks.polymarket_open_contracts import (
        open_contract_markets_stmt, open_contract_outcomes_stmt,
    )

    return str(stmt) in {
        str(open_contract_markets_stmt()), str(open_contract_outcomes_stmt()),
    }


def _install_session(monkeypatch, slate_batches, reread):
    """Slate queries answered in order; every later query is the reread, whose
    rows are `(event_id, market_id, source_entry)`. `reread(n)` gets the
    1-based call number (call 1 is the watcher's baseline)."""
    import app.tasks.base as task_base

    state = {"slate": [list(b) for b in slate_batches], "reread_calls": 0}

    class _Session:
        async def execute(self, _stmt):
            if _is_poly_open_contract_read(_stmt):
                return _Result([])
            if state["slate"]:
                return _Result(state["slate"].pop(0))
            state["reread_calls"] += 1
            return _Result(reread(state["reread_calls"]))

    class _Ctx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())
    return state


#: The two runs that go to their timer and then count rereads. The count only
#: has to prove the watcher compared at least once after its baseline (the
#: #9418 file's `_AT_LEAST_ONE_COMPARISON`); a wall-clock ">= 5" in 0.3 s was a
#: bet on the runner and lost it on a loaded CI shard (CI 37634905380: 1 call,
#: the baseline only). A 2 s window leaves room for a stall without making the
#: count mean anything more.
_HELD_RUN_REFRESH_SECONDS = 2.0
_AT_LEAST_ONE_COMPARISON = 2


def _timing(monkeypatch, module, *, refresh, check=0.01, floor=0):
    monkeypatch.setattr(module, "SUBSCRIPTION_REFRESH_SECONDS", refresh)
    monkeypatch.setattr(admission, "ADMISSION_CHECK_SECONDS", check)
    monkeypatch.setattr(admission, "ADMISSION_MIN_RECYCLE_SECONDS", floor)


def _gamma_down(monkeypatch):
    async def _boom(*_a, **_kw):
        raise RuntimeError("gamma down")

    monkeypatch.setattr(topup, "topup_clob_tokens", _boom)
    monkeypatch.setattr(topup, "topup_outcome_clob_tokens", _boom)


def _verified(*market_ids):
    record = {"v": 1, "status": "verified", "market_id": market_ids[0]}
    if len(market_ids) > 1:
        record["contributors"] = [{"market_id": m} for m in market_ids]
    # The venue's whole `win_probability_sources` entry, as the reread reads it.
    return {"value": 0.61, "updated_at": "2026-09-28T23:00:00+00:00",
            "eligibility": record}


#: Polymarket slate: event 800's market 7 has tokens; event 900's market 9 has
#: none and Gamma cannot supply them this run.
POLY_TWO_EVENTS = [
    [
        (71, 7, "0xabc_yes", "0xabc", 800),
        (91, 9, "0xdef_yes", "0xdef", 900),
    ],
    [(7, "0xabc", {"clob_token_ids": ["111", "222"]}, "scheduled"), (9, "0xdef", None, "scheduled")],
    [(71, 7, "0xabc_yes"), (91, 9, "0xdef_yes")],
]

#: Polymarket slate: ONE event, 900, with a streaming prop (market 7, tokened)
#: and its moneyline (market 9) whose tokens Gamma cannot supply.
POLY_PROP_AND_MONEYLINE = [
    [
        (71, 7, "0xabc_yes", "0xabc", 900),
        (91, 9, "0xdef_yes", "0xdef", 900),
    ],
    [(7, "0xabc", {"clob_token_ids": ["111", "222"]}, "scheduled"), (9, "0xdef", None, "scheduled")],
    [(71, 7, "0xabc_yes"), (91, 9, "0xdef_yes")],
]

#: Kalshi slate: event 900's market 7, one outcome ticker.
KALSHI_ONE_MARKET = [
    [("KXATPMATCH-26SEP28ANGJOH", 7, 900)],
    [("KXATPMATCH-26SEP28ANGJOH-ANG", 7, 71)],
    # #9484: the open-contract admission read — none here, so reread call 1
    # is still the watcher's baseline.
    [],
]


def _kalshi_creds(monkeypatch):
    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key-id")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-pem")


# ------------------------------- gap 1: admission is by MAPPED leg ----


class TestAnEventWhoseLookupFailedIsNotSubscribed:
    async def test_it_is_admitted_when_it_turns_live(self, monkeypatch):
        """The review's trace: 900 is on the slate while scheduled, its token
        top-up fails, a sibling keeps the socket up; 900 turns live. Before,
        900 was in the SELECTED set, the difference was empty, and it waited
        for the 600 s timer."""
        _timing(monkeypatch, poly_task, refresh=30)
        _install_quiet_socket(monkeypatch)
        _gamma_down(monkeypatch)
        # Baseline: nothing live. Then 900 (and 800) turn live.
        _install_session(
            monkeypatch, POLY_TWO_EVENTS,
            lambda n: [] if n == 1 else [(800, 7, None), (900, 9, None)],
        )

        stats = await asyncio.wait_for(
            poly_task._run_polymarket_ws_consumer(), timeout=5,
        )

        assert stats["status"] == "resubscribe"
        assert stats["recycle_reason"] == "admission"
        # 800 streams on market 7, so only 900 is missing.
        assert stats["admitted_event_ids"] == [900]

    async def test_one_already_live_when_the_lookup_failed_is_held_to_the_timer(
        self, monkeypatch,
    ):
        """The thrash bound. 900 was live when this run looked its tokens up
        and failed; a recycle would repeat that lookup, so it waits for the
        timer rather than reconnecting the whole socket every minute."""
        _timing(monkeypatch, poly_task, refresh=_HELD_RUN_REFRESH_SECONDS)
        _install_quiet_socket(monkeypatch)
        _gamma_down(monkeypatch)
        state = _install_session(
            monkeypatch, POLY_TWO_EVENTS,
            lambda n: [(800, 7, None), (900, 9, None)],
        )

        stats = await asyncio.wait_for(
            poly_task._run_polymarket_ws_consumer(), timeout=5,
        )

        assert stats["status"] == "resubscribe"
        assert "recycle_reason" not in stats
        assert state["reread_calls"] >= _AT_LEAST_ONE_COMPARISON, state["reread_calls"]

    async def test_a_held_event_does_not_mask_a_new_one(self, monkeypatch):
        _timing(monkeypatch, poly_task, refresh=30)
        _install_quiet_socket(monkeypatch)
        _gamma_down(monkeypatch)
        _install_session(
            monkeypatch, POLY_TWO_EVENTS,
            lambda n: [(900, 9, None)] if n < 3
            else [(900, 9, None), (901, 99, None)],
        )

        stats = await asyncio.wait_for(
            poly_task._run_polymarket_ws_consumer(), timeout=5,
        )

        assert stats["admitted_event_ids"] == [901]


class TestAStreamingPropDoesNotHideAMissingMoneyline:
    async def test_the_leg_the_reading_names_must_be_mapped(self, monkeypatch):
        _timing(monkeypatch, poly_task, refresh=30)
        _install_quiet_socket(monkeypatch)
        _gamma_down(monkeypatch)
        reading = _verified(9)  # the card's number comes from market 9
        _install_session(
            monkeypatch, POLY_PROP_AND_MONEYLINE,
            lambda n: [] if n == 1 else [(900, 7, reading), (900, 9, reading)],
        )

        stats = await asyncio.wait_for(
            poly_task._run_polymarket_ws_consumer(), timeout=5,
        )

        assert stats["recycle_reason"] == "admission"
        assert stats["admitted_event_ids"] == [900]

    async def test_control_a_reading_from_the_mapped_market_is_admitted(
        self, monkeypatch,
    ):
        """Same slate, same streaming prop; the reading names market 7, which
        IS mapped. Nothing is missing, so the run goes to its timer."""
        _timing(monkeypatch, poly_task, refresh=_HELD_RUN_REFRESH_SECONDS)
        _install_quiet_socket(monkeypatch)
        _gamma_down(monkeypatch)
        reading = _verified(7)
        state = _install_session(
            monkeypatch, POLY_PROP_AND_MONEYLINE,
            lambda n: [] if n == 1 else [(900, 7, reading), (900, 9, reading)],
        )

        stats = await asyncio.wait_for(
            poly_task._run_polymarket_ws_consumer(), timeout=5,
        )

        assert "recycle_reason" not in stats
        assert state["reread_calls"] >= _AT_LEAST_ONE_COMPARISON, state["reread_calls"]


class TestAKalshiWinnerMarketAddedAfterTheSlate:
    async def test_is_admitted_although_its_event_was_selected(self, monkeypatch):
        """900 is live and streaming market 7. Its winner market 8 is linked
        after the slate was read and the stored reading now comes from it."""
        _kalshi_creds(monkeypatch)
        _timing(monkeypatch, kalshi_task, refresh=30)
        _install_quiet_socket(monkeypatch)
        reading = _verified(8)
        _install_session(
            monkeypatch, KALSHI_ONE_MARKET,
            lambda n: [(900, 7, None)] if n < 3
            else [(900, 7, reading), (900, 8, reading)],
        )

        stats = await asyncio.wait_for(
            kalshi_task._run_kalshi_ws_consumer(), timeout=5,
        )

        assert stats["recycle_reason"] == "admission"
        assert stats["admitted_event_ids"] == [900]


class TestUnadmittedLiveEvents:
    def test_no_reading_needs_any_mapped_leg(self):
        rows = [(900, 7, None), (900, 9, None), (901, 11, None)]
        assert admission.unadmitted_live_events(rows, {7}) == {901}

    def test_a_verified_reading_needs_its_own_leg(self):
        rows = [(900, 7, _verified(9)), (900, 9, _verified(9))]
        assert admission.unadmitted_live_events(rows, {7}) == {900}
        assert admission.unadmitted_live_events(rows, {9}) == frozenset()

    def test_every_contributor_of_a_devigged_reading_on_the_slate(self):
        reading = _verified(7, 8)
        rows = [(900, 7, reading), (900, 8, reading)]
        assert admission.unadmitted_live_events(rows, {7}) == {900}
        assert admission.unadmitted_live_events(rows, {7, 8}) == frozenset()

    def test_a_named_market_off_the_slate_falls_back_to_any_leg(self):
        """A settled/filtered market cannot be subscribed; it must not hold
        its event hostage to a once-a-minute recycle."""
        rows = [(900, 7, _verified(5))]
        assert admission.unadmitted_live_events(rows, {7}) == frozenset()
        assert admission.unadmitted_live_events(rows, set()) == {900}

    @pytest.mark.parametrize("entry", [
        {"value": 0.6, "eligibility": {"v": 1, "status": "unverified", "market_id": 9}},
        {"value": 0.6, "eligibility": {"v": 1, "status": "ineligible", "market_id": 9}},
        {"value": 0.6, "eligibility": {"v": 99, "status": "verified", "market_id": 9}},
        "not-a-record",
        0.61,
        {},
    ])
    def test_an_unproven_reading_names_nothing(self, entry):
        rows = [(900, 7, entry), (900, 9, entry)]
        assert admission.unadmitted_live_events(rows, {7}) == frozenset()


# ---------------------------- gap 2: owed stamps survive a recycle ----


class TestTheHandOff:
    def test_owed_stamps_move_to_the_next_refresher_and_are_due(self):
        old = lbr.LiveBlendRefresher("kalshi")
        old._throttle_deferred.add(900)
        old._lock_retry.add(901)

        assert lbr.hand_off_pending(old) == 2
        new = lbr.LiveBlendRefresher("kalshi")
        assert lbr.adopt_handed_off(new) == 2

        assert new.pending_event_ids() == {900, 901}
        now = lbr._mono()
        assert new._due(900, now) and new._due(901, now)

    def test_consumed_once_and_per_source(self):
        old = lbr.LiveBlendRefresher("kalshi")
        old._throttle_deferred.add(900)
        lbr.hand_off_pending(old)

        assert lbr.adopt_handed_off(lbr.LiveBlendRefresher("polymarket")) == 0
        assert lbr.adopt_handed_off(lbr.LiveBlendRefresher("kalshi")) == 1
        assert lbr.adopt_handed_off(lbr.LiveBlendRefresher("kalshi")) == 0

    def test_a_stale_hand_off_is_dropped(self, monkeypatch):
        clock = {"t": 1000.0}
        monkeypatch.setattr(lbr, "_mono", lambda: clock["t"])
        old = lbr.LiveBlendRefresher("kalshi")
        old._throttle_deferred.add(900)
        lbr.hand_off_pending(old)

        clock["t"] += lbr.PENDING_HANDOFF_TTL_S + 1
        assert lbr.adopt_handed_off(lbr.LiveBlendRefresher("kalshi")) == 0

    def test_an_empty_run_clears_an_older_hand_off(self):
        old = lbr.LiveBlendRefresher("kalshi")
        old._throttle_deferred.add(900)
        lbr.hand_off_pending(old)
        assert lbr.hand_off_pending(lbr.LiveBlendRefresher("kalshi")) == 0
        assert lbr.adopt_handed_off(lbr.LiveBlendRefresher("kalshi")) == 0

    def test_a_refresher_that_cannot_say_hands_off_nothing(self):
        class _Double:
            source = "kalshi"

        assert lbr.hand_off_pending(_Double()) == 0
        assert lbr.adopt_handed_off(_Double()) == 0


class _RecordingRefresher(lbr.LiveBlendRefresher):
    """The real refresher with its database batch recorded instead of run.

    `owe_on_first` seeds the reviewer's state on the first instance: event 900
    was stamped a moment ago and a later price is held by the 2 s throttle."""

    instances: list = []
    owe_on_first = True

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.batches: list = []
        if self.owe_on_first and not _RecordingRefresher.instances:
            self._last_refresh_at[900] = lbr._mono()
            self._throttle_deferred.add(900)
        _RecordingRefresher.instances.append(self)

    async def _refresh_batch(
        self, event_ids, now, *, prepared=None, on_committed=None, publish_committed=None
    ):
        self.batches.append(sorted(event_ids))
        self._last_refresh_at.update({e: now for e in event_ids})
        if on_committed is not None:
            on_committed(event_ids)


ARMS = pytest.mark.parametrize("arm", ["kalshi", "polymarket"])


def _arm(monkeypatch, arm):
    if arm == "kalshi":
        _kalshi_creds(monkeypatch)
        return kalshi_task, kalshi_task._run_kalshi_ws_consumer, KALSHI_ONE_MARKET
    slate = [
        [(71, 7, "0xabc_yes", "0xabc", 900)],
        [(7, "0xabc", {"clob_token_ids": ["111", "222"]}, "scheduled")],
        [(71, 7, "0xabc_yes")],
    ]
    return poly_task, poly_task._run_polymarket_ws_consumer, slate


class TestAnAdmissionRecycleKeepsTheOwedStamp:
    @ARMS
    async def test_the_next_run_stamps_what_the_last_run_owed(
        self, monkeypatch, arm,
    ):
        """The review's counterexample, end to end: run 1 ends by admission
        0.x s after stamping 900 with a later price held by the floor. Its
        final drain finds an empty buffer and 900 not yet due. Before, the
        next run's refresher started empty (`next_run_deferred=[]`)."""
        module, consumer, slate = _arm(monkeypatch, arm)
        monkeypatch.setattr(_RecordingRefresher, "instances", [])
        monkeypatch.setattr(lbr, "LiveBlendRefresher", _RecordingRefresher)
        monkeypatch.setattr(module, "PRICE_FLUSH_SECONDS", 0.01)
        _install_quiet_socket(monkeypatch)

        # Run 1: 901 turns live, so the run recycles for admission at once.
        _timing(monkeypatch, module, refresh=30)
        _install_session(monkeypatch, slate, lambda n: [] if n == 1 else [
            (901, 9010, None),
        ])
        first = await asyncio.wait_for(consumer(), timeout=5)
        assert first["recycle_reason"] == "admission"
        run1 = _RecordingRefresher.instances[0]
        # The throttle held 900 through the final drain — the gap's premise.
        assert 900 not in [e for b in run1.batches for e in b]
        assert first["blend_pending_carried"] == 1

        # Run 2, 2 s floor long since passed for a fresh refresher. #10090: it
        # ends by admission once it has stamped — a changed scope no longer
        # ends a run at its refresh.
        def reread_2(_n):
            runs = _RecordingRefresher.instances
            stamped = len(runs) > 1 and [900] in runs[1].batches
            return [(901, 9010, None)] if stamped else []

        _timing(monkeypatch, module, refresh=30)
        _install_session(monkeypatch, slate, reread_2)
        second = await asyncio.wait_for(consumer(), timeout=5)
        run2 = _RecordingRefresher.instances[1]

        assert second["blend_pending_adopted"] == 1
        assert [900] in run2.batches, run2.batches
