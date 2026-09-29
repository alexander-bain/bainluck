"""#9605 — an imminent Polymarket field no pass had read for a day is re-read, oldest first.

THE SPECIMEN (production, 2026-09-29 11:11Z, #9605): on the first day of MLB's
postseason, search answered "MLB Playoffs: Team to advance to NLDS — Atlanta
Braves 71%" while Polymarket quoted the Braves at 56.5. Our parent 60087232
(Gamma 956263) and its ALDS sibling 60087233 (956262) were last stamped
09-21 16:30Z; the ALCS sibling 60087229 (956264, resolving 10-15) refreshed
normally.

WHY NOTHING RE-READ THEM: the sunk pass's rotate arm takes only rows resolving
past the 14-day horizon, and the imminent arm takes 300 a pass soonest-resolving
first from a pool at its limit. NLDS/ALDS resolve 10-05, so at 09-21 23:59Z they
left the rotate arm for the imminent arm's tail — 1,970 rows ahead of them — and
no arm ever reached them again. 2,140 imminent rows were in the same state.

THE FIX is ordering, no writer: a starved arm selects imminent rows unstamped for
24h, oldest stamp first, read after the imminent arm and before the rotate arm.
The poll's writer re-prices the field and re-stamps the volume.

FIXTURE — `tests/fixtures/polymarket_sunk_starved_9605/event-956263.json.gz`:
LOSSLESS venue bytes, `GET gamma-api.polymarket.com/events/956263` read
2026-09-29 11:35Z (gzip only; decompressed SHA256 `8a9779cf…b2b5`).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from app.tasks import polymarket as poly
from tests.test_polymarket_sunk_open_events_6758 import (
    _Gamma,
    _market_rows,
    _Redis,
    _Row,
    _SelectorSession,
    _service,
)
from tests.test_polymarket_under_snapshot_book_p097 import RecordingSession, _bound_params

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "polymarket_sunk_starved_9605"
    / "event-956263.json.gz"
)
SPECIMEN_BYTES = gzip.decompress(FIXTURE.read_bytes())
SPECIMEN_RAW = json.loads(SPECIMEN_BYTES)
SPECIMEN = "956263"
SPECIMEN_ROW_ID = 60087232
BRAVES = next(m for m in SPECIMEN_RAW["markets"] if m["groupItemTitle"] == "Atlanta Braves")


async def _run(
    monkeypatch, *, head=(), childless=(), unlinked=(), imminent=(), rotate=(),
    starved=(), gamma=None, redis=None,
):
    """Drive the REAL pass. The selector answers in execution order: imminent,
    rotate, head, unlinked-game, post-start, childless-game, then the starved
    arm (executed last, read after the imminent arm)."""
    gamma = gamma or _Gamma(by_id={SPECIMEN: SPECIMEN_RAW})
    redis = redis or _Redis()
    selector = _SelectorSession(
        [
            list(imminent), list(rotate), list(head), list(unlinked), [],
            list(childless), list(starved),
        ]
    )
    writer = RecordingSession()
    sessions = iter([selector])

    @asynccontextmanager
    async def _fake_session():
        yield next(sessions, writer)

    async def _no_link():
        return 0

    monkeypatch.setattr(poly, "get_task_session", _fake_session)
    monkeypatch.setattr(poly, "link_polymarket_sub_markets", _no_link)
    monkeypatch.setattr(poly, "_SUNK_POLY_DIRECT_PAUSE_S", 0)
    monkeypatch.setattr("app.services.polymarket_api.PolymarketAPIService", lambda *a, **k: _service(gamma))
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: redis)
    stats = await poly._recover_sunk_polymarket_events()
    return stats, writer, selector, gamma, redis


def _batches(gamma):
    return [u.params.get_list("id") for u in gamma.requests if u.params.get_list("id")]


def _read_ids(gamma):
    return [i for b in _batches(gamma) for i in b]


def _outcome_prices(writer):
    """outcome name -> current_probability, for every futures_outcomes insert."""
    out = {}
    for stmt in writer.statements:
        if getattr(getattr(stmt, "table", None), "name", None) == "futures_outcomes" and stmt.is_insert:
            p = _bound_params(stmt)
            out.setdefault(p.get("name"), []).append(p.get("current_probability"))
    return out


class TestTheFixtureIsTheSpecimen:
    def test_the_bytes_are_the_ones_read(self):
        assert hashlib.sha256(SPECIMEN_BYTES).hexdigest().startswith("8a9779cf")

    def test_it_is_the_open_nlds_field_the_venue_prices(self):
        assert str(SPECIMEN_RAW["id"]) == SPECIMEN
        assert SPECIMEN_RAW["slug"] == "mlb-playoffs-team-to-advance-to-nlds"
        assert SPECIMEN_RAW["active"] is True and SPECIMEN_RAW["closed"] is False
        assert len(SPECIMEN_RAW["markets"]) == 15
        assert json.loads(BRAVES["outcomePrices"]) == ["0.57", "0.43"]
        assert BRAVES["closed"] is False

    def test_the_writer_would_find_priced_legs(self):
        # A reach defect, not a venue with nothing to price.
        event = _service(_Gamma())._parse_event(SPECIMEN_RAW)
        assert poly.sunk_event_is_open(event)
        n_children, n_priced = poly.sunk_event_child_census(event)
        assert n_children == 15 and n_priced >= 4


class TestTheStarvedRowIsRead:
    @pytest.mark.asyncio
    async def test_behind_a_full_imminent_arm_it_is_read_this_pass(self, monkeypatch):
        imminent = [_Row(i, str(4_000_000 + i)) for i in range(poly._SUNK_POLY_IMMINENT_MAX)]
        stats, _w, _s, gamma, _r = await _run(
            monkeypatch, imminent=imminent, starved=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
        )
        assert stats["starved_selected"] == 1
        assert SPECIMEN in _read_ids(gamma)

    @pytest.mark.asyncio
    async def test_the_re_read_writes_the_venues_price_and_the_stamp(self, monkeypatch):
        imminent = [_Row(i, str(4_000_000 + i)) for i in range(poly._SUNK_POLY_IMMINENT_MAX)]
        _st, writer, *_ = await _run(
            monkeypatch, imminent=imminent, starved=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
        )
        rows = _market_rows(writer)
        assert SPECIMEN in rows, "the parent is re-written (stamps volume_updated_at)"
        assert rows[SPECIMEN][0]["status"] == "open"
        prices = _outcome_prices(writer)
        braves = [p for p in prices.get("Atlanta Braves", []) if p is not None]
        assert braves, sorted(k for k in prices if k)[:10]
        # The venue's number, not the stored 0.71 from 09-21.
        assert all(abs(p - 0.57) < 0.02 for p in braves), braves

    @pytest.mark.asyncio
    async def test_without_the_arm_a_full_imminent_arm_never_reaches_it(self, monkeypatch):
        # CONTROL: the same pass with the specimen where production had it —
        # behind the imminent arm's 300, in no other arm — reads 300 rows and
        # not the specimen, and writes no Braves price.
        imminent = [_Row(i, str(4_000_000 + i)) for i in range(poly._SUNK_POLY_IMMINENT_MAX)]
        _st, writer, _s, gamma, _r = await _run(monkeypatch, imminent=imminent)
        assert len(_read_ids(gamma)) == poly._SUNK_POLY_IMMINENT_MAX
        assert SPECIMEN not in _read_ids(gamma)
        assert "Atlanta Braves" not in _outcome_prices(writer)
        assert SPECIMEN not in _market_rows(writer)


class TestTheOrder:
    @pytest.mark.asyncio
    async def test_it_goes_after_the_imminent_arm_and_before_the_rotate_arm(self, monkeypatch):
        _st, _w, _s, gamma, _r = await _run(
            monkeypatch,
            imminent=[_Row(2, "4000001")],
            starved=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
            rotate=[_Row(90_000_000, "5000001")],
        )
        assert _read_ids(gamma) == ["4000001", SPECIMEN, "5000001"]

    @pytest.mark.asyncio
    async def test_an_id_in_the_imminent_arm_and_this_arm_is_read_once(self, monkeypatch):
        _st, writer, _s, gamma, _r = await _run(
            monkeypatch,
            imminent=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
            starved=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
        )
        assert _read_ids(gamma) == [SPECIMEN]
        assert len(_market_rows(writer)[SPECIMEN]) == 1

    @pytest.mark.asyncio
    async def test_a_starved_only_selection_is_not_an_empty_pass(self, monkeypatch):
        stats, *_ = await _run(monkeypatch, starved=[_Row(SPECIMEN_ROW_ID, SPECIMEN)])
        assert stats["terminal"] != "no_sunk_open_events"
        assert stats["events_reached"] == 1

    @pytest.mark.asyncio
    async def test_the_rotate_cursor_is_untouched_by_a_starved_row(self, monkeypatch):
        rotate = [_Row(i, str(5_000_000 + i)) for i in range(1, 4)]
        _st, _w, _s, _g, redis = await _run(
            monkeypatch, starved=[_Row(SPECIMEN_ROW_ID, SPECIMEN)], rotate=rotate,
        )
        # The specimen's id (60,087,232) is far above the last rotate row read.
        assert redis.kv[poly._SUNK_POLY_CURSOR_KEY] == "3"

    @pytest.mark.asyncio
    async def test_the_pool_limit_is_reported(self, monkeypatch):
        full = [_Row(i, str(6_000_000 + i)) for i in range(poly._SUNK_POLY_STARVED_MAX)]
        stats, *_ = await _run(monkeypatch, starved=full, gamma=_Gamma())
        assert stats["starved_pool_at_limit"] is True
        stats, *_ = await _run(monkeypatch, starved=full[:-1], gamma=_Gamma())
        assert stats["starved_pool_at_limit"] is False


class TestTheStarvedSelector:
    SQL = str(poly._SUNK_POLY_STARVED_SQL)

    def _predicates(self):
        return re.sub(r"\s+", " ", "\n".join(
            line.split("--")[0] for line in self.SQL.lower().splitlines()
        ))

    def test_it_is_the_shared_sunk_predicate_on_its_own_staleness(self):
        sql = self._predicates()
        assert "fm.source = 'polymarket'" in sql
        assert "fm.status = 'open'" in sql
        assert "fm.external_id not like '0x%'" in sql
        assert "make_interval(hours => :starved_stale_hours)" in sql
        # The resolution FLOOR stays on the shared six hours (gotcha #41).
        assert "fm.resolution_date > now() - make_interval(hours => :stale_hours)" in sql
        assert "not (fm.external_id = any(:refused))" in sql

    def test_it_is_bounded_to_the_imminent_window(self):
        sql = self._predicates()
        assert "fm.resolution_date <= now() + make_interval(days => :horizon_days)" in sql

    def test_oldest_stamp_first(self):
        assert "order by fm.volume_updated_at nulls first, fm.id" in self._predicates()

    def test_it_is_looser_than_the_imminent_cycle(self):
        # A row the imminent arm still reaches (every 6h) never qualifies.
        assert poly.SUNK_POLY_STARVED_STALE_HOURS > poly.SUNK_POLY_STALE_HOURS

    @pytest.mark.asyncio
    async def test_every_bind_is_supplied(self, monkeypatch):
        _st, _w, selector, _g, _r = await _run(
            monkeypatch, starved=[_Row(SPECIMEN_ROW_ID, SPECIMEN)],
        )
        stmt, params = next(c for c in selector.calls if c[0] == self.SQL)
        binds = set(re.findall(r"(?<!:):([a-z_]+)", stmt))
        assert binds <= set(params), binds - set(params)
        assert params["starved_stale_hours"] == poly.SUNK_POLY_STARVED_STALE_HOURS
        assert params["horizon_days"] == poly.SUNK_POLY_IMMINENT_DAYS
        assert params["max_rows"] == poly._SUNK_POLY_STARVED_MAX
