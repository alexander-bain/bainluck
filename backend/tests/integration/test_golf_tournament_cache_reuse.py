"""LAT-P186 — the golf tournament detail route must read the warm listing, not rebuild it.

Why this file exists
--------------------
``GET /api/golf/tournaments/{slug}`` opened with the comment *"Reuse get_golf() for
its caching and aggregation"* and then called ``get_golf()`` — which has no caching
at all. The caching lives in ``get_golf_cached()``, its sibling thirty lines up, and
that is what ``GET /api/golf`` is wired to. So the golf landing page answered out of
Redis while the tournament DETAIL page rebuilt the entire golf listing from scratch
on every request.

``_build_completed_tournament`` carried the same wrong belief in its own comment
(*"from the golf API response (already cached)"*) and called ``get_golf()`` a SECOND
time inside the same request, to read one key off the result. Every completed
tournament therefore paid the full rebuild twice.

MEASURED on production 2026-09-01 via ``x-timing-split``, median of 5 samples:

===================================  =========================================
``/api/golf/tournaments/us-open``    **2,076 ms wall / 1,556 ms app / q=19**
``/api/golf/tournaments/the-masters``  **1,795 ms wall / 1,391 ms app / q=18**
``/api/golf``            (cached)    **45 ms wall / 0 ms db / q=0**
===================================  =========================================

These assert the WIRING, not wall-clock — a timing assertion on CI hardware is
flaky and proves nothing about production (LAT-P005, and the sibling file
``test_golf_completed_tournament_query_shape.py`` makes the same choice).

What makes this worth guarding at all: the regression is SILENT. Point the route
back at ``get_golf`` and every existing golf test still passes, every response body
is byte-identical, and the only symptom is that the page takes two seconds again.
Nothing else in the suite would notice.
"""

from __future__ import annotations

import inspect

from app.routes import golf as golf_route


def _listing(*, tournaments):
    """A minimally-valid `get_golf()`-shaped payload."""
    return {
        "tournaments": list(tournaments),
        "biggest_movers": [],
        "upcoming_events": [],
        "current_event": None,
        "total_tournaments": len(tournaments),
        "total_golfers": 0,
        "pga_schedule": [],
    }


_MASTERS = {
    "name": "The Masters",
    "slug": "masters",
    "key": "masters",
    "is_major": True,
    "is_womens": False,
    "start_date": "2026-04-09T00:00:00+00:00",
    "end_date": "2026-04-12T00:00:00+00:00",
    "venue": "Augusta National",
    "location": "Augusta, GA",
    "schedule_status": "upcoming",
    "commence_time": "2026-04-09T00:00:00+00:00",
    "resolution_date": "2026-04-12T00:00:00+00:00",
    "golfers": [{"name": "Scottie Scheffler", "win_prob": 18.4, "sources": ["datagolf"]}],
    "market_ids": [],
    "market_names": [],
    "h2h_matchups": [],
}


class TestRouteReadsTheCachedListing:
    """R1 — the detail route must resolve its listing through `get_golf_cached`."""

    async def test_detail_route_does_not_rebuild_the_listing(self, client, monkeypatch):
        """The load-bearing one.

        `get_golf` is replaced by a mock that FAILS the test if it is reached, so
        this cannot pass under the old wiring: the pre-fix route called `get_golf`
        directly and would trip the sentinel. `get_golf_cached` returns the payload,
        so a passing run proves the cached read is the one that served the request.
        """
        calls: list[str] = []

        async def _cached(db):
            calls.append("cached")
            return _listing(tournaments=[_MASTERS])

        async def _uncached(db):
            calls.append("uncached")
            raise AssertionError(
                "the tournament detail route rebuilt the whole golf listing — it "
                "must read `get_golf_cached()`, the same warm payload `GET /api/golf` "
                "serves, not the uncached `get_golf()` (LAT-P186)"
            )

        monkeypatch.setattr(golf_route, "get_golf_cached", _cached)
        monkeypatch.setattr(golf_route, "get_golf", _uncached)

        resp = await client.get("/api/golf/tournaments/masters")

        assert resp.status_code == 200, resp.text
        assert resp.json()["tournament"]["name"] == "The Masters"
        assert calls == ["cached"], (
            f"expected exactly one cached listing read, got {calls}"
        )

    async def test_a_cold_redis_still_serves_the_page(self, client, monkeypatch):
        """The degradation claim, which is the thing a reviewer should attack.

        The fix is only safe because `get_golf_cached` falls back to the live
        rebuild when Redis is missing or empty. If that fallback ever stops
        working, an evicted key turns the golf page into an error instead of a
        slow page. This drives the REAL `get_golf_cached` with Redis broken.
        """
        import app.tasks.redis_state as redis_state

        def _no_redis():
            raise RuntimeError("redis is down")

        calls: list[str] = []

        async def _uncached(db):
            calls.append("uncached")
            return _listing(tournaments=[_MASTERS])

        monkeypatch.setattr(redis_state, "get_async_redis_client", _no_redis)
        monkeypatch.setattr(golf_route, "get_golf", _uncached)

        resp = await client.get("/api/golf/tournaments/masters")

        assert resp.status_code == 200, resp.text
        assert resp.json()["tournament"]["name"] == "The Masters"
        assert calls == ["uncached"], (
            "with Redis down the route must fall back to the live rebuild rather "
            f"than failing; got {calls}"
        )


class TestCompletedPathDoesNotRebuildASecondTime:
    """R2 — the listing the caller already holds is handed down, not re-fetched."""

    async def test_route_hands_its_listing_to_the_completed_builder(
        self, client, monkeypatch
    ):
        """Caller half, behavioural.

        Under the old wiring `_build_completed_tournament` was called as
        `(slug, db)` and went and fetched the listing itself. The route must now
        pass the copy it already has.
        """
        seen: dict = {}

        async def _cached(db):
            return _listing(tournaments=[])

        async def _completed(slug, db, golf_data=None):
            seen["slug"] = slug
            seen["golf_data"] = golf_data
            return None

        monkeypatch.setattr(golf_route, "get_golf_cached", _cached)
        monkeypatch.setattr(golf_route, "_build_completed_tournament", _completed)

        resp = await client.get("/api/golf/tournaments/not-real")

        assert resp.status_code == 404
        assert seen["slug"] == "not-real"
        assert seen["golf_data"] is not None, (
            "the route discarded the listing it had just paid for and left "
            "`_build_completed_tournament` to fetch its own — that is the second "
            "full rebuild this fix removed (LAT-P186)"
        )
        assert "pga_schedule" in seen["golf_data"], (
            "what gets handed down must be the listing itself — `pga_schedule` is "
            "the only key the completed builder reads off it"
        )

    def test_completed_builder_only_fetches_when_it_was_given_nothing(self):
        """Callee half, by source shape.

        A behavioural version of this would need a DB stub that returns matched
        markets; with an empty stub the function early-returns before it ever
        reaches the schedule block, and the assertion would pass while proving
        nothing (the early-exit vacuity trap). So this reads the shape instead,
        and the guard below proves the read is not vacuous.
        """
        code = _strip_comments(inspect.getsource(golf_route._build_completed_tournament))

        assert "if golf_data is None:" in code, (
            "`_build_completed_tournament` must only fetch the listing when the "
            "caller did not give it one"
        )
        # Every fetch in the live body must sit under that guard.
        for fetch in ("get_golf(", "get_golf_cached("):
            for line in code.splitlines():
                if fetch in line:
                    assert "golf_data = await" in line, (
                        f"unexpected `{fetch}` call shape in "
                        f"`_build_completed_tournament`: {line.strip()!r}"
                    )
        assert "await get_golf(db=db)" not in code, (
            "the completed-tournament path is calling the UNCACHED `get_golf()` "
            "again — that is the second full listing rebuild per request that "
            "LAT-P186 removed"
        )

    def test_the_comment_stripper_is_not_lying(self):
        """`getsource` guards go vacuous when the fix's own comments quote the
        anti-pattern. This fix's comments quote `get_golf()` repeatedly and by
        name, so if `_strip_comments` ever stopped working the assertions above
        would match the explanation instead of the code — and still pass.
        """
        raw = inspect.getsource(golf_route._build_completed_tournament)
        stripped = _strip_comments(raw)

        assert "# LAT-P186" not in stripped and "already cached" not in stripped, (
            "comment stripping regressed — the guards above are now reading prose"
        )
        assert len(stripped) < len(raw), "nothing was stripped; the helper is a no-op"
        # And the stripper must not have eaten the code it is meant to expose.
        assert "if golf_data is None:" in stripped


def _strip_comments(src: str) -> str:
    """Drop whole-line `#` comments.

    Mirrors the helper in `test_golf_completed_tournament_query_shape.py`. The fix
    is heavily commented and those comments QUOTE the anti-pattern they replaced,
    so a naive substring check matches the explanation rather than live code.
    """
    return "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )


def test_the_route_and_the_landing_page_read_the_same_key():
    """The whole ship in one line: both surfaces resolve through the same function.

    `GET /api/golf` is `get_golf_cached`. If the detail route ever stops routing
    through it, the two surfaces can print different probabilities for the same
    tournament again — which is the divergence this fix closed, not just a
    latency win.
    """
    detail = _strip_comments(inspect.getsource(golf_route.get_golf_tournament))

    assert "await get_golf_cached(db=db)" in detail
    assert "await get_golf(db=db)" not in detail, (
        "the detail route is back on the uncached rebuild (LAT-P186)"
    )
