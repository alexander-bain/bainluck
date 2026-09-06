"""LAT-P124 / #2285 — `/api/events/search-suggestions` stops rebuilding itself for
every visitor, and stops paying a 1.14 GB sort for five rows that cannot reach the
page.

WHAT A PERSON WAITS FOR. `frontend/app/search/page.tsx:313` calls
`fetchSearchSuggestions()` on mount and renders "Loading suggestions..." until it
answers. Measured on production slug `d9b76e9b`, three consecutive reads two
seconds apart, against a measured 0.32 s transport floor:

    /api/events/search-suggestions   wall=12.2s
    /api/events/search-suggestions   wall=14.5s
    /api/events/search-suggestions   wall= 7.5s

TWO DEFECTS, ONE ROUTE.

1. The `setex` at the bottom of the route referenced `_cache_key` and `_json`,
   and neither name existed in that scope — a copy of `team_progression`'s WRITE
   half without its HEAD half, with a bare `except Exception: pass` turning the
   `NameError` into silence. No write, and no read path at all. Three slow reads
   in a row is the signature.
2. Section 3's `ORDER BY abs(probability_change_24h) DESC` seq-scans and sorts
   `futures_outcomes` — 146,437 shared blocks, 1,808,454 rows removed by filter,
   an external merge to disk — to keep FIVE rows. On the read that motivated
   this change all eight slots were already filled by section 2, so the loop
   broke on its first iteration and every one of those blocks was discarded.

A THIRD DEFECT, FOUND WHILE BUILDING THESE FIXTURES AND FILED AS #2286: sections
1 and 5 have NEVER RUN. Both name a model attribute that does not exist
(`OddsSnapshot.home_probability`, `FuturesMarket.outcome_count`), so both raise
`AttributeError` while their statement is still being built and both bare
`except`s swallow it. That is why every production read returns nothing but
"Starts in Nh" chips — section 2 is the first section that works. Pinned by
`TestSectionsThatHaveNeverRun`, not repaired here.

🔴 EVERY ASSERTION HERE IS ON A QUERY COUNT, A CACHE INTERACTION OR A RENDERED
VALUE. None reads a clock (gotcha #44). The window is filled from section 2,
whose label IS time-derived — so its `commence_time` fixture is pinned far
enough in the past that the `minutes < 60` branch is taken on every clock
forever, and no assertion reads `label` at all. See `_FIXED_COMMENCE`.
"""

import ast
import json
import pathlib
from types import SimpleNamespace

import pytest

from app.models.models import FuturesMarket
from app.routes import events as events_routes
from app.routes.events import (
    _MAX_SUGGESTIONS,
    _build_search_suggestions,
    search_suggestions,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class _Rows:
    """A result that answers both `.scalars().all()` and `.all()`.

    The route uses both shapes — `.scalars().all()` for entity selects and a bare
    `.all()` for the odds tuple select — so one double serves every call site.
    """

    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _RecordingDB:
    """Hands back queued results in call order and records every statement.

    🔴 It RAISES on an unexpected extra `execute`. A double that quietly returns
    an empty result for a statement the test did not expect would let a skip
    regression pass as a pass — the count is the whole measurement here.
    """

    def __init__(self, results):
        self._results = list(results)
        self.executed = []

    async def execute(self, q):
        self.executed.append(q)
        if not self._results:
            raise AssertionError(
                f"db.execute called {len(self.executed)} times; the fixture only "
                f"queued {len(self.executed) - 1}. An unexpected statement ran."
            )
        return self._results.pop(0)


class _FakeRedis:
    def __init__(self, stored=None, get_raises=False, setex_raises=False):
        self.stored = stored
        self.get_calls = []
        self.setex_calls = []
        self.delete_calls = []
        self._get_raises = get_raises
        self._setex_raises = setex_raises

    def get(self, key):
        self.get_calls.append(key)
        if self._get_raises:
            raise RuntimeError("redis down")
        return self.stored

    def setex(self, key, ttl, payload):
        self.setex_calls.append((key, ttl, payload))
        if self._setex_raises:
            raise RuntimeError("redis down")

    def delete(self, key):
        # LAT-P139: `write_payload` clears the tier's negative slot on every
        # write. This tier has no negative path, but the shared writer is shared
        # and a double that cannot answer it would turn every write into a
        # swallowed exception — i.e. into the LAT-P124 defect, in the fixtures.
        self.delete_calls.append(key)


def _stored(items, created_at=None):
    """An enveloped payload, the way the tier actually stores one.

    A bare `{"suggestions": [...]}` is what the pre-LAT-P139 writer produced and
    `read_slot` now reads it as a MISS — deliberately, so no pre-envelope value
    is ever served as though it carried one. Fixtures therefore have to build a
    real envelope, and building it through the tier's own `stamp` is what stops
    this helper drifting away from the producer.
    """
    from fastapi.encoders import jsonable_encoder

    from app.utils import search_suggestions_cache as ssc

    return jsonable_encoder(ssc.stamp({"suggestions": items}, created_at=created_at))


@pytest.fixture
def redis_double(monkeypatch):
    """Install a fake `get_redis_client` and hand the test the client back.

    The route imports `get_redis_client` from `app.tasks.redis_state` INSIDE the
    function body, so the patch has to land on the source module, not on
    `app.routes.events`.
    """
    import app.tasks.redis_state as redis_state

    holder = {}

    def install(client):
        holder["client"] = client
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: client)
        return client

    return install


#: How far ahead of the route's own `now` a fixture game starts.
#:
#: 🔴 GOTCHA #44 — THE ANCHOR MUST NOT BRANCH ON THE CLOCK, AND THIS ONE DOES
#: NOT: the offset is applied FIRST and 30 is `< 60` on every clock, forever, so
#: the "Tips off in N min" branch is the one taken every run. There is no `if`
#: in the anchor. The exact N varies and no assertion in this file reads it.
#:
#: 🔴 IT USED TO BE `datetime(2020, 1, 1)` — A DATE IN THE PAST — AND LAT-P139
#: MOVED IT, WHICH IS A REAL BEHAVIOUR CHANGE AND NOT A FIXTURE TIDY-UP.
#: The old route rendered a past commence_time as "Tips off in -3466080 min"
#: without complaint; `search_suggestions_cache.countdown_label` returns None for
#: a game that has already started and the section skips the item. Production
#: cannot reach that case — section 2's query is `commence_time BETWEEN now AND
#: now + 3h` — so the fixture was exercising a state the query forbids, and it
#: only ever worked because the old label was unguarded arithmetic. A fixture in
#: the future is what the query actually returns.
_SOON_MINUTES = 30


def _soon_commence():
    from datetime import datetime, timedelta, timezone as _tz

    return datetime.now(_tz.utc) + timedelta(minutes=_SOON_MINUTES)

#: Eight distinct pairs. `_add` dedups on the lowercased query, and the query is
#: the SHORTER of the two names, so every pair must have a distinct shorter name
#: or the window silently fails to fill.
_PAIRS = [
    ("Aces", "Liberty"),
    ("Sky", "Lynx"),
    ("Storm", "Mercury"),
    ("Sun", "Wings"),
    ("Fever", "Dream"),
    ("Mystics", "Sparks"),
    ("Wolves", "Valkyries"),
    ("Devils", "Rangers"),
]

#: The eight `query` values the fixtures above must produce, in order — the
#: shorter of each pair, ties going to the home name.
_EXPECTED_QUERIES = ["Aces", "Sky", "Storm", "Sun", "Fever", "Sparks", "Wolves", "Devils"]


def _soon_events(n):
    return [
        SimpleNamespace(
            id=i + 1,
            home_team_name=h,
            away_team_name=a,
            commence_time=_soon_commence(),
        )
        for i, (h, a) in enumerate(_PAIRS[:n])
    ]


def _code_of(fn) -> str:
    """A function's source with comments and docstrings stripped.

    🔴 A SOURCE-SCANNING ASSERTION MUST NOT READ ITS OWN EXPLANATION. The first
    draft of `test_section_1_reads_the_blend_not_an_odds_snapshot` asserted that
    `bookmaker == "aggregate"` is absent from section 1 — and it failed, because
    the comment ABOVE the repair quotes that exact string while explaining why the
    filter was removed. A guard that a comment can turn red is a guard that pushes
    the next author to delete the explanation, which is the opposite of what these
    files are for.
    """
    import inspect
    import io
    import tokenize

    src = inspect.getsource(fn)
    out = []
    prev_type = tokenize.INDENT
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        # A STRING that is the whole statement is a docstring.
        if tok.type == tokenize.STRING and prev_type in (
            tokenize.INDENT, tokenize.NEWLINE, tokenize.NL, tokenize.DEDENT,
        ):
            continue
        out.append(tok.string if tok.type != tokenize.NL else "\n")
        if tok.type not in (tokenize.NL,):
            prev_type = tok.type
    return " ".join(out)


def _db_with_soon(n, *, extra_sections):
    """Section 1 finds no live events; section 2 returns `n`.

    Section 1 is given an empty result so that section 2 owns the window and the
    statement count below reads as a statement about the SKIP rather than about
    section 1's contribution.

    🔴 THIS DOCSTRING USED TO SAY THE EMPTY RESULT WAS THE ONLY WAY TO EXERCISE
    SECTION 1 "WITHOUT TRIPPING #2286" — because a non-empty result made the route
    raise `AttributeError` while BUILDING `odds_q`. #2286 is repaired: section 1
    reads the blend off the rows this fixture returns and issues no second
    statement, so a non-empty result is now perfectly safe here. It is kept empty
    only to isolate the skip.
    """
    return _RecordingDB(
        [_Rows([]), _Rows(_soon_events(n))] + [_Rows([]) for _ in range(extra_sections)]
    )


def _full_window_db():
    """Section 2 fills all eight slots; nothing after it should be queried."""
    return _db_with_soon(8, extra_sections=0)


def _open_window_db():
    """Section 2 fills two slots; sections 3, 4 and 5 must all still run."""
    return _db_with_soon(2, extra_sections=3)


# ---------------------------------------------------------------------------
# 1. The skip — the latency ship
# ---------------------------------------------------------------------------


class TestTheWindowFullSkip:
    async def test_a_full_window_issues_exactly_two_statements(self, redis_double):
        """The 1.14 GB sort does not run when its rows cannot reach the page.

        Before this change the route always issued four statements once section
        2 was reached. Section 3 — 146,437 shared blocks of the route's ~147,100
        — was the third of them.
        """
        redis_double(_FakeRedis())
        db = _full_window_db()

        resp = await search_suggestions(db=db)

        assert len(db.executed) == 2, (
            f"expected only section 1's live-event probe and section 2's, got "
            f"{len(db.executed)}. A third means a later section ran with the "
            "window already full — the movers seq-scan is back."
        )
        assert len(resp["suggestions"]) == _MAX_SUGGESTIONS

    async def test_an_open_window_still_runs_every_live_section(self, redis_double):
        """🔴 The mirror direction, and the one that matters for recall.

        A skip that fires when the window is NOT full would silently delete
        suggestions. `_RecordingDB` raises on any statement the fixture did not
        queue, so this fails loudly in both directions: too few statements is an
        over-eager skip, too many is a statement nobody accounted for.
        """
        redis_double(_FakeRedis())
        db = _open_window_db()

        resp = await search_suggestions(db=db)

        assert len(db.executed) == 5, (
            f"expected all five sections to run on a two-slot window, got "
            f"{len(db.executed)}. A section was skipped while it could still "
            "have contributed."
        )
        assert len(resp["suggestions"]) == 2

    @pytest.mark.parametrize("filled", [0, 1, 7])
    async def test_the_boundary_is_walked_below_the_window(
        self, filled, redis_double
    ):
        """Anything short of the window keeps every later section alive.

        7 is the interesting one: one slot free is still a slot, and the movers
        row that fills it is a real suggestion a reader would otherwise not see.
        """
        redis_double(_FakeRedis())
        db = _db_with_soon(filled, extra_sections=3)

        await search_suggestions(db=db)

        # FIVE, not four. #2286 brought section 5 back from the dead, so the
        # ceiling this test walks up to moved by exactly one statement — see
        # `TestSectionsThatHaveNeverRun`.
        assert len(db.executed) == 5

    async def test_at_exactly_the_window_the_later_sections_stop(self, redis_double):
        """8 filled is the first value at which the skip is allowed to fire."""
        redis_double(_FakeRedis())
        db = _full_window_db()

        await search_suggestions(db=db)

        assert len(db.executed) == 2

    async def test_the_skip_changes_the_cost_and_not_the_content(self, redis_double):
        """The skip is a COST change. These eight values are what the old code
        returned for this fixture too, because the loops it skipped broke on
        their first iteration and added nothing."""
        redis_double(_FakeRedis())
        resp = await search_suggestions(db=_full_window_db())

        assert [s["query"] for s in resp["suggestions"]] == _EXPECTED_QUERIES
        assert all(s["type"] == "event" for s in resp["suggestions"])


# ---------------------------------------------------------------------------
# 2. The cache that never existed
# ---------------------------------------------------------------------------


class TestTheCache:
    async def test_a_warm_slot_is_served_without_touching_the_database(
        self, redis_double
    ):
        cached = _stored(
            [{"query": "Aces", "label": "Championship odds", "type": "futures"}]
        )
        redis_double(_FakeRedis(stored=json.dumps(cached)))
        db = _RecordingDB([])  # raises on ANY execute

        resp = await search_suggestions(db=db)

        assert resp["suggestions"] == cached["suggestions"]
        assert db.executed == [], "a cache hit must not query the database"

    async def test_the_key_is_shared_and_unparameterised(self, redis_double):
        """One slot for the fleet — the endpoint takes no argument and reads no
        principal, so there is nothing to key on.

        LAT-P139 added the MIRROR beside it. The primary keeps its production
        name, which is the whole reason the prefix and the slot were chosen the
        way they were; the mirror is that name plus `:stale`.
        """
        rc = redis_double(_FakeRedis())
        await search_suggestions(db=_full_window_db())

        assert rc.get_calls == [
            "bainluck:search_suggestions:v1",
            "bainluck:search_suggestions:v1:stale",
        ], "a miss reads the primary and then the mirror, in that order"
        assert [c[0] for c in rc.setex_calls] == [
            "bainluck:search_suggestions:v1",
            "bainluck:search_suggestions:v1:stale",
        ]

    async def test_the_ttl_is_sixty_seconds_and_the_mirror_is_a_day(
        self, redis_double
    ):
        """🔴 THE FRESH TTL IS STILL 60 s, AND THAT IS DELIBERATE.

        LAT-P124 pinned 60 s with a reason: `label` was baked at build time, so a
        copy older than a minute printed a wrong minute count. LAT-P139 removed
        that reason rather than the constant — the countdown is rendered at SERVE
        time now — and the fresh TTL stayed 60 s anyway, because how often the
        tier rebuilds is a different question from how stale a reader's copy may
        be. The mirror is what answers the second one, and it is a day.

        So this is no longer "do not widen"; it is "widening this is a decision
        about rebuild frequency, and it buys nothing, because the mirror already
        means nobody waits."
        """
        rc = redis_double(_FakeRedis())
        await search_suggestions(db=_full_window_db())

        assert [c[1] for c in rc.setex_calls] == [60, 86400]

    async def test_the_written_payload_is_the_returned_payload_plus_the_serve(
        self, redis_double
    ):
        """🔴 STORED AND SERVED DIFFER BY EXACTLY THE RENDER AND THE AVAILABILITY.

        They were byte-identical before LAT-P139 and they cannot be now: the
        stored artifact carries `countdown_from` so a later reader can re-derive
        the minute count, and the served body has it stripped and its labels
        rendered. Asserting the difference is EXACTLY the render is what stops
        the two drifting into two payloads.
        """
        from app.utils import search_suggestions_cache as ssc

        rc = redis_double(_FakeRedis())
        resp = await search_suggestions(db=_full_window_db())

        stored = json.loads(rc.setex_calls[0][2])
        assert stored == json.loads(rc.setex_calls[1][2]), "both slots, one payload"
        assert all(
            ssc.COUNTDOWN_FIELD in s for s in stored["suggestions"]
        ), "the stored copy must keep the deadlines or the mirror cannot render"
        assert all(
            ssc.COUNTDOWN_FIELD not in s for s in resp["suggestions"]
        ), "the deadline is an internal field and must not reach the wire"
        assert resp == ssc.with_availability(
            ssc.render(stored), ssc.AVAILABILITY_LIVE
        )

    async def test_a_dead_redis_still_serves_the_chips(self, redis_double):
        """A cache outage degrades to slow, never to blank."""
        redis_double(_FakeRedis(get_raises=True, setex_raises=True))
        resp = await search_suggestions(db=_full_window_db())

        assert len(resp["suggestions"]) == _MAX_SUGGESTIONS

    async def test_a_truthy_but_unparseable_slot_falls_through_to_a_build(
        self, redis_double
    ):
        """🔴 LAT-P123's lesson, applied before it could bite.

        `if _cached:` is a truthiness test. A slot holding anything that is not
        JSON — a half-written value, or an auto-`MagicMock` in a suite that
        stubs Redis loosely — is truthy. It must fall through to the build, not
        500 and not return the mock.
        """
        redis_double(_FakeRedis(stored=b"\xff not json"))
        resp = await search_suggestions(db=_full_window_db())

        assert len(resp["suggestions"]) == _MAX_SUGGESTIONS


# ---------------------------------------------------------------------------
# 3. The invariant that makes the skip sound
# ---------------------------------------------------------------------------


def _search_suggestions_source():
    """The AST of the function that holds the five SECTIONS.

    🔴 LAT-P139 SPLIT THE ROUTE AND THIS FOLLOWED THE BODY, NOT THE NAME.
    `search_suggestions` is now the cache policy and `_build_search_suggestions`
    is the build — the same split `get_related_futures` / `_build_related_futures`
    already has one file over. Every assertion below is about the sections, so it
    has to read the function the sections live in; pointing it at the policy
    would make all three pass vacuously (no `8`, no `_window_full`, no
    `_MAX_SUGGESTIONS` in it) and that is the silent-narrowing failure these
    tests exist to refuse. Hence the explicit not-found error.
    """
    src = pathlib.Path(events_routes.__file__).read_text()
    tree = ast.parse(src)
    for node in tree.body:
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_build_search_suggestions"
        ):
            return node
    raise AssertionError(
        "_build_search_suggestions not found in app/routes/events.py — if the "
        "build was renamed or re-inlined, re-target this helper. Do NOT point it "
        "at a function without the sections in it; these tests would then pass "
        "by describing nothing."
    )


class TestTheWindowConstantIsSingleSourced:
    def test_no_bare_window_literal_survives_in_the_route(self):
        """🔴 The skip and the `break` MUST test the same number.

        A section is skipped exactly when its loop would break on the first
        iteration. If a later edit moves one `8` and not the other, the skip
        stops being a no-op and starts deleting suggestions — silently, because
        the response would still be well-formed. Naming the constant is what
        makes that edit impossible; this test is what keeps the name.
        """
        fn = _search_suggestions_source()
        bare = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Compare)
            and any(
                isinstance(c, ast.Constant) and c.value == 8 for c in n.comparators
            )
        ]
        assert bare == [], (
            "a bare `8` comparison is back in search_suggestions; use "
            "_MAX_SUGGESTIONS so the skip and the break cannot diverge"
        )

    def test_the_predicate_is_used_by_every_later_section(self):
        """Sections 2-5 are guarded; section 1 is deliberately not.

        Section 1 runs against an empty `suggestions`, so a guard there is a
        branch that can never be taken — and an untakeable branch is worse than
        no branch, because it reads as coverage.
        """
        fn = _search_suggestions_source()
        calls = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_window_full"
        ]
        assert len(calls) == 4, (
            f"expected _window_full() at sections 2, 3, 4 and 5 — found "
            f"{len(calls)} call sites"
        )

    def test_the_predicate_reads_the_named_constant(self):
        fn = _search_suggestions_source()
        inner = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.FunctionDef) and n.name == "_window_full"
        ]
        assert len(inner) == 1
        names = {n.id for n in ast.walk(inner[0]) if isinstance(n, ast.Name)}
        assert "_MAX_SUGGESTIONS" in names


# ---------------------------------------------------------------------------
# 4. The class guard — the defect that hid for as long as the code existed
# ---------------------------------------------------------------------------


class TestNoCacheWriteReferencesAnUnboundName:
    """🔴 THE CHECK THAT CATCHES THIS CLASS, not just this instance.

    The bug was a cache write naming `_cache_key` and `_json` in a function that
    bound neither, inside a bare `except Exception: pass`. Nothing failed, no
    log line appeared, and the route silently had no cache for as long as it had
    existed. A reviewer cannot see it: the block is byte-identical to a working
    one thirty-eight hundred lines away.

    So the guard is structural. For every top-level function in
    `app/routes/events.py`, any of these private cache names it READS, it must
    also BIND — by assignment or by import — somewhere in its own body.
    """

    WATCHED = ("_cache_key", "_json", "_rc")

    def test_every_reader_of_a_cache_name_also_binds_it(self):
        src = pathlib.Path(events_routes.__file__).read_text()
        tree = ast.parse(src)

        module_bound = set()
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    module_bound.add(a.asname or a.name.split(".")[0])
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        module_bound.add(t.id)

        offenders = []
        for fn in tree.body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            bound = set(module_bound)
            read = set()
            for n in ast.walk(fn):
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    for a in n.names:
                        bound.add(a.asname or a.name.split(".")[0])
                elif isinstance(n, ast.Name):
                    if isinstance(n.ctx, ast.Store):
                        bound.add(n.id)
                    elif isinstance(n.ctx, ast.Load):
                        read.add(n.id)
            for name in self.WATCHED:
                if name in read and name not in bound:
                    offenders.append(f"{fn.name}() reads {name} without binding it")

        assert offenders == [], (
            "a cache write references a name its function never binds — this is "
            "the LAT-P124 defect, and the surrounding `except Exception: pass` "
            "will hide it in production:\n  " + "\n  ".join(offenders)
        )


# ---------------------------------------------------------------------------
# 5. Two sections have never run — pinned, not repaired
# ---------------------------------------------------------------------------


class TestSectionsThatHaveNeverRun:
    """🔴 #2286, REPAIRED — AND THESE PINS ARE INVERTED RATHER THAN DELETED.

    LAT-P124 found two of the five sections naming a model attribute that does not
    exist, so each raised `AttributeError` while its statement was still being
    BUILT — before any round trip — and each section's bare `except Exception:
    pass` swallowed it. Neither had ever produced a suggestion, which is why every
    production read returned nothing but "Starts in Nh" chips: section 2 was the
    first section that worked, so it filled the window and the rest was decoration.

    That queue pinned both as facts and said: *"WHEN EITHER OF THESE GOES RED the
    attribute exists, the section has started issuing a real query, and somebody
    owes `/search` a fresh cost measurement."* This is that day. The cost
    measurement is in the class docstring of `TestSectionOneCostsNothingNow` below
    and in the commit body.

    **Inverted, not deleted, because the pin's SUBJECT is still live.** The old
    assertions said "this attribute is absent". The new ones say "the section runs
    and contributes", which is the same claim about the same code with the sign
    flipped — and deleting them would have retired the only tests that can tell
    anyone whether these two sections are alive. They were dead for as long as the
    code existed precisely because nothing asserted they were not.

    The repairs are NOT what #2286's scope proposed, and the difference is
    measured rather than argued — see `test_section_1_reads_the_blend_not_an_odds_snapshot`.
    """

    def test_section_1_reads_the_blend_not_an_odds_snapshot(self):
        """The rename #2286 asked for would have shipped an 800 ms no-op.

        The issue scoped section 1 as "rename `home_probability` to
        `home_win_probability` and re-measure". Measured on production before
        writing the repair, that rename alone fixes nothing: the same subquery also
        filters `bookmaker == "aggregate"`, and **nothing writes that bookmaker.**

          * 18 real books wrote `odds_snapshots` rows in the last two hours;
            `aggregate` was not among them.
          * Independently: every `bookmaker=` write site in `app/` emits a real book
            key, `polymarket`, `kalshi` or `datagolf_model`. No writer, ever.
          * So with the name corrected the query still returns `Actual Rows: 0` —
            `EXPLAIN (ANALYZE, BUFFERS)` measured 799.8 ms and 46,012 shared buffer
            hits to return nothing, on every uncached build.

        So the odds subquery is GONE rather than renamed, and the probability comes
        from the blend already loaded on the `Event` rows. This test pins the
        negative half — that neither dead reference can come back — because a future
        editor reaching for "the latest odds snapshot" here would reintroduce both
        the cost and the emptiness.
        """
        section_1 = _code_of(_build_search_suggestions).split(
            "# --- 2. Starting soon"
        )[0]

        assert "compute_aggregate_probability" in section_1, (
            "section 1 no longer reads the blend. It is the app-wide ruling for "
            "this number (one number per question) and it is the only source with "
            "coverage: 55 of 69 live events carry a blend, 0 carry an `aggregate` "
            "odds snapshot"
        )
        # ⚠️ `OddsSnapshot`, not `"home_probability"`. The narrower string is a
        # SUBSTRING of `ev.opening_home_probability`, which section 1 legitimately
        # reads for its upset check — an assertion on it fails on correct code.
        # The real claim is bigger and simpler anyway: section 1 does not touch the
        # odds-snapshot table at all any more, which is what makes it free.
        assert "OddsSnapshot" not in section_1, (
            "section 1 references `OddsSnapshot` again. Both of its dead names lived "
            "there — `home_probability` (no such column) and `bookmaker == "
            '"aggregate"` (no such writer) — and the query they formed measured '
            "799.8 ms and 46,012 shared buffers to return zero rows (#2286). The "
            "blend needs no round trip; this would be a paid one."
        )

    def test_section_5_orders_by_volume_and_not_by_a_column_that_never_existed(self):
        """`outcome_count` is dead, and its literal intent is refused."""
        assert not hasattr(FuturesMarket, "outcome_count"), (
            "FuturesMarket.outcome_count now exists. #2286 rejected this quantity "
            "on the merits — a correlated COUNT of outcomes is 'most runners', not "
            "'most popular', and a 30-runner novelty market would outrank the Super "
            "Bowl. If it has been added for another purpose, section 5 must still "
            "not order by it."
        )
        assert hasattr(FuturesMarket, "volume_24h") and hasattr(FuturesMarket, "volume"), (
            "section 5's ordering columns are gone; re-derive #2286 before trusting "
            "anything here"
        )

        section_5 = _code_of(_build_search_suggestions).split(
            "# --- 5. Popular championship markets"
        )[-1]
        assert "volume_24h" in section_5 and "nulls_last" in section_5, (
            "section 5 stopped ordering by volume with NULLS LAST — ~1,100 of the "
            "3,126 tier-1 open markets have no volume at all and would win on a NULL"
        )

    async def test_a_live_event_now_produces_a_chip_and_costs_no_extra_statement(
        self, redis_double
    ):
        """The behavioural half, inverted. **One statement, not two.**

        Before: the route paid for `live_events_q` and then died building `odds_q`
        — a round trip bought for nothing on every uncached request. After: the
        blend is read off the rows `live_events_q` already returned, so section 1
        issues exactly ONE statement and produces a chip from it.

        The count is the assertion that matters. A repair that added the odds query
        back and merely made it work would still pass a chip-shaped assertion.
        """
        redis_double(_FakeRedis())
        live = [
            SimpleNamespace(
                id=1,
                status="live",
                home_team_name="Aces",
                away_team_name="Liberty",
                # 🔴 #3671. BOTH OF THESE LINES ARE THE FIX, AND THE SECOND ONE
                # IS THE HALF THAT MAKES THE FIRST WORTH ANYTHING.
                #
                # This fixture used to read `{"betting": {"home": 0.52}}` with
                # `opening_home_probability=0.5` beside it. The nested shape is
                # obsolete — production stores the flat form, verified on a live
                # event 2026-09-06 — and `compute_aggregate_probability` returns
                # None for it. So the chip below was produced by the
                # `opening_home_probability` COALESCE fallback (gotcha #144 /
                # ruling 103), not by the blend, and a regression in the blend
                # read this test exists to cover would have left it green.
                #
                # Flat shape, and no fallback for the assertion to land on: 0.52
                # can now only reach the band through `win_probability_sources`.
                opening_home_probability=None,
                win_probability_sources={"betting": 0.52},
                espn_win_prob_home=None,
            )
        ]
        db = _RecordingDB([_Rows(live), _Rows(_soon_events(8))])

        resp = await search_suggestions(db=db)

        assert len(db.executed) == 2, (
            f"section 1 must issue exactly one statement (the live-event probe) and "
            f"read the blend off its rows; section 2 issues the other. "
            f"{len(db.executed)} means the odds round trip is back"
        )
        labels = [s["label"] for s in resp["suggestions"]]
        assert any("Live" in lbl for lbl in labels), (
            f"section 1 ran but contributed nothing — a 0.52 blend is inside the "
            f"0.35-0.65 tight-game band and must produce a chip: {labels}"
        )

    async def test_a_failing_section_says_so_instead_of_vanishing(
        self, redis_double, caplog
    ):
        """🔴 THE CLASS, AND THE ONLY REASON #2286 LASTED. A surviving mutant.

        Replacing any section's `_log_dead_suggestion_section(...)` with `pass`
        left the whole suite green — which is exactly the state the route shipped
        in for as long as it existed. Two sections were dead, the endpoint returned
        200 with a short list, and nothing anywhere said a word; the defect was
        found by someone measuring the endpoint for an unrelated reason.

        Two claims, and both matter:

          * the route SURVIVES a broken section (non-critical is still the rule —
            one dead chip source must not take the search box down), and
          * it is no longer SILENT about it, and the log names WHICH section, so an
            operator reading it does not have to bisect five try blocks.

        Driven by making section 3's query raise, because a raise from `execute` and
        a raise while BUILDING a statement land in the same `except` — and the
        second is the one that hid here.
        """
        import logging

        redis_double(_FakeRedis())

        class _BoomOnThird:
            def __init__(self):
                self.executed = []
                self._results = [_Rows([]), _Rows(_soon_events(2)), None, _Rows([]), _Rows([])]

            async def execute(self, q):
                self.executed.append(q)
                nxt = self._results.pop(0)
                if nxt is None:
                    raise RuntimeError("movers query exploded")
                return nxt

        db = _BoomOnThird()
        with caplog.at_level(logging.WARNING, logger="app.routes.events"):
            resp = await search_suggestions(db=db)

        assert resp["suggestions"], (
            "a single broken section emptied the whole response — the per-section "
            "`try` is what keeps one dead chip source from taking search down"
        )
        dead = [r for r in caplog.records if "contributed nothing" in r.getMessage()]
        assert dead, (
            "section 3 raised and NOTHING was logged. That is #2286's class exactly: "
            "a swallowed exception turns a defect into a permanently missing feature "
            f"with no trace. Records seen: {[r.getMessage() for r in caplog.records]}"
        )
        assert any("section 3" in r.getMessage() for r in dead), (
            f"the log fired but does not name the section that died: "
            f"{[r.getMessage() for r in dead]}"
        )
        assert any(r.exc_info for r in dead), (
            "the log carries no traceback. The exception TYPE is the finding — "
            "`AttributeError` means this section can never have worked, an "
            "`OperationalError` means the database had a bad minute, and an "
            "operator cannot act on a message that cannot tell them which"
        )
        # ...and the sections after the broken one still ran.
        assert len(db.executed) == 5, (
            f"a raise in section 3 stopped later sections: {len(db.executed)}"
        )

    def test_no_section_swallows_its_failure_in_silence(self):
        """The behavioural test above covers ONE section. There are five.

        🔴 A SURVIVING MUTANT SAID SO. Replacing section 5's
        `_log_dead_suggestion_section(...)` with `pass` left the suite green even
        after the behavioural guard was added, because that guard breaks section 3.
        Five independent call sites need five-site coverage, and the honest way to
        get it is structurally rather than by writing the same test five times.

        This is the assertion that would have caught #2286 on the day it was
        written: every one of these `except` blocks was `pass`, and the two dead
        sections were therefore indistinguishable from working ones.
        """
        import ast
        import inspect
        import textwrap

        from app.routes import events as events_module

        tree = ast.parse(
            textwrap.dedent(inspect.getsource(events_module._build_search_suggestions))
        )
        handlers = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]
        assert len(handlers) == 5, (
            f"expected one `except` per chip section, found {len(handlers)}. If a "
            f"section was added or removed, this test's premise moved with it."
        )
        silent = [
            h.lineno
            for h in handlers
            if all(isinstance(stmt, ast.Pass) for stmt in h.body)
        ]
        assert not silent, (
            f"{len(silent)} chip section(s) still swallow their failure with a bare "
            f"`pass` (handler line(s) {silent}, relative to the function). That is "
            f"#2286's class: the `except` wraps the statement BUILD as well as its "
            f"execution, so a typo becomes a permanently missing feature with no log "
            f"line. Call `_log_dead_suggestion_section(...)` instead."
        )

    async def test_section_five_now_reaches_the_database(self, redis_double):
        """Five statements where four was the ceiling. Section 5 is alive."""
        redis_double(_FakeRedis())
        db = _open_window_db()

        await search_suggestions(db=db)

        assert len(db.executed) == 5, (
            f"section 5 issued no statement ({len(db.executed)} total). It ordered "
            f"by a column that never existed and died while BUILDING its query for "
            f"as long as the code existed (#2286)"
        )
