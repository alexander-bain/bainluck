"""Q460 — the fast lane must reach the number, and keep reaching it.

These are wiring guards, not logic guards. The logic has its own tests
(`test_live_blend.py`, `test_live_blend_refresh.py`); what those cannot catch is
the WebSocket consumer quietly going back to writing `futures_outcomes` and
nothing else, which is the exact state production was in before this queue and
which produced no error, no alert and no failing test for months.

WHY AST AND NOT A BEHAVIOURAL TEST. `flush_prices` is a closure inside
`_run_kalshi_ws_consumer`, which needs Kalshi credentials, a live socket and a
database before it will hand that closure out. A guard that cannot run is worth
less than a coarse one that does, so this reads the structure instead — and it
asserts ORDER, because a containment check that only asks "is the call present"
is blind to an early exit placed in front of it.
"""

import ast
import inspect

import app.tasks.kalshi_ws as kalshi_ws
import app.tasks.polymarket_ws as polymarket_ws
from app.tasks.polymarket import sub_market_metadata


def _flush_function(module, consumer_name: str) -> ast.AsyncFunctionDef:
    """The nested `flush_prices` coroutine inside a WS consumer."""
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == consumer_name:
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.AsyncFunctionDef)
                    and inner.name == "flush_prices"
                ):
                    return inner
    raise AssertionError(f"{consumer_name} has no nested flush_prices")


def _calls_named(node, name: str) -> list[ast.Call]:
    found = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name) and func.id == name:
                found.append(sub)
            elif isinstance(func, ast.Attribute) and func.attr == name:
                found.append(sub)
    return found


def _keyword_names(node) -> set[str]:
    return {
        kw.arg
        for sub in ast.walk(node)
        if isinstance(sub, ast.Call)
        for kw in sub.keywords
        if kw.arg
    }


CONSUMERS = [
    (kalshi_ws, "_run_kalshi_ws_consumer"),
    (polymarket_ws, "_run_polymarket_ws_consumer"),
]


class TestFlushStampsBothPriceColumns:
    """#2024: a live socket is a price writer and owes both stamps.

    Without `last_updated`, `playoffs.py`'s liveness gate read actively-streaming
    rows as long dead — measured on production 2026-08-30 at up to 23 days on
    outcomes whose price had moved seconds earlier.
    """

    def test_every_ws_flush_touches_last_updated(self):
        for module, consumer in CONSUMERS:
            flush = _flush_function(module, consumer)
            assert "last_updated" in _keyword_names(flush), consumer

    def test_every_ws_flush_maintains_price_changed_at(self):
        for module, consumer in CONSUMERS:
            flush = _flush_function(module, consumer)
            assert _calls_named(flush, "price_changed_at_value"), consumer

    def test_price_changed_at_uses_the_shared_helper_not_a_copy(self):
        """A drifted change-detection predicate does not throw, it just stops
        stamping — so there is exactly one implementation and both sockets use
        it."""
        for module, _consumer in CONSUMERS:
            src = inspect.getsource(module)
            assert "from app.utils.price_change_stamp import price_changed_at_value" in src


class TestFlushReachesTheBlend:
    """THE SHIP. Prices in `futures_outcomes` are invisible; the card renders
    `Event.win_probability_sources`."""

    def test_every_ws_flush_refreshes_the_blend(self):
        for module, consumer in CONSUMERS:
            flush = _flush_function(module, consumer)
            assert _calls_named(flush, "refresh"), (
                f"{consumer}'s flush writes prices nothing renders"
            )

    def test_the_blend_refresh_runs_after_the_price_write(self):
        """Order matters: the refresh reads the rows the flush just wrote."""
        for module, consumer in CONSUMERS:
            flush = _flush_function(module, consumer)
            try_nodes = [n for n in flush.body if isinstance(n, ast.Try)]
            assert try_nodes, f"{consumer}: expected the DB write in a try block"
            write_line = max(n.lineno for n in try_nodes)
            refresh_calls = _calls_named(flush, "refresh")
            assert refresh_calls, consumer
            assert min(c.lineno for c in refresh_calls) > write_line, (
                f"{consumer}: blend refresh must follow the price write"
            )

    def test_a_failed_flush_returns_before_stamping_a_blend(self):
        """If the price write failed, the rows the refresh would read are stale;
        stamping a blend off them would publish a number the venue never sent."""
        for module, consumer in CONSUMERS:
            flush = _flush_function(module, consumer)
            handlers = [
                h
                for n in flush.body
                if isinstance(n, ast.Try)
                for h in n.handlers
            ]
            assert handlers, consumer
            assert any(
                isinstance(stmt, ast.Return)
                for h in handlers
                for stmt in ast.walk(h)
            ), f"{consumer}: flush error path must not fall through to the refresh"

    def test_each_consumer_owns_a_refresher_for_its_own_source(self):
        for module, consumer, source in (
            (kalshi_ws, "_run_kalshi_ws_consumer", "kalshi"),
            (polymarket_ws, "_run_polymarket_ws_consumer", "polymarket"),
        ):
            tree = ast.parse(inspect.getsource(module))
            found = [
                call
                for node in ast.walk(tree)
                if isinstance(node, ast.AsyncFunctionDef) and node.name == consumer
                for call in _calls_named(node, "LiveBlendRefresher")
            ]
            assert found, consumer
            literals = [
                a.value
                for c in found
                for a in c.args
                if isinstance(a, ast.Constant)
            ]
            assert source in literals, f"{consumer} must refresh the {source} key"


class TestSubscriptionListIsRefreshed:
    """A socket that never resubscribes only covers the slate it started with.

    Both consumers build their subscription from events that are live or start
    within 6 hours, ONCE, and `ws.run` reconnects internally without rebuilding
    it. Heroku cycles this dyno roughly daily, so a restart at 11:17am
    subscribes nothing starting after 5:17pm — every evening game would miss the
    fast lane, silently, and the ship would look broken rather than absent.
    """

    def test_both_consumers_bound_their_run_with_a_timeout(self):
        for module, consumer in CONSUMERS:
            tree = ast.parse(inspect.getsource(module))
            node = next(
                n
                for n in ast.walk(tree)
                if isinstance(n, ast.AsyncFunctionDef) and n.name == consumer
            )
            waits = _calls_named(node, "wait_for")
            assert waits, f"{consumer}: ws.run must not be awaited unbounded"
            assert any(
                kw.arg == "timeout" for w in waits for kw in w.keywords
            ), consumer

    def test_both_consumers_report_the_recycle_distinctly(self):
        """The runner has to tell a planned recycle from a crash, or it applies
        the error backoff and blinds the fast lane on every refresh."""
        for module, _consumer in CONSUMERS:
            assert '"resubscribe"' in inspect.getsource(module)

    def test_the_runner_resubscribes_without_the_error_backoff(self):
        import run_kalshi_ws

        src = inspect.getsource(run_kalshi_ws)
        assert src.count('== "resubscribe"') == 2, (
            "both the Kalshi and Polymarket arms must handle the recycle"
        )
        tree = ast.parse(src)
        for fn_name in ("run_kalshi", "run_polymarket"):
            fn = next(
                n
                for n in ast.walk(tree)
                if isinstance(n, ast.AsyncFunctionDef) and n.name == fn_name
            )
            # The recycle branch must `continue`, not fall through to sleep(10).
            recycle_tests = [
                n
                for n in ast.walk(fn)
                if isinstance(n, ast.If)
                and "resubscribe" in ast.dump(n.test)
            ]
            assert recycle_tests, fn_name
            assert any(
                isinstance(s, ast.Continue)
                for t in recycle_tests
                for s in t.body
            ), f"{fn_name}: a planned recycle must not take the error backoff"

    def test_the_two_sockets_share_one_refresh_window(self):
        """Different windows would give the two venues different coverage."""
        from app.tasks.kalshi_ws import SUBSCRIPTION_REFRESH_SECONDS as k
        from app.tasks.polymarket_ws import SUBSCRIPTION_REFRESH_SECONDS as p

        assert k == p
        assert 0 < k <= 1800, "a refresh window longer than 30m re-opens the hole"


class TestPolymarketAssetIdsAreActuallyWritten:
    """The gap that made the Polymarket fast lane dead code.

    Production, 2026-08-30: of 687 live-or-starting-within-6h Polymarket
    markets, ZERO carried `clob_token_ids`. `_run_polymarket_ws_consumer` reads
    exactly that key to build its subscription, so it returned `no_asset_ids`
    and slept — every 60 seconds, forever. Alex's Hawaii @ Stanford card, whose
    blend carried Polymarket and nothing else, is what that cost.
    """

    def test_ingest_stamps_the_key_the_consumer_reads(self):
        """Writer/reader key parity. A rename on either side re-opens the gap."""
        meta = sub_market_metadata(
            event_id=42, matchup_title="A vs B", clob_token_ids=["111", "222"],
        )
        assert meta is not None
        assert "clob_token_ids" in meta
        consumer_src = inspect.getsource(
            polymarket_ws._run_polymarket_ws_consumer
        )
        assert '"clob_token_ids"' in consumer_src or "'clob_token_ids'" in consumer_src

    def test_token_ids_are_stored_as_strings(self):
        """Gamma returns decimal strings wider than a float64. A token id that
        has been through a JSON number no longer subscribes to anything."""
        meta = sub_market_metadata(
            event_id=1,
            matchup_title=None,
            clob_token_ids=[111222333444555666777888999, "42"],
        )
        assert meta["clob_token_ids"] == ["111222333444555666777888999", "42"]
        assert all(isinstance(t, str) for t in meta["clob_token_ids"])

    def test_absent_token_ids_stamp_nothing(self):
        """gotcha #53: a placeholder would satisfy a census while pointing at
        nothing, turning a countable gap into an invisible one."""
        for empty in (None, []):
            meta = sub_market_metadata(
                event_id=1, matchup_title=None, clob_token_ids=empty,
            )
            assert meta is None or "clob_token_ids" not in meta

    def test_the_key_alone_is_enough_to_produce_metadata(self):
        """A market with no matchup title and no event id still needs to be
        subscribable."""
        meta = sub_market_metadata(
            event_id=None, matchup_title=None, clob_token_ids=["7"],
        )
        assert meta == {"clob_token_ids": ["7"]}
