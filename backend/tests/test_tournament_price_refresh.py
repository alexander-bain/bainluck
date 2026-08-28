"""The targeted price refresh for register-pinned markets (UX-P139).

Alex, item 2: "state the production guarantee: with the freshness gates,
silently-stale data can never render — and show the UI treatment that proves
it."

The gates were already right. What they could not do is make a number fresh,
and measured 2026-08-26 the whole playoff grid was 27 hours old while
Polymarket snapshots overall were current to the minute — because Gamma caps
offset pagination at 2,000, so the scanning poll rotates a window and reaches a
given event about once a day. This task closes that by asking for the market
IDs the register already pins.

What is asserted here, and why each one is a defect that shipped or nearly did:

* **The register bounds the request.** A refresh that discovered markets would
  be a second scanning poll, at six times the cadence.
* **Every collection is walked**, players and matchups and reaches. The first
  version walked players only, which is 80 of 420 markets.
* **A zero-yield run is loud** (gotcha #53): "it returned" is not "it worked".

═══ WHAT CERT C-UX-P139-GRID-REGISTER-1 [P2] ADDED, AND WHY IT WAS NEEDED ═══

The bullet above was TRUE OF THE LOG LINE AND FALSE OF THE CONTRACT. Both rails
returned a bare ``verdict`` string that nothing reads; ``verdict_for`` produced a
non-authoritative unknown, whose ``blocks_success`` is False, so every zero-yield
run was recorded exactly like a working one. The cert executed it and got
``TaskVerdict(verdict='unknown', authoritative=False)`` for both
``no_prices_written`` and ``nothing_written``.

So the mutants below are the point of this file now: each one drives the real
function through a distinct way of achieving nothing — nothing to ask, nothing
returned, the fetch raising, the write raising, nothing written — and asserts
the resulting SUMMARY is not green THROUGH ``verdict_for``, which is the thing
task metrics actually consult. Asserting the terminal string alone would pass on
an unenrolled task, which is the no-op these two shipped as.
"""

from __future__ import annotations

import pytest

from app.tasks import tournament_price_refresh as rail
from app.tasks.tournament_price_refresh import (
    BATCH_SIZE,
    MAX_MARKETS,
    _refresh_registered_tournament_prices,
    _sync_tournament_results,
    registered_polymarket_conditions,
)
from app.utils.task_verdict import ENFORCED_TASKS, verdict_for
from app.utils.tournament_register import load_register


def _register(**overrides):
    base = {
        "players": [
            {
                "entity_key": "a",
                "sources": [
                    {"source": "polymarket", "market_external_id": "0xaaa", "outcome_id": 1},
                    {"source": "kalshi", "market_external_id": "KX-1", "outcome_id": 2},
                ],
            }
        ],
        "matchups": [
            {
                "matchup_key": "m",
                "sources": [
                    {
                        "source": "polymarket",
                        "market_external_id": "0xbbb",
                        "sides": {
                            "a": {"outcome_id": 10},
                            "b": {"outcome_id": 11},
                        },
                    }
                ],
            }
        ],
        "reaches": [
            {
                "draw": "mens-singles",
                "entity_key": "a",
                "round": "SF",
                "sources": [
                    {"source": "polymarket", "market_external_id": "0xccc", "outcome_id": 20},
                    {"source": "kalshi", "market_external_id": None, "outcome_id": None},
                ],
            }
        ],
    }
    base.update(overrides)
    return base


class TestWhatGetsRefreshed:
    def test_walks_players_matchups_AND_reaches(self):
        # The first version walked players only — 80 of ~420 markets, and the
        # 336 that ARE the bracket grid were not among them.
        conditions = registered_polymarket_conditions(_register())
        assert set(conditions) == {"0xaaa", "0xbbb", "0xccc"}

    def test_collects_both_sides_of_a_matchup(self):
        conditions = registered_polymarket_conditions(_register())
        assert sorted(conditions["0xbbb"]) == [10, 11]

    def test_ignores_kalshi_entirely(self):
        # Kalshi is polled by its own task on its own cadence, and this method
        # asks Gamma. A Kalshi ticker in the list would be a 404 per batch.
        conditions = registered_polymarket_conditions(_register())
        assert "KX-1" not in conditions

    def test_a_missing_source_block_pins_nothing(self):
        # A `missing` block carries no identity by construction
        # (`MISSING_ENTRY_HAS_IDENTITY`), so a censused absence costs no request.
        conditions = registered_polymarket_conditions(_register())
        assert None not in conditions
        assert all(condition.startswith("0x") for condition in conditions)

    def test_an_empty_register_asks_for_nothing(self):
        assert registered_polymarket_conditions({}) == {}

    def test_survives_a_malformed_collection_without_dropping_the_rest(self):
        register = _register(players=[None, "nonsense", _register()["players"][0]])
        conditions = registered_polymarket_conditions(register)
        assert "0xaaa" in conditions


class TestTheCommittedRegisterIsABoundedAsk:
    def test_the_us_open_refresh_is_a_handful_of_requests(self):
        register = load_register("us-open", "2026")
        assert register is not None
        conditions = registered_polymarket_conditions(register)
        # ~366 conditions today: 336 reach + 28 matchups + 2 outright fields.
        assert 300 < len(conditions) < MAX_MARKETS
        requests = -(-len(conditions) // BATCH_SIZE)
        # Cheap enough for a 10-minute cadence against a ~1,000/hr limit.
        assert requests <= 12

    def test_every_reach_market_is_in_the_refresh_set(self):
        """The grid's 336 markets are the whole reason this task exists."""
        register = load_register("us-open", "2026")
        assert register is not None
        conditions = set(registered_polymarket_conditions(register))
        pinned = {
            block["market_external_id"]
            for reach in register["reaches"]
            for block in reach["sources"]
            if block.get("market_external_id")
        }
        assert pinned
        assert pinned <= conditions


# ---------------------------------------------------------------------------
# CERT C-UX-P139-GRID-REGISTER-1 [P2] — the terminal contract, per mutant
# ---------------------------------------------------------------------------


class _Market:
    """The one attribute the rail reads off a Gamma market before writing."""

    def __init__(self, condition_id: str):
        self.condition_id = condition_id


class _Service:
    def __init__(self, markets=None, raises: Exception | None = None):
        self._markets = markets or []
        self._raises = raises

    async def get_markets_by_conditions(self, conditions, batch_size=None):
        if self._raises is not None:
            raise self._raises
        return self._markets


def _arm_refresh(monkeypatch, *, register=None, service=None, writer=None):
    """Point the rail at scripted collaborators. No DB, no network."""
    import app.services.polymarket_api as poly
    import app.utils.tournament_register as reg

    monkeypatch.setattr(reg, "load_register", lambda *a, **k: register)
    monkeypatch.setattr(poly, "PolymarketAPIService", lambda *a, **k: service or _Service())
    if writer is not None:
        monkeypatch.setattr(rail, "_write_refreshed_prices", writer)


class TestThePriceRefreshRailCannotAchieveNothingQuietly:
    """Five ways to refresh no prices. None of them may read GREEN.

    This rail's failure is invisible on the page BY CONSTRUCTION: a dead refresh
    does not blank the grid, it lets every number on it age wearing whatever
    freshness word the gates award. The 27-hour grid that caused this task to be
    written is exactly what a permanently-dead version of it looks like.
    """

    def test_the_rail_is_enrolled_so_its_terminal_is_authoritative(self):
        # Enrolment WITHOUT a terminal is a no-op, and a terminal WITHOUT
        # enrolment is ignored. Both halves, or neither is worth anything.
        assert "tournament_price_refresh" in ENFORCED_TASKS

    async def test_an_unreadable_register_is_failed_not_no_work(self, monkeypatch):
        """The registers are committed files. None loading is our breakage."""
        _arm_refresh(monkeypatch, register=None)
        stats = await _refresh_registered_tournament_prices([("us-open", "2026")])

        assert stats["terminal"] == "failed"
        assert stats["reason"] == "no_readable_register"
        assert verdict_for("tournament_price_refresh", stats).is_green is False

    async def test_a_register_pinning_no_polymarket_identity_is_no_work(self, monkeypatch):
        """A retired tournament is honest — and still not a healthy run."""
        _arm_refresh(monkeypatch, register={"players": [], "matchups": [], "reaches": []})
        stats = await _refresh_registered_tournament_prices([("us-open", "2026")])

        assert stats["terminal"] == "no_work"
        verdict = verdict_for("tournament_price_refresh", stats)
        assert verdict.is_green is False
        # Authoritative, so it BLOCKS the success counter rather than being
        # waved through as a legacy return.
        assert verdict.authoritative is True
        assert verdict.blocks_success is True

    async def test_a_raising_fetch_is_failed_and_names_the_cause(self, monkeypatch):
        _arm_refresh(
            monkeypatch,
            register=_register(),
            service=_Service(raises=RuntimeError("gamma 429")),
        )
        stats = await _refresh_registered_tournament_prices([("us-open", "2026")])

        assert stats["terminal"] == "failed"
        assert stats["reason"] == "fetch_failed"
        assert any("gamma 429" in e for e in stats["errors"])
        assert verdict_for("tournament_price_refresh", stats).is_green is False

    async def test_zero_markets_returned_for_ids_we_pinned_is_failed(self, monkeypatch):
        """We asked BY ID. Getting none back is a broken link, not an empty day."""
        _arm_refresh(monkeypatch, register=_register(), service=_Service(markets=[]))
        stats = await _refresh_registered_tournament_prices([("us-open", "2026")])

        assert stats["terminal"] == "failed"
        assert stats["reason"] == "no_markets_returned"
        assert stats["conditions_requested"] > 0
        assert verdict_for("tournament_price_refresh", stats).is_green is False

    async def test_a_write_that_raises_is_failed_rather_than_a_bare_exception(
        self, monkeypatch
    ):
        """The quietest failure: fetched fine, wrote nothing, page unchanged."""
        async def _boom(markets, stats, *, now):
            raise RuntimeError("deadlock detected")

        _arm_refresh(
            monkeypatch,
            register=_register(),
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_boom,
        )
        stats = await _refresh_registered_tournament_prices([("us-open", "2026")])

        assert stats["terminal"] == "failed"
        assert stats["reason"] == "write_failed"
        assert any("deadlock detected" in e for e in stats["errors"])
        assert verdict_for("tournament_price_refresh", stats).is_green is False

    async def test_markets_returned_but_no_snapshot_written_is_failed(self, monkeypatch):
        """The zero-yield mutant. Everything 'worked' and nothing landed."""
        async def _writes_nothing(markets, stats, *, now):
            stats["unpriced"] = len(markets)

        _arm_refresh(
            monkeypatch,
            register=_register(),
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_writes_nothing,
        )
        stats = await _refresh_registered_tournament_prices([("us-open", "2026")])

        assert stats["terminal"] == "failed"
        assert stats["reason"] == "no_prices_written"
        assert stats["snapshots_written"] == 0
        assert verdict_for("tournament_price_refresh", stats).is_green is False

    async def test_a_run_that_wrote_prices_is_the_only_green(self, monkeypatch):
        async def _writes(markets, stats, *, now):
            stats["outcomes_updated"] = 2
            stats["snapshots_written"] = 2

        _arm_refresh(
            monkeypatch,
            register=_register(),
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_writes,
        )
        stats = await _refresh_registered_tournament_prices([("us-open", "2026")])

        assert stats["terminal"] == "complete"
        assert verdict_for("tournament_price_refresh", stats).is_green is True

    async def test_one_register_failing_beside_one_that_worked_is_partial(
        self, monkeypatch
    ):
        """Coverage is never implied. A named error downgrades a written run."""
        import app.services.polymarket_api as poly
        import app.utils.tournament_register as reg

        loaded = {"us-open": _register()}
        monkeypatch.setattr(
            reg, "load_register", lambda tournament, season: loaded.get(tournament)
        )
        monkeypatch.setattr(
            poly, "PolymarketAPIService", lambda *a, **k: _Service(markets=[_Market("0xaaa")])
        )

        async def _writes(markets, stats, *, now):
            stats["snapshots_written"] = 1

        monkeypatch.setattr(rail, "_write_refreshed_prices", _writes)
        stats = await _refresh_registered_tournament_prices(
            [("us-open", "2026"), ("roland-garros", "2026")]
        )

        assert stats["terminal"] == "complete"
        assert stats["errors"]
        verdict = verdict_for("tournament_price_refresh", stats)
        assert verdict.verdict == "partial"
        assert verdict.is_green is False


class TestTheResultsSyncRailCannotAchieveNothingQuietly:
    """A dead results sync does not show a wrong score. It shows none, behind a
    cache that expires — and an honest empty section reads the same whether the
    rail is healthy or has been dead for a week."""

    @staticmethod
    def _arm(monkeypatch, *, results=None, fetch_raises=None, write_raises=None):
        import app.services.espn_tennis as espn
        import app.tasks.redis_state as redis_state

        async def _fetch(event_name):
            if fetch_raises is not None:
                raise fetch_raises
            return results if results is not None else {"errors": []}

        class _Redis:
            async def setex(self, key, ttl, value):
                if write_raises is not None:
                    raise write_raises
                return True

        monkeypatch.setattr(espn, "fetch_tournament_results", _fetch)
        monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: _Redis())

    def test_the_rail_is_enrolled_so_its_terminal_is_authoritative(self):
        assert "tournament_results_sync" in ENFORCED_TASKS

    async def test_nothing_to_sync_is_no_work(self, monkeypatch):
        self._arm(monkeypatch)
        stats = await _sync_tournament_results([])

        assert stats["terminal"] == "no_work"
        assert verdict_for("tournament_results_sync", stats).is_green is False

    async def test_a_raising_fetch_writes_nothing_and_is_failed(self, monkeypatch):
        self._arm(monkeypatch, fetch_raises=RuntimeError("espn 503"))
        stats = await _sync_tournament_results([("us-open", "US Open")])

        assert stats["terminal"] == "failed"
        assert stats["reason"] == "nothing_written"
        assert any("espn 503" in e for e in stats["errors"])
        assert verdict_for("tournament_results_sync", stats).is_green is False

    async def test_a_cache_write_that_fails_is_failed_not_a_quiet_error_entry(
        self, monkeypatch
    ):
        """Fetched fine, cached nothing. The route reads the cache, so this is
        the same outcome as never having run — and it used to read GREEN."""
        self._arm(monkeypatch, write_raises=RuntimeError("redis down"))
        stats = await _sync_tournament_results([("us-open", "US Open")])

        assert stats["terminal"] == "failed"
        assert stats["reason"] == "nothing_written"
        assert stats["written"] == 0
        assert verdict_for("tournament_results_sync", stats).is_green is False

    async def test_a_cached_payload_is_complete(self, monkeypatch):
        self._arm(monkeypatch, results={"errors": [], "matches": [{"id": 1}]})
        stats = await _sync_tournament_results([("us-open", "US Open")])

        assert stats["terminal"] == "complete"
        assert stats["written"] == 1
        assert verdict_for("tournament_results_sync", stats).is_green is True

    async def test_a_partial_fetch_is_written_but_never_green(self, monkeypatch):
        """Half the tours is better than none, and it is not a healthy run."""
        self._arm(monkeypatch, results={"errors": ["womens scoreboard 500"]})
        stats = await _sync_tournament_results([("us-open", "US Open")])

        assert stats["terminal"] == "complete"
        assert stats["written"] == 1
        verdict = verdict_for("tournament_results_sync", stats)
        assert verdict.verdict == "partial"
        assert verdict.is_green is False


class TestTheContractIsReadThroughTheEnrolmentNotAroundIt:
    """The no-op this cert finding was: a terminal nothing consults.

    Kept as a live demonstration rather than a comment, because the failure it
    describes is silent — an unenrolled rail returning a perfect terminal reads
    exactly as green as one returning nothing at all.
    """

    @pytest.mark.parametrize("terminal", ["failed", "no_work", "complete"])
    def test_an_unenrolled_label_launders_every_terminal_into_one_unknown(
        self, terminal
    ):
        verdict = verdict_for("some_unenrolled_rail", {"terminal": terminal})
        assert verdict.verdict == "unknown"
        assert verdict.authoritative is False
        assert verdict.blocks_success is False


class TestAnExplicitEmptyTargetListIsNotAFullRun:
    """`tournaments or DEFAULT` turned "refresh nothing" into "refresh
    everything", and made the `no_work` terminal unreachable — a guard that
    cannot be entered is a guard that was never tested."""

    async def test_the_price_rail_treats_an_empty_list_as_no_work(self, monkeypatch):
        _arm_refresh(monkeypatch, register=_register())
        stats = await _refresh_registered_tournament_prices([])

        assert stats["terminal"] == "no_work"
        assert stats["tournaments"] == 0
        assert verdict_for("tournament_price_refresh", stats).is_green is False

    async def test_the_default_target_is_still_the_live_tournament(self, monkeypatch):
        """`None` means "the scheduled run", and it still means the US Open."""
        seen: list[tuple[str, str]] = []

        import app.utils.tournament_register as reg

        def _load(tournament, season):
            seen.append((tournament, season))
            return None

        monkeypatch.setattr(reg, "load_register", _load)
        await _refresh_registered_tournament_prices()
        assert seen == [("us-open", "2026")]

    async def test_the_results_rail_default_is_still_the_live_tournament(
        self, monkeypatch
    ):
        seen: list[str] = []

        import app.services.espn_tennis as espn
        import app.tasks.redis_state as redis_state

        async def _fetch(event_name):
            seen.append(event_name)
            return {"errors": []}

        class _Redis:
            async def setex(self, key, ttl, value):
                return True

        monkeypatch.setattr(espn, "fetch_tournament_results", _fetch)
        monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: _Redis())
        await _sync_tournament_results()
        assert seen == ["US Open"]
