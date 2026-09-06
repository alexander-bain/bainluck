"""LAT-P090 — `/api/events/search` gets a response cache, and the head rides on it.

THE SHIP: search that feels instant on the words people actually type.

WHY A CACHE AND NOT AN INDEX, decided by measurement rather than by preference.
LAT-P088 specified a partial trigram GIN on `futures_markets.name WHERE
status='open'`, Alex built it in an attended psql batch, and the pre-registered
gate came back **RED** on its budget arm: median per-term collapse 0.7194 against
a 0.5 ceiling. The per-term table is the interesting part, because it is not
noise — it splits cleanly by term frequency:

    term                    collapse (1.0 = no change)
    super bowl                  0.078   <- rare phrase, index wins big
    world series                0.083
    best picture                0.368   (0.277 before)
    world cup                   0.500
    champion                    0.593
    presidential election       0.658
    super bowl                  0.781
    winner                      0.979   <- common word, index does nothing
    election                    0.998

A trigram index is a selectivity instrument. `%winner%` matches 42,336 of
858,938 futures rows; the bitmap it builds is most of the table, so the index
scan costs what the sequential scan costs and saves nothing. **No string index
will ever fix the common-word head** — that is a property of the distribution,
not of the index. Per the pre-registered contract Alex DROPPED
`ix_futures_name_trgm_open`, and the standing rule holds: a lane does not
re-grade its own bar after seeing the result.

So the lever moves from "make the scan cheaper" to "do not run the scan". The
head of the real `/search` distribution is small and measured —
`search_query_logs` 30-day top rows were `masters winner` (102), `stanley cup`
(101), `world series` (95), `nba champion` (90) — and those queries are, by
definition, the ones asked most often. Caching their answers and keeping the
head warm removes the query for exactly the traffic the index could not help.

WHAT THIS FILE PINS. Four failure classes, each of which has already happened
once in this repo on the neighbouring surface:

1. **The cache does not exist** (the ship). `/typeahead` has had a response cache
   since #1866; `/search` — the slower endpoint, with a 20,000 ms deadline — has
   never had one. Tests 1-3.
2. **An incomplete cache key** (#2203 / LAT-P089, one cycle ago). A key that
   omits a parameter which shapes the answer serves one caller another caller's
   results. Here the key is derived from the route's own signature and a test
   asserts the two cannot drift. Tests 4-7.
3. **A warmed term becomes uncountable** (#2117), and its mirror, **the warmer
   voting for its own head** (#1866). The query log elects the head; if a cache
   hit stops logging, the head starves itself, and if the warmer's own calls DO
   log, the head freezes closed. Both directions are pinned. Tests 8-11.
4. **A warmer that warms a key nobody reads** (LAT-P001). The warmer and the
   route derive their key from the same function, and the warmed shape is
   asserted against the route's declared defaults — which is what iOS relies on,
   since `APIClient.fetchSearch` sends only `q` and `page`. Tests 12-15.
"""

from __future__ import annotations

import inspect
import json

import pytest


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class FakeRedis:
    """Minimal sync Redis double: the four commands this feature uses."""

    def __init__(self):
        self.strings: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.commands: list[tuple] = []

    def get(self, key):
        self.commands.append(("get", key))
        v = self.strings.get(key)
        return v.encode() if isinstance(v, str) else v

    def setex(self, key, ttl, value):
        self.commands.append(("setex", key, ttl))
        self.strings[key] = value
        self.ttls[key] = int(ttl)
        return True

    def ttl(self, key):
        self.commands.append(("ttl", key))
        if key not in self.strings:
            return -2
        return self.ttls.get(key, -1)

    def delete(self, *keys):
        n = 0
        for key in keys:
            self.commands.append(("delete", key))
            if key in self.strings:
                del self.strings[key]
                self.ttls.pop(key, None)
                n += 1
        return n

    def set(self, key, value, nx=False, ex=None):
        self.commands.append(("set", key, nx, ex))
        if nx and key in self.strings:
            return None
        self.strings[key] = value
        if ex is not None:
            self.ttls[key] = int(ex)
        return True


@pytest.fixture
def rc(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: client
    )
    return client


def _request(headers: list[tuple[bytes, bytes]] | None = None):
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/events/search",
            "headers": headers or [],
            "query_string": b"",
        }
    )


#: A payload with the shape `search_events` really returns, small enough to read.
CACHED_BODY = {
    "query": "winner",
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


async def _search(rc: FakeRedis | None = None, *, q="winner", response=None, **over):
    """Call the route directly with EVERY parameter passed explicitly.

    Their declared defaults are `Query(...)` marker objects, which are TRUTHY
    outside FastAPI — omitting `debug_timing` would silently disable the cache
    in both directions and every assertion below would be made against the
    uncached path. `/typeahead`'s suite paid one red run to learn this.
    """
    from fastapi import Response

    from app.routes.events import search_events

    kwargs = {
        "request": _request(),
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


def _warm(rc: FakeRedis, q="winner", payload=None, ttl=60, **key_over):
    """Put `q` in the response cache exactly as the route's own writer would."""
    from app.utils.search_cache import search_response_cache_key

    key_kwargs = {
        "q": q,
        "sport": None,
        "tags": None,
        "page": 1,
        "per_page": 25,
        "days_back": 30,
        "include_upcoming": True,
    }
    key_kwargs.update(key_over)
    key = search_response_cache_key(**key_kwargs)
    rc.strings[key] = json.dumps(payload if payload is not None else CACHED_BODY)
    rc.ttls[key] = ttl
    return key


# ---------------------------------------------------------------------------
# 1-3. THE SHIP: the answer is served from cache, and the database is not touched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_warm_query_is_served_without_touching_the_database(rc):
    """RED before LAT-P090. `db=None` is the assertion.

    Every database stage in `search_events` runs through the session, starting
    with `_apply_search_statement_timeout`. If the route reaches ANY of them it
    raises on `None`. Returning the cached body therefore proves the whole query
    path was skipped, not merely that it was fast.
    """
    _warm(rc, "winner")

    result = await _search(rc, q="winner")

    assert result == CACHED_BODY, (
        "a repeated search did not come back from the response cache — the "
        "common-word head pays the full 20s-budget scan on every request"
    )


@pytest.mark.asyncio
async def test_a_cold_query_is_a_miss_and_does_not_serve_another_querys_answer(rc):
    """The complement. A key that is not warm must not resolve to one that is."""
    _warm(rc, "winner")

    with pytest.raises(Exception):
        # No cached entry for this query, so the route must fall through to the
        # database — which is `None`, so it raises. That raise IS the miss.
        await _search(rc, q="election")


@pytest.mark.asyncio
async def test_a_cache_hit_is_reported_on_the_response_header(rc):
    """`x-search-cache` is how a production deploy check reads hit vs miss.

    Header rather than a body key on purpose: the cached body must be BYTE
    IDENTICAL to the built one, so the two can be compared directly and so no
    frontend type changes. `middleware/latency.py` already reads the sibling
    `x-feed-cache` this way.
    """
    from fastapi import Response

    from app.utils.search_cache import SEARCH_CACHE_HEADER

    _warm(rc, "winner")
    response = Response()

    await _search(rc, q="winner", response=response)

    assert response.headers.get(SEARCH_CACHE_HEADER) == "hit"


# ---------------------------------------------------------------------------
# 4-7. THE KEY IS COMPLETE, and cannot silently stop being complete (#2203)
# ---------------------------------------------------------------------------


#: Route parameters that do NOT shape the cached answer, each with the reason it
#: is excluded. Declared here so an addition to this set is a visible act in a
#: diff, which is the half #2203 was missing.
_DECLARED_NON_KEY_PARAMS = {
    # Plumbing, not an answer input.
    "request",
    "response",
    "db",
    # The response body is IDENTICAL for every principal: `current_user` is read
    # once, at the very end, and only to attribute the analytics row. Nothing
    # about the results, ordering, futures or teams depends on it. That is what
    # makes an unsegmented key safe here and what made the feed's key unsafe
    # (#2203) — the feed genuinely personalizes.
    "current_user",
    # Never cached in either direction, so it can never key an entry.
    "debug_timing",
}


def test_the_cache_key_covers_every_answer_shaping_route_parameter():
    """The #2203 class, made structural instead of remembered.

    A new query parameter on `search_events` that changes the answer and is not
    in the key means two different questions share one cached answer. This test
    goes red the moment such a parameter is added, and the only two ways to make
    it green are the two correct ones: put it in the key, or declare in
    `_DECLARED_NON_KEY_PARAMS` why it cannot change the answer.
    """
    from app.routes.events import search_events
    from app.utils.search_cache import search_response_cache_key

    route_params = set(inspect.signature(search_events).parameters)
    key_params = set(inspect.signature(search_response_cache_key).parameters)

    shaping = route_params - _DECLARED_NON_KEY_PARAMS
    missing = shaping - key_params
    assert not missing, (
        f"route parameters shape the answer but are absent from the cache key: "
        f"{sorted(missing)} — either add them to search_response_cache_key or "
        f"declare in _DECLARED_NON_KEY_PARAMS why they cannot change the answer"
    )

    stale = key_params - route_params
    assert not stale, (
        f"the cache key segments on parameters the route no longer takes: "
        f"{sorted(stale)} — a key wider than the question fragments the cache"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("q", "election"),
        ("sport", "basketball_nba"),
        ("tags", '["importance:playoff"]'),
        ("page", 2),
        ("per_page", 50),
        ("days_back", 90),
        ("include_upcoming", False),
    ],
)
def test_every_key_field_actually_changes_the_key(field, value):
    """A field in the signature that does not reach the digest is not in the key.

    The previous test reads the signature; this one reads the bytes. Both are
    needed — a parameter accepted and then dropped on the floor passes the first
    and fails this one, and that is precisely how an incomplete key survives
    review.
    """
    from app.utils.search_cache import search_response_cache_key

    base = dict(
        q="winner",
        sport=None,
        tags=None,
        page=1,
        per_page=25,
        days_back=30,
        include_upcoming=True,
    )
    changed = {**base, field: value}
    assert search_response_cache_key(**base) != search_response_cache_key(**changed)


def test_the_query_is_normalized_so_typing_case_does_not_fragment_the_cache():
    """`Winner`, `winner ` and `  WINNER` are one question, so they are one key.

    This is not cosmetic: the head is elected from `lower(btrim(query))` in
    `search_query_logs`, so a warmer warms the normalized form. Without the same
    normalization on the read side the warmer would warm `winner` and a user
    typing `Winner` would miss it — a warmer that reports success and delivers
    nothing, which is the failure mode this whole subsystem is built around.
    """
    from app.utils.search_cache import search_response_cache_key

    def key(q):
        return search_response_cache_key(
            q=q,
            sport=None,
            tags=None,
            page=1,
            per_page=25,
            days_back=30,
            include_upcoming=True,
        )

    assert key("winner") == key("Winner") == key("  WINNER  ")


@pytest.mark.asyncio
async def test_a_debug_timing_request_neither_reads_nor_writes_the_cache(rc):
    """A cached body carries no `debug_timing` block.

    Serving one to a timing request would answer it with SILENCE, which reads
    identically to a stage that cost nothing (gotcha #53). Same rule `/typeahead`
    applies to `debug_evidence` and `debug_timing`, and for the same reason: an
    answer produced under different rules is never interchangeable in a cache.
    """
    _warm(rc, "winner")

    with pytest.raises(Exception):
        await _search(rc, q="winner", debug_timing=True)


# ---------------------------------------------------------------------------
# 8-11. THE COUNTER. The log elects the head; the head must not starve or freeze
# ---------------------------------------------------------------------------


@pytest.fixture
def logged(monkeypatch):
    """Capture `_dispatch_search_log` calls instead of writing rows."""
    calls: list[dict] = []
    monkeypatch.setattr(
        "app.routes.events._dispatch_search_log", lambda **kw: calls.append(kw)
    )
    return calls


@pytest.mark.asyncio
async def test_a_cache_hit_still_logs_the_query(rc, logged):
    """#2117 in its mirror, and the reason it must be written down twice.

    `search_query_logs` is what `_head_from_query_log` reads to decide which
    queries to warm. A cache hit that returns early without logging makes a
    warmed query invisible to the thing that decides what to warm — so a term,
    once warm, could never be re-elected, and the head would drain to exactly
    the queries we had FAILED to serve fast. `/typeahead` shipped that bug and
    ran with it for weeks; this surface gets the guard on day one.
    """
    _warm(rc, "winner")

    await _search(rc, q="winner")

    assert len(logged) == 1, "a query served from cache was not logged"
    assert logged[0]["query"] == "winner"


@pytest.mark.asyncio
async def test_the_hit_path_logs_the_same_counts_the_miss_path_would(rc, logged):
    """The row must not degrade just because the answer came from Redis.

    `result_count` and `top_result_id` are both recoverable from the cached body
    — they are fields of it. Writing NULLs on the hit path would make the log's
    own columns depend on cache state, and the 30-day head query would then be
    reading a distribution polluted by our own caching.
    """
    _warm(rc, "winner")

    await _search(rc, q="winner")

    assert logged[0]["result_count"] == 7
    assert logged[0]["top_result_id"] == 4242


@pytest.mark.asyncio
async def test_the_warmers_own_calls_are_never_logged(rc, logged):
    """#1866 on the new surface, refused before it can start.

    The warmer warms by calling this route. If those calls landed in
    `search_query_logs` the warmer would vote for its own head — at one pass per
    45 s that is ~1,900 votes a day per term against ~3 for a real query, so the
    head would freeze closed within a day and no organic query could ever break
    in. `/typeahead` reached exactly that state: its top five scored 5414, 5411,
    5403, 5400, 5399, a spread of 15, which is a round-robin machine and not a
    human distribution.
    """
    from app.routes.events import _suppress_search_log

    _warm(rc, "winner")
    token = _suppress_search_log.set(True)
    try:
        await _search(rc, q="winner")
    finally:
        _suppress_search_log.reset(token)

    assert logged == [], "the warmer voted for its own head (#1866)"


def test_the_suppression_guard_lives_inside_the_shared_recorder():
    """One helper, called from both exits, with the guard INSIDE it.

    #2117's own conclusion, applied structurally. Two call sites each carrying
    their own `if not suppressed` is two chances to forget, and the exit that
    forgets is always the one added later.
    """
    from app.routes import events

    src = inspect.getsource(events._record_search_query)
    assert "_suppress_search_log" in src, (
        "the suppression guard is not inside _record_search_query — a per-call-"
        "site guard is one edit away from an unguarded exit"
    )

    route_src = inspect.getsource(events.search_events)
    assert route_src.count("_record_search_query(") == 2, (
        "search_events must call the recorder from BOTH exits (hit and miss) "
        "and from nowhere else"
    )
    assert "_dispatch_search_log(" not in route_src, (
        "the route dispatches the log directly, bypassing the suppression guard"
    )


# ---------------------------------------------------------------------------
# 12-15. THE WARMER WARMS THE KEY THE ROUTE READS (LAT-P001)
# ---------------------------------------------------------------------------


def test_the_warmer_derives_its_key_from_the_route_s_own_key_function():
    """A second key implementation is a warmer that warms nothing, silently.

    LAT-P001 is the named case: the feed pre-warm computed its key inline and
    published under a key the request path never read. It reported success every
    pass. There is one key function and both callers use it.
    """
    from app.tasks import search_head_warmer as w

    src = inspect.getsource(w)
    assert "search_response_cache_key" in src, (
        "the warmer builds its own key instead of calling the shared builder"
    )


def test_the_warmer_passes_every_route_parameter_explicitly():
    """A `Query(...)` default is a marker object, and marker objects are TRUTHY.

    The warmer calls `search_events` as a plain function, so any parameter it
    omits arrives as its FastAPI marker rather than as its literal default. For
    `debug_timing` that is catastrophically quiet: the route would read it as
    true, skip the cache in BOTH directions, execute the entire query path, warm
    nothing, and return successfully. The pass would report `warmed: 8/8`.

    `typeahead_warmer` carries this trap as a comment because it hit it. This is
    the same trap, asserted instead of remembered — the call site is compared
    against the route signature, so a NEW route parameter also goes red here
    rather than being silently defaulted to a marker object.
    """
    import ast

    from app.routes.events import search_events
    from app.tasks import search_head_warmer as w
    from app.utils.search_cache import SEARCH_WARM_SHAPE

    tree = ast.parse(inspect.getsource(w._warm_one).lstrip())
    call = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "search_events"
    )
    passed = {kw.arg for kw in call.keywords if kw.arg is not None}
    # `**SEARCH_WARM_SHAPE` arrives as a keyword with `arg is None`.
    assert any(kw.arg is None for kw in call.keywords), "the warm shape is not splatted"
    passed |= set(SEARCH_WARM_SHAPE)

    required = set(inspect.signature(search_events).parameters)
    missing = required - passed
    assert not missing, (
        f"the warmer omits route parameters {sorted(missing)} — each arrives as a "
        f"truthy Query() marker, and omitting debug_timing alone turns every pass "
        f"into a full query that warms nothing and reports success"
    )


def test_the_warmed_shape_is_the_shape_both_clients_actually_request():
    """The warmed shape must equal the route's DECLARED DEFAULTS.

    This is load-bearing because of what the clients send. `frontend/lib/api.ts`
    sets `page` and `per_page` and omits the rest; `APIClient.fetchSearch` sends
    only `q` and `page`. Both therefore resolve to the server-side defaults for
    `days_back` and `include_upcoming`. Change a default and the two surfaces
    move to a shape the warmer is not warming — with no diff anywhere near the
    warmer. This test is the thing that notices.
    """
    from app.routes.events import search_events
    from app.utils.search_cache import SEARCH_WARM_SHAPE

    params = inspect.signature(search_events).parameters

    def declared_default(name):
        # `Query(25, ...)` keeps the literal on `.default`.
        return getattr(params[name].default, "default", params[name].default)

    for field in ("per_page", "days_back", "include_upcoming", "page"):
        assert SEARCH_WARM_SHAPE[field] == declared_default(field), (
            f"the warmer warms {field}={SEARCH_WARM_SHAPE[field]!r} but the route "
            f"defaults to {declared_default(field)!r} — every client that omits "
            f"{field} would miss the warmed entry"
        )
    assert SEARCH_WARM_SHAPE["sport"] is None
    assert SEARCH_WARM_SHAPE["tags"] is None


def test_the_head_is_elected_by_the_search_log_not_by_the_typeahead_zset():
    """Warm the surface you measure. `search:trending:24h` measures `/typeahead`.

    `typeahead_warmer` blends the two sources because a typeahead head needs the
    PREFIXES a user passes through, which `/search` never sees. `/search` has the
    opposite need and one unpolluted source that measures it exactly, so this
    warmer takes the query log whole. Stated as a test because "which
    distribution" is the single decision that determines whether a warmer helps
    anybody.
    """
    from app.tasks import search_head_warmer as w

    src = inspect.getsource(w)
    assert "_head_from_query_log" in src
    assert "search_trending" not in src and "read_window" not in src, (
        "the /search warmer is heading from the /typeahead zset — that measures "
        "a different surface and is written to by the other warmer"
    )


def test_a_fresh_entry_is_left_alone_and_a_near_dead_one_is_rebuilt(rc):
    """Hole 2 (LAT-P060), which cadence alone can never fix.

    The route writes its cache only on the MISS path, so a warm read resets no
    clock: a pass that hits the cache extends nothing and reports success. The
    only way a warmer can extend an entry's life is to make the entry not be
    there. Both arms are asserted because reporting `warmed: N/N` for a pass
    that rebuilt nothing is the exact green-but-useless run this subsystem keeps
    producing.
    """
    from app.tasks.search_head_warmer import REFRESH_AHEAD_SECONDS, _needs_rebuild
    from app.utils.search_cache import SEARCH_RESPONSE_TTL_SECONDS

    assert _needs_rebuild(SEARCH_RESPONSE_TTL_SECONDS) is False
    assert _needs_rebuild(REFRESH_AHEAD_SECONDS - 1) is True
    # -2: no key at all. The pass must treat that as needing work, not as fresh.
    assert _needs_rebuild(-2) is True
    # -1: a key with no expiry. Impossible here, and a bug to correct rather
    # than a state to rest on.
    assert _needs_rebuild(-1) is True
    # None: Redis did not answer. NOT a TTL. Fail toward doing the work.
    assert _needs_rebuild(None) is True


def test_the_refresh_ahead_window_actually_keeps_the_head_alive():
    """The arithmetic that makes the duty cycle flat instead of a sawtooth.

    🔴 REWRITTEN under #3539 / CERT-2068. This test used to read:

        assert MIN_PASS_PERIOD_SECONDS < SEARCH_RESPONSE_TTL_SECONDS
        assert SEARCH_RESPONSE_TTL_SECONDS - MIN_PASS_PERIOD_SECONDS <= REFRESH_AHEAD_SECONDS

    and it was GREEN across every configuration that shipped a cold head, for two
    independent reasons: `MIN_PASS_PERIOD_SECONDS` is the FLOOR (45 s) rather than
    the achievable period (60 s, the floor quantized up to the 20 s beat), and
    there was no rebuild-duration term at all, though the replacement entry is
    written at the END of a pass. Restated with the real period the first clause
    is `60 < 60` — false.

    It now calls `residency_invariant()` rather than re-deriving the relation.
    A guard that re-derives production's own expression agrees with it by
    construction and cannot fail; this one asserts the OUTCOME and prints
    production's own reason on failure.
    """
    from app.tasks.search_head_warmer import (
        REFRESH_AHEAD_SECONDS,
        effective_pass_period_s,
        full_rebuild_budget_s,
        residency_invariant,
    )
    from app.utils.search_cache import SEARCH_RESPONSE_TTL_SECONDS

    ok, why = residency_invariant()
    assert ok, f"the head is not provably resident at the shipped constants: {why}"

    # Both clauses fire on their own — a single assert on `ok` cannot tell us the
    # invariant still has two teeth, and a one-toothed invariant is how this
    # regressed the first time.
    period = effective_pass_period_s()
    budget = full_rebuild_budget_s()

    caught, why_caught = residency_invariant(refresh_ahead_s=SEARCH_RESPONSE_TTL_SECONDS - period)
    assert not caught, "clause (1) is dead: a threshold at exactly TTL - period must NOT pass"
    assert "NOT CAUGHT" in why_caught

    # 🔴 Clause (2) is about the THRESHOLD, not the TTL. CERT-2084 blocked the
    # version that read `ttl - period > budget` here; a threshold at exactly
    # `period + budget` is the boundary it must refuse.
    survives, why_survives = residency_invariant(refresh_ahead_s=period + budget)
    assert not survives, (
        "clause (2) is dead: a threshold at exactly period + budget must NOT pass"
    )
    assert "DOES NOT SURVIVE" in why_survives

    bounded, why_bounded = residency_invariant(ttl_s=REFRESH_AHEAD_SECONDS - 1)
    assert not bounded, "clause (3) is dead: refresh-ahead above the TTL must NOT pass"
    assert "NOT A THRESHOLD" in why_bounded

    # Three configurations that all read plausible and all hole. Each must be
    # refused BY NAME, and each was actually proposed by someone.
    assert residency_invariant(ttl_s=60, refresh_ahead_s=25)[0] is False, (
        "the pre-#3526 constants (60/25) must not satisfy the invariant"
    )
    assert residency_invariant(ttl_s=180, refresh_ahead_s=90)[0] is False, (
        "#3539's option 4 (180/90) leaves the entry uncaught at its first "
        "eligible pass — it must not satisfy the invariant either"
    )
    blocked_2084 = residency_invariant(ttl_s=180, refresh_ahead_s=150)
    assert blocked_2084[0] is False, (
        "180/150 is the configuration CERT-2084 blocked: an organic entry seen at "
        "the threshold is rebuilt one period later with 90s against a 100s budget"
    )
    assert "DOES NOT SURVIVE" in blocked_2084[1]

    # And the shipped threshold is the derived one, not a hand-picked neighbour.
    from app.tasks.search_head_warmer import derive_refresh_ahead_s

    assert REFRESH_AHEAD_SECONDS == derive_refresh_ahead_s(), (
        f"REFRESH_AHEAD_SECONDS={REFRESH_AHEAD_SECONDS} has drifted from its "
        f"derivation {derive_refresh_ahead_s()}"
    )


def test_the_effective_pass_period_is_the_floor_quantized_to_the_beat_not_the_floor():
    """#3539 defect 1, pinned as its own test because it fooled three readers.

    A pass may start only on a delivered beat fire, and only once the floor has
    elapsed. 20 s beat + 45 s floor => fires at 20 and 40 both skip, 60 runs.
    The sibling's `max(beat, floor)` form agrees only because its floor (30 s) is
    an exact multiple of its beat (10 s); ours is not, and 45 != 60 is the gap.
    """
    from app.tasks.search_head_warmer import (
        BEAT_PERIOD_SECONDS,
        MIN_PASS_PERIOD_SECONDS,
        effective_pass_period_s,
    )

    assert effective_pass_period_s() == 60.0
    assert effective_pass_period_s() > MIN_PASS_PERIOD_SECONDS, (
        "the achievable period must be strictly above the floor whenever the "
        "floor is not a multiple of the beat — that gap is the whole defect"
    )
    # The naive forms this replaced, each refused by name.
    assert effective_pass_period_s() != MIN_PASS_PERIOD_SECONDS, "reads the floor"
    assert effective_pass_period_s() != max(BEAT_PERIOD_SECONDS, MIN_PASS_PERIOD_SECONDS), (
        "reads the sibling's max() form, which is wrong for a non-multiple floor"
    )
    # Quantization, not rounding: a floor already on a beat multiple stays put.
    assert effective_pass_period_s(beat_s=10, floor_s=30) == 30.0
    assert effective_pass_period_s(beat_s=20, floor_s=41) == 60.0
    assert effective_pass_period_s(beat_s=20, floor_s=60) == 60.0


def test_the_full_rebuild_budget_is_the_pass_not_one_query():
    """#3539 defect 3: option 4 priced the rebuild at ONE query's timeout.

    The entry that has to survive is the one written LAST. At 8 terms and
    concurrency 2 that entry waits out three full waves before its own rebuild
    starts, so the budget is `waves * per-query bound`, not the per-query bound.
    Derived from what the code PERMITS, never from a measured wall — sizing a
    bound at `measured_max * k` is refuted by the next sample.
    """
    from app.tasks.search_head_warmer import (
        PER_QUERY_TIMEOUT_SECONDS,
        full_rebuild_budget_s,
    )

    assert full_rebuild_budget_s() == 100.0
    assert full_rebuild_budget_s() > PER_QUERY_TIMEOUT_SECONDS, (
        "the budget must exceed one query's bound — the last-written entry "
        "waits out every earlier wave"
    )
    assert full_rebuild_budget_s(head_size=2, concurrency=2, per_query_s=25) == 25.0
    assert full_rebuild_budget_s(head_size=3, concurrency=2, per_query_s=25) == 50.0


def test_the_message_expiry_is_derived_from_the_lock_ttl_not_the_beat_period():
    """#3364: the bound that decides whether a fire is delivered at all.

    The old value was the beat period, justified against the task's WALL. The
    wall is the wrong quantity — it decides whether a *delivered* fire can start,
    not whether the fire survives the broker queue. Production read
    `matched_emitted` 30 / `matched_delivered` 0 in one 600 s bucket under the
    old bound.

    Asserted as a DERIVATION rather than as the number 180, so lowering
    `_LOCK_TTL_SECONDS` moves the bound with it instead of silently leaving a
    stale literal behind.
    """
    from app.tasks.search_head_warmer import (
        _LOCK_TTL_SECONDS,
        BEAT_PERIOD_SECONDS,
        derive_message_expiry_s,
    )

    derived = derive_message_expiry_s()
    assert derived == float(_LOCK_TTL_SECONDS)
    # The whole point: strictly above the period, or the flat rule would apply
    # and the delivery deficit would be back.
    assert derived > BEAT_PERIOD_SECONDS


def test_the_message_expiry_refuses_rather_than_clamping():
    """Both refusals, because a quietly clamped bound is how this drifts back.

    A bound that returns a smaller number when its inputs go out of range looks
    like it worked. `derive_message_expiry_s` raises instead, and the wiring
    guard propagates the raise.
    """
    import pytest

    from app.tasks.search_head_warmer import derive_message_expiry_s

    # A lock TTL at or under the beat period means this beat does not need a
    # delivery bound at all — the flat #1609 rule covers it.
    with pytest.raises(ValueError, match="beat period"):
        derive_message_expiry_s(beat_s=20.0, lock_ttl_s=20.0)

    # Too many messages alive at once is a real cost even at ~30 ms a skip, so
    # the cap is enforced rather than documented.
    with pytest.raises(ValueError, match="alive at once"):
        derive_message_expiry_s(beat_s=1.0, lock_ttl_s=180.0)

    for bad in ({"beat_s": 0}, {"lock_ttl_s": 0}, {"beat_s": -20.0}):
        with pytest.raises(ValueError, match="must both be positive"):
            derive_message_expiry_s(**bad)


# ---------------------------------------------------------------------------
# 16-18. HONEST INVALIDATION: what is never cached, and what says so out loud
# ---------------------------------------------------------------------------


def test_a_degraded_answer_is_never_written_to_the_cache():
    """LAT-P007's rule, on the endpoint with the longest budget in the API.

    `/search` sheds stages when its 20,000 ms budget runs out and says so in
    `degraded`. Caching one of those means a single slow moment pins a
    futures-less answer in front of every user asking that question for the full
    TTL — a transient becomes sticky. Caching an answer you already know is
    incomplete is worse than not caching at all.
    """
    from app.routes import events

    src = inspect.getsource(events.search_events)
    assert "if not degraded and not debug_timing:" in src, (
        "the cache write is not jointly guarded on `degraded` and `debug_timing`"
    )


def test_the_ttl_is_declared_once_and_is_the_whole_invalidation_contract():
    """There is no event-driven invalidation here, and that is the honest design.

    A search answer is assembled from live scores, odds, probabilities, futures
    prices and team rows — there is no single write whose commit could invalidate
    it. So the contract is stated as a bound rather than implied: an answer may
    be up to `SEARCH_RESPONSE_TTL_SECONDS` old, and one constant is the only
    thing to change if that judgement moves.

    🔴 IT MOVED: 60 -> 180 s by **RULING D81 = A (Alex, 2026-09-06)**. The
    literal is still asserted, because this bound is a PRODUCT judgement and a
    lane must not be able to drift it silently — but the number it pins is now
    the ruled one, and the ruling is named here so the next reader can tell a
    ruling from a tuning. It is no longer "the same order as the neighbours"
    (`/typeahead` 65 s, anonymous Discover 60 s), and that divergence is the
    substance of the ruling rather than an oversight: `residency_invariant()`
    cannot be satisfied below `P_effective + full_rebuild_budget` = 160 s.
    """
    from app.utils.search_cache import SEARCH_RESPONSE_TTL_SECONDS

    assert SEARCH_RESPONSE_TTL_SECONDS == 180, (
        "the /search freshness ceiling is set by ruling D81 = A, not by a lane. "
        "Changing it needs Alex's words and a re-check of residency_invariant()."
    )

    # The ceiling and the residency proof are ONE decision. Pinning the literal
    # alone would let someone lower it to 60 and satisfy this test's sibling
    # while re-opening the hole CERT-2068 blocked.
    from app.tasks.search_head_warmer import residency_invariant

    ok, why = residency_invariant(ttl_s=SEARCH_RESPONSE_TTL_SECONDS)
    assert ok, f"the declared TTL does not keep the head resident: {why}"

    from app.routes import events

    src = inspect.getsource(events.search_events)
    assert "SEARCH_RESPONSE_TTL_SECONDS" in src, (
        "the route hardcodes a TTL instead of reading the declared constant — "
        "the /typeahead 45->65s change had to be made in two places for exactly "
        "this reason, and the drift between them is a red test there"
    )


def test_the_head_warmer_ships_enabled_because_the_block_moved_into_the_head_query(
    monkeypatch,
):
    """The switch fails OPEN again, and the guarantee it used to carry moved.

    THIS TEST REPLACES `..._ships_disabled_because_1916_blocks_its_head_source`,
    which existed to make lifting the block a visible act — a future window had
    to delete it, and deleting it meant reading why it was there. LAT-P102 is
    that window, so here is the reading, banked where the next one will find it.

    #1916 blocked head selection from `search_query_logs` until a clean
    distribution existed. LAT-P102's census found that one can be READ without a
    migration: `session_id` is written from the `x-session-id` header that
    `frontend/lib/api.ts` and `APIClient.swift` both attach to every search, and
    no probe in this repo sends it. Through that filter the table is **99.66%
    session-less automation** — four times worse than #1916's 23.6%, because that
    figure counted only the 07:10 sentinel and missed 2,858 rows of burst-minute
    probe traffic — and all eight terms the old whole-table head would have
    warmed are probe terms.

    So the env var is no longer where the guarantee lives. It is in
    `_head_from_user_rows`, which cannot elect a probe term at all, and in
    `MIN_HEAD_SESSIONS`, which cannot elect a term one person asked. A filter
    beats a default: an operator can flip a default without reading #1916.

    What did NOT change: the response cache is still not gated on this switch.
    """
    from app.tasks.search_head_warmer import SEARCH_HEAD_WARM_ENV, head_warm_enabled
    from app.utils.search_cache import search_response_cache_enabled

    monkeypatch.delenv(SEARCH_HEAD_WARM_ENV, raising=False)
    assert head_warm_enabled() is True, (
        "the head warmer defaults OFF — but #1916's block now lives in the head "
        "QUERY, so defaulting off keeps a fix dark and protects nothing"
    )

    # Only an explicit off value turns it off...
    for off in ("0", "false", "no", "off", "OFF", " No "):
        monkeypatch.setenv(SEARCH_HEAD_WARM_ENV, off)
        assert head_warm_enabled() is False, f"{off!r} must disable the warmer"

    # ...and a typo resolves toward the WORKING state, like the rest of the
    # family. This is the direction that inverted, and it is the whole change.
    monkeypatch.setenv(SEARCH_HEAD_WARM_ENV, "yse")
    assert head_warm_enabled() is True

    # And the cache is still NOT gated on it.
    monkeypatch.delenv("SEARCH_RESPONSE_CACHE", raising=False)
    assert search_response_cache_enabled() is True, (
        "the response cache defaults off — it is the ship, and it is "
        "contamination-proof, so it must not inherit the warmer's switch"
    )


def test_off_spelled_the_same_way_for_the_cache_and_the_warmer():
    """Two neighbouring kill switches must not disagree about what "off" spells.

    An operator reaching for one of these under load is not going to check
    whether `SEARCH_RESPONSE_CACHE=off` and `SEARCH_HEAD_WARM_ENABLED=off` mean
    the same thing. They do, and this asserts it rather than trusting a comment.
    """
    from app.tasks.search_head_warmer import _WARM_OFF_VALUES
    from app.utils.search_cache import _CACHE_OFF_VALUES

    assert _WARM_OFF_VALUES == _CACHE_OFF_VALUES


@pytest.mark.asyncio
async def test_a_disabled_pass_says_disabled_and_not_merely_zero(monkeypatch):
    """"Turned off on purpose" and "wedged" must never produce the same summary.

    A pass that warmed nothing because an operator disabled it, and a pass that
    warmed nothing because the lock was stuck, are opposite diagnoses reaching
    the same `warmed: 0`. `skip_reason` is what separates them (gotcha #53).

    The disable is now EXPLICIT rather than inherited from an unset var: since
    LAT-P102 unset means ON, so a test that wants the disabled path has to ask
    for it. Deleting the `setenv` would silently turn this into a test of the
    ENABLED path against a Redis that is not running.
    """
    from app.tasks.search_head_warmer import SEARCH_HEAD_WARM_ENV, _warm_search_head

    monkeypatch.setenv(SEARCH_HEAD_WARM_ENV, "0")
    summary = await _warm_search_head()

    assert summary["terminal"] == "skipped"
    assert summary["skip_reason"] == "disabled"
    assert summary["warmed"] == 0


def test_an_empty_head_is_reported_as_partial_and_never_as_a_clean_pass():
    """"It returned" is not "it worked" (`app/utils/task_verdict.py`).

    A warmer whose entire purpose is that the head is hot must not be able to
    report `complete` while it is cold. An empty head means the query log had
    nothing to say, which is a real finding and a broken guarantee — not a
    successful pass over zero items.
    """
    from app.tasks.search_head_warmer import _summarize

    empty = _summarize(head=[], results=[], source="db:search_query_logs:30d",
                       seconds_wall=0.0, since_last=None, width=2)
    assert empty["terminal"] == "partial"
    assert empty["total"] == 0
