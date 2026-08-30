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
from app.routes.events import _MAX_SUGGESTIONS, search_suggestions

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


def _db_with_soon(n, *, extra_sections):
    """Section 1 finds no live events; section 2 returns `n`.

    🔴 SECTION 1 IS DELIBERATELY GIVEN AN EMPTY RESULT, AND THAT IS NOT A
    CONVENIENCE — IT IS THE ONLY WAY TO EXERCISE IT WITHOUT TRIPPING #2286.
    `OddsSnapshot.home_probability` does not exist (the column is
    `home_win_probability`), so the moment `live_events` is non-empty the route
    raises `AttributeError` while BUILDING `odds_q` and section 1 dies into its
    bare `except`. That is production's behaviour today, pinned separately by
    `TestSectionsThatHaveNeverRun`. Here the empty result keeps section 1 to a
    single statement and lets section 2 own the window.
    """
    return _RecordingDB(
        [_Rows([]), _Rows(_soon_events(n))] + [_Rows([]) for _ in range(extra_sections)]
    )


def _full_window_db():
    """Section 2 fills all eight slots; nothing after it should be queried."""
    return _db_with_soon(8, extra_sections=0)


def _open_window_db():
    """Section 2 fills two slots; sections 3 and 4 must both still run."""
    return _db_with_soon(2, extra_sections=2)


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

        assert len(db.executed) == 4, (
            f"expected sections 1, 2, 3 and 4 to run on a two-slot window, got "
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
        db = _db_with_soon(filled, extra_sections=2)

        await search_suggestions(db=db)

        assert len(db.executed) == 4

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
    """🔴 LAT-P124 finding #2286, recorded as a fact rather than a suspicion,
    and deliberately NOT repaired in this queue.

    Two of the route's five sections name a model attribute that does not exist,
    so they raise `AttributeError` while their statement is still being BUILT —
    before any round trip — and each section's bare `except Exception: pass`
    swallows it. Neither has ever produced a suggestion:

      * section 1 (live close games) reads `OddsSnapshot.home_probability`; the
        column is `home_win_probability` (#2286);
      * section 5 (popular championship markets) orders by
        `FuturesMarket.outcome_count`, which exists nowhere in `app/` (#2286).

    That is why every production read of this endpoint returns nothing but
    "Starts in Nh" chips: section 2 is the first section that works, so it fills
    the window and the rest of the route is decoration.

    THEY ARE NOT REPAIRED HERE ON PURPOSE. Making a never-executing section start
    executing CHANGES WHAT A USER SEES on `/search` — new chips appear — and it
    adds a round trip this queue then has not measured. Deciding what a "tight
    game" or a "popular championship market" should be is a product call. This
    queue ships a cost change; the findings are filed and pinned.

    WHEN EITHER OF THESE GOES RED the attribute exists, the section has started
    issuing a real query, and somebody owes `/search` a fresh cost measurement.
    That is the entire point of pinning them.
    """

    def test_section_1_is_dead_because_the_odds_column_is_named_differently(self):
        from app.models.models import OddsSnapshot

        assert not hasattr(OddsSnapshot, "home_probability"), (
            "OddsSnapshot.home_probability now exists, so search_suggestions "
            "section 1 has started issuing its odds query. Re-measure the route "
            "and close #2286."
        )
        assert hasattr(OddsSnapshot, "home_win_probability"), (
            "the real column has been renamed too — re-derive #2286 before "
            "trusting anything above"
        )

    def test_section_5_is_dead_because_the_column_does_not_exist(self):
        assert not hasattr(FuturesMarket, "outcome_count"), (
            "FuturesMarket.outcome_count now exists, so search_suggestions "
            "section 5 has started issuing a real query. Re-measure the route "
            "and close #2286."
        )

    async def test_a_live_event_kills_section_1_after_exactly_one_statement(
        self, redis_double
    ):
        """The behavioural half of #2286, so it is not just a `hasattr`.

        With live events present the route pays for `live_events_q` and then dies
        building `odds_q`. Section 2 owns the window regardless. 94 blocks, so it
        is noise against section 3 — but it is a round trip bought for nothing on
        every uncached request, and that belongs in the issue.
        """
        redis_double(_FakeRedis())
        live = [
            SimpleNamespace(
                id=1,
                home_team_name="Aces",
                away_team_name="Liberty",
                opening_home_probability=0.5,
            )
        ]
        db = _RecordingDB([_Rows(live), _Rows(_soon_events(8))])

        resp = await search_suggestions(db=db)

        assert len(db.executed) == 2, (
            "section 1 executed its live-event probe and then must have raised "
            "while building odds_q; a third statement means #2286 is fixed"
        )
        assert [s["label"] for s in resp["suggestions"]] != [], "window still filled"
        assert all("Live" not in s["label"] for s in resp["suggestions"]), (
            "a section-1 chip appeared — #2286 is fixed and this pin is stale"
        )

    async def test_section_five_never_reaches_the_database(self, redis_double):
        """Four statements is the ceiling: sections 1, 2, 3, 4. Section 5 dies
        before a fifth."""
        redis_double(_FakeRedis())
        db = _open_window_db()

        await search_suggestions(db=db)

        assert len(db.executed) == 4
