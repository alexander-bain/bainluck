"""#9733 — a quiet Polymarket future is priced from the venue's current book.

WHAT A READER SAW. ``/api/futures/61352683`` (2026-09-30 16:2xZ), "Will George
Kittle have 524.5+ receiving yards …": **Yes 77% / No 10%**, stored at 12:57Z
and 12:24Z. Polymarket's own book at 16:18:53Z read Yes 0.80 / 0.87 and No
0.13 / 0.20, a tradeable 0.835 / 0.165. PR #9837 (both legs from one tick) was
live and could not help: no tick came. worker-ws reconnected at 16:21Z and the
row still had not moved at 16:28Z.

WHY. The venue answers a subscribe with the current book of every asset (a
LIST of ``event_type: book`` entries — the frame below is the one it sent for
Kittle at 16:28Z). ``PolymarketWebSocket`` discarded it ("book snapshot — skip
for now"), so only a CHANGE (``best_bid_ask``) or a trade moved a leg. A quiet
book that moved while the socket was down (every ten-minute recycle) or before
#9484 admitted the leg stayed frozen until it moved again.

THE RULE. The open-contract client hands each snapshot book to the ordinary
price handler as a quote: same tradeable-book refusal, same Yes/No complement,
same flush. The game socket and the shadow consumer are unchanged.
``POLYMARKET_WS_BOOK_SNAPSHOT_PRICES=0`` is the undo line.
"""

import asyncio
import json

import pytest
from tests.pm_bulk_test_support import (
    cleanup_pg_engines,
)
from sqlalchemy import text

import app.services.polymarket_ws as poly_svc
from app.tasks.polymarket_open_contracts import book_snapshot_prices_enabled
from tests.test_poly_ws_binary_complement_9733 import (
    KITTLE,
    KITTLE_NO,
    KITTLE_YES,
    NO_TOKEN,
    YES_TOKEN,
    _kittle_database,
    _open_rows,
)
from tests.test_ws_polymarket_open_contract_prices_9484 import (
    GAME_OUTCOME,
    GAME_SLATE,
    GAME_TOKEN,
    _drive,
    _frames_by_token,
    _Rig,
    _stored,
)

REAL_YES = (
    "5671805224542879768640213616363713192167288550060997720346676888399226595368"
)
REAL_NO = (
    "17285345387781064069457788076169424145616034984782301654941500701325798456033"
)


def _book(asset_id, bids, asks, **extra):
    return {
        "market": KITTLE,
        "asset_id": asset_id,
        "timestamp": "1790785731539",
        "bids": [{"price": p, "size": s} for p, s in bids],
        "asks": [{"price": p, "size": s} for p, s in asks],
        "tick_size": "0.01",
        "event_type": "book",
        "last_trade_price": "0.100",
        **extra,
    }


def _kittle_frame(yes=REAL_YES, no=REAL_NO):
    """The subscribe snapshot Polymarket sent for Kittle, 2026-09-30 16:28Z
    (the venue lists bids ascending and asks descending; hash dropped)."""
    return [
        _book(
            no,
            [("0.01", "22.39"), ("0.13", "119.72")],
            [("0.99", "12.6"), ("0.2", "40")],
        ),
        _book(
            yes,
            [("0.01", "12.6"), ("0.8", "40")],
            [("0.99", "22.39"), ("0.87", "119.72")],
        ),
    ]


class TestSnapshotQuotes:
    def test_the_kittle_snapshot_is_two_quotes_at_the_top_of_each_book(self):
        quotes = poly_svc._snapshot_quotes(_kittle_frame())
        assert [(q["asset_id"], q["best_bid"], q["best_ask"]) for q in quotes] == [
            (REAL_NO, "0.13", "0.2"),
            (REAL_YES, "0.8", "0.87"),
        ]
        assert all(q["event_type"] == "best_bid_ask" for q in quotes)
        assert all(q["timestamp"] == "1790785731539" for q in quotes)

    def test_the_top_is_read_by_value_not_by_position(self):
        """``[0]`` is the WORST quote on each side of the venue's order; the
        best must not depend on which end it sits."""
        frame = _kittle_frame()
        for book in frame:
            book["bids"].reverse()
            book["asks"].reverse()
        assert poly_svc._snapshot_quotes(frame) == poly_svc._snapshot_quotes(
            _kittle_frame()
        )

    def test_a_lone_book_dict_is_the_same_thing(self):
        (book,) = _kittle_frame()[1:]
        assert poly_svc._snapshot_quotes(book) == poly_svc._snapshot_quotes([book])

    @pytest.mark.parametrize(
        "book",
        [
            _book("a", [], [("0.87", "1")]),  # nobody bids
            _book("a", [("0.80", "1")], []),  # nobody offers
            _book("a", [], []),
            _book("a", [("x", "1")], [("0.87", "1")]),  # no readable bid
            {
                "event_type": "book",
                "bids": [{"price": "0.8"}],
                "asks": [{"price": "0.87"}],
            },  # names no asset
            "not a book",
        ],
    )
    def test_a_book_without_both_sides_yields_no_quote(self, book):
        assert poly_svc._snapshot_quotes([book]) == []

    def test_an_unreadable_level_is_skipped_not_fatal(self):
        book = _book("a", [("0.80", "1")], [("0.87", "1")])
        book["bids"].insert(0, {"size": "3"})
        book["asks"].append({"price": None})
        (quote,) = poly_svc._snapshot_quotes([book])
        assert (quote["best_bid"], quote["best_ask"]) == ("0.8", "0.87")


class _OneFrame:
    def __init__(self, frames):
        self._frames = [json.dumps(f) for f in frames]

    async def send(self, payload):
        return None

    def __aiter__(self):
        async def gen():
            for frame in self._frames:
                yield frame
            await asyncio.sleep(3600)

        return gen()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


async def _client_quotes(monkeypatch, frames, on_price, **kwargs):
    monkeypatch.setattr(
        "websockets.connect", lambda *a, **kw: _OneFrame(frames), raising=False
    )
    ws = poly_svc.PolymarketWebSocket(**kwargs)
    ws.on_price = on_price
    task = asyncio.create_task(ws.run(asset_ids=[REAL_YES, REAL_NO]))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises((asyncio.CancelledError, Exception)):
        await task
    return ws


class TestTheClient:
    async def test_a_client_that_asks_prices_each_snapshot_book(self, monkeypatch):
        seen = []
        ws = await _client_quotes(
            monkeypatch, [_kittle_frame()], seen.append, price_book_snapshots=True
        )
        assert [(q["asset_id"], q["best_bid"]) for q in seen] == [
            (REAL_NO, "0.13"),
            (REAL_YES, "0.8"),
        ]
        assert ws.stats["book_snapshot_quotes"] == 2

    async def test_every_other_client_still_skips_the_snapshot(self, monkeypatch):
        """The game socket and the shadow consumer construct the default."""
        seen = []
        ws = await _client_quotes(monkeypatch, [_kittle_frame()], seen.append)
        assert seen == []
        assert ws.stats["book_snapshot_quotes"] == 0
        assert ws.stats["assets_served"] == 2, "still counted as served (#837)"

    async def test_a_lone_book_dict_is_priced_too(self, monkeypatch):
        seen = []
        await _client_quotes(
            monkeypatch, [_kittle_frame()[1]], seen.append, price_book_snapshots=True
        )
        assert [q["asset_id"] for q in seen] == [REAL_YES]

    async def test_one_failing_quote_does_not_lose_the_rest(self, monkeypatch):
        seen = []

        async def on_price(quote):
            if quote["asset_id"] == REAL_NO:
                raise RuntimeError("boom")
            seen.append(quote["asset_id"])

        await _client_quotes(
            monkeypatch, [_kittle_frame()], on_price, price_book_snapshots=True
        )
        assert seen == [REAL_YES]


class TestTheUndoLine:
    def test_on_by_default(self, monkeypatch):
        monkeypatch.delenv("POLYMARKET_WS_BOOK_SNAPSHOT_PRICES", raising=False)
        assert book_snapshot_prices_enabled() is True

    def test_zero_turns_it_off(self, monkeypatch):
        monkeypatch.setenv("POLYMARKET_WS_BOOK_SNAPSHOT_PRICES", "0")
        assert book_snapshot_prices_enabled() is False


def _frozen_kittle(tmp_path):
    """Kittle as production stored it at 16:28Z: Yes 0.77 / No 0.10."""
    engine = _kittle_database(tmp_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE futures_outcomes SET current_probability = 0.10 WHERE id = :i"
            ),
            {"i": KITTLE_NO},
        )
    return engine


class TestTheConsumer:
    async def test_the_frozen_kittle_pair_takes_the_venues_book(
        self, monkeypatch, tmp_path
    ):
        """THE REGRESSION. Before this the subscribe snapshot was discarded and
        the pair stayed 0.77 / 0.10 with no tick to move it."""
        monkeypatch.delenv("POLYMARKET_WS_BOOK_SNAPSHOT_PRICES", raising=False)
        engine = _frozen_kittle(tmp_path)
        rig = _Rig(
            engine,
            GAME_SLATE,
            _open_rows(),
            _frames_by_token(
                {YES_TOKEN: [(0.0, json.dumps(_kittle_frame(YES_TOKEN, NO_TOKEN)))]}
            ),
        )
        stats = await _drive(monkeypatch, rig)

        assert stats["errors"] == 0
        assert _stored(engine, KITTLE_YES) == pytest.approx(0.835)
        assert _stored(engine, KITTLE_NO) == pytest.approx(0.165)

    async def test_the_undo_line_leaves_the_pair_where_it_was(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("POLYMARKET_WS_BOOK_SNAPSHOT_PRICES", "0")
        engine = _frozen_kittle(tmp_path)
        rig = _Rig(
            engine,
            GAME_SLATE,
            _open_rows(),
            _frames_by_token(
                {YES_TOKEN: [(0.0, json.dumps(_kittle_frame(YES_TOKEN, NO_TOKEN)))]}
            ),
        )
        await _drive(monkeypatch, rig)

        assert _stored(engine, KITTLE_YES) == pytest.approx(0.77)
        assert _stored(engine, KITTLE_NO) == pytest.approx(0.10)

    async def test_a_wide_snapshot_book_is_refused_like_any_quote(
        self, monkeypatch, tmp_path
    ):
        """#1578 still holds: a book nobody trades inside is not a price."""
        monkeypatch.delenv("POLYMARKET_WS_BOOK_SNAPSHOT_PRICES", raising=False)
        engine = _frozen_kittle(tmp_path)
        wide = [
            _book(YES_TOKEN, [("0.46", "5")], [("0.82", "5")]),
            _book(NO_TOKEN, [("0.18", "5")], [("0.54", "5")]),
        ]
        rig = _Rig(
            engine,
            GAME_SLATE,
            _open_rows(),
            _frames_by_token({YES_TOKEN: [(0.0, json.dumps(wide))]}),
        )
        await _drive(monkeypatch, rig)

        assert _stored(engine, KITTLE_YES) == pytest.approx(0.77)
        assert _stored(engine, KITTLE_NO) == pytest.approx(0.10)

    async def test_the_game_socket_still_skips_its_snapshot(
        self, monkeypatch, tmp_path
    ):
        """Scope: the game slate's legs are refreshed by the poll and their own
        ticks; this change does not reprice them at every recycle."""
        monkeypatch.delenv("POLYMARKET_WS_BOOK_SNAPSHOT_PRICES", raising=False)
        engine = _frozen_kittle(tmp_path)
        game_book = [_book(GAME_TOKEN, [("0.60", "50")], [("0.62", "50")])]
        rig = _Rig(
            engine,
            GAME_SLATE,
            _open_rows(),
            _frames_by_token({GAME_TOKEN: [(0.0, json.dumps(game_book))]}),
        )
        await _drive(monkeypatch, rig)

        assert _stored(engine, GAME_OUTCOME) == pytest.approx(0.30)
