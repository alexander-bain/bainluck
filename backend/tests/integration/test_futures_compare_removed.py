"""`GET /api/futures/compare` is DELETED, and must stay deleted.

LAT-P086 (F1), Fable directive 2026-08-24 item 1 — Alex ruled removal rather
than repair, on zero consumers (frontend and iOS grepped in both the master and
the program worktree, 2026-08-24: no hits outside this route's own tests).

**Why removal and not a fix.** The route grouped every `FuturesMarket` sharing
a `canonical_market_key` and merged their outcomes into one comparison. That
key is `{sport}:{league}:{category}:{season}` by construction
(`compute_canonical_market_key`) — a category taxonomy built for calibration
cohort counting, with nothing in it that identifies a market. Comparing "how
different sources price the same market" across it compares markets that are
not the same market and were never claimed to be.

Measured live against production on 2026-08-24, HTTP **200** in 0.60 s, 61 KB:

    GET /api/futures/compare?key=entertainment::game_prop:2026
      source_markets ............ 449   (423 distinct names)
      sum of member outcomes .... 890
      outcomes RETURNED .......... 10

Members merged into that single comparison included "Will Jay Z release an
album in 2026?", "Will Justin Bieber perform at the 2026 Todo Mundo no Rio
music festival?", "Taylor Swift pregnant by March 31?", "Trump declassifies new
UFO files by December 31?", "Dune vs Avengers: Highest Rotten Tomatoes Score"
and "Yellow Submarine vs. Power Rangers: Map 2" — a music release, a football
transfer window's worth of celebrity props, a declassification date and an
esports map. Its ten merged "outcomes" read: `Yes`, `No`, `August 31`,
`June 12`, `May 31`, `April 30`, `Yellow Submarine`, `Power Rangers`,
`Dune: Part Three`, `Avengers: Doomsday`. Every Yes/No pair from 400+ unrelated
binary markets collapsed onto two rows, and the endpoint presented an esports
map name and a film title as competing answers to one question, each with a
probability.

There is no threshold to tune here: the merge identity is wrong, the route has
no callers, and the sibling site that shared the mistake (the league page's
`seen_canonical`) is repaired rather than removed because it has a job to do.
This one did not. Captured payload:
``docs/audits/latency/lat-p086-compare-specimen.json``.

Related: `events.py:101-157` (LAT-P038/#1769, the first site, pinned by
``test_search_futures_dedup_identity.py``) and
``test_league_futures_dedup_identity.py`` (the second).
"""

from __future__ import annotations

import inspect

from app.routes import futures as futures_routes


class TestCompareRouteIsGone:
    """The path now falls through to `GET /api/futures/{market_id}`.

    Not a 404: with `/compare` unregistered, `compare` is matched as a
    `market_id` path segment and rejected by *integer parsing*. That reason is
    the assertion worth making — a bare status check could not tell "the route
    is gone" from "the route is still there and rejected your query string",
    which is the shape of every 422 the old route produced when `key` was
    missing. So both tests read the failure `loc`, not just the code.
    """

    async def test_get_with_key_falls_through_to_market_id(self, client):
        resp = await client.get("/api/futures/compare?key=test:key")
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert [d["loc"] for d in detail] == [["path", "market_id"]], (
            "the compare route answered — it was deleted, not disabled"
        )
        assert detail[0]["type"] == "int_parsing"
        assert detail[0]["input"] == "compare"

    async def test_missing_key_is_not_what_is_rejected(self, client):
        """The old route's own 422 blamed `query.key`. This one cannot."""
        resp = await client.get("/api/futures/compare")
        assert resp.status_code == 422
        locs = [d["loc"] for d in resp.json()["detail"]]
        assert ["query", "key"] not in locs
        assert locs == [["path", "market_id"]]


def test_route_is_not_registered_on_the_router():
    paths = {
        getattr(r, "path", None) for r in futures_routes.router.routes
    }
    assert "/compare" not in paths


def test_handler_and_its_sole_helper_are_gone():
    """`_avg_probability` existed only to sort this route's merged outcomes."""
    assert not hasattr(futures_routes, "compare_futures_sources")
    assert not hasattr(futures_routes, "_avg_probability")


def test_module_source_has_no_canonical_key_grouping_left():
    src = inspect.getsource(futures_routes)
    assert "compare_futures_sources" not in src
    assert '"/compare"' not in src
