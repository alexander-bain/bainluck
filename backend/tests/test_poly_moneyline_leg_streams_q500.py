"""Q500 — the moneyline leg streams, so the number on the card moves live.

WHY THIS FILE EXISTS.  Q460 carried WebSocket prices through to
``Event.win_probability_sources``, Q489 landed each tick on the leg whose book
it is, Q490 stopped the socket waiting for a Gamma rotation to hand it tokens,
and Q491 stopped a failed flush dropping prices.  Every one of those shipped.
The hero was still two minutes stale.

MEASURED ON PRODUCTION, 2026-09-01 18:40-18:44 UTC.  The socket was healthy:
seven distinct sub-minute flush batches inside one minute (18:42:12, :25, :41,
:51, :56, :58, 18:43:00), each 2-6 outcomes — the 2s flush cadence, unmistakably
not the 120s poll's 55-outcome batch at 18:41:04.  And across EVERY live event::

    src          events   p50 stamp age   fresher than 2min
    betting          15             23s              14 / 15
    kalshi            7            122s               0 / 7
    polymarket        2            122s               0 / 2

122s is the 120s poll's sawtooth.  Zero live events carried a prediction-market
number the socket had touched.  The three events whose Polymarket outcomes were
ticking at that moment (Wolfsberger AC, Helsingborgs IF, Potapova) had **no
``polymarket`` key in their blend at all**.

THE CAUSE.  The socket subscribed only to markets addressable by their OWN
condition id.  A three-way "who wins" market is a PARENT row whose
``external_id`` is a bare Gamma event id (``"917153"``), so ``condition_id_of``
returns None — correctly, it is not a condition id — and the market-level top-up
skipped it.  What DID carry tokens were the Over/Under and Both-Teams-To-Score
props: ``quantity`` and ``container_member`` rows, every one of them invisible
to ``compute_source_home_probability``, which can only read the moneyline.  So
the fast lane streamed continuously into markets the hero does not render, and
the one market it does render moved every 120 seconds.

THE FIX, verified against production Gamma the same day: a field market's
OUTCOMES each carry a real condition id, and each resolves to its own binary
market —  ``0xfa91ccd0…`` → *"Will Wolfsberger AC win on 2026-09-01?"*,
``outcomes: ["Yes","No"]``, two ``clobTokenIds``.  The YES token of that market
IS the book for that leg.  The tokens were one level down the whole time.

The tests below pin the three things that make that safe: the YES token is
chosen BY NAME and never guessed, the NO token is never written anywhere, and
the persisted map merges instead of clobbering siblings — then prove the ship
end to end, on the production shape.
"""

import asyncio
import json

import pytest
import websockets
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update

import app.tasks.live_blend_refresh as blend_mod
import app.tasks.polymarket_ws as poly_task
from app.tasks.polymarket_token_topup import (
    OUTCOME_TOKEN_METADATA_KEY,
    topup_outcome_clob_tokens,
    yes_token_of,
)

# The production shape, kept verbatim so the fixture cannot drift into a
# friendlier one: a parent row addressed by a Gamma EVENT id, whose outcomes
# each carry a real condition id.
PARENT_EVENT_ID = "917153"
MARKET_ID = 59613231
EVENT_ID = 15291224

HOME_CONDITION = "0xfa91ccd064fb0916295a44e03077ab8632b6943af710bebaae55a85954e3f1bf"
AWAY_CONDITION = "0x95022b5ffea20c57f676dfe76473b5617cd39431edff5710ca595bb989cc7d6f"
DRAW_CONDITION = "0x7d8205ed4fcd05d19ba32de27887bc92fbc1f30cec59bcc4b867955a73592a8e"

HOME_OUTCOME_ID = 221927369
AWAY_OUTCOME_ID = 221893614
DRAW_OUTCOME_ID = 221893615

HOME_YES_TOKEN = (
    "37424116597795289341416204452344360730704946170353838301223818699083921393924"
)
HOME_NO_TOKEN = (
    "31073709865413954176470378439830005033155647149000000000000000000000000000000"
)


class _FakeMarket:
    def __init__(self, condition_id, clob_token_ids, outcomes=("Yes", "No")):
        self.condition_id = condition_id
        self.clob_token_ids = list(clob_token_ids)
        self.outcomes = list(outcomes)


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


# ------------------------------------------- which token is the YES book ----


class TestYesTokenOf:
    def test_the_yes_token_is_found_by_name(self):
        market = _FakeMarket(HOME_CONDITION, ["yes_tok", "no_tok"], ["Yes", "No"])
        assert yes_token_of(market) == "yes_tok"

    def test_it_is_not_assumed_to_be_index_zero(self):
        """The one assertion index-0 cannot make.  If Gamma ever serves
        `["No","Yes"]`, taking index 0 subscribes the NO book and the rendered
        probability becomes 1-p — the Q489 failure, rebuilt one layer up."""
        market = _FakeMarket(HOME_CONDITION, ["no_tok", "yes_tok"], ["No", "Yes"])
        assert yes_token_of(market) == "yes_tok"

    def test_outcomes_that_do_not_name_a_yes_are_refused_not_guessed(self):
        """A scalar/categorical market has no Yes leg.  Returning a token here
        would attribute someone else's book to a moneyline outcome."""
        market = _FakeMarket(HOME_CONDITION, ["a", "b"], ["Over", "Under"])
        assert yes_token_of(market) is None

    def test_a_market_with_no_tokens_yields_none(self):
        assert yes_token_of(_FakeMarket(HOME_CONDITION, [], ["Yes", "No"])) is None

    def test_a_yes_beyond_the_token_list_yields_none(self):
        """Index-aligned means aligned; a ragged pair is a shape we did not
        anticipate, and dropping it beats writing a token we cannot justify."""
        market = _FakeMarket(HOME_CONDITION, ["only_one"], ["No", "Yes"])
        assert yes_token_of(market) is None


# ------------------------------------------------ the outcome-level top-up ----


class TestTopupOutcomeClobTokens:
    async def test_it_asks_gamma_with_the_outcomes_condition_ids(self):
        """The whole point: the market's own external_id ("917153") is
        unaddressable, but its outcomes' ids are."""
        service = _FakeService(
            [_FakeMarket(HOME_CONDITION, [HOME_YES_TOKEN, HOME_NO_TOKEN])]
        )
        session = _CapturingSession()

        filled = await topup_outcome_clob_tokens(
            session,
            [(MARKET_ID, HOME_OUTCOME_ID, HOME_CONDITION)],
            service=service,
        )

        assert service.asked == [[HOME_CONDITION]]
        assert filled == {HOME_OUTCOME_ID: (MARKET_ID, HOME_YES_TOKEN)}

    async def test_only_the_yes_token_is_returned(self):
        """THE THREE-WAY TRAP.  On "Will Wolfsberger AC win?", the NO book is
        P(draw or LASK) — that is not the Draw row and not the LASK row, it is
        both combined.  There is no leg to write it to, so it is never
        subscribed rather than written somewhere plausible."""
        service = _FakeService(
            [_FakeMarket(HOME_CONDITION, [HOME_YES_TOKEN, HOME_NO_TOKEN])]
        )
        session = _CapturingSession()

        filled = await topup_outcome_clob_tokens(
            session,
            [(MARKET_ID, HOME_OUTCOME_ID, HOME_CONDITION)],
            service=service,
        )

        tokens = [token for _mid, token in filled.values()]
        assert tokens == [HOME_YES_TOKEN]
        assert HOME_NO_TOKEN not in tokens

    async def test_each_outcome_gets_its_own_condition_s_token(self):
        """Attribution is carried by the condition id, not reconstructed from
        ordering — so a Gamma response in a different order than we asked still
        lands each token on its own leg."""
        service = _FakeService(
            [
                _FakeMarket(DRAW_CONDITION, ["draw_yes", "draw_no"]),
                _FakeMarket(HOME_CONDITION, ["home_yes", "home_no"]),
                _FakeMarket(AWAY_CONDITION, ["away_yes", "away_no"]),
            ]
        )
        session = _CapturingSession()

        filled = await topup_outcome_clob_tokens(
            session,
            [
                (MARKET_ID, HOME_OUTCOME_ID, HOME_CONDITION),
                (MARKET_ID, AWAY_OUTCOME_ID, AWAY_CONDITION),
                (MARKET_ID, DRAW_OUTCOME_ID, DRAW_CONDITION),
            ],
            service=service,
        )

        assert filled == {
            HOME_OUTCOME_ID: (MARKET_ID, "home_yes"),
            AWAY_OUTCOME_ID: (MARKET_ID, "away_yes"),
            DRAW_OUTCOME_ID: (MARKET_ID, "draw_yes"),
        }

    async def test_the_persisted_map_merges_at_BOTH_levels(self):
        """`||` is shallow.  The outer merge protects `polymarket_event_id` and
        `matchup_title`; the INNER one protects outcome entries stamped on an
        earlier pass, which a plain `jsonb_build_object(KEY, {...})` would drop
        every time a different subset of legs was topped up."""
        service = _FakeService([_FakeMarket(HOME_CONDITION, ["home_yes", "home_no"])])
        session = _CapturingSession()

        await topup_outcome_clob_tokens(
            session,
            [(MARKET_ID, HOME_OUTCOME_ID, HOME_CONDITION)],
            service=service,
        )

        stmt = session.updates[0]
        assert isinstance(stmt, Update)
        sql = str(stmt.compile(dialect=postgresql.dialect())).lower()
        assert OUTCOME_TOKEN_METADATA_KEY in str(
            stmt.compile(dialect=postgresql.dialect()).params
        ), stmt.compile(dialect=postgresql.dialect()).params
        # Two concatenations, not one: outer (siblings) and inner (prior legs).
        assert sql.count("||") >= 2, f"a nested merge needs both levels: {sql}"
        assert sql.count("coalesce") >= 2, sql

    async def test_a_market_level_condition_id_is_still_handled(self):
        """Non-vacuity: this path is additive.  An ordinary binary sub-market
        whose outcome ids are suffixed still resolves to the bare condition."""
        service = _FakeService([_FakeMarket("0xabc", ["y", "n"])])
        session = _CapturingSession()

        filled = await topup_outcome_clob_tokens(
            session, [(7, 71, "0xabc_yes")], service=service
        )

        assert service.asked == [["0xabc"]]
        assert filled == {71: (7, "y")}

    async def test_an_unaddressable_outcome_costs_no_request(self):
        service = _FakeService([])
        session = _CapturingSession()

        filled = await topup_outcome_clob_tokens(
            session, [(MARKET_ID, HOME_OUTCOME_ID, PARENT_EVENT_ID)], service=service
        )

        assert filled == {}
        assert service.asked == []
        assert session.updates == []

    async def test_a_rate_limit_re_raises(self):
        """Gotcha #36 — an empty list would read as "this leg has no token"."""
        service = _FakeService([], raises=RuntimeError("429 Too Many Requests"))
        session = _CapturingSession()

        with pytest.raises(RuntimeError):
            await topup_outcome_clob_tokens(
                session,
                [(MARKET_ID, HOME_OUTCOME_ID, HOME_CONDITION)],
                service=service,
            )

    async def test_the_cap_is_logged_not_silent(self, caplog):
        service = _FakeService([])
        session = _CapturingSession()
        many = [(MARKET_ID, i, f"0x{i:04x}") for i in range(10)]

        with caplog.at_level("WARNING"):
            await topup_outcome_clob_tokens(
                session, many, service=service, max_outcomes=4
            )

        assert len(service.asked[0]) == 4
        assert any("capped at 4" in r.getMessage() for r in caplog.records), [
            r.getMessage() for r in caplog.records
        ]


# ------------------------------------------------------------- end to end ----


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


class _RecordingRefresher:
    """Captures the event ids the blend refresh is actually asked to re-stamp.

    This is the assertion that distinguishes "a price was written" from "the
    number on the card moved" — the exact gap production was sitting in.
    """

    refreshed: list[set] = []

    def __init__(self, *_a, **_kw):
        pass

    async def refresh(self, event_ids):
        _RecordingRefresher.refreshed.append(set(event_ids))
        return None


def _production_batches():
    """The slate exactly as production served it for Wolfsberger AC vs LASK.

    One parent `field` market (external_id = a Gamma EVENT id, metadata with no
    tokens) whose three outcomes each carry a condition id.
    """
    return [
        # slate: (outcome_id, market_id, outcome_ext, market_ext, event_id)
        [
            (HOME_OUTCOME_ID, MARKET_ID, HOME_CONDITION, PARENT_EVENT_ID, EVENT_ID),
            (AWAY_OUTCOME_ID, MARKET_ID, AWAY_CONDITION, PARENT_EVENT_ID, EVENT_ID),
            (DRAW_OUTCOME_ID, MARKET_ID, DRAW_CONDITION, PARENT_EVENT_ID, EVENT_ID),
        ],
        # market rows: a parent row with NO clob_token_ids — production's state
        [(MARKET_ID, PARENT_EVENT_ID, {"polymarket_event_id": PARENT_EVENT_ID})],
        # outcome rows, ordered by id
        [
            (AWAY_OUTCOME_ID, MARKET_ID, AWAY_CONDITION),
            (DRAW_OUTCOME_ID, MARKET_ID, DRAW_CONDITION),
            (HOME_OUTCOME_ID, MARKET_ID, HOME_CONDITION),
        ],
    ]


class TestTheMoneylineLegReachesTheRenderedBlend:
    async def test_a_parent_row_becomes_a_subscribed_attributed_live_number(
        self, monkeypatch
    ):
        """THE SHIP.  Production's exact shape: the only market on the event is
        a parent `field` row with no tokens and an unaddressable external_id.
        Before this queue it subscribed nothing and the hero moved on the 120s
        poll.  It must now top up per outcome, subscribe the home leg, land the
        tick on the HOME outcome, and re-stamp THAT EVENT's blend."""
        _RecordingRefresher.refreshed = []
        writes: list[tuple[int, float]] = []
        meta_writes: list[int] = []
        service = _FakeService(
            [
                _FakeMarket(HOME_CONDITION, [HOME_YES_TOKEN, HOME_NO_TOKEN]),
                _FakeMarket(AWAY_CONDITION, ["away_yes", "away_no"]),
                _FakeMarket(DRAW_CONDITION, ["draw_yes", "draw_no"]),
            ]
        )
        batches = _production_batches()

        class _Ctx:
            async def __aenter__(self):
                return _Session(batches, writes, meta_writes)

            async def __aexit__(self, *_exc):
                return False

        import app.tasks.base as task_base
        import app.services.polymarket_api as poly_api

        monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.05)
        monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _RecordingRefresher)
        monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())
        monkeypatch.setattr(poly_api, "PolymarketAPIService", lambda *a, **kw: service)

        frames = [
            json.dumps(
                {
                    "event_type": "best_bid_ask",
                    "asset_id": HOME_YES_TOKEN,
                    "best_bid": "0.33",
                    "best_ask": "0.35",
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

        assert service.asked, "the consumer must ask Gamma for the outcome ids"
        assert sorted(service.asked[-1]) == sorted(
            [HOME_CONDITION, AWAY_CONDITION, DRAW_CONDITION]
        ), service.asked

        # The count that was zero in production while everything else looked fine.
        assert stats["moneyline_legs_subscribed"] == 3, stats
        assert stats["assets_mapped"] == 3, stats
        assert stats["assets_unmapped"] == 0, stats

        assert writes == [
            (HOME_OUTCOME_ID, pytest.approx(0.34))
        ], f"the home leg's own book must land on the home leg; got {writes}"

        assert _RecordingRefresher.refreshed == [
            {EVENT_ID}
        ], f"the price must reach the rendered blend, not stop at the outcome row; got {_RecordingRefresher.refreshed}"

    async def test_the_no_token_is_never_subscribed(self, monkeypatch):
        """Non-vacuity partner to the ship test.  A three-way market's NO book
        is P(not this leg) and belongs to no outcome row.  If it were mapped,
        this frame would write 0.66 onto the home leg — an inverted hero, which
        is worse than the stale one we started with."""
        _RecordingRefresher.refreshed = []
        writes: list[tuple[int, float]] = []
        meta_writes: list[int] = []
        service = _FakeService(
            [_FakeMarket(HOME_CONDITION, [HOME_YES_TOKEN, HOME_NO_TOKEN])]
        )
        batches = _production_batches()

        class _Ctx:
            async def __aenter__(self):
                return _Session(batches, writes, meta_writes)

            async def __aexit__(self, *_exc):
                return False

        import app.tasks.base as task_base
        import app.services.polymarket_api as poly_api

        monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.05)
        monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _RecordingRefresher)
        monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())
        monkeypatch.setattr(poly_api, "PolymarketAPIService", lambda *a, **kw: service)

        frames = [
            json.dumps(
                {
                    "event_type": "best_bid_ask",
                    "asset_id": HOME_NO_TOKEN,
                    "best_bid": "0.65",
                    "best_ask": "0.67",
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

        await poly_task._run_polymarket_ws_consumer()

        assert (
            writes == []
        ), f"a NO-token tick must be dropped, not written; got {writes}"
        assert _RecordingRefresher.refreshed == []

    async def test_a_gamma_outage_leaves_the_prop_stream_running(self, monkeypatch):
        """The moneyline top-up is an improvement, not a new single point of
        failure: with Gamma down, a market that already has tokens must still
        stream."""
        _RecordingRefresher.refreshed = []
        writes: list[tuple[int, float]] = []
        meta_writes: list[int] = []
        service = _FakeService([], raises=RuntimeError("gamma down"))

        prop_condition = "0x26a0"
        batches = [
            [
                (HOME_OUTCOME_ID, MARKET_ID, HOME_CONDITION, PARENT_EVENT_ID, EVENT_ID),
                (901, 59620623, f"{prop_condition}_yes", prop_condition, EVENT_ID),
            ],
            [
                (MARKET_ID, PARENT_EVENT_ID, {}),
                (59620623, prop_condition, {"clob_token_ids": ["ptok_y", "ptok_n"]}),
            ],
            [
                (HOME_OUTCOME_ID, MARKET_ID, HOME_CONDITION),
                (901, 59620623, f"{prop_condition}_yes"),
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
        monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _RecordingRefresher)
        monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())
        monkeypatch.setattr(poly_api, "PolymarketAPIService", lambda *a, **kw: service)

        frames = [
            json.dumps(
                {
                    "event_type": "best_bid_ask",
                    "asset_id": "ptok_y",
                    "best_bid": "0.88",
                    "best_ask": "0.90",
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

        assert stats["moneyline_legs_subscribed"] == 0, stats
        assert writes == [(901, pytest.approx(0.89))], writes
