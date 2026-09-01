"""Q490 — the fast lane asks for its own tokens instead of waiting for a rotation.

WHY THIS FILE EXISTS.  Q460 made ``poll_polymarket_markets`` stamp
``clob_token_ids``, and it stamps on UPDATE as well as insert — measured on
production, the first sync after that deploy took 0 -> 701 markets carrying the
key, 558 of them rows created before the deploy.  The write is correct.

Reaching the row is not.  Gamma caps ``/events`` at offset 2000, so the poll
addresses ~2,000 of ~39,000 open markets per run, on a rotating cursor with a
420s budget.  Two hours after that deploy, 701 markets carried tokens and **0 of
the 77 markets the WebSocket consumer subscribes to** were among them — the
socket was still returning ``no_asset_ids``.

So the consumer names its markets: ``/markets?condition_ids=`` is the one Gamma
read that does not paginate.  The tests below pin the two things that make that
safe — the id it asks with, and the fact that the answer MERGES into
``market_metadata`` rather than replacing a column four other writers share —
and then prove the end-to-end ship: a slate row with no tokens becomes a
subscribed, correctly-attributed asset within one recycle.
"""

import asyncio
import json

import pytest
import websockets
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update

import app.tasks.live_blend_refresh as blend_mod
import app.tasks.polymarket_ws as poly_task
from app.tasks.polymarket_token_topup import condition_id_of, topup_clob_tokens

CONDITION_ID = "0xabc"
YES_TOKEN = "111"
NO_TOKEN = "222"
MARKET_ID = 7
YES_OUTCOME_ID = 71
NO_OUTCOME_ID = 72
EVENT_ID = 900


# ------------------------------------------------- the id we ask Gamma with ----


class TestConditionIdOf:
    def test_a_bare_sub_market_condition_id_passes_through(self):
        assert condition_id_of("0xabc") == "0xabc"

    @pytest.mark.parametrize("suffixed", ["0xabc_yes", "0xabc_no"])
    def test_an_outcome_suffix_is_stripped(self, suffixed):
        """Outcome rows store the suffixed form; Gamma 404s on it (12fd2496)."""
        assert condition_id_of(suffixed) == "0xabc"

    def test_removesuffix_not_rstrip_a_hex_id_ending_in_those_letters(self):
        """THE TRAP.  `12fd2496` used `cid.rstrip("_yes").rstrip("_no")`, and
        `rstrip` takes a CHARACTER SET, not a suffix: every trailing character
        drawn from {_, y, e, s, n, o} is eaten.  A hex condition id ending in
        `e` is real and common, and truncating it produces a 404 that reads as
        "this market is gone"."""
        assert condition_id_of("0xdeadbeefe") == "0xdeadbeefe"
        assert condition_id_of("0xfacade") == "0xfacade"
        # The exact shape rstrip would destroy: real id, then a real suffix.
        assert condition_id_of("0xfacade_yes") == "0xfacade"

    def test_a_parent_row_event_id_is_refused_not_guessed(self):
        """Parent rows store a Gamma EVENT id (a bare integer).  Asking
        `/markets?condition_ids=` for one returns nothing; the discriminator is
        `0x`, and guessing would be the bug."""
        assert condition_id_of("31415") is None

    @pytest.mark.parametrize("empty", [None, ""])
    def test_missing_external_id_is_refused(self, empty):
        assert condition_id_of(empty) is None


# ------------------------------------------------------------ fake service ----


class _FakeMarket:
    def __init__(self, condition_id, clob_token_ids):
        self.condition_id = condition_id
        self.clob_token_ids = clob_token_ids


class _FakeService:
    def __init__(self, markets, *, raises=None):
        self._markets = markets
        self._raises = raises
        self.asked: list[list[str]] = []
        self.closed = False

    async def get_markets_by_conditions(self, condition_ids, **_kw):
        self.asked.append(list(condition_ids))
        if self._raises:
            raise self._raises
        return list(self._markets)

    async def close(self):
        self.closed = True


class _CapturingSession:
    def __init__(self):
        self.updates: list = []

    async def execute(self, stmt):
        self.updates.append(stmt)
        return None


# ---------------------------------------------------------- the top-up call ----


class TestTopupStampsTheSlate:
    async def test_it_asks_gamma_for_exactly_the_missing_markets(self):
        service = _FakeService([_FakeMarket(CONDITION_ID, [YES_TOKEN, NO_TOKEN])])
        session = _CapturingSession()

        filled = await topup_clob_tokens(
            session, [(MARKET_ID, CONDITION_ID)], service=service
        )

        assert service.asked == [[CONDITION_ID]]
        assert filled == {MARKET_ID: [YES_TOKEN, NO_TOKEN]}
        assert len(session.updates) == 1

    async def test_the_write_MERGES_and_does_not_clobber(self):
        """`market_metadata` is shared with `polymarket_event_id`,
        `matchup_title` and the venue-settled stamp (#2222).  A plain assignment
        would drop all three.  Asserted on the COMPILED SQL, not on the source,
        so the idiom cannot drift out from under the claim."""
        service = _FakeService([_FakeMarket(CONDITION_ID, [YES_TOKEN])])
        session = _CapturingSession()

        await topup_clob_tokens(session, [(MARKET_ID, CONDITION_ID)], service=service)

        stmt = session.updates[0]
        assert isinstance(stmt, Update)
        sql = str(stmt.compile(dialect=postgresql.dialect())).lower()
        assert "coalesce" in sql, sql
        assert "||" in sql, f"a merge must concatenate, not assign: {sql}"
        assert "jsonb_build_object" in sql, sql

    async def test_a_parent_row_is_skipped_without_a_gamma_call(self):
        service = _FakeService([])
        session = _CapturingSession()

        filled = await topup_clob_tokens(
            session, [(MARKET_ID, "31415")], service=service
        )

        assert filled == {}
        assert service.asked == [], "an un-addressable id must not cost a request"
        assert session.updates == []

    async def test_a_market_gamma_does_not_return_is_left_alone(self):
        """Gamma omits ids it does not know.  Keying by the RESPONSE's condition
        id (not by request order) is what keeps a partial answer from stamping
        one market's tokens onto another."""
        service = _FakeService([_FakeMarket("0xother", [YES_TOKEN, NO_TOKEN])])
        session = _CapturingSession()

        filled = await topup_clob_tokens(
            session, [(MARKET_ID, CONDITION_ID)], service=service
        )

        assert filled == {}
        assert session.updates == []

    async def test_a_market_with_no_tokens_is_not_stamped_empty(self):
        service = _FakeService([_FakeMarket(CONDITION_ID, [])])
        session = _CapturingSession()

        filled = await topup_clob_tokens(
            session, [(MARKET_ID, CONDITION_ID)], service=service
        )

        assert filled == {}
        assert session.updates == [], "an empty token list must not be persisted"

    async def test_a_rate_limit_re_raises_rather_than_reading_as_no_tokens(self):
        """Gotcha #36.  A swallowed 429 returning `[]` would mean "these markets
        have no tokens", which is the exact false negative this queue exists to
        end."""
        service = _FakeService([], raises=RuntimeError("429 Too Many Requests"))
        session = _CapturingSession()

        with pytest.raises(RuntimeError):
            await topup_clob_tokens(
                session, [(MARKET_ID, CONDITION_ID)], service=service
            )

    async def test_the_cap_is_logged_not_silent(self, caplog):
        """A truncated top-up that read as "nothing was missing" is gotcha #53
        made on purpose."""
        service = _FakeService([])
        session = _CapturingSession()
        many = [(i, f"0x{i:04x}") for i in range(10)]

        with caplog.at_level("WARNING"):
            await topup_clob_tokens(session, many, service=service, max_markets=4)

        assert len(service.asked[0]) == 4
        assert any("capped at 4" in r.getMessage() for r in caplog.records), [
            r.getMessage() for r in caplog.records
        ]


# ------------------------------------------------------------- end to end ----
# Real consumer, real service dispatch; only the socket, the slate query and
# Gamma are faked. This is the test that says the ship happened.


class _TickingSocket:
    def __init__(self, frames):
        self._frames = list(frames)

    async def send(self, _payload):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._frames:
            return self._frames.pop(0)
        await asyncio.sleep(3600)
        raise StopAsyncIteration  # pragma: no cover


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, batches, writes, meta_writes):
        self._batches = batches
        self._writes = writes
        self._meta_writes = meta_writes

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            params = stmt.compile(dialect=postgresql.dialect()).params
            if (
                stmt.table.name == "futures_outcomes"
                and "current_probability" in params
            ):
                self._writes.append((params["id_1"], params["current_probability"]))
            elif stmt.table.name == "futures_markets":
                self._meta_writes.append(params["id_1"])
            return _Result([])
        return _Result(self._batches.pop(0) if self._batches else [])


class _NoopRefresher:
    def __init__(self, *_a, **_kw):
        pass

    async def refresh(self, _event_ids):
        return None


class TestTheSocketSubscribesToAMarketItHadToAskFor:
    async def test_a_tokenless_slate_row_becomes_a_correctly_attributed_tick(
        self, monkeypatch
    ):
        """THE SHIP.  The slate row carries NO `clob_token_ids` — production's
        state for all 77 live markets.  The consumer must top it up, subscribe,
        and land the No-token tick on the No leg (Q489), all in one recycle."""
        writes: list[tuple[int, float]] = []
        meta_writes: list[int] = []
        service = _FakeService([_FakeMarket(CONDITION_ID, [YES_TOKEN, NO_TOKEN])])

        batches = [
            # slate rows: (outcome_id, market_id, outcome_ext, market_ext, event_id)
            [
                (
                    YES_OUTCOME_ID,
                    MARKET_ID,
                    f"{CONDITION_ID}_yes",
                    CONDITION_ID,
                    EVENT_ID,
                ),
                (
                    NO_OUTCOME_ID,
                    MARKET_ID,
                    f"{CONDITION_ID}_no",
                    CONDITION_ID,
                    EVENT_ID,
                ),
            ],
            # market rows: metadata WITHOUT tokens — the production state
            [(MARKET_ID, CONDITION_ID, {"polymarket_event_id": "31415"})],
            # outcome rows, ordered by id: Yes then No
            [
                (YES_OUTCOME_ID, MARKET_ID, f"{CONDITION_ID}_yes"),
                (NO_OUTCOME_ID, MARKET_ID, f"{CONDITION_ID}_no"),
            ],
        ]

        class _Ctx:
            async def __aenter__(self):
                return _Session(batches, writes, meta_writes)

            async def __aexit__(self, *_exc):
                return False

        import app.tasks.base as task_base
        import app.services.polymarket_api as poly_api

        monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.05)
        monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _NoopRefresher)
        monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())
        monkeypatch.setattr(poly_api, "PolymarketAPIService", lambda *a, **kw: service)

        frames = [
            json.dumps(
                {
                    "event_type": "best_bid_ask",
                    "asset_id": NO_TOKEN,
                    "best_bid": "0.28",
                    "best_ask": "0.32",
                }
            )
        ]

        def _connect(*_a, **_kw):
            class _C:
                async def __aenter__(self_inner):
                    return _TickingSocket(frames)

                async def __aexit__(self_inner, *_exc):
                    return False

            return _C()

        monkeypatch.setattr(websockets, "connect", _connect)

        stats = await poly_task._run_polymarket_ws_consumer()

        assert service.asked == [
            [CONDITION_ID]
        ], f"the consumer must ask Gamma for its own slate; got {service.asked}"
        assert meta_writes == [MARKET_ID], "the tokens must be persisted, not just used"
        assert stats["assets_subscribed"] == 2, stats
        assert stats["assets_mapped"] == 2, stats
        assert writes == [
            (NO_OUTCOME_ID, pytest.approx(0.30))
        ], f"topped-up assets must still attribute correctly; got {writes}"

    async def test_a_gamma_outage_does_not_take_the_socket_down(self, monkeypatch):
        """Non-vacuity partner: the top-up is a best-effort improvement, not a
        new single point of failure.  With one market already stamped and the
        other un-toppable, the stamped one must still stream."""
        writes: list[tuple[int, float]] = []
        meta_writes: list[int] = []
        service = _FakeService([], raises=RuntimeError("gamma down"))

        batches = [
            [
                (
                    YES_OUTCOME_ID,
                    MARKET_ID,
                    f"{CONDITION_ID}_yes",
                    CONDITION_ID,
                    EVENT_ID,
                ),
                (
                    NO_OUTCOME_ID,
                    MARKET_ID,
                    f"{CONDITION_ID}_no",
                    CONDITION_ID,
                    EVENT_ID,
                ),
                (81, 8, "0xdef_yes", "0xdef", EVENT_ID),
            ],
            [
                (MARKET_ID, CONDITION_ID, {"clob_token_ids": [YES_TOKEN, NO_TOKEN]}),
                (8, "0xdef", {}),  # no tokens, and Gamma is down
            ],
            [
                (YES_OUTCOME_ID, MARKET_ID, f"{CONDITION_ID}_yes"),
                (NO_OUTCOME_ID, MARKET_ID, f"{CONDITION_ID}_no"),
                (81, 8, "0xdef_yes"),
            ],
        ]

        class _Ctx:
            async def __aenter__(self):
                return _Session(batches, writes, meta_writes)

            async def __aexit__(self, *_exc):
                return False

        import app.tasks.base as task_base
        import app.services.polymarket_api as poly_api

        monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.05)
        monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _NoopRefresher)
        monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())
        monkeypatch.setattr(poly_api, "PolymarketAPIService", lambda *a, **kw: service)

        frames = [
            json.dumps(
                {
                    "event_type": "best_bid_ask",
                    "asset_id": YES_TOKEN,
                    "best_bid": "0.68",
                    "best_ask": "0.72",
                }
            )
        ]

        def _connect(*_a, **_kw):
            class _C:
                async def __aenter__(self_inner):
                    return _TickingSocket(frames)

                async def __aexit__(self_inner, *_exc):
                    return False

            return _C()

        monkeypatch.setattr(websockets, "connect", _connect)

        stats = await poly_task._run_polymarket_ws_consumer()

        assert stats["assets_subscribed"] == 2, stats
        assert writes == [(YES_OUTCOME_ID, pytest.approx(0.70))], writes
