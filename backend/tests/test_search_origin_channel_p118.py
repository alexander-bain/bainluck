"""LAT-P118 / #1916 step 1 — THE ORIGIN CHANNEL.

THE SHIP: the searches the product keeps fast are chosen by what PEOPLE typed,
not by what our own measurement scripts typed.

MEASURED FIRST, on production, 2026-08-29, with the warmer's own head query
(`typeahead_warmer._head_from_query_log`, `DEFAULT_HEAD_SIZE = 40`)::

    ...
    38  nba rookie of the year       44
    39  lakers                       44
    40  cremonese                    42   <-- A LATENCY HARNESS PROBE TERM
    41  president                    42
    42  nba finals                   41
    43  sandhagen                    40   <-- harness
    44  osasuna                      40   <-- harness

`cremonese` is a Serie A club that nobody searched for. All 42 of its rows were
written by this program's own cold-path probes inside a two-hour window on
2026-08-28, and they are enough to hold **slot 40 of the 40 warm slots**,
displacing `president` and `nba finals`. Three more probe terms sit two votes
below the cut. The head is elected from `search_query_logs`, which LAT-P117
measured at **4,244 unattested rows out of 4,257 — 99.7 % machine**.

🔴 AND THE INSTRUMENT WAS ABOUT TO EAT ITS OWN NUMBER. `search_cold` is the
LARGEST member of the latency needle's pool (287-503 ms against a 20 ms median).
Its samples are exactly these probe terms. Once a probe term wins a warm slot the
warmer keeps it hot, `search_cold` starts returning cache hits, and the published
needle falls with nothing whatsoever having got faster.

WHY A HEADER, AND WHY NOT THE TWO MECHANISMS THAT ALREADY EXIST.

* `_suppress_search_log` (a ContextVar, #1866/#2211) is readable only inside the
  API process, so it reaches exactly one caller — the warmer, which invokes the
  route function directly. Every other automated writer arrives over HTTP: the
  Flow Sentinel's nightly gold set via `httpx` from a Celery worker, and these
  harnesses from a laptop. A ContextVar cannot be set from either.

* `?debug_timing=1` is the obvious reach and LAT-P117 disproved it. On this route
  it bypasses the response cache in BOTH directions — deliberately, and for a
  good reason that has nothing to do with logging (a cached body carries no
  timing block, so serving one would answer a timing request with silence). A
  harness using it to stop voting would pin `search_cold` to a forced cold build
  for ever, and the needle could never show a warmer reaching that surface.
  **Suppressing a write and bypassing a cache are two different asks and they
  must not share one flag.** `test_the_origin_header_is_not_a_cache_bypass` and
  `test_debug_timing_still_is_one_which_is_why_it_could_not_be_the_channel` are
  the pair that pins the distinction, and neither may be deleted without the
  other.

WHAT IS DELIBERATELY *NOT* SUPPRESSED. The **Flow Sentinel** keeps voting, on
purpose. LAT-P117 measured the alternative: the attested head is ONE row
(`red sox`, 2 sessions) out of 40 slots, and dropping the unattested rows leaves
about seven terms with nothing to take up the slack. The sentinel's gold set was
chosen to be representative user intents, so it is by accident a defensible warm
list, while `cremonese` is defensible as nothing at all. Removing the sentinel is
parked (P118-3) behind a demand signal, and the header is what makes it a
one-line change when that signal arrives.
"""

from __future__ import annotations

import inspect
import json
import pathlib
import re

import pytest

# ---------------------------------------------------------------------------
# Harness — a Redis double and a direct route call, both deliberately local to
# this file. `test_search_response_cache.py` has equivalents, and importing them
# would couple two suites through a private helper; the shapes are small enough
# that a copy is cheaper than the coupling.
# ---------------------------------------------------------------------------


class FakeRedis:
    def __init__(self):
        self.strings: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.setex_calls: list[tuple[str, int]] = []

    def get(self, key):
        return self.strings.get(key)

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, int(ttl)))
        self.strings[key] = value
        self.ttls[key] = int(ttl)
        return True


@pytest.fixture
def rc(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: client
    )
    return client


@pytest.fixture
def logged(monkeypatch):
    """Capture `_dispatch_search_log` calls instead of writing rows."""
    calls: list[dict] = []
    monkeypatch.setattr(
        "app.routes.events._dispatch_search_log", lambda **kw: calls.append(kw)
    )
    return calls


def _request(origin: str | None = None):
    from starlette.requests import Request

    headers: list[tuple[bytes, bytes]] = []
    if origin is not None:
        headers.append((b"x-bainluck-origin", origin.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/events/search",
            "headers": headers,
            "query_string": b"",
        }
    )


CACHED_BODY = {
    "query": "cremonese",
    "teams": [],
    "event_concepts": [],
    "results": [{"id": 4242, "home_team": "A", "away_team": "B"}],
    "futures": [],
    "futures_families": [],
    "pagination": {
        "page": 1,
        "per_page": 25,
        "total_results": 7,
        "total_pages": 1,
        "has_next": False,
        "has_prev": False,
    },
    "sports": [],
    "filters": {"sport": None, "days_back": 30, "include_upcoming": True},
}


def _warm(rc: FakeRedis, q="cremonese"):
    """Put `q` in the response cache exactly as the route's own writer would."""
    from app.utils.search_cache import search_response_cache_key

    key = search_response_cache_key(
        q=q,
        sport=None,
        tags=None,
        page=1,
        per_page=25,
        days_back=30,
        include_upcoming=True,
    )
    rc.strings[key] = json.dumps(CACHED_BODY)
    rc.ttls[key] = 60
    return key


async def _search(*, origin=None, q="cremonese", response=None, **over):
    """Call the route directly with EVERY parameter passed explicitly.

    Their declared defaults are `Query(...)` marker objects, which are TRUTHY
    outside FastAPI — omitting `debug_timing` would silently disable the cache in
    both directions and every assertion below would be made against the uncached
    path, which is precisely the confusion this file exists to pin.
    """
    from fastapi import Response

    from app.routes.events import search_events

    kwargs = {
        "request": _request(origin),
        "response": response if response is not None else Response(),
        "q": q,
        "sport": None,
        "tags": None,
        "page": 1,
        "per_page": 25,
        "days_back": 30,
        "include_upcoming": True,
        "debug_timing": False,
        "db": None,
        "current_user": None,
    }
    kwargs.update(over)
    return await search_events(**kwargs)


# ---------------------------------------------------------------------------
# 1-5. THE CHANNEL: who votes and who does not
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_harness_request_does_not_vote_in_the_head(rc, logged):
    """THE SHIP. RED before LAT-P118 — this is the write that took warm slot 40."""
    _warm(rc)

    await _search(origin="harness")

    assert logged == [], (
        "a request that declared itself machine traffic still wrote a "
        "search_query_logs row — it is still voting for what gets warmed"
    )


@pytest.mark.asyncio
async def test_a_request_with_no_origin_header_still_votes(rc, logged):
    """The complement, and the one that keeps the product working.

    A person's browser sends no such header. If absence suppressed, the head
    would elect from nothing and every search would go cold — a far worse bug
    than the one being fixed, arrived at by being tidy.
    """
    _warm(rc)

    await _search(origin=None)

    assert len(logged) == 1, "an ordinary search stopped being counted"
    assert logged[0]["query"] == "cremonese"


@pytest.mark.asyncio
async def test_an_explicit_user_origin_votes(rc, logged):
    """`user` is honoured as a POSITIVE assertion, not merely tolerated.

    #1916's acceptance asks for `user` to be an assertion rather than a
    default-by-absence. The value is honoured here; RECORDING it needs the
    `origin` column that issue also asks for, which is DDL and is not in this
    ship. Parked P118-1 — stated so the acceptance box is not read as ticked.
    """
    _warm(rc)

    await _search(origin="user")

    assert len(logged) == 1, "an explicit `user` origin was suppressed"


@pytest.mark.asyncio
async def test_an_unrecognised_origin_suppresses_rather_than_votes(rc, logged):
    """The rule is asymmetric ON PURPOSE, so write down which way and why.

    The header is private, non-standard and sent by no browser, so the only way
    it arrives at all is a caller asserting "I am not a person". An unrecognised
    value there is overwhelmingly a typo in a new harness, and the failure that
    HIDES is the other one: a typo that keeps voting pollutes the head silently,
    while a typo that stops voting costs one uncounted probe.
    """
    _warm(rc)

    await _search(origin="sentinal-typo")

    assert logged == [], "an unrecognised origin was treated as a person"


@pytest.mark.asyncio
async def test_the_case_and_whitespace_of_the_value_do_not_decide_it(rc, logged):
    """`User` from a client that title-cases its headers is still a person."""
    _warm(rc)

    await _search(origin="  User  ")

    assert len(logged) == 1, "`user` stopped being `user` because of whitespace"


@pytest.mark.asyncio
async def test_an_empty_origin_value_reads_as_ABSENT_and_not_as_automation(rc, logged):
    """`X-Bainluck-Origin:` with nothing after it is a proxy artefact, not a claim.

    Gotcha #53's shape at the header level: an empty value and a stated value
    must not read the same. Treating `""` as automation would let any middlebox
    that normalises headers silently delete a person's vote, and the deletion
    would be invisible — the row simply would not exist to be counted.
    """
    _warm(rc)

    await _search(origin="")

    assert len(logged) == 1, "an empty header value was read as a machine claim"


# ---------------------------------------------------------------------------
# 6-8. NOT A CACHE BYPASS — the whole reason this is not `?debug_timing=1`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_origin_header_is_not_a_cache_bypass(rc, logged):
    """🔴 THE LOAD-BEARING TEST. `db=None` is the assertion.

    Every database stage in `search_events` runs through the session, starting
    with `_apply_search_statement_timeout`, so reaching ANY of them raises on
    `None`. Getting the cached body back proves the read side was untouched by
    the header.

    If this ever goes red the harness has silently opted out of the cache it is
    measuring, `search_cold` becomes a permanently-cold number, and the needle
    can never show a warmer reaching the surface it is loudest about.
    """
    from fastapi import Response

    _warm(rc)
    response = Response()

    result = await _search(origin="harness", response=response)

    assert result == CACHED_BODY, (
        "the origin header stopped the cache being READ — it is behaving like "
        "debug_timing, which is exactly what it exists not to do"
    )
    assert response.headers["x-search-cache"] == "hit", (
        "the route reported something other than a cache hit for a warm entry "
        "served under the origin header"
    )
    assert isinstance(response, Response)


@pytest.mark.asyncio
async def test_debug_timing_still_is_one_which_is_why_it_could_not_be_the_channel(
    rc, logged
):
    """The disproof, pinned as a test so it cannot be re-proposed cheaply.

    Paired with the test above: same warm entry, same query, the only difference
    is which flag is set. `debug_timing` refuses the cached body and falls
    through to a database that is `None`. That raise IS the bypass.
    """
    _warm(rc)

    with pytest.raises(Exception):
        await _search(debug_timing=True)


def test_the_route_never_consults_the_origin_channel_itself(rc):
    """Structural, and it is what makes the bypass impossible rather than absent.

    The cache read condition (`_search_cache_readable`) and the cache write
    condition are both computed inside `search_events`. If neither can see the
    origin channel, no future edit can accidentally couple them to it — the
    guarantee is topological, not a promise about today's boolean.
    """
    from app.routes import events

    route_src = inspect.getsource(events.search_events)
    assert "_request_is_automation" not in route_src, (
        "search_events consults the origin channel directly — the channel is "
        "one edit away from becoming a cache bypass, which is the failure "
        "LAT-P117 disproved debug_timing on"
    )
    assert "_ORIGIN_HEADER" not in route_src


# ---------------------------------------------------------------------------
# 9-11. STRUCTURE — one rule, every consumer (gotcha #128)
# ---------------------------------------------------------------------------


def test_the_origin_guard_lives_inside_the_shared_recorder():
    """#2117's conclusion applied to the new guard, not re-derived beside it.

    Two call sites each carrying their own `if not automation` is two chances to
    forget, and the exit that forgets is always the one added later.
    """
    from app.routes import events

    src = inspect.getsource(events._record_search_query)
    assert "_request_is_automation" in src, (
        "the origin guard is not inside _record_search_query — a per-call-site "
        "guard is one edit away from an unguarded exit"
    )


@pytest.mark.asyncio
async def test_the_cache_hit_exit_is_guarded_too(rc, logged):
    """Both of the route's exits, and the hit path is the one that matters most.

    A harness re-probing a term it has already warmed is DISPROPORTIONATELY a
    cache hit. An unguarded hit path would keep voting on exactly the traffic
    that this fix exists to silence, and more efficiently than the miss path.
    """
    _warm(rc)

    result = await _search(origin="harness")

    assert result == CACHED_BODY, "the test did not exercise the hit path at all"
    assert logged == [], "the cache-hit exit voted despite the origin header"


async def _typeahead(q: str, *, origin=None, debug_evidence=False, debug_timing=False):
    """Call `/typeahead` directly, with the debug flags passed EXPLICITLY.

    Their declared defaults are `Query(False, ...)` objects, which are TRUTHY
    outside FastAPI — omitting them would make every call a debug call and every
    assertion here vacuous. Two suites have paid a red run to learn this.
    """
    from app.routes.events import typeahead_search

    return await typeahead_search(
        q=q,
        debug_evidence=debug_evidence,
        debug_timing=debug_timing,
        db=None,
        request=_request(origin),
    )


@pytest.mark.asyncio
async def test_a_harness_typeahead_call_does_not_vote_in_the_zset(rc):
    """The OTHER sink, asserted at runtime and not only by reading the source.

    On the ContextVar rather than on a resulting zset score, and the reason is
    structural: with `db=None` the full build raises long before reaching the
    trending write, so a score-based assertion would read 0.0 with or without the
    fix — a test that passes for the wrong reason. `_record_trending`'s obedience
    to the flag is pinned by the #2117 suite.
    """
    from app.routes.events import _suppress_trending_write

    token = _suppress_trending_write.set(False)
    try:
        with pytest.raises(Exception):
            await _typeahead("cremonese", origin="harness")

        assert _suppress_trending_write.get() is True, (
            "a probe that declared itself machine traffic still voted into "
            "search:trending:24h — the rule has two consumers and one verdict"
        )
    finally:
        _suppress_trending_write.reset(token)


@pytest.mark.asyncio
async def test_an_ordinary_typeahead_call_still_votes(rc):
    """The complement. `/typeahead`'s zset is half the warmer's head.

    If an ordinary keystroke stopped voting the head would elect from the
    `search_query_logs` arm alone, and the surface that measures `/typeahead`
    would stop measuring it — the mirror of #2117, arrived at by tidying.
    """
    from app.routes.events import _suppress_trending_write

    token = _suppress_trending_write.set(False)
    try:
        with pytest.raises(Exception):
            await _typeahead("cremonese", origin=None)

        assert _suppress_trending_write.get() is False, (
            "an ordinary typeahead request was suppressed — the head can no "
            "longer learn what people type"
        )
    finally:
        _suppress_trending_write.reset(token)


def test_the_trending_sink_honours_the_same_rule(rc):
    """One rule, TWO consumers — gotcha #128, which has already cost this surface.

    `search_head_warmer` filtered its head for attested traffic while
    `typeahead_warmer` read the same table whole; the repaired copy hid the
    broken one for weeks. A caller that declares itself machine traffic must
    stop voting in `search:trending:24h` as well as in `search_query_logs`, or
    it has not stopped voting — it has moved.
    """
    from app.routes import events

    src = inspect.getsource(events.typeahead_search)
    assert "_request_is_automation(request)" in src, (
        "/typeahead does not honour the origin channel — the rule now has two "
        "consumers and one verdict"
    )
    # SET-ONLY, never an `else`: `typeahead_warmer` sets the same ContextVar
    # before calling this route in-process, and assigning `bool(...)` here would
    # clobber it and re-open #1866 proper.
    assert re.search(
        r"if debug_evidence or debug_timing or _request_is_automation\(request\):\s*\n"
        r"\s*_suppress_trending_write\.set\(True\)",
        src,
    ), (
        "the origin channel was wired into /typeahead as an assignment rather "
        "than a set-only guard — that clobbers the warmer's own suppression"
    )


# ---------------------------------------------------------------------------
# 12-13. THE INJECTION, and the direction the helper fails in
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route_name", ["search_events", "typeahead_search"])
def test_fastapi_really_injects_the_request_despite_the_default(route_name):
    """🔴 The whole channel is silently dead if this is false.

    `typeahead_search` declares `request: Optional[Request] = None` so its three
    in-process callers keep working unchanged. A default on a parameter is
    normally how FastAPI decides something is a query parameter, so "does the
    annotation still win" is a real question and not a formality — and a channel
    that never receives a request suppresses nothing while looking exactly like
    a clean table.

    Asserted against FastAPI's own resolver rather than through a live request:
    `get_dependant` is the function the router calls to build the signature it
    will inject from, so `request_param_name` IS the injection.
    """
    from fastapi.dependencies.utils import get_dependant

    from app.routes import events

    dependant = get_dependant(
        path=f"/{route_name}", call=getattr(events, route_name)
    )
    assert dependant.request_param_name == "request", (
        f"FastAPI will not inject the Request into {route_name} — the origin "
        "header can never be read and every suppression silently stops working"
    )


def test_a_request_that_cannot_answer_reads_as_a_person():
    """Fails toward LOGGING, in both of its two failure shapes.

    Over-suppression drains the warm head invisibly; under-suppression leaves a
    row we can see and count. Only one of those is recoverable by looking.
    """
    from app.routes.events import _request_is_automation

    class Hostile:
        @property
        def headers(self):
            raise RuntimeError("no headers here")

    assert _request_is_automation(None) is False
    assert _request_is_automation(Hostile()) is False


# ---------------------------------------------------------------------------
# 14. THE CLASS GUARD — every probing script, not just the ones fixed today
# ---------------------------------------------------------------------------

#: A script BUILDS a request when a search surface appears with its query string
#: attached. Everything else that mentions these paths — a docstring, a `"source"`
#: field, a `--help` line, a SQL arm compiled from the ORM — is prose about the
#: surface rather than traffic to it.
#:
#: 🔴 THE FIRST VERSION OF THIS PREDICATE WAS "the file imports a transport", and
#: it under-scanned by two files. `probe_typeahead_segments.py` and
#: `probe_typeahead_warm_effect.py` shell out to `curl` through `subprocess`, so
#: they matched neither `urlopen(` nor `httpx` and passed a guard that had simply
#: not looked at them. Detecting the URL is transport-agnostic by construction:
#: however the request is eventually sent, it has to be addressed first.
_URL_BUILD = re.compile(r"/api/events/(?:search|typeahead)\?")

#: Files that address a search URL but do not send it themselves. Named
#: individually, with the reason, so that joining this set is a visible decision
#: in a diff rather than a predicate quietly widening.
_ADDRESSES_BUT_DOES_NOT_SEND = {
    # Declares the needle pool's path constants and hands them to
    # `cold_path_snapshot._get`, which sets the header. It opens no connection.
    "needle_latency.py",
}


def test_every_search_probing_script_declares_itself_machine_traffic():
    """THE CLASS, not the six instances. RED before LAT-P118 on all of them.

    A fix that patches the harnesses that happen to exist today has a shelf life
    of one new script — and this program writes probes constantly. The scan walks
    `backend/scripts/` so the next one fails here, in CI, rather than in the warm
    head six weeks later where it took two cycles and a production census to
    notice.
    """
    root = pathlib.Path(__file__).resolve().parents[1] / "scripts"
    assert root.is_dir(), f"scripts directory not found at {root}"

    offenders = []
    checked = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not _URL_BUILD.search(text):
            continue
        if path.name in _ADDRESSES_BUT_DOES_NOT_SEND:
            continue
        checked.append(path.name)
        if "X-Bainluck-Origin" not in text:
            offenders.append(path.name)

    assert checked, (
        "the scan matched no scripts at all — the guard has stopped guarding, "
        "which reads identically to every script being clean (gotcha #53)"
    )
    assert not offenders, (
        "these scripts address a search surface without declaring themselves "
        f"machine traffic, so they vote in the warm head: {sorted(offenders)}"
    )


def test_the_scan_covers_every_harness_that_was_polluting():
    """The complement, and it is not decoration.

    The predicate above is a regex, and a regex that stops matching fails SILENT
    and GREEN — `checked` would shrink and `offenders` would still be empty. This
    pins the six files the production census implicated, by name, so a narrowing
    of the pattern shows up as a red test instead of as a shorter scan nobody
    reads.
    """
    root = pathlib.Path(__file__).resolve().parents[1] / "scripts"
    found = {
        p.name
        for p in root.rglob("*.py")
        if _URL_BUILD.search(p.read_text(encoding="utf-8", errors="replace"))
    }
    for name in (
        "cold_path_snapshot.py",
        "done_bar_snapshot.py",
        "probe_search_userfelt.py",
        "probe_typeahead_userfelt.py",
        "probe_typeahead_segments.py",
        "probe_typeahead_warm_effect.py",
        "search_bucket_producer.py",
        "search_results_producer.py",
    ):
        assert name in found, (
            f"{name} builds a search URL and the scan no longer sees it — the "
            "guard narrowed rather than the script being fixed"
        )
