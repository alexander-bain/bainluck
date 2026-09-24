"""#6758 — an open Polymarket event that has sunk out of the discovery window.

From other-model Brief 13, vendored into the repo by authority/431.

Drives the REAL request builders (`PolymarketAPIService.get_events`,
`.get_events_by_ids`), the REAL parser, the REAL price resolver and the REAL
writer (`_process_event_batch`). Only the network (httpx.MockTransport), the DB
session (the repo's own `RecordingSession`) and Redis are replaced.

FIXTURES — `tests/fixtures/polymarket_sunk_open_6758/`, gzipped, 30 KB total
(the brief read 3.4 MB from an out-of-tree `$B13_RAW`, which committed as-is is a
CI collection error, not a test). Two kinds, and the difference matters:

* SUBJECT, LOSSLESS — `events-by-id-972401-1013438.json.gz` (the two named
  events) and `weather-event.json.gz` (one element of the same venue read, the
  non-sports control). Original venue bytes, gzip only; their decompressed
  SHA256 still match the artifact's own `SHA256SUMS` (`96b04eab…`, `8321aed4…`).
  Everything the new code is judged on reads these.
* DIAGNOSIS, PROJECTED — `gamma-page-offset0.json.gz` /
  `gamma-page-offset1900.json.gz`. Each element keeps ONLY `id`, `startDate` and
  `tags[].label` — the only fields the two `TestTheWindow` page arms read —
  with element order and count (100 each) preserved, because the sort is what
  makes the floor a floor. These two arms prove WHY the named event is
  unreachable from the list side; they do not exercise the new code. The
  projection is `artifacts-431/6758-fixtures/vendor_fixtures.py`, which is also
  how they are regenerated.

The two DERIVED fixtures (`_book_opened`, `_closed`) are built in this file from
the subject bytes and say exactly which fields they change.
"""
from __future__ import annotations

import copy
import gzip
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from app.services.polymarket_api import PolymarketAPIService
from app.tasks import polymarket as poly
from tests.test_polymarket_under_snapshot_book_p097 import RecordingSession, _bound_params

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "polymarket_sunk_open_6758"

NAMED = "1013438"   # Dumont–Perez, listed 2026-09-12, fights 2026-09-26: EMPTY books
TRADED = "972401"   # UFC 331 Tsarukyan–Ruffy, listed 2026-09-05: REAL traded books
MONEYLINE_CID_NAMED = "0xf4cf69164b08"


def _instant(stamp: str):
    """Gamma mixes `...:30Z` and `...:30.11892Z`; compare instants, not strings.

    Own parser because the repo's `_parse_timestamp` leans on `fromisoformat`,
    which only accepts 5-digit fractions from Python 3.11 on. Production and CI
    are past that, but the parser stays: it is the assertion's own clock, and it
    must not move when the repo's does.
    """
    from datetime import datetime, timezone
    head, _, frac = stamp.rstrip("Z").partition(".")
    base = datetime.strptime(head, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    return base.replace(microsecond=int((frac + "000000")[:6])) if frac else base


def _load(name):
    return json.loads(gzip.decompress((FIXTURES / name).read_bytes()))


PAGE_0 = _load("gamma-page-offset0.json.gz")
PAGE_1900 = _load("gamma-page-offset1900.json.gz")
BY_ID = {str(e["id"]): e for e in _load("events-by-id-972401-1013438.json.gz")}
WEATHER = _load("weather-event.json.gz")  # one element of the same venue read, unedited
BY_ID[str(WEATHER["id"])] = WEATHER


def _book_opened(raw_event):
    """DERIVED, SYNTHETIC: the named event on the day its moneyline first trades.

    Only the moneyline's five book fields change; the 18 props keep their real
    empty books. No such bytes exist yet — the venue has never traded it.
    """
    ev = copy.deepcopy(raw_event)
    ml = next(m for m in ev["markets"] if m.get("sportsMarketType") == "moneyline")
    ml.update(bestBid=0.55, bestAsk=0.58, lastTradePrice=0.57,
              outcomePrices='["0.565", "0.435"]', volume24hr=1200.0, spread=0.03)
    return ev


def _archived(raw_event):
    """DERIVED: the traded event after the venue takes it off the board.

    The flag shape is the one Gamma actually served for Brazil event 871036 on
    2026-09-22 — `active=false, closed=false, archived=true` — which is NOT the
    `_closed` shape below and is the reason both are here. 16 of 120 oldest-id
    served-and-stale parents read exactly this way; they are invisible to a list
    read and 200-with-flags to a direct one.
    """
    ev = copy.deepcopy(raw_event)
    ev["active"], ev["closed"], ev["archived"] = False, False, True
    return ev


def _closed(raw_event):
    """DERIVED: the traded event after it settles. Gamma keeps `active=true`."""
    ev = copy.deepcopy(raw_event)
    ev["closed"] = True
    return ev


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------
_DIRECT_PATH = re.compile(r"^/events/(?P<id>[^/]+)$")


class _Gamma:
    """httpx.MockTransport handler: records every request the REAL client built.

    THE LIST AND THE DIRECT ADDRESS ARE TWO DIFFERENT ENDPOINTS HERE BECAUSE
    THEY ARE TWO DIFFERENT ENDPOINTS AT THE VENUE — and that difference IS the
    #7930 specimen. Measured against Gamma 2026-09-22: `/events?id=871036`
    answers `200 []` for an archived event while `/events/871036` answers 200
    with `archived: true` and its four markets; `/events/999999999` answers 404.
    A fake that served both from one dict would make the bug unreproducible, so
    `hidden_from_list` holds the events only the direct address can see.
    """

    def __init__(self, by_id=None, *, status_for_batch=None,
                 hidden_from_list=None, status_for_direct=None):
        self.by_id = dict(BY_ID if by_id is None else by_id)
        self.hidden_from_list = dict(hidden_from_list or {})
        self.requests: list[httpx.URL] = []
        self.status_for_batch = status_for_batch or {}
        self.status_for_direct = dict(status_for_direct or {})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url)
        q = request.url.params
        if request.url.path == "/events" and q.get_list("id"):
            n = sum(1 for u in self.requests if u.params.get_list("id"))
            code = self.status_for_batch.get(n)
            if code:
                return httpx.Response(code, json={"error": "x"}, request=request)
            ids = q.get_list("id")
            # Gamma promises neither order nor length — and it omits archived
            # events from a list read entirely, which `hidden_from_list` models.
            return httpx.Response(200, json=[self.by_id[i] for i in reversed(ids) if i in self.by_id])
        if request.url.path == "/events":
            off = int(q.get("offset", "0"))
            page = {0: PAGE_0, 1900: PAGE_1900}.get(off)
            return httpx.Response(200 if page is not None else 404, json=page or [])
        direct = _DIRECT_PATH.match(request.url.path)
        if direct:
            eid = direct.group("id")
            code = self.status_for_direct.get(eid)
            if code:
                return httpx.Response(code, json={"error": "x"}, request=request)
            body = self.hidden_from_list.get(eid, self.by_id.get(eid))
            if body is None:
                return httpx.Response(404, json={"error": "not found"}, request=request)
            return httpx.Response(200, json=body)
        return httpx.Response(404, json=[])


def _service(gamma: _Gamma) -> PolymarketAPIService:
    svc = PolymarketAPIService()
    svc.gamma_client = httpx.AsyncClient(
        base_url=PolymarketAPIService.GAMMA_BASE_URL, transport=httpx.MockTransport(gamma)
    )
    return svc


class _Rows:
    def __init__(self, rows): self._rows = rows
    def fetchall(self): return self._rows


class _Row:
    def __init__(self, ident, ext): self.id, self.external_id = ident, ext


class _SelectorSession:
    def __init__(self, answers): self.answers, self.calls = list(answers), []
    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), dict(params or {})))
        return _Rows(self.answers.pop(0) if self.answers else [])


class _Redis:
    def __init__(self, cursor=None, refused=(), broken=False):
        self.kv, self.sets, self.broken = ({} if cursor is None else {poly._SUNK_POLY_CURSOR_KEY: str(cursor)}), {poly._SUNK_POLY_REFUSED_KEY: set(refused)}, broken
    def _chk(self):
        if self.broken: raise ConnectionError("redis down")
    def get(self, k): self._chk(); return self.kv.get(k)
    def setex(self, k, ttl, v): self._chk(); self.kv[k] = v
    def smembers(self, k): self._chk(); return set(self.sets.get(k, ()))
    def sadd(self, k, *v): self._chk(); self.sets.setdefault(k, set()).update(v)
    def expire(self, k, ttl): self._chk()


async def _run(monkeypatch, imminent, rotate=(), *, gamma=None, redis=None, rotate_after_wrap=None, **kw):
    gamma = gamma or _Gamma()
    redis = redis or _Redis()
    answers = [list(imminent), list(rotate)]
    if rotate_after_wrap is not None:
        answers.append(list(rotate_after_wrap))
    selector, writer = _SelectorSession(answers), RecordingSession()
    sessions = iter([selector])

    @asynccontextmanager
    async def _fake_session():
        yield next(sessions, writer)

    async def _no_link():
        return 0

    monkeypatch.setattr(poly, "get_task_session", _fake_session)
    monkeypatch.setattr(poly, "link_polymarket_sub_markets", _no_link)
    monkeypatch.setattr("app.services.polymarket_api.PolymarketAPIService", lambda *a, **k: _service(gamma))
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: redis)
    stats = await poly._recover_sunk_polymarket_events(**kw)
    return stats, writer, selector, gamma, redis


def _market_rows(writer):
    """external_id -> bound params, for every futures_markets upsert the writer emitted."""
    out = {}
    for stmt in writer.statements:
        if getattr(getattr(stmt, "table", None), "name", None) == "futures_markets" and stmt.is_insert:
            p = _bound_params(stmt)
            out.setdefault(p["external_id"], []).append(p)
    return out


def _parent_update_set(writer, external_id):
    """The ON CONFLICT DO UPDATE clause the writer emitted for one parent.

    The ship is about rows that ALREADY EXIST, so the INSERT arm's values are
    the wrong half to assert on — a `status` read from `stmt.compile()` params
    would pass while the update arm wrote something else. This reads the clause
    Postgres would actually run for a conflicting row.
    """
    for stmt in writer.statements:
        if getattr(getattr(stmt, "table", None), "name", None) != "futures_markets":
            continue
        if not stmt.is_insert:
            continue
        if _bound_params(stmt).get("external_id") != external_id:
            continue
        clause = getattr(stmt, "_post_values_clause", None)
        values = getattr(clause, "update_values_to_set", None)
        if values:
            return {str(getattr(k, "name", k)): v for k, v in dict(values).items()}
    raise AssertionError(f"no futures_markets upsert for {external_id!r}")


def _literal(value):
    """The Python value behind a bound literal in an update clause."""
    return getattr(value, "value", value)


def _outcome_names(writer):
    return [
        _bound_params(s).get("name") for s in writer.statements
        if getattr(getattr(s, "table", None), "name", None) == "futures_outcomes" and s.is_insert
    ]


# --------------------------------------------------------------------------
# 1. WHY the named event cannot be reached (list side) — proved on saved bytes
# --------------------------------------------------------------------------
class TestTheWindow:
    @pytest.mark.asyncio
    async def test_the_real_request_and_the_floor_of_what_it_can_return(self):
        gamma = _Gamma()
        svc = _service(gamma)
        last = await svc.get_events(active=True, closed=False, limit=100, offset=1900,
                                    order="startDate", ascending=False)
        q = gamma.requests[-1].params
        assert (q["order"], q["ascending"], q["offset"], q["closed"]) == ("startDate", "false", "1900", "false")
        starts = [_instant(e["startDate"]) for e in last]  # instants, not strings
        assert starts == sorted(starts, reverse=True), "the sort is what makes the floor a floor"
        floor = min(starts)
        assert floor > _instant(BY_ID[NAMED]["startDate"])
        assert floor.isoformat().startswith("2026-09-17T05:"), "the 2,000-event window is ~10.5h deep"
        assert NAMED not in {str(e["id"]) for e in PAGE_0 + last}
        await svc.close()

    def test_most_of_every_page_is_discarded_by_our_own_writer(self):
        svc = PolymarketAPIService()
        for page in (PAGE_0, PAGE_1900):
            crypto = sum(1 for e in page if "crypto" in poly._tags_to_category(svc._parse_event(e).tags))
            assert crypto >= 86

    @pytest.mark.asyncio
    async def test_the_id_addressed_read_reaches_it(self):
        gamma = _Gamma()
        svc = _service(gamma)
        got = await svc.get_events_by_ids([NAMED, TRADED])
        assert {str(e["id"]) for e in got} == {NAMED, TRADED}
        assert gamma.requests[-1].params.get_list("id") == [NAMED, TRADED]
        assert "offset" not in gamma.requests[-1].params
        await svc.close()


# --------------------------------------------------------------------------
# 2. WHY the parent is empty (child side) — the writer's own resolver
# --------------------------------------------------------------------------
class TestTheChildren:
    def test_the_named_event_has_no_price_the_writer_will_take(self):
        """19 children, 0 priced: 0.54 IS (0.17+0.91)/2 on a never-traded book."""
        ev = PolymarketAPIService()._parse_event(BY_ID[NAMED])
        assert poly.sunk_event_child_census(ev) == (19, 0)
        ml = next(m for m in ev.markets if m.condition_id.startswith(MONEYLINE_CID_NAMED))
        assert (ml.best_bid, ml.best_ask, ml.last_trade_price) == (0.17, 0.91, None)
        assert poly._parent_outcome_data(ev) == []

    def test_the_traded_event_is_partial_by_the_venues_own_books(self):
        ev = PolymarketAPIService()._parse_event(BY_ID[TRADED])
        assert poly.sunk_event_child_census(ev) == (27, 10)


# --------------------------------------------------------------------------
# 3. THE PASS
# --------------------------------------------------------------------------
class TestRecovery:
    @pytest.mark.asyncio
    async def test_every_priced_child_of_a_sunk_event_is_written_once(self, monkeypatch):
        stats, writer, *_ = await _run(monkeypatch, [_Row(60280239, TRADED)])
        rows = _market_rows(writer)
        ev = PolymarketAPIService()._parse_event(BY_ID[TRADED])
        priced = {m.condition_id for m in ev.markets if poly._resolve_market_probability(m)}
        unpriced = {m.condition_id for m in ev.markets} - priced
        assert len(priced) == 10
        assert priced <= set(rows), "every child the venue prices must be visited"
        assert not (unpriced & set(rows)), "an empty book must not mint a row"
        assert all(len(v) == 1 for v in rows.values()), "one child identity, one upsert"
        assert TRADED in rows, "the parent is re-stamped, which takes it out of the next passes"
        assert stats["events_partially_priced_at_venue"] == 1
        assert (stats["children_at_venue"], stats["children_priced_at_venue"]) == (27, 10)
        assert not stats["writer"]["errors"], stats["writer"]["errors"]

    @pytest.mark.asyncio
    async def test_the_named_event_today_writes_no_price_and_says_so(self, monkeypatch):
        stats, writer, *_ = await _run(monkeypatch, [_Row(60880026, NAMED)])
        rows = _market_rows(writer)
        assert set(rows) == {NAMED}, "parent re-stamped; zero children minted"
        assert _outcome_names(writer) == []
        assert stats["events_unpriced_at_venue"] == 1
        assert stats["events_fully_priced_at_venue"] == 0
        assert stats["terminal"] == "slice_done" and "complete" not in stats["terminal"]

    @pytest.mark.asyncio
    async def test_when_the_book_opens_the_moneyline_lands_and_the_props_do_not(self, monkeypatch):
        gamma = _Gamma({NAMED: _book_opened(BY_ID[NAMED])})
        stats, writer, *_ = await _run(monkeypatch, [_Row(60880026, NAMED)], gamma=gamma)
        rows = _market_rows(writer)
        children = {k for k in rows if k.startswith("0x")}
        assert len(children) == 1 and next(iter(children)).startswith(MONEYLINE_CID_NAMED)
        names = _outcome_names(writer)
        assert "Norma Dumont" in names and "Ailin Perez" in names, names
        assert not any("Round" in (n or "") or "KO" in (n or "") for n in names), names
        assert stats["events_partially_priced_at_venue"] == 1

    @pytest.mark.asyncio
    async def test_a_non_sports_event_goes_through_the_same_pass(self, monkeypatch):
        wid = str(WEATHER["id"])
        stats, writer, *_ = await _run(monkeypatch, [], [_Row(61000001, wid)])
        assert wid in _market_rows(writer)
        assert stats["events_reached"] == 1 and stats["rotate_selected"] == 1

    @pytest.mark.asyncio
    async def test_an_absent_id_is_recorded_not_acted_on(self, monkeypatch):
        stats, writer, _s, _g, redis = await _run(monkeypatch, [_Row(1, "999999999")])
        assert writer.statements == [] and stats["events_absent_at_venue"] == 1
        assert "999999999" in redis.sets[poly._SUNK_POLY_REFUSED_KEY]

    @pytest.mark.asyncio
    async def test_an_id_in_both_arms_is_read_and_written_once(self, monkeypatch):
        stats, writer, _s, gamma, _r = await _run(
            monkeypatch, [_Row(60280239, TRADED)], [_Row(60280239, TRADED)])
        assert gamma.requests[-1].params.get_list("id") == [TRADED]
        assert len(_market_rows(writer)[TRADED]) == 1


class TestTheVenueStoppedOfferingIt:
    """#7930. One shape per test, because they are not one shape.

    The ship: a question the venue has taken off the board stops being served
    to a reader as a live answer. Production, 2026-09-22: `Who will Trump
    nominate as Fed Chair?`, `LCK 2026 Season Winner` and `Which coalition will
    form the next Dutch government?` all come back from `/api/events/search` as
    `status: open` while Gamma reads `closed` or `archived` for each.
    """

    @pytest.mark.asyncio
    async def test_a_closed_event_reaches_the_writer_and_is_settled_not_reopened(
        self, monkeypatch
    ):
        """SHAPE 1 — `closed=true`. The list DOES return it; we binned it anyway."""
        gamma = _Gamma({TRADED: _closed(BY_ID[TRADED])})
        stats, writer, _s, _g, redis = await _run(
            monkeypatch, [_Row(60280239, TRADED)], gamma=gamma)
        assert stats["events_closed_at_venue"] == 1
        update = _parent_update_set(writer, TRADED)
        assert _literal(update["status"]) == "resolved", (
            "the row must stop being served as open — the writer's own "
            "`_venue_open` branch is what says so"
        )
        assert "settled_at" in update, "status and stamp move in one statement"
        # The status write IS the exclusion, and it is one SQL can see. A Redis
        # refusal set cannot be read by `_SUNK_POLY_WHERE`, and its key-wide TTL
        # is refreshed every pass, so a row put in it is excluded for good
        # WITHOUT ever being fixed. That is what this row used to get.
        assert TRADED not in redis.sets.get(poly._SUNK_POLY_REFUSED_KEY, set())

    @pytest.mark.asyncio
    async def test_an_archived_event_is_invisible_to_the_list_and_still_settled(
        self, monkeypatch
    ):
        """SHAPE 2 — `archived=true`. The list hides it; only direct address sees it."""
        gamma = _Gamma({}, hidden_from_list={TRADED: _archived(BY_ID[TRADED])})
        stats, writer, _s, _g, redis = await _run(
            monkeypatch, [_Row(60280239, TRADED)], gamma=gamma)
        assert stats["events_missing_from_list"] == 1, "the list must miss it"
        assert stats["direct_reads"] == 1
        assert stats["events_absent_at_venue"] == 0, (
            "an archived event is NOT absent — reporting it as absent is the "
            "defect, because absence is the one reading nothing may act on"
        )
        assert stats["events_closed_at_venue"] == 1
        assert _literal(_parent_update_set(writer, TRADED)["status"]) == "resolved"
        assert TRADED not in redis.sets.get(poly._SUNK_POLY_REFUSED_KEY, set())

    @pytest.mark.asyncio
    async def test_an_event_the_list_missed_but_still_offers_is_recovered_open(
        self, monkeypatch
    ):
        """SHAPE 3 — the list was simply wrong. The row must stay OPEN.

        The control for both tests above: the direct arm must be able to say
        "still offered", or it is a one-way retirement rail wearing a verdict's
        clothes.
        """
        gamma = _Gamma({}, hidden_from_list={TRADED: BY_ID[TRADED]})
        stats, writer, _s, _g, redis = await _run(
            monkeypatch, [_Row(60280239, TRADED)], gamma=gamma)
        assert stats["events_recovered_by_direct"] == 1
        assert stats["events_closed_at_venue"] == 0
        assert _literal(_parent_update_set(writer, TRADED)["status"]) == "open"
        assert TRADED not in redis.sets.get(poly._SUNK_POLY_REFUSED_KEY, set())

    @pytest.mark.asyncio
    async def test_a_404_on_direct_address_writes_nothing(self, monkeypatch):
        """SHAPE 4 — genuinely absent. Recorded, acted on by nothing (gotcha #53).

        0 of 240 sampled production rows read this way, so the arm exists to
        REFUSE, not to retire: one channel's silence is not a fact about a
        market, however long it lasts.
        """
        gamma = _Gamma({})
        stats, writer, _s, _g, redis = await _run(
            monkeypatch, [_Row(60280239, TRADED)], gamma=gamma)
        assert stats["events_absent_at_venue"] == 1
        assert writer.statements == []
        assert TRADED in redis.sets[poly._SUNK_POLY_REFUSED_KEY]

    @pytest.mark.asyncio
    async def test_a_transport_error_on_direct_address_concludes_nothing(
        self, monkeypatch
    ):
        """FAIL CLOSED. A 500 is not a verdict, and it must not become a refusal.

        The refusal matters as much as the write: an id refused here is dropped
        from every later pass (the set's TTL is key-wide and refreshed), so
        treating an outage as "the venue dropped it" would retire a healthy
        market permanently and silently.
        """
        gamma = _Gamma({}, status_for_direct={TRADED: 503})
        stats, writer, _s, _g, redis = await _run(
            monkeypatch, [_Row(60280239, TRADED)], gamma=gamma)
        assert stats["direct_unreadable"] == 1
        assert stats["events_absent_at_venue"] == 0
        assert stats["events_closed_at_venue"] == 0
        assert writer.statements == []
        assert TRADED not in redis.sets.get(poly._SUNK_POLY_REFUSED_KEY, set())

    @pytest.mark.asyncio
    async def test_a_429_on_direct_address_stops_the_pass_and_keeps_the_cursor(
        self, monkeypatch
    ):
        rows = [_Row(60280239, TRADED), _Row(60280240, "2000001")]
        gamma = _Gamma({}, status_for_direct={TRADED: 429})
        stats, writer, _s, _g, redis = await _run(
            monkeypatch, [], rows, gamma=gamma, redis=_Redis(cursor=7))
        assert stats["rate_limited"] is True
        assert stats["direct_reads"] == 1, "back off means stop asking"
        assert writer.statements == []
        assert redis.kv[poly._SUNK_POLY_CURSOR_KEY] == "7", "the cursor does not move"

    @pytest.mark.asyncio
    async def test_the_direct_arm_has_its_own_ceiling(self, monkeypatch):
        monkeypatch.setattr(poly, "_SUNK_POLY_DIRECT_MAX", 4)
        monkeypatch.setattr(poly, "_SUNK_POLY_DIRECT_PAUSE_S", 0)
        rows = [_Row(i, str(2_000_000 + i)) for i in range(12)]
        stats, _w, _s, gamma, _r = await _run(monkeypatch, rows)
        assert stats["events_missing_from_list"] == 12
        assert stats["direct_reads"] == 4 and stats["direct_budget_hit"] is True
        direct = [u for u in gamma.requests if _DIRECT_PATH.match(u.path)]
        assert len(direct) == 4, "the ceiling binds the REQUESTS, not just a counter"

    def test_the_verdict_is_four_facts_and_two_of_them_write_nothing(self):
        """The pure predicate, driven by hand — no network, no parse.

        Named separately from the arms above because the arms can only reach it
        through a fake venue: if the four verdicts were ever collapsed into
        three plus a default, the two that must write nothing are exactly the
        two a default would swallow.
        """
        class _E:
            def __init__(self, **kw):
                self.id = kw.pop("id", "1")
                self.active, self.closed, self.archived = (
                    kw.get("active", True), kw.get("closed", False), kw.get("archived", False))

        assert poly.sunk_direct_verdict(False, None) == "absent"
        assert poly.sunk_direct_verdict(True, None) == "unparseable"
        assert poly.sunk_direct_verdict(True, _E()) == "offered"
        assert poly.sunk_direct_verdict(True, _E(archived=True, active=False)) == "not_offered"
        assert poly.sunk_direct_verdict(True, _E(closed=True)) == "not_offered"
        # The flag rule is IMPORTED from the writer's own predicate, never a
        # second copy of it: patching that predicate must move this verdict.
        assert poly.sunk_direct_verdict(True, _E()) == "offered"


class TestBoundsAndFailure:
    @pytest.mark.asyncio
    async def test_request_count_is_bounded_by_the_selection(self, monkeypatch):
        rows = [_Row(i, str(2_000_000 + i)) for i in range(45)]
        monkeypatch.setattr(poly, "_SUNK_POLY_DIRECT_PAUSE_S", 0)
        stats, _w, _s, gamma, _r = await _run(monkeypatch, rows)
        batches = [u for u in gamma.requests if u.params.get_list("id")]
        assert len(batches) == 3 == stats["batches_read"]  # ceil(45/20)
        assert all(len(u.params.get_list("id")) <= 20 for u in batches)
        # #7930: every id the batch did not return costs ONE direct-address
        # read, and nothing else. 45 selected, none known to the fake ⇒ 45
        # misses, all 45 under the 60-read ceiling.
        direct = [u for u in gamma.requests if _DIRECT_PATH.match(u.path)]
        assert len(direct) == stats["direct_reads"] == 45
        assert stats["events_missing_from_list"] == 45
        assert len(gamma.requests) == len(batches) + len(direct)

    def test_the_per_pass_ceiling_is_thirty_five_gamma_calls(self):
        # 30 for the two arms here, plus 5 for #837's head arm (its own file).
        total = poly._SUNK_POLY_HEAD_MAX + poly._SUNK_POLY_IMMINENT_MAX + poly._SUNK_POLY_ROTATE_MAX
        assert -(-total // poly._LINKED_POLY_ID_BATCH) == 35

    @pytest.mark.asyncio
    async def test_a_429_stops_the_pass_and_keeps_the_cursor(self, monkeypatch):
        gamma = _Gamma(status_for_batch={1: 429})
        stats, writer, _s, _g, redis = await _run(
            monkeypatch, [], [_Row(500, TRADED)], gamma=gamma, redis=_Redis(cursor=77))
        assert stats["rate_limited"] and stats["terminal"] == "rate_limited"
        assert writer.statements == [] and redis.kv[poly._SUNK_POLY_CURSOR_KEY] == "77"

    @pytest.mark.asyncio
    async def test_one_unreadable_batch_does_not_end_the_run_or_advance_past_itself(self, monkeypatch):
        gamma = _Gamma(status_for_batch={1: 500})
        rotate = [_Row(100 + i, str(3_000_000 + i)) for i in range(20)] + [_Row(900, TRADED)]
        stats, writer, _s, _g, redis = await _run(monkeypatch, [], rotate, gamma=gamma)
        assert stats["batches_unreadable"] == 1 and stats["batches_read"] == 1
        assert TRADED in _market_rows(writer)

    @pytest.mark.asyncio
    async def test_the_deadline_stops_before_any_read(self, monkeypatch):
        stats, writer, _s, gamma, _r = await _run(monkeypatch, [_Row(1, TRADED)], deadline_s=-1)
        assert stats["deadline_hit"] and gamma.requests == [] and writer.statements == []

    @pytest.mark.asyncio
    async def test_resume_the_cursor_is_sent_and_advanced(self, monkeypatch):
        stats, _w, selector, _g, redis = await _run(
            monkeypatch, [], [_Row(4242, TRADED)], redis=_Redis(cursor=4000))
        assert selector.calls[1][1]["cursor"] == 4000
        assert redis.kv[poly._SUNK_POLY_CURSOR_KEY] == "4242"

    @pytest.mark.asyncio
    async def test_past_the_tail_wraps_in_the_same_pass(self, monkeypatch):
        stats, _w, selector, _g, _r = await _run(
            monkeypatch, [], [], redis=_Redis(cursor=9_999_999),
            rotate_after_wrap=[_Row(5, TRADED)])
        assert stats["cursor_wrapped"] and selector.calls[2][1]["cursor"] == 0
        assert stats["events_reached"] == 1

    @pytest.mark.asyncio
    async def test_an_empty_selection_names_the_question(self, monkeypatch):
        stats, *_ = await _run(monkeypatch, [], [])
        assert stats["terminal"] == "no_sunk_open_events"

    @pytest.mark.asyncio
    async def test_redis_down_is_not_fatal(self, monkeypatch):
        stats, writer, *_ = await _run(monkeypatch, [_Row(60280239, TRADED)], redis=_Redis(broken=True))
        assert TRADED in _market_rows(writer) and any("redis" in e for e in stats["errors"])

    @pytest.mark.asyncio
    async def test_refused_ids_are_sent_to_the_selector(self, monkeypatch):
        _st, _w, selector, *_ = await _run(monkeypatch, [], [], redis=_Redis(refused={"123"}))
        assert selector.calls[0][1]["refused"] == ["123"]


class TestTheSelector:
    def test_it_is_bounded_floored_and_category_agnostic(self):
        for stmt in (poly._SUNK_POLY_IMMINENT_SQL, poly._SUNK_POLY_ROTATE_SQL):
            raw = str(stmt.compile(dialect=postgresql.dialect())).lower()
            sql = "\n".join(line.split("--")[0] for line in raw.splitlines())  # comments are not predicates
            assert "limit" in sql and "fm.status = 'open'" in sql
            assert "volume_updated_at" in sql
            assert "not like '0x%" in sql
            assert "resolution_date >" in sql, "a floor, not only an order (gotcha #41)"
            for token in ("ufc", "mma", "sport", "category", "join"):
                assert not re.search(rf"\b{token}", sql), token

    def test_open_means_open(self):
        svc = PolymarketAPIService()
        assert poly.sunk_event_is_open(svc._parse_event(BY_ID[TRADED]))
        assert not poly.sunk_event_is_open(svc._parse_event(_closed(BY_ID[TRADED])))

    def test_the_beat_and_task_are_wired(self):
        from app.tasks import celery_app
        entry = celery_app.conf.beat_schedule["recover-sunk-polymarket-events-hourly"]
        assert entry["task"] == "app.tasks.recover_sunk_polymarket_events"
        assert entry["task"] in celery_app.tasks
