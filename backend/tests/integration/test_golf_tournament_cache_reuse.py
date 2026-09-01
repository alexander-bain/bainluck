"""LAT-P186 — the golf tournament detail route builds its listing ONCE, not twice.

Why this file exists
--------------------
``GET /api/golf/tournaments/{slug}`` opened with the comment *"Reuse get_golf() for
its caching and aggregation"* and then called ``get_golf()`` — which has no caching.
``_build_completed_tournament`` carried the same wrong belief in its own comment
(*"from the golf API response (already cached)"*) and called ``get_golf()`` a
**second** time inside the same request, to read one key (``pga_schedule``) off the
result. So every completed tournament paid the entire golf-listing rebuild twice.

MEASURED on production 2026-09-01 via ``x-timing-split``, median of 5 samples:

===================================  =========================================
``/api/golf/tournaments/us-open``    **2,076 ms wall / 1,556 ms app / q=19**
``/api/golf/tournaments/the-masters``  **1,795 ms wall / 1,391 ms app / q=18**
===================================  =========================================

These assert the WIRING, not wall-clock — a timing assertion on CI hardware is
flaky and proves nothing about production (LAT-P005, and the sibling file
``test_golf_completed_tournament_query_shape.py`` makes the same choice).

What this file does NOT do, deliberately
----------------------------------------
An earlier revision of this ship ALSO pointed the route at ``get_golf_cached()``,
the Redis-backed sibling that serves ``GET /api/golf`` in ~45 ms. **CERT-686 blocked
that, correctly**, and ``test_the_route_must_not_read_the_hourly_cache`` below now
guards against it coming back. The short version: during play the DataGolf task
writes ``FuturesOutcome.current_probability`` every **90 seconds**, while
``bainluck:category:golf`` is produced hourly with a 7,200 s TTL — so sourcing the
winner field from it makes the headline "who wins?" number lag by up to an hour,
``fuse_golf_live()`` overlays position/score/thru/round but never ``probability`` so
nothing repairs it, and a cached still-open entry is found before the completed
fallback and keeps pre-settlement numbers after the DB already has a winner.

The freshness evidence that argued for the cache measured ``futures_odds_snapshots``
cadence on UPCOMING tournaments and mistook it for the freshness of the live field.
Wrong table, wrong state. That is why the guard is here and not just a comment.
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


def _strip_comments(src: str) -> str:
    """Drop whole-line `#` comments.

    Mirrors the helper in `test_golf_completed_tournament_query_shape.py`. This fix
    is heavily commented and those comments QUOTE the anti-pattern they replaced —
    including the literal string `get_golf_cached` many times over — so a naive
    substring check matches the explanation rather than live code.
    """
    return "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )


class TestTheListingIsBuiltOncePerRequest:
    """The ship: one rebuild per request, not two."""

    async def test_route_builds_the_listing_exactly_once(self, client, monkeypatch):
        calls: list[str] = []

        async def _counted(db):
            calls.append("build")
            return _listing(tournaments=[_MASTERS])

        monkeypatch.setattr(golf_route, "get_golf", _counted)

        resp = await client.get("/api/golf/tournaments/masters")

        assert resp.status_code == 200, resp.text
        assert resp.json()["tournament"]["name"] == "The Masters"
        assert len(calls) == 1, (
            f"the route built the golf listing {len(calls)} times in one request; "
            "it must build it once (LAT-P186)"
        )

    async def test_route_hands_its_listing_to_the_completed_builder(
        self, client, monkeypatch
    ):
        """The caller half of the duplicate-removal, behavioural.

        Under the old wiring `_build_completed_tournament` was called as
        `(slug, db)` and went and rebuilt the listing itself. The route must pass
        down the copy it already has.
        """
        seen: dict = {}

        async def _build(db):
            return _listing(tournaments=[])

        async def _completed(slug, db, golf_data=None):
            seen["slug"] = slug
            seen["golf_data"] = golf_data
            return None

        monkeypatch.setattr(golf_route, "get_golf", _build)
        monkeypatch.setattr(golf_route, "_build_completed_tournament", _completed)

        resp = await client.get("/api/golf/tournaments/not-real")

        assert resp.status_code == 404
        assert seen["slug"] == "not-real"
        assert seen["golf_data"] is not None, (
            "the route discarded the listing it had just paid for and left "
            "`_build_completed_tournament` to rebuild its own — that is the second "
            "full rebuild this fix removed (LAT-P186)"
        )
        assert "pga_schedule" in seen["golf_data"], (
            "what gets handed down must be the listing itself — `pga_schedule` is "
            "the only key the completed builder reads off it"
        )

    def test_completed_builder_only_builds_when_it_was_given_nothing(self):
        """Callee half, by source shape.

        A behavioural version would need a DB stub that returns matched markets;
        with an empty stub the function early-returns before it ever reaches the
        schedule block, and the assertion would pass while proving nothing (the
        early-exit vacuity trap).
        """
        code = _strip_comments(inspect.getsource(golf_route._build_completed_tournament))

        assert "if golf_data is None:" in code, (
            "`_build_completed_tournament` must only build the listing when the "
            "caller did not give it one"
        )
        for line in code.splitlines():
            if "get_golf(" in line:
                assert "golf_data = await" in line, (
                    f"unexpected `get_golf(` call shape in "
                    f"`_build_completed_tournament`: {line.strip()!r}"
                )


class TestTheCacheStaysOut:
    """CERT-686's block, encoded so it cannot be silently undone."""

    def test_the_route_must_not_read_the_hourly_cache(self):
        """`get_golf_cached` serves `/api/golf` from a 7,200 s Redis key.

        Pointing the detail route at it is a one-word change that makes the page
        ~45x faster and silently makes the in-play winner probabilities up to an
        hour stale — DataGolf writes `current_probability` every 90 SECONDS, and
        `fuse_golf_live()` overlays position/score/thru/round but never
        `probability`. CERT-686 blocked exactly this. Anyone who wants it back
        needs a live-winner overlay and a settlement bypass, not a swap.
        """
        for fn in (golf_route.get_golf_tournament, golf_route._build_completed_tournament):
            code = _strip_comments(inspect.getsource(fn))
            assert "get_golf_cached" not in code, (
                f"`{fn.__name__}` is reading the hourly `bainluck:category:golf` "
                "cache. CERT-686 blocked that: it makes the in-play winner field "
                "up to an hour stale and keeps pre-settlement probabilities after "
                "the DB has a winner. See the note at the `get_golf` call site."
            )

    def test_the_comment_stripper_is_not_lying(self):
        """`getsource` guards go vacuous when the fix's own comments quote the
        anti-pattern. These comments name `get_golf_cached` repeatedly and on
        purpose, so if `_strip_comments` ever stopped working the guard above
        would match the explanation instead of the code — and FAIL confusingly,
        or worse, be "fixed" by deleting it.
        """
        raw = inspect.getsource(golf_route.get_golf_tournament)
        stripped = _strip_comments(raw)

        assert "get_golf_cached" in raw, (
            "the CERT-686 rationale has been deleted from the call site; it is the "
            "only thing telling the next reader why the fast path is refused"
        )
        assert "get_golf_cached" not in stripped, (
            "comment stripping regressed — the guard above is now reading prose"
        )
        assert len(stripped) < len(raw), "nothing was stripped; the helper is a no-op"
        assert "golf_data = await get_golf(db=db)" in stripped
